import json
from collections import defaultdict

from .store import json_text, utc_now


def compute_team_seasons(store, league_id, season):
    entity_key = f"{league_id}:{season}"
    now = utc_now()
    with store.connect() as connection:
        league = connection.execute(
            "SELECT * FROM league_seasons WHERE league_id = ? AND season = ?",
            (league_id, season),
        ).fetchone()
        if league is None:
            raise ValueError(f"unknown league-season {entity_key}")
        rosters = connection.execute(
            "SELECT * FROM rosters WHERE league_id = ? AND season = ? ORDER BY roster_id",
            (league_id, season),
        ).fetchall()
        regular_end = league["playoff_week_start"]
        regular_end = (
            regular_end - 1
            if regular_end and regular_end > 1
            else league["last_scored_leg"]
        )
        matchups = connection.execute(
            """
            SELECT * FROM weekly_matchups
            WHERE league_id = ? AND season = ? AND week <= ?
            ORDER BY week, matchup_id, roster_id
            """,
            (league_id, season, regular_end or 99),
        ).fetchall()
        results = {
            row["roster_id"]: {
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points": 0.0,
                "games": 0,
            }
            for row in rosters
        }
        groups = defaultdict(list)
        for row in matchups:
            score = (
                row["custom_points"]
                if row["custom_points"] is not None
                else row["points"]
            )
            if score is not None and row["roster_id"] in results:
                results[row["roster_id"]]["points"] += score
            if row["matchup_id"] is not None:
                groups[(row["week"], row["matchup_id"])].append(
                    (row["roster_id"], score)
                )
        invalid_groups = []
        for key, teams in groups.items():
            if len(teams) != 2 or any(score is None for _, score in teams):
                invalid_groups.append(key)
                continue
            (left_id, left), (right_id, right) = teams
            if left_id not in results or right_id not in results:
                continue
            results[left_id]["games"] += 1
            results[right_id]["games"] += 1
            if left == right:
                results[left_id]["ties"] += 1
                results[right_id]["ties"] += 1
            elif left > right:
                results[left_id]["wins"] += 1
                results[right_id]["losses"] += 1
            else:
                results[right_id]["wins"] += 1
                results[left_id]["losses"] += 1
        if invalid_groups:
            _quality(
                connection,
                "league_season",
                entity_key,
                "invalid_matchup_group",
                "error",
                {"week_matchup_ids": invalid_groups},
            )
        if not matchups:
            _quality(
                connection,
                "league_season",
                entity_key,
                "no_regular_season_games",
                "error",
                {},
            )
        else:
            _delete_quality(
                connection,
                "league_season",
                entity_key,
                "no_regular_season_games",
            )

        winner_rows = connection.execute(
            """
            SELECT * FROM playoff_matches
            WHERE league_id = ? AND season = ? AND bracket_type = 'winners'
            """,
            (league_id, season),
        ).fetchall()
        playoff_rosters = set()
        finish = {}
        champion = runner_up = None
        for match in winner_rows:
            for column in ("team_1", "team_2", "winner", "loser"):
                if match[column] is not None:
                    playoff_rosters.add(match[column])
            if match["placement"] is not None:
                if match["winner"] is not None:
                    finish[match["winner"]] = match["placement"]
                if match["loser"] is not None:
                    finish[match["loser"]] = match["placement"] + 1
                if match["placement"] == 1:
                    champion, runner_up = match["winner"], match["loser"]
        roster_ids = {row["roster_id"] for row in rosters}
        unknown = sorted(playoff_rosters - roster_ids)
        if unknown:
            _quality(
                connection,
                "league_season",
                entity_key,
                "playoff_unknown_roster",
                "error",
                {"roster_ids": unknown},
            )
        connection.execute(
            "DELETE FROM team_seasons WHERE league_id = ? AND season = ?",
            (league_id, season),
        )
        for roster in rosters:
            roster_id = roster["roster_id"]
            settings = json.loads(roster["settings_json"])
            reported_points = _points_setting(settings, "fpts")
            reported_against = _points_setting(settings, "fpts_against")
            result = results[roster_id]
            connection.execute(
                """
                INSERT INTO team_seasons (
                    league_id, season, roster_id, owner_id, reported_wins,
                    reported_losses, reported_ties, reported_points_for,
                    reported_points_against, h2h_wins, h2h_losses, h2h_ties,
                    matchup_points_for, regular_season_games, made_playoffs,
                    champion, runner_up, final_finish, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    league_id,
                    season,
                    roster_id,
                    roster["owner_id"],
                    _int(settings.get("wins")),
                    _int(settings.get("losses")),
                    _int(settings.get("ties")),
                    reported_points,
                    reported_against,
                    result["wins"],
                    result["losses"],
                    result["ties"],
                    result["points"],
                    result["games"],
                    int(roster_id in playoff_rosters) if winner_rows else None,
                    int(roster_id == champion) if champion is not None else None,
                    int(roster_id == runner_up) if runner_up is not None else None,
                    finish.get(roster_id),
                    now,
                ),
            )


def _points_setting(settings, key):
    whole = _float(settings.get(key))
    decimal = _float(settings.get(f"{key}_decimal"))
    if whole is None:
        return None
    return whole + (decimal or 0.0) / 100.0


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
