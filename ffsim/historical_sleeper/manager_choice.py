import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

from .hdvn_snapshot import canonical_json, sha256_file
from .opponent_model import _iter_drafts

MANAGER_CHOICE_VERSION = "manager-position-residual-v1"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")
POSITION_INDEX = {position: index for index, position in enumerate(POSITIONS)}
SHRINKAGE = 50.0
MINIMUM_MANAGER_PICKS = 20
BENCHMARK_SHA256 = "f5dca7e79844e2ffad3935a33d9068f16e29c45a9301bc1b9be919a4e2574fe7"


def build_manager_choice_artifact(
    source_database,
    market_database,
    market_manifest,
    benchmark,
    output_directory,
    *,
    expected_source_hash,
    expected_feature_hash,
    command,
    code_revision,
):
    source_database = Path(source_database).resolve()
    market_database = Path(market_database).resolve()
    market_manifest = Path(market_manifest).resolve()
    benchmark = Path(benchmark).resolve()
    output_directory = Path(output_directory).resolve()
    model_path = output_directory / "manager-choice.json"
    report_path = output_directory / "build-report.json"
    manifest_path = output_directory / "manager-choice.manifest.json"
    paths = (model_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable manager-choice output exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    source_manifest = _load_hashed_json(market_manifest, "market manifest")
    if source_manifest.get("source_snapshot_sha256") != expected_source_hash:
        raise ValueError("market and source hashes do not match")
    if source_manifest.get("feature_manifest_hash") != expected_feature_hash:
        raise ValueError("market and feature hashes do not match")
    database_record = source_manifest.get("files", {}).get(market_database.name)
    if database_record is None or sha256_file(market_database) != database_record["sha256"]:
        raise ValueError("market database hash mismatch")
    if sha256_file(source_database) != expected_source_hash:
        raise ValueError("source snapshot hash mismatch")
    if sha256_file(benchmark) != BENCHMARK_SHA256:
        raise ValueError("manager benchmark hash mismatch")
    benchmark_result = json.loads(benchmark.read_text())
    if (
        benchmark_result.get("status") != "locked_benchmark_passed"
        or not benchmark_result.get("gate", {}).get("passes")
        or benchmark_result.get("train_seasons") != [2021, 2022, 2023, 2024]
        or benchmark_result.get("validation_seasons") != [2025]
        or benchmark_result.get("locked_test_evaluation_count") != 1
    ):
        raise ValueError("manager benchmark did not pass its frozen contract")

    market = sqlite3.connect(f"file:{market_database}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{source_database}?mode=ro&immutable=1", uri=True)
    try:
        global_factor, managers, counts = fit_manager_choice(
            source, market, (2021, 2022, 2023, 2024)
        )
    finally:
        source.close()
        market.close()
    supported = {
        manager: record
        for manager, record in managers.items()
        if record["picks"] >= MINIMUM_MANAGER_PICKS
    }
    model = {
        "model_version": MANAGER_CHOICE_VERSION,
        "status": "research",
        "positions": list(POSITIONS),
        "population_position_factors": global_factor.tolist(),
        "shrinkage_opportunities": SHRINKAGE,
        "minimum_manager_picks": MINIMUM_MANAGER_PICKS,
        "managers": [
            {
                "manager_id": manager,
                "training_picks": record["picks"],
                "position_factors": record["factor"].tolist(),
            }
            for manager, record in sorted(supported.items())
        ],
    }
    model_path.write_text(canonical_json(model) + "\n")
    report = {
        "model_version": MANAGER_CHOICE_VERSION,
        "status": "research",
        "train_seasons": [2021, 2022, 2023, 2024],
        "builder_locked_test_loaded": False,
        "locked_benchmark_sha256": BENCHMARK_SHA256,
        "locked_benchmark_gate": benchmark_result["gate"],
        "training_counts": counts,
        "supported_managers": len(supported),
        "limitations": [
            "offline opponent-choice research only",
            "position preference does not model player-specific affinity",
            "unsupported managers use the population distribution",
            "the builder did not query 2025",
            "no live opponent callback, VONA, rollout, API, or UI integration",
        ],
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "model_version": MANAGER_CHOICE_VERSION,
        "status": "research",
        "source_snapshot_sha256": expected_source_hash,
        "feature_manifest_hash": expected_feature_hash,
        "market_manifest_hash": source_manifest["sha256"],
        "market_database_sha256": database_record["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "train_seasons": [2021, 2022, 2023, 2024],
        "builder_locked_test_loaded": False,
        "locked_benchmark_sha256": BENCHMARK_SHA256,
        "shrinkage_opportunities": SHRINKAGE,
        "minimum_manager_picks": MINIMUM_MANAGER_PICKS,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (model_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_manager_choice_artifact(
        manifest_path,
        expected={
            "source_snapshot_sha256": expected_source_hash,
            "feature_manifest_hash": expected_feature_hash,
            "status": "research",
        },
    )
    for path in paths:
        path.chmod(0o444)
    return manifest


def fit_manager_choice(source, market, years):
    observed = np.zeros(len(POSITIONS))
    expected = np.zeros(len(POSITIONS))
    managers = defaultdict(
        lambda: {
            "observed": np.zeros(len(POSITIONS)),
            "expected": np.zeros(len(POSITIONS)),
            "picks": 0,
        }
    )
    counts = defaultdict(int)
    for draft in _iter_drafts(market, years):
        counts["drafts"] += 1
        identities = _manager_by_pick(source, draft["draft_id"])
        positions, weights, available = _choice_state(draft)
        for pick in draft["picks"]:
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                counts["missing_board_picks"] += 1
                continue
            probability = weights * available
            probability /= probability.sum()
            opportunity = np.bincount(
                positions, weights=probability, minlength=len(POSITIONS)
            )
            selected_position = positions[selected]
            observed[selected_position] += 1
            expected += opportunity
            manager = identities.get(pick["pick_no"])
            if manager:
                record = managers[manager]
                record["observed"][selected_position] += 1
                record["expected"] += opportunity
                record["picks"] += 1
            else:
                counts["missing_manager_picks"] += 1
            counts["picks"] += 1
            available[selected] = False
    observed_rate = observed / observed.sum()
    expected_rate = expected / expected.sum()
    global_factor = (observed + 1) / (expected + 1)
    fitted = {
        manager: {
            "picks": record["picks"],
            "factor": (
                (record["observed"] + SHRINKAGE * observed_rate)
                / (record["expected"] + SHRINKAGE * expected_rate)
            ),
        }
        for manager, record in managers.items()
    }
    counts["managers"] = len(fitted)
    counts["supported_managers"] = sum(
        record["picks"] >= MINIMUM_MANAGER_PICKS for record in fitted.values()
    )
    return global_factor, fitted, dict(counts)


def load_manager_choice_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "manager-choice manifest")
    if manifest.get("model_version") != MANAGER_CHOICE_VERSION:
        raise ValueError("manager-choice version mismatch")
    if manifest.get("status") != "research":
        raise ValueError("manager-choice status is invalid")
    if manifest.get("train_seasons") != [2021, 2022, 2023, 2024]:
        raise ValueError("manager-choice train seasons mismatch")
    if manifest.get("builder_locked_test_loaded") is not False:
        raise ValueError("manager-choice builder touched locked test")
    if manifest.get("locked_benchmark_sha256") != BENCHMARK_SHA256:
        raise ValueError("manager-choice benchmark mismatch")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"manager-choice file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"manager-choice context mismatch for {key}")
    return manifest


def load_manager_choice_model(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_manager_choice_artifact(manifest_path, expected=expected)
    try:
        payload = json.loads((manifest_path.parent / "manager-choice.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("manager-choice model is malformed") from error
    if payload.get("model_version") != MANAGER_CHOICE_VERSION:
        raise ValueError("manager-choice model version mismatch")
    if payload.get("status") != manifest["status"]:
        raise ValueError("manager-choice model status mismatch")
    return {
        **payload,
        "population_position_factors": np.asarray(
            payload["population_position_factors"], dtype=np.float64
        ),
        "manager_factors": {
            row["manager_id"]: {
                "training_picks": row["training_picks"],
                "position_factors": np.asarray(
                    row["position_factors"], dtype=np.float64
                ),
            }
            for row in payload["managers"]
        },
    }


def personalize_choice_probabilities(model, manager_id, positions, probabilities):
    probabilities = np.asarray(probabilities, dtype=np.float64)
    if probabilities.ndim != 1 or len(probabilities) != len(positions):
        raise ValueError("choice probabilities and positions must align")
    if np.any(probabilities < 0) or not np.isclose(probabilities.sum(), 1.0):
        raise ValueError("choice probabilities must be a normalized distribution")
    record = model["manager_factors"].get(str(manager_id))
    factors = (
        record["position_factors"]
        if record is not None
        else model["population_position_factors"]
    )
    indices = np.asarray(
        [POSITION_INDEX.get(str(position or "UNKNOWN").upper(), POSITION_INDEX["UNKNOWN"])
         for position in positions],
        dtype=np.int64,
    )
    adjusted = probabilities * factors[indices]
    adjusted /= adjusted.sum()
    return {
        "probabilities": adjusted,
        "status": "personalized" if record is not None else "population",
        "training_picks": record["training_picks"] if record is not None else 0,
        "model_version": MANAGER_CHOICE_VERSION,
    }


def _manager_by_pick(source, draft_id):
    return dict(source.execute(
        "SELECT pick_no, picked_by FROM draft_picks WHERE draft_id = ?",
        (draft_id,),
    ))


def _choice_state(draft):
    positions = np.asarray([
        POSITION_INDEX.get(
            str(value or "UNKNOWN").upper(), POSITION_INDEX["UNKNOWN"]
        )
        for value in draft["positions"]
    ])
    weights = 1.0 / np.maximum(draft["adp"], 1e-12)
    return positions, weights, np.ones(len(positions), dtype=bool)


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
