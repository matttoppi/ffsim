"""Deterministic roster-value scorer and projected-value objective tests."""

from dataclasses import replace
import unittest

import numpy as np

from ffsim.draft_intel.decision import (
    evaluate_candidates,
    rank_candidates,
    recommendation_summary,
)
from ffsim.draft_intel.state import replay_sleeper_draft
from ffsim.models.league import League
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.simulation.world_bank import SeasonWorldBank
from tests.test_decision import draft_state, evaluator, market_utility


WEEKS = (1, 2, 3)


def mixed_evaluator(roster_positions, players):
    """Four-team evaluator over (player_id, position, weekly_mean) rows."""
    players = tuple(players)
    player_ids = tuple(player_id for player_id, _, _ in players)
    positions = tuple(position for _, position, _ in players)
    expected = np.asarray([score for _, _, score in players], dtype=float)
    scores = np.repeat(expected[None, :, None], 2, axis=0)
    scores = np.repeat(scores, len(WEEKS), axis=2).astype(np.float32)
    available = np.ones_like(scores, dtype=bool)
    for array in (scores, available, expected):
        array.flags.writeable = False
    bank = SeasonWorldBank(
        version="mixed-bank-v1",
        seed=1,
        player_ids=player_ids,
        player_positions=positions,
        expected_scores=expected,
        weeks=WEEKS,
        input_hash="mixed-inputs-v1",
        scores=scores,
        available=available,
    )
    league = League({
        "league_id": "mixed-league",
        "roster_positions": list(roster_positions),
        "settings": {
            "playoff_teams": 4,
            "playoff_round_type": 0,
            "playoff_seed_type": 0,
        },
    })
    return LeagueEvaluator(league, bank, range(1, 5), 1, seed=31)


def mixed_players():
    return [
        ("qb1", "QB", 30.0),
        ("qb2", "QB", 28.0),
        ("rb1", "RB", 20.0),
        ("rb2", "RB", 18.0),
        ("rb3", "RB", 12.0),
        ("wr1", "WR", 19.0),
        ("wr2", "WR", 17.0),
        ("te1", "TE", 15.0),
        ("kbig", "K", 15.0),
        *((f"qbf{index}", "QB", 20.0) for index in range(6)),
        *((f"rbf{index}", "RB", 5.0) for index in range(6)),
        *((f"wrf{index}", "WR", 6.0) for index in range(6)),
        *((f"tef{index}", "TE", 4.0) for index in range(6)),
        *((f"kf{index}", "K", 3.0) for index in range(6)),
    ]


def value(subject, roster, roster_id=1):
    ids = {player_id: i for i, player_id in enumerate(subject.bank.player_ids)}
    assignment = {r: () for r in subject.roster_ids}
    assignment[roster_id] = tuple(ids[player_id] for player_id in roster)
    return subject.projected_roster_value(assignment, roster_id)


class RosterValueScorerTest(unittest.TestCase):
    def setUp(self):
        self.subject = mixed_evaluator(
            ("QB", "RB", "RB", "WR", "FLEX"), mixed_players()
        )

    def test_replacement_marginal_value_is_exact(self):
        # Empty roster scores exactly the all-streamer baseline.
        self.assertEqual(value(self.subject, ()), 0.0)
        # RB replacement is the assignment-independent starter cutline: four
        # teams reserve eight dedicated RBs and the flex cutline leaves the
        # ninth RB at 5.0, so one starting RB is worth (20 - 5) per week for
        # three weeks regardless of who is rostered elsewhere.
        self.assertAlmostEqual(value(self.subject, ("rb1",)), 3 * (20 - 5))

    def test_bench_points_are_not_credited(self):
        starters = ("rb1", "rb2", "rb3", "wr1")
        with_bench = (*starters, "rbf0")
        self.assertEqual(
            value(self.subject, starters), value(self.subject, with_bench)
        )

    def test_high_raw_qb_does_not_outrank_scarce_starter_when_qb_is_filled(self):
        base = ("qb1", "rb1", "rb2", "rb3")
        with_backup_qb = (*base, "qb2")
        with_wr = (*base, "wr2")
        # qb2 projects 28/week versus wr2's 17, but the QB seat is taken and
        # QB is not FLEX eligible, so the scarce WR starter wins; the benched
        # qb2 keeps only his discounted asset value over the QB cutline (20).
        self.assertGreater(
            value(self.subject, with_wr), value(self.subject, with_backup_qb)
        )
        self.assertAlmostEqual(
            value(self.subject, with_backup_qb) - value(self.subject, base),
            0.25 * (28 - 20) * 3,
        )

    def test_flex_credits_eligible_positions_only(self):
        base = ("rb1", "rb2", "wr1")
        # te1 and kbig project identically; only the TE is FLEX eligible.
        self.assertGreater(
            value(self.subject, (*base, "te1")), value(self.subject, (*base, "kbig"))
        )
        self.assertEqual(
            value(self.subject, base), value(self.subject, (*base, "kbig"))
        )

    def test_super_flex_credits_a_second_quarterback(self):
        superflex = mixed_evaluator(
            ("QB", "RB", "RB", "WR", "SUPER_FLEX"), mixed_players()
        )
        base = ("qb1", "rb1", "rb2", "wr1")
        # Without a superflex seat the backup QB carries only discounted
        # bench asset value; with one it starts and beats an equal-projection
        # K and a weaker flex option.
        self.assertAlmostEqual(
            value(self.subject, (*base, "qb2")) - value(self.subject, base),
            0.25 * (28 - 20) * 3,
        )
        self.assertGreater(
            value(superflex, (*base, "qb2")), value(superflex, (*base, "kbig"))
        )
        self.assertGreater(
            value(superflex, (*base, "qb2")), value(superflex, (*base, "rb3"))
        )

    def test_bye_weeks_are_streamed_not_credited(self):
        players = mixed_players()
        player_ids = [player_id for player_id, _, _ in players]
        subject = mixed_evaluator(("QB", "RB", "RB", "WR", "FLEX"), players)
        scores = subject.bank.scores.copy()
        available = subject.bank.available.copy()
        rb1 = player_ids.index("rb1")
        available[:, rb1, 1] = False
        scores[:, rb1, 1] = 0.0
        for array in (scores, available):
            array.flags.writeable = False
        bye_subject = mixed_evaluator(("QB", "RB", "RB", "WR", "FLEX"), players)
        object.__setattr__(bye_subject.bank, "scores", scores)
        object.__setattr__(bye_subject.bank, "available", available)
        # rb1 contributes two playable weeks; the bye week falls back to the
        # cutline streamer instead of crediting the bye as zero starters.
        self.assertAlmostEqual(value(bye_subject, ("rb1",)), 2 * (20 - 5))

    def test_scorer_is_deterministic_and_versioned(self):
        roster = ("qb1", "rb1", "rb2", "wr1", "te1")
        self.assertEqual(value(self.subject, roster), value(self.subject, roster))
        again = mixed_evaluator(("QB", "RB", "RB", "WR", "FLEX"), mixed_players())
        self.assertEqual(value(self.subject, roster), value(again, roster))


class ProjectedValueObjectiveTest(unittest.TestCase):
    def test_recommendation_is_the_projected_value_argmax(self):
        evaluation = evaluate_candidates(
            draft_state(),
            ("p1", "p2", "p3"),
            1,
            range(8),
            market_utility,
            market_utility,
            evaluator(),
            draft_model_version="manual-test-v1",
            seed=19,
        )
        best = max(
            evaluation.candidates, key=lambda c: c.projected_roster_value
        )
        recommendation = recommendation_summary(evaluation)
        self.assertEqual(recommendation.recommended_candidate_id, best.candidate_id)
        self.assertEqual(
            recommendation.projected_roster_value, best.projected_roster_value
        )
        self.assertIn("PROJECTED_VALUE_LEADER", recommendation.reason_codes)

    def test_projected_value_outranks_championship_probability(self):
        evaluation = evaluate_candidates(
            draft_state(),
            ("p1", "p2"),
            1,
            range(8),
            market_utility,
            market_utility,
            evaluator(),
            draft_model_version="manual-test-v1",
            seed=19,
        )
        value_leader = rank_candidates(evaluation)[0]
        other = next(
            candidate for candidate in evaluation.candidates
            if candidate is not value_leader
        )
        # Give the value runner-up a dominant championship record; the
        # ranking and headline must still follow projected roster value.
        inflated = replace(
            other,
            championship_probability=1.0,
            continuation_championship_probabilities=tuple(
                1.0 for _ in other.continuation_championship_probabilities
            ),
            championship_outcomes=tuple(
                True for _ in other.championship_outcomes
            ),
        )
        adjusted = replace(evaluation, candidates=(value_leader, inflated))
        self.assertEqual(
            rank_candidates(adjusted)[0].candidate_id, value_leader.candidate_id
        )
        self.assertEqual(
            recommendation_summary(adjusted).recommended_candidate_id,
            value_leader.candidate_id,
        )

    def test_scarce_candidate_is_selected_and_survivor_deferred(self):
        # Two-slot WR league: the user owns picks 1 and 8. Opponents never
        # take p1 but race for everything else, so p1 always survives while
        # p2 never does. Taking the lower-projection p2 now completes the
        # best roster (p2 now, p1 later); taking p1 now wastes the survival.
        def opponents(roster_id, pick_no, rosters, available):
            utilities = {
                player_id: -100.0 * int(player_id[1:]) for player_id in available
            }
            if "p1" in utilities:
                utilities["p1"] = -1e9
            return utilities

        player_ids = tuple(f"p{index}" for index in range(1, 13))
        expected = np.asarray(
            [110 - index * 10 for index in range(1, 13)], dtype=float
        )
        scores = np.repeat(expected[None, :, None], 2, axis=0)
        scores = np.repeat(scores, 3, axis=2).astype(np.float32)
        available = np.ones_like(scores, dtype=bool)
        for array in (scores, available, expected):
            array.flags.writeable = False
        bank = SeasonWorldBank(
            version="defer-bank-v1",
            seed=1,
            player_ids=player_ids,
            player_positions=("WR",) * len(player_ids),
            expected_scores=expected,
            weeks=WEEKS,
            input_hash="defer-inputs-v1",
            scores=scores,
            available=available,
        )
        league = League({
            "league_id": "defer-league",
            "roster_positions": ["WR", "WR"],
            "settings": {
                "playoff_teams": 4,
                "playoff_round_type": 0,
                "playoff_seed_type": 0,
            },
        })
        league_evaluator = LeagueEvaluator(league, bank, range(1, 5), 1, seed=31)
        evaluation = evaluate_candidates(
            draft_state(),
            ("p1", "p2"),
            1,
            range(12),
            opponents,
            market_utility,
            league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            survival_player_ids=("p1", "p2"),
        )

        recommendation = recommendation_summary(evaluation)
        self.assertEqual(recommendation.recommended_candidate_id, "p2")
        # p1 survives to pick 8 in every continuation that passed on it.
        survival = next(
            player
            for player in evaluation.candidate("p2").survival.players
            if player.player_id == "p1"
        )
        self.assertEqual(survival.survives_to_next_pick, 1.0)
        delta = evaluation.paired_value_delta("p2", "p1")
        self.assertGreater(delta.projected_value_delta, 0)

    def test_changing_the_board_changes_survival_but_not_player_value(self):
        league_evaluator = evaluator()

        def board_a(roster_id, pick_no, rosters, available):
            return {player_id: -100 * int(player_id[1:]) for player_id in available}

        def board_b(roster_id, pick_no, rosters, available):
            # Reversed market order: opponents now hunt high-numbered players.
            return {player_id: 100 * int(player_id[1:]) for player_id in available}

        kwargs = dict(
            user_roster_id=1,
            rollout_ids=range(8),
            user_policy=market_utility,
            league_evaluator=league_evaluator,
            draft_model_version="manual-test-v1",
            seed=19,
            survival_player_ids=("p2", "p3"),
        )
        with_a = evaluate_candidates(
            draft_state(), ("p1",), opponent_choice=board_a, **kwargs
        )
        with_b = evaluate_candidates(
            draft_state(), ("p1",), opponent_choice=board_b, **kwargs
        )

        survival_a = {
            player.player_id: player.survives_to_next_pick
            for player in with_a.candidate("p1").survival.players
        }
        survival_b = {
            player.player_id: player.survives_to_next_pick
            for player in with_b.candidate("p1").survival.players
        }
        self.assertNotEqual(survival_a, survival_b)

        # The same completed roster scores identically under either board:
        # market/opponent inputs never touch the deterministic scorer.
        ids = {
            player_id: index
            for index, player_id in enumerate(league_evaluator.bank.player_ids)
        }
        assignment = {
            1: (ids["p1"], ids["p5"]),
            2: (ids["p2"], ids["p6"]),
            3: (ids["p3"], ids["p7"]),
            4: (ids["p4"], ids["p8"]),
        }
        before = league_evaluator.projected_roster_value(assignment, 1)
        self.assertEqual(
            before, league_evaluator.projected_roster_value(assignment, 1)
        )


if __name__ == "__main__":
    unittest.main()
