import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .hdvn_residual import (
    METHODS,
    _support_bucket,
    load_residual_artifact,
    load_train_only,
    run_residual_alpha,
)
from .hdvn_snapshot import canonical_json, sha256_file


SOURCE_HASH = "source-hash"
FEATURE_HASH = "feature-hash"
TABLE_HASH = "table-hash"
LABEL_HASH = "label-hash"
MARKET_HASH = "market-hash"


class HDVNResidualAlphaTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.split_path = self._write_split()

    def tearDown(self):
        self.temporary.cleanup()

    @property
    def expected(self):
        return {
            "source_snapshot_sha256": SOURCE_HASH,
            "feature_manifest_hash": FEATURE_HASH,
            "tables_manifest_hash": TABLE_HASH,
            "label_manifest_hash": LABEL_HASH,
        }

    def _row(self, season, league_index, roster):
        positions = ("RB", "WR", "QB") if roster == 1 else ("WR", "RB", "TE")
        champion = int(roster == 1)
        points = 65.0 + league_index + 15 * champion + (season - 2021)
        counts = {position: positions.count(position) for position in set(positions)}
        return {
            "team_table_version": "hdvn-team-table-v1",
            "league_id": f"league-{season}-{league_index}",
            "season": season,
            "draft_id": f"draft-{season}-{league_index}",
            "roster_id": roster,
            "owner_id": f"owner-{roster}",
            "draft_slot": roster,
            "draft_geometry": "snake",
            "draft_type": "snake",
            "round_count": 3,
            "team_count": 2,
            "scoring_format": "PPR",
            "scoring_settings_hash": "settings",
            "roster_positions_json": '["QB","RB","WR","TE","FLEX","BN"]',
            "position_sequence_json": json.dumps(positions, separators=(",", ":")),
            "pick_player_ids_json": '["ignored-1","ignored-2","ignored-3"]',
            "pick_numbers_json": json.dumps([roster, 5 - roster, 4 + roster], separators=(",", ":")),
            "pick_rounds_json": "[1,2,3]",
            "first_qb_round": 3 if roster == 1 else 4,
            "first_rb_round": 1 if roster == 1 else 2,
            "first_wr_round": 2 if roster == 1 else 1,
            "first_te_round": 4 if roster == 1 else 3,
            "position_counts_r3_json": json.dumps(counts, separators=(",", ":")),
            "position_counts_r5_json": json.dumps(counts, separators=(",", ":")),
            "position_counts_r8_json": json.dumps(counts, separators=(",", ":")),
            "position_counts_json": json.dumps(counts, separators=(",", ":")),
            "starter_slots": 5,
            "starter_covered": 3,
            "flex_slots": 1,
            "flex_covered": 1,
            "bench_structure_json": "{}",
            "market_rank_by_pick_json": "[1,4,5]",
            "market_adp_by_pick_json": "[1.5,3.5,5.5]",
            "market_value_by_pick_json": "[0.5,-0.5,0.5]",
            "cumulative_market_value": 0.5,
            "market_support_drafts": 30 + league_index,
            "market_cutoff_ms": 1,
            "market_provenance_hash": "market",
            "source_manifest_hash": "source-manifest",
            "feature_manifest_hash": FEATURE_HASH,
            "feature_version": "hdvn-features-v1",
            "label_version": "hdvn-labels-v1",
            "points_for_percentile": points,
            "regular_season_win_percentage": 0.7 if champion else 0.3,
            "made_playoffs": champion,
            "champion": champion,
            "training_eligible": True,
            "exclusion_reasons_json": "[]",
        }

    def _write_split(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        train_rows = [
            self._row(season, league, roster)
            for season in (2021, 2022, 2023)
            for league in range(6)
            for roster in (1, 2)
        ]
        train = self.root / "train.parquet"
        pq.write_table(pa.Table.from_pylist(train_rows), train)
        validation = self.root / "validation-2024.parquet"
        validation.write_bytes(b"must not open 2024")
        locked = self.root / "locked-2025.parquet"
        locked.write_bytes(b"must not open 2025")
        body = {
            "split_version": "hdvn-split-v1",
            "source_snapshot_sha256": SOURCE_HASH,
            "feature_manifest_hash": FEATURE_HASH,
            "tables_manifest_hash": TABLE_HASH,
            "label_manifest_hash": LABEL_HASH,
            "years": {"train": [2021, 2022, 2023], "validation": [2024], "locked_test": [2025]},
            "partition_files": {
                "train": {"path": train.name, "sha256": sha256_file(train)},
                "validation": {"path": validation.name, "sha256": sha256_file(validation)},
                "locked_test": {"path": locked.name, "sha256": sha256_file(locked)},
            },
        }
        manifest = {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}
        path = self.root / "split.json"
        path.write_text(canonical_json(manifest) + "\n")
        return path

    def test_loader_reads_only_train_years(self):
        rows, dataset, manifest, opened = load_train_only(self.split_path, expected=self.expected)
        self.assertEqual(len(rows), 36)
        self.assertEqual({row["season"] for row in rows}, {2021, 2022, 2023})
        self.assertEqual(Path(opened).name, "train.parquet")
        self.assertEqual(dataset.partition, "train")
        self.assertEqual(manifest["years"]["locked_test"], [2025])

    def test_support_buckets_are_fixed(self):
        self.assertEqual(
            [_support_bucket(value) for value in (0, 1, 24, 25, 99, 100, 499, 500)],
            ["none", "sparse", "sparse", "25-99", "25-99", "100-499", "100-499", "500+"],
        )

    def test_residual_discovery_is_train_only_and_reproducible(self):
        output = self.root / "output"
        manifest = run_residual_alpha(
            self.split_path,
            output,
            source_snapshot_hash=SOURCE_HASH,
            feature_manifest_hash=FEATURE_HASH,
            market_manifest_hash=MARKET_HASH,
            tables_manifest_hash=TABLE_HASH,
            label_manifest_hash=LABEL_HASH,
            command="fixed",
            code_revision="test",
            bootstrap_samples=20,
        )
        self.assertEqual(manifest["loaded_partitions"], ["train"])
        self.assertFalse(manifest["validation_2024_loaded"])
        self.assertFalse(manifest["locked_test_loaded"])
        self.assertEqual(manifest["methods"], list(METHODS))
        report = json.loads((output / "residual-alpha-report.json").read_text())
        self.assertTrue(report["prediction_reproducibility"]["identical"])
        self.assertTrue(report["neural_reproducible"])
        self.assertEqual(len(report["folds"]), 2)
        self.assertEqual(
            load_residual_artifact(
                output / "residual-alpha.manifest.json",
                expected={"feature_manifest_hash": FEATURE_HASH},
            )["sha256"],
            manifest["sha256"],
        )

    def test_artifact_loader_rejects_semantic_mismatch(self):
        output = self.root / "output"
        run_residual_alpha(
            self.split_path,
            output,
            source_snapshot_hash=SOURCE_HASH,
            feature_manifest_hash=FEATURE_HASH,
            market_manifest_hash=MARKET_HASH,
            tables_manifest_hash=TABLE_HASH,
            label_manifest_hash=LABEL_HASH,
            command="fixed",
            code_revision="test",
            bootstrap_samples=5,
        )
        with self.assertRaisesRegex(ValueError, "feature_manifest_hash"):
            load_residual_artifact(
                output / "residual-alpha.manifest.json",
                expected={"feature_manifest_hash": "wrong"},
            )


if __name__ == "__main__":
    unittest.main()
