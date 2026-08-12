import json
import unittest
from pathlib import Path

from ffsim.draft_intel.history import load_history, summarize_history


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
            canonical_player_ids={"9509", "6803"},
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
        self.assertTrue(history.drafts[0].included)
        self.assertEqual(history.drafts[1].exclusion_reasons, ("auction",))

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
