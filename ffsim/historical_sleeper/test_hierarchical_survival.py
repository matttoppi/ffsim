import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .hdvn_snapshot import canonical_json, sha256_file
from .hierarchical_survival import (
    HIERARCHICAL_SURVIVAL_VERSION,
    _probability,
    load_hierarchical_survival_artifact,
    load_hierarchical_survival_model,
    predict_hierarchical_survival,
)


class HierarchicalSurvivalTest(unittest.TestCase):
    def test_position_cell_shrinks_toward_the_rank_gap_round_rate(self):
        model = {
            "global": (800, 1_000),
            "pooled": {(2, 18, 1): (60, 1_000)},
            "position": {(2, 18, 1, "RB"): (7, 2_006)},
        }
        probability = _probability(model, (2, 18, 1, "RB"))

        self.assertLess(probability, 0.01)
        self.assertGreater(probability, 7 / 2_006)

    def test_prediction_exposes_direct_and_pooled_support(self):
        model = {
            "global": (80, 100),
            "pooled": {(1, 4, 3): (40, 50)},
            "position": {},
        }
        prediction = predict_hierarchical_survival(
            model,
            market_rank=1,
            gap=4,
            round_=3,
            position="WR",
        )

        self.assertEqual(prediction["direct_support"], 0)
        self.assertEqual(prediction["pooled_support"], 50)
        self.assertEqual(prediction["status"], "offline_research")

    def test_loader_rejects_locked_test_and_changed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            model_path = directory / "hierarchical-survival.json"
            report_path = directory / "validation-report.json"
            manifest_path = directory / "hierarchical-survival.manifest.json"
            model_path.write_text(canonical_json({
                "model_version": HIERARCHICAL_SURVIVAL_VERSION,
                "status": "research",
                "shrinkage_observations": 100.0,
                "key_order": ["market_rank", "gap", "round", "position"],
                "global": [8, 10],
                "pooled_cells": [{
                    "key": [1, 2, 1], "successes": 4, "count": 5,
                }],
                "position_cells": [{
                    "key": [1, 2, 1, "RB"], "successes": 3, "count": 4,
                }],
            }) + "\n")
            report_path.write_text("{}\n")
            manifest = {
                "model_version": HIERARCHICAL_SURVIVAL_VERSION,
                "status": "research",
                "source_snapshot_sha256": "source",
                "feature_manifest_hash": "features",
                "market_manifest_hash": "market",
                "market_database_sha256": "database",
                "code_revision": "test",
                "code_sha256": "test",
                "train_development_seasons": [2021, 2022, 2023],
                "seen_transfer_seasons": [2024],
                "locked_test_loaded": False,
                "shrinkage_observations": 100.0,
                "bootstrap_samples": 2,
                "seed": 20260828,
                "gate": {"passes": True},
                "command": "test",
                "files": {
                    model_path.name: {
                        "bytes": model_path.stat().st_size,
                        "sha256": sha256_file(model_path),
                    },
                    report_path.name: {
                        "bytes": report_path.stat().st_size,
                        "sha256": sha256_file(report_path),
                    },
                },
            }
            manifest["sha256"] = hashlib.sha256(
                canonical_json(manifest).encode()
            ).hexdigest()
            manifest_path.write_text(canonical_json(manifest) + "\n")

            loaded = load_hierarchical_survival_model(manifest_path)
            self.assertEqual(loaded["global"], (8, 10))
            self.assertIn((1, 2, 1, "RB"), loaded["position"])

            manifest["locked_test_loaded"] = True
            body = {key: value for key, value in manifest.items() if key != "sha256"}
            manifest["sha256"] = hashlib.sha256(
                canonical_json(body).encode()
            ).hexdigest()
            manifest_path.write_text(canonical_json(manifest) + "\n")
            with self.assertRaisesRegex(ValueError, "touched locked test"):
                load_hierarchical_survival_artifact(manifest_path)

            manifest["locked_test_loaded"] = False
            body = {key: value for key, value in manifest.items() if key != "sha256"}
            manifest["sha256"] = hashlib.sha256(
                canonical_json(body).encode()
            ).hexdigest()
            manifest_path.write_text(canonical_json(manifest) + "\n")
            model_path.write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "file hash mismatch"):
                load_hierarchical_survival_artifact(manifest_path)


if __name__ == "__main__":
    unittest.main()
