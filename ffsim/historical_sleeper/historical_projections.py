import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from .hdvn_snapshot import canonical_json, sha256_file

HISTORICAL_PROJECTION_VERSION = "historical-projection-snapshot-v1"
REQUIRED_COLUMNS = {"sleeper_id", "projected_points"}
POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
REQUIRED_EVIDENCE = {
    "schema_version",
    "source",
    "season",
    "observed_at",
    "regular_season_start",
    "timestamp_evidence",
    "authorization",
    "scoring",
    "decision_reference",
    "raw_sha256",
    "player_id_namespace",
}


def import_historical_projection_snapshot(csv_path, evidence_path, output_directory):
    csv_path = Path(csv_path).resolve()
    evidence_path = Path(evidence_path).resolve()
    output_directory = Path(output_directory).resolve()
    raw_path = output_directory / "raw.csv"
    normalized_path = output_directory / "projections.json"
    manifest_path = output_directory / "projection-snapshot.manifest.json"
    paths = (raw_path, normalized_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(
            f"immutable historical projection output exists: {output_directory}"
        )
    try:
        evidence = json.loads(evidence_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("projection evidence is malformed") from error
    missing_evidence = REQUIRED_EVIDENCE - set(evidence)
    if missing_evidence:
        raise ValueError(
            f"projection evidence is missing {', '.join(sorted(missing_evidence))}"
        )
    if evidence["schema_version"] != HISTORICAL_PROJECTION_VERSION:
        raise ValueError("projection evidence schema version mismatch")
    if str(evidence["player_id_namespace"]).lower() != "sleeper":
        raise ValueError("historical projections require Sleeper player IDs")
    for key in (
        "source",
        "timestamp_evidence",
        "authorization",
        "scoring",
        "decision_reference",
    ):
        if not str(evidence[key]).strip():
            raise ValueError(f"projection evidence {key} is empty")
    observed_at = _timestamp(evidence["observed_at"], "observed_at")
    season_start = _timestamp(
        evidence["regular_season_start"], "regular_season_start"
    )
    if observed_at >= season_start:
        raise ValueError("projection observation must predate the regular season")
    raw = csv_path.read_bytes()
    raw_hash = hashlib.sha256(raw).hexdigest()
    if evidence["raw_sha256"] != raw_hash:
        raise ValueError("projection raw hash mismatch")

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing_columns = REQUIRED_COLUMNS - columns
        if missing_columns:
            raise ValueError(
                f"projection CSV is missing {', '.join(sorted(missing_columns))}"
            )
        rows = [_normalize_row(row) for row in reader]
    if not rows:
        raise ValueError("projection CSV has no rows")
    counts = Counter(row["sleeper_id"] for row in rows)
    duplicates = sorted(player_id for player_id, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"projection CSV has duplicate Sleeper IDs: {duplicates[:10]}")
    rows.sort(key=lambda row: row["sleeper_id"])

    output_directory.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    payload = {
        "snapshot_version": HISTORICAL_PROJECTION_VERSION,
        "source": evidence["source"],
        "season": int(evidence["season"]),
        "observed_at": observed_at.isoformat(),
        "regular_season_start": season_start.isoformat(),
        "scoring": evidence["scoring"],
        "target_draft_rule": "draft start must be at or after observed_at",
        "rows": rows,
    }
    normalized_path.write_text(canonical_json(payload) + "\n")
    manifest = {
        "snapshot_version": HISTORICAL_PROJECTION_VERSION,
        "status": "research_approved_source",
        "source": evidence["source"],
        "season": int(evidence["season"]),
        "observed_at": observed_at.isoformat(),
        "regular_season_start": season_start.isoformat(),
        "timestamp_evidence": evidence["timestamp_evidence"],
        "authorization": evidence["authorization"],
        "scoring": evidence["scoring"],
        "decision_reference": evidence["decision_reference"],
        "player_id_namespace": "sleeper",
        "row_count": len(rows),
        "target_draft_rule": "draft start must be at or after observed_at",
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (raw_path, normalized_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_historical_projection_snapshot(manifest_path)
    for path in paths:
        path.chmod(0o444)
    return manifest


def load_historical_projection_snapshot(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("projection manifest is malformed") from error
    stored = manifest.get("sha256")
    body = {key: value for key, value in manifest.items() if key != "sha256"}
    if stored != hashlib.sha256(canonical_json(body).encode()).hexdigest():
        raise ValueError("projection manifest hash mismatch")
    if manifest.get("snapshot_version") != HISTORICAL_PROJECTION_VERSION:
        raise ValueError("projection snapshot version mismatch")
    if manifest.get("status") != "research_approved_source":
        raise ValueError("projection snapshot status is not approved")
    if manifest.get("player_id_namespace") != "sleeper":
        raise ValueError("projection snapshot player namespace mismatch")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"projection snapshot file hash mismatch: {filename}")
    payload = json.loads((manifest_path.parent / "projections.json").read_text())
    if len(payload.get("rows", ())) != manifest["row_count"]:
        raise ValueError("projection snapshot row count mismatch")
    return {**manifest, "rows": payload["rows"]}


def projection_rows_for_draft(snapshot, draft_start):
    draft_start = _timestamp(draft_start, "draft_start")
    observed_at = _timestamp(snapshot["observed_at"], "observed_at")
    if draft_start < observed_at:
        raise ValueError("projection snapshot was not observable before this draft")
    return snapshot["rows"]


def _normalize_row(row):
    sleeper_id = str(row.get("sleeper_id") or "").strip()
    if not sleeper_id:
        raise ValueError("projection row has no Sleeper ID")
    try:
        projected_points = float(row["projected_points"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid projected points for {sleeper_id}") from error
    if not math.isfinite(projected_points) or projected_points < 0:
        raise ValueError(f"invalid projected points for {sleeper_id}")
    position = str(row.get("position") or "").strip().upper() or None
    if position is not None and position not in POSITIONS:
        raise ValueError(f"invalid projection position for {sleeper_id}: {position}")
    result = {
        "sleeper_id": sleeper_id,
        "projected_points": projected_points,
        "position": position,
    }
    if str(row.get("projected_games") or "").strip():
        try:
            games = float(row["projected_games"])
        except ValueError as error:
            raise ValueError(f"invalid projected games for {sleeper_id}") from error
        if not math.isfinite(games) or not 0 <= games <= 18:
            raise ValueError(f"invalid projected games for {sleeper_id}")
        result["projected_games"] = games
    return result


def _timestamp(value, label):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid projection {label}") from error
    if result.tzinfo is None:
        raise ValueError(f"projection {label} must include a timezone")
    return result
