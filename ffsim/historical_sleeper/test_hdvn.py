import json
import gzip
import sqlite3
import tempfile
import tracemalloc
import unittest
from contextlib import closing
from pathlib import Path

from .__main__ import main
from .hdvn_baselines import fit_baselines, load_baseline_bundle
from .hdvn_contract import (
    FEATURE_BY_NAME,
    MATERIALIZED_COLUMN_FEATURES,
    feature_manifest,
    validate_feature_observations,
    validate_materialized_columns,
    write_final_feature_manifest,
)
from .hdvn_evaluation import (
    ARTIFACT_SCHEMA_VERSION,
    BASELINE_INTERFACES,
    ModelFamily,
    clustered_bootstrap,
    evaluate_predictions,
    load_artifact_manifest,
    uniform_championship_predictions,
    write_artifact_manifest,
)
from .hdvn_labels import (
    assert_split_isolation,
    build_split_manifest,
    label_manifest,
    labels_for_league,
    load_team_partition,
    materialize_labels_and_split,
    training_exclusion_reasons,
    write_split_manifest,
)
from .hdvn_market import build_market_board, market_only_pick, materialize_rolling_markets
from .hdvn_raw_audit import audit_raw_sources
from .hdvn_snapshot import create_snapshot
from .hdvn_synthetic import build_synthetic_source, run_synthetic_dry_run
from .hdvn_tables import (
    derive_strategy_labels,
    iter_prefix_rows,
    iter_sampled_prefixes,
    iter_sampled_team_prefixes,
    iter_team_rows,
    materialize_training_tables,
    sample_prefix_for_team,
    starter_coverage,
)
from .store import Store


class HDVNFixtureTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = build_synthetic_source(self.root / "source")
        self.market_directory = self.root / "market"
        materialize_rolling_markets(
            self.store.database_path,
            self.market_directory,
            source_snapshot_hash="source-hash",
            feature_manifest_hash="feature-hash",
            command="fixed",
            min_support_drafts=1,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def connection(self):
        connection = sqlite3.connect(self.store.database_path)
        connection.row_factory = sqlite3.Row
        return closing(connection)

    def market_connection(self):
        connection = sqlite3.connect(self.market_directory / "market-v1.sqlite3")
        connection.row_factory = sqlite3.Row
        return closing(connection)

    def team_rows(self):
        with self.connection() as connection, self.market_connection() as market:
            return list(
                iter_team_rows(
                    connection,
                    market,
                    "source-hash",
                    "feature-hash",
                )
            )

    def team_and_prefix_rows(self):
        teams = self.team_rows()
        with self.connection() as connection, self.market_connection() as market:
            prefixes = list(iter_prefix_rows(connection, market, teams))
        return teams, prefixes

    def test_snapshot_manifest_records_provenance_and_is_immutable(self):
        destination = self.root / "snapshot.sqlite3"
        manifest = create_snapshot(
            self.store.database_path,
            destination,
            captured_at="2026-08-27T00:00:00+00:00",
            pages=1,
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["strict_training_ready"]["total"], 15)
        self.assertEqual(manifest["canonical_counts"]["league_seasons"], 15)
        self.assertEqual(manifest["hydration_states"], {"done": 15})
        self.assertEqual(manifest["integrity_check"], "ok")
        self.assertEqual(len(manifest["sha256"]), 64)
        self.assertTrue(manifest["graph_provenance"])
        self.assertTrue(manifest["raw_object_coverage"]["tables"]["draft_picks"]["with_raw_hash"])
        stored = json.loads(Path(str(destination) + ".manifest.json").read_text())
        self.assertEqual(stored, manifest)
        with self.assertRaises(FileExistsError):
            create_snapshot(self.store.database_path, destination)

    def test_feature_registry_is_versioned_and_rejects_leakage(self):
        manifest = feature_manifest()
        self.assertEqual(len(manifest["sha256"]), 64)
        groups = {feature["group"] for feature in manifest["features"]}
        self.assertTrue({
            "league_context", "draft_geometry", "pick_sequence", "roster_construction",
            "starter_flex_coverage", "market_relative_value", "remaining_board_context",
            "prefix_state", "prohibited",
        }.issubset(groups))
        self.assertFalse(FEATURE_BY_NAME["post_season_player_outcomes"]["model_eligible"])
        with self.assertRaisesRegex(ValueError, "post-draft"):
            validate_feature_observations(
                [{"name": "season", "observed_at_ms": 101}], 100
            )
        with self.assertRaisesRegex(ValueError, "not a model input"):
            validate_feature_observations(
                [{"name": "outcome_labels_as_features", "observed_at_ms": 1}], 100
            )

    def test_materialized_columns_are_registered_and_eligible_columns_are_used(self):
        manifest = feature_manifest()
        for table, contract in MATERIALIZED_COLUMN_FEATURES.items():
            self.assertTrue(
                validate_materialized_columns(
                    table,
                    contract,
                    manifest["model_eligible_columns"][table],
                )
            )
        with self.assertRaisesRegex(ValueError, "unregistered materialized"):
            validate_materialized_columns(
                "team",
                [*MATERIALIZED_COLUMN_FEATURES["team"], "unknown"],
            )
        used = manifest["model_eligible_columns"]["team"][1:]
        with self.assertRaisesRegex(ValueError, "unused eligible"):
            validate_materialized_columns(
                "team",
                MATERIALIZED_COLUMN_FEATURES["team"],
                used,
            )
        with self.assertRaisesRegex(ValueError, "not a model input"):
            validate_feature_observations(
                [{"name": "pick_player_ids", "observed_at_ms": 1}],
                100,
            )

    def test_final_feature_manifest_binds_accepted_snapshot_and_is_immutable(self):
        source = self.root / "source.manifest.json"
        acceptance = self.root / "acceptance.json"
        output = self.root / "features.json"
        source.write_text(json.dumps({"sha256": "source-hash"}))
        acceptance.write_text(json.dumps({
            "passed": True,
            "snapshot_sha256": "source-hash",
            "completed_at": "2026-08-28T00:00:00+00:00",
        }))
        manifest = write_final_feature_manifest(source, acceptance, output)
        self.assertEqual(manifest["source_snapshot_sha256"], "source-hash")
        self.assertEqual(output.stat().st_mode & 0o777, 0o444)
        with self.assertRaises(FileExistsError):
            write_final_feature_manifest(source, acceptance, output)

    def test_rolling_board_excludes_target_and_future_drafts(self):
        with self.connection() as connection:
            board = build_market_board(connection, "draft-2021-1")
            self.assertEqual(board["provenance"]["source_draft_count"], 1)
            self.assertLess(
                board["provenance"]["max_source_completed_ms"],
                board["provenance"]["cutoff_ms"],
            )
            ranks = {row["player_id"]: row["rank"] for row in board["players"]}
            self.assertEqual(ranks["p1"], 1)
            self.assertEqual(market_only_pick(board, ["p2", "p3"])["player_id"], "p2")
            future_inclusive = connection.execute(
                """
                SELECT player_id, AVG(pick_no) AS adp
                FROM draft_picks
                WHERE draft_id IN ('draft-2021-0', 'draft-2021-2')
                GROUP BY player_id ORDER BY adp, player_id
                """
            ).fetchall()
            naive_ranks = {row["player_id"]: rank for rank, row in enumerate(future_inclusive, 1)}
            self.assertNotEqual(naive_ranks["p1"], ranks["p1"])

    def test_sparse_market_context_returns_unavailable_without_fallback(self):
        with self.connection() as connection:
            board = build_market_board(connection, "draft-2021-0", min_support_drafts=1)
        self.assertEqual(board["players"], [])
        self.assertTrue(board["provenance"]["sparse_context"])
        self.assertEqual(board["provenance"]["sparse_behavior"], "unavailable_without_fallback")

    def test_bulk_market_is_leakage_safe_deterministic_and_bounded(self):
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE draft_picks SET player_id = 'p1' "
                "WHERE draft_id = 'draft-2021-0' AND pick_no = 2"
            )
            connection.execute(
                "UPDATE drafts SET last_picked_ms = start_time - 1000 "
                "WHERE draft_id = 'draft-2021-1'"
            )
        left = self.root / "market-left"
        right = self.root / "market-right"
        tracemalloc.start()
        first = materialize_rolling_markets(
            self.store.database_path,
            left,
            source_snapshot_hash="source-hash",
            feature_manifest_hash="feature-hash",
            command="fixed",
            min_support_drafts=1,
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        second = materialize_rolling_markets(
            self.store.database_path,
            right,
            source_snapshot_hash="source-hash",
            feature_manifest_hash="feature-hash",
            command="fixed",
            min_support_drafts=1,
        )
        self.assertEqual(first, second)
        self.assertLess(peak, 50 * 1024 * 1024)
        connection = sqlite3.connect(left / "market-v1.sqlite3")
        connection.row_factory = sqlite3.Row
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM boards").fetchone()[0], 15)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM market_picks").fetchone()[0], 90)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM boards "
                    "WHERE max_source_completed_ms >= cutoff_ms"
                ).fetchone()[0],
                0,
            )
            player = connection.execute(
                "SELECT observation_count, support_draft_count, rank FROM players "
                "WHERE target_draft_id = 'draft-2021-1' AND player_id = 'p1'"
            ).fetchone()
            self.assertEqual(dict(player), {
                "observation_count": 2,
                "support_draft_count": 1,
                "rank": 1,
            })
        finally:
            connection.close()
        report = json.loads((left / "market-v1.report.json").read_text())
        self.assertEqual(report["target_future_exclusion"]["violations"], 0)
        self.assertEqual(report["bounded_generation"]["target_history_queries"], 0)
        with self.assertRaises(FileExistsError):
            materialize_rolling_markets(
                self.store.database_path,
                left,
                source_snapshot_hash="source-hash",
                feature_manifest_hash="feature-hash",
                command="fixed",
                min_support_drafts=1,
            )

    def test_team_table_is_one_row_per_team_season_and_strategy_is_derived(self):
        rows = self.team_rows()
        self.assertEqual(len(rows), 30)
        self.assertEqual(len({(row["season"], row["league_id"], row["roster_id"]) for row in rows}), 30)
        row = next(value for value in rows if value["draft_id"] == "draft-2021-1" and value["roster_id"] == 1)
        self.assertIn("market_value_by_pick_json", row)
        self.assertIn("feature_manifest_hash", row)
        self.assertTrue(row["training_eligible"])
        self.assertNotIn("zero_rb_through_round_5", row)
        self.assertIn("zero_rb_through_round_5", derive_strategy_labels(row))

    def test_starter_and_flex_coverage_preserves_bench_structure(self):
        coverage = starter_coverage(
            ["QB", "RB", "WR", "TE", "WR"],
            ["QB", "RB", "WR", "FLEX", "BN"],
        )
        self.assertEqual(coverage["starter_covered"], 4)
        self.assertEqual(coverage["flex_covered"], 1)
        self.assertEqual(sum(coverage["bench_structure"].values()), 1)

    def test_prefixes_observe_only_past_and_sampling_has_constant_team_weight(self):
        teams, prefixes = self.team_and_prefix_rows()
        for row in prefixes:
            observed = json.loads(row["observed_picks_json"])
            self.assertTrue(all(pick["pick_no"] <= row["prefix_pick_no"] for pick in observed))
        first_team = [
            row for row in prefixes
            if row["league_season_id"] == prefixes[0]["league_season_id"]
            and row["roster_id"] == prefixes[0]["roster_id"]
        ]
        self.assertEqual(
            sample_prefix_for_team(first_team, seed=9, epoch=2),
            sample_prefix_for_team(first_team, seed=9, epoch=2),
        )
        sampled = list(iter_sampled_prefixes(prefixes, seed=9, epoch=2))
        weights = {}
        for row in sampled:
            key = (row["league_season_id"], row["roster_id"])
            weights[key] = weights.get(key, 0) + row["prefix_weight"]
        self.assertEqual(set(weights.values()), {1.0})
        with self.connection() as connection, self.market_connection() as market:
            direct = list(
                iter_sampled_team_prefixes(
                    connection,
                    market,
                    teams,
                    seed=9,
                    epoch=2,
                )
            )
        self.assertEqual(direct, sampled)
        self.assertEqual(
            {row["sampled_bucket"] for row in sampled},
            {"early", "middle", "late"},
        )

    def test_parquet_tables_are_bounded_deterministic_and_weighted(self):
        left = self.root / "tables-left"
        right = self.root / "tables-right"
        arguments = {
            "source_snapshot_hash": "snapshot-hash",
            "source_manifest_hash": "source-hash",
            "feature_manifest_hash": "feature-hash",
            "market_manifest_hash": "market-hash",
            "command": "fixed",
            "seed": 9,
            "epoch": 2,
            "batch_size": 3,
        }
        tracemalloc.start()
        first = materialize_training_tables(
            self.store.database_path,
            self.market_directory / "market-v1.sqlite3",
            left,
            **arguments,
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        second = materialize_training_tables(
            self.store.database_path,
            self.market_directory / "market-v1.sqlite3",
            right,
            **arguments,
        )
        self.assertEqual(first, second)
        self.assertLess(peak, 100 * 1024 * 1024)
        self.assertEqual(first["files"]["team-v1.parquet"]["rows"], 30)
        self.assertEqual(first["files"]["prefix-v1.parquet"]["rows"], 30)
        self.assertEqual(first["sampling"]["total_team_weight"], 30.0)
        self.assertEqual(
            set(first["sampling"]["prefix_buckets"]),
            {"early", "middle", "late"},
        )
        self.assertEqual(first["hydration_cohort_exclusions"]["included"], 15)
        self.assertEqual((left / "team-v1.parquet").stat().st_mode & 0o777, 0o444)
        with self.assertRaises(FileExistsError):
            materialize_training_tables(
                self.store.database_path,
                self.market_directory / "market-v1.sqlite3",
                left,
                **arguments,
            )

    def test_label_split_artifacts_are_locked_and_guard_2025(self):
        tables = self.root / "label-tables"
        materialize_training_tables(
            self.store.database_path,
            self.market_directory / "market-v1.sqlite3",
            tables,
            source_snapshot_hash="snapshot-hash",
            source_manifest_hash="source-hash",
            feature_manifest_hash="feature-hash",
            market_manifest_hash="market-hash",
            command="fixed",
            seed=9,
            epoch=2,
            batch_size=3,
        )
        output = self.root / "labels-split"
        manifest = materialize_labels_and_split(
            tables / "team-v1.parquet",
            tables / "prefix-v1.parquet",
            output,
            source_snapshot_hash="snapshot-hash",
            feature_manifest_hash="feature-hash",
            tables_manifest_hash="tables-hash",
            command="fixed",
            batch_size=3,
        )
        self.assertEqual(manifest["label_acceptance"]["league_seasons"], 15)
        self.assertEqual(manifest["label_acceptance"]["invalid_champion_leagues"], 0)
        self.assertEqual(len(label_manifest()["sha256"]), 64)
        split = json.loads((output / "split-v1.json").read_text())
        self.assertEqual(
            split["counts"]["league_seasons"],
            {"train": 9, "validation": 3, "locked_test": 3},
        )
        self.assertEqual((output / "locked-test-2025-v1.json").stat().st_mode & 0o777, 0o444)
        self.assertEqual((output / "split-v1.json").stat().st_mode & 0o777, 0o444)
        self.assertEqual(len(list(load_team_partition(output / "split-v1.json", "train"))), 18)
        with self.assertRaisesRegex(PermissionError, "locked-benchmark"):
            load_team_partition(output / "split-v1.json", "locked_test")
        with self.assertRaises(FileExistsError):
            materialize_labels_and_split(
                tables / "team-v1.parquet",
                tables / "prefix-v1.parquet",
                output,
                source_snapshot_hash="snapshot-hash",
                feature_manifest_hash="feature-hash",
                tables_manifest_hash="tables-hash",
                command="fixed",
                batch_size=3,
            )


    def test_baseline_bundle_is_reproducible_and_never_loads_2025(self):
        tables = self.root / "baseline-tables"
        materialize_training_tables(
            self.store.database_path,
            self.market_directory / "market-v1.sqlite3",
            tables,
            source_snapshot_hash="snapshot-hash",
            source_manifest_hash="source-hash",
            feature_manifest_hash="feature-hash",
            market_manifest_hash="market-hash",
            command="fixed",
            seed=9,
            epoch=2,
            batch_size=3,
        )
        split_output = self.root / "baseline-split"
        split_artifact = materialize_labels_and_split(
            tables / "team-v1.parquet",
            tables / "prefix-v1.parquet",
            split_output,
            source_snapshot_hash="snapshot-hash",
            feature_manifest_hash="feature-hash",
            tables_manifest_hash="tables-hash",
            command="fixed",
            batch_size=3,
        )
        arguments = {
            "source_snapshot_hash": "snapshot-hash",
            "feature_manifest_hash": "feature-hash",
            "label_manifest_hash": split_artifact["label_contract"]["sha256"],
            "tables_manifest_hash": "tables-hash",
            "market_manifest_hash": "market-hash",
            "command": "fixed",
            "code_revision": "fixture",
            "seed": 9,
            "bootstrap_samples": 5,
        }
        left = self.root / "baselines-left"
        right = self.root / "baselines-right"
        first = fit_baselines(
            split_output / "split-v1.json",
            left,
            **arguments,
        )
        second = fit_baselines(
            split_output / "split-v1.json",
            right,
            **arguments,
        )
        self.assertEqual(first, second)
        self.assertFalse(first["locked_test_loaded"])
        self.assertEqual(first["loaded_partitions"], ["train", "validation"])
        self.assertEqual(
            set(first["artifacts"]),
            {
                "uniform_championship",
                "draft_slot_and_context",
                "historical_market_value",
                "regularized_linear_logistic",
                "gradient_boosted_tree",
            },
        )
        self.assertEqual({row["status"] for row in first["artifacts"].values()}, {"research"})
        self.assertEqual(
            load_baseline_bundle(left / "baseline-bundle.manifest.json")["sha256"],
            first["sha256"],
        )
        with self.assertRaisesRegex(ValueError, "context mismatch"):
            load_baseline_bundle(
                left / "baseline-bundle.manifest.json",
                expected={"feature_manifest_hash": "wrong"},
            )


    def test_labels_use_custom_points_cover_ties_and_preserve_incomplete_champion_null(self):
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE team_seasons SET h2h_wins = 0, h2h_losses = 0, h2h_ties = 1,
                                        regular_season_games = 1
                WHERE league_id = 'synthetic-2021-0'
                """
            )
            connection.execute(
                "UPDATE team_seasons SET champion = NULL WHERE league_id = 'synthetic-2021-1'"
            )
            connection.commit()
            tied = labels_for_league(connection, "synthetic-2021-0", 2021)
            incomplete = labels_for_league(connection, "synthetic-2021-1", 2021)
        self.assertEqual({row["regular_season_win_percentage"] for row in tied.values()}, {0.5})
        self.assertEqual(tied[1]["points_for_percentile"], 100.0)
        self.assertTrue(all(row["champion"] is None for row in incomplete.values()))

    def test_training_exclusions_cover_keeper_and_error_quality(self):
        with self.connection() as connection:
            connection.execute(
                "UPDATE draft_picks SET is_keeper = 1 WHERE draft_id = 'draft-2021-0' AND pick_no = 1"
            )
            connection.execute(
                """
                INSERT INTO quality_flags(scope, entity_key, code, severity, details_json, detected_at)
                VALUES ('league_season', 'synthetic-2021-0:2021', 'broken', 'error', '{}', 'fixed')
                """
            )
            connection.commit()
            reasons = training_exclusion_reasons(
                connection, "synthetic-2021-0", 2021, "draft-2021-0"
            )
        self.assertIn("keeper_draft", reasons)
        self.assertIn("error_quality_flag", reasons)

    def test_temporal_split_is_whole_league_and_locked_manifest_is_immutable(self):
        teams, prefixes = self.team_and_prefix_rows()
        manifest = build_split_manifest(teams)
        self.assertEqual(
            manifest["counts"]["league_seasons"],
            {"train": 9, "validation": 3, "locked_test": 3},
        )
        self.assertTrue(all(value.startswith("2025:") for value in manifest["partitions"]["locked_test"]))
        self.assertTrue(assert_split_isolation(teams, manifest))
        self.assertTrue(assert_split_isolation(prefixes, manifest))
        leaked = [{**prefixes[0], "partition": "locked_test"}]
        with self.assertRaisesRegex(ValueError, "crosses"):
            assert_split_isolation(leaked, manifest)
        path = self.root / "split.json"
        write_split_manifest(manifest, path)
        with self.assertRaises(FileExistsError):
            write_split_manifest(manifest, path)


class HDVNRawAuditTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = Store(self.root)
        self.raw_hash = self.store.save_raw("fixture", {"valid": True})
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO users(
                    user_id, username, raw_hash, first_seen_at, updated_at
                ) VALUES ('fixture', 'fixture', ?, 'fixed', 'fixed')
                """,
                (self.raw_hash,),
            )
            row = connection.execute(
                "SELECT relative_path FROM raw_objects WHERE content_hash = ?",
                (self.raw_hash,),
            ).fetchone()
        self.raw_path = self.root / row["relative_path"]

    def tearDown(self):
        self.temporary.cleanup()

    def audit(self):
        return audit_raw_sources(self.store.database_path, self.root, chunk_size=3)

    def test_raw_trace_accepts_valid_object(self):
        report = self.audit()
        self.assertTrue(report["passed"])
        self.assertEqual(report["verified_objects"], 1)
        self.assertEqual(report["missing_database_references"], 0)

    def test_raw_trace_reports_missing_file(self):
        self.raw_path.unlink()
        report = self.audit()
        self.assertFalse(report["passed"])
        self.assertEqual(report["missing_files"], 1)

    def test_raw_trace_reports_corrupt_gzip(self):
        self.raw_path.write_bytes(b"not gzip")
        report = self.audit()
        self.assertFalse(report["passed"])
        self.assertEqual(report["corrupt_gzip_files"], 1)

    def test_raw_trace_reports_wrong_byte_count(self):
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE raw_objects SET byte_count = byte_count + 1 WHERE content_hash = ?",
                (self.raw_hash,),
            )
        report = self.audit()
        self.assertFalse(report["passed"])
        self.assertEqual(report["wrong_byte_counts"], 1)

    def test_raw_trace_reports_wrong_hash(self):
        data = b'{"valid\":false}'
        self.raw_path.write_bytes(gzip.compress(data, mtime=0))
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE raw_objects SET byte_count = ? WHERE content_hash = ?",
                (len(data), self.raw_hash),
            )
        report = self.audit()
        self.assertFalse(report["passed"])
        self.assertEqual(report["wrong_hashes"], 1)
        self.assertEqual(report["wrong_byte_counts"], 0)

    def test_raw_trace_reports_missing_database_reference(self):
        connection = sqlite3.connect(self.store.database_path)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "UPDATE users SET raw_hash = ? WHERE user_id = 'fixture'",
                ("f" * 64,),
            )
            connection.commit()
        finally:
            connection.close()
        report = self.audit()
        self.assertFalse(report["passed"])
        self.assertEqual(report["missing_database_references"], 1)


class HDVNEvaluationTest(unittest.TestCase):
    def prediction_rows(self):
        rows = []
        for league_id in ("a", "b"):
            for roster_id in (1, 2):
                rows.append({
                    "league_season_id": f"2024:{league_id}",
                    "league_id": league_id,
                    "season": 2024,
                    "team_count": 2,
                    "scoring_format": "ppr",
                    "draft_slot": roster_id,
                    "roster_id": roster_id,
                    "points_for_percentile": 100.0 if roster_id == 1 else 0.0,
                    "made_playoffs": 1 if roster_id == 1 else 0,
                    "champion": 1 if roster_id == 1 else 0,
                    "predicted_points_for_percentile": 80.0 if roster_id == 1 else 20.0,
                    "predicted_playoff": 0.8 if roster_id == 1 else 0.2,
                })
        return uniform_championship_predictions(rows)

    def test_metric_harness_and_clustered_bootstrap_are_deterministic(self):
        rows = self.prediction_rows()
        metrics = evaluate_predictions(rows)
        self.assertEqual(metrics["points_percentile"]["mae"], 20.0)
        self.assertAlmostEqual(metrics["playoff"]["brier"], 0.04)
        self.assertEqual(metrics["within_league_roster_ranking"]["pairwise_concordance"], 1.0)
        metric = lambda sample: evaluate_predictions(sample)["points_percentile"]["mae"]
        self.assertEqual(
            clustered_bootstrap(rows, metric, seed=7, samples=20),
            clustered_bootstrap(rows, metric, seed=7, samples=20),
        )

    def test_championship_probabilities_fail_when_not_normalized(self):
        rows = self.prediction_rows()
        rows[0]["predicted_champion"] = 0.6
        with self.assertRaisesRegex(ValueError, "sum to one"):
            evaluate_predictions(rows)

    def test_required_baseline_interfaces_are_named(self):
        names = {row["name"] for row in BASELINE_INTERFACES}
        self.assertEqual(
            names,
            {
                "uniform_championship", "draft_slot_and_context", "historical_market_value",
                "regularized_linear_logistic", "gradient_boosted_tree", "projection_value",
                "deterministic_projection_lookahead", "coupled_ffsim_terminal_rollouts",
            },
        )
        self.assertEqual(
            {family.value for family in ModelFamily},
            {
                "context_baseline", "regularized_linear_logistic", "boosted_tree",
                "completed_draft_neural", "partial_prefix_neural",
            },
        )

    def metadata(self):
        return {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "model_family": ModelFamily.CONTEXT_BASELINE.value,
            "model_version": "fixture",
            "code_revision": "abc",
            "source_snapshot_hash": "s",
            "feature_version": "f",
            "label_version": "l",
            "split_manifest_hash": "x",
            "market_projection_provenance": {},
            "counts_by_year_context": [],
            "prefix_sampling_method": "one_per_team",
            "total_team_weight": 1.0,
            "architecture": "fixture_no_model",
            "parameter_count": 0,
            "seed": 1,
            "optimizer": None,
            "loss_weights": None,
            "stopping_rule": None,
            "baseline_metrics": {},
            "holdout_metrics": None,
            "calibration": {},
            "limitations": ["fixture"],
            "status": "research",
        }

    def test_artifact_loading_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            write_artifact_manifest(self.metadata(), path)
            self.assertEqual(load_artifact_manifest(path)["status"], "research")
            with self.assertRaisesRegex(ValueError, "context mismatch"):
                load_artifact_manifest(path, expected={"feature_version": "wrong"})
            path.write_text(json.dumps(self.metadata()))
            with self.assertRaisesRegex(ValueError, "hash missing"):
                load_artifact_manifest(path)
            path.write_text("not json")
            with self.assertRaisesRegex(ValueError, "malformed"):
                load_artifact_manifest(path)
            path.write_text(json.dumps({"artifact_schema_version": ARTIFACT_SCHEMA_VERSION}))
            with self.assertRaisesRegex(ValueError, "missing"):
                load_artifact_manifest(path)


class HDVNDryRunTest(unittest.TestCase):
    def test_dry_run_is_deterministic_bounded_and_network_free(self):
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            tracemalloc.start()
            first = run_synthetic_dry_run(left)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            second = run_synthetic_dry_run(right)
        self.assertEqual(first, second)
        self.assertLess(peak, 20 * 1024 * 1024)
        self.assertEqual(first["sleeper_calls"], 0)
        self.assertFalse(first["active_crawler_database_used"])
        self.assertTrue(first["deliberate_leakage_rejected"])
        self.assertTrue(first["championship_probability_sums_valid"])
        self.assertTrue(first["future_draft_rank_change_rejected"])
        self.assertEqual(first["sampled_prefix_rows"], first["total_team_weight"])

    def test_cli_dry_run_does_not_initialize_active_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory) / "active-crawler"
            output = Path(directory) / "dry-run"
            self.assertEqual(
                main(["--data-dir", str(active), "hdvn-dry-run", "--output", str(output)]),
                0,
            )
            self.assertFalse(active.exists())
            self.assertTrue((output / "report.json").is_file())


if __name__ == "__main__":
    unittest.main()
