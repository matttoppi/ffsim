import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from .hdvn_neural import (
    CONTEXT_FEATURE_ORDER,
    PICK_FEATURE_ORDER,
    CompletedDraftNetwork,
    fit_normalizer,
    load_completed_draft_datasets,
    load_neural_artifact,
    normalize_inputs,
    predict_rows,
    train_network,
    within_league_softmax,
)
from .hdvn_snapshot import canonical_json, sha256_file

SOURCE_HASH = "source-hash"
FEATURE_HASH = "feature-hash"
TABLE_HASH = "table-hash"
LABEL_HASH = "label-hash"


class HDVNNeuralTest(unittest.TestCase):
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

    def _row(self, season, league, roster, *, champion, positions=("RB", "WR")):
        count = len(positions)
        return {
            "league_id": league,
            "season": season,
            "draft_id": f"draft-{league}",
            "roster_id": roster,
            "draft_slot": roster,
            "round_count": count,
            "team_count": 2,
            "scoring_format": "PPR",
            "roster_positions_json": '["QB","RB","WR","FLEX","BN"]',
            "position_sequence_json": json.dumps(positions, separators=(",", ":")),
            "pick_numbers_json": json.dumps(list(range(roster, 2 * count + 1, 2))[:count], separators=(",", ":")),
            "pick_rounds_json": json.dumps(list(range(1, count + 1)), separators=(",", ":")),
            "market_rank_by_pick_json": json.dumps(list(range(1, count + 1)), separators=(",", ":")),
            "market_adp_by_pick_json": json.dumps([float(value) for value in range(1, count + 1)], separators=(",", ":")),
            "market_value_by_pick_json": json.dumps([0.5] * count, separators=(",", ":")),
            "cumulative_market_value": 0.5 * count,
            "market_support_drafts": 25,
            "feature_manifest_hash": FEATURE_HASH,
            "points_for_percentile": float(100 * champion),
            "made_playoffs": champion,
            "champion": champion,
        }

    def _write_split(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        rows = {
            "train": [
                self._row(2021, "train", 1, champion=1),
                self._row(2021, "train", 2, champion=0),
            ],
            "validation": [
                self._row(2024, "validation", 1, champion=0, positions=("WR", "RB", "TE")),
                self._row(2024, "validation", 2, champion=1, positions=("RB", "WR", "QB")),
            ],
        }
        records = {}
        for partition, partition_rows in rows.items():
            path = self.root / f"{partition}.parquet"
            pq.write_table(pa.Table.from_pylist(partition_rows), path)
            records[partition] = {"path": path.name, "sha256": sha256_file(path)}
        locked = self.root / "locked-test-2025.parquet"
        locked.write_bytes(b"this file must not be opened")
        records["locked_test"] = {"path": locked.name, "sha256": sha256_file(locked)}
        body = {
            "split_version": "hdvn-split-v1",
            "source_snapshot_sha256": SOURCE_HASH,
            "feature_manifest_hash": FEATURE_HASH,
            "tables_manifest_hash": TABLE_HASH,
            "label_manifest_hash": LABEL_HASH,
            "years": {"train": [2021, 2022, 2023], "validation": [2024], "locked_test": [2025]},
            "partition_files": records,
        }
        manifest = {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}
        path = self.root / "split.json"
        path.write_text(canonical_json(manifest) + "\n")
        return path

    def test_loader_opens_only_train_and_validation_partitions(self):
        datasets = load_completed_draft_datasets(self.split_path, expected=self.expected)
        self.assertEqual(
            [Path(path).name for path in datasets.opened_paths],
            ["train.parquet", "validation.parquet"],
        )
        self.assertEqual({row["season"] for row in datasets.train.metadata}, {2021})
        self.assertEqual({row["season"] for row in datasets.validation.metadata}, {2024})
        self.assertNotIn("player_id", PICK_FEATURE_ORDER)
        self.assertNotIn("player_id", CONTEXT_FEATURE_ORDER)

    def test_explicit_mask_makes_padding_invariant(self):
        datasets = load_completed_draft_datasets(self.split_path, expected=self.expected)
        normalizer = fit_normalizer(datasets.train)
        picks, context = normalize_inputs(datasets.train, normalizer)
        model = CompletedDraftNetwork(seed=123)
        expected = model.forward(picks, datasets.train.mask, context)
        changed = picks.copy()
        changed[~datasets.train.mask] = 1000.0
        actual = model.forward(changed, datasets.train.mask, context)
        for left, right in zip(expected, actual):
            np.testing.assert_array_equal(left, right)
        self.assertTrue(np.all(picks[~datasets.train.mask] == 0))

    def test_feature_order_and_seed_are_deterministic(self):
        self.assertEqual(PICK_FEATURE_ORDER[:7], tuple(f"position_{value}" for value in ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")))
        left = CompletedDraftNetwork(seed=20260828)
        right = CompletedDraftNetwork(seed=20260828)
        self.assertEqual(left.parameter_count, 4707)
        self.assertLess(left.parameter_count, 100_000)
        for name in left.params:
            np.testing.assert_array_equal(left.params[name], right.params[name])

    def test_within_league_probabilities_sum_to_one(self):
        probabilities = within_league_softmax(
            np.asarray([1.0, 2.0, -1.0, 4.0]),
            ("league-a", "league-a", "league-b", "league-b"),
        )
        self.assertAlmostEqual(float(probabilities[:2].sum()), 1.0)
        self.assertAlmostEqual(float(probabilities[2:].sum()), 1.0)

    def test_direct_training_loop_is_deterministic(self):
        datasets = load_completed_draft_datasets(self.split_path, expected=self.expected)
        left_model, left_normalizer, left_training = train_network(
            datasets.train,
            datasets.validation,
            seed=20260828,
            batch_size=1,
        )
        right_model, right_normalizer, right_training = train_network(
            datasets.train,
            datasets.validation,
            seed=20260828,
            batch_size=1,
        )
        self.assertEqual(left_training, right_training)
        self.assertEqual(
            predict_rows(left_model, left_normalizer, datasets.validation),
            predict_rows(right_model, right_normalizer, datasets.validation),
        )

    def test_loader_rejects_locked_year_in_training_partition(self):
        manifest = json.loads(self.split_path.read_text())
        manifest["years"]["train"] = [2021, 2022, 2023, 2025]
        body = {key: value for key, value in manifest.items() if key != "sha256"}
        manifest["sha256"] = hashlib.sha256(canonical_json(body).encode()).hexdigest()
        self.split_path.write_text(canonical_json(manifest) + "\n")
        with self.assertRaisesRegex(ValueError, "training years"):
            load_completed_draft_datasets(self.split_path, expected=self.expected)


class HDVNNeuralArtifactTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        model = CompletedDraftNetwork(seed=1)
        self.model_path = self.root / "model.json"
        self.model_path.write_text(canonical_json({
            "parameter_count": model.parameter_count,
            "pick_feature_order": list(PICK_FEATURE_ORDER),
            "context_feature_order": list(CONTEXT_FEATURE_ORDER),
            "parameters": {name: value.tolist() for name, value in model.params.items()},
        }) + "\n")
        self.prediction_path = self.root / "predictions-2024.parquet"
        self.prediction_path.write_bytes(b"predictions")
        self.report_path = self.root / "validation-report.json"
        self.report_path.write_text("{}\n")
        self.manifest_path = self.root / "neural-artifact.manifest.json"
        self._write_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def _write_manifest(self, **changes):
        body = {
            "status": "research",
            "source_snapshot_sha256": SOURCE_HASH,
            "feature_manifest_hash": FEATURE_HASH,
            "split_manifest_hash": "split-hash",
            "loaded_partitions": ["train", "validation"],
            "locked_test_loaded": False,
            "deterministic_feature_order": {
                "pick": list(PICK_FEATURE_ORDER),
                "context": list(CONTEXT_FEATURE_ORDER),
            },
            "parameter_count": 4707,
            "files": {
                path.name: {"sha256": sha256_file(path)}
                for path in (self.model_path, self.prediction_path, self.report_path)
            },
            **changes,
        }
        manifest = {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}
        self.manifest_path.write_text(canonical_json(manifest) + "\n")

    def test_artifact_loader_fails_closed_on_contract_mismatches(self):
        expected = {
            "source_snapshot_sha256": SOURCE_HASH,
            "feature_manifest_hash": FEATURE_HASH,
            "split_manifest_hash": "split-hash",
            "status": "research",
            "parameter_count": 4707,
        }
        self.assertEqual(load_neural_artifact(self.manifest_path, expected=expected)["status"], "research")
        for key in ("source_snapshot_sha256", "feature_manifest_hash", "split_manifest_hash", "status"):
            with self.subTest(key=key):
                wrong = dict(expected)
                wrong[key] = "wrong"
                with self.assertRaisesRegex(ValueError, key):
                    load_neural_artifact(self.manifest_path, expected=wrong)
        self._write_manifest(status="live")
        with self.assertRaisesRegex(ValueError, "status"):
            load_neural_artifact(self.manifest_path)
        self._write_manifest(parameter_count=1)
        with self.assertRaisesRegex(ValueError, "parameter count"):
            load_neural_artifact(self.manifest_path)

    def test_artifact_loader_rejects_manifest_and_file_hash_changes(self):
        manifest = json.loads(self.manifest_path.read_text())
        manifest["locked_test_loaded"] = True
        self.manifest_path.write_text(canonical_json(manifest) + "\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_neural_artifact(self.manifest_path)
        self._write_manifest()
        self.model_path.write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "file hash mismatch"):
            load_neural_artifact(self.manifest_path)


if __name__ == "__main__":
    unittest.main()
