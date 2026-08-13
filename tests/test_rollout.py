import math
import unittest

from ffsim.draft_intel.rollout import (
    choice_probabilities,
    complete_drafts,
    stable_gumbel,
    summarize_survival,
)
from ffsim.draft_intel.state import replay_sleeper_draft


def draft_state():
    draft = {
        "draft_id": "offline-rollout",
        "type": "snake",
        "status": "drafting",
        "settings": {"teams": 3, "rounds": 3, "reversal_round": 0},
        "draft_order": {"a": 1, "b": 2, "c": 3},
        "slot_to_roster_id": {"1": 101, "2": 102, "3": 103},
    }
    return replay_sleeper_draft(
        draft,
        picks=(),
        traded_picks=(),
        player_ids=(f"p{index}" for index in range(1, 13)),
    )


def equal_utilities(roster_id, pick_no, rosters, available):
    return {player_id: 0.0 for player_id in available}


class DraftRolloutTest(unittest.TestCase):
    def test_choice_distribution_is_normalized_and_stable(self):
        probabilities = dict(choice_probabilities({"p1": 2, "p2": 1, "p3": -1}))

        self.assertAlmostEqual(sum(probabilities.values()), 1.0)
        self.assertGreater(probabilities["p1"], probabilities["p2"])
        self.assertEqual(
            stable_gumbel(7, 3, 11, 102, "p1"),
            stable_gumbel(7, 3, 11, 102, "p1"),
        )
        self.assertNotEqual(
            stable_gumbel(7, 3, 11, 102, "p1"),
            stable_gumbel(7, 3, 11, 102, "p2"),
        )
        self.assertTrue(math.isfinite(stable_gumbel(7, 3, 11, 102, "p1")))
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            choice_probabilities({"p1": 1}, temperature=0)

        state = replay_sleeper_draft(
            {
                "draft_id": "choice-frequency",
                "type": "linear",
                "status": "drafting",
                "settings": {"teams": 2, "rounds": 1, "reversal_round": 0},
                "draft_order": {"a": 1, "b": 2},
                "slot_to_roster_id": {"1": 1, "2": 2},
            },
            (),
            (),
            ("root", "p1", "p2"),
        )

        def weighted_choice(roster_id, pick_no, rosters, available):
            return {"p1": 1.0, "p2": 0.0}

        completions = complete_drafts(
            state,
            "root",
            1,
            range(2000),
            weighted_choice,
            weighted_choice,
            seed=4,
        )
        observed = sum(
            completion.picks[-1].player_id == "p1" for completion in completions
        ) / 2000
        expected = dict(choice_probabilities({"p1": 1, "p2": 0}))["p1"]
        self.assertAlmostEqual(observed, expected, delta=0.03)

    def test_completions_are_sequential_coupled_and_require_many_rollouts(self):
        state = draft_state()

        def opponent_choice(roster_id, pick_no, rosters, available):
            roster = dict(rosters)[roster_id]
            if roster_id == 103 and pick_no == 4:
                self.assertEqual(len(roster), 1)
            return {player_id: 0.0 for player_id in available}

        def user_policy(roster_id, pick_no, rosters, available):
            if pick_no == 6:
                self.assertIn("p1", dict(rosters)[roster_id])
            return {player_id: -int(player_id[1:]) for player_id in available}

        first = complete_drafts(
            state,
            "p1",
            101,
            range(12),
            opponent_choice,
            user_policy,
            seed=9,
        )
        second = complete_drafts(
            state,
            "p1",
            101,
            range(12),
            opponent_choice,
            user_policy,
            seed=9,
        )

        self.assertEqual(first, second)
        self.assertEqual(len({completion.picks for completion in first}), 12)
        expected_first_opponent_pick = max(
            sorted(state.available_player_ids - {"p1"}),
            key=lambda player_id: stable_gumbel(9, 0, 2, 102, player_id),
        )
        self.assertEqual(first[0].picks[1].player_id, expected_first_opponent_pick)
        for completion in first:
            selected = [player for _, roster in completion.rosters for player in roster]
            self.assertEqual(tuple(len(roster) for _, roster in completion.rosters), (3, 3, 3))
            self.assertEqual(len(selected), len(set(selected)))
            self.assertTrue(math.isfinite(completion.opponent_log_probability))
            self.assertLessEqual(completion.opponent_log_probability, 0)

        alternate = complete_drafts(
            state,
            "p2",
            101,
            range(12),
            equal_utilities,
            equal_utilities,
            seed=9,
        )
        for original, counterfactual in zip(first, alternate):
            original_pick = original.picks[1].player_id
            counterfactual_pick = counterfactual.picks[1].player_id
            if original_pick != counterfactual_pick:
                self.assertTrue(original_pick == "p2" or counterfactual_pick == "p1")
        with self.assertRaisesRegex(ValueError, "at least two"):
            complete_drafts(
                state,
                "p1",
                101,
                [0],
                opponent_choice,
                user_policy,
            )

    def test_survival_hazards_threats_and_tier_counts_match_rollouts(self):
        completions = complete_drafts(
            draft_state(),
            "p1",
            101,
            range(100),
            equal_utilities,
            equal_utilities,
            seed=17,
        )

        report = summarize_survival(
            completions,
            player_ids=("p2", "p3"),
            tiers={"top": ("p2", "p3", "p4")},
        )

        p2 = dict((player.player_id, player) for player in report.players)["p2"]
        expected_survival = sum(
            not any(pick.player_id == "p2" and pick.pick_no < 6 for pick in completion.picks)
            for completion in completions
        ) / len(completions)
        self.assertEqual(p2.survives_to_next_pick, expected_survival)
        self.assertLessEqual(sum(probability for _, probability in p2.pick_hazard), 1)
        if p2.threat_share:
            self.assertAlmostEqual(sum(probability for _, probability in p2.threat_share), 1)

        tier = report.tiers[0]
        self.assertAlmostEqual(
            sum(probability for _, probability in tier.remaining_count_probabilities),
            1,
        )
        self.assertEqual(tier.survives_to_next_pick, 1 - tier.exhaustion_probability)
        self.assertAlmostEqual(
            tier.expected_remaining,
            sum(
                remaining * probability
                for remaining, probability in tier.remaining_count_probabilities
            ),
        )


if __name__ == "__main__":
    unittest.main()
