import hashlib
import json
import math
import random
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .hdvn_snapshot import canonical_json, sha256_file


OPPONENT_ARTIFACT_VERSION = "historical-opponent-model-v3"
SEED = 20260828
TEMPERATURES = (1.0,)
REACH_RATES = (0.0,)
REACH_TEMPERATURE = 0.30
COMPARATORS = {"live_provisional": (0.11, 0.15)}
PLAYER_PRIOR = (2.0, 2.0)
SHRINKAGE = 50.0
CHOICE_MINIMUM_LOG_LOSS_IMPROVEMENT = 0.01
SURVIVAL_MINIMUM_BRIER_IMPROVEMENT = 0.001
CALIBRATION_EDGES = (0.0, 0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0000001)


def fit_opponent_model(
    market_database,
    market_manifest,
    output_directory,
    *,
    expected_source_hash,
    expected_feature_hash,
    command,
    code_revision,
    seed=SEED,
    bootstrap_samples=200,
):
    if seed != SEED:
        raise ValueError(f"OPP-01 uses the frozen seed {SEED}")
    if bootstrap_samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    market_database = Path(market_database).resolve()
    market_manifest = Path(market_manifest).resolve()
    output_directory = Path(output_directory).resolve()
    model_path = output_directory / "opponent-model.json"
    report_path = output_directory / "validation-report.json"
    manifest_path = output_directory / "opponent-model.manifest.json"
    paths = (model_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable opponent-model output exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    source_manifest = _load_hashed_json(market_manifest, "market manifest")
    if source_manifest.get("source_snapshot_sha256") != expected_source_hash:
        raise ValueError("market and source snapshot hashes do not match")
    if source_manifest.get("feature_manifest_hash") != expected_feature_hash:
        raise ValueError("market and feature hashes do not match")
    database_record = source_manifest.get("files", {}).get(market_database.name)
    if database_record is None or sha256_file(market_database) != database_record["sha256"]:
        raise ValueError("market database hash mismatch")

    connection = sqlite3.connect(f"file:{market_database}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        training_choice = _fit_choice(connection)
        survival_model = _fit_survival(connection)
        validation_choice = _validate_choice(
            connection,
            training_choice["temperature"],
            training_choice["reach_rate"],
            seed=seed,
            bootstrap_samples=bootstrap_samples,
        )
        validation_survival = _validate_survival(
            connection,
            survival_model,
            seed=seed,
            bootstrap_samples=bootstrap_samples,
        )
    finally:
        connection.close()

    choice_pass = all(
        comparison["improvement"] >= CHOICE_MINIMUM_LOG_LOSS_IMPROVEMENT
        and comparison["paired_log_loss_difference"]["high"] < 0
        for comparison in validation_choice["comparisons"].values()
    )
    player_pass = (
        validation_survival["players"]["brier_improvement"]
        >= SURVIVAL_MINIMUM_BRIER_IMPROVEMENT
        and validation_survival["players"]["paired_brier_difference"]["high"] < 0
    )
    tier_pass = (
        validation_survival["tiers"]["brier_improvement"]
        >= SURVIVAL_MINIMUM_BRIER_IMPROVEMENT
        and validation_survival["tiers"]["paired_brier_difference"]["high"] < 0
    )
    gates = {
        "choice": choice_pass,
        "player_survival": player_pass,
        "tier_survival": tier_pass,
        "all_passed": choice_pass and player_pass and tier_pass,
    }
    status = "research" if gates["all_passed"] else "rejected"

    model = {
        "artifact_version": OPPONENT_ARTIFACT_VERSION,
        "status": status,
        "choice": training_choice,
        "survival": _serialize_survival_model(survival_model),
        "buckets": {
            "player_rank": "exact_integer_1_to_10",
            "player_gap": "exact_integer",
            "player_round": "exact_integer",
            "tier_rank": ["1", "2-3", "4-6", "7-10"],
            "tier_gap": ["1-2", "3-5", "6-9", "10+"],
            "tier_round": ["early", "middle", "late"],
        },
        "player_prior": list(PLAYER_PRIOR),
        "shrinkage": SHRINKAGE,
    }
    model_path.write_text(canonical_json(model) + "\n")
    report = {
        "artifact_version": OPPONENT_ARTIFACT_VERSION,
        "status": status,
        "train_seasons": [2021, 2022, 2023],
        "validation_seasons": [2024],
        "locked_test_loaded": False,
        "choice": validation_choice,
        "survival": validation_survival,
        "gates": gates,
        "limitations": [
            "population model only; no manager personalization",
            "choice rank is still market rank; this slice calibrates probabilities",
            "survival tiers are the top three remaining market players",
            "point-in-time historical projections are unavailable",
            "offline research only; no live callback integration",
        ],
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "artifact_version": OPPONENT_ARTIFACT_VERSION,
        "status": status,
        "source_snapshot_sha256": expected_source_hash,
        "feature_manifest_hash": expected_feature_hash,
        "market_manifest_hash": source_manifest["sha256"],
        "market_database_sha256": database_record["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "seed": seed,
        "train_seasons": [2021, 2022, 2023],
        "validation_seasons": [2024],
        "locked_test_loaded": False,
        "temperature_grid": list(TEMPERATURES),
        "reach_rate_grid": list(REACH_RATES),
        "reach_temperature": REACH_TEMPERATURE,
        "comparators": {name: list(values) for name, values in COMPARATORS.items()},
        "survival_prior": list(PLAYER_PRIOR),
        "survival_shrinkage": SHRINKAGE,
        "gates": gates,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (model_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_opponent_artifact(
        manifest_path,
        expected={
            "source_snapshot_sha256": expected_source_hash,
            "feature_manifest_hash": expected_feature_hash,
            "market_manifest_hash": source_manifest["sha256"],
            "status": status,
        },
    )
    for path in paths:
        path.chmod(0o444)
    return manifest


def load_opponent_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "opponent-model manifest")
    if manifest.get("status") not in {"research", "rejected"}:
        raise ValueError("opponent-model status is invalid")
    if manifest.get("train_seasons") != [2021, 2022, 2023]:
        raise ValueError("opponent-model train seasons mismatch")
    if manifest.get("validation_seasons") != [2024]:
        raise ValueError("opponent-model validation season mismatch")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("opponent-model artifact touched locked test")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"opponent-model file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"opponent-model context mismatch for {key}")
    return manifest

def load_opponent_model(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_opponent_artifact(manifest_path, expected=expected)
    try:
        model = json.loads((manifest_path.parent / "opponent-model.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("opponent model is malformed") from error
    if model.get("artifact_version") != OPPONENT_ARTIFACT_VERSION:
        raise ValueError("opponent model version mismatch")
    if model.get("status") != manifest["status"]:
        raise ValueError("opponent model status mismatch")
    if model.get("choice", {}).get("temperature") != 1.0:
        raise ValueError("opponent model choice temperature mismatch")
    if model.get("choice", {}).get("reach_rate") != 0.0:
        raise ValueError("opponent model choice reach rate mismatch")
    model["_survival_lookups"] = {
        name: {
            tuple(record["key"]): record["values"]
            for record in model["survival"][name]
        }
        for name in (
            "player_baseline",
            "player_model",
            "tier_baseline",
            "tier_model",
        )
    }
    return model


def predict_player_survival(model, *, market_rank, gap, position, round_):
    survival = model["survival"]
    lookups = model["_survival_lookups"]
    exact_rank = int(market_rank)
    exact_gap = int(gap)
    exact_round = int(round_)
    baseline_stat = lookups["player_baseline"].get(
        (exact_rank, exact_gap, exact_round)
    )
    baseline = _baseline_probability(baseline_stat, survival["player_global"])
    model_stat = lookups["player_model"].get(
        (exact_rank, exact_gap, exact_round, str(position).upper())
    )
    probability = _shrunk_probability(model_stat, baseline)
    return {
        "survives_to_next_pick": probability,
        "market_only_survival": baseline,
        "support": model_stat[1] if model_stat is not None else 0,
        "status": "offline_research",
    }


def predict_tier_survival(
    model,
    *,
    gap,
    round_,
    scoring_format,
    team_count,
):
    survival = model["survival"]
    lookups = model["_survival_lookups"]
    gap_bucket = _gap_bucket(int(gap))
    round_bucket = _round_bucket(int(round_))
    baseline_stat = lookups["tier_baseline"].get((gap_bucket,))
    baseline = _baseline_probability(baseline_stat, survival["tier_global"])
    model_stat = lookups["tier_model"].get(
        (gap_bucket, round_bucket, str(scoring_format), int(team_count))
    )
    probability = _shrunk_probability(model_stat, baseline)
    expected_remaining = _shrunk_remaining(
        model_stat,
        baseline_stat,
        survival["tier_global"],
    )
    return {
        "survives_to_next_pick": probability,
        "market_only_survival": baseline,
        "expected_remaining": expected_remaining,
        "support": model_stat[1] if model_stat is not None else 0,
        "status": "offline_research",
    }


def _fit_choice(connection):
    losses = np.zeros((len(TEMPERATURES), len(REACH_RATES)), dtype=np.float64)
    scored = missing = drafts = 0
    for draft in _iter_drafts(connection, (2021, 2022, 2023)):
        drafts += 1
        log_weights = _log_weight_matrix(draft["adp"], TEMPERATURES)
        log_reach_weights = _log_weight_matrix(
            draft["adp"], (REACH_TEMPERATURE,)
        )
        log_sums = _logsumexp_columns(log_weights)
        log_reach_sum = _logsumexp_columns(log_reach_weights)
        available = np.ones(len(draft["player_ids"]), dtype=bool)
        for pick in draft["picks"]:
            index = draft["index"].get(pick["player_id"])
            if index is None:
                missing += 1
                continue
            if not available[index]:
                raise ValueError(f"duplicate market pick in {draft['draft_id']}")
            log_sharp = log_weights[index] - log_sums
            log_reach = log_reach_weights[index, 0] - log_reach_sum[0]
            for reach_index, reach_rate in enumerate(REACH_RATES):
                if reach_rate == 0:
                    log_probability = log_sharp
                else:
                    log_probability = np.logaddexp(
                        math.log1p(-reach_rate) + log_sharp,
                        math.log(reach_rate) + log_reach,
                    )
                losses[:, reach_index] -= log_probability
            scored += 1
            available[index] = False
            log_sums = _subtract_log_weight(
                log_sums,
                log_weights[index],
                log_weights[available],
            )
            log_reach_sum = _subtract_log_weight(
                log_reach_sum,
                log_reach_weights[index],
                log_reach_weights[available],
            )
    if not scored:
        raise ValueError("opponent choice fitting has no supported picks")
    candidates = [
        (float(losses[t, r] / scored), TEMPERATURES[t], REACH_RATES[r])
        for t in range(len(TEMPERATURES))
        for r in range(len(REACH_RATES))
    ]
    loss, temperature, reach_rate = min(candidates)
    return {
        "temperature": temperature,
        "reach_rate": reach_rate,
        "reach_temperature": REACH_TEMPERATURE,
        "mean_log_loss": loss,
        "scored_picks": scored,
        "missing_board_picks": missing,
        "drafts": drafts,
    }


def _validate_choice(connection, temperature, reach_rate, *, seed, bootstrap_samples):
    specifications = {
        "fitted": (temperature, reach_rate),
        **COMPARATORS,
    }
    totals = {
        name: {
            "log_loss": 0.0,
            "brier": 0.0,
            "scored": 0,
            "calibration": _calibration_state(),
        }
        for name in specifications
    }
    draft_losses = {name: {} for name in specifications}
    ranks = Counter()
    missing = total = drafts = 0
    contexts = Counter()
    for draft in _iter_drafts(connection, (2024,)):
        drafts += 1
        contexts[(draft["scoring_format"], draft["team_count"])] += 1
        unique_temperatures = tuple(
            sorted({value[0] for value in specifications.values()} | {REACH_TEMPERATURE})
        )
        log_weights = _log_weight_matrix(draft["adp"], unique_temperatures)
        by_temperature = {
            value: log_weights[:, index]
            for index, value in enumerate(unique_temperatures)
        }
        available = np.ones(len(draft["player_ids"]), dtype=bool)
        per_draft = {name: [0.0, 0] for name in specifications}
        for pick in draft["picks"]:
            total += 1
            index = draft["index"].get(pick["player_id"])
            if index is None:
                missing += 1
                continue
            if not available[index]:
                raise ValueError(f"duplicate market pick in {draft['draft_id']}")
            available_indices = np.flatnonzero(available)
            market_rank = int(np.flatnonzero(available_indices == index)[0]) + 1
            ranks["top_1"] += market_rank <= 1
            ranks["top_3"] += market_rank <= 3
            ranks["top_6"] += market_rank <= 6
            for name, (model_temperature, model_reach) in specifications.items():
                sharp = _softmax_logs(
                    by_temperature[model_temperature][available_indices]
                )
                reach = _softmax_logs(
                    by_temperature[REACH_TEMPERATURE][available_indices]
                )
                probabilities = (1 - model_reach) * sharp + model_reach * reach
                selected_local = int(np.flatnonzero(available_indices == index)[0])
                selected_probability = float(probabilities[selected_local])
                loss = -math.log(max(selected_probability, 1e-300))
                totals[name]["log_loss"] += loss
                totals[name]["brier"] += float(np.sum(probabilities * probabilities) - 2 * selected_probability + 1)
                totals[name]["scored"] += 1
                per_draft[name][0] += loss
                per_draft[name][1] += 1
                _add_multiclass_calibration(
                    totals[name]["calibration"], probabilities, selected_local
                )
            available[index] = False
        for name, (loss, count) in per_draft.items():
            if count:
                draft_losses[name][draft["draft_id"]] = (loss, count)
    metrics = {}
    for name, values in totals.items():
        count = values["scored"]
        metrics[name] = {
            "mean_log_loss": values["log_loss"] / count,
            "multiclass_brier": values["brier"] / count,
            "scored_picks": count,
            "calibration": _finish_calibration(values["calibration"]),
            "temperature": specifications[name][0],
            "reach_rate": specifications[name][1],
        }
    comparisons = {}
    for offset, comparator in enumerate(COMPARATORS):
        differences = {
            draft_id: (
                draft_losses["fitted"][draft_id][0] - draft_losses[comparator][draft_id][0],
                draft_losses["fitted"][draft_id][1],
            )
            for draft_id in draft_losses["fitted"]
            if draft_id in draft_losses[comparator]
        }
        interval = _clustered_difference(
            differences,
            seed=seed + offset,
            samples=bootstrap_samples,
        )
        comparisons[comparator] = {
            "improvement": metrics[comparator]["mean_log_loss"] - metrics["fitted"]["mean_log_loss"],
            "paired_log_loss_difference": interval,
        }
    scored = metrics["fitted"]["scored_picks"]
    return {
        "drafts": drafts,
        "total_picks": total,
        "missing_board_picks": missing,
        "coverage": scored / total if total else 0.0,
        "models": metrics,
        "comparisons": comparisons,
        "top_k_accuracy": {
            "top_1": ranks["top_1"] / scored,
            "top_3": ranks["top_3"] / scored,
            "top_6": ranks["top_6"] / scored,
        },
        "contexts": [
            {"scoring_format": key[0], "team_count": key[1], "drafts": count}
            for key, count in sorted(contexts.items())
        ],
    }


def _fit_survival(connection):
    stats = {
        "player_global": [0.0, 0],
        "player_baseline": defaultdict(lambda: [0.0, 0]),
        "player_model": defaultdict(lambda: [0.0, 0]),
        "tier_global": [0.0, 0, 0.0],
        "tier_baseline": defaultdict(lambda: [0.0, 0, 0.0]),
        "tier_model": defaultdict(lambda: [0.0, 0, 0.0]),
    }
    drafts = states = player_samples = 0
    for draft in _iter_drafts(connection, (2021, 2022, 2023)):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            gap = _gap_bucket(sample["gap"])
            round_ = _round_bucket(sample["round"])
            exact_gap = int(sample["gap"])
            exact_round = int(sample["round"])
            for player in sample["players"]:
                rank = int(player["rank"])
                label = float(player["survived"])
                _add_stat(stats["player_global"], label)
                _add_stat(
                    stats["player_baseline"][(rank, exact_gap, exact_round)],
                    label,
                )
                _add_stat(
                    stats["player_model"][
                        (rank, exact_gap, exact_round, player["position"])
                    ],
                    label,
                )
                player_samples += 1
            tier_label = float(sample["tier_remaining"] > 0)
            tier_key = (gap,)
            tier_model_key = (gap, round_, sample["scoring_format"], sample["team_count"])
            _add_tier_stat(stats["tier_global"], tier_label, sample["tier_remaining"])
            _add_tier_stat(stats["tier_baseline"][tier_key], tier_label, sample["tier_remaining"])
            _add_tier_stat(stats["tier_model"][tier_model_key], tier_label, sample["tier_remaining"])
    stats["counts"] = {"drafts": drafts, "states": states, "player_samples": player_samples}
    return stats


def _validate_survival(connection, model, *, seed, bootstrap_samples):
    player = _binary_metric_state()
    player_baseline = _binary_metric_state()
    tier = _binary_metric_state()
    tier_baseline = _binary_metric_state()
    tier_remaining_error = [0.0, 0]
    player_draft_differences = defaultdict(lambda: [0.0, 0])
    tier_draft_differences = defaultdict(lambda: [0.0, 0])
    contexts = Counter()
    drafts = states = 0
    for draft in _iter_drafts(connection, (2024,)):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            contexts[(sample["scoring_format"], sample["team_count"], _round_bucket(sample["round"]), _gap_bucket(sample["gap"]))] += 1
            gap = _gap_bucket(sample["gap"])
            exact_gap = int(sample["gap"])
            exact_round = int(sample["round"])
            round_ = _round_bucket(sample["round"])
            for target in sample["players"]:
                rank = int(target["rank"])
                baseline_probability = _baseline_probability(
                    model["player_baseline"].get(
                        (rank, exact_gap, exact_round)
                    ),
                    model["player_global"],
                )
                probability = _shrunk_probability(
                    model["player_model"].get(
                        (rank, exact_gap, exact_round, target["position"])
                    ),
                    baseline_probability,
                )
                actual = float(target["survived"])
                _add_binary_metric(player, actual, probability)
                _add_binary_metric(player_baseline, actual, baseline_probability)
                difference = (probability - actual) ** 2 - (baseline_probability - actual) ** 2
                player_draft_differences[draft["draft_id"]][0] += difference
                player_draft_differences[draft["draft_id"]][1] += 1
            tier_actual = float(sample["tier_remaining"] > 0)
            tier_base_probability = _baseline_probability(
                model["tier_baseline"].get((gap,)),
                model["tier_global"],
            )
            tier_probability = _shrunk_probability(
                model["tier_model"].get((gap, round_, sample["scoring_format"], sample["team_count"])),
                tier_base_probability,
            )
            _add_binary_metric(tier, tier_actual, tier_probability)
            _add_binary_metric(tier_baseline, tier_actual, tier_base_probability)
            difference = (tier_probability - tier_actual) ** 2 - (tier_base_probability - tier_actual) ** 2
            tier_draft_differences[draft["draft_id"]][0] += difference
            tier_draft_differences[draft["draft_id"]][1] += 1
            expected_remaining = _shrunk_remaining(
                model["tier_model"].get((gap, round_, sample["scoring_format"], sample["team_count"])),
                model["tier_baseline"].get((gap,)),
                model["tier_global"],
            )
            tier_remaining_error[0] += (expected_remaining - sample["tier_remaining"]) ** 2
            tier_remaining_error[1] += 1
    player_metrics = _finish_binary_metric(player)
    player_baseline_metrics = _finish_binary_metric(player_baseline)
    tier_metrics = _finish_binary_metric(tier)
    tier_baseline_metrics = _finish_binary_metric(tier_baseline)
    return {
        "drafts": drafts,
        "states": states,
        "players": {
            "model": player_metrics,
            "baseline": player_baseline_metrics,
            "brier_improvement": player_baseline_metrics["brier"] - player_metrics["brier"],
            "paired_brier_difference": _clustered_difference(
                player_draft_differences,
                seed=seed + 10,
                samples=bootstrap_samples,
            ),
        },
        "tiers": {
            "model": tier_metrics,
            "baseline": tier_baseline_metrics,
            "brier_improvement": tier_baseline_metrics["brier"] - tier_metrics["brier"],
            "paired_brier_difference": _clustered_difference(
                tier_draft_differences,
                seed=seed + 11,
                samples=bootstrap_samples,
            ),
            "expected_remaining_rmse": math.sqrt(tier_remaining_error[0] / tier_remaining_error[1]),
        },
        "contexts": [
            {
                "scoring_format": key[0],
                "team_count": key[1],
                "round_bucket": key[2],
                "gap_bucket": key[3],
                "states": count,
            }
            for key, count in sorted(contexts.items())
        ],
    }


def _iter_drafts(connection, seasons):
    placeholders = ",".join("?" for _ in seasons)
    boards = connection.execute(
        f"""
        SELECT target_draft_id, season, scoring_format, team_count
        FROM boards
        WHERE sparse_context = 0 AND season IN ({placeholders})
        ORDER BY season, target_draft_id
        """,
        tuple(seasons),
    )
    for board in boards:
        player_rows = connection.execute(
            """
            SELECT player_id, position, adp FROM players
            WHERE target_draft_id = ? ORDER BY rank, player_id
            """,
            (board["target_draft_id"],),
        ).fetchall()
        if not player_rows:
            continue
        pick_rows = connection.execute(
            """
            SELECT pick_no, roster_id, player_id FROM market_picks
            WHERE target_draft_id = ? ORDER BY pick_no
            """,
            (board["target_draft_id"],),
        ).fetchall()
        player_ids = tuple(row["player_id"] for row in player_rows)
        yield {
            "draft_id": board["target_draft_id"],
            "season": int(board["season"]),
            "scoring_format": board["scoring_format"],
            "team_count": int(board["team_count"]),
            "player_ids": player_ids,
            "positions": tuple(row["position"] or "UNKNOWN" for row in player_rows),
            "adp": np.asarray([row["adp"] for row in player_rows], dtype=np.float64),
            "index": {player_id: index for index, player_id in enumerate(player_ids)},
            "picks": tuple(
                {
                    "pick_no": int(row["pick_no"]),
                    "roster_id": row["roster_id"],
                    "player_id": row["player_id"],
                }
                for row in pick_rows
            ),
        }


def _iter_survival_samples(draft, target_count=10):
    if target_count < 1:
        raise ValueError("survival target count must be positive")
    picks = draft["picks"]
    next_same = [None] * len(picks)
    next_by_roster = {}
    for index in range(len(picks) - 1, -1, -1):
        roster_id = picks[index]["roster_id"]
        if roster_id is not None:
            next_same[index] = next_by_roster.get(roster_id)
            next_by_roster[roster_id] = index
    available = np.ones(len(draft["player_ids"]), dtype=bool)
    for index, pick in enumerate(picks):
        player_index = draft["index"].get(pick["player_id"])
        if player_index is not None:
            if not available[player_index]:
                raise ValueError(f"duplicate market pick in {draft['draft_id']}")
            available[player_index] = False
        next_index = next_same[index]
        if next_index is None:
            continue
        targets = np.flatnonzero(available)[:target_count]
        if not len(targets):
            continue
        intervening = {
            picks[future]["player_id"]
            for future in range(index + 1, next_index)
            if picks[future]["player_id"] is not None
        }
        tier_targets = targets[:3]
        yield {
            "gap": next_index - index - 1,
            "round": math.ceil(pick["pick_no"] / draft["team_count"]),
            "scoring_format": draft["scoring_format"],
            "team_count": draft["team_count"],
            "players": tuple(
                {
                    "rank": rank,
                    "position": draft["positions"][target],
                    "survived": draft["player_ids"][target] not in intervening,
                }
                for rank, target in enumerate(targets, 1)
            ),
            "tier_remaining": sum(
                draft["player_ids"][target] not in intervening for target in tier_targets
            ),
        }


def _log_weight_matrix(adp, temperatures):
    return (
        -np.log(np.maximum(adp, 1e-12))[:, None]
        / np.asarray(temperatures, dtype=np.float64)[None, :]
    )


def _softmax_logs(values):
    shifted = values - values.max()
    weights = np.exp(shifted)
    return weights / weights.sum()


def _logsumexp_columns(values):
    maximum = values.max(axis=0)
    return maximum + np.log(np.exp(values - maximum).sum(axis=0))


def _subtract_log_weight(log_sums, removed, remaining):
    ratios = np.exp(np.minimum(removed - log_sums, 0.0))
    result = log_sums.copy()
    stable = ratios < 1 - 1e-12
    result[stable] += np.log1p(-ratios[stable])
    for index in np.flatnonzero(~stable):
        result[index] = (
            _logsumexp_columns(remaining[:, index:index + 1])[0]
            if len(remaining)
            else -math.inf
        )
    return result


def _rank_bucket(rank):
    if rank == 1:
        return "1"
    if rank <= 3:
        return "2-3"
    if rank <= 6:
        return "4-6"
    return "7-10"


def _gap_bucket(gap):
    if gap <= 2:
        return "1-2"
    if gap <= 5:
        return "3-5"
    if gap <= 9:
        return "6-9"
    return "10+"


def _round_bucket(round_):
    if round_ <= 3:
        return "early"
    if round_ <= 8:
        return "middle"
    return "late"


def _add_stat(stat, label):
    stat[0] += label
    stat[1] += 1


def _add_tier_stat(stat, label, remaining):
    stat[0] += label
    stat[1] += 1
    stat[2] += remaining


def _baseline_probability(stat, global_stat):
    successes, count = (stat if stat is not None else global_stat)[:2]
    return (successes + PLAYER_PRIOR[0]) / (count + sum(PLAYER_PRIOR))


def _shrunk_probability(stat, baseline_probability):
    if stat is None:
        return baseline_probability
    return (stat[0] + SHRINKAGE * baseline_probability) / (stat[1] + SHRINKAGE)


def _shrunk_remaining(stat, baseline_stat, global_stat):
    source = baseline_stat if baseline_stat is not None else global_stat
    baseline_mean = source[2] / source[1] if source[1] else 0.0
    if stat is None:
        return baseline_mean
    return (stat[2] + SHRINKAGE * baseline_mean) / (stat[1] + SHRINKAGE)


def _binary_metric_state():
    return {
        "count": 0,
        "log_loss": 0.0,
        "brier": 0.0,
        "calibration": _calibration_state(),
    }


def _add_binary_metric(state, actual, probability):
    probability = min(max(float(probability), 1e-15), 1 - 1e-15)
    state["count"] += 1
    state["log_loss"] -= actual * math.log(probability) + (1 - actual) * math.log1p(-probability)
    state["brier"] += (probability - actual) ** 2
    index = min(int(probability * 10), 9)
    state["calibration"][index][0] += 1
    state["calibration"][index][1] += probability
    state["calibration"][index][2] += actual


def _finish_binary_metric(state):
    count = state["count"]
    return {
        "count": count,
        "log_loss": state["log_loss"] / count,
        "brier": state["brier"] / count,
        "calibration": [
            {
                "lower": index / 10,
                "upper": (index + 1) / 10,
                "count": values[0],
                "mean_prediction": values[1] / values[0],
                "observed_rate": values[2] / values[0],
            }
            for index, values in enumerate(state["calibration"])
            if values[0]
        ],
    }


def _calibration_state():
    return [[0, 0.0, 0.0] for _ in range(10)]


def _add_multiclass_calibration(state, probabilities, selected_index):
    indices = np.searchsorted(CALIBRATION_EDGES[1:], probabilities, side="right")
    counts = np.bincount(indices, minlength=len(state))
    sums = np.bincount(indices, weights=probabilities, minlength=len(state))
    for index in range(len(state)):
        state[index][0] += int(counts[index])
        state[index][1] += float(sums[index])
    state[int(indices[selected_index])][2] += 1.0


def _finish_calibration(state):
    return [
        {
            "lower": CALIBRATION_EDGES[index],
            "upper": CALIBRATION_EDGES[index + 1],
            "count": values[0],
            "mean_prediction": values[1] / values[0],
            "observed_rate": values[2] / values[0],
        }
        for index, values in enumerate(state)
        if values[0]
    ]


def _clustered_difference(clusters, *, seed, samples, confidence=0.95):
    keys = sorted(clusters)
    if not keys:
        raise ValueError("clustered interval has no drafts")
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        total = count = 0
        for _ in keys:
            difference, observations = clusters[rng.choice(keys)]
            total += difference
            count += observations
        values.append(total / count)
    values.sort()
    total = sum(value[0] for value in clusters.values())
    count = sum(value[1] for value in clusters.values())
    tail = (1 - confidence) / 2
    return {
        "estimate": total / count,
        "low": values[max(0, int(tail * samples))],
        "high": values[min(samples - 1, math.ceil((1 - tail) * samples) - 1)],
        "samples": samples,
        "seed": seed,
        "drafts": len(keys),
    }


def _serialize_survival_model(model):
    return {
        "counts": model["counts"],
        "player_global": model["player_global"],
        "player_baseline": _serialize_stats(model["player_baseline"]),
        "player_model": _serialize_stats(model["player_model"]),
        "tier_global": model["tier_global"],
        "tier_baseline": _serialize_stats(model["tier_baseline"]),
        "tier_model": _serialize_stats(model["tier_model"]),
    }


def _serialize_stats(stats):
    return [
        {"key": list(key), "values": values}
        for key, values in sorted(stats.items())
    ]



def _serialized_stat(records, key):
    target = list(key)
    return next(
        (record["values"] for record in records if record["key"] == target),
        None,
    )

def _load_hashed_json(path, label):
    try:
        manifest = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    stored = manifest.get("sha256")
    body = {key: value for key, value in manifest.items() if key != "sha256"}
    if stored != hashlib.sha256(canonical_json(body).encode()).hexdigest():
        raise ValueError(f"{label} hash mismatch")
    return manifest
