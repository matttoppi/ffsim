import json

from .outcomes import compute_team_seasons
from .store import json_text, utc_now


DEFAULT_TRAINING_READY_TARGET = 10_000
DEFAULT_CANDIDATE_BUFFER = 500
DEFAULT_MIN_TRAINING_READY_PER_YEAR = 500


def validate_dataset(store):
    with store.connect() as connection:
        hydrated = connection.execute(
            "SELECT league_id, season FROM hydration_queue WHERE status = 'done'"
        ).fetchall()
    for row in hydrated:
        compute_team_seasons(store, row["league_id"], row["season"])

    with store.connect() as connection:
        for league in connection.execute(
            "SELECT league_id, season, scoring_settings_json FROM league_seasons"
        ):
            scoring = json.loads(league["scoring_settings_json"])
            invalid = sorted(
                key for key, value in scoring.items()
                if isinstance(value, bool) or not isinstance(value, (int, float))
            )
            _set_quality(
                connection,
                "league_season",
                f"{league['league_id']}:{league['season']}",
                "non_numeric_scoring_setting",
                "error",
                {"keys": invalid},
                present=bool(invalid),
            )
        for league in connection.execute(
            """
            SELECT league_seasons.league_id, league_seasons.season,
                   league_seasons.total_rosters, COUNT(rosters.roster_id) AS actual
            FROM league_seasons
            LEFT JOIN rosters USING (league_id, season)
            GROUP BY league_seasons.league_id, league_seasons.season
            """
        ):
            mismatch = league["total_rosters"] is not None and league["actual"] not in {0, league["total_rosters"]}
            _set_quality(
                connection,
                "league_season",
                f"{league['league_id']}:{league['season']}",
                "roster_count_mismatch",
                "error",
                {"expected": league["total_rosters"], "actual": league["actual"]},
                present=mismatch,
            )
        for draft in connection.execute(
            """
            SELECT drafts.draft_id, drafts.status, drafts.team_count, drafts.rounds,
                   COUNT(draft_picks.pick_no) AS actual,
                   EXISTS(
                       SELECT 1 FROM endpoint_cache
                       WHERE endpoint = 'draft/' || drafts.draft_id || '/picks'
                   ) AS picks_hydrated
            FROM drafts
            LEFT JOIN draft_picks USING (draft_id)
            GROUP BY drafts.draft_id
            """
        ):
            expected = (
                draft["team_count"] * draft["rounds"]
                if draft["team_count"] and draft["rounds"] else None
            )
            mismatch = draft["status"] == "complete" and draft["picks_hydrated"] and draft["actual"] != expected
            _set_quality(
                connection,
                "draft",
                draft["draft_id"],
                "draft_pick_count_mismatch",
                "error",
                {"expected": expected, "actual": draft["actual"]},
                present=mismatch,
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [dict(row) for row in connection.execute("PRAGMA foreign_key_check")]
        error_flags = connection.execute(
            "SELECT COUNT(*) FROM quality_flags WHERE severity = 'error'"
        ).fetchone()[0]

    report = quality_report(store)
    report["integrity_check"] = integrity
    report["foreign_key_errors"] = foreign_keys
    report["error_quality_flags"] = error_flags
    report["structurally_valid"] = integrity == "ok" and not foreign_keys
    return report


def quality_report(store):
    with store.connect() as connection:
        training_ready_by_year = _training_ready_by_year(connection)
        report = {
            "users_discovered": _count(connection, "users"),
            "league_seasons_discovered": _count(connection, "league_seasons"),
            "league_seasons_by_year": _group(connection, "SELECT season AS key, COUNT(*) AS count FROM league_seasons GROUP BY season ORDER BY season"),
            "league_types": _group(connection, "SELECT COALESCE(CAST(league_type AS TEXT), 'unknown') AS key, COUNT(*) AS count FROM league_seasons GROUP BY league_type ORDER BY league_type"),
            "league_sizes": _group(connection, "SELECT COALESCE(CAST(total_rosters AS TEXT), 'unknown') AS key, COUNT(*) AS count FROM league_seasons GROUP BY total_rosters ORDER BY total_rosters"),
            "scoring_formats": _group(connection, "SELECT scoring_format AS key, COUNT(*) AS count FROM league_seasons GROUP BY scoring_format ORDER BY scoring_format"),
            "candidate_league_seasons": connection.execute("SELECT COUNT(*) FROM league_seasons WHERE is_candidate = 1").fetchone()[0],
            "fully_hydrated_leagues": connection.execute("SELECT COUNT(*) FROM hydration_queue WHERE status = 'done'").fetchone()[0],
            "training_ready_leagues": sum(training_ready_by_year.values()),
            "training_ready_by_year": training_ready_by_year,
            "training_ready_target": _metadata_int(
                connection,
                "collection_training_ready_target",
                DEFAULT_TRAINING_READY_TARGET,
            ),
            "candidate_buffer_target": _metadata_int(
                connection,
                "collection_candidate_buffer",
                DEFAULT_CANDIDATE_BUFFER,
            ),
            "min_training_ready_per_year": _metadata_int(
                connection,
                "collection_min_training_ready_per_year",
                DEFAULT_MIN_TRAINING_READY_PER_YEAR,
            ),
            "failed_hydration": connection.execute("SELECT COUNT(*) FROM hydration_queue WHERE status = 'failed'").fetchone()[0],
            "drafts_collected": _count(connection, "drafts"),
            "draft_picks_collected": _count(connection, "draft_picks"),
            "team_seasons_collected": _count(connection, "team_seasons"),
            "weekly_matchup_rows": _count(connection, "weekly_matchups"),
            "raw_objects": _count(connection, "raw_objects"),
            "quality_flags": {
                row["code"]: {"count": row["count"], "severity": row["severity"]}
                for row in connection.execute(
                    """
                    SELECT code, severity, COUNT(*) AS count
                    FROM quality_flags
                    GROUP BY code, severity
                    ORDER BY severity, code
                    """
                )
            },
        }
    return report


def _metadata_int(connection, key, default):
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = ?",
        (key,),
    ).fetchone()
    try:
        return int(row[0]) if row is not None else int(default)
    except (TypeError, ValueError):
        return int(default)


def _training_ready_by_year(connection):
    return {
        str(row["season"]): row["count"]
        for row in connection.execute(
            """
            SELECT l.season, COUNT(*) AS count
            FROM hydration_queue AS h
            JOIN league_seasons AS l USING (league_id, season)
            WHERE h.status = 'done'
              AND l.is_candidate = 1
              AND (
                  SELECT COUNT(*) FROM rosters AS r
                  WHERE r.league_id = h.league_id AND r.season = h.season
              ) = l.total_rosters
              AND EXISTS (
                  SELECT 1
                  FROM drafts AS d
                  WHERE d.league_id = h.league_id
                    AND d.season = h.season
                    AND d.status = 'complete'
                    AND d.draft_type = 'snake'
                    AND d.team_count = l.total_rosters
                    AND d.rounds > 0
                    AND (
                        SELECT COUNT(*) FROM draft_picks AS p
                        WHERE p.draft_id = d.draft_id
                    ) = d.team_count * d.rounds
                    AND NOT EXISTS (
                        SELECT 1 FROM draft_picks AS p
                        WHERE p.draft_id = d.draft_id AND p.is_keeper = 1
                    )
              )
              AND l.playoff_week_start > 1
              AND (
                  SELECT COUNT(*) FROM weekly_matchups AS w
                  WHERE w.league_id = h.league_id
                    AND w.season = h.season
                    AND w.week < l.playoff_week_start
              ) = l.total_rosters * (l.playoff_week_start - 1)
              AND (
                  SELECT COUNT(*) FROM team_seasons AS t
                  WHERE t.league_id = h.league_id AND t.season = h.season
              ) = l.total_rosters
              AND (
                  SELECT COUNT(*) FROM team_seasons AS t
                  WHERE t.league_id = h.league_id
                    AND t.season = h.season
                    AND t.champion = 1
              ) = 1
              AND NOT EXISTS (
                  SELECT 1
                  FROM quality_flags AS q
                  WHERE q.severity = 'error'
                    AND (
                        (
                            q.scope = 'league_season'
                            AND q.entity_key = h.league_id || ':' || h.season
                        )
                        OR (
                            q.scope = 'draft'
                            AND q.entity_key IN (
                                SELECT draft_id FROM drafts
                                WHERE league_id = h.league_id AND season = h.season
                            )
                        )
                    )
              )
            GROUP BY l.season
            """
        )
    }


def _set_quality(connection, scope, entity_key, code, severity, details, *, present):
    if not present:
        connection.execute(
            "DELETE FROM quality_flags WHERE scope = ? AND entity_key = ? AND code = ?",
            (scope, entity_key, code),
        )
        return
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


def _count(connection, table):
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _group(connection, sql):
    return {str(row["key"]): row["count"] for row in connection.execute(sql)}
