import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .hdvn_snapshot import canonical_json, sha256_file
from .manager_choice import (
    MINIMUM_MANAGER_PICKS,
    POSITION_INDEX,
    POSITIONS,
    SHRINKAGE,
    _choice_state,
    _manager_by_pick,
)
from .opponent_model import _iter_drafts

ROSTER_MANAGER_CHOICE_VERSION = "manager-position-count-residual-v1"
BENCHMARK_SHA256 = "3fdd5349fb9cb6ba1b34937c7ecee27d207e76fb5f72b67c91334b5b2f803fe6"


def build_roster_manager_choice_artifact(
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
    model_path = output_directory / "roster-manager-choice.json"
    report_path = output_directory / "build-report.json"
    manifest_path = output_directory / "roster-manager-choice.manifest.json"
    paths = (model_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(
            f"immutable roster-manager output exists: {output_directory}"
        )
    output_directory.mkdir(parents=True, exist_ok=True)

    source_manifest = _load_hashed_json(market_manifest, "market manifest")
    if source_manifest.get("source_snapshot_sha256") != expected_source_hash:
        raise ValueError("market and source hashes do not match")
    if source_manifest.get("feature_manifest_hash") != expected_feature_hash:
        raise ValueError("market and feature hashes do not match")
    market_record = source_manifest.get("files", {}).get(market_database.name)
    if market_record is None or sha256_file(market_database) != market_record["sha256"]:
        raise ValueError("market database hash mismatch")
    if sha256_file(source_database) != expected_source_hash:
        raise ValueError("source snapshot hash mismatch")
    if sha256_file(benchmark) != BENCHMARK_SHA256:
        raise ValueError("roster-manager benchmark hash mismatch")
    benchmark_result = json.loads(benchmark.read_text())
    if (
        benchmark_result.get("status") != "research"
        or not benchmark_result.get("gate", {}).get("passes")
        or benchmark_result.get("train_development_seasons") != [2021, 2022, 2023]
        or benchmark_result.get("seen_transfer_seasons") != [2024]
        or benchmark_result.get("locked_test_loaded") is not False
    ):
        raise ValueError("roster-manager benchmark did not pass its frozen contract")

    market = sqlite3.connect(f"file:{market_database}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{source_database}?mode=ro&immutable=1", uri=True)
    try:
        population, managers, counts = fit_roster_manager_choice(
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
        "model_version": ROSTER_MANAGER_CHOICE_VERSION,
        "status": "research",
        "positions": list(POSITIONS),
        "count_buckets": ["zero", "one", "two_plus"],
        "population_factors": population.tolist(),
        "shrinkage_opportunities": SHRINKAGE,
        "minimum_manager_picks": MINIMUM_MANAGER_PICKS,
        "managers": [
            {
                "manager_id": manager,
                "training_picks": record["picks"],
                "position_count_factors": record["factor"].tolist(),
            }
            for manager, record in sorted(supported.items())
        ],
    }
    model_path.write_text(canonical_json(model) + "\n")
    report = {
        "model_version": ROSTER_MANAGER_CHOICE_VERSION,
        "status": "research",
        "train_seasons": [2021, 2022, 2023, 2024],
        "builder_locked_test_loaded": False,
        "benchmark_sha256": BENCHMARK_SHA256,
        "benchmark_gate": benchmark_result["gate"],
        "training_counts": counts,
        "supported_managers": len(supported),
        "limitations": [
            "offline opponent-choice research only",
            "2024 is a seen transfer diagnostic",
            "the model was selected after the one-time 2025 benchmark",
            "the builder did not query 2025",
            "no live opponent callback or recommendation integration",
        ],
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "model_version": ROSTER_MANAGER_CHOICE_VERSION,
        "status": "research",
        "source_snapshot_sha256": expected_source_hash,
        "feature_manifest_hash": expected_feature_hash,
        "market_manifest_hash": source_manifest["sha256"],
        "market_database_sha256": market_record["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "train_seasons": [2021, 2022, 2023, 2024],
        "builder_locked_test_loaded": False,
        "benchmark_sha256": BENCHMARK_SHA256,
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
    load_roster_manager_choice_artifact(
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


def fit_roster_manager_choice(source, market, years):
    observed = np.zeros((len(POSITIONS), 3))
    expected = np.zeros((len(POSITIONS), 3))
    managers = defaultdict(
        lambda: {
            "observed": np.zeros((len(POSITIONS), 3)),
            "expected": np.zeros((len(POSITIONS), 3)),
            "picks": 0,
        }
    )
    counts = defaultdict(int)
    for draft in _iter_drafts(market, years):
        identities = _manager_by_pick(source, draft["draft_id"])
        source_positions = _source_positions_by_pick(source, draft["draft_id"])
        positions, weights, available = _choice_state(draft)
        roster_counts = defaultdict(lambda: np.zeros(len(POSITIONS), dtype=np.int64))
        for pick in draft["picks"]:
            roster = roster_counts[pick["roster_id"]]
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                position = source_positions.get(pick["pick_no"])
                if position is not None:
                    roster[position] += 1
                    counts["missing_board_state_updates"] += 1
                continue
            probability = weights * available
            probability /= probability.sum()
            opportunity = np.bincount(
                positions, weights=probability, minlength=len(POSITIONS)
            )
            buckets = np.minimum(roster, 2)
            for position, mass in enumerate(opportunity):
                expected[position, buckets[position]] += mass
            selected_position = positions[selected]
            observed[selected_position, buckets[selected_position]] += 1
            manager = identities.get(pick["pick_no"])
            if manager:
                record = managers[manager]
                for position, mass in enumerate(opportunity):
                    record["expected"][position, buckets[position]] += mass
                record["observed"][selected_position, buckets[selected_position]] += 1
                record["picks"] += 1
            roster[selected_position] += 1
            available[selected] = False
            counts["scored_picks"] += 1
    observed_rate = observed / observed.sum()
    expected_rate = expected / expected.sum()
    population = (observed + 1) / (expected + 1)
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
    return population, fitted, dict(counts)


def load_roster_manager_choice_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "roster-manager manifest")
    if manifest.get("model_version") != ROSTER_MANAGER_CHOICE_VERSION:
        raise ValueError("roster-manager version mismatch")
    if manifest.get("status") != "research":
        raise ValueError("roster-manager status is invalid")
    if manifest.get("train_seasons") != [2021, 2022, 2023, 2024]:
        raise ValueError("roster-manager train seasons mismatch")
    if manifest.get("builder_locked_test_loaded") is not False:
        raise ValueError("roster-manager builder touched locked test")
    if manifest.get("benchmark_sha256") != BENCHMARK_SHA256:
        raise ValueError("roster-manager benchmark mismatch")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"roster-manager file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"roster-manager context mismatch for {key}")
    return manifest


def load_roster_manager_choice_model(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_roster_manager_choice_artifact(manifest_path, expected=expected)
    try:
        payload = json.loads(
            (manifest_path.parent / "roster-manager-choice.json").read_text()
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("roster-manager model is malformed") from error
    if payload.get("model_version") != ROSTER_MANAGER_CHOICE_VERSION:
        raise ValueError("roster-manager model version mismatch")
    if payload.get("status") != manifest["status"]:
        raise ValueError("roster-manager model status mismatch")
    return {
        **payload,
        "population_factors": np.asarray(
            payload["population_factors"], dtype=np.float64
        ),
        "manager_factors": {
            row["manager_id"]: {
                "training_picks": row["training_picks"],
                "position_count_factors": np.asarray(
                    row["position_count_factors"], dtype=np.float64
                ),
            }
            for row in payload["managers"]
        },
    }


def manager_position_factors(model, manager_id, roster_positions):
    counts = Counter(str(position or "UNKNOWN").upper() for position in roster_positions)
    buckets = np.minimum(
        np.asarray([counts.get(position, 0) for position in POSITIONS]), 2
    )
    record = model["manager_factors"].get(str(manager_id))
    source = (
        record["position_count_factors"]
        if record is not None
        else model["population_factors"]
    )
    return {
        "factors": source[np.arange(len(POSITIONS)), buckets],
        "status": "personalized" if record is not None else "population",
        "training_picks": record["training_picks"] if record is not None else 0,
        "model_version": ROSTER_MANAGER_CHOICE_VERSION,
    }


def _source_positions_by_pick(source, draft_id):
    return {
        int(pick_no): POSITION_INDEX.get(str(position or "UNKNOWN").upper())
        for pick_no, position in source.execute(
            "SELECT pick_no, position FROM draft_picks WHERE draft_id = ?",
            (draft_id,),
        )
    }


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
