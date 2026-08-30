import json
import os
from pathlib import Path

from .schema import SCHEMA_VERSION
from .store import utc_now


LEAGUES_SQL = """
SELECT
    league_id, season, name, status, season_type, total_rosters,
    previous_league_id, draft_id, league_type, best_ball, max_keepers,
    playoff_teams, playoff_week_start, last_scored_leg, scoring_format,
    is_candidate, candidate_reasons_json, settings_json,
    scoring_settings_json, roster_positions_json, first_seen_at, updated_at
FROM league_seasons
ORDER BY season, league_id
"""

TEAM_SEASONS_SQL = """
SELECT
    team_seasons.league_id,
    team_seasons.season,
    team_seasons.roster_id,
    team_seasons.owner_id,
    team_seasons.reported_wins,
    team_seasons.reported_losses,
    team_seasons.reported_ties,
    team_seasons.reported_points_for,
    team_seasons.reported_points_against,
    team_seasons.h2h_wins,
    team_seasons.h2h_losses,
    team_seasons.h2h_ties,
    team_seasons.matchup_points_for,
    team_seasons.regular_season_games,
    team_seasons.made_playoffs,
    team_seasons.champion,
    team_seasons.runner_up,
    team_seasons.final_finish,
    CASE
        WHEN COALESCE(team_seasons.reported_wins, 0)
           + COALESCE(team_seasons.reported_losses, 0)
           + COALESCE(team_seasons.reported_ties, 0) = 0 THEN NULL
        ELSE (
            COALESCE(team_seasons.reported_wins, 0)
            + 0.5 * COALESCE(team_seasons.reported_ties, 0)
        ) / (
            COALESCE(team_seasons.reported_wins, 0)
            + COALESCE(team_seasons.reported_losses, 0)
            + COALESCE(team_seasons.reported_ties, 0)
        )
    END AS regular_season_win_percentage,
    PERCENT_RANK() OVER (
        PARTITION BY team_seasons.league_id, team_seasons.season
        ORDER BY team_seasons.reported_points_for
    ) AS points_for_percentile,
    league_seasons.name AS league_name,
    league_seasons.total_rosters,
    league_seasons.scoring_format,
    league_seasons.league_type,
    league_seasons.best_ball,
    league_seasons.roster_positions_json,
    league_seasons.scoring_settings_json,
    league_seasons.is_candidate
FROM team_seasons
JOIN league_seasons USING (league_id, season)
ORDER BY team_seasons.season, team_seasons.league_id, team_seasons.roster_id
"""

DRAFT_PICKS_SQL = """
SELECT
    draft_picks.league_id,
    draft_picks.season,
    draft_picks.draft_id,
    draft_picks.pick_no,
    draft_picks.round,
    draft_picks.draft_slot,
    draft_picks.roster_id,
    draft_picks.effective_roster_id,
    draft_picks.ownership_source,
    draft_picks.picked_by,
    draft_picks.player_id,
    draft_picks.is_keeper,
    draft_picks.picked_at_ms,
    draft_picks.position,
    draft_picks.nfl_team,
    draft_picks.metadata_json,
    drafts.status AS draft_status,
    drafts.draft_type,
    drafts.team_count,
    drafts.rounds,
    drafts.scoring_type,
    players.full_name,
    players.position AS player_position,
    players.nfl_team AS player_nfl_team,
    league_seasons.scoring_format,
    league_seasons.roster_positions_json,
    league_seasons.scoring_settings_json,
    league_seasons.is_candidate AS league_is_candidate
FROM draft_picks
JOIN drafts USING (draft_id)
LEFT JOIN players USING (player_id)
LEFT JOIN league_seasons
    ON league_seasons.league_id = draft_picks.league_id
   AND league_seasons.season = draft_picks.season
ORDER BY draft_picks.season, draft_picks.draft_id, draft_picks.pick_no
"""


TYPE_CODES = {
    "string": "string",
    "int": "int64",
    "float": "float64",
}

EXPORT_COLUMNS = {
    "leagues": [
        ("league_id", "string"), ("season", "int"), ("name", "string"),
        ("status", "string"), ("season_type", "string"), ("total_rosters", "int"),
        ("previous_league_id", "string"), ("draft_id", "string"), ("league_type", "int"),
        ("best_ball", "int"), ("max_keepers", "int"), ("playoff_teams", "int"),
        ("playoff_week_start", "int"), ("last_scored_leg", "int"),
        ("scoring_format", "string"), ("is_candidate", "int"),
        ("candidate_reasons_json", "string"), ("settings_json", "string"),
        ("scoring_settings_json", "string"), ("roster_positions_json", "string"),
        ("first_seen_at", "string"), ("updated_at", "string"),
    ],
    "team_seasons": [
        ("league_id", "string"), ("season", "int"), ("roster_id", "int"),
        ("owner_id", "string"), ("reported_wins", "int"), ("reported_losses", "int"),
        ("reported_ties", "int"), ("reported_points_for", "float"),
        ("reported_points_against", "float"), ("h2h_wins", "int"),
        ("h2h_losses", "int"), ("h2h_ties", "int"),
        ("matchup_points_for", "float"), ("regular_season_games", "int"),
        ("made_playoffs", "int"), ("champion", "int"), ("runner_up", "int"),
        ("final_finish", "int"), ("regular_season_win_percentage", "float"),
        ("points_for_percentile", "float"), ("league_name", "string"),
        ("total_rosters", "int"), ("scoring_format", "string"),
        ("league_type", "int"), ("best_ball", "int"),
        ("roster_positions_json", "string"), ("scoring_settings_json", "string"),
        ("is_candidate", "int"),
    ],
    "draft_picks": [
        ("league_id", "string"), ("season", "int"), ("draft_id", "string"),
        ("pick_no", "int"), ("round", "int"), ("draft_slot", "int"),
        ("roster_id", "int"), ("effective_roster_id", "int"),
        ("ownership_source", "string"), ("picked_by", "string"),
        ("player_id", "string"), ("is_keeper", "int"), ("picked_at_ms", "int"),
        ("position", "string"), ("nfl_team", "string"), ("metadata_json", "string"),
        ("draft_status", "string"), ("draft_type", "string"), ("team_count", "int"),
        ("rounds", "int"), ("scoring_type", "string"), ("full_name", "string"),
        ("player_position", "string"), ("player_nfl_team", "string"),
        ("scoring_format", "string"), ("roster_positions_json", "string"),
        ("scoring_settings_json", "string"), ("league_is_candidate", "int"),
    ],
}

SQL_BY_EXPORT = {
    "leagues": LEAGUES_SQL,
    "team_seasons": TEAM_SEASONS_SQL,
    "draft_picks": DRAFT_PICKS_SQL,
}


def export_parquet(store, output_dir, *, batch_size=50_000):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError(
            "Parquet export requires pyarrow; install "
            "ffsim/historical_sleeper/requirements.txt"
        ) from error

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": utc_now(),
        "source_database": str(store.database_path.resolve()),
        "tables": {},
    }
    with store.connect() as connection:
        for name, sql in SQL_BY_EXPORT.items():
            columns = EXPORT_COLUMNS[name]
            schema = pa.schema([(column, getattr(pa, TYPE_CODES[type_code])()) for column, type_code in columns])
            destination = output_dir / f"{name}.parquet"
            temporary = destination.with_suffix(".parquet.tmp")
            cursor = connection.execute(sql)
            writer = pq.ParquetWriter(temporary, schema, compression="zstd")
            row_count = 0
            try:
                while rows := cursor.fetchmany(batch_size):
                    records = [dict(row) for row in rows]
                    writer.write_table(pa.Table.from_pylist(records, schema=schema))
                    row_count += len(records)
            finally:
                writer.close()
            os.replace(temporary, destination)
            manifest["tables"][name] = {
                "path": destination.name,
                "rows": row_count,
                "columns": [column for column, _ in columns],
            }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
