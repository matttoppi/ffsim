import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ffsim.draft_intel.market import (
    fantasypros_market_status,
    import_market_csv,
    load_market_snapshot_at,
    refresh_fantasypros_adp,
)
from ffsim.draft_intel.storage import SCHEMA


class MarketSnapshotTest(unittest.TestCase):
    def test_fantasypros_refresh_fetches_only_stale_contexts_and_stores_platform_adp(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with closing(sqlite3.connect(database_path)) as database, database:
                database.executescript(SCHEMA)
                for player_id, name, position, team in (
                    ("1", "One", "WR", "ARI"),
                    ("ARI", "Arizona Cardinals", "DEF", "ARI"),
                ):
                    canonical_id = f"sleeper:{player_id}"
                    database.execute(
                        "INSERT INTO canonical_players VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (canonical_id, name, name.lower(), position, team, 1, "now"),
                    )
                    database.execute(
                        "INSERT INTO player_external_ids VALUES (?, ?, ?, ?, ?, ?)",
                        (canonical_id, "sleeper", player_id, "now", "now", 1.0),
                    )

            sleeper_path = Path(directory) / "sleeper_players.json"
            sleeper_path.write_text(json.dumps({
                "1": {"player_id": "1", "position": "WR", "sportradar_id": "sr-1"},
                "inactive-duplicate": {
                    "player_id": "inactive-duplicate",
                    "position": "WR",
                    "sportradar_id": "sr-1",
                },
                "ARI": {"player_id": "ARI", "position": "DEF", "team": "ARI"},
            }))
            payload = json.dumps({
                "tier": "premium",
                "limit": None,
                "count": 3,
                "year": 2026,
                "scoring": "PPR",
                "position_id": "ALL",
                "last_updated_ts": 1786543200,
                "players": [
                    {
                        "player_id": 101,
                        "player_name": "One",
                        "player_position_id": "WR",
                        "sportsdata_id": "sr-1",
                        "rank_ave": "10.5",
                        "rank_ecr": 9,
                        "rank_std": "2.5",
                        "tier": 2,
                        "experts": {"79": "11", "4350": "9"},
                    },
                    {
                        "player_id": 102,
                        "player_name": "Arizona Cardinals",
                        "player_position_id": "DST",
                        "player_team_id": "ARI",
                        "rank_ave": "150",
                        "rank_ecr": 151,
                        "experts": {"4350": "145"},
                    },
                    {
                        "player_id": 103,
                        "player_name": "Unmapped",
                        "player_position_id": "WR",
                        "rank_ave": "500",
                        "rank_ecr": 500,
                        "experts": {},
                    },
                ],
            }, separators=(",", ":")).encode()
            calls = []

            def fetch_payload(**request):
                calls.append(request)
                return payload

            context = (("1qb", "PPR", "ALL"),)
            first_at = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
            first = refresh_fantasypros_adp(
                season=2026,
                storage_dir=directory,
                sleeper_players_path=sleeper_path,
                contexts=context,
                now=first_at,
                fetch_payload=fetch_payload,
                api_key="test",
            )
            fresh = refresh_fantasypros_adp(
                season=2026,
                storage_dir=directory,
                sleeper_players_path=sleeper_path,
                contexts=context,
                now=first_at + timedelta(hours=11),
                fetch_payload=fetch_payload,
            )
            stale = refresh_fantasypros_adp(
                season=2026,
                storage_dir=directory,
                sleeper_players_path=sleeper_path,
                contexts=context,
                now=first_at + timedelta(hours=12),
                fetch_payload=fetch_payload,
                api_key="test",
            )

            self.assertEqual(len(calls), 2)
            self.assertEqual(first["fetched_contexts"][0]["mapped_player_count"], 2)
            self.assertEqual(
                first["fetched_contexts"][0]["unmatched_players"][0]["name"],
                "Unmapped",
            )
            self.assertEqual(fresh["fetched_contexts"], [])
            self.assertEqual(len(stale["fetched_contexts"]), 1)
            self.assertTrue(fantasypros_market_status(
                season=2026,
                storage_dir=directory,
                contexts=context,
                now=first_at + timedelta(hours=12),
            )["fresh"])
            with closing(sqlite3.connect(database_path)) as database:
                sources = database.execute(
                    "SELECT source, COUNT(*) FROM market_snapshots GROUP BY source ORDER BY source"
                ).fetchall()
                self.assertEqual(sources, [
                    ("fantasypros:consensus", 2),
                    ("fantasypros:espn", 2),
                    ("fantasypros:sleeper", 2),
                ])
                sleeper_adp = database.execute(
                    """
                    SELECT adp FROM market_observations o
                    JOIN market_snapshots s USING (snapshot_id)
                    WHERE s.source = 'fantasypros:sleeper'
                      AND o.canonical_player_id = 'sleeper:1'
                    ORDER BY s.retrieved_at DESC LIMIT 1
                    """
                ).fetchone()[0]
                self.assertEqual(sleeper_adp, 9.0)

            unsupported = json.dumps({
                "tier": "premium",
                "limit": None,
                "count": 0,
                "year": "2026",
                "scoring": "PPR",
                "position_id": "OP",
                "players": [],
            }, separators=(",", ":")).encode()
            with self.assertRaisesRegex(ValueError, "missing last_updated_ts"):
                refresh_fantasypros_adp(
                    season=2026,
                    storage_dir=directory,
                    sleeper_players_path=sleeper_path,
                    contexts=(("superflex", "PPR", "OP"),),
                    now=first_at,
                    fetch_payload=lambda **_: unsupported,
                    api_key="test",
                )
            raw_path = (
                Path(directory) / "raw" /
                f"fantasypros-{hashlib.sha256(unsupported).hexdigest()}.json"
            )
            self.assertEqual(raw_path.read_bytes(), unsupported)
            self.assertFalse(fantasypros_market_status(
                season=2026,
                storage_dir=directory,
                contexts=(("superflex", "PPR", "OP"),),
                now=first_at,
            )["fresh"])

    def test_csv_import_is_append_only_and_reconstructs_historical_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with closing(sqlite3.connect(database_path)) as database, database:
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
            with closing(sqlite3.connect(database_path)) as database, database:
                self.assertEqual(database.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0], 2)

    def test_csv_import_rejects_unknown_players(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with closing(sqlite3.connect(database_path)) as database, database:
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
