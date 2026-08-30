import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .schema import SCHEMA_VERSION


CANONICAL_TABLES = (
    "metadata",
    "raw_objects",
    "users",
    "seeds",
    "league_seasons",
    "league_provenance",
    "rosters",
    "drafts",
    "players",
    "draft_picks",
    "traded_draft_picks",
    "weekly_matchups",
    "playoff_matches",
    "team_seasons",
    "quality_flags",
    "crawl_queue",
    "hydration_queue",
    "request_failures",
)
RAW_HASH_TABLES = (
    "users",
    "league_seasons",
    "rosters",
    "drafts",
    "players",
    "draft_picks",
    "traded_draft_picks",
    "weekly_matchups",
    "playoff_matches",
)


TRAINING_READY_CTE = """
WITH ready AS (
    SELECT h.league_id, h.season
    FROM hydration_queue AS h
    JOIN league_seasons AS l USING (league_id, season)
    WHERE h.status = 'done'
      AND l.is_candidate = 1
      AND (SELECT COUNT(*) FROM rosters AS r
           WHERE r.league_id = h.league_id AND r.season = h.season) = l.total_rosters
      AND EXISTS (
          SELECT 1 FROM drafts AS d
          WHERE d.league_id = h.league_id AND d.season = h.season
            AND d.status = 'complete' AND d.draft_type = 'snake'
            AND d.team_count = l.total_rosters AND d.rounds > 0
            AND (SELECT COUNT(*) FROM draft_picks AS p WHERE p.draft_id = d.draft_id)
                = d.team_count * d.rounds
            AND NOT EXISTS (
                SELECT 1 FROM draft_picks AS p
                WHERE p.draft_id = d.draft_id AND p.is_keeper = 1
            )
      )
      AND l.playoff_week_start > 1
      AND (SELECT COUNT(*) FROM weekly_matchups AS w
           WHERE w.league_id = h.league_id AND w.season = h.season
             AND w.week < l.playoff_week_start)
          = l.total_rosters * (l.playoff_week_start - 1)
      AND (SELECT COUNT(*) FROM team_seasons AS t
           WHERE t.league_id = h.league_id AND t.season = h.season) = l.total_rosters
      AND (SELECT COUNT(*) FROM team_seasons AS t
           WHERE t.league_id = h.league_id AND t.season = h.season
             AND t.champion = 1) = 1
      AND NOT EXISTS (
          SELECT 1 FROM quality_flags AS q
          WHERE q.severity = 'error'
            AND ((q.scope = 'league_season'
                  AND q.entity_key = h.league_id || ':' || h.season)
                 OR (q.scope = 'draft' AND q.entity_key IN (
                     SELECT draft_id FROM drafts
                     WHERE league_id = h.league_id AND season = h.season
                 )))
      )
)
"""


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path, *, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def create_snapshot(source_database, snapshot_database, *, captured_at=None, pages=256):
    """Create one immutable SQLite backup and its deterministic JSON manifest."""
    source_database = Path(source_database).expanduser().resolve()
    snapshot_database = Path(snapshot_database).expanduser().resolve()
    manifest_path = snapshot_database.with_suffix(snapshot_database.suffix + ".manifest.json")
    if not source_database.is_file():
        raise FileNotFoundError(source_database)
    if snapshot_database.exists() or manifest_path.exists():
        raise FileExistsError(f"immutable snapshot already exists: {snapshot_database}")
    if source_database == snapshot_database:
        raise ValueError("snapshot must differ from source database")
    if pages < 1:
        raise ValueError("backup page batch must be positive")

    snapshot_database.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source_database.as_posix()}?mode=ro"
    try:
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            with closing(sqlite3.connect(snapshot_database)) as destination:
                source.backup(destination, pages=pages)
        captured_at = captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest = inspect_snapshot(
            snapshot_database,
            source_database=source_database,
            captured_at=captured_at,
        )
        manifest_path.write_text(canonical_json(manifest) + "\n")
    except BaseException:
        snapshot_database.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    return manifest


def inspect_snapshot(snapshot_database, *, source_database, captured_at):
    snapshot_database = Path(snapshot_database).resolve()
    connection = sqlite3.connect(f"file:{snapshot_database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        schema_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        schema_version = int(schema_row[0]) if schema_row else SCHEMA_VERSION
        table_counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in CANONICAL_TABLES
        }
        strict_context = [
            dict(row)
            for row in connection.execute(
                TRAINING_READY_CTE
                + """
                SELECT l.season, l.total_rosters AS team_count, l.scoring_format,
                       COUNT(*) AS league_seasons
                FROM ready
                JOIN league_seasons AS l USING (league_id, season)
                GROUP BY l.season, l.total_rosters, l.scoring_format
                ORDER BY l.season, l.total_rosters, l.scoring_format
                """
            )
        ]
        quality_flags = [
            dict(row)
            for row in connection.execute(
                """
                SELECT severity, code, COUNT(*) AS count
                FROM quality_flags GROUP BY severity, code ORDER BY severity, code
                """
            )
        ]
        hydration_states = {
            row["status"]: row["count"]
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM hydration_queue GROUP BY status ORDER BY status"
            )
        }
        raw_coverage = {}
        for table in RAW_HASH_TABLES:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS rows,
                       SUM(CASE WHEN raw_hash IS NOT NULL THEN 1 ELSE 0 END) AS with_raw_hash,
                       COUNT(DISTINCT raw_hash) AS distinct_raw_hashes
                FROM "{table}"
                """
            ).fetchone()
            raw_coverage[table] = {
                "rows": row["rows"],
                "with_raw_hash": row["with_raw_hash"] or 0,
                "distinct_raw_hashes": row["distinct_raw_hashes"],
            }
        graph_provenance = [
            dict(row)
            for row in connection.execute(
                """
                SELECT COALESCE(seed_user_id, 'unknown') AS seed_user_id,
                       discovery_depth, mechanism,
                       COUNT(DISTINCT league_id || ':' || season) AS league_seasons
                FROM league_provenance
                GROUP BY seed_user_id, discovery_depth, mechanism
                ORDER BY seed_user_id, discovery_depth, mechanism
                """
            )
        ]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = [dict(row) for row in connection.execute("PRAGMA foreign_key_check")]
    finally:
        connection.close()

    return {
        "manifest_version": 1,
        "source_database": str(Path(source_database).resolve()),
        "snapshot_database": snapshot_database.name,
        "schema_version": schema_version,
        "snapshot_time": captured_at,
        "byte_size": snapshot_database.stat().st_size,
        "sha256": sha256_file(snapshot_database),
        "integrity_check": integrity,
        "foreign_key_errors": foreign_key_errors,
        "canonical_counts": table_counts,
        "strict_training_ready": {
            "total": sum(row["league_seasons"] for row in strict_context),
            "by_context": strict_context,
        },
        "quality_flags": quality_flags,
        "hydration_states": hydration_states,
        "raw_object_coverage": {
            "stored_objects": table_counts["raw_objects"],
            "tables": raw_coverage,
        },
        "graph_provenance": graph_provenance,
    }
