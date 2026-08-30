import hashlib
import json
import sqlite3
from pathlib import Path

from scipy.stats import beta as beta_distribution

from .continuous_survival import _aggregate_samples
from .hdvn_snapshot import canonical_json, sha256_file
from .hierarchical_survival import SHRINKAGE, _probability, _tables

RANK20_SURVIVAL_VERSION = "hierarchical-position-survival-rank20-v1"
TARGET_COUNT = 20
EVIDENCE_SHA256 = "ccc41b021f42f362bc0cfdcc33a1c9b11e048a025c39f4839b2e31b869178335"


def build_rank20_survival_artifact(
    market_database,
    market_manifest,
    evidence,
    output_directory,
    *,
    expected_source_hash,
    expected_feature_hash,
    command,
    code_revision,
):
    market_database = Path(market_database).resolve()
    market_manifest = Path(market_manifest).resolve()
    evidence = Path(evidence).resolve()
    output_directory = Path(output_directory).resolve()
    model_path = output_directory / "rank20-survival.json"
    report_path = output_directory / "build-report.json"
    manifest_path = output_directory / "rank20-survival.manifest.json"
    paths = (model_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(
            f"immutable rank-20 survival output exists: {output_directory}"
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
    if sha256_file(evidence) != EVIDENCE_SHA256:
        raise ValueError("rank-20 evidence hash mismatch")
    result = json.loads(evidence.read_text())
    if (
        result.get("status") != "research"
        or not result.get("gate", {}).get("passes")
        or result.get("target_count") != TARGET_COUNT
        or result.get("locked_test_loaded") is not False
    ):
        raise ValueError("rank-20 evidence did not pass its frozen gate")

    connection = sqlite3.connect(
        f"file:{market_database}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        aggregate = _aggregate_samples(
            connection, (2021, 2022, 2023), TARGET_COUNT
        )
    finally:
        connection.close()
    model = _tables(aggregate["cells"])
    payload = {
        "model_version": RANK20_SURVIVAL_VERSION,
        "status": "research",
        "target_count": TARGET_COUNT,
        "shrinkage_observations": SHRINKAGE,
        "key_order": ["market_rank", "gap", "round", "position"],
        "global": list(model["global"]),
        "pooled_cells": [
            {"key": list(key), "successes": values[0], "count": values[1]}
            for key, values in sorted(model["pooled"].items())
        ],
        "position_cells": [
            {"key": list(key), "successes": values[0], "count": values[1]}
            for key, values in sorted(model["position"].items())
        ],
    }
    model_path.write_text(canonical_json(payload) + "\n")
    build_report = {
        "model_version": RANK20_SURVIVAL_VERSION,
        "status": "research",
        "target_count": TARGET_COUNT,
        "train_seasons": [2021, 2022, 2023],
        "builder_locked_test_loaded": False,
        "evidence_sha256": EVIDENCE_SHA256,
        "training_counts": aggregate["counts"],
        "frozen_gate": result["gate"],
        "terminal_candidate_coverage": result[
            "terminal_candidate_coverage"
        ],
        "limitations": [
            "offline research only",
            "2024 validation is recorded in the frozen evidence",
            "the builder did not query 2024 or 2025",
            "no live ranking, callback, or default shadow integration",
        ],
    }
    report_path.write_text(canonical_json(build_report) + "\n")
    manifest = {
        "model_version": RANK20_SURVIVAL_VERSION,
        "status": "research",
        "target_count": TARGET_COUNT,
        "source_snapshot_sha256": expected_source_hash,
        "feature_manifest_hash": expected_feature_hash,
        "market_manifest_hash": source_manifest["sha256"],
        "market_database_sha256": database_record["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "train_seasons": [2021, 2022, 2023],
        "builder_locked_test_loaded": False,
        "evidence_sha256": EVIDENCE_SHA256,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (model_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(
        canonical_json(manifest).encode()
    ).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_rank20_survival_artifact(
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


def load_rank20_survival_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "rank-20 survival manifest")
    if manifest.get("model_version") != RANK20_SURVIVAL_VERSION:
        raise ValueError("rank-20 survival version mismatch")
    if manifest.get("status") != "research":
        raise ValueError("rank-20 survival status is invalid")
    if manifest.get("target_count") != TARGET_COUNT:
        raise ValueError("rank-20 survival target count mismatch")
    if manifest.get("train_seasons") != [2021, 2022, 2023]:
        raise ValueError("rank-20 survival train seasons mismatch")
    if manifest.get("builder_locked_test_loaded") is not False:
        raise ValueError("rank-20 survival builder touched locked test")
    if manifest.get("evidence_sha256") != EVIDENCE_SHA256:
        raise ValueError("rank-20 survival evidence mismatch")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"rank-20 survival file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"rank-20 survival context mismatch for {key}")
    return manifest


def load_rank20_survival_model(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_rank20_survival_artifact(manifest_path, expected=expected)
    try:
        payload = json.loads(
            (manifest_path.parent / "rank20-survival.json").read_text()
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("rank-20 survival model is malformed") from error
    if payload.get("model_version") != RANK20_SURVIVAL_VERSION:
        raise ValueError("rank-20 survival model version mismatch")
    if payload.get("status") != manifest["status"]:
        raise ValueError("rank-20 survival model status mismatch")
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


def predict_rank20_survival(model, *, market_rank, gap, round_, position):
    rank = int(market_rank)
    if not 1 <= rank <= TARGET_COUNT:
        return {
            "status": "unavailable",
            "model_version": RANK20_SURVIVAL_VERSION,
            "target_count": TARGET_COUNT,
        }
    key = (rank, int(gap), int(round_), str(position))
    pooled = model["pooled"].get(key[:3], model["global"])
    direct = model["position"].get(key, (0, 0))
    prior = (pooled[0] + 1) / (pooled[1] + 2)
    alpha = direct[0] + SHRINKAGE * prior
    beta = direct[1] - direct[0] + SHRINKAGE * (1 - prior)
    return {
        "status": "available",
        "probability": alpha / (alpha + beta),
        "interval_95": (
            float(beta_distribution.ppf(0.025, alpha, beta)),
            float(beta_distribution.ppf(0.975, alpha, beta)),
        ),
        "raw_rate": direct[0] / direct[1] if direct[1] else None,
        "direct_support": direct[1],
        "pooled_support": pooled[1],
        "model_version": RANK20_SURVIVAL_VERSION,
        "target_count": TARGET_COUNT,
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
