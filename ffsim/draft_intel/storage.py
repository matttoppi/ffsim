import hashlib
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ffsim.paths import CACHE_DIR


SCHEMA = """
CREATE TABLE IF NOT EXISTS managers (
    sleeper_user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_players (
    canonical_player_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    position TEXT NOT NULL,
    nfl_team TEXT,
    active INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_external_ids (
    canonical_player_id TEXT NOT NULL REFERENCES canonical_players(canonical_player_id),
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY (source, external_id),
    UNIQUE (canonical_player_id, source)
);

CREATE TABLE IF NOT EXISTS historical_leagues (
    league_id TEXT PRIMARY KEY,
    season INTEGER,
    status TEXT NOT NULL,
    name TEXT NOT NULL,
    best_ball INTEGER,
    max_keepers INTEGER,
    league_type INTEGER,
    roster_positions_json TEXT NOT NULL,
    raw_snapshot_hash TEXT NOT NULL,
    raw_snapshot_path TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_drafts (
    draft_id TEXT PRIMARY KEY,
    league_id TEXT,
    season INTEGER NOT NULL,
    season_type TEXT,
    status TEXT NOT NULL,
    draft_type TEXT NOT NULL,
    scoring_type TEXT,
    team_count INTEGER,
    rounds INTEGER,
    player_type INTEGER,
    roster_slots_json TEXT NOT NULL,
    created_at INTEGER,
    start_time INTEGER,
    last_picked_at INTEGER,
    context_hash TEXT NOT NULL,
    included INTEGER NOT NULL,
    exclusion_reasons_json TEXT NOT NULL,
    raw_snapshot_hash TEXT NOT NULL,
    raw_snapshot_path TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_draft_managers (
    draft_id TEXT NOT NULL REFERENCES historical_drafts(draft_id) ON DELETE CASCADE,
    manager_id TEXT NOT NULL REFERENCES managers(sleeper_user_id),
    draft_slot INTEGER,
    roster_id INTEGER,
    PRIMARY KEY (draft_id, manager_id)
);

CREATE TABLE IF NOT EXISTS historical_picks (
    draft_id TEXT NOT NULL REFERENCES historical_drafts(draft_id) ON DELETE CASCADE,
    pick_no INTEGER NOT NULL,
    round INTEGER,
    draft_slot INTEGER,
    roster_id INTEGER,
    manager_id TEXT,
    canonical_player_id TEXT,
    source_player_id TEXT NOT NULL,
    position TEXT,
    is_keeper INTEGER,
    PRIMARY KEY (draft_id, pick_no)
);
"""


def store_history(
    history,
    raw_responses,
    canonical_players,
    storage_dir=None,
    observed_at=None,
):
    if not raw_responses:
        raise ValueError("Raw Sleeper responses are required for persistence")

    storage_dir = Path(storage_dir or CACHE_DIR / "draft_intel")
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    payload = _json_bytes(raw_responses)
    snapshot_hash = hashlib.sha256(payload).hexdigest()
    snapshot_relative = Path("raw") / f"sleeper-history-{snapshot_hash}.json"
    snapshot_path = storage_dir / snapshot_relative
    if not snapshot_path.exists():
        _atomic_write(
            snapshot_path,
            _json_bytes({
                "source": "sleeper",
                "retrieved_at": observed_at,
                "responses": raw_responses,
            }),
        )

    database_path = storage_dir / "history.sqlite3"
    storage_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.executescript(SCHEMA)
        _store_normalized(
            connection,
            history,
            tuple(canonical_players),
            snapshot_hash,
            snapshot_relative.as_posix(),
            observed_at,
        )
    finally:
        connection.close()

    return {
        "database_path": str(database_path),
        "raw_snapshot_path": str(snapshot_path),
        "raw_snapshot_hash": snapshot_hash,
    }


def load_sleeper_identity_map(storage_dir=None):
    database_path = Path(storage_dir or CACHE_DIR / "draft_intel") / "history.sqlite3"
    if not database_path.exists():
        return {}
    connection = sqlite3.connect(database_path)
    try:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'player_external_ids'"
        ).fetchone()
        if not table_exists:
            return {}
        return dict(connection.execute(
            """
            SELECT external_id, canonical_player_id
            FROM player_external_ids
            WHERE source = 'sleeper'
            """
        ))
    finally:
        connection.close()


def _store_normalized(
    connection,
    history,
    canonical_players,
    snapshot_hash,
    snapshot_path,
    observed_at,
):
    picks_by_draft = defaultdict(list)
    for pick in history.picks:
        picks_by_draft[pick.draft_id].append(pick)

    with connection:
        connection.executemany(
            """
            INSERT INTO managers (sleeper_user_id, display_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sleeper_user_id) DO UPDATE SET
                display_name = excluded.display_name,
                updated_at = excluded.updated_at
            """,
            (
                (manager.user_id, manager.display_name, observed_at, observed_at)
                for manager in history.managers
            ),
        )
        connection.execute(
            """
            UPDATE canonical_players
            SET active = 0, updated_at = ?
            WHERE canonical_player_id IN (
                SELECT canonical_player_id
                FROM player_external_ids
                WHERE source = 'sleeper'
            )
            """,
            (observed_at,),
        )
        connection.executemany(
            """
            INSERT INTO canonical_players (
                canonical_player_id, full_name, normalized_name, position,
                nfl_team, active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_player_id) DO UPDATE SET
                full_name = excluded.full_name,
                normalized_name = excluded.normalized_name,
                position = excluded.position,
                nfl_team = excluded.nfl_team,
                active = excluded.active,
                updated_at = excluded.updated_at
            """,
            (
                (
                    player.canonical_player_id,
                    player.full_name,
                    player.normalized_name,
                    player.position,
                    player.nfl_team,
                    int(player.active),
                    observed_at,
                )
                for player in canonical_players
            ),
        )
        connection.executemany(
            """
            INSERT INTO player_external_ids (
                canonical_player_id, source, external_id,
                first_seen_at, last_seen_at, confidence
            ) VALUES (?, 'sleeper', ?, ?, ?, 1.0)
            ON CONFLICT(source, external_id) DO UPDATE SET
                canonical_player_id = excluded.canonical_player_id,
                last_seen_at = excluded.last_seen_at,
                confidence = excluded.confidence
            """,
            (
                (
                    player.canonical_player_id,
                    player.sleeper_id,
                    observed_at,
                    observed_at,
                )
                for player in canonical_players
            ),
        )
        connection.executemany(
            """
            INSERT INTO historical_leagues (
                league_id, season, status, name, best_ball, max_keepers,
                league_type, roster_positions_json, raw_snapshot_hash,
                raw_snapshot_path, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(league_id) DO UPDATE SET
                season = excluded.season,
                status = excluded.status,
                name = excluded.name,
                best_ball = excluded.best_ball,
                max_keepers = excluded.max_keepers,
                league_type = excluded.league_type,
                roster_positions_json = excluded.roster_positions_json,
                raw_snapshot_hash = excluded.raw_snapshot_hash,
                raw_snapshot_path = excluded.raw_snapshot_path,
                observed_at = excluded.observed_at
            """,
            (
                (
                    league.league_id,
                    league.season,
                    league.status,
                    league.name,
                    None if league.best_ball is None else int(league.best_ball),
                    league.max_keepers,
                    league.league_type,
                    json.dumps(league.roster_positions),
                    snapshot_hash,
                    snapshot_path,
                    observed_at,
                )
                for league in history.leagues
            ),
        )
        leagues_by_id = {league.league_id: league for league in history.leagues}
        for draft in history.drafts:
            connection.execute(
                """
                INSERT INTO historical_drafts (
                    draft_id, league_id, season, season_type, status, draft_type,
                    scoring_type, team_count, rounds, player_type, roster_slots_json,
                    created_at, start_time, last_picked_at, context_hash, included,
                    exclusion_reasons_json, raw_snapshot_hash, raw_snapshot_path, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_id) DO UPDATE SET
                    league_id = excluded.league_id,
                    season = excluded.season,
                    season_type = excluded.season_type,
                    status = excluded.status,
                    draft_type = excluded.draft_type,
                    scoring_type = excluded.scoring_type,
                    team_count = excluded.team_count,
                    rounds = excluded.rounds,
                    player_type = excluded.player_type,
                    roster_slots_json = excluded.roster_slots_json,
                    created_at = excluded.created_at,
                    start_time = excluded.start_time,
                    last_picked_at = excluded.last_picked_at,
                    context_hash = excluded.context_hash,
                    included = excluded.included,
                    exclusion_reasons_json = excluded.exclusion_reasons_json,
                    raw_snapshot_hash = excluded.raw_snapshot_hash,
                    raw_snapshot_path = excluded.raw_snapshot_path,
                    observed_at = excluded.observed_at
                """,
                (
                    draft.draft_id,
                    draft.league_id,
                    draft.season,
                    draft.season_type,
                    draft.status,
                    draft.draft_type,
                    draft.scoring_type,
                    draft.teams,
                    draft.rounds,
                    draft.player_type,
                    json.dumps(draft.roster_slots),
                    draft.created_at,
                    draft.start_time,
                    draft.last_picked_at,
                    _context_hash(draft, leagues_by_id.get(draft.league_id)),
                    int(draft.included),
                    json.dumps(draft.exclusion_reasons),
                    snapshot_hash,
                    snapshot_path,
                    observed_at,
                ),
            )
            connection.execute(
                "DELETE FROM historical_picks WHERE draft_id = ?",
                (draft.draft_id,),
            )

            draft_order = dict(draft.draft_order)
            roster_ids = dict(draft.slot_to_roster_id)
            connection.executemany(
                """
                INSERT INTO historical_draft_managers
                    (draft_id, manager_id, draft_slot, roster_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(draft_id, manager_id) DO UPDATE SET
                    draft_slot = COALESCE(
                        excluded.draft_slot,
                        historical_draft_managers.draft_slot
                    ),
                    roster_id = COALESCE(
                        excluded.roster_id,
                        historical_draft_managers.roster_id
                    )
                """,
                (
                    (
                        draft.draft_id,
                        manager_id,
                        draft_order.get(manager_id),
                        roster_ids.get(draft_order.get(manager_id)),
                    )
                    for manager_id in draft.manager_ids
                ),
            )
            connection.executemany(
                """
                INSERT INTO historical_picks (
                    draft_id, pick_no, round, draft_slot, roster_id, manager_id,
                    canonical_player_id, source_player_id, position, is_keeper
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        pick.draft_id,
                        pick.pick_no,
                        pick.round,
                        pick.draft_slot,
                        pick.roster_id,
                        pick.manager_id,
                        pick.canonical_player_id,
                        pick.player_id,
                        pick.position,
                        None if pick.is_keeper is None else int(pick.is_keeper),
                    )
                    for pick in picks_by_draft[draft.draft_id]
                ),
            )


def _context_hash(draft, league):
    return hashlib.sha256(_json_bytes({
        "season": draft.season,
        "season_type": draft.season_type,
        "draft_type": draft.draft_type,
        "scoring_type": draft.scoring_type,
        "teams": draft.teams,
        "rounds": draft.rounds,
        "player_type": draft.player_type,
        "roster_slots": draft.roster_slots,
        "best_ball": league.best_ball if league else None,
        "max_keepers": league.max_keepers if league else None,
        "league_type": league.league_type if league else None,
        "league_roster_positions": league.roster_positions if league else None,
    })).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        os.replace(temporary_path, path)
    finally:
        Path(temporary_path).unlink(missing_ok=True)
