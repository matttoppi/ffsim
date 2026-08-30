import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .hdvn_contract import FEATURE_VERSION, LABEL_VERSION, feature_manifest, validate_feature_observations
from .hdvn_evaluation import (
    ARTIFACT_SCHEMA_VERSION,
    ModelFamily,
    evaluate_predictions,
    load_artifact_manifest,
    uniform_championship_predictions,
    write_artifact_manifest,
)
from .hdvn_labels import build_split_manifest, write_split_manifest
from .hdvn_market import build_market_board, materialize_rolling_markets
from .hdvn_snapshot import canonical_json, create_snapshot
from .hdvn_tables import iter_prefix_rows, iter_sampled_prefixes, iter_team_rows
from .store import Store


FIXED_TIME = "2026-08-27T00:00:00+00:00"
POSITIONS = ("QB", "RB", "WR", "QB", "RB", "WR")
PLAYERS = ("p1", "p2", "p3", "p4", "p5", "p6")


def build_synthetic_source(data_dir):
    """Build a deterministic, network-free HDVN contract fixture."""
    store = Store(data_dir)
    raw_hash = "0" * 64
    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO raw_objects(content_hash, endpoint, relative_path, fetched_at, byte_count)
            VALUES (?, 'synthetic', 'raw/synthetic.json.gz', ?, 1)
            """,
            (raw_hash, FIXED_TIME),
        )
        connection.execute(
            """
            INSERT INTO users(user_id, username, display_name, is_bot, raw_hash, first_seen_at, updated_at)
            VALUES ('seed', 'seed', 'Seed', 0, ?, ?, ?)
            """,
            (raw_hash, FIXED_TIME, FIXED_TIME),
        )
        connection.execute(
            "INSERT INTO seeds(user_id, username, source, added_at) VALUES ('seed', 'seed', 'synthetic', ?)",
            (FIXED_TIME,),
        )
        for player_id, position in zip(PLAYERS, POSITIONS):
            connection.execute(
                """
                INSERT INTO players(
                    player_id, full_name, position, active, raw_json, raw_hash, updated_at
                ) VALUES (?, ?, ?, 1, '{}', ?, ?)
                """,
                (player_id, player_id.upper(), position, raw_hash, FIXED_TIME),
            )
        for season in range(2021, 2026):
            for sequence in range(3):
                _insert_league(connection, season, sequence, raw_hash)
    return store


def _insert_league(connection, season, sequence, raw_hash):
    league_id = f"synthetic-{season}-{sequence}"
    draft_id = f"draft-{season}-{sequence}"
    start_ms = int(datetime(season, 8, 10 + sequence * 5, tzinfo=timezone.utc).timestamp() * 1000)
    finish_ms = start_ms + 60 * 60 * 1000
    connection.execute(
        """
        INSERT INTO league_seasons(
            league_id, season, name, status, season_type, total_rosters,
            draft_id, league_type, best_ball, max_keepers, playoff_teams,
            playoff_week_start, last_scored_leg, settings_json,
            scoring_settings_json, roster_positions_json, scoring_format,
            is_candidate, candidate_reasons_json, raw_hash, first_seen_at, updated_at
        ) VALUES (?, ?, ?, 'complete', 'regular', 2, ?, 0, 0, 0, 2, 2, 1,
                  '{}', '{"rec":1}', '["QB","RB","WR","BN","BN","BN"]',
                  'ppr', 1, '[]', ?, ?, ?)
        """,
        (league_id, season, league_id, draft_id, raw_hash, FIXED_TIME, FIXED_TIME),
    )
    connection.execute(
        """
        INSERT INTO league_provenance(
            league_id, season, seed_user_id, discovery_depth, discovering_user_id,
            source_league_id, mechanism, discovered_at
        ) VALUES (?, ?, 'seed', ?, 'seed', NULL, 'synthetic', ?)
        """,
        (league_id, season, sequence, FIXED_TIME),
    )
    connection.execute(
        """
        INSERT INTO drafts(
            draft_id, league_id, season, status, draft_type, season_type,
            team_count, rounds, start_time, created_at_ms, last_picked_ms,
            scoring_type, draft_order_json, slot_to_roster_id_json,
            settings_json, metadata_json, raw_hash, updated_at
        ) VALUES (?, ?, ?, 'complete', 'snake', 'regular', 2, 3, ?, ?, ?, 'ppr',
                  '{"owner-1":1,"owner-2":2}', '{"1":1,"2":2}', '{}', '{}', ?, ?)
        """,
        (draft_id, league_id, season, start_ms, start_ms - 1000, finish_ms, raw_hash, FIXED_TIME),
    )
    for roster_id in (1, 2):
        points = 100.0 + sequence if roster_id == 1 else 90.0 - sequence
        settings = canonical_json({
            "wins": 1 if roster_id == 1 else 0,
            "losses": 0 if roster_id == 1 else 1,
            "ties": 0,
            "fpts": int(points),
            "fpts_decimal": 0,
        })
        connection.execute(
            """
            INSERT INTO rosters(
                league_id, season, roster_id, owner_id, co_owners_json, players_json,
                starters_json, reserve_json, settings_json, raw_hash, updated_at
            ) VALUES (?, ?, ?, ?, '[]', '[]', '[]', '[]', ?, ?, ?)
            """,
            (league_id, season, roster_id, f"owner-{roster_id}", settings, raw_hash, FIXED_TIME),
        )
        connection.execute(
            """
            INSERT INTO weekly_matchups(
                league_id, season, week, roster_id, matchup_id, points, custom_points,
                starters_json, players_json, raw_hash
            ) VALUES (?, ?, 1, ?, 1, ?, ?, '[]', '[]', ?)
            """,
            (league_id, season, roster_id, points - 1, points, raw_hash),
        )
        connection.execute(
            """
            INSERT INTO team_seasons(
                league_id, season, roster_id, owner_id, reported_wins, reported_losses,
                reported_ties, reported_points_for, h2h_wins, h2h_losses, h2h_ties,
                matchup_points_for, regular_season_games, made_playoffs, champion,
                runner_up, final_finish, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 0, ?, 1, 1, ?, ?, ?, ?)
            """,
            (
                league_id, season, roster_id, f"owner-{roster_id}",
                1 if roster_id == 1 else 0, 0 if roster_id == 1 else 1,
                points, 1 if roster_id == 1 else 0, 0 if roster_id == 1 else 1,
                points, 1 if roster_id == 1 else 0, 0 if roster_id == 1 else 1,
                roster_id, FIXED_TIME,
            ),
        )
    connection.execute(
        """
        INSERT INTO playoff_matches(
            league_id, season, bracket_type, match_id, round, team_1, team_2,
            winner, loser, placement, raw_json, raw_hash
        ) VALUES (?, ?, 'winners', 1, 1, 1, 2, 1, 2, 1, '{}', ?)
        """,
        (league_id, season, raw_hash),
    )
    connection.execute(
        """
        INSERT INTO hydration_queue(
            league_id, season, status, attempts, available_at, completed_at
        ) VALUES (?, ?, 'done', 1, ?, ?)
        """,
        (league_id, season, FIXED_TIME, FIXED_TIME),
    )
    if sequence == 0:
        order = PLAYERS
    elif sequence == 1:
        order = ("p2", "p1", "p3", "p4", "p5", "p6")
    else:
        order = ("p2", "p6", "p5", "p4", "p3", "p1")
    position_by_player = dict(zip(PLAYERS, POSITIONS))
    for pick_no, player_id in enumerate(order, 1):
        round_number = (pick_no - 1) // 2 + 1
        draft_slot = pick_no if round_number % 2 else 3 - ((pick_no - 1) % 2 + 1)
        draft_slot = ((pick_no - 1) % 2 + 1) if round_number % 2 else (2 - ((pick_no - 1) % 2))
        connection.execute(
            """
            INSERT INTO draft_picks(
                draft_id, pick_no, league_id, season, round, draft_slot, roster_id,
                effective_roster_id, ownership_source, picked_by, player_id,
                is_keeper, picked_at_ms, position, metadata_json, raw_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'fixed', ?, ?, 0, ?, ?, '{}', ?)
            """,
            (
                draft_id, pick_no, league_id, season, round_number, draft_slot,
                draft_slot, draft_slot, f"owner-{draft_slot}", player_id,
                start_ms + pick_no * 1000, position_by_player[player_id], raw_hash,
            ),
        )


def run_synthetic_dry_run(work_dir):
    work_dir = Path(work_dir)
    if work_dir.exists() and any(work_dir.iterdir()):
        raise FileExistsError(f"dry-run directory must be empty: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)
    source = build_synthetic_source(work_dir / "source")
    snapshot_path = work_dir / "interim.sqlite3"
    snapshot = create_snapshot(
        source.database_path,
        snapshot_path,
        captured_at=FIXED_TIME,
    )
    feature = feature_manifest()
    market_directory = work_dir / "market"
    materialize_rolling_markets(
        snapshot_path,
        market_directory,
        source_snapshot_hash=snapshot["sha256"],
        feature_manifest_hash=feature["sha256"],
        command="synthetic-fixed",
        min_support_drafts=1,
    )
    connection = sqlite3.connect(
        f"file:{snapshot_path.resolve().as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    market = sqlite3.connect(
        f"file:{(market_directory / 'market-v1.sqlite3').resolve().as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    market.row_factory = sqlite3.Row
    try:
        teams = list(
            iter_team_rows(
                connection,
                market,
                snapshot["sha256"],
                feature["sha256"],
                batch_size=2,
            )
        )
        prefixes = list(iter_prefix_rows(connection, market, teams))
        leakage_board = build_market_board(connection, "draft-2021-1")
        leakage_ranks = {
            player["player_id"]: player["rank"] for player in leakage_board["players"]
        }
        future_inclusive = connection.execute(
            """
            SELECT player_id, AVG(pick_no) AS adp
            FROM draft_picks
            WHERE draft_id IN ('draft-2021-0', 'draft-2021-2')
            GROUP BY player_id ORDER BY adp, player_id
            """
        ).fetchall()
        future_ranks = {
            row["player_id"]: rank for rank, row in enumerate(future_inclusive, 1)
        }
        future_rank_change_rejected = (
            leakage_ranks["p1"] == 1 and future_ranks["p1"] != leakage_ranks["p1"]
        )
        if not future_rank_change_rejected:
            raise AssertionError("future-draft market rank leakage was not detected")
    finally:
        market.close()
        connection.close()
    sampled = list(iter_sampled_prefixes(prefixes, seed=20260827, epoch=0))
    team_keys = {(row["league_season_id"], row["roster_id"]) for row in sampled}
    if len(sampled) != len(team_keys) or any(row["prefix_weight"] != 1.0 for row in sampled):
        raise AssertionError("prefix team-weight invariant failed")
    split = build_split_manifest(teams)
    write_split_manifest(split, work_dir / "split.json")

    predictions = uniform_championship_predictions([
        {
            **team,
            "league_season_id": f"{team['season']}:{team['league_id']}",
            "predicted_points_for_percentile": 75.0 if team["roster_id"] == 1 else 25.0,
            "predicted_playoff": 0.75 if team["roster_id"] == 1 else 0.25,
        }
        for team in teams if team["training_eligible"]
    ])
    probability_sums = {}
    for row in predictions:
        key = row["league_season_id"]
        probability_sums[key] = probability_sums.get(key, 0.0) + row["predicted_champion"]
    championship_sums_valid = all(
        abs(total - 1.0) <= 1e-9 for total in probability_sums.values()
    )
    if not championship_sums_valid:
        raise AssertionError("championship probabilities do not sum to one")
    metrics = evaluate_predictions(predictions)

    leakage_rejected = False
    try:
        validate_feature_observations(
            [{"name": "season", "observed_at_ms": 200}], target_draft_ms=100
        )
    except ValueError:
        leakage_rejected = True
    if not leakage_rejected:
        raise AssertionError("deliberate leakage was accepted")

    metadata = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "model_family": ModelFamily.CONTEXT_BASELINE.value,
        "model_version": "synthetic-contract-fixture-v1",
        "code_revision": "synthetic-fixture",
        "source_snapshot_hash": snapshot["sha256"],
        "feature_version": FEATURE_VERSION,
        "label_version": LABEL_VERSION,
        "split_manifest_hash": split["sha256"],
        "market_projection_provenance": {
            "mode": "market_and_construction_only",
            "market": "rolling_prior_sleeper_drafts",
            "projection": None,
        },
        "counts_by_year_context": split["counts"]["by_context"],
        "prefix_sampling_method": "one_per_team_per_epoch_balanced_thirds",
        "total_team_weight": float(len(sampled)),
        "architecture": "contract_fixture_no_fitted_model",
        "parameter_count": 0,
        "seed": 20260827,
        "optimizer": None,
        "loss_weights": None,
        "stopping_rule": None,
        "baseline_metrics": metrics,
        "holdout_metrics": None,
        "calibration": metrics["calibration"],
        "limitations": ["synthetic contract fixture", "no model trained"],
        "status": "research",
    }
    artifact = write_artifact_manifest(metadata, work_dir / "artifact.json")
    load_artifact_manifest(
        work_dir / "artifact.json",
        expected={
            "source_snapshot_hash": snapshot["sha256"],
            "feature_version": FEATURE_VERSION,
            "split_manifest_hash": split["sha256"],
        },
    )
    report = {
        "dry_run_version": 1,
        "source_snapshot_hash": snapshot["sha256"],
        "feature_manifest_hash": feature["sha256"],
        "split_manifest_hash": split["sha256"],
        "artifact_manifest_hash": artifact["manifest_sha256"],
        "team_rows": len(teams),
        "prefix_rows": len(prefixes),
        "sampled_prefix_rows": len(sampled),
        "total_team_weight": sum(row["prefix_weight"] for row in sampled),
        "deliberate_leakage_rejected": leakage_rejected,
        "championship_probability_sums_valid": championship_sums_valid,
        "future_draft_rank_change_rejected": future_rank_change_rejected,
        "sleeper_calls": 0,
        "active_crawler_database_used": False,
    }
    (work_dir / "report.json").write_text(canonical_json(report) + "\n")
    return report
