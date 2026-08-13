import json
import unittest
from pathlib import Path

from ffsim.draft_intel.state import reconcile_sleeper_draft, replay_sleeper_draft


class DraftStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / "fixtures" / "sleeper_draft_states.json"
        cls.fixtures = json.loads(fixture.read_text())

    def replay(self, name, **changes):
        data = {**self.fixtures[name], **changes}
        return replay_sleeper_draft(
            data["draft"],
            data["picks"],
            data["traded_picks"],
            data["player_ids"],
        )

    def test_snake_replay_tracks_trade_rosters_availability_and_turn_geometry(self):
        state = self.replay("snake")

        self.assertEqual(state.reversal_round, 3)
        self.assertEqual(state.pick_slots, (1, 2, 3, 3, 2, 1, 3, 2, 1))
        self.assertEqual(state.pick_owners, (101, 102, 103, 103, 102, 102, 103, 102, 101))
        self.assertEqual(state.current_pick_no, 5)
        self.assertEqual(state.current_roster_id, 102)
        self.assertEqual(state.roster_player_ids(103), ("p3", "p4"))
        self.assertEqual(state.roster_id_for_manager("manager-a"), 101)
        self.assertEqual(state.available_player_ids, frozenset({"p5", "p6", "p7", "p8", "p9"}))

        turn = state.turn_for(101)
        self.assertIsNone(turn.user_current_pick_no)
        self.assertEqual(turn.user_next_pick_no, 9)
        self.assertEqual(turn.future_user_pick_nos, (9,))
        self.assertEqual(turn.opponent_roster_ids_until_next, (102, 102, 103, 102))
        self.assertEqual(turn.opponent_pick_counts, ((102, 3), (103, 1)))
        self.assertEqual(turn.back_to_back_roster_ids, (102,))
        reordered = self.replay(
            "snake",
            picks=list(reversed(self.fixtures["snake"]["picks"])),
        )
        self.assertEqual(state, reordered)
        self.assertEqual(hash(state), hash(reordered))

        standard_draft = {
            **self.fixtures["snake"]["draft"],
            "settings": {"teams": 3, "rounds": 3, "reversal_round": 0},
        }
        standard = self.replay("snake", draft=standard_draft)
        self.assertEqual(standard.pick_slots, (1, 2, 3, 3, 2, 1, 1, 2, 3))

    def test_linear_replay_uses_the_same_direction_each_round(self):
        state = self.replay("linear")

        self.assertEqual(state.pick_owners, (201, 202, 201, 201, 201, 202))
        turn = state.turn_for(201)
        self.assertEqual(turn.user_current_pick_no, 3)
        self.assertEqual(turn.user_next_pick_no, 4)
        self.assertEqual(turn.future_user_pick_nos, (4, 5))

    def test_auction_replay_tracks_winners_and_budgets_without_inventing_future_owners(self):
        state = self.replay("auction")

        self.assertEqual(state.pick_owners, (301, 301, None, None))
        self.assertEqual(state.pick_slots, (1, 1, None, None))
        self.assertEqual(state.roster_player_ids(301), ("p1", "p2"))
        self.assertEqual(state.remaining_budgets, ((301, 95), (302, 200)))
        self.assertEqual(state.current_pick_no, 3)
        self.assertIsNone(state.current_roster_id)
        with self.assertRaisesRegex(ValueError, "not predetermined"):
            state.turn_for(301)

    def test_replay_fails_closed_on_conflicting_or_incomplete_source_state(self):
        fixture = self.fixtures["snake"]
        duplicate = {**fixture["picks"][1], "player_id": "different"}
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate pick"):
            self.replay("snake", picks=[*fixture["picks"], duplicate])
        with self.assertRaisesRegex(ValueError, "contiguous"):
            self.replay("snake", picks=[fixture["picks"][0], fixture["picks"][2]])
        with self.assertRaisesRegex(ValueError, "outside the redraft"):
            self.replay("snake", picks=[{**fixture["picks"][0], "is_keeper": True}])

    def test_reconciliation_only_appends_to_the_observed_pick_prefix(self):
        fixture = self.fixtures["snake"]
        previous = self.replay("snake", picks=fixture["picks"][:2])
        current = reconcile_sleeper_draft(
            previous,
            fixture["draft"],
            fixture["picks"],
            fixture["traded_picks"],
            fixture["player_ids"],
        )
        self.assertEqual(len(current.completed_picks), 4)

        rewritten = [{**fixture["picks"][0], "player_id": "p9"}, fixture["picks"][1]]
        with self.assertRaisesRegex(ValueError, "rewrote or removed"):
            reconcile_sleeper_draft(
                previous,
                fixture["draft"],
                rewritten,
                fixture["traded_picks"],
                fixture["player_ids"],
            )


if __name__ == "__main__":
    unittest.main()
