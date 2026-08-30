import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from .hdvn_snapshot import canonical_json, sha256_file
from .opponent_model import _clustered_difference, _iter_drafts, _iter_survival_samples


CONTINUOUS_SURVIVAL_VERSION = "continuous-player-survival-v1"
SEED = 20260828
L2 = 0.001
MAX_ITERATIONS = 200
SAFE_THRESHOLD = 0.70
URGENT_THRESHOLD = 0.30
MINIMUM_BRIER_IMPROVEMENT = 0.001
MINIMUM_FALSE_SAFE_IMPROVEMENT = 0.02
MAXIMUM_SAFE_COVERAGE_LOSS = 0.10
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")
SCORING_FORMATS = ("STD", "HALF_PPR", "PPR")
FEATURE_ORDER = (
    "intercept",
    "log1p_market_rank",
    "log1p_gap",
    "round_div_10",
    "team_count_div_12",
    *(f"position_{position}" for position in POSITIONS),
    *(f"scoring_{scoring}" for scoring in SCORING_FORMATS),
)
FOLDS = (
    {"name": "train-2021_validate-2022", "train": (2021,), "validation": (2022,)},
    {"name": "train-2021-2022_validate-2023", "train": (2021, 2022), "validation": (2023,)},
)


def fit_continuous_survival(
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
        raise ValueError(f"OPP-04 uses the frozen seed {SEED}")
    if bootstrap_samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    market_database = Path(market_database).resolve()
    market_manifest = Path(market_manifest).resolve()
    output_directory = Path(output_directory).resolve()
    model_path = output_directory / "continuous-survival-model.json"
    report_path = output_directory / "rolling-fold-report.json"
    manifest_path = output_directory / "continuous-survival.manifest.json"
    paths = (model_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable continuous-survival output exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    source_manifest = _load_hashed_json(market_manifest, "market manifest")
    if source_manifest.get("source_snapshot_sha256") != expected_source_hash:
        raise ValueError("market and source hashes do not match")
    if source_manifest.get("feature_manifest_hash") != expected_feature_hash:
        raise ValueError("market and feature hashes do not match")
    database_record = source_manifest.get("files", {}).get(market_database.name)
    if database_record is None or sha256_file(market_database) != database_record["sha256"]:
        raise ValueError("market database hash mismatch")

    connection = sqlite3.connect(f"file:{market_database}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        aggregates = {
            years: _aggregate_samples(connection, years)
            for years in ((2021,), (2021, 2022), (2021, 2022, 2023))
        }
        fold_reports = {}
        pooled_differences = defaultdict(lambda: [0.0, 0])
        for fold_index, fold in enumerate(FOLDS):
            training = aggregates[fold["train"]]
            model = _fit_model(training["cells"])
            baseline = _baseline_table(training["cells"])
            validation = _validate_fold(
                connection,
                fold["validation"],
                model,
                baseline,
            )
            for draft_id, values in validation.pop("draft_differences").items():
                pooled_differences[draft_id][0] += values[0]
                pooled_differences[draft_id][1] += values[1]
            fold_reports[fold["name"]] = {
                "train_years": list(fold["train"]),
                "validation_years": list(fold["validation"]),
                "training_counts": training["counts"],
                "optimizer": model["optimizer"],
                **validation,
            }
        pooled_interval = _clustered_difference(
            pooled_differences,
            seed=seed,
            samples=bootstrap_samples,
        )
        final_training = aggregates[(2021, 2022, 2023)]
        final_model = _fit_model(final_training["cells"])
        final_baseline = _baseline_table(final_training["cells"])
    finally:
        connection.close()

    elite_support = _cell_support(
        final_training["cells"],
        rank=2,
        gap=18,
        round_=1,
        position="RB",
    )
    elite_prediction = predict_probability(
        final_model,
        market_rank=2,
        gap=18,
        round_=1,
        position="RB",
        scoring_format="PPR",
        team_count=10,
    )
    fold_gates = {}
    for name, fold in fold_reports.items():
        model_metrics = fold["model"]
        baseline_metrics = fold["baseline"]
        fold_gates[name] = {
            "brier_improvement": baseline_metrics["brier"] - model_metrics["brier"],
            "false_safe_improvement": (
                baseline_metrics["false_safe_rate"] - model_metrics["false_safe_rate"]
            ),
            "safe_coverage_loss": (
                baseline_metrics["safe_coverage"] - model_metrics["safe_coverage"]
            ),
        }
        fold_gates[name]["passes"] = (
            fold_gates[name]["brier_improvement"] >= MINIMUM_BRIER_IMPROVEMENT
            and fold_gates[name]["false_safe_improvement"] >= MINIMUM_FALSE_SAFE_IMPROVEMENT
            and fold_gates[name]["safe_coverage_loss"] <= MAXIMUM_SAFE_COVERAGE_LOSS
        )
    gate = {
        "folds": fold_gates,
        "pooled_paired_brier_difference": pooled_interval,
        "elite_rb_gap18_support": elite_support,
        "elite_rb_gap18_prediction": elite_prediction,
        "passes": (
            all(fold["passes"] for fold in fold_gates.values())
            and pooled_interval["high"] < 0
            and elite_support >= 1_000
            and elite_prediction < 0.01
        ),
    }
    status = "research" if gate["passes"] else "rejected"

    model_payload = {
        "model_version": CONTINUOUS_SURVIVAL_VERSION,
        "status": status,
        "feature_order": list(FEATURE_ORDER),
        "coefficients": final_model["coefficients"].tolist(),
        "constraints": {
            "log1p_market_rank": "nonnegative",
            "log1p_gap": "nonpositive",
        },
        "optimizer": final_model["optimizer"],
        "baseline": [
            {"key": list(key), "successes": values[0], "count": values[1]}
            for key, values in sorted(final_baseline.items())
        ],
        "safe_threshold": SAFE_THRESHOLD,
        "urgent_threshold": URGENT_THRESHOLD,
    }
    model_path.write_text(canonical_json(model_payload) + "\n")
    report = {
        "model_version": CONTINUOUS_SURVIVAL_VERSION,
        "status": status,
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "folds": fold_reports,
        "gate": gate,
        "limitations": [
            "training-year rolling development only",
            "2024 and 2025 were not queried",
            "population model; no manager identity or player identity",
            "offline research only; no timing-report or live integration",
        ],
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "model_version": CONTINUOUS_SURVIVAL_VERSION,
        "status": status,
        "source_snapshot_sha256": expected_source_hash,
        "feature_manifest_hash": expected_feature_hash,
        "market_manifest_hash": source_manifest["sha256"],
        "market_database_sha256": database_record["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "seed": seed,
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "feature_order": list(FEATURE_ORDER),
        "optimizer": {"name": "L-BFGS-B", "l2": L2, "max_iterations": MAX_ITERATIONS},
        "thresholds": {"safe": SAFE_THRESHOLD, "urgent": URGENT_THRESHOLD},
        "gate": gate,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (model_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_continuous_survival_artifact(
        manifest_path,
        expected={
            "source_snapshot_sha256": expected_source_hash,
            "feature_manifest_hash": expected_feature_hash,
            "status": status,
        },
    )
    for path in paths:
        path.chmod(0o444)
    return manifest


def load_continuous_survival_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "continuous-survival manifest")
    if manifest.get("model_version") != CONTINUOUS_SURVIVAL_VERSION:
        raise ValueError("continuous-survival version mismatch")
    if manifest.get("status") not in {"research", "rejected"}:
        raise ValueError("continuous-survival status is invalid")
    if manifest.get("train_development_seasons") != [2021, 2022, 2023]:
        raise ValueError("continuous-survival train seasons mismatch")
    if manifest.get("validation_2024_loaded") is not False:
        raise ValueError("continuous-survival artifact touched 2024")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("continuous-survival artifact touched 2025")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"continuous-survival file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"continuous-survival context mismatch for {key}")
    return manifest


def load_continuous_survival_model(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_continuous_survival_artifact(manifest_path, expected=expected)
    try:
        payload = json.loads(
            (manifest_path.parent / "continuous-survival-model.json").read_text()
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("continuous-survival model is malformed") from error
    if payload.get("model_version") != CONTINUOUS_SURVIVAL_VERSION:
        raise ValueError("continuous-survival model version mismatch")
    if payload.get("status") != manifest["status"]:
        raise ValueError("continuous-survival model status mismatch")
    payload["coefficients"] = np.asarray(payload["coefficients"], dtype=np.float64)
    return payload


def predict_continuous_survival(
    model,
    *,
    market_rank,
    gap,
    round_,
    position,
    scoring_format,
    team_count,
):
    probability = predict_probability(
        model,
        market_rank=market_rank,
        gap=gap,
        round_=round_,
        position=position,
        scoring_format=scoring_format,
        team_count=team_count,
    )
    return {
        "survives_to_next_pick": probability,
        "status": "offline_research",
        "model_version": CONTINUOUS_SURVIVAL_VERSION,
    }


def predict_probability(
    model,
    *,
    market_rank,
    gap,
    round_,
    position,
    scoring_format,
    team_count,
):
    coefficients = np.asarray(model["coefficients"], dtype=np.float64)
    features = _features(
        int(market_rank),
        int(gap),
        int(round_),
        str(position),
        str(scoring_format),
        int(team_count),
    )
    return float(_sigmoid(features @ coefficients))


def _aggregate_samples(connection, seasons, target_count=10):
    cells = defaultdict(lambda: [0.0, 0])
    drafts = states = samples = 0
    for draft in _iter_drafts(connection, seasons):
        drafts += 1
        for sample in _iter_survival_samples(draft, target_count):
            states += 1
            for target in sample["players"]:
                key = (
                    int(target["rank"]),
                    int(sample["gap"]),
                    int(sample["round"]),
                    str(target["position"]),
                    str(sample["scoring_format"]),
                    int(sample["team_count"]),
                )
                cells[key][0] += int(target["survived"])
                cells[key][1] += 1
                samples += 1
    return {
        "cells": cells,
        "counts": {"drafts": drafts, "states": states, "samples": samples, "cells": len(cells)},
    }


def _fit_model(cells):
    keys = sorted(cells)
    x = np.asarray([_features(*key) for key in keys], dtype=np.float64)
    successes = np.asarray([cells[key][0] for key in keys], dtype=np.float64)
    counts = np.asarray([cells[key][1] for key in keys], dtype=np.float64)
    total = counts.sum()
    global_rate = successes.sum() / total
    initial = np.zeros(len(FEATURE_ORDER), dtype=np.float64)
    initial[0] = math.log(global_rate / (1 - global_rate))
    initial[1] = 1.0
    initial[2] = -1.0

    def objective(coefficients):
        logits = x @ coefficients
        loss = (
            np.sum(counts * np.logaddexp(0.0, logits) - successes * logits)
            / total
        )
        loss += 0.5 * L2 * float(coefficients[1:] @ coefficients[1:])
        probabilities = _sigmoid(logits)
        gradient = x.T @ (counts * probabilities - successes) / total
        gradient[1:] += L2 * coefficients[1:]
        return float(loss), gradient

    bounds = [(None, None)] * len(FEATURE_ORDER)
    bounds[1] = (0.0, None)
    bounds[2] = (None, 0.0)
    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        bounds=bounds,
        options={"maxiter": MAX_ITERATIONS, "ftol": 1e-12, "gtol": 1e-8},
    )
    if not result.success:
        raise ValueError(f"continuous-survival optimizer failed: {result.message}")
    return {
        "coefficients": np.asarray(result.x, dtype=np.float64),
        "optimizer": {
            "name": "L-BFGS-B",
            "iterations": int(result.nit),
            "objective": float(result.fun),
            "l2": L2,
            "max_iterations": MAX_ITERATIONS,
            "success": True,
        },
    }


def _baseline_table(cells):
    table = defaultdict(lambda: [0.0, 0])
    for key, values in cells.items():
        rank, gap, round_ = key[:3]
        table[(rank, gap, round_)][0] += values[0]
        table[(rank, gap, round_)][1] += values[1]
    return table


def _validate_fold(connection, seasons, model, baseline):
    model_state = _metric_state()
    baseline_state = _metric_state()
    draft_differences = defaultdict(lambda: [0.0, 0])
    drafts = states = samples = 0
    for draft in _iter_drafts(connection, seasons):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            for target in sample["players"]:
                rank = int(target["rank"])
                gap = int(sample["gap"])
                round_ = int(sample["round"])
                actual = float(target["survived"])
                probability = predict_probability(
                    model,
                    market_rank=rank,
                    gap=gap,
                    round_=round_,
                    position=target["position"],
                    scoring_format=sample["scoring_format"],
                    team_count=sample["team_count"],
                )
                base_values = baseline.get((rank, gap, round_), (0.0, 0))
                baseline_probability = (base_values[0] + 2.0) / (base_values[1] + 4.0)
                _add_metric(model_state, actual, probability)
                _add_metric(baseline_state, actual, baseline_probability)
                draft_differences[draft["draft_id"]][0] += (
                    (probability - actual) ** 2
                    - (baseline_probability - actual) ** 2
                )
                draft_differences[draft["draft_id"]][1] += 1
                samples += 1
    return {
        "counts": {"drafts": drafts, "states": states, "samples": samples},
        "model": _finish_metric(model_state),
        "baseline": _finish_metric(baseline_state),
        "draft_differences": draft_differences,
    }


def _features(rank, gap, round_, position, scoring_format, team_count):
    position = position if position in POSITIONS else "UNKNOWN"
    scoring_format = scoring_format if scoring_format in SCORING_FORMATS else "STD"
    return np.asarray([
        1.0,
        math.log1p(rank),
        math.log1p(gap),
        round_ / 10.0,
        team_count / 12.0,
        *(float(position == value) for value in POSITIONS),
        *(float(scoring_format == value) for value in SCORING_FORMATS),
    ], dtype=np.float64)


def _metric_state():
    return {
        "count": 0,
        "brier": 0.0,
        "log_loss": 0.0,
        "safe": 0,
        "false_safe": 0,
        "urgent": 0,
        "false_urgent": 0,
        "calibration": [[0, 0.0, 0.0] for _ in range(10)],
    }


def _add_metric(state, actual, probability):
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
        state["false_safe"] += int(not actual)
    if probability <= URGENT_THRESHOLD:
        state["urgent"] += 1
        state["false_urgent"] += int(bool(actual))


def _finish_metric(state):
    count = state["count"]
    return {
        "count": count,
        "brier": state["brier"] / count,
        "log_loss": state["log_loss"] / count,
        "safe_coverage": state["safe"] / count,
        "false_safe_rate": (
            state["false_safe"] / state["safe"] if state["safe"] else None
        ),
        "urgent_coverage": state["urgent"] / count,
        "false_urgent_rate": (
            state["false_urgent"] / state["urgent"] if state["urgent"] else None
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


def _cell_support(cells, *, rank, gap, round_, position):
    return sum(
        values[1]
        for key, values in cells.items()
        if key[0] == rank and key[1] == gap and key[2] == round_ and key[3] == position
    )


def _sigmoid(values):
    values = np.asarray(values, dtype=np.float64)
    result = np.empty_like(values)
    positive = values >= 0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponential = np.exp(values[~positive])
    result[~positive] = exponential / (1.0 + exponential)
    return result


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
