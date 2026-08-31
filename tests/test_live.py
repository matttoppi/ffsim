import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import call, patch

from ffsim.draft_intel.live import (
    PreparedDraft,
    _draft_id,
    _future_turn_survival,
    _manager_slot,
    _projection_user_policy,
    _refresh_history,
    create_live_executor,
    evaluate_live_candidates,
    evaluate_live_league_equity,
    live_candidate_pool,
    live_league_equity_payload,
    live_recommendation_payload,
    live_state_summary,
    merge_screen_refinement,
    mock_mismatch_reasons,
    position_timing_outlook,
    projection_value_board,
    predicted_next_state,
    select_finalists,
)
from ffsim.draft_intel.market_model import SLEEPER_ADP_SOURCE
from ffsim.draft_intel.state import DraftPick
from ffsim.draft_intel.worp import WORPCurve
from tests.test_decision import draft_state, evaluator


class FutureTurnSurvivalTest(unittest.TestCase):
    """Mean-field survival against exact without-replacement enumeration."""

    @staticmethod
    def _exact_survival(utilities, picks, temperature):
        from itertools import permutations
        from math import exp as _exp

        from ffsim.draft_intel.live import LIVE_REACH_RATE
        from ffsim.draft_intel.market_model import REACH_TEMPERATURE

        ids = sorted(utilities)
        components = (
            (1.0 - LIVE_REACH_RATE, temperature),
            (LIVE_REACH_RATE, REACH_TEMPERATURE),
        )

        def pick_probability(player_id, available):
            total = 0.0
            for rate, component_temperature in components:
                weights = {
                    other: _exp(utilities[other] / component_temperature)
                    for other in available
                }
                total += rate * weights[player_id] / sum(weights.values())
            return total

        survival = dict.fromkeys(ids, 0.0)
        for sequence in permutations(ids, picks):
            probability = 1.0
            available = set(ids)
            for player_id in sequence:
                probability *= pick_probability(player_id, available)
                available.remove(player_id)
            for player_id in available:
                survival[player_id] += probability
        return survival

    def test_matches_exact_enumeration_and_conserves_picks(self):
        # Sharp ADP-like board: the adversarial case for mean-field.
        utilities = {
            f"p{index}": -0.35 * index for index in range(8)
        }
        temperature = 0.11
        picks = 4
        snapshots = _future_turn_survival(
            utilities, frozenset(utilities), 1, [1 + picks + 1], temperature,
        )
        approximate = snapshots[1 + picks + 1]
        # One expected pick left the board per intervening pick... the
        # snapshot is taken BEFORE the turn's own pick, after `picks` picks.
        self.assertAlmostEqual(
            sum(approximate.values()), len(utilities) - picks, places=6
        )
        exact = self._exact_survival(utilities, picks, temperature)
        for player_id, exact_survival in exact.items():
            self.assertAlmostEqual(
                approximate[player_id], exact_survival, delta=0.13,
                msg=player_id,
            )

    def test_players_without_market_observations_always_survive(self):
        utilities = {"p0": 0.0, "p1": -0.5}
        snapshots = _future_turn_survival(
            utilities, frozenset({"p0", "p1", "unlisted"}), 1, [3], 0.11,
        )
        self.assertNotIn("unlisted", snapshots[3])
        self.assertLess(snapshots[3]["p0"], snapshots[3]["p1"])


class LiveDraftTest(unittest.TestCase):
    def test_position_timing_targets_the_pick_before_the_adp_value_cliff(self):
        player_ids = ("qb1", "qb2", "qb3", "qb4", "te1", "te2")
        prepared = SimpleNamespace(
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "observations": [
                    {"canonical_player_id": player_id, "adp": adp}
                    for player_id, adp in zip(player_ids, (30, 55, 75, 110, 80, 110))
                ],
            },
            evaluator=SimpleNamespace(
                bank=SimpleNamespace(
                    player_ids=player_ids,
                    player_positions=("QB", "QB", "QB", "QB", "TE", "TE"),
                    expected_scores=(200, 180, 165, 125, 125, 90),
                    weeks=(1, 2),
                ),
                slot_counts={"QB": 1, "TE": 1},
            ),
            player_details={player_id: {"name": player_id.upper()} for player_id in player_ids},
        )
        state = SimpleNamespace(
            current_pick_no=24,
            available_player_ids=frozenset(player_ids),
            future_turn_pick_nos=lambda _roster_id: (48, 72, 96),
            roster_player_ids=lambda _roster_id: (),
        )

        qb, te = position_timing_outlook(prepared, state)

        self.assertEqual([turn["pick_no"] for turn in qb["turns"]], [48, 72, 96])
        # qb3 (ADP 75) no longer counts as available at pick 72: the reach
        # cushion expects intervening off-board picks to displace near-pick
        # targets, so the projected board at 72 already falls to qb4.
        self.assertEqual([turn["player_id"] for turn in qb["turns"]], [
            "qb2", "qb4", "qb4",
        ])
        self.assertEqual(qb["target_pick_no"], 48)
        self.assertEqual(qb["recommendation"], "TARGET_BY_PICK")
        self.assertEqual(te["target_pick_no"], 72)

        prepared.evaluator.bank.expected_scores = (200, 150, 140, 130, 125, 90)
        (urgent_qb,) = position_timing_outlook(prepared, state, positions=("QB",))
        self.assertEqual(urgent_qb["target_pick_no"], 24)
        self.assertEqual(urgent_qb["recommendation"], "TAKE_NOW")

    def test_projection_value_board_ranks_league_points_and_wait_routes(self):
        player_ids = (
            "qb1", "qb2", "qb3",
            "rb1", "rb2", "rb3",
            "wr1", "wr2", "wr3",
        )
        positions = ("QB",) * 3 + ("RB",) * 3 + ("WR",) * 3
        expected_scores = (30, 20, 10, 24, 16, 8, 22, 15, 7)
        league_evaluator = SimpleNamespace(
            bank=SimpleNamespace(
                player_ids=player_ids,
                player_positions=positions,
                expected_scores=expected_scores,
                weeks=(1, 2, 3),
            ),
            roster_ids=(1, 2),
            slot_counts={"QB": 1, "RB": 1, "WR": 1},
            regular_season_weeks=3,
        )
        prepared = SimpleNamespace(
            user_roster_id=1,
            summary={
                "market_context": {
                    "target_context": {"team_count": 2, "scoring": "PPR"}
                }
            },
            evaluator=league_evaluator,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "projection-board",
                "observations": [
                    {"canonical_player_id": player_id, "adp": index * 4}
                    for index, player_id in enumerate(player_ids, 1)
                ],
            },
            player_details={
                player_id: {"name": player_id.upper(), "team": "TST"}
                for player_id in player_ids
            },
        )
        state = SimpleNamespace(
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1, 2, 1, 2, 1, 2, 1, 2),
            rosters=((1, ()), (2, ())),
            available_player_ids=frozenset(player_ids),
        )

        with patch(
            "ffsim.draft_intel.live.load_worp_curve",
            return_value=(
                WORPCurve(2, "PPR", (0.0, 10.0), (0.0, 0.2)),
                {"status": "validated", "team_count": 2, "scoring_format": "PPR"},
            ),
        ):
            board = projection_value_board(prepared, state)

        self.assertEqual(board["pick_no"], 1)
        self.assertEqual(board["model_version"], 3)
        self.assertEqual(
            board["route_model_status"],
            "approximate_adp_opponent_choice_lookahead",
        )
        self.assertEqual(board["worp_calibration"]["status"], "validated")
        self.assertEqual(board["next_user_pick_no"], 3)
        self.assertEqual(
            board["points_source"], "fantasypros_primary_offense"
        )
        self.assertEqual(board["special_teams_points_source"], "pff")
        self.assertEqual(
            [plan["position"] for plan in board["plans"]],
            [
                plan["position"]
                for plan in sorted(
                    board["plans"],
                    key=lambda plan: -plan["route_value"],
                )
            ],
        )
        qb_rows = [
            player for player in board["players"] if player["position"] == "QB"
        ]
        self.assertEqual(
            [(player["player_id"], player["projected_points"]) for player in qb_rows],
            [("qb1", 90.0), ("qb2", 60.0), ("qb3", 30.0)],
        )
        points_qb = [
            player
            for player in board["points_players"]
            if player["position"] == "QB"
        ]
        self.assertEqual(
            [
                (
                    player["position_rank"],
                    player["player_id"],
                    player["projected_points"],
                )
                for player in points_qb
            ],
            [
                (1, "qb1", 90.0),
                (2, "qb2", 60.0),
                (3, "qb3", 30.0),
            ],
        )
        self.assertEqual(qb_rows[0]["replacement_points"], 30.0)
        self.assertEqual(qb_rows[0]["value_over_replacement"], 60.0)
        self.assertAlmostEqual(qb_rows[0]["wins_over_replacement"], 0.6)
        self.assertEqual(
            board["recommended_player_id"],
            board["plans"][0]["player_id"],
        )
        self.assertGreaterEqual(
            board["plans"][0]["route_value"],
            board["plans"][-1]["route_value"],
        )

    def test_projection_value_board_publishes_tables_without_plans_off_clock(self):
        player_ids = (
            "qb1", "qb2", "qb3",
            "rb1", "rb2", "rb3",
            "wr1", "wr2", "wr3",
        )
        positions = ("QB",) * 3 + ("RB",) * 3 + ("WR",) * 3
        expected_scores = (30, 20, 10, 24, 16, 8, 22, 15, 7)
        league_evaluator = SimpleNamespace(
            bank=SimpleNamespace(
                player_ids=player_ids,
                player_positions=positions,
                expected_scores=expected_scores,
                weeks=(1, 2, 3),
            ),
            roster_ids=(1, 2),
            slot_counts={"QB": 1, "RB": 1, "WR": 1},
            regular_season_weeks=3,
        )
        prepared = SimpleNamespace(
            user_roster_id=1,
            summary={
                "market_context": {
                    "target_context": {"team_count": 2, "scoring": "PPR"}
                }
            },
            evaluator=league_evaluator,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "projection-board",
                "observations": [
                    {"canonical_player_id": player_id, "adp": index * 4}
                    for index, player_id in enumerate(player_ids, 1)
                ],
            },
            player_details={
                player_id: {"name": player_id.upper(), "team": "TST"}
                for player_id in player_ids
            },
        )
        opponent_state = SimpleNamespace(
            current_pick_no=2,
            current_roster_id=2,
            pick_owners=(1, 2, 1, 2, 1, 2, 1, 2),
            rosters=((1, ()), (2, ())),
            available_player_ids=frozenset(player_ids),
        )

        with patch(
            "ffsim.draft_intel.live.load_worp_curve",
            return_value=(
                WORPCurve(2, "PPR", (0.0, 10.0), (0.0, 0.2)),
                {"status": "validated", "team_count": 2, "scoring_format": "PPR"},
            ),
        ):
            board = projection_value_board(prepared, opponent_state)

        self.assertEqual(board["pick_no"], 2)
        self.assertTrue(board["players"])
        self.assertTrue(board["points_players"])
        self.assertEqual(board["plans"], [])
        self.assertIsNone(board["recommended_player_id"])
        self.assertIsNone(board["recommended_position"])
        self.assertEqual(board["next_user_pick_no"], 3)

        outlook = board["position_outlook"]
        self.assertEqual(outlook["edge_basis"], "first_marginal_seat")
        self.assertEqual(
            outlook["availability_model"], "market_mixture_mean_field_survival"
        )
        self.assertEqual(
            outlook["survival_model"], "mean_field_without_replacement"
        )
        # Off the clock at pick 2, the user's future turns are 3, 5, 7.
        self.assertEqual(outlook["future_turn_pick_nos"], [3, 5, 7])
        rows = outlook["positions"]
        self.assertEqual(
            sorted(row["position"] for row in rows), ["QB", "RB", "WR"]
        )
        # Positions are ordered by take-now edge; every edge and drop is the
        # first-seat marginal value difference against the same turn, and the
        # no-flex league reports one dedicated seat per position.
        edges = [row["take_now_edge"] for row in rows]
        self.assertEqual(edges, sorted(edges, reverse=True))
        for row in rows:
            self.assertEqual(row["open_dedicated_slots"], 1)
            self.assertEqual(row["eligible_open_flex_slots"], 0)
            self.assertEqual(row["remaining_starting_opportunities"], 1)
            self.assertEqual(
                [turn["pick_no"] for turn in row["turns"]], [3, 5, 7]
            )
            for turn in row["turns"]:
                self.assertAlmostEqual(
                    turn["drop_from_now"],
                    row["best_now_marginal_value"] - turn["marginal_value"],
                )
            self.assertAlmostEqual(
                row["take_now_edge"],
                row["best_now_marginal_value"]
                - max(turn["marginal_value"] for turn in row["turns"]),
            )
            for turn in row["turns"]:
                self.assertGreaterEqual(turn["survival_probability"], 0.0)
                self.assertLessEqual(turn["survival_probability"], 1.0)
            self.assertLessEqual(len(row["top_players"]), 5)
            self.assertAlmostEqual(
                row["top_players"][0]["edge_vs_waiting"], row["take_now_edge"]
            )

        completed_state = SimpleNamespace(
            current_pick_no=None,
            current_roster_id=None,
            pick_owners=(1, 2),
            rosters=((1, ()), (2, ())),
            available_player_ids=frozenset(),
        )
        self.assertIsNone(projection_value_board(prepared, completed_state))

    def test_personal_offsets_move_board_points_but_not_falloff(self):
        player_ids = (
            "qb1", "qb2", "qb3",
            "rb1", "rb2", "rb3",
            "wr1", "wr2", "wr3",
        )
        positions = ("QB",) * 3 + ("RB",) * 3 + ("WR",) * 3
        expected_scores = (30, 20, 10, 24, 16, 8, 22, 15, 7)

        def prepared_with(personal_ranks):
            return SimpleNamespace(
                user_roster_id=1,
                summary={
                    "market_context": {
                        "target_context": {"team_count": 2, "scoring": "PPR"}
                    }
                },
                evaluator=SimpleNamespace(
                    bank=SimpleNamespace(
                        player_ids=player_ids,
                        player_positions=positions,
                        expected_scores=expected_scores,
                        weeks=(1, 2, 3),
                    ),
                    roster_ids=(1, 2),
                    slot_counts={"QB": 1, "RB": 1, "WR": 1},
                    regular_season_weeks=3,
                ),
                market_snapshot={
                    "source": SLEEPER_ADP_SOURCE,
                    "snapshot_id": "projection-board",
                    "observations": [
                        {"canonical_player_id": player_id, "adp": index * 4}
                        for index, player_id in enumerate(player_ids, 1)
                    ],
                },
                player_details={
                    player_id: {"name": player_id.upper(), "team": "TST"}
                    for player_id in player_ids
                },
                personal_ranks=personal_ranks,
            )

        state = SimpleNamespace(
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1, 2, 1, 2, 1, 2, 1, 2),
            rosters=((1, ()), (2, ())),
            available_player_ids=frozenset(player_ids),
        )
        with patch(
            "ffsim.draft_intel.live.load_worp_curve",
            return_value=(
                WORPCurve(2, "PPR", (0.0, 10.0), (0.0, 0.2)),
                {"status": "validated", "team_count": 2, "scoring_format": "PPR"},
            ),
        ):
            raw_board = projection_value_board(prepared_with({}), state)
            # +30 season points on the deep WR dart throw (wr3: 21 raw).
            my_board = projection_value_board(
                prepared_with({"wr3": 30}), state
            )

        rows = {row["player_id"]: row for row in my_board["players"]}
        # Board points are personal: base projection + offset; VORP follows
        # with the raw replacement baseline; untouched players unchanged.
        self.assertEqual(rows["wr3"]["projected_points"], 51.0)
        self.assertEqual(rows["wr3"]["personal_offset"], 30)
        self.assertEqual(rows["wr1"]["projected_points"], 66.0)
        self.assertEqual(
            rows["wr3"]["value_over_replacement"],
            51.0 - rows["wr3"]["replacement_points"],
        )
        # The Points table resorts on personal points: wr3 (51) over wr2 (45).
        self.assertEqual(
            [
                row["player_id"]
                for row in my_board["points_players"]
                if row["position"] == "WR"
            ],
            ["wr1", "wr3", "wr2"],
        )

        # The falloff diagnostic ignores offsets entirely: same targets,
        # same edges as the raw board, and it says so.
        self.assertEqual(
            my_board["position_outlook"]["value_basis"], "raw_projection"
        )
        raw_wr = next(
            row for row in raw_board["position_outlook"]["positions"]
            if row["position"] == "WR"
        )
        my_wr = next(
            row for row in my_board["position_outlook"]["positions"]
            if row["position"] == "WR"
        )
        # The raw-strongest WR keeps the falloff headline despite the boost.
        self.assertEqual(my_wr["best_now_player_id"], "wr1")
        self.assertEqual(my_wr["best_now_player_id"], raw_wr["best_now_player_id"])
        self.assertEqual(
            [turn["player_id"] for turn in my_wr["turns"]],
            [turn["player_id"] for turn in raw_wr["turns"]],
        )
        self.assertEqual(my_wr["take_now_edge"], raw_wr["take_now_edge"])
        self.assertEqual(
            [player["marginal_value"] for player in my_wr["top_players"]],
            [player["marginal_value"] for player in raw_wr["top_players"]],
        )
        # Falloff points stay raw (market card, one basis), with the offset
        # carried separately so the UI can flag the boosted name.
        wr3_target = next(
            player for player in my_wr["top_players"]
            if player["player_id"] == "wr3"
        )
        self.assertEqual(wr3_target["projected_points"], 21.0)
        self.assertEqual(wr3_target["personal_offset"], 30)
        self.assertEqual(my_wr["best_now_points"], raw_wr["best_now_points"])

    def test_projection_points_board_caps_each_position_at_ten_remaining(self):
        player_ids = tuple(f"qb{index:02d}" for index in range(1, 13))
        league_evaluator = SimpleNamespace(
            bank=SimpleNamespace(
                player_ids=player_ids,
                player_positions=("QB",) * len(player_ids),
                expected_scores=tuple(
                    range(len(player_ids), 0, -1)
                ),
                weeks=(1,),
            ),
            roster_ids=(1, 2),
            slot_counts={"QB": 1},
            regular_season_weeks=1,
        )
        prepared = SimpleNamespace(
            user_roster_id=1,
            summary={
                "market_context": {
                    "target_context": {
                        "team_count": 2,
                        "scoring": "PPR",
                    }
                }
            },
            evaluator=league_evaluator,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "points-board",
                "observations": [
                    {
                        "canonical_player_id": player_id,
                        "adp": index,
                    }
                    for index, player_id in enumerate(player_ids, 1)
                ],
            },
            player_details={
                player_id: {"name": player_id.upper(), "team": "TST"}
                for player_id in player_ids
            },
        )
        state = SimpleNamespace(
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1, 2, 1, 2),
            rosters=((1, ()), (2, ())),
            available_player_ids=frozenset(player_ids),
        )

        with patch(
            "ffsim.draft_intel.live.load_worp_curve",
            return_value=(
                None,
                {
                    "status": "missing",
                    "team_count": 2,
                    "scoring_format": "PPR",
                },
            ),
        ):
            board = projection_value_board(prepared, state)

        self.assertEqual(len(board["points_players"]), 10)
        self.assertEqual(
            [player["position_rank"] for player in board["points_players"]],
            list(range(1, 11)),
        )
        self.assertEqual(
            [player["player_id"] for player in board["points_players"]],
            list(player_ids[:10]),
        )

    def test_live_league_equity_payload_names_and_ranks_every_roster(self):
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={},
            roster_details={
                roster_id: {
                    "name": f"Team {roster_id}",
                    "draft_slot": roster_id,
                    "is_user": roster_id == 1,
                }
                for roster_id in range(1, 5)
            },
        )

        payload = live_league_equity_payload(
            prepared,
            evaluate_live_league_equity(prepared, draft_state(), 4),
        )

        self.assertEqual(len(payload["rosters"]), 4)
        self.assertEqual({row["name"] for row in payload["rosters"]}, {
            "Team 1", "Team 2", "Team 3", "Team 4",
        })
        self.assertTrue(next(row for row in payload["rosters"] if row["roster_id"] == 1)["is_user"])
        self.assertAlmostEqual(
            sum(row["championship_probability"] for row in payload["rosters"]),
            1.0,
        )

    def test_parallel_candidate_evaluation_matches_the_sequential_batch(self):
        state = draft_state()
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={},
        )
        candidates = ("p1", "p2", "p3")
        with (
            patch(
                "ffsim.historical_sleeper.manager_choice.load_manager_choice_model",
                side_effect=AssertionError("live path loaded manager research"),
            ),
            patch(
                "ffsim.historical_sleeper.hierarchical_survival.load_hierarchical_survival_model",
                side_effect=AssertionError("live path loaded survival research"),
            ),
            patch(
                "ffsim.historical_sleeper.hdvn_neural.load_neural_artifact",
                side_effect=AssertionError("live path loaded rejected neural research"),
            ),
        ):
            sequential = evaluate_live_candidates(prepared, state, 4, candidates)
            with create_live_executor(prepared, workers=2) as executor:
                parallel = evaluate_live_candidates(
                    prepared, state, 4, candidates, executor=executor
                )
        self.assertEqual(sequential.rollout_ids, parallel.rollout_ids)
        self.assertEqual(sequential.world_indices, parallel.world_indices)
        self.assertEqual(sequential.draft_model_version, parallel.draft_model_version)
        self.assertTrue(
            sequential.draft_model_version.endswith(
                ":t0.11:reach0.15:needs:vona5:hazard1"
            )
        )
        self.assertEqual(
            {candidate.candidate_id: candidate for candidate in sequential.candidates},
            {candidate.candidate_id: candidate for candidate in parallel.candidates},
        )

    def test_trusted_log_probability_callback_matches_the_generic_path(self):
        from ffsim.draft_intel.live import (
            _live_opponent_choice,
            _projection_user_policy,
        )
        from ffsim.draft_intel.rollout import complete_drafts

        state = draft_state()
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={},
        )
        choose = _live_opponent_choice(
            prepared.market_snapshot, prepared.evaluator, state, 0.11
        )
        self.assertTrue(choose.returns_final_log_probabilities)

        def generic(*args):
            ids, log_probabilities, _ = choose(*args)
            return dict(zip(ids.tolist(), log_probabilities.tolist()))

        policy = _projection_user_policy(prepared.evaluator, state, choose)
        kwargs = dict(seed=7, temperature=1.0)
        trusted_runs = complete_drafts(
            state, "p2", 1, range(6), choose, policy, **kwargs
        )
        generic_runs = complete_drafts(
            state, "p2", 1, range(6), generic, policy, **kwargs
        )
        for trusted_run, generic_run in zip(trusted_runs, generic_runs, strict=True):
            self.assertEqual(
                [pick.player_id for pick in trusted_run.picks],
                [pick.player_id for pick in generic_run.picks],
            )
            self.assertEqual(trusted_run.rosters, generic_run.rosters)
            self.assertAlmostEqual(
                trusted_run.opponent_log_probability,
                generic_run.opponent_log_probability,
                places=10,
            )

    def test_refinement_survivors_use_the_practical_tie_boundary(self):
        from ffsim.draft_intel.live import refinement_survivors

        leader = SimpleNamespace(
            candidate_id="leader",
            projected_roster_value=1.0,
            championship_probability=0.0,
            playoff_probability=0.0,
            expected_wins=0.0,
            expected_points=0.0,
        )
        rival = SimpleNamespace(
            candidate_id="rival",
            projected_roster_value=0.0,
            championship_probability=0.0,
            playoff_probability=0.0,
            expected_wins=0.0,
            expected_points=0.0,
        )
        cases = (
            # Candidate-minus-leader upper bound is -0.05: still within the
            # 0.1-point practical tier, but already bounded.
            ("boundary_survives", (0.05, 0.05), ("leader", "rival"), False),
            ("bounded_practical_tie", (0.02, 0.09), ("leader", "rival"), False),
            ("wide_boundary", (0.04, 4.10), ("leader", "rival"), True),
            ("exact_upper_boundary", (0.02, 0.10), ("leader", "rival"), False),
            ("dominated", (0.100001, 4.10), ("leader",), False),
        )
        for name, interval, expected_survivors, expected_refinement in cases:
            with self.subTest(name=name):
                def paired_value_delta(candidate_id, baseline_candidate_id):
                    self.assertEqual(
                        (candidate_id, baseline_candidate_id),
                        ("leader", "rival"),
                    )
                    return SimpleNamespace(interval=interval)

                evaluation = SimpleNamespace(
                    candidates=(leader, rival),
                    paired_value_delta=paired_value_delta,
                )

                survivors, needs_refinement = refinement_survivors(evaluation)

                self.assertEqual(survivors, expected_survivors)
                self.assertEqual(needs_refinement, expected_refinement)

    def test_predicted_next_state_applies_the_model_argmax_pick(self):
        state = draft_state()
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=2,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={"p1": {"position": "WR"}},
        )
        self.assertEqual(state.current_roster_id, 1)
        hypothetical = predicted_next_state(prepared, state)
        # The sharp board-follower's most likely pick is the best ADP player.
        self.assertEqual(hypothetical.completed_picks[-1].player_id, "p1")
        self.assertEqual(hypothetical.completed_picks[-1].position, "WR")
        self.assertEqual(hypothetical.current_roster_id, 2)
        self.assertNotIn("p1", hypothetical.available_player_ids)
        # No speculation on the user's own turn.
        self.assertIsNone(
            predicted_next_state(
                PreparedDraft(
                    summary={},
                    live_draft_id="draft",
                    league_id=None,
                    standalone=True,
                    user_roster_id=1,
                    market_snapshot=prepared.market_snapshot,
                    evaluator=prepared.evaluator,
                    player_details={},
                ),
                state,
            )
        )

    def test_chunked_rollout_fanout_matches_the_sequential_batch(self):
        from ffsim.draft_intel import live

        state = draft_state()
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={},
        )
        candidates = ("p1", "p2")
        sequential = evaluate_live_candidates(prepared, state, 7, candidates)
        with patch.object(live, "LIVE_ROLLOUT_CHUNK", 3):
            self.assertEqual(
                [range(0, 3), range(3, 7)],
                live._rollout_chunks(range(7), 3),
            )
            with create_live_executor(prepared, workers=2) as executor:
                chunked = evaluate_live_candidates(
                    prepared, state, 7, candidates, executor=executor
                )
        self.assertEqual(
            {candidate.candidate_id: candidate for candidate in sequential.candidates},
            {candidate.candidate_id: candidate for candidate in chunked.candidates},
        )
        self.assertEqual(sequential.rollout_ids, chunked.rollout_ids)
        self.assertEqual(sequential.world_indices, chunked.world_indices)

    def test_screen_reuse_refinement_equals_one_full_range_evaluation(self):
        state = draft_state()
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={},
        )
        pool = ("p1", "p2", "p3", "p4")
        finalists = ("p2", "p4")
        screen_evaluations = [
            evaluate_live_candidates(
                prepared, state, 5, pool[:2], survival_ids=pool
            ),
            evaluate_live_candidates(
                prepared, state, 5, pool[2:], survival_ids=pool
            ),
        ]
        extension = evaluate_live_candidates(
            prepared, state, range(5, 12), finalists, survival_ids=finalists
        )
        merged = merge_screen_refinement(screen_evaluations, extension)
        flat = evaluate_live_candidates(
            prepared, state, 12, finalists, survival_ids=finalists
        )
        self.assertEqual(merged, flat)

    def test_recommendation_uses_the_best_alternative_branch_for_return_chance(self):
        state = draft_state()
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={
                f"p{index}": {"name": f"Player {index}", "position": "WR"}
                for index in range(1, 13)
            },
        )
        evaluation = evaluate_live_candidates(prepared, state, 20, ("p1", "p8"))

        payload = live_recommendation_payload(prepared, state, [evaluation], 2)
        self.assertIn("PROJECTED_VALUE_LEADER", payload["reason_codes"])
        self.assertEqual(
            payload["recommended_candidate_id"],
            max(
                evaluation.candidates,
                key=lambda candidate: candidate.projected_roster_value,
            ).candidate_id,
        )
        self.assertIn("projected_roster_value", payload)
        self.assertIn("paired_value_delta_vs_runner_up", payload)
        for candidate_row in payload["candidates"]:
            self.assertIn("projected_roster_value", candidate_row)
        # Ranked payload order follows projected value, not championship.
        values = [
            row["projected_roster_value"] for row in payload["candidates"]
        ]
        self.assertEqual(values, sorted(values, reverse=True))

        own_branch = next(
            player for player in evaluation.candidate("p8").survival.players
            if player.player_id == "p8"
        )
        row = next(
            candidate
            for candidate in live_recommendation_payload(
                prepared, state, [evaluation], 2
            )["candidates"]
            if candidate["player_id"] == "p8"
        )

        self.assertEqual(own_branch.survives_to_next_pick, 0)
        self.assertAlmostEqual(row["adp"], 8)
        self.assertIsInstance(row["is_top_tier"], bool)
        self.assertEqual(row["best_wait_candidate_id"], "p1")
        self.assertEqual(row["survival_branch_root_candidate_id"], "p1")
        self.assertEqual(
            row["opportunity_evidence_branch_root_candidate_id"],
            "p8",
        )
        self.assertLessEqual(
            row["target_selected_when_available_count"],
            row["target_available_count"],
        )
        self.assertEqual(
            row["target_rollout_count"],
            evaluation.candidate("p1").survival.rollout_count,
        )
        self.assertEqual(row["rollout_count"], 20)
        self.assertEqual(row["next_turn_pick_no"], evaluation.next_user_pick_no)
        self.assertEqual(row["opportunity_sample_count"], 20)
        self.assertEqual(
            row["opportunity_model_version"],
            "next-turn-vona-v3:terminal-marginal-flex-streamer",
        )
        self.assertIsNotNone(row["current_marginal_value"])
        self.assertIsNotNone(row["expected_best_later_value"])
        self.assertAlmostEqual(
            sum(alternative["probability"] for alternative in row["later_alternatives"])
            + row["later_alternative_other_probability"],
            1.0,
        )
        # Reach-mixture opponents occasionally snipe p8 before the next
        # pick, so the return chance is high but never certain.
        self.assertGreater(row["survives_to_next_pick"], 0.5)
        self.assertLess(row["survives_to_next_pick"], 1.0)
        self.assertEqual(
            payload["q_leader_candidate_id"],
            max(
                evaluation.candidates,
                key=lambda candidate: candidate.projected_roster_value,
            ).candidate_id,
        )
        self.assertEqual(
            {bound["candidate_id"] for bound in payload["paired_value_bounds_vs_q_leader"]},
            {"p1", "p8"},
        )

    def test_live_payload_exposes_branch_denominator_and_effective_urgency(self):
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={
                **{
                    f"p{index}": {"name": f"Player {index}", "position": "WR"}
                    for index in range(1, 13)
                },
                "p1": {"name": "Player 1", "position": "K"},
            },
        )
        evaluation = evaluate_live_candidates(
            prepared, draft_state(), 20, ("p1", "p8")
        )
        p1, p8 = evaluation.candidates
        evaluation = replace(
            evaluation,
            candidates=(
                p1,
                replace(
                    p8,
                    continuation_championship_probabilities=(
                        p8.continuation_championship_probabilities[:7]
                    ),
                ),
            ),
        )

        payload = live_recommendation_payload(
            prepared, draft_state(), [evaluation], 2
        )
        kicker = next(
            row for row in payload["candidates"] if row["player_id"] == "p1"
        )
        shortened = next(
            row for row in payload["candidates"] if row["player_id"] == "p8"
        )

        self.assertGreater(kicker["value_over_next_alternative"], 0)
        self.assertEqual(kicker["effective_tie_break_urgency"], 0)
        self.assertEqual(shortened["rollout_count"], 7)
        self.assertEqual(shortened["target_rollout_count"], 20)
        self.assertEqual(payload["practical_tie_points"], 0.1)
        self.assertEqual(payload["bench_asset_factor"], 0.25)
        self.assertIsNone(payload["headline_tie_break_basis"])

    def test_toss_up_payload_names_the_actual_tie_break_basis(self):
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={
                f"p{index}": {"name": f"Player {index}", "position": "WR"}
                for index in range(1, 13)
            },
        )
        evaluation = evaluate_live_candidates(
            prepared, draft_state(), 20, ("p1", "p8")
        )
        leader, rival = evaluation.candidates
        rival = replace(
            rival,
            projected_roster_value=leader.projected_roster_value,
            continuation_roster_values=leader.continuation_roster_values,
        )

        cases = (
            ("urgency", 0.0, 2.0, 1.0, 8.0, "p8", "URGENCY_TIEBREAK"),
            ("market_adp", 0.0, 0.0, 8.0, 1.0, "p8", "MARKET_ADP_TIEBREAK"),
            ("engine_rank", 0.0, 0.0, 1.0, 1.0, "p1", "ENGINE_RANK_TIEBREAK"),
        )
        for (
            basis,
            leader_vona,
            rival_vona,
            leader_adp,
            rival_adp,
            headline,
            reason,
        ) in cases:
            with self.subTest(basis=basis):
                candidates = (
                    replace(
                        leader,
                        opportunity_cost=replace(
                            leader.opportunity_cost,
                            value_over_next_alternative=leader_vona,
                        ),
                    ),
                    replace(
                        rival,
                        opportunity_cost=replace(
                            rival.opportunity_cost,
                            value_over_next_alternative=rival_vona,
                        ),
                    ),
                )
                observations = [
                    {**row, "adp": leader_adp}
                    if row["canonical_player_id"] == "p1"
                    else {**row, "adp": rival_adp}
                    if row["canonical_player_id"] == "p8"
                    else row
                    for row in prepared.market_snapshot["observations"]
                ]
                case_prepared = replace(
                    prepared,
                    market_snapshot={
                        **prepared.market_snapshot,
                        "observations": observations,
                    },
                )

                payload = live_recommendation_payload(
                    case_prepared,
                    draft_state(),
                    [replace(evaluation, candidates=candidates)],
                    2,
                )

                self.assertEqual(payload["decision_status"], "toss_up")
                self.assertEqual(payload["headline_tie_break_basis"], basis)
                self.assertEqual(payload["recommended_candidate_id"], headline)
                self.assertEqual(
                    {code for code in payload["reason_codes"] if "TIEBREAK" in code},
                    {reason},
                )

    def test_future_user_policy_prefers_value_over_replacement_in_open_slots(self):
        bank = SimpleNamespace(
            player_ids=(
                "qb1", "qb2", "qb3", "rb1", "rb2", "rb3", "wr1", "wr2", "te1",
                "k1", "k2", "k3", "def1", "def2", "def3",
            ),
            player_positions=(
                "QB", "QB", "QB", "RB", "RB", "RB", "WR", "WR", "TE",
                "K", "K", "K", "DEF", "DEF", "DEF",
            ),
            expected_scores=(
                25.0, 24.0, 20.0, 18.0, 15.0, 8.0, 17.0, 9.0, 12.0,
                10.0, 9.0, 8.0, 9.0, 8.0, 7.0,
            ),
            weeks=(1, 2, 3),
        )
        league_evaluator = SimpleNamespace(
            bank=bank,
            roster_ids=(1, 2),
            slot_counts={"QB": 1, "RB": 1, "FLEX": 1, "K": 1, "DEF": 1},
        )
        state = SimpleNamespace(pick_owners=(1, 2) * 7)
        snapshot = {
            "source": SLEEPER_ADP_SOURCE,
            "snapshot_id": "policy",
            "observations": [
                {"canonical_player_id": player_id, "adp": index}
                for index, player_id in enumerate(bank.player_ids, 1)
            ],
        }
        from ffsim.draft_intel.live import _live_opponent_choice
        choose = _live_opponent_choice(snapshot, league_evaluator, state, 0.11)
        policy = _projection_user_policy(league_evaluator, state, choose)

        # The lookahead compares the best current option at each feasible
        # position; dominated same-position alternatives do not add work.
        empty = ((1, ()), (2, ()))
        utilities = policy(1, 2, empty, frozenset(bank.player_ids))
        self.assertIn("rb1", utilities)
        self.assertNotIn("rb2", utilities)

        # Once the only QB slot is filled (QB is not FLEX eligible here), a
        # backup QB stays priced as a discounted bench asset (ADR-031) and
        # never leads while starter seats are open.
        after_qb = ((1, ("qb1",)), (2, ()))
        utilities = policy(1, 3, after_qb, frozenset(bank.player_ids) - {"qb1"})
        self.assertIn("qb2", utilities)
        self.assertNotEqual(max(utilities, key=utilities.get), "qb2")

        # Once the core lineup is full, bench value competes with K/DEF
        # instead of those slots being filled mechanically: rb2 stays in the
        # pool at discounted bench-asset value (ADR-029/031), and k1's full
        # starter edge over the kicker cutline honestly outranks it here
        # (6.0 over cutline versus 0.25 x 21 = 5.25 bench credit).
        core_filled = ((1, ("qb1", "rb1", "wr1")), (2, ()))
        available = frozenset(bank.player_ids) - set(core_filled[0][1])
        utilities = policy(1, 4, core_filled, available)
        self.assertIn("rb2", utilities)
        self.assertGreaterEqual(utilities["k1"], utilities["rb2"])

        # There is no reason for the user's rollout policy to draft a backup
        # kicker or defense while replacement streaming exists.
        after_kicker = ((1, (*core_filled[0][1], "k1")), (2, ()))
        utilities = policy(1, 5, after_kicker, available - {"k1"})
        self.assertNotIn("k2", utilities)

        # With exactly two picks left and K/DEF still open, both picks must
        # fill those seats; another bench player would create the impossible
        # terminal rosters found in live telemetry.
        late = ((1, ("qb1", "rb1", "wr1", "rb2", "wr2")), (2, ()))
        late_available = frozenset(bank.player_ids) - set(late[0][1])
        utilities = policy(1, 6, late, late_available)
        self.assertEqual(
            {
                bank.player_positions[bank.player_ids.index(player_id)]
                for player_id in utilities
            },
            {"K", "DEF"},
        )

        # One backup is allowed at QB, but a third QB is not.
        two_qbs = ((1, ("qb1", "qb2", "rb1", "wr1")), (2, ()))
        utilities = policy(
            1,
            5,
            two_qbs,
            frozenset(bank.player_ids) - set(two_qbs[0][1]),
        )
        self.assertNotIn("qb3", utilities)

        # The final user pick returns current values without lookahead.
        final_pick_values = policy(
            1,
            13,
            empty,
            frozenset(bank.player_ids),
        )
        self.assertIn("qb1", final_pick_values)
        self.assertIsInstance(final_pick_values["qb1"], float)

    def test_live_rollouts_finish_with_complete_sane_rosters(self):
        from collections import Counter

        from ffsim.draft_intel.live import _live_opponent_choice
        from ffsim.draft_intel.market_model import starting_lineup_needs
        from ffsim.draft_intel.rollout import complete_drafts
        from ffsim.draft_intel.state import replay_sleeper_draft

        positions = tuple(
            position
            for position, count in (
                ("QB", 12), ("RB", 24), ("WR", 24), ("TE", 12),
                ("K", 4), ("DEF", 4),
            )
            for _ in range(count)
        )
        player_ids = tuple(
            f"{position.lower()}{index}"
            for index, position in enumerate(positions, 1)
        )
        position_of = dict(zip(player_ids, positions))
        slots = {
            "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1,
        }
        state = replay_sleeper_draft(
            {
                "draft_id": "roster-policy",
                "type": "snake",
                "status": "drafting",
                "settings": {"teams": 4, "rounds": 12, "reversal_round": 0},
                "draft_order": {str(roster): roster for roster in range(1, 5)},
                "slot_to_roster_id": {str(roster): roster for roster in range(1, 5)},
            },
            picks=(),
            traded_picks=(),
            player_ids=player_ids,
        )
        league_evaluator = SimpleNamespace(
            bank=SimpleNamespace(
                player_ids=player_ids,
                player_positions=positions,
                expected_scores=tuple(
                    float(len(player_ids) - index) for index in range(len(player_ids))
                ),
                weeks=(1,),
            ),
            roster_ids=(1, 2, 3, 4),
            slot_counts=slots,
        )
        snapshot = {
            "source": SLEEPER_ADP_SOURCE,
            "snapshot_id": "roster-policy",
            "observations": [
                {"canonical_player_id": player_id, "adp": index}
                for index, player_id in enumerate(player_ids, 1)
            ],
        }
        choose = _live_opponent_choice(snapshot, league_evaluator, state, 0.11)
        completions = complete_drafts(
            state,
            None,
            1,
            range(10),
            choose,
            _projection_user_policy(league_evaluator, state, choose),
            temperature=1.0,
        )

        for completion in completions:
            for _, roster in completion.rosters:
                counts = Counter(position_of[player_id] for player_id in roster)
                self.assertEqual(starting_lineup_needs(roster, position_of, slots), ())
                self.assertLessEqual(counts["QB"], 2)
                self.assertLessEqual(counts["TE"], 2)
                self.assertEqual(counts["K"], 1)
                self.assertEqual(counts["DEF"], 1)

    def test_finalists_always_include_market_chalk_and_top_model_value(self):
        prepared = SimpleNamespace(evaluator=evaluator())
        rows = [
            {"player_id": f"p{number}", "adp": float(adp)}
            for number, adp in ((5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (3, 50))
        ]

        finalists = select_finalists(prepared, None, rows, 5)

        # p3 is the model's best value but screened last (the market prices
        # it at ADP 50), and p5 is the best remaining market pick; both are
        # guaranteed finalists so screen noise can only cost depth.
        self.assertEqual(finalists, ("p5", "p6", "p7", "p8", "p3"))

    def test_all_statistically_tied_screen_leaders_advance(self):
        prepared = SimpleNamespace(evaluator=evaluator())
        rows = [
            {
                "player_id": f"p{number}",
                "adp": float(number),
                "is_top_tier": number in {5, 6, 7, 8, 9, 10},
            }
            for number in range(1, 11)
        ]

        self.assertEqual(
            select_finalists(prepared, None, rows, 5),
            ("p1", "p5", "p6", "p7", "p8", "p9", "p10"),
        )

    def test_candidate_pool_expands_outward_from_the_current_pick(self):
        adps = {
            "p02": ("RB", 2.0),   # fallen stud
            "p09": ("WR", 9.0),
            "p10": ("WR", 10.0),  # at the anchor
            "p11": ("QB", 11.0),
            "p14": ("QB", 14.0),
            "p30": ("TE", 30.0),
            "p90": ("K", 90.0),   # never forced into the early window
        }
        prepared = SimpleNamespace(
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": player_id, "adp": adp}
                    for player_id, (_, adp) in adps.items()
                ],
            },
            evaluator=SimpleNamespace(
                bank=SimpleNamespace(
                    player_ids=tuple(adps),
                    player_positions=tuple(position for position, _ in adps.values()),
                    expected_scores=(20.0, 15.0, 14.0, 18.0, 17.0, 10.0, 5.0),
                    weeks=(1, 2, 3),
                ),
                roster_ids=(1, 2),
                slot_counts={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "K": 1},
            ),
            player_details={
                player_id: {"position": position}
                for player_id, (position, _) in adps.items()
            },
        )
        state = SimpleNamespace(
            available_player_ids=frozenset(adps),
            current_pick_no=10,
            pick_owners=(1,) * 20,
            roster_player_ids=lambda _roster_id: (),
        )
        # Best-player-available by ADP: fallers first, then the window deepens
        # down the board; the kicker enters only at its ADP depth. Top
        # value-over-replacement players (never K/DEF) always join the window
        # so an ADP cutoff cannot exclude the value model's favorite.
        self.assertEqual(
            live_candidate_pool(prepared, state, 10),
            ["p02", "p09", "p10", "p11", "p14", "p30", "p90"],
        )
        self.assertEqual(live_candidate_pool(prepared, state, 5),
                         ["p02", "p09", "p10", "p11", "p14", "p30"])
        self.assertNotIn("p90", live_candidate_pool(prepared, state, 6))
        self.assertEqual(
            live_candidate_pool(prepared, state, 5, sticky=("p30", "gone")),
            ["p30", "p02", "p09", "p10", "p11", "p14"],
        )
        with self.assertRaisesRegex(ValueError, "No available market players"):
            live_candidate_pool(
                SimpleNamespace(
                    market_snapshot=prepared.market_snapshot,
                    evaluator=prepared.evaluator,
                    player_details={},
                ),
                SimpleNamespace(available_player_ids=frozenset(), current_pick_no=1),
                5,
            )

    def test_personal_point_offsets_promote_value_entrants_only(self):
        adps = {
            "p02": ("RB", 2.0),
            "p09": ("WR", 9.0),
            "p10": ("WR", 10.0),
            "p11": ("QB", 11.0),
            "p14": ("QB", 14.0),
            "p30": ("TE", 30.0),
            "p90": ("K", 90.0),
        }

        def prepared_with(personal_ranks):
            return SimpleNamespace(
                user_roster_id=1,
                market_snapshot={
                    "source": SLEEPER_ADP_SOURCE,
                    "snapshot_id": "snap",
                    "observations": [
                        {"canonical_player_id": player_id, "adp": adp}
                        for player_id, (_, adp) in adps.items()
                    ],
                },
                evaluator=SimpleNamespace(
                    bank=SimpleNamespace(
                        player_ids=tuple(adps),
                        player_positions=tuple(
                            position for position, _ in adps.values()
                        ),
                        expected_scores=(20.0, 15.0, 14.0, 18.0, 17.0, 10.0, 5.0),
                        weeks=(1, 2, 3),
                    ),
                    roster_ids=(1, 2),
                    slot_counts={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "K": 1},
                ),
                player_details={
                    player_id: {"position": position}
                    for player_id, (position, _) in adps.items()
                },
                personal_ranks=personal_ranks,
            )

        state = SimpleNamespace(
            available_player_ids=frozenset(adps),
            current_pick_no=10,
            pick_owners=(1,) * 20,
            roster_player_ids=lambda _roster_id: (),
        )

        baseline = live_candidate_pool(prepared_with({}), state, 3)
        # +40 season points on the deep TE raise his subjective value over
        # the QBs, so he enters the evaluated window as an earlier
        # value-over-replacement entrant.
        liked = live_candidate_pool(prepared_with({"p30": 40}), state, 3)

        # The ADP head is market-ordered in both cases — offsets are point
        # opinions, not board moves.
        self.assertEqual(baseline[:3], ["p02", "p09", "p10"])
        self.assertEqual(liked[:3], ["p02", "p09", "p10"])
        self.assertLess(baseline.index("p11"), baseline.index("p30"))
        self.assertLess(liked.index("p30"), liked.index("p11"))

    def test_candidate_pool_requires_starter_positions_at_the_draft_tail(self):
        adps = {"rb": 1.0, "k": 50.0, "def": 60.0}
        positions = {"rb": "RB", "k": "K", "def": "DEF", "wr": "WR"}
        prepared = SimpleNamespace(
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": player_id, "adp": adp}
                    for player_id, adp in adps.items()
                ],
            },
            evaluator=SimpleNamespace(
                bank=SimpleNamespace(
                    player_ids=tuple(positions),
                    player_positions=tuple(positions.values()),
                    expected_scores=(12.0, 8.0, 7.0, 11.0),
                    weeks=(1, 2, 3),
                ),
                roster_ids=(1, 2),
                slot_counts={"WR": 1, "K": 1, "DEF": 1},
            ),
            player_details={
                player_id: {"position": position}
                for player_id, position in positions.items()
            },
        )
        state = SimpleNamespace(
            available_player_ids=frozenset(adps),
            current_pick_no=2,
            pick_owners=(1, 1, 1),
            roster_player_ids=lambda _roster_id: ("wr",),
        )

        self.assertEqual(live_candidate_pool(prepared, state, 10), ["k", "def"])

    def test_candidate_pool_respects_roster_position_limits(self):
        positions = {
            "qb1": "QB", "qb2": "QB", "qb3": "QB",
            "te1": "TE", "te2": "TE", "te3": "TE", "rb": "RB",
        }
        prepared = SimpleNamespace(
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": player_id, "adp": adp}
                    for player_id, adp in (("qb3", 1), ("te3", 2), ("rb", 3))
                ],
            },
            evaluator=SimpleNamespace(
                bank=SimpleNamespace(
                    player_ids=tuple(positions),
                    player_positions=tuple(positions.values()),
                    expected_scores=(20.0, 19.0, 18.0, 12.0, 11.0, 10.0, 14.0),
                    weeks=(1, 2, 3),
                ),
                roster_ids=(1, 2),
                slot_counts={"QB": 1, "RB": 1, "TE": 1},
            ),
        )
        state = SimpleNamespace(
            available_player_ids=frozenset({"qb3", "te3", "rb"}),
            current_pick_no=1,
            pick_owners=(1,) * 10,
            roster_player_ids=lambda _roster_id: ("qb1", "qb2", "te1", "te2"),
        )

        self.assertEqual(live_candidate_pool(prepared, state, 10), ["rb"])

    def test_live_state_summary_includes_the_full_pick_feed(self):
        prepared = SimpleNamespace(
            user_roster_id=None,
            player_details={
                "p1": {"name": "Alpha One", "position": "WR", "team": "BUF"},
            },
        )
        picks = tuple(
            DraftPick(
                pick_no=pick_no,
                round=1,
                draft_slot=pick_no,
                roster_id=pick_no,
                picked_by=None,
                player_id=f"p{pick_no}",
                position="RB" if pick_no == 2 else None,
                price=None,
            )
            for pick_no in (1, 2)
        )
        state = SimpleNamespace(
            draft_id="draft",
            status="drafting",
            completed_picks=picks,
            current_pick_no=3,
            current_roster_id=3,
        )
        summary = live_state_summary(prepared, state)
        self.assertEqual(summary["completed_picks"], 2)
        self.assertEqual(summary["recent_picks"], [
            {
                "pick_no": 1,
                "round": 1,
                "draft_slot": 1,
                "roster_id": 1,
                "player_id": "p1",
                "name": "Alpha One",
                "position": "WR",
                "team": "BUF",
            },
            {
                "pick_no": 2,
                "round": 1,
                "draft_slot": 2,
                "roster_id": 2,
                "player_id": "p2",
                "name": "p2",
                "position": "RB",
                "team": None,
            },
        ])

    def test_draft_url_and_id_inputs(self):
        self.assertEqual(_draft_id(" 1393634461312106496 ", "Mock"), "1393634461312106496")
        self.assertEqual(
            _draft_id(
                "https://sleeper.app/draft/nfl/1393634461312106496",
                "Mock",
            ),
            "1393634461312106496",
        )
        self.assertIsNone(_draft_id("", "Mock", required=False))
        with self.assertRaisesRegex(ValueError, "Sleeper draft ID or draft URL"):
            _draft_id("https://example.com/draft/nfl/123", "Mock")

        self.assertEqual(_manager_slot({"draft_order": {"user": 3}}, "user"), 3)
        self.assertIsNone(_manager_slot({"draft_order": {"creator": 1}}, "user"))

    def test_league_mock_must_match_real_geometry_and_market(self):
        real = {
            "league_id": "league",
            "type": "snake",
            "settings": {
                "teams": 12,
                "rounds": 15,
                "slots_qb": 1,
                "slots_flex": 1,
                "slots_bn": 6,
            },
            "metadata": {"scoring_type": "ppr"},
        }
        league_mock = {
            **real,
            "league_id": None,
            "metadata": {
                "scoring_type": "ppr",
                "type": "league_mock",
                "league_id": "league",
            },
        }
        self.assertEqual(mock_mismatch_reasons(real, league_mock), [])

        mock = {
            **league_mock,
            "settings": {**real["settings"], "teams": 10, "slots_flex": 2},
            "metadata": {"scoring_type": "std", "type": "mock"},
        }
        codes = {reason["code"] for reason in mock_mismatch_reasons(real, mock)}
        self.assertEqual(codes, {
            "mock_league_link_mismatch",
            "mock_team_count_mismatch",
            "mock_roster_slots_mismatch",
            "mock_market_context_mismatch",
        })

    def test_history_refresh_can_initialize_an_empty_store(self):
        canonical_player = SimpleNamespace(sleeper_id="s", canonical_player_id="c")
        history = object()
        with (
            TemporaryDirectory() as directory,
            patch("ffsim.draft_intel.live.CACHE_DIR", Path(directory)),
            patch("ffsim.draft_intel.live.canonical_players_from_cache", return_value=(canonical_player,)),
            patch("ffsim.draft_intel.live.load_sleeper_identity_map", return_value={}),
            patch("ffsim.draft_intel.live.load_history", return_value=history) as load,
            patch("ffsim.draft_intel.live.summarize_history", return_value={}) as summarize,
            patch("ffsim.draft_intel.live.store_history", return_value={"database_path": "db"}) as store,
        ):
            (Path(directory) / "players.json").write_text("{}")
            result = _refresh_history("league", 2026)

        load.assert_has_calls([call(
            "league",
            range(2026, 2023, -1),
            canonical_player_ids={"s": "c"},
            raw_responses={},
        )])
        summarize.assert_called_once_with(history, 2026)
        store.assert_called_once()
        self.assertEqual(result["storage"], {"database_path": "db"})


if __name__ == "__main__":
    unittest.main()
