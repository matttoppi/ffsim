import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from scipy.stats import beta as beta_distribution

from .continuous_survival import (
    _add_metric,
    _aggregate_samples,
    _finish_metric,
    _metric_state,
)
from .hdvn_snapshot import canonical_json, sha256_file
from .opponent_model import (
    _clustered_difference,
    _iter_drafts,
    _iter_survival_samples,
)

HIERARCHICAL_SURVIVAL_VERSION = "hierarchical-position-survival-v1"
SHRINKAGE = 100.0
SEED = 20260828
FOLDS = (
    {"name": "train-2021_validate-2022", "train": (2021,), "validation": (2022,)},
    {"name": "train-2021-2022_validate-2023", "train": (2021, 2022), "validation": (2023,)},
)


def build_hierarchical_survival(
    market_database,
    market_manifest,
    output_directory,
    *,
    expected_source_hash,
    expected_feature_hash,
    command,
    code_revision,
    bootstrap_samples=200,
):
    if bootstrap_samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    market_database = Path(market_database).resolve()
    market_manifest = Path(market_manifest).resolve()
    output_directory = Path(output_directory).resolve()
    model_path = output_directory / "hierarchical-survival.json"
    report_path = output_directory / "validation-report.json"
    manifest_path = output_directory / "hierarchical-survival.manifest.json"
    paths = (model_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(
            f"immutable hierarchical-survival output exists: {output_directory}"
        )
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
        folds = {}
        for index, fold in enumerate(FOLDS):
            model = _tables(aggregates[fold["train"]]["cells"])
            folds[fold["name"]] = _evaluate(
                connection,
                fold["validation"],
                model,
                seed=SEED + index,
                bootstrap_samples=bootstrap_samples,
            )
        final_model = _tables(aggregates[(2021, 2022, 2023)]["cells"])
        transfer = _evaluate(
            connection,
            (2024,),
            final_model,
            seed=SEED + len(FOLDS),
            bootstrap_samples=bootstrap_samples,
        )
    finally:
        connection.close()

    elite_key = (2, 18, 1, "RB")
    elite = final_model["position"].get(elite_key, (0, 0))
    elite_probability = _probability(final_model, elite_key)
    fold_gates = {
        name: _gate(result, require_relative=True) for name, result in folds.items()
    }
    transfer_gate = _gate(transfer, require_relative=False)
    gate = {
        "folds": fold_gates,
        "transfer_2024": transfer_gate,
        "elite_rank2_rb_gap18_round1": {
            "successes": elite[0],
            "count": elite[1],
            "probability": elite_probability,
        },
    }
    gate["passes"] = (
        all(result["passes"] for result in fold_gates.values())
        and transfer_gate["passes"]
        and elite[1] >= 1_000
        and elite_probability < 0.01
    )
    status = "research" if gate["passes"] else "rejected"

    model_payload = {
        "model_version": HIERARCHICAL_SURVIVAL_VERSION,
        "status": status,
        "shrinkage_observations": SHRINKAGE,
        "key_order": ["market_rank", "gap", "round", "position"],
        "global": list(final_model["global"]),
        "pooled_cells": [
            {"key": list(key), "successes": values[0], "count": values[1]}
            for key, values in sorted(final_model["pooled"].items())
        ],
        "position_cells": [
            {"key": list(key), "successes": values[0], "count": values[1]}
            for key, values in sorted(final_model["position"].items())
        ],
    }
    model_path.write_text(canonical_json(model_payload) + "\n")
    report = {
        "model_version": HIERARCHICAL_SURVIVAL_VERSION,
        "status": status,
        "train_development_seasons": [2021, 2022, 2023],
        "validation_seasons": [2022, 2023],
        "seen_transfer_seasons": [2024],
        "locked_test_loaded": False,
        "folds": folds,
        "transfer_2024": transfer,
        "gate": gate,
        "limitations": [
            "offline population survival research only",
            "2024 is a seen transfer diagnostic",
            "scoring format, team count, and manager identity are pooled",
            "joint tier survival is not modeled",
            "2025 was not queried",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "model_version": HIERARCHICAL_SURVIVAL_VERSION,
        "status": status,
        "source_snapshot_sha256": expected_source_hash,
        "feature_manifest_hash": expected_feature_hash,
        "market_manifest_hash": source_manifest["sha256"],
        "market_database_sha256": database_record["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "train_development_seasons": [2021, 2022, 2023],
        "seen_transfer_seasons": [2024],
        "locked_test_loaded": False,
        "shrinkage_observations": SHRINKAGE,
        "bootstrap_samples": bootstrap_samples,
        "seed": SEED,
        "gate": gate,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (model_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_hierarchical_survival_artifact(
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


def load_hierarchical_survival_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "hierarchical-survival manifest")
    if manifest.get("model_version") != HIERARCHICAL_SURVIVAL_VERSION:
        raise ValueError("hierarchical-survival version mismatch")
    if manifest.get("status") not in {"research", "rejected"}:
        raise ValueError("hierarchical-survival status is invalid")
    if manifest.get("train_development_seasons") != [2021, 2022, 2023]:
        raise ValueError("hierarchical-survival train seasons mismatch")
    if manifest.get("seen_transfer_seasons") != [2024]:
        raise ValueError("hierarchical-survival transfer seasons mismatch")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("hierarchical-survival artifact touched locked test")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"hierarchical-survival file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"hierarchical-survival context mismatch for {key}")
    return manifest


def load_hierarchical_survival_model(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_hierarchical_survival_artifact(manifest_path, expected=expected)
    try:
        payload = json.loads((manifest_path.parent / "hierarchical-survival.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("hierarchical-survival model is malformed") from error
    if payload.get("model_version") != HIERARCHICAL_SURVIVAL_VERSION:
        raise ValueError("hierarchical-survival model version mismatch")
    if payload.get("status") != manifest["status"]:
        raise ValueError("hierarchical-survival model status mismatch")
    return {
        **payload,
        "global": tuple(payload["global"]),
        "pooled": {
            tuple(cell["key"]): (cell["successes"], cell["count"])
            for cell in payload["pooled_cells"]
        },
        "position": {
            tuple(cell["key"]): (cell["successes"], cell["count"])
            for cell in payload["position_cells"]
        },
    }


def predict_hierarchical_survival(
    model, *, market_rank, gap, round_, position
):
    key = (int(market_rank), int(gap), int(round_), str(position))
    pooled = model["pooled"].get(key[:3], model["global"])
    direct = model["position"].get(key, (0, 0))
    prior = (pooled[0] + 1) / (pooled[1] + 2)
    alpha = direct[0] + SHRINKAGE * prior
    beta = direct[1] - direct[0] + SHRINKAGE * (1 - prior)
    probability = alpha / (alpha + beta)
    return {
        "survives_to_next_pick": probability,
        "probability": probability,
        "interval_95": (
            float(beta_distribution.ppf(0.025, alpha, beta)),
            float(beta_distribution.ppf(0.975, alpha, beta)),
        ),
        "raw_rate": direct[0] / direct[1] if direct[1] else None,
        "direct_support": direct[1],
        "pooled_support": pooled[1],
        "model_version": HIERARCHICAL_SURVIVAL_VERSION,
        "status": "offline_research",
    }


def _tables(cells):
    pooled = defaultdict(lambda: [0, 0])
    positioned = defaultdict(lambda: [0, 0])
    total = [0, 0]
    for key, values in cells.items():
        for target in (pooled[key[:3]], positioned[key[:4]], total):
            target[0] += int(values[0])
            target[1] += int(values[1])
    return {"pooled": pooled, "position": positioned, "global": total}


def _probability(model, key):
    pooled = model["pooled"].get(key[:3], model["global"])
    prior = (pooled[0] + 1) / (pooled[1] + 2)
    direct = model["position"].get(key, (0, 0))
    return (direct[0] + SHRINKAGE * prior) / (direct[1] + SHRINKAGE)


def _evaluate(
    connection,
    years,
    model,
    *,
    seed,
    bootstrap_samples,
    target_count=10,
):
    hierarchical = _metric_state()
    baseline = _metric_state()
    differences = defaultdict(lambda: [0.0, 0])
    drafts = states = samples = 0
    for draft in _iter_drafts(connection, years):
        drafts += 1
        for sample in _iter_survival_samples(draft, target_count):
            states += 1
            for target in sample["players"]:
                key = (
                    int(target["rank"]),
                    int(sample["gap"]),
                    int(sample["round"]),
                    str(target["position"]),
                )
                actual = float(target["survived"])
                predicted = _probability(model, key)
                pooled = model["pooled"].get(key[:3], (0, 0))
                base_probability = (pooled[0] + 2) / (pooled[1] + 4)
                _add_metric(hierarchical, actual, predicted)
                _add_metric(baseline, actual, base_probability)
                differences[draft["draft_id"]][0] += (
                    (predicted - actual) ** 2 - (base_probability - actual) ** 2
                )
                differences[draft["draft_id"]][1] += 1
                samples += 1
    result = {
        "counts": {"drafts": drafts, "states": states, "samples": samples},
        "hierarchical": _finish_metric(hierarchical),
        "baseline": _finish_metric(baseline),
        "paired_brier_difference": _clustered_difference(
            differences, seed=seed, samples=bootstrap_samples
        ),
    }
    result["hierarchical"]["expected_calibration_error"] = _ece(
        result["hierarchical"]
    )
    return result


def _gate(result, *, require_relative):
    metrics = result["hierarchical"]
    improvement = result["baseline"]["brier"] - metrics["brier"]
    gate = {
        "coverage": 1.0,
        "brier": metrics["brier"],
        "expected_calibration_error": metrics["expected_calibration_error"],
        "false_safe_rate": metrics["false_safe_rate"],
        "brier_improvement": improvement,
        "paired_brier_difference": result["paired_brier_difference"],
    }
    gate["passes"] = (
        gate["brier"] <= 0.12
        and gate["expected_calibration_error"] <= 0.05
        and gate["false_safe_rate"] <= 0.10
        and (
            not require_relative
            or (
                improvement >= 0.001
                and result["paired_brier_difference"]["high"] < 0
            )
        )
    )
    return gate


def _ece(metrics):
    return sum(
        bucket["count"]
        * abs(bucket["mean_prediction"] - bucket["observed_rate"])
        for bucket in metrics["calibration"]
    ) / metrics["count"]


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
