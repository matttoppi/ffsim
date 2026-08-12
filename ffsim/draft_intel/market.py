import csv
import hashlib
import io
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ffsim.draft_intel.storage import SCHEMA, _atomic_write
from ffsim.paths import CACHE_DIR


CSV_COLUMNS = {"sleeper_id", "adp", "rank", "std_dev", "tier"}


def import_market_csv(
    csv_path,
    *,
    source,
    season,
    scoring,
    observed_at,
    team_count=None,
    storage_dir=None,
    retrieved_at=None,
):
    storage_dir = Path(storage_dir or CACHE_DIR / "draft_intel")
    database_path = storage_dir / "history.sqlite3"
    if not database_path.exists():
        raise FileNotFoundError("Draft intelligence store is missing; run draft-audit --persist first")

    observed_at = _timestamp(observed_at)
    retrieved_at = _timestamp(retrieved_at or datetime.now(timezone.utc))
    source = source.strip()
    scoring = scoring.strip()
    if not source or not scoring:
        raise ValueError("source and scoring are required")
    if season <= 0 or team_count is not None and team_count <= 0:
        raise ValueError("season and team_count must be positive")

    payload = Path(csv_path).read_bytes()
    raw_hash = hashlib.sha256(payload).hexdigest()
    snapshot_id = hashlib.sha256(
        json.dumps(
            {
                "raw_snapshot_hash": raw_hash,
                "source": source,
                "season": season,
                "scoring": scoring,
                "team_count": team_count,
                "observed_at": observed_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    raw_relative = Path("raw") / f"market-{raw_hash}.csv"
    raw_path = storage_dir / raw_relative

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.executescript(SCHEMA)
        observations = _parse_csv(payload, _sleeper_ids(connection))
        existing = connection.execute(
            "SELECT observation_count FROM market_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if existing:
            if existing[0] != len(observations):
                raise ValueError(f"Stored market snapshot {snapshot_id} conflicts with this import")
        else:
            if not raw_path.exists():
                _atomic_write(raw_path, payload)
            with connection:
                connection.execute(
                    """
                    INSERT INTO market_snapshots (
                        snapshot_id, source, source_type, season, scoring, team_count,
                        observed_at, retrieved_at, raw_snapshot_hash, raw_snapshot_path,
                        observation_count
                    ) VALUES (?, ?, 'manual_csv', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        source,
                        season,
                        scoring,
                        team_count,
                        observed_at,
                        retrieved_at,
                        raw_hash,
                        raw_relative.as_posix(),
                        len(observations),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO market_observations (
                        snapshot_id, canonical_player_id, source_player_id,
                        adp, rank, std_dev, tier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ((snapshot_id, *observation) for observation in observations),
                )
    finally:
        connection.close()

    return {
        "snapshot_id": snapshot_id,
        "database_path": str(database_path),
        "raw_snapshot_path": str(raw_path),
        "raw_snapshot_hash": raw_hash,
        "observation_count": len(observations),
    }


def load_market_snapshot_at(
    *,
    source,
    season,
    scoring,
    at,
    team_count=None,
    max_age=None,
    storage_dir=None,
):
    database_path = Path(storage_dir or CACHE_DIR / "draft_intel") / "history.sqlite3"
    if not database_path.exists():
        return None

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        at = _timestamp(at)
        snapshot = connection.execute(
            """
            SELECT * FROM market_snapshots
            WHERE source = ? AND season = ? AND scoring = ?
              AND team_count IS ? AND observed_at <= ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            (source, season, scoring, team_count, at),
        ).fetchone()
        if snapshot is None:
            return None
        if max_age is not None:
            age = datetime.fromisoformat(at) - datetime.fromisoformat(snapshot["observed_at"])
            if age > max_age:
                return None
        observations = connection.execute(
            """
            SELECT canonical_player_id, source_player_id, adp, rank, std_dev, tier
            FROM market_observations
            WHERE snapshot_id = ?
            ORDER BY COALESCE(rank, adp), canonical_player_id
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()
        result = dict(snapshot)
        result["observations"] = [dict(observation) for observation in observations]
        return result
    finally:
        connection.close()


def _sleeper_ids(connection):
    return dict(connection.execute(
        """
        SELECT external_id, canonical_player_id
        FROM player_external_ids
        WHERE source = 'sleeper'
        """
    ))


def _parse_csv(payload, sleeper_ids):
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""))
    except UnicodeDecodeError as error:
        raise ValueError("Market CSV must be UTF-8") from error
    fieldnames = reader.fieldnames or ()
    columns = set(fieldnames)
    if len(columns) != len(fieldnames):
        raise ValueError("Market CSV has duplicate columns")
    if "sleeper_id" not in columns or not {"adp", "rank"} & columns:
        raise ValueError("Market CSV requires sleeper_id and at least one of adp or rank")
    unknown_columns = columns - CSV_COLUMNS
    if unknown_columns:
        raise ValueError(f"Unknown market CSV columns: {', '.join(sorted(unknown_columns))}")

    observations = []
    seen = set()
    for line_number, row in enumerate(reader, start=2):
        if None in row:
            raise ValueError(f"Too many values on line {line_number}")
        sleeper_id = (row["sleeper_id"] or "").strip()
        if not sleeper_id:
            raise ValueError(f"Missing sleeper_id on line {line_number}")
        if sleeper_id in seen:
            raise ValueError(f"Duplicate sleeper_id {sleeper_id} on line {line_number}")
        canonical_player_id = sleeper_ids.get(sleeper_id)
        if canonical_player_id is None:
            raise ValueError(f"Unknown sleeper_id {sleeper_id} on line {line_number}")

        adp = _number(row, "adp", line_number, float)
        rank = _number(row, "rank", line_number, int)
        std_dev = _number(row, "std_dev", line_number, float)
        tier = _number(row, "tier", line_number, int)
        if adp is None and rank is None:
            raise ValueError(f"Line {line_number} requires adp or rank")
        if any(value is not None and value <= 0 for value in (adp, rank, tier)):
            raise ValueError(f"adp, rank, and tier must be positive on line {line_number}")
        if std_dev is not None and std_dev < 0:
            raise ValueError(f"std_dev must be non-negative on line {line_number}")
        observations.append((canonical_player_id, sleeper_id, adp, rank, std_dev, tier))
        seen.add(sleeper_id)
    if not observations:
        raise ValueError("Market CSV has no observations")
    return observations


def _number(row, name, line_number, value_type):
    value = (row.get(name) or "").strip()
    if not value:
        return None
    try:
        converted = value_type(value)
    except ValueError as error:
        raise ValueError(f"Invalid {name} on line {line_number}: {value}") from error
    if isinstance(converted, float) and not math.isfinite(converted):
        raise ValueError(f"Invalid {name} on line {line_number}: {value}")
    if value_type is int and str(converted) != value:
        raise ValueError(f"Invalid {name} on line {line_number}: {value}")
    return converted


def _timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Market snapshot timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat()
