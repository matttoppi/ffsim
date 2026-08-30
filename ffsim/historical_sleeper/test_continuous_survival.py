import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from .continuous_survival import (
    FEATURE_ORDER,
    fit_continuous_survival,
    load_continuous_survival_artifact,
    load_continuous_survival_model,
    predict_continuous_survival,
)
from .empirical_survival import (
    build_empirical_survival,
    load_empirical_survival_artifact,
    load_empirical_survival_lookup,
    lookup_survival,
)
from .hdvn_market import _create_market_schema
from .hdvn_snapshot import canonical_json, sha256_file


class ContinuousSurvivalTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "market.sqlite3"
        self._write_database()
        body = {
            "source_snapshot_sha256": "source",
            "feature_manifest_hash": "features",
            "files": {
                self.database.name: {
                    "bytes": self.database.stat().st_size,
                    "sha256": sha256_file(self.database),
                }
            },
        }
        manifest = {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}
        self.market_manifest = self.root / "market.manifest.json"
        self.market_manifest.write_text(canonical_json(manifest) + "\n")

    def tearDown(self):
        self.temporary.cleanup()

    def _write_database(self):
        connection = sqlite3.connect(self.database)
        _create_market_schema(connection)
        positions = ("RB", "WR", "WR", "RB", "QB", "TE", "RB", "WR", "QB", "TE", "K", "DEF")
        for season in (2021, 2022, 2023, 2024, 2025):
            for number in range(8):
                draft_id = f"draft-{season}-{number}"
                connection.execute(
                    "INSERT INTO boards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (draft_id, season, "PPR", 2, "snake", "main", 1, 0, 30, "sources", 0, 12),
                )
                for rank, position in enumerate(positions, 1):
                    player_id = f"{draft_id}-p{rank}"
                    connection.execute(
                        "INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (draft_id, player_id, position, rank, float(rank), 1.0, 30, 30),
                    )
                order = (1, 2, 2, 1, 1, 2, 2, 1)
                selected = (
                    (1, 2, 4, 3, 5, 7, 6, 8)
                    if number % 2
                    else (1, 3, 2, 4, 5, 6, 8, 7)
                )
                for pick_no, (roster_id, rank) in enumerate(zip(order, selected), 1):
                    player_id = f"{draft_id}-p{rank}"
                    connection.execute(
                        "INSERT INTO market_picks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (draft_id, pick_no, roster_id, player_id, rank, float(rank), float(rank - pick_no), 30, "sources"),
                    )
        connection.commit()
        connection.close()

    def test_prediction_is_monotonic_in_rank_and_gap(self):
        coefficients = np.zeros(len(FEATURE_ORDER))
        coefficients[1] = 2.0
        coefficients[2] = -3.0
        model = {"coefficients": coefficients}
        common = {
            "round_": 1,
            "position": "RB",
            "scoring_format": "PPR",
            "team_count": 10,
        }
        rank_one = predict_continuous_survival(model, market_rank=1, gap=10, **common)
        rank_five = predict_continuous_survival(model, market_rank=5, gap=10, **common)
        short_gap = predict_continuous_survival(model, market_rank=2, gap=2, **common)
        long_gap = predict_continuous_survival(model, market_rank=2, gap=18, **common)
        self.assertGreater(rank_five["survives_to_next_pick"], rank_one["survives_to_next_pick"])
        self.assertGreater(short_gap["survives_to_next_pick"], long_gap["survives_to_next_pick"])

    def test_rolling_fit_excludes_2024_and_2025_and_loads_fail_closed(self):
        output = self.root / "output"
        manifest = fit_continuous_survival(
            self.database,
            self.market_manifest,
            output,
            expected_source_hash="source",
            expected_feature_hash="features",
            command="fixed",
            code_revision="test",
            bootstrap_samples=10,
        )
        self.assertEqual(manifest["train_development_seasons"], [2021, 2022, 2023])
        self.assertFalse(manifest["validation_2024_loaded"])
        self.assertFalse(manifest["locked_test_loaded"])
        report = json.loads((output / "rolling-fold-report.json").read_text())
        self.assertEqual(set(report["folds"]), {
            "train-2021_validate-2022",
            "train-2021-2022_validate-2023",
        })
        model = load_continuous_survival_model(output / "continuous-survival.manifest.json")
        self.assertGreaterEqual(model["coefficients"][1], 0)
        self.assertLessEqual(model["coefficients"][2], 0)
        loaded = load_continuous_survival_artifact(
            output / "continuous-survival.manifest.json",
            expected={"feature_manifest_hash": "features"},
        )
        self.assertEqual(loaded["sha256"], manifest["sha256"])
        with self.assertRaisesRegex(ValueError, "feature_manifest_hash"):
            load_continuous_survival_artifact(
                output / "continuous-survival.manifest.json",
                expected={"feature_manifest_hash": "wrong"},
            )

    def test_empirical_lookup_is_exact_supported_and_fail_closed(self):
        lookup = {
            "minimum_support": 250,
            "lookup": {
                (2, 18, 1, "RB", "PPR", 10): {
                    "successes": 5,
                    "count": 696,
                    "raw_rate": 5 / 696,
                    "probability": 6 / 698,
                    "interval_95": [0.0, 0.02],
                }
            },
        }
        available = lookup_survival(
            lookup,
            market_rank=2,
            gap=18,
            round_=1,
            position="RB",
            scoring_format="PPR",
            team_count=10,
        )
        unavailable = lookup_survival(
            lookup,
            market_rank=2,
            gap=18,
            round_=1,
            position="RB",
            scoring_format="HALF_PPR",
            team_count=10,
        )
        self.assertEqual(available["status"], "available")
        self.assertEqual(available["count"], 696)
        self.assertLess(available["probability"], 0.01)
        self.assertEqual(unavailable["status"], "unavailable")

    def test_empirical_build_uses_training_years_only(self):
        output = self.root / "empirical"
        manifest = build_empirical_survival(
            self.database,
            self.market_manifest,
            output,
            expected_source_hash="source",
            expected_feature_hash="features",
            command="fixed",
            code_revision="test",
        )
        self.assertFalse(manifest["validation_2024_loaded"])
        self.assertFalse(manifest["locked_test_loaded"])
        loaded = load_empirical_survival_artifact(
            output / "empirical-survival.manifest.json"
        )
        self.assertEqual(loaded["sha256"], manifest["sha256"])
        lookup = load_empirical_survival_lookup(
            output / "empirical-survival.manifest.json"
        )
        self.assertEqual(lookup["minimum_support"], 250)


if __name__ == "__main__":
    unittest.main()
