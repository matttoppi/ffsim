import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from .hdvn_snapshot import canonical_json, sha256_file
from .opponent_model import _iter_drafts, _iter_survival_samples


EMPIRICAL_SURVIVAL_VERSION = "exact-empirical-survival-v1"
MINIMUM_SUPPORT = 250
SAFE_THRESHOLD = 0.70
URGENT_THRESHOLD = 0.30
FOLDS = (
    {"name": "train-2021_validate-2022", "train": (2021,), "validation": (2022,)},
    {"name": "train-2021-2022_validate-2023", "train": (2021, 2022), "validation": (2023,)},
)


def build_empirical_survival(
    market_database,
    market_manifest,
    output_directory,
    *,
    expected_source_hash,
    expected_feature_hash,
    command,
    code_revision,
):
    market_database = Path(market_database).resolve()
    market_manifest = Path(market_manifest).resolve()
    output_directory = Path(output_directory).resolve()
    lookup_path = output_directory / "empirical-survival.json"
    report_path = output_directory / "rolling-fold-report.json"
    manifest_path = output_directory / "empirical-survival.manifest.json"
    paths = (lookup_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable empirical-survival output exists: {output_directory}")
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
            years: _aggregate(connection, years)
            for years in ((2021,), (2021, 2022), (2021, 2022, 2023))
        }
        folds = {
            fold["name"]: _evaluate_fold(
                connection,
                fold["validation"],
                aggregates[fold["train"]]["cells"],
            )
            for fold in FOLDS
        }
    finally:
        connection.close()

    final = aggregates[(2021, 2022, 2023)]
    supported = {
        key: values for key, values in final["cells"].items()
        if values[1] >= MINIMUM_SUPPORT
    }
    elite = {
        "ppr_10": _cell_result(supported.get((2, 18, 1, "RB", "PPR", 10))),
        "ppr_12": _cell_result(supported.get((2, 18, 1, "RB", "PPR", 12))),
    }
    gate = {
        "folds": {
            name: {
                "coverage": result["coverage"],
                "brier": result["metrics"]["brier"],
                "expected_calibration_error": result["metrics"][
                    "expected_calibration_error"
                ],
                "passes": (
                    result["coverage"] >= 0.10
                    and result["metrics"]["brier"] is not None
                    and result["metrics"]["brier"] <= 0.15
                    and result["metrics"]["expected_calibration_error"] <= 0.05
                ),
            }
            for name, result in folds.items()
        },
        "elite_cells": elite,
    }
    gate["passes"] = (
        all(result["passes"] for result in gate["folds"].values())
        and all(
            cell is not None
            and cell["count"] >= MINIMUM_SUPPORT
            and cell["probability"] < 0.01
            for cell in elite.values()
        )
    )
    status = "research" if gate["passes"] else "rejected"

    lookup = {
        "model_version": EMPIRICAL_SURVIVAL_VERSION,
        "status": status,
        "minimum_support": MINIMUM_SUPPORT,
        "smoothing": "Beta(1,1) posterior mean",
        "interval": "95% Wilson raw-rate interval",
        "key_order": [
            "market_rank",
            "gap",
            "round",
            "position",
            "scoring_format",
            "team_count",
        ],
        "cells": [
            {
                "key": list(key),
                **_cell_result(values),
            }
            for key, values in sorted(supported.items())
        ],
    }
    lookup_path.write_text(canonical_json(lookup) + "\n")
    report = {
        "model_version": EMPIRICAL_SURVIVAL_VERSION,
        "status": status,
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "minimum_support": MINIMUM_SUPPORT,
        "folds": folds,
        "final_counts": {
            **final["counts"],
            "supported_cells": len(supported),
            "supported_training_samples": sum(values[1] for values in supported.values()),
        },
        "gate": gate,
        "limitations": [
            "exact supported cells only; no interpolation or fallback",
            "training-year rolling development only",
            "2024 and 2025 were not queried",
            "offline research only; no timing-report or live integration",
        ],
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "model_version": EMPIRICAL_SURVIVAL_VERSION,
        "status": status,
        "source_snapshot_sha256": expected_source_hash,
        "feature_manifest_hash": expected_feature_hash,
        "market_manifest_hash": source_manifest["sha256"],
        "market_database_sha256": database_record["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "minimum_support": MINIMUM_SUPPORT,
        "gate": gate,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (lookup_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_empirical_survival_artifact(
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


def load_empirical_survival_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "empirical-survival manifest")
    if manifest.get("model_version") != EMPIRICAL_SURVIVAL_VERSION:
        raise ValueError("empirical-survival version mismatch")
    if manifest.get("status") not in {"research", "rejected"}:
        raise ValueError("empirical-survival status is invalid")
    if manifest.get("train_development_seasons") != [2021, 2022, 2023]:
        raise ValueError("empirical-survival train seasons mismatch")
    if manifest.get("validation_2024_loaded") is not False:
        raise ValueError("empirical-survival artifact touched 2024")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("empirical-survival artifact touched 2025")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"empirical-survival file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"empirical-survival context mismatch for {key}")
    return manifest


def load_empirical_survival_lookup(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_empirical_survival_artifact(manifest_path, expected=expected)
    try:
        payload = json.loads((manifest_path.parent / "empirical-survival.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("empirical-survival lookup is malformed") from error
    if payload.get("model_version") != EMPIRICAL_SURVIVAL_VERSION:
        raise ValueError("empirical-survival lookup version mismatch")
    if payload.get("status") != manifest["status"]:
        raise ValueError("empirical-survival lookup status mismatch")
    payload["lookup"] = {
        tuple(cell["key"]): cell for cell in payload["cells"]
    }
    return payload


def lookup_survival(
    lookup,
    *,
    market_rank,
    gap,
    round_,
    position,
    scoring_format,
    team_count,
):
    key = (
        int(market_rank),
        int(gap),
        int(round_),
        str(position),
        str(scoring_format),
        int(team_count),
    )
    cell = lookup["lookup"].get(key)
    if cell is None:
        return {
            "status": "unavailable",
            "minimum_support": lookup["minimum_support"],
            "key": list(key),
        }
    return {
        "status": "available",
        "key": list(key),
        "successes": cell["successes"],
        "count": cell["count"],
        "raw_rate": cell["raw_rate"],
        "probability": cell["probability"],
        "interval_95": cell["interval_95"],
    }


def _aggregate(connection, seasons):
    cells = defaultdict(lambda: [0, 0])
    drafts = states = samples = 0
    for draft in _iter_drafts(connection, seasons):
        drafts += 1
        for sample in _iter_survival_samples(draft):
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


def _evaluate_fold(connection, seasons, training_cells):
    state = {
        "supported": 0,
        "total": 0,
        "brier": 0.0,
        "log_loss": 0.0,
        "calibration": [[0, 0.0, 0.0] for _ in range(10)],
    }
    drafts = states = 0
    for draft in _iter_drafts(connection, seasons):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            for target in sample["players"]:
                state["total"] += 1
                key = (
                    int(target["rank"]),
                    int(sample["gap"]),
                    int(sample["round"]),
                    str(target["position"]),
                    str(sample["scoring_format"]),
                    int(sample["team_count"]),
                )
                values = training_cells.get(key)
                if values is None or values[1] < MINIMUM_SUPPORT:
                    continue
                probability = (values[0] + 1.0) / (values[1] + 2.0)
                actual = float(target["survived"])
                state["supported"] += 1
                state["brier"] += (probability - actual) ** 2
                probability = min(max(probability, 1e-15), 1 - 1e-15)
                state["log_loss"] -= actual * math.log(probability) + (1 - actual) * math.log1p(-probability)
                bucket = min(int(probability * 10), 9)
                state["calibration"][bucket][0] += 1
                state["calibration"][bucket][1] += probability
                state["calibration"][bucket][2] += actual
    supported = state["supported"]
    if not supported:
        return {
            "counts": {
                "drafts": drafts,
                "states": states,
                "samples": state["total"],
                "supported": 0,
            },
            "coverage": 0.0,
            "metrics": {
                "brier": None,
                "log_loss": None,
                "expected_calibration_error": None,
                "calibration": [],
            },
        }
    calibration = [
        {
            "lower": index / 10,
            "upper": (index + 1) / 10,
            "count": values[0],
            "mean_prediction": values[1] / values[0],
            "observed_rate": values[2] / values[0],
        }
        for index, values in enumerate(state["calibration"])
        if values[0]
    ]
    ece = sum(
        row["count"] / supported
        * abs(row["mean_prediction"] - row["observed_rate"])
        for row in calibration
    )
    return {
        "counts": {
            "drafts": drafts,
            "states": states,
            "samples": state["total"],
            "supported": supported,
        },
        "coverage": supported / state["total"],
        "metrics": {
            "brier": state["brier"] / supported,
            "log_loss": state["log_loss"] / supported,
            "expected_calibration_error": ece,
            "calibration": calibration,
        },
    }


def _cell_result(values):
    if values is None:
        return None
    successes, count = values
    return {
        "successes": successes,
        "count": count,
        "raw_rate": successes / count,
        "probability": (successes + 1.0) / (count + 2.0),
        "interval_95": list(_wilson(successes, count)),
    }


def _wilson(successes, count, z=1.96):
    rate = successes / count
    denominator = 1 + z * z / count
    center = (rate + z * z / (2 * count)) / denominator
    half = (
        z
        * math.sqrt(rate * (1 - rate) / count + z * z / (4 * count * count))
        / denominator
    )
    return max(0.0, center - half), min(1.0, center + half)


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
