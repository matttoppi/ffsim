import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pyarrow.parquet as pq

from .hdvn_market import _create_market_schema
from .hdvn_snapshot import canonical_json, sha256_file
from .opponent_model import fit_opponent_model
from .wait_reach_replay import (
    _modal_hazard_survival,
    load_wait_reach_artifact,
    run_wait_reach_replay,
)


class WaitReachReplayTest(unittest.TestCase):
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
        self.opponent_output = self.root / "opponent"
        fit_opponent_model(
            self.database,
            self.market_manifest,
            self.opponent_output,
            expected_source_hash="source",
            expected_feature_hash="features",
            command="fixed",
            code_revision="test",
            bootstrap_samples=10,
        )

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

    def test_modal_hazard_respects_rank_and_gap(self):
        adp = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(_modal_hazard_survival(adp, 0, 0), 1.0)
        self.assertLess(
            _modal_hazard_survival(adp, 0, 2),
            _modal_hazard_survival(adp, 3, 2),
        )
        self.assertLess(
            _modal_hazard_survival(adp, 1, 2),
            _modal_hazard_survival(adp, 1, 1),
        )

    def test_replay_is_2024_only_and_fail_closed(self):
        output = self.root / "replay"
        manifest = run_wait_reach_replay(
            self.database,
            self.opponent_output / "opponent-model.manifest.json",
            output,
            command="fixed",
            code_revision="test",
            bootstrap_samples=10,
        )
        report = json.loads((output / "wait-reach-report.json").read_text())
        self.assertEqual(report["season"], 2024)
        self.assertTrue(report["seen_validation_diagnostic"])
        self.assertFalse(report["locked_test_loaded"])
        self.assertEqual(set(report["methods"]), {"market", "historical_player", "live_modal_hazard"})
        self.assertGreater(report["counts"]["targets"], 0)
        predictions = pq.read_table(output / "wait-reach-predictions-2024.parquet")
        self.assertEqual(set(predictions.column("season").to_pylist()), {2024})
        loaded = load_wait_reach_artifact(
            output / "wait-reach.manifest.json",
            expected={"opponent_manifest_hash": manifest["opponent_manifest_hash"]},
        )
        self.assertEqual(loaded["sha256"], manifest["sha256"])
        with self.assertRaisesRegex(ValueError, "opponent_manifest_hash"):
            load_wait_reach_artifact(
                output / "wait-reach.manifest.json",
                expected={"opponent_manifest_hash": "wrong"},
            )


if __name__ == "__main__":
    unittest.main()
