from collections import Counter
from dataclasses import asdict
from dataclasses import replace
import json
import unittest

import numpy as np

from ffsim.draft_intel.decision import (
    coupled_world_indices,
    evaluate_candidates,
    evaluate_completed_league,
    evaluate_league_equity,
    merge_evaluations,
    merge_rollout_ranges,
    recommendation_summary,
)
from ffsim.draft_intel.state import replay_sleeper_draft
from ffsim.models.league import League
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.simulation.world_bank import SeasonWorldBank


def draft_state(picks=()):
    draft = {
        "draft_id": "nested-offline",
        "type": "snake",
        "status": "drafting",
        "settings": {"teams": 4, "rounds": 2, "reversal_round": 0},
        "draft_order": {str(roster): roster for roster in range(1, 5)},
        "slot_to_roster_id": {str(roster): roster for roster in range(1, 5)},
    }
    return replay_sleeper_draft(
        draft,
        picks=picks,
        traded_picks=(),
        player_ids=(f"p{index}" for index in range(1, 13)),
    )


def evaluator():
    player_ids = tuple(f"p{index}" for index in range(1, 13))
    expected = np.asarray([110 - index * 10 for index in range(1, 13)], dtype=float)
    scores = np.repeat(expected[None, :, None], 5, axis=0)
    scores = np.repeat(scores, 3, axis=2).astype(np.float32)
    scores.flags.writeable = False
    available = np.ones_like(scores, dtype=bool)
    available.flags.writeable = False
    expected.flags.writeable = False
    world_bank = SeasonWorldBank(
        version="nested-bank-v1",
        seed=1,
        player_ids=player_ids,
        player_positions=("WR",) * len(player_ids),
        expected_scores=expected,
        weeks=(1, 2, 3),
        input_hash="nested-inputs-v1",
        scores=scores,
        available=available,
    )
    subject = League({
        "league_id": "nested-league",
        "roster_positions": ["WR"],
        "settings": {
            "playoff_teams": 4,
            "playoff_round_type": 0,
            "playoff_seed_type": 0,
        },
    })
    return LeagueEvaluator(subject, world_bank, range(1, 5), 1, seed=31)


def market_utility(roster_id, pick_no, rosters, available):
    return {player_id: -100 * int(player_id[1:]) for player_id in available}


class DecisionEvaluationTest(unittest.TestCase):
    def test_completed_league_uses_exact_rosters_and_every_season_world(self):
        state = draft_state()
        for player_id in (f"p{index}" for index in range(1, 9)):
            state = state.with_pick(player_id)
        league_evaluator = evaluator()

        result = evaluate_completed_league(state, league_evaluator)

        self.assertIsNone(result.state_pick_no)
        self.assertEqual(result.completed_picks, 8)
        self.assertEqual(result.rollout_count, 1)
        self.assertEqual(result.season_worlds_per_rollout, 5)
        self.assertEqual(result.joint_outcome_count, 5)
        self.assertAlmostEqual(
            sum(row.championship_probability for row in result.rosters),
            1.0,
        )
        self.assertEqual(
            result,
            evaluate_completed_league(state, league_evaluator, use_cache=False),
        )
        with self.assertRaisesRegex(ValueError, "not complete"):
            evaluate_completed_league(draft_state(), league_evaluator)

    def test_league_equity_scores_every_roster_without_forcing_a_root_pick(self):
        state = draft_state()
        league_evaluator = evaluator()
        result = evaluate_league_equity(
            state,
            1,
            range(8),
            market_utility,
            market_utility,
            league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
        )

        self.assertEqual(result.completed_picks, 0)
        self.assertEqual(result.state_pick_no, 1)
        self.assertEqual(result.rollout_count, 8)
        self.assertEqual(result.joint_outcome_count, 24)
        self.assertEqual({row.roster_id for row in result.rosters}, {1, 2, 3, 4})
        self.assertAlmostEqual(
            sum(row.championship_probability for row in result.rosters),
            1.0,
        )
        self.assertEqual(result, evaluate_league_equity(
            state,
            1,
            range(8),
            market_utility,
            market_utility,
            league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
            use_cache=False,
        ))

    def test_merged_candidate_batches_equal_one_combined_evaluation(self):
        league_evaluator = evaluator()
        kwargs = dict(
            user_roster_id=1,
            rollout_ids=range(8),
            opponent_choice=market_utility,
            user_policy=market_utility,
            league_evaluator=league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
        )
        combined = evaluate_candidates(draft_state(), ("p1", "p2", "p3"), **kwargs)
        merged = merge_evaluations([
            evaluate_candidates(draft_state(), ("p1", "p2"), **kwargs),
            evaluate_candidates(draft_state(), ("p3",), **kwargs),
        ])
        self.assertEqual(merged, combined)
        self.assertEqual(
            recommendation_summary(merged),
            recommendation_summary(combined),
        )
        with self.assertRaisesRegex(ValueError, "different states or model inputs"):
            merge_evaluations([
                combined,
                evaluate_candidates(draft_state(), ("p4",), **{**kwargs, "seed": 20}),
            ])
        with self.assertRaisesRegex(ValueError, "duplicate candidates"):
            merge_evaluations([combined, combined])

    def test_merged_rollout_ranges_equal_one_full_range_evaluation(self):
        league_evaluator = evaluator()
        kwargs = dict(
            user_roster_id=1,
            opponent_choice=market_utility,
            user_policy=market_utility,
            league_evaluator=league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
            survival_player_ids=("p1", "p2", "p3"),
            tiers={"next": ("p2", "p3")},
        )
        candidates = ("p1", "p2")
        flat = evaluate_candidates(
            draft_state(), candidates, rollout_ids=range(12), **kwargs
        )
        merged = merge_rollout_ranges([
            evaluate_candidates(
                draft_state(), candidates, rollout_ids=range(5), **kwargs
            ),
            evaluate_candidates(
                draft_state(), candidates, rollout_ids=range(5, 12), **kwargs
            ),
        ])
        self.assertEqual(merged, flat)
        self.assertEqual(
            recommendation_summary(merged),
            recommendation_summary(flat),
        )
        with self.assertRaisesRegex(ValueError, "overlapping rollout ranges"):
            merge_rollout_ranges([flat, flat])
        with self.assertRaisesRegex(ValueError, "different states or candidates"):
            merge_rollout_ranges([
                flat,
                evaluate_candidates(
                    draft_state(), ("p1", "p3"), rollout_ids=range(12, 14), **kwargs
                ),
            ])

    def test_candidates_use_many_paired_draft_paths_and_selected_season_worlds(self):
        league_evaluator = evaluator()
        result = evaluate_candidates(
            draft_state(),
            ("p2", "p1"),
            user_roster_id=1,
            rollout_ids=range(20),
            opponent_choice=market_utility,
            user_policy=market_utility,
            league_evaluator=league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
            survival_player_ids=("p1", "p2", "p3"),
            tiers={"next": ("p2", "p3")},
        )

        best = result.candidate("p1")
        alternative = result.candidate("p2")
        self.assertEqual(result.rollout_ids, tuple(range(20)))
        self.assertEqual(len(result.world_indices), 20)
        self.assertTrue(all(len(set(worlds)) == 3 for worlds in result.world_indices))
        self.assertTrue(
            {world for worlds in result.world_indices for world in worlds}
            <= set(range(5))
        )
        self.assertEqual(
            set(Counter(
                world for worlds in result.world_indices for world in worlds
            ).values()),
            {12},
        )
        self.assertEqual(best.sample_count, 60)
        self.assertEqual(best.rollout_count, 20)
        self.assertEqual(best.championship_probability, 1)
        self.assertEqual(alternative.championship_probability, 0)
        self.assertEqual(best.playoff_probability, 1)
        self.assertTrue(all(value <= 0 for value in best.continuation_log_probabilities))
        self.assertEqual(best.survival.rollout_count, 20)

        delta = result.paired_delta("p1", "p2")
        self.assertEqual(delta.championship_probability_delta, 1)
        self.assertEqual(delta.standard_error, 0)
        self.assertEqual(delta.better_outcome_probability, 1)

        recommendation = recommendation_summary(result)
        self.assertEqual(recommendation.recommended_candidate_id, "p1")
        self.assertEqual(recommendation.runner_up_candidate_id, "p2")
        self.assertEqual(recommendation.joint_outcome_count, 60)
        self.assertEqual(recommendation.season_worlds_per_rollout, 3)
        self.assertEqual(recommendation.decision_engine_version, 5)
        self.assertEqual(recommendation.draft_model_version, "manual-test-v1")
        self.assertEqual(recommendation.decision_status, "clear_leader")
        self.assertEqual(recommendation.co_leader_candidate_ids, ("p1",))
        self.assertEqual(
            tuple(player.player_id for player in recommendation.availability.players),
            ("p1",),
        )
        self.assertIn("PAIRED_VALUE_EDGE", recommendation.reason_codes)
        json.dumps(asdict(recommendation))

        cached = evaluate_candidates(
            draft_state(),
            ("p1", "p2"),
            1,
            range(20),
            market_utility,
            market_utility,
            league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
            survival_player_ids=("p1", "p2", "p3"),
            tiers={"next": ("p2", "p3")},
        )
        self.assertEqual(result, cached)
        self.assertEqual(
            recommendation.run_signature,
            recommendation_summary(cached).run_signature,
        )
        self.assertGreater(league_evaluator.cache_hits, 0)

        uncached = evaluate_candidates(
            draft_state(),
            ("p1", "p2"),
            1,
            range(20),
            market_utility,
            market_utility,
            league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
            survival_player_ids=("p1", "p2", "p3"),
            tiers={"next": ("p2", "p3")},
            use_cache=False,
        )
        self.assertEqual(result, uncached)

    def test_statistically_tied_candidates_form_one_top_tier(self):
        evaluation = evaluate_candidates(
            draft_state(),
            ("p1", "p2"),
            1,
            range(20),
            market_utility,
            market_utility,
            evaluator(),
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
        )
        leader = evaluation.candidate("p1")
        tied = replace(
            evaluation.candidate("p2"),
            projected_roster_value=leader.projected_roster_value,
            continuation_roster_values=leader.continuation_roster_values,
            championship_probability=leader.championship_probability,
            championship_outcomes=leader.championship_outcomes,
            continuation_championship_probabilities=(
                leader.continuation_championship_probabilities
            ),
        )

        recommendation = recommendation_summary(
            replace(evaluation, candidates=(leader, tied))
        )

        self.assertEqual(recommendation.decision_status, "toss_up")
        self.assertEqual(recommendation.co_leader_candidate_ids, ("p1", "p2"))
        self.assertIn("LOW_CONFIDENCE_TOSS_UP", recommendation.reason_codes)
        self.assertNotIn("PAIRED_VALUE_EDGE", recommendation.reason_codes)

    def test_toss_up_keeps_the_projected_value_leader_as_the_headline(self):
        def opponents(roster_id, pick_no, rosters, available):
            utilities = {
                player_id: -100.0 * int(player_id[1:]) for player_id in available
            }
            # Opponents hunt p2 and never want p1, so p2 is the scarce
            # co-leader while p1 always returns at the next pick.
            if "p1" in utilities:
                utilities["p1"] = -100000.0
            if "p2" in utilities:
                utilities["p2"] = 100000.0
            return utilities

        evaluation = evaluate_candidates(
            draft_state(),
            ("p1", "p2"),
            1,
            range(20),
            opponents,
            market_utility,
            evaluator(),
            draft_model_version="manual-test-v1",
            seed=19,
            season_worlds_per_rollout=3,
            survival_player_ids=("p1", "p2"),
        )
        leader = evaluation.candidate("p1")
        tied = replace(
            evaluation.candidate("p2"),
            projected_roster_value=leader.projected_roster_value,
            continuation_roster_values=leader.continuation_roster_values,
            championship_probability=leader.championship_probability,
            playoff_probability=leader.playoff_probability,
            expected_wins=leader.expected_wins,
            expected_points=leader.expected_points,
            championship_outcomes=leader.championship_outcomes,
            continuation_championship_probabilities=(
                leader.continuation_championship_probabilities
            ),
        )

        recommendation = recommendation_summary(
            replace(evaluation, candidates=(leader, tied))
        )

        self.assertEqual(recommendation.decision_status, "toss_up")
        self.assertEqual(recommendation.recommended_candidate_id, "p1")
        self.assertEqual(recommendation.runner_up_candidate_id, "p2")
        self.assertEqual(recommendation.co_leader_candidate_ids, ("p1", "p2"))
        self.assertNotIn("SCARCITY_TIEBREAK", recommendation.reason_codes)
        self.assertIn("PROJECTED_VALUE_LEADER", recommendation.reason_codes)
        self.assertIn("LOW_CONFIDENCE_TOSS_UP", recommendation.reason_codes)

    def test_final_pick_evaluations_skip_next_pick_survival(self):
        picks = tuple(
            {
                "draft_id": "nested-offline",
                "pick_no": pick_no,
                "round": (pick_no - 1) // 4 + 1,
                "draft_slot": slot,
                "roster_id": slot,
                "player_id": f"p{pick_no}",
            }
            for pick_no, slot in enumerate((1, 2, 3, 4, 4, 3, 2), start=1)
        )
        evaluation = evaluate_candidates(
            draft_state(picks),
            ("p8", "p9"),
            1,
            range(4),
            market_utility,
            market_utility,
            evaluator(),
            draft_model_version="manual-test-v1",
            seed=19,
            survival_player_ids=("p8", "p9"),
        )

        self.assertIsNone(evaluation.next_user_pick_no)
        self.assertTrue(
            all(candidate.survival is None for candidate in evaluation.candidates)
        )
        self.assertIsNone(recommendation_summary(evaluation).availability)

    def test_nested_evaluation_rejects_one_draft_continuation(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            evaluate_candidates(
                draft_state(),
                ("p1", "p2"),
                1,
                (0,),
                market_utility,
                market_utility,
                evaluator(),
                draft_model_version="manual-test-v1",
            )
        with self.assertRaisesRegex(ValueError, "exceeds"):
            coupled_world_indices(1, 1, 5, 6)


if __name__ == "__main__":
    unittest.main()
