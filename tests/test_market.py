import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from ffsim.draft_intel.market import import_market_csv, load_market_snapshot_at
from ffsim.draft_intel.storage import SCHEMA


class MarketSnapshotTest(unittest.TestCase):
    def test_csv_import_is_append_only_and_reconstructs_historical_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with sqlite3.connect(database_path) as database:
                database.executescript(SCHEMA)
                database.execute(
                    "INSERT INTO canonical_players VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("sleeper:1", "One", "one", "WR", "ARI", 1, "now"),
                )
                database.execute(
                    "INSERT INTO player_external_ids VALUES (?, ?, ?, ?, ?, ?)",
                    ("sleeper:1", "sleeper", "1", "now", "now", 1.0),
                )

            csv_path = Path(directory) / "market.csv"
            csv_path.write_text("sleeper_id,adp,rank,std_dev,tier\n1,10.5,9,2.5,2\n")
            first = import_market_csv(
                csv_path,
                source="consensus",
                season=2026,
                scoring="ppr",
                team_count=10,
                observed_at="2026-08-01T12:00:00-04:00",
                storage_dir=directory,
                retrieved_at="2026-08-01T16:01:00Z",
            )
            self.assertEqual(
                first["snapshot_id"],
                import_market_csv(
                    csv_path,
                    source="consensus",
                    season=2026,
                    scoring="ppr",
                    team_count=10,
                    observed_at="2026-08-01T16:00:00Z",
                    storage_dir=directory,
                    retrieved_at="2026-08-02T00:00:00Z",
                )["snapshot_id"],
            )

            csv_path.write_text("sleeper_id,adp,rank\n1,8,7\n")
            second = import_market_csv(
                csv_path,
                source="consensus",
                season=2026,
                scoring="ppr",
                team_count=10,
                observed_at="2026-08-02T12:00:00Z",
                storage_dir=directory,
            )
            snapshot = load_market_snapshot_at(
                source="consensus",
                season=2026,
                scoring="ppr",
                team_count=10,
                at="2026-08-02T11:59:59Z",
                storage_dir=directory,
            )

            self.assertEqual(snapshot["snapshot_id"], first["snapshot_id"])
            self.assertEqual(snapshot["observations"][0]["canonical_player_id"], "sleeper:1")
            self.assertEqual(snapshot["observations"][0]["adp"], 10.5)
            self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
            self.assertEqual(Path(first["raw_snapshot_path"]).read_bytes(), b"sleeper_id,adp,rank,std_dev,tier\n1,10.5,9,2.5,2\n")
            self.assertIsNone(load_market_snapshot_at(
                source="consensus",
                season=2026,
                scoring="ppr",
                team_count=10,
                at="2026-08-02T11:59:59Z",
                max_age=timedelta(hours=12),
                storage_dir=directory,
            ))
            with sqlite3.connect(database_path) as database:
                self.assertEqual(database.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0], 2)

    def test_csv_import_rejects_unknown_players(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with sqlite3.connect(database_path) as database:
                database.executescript(SCHEMA)
            csv_path = Path(directory) / "market.csv"
            csv_path.write_text("sleeper_id,adp\nmissing,1\n")

            with self.assertRaisesRegex(ValueError, "Unknown sleeper_id missing"):
                import_market_csv(
                    csv_path,
                    source="consensus",
                    season=2026,
                    scoring="ppr",
                    observed_at="2026-08-01T12:00:00Z",
                    storage_dir=directory,
                )
