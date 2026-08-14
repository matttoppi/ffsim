from types import SimpleNamespace
import unittest

from ffsim.draft_intel.decision import evaluate_candidates
from ffsim.draft_intel.live import (
    _live_opponent_choice,
    _next_user_turn_pick_no,
    _projection_user_policy,
    live_candidate_pool,
)
from ffsim.draft_intel.market_model import SLEEPER_ADP_SOURCE
from ffsim.draft_intel.rollout import complete_drafts
from ffsim.draft_intel.state import replay_sleeper_draft
from tests.test_decision import draft_state, evaluator


def policy_fixture(
    *, scarce_rb_points=70.0, rb_filler_points=50.0,
    pick_owners=(1, 2, 2, 1), temperature=0.01,
):
    player_ids = (
        "qb_now", "qb_later", "qb_filler", "qb_replacement",
        "rb_now", "rb_later", "rb_filler", "rb_replacement",
    )
    positions = ("QB",) * 4 + ("RB",) * 4
    expected = (
        80.0, 78.0, 60.0, 0.0,
        scarce_rb_points, 20.0, rb_filler_points, 0.0,
    )
    adp = {
        "qb_now": 1,
        "rb_now": 1.5,
        "qb_filler": 2,
        "rb_filler": 3,
        "qb_replacement": 4,
        "qb_later": 100,
        "rb_later": 101,
        "rb_replacement": 102,
    }
    league_evaluator = SimpleNamespace(
        bank=SimpleNamespace(
            player_ids=player_ids,
            player_positions=positions,
            expected_scores=expected,
            weeks=(1,),
        ),
        roster_ids=(1, 2),
        slot_counts={"QB": 1, "RB": 1},
    )
    state = SimpleNamespace(pick_owners=pick_owners)
    snapshot = {
        "source": SLEEPER_ADP_SOURCE,
        "snapshot_id": "vona-policy",
        "observations": [
            {"canonical_player_id": player_id, "adp": adp[player_id]}
            for player_id in player_ids
        ],
    }
    choose = _live_opponent_choice(snapshot, league_evaluator, state, temperature)
    return (
        _projection_user_policy(league_evaluator, state, choose),
        ((1, ()), (2, ())),
        frozenset(player_ids),
        league_evaluator,
        snapshot,
    )


class NextTurnOpportunityCostTest(unittest.TestCase):
    def test_root_defense_evidence_does_not_reuse_future_policy_feasibility(self):
        player_ids = (
            "qb1", "qb2", "qb3", "rb1", "rb2", "rb3", "def1", "def2",
        )
        positions = ("QB", "QB", "QB", "RB", "RB", "RB", "DEF", "DEF")
        expected = (80.0, 70.0, 60.0, 75.0, 65.0, 55.0, 30.0, 20.0)
        league_evaluator = SimpleNamespace(
            bank=SimpleNamespace(
                player_ids=player_ids,
                player_positions=positions,
                expected_scores=expected,
                weeks=(1,),
            ),
            roster_ids=(1, 2),
            slot_counts={"QB": 1, "RB": 1, "DEF": 1},
        )
        state = replay_sleeper_draft(
            {
                "draft_id": "root-defense-evidence",
                "type": "snake",
                "status": "drafting",
                "settings": {"teams": 2, "rounds": 4, "reversal_round": 0},
                "draft_order": {"one": 1, "two": 2},
                "slot_to_roster_id": {"1": 1, "2": 2},
            },
            picks=(),
            traded_picks=(),
            player_ids=player_ids,
        )
        snapshot = {
            "source": SLEEPER_ADP_SOURCE,
            "snapshot_id": "root-defense-evidence",
            "observations": [
                {"canonical_player_id": player_id, "adp": index}
                for index, player_id in enumerate(player_ids, 1)
            ],
        }
        prepared = SimpleNamespace(
            user_roster_id=1,
            market_snapshot=snapshot,
            evaluator=league_evaluator,
        )
        choose = _live_opponent_choice(snapshot, league_evaluator, state, 0.01)
        policy = _projection_user_policy(league_evaluator, state, choose)

        self.assertIn("def1", live_candidate_pool(prepared, state, len(player_ids)))
        # DEF is no longer hard-gated out of future picks while other seats
        # are open; it is priced at its open-seat terminal value (ADR-031)
        # and only the end-of-draft feasibility guard restricts positions.
        future_options = policy(1, 1, state.rosters, state.available_player_ids)
        self.assertIn("def1", future_options)
        completions = complete_drafts(
            state, "def1", 1, range(2), choose, policy, seed=17
        )

        evidence = policy.opportunity_evidence(state, "def1", completions)

        self.assertEqual(evidence.current_marginal_value, 30.0)

    def test_audited_1393836057060978688_close_substitute_can_wait(self):
        policy, rosters, available, _, _ = policy_fixture()

        utilities = policy(1, 1, rosters, available)

        # Regression for the audited mock's early QB/TE behavior: QB has the
        # higher current projection, but its close substitute is expected
        # back. RB collapses from 70 to 20, so the two-pick roster is better
        # by taking RB now and QB later.
        self.assertGreater(utilities["rb_now"], utilities["qb_now"])
        # Exact values carry the deterministic 1e-9 projection tiebreak the
        # terminal-marginal policy adds on top of the floored VOR terms.
        self.assertEqual(utilities, {
            "qb_now": 50.7484801147467,
            "rb_now": 68.03562105627304,
        })

    def test_scarce_materially_inferior_player_does_not_automatically_win(self):
        policy, rosters, available, _, _ = policy_fixture(
            scarce_rb_points=21.0, rb_filler_points=20.0
        )

        utilities = policy(1, 1, rosters, available)

        self.assertGreater(utilities["qb_now"], utilities["rb_now"])

    def test_adjacent_picks_are_one_turn(self):
        self.assertEqual(
            _next_user_turn_pick_no((1, 1, 2, 3, 3, 2, 1), 1, 1),
            7,
        )
        self.assertEqual(
            _next_user_turn_pick_no((1, 2, 3, 3, 2, 1), 1, 1),
            6,
        )

        state = replay_sleeper_draft(
            {
                "draft_id": "adjacent-turn",
                "type": "snake",
                "status": "drafting",
                "settings": {"teams": 4, "rounds": 3, "reversal_round": 0},
                "draft_order": {str(roster): roster for roster in range(1, 5)},
                "slot_to_roster_id": {str(roster): roster for roster in range(1, 5)},
            },
            picks=tuple(
                {
                    "draft_id": "adjacent-turn",
                    "pick_no": pick_no,
                    "round": 1,
                    "draft_slot": pick_no,
                    "roster_id": pick_no,
                    "player_id": f"p{pick_no}",
                }
                for pick_no in range(1, 4)
            ),
            traded_picks=(),
            player_ids=(f"p{index}" for index in range(1, 13)),
        )
        utility = lambda _r, _p, _rs, available: {
            player_id: -int(player_id[1:]) for player_id in available
        }
        evaluation = evaluate_candidates(
            state,
            ("p4", "p5"),
            4,
            range(4),
            utility,
            utility,
            evaluator(),
            draft_model_version="adjacent-vona-v1",
            survival_player_ids=("p6",),
        )
        self.assertEqual(evaluation.next_user_pick_no, 12)
        self.assertEqual(
            evaluation.candidate("p4").survival.players[0].survives_to_next_pick,
            0,
        )

    def test_draft_slot_intervening_pick_count_changes_opportunity_cost(self):
        short_policy, rosters, available, _, _ = policy_fixture(
            pick_owners=(1, 2, 1, 2)
        )
        long_policy, _, _, _, _ = policy_fixture(
            pick_owners=(1, 2, 2, 2, 1)
        )

        short = short_policy(1, 1, rosters, available)
        long = long_policy(1, 1, rosters, available)

        self.assertNotEqual(short, long)

    def test_future_availability_uses_the_opponent_probability_model(self):
        sharp, rosters, available, _, _ = policy_fixture(temperature=0.01)
        diffuse, _, _, _, _ = policy_fixture(temperature=5.0)

        # The ADP order and cutoff are identical; only the conditional choice
        # distribution changes, and therefore so does next-turn value.
        self.assertNotEqual(
            sharp(1, 1, rosters, available),
            diffuse(1, 1, rosters, available),
        )

    def test_same_seed_is_deterministic(self):
        policy, rosters, available, _, _ = policy_fixture()

        self.assertEqual(
            policy(1, 1, rosters, available),
            policy(1, 1, rosters, available),
        )

    def test_full_rollouts_expose_a_distribution_of_next_turn_alternatives(self):
        _, _, player_ids, league_evaluator, snapshot = policy_fixture()
        state = replay_sleeper_draft(
            {
                "draft_id": "vona-evidence",
                "type": "snake",
                "status": "drafting",
                "settings": {"teams": 2, "rounds": 2, "reversal_round": 0},
                "draft_order": {"one": 1, "two": 2},
                "slot_to_roster_id": {"1": 1, "2": 2},
            },
            picks=(),
            traded_picks=(),
            player_ids=player_ids,
        )
        choose = _live_opponent_choice(snapshot, league_evaluator, state, 0.01)
        policy = _projection_user_policy(league_evaluator, state, choose)

        qb_completions = complete_drafts(
            state, "qb_now", 1, range(100), choose, policy, seed=17
        )
        rb_completions = complete_drafts(
            state, "rb_now", 1, range(100), choose, policy, seed=17
        )
        qb_cost = policy.opportunity_evidence(state, "qb_now", qb_completions)
        rb_cost = policy.opportunity_evidence(state, "rb_now", rb_completions)

        self.assertEqual(qb_cost.next_user_pick_no, 4)
        self.assertEqual(qb_cost.sample_count, 100)
        self.assertAlmostEqual(
            sum(probability for _, probability in qb_cost.later_alternative_distribution),
            1.0,
        )
        # Waiting on QB through the RB branch commonly leaves the close QB;
        # waiting on RB through the QB branch produces the larger value drop.
        qb_drop = qb_cost.current_marginal_value - rb_cost.expected_best_later_value
        rb_drop = rb_cost.current_marginal_value - qb_cost.expected_best_later_value
        self.assertGreater(rb_cost.expected_best_later_value, 10)
        self.assertGreater(rb_drop, qb_drop)

    def test_vona_policy_keeps_cached_and_uncached_evaluation_equivalent(self):
        state = draft_state()
        league_evaluator = evaluator()
        snapshot = {
            "source": SLEEPER_ADP_SOURCE,
            "snapshot_id": "vona-cache",
            "observations": [
                {"canonical_player_id": f"p{index}", "adp": float(index)}
                for index in range(1, 13)
            ],
        }
        choose = _live_opponent_choice(snapshot, league_evaluator, state, 0.11)
        policy = _projection_user_policy(league_evaluator, state, choose)
        kwargs = dict(
            state=state,
            candidate_ids=("p1", "p2"),
            user_roster_id=1,
            rollout_ids=range(12),
            opponent_choice=choose,
            user_policy=policy,
            league_evaluator=league_evaluator,
            draft_model_version="vona-cache-v1",
            seed=19,
            survival_player_ids=("p1", "p2"),
        )

        cached = evaluate_candidates(**kwargs)
        uncached = evaluate_candidates(**kwargs, use_cache=False)
        reversed_order = evaluate_candidates(
            **{**kwargs, "candidate_ids": ("p2", "p1")},
            use_cache=False,
        )

        self.assertEqual(cached, uncached)
        self.assertIsNotNone(cached.candidate("p1").opportunity_cost)
        self.assertEqual(cached.rollout_ids, reversed_order.rollout_ids)
        self.assertEqual(cached.world_indices, reversed_order.world_indices)
        self.assertEqual(cached.candidate("p1"), reversed_order.candidate("p1"))
        self.assertEqual(cached.candidate("p2"), reversed_order.candidate("p2"))


class TerminalMarginalAlignmentTest(unittest.TestCase):
    """The policy's player values mirror the terminal roster scorer (ADR-031)."""

    def _policy(self, subject, pick_owners=(1, 2, 1)):
        state = SimpleNamespace(pick_owners=pick_owners)
        snapshot = {
            "source": SLEEPER_ADP_SOURCE,
            "snapshot_id": "terminal-marginal",
            "observations": [
                {"canonical_player_id": player_id, "adp": index}
                for index, player_id in enumerate(subject.bank.player_ids, 1)
            ],
        }
        choose = _live_opponent_choice(snapshot, subject, state, 0.11)
        return _projection_user_policy(subject, state, choose)

    def _current_values(self, subject, roster, available):
        # The final user pick has no next turn, so the policy returns its
        # current per-player values directly.
        policy = self._policy(subject)
        rosters = ((1, tuple(roster)), (2, ()), (3, ()), (4, ()))
        return policy(1, len(subject.bank.player_ids), rosters, frozenset(available))

    def test_policy_values_equal_terminal_scorer_marginals(self):
        from tests.test_roster_value import mixed_evaluator, mixed_players, value

        subject = mixed_evaluator(("QB", "RB", "RB", "WR", "FLEX"), mixed_players())
        roster = ("qb1", "rb1", "wr1")
        base = value(subject, roster)
        available = [
            player_id for player_id, _, _ in mixed_players()
            if player_id not in roster
        ]
        utilities = self._current_values(subject, roster, available)
        # Open dedicated seat (rb2), open flex seat (te1), and a bench asset
        # behind the flex (rb3 once te1 outranks it) all price exactly like
        # adding the player to the terminal scorer's roster.
        for candidate in ("rb2", "te1", "wr2", "rb3"):
            self.assertAlmostEqual(
                utilities[candidate],
                value(subject, (*roster, candidate)) - base,
                places=5,
                msg=candidate,
            )

    def test_flex_worthy_te_outranks_backup_qb_when_lineup_is_full(self):
        # Regression for the 7ae93a0e QB pile-up and the ADR-030 phantom
        # survivor edge: static season VOR loved backup QBs and skipped
        # flex-worthy second TEs the terminal scorer values, so wait branches
        # leaked the value the root-forced branch captured.
        player_ids = (
            "qb1", "qb2", "rb1", "rbw", "wr1", "wr2", "te1", "te2",
            "qbr", "rbr", "wrr", "ter",
        )
        positions = ("QB", "QB", "RB", "RB", "WR", "WR", "TE", "TE",
                     "QB", "RB", "WR", "TE")
        # qb2 has a huge static VOR (40 over the QB cutline); te2 is worth 20
        # over the TE cutline and displaces the weak flex starter rbw.
        expected = (80.0, 60.0, 50.0, 12.0, 48.0, 44.0, 40.0, 30.0,
                    20.0, 10.0, 12.0, 10.0)
        subject = SimpleNamespace(
            bank=SimpleNamespace(
                player_ids=player_ids,
                player_positions=positions,
                expected_scores=expected,
                weeks=(1,),
            ),
            roster_ids=(1, 2),
            slot_counts={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1},
        )
        roster = ("qb1", "rb1", "wr1", "te1", "rbw")
        utilities = self._current_values(
            subject, roster, set(player_ids) - set(roster)
        )
        # te2 takes the FLEX seat from rbw (30 - 12 plus the displaced bench
        # credit); qb2 is a bench asset at the discounted fraction despite
        # the larger static VOR, which the old policy would have preferred.
        self.assertGreater(utilities["te2"], utilities["qb2"])
        self.assertAlmostEqual(utilities["qb2"], 0.25 * (60.0 - 20.0), places=5)
        self.assertAlmostEqual(
            utilities["te2"], (30.0 - 12.0) + 0.25 * 12.0, places=5
        )

    def test_zero_value_bench_ties_break_by_projection(self):
        # Below-cutline bench players are terminal ties at zero; the rollout
        # still drafts the better real player, not the smallest player ID.
        player_ids = ("qb1", "rb1", "wr1", "z_big", "a_small")
        positions = ("QB", "RB", "WR", "RB", "RB")
        expected = (80.0, 50.0, 48.0, 30.0, 29.0)
        subject = SimpleNamespace(
            bank=SimpleNamespace(
                player_ids=player_ids,
                player_positions=positions,
                expected_scores=expected,
                weeks=(1,),
            ),
            roster_ids=(1, 2),
            slot_counts={"QB": 1, "RB": 1, "WR": 1},
        )
        utilities = self._current_values(
            subject, ("qb1", "rb1", "wr1"), {"z_big", "a_small"}
        )
        self.assertGreater(utilities["z_big"], utilities["a_small"])


if __name__ == "__main__":
    unittest.main()
