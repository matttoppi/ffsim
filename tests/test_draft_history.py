import unittest

from ffsim.draft_intel.history import load_history, summarize_history


class DraftHistoryTest(unittest.TestCase):
    def test_shared_drafts_and_picks_are_fetched_and_counted_once(self):
        draft_a = {
            "draft_id": "a", "league_id": "la", "season": "2026",
            "status": "complete", "type": "snake", "start_time": 10,
            "settings": {"teams": 10, "rounds": 16},
            "metadata": {"scoring_type": "ppr"},
        }
        draft_b = {
            "draft_id": "b", "league_id": "lb", "season": "2025",
            "status": "complete", "type": "linear", "start_time": 20,
            "settings": {"teams": 12, "rounds": 4},
            "metadata": {"scoring_type": "dynasty_2qb"},
        }
        pick_a = {
            "draft_id": "a", "pick_no": 1, "round": 1, "draft_slot": 1,
            "roster_id": 2, "picked_by": "u1", "player_id": "9509",
            "is_keeper": None, "metadata": {"position": "RB"},
        }
        pick_b = {
            "draft_id": "b", "pick_no": 1, "round": 1, "draft_slot": 1,
            "roster_id": 4, "picked_by": "u2", "player_id": "6803",
            "is_keeper": True, "metadata": {"position": "WR"},
        }
        responses = {
            "league/target/users": [
                {"user_id": "u2", "display_name": "Two"},
                {"user_id": "u1", "display_name": "One"},
            ],
            "user/u1/drafts/nfl/2026": [draft_a],
            "user/u1/drafts/nfl/2025": [],
            "user/u2/drafts/nfl/2026": [draft_a],
            "user/u2/drafts/nfl/2025": [draft_b],
            "draft/a": draft_a,
            "draft/a/picks": [pick_a, pick_a],
            "draft/b": draft_b,
            "draft/b/picks": [pick_b],
        }
        calls = []

        def fetch(path):
            calls.append(path)
            return responses[path]

        history = load_history("target", (2026, 2025), fetch)
        summary = summarize_history(history, 2026)

        self.assertEqual([manager.user_id for manager in history.managers], ["u1", "u2"])
        self.assertEqual(history.draft_discoveries, 3)
        self.assertEqual(len(history.drafts), 2)
        self.assertEqual(len(history.picks), 2)
        self.assertEqual(history.drafts[0].manager_ids, ("u1", "u2"))
        self.assertEqual(calls.count("draft/a"), 1)
        self.assertEqual(calls.count("draft/a/picks"), 1)
        self.assertEqual(summary["duplicate_discoveries_removed"], 1)
        self.assertEqual(summary["shared_drafts"], 1)
        self.assertEqual(summary["keeper_picks"], 1)

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
