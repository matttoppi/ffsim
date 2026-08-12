import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ffsim.draft_intel.history import load_history, summarize_history
from ffsim.draft_intel.identity import canonical_players_from_cache
from ffsim.draft_intel.storage import load_sleeper_identity_map, store_history


class DraftHistoryTest(unittest.TestCase):
    def test_shared_drafts_and_picks_are_fetched_and_counted_once(self):
        fixture = Path(__file__).parent / "fixtures" / "sleeper_history.json"
        responses = json.loads(fixture.read_text())
        calls = []

        def fetch(path):
            calls.append(path)
            return responses[path]

        history = load_history(
            "target",
            (2026, 2025),
            fetch,
            canonical_player_ids={
                "9509": "sleeper:9509",
                "6803": "sleeper:6803",
            },
        )
        summary = summarize_history(history, 2026)

        self.assertEqual([manager.user_id for manager in history.managers], ["u1", "u2"])
        self.assertEqual(history.draft_discoveries, 6)
        self.assertEqual(len(history.drafts), 5)
        self.assertEqual(len(history.picks), 5)
        self.assertEqual(history.drafts[0].manager_ids, ("u1", "u2"))
        self.assertEqual(calls.count("draft/a"), 1)
        self.assertEqual(calls.count("draft/a/picks"), 1)
        self.assertEqual(summary["duplicate_discoveries_removed"], 1)
        self.assertEqual(summary["shared_drafts"], 1)
        self.assertEqual(summary["keeper_picks"], 1)
        self.assertEqual(summary["model_eligible_picks"], 1)
        self.assertEqual(summary["draft_classification"], {
            "included": 1,
            "excluded": 4,
            "exclusion_reasons": {
                "auction": 1,
                "dynasty": 2,
                "non_snake": 1,
                "not_complete": 1,
            },
        })
        self.assertEqual(
            summary["canonical_player_coverage"]["all_picks"]["pick_match_rate"],
            0.4,
        )
        self.assertEqual(
            summary["canonical_player_coverage"]["model_eligible_picks"]["pick_match_rate"],
            1.0,
        )
        self.assertEqual(history.drafts[0].player_type, 0)
        self.assertIn(("super_flex", 1), history.drafts[0].roster_slots)
        self.assertEqual(history.drafts[0].draft_order, (("u1", 1), ("u2", 2)))
        self.assertEqual(history.drafts[0].slot_to_roster_id, ((1, 2), (2, 3)))
        self.assertTrue(history.drafts[0].included)
        self.assertEqual(history.drafts[1].exclusion_reasons, ("auction",))

    def test_persistence_is_idempotent_and_preserves_raw_source_ids(self):
        fixture = Path(__file__).parent / "fixtures" / "sleeper_history.json"
        responses = json.loads(fixture.read_text())
        canonical_players = canonical_players_from_cache([
            {
                "sleeper_id": "9509",
                "full_name": "Player One Jr.",
                "position": "RB",
                "team": "ARZ",
            },
            {
                "sleeper_id": "6803",
                "full_name": "Player Two",
                "position": "WR",
                "team": "PIT",
            },
        ])
        canonical_ids = {
            player.sleeper_id: player.canonical_player_id
            for player in canonical_players
        }
        captured = {}
        history = load_history(
            "target",
            (2026, 2025),
            responses.__getitem__,
            canonical_player_ids=canonical_ids,
            raw_responses=captured,
        )

        with tempfile.TemporaryDirectory() as directory:
            first = store_history(
                history,
                captured,
                canonical_players,
                storage_dir=directory,
                observed_at="2026-08-12T12:00:00+00:00",
            )
            with closing(sqlite3.connect(first["database_path"])) as database, database:
                database.execute(
                    "INSERT INTO managers VALUES (?, ?, ?, ?)",
                    ("other-target", "Other", "earlier", "earlier"),
                )
                database.execute(
                    "INSERT INTO historical_draft_managers VALUES (?, ?, ?, ?)",
                    ("a", "other-target", 3, 4),
                )
            second = store_history(
                history,
                captured,
                canonical_players[:1],
                storage_dir=directory,
                observed_at="2026-08-12T13:00:00+00:00",
            )

            self.assertEqual(first["raw_snapshot_hash"], second["raw_snapshot_hash"])
            raw = json.loads(Path(first["raw_snapshot_path"]).read_text())
            self.assertEqual(
                raw["responses"]["draft/a/picks"][1]["player_id"],
                "retired-player",
            )
            with closing(sqlite3.connect(first["database_path"])) as database:
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM historical_drafts").fetchone()[0],
                    5,
                )
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM historical_picks").fetchone()[0],
                    5,
                )
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM canonical_players").fetchone()[0],
                    2,
                )
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM player_external_ids").fetchone()[0],
                    2,
                )
                self.assertEqual(
                    database.execute(
                        "SELECT COUNT(*) FROM historical_draft_managers WHERE draft_id = 'a'"
                    ).fetchone()[0],
                    3,
                )
                self.assertEqual(
                    database.execute(
                        """
                        SELECT source_player_id, canonical_player_id
                        FROM historical_picks
                        WHERE source_player_id = 'retired-player'
                        """
                    ).fetchone(),
                    ("retired-player", None),
                )
                self.assertEqual(
                    database.execute(
                        """
                        SELECT draft_slot, roster_id
                        FROM historical_draft_managers
                        WHERE draft_id = 'a' AND manager_id = 'u1'
                        """
                    ).fetchone(),
                    (1, 2),
                )
                self.assertEqual(
                    database.execute(
                        """
                        SELECT normalized_name, nfl_team, active
                        FROM canonical_players
                        WHERE canonical_player_id = 'sleeper:9509'
                        """
                    ).fetchone(),
                    ("playerone", "ARI", 0),
                )
            self.assertEqual(
                load_sleeper_identity_map(directory),
                {"9509": "sleeper:9509", "6803": "sleeper:6803"},
            )

    def test_conflicting_cached_player_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Conflicting cached players"):
            canonical_players_from_cache([
                {"sleeper_id": "1", "full_name": "One", "position": "WR"},
                {"sleeper_id": "1", "full_name": "Other", "position": "WR"},
            ])

    def test_conflicting_duplicate_pick_fails_closed(self):
        draft = {
            "draft_id": "a", "season": "2026", "status": "complete", "type": "snake",
        }
        pick = {"draft_id": "a", "pick_no": 1, "player_id": "1"}
        responses = {
            "league/target/users": [{"user_id": "u1"}],
            "user/u1/drafts/nfl/2026": [draft],
            "draft/a": draft,
            "draft/a/picks": [pick, {**pick, "player_id": "2"}],
        }

        with self.assertRaisesRegex(ValueError, "Conflicting duplicate Sleeper pick a/1"):
            load_history("target", (2026,), responses.__getitem__)


if __name__ == "__main__":
    unittest.main()
