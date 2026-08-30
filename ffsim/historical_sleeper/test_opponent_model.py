import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from .hdvn_market import _create_market_schema
from .hdvn_snapshot import canonical_json, sha256_file
from .opponent_model import (
    fit_opponent_model,
    load_opponent_artifact,
    load_opponent_model,
    predict_player_survival,
    predict_tier_survival,
)


SOURCE_HASH = "source-hash"
FEATURE_HASH = "feature-hash"


class OpponentModelTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "market.sqlite3"
        self._write_database()
        body = {
            "source_snapshot_sha256": SOURCE_HASH,
            "feature_manifest_hash": FEATURE_HASH,
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
            for number in range(6):
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
                selected = (1, 2, 4, 3, 5, 7, 6, 8) if number % 2 else (1, 3, 2, 4, 5, 6, 8, 7)
                for pick_no, (roster_id, rank) in enumerate(zip(order, selected), 1):
                    player_id = f"{draft_id}-p{rank}"
                    connection.execute(
                        "INSERT INTO market_picks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (draft_id, pick_no, roster_id, player_id, rank, float(rank), float(rank - pick_no), 30, "sources"),
                    )
        connection.commit()
        connection.close()

    def test_fit_is_offline_reproducible_and_fail_closed(self):
        output = self.root / "output"
        manifest = fit_opponent_model(
            self.database,
            self.market_manifest,
            output,
            expected_source_hash=SOURCE_HASH,
            expected_feature_hash=FEATURE_HASH,
            command="fixed",
            code_revision="test",
            bootstrap_samples=20,
        )
        self.assertEqual(manifest["temperature_grid"], [1.0])
        self.assertEqual(manifest["reach_rate_grid"], [0.0])
        self.assertEqual(set(manifest["comparators"]), {"live_provisional"})
        report = json.loads((output / "validation-report.json").read_text())
        self.assertEqual(report["train_seasons"], [2021, 2022, 2023])
        self.assertEqual(report["validation_seasons"], [2024])
        self.assertFalse(report["locked_test_loaded"])
        self.assertGreater(report["choice"]["models"]["fitted"]["scored_picks"], 0)
        self.assertGreater(report["survival"]["players"]["model"]["count"], 0)
        self.assertGreater(report["survival"]["tiers"]["model"]["count"], 0)
        loaded = load_opponent_artifact(
            output / "opponent-model.manifest.json",
            expected={"feature_manifest_hash": FEATURE_HASH},
        )
        self.assertEqual(loaded["sha256"], manifest["sha256"])
        with self.assertRaisesRegex(ValueError, "feature_manifest_hash"):
            load_opponent_artifact(
                output / "opponent-model.manifest.json",
                expected={"feature_manifest_hash": "wrong"},
            )
        model = load_opponent_model(output / "opponent-model.manifest.json")
        self.assertEqual(model["buckets"]["player_rank"], "exact_integer_1_to_10")
        self.assertEqual(model["buckets"]["player_gap"], "exact_integer")
        self.assertEqual(model["buckets"]["player_round"], "exact_integer")
        player_key = next(iter(model["_survival_lookups"]["player_model"]))
        self.assertIsInstance(player_key[0], int)
        self.assertIsInstance(player_key[1], int)
        self.assertIsInstance(player_key[2], int)
        player = predict_player_survival(
            model,
            market_rank=1,
            gap=2,
            position="RB",
            round_=1,
        )
        tier = predict_tier_survival(
            model,
            gap=2,
            round_=1,
            scoring_format="PPR",
            team_count=2,
        )
        self.assertGreaterEqual(player["survives_to_next_pick"], 0)
        self.assertLessEqual(player["survives_to_next_pick"], 1)
        self.assertGreaterEqual(tier["survives_to_next_pick"], 0)
        self.assertLessEqual(tier["survives_to_next_pick"], 1)
        self.assertGreaterEqual(tier["expected_remaining"], 0)

    def test_elite_rb_long_gap_regression_stays_below_one_percent(self):
        model = {
            "survival": {"player_global": [5_354_108.0, 6_170_610]},
            "_survival_lookups": {
                "player_baseline": {(2, 18, 1): [230.0, 3_801]},
                "player_model": {(2, 18, 1, "RB"): [7.0, 2_006]},
            },
        }
        result = predict_player_survival(
            model,
            market_rank=2,
            gap=18,
            position="RB",
            round_=1,
        )
        self.assertEqual(result["support"], 2_006)
        self.assertAlmostEqual(7 / 2_006, 0.003489531405782652)
        self.assertLess(result["survives_to_next_pick"], 0.01)

    def test_market_hash_mismatch_fails_before_fitting(self):
        self.database.write_bytes(self.database.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "database hash"):
            fit_opponent_model(
                self.database,
                self.market_manifest,
                self.root / "output",
                expected_source_hash=SOURCE_HASH,
                expected_feature_hash=FEATURE_HASH,
                command="fixed",
                code_revision="test",
                bootstrap_samples=5,
            )


if __name__ == "__main__":
    unittest.main()
