import hashlib
import json
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .hdvn_snapshot import canonical_json, sha256_file
from .opponent_model import (
    _gap_bucket,
    _iter_drafts,
    _round_bucket,
    load_opponent_artifact,
    load_opponent_model,
    predict_player_survival,
)


REPLAY_ARTIFACT_VERSION = "historical-wait-reach-replay-v1"
SAFE_THRESHOLD = 0.70
URGENT_THRESHOLD = 0.30
LIVE_TEMPERATURE = 0.11
LIVE_REACH_RATE = 0.15
REACH_TEMPERATURE = 0.30
MINIMUM_FALSE_SAFE_IMPROVEMENT = 0.02
MAXIMUM_SAFE_COVERAGE_LOSS = 0.10
SEED = 20260828
METHODS = ("market", "historical_player", "live_modal_hazard")


def run_wait_reach_replay(
    market_database,
    opponent_manifest,
    output_directory,
    *,
    command,
    code_revision,
    seed=SEED,
    bootstrap_samples=200,
):
    if seed != SEED:
        raise ValueError(f"OPP-02 uses the frozen seed {SEED}")
    if bootstrap_samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    market_database = Path(market_database).resolve()
    opponent_manifest = Path(opponent_manifest).resolve()
    output_directory = Path(output_directory).resolve()
    predictions_path = output_directory / "wait-reach-predictions-2024.parquet"
    report_path = output_directory / "wait-reach-report.json"
    manifest_path = output_directory / "wait-reach.manifest.json"
    paths = (predictions_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable wait-reach output exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    opponent_artifact = load_opponent_artifact(opponent_manifest)
    opponent_model = load_opponent_model(opponent_manifest)
    opponent_report = json.loads(
        (opponent_manifest.parent / "validation-report.json").read_text()
    )
    if opponent_report.get("gates", {}).get("player_survival") is not True:
        raise ValueError("OPP-02 requires a passed exact-player survival component")
    if opponent_artifact["temperature_grid"] != [1.0] or opponent_artifact["reach_rate_grid"] != [0.0]:
        raise ValueError("OPP-02 requires the fixed-parameter OPP-01 artifact")
    if sha256_file(market_database) != opponent_artifact["market_database_sha256"]:
        raise ValueError("wait-reach market database hash mismatch")

    metrics = {method: _metric_state() for method in METHODS}
    draft_differences = {
        "historical_player": defaultdict(lambda: [0.0, 0]),
        "live_modal_hazard": defaultdict(lambda: [0.0, 0]),
    }
    contexts = Counter()
    drafts = states = targets = 0
    writer = None
    temporary = predictions_path.with_suffix(predictions_path.suffix + ".tmp")
    batch = []
    connection = sqlite3.connect(f"file:{market_database}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        for draft in _iter_drafts(connection, (2024,)):
            drafts += 1
            if drafts % 250 == 0:
                print(
                    f"wait-reach replay: {drafts} drafts, {states} states, "
                    f"{targets} targets",
                    file=sys.stderr,
                    flush=True,
                )
            for state in _iter_replay_states(draft):
                states += 1
                context_key = (
                    state["scoring_format"],
                    state["team_count"],
                    _round_bucket(state["round"]),
                    _gap_bucket(state["gap"]),
                )
                contexts[context_key] += 1
                live_survivals = _modal_hazard_survivals(
                    state["available_adp"],
                    state["gap"],
                    len(state["targets"]),
                )
                for target_index, target in enumerate(state["targets"]):
                    targets += 1
                    prediction = predict_player_survival(
                        opponent_model,
                        market_rank=target["rank"],
                        gap=state["gap"],
                        position=target["position"],
                        round_=state["round"],
                    )
                    probabilities = {
                        "market": prediction["market_only_survival"],
                        "historical_player": prediction["survives_to_next_pick"],
                        "live_modal_hazard": live_survivals[target_index],
                    }
                    actual = float(target["survived"])
                    market_error = (
                        probabilities["market"] - actual
                    ) ** 2
                    for method, probability in probabilities.items():
                        _add_metric(
                            metrics[method],
                            actual,
                            probability,
                            target["fallback_rank_loss"],
                            target["elimination_offset"],
                        )
                        if method != "market":
                            difference = (probability - actual) ** 2 - market_error
                            draft_differences[method][draft["draft_id"]][0] += difference
                            draft_differences[method][draft["draft_id"]][1] += 1
                    batch.append({
                        "draft_id": draft["draft_id"],
                        "season": 2024,
                        "pick_no": state["pick_no"],
                        "roster_id": state["roster_id"],
                        "gap": state["gap"],
                        "round": state["round"],
                        "scoring_format": state["scoring_format"],
                        "team_count": state["team_count"],
                        "player_id": target["player_id"],
                        "position": target["position"],
                        "market_rank": target["rank"],
                        "survived": target["survived"],
                        "elimination_offset": target["elimination_offset"],
                        "fallback_rank_loss": target["fallback_rank_loss"],
                        "market_survival": probabilities["market"],
                        "historical_player_survival": probabilities["historical_player"],
                        "live_modal_hazard_survival": probabilities["live_modal_hazard"],
                    })
                    if len(batch) >= 50_000:
                        writer = _write_batch(batch, temporary, writer, pa, pq)
                        batch.clear()
        if batch:
            writer = _write_batch(batch, temporary, writer, pa, pq)
        if writer is None:
            raise ValueError("wait-reach replay produced no predictions")
        writer.close()
        writer = None
        temporary.replace(predictions_path)
    except BaseException:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    finished = {method: _finish_metric(state) for method, state in metrics.items()}
    paired = {
        method: _clustered_difference(
            draft_differences[method],
            seed=seed + offset,
            samples=bootstrap_samples,
        )
        for offset, method in enumerate(("historical_player", "live_modal_hazard"))
    }
    historical = finished["historical_player"]
    market = finished["market"]
    false_safe_improvement = market["false_safe_rate"] - historical["false_safe_rate"]
    safe_coverage_loss = market["safe_coverage"] - historical["safe_coverage"]
    gate = {
        "false_safe_improvement": false_safe_improvement,
        "safe_coverage_loss": safe_coverage_loss,
        "paired_brier_difference": paired["historical_player"],
        "passes": (
            false_safe_improvement >= MINIMUM_FALSE_SAFE_IMPROVEMENT
            and safe_coverage_loss <= MAXIMUM_SAFE_COVERAGE_LOSS
            and paired["historical_player"]["high"] < 0
        ),
    }
    status = "research" if gate["passes"] else "rejected"
    report = {
        "artifact_version": REPLAY_ARTIFACT_VERSION,
        "status": status,
        "season": 2024,
        "seen_validation_diagnostic": True,
        "locked_test_loaded": False,
        "thresholds": {"safe": SAFE_THRESHOLD, "urgent": URGENT_THRESHOLD},
        "counts": {"drafts": drafts, "states": states, "targets": targets},
        "methods": finished,
        "paired_brier_differences": paired,
        "gate": gate,
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
        "limitations": [
            "2024 is seen OPP-01 validation data; this is downstream diagnostic evidence",
            "live comparator is the conditional modal-hazard approximation, not full rollouts",
            "fallback loss uses market-rank distance, not projected roster value",
            "no manager personalization or tier decision claim",
            "offline only; no live integration",
        ],
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "artifact_version": REPLAY_ARTIFACT_VERSION,
        "status": status,
        "opponent_manifest_hash": opponent_artifact["sha256"],
        "market_database_sha256": opponent_artifact["market_database_sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "seed": seed,
        "season": 2024,
        "seen_validation_diagnostic": True,
        "locked_test_loaded": False,
        "methods": list(METHODS),
        "safe_threshold": SAFE_THRESHOLD,
        "urgent_threshold": URGENT_THRESHOLD,
        "gate": gate,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (predictions_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_wait_reach_artifact(
        manifest_path,
        expected={
            "opponent_manifest_hash": opponent_artifact["sha256"],
            "status": status,
        },
    )
    for path in paths:
        path.chmod(0o444)
    return manifest


def load_wait_reach_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "wait-reach manifest")
    if manifest.get("status") not in {"research", "rejected"}:
        raise ValueError("wait-reach status is invalid")
    if manifest.get("season") != 2024 or manifest.get("seen_validation_diagnostic") is not True:
        raise ValueError("wait-reach diagnostic season mismatch")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("wait-reach artifact touched locked test")
    if manifest.get("methods") != list(METHODS):
        raise ValueError("wait-reach method contract mismatch")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"wait-reach file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"wait-reach context mismatch for {key}")
    return manifest


def _iter_replay_states(draft):
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
        available_indices = np.flatnonzero(available)
        targets = available_indices[:10]
        if not len(targets):
            continue
        intervening = [
            picks[future]["player_id"]
            for future in range(index + 1, next_index)
            if picks[future]["player_id"] is not None
        ]
        intervening_set = set(intervening)
        best_remaining_rank = next(
            (
                rank
                for rank, candidate in enumerate(available_indices, 1)
                if draft["player_ids"][candidate] not in intervening_set
            ),
            len(available_indices) + 1,
        )
        target_rows = []
        for rank, target in enumerate(targets, 1):
            player_id = draft["player_ids"][target]
            survived = player_id not in intervening_set
            elimination_offset = (
                intervening.index(player_id) + 1 if not survived else None
            )
            target_rows.append({
                "player_id": player_id,
                "position": draft["positions"][target],
                "rank": rank,
                "survived": survived,
                "elimination_offset": elimination_offset,
                "fallback_rank_loss": (
                    max(0, best_remaining_rank - rank) if not survived else None
                ),
            })
        yield {
            "pick_no": pick["pick_no"],
            "roster_id": pick["roster_id"],
            "gap": next_index - index - 1,
            "round": math.ceil(pick["pick_no"] / draft["team_count"]),
            "scoring_format": draft["scoring_format"],
            "team_count": draft["team_count"],
            "available_adp": draft["adp"][available_indices],
            "targets": tuple(target_rows),
        }


def _modal_hazard_survival(adp, target_index, gap):
    if target_index < 0:
        raise ValueError("modal hazard target rank is outside the available board")
    probabilities = _modal_hazard_survivals(adp, gap, target_index + 1)
    return probabilities[target_index]


def _modal_hazard_survivals(adp, gap, target_count):
    adp = np.asarray(adp, dtype=np.float64)
    if not 0 <= target_count <= len(adp):
        raise ValueError("modal hazard target count is outside the available board")
    steps = min(int(gap), len(adp) - 1)
    if steps <= 0:
        return np.ones(target_count, dtype=np.float64)
    log_sharp = -np.log(np.maximum(adp, 1e-12)) / LIVE_TEMPERATURE
    log_reach = -np.log(np.maximum(adp, 1e-12)) / REACH_TEMPERATURE
    sharp_tail = _tail_logsumexp(log_sharp)
    reach_tail = _tail_logsumexp(log_reach)
    survivals = np.ones(target_count, dtype=np.float64)
    for target_index in range(target_count):
        for removed in range(steps):
            sharp_denominator = _conditional_log_denominator(
                log_sharp, sharp_tail, target_index, removed
            )
            reach_denominator = _conditional_log_denominator(
                log_reach, reach_tail, target_index, removed
            )
            probability = (
                (1 - LIVE_REACH_RATE)
                * math.exp(log_sharp[target_index] - sharp_denominator)
                + LIVE_REACH_RATE
                * math.exp(log_reach[target_index] - reach_denominator)
            )
            survivals[target_index] *= 1 - probability
    return np.clip(survivals, 0.0, 1.0)


def _tail_logsumexp(values):
    result = np.empty(len(values) + 1, dtype=np.float64)
    result[:-1] = np.logaddexp.accumulate(values[::-1])[::-1]
    result[-1] = -math.inf
    return result


def _conditional_log_denominator(values, tails, target, removed):
    if removed < target:
        return float(tails[removed])
    return float(np.logaddexp(values[target], tails[removed + 1]))


def _metric_state():
    return {
        "count": 0,
        "brier": 0.0,
        "log_loss": 0.0,
        "safe": 0,
        "false_safe": 0,
        "urgent": 0,
        "false_urgent": 0,
        "false_safe_fallback_loss": 0.0,
        "false_safe_fallback_count": 0,
        "false_safe_elimination_offset": 0.0,
        "calibration": [[0, 0.0, 0.0] for _ in range(10)],
    }


def _add_metric(state, actual, probability, fallback_loss, elimination_offset):
    probability = min(max(float(probability), 1e-15), 1 - 1e-15)
    state["count"] += 1
    state["brier"] += (probability - actual) ** 2
    state["log_loss"] -= actual * math.log(probability) + (1 - actual) * math.log1p(-probability)
    bucket = min(int(probability * 10), 9)
    state["calibration"][bucket][0] += 1
    state["calibration"][bucket][1] += probability
    state["calibration"][bucket][2] += actual
    if probability >= SAFE_THRESHOLD:
        state["safe"] += 1
        if not actual:
            state["false_safe"] += 1
            if fallback_loss is not None:
                state["false_safe_fallback_loss"] += fallback_loss
                state["false_safe_fallback_count"] += 1
            if elimination_offset is not None:
                state["false_safe_elimination_offset"] += elimination_offset
    if probability <= URGENT_THRESHOLD:
        state["urgent"] += 1
        state["false_urgent"] += int(bool(actual))


def _finish_metric(state):
    count = state["count"]
    safe = state["safe"]
    urgent = state["urgent"]
    false_safe = state["false_safe"]
    return {
        "count": count,
        "brier": state["brier"] / count,
        "log_loss": state["log_loss"] / count,
        "safe_coverage": safe / count,
        "false_safe_rate": false_safe / safe if safe else None,
        "urgent_coverage": urgent / count,
        "false_urgent_rate": state["false_urgent"] / urgent if urgent else None,
        "false_safe_mean_fallback_rank_loss": (
            state["false_safe_fallback_loss"] / state["false_safe_fallback_count"]
            if state["false_safe_fallback_count"]
            else None
        ),
        "false_safe_mean_elimination_offset": (
            state["false_safe_elimination_offset"] / false_safe
            if false_safe
            else None
        ),
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


def _clustered_difference(clusters, *, seed, samples, confidence=0.95):
    keys = sorted(clusters)
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        total = count = 0
        for _ in keys:
            value, observations = clusters[rng.choice(keys)]
            total += value
            count += observations
        estimates.append(total / count)
    estimates.sort()
    total = sum(value[0] for value in clusters.values())
    count = sum(value[1] for value in clusters.values())
    tail = (1 - confidence) / 2
    return {
        "estimate": total / count,
        "low": estimates[max(0, int(tail * samples))],
        "high": estimates[min(samples - 1, math.ceil((1 - tail) * samples) - 1)],
        "samples": samples,
        "seed": seed,
        "drafts": len(keys),
    }


def _write_batch(rows, path, writer, pa, pq):
    table = pa.Table.from_pylist(rows)
    if writer is None:
        writer = pq.ParquetWriter(path, table.schema, compression="zstd")
    writer.write_table(table)
    return writer


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
