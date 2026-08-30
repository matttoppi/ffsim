import json

from .store import json_text, utc_now


TARGET_SEASONS = (2021, 2022, 2023, 2024, 2025)
IDP_POSITIONS = {"DB", "DL", "IDP", "LB", "CB", "S", "DE", "DT"}


def ingest_user_leagues(store, payload, raw_hash, task, *, max_depth):
    if not isinstance(payload, list):
        raise ValueError("user leagues response must be a list")
    for league in payload:
        season = _required_int(league, "season")
        league_id = _required_text(league, "league_id")
        _upsert_league(store, league, raw_hash, season)
        _record_provenance(
            store,
            league_id,
            season,
            task,
            discovering_user_id=task["entity_id"],
            mechanism="user_graph",
        )
        _enqueue_league_parts(store, league_id, season, task)
        previous = _source_id(league.get("previous_league_id"))
        if previous:
            store.enqueue_crawl(
                "league",
                previous,
                season - 1,
                depth=task["depth"],
                seed_user_id=task["seed_user_id"],
                mechanism="previous_league",
            )


def ingest_league(store, payload, raw_hash, task):
    if not isinstance(payload, dict):
        raise ValueError("league response must be an object")
    league_id = _required_text(payload, "league_id")
    if league_id != task["entity_id"]:
        raise ValueError(f"expected league {task['entity_id']}, got {league_id}")
    season = _required_int(payload, "season")
    _upsert_league(store, payload, raw_hash, season)
    _record_provenance(
        store,
        league_id,
        season,
        task,
        source_league_id=None,
        mechanism=task["mechanism"],
    )
    _enqueue_league_parts(store, league_id, season, task)
    previous = _source_id(payload.get("previous_league_id"))
    if previous:
        store.enqueue_crawl(
            "league",
            previous,
            season - 1,
            depth=task["depth"],
            seed_user_id=task["seed_user_id"],
            mechanism="previous_league",
        )


def ingest_rosters(store, payload, raw_hash, task, *, max_depth):
    if not isinstance(payload, list):
        raise ValueError("rosters response must be a list")
    league_id = task["entity_id"]
    season = int(task["season"])
    now = utc_now()
    seen = set()
    owner_ids = set()
    with store.connect() as connection:
        for roster in payload:
            roster_id = _required_int(roster, "roster_id")
            if roster_id in seen:
                _quality(connection, "league_season", f"{league_id}:{season}", "duplicate_roster_id", "error", {"roster_id": roster_id})
                continue
            seen.add(roster_id)
            owner_id = _text(roster.get("owner_id"))
            if owner_id:
                owner_ids.add(owner_id)
            connection.execute(
                """
                INSERT INTO rosters (
                    league_id, season, roster_id, owner_id, co_owners_json,
                    players_json, starters_json, reserve_json, settings_json,
                    raw_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(league_id, season, roster_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    co_owners_json = excluded.co_owners_json,
                    players_json = excluded.players_json,
                    starters_json = excluded.starters_json,
                    reserve_json = excluded.reserve_json,
                    settings_json = excluded.settings_json,
                    raw_hash = excluded.raw_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    league_id,
                    season,
                    roster_id,
                    owner_id,
                    json_text(roster.get("co_owners") or []),
                    json_text(roster.get("players") or []),
                    json_text(roster.get("starters") or []),
                    json_text(roster.get("reserve") or []),
                    json_text(roster.get("settings") or {}),
                    raw_hash,
                    now,
                ),
            )
            if owner_id:
                connection.execute(
                    """
                    INSERT INTO users(user_id, first_seen_at, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO NOTHING
                    """,
                    (owner_id, now, now),
                )
        expected = connection.execute(
            "SELECT total_rosters FROM league_seasons WHERE league_id = ? AND season = ?",
            (league_id, season),
        ).fetchone()
        if expected and expected[0] is not None and expected[0] != len(seen):
            _quality(
                connection,
                "league_season",
                f"{league_id}:{season}",
                "roster_count_mismatch",
                "error",
                {"expected": expected[0], "actual": len(seen)},
            )
    if task["depth"] < max_depth:
        store.enqueue_user_seasons(
            owner_ids,
            TARGET_SEASONS,
            depth=task["depth"] + 1,
            seed_user_id=task["seed_user_id"],
            mechanism="roster_owner",
        )


def ingest_league_users(store, payload, raw_hash):
    if not isinstance(payload, list):
        raise ValueError("league users response must be a list")
    for user in payload:
        store.add_user(user, raw_hash)


def ingest_drafts(store, payload, raw_hash, task):
    if not isinstance(payload, list):
        raise ValueError("league drafts response must be a list")
    for draft in payload:
        _upsert_draft(store, draft, raw_hash, fallback_season=task["season"])
    refresh_candidate(store, task["entity_id"], int(task["season"]))


def ingest_draft(store, payload, raw_hash, *, fallback_season=None):
    if not isinstance(payload, dict):
        raise ValueError("draft response must be an object")
    _upsert_draft(store, payload, raw_hash, fallback_season=fallback_season)


def ingest_picks(store, payload, raw_hash, draft_id):
    if not isinstance(payload, list):
        raise ValueError("draft picks response must be a list")
    with store.connect() as connection:
        draft = connection.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        if draft is None:
            raise ValueError(f"draft {draft_id} must be ingested before its picks")
        slot_map = json.loads(draft["slot_to_roster_id_json"])
        connection.execute("DELETE FROM draft_picks WHERE draft_id = ?", (draft_id,))
        seen_pick_numbers = set()
        seen_players = set()
        duplicate_pick_numbers = []
        duplicate_players = []
        for pick in payload:
            source_draft_id = _required_text(pick, "draft_id")
            if source_draft_id != draft_id:
                raise ValueError(f"pick belongs to draft {source_draft_id}, not {draft_id}")
            pick_no = _required_int(pick, "pick_no")
            if pick_no in seen_pick_numbers:
                duplicate_pick_numbers.append(pick_no)
                continue
            seen_pick_numbers.add(pick_no)
            player_id = _text(pick.get("player_id"))
            if player_id and player_id in seen_players:
                duplicate_players.append(player_id)
            if player_id:
                seen_players.add(player_id)
            roster_id = _int(pick.get("roster_id"))
            draft_slot = _int(pick.get("draft_slot"))
            inferred_roster_id = _int(slot_map.get(str(draft_slot))) if draft_slot is not None else None
            effective_roster_id = roster_id if roster_id is not None else inferred_roster_id
            ownership_source = "source_roster_id" if roster_id is not None else ("slot_map" if inferred_roster_id is not None else "unknown")
            metadata = pick.get("metadata") or {}
            connection.execute(
                """
                INSERT INTO draft_picks (
                    draft_id, pick_no, league_id, season, round, draft_slot,
                    roster_id, effective_roster_id, ownership_source, picked_by,
                    player_id, is_keeper, picked_at_ms, position, nfl_team,
                    metadata_json, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    pick_no,
                    draft["league_id"],
                    draft["season"],
                    _int(pick.get("round")),
                    draft_slot,
                    roster_id,
                    effective_roster_id,
                    ownership_source,
                    _text(pick.get("picked_by")),
                    player_id,
                    _bool_int(pick.get("is_keeper")),
                    _int(pick.get("picked_at")),
                    _text(metadata.get("position")),
                    _text(metadata.get("team")),
                    json_text(metadata),
                    raw_hash,
                ),
            )
            if player_id:
                _upsert_player(connection, player_id, metadata, raw_hash)
        entity_key = draft_id
        if duplicate_pick_numbers:
            _quality(connection, "draft", entity_key, "duplicate_pick_number", "error", {"pick_numbers": duplicate_pick_numbers})
        if duplicate_players:
            _quality(connection, "draft", entity_key, "duplicate_player_pick", "error", {"player_ids": duplicate_players})
        expected = None
        if draft["team_count"] and draft["rounds"]:
            expected = draft["team_count"] * draft["rounds"]
        if draft["status"] == "complete" and expected != len(seen_pick_numbers):
            _quality(connection, "draft", entity_key, "draft_pick_count_mismatch", "error", {"expected": expected, "actual": len(seen_pick_numbers)})
        elif expected is not None:
            _delete_quality(connection, "draft", entity_key, "draft_pick_count_mismatch")
        if any(pick.get("is_keeper") is True for pick in payload):
            _quality(connection, "draft", entity_key, "keeper_picks", "info", {})
        else:
            _delete_quality(connection, "draft", entity_key, "keeper_picks")
    if draft["league_id"]:
        refresh_candidate(store, draft["league_id"], draft["season"])

def ingest_traded_picks(store, payload, raw_hash, draft_id):
    if not isinstance(payload, list):
        raise ValueError("traded picks response must be a list")
    with store.connect() as connection:
        connection.execute("DELETE FROM traded_draft_picks WHERE draft_id = ?", (draft_id,))
        for pick in payload:
            connection.execute(
                """
                INSERT INTO traded_draft_picks (
                    draft_id, season, round, roster_id, previous_owner_id,
                    owner_id, raw_json, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    _int(pick.get("season")),
                    _required_int(pick, "round"),
                    _required_int(pick, "roster_id"),
                    _int(pick.get("previous_owner_id")),
                    _required_int(pick, "owner_id"),
                    json_text(pick),
                    raw_hash,
                ),
            )


def ingest_matchups(store, payload, raw_hash, league_id, season, week):
    if not isinstance(payload, list):
        raise ValueError("matchups response must be a list")
    seen = set()
    with store.connect() as connection:
        connection.execute(
            "DELETE FROM weekly_matchups WHERE league_id = ? AND season = ? AND week = ?",
            (league_id, season, week),
        )
        for matchup in payload:
            roster_id = _required_int(matchup, "roster_id")
            if roster_id in seen:
                _quality(connection, "league_week", f"{league_id}:{season}:{week}", "duplicate_matchup_roster", "error", {"roster_id": roster_id})
                continue
            seen.add(roster_id)
            connection.execute(
                """
                INSERT INTO weekly_matchups (
                    league_id, season, week, roster_id, matchup_id, points,
                    custom_points, starters_json, players_json, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    league_id,
                    season,
                    week,
                    roster_id,
                    _int(matchup.get("matchup_id")),
                    _float(matchup.get("points")),
                    _float(matchup.get("custom_points")),
                    json_text(matchup.get("starters") or []),
                    json_text(matchup.get("players") or []),
                    raw_hash,
                ),
            )


def ingest_bracket(store, payload, raw_hash, league_id, season, bracket_type):
    if not isinstance(payload, list):
        raise ValueError("playoff bracket response must be a list")
    with store.connect() as connection:
        connection.execute(
            "DELETE FROM playoff_matches WHERE league_id = ? AND season = ? AND bracket_type = ?",
            (league_id, season, bracket_type),
        )
        seen = set()
        for match in payload:
            match_id = _required_int(match, "m")
            if match_id in seen:
                _quality(connection, "league_season", f"{league_id}:{season}", f"duplicate_{bracket_type}_match", "error", {"match_id": match_id})
                continue
            seen.add(match_id)
            connection.execute(
                """
                INSERT INTO playoff_matches (
                    league_id, season, bracket_type, match_id, round, team_1,
                    team_2, winner, loser, placement, raw_json, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    league_id,
                    season,
                    bracket_type,
                    match_id,
                    _int(match.get("r")),
                    _int(match.get("t1")),
                    _int(match.get("t2")),
                    _int(match.get("w")),
                    _int(match.get("l")),
                    _int(match.get("p")),
                    json_text(match),
                    raw_hash,
                ),
            )


def ingest_players(store, payload, raw_hash):
    if not isinstance(payload, dict):
        raise ValueError("players response must be an object")
    now = utc_now()
    with store.connect() as connection:
        for source_id, player in payload.items():
            if not isinstance(player, dict):
                continue
            player_id = str(player.get("player_id") or source_id)
            _upsert_player(connection, player_id, player, raw_hash, now=now)


def refresh_candidate(store, league_id, season):
    with store.connect() as connection:
        league = connection.execute(
            "SELECT * FROM league_seasons WHERE league_id = ? AND season = ?",
            (league_id, season),
        ).fetchone()
        if league is None:
            return
        reasons = []
        settings = json.loads(league["settings_json"])
        positions = json.loads(league["roster_positions_json"])
        if season not in TARGET_SEASONS:
            reasons.append("outside_target_seasons")
        if league["status"] != "complete":
            reasons.append("season_not_complete")
        if league["total_rosters"] not in {10, 12}:
            reasons.append("team_count_not_10_or_12")
        if league["league_type"] != 0:
            reasons.append("not_confirmed_redraft_type")
        if league["best_ball"] != 0:
            reasons.append("best_ball_or_unknown")
        if positions.count("QB") != 1 or any(position in {"SUPER_FLEX", "OP"} for position in positions):
            reasons.append("not_one_qb")
        if IDP_POSITIONS.intersection(positions):
            reasons.append("idp_roster")
        if league["scoring_format"] not in {"STD", "HALF_PPR", "PPR"}:
            reasons.append("unsupported_or_unknown_reception_scoring")
        drafts = connection.execute(
            "SELECT draft_id, status, draft_type FROM drafts WHERE league_id = ? AND season = ?",
            (league_id, season),
        ).fetchall()
        eligible_drafts = [row for row in drafts if row["status"] == "complete" and row["draft_type"] == "snake"]
        if not eligible_drafts:
            reasons.append("complete_snake_draft_missing")
        elif any(
            connection.execute(
                "SELECT 1 FROM draft_picks WHERE draft_id = ? AND is_keeper = 1 LIMIT 1",
                (row["draft_id"],),
            ).fetchone()
            for row in eligible_drafts
        ):
            reasons.append("keeper_picks")
        connection.execute(
            """
            UPDATE league_seasons
            SET is_candidate = ?, candidate_reasons_json = ?
            WHERE league_id = ? AND season = ?
            """,
            (int(not reasons), json_text(reasons), league_id, season),
        )


def _upsert_league(store, league, raw_hash, fallback_season):
    league_id = _required_text(league, "league_id")
    season = _int(league.get("season")) or int(fallback_season)
    settings = league.get("settings") or {}
    scoring = league.get("scoring_settings") or {}
    positions = league.get("roster_positions") or []
    now = utc_now()
    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO league_seasons (
                league_id, season, name, status, season_type, total_rosters,
                previous_league_id, draft_id, league_type, best_ball,
                max_keepers, playoff_teams, playoff_week_start, last_scored_leg,
                settings_json, scoring_settings_json, roster_positions_json,
                scoring_format, raw_hash, first_seen_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(league_id, season) DO UPDATE SET
                name = excluded.name,
                status = excluded.status,
                season_type = excluded.season_type,
                total_rosters = excluded.total_rosters,
                previous_league_id = excluded.previous_league_id,
                draft_id = excluded.draft_id,
                league_type = excluded.league_type,
                best_ball = excluded.best_ball,
                max_keepers = excluded.max_keepers,
                playoff_teams = excluded.playoff_teams,
                playoff_week_start = excluded.playoff_week_start,
                last_scored_leg = excluded.last_scored_leg,
                settings_json = excluded.settings_json,
                scoring_settings_json = excluded.scoring_settings_json,
                roster_positions_json = excluded.roster_positions_json,
                scoring_format = excluded.scoring_format,
                raw_hash = excluded.raw_hash,
                updated_at = excluded.updated_at
            """,
            (
                league_id,
                season,
                str(league.get("name") or ""),
                _text(league.get("status")),
                _text(league.get("season_type")),
                _int(league.get("total_rosters")) or _int(settings.get("num_teams")),
                _source_id(league.get("previous_league_id")),
                _source_id(league.get("draft_id")),
                _int(settings.get("type")),
                _bool_int(settings.get("best_ball")),
                _int(settings.get("max_keepers")),
                _int(settings.get("playoff_teams")),
                _int(settings.get("playoff_week_start")),
                _int(settings.get("last_scored_leg")),
                json_text(settings),
                json_text(scoring),
                json_text(positions),
                _scoring_format(scoring),
                raw_hash,
                now,
                now,
            ),
        )
    refresh_candidate(store, league_id, season)


def _upsert_draft(store, draft, raw_hash, fallback_season=None):
    draft_id = _required_text(draft, "draft_id")
    settings = draft.get("settings") or {}
    metadata = draft.get("metadata") or {}
    season = _int(draft.get("season")) or _int(fallback_season)
    if season is None:
        raise ValueError(f"draft {draft_id} is missing season")
    now = utc_now()
    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO drafts (
                draft_id, league_id, season, status, draft_type, season_type,
                team_count, rounds, start_time, created_at_ms, last_picked_ms,
                scoring_type, draft_order_json, slot_to_roster_id_json,
                settings_json, metadata_json, raw_hash, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(draft_id) DO UPDATE SET
                league_id = excluded.league_id,
                season = excluded.season,
                status = excluded.status,
                draft_type = excluded.draft_type,
                season_type = excluded.season_type,
                team_count = excluded.team_count,
                rounds = excluded.rounds,
                start_time = excluded.start_time,
                created_at_ms = excluded.created_at_ms,
                last_picked_ms = excluded.last_picked_ms,
                scoring_type = excluded.scoring_type,
                draft_order_json = excluded.draft_order_json,
                slot_to_roster_id_json = excluded.slot_to_roster_id_json,
                settings_json = excluded.settings_json,
                metadata_json = excluded.metadata_json,
                raw_hash = excluded.raw_hash,
                updated_at = excluded.updated_at
            """,
            (
                draft_id,
                _source_id(draft.get("league_id")),
                season,
                _text(draft.get("status")),
                _text(draft.get("type")),
                _text(draft.get("season_type")),
                _int(settings.get("teams")),
                _int(settings.get("rounds")),
                _int(draft.get("start_time")),
                _int(draft.get("created")),
                _int(draft.get("last_picked")),
                _text(metadata.get("scoring_type")),
                json_text(draft.get("draft_order") or {}),
                json_text(draft.get("slot_to_roster_id") or {}),
                json_text(settings),
                json_text(metadata),
                raw_hash,
                now,
            ),
        )


def _upsert_player(connection, player_id, player, raw_hash, now=None):
    now = now or utc_now()
    full_name = _text(player.get("full_name"))
    if not full_name:
        full_name = " ".join(filter(None, [_text(player.get("first_name")), _text(player.get("last_name"))])) or None
    connection.execute(
        """
        INSERT INTO players (
            player_id, full_name, first_name, last_name, position, nfl_team,
            status, active, birth_date, years_exp, raw_json, raw_hash, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            full_name = COALESCE(excluded.full_name, players.full_name),
            first_name = COALESCE(excluded.first_name, players.first_name),
            last_name = COALESCE(excluded.last_name, players.last_name),
            position = COALESCE(excluded.position, players.position),
            nfl_team = COALESCE(excluded.nfl_team, players.nfl_team),
            status = COALESCE(excluded.status, players.status),
            active = COALESCE(excluded.active, players.active),
            birth_date = COALESCE(excluded.birth_date, players.birth_date),
            years_exp = COALESCE(excluded.years_exp, players.years_exp),
            raw_json = excluded.raw_json,
            raw_hash = COALESCE(excluded.raw_hash, players.raw_hash),
            updated_at = excluded.updated_at
        """,
        (
            player_id,
            full_name,
            _text(player.get("first_name")),
            _text(player.get("last_name")),
            _text(player.get("position")),
            _text(player.get("team")),
            _text(player.get("status")),
            _bool_int(player.get("active")),
            _text(player.get("birth_date")),
            _int(player.get("years_exp")),
            json_text(player),
            raw_hash,
            now,
        ),
    )


def _enqueue_league_parts(store, league_id, season, task):
    for task_type in ("league_rosters", "league_users", "league_drafts"):
        store.enqueue_crawl(
            task_type,
            league_id,
            season,
            depth=task["depth"],
            seed_user_id=task["seed_user_id"],
            mechanism=task["mechanism"],
        )


def _record_provenance(
    store,
    league_id,
    season,
    task,
    *,
    discovering_user_id=None,
    source_league_id=None,
    mechanism,
):
    with store.connect() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO league_provenance (
                league_id, season, seed_user_id, discovery_depth,
                discovering_user_id, source_league_id, mechanism, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                league_id,
                season,
                task.get("seed_user_id"),
                task["depth"],
                discovering_user_id,
                source_league_id,
                mechanism,
                utc_now(),
            ),
        )


def _quality(connection, scope, entity_key, code, severity, details):
    connection.execute(
        """
        INSERT INTO quality_flags (
            scope, entity_key, code, severity, details_json, detected_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(scope, entity_key, code) DO UPDATE SET
            severity = excluded.severity,
            details_json = excluded.details_json,
            detected_at = excluded.detected_at
        """,
        (scope, entity_key, code, severity, json_text(details), utc_now()),
    )


def _delete_quality(connection, scope, entity_key, code):
    connection.execute(
        "DELETE FROM quality_flags WHERE scope = ? AND entity_key = ? AND code = ?",
        (scope, entity_key, code),
    )


def _scoring_format(scoring):
    if "rec" not in scoring:
        return "UNKNOWN"
    reception = _float(scoring["rec"])
    if reception == 0:
        return "STD"
    if reception == 0.5:
        return "HALF_PPR"
    if reception == 1:
        return "PPR"
    return "CUSTOM"


def _required_text(value, key):
    result = _text(value.get(key))
    if result is None:
        raise ValueError(f"missing {key}")
    return result


def _required_int(value, key):
    result = _int(value.get(key))
    if result is None:
        raise ValueError(f"missing integer {key}")
    return result


def _text(value):
    return None if value is None or str(value) == "" else str(value)


def _source_id(value):
    text = _text(value)
    return None if text == "0" else text


def _int(value):
    try:
        return None if value is None or value == "" else int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _bool_int(value):
    parsed = _int(value)
    return parsed if parsed in {0, 1} else None
