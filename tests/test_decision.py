from dataclasses import asdict
import json
import unittest

import numpy as np

from ffsim.draft_intel.decision import (
    coupled_world_indices,
    evaluate_candidates,
    merge_evaluations,
    recommendation_summary,
)
from ffsim.draft_intel.state import replay_sleeper_draft
from ffsim.models.league import League
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.simulation.world_bank import SeasonWorldBank


def draft_state():
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
        picks=(),
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
            survival_player_ids=("p2", "p3"),
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
        self.assertEqual(recommendation.decision_engine_version, 1)
        self.assertEqual(recommendation.draft_model_version, "manual-test-v1")
        self.assertIn("PAIRED_CHAMPIONSHIP_EDGE", recommendation.reason_codes)
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
            survival_player_ids=("p2", "p3"),
            tiers={"next": ("p2", "p3")},
        )
        self.assertEqual(result, cached)
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
            survival_player_ids=("p2", "p3"),
            tiers={"next": ("p2", "p3")},
            use_cache=False,
        )
        self.assertEqual(result, uncached)

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
