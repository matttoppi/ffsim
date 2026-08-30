from pathlib import Path

from .ingest import (
    ingest_bracket,
    ingest_draft,
    ingest_drafts,
    ingest_league,
    ingest_league_users,
    ingest_matchups,
    ingest_picks,
    ingest_players,
    ingest_rosters,
    ingest_traded_picks,
    ingest_user_leagues,
)
from .outcomes import compute_team_seasons
from .store import Store


def rebuild_from_raw(source_store, output_dir):
    output_dir = Path(output_dir)
    if output_dir.resolve() == source_store.data_dir.resolve():
        raise ValueError("rebuild output must differ from the source data directory")
    if (output_dir / "historical_sleeper.sqlite3").exists():
        raise ValueError("rebuild output database already exists")
    target = Store(output_dir)
    endpoints = [row["endpoint"] for row in source_store.cached_endpoints()]
    for endpoint in sorted(endpoints, key=_endpoint_rank):
        payload, _ = source_store.cached_payload(endpoint)
        raw_hash = target.save_raw(endpoint, payload)
        _replay(target, endpoint, payload, raw_hash)

    with source_store.connect() as connection:
        seeds = connection.execute("SELECT * FROM seeds ORDER BY user_id").fetchall()
    with target.connect() as connection:
        for seed in seeds:
            if connection.execute("SELECT 1 FROM users WHERE user_id = ?", (seed["user_id"],)).fetchone():
                connection.execute(
                    """
                    INSERT OR REPLACE INTO seeds(user_id, username, source, added_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (seed["user_id"], seed["username"], seed["source"], seed["added_at"]),
                )
        leagues = connection.execute(
            """
            SELECT DISTINCT league_id, season FROM weekly_matchups
            UNION
            SELECT DISTINCT league_id, season FROM playoff_matches
            """
        ).fetchall()
    for league in leagues:
        compute_team_seasons(target, league["league_id"], league["season"])
    return target.status()


def _replay(store, endpoint, payload, raw_hash):
    parts = endpoint.split("/")
    if parts[0] == "user" and len(parts) == 2:
        if isinstance(payload, dict) and payload.get("user_id"):
            store.add_user(payload, raw_hash)
        return
    if parts[0] == "user" and len(parts) == 5 and parts[2] == "leagues":
        user_id, season = parts[1], int(parts[4])
        task = _task(user_id, season, mechanism="raw_rebuild")
        ingest_user_leagues(store, payload, raw_hash, task, max_depth=0)
        return
    if parts[0] == "league" and len(parts) == 2:
        season = int(payload["season"])
        ingest_league(store, payload, raw_hash, _task(parts[1], season, mechanism="raw_rebuild"))
        return
    if parts[0] == "league" and len(parts) >= 3:
        league_id = parts[1]
        season = _league_season(store, league_id)
        task = _task(league_id, season, mechanism="raw_rebuild")
        if parts[2] == "rosters":
            ingest_rosters(store, payload, raw_hash, task, max_depth=0)
        elif parts[2] == "users":
            ingest_league_users(store, payload, raw_hash)
        elif parts[2] == "drafts":
            ingest_drafts(store, payload, raw_hash, task)
        elif parts[2] in {"winners_bracket", "losers_bracket"}:
            bracket_type = parts[2].split("_", 1)[0]
            ingest_bracket(store, payload, raw_hash, league_id, season, bracket_type)
        elif parts[2] == "matchups":
            ingest_matchups(store, payload, raw_hash, league_id, season, int(parts[3]))
        return
    if parts[0] == "draft" and len(parts) == 2:
        ingest_draft(store, payload, raw_hash)
        return
    if parts[0] == "draft" and len(parts) == 3:
        if parts[2] == "picks":
            ingest_picks(store, payload, raw_hash, parts[1])
        elif parts[2] == "traded_picks":
            ingest_traded_picks(store, payload, raw_hash, parts[1])
        return
    if endpoint == "players/nfl":
        ingest_players(store, payload, raw_hash)


def _endpoint_rank(endpoint):
    parts = endpoint.split("/")
    if parts[0] == "user" and len(parts) == 2:
        return 0, endpoint
    if parts[0] == "user" and "leagues" in parts:
        return 1, endpoint
    if parts[0] == "league" and len(parts) == 2:
        return 2, endpoint
    if parts[0] == "league" and len(parts) == 3 and parts[2] in {"rosters", "users", "drafts"}:
        return 3, endpoint
    if parts[0] == "draft" and len(parts) == 2:
        return 4, endpoint
    if parts[0] == "draft":
        return 5, endpoint
    if parts[0] == "league":
        return 6, endpoint
    return 7, endpoint


def _league_season(store, league_id):
    with store.connect() as connection:
        rows = connection.execute(
            "SELECT season FROM league_seasons WHERE league_id = ? ORDER BY season DESC",
            (league_id,),
        ).fetchall()
    if len(rows) != 1:
        raise ValueError(f"cannot resolve one season for league {league_id}")
    return rows[0]["season"]


def _task(entity_id, season, *, mechanism):
    return {
        "entity_id": str(entity_id),
        "season": int(season),
        "depth": 0,
        "seed_user_id": None,
        "mechanism": mechanism,
    }
