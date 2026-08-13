import copy
import tempfile
import unittest
from pathlib import Path

from ffsim.draft_intel.mock import attach_mock_draft, refresh_attached_mock


class StandaloneMockTest(unittest.TestCase):
    def test_attach_refresh_and_reconcile_standalone_mock(self):
        draft = {
            "draft_id": "mock",
            "league_id": None,
            "sport": "nfl",
            "status": "pre_draft",
            "type": "snake",
            "season": "2026",
            "settings": {
                "teams": 2,
                "rounds": 2,
                "slots_qb": 1,
                "slots_wr": 1,
            },
            "metadata": {"scoring_type": "std"},
            "creators": ["user"],
            "draft_order": None,
            "slot_to_roster_id": {"1": 1, "2": 2},
        }
        responses = {
            "draft/mock": draft,
            "draft/mock/picks": [],
            "draft/mock/traded_picks": [],
        }

        def fetch(path):
            return copy.deepcopy(responses[path])

        with tempfile.TemporaryDirectory() as directory:
            first = attach_mock_draft(
                "mock",
                fetch_json=fetch,
                cache_dir=directory,
                player_ids=("p1", "p2", "p3", "p4"),
            )
            self.assertEqual(first["status"], "pre_draft")
            self.assertIsNone(first["user_roster_id"])
            self.assertEqual(first["market_context"]["status"], "exact")
            self.assertEqual(first["market_context"]["scoring"], "STD")

            responses["draft/mock"]["status"] = "drafting"
            responses["draft/mock"]["draft_order"] = {"user": 2}
            responses["draft/mock/picks"] = [{
                "draft_id": "mock",
                "pick_no": 1,
                "round": 1,
                "draft_slot": 1,
                "roster_id": 1,
                "picked_by": "cpu",
                "player_id": "p1",
                "metadata": {"position": "WR"},
            }]
            refreshed = refresh_attached_mock(
                fetch_json=fetch,
                cache_dir=directory,
                player_ids=("p1", "p2", "p3", "p4"),
            )
            self.assertEqual(refreshed["completed_picks"], 1)
            self.assertEqual(refreshed["user_roster_id"], 2)

            cache_path = Path(refreshed["cache_path"])
            before = cache_path.read_bytes()
            responses["draft/mock/picks"][0]["player_id"] = "p2"
            with self.assertRaisesRegex(ValueError, "rewrote or removed"):
                refresh_attached_mock(
                    fetch_json=fetch,
                    cache_dir=directory,
                    player_ids=("p1", "p2", "p3", "p4"),
                )
            self.assertEqual(cache_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
