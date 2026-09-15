import itertools
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ffsim.guillotine import (
    analyze, best_ball_totals, chop_shares, format_report, player_bid_range,
    projection_map, rest_of_season_ranks, spending_plan, weekly_player,
)
from ffsim.models.team import FLEX_ELIGIBILITY
from ffsim.scoring import ScoringSettings


def fixture():
    ids = ["1", "2", "3", "4"]
    return {
        "retrieved_at": "2026-09-15T12:00:00+00:00", "week": 2,
        "league": {
            "league_id": "test", "name": "Chopped", "season": "2026",
            "settings": {"type": 3, "best_ball": 1, "last_scored_leg": 1,
                         "waiver_type": 2, "waiver_budget": 1000},
            "roster_positions": ["WR", "BN"], "scoring_settings": {"rec": 1},
        },
        "user": {"user_id": "me", "display_name": "Me"},
        "rosters": [
            {"roster_id": 1, "owner_id": "me", "players": ["1", "2"],
             "settings": {"fpts": 10, "waiver_budget_used": 100}},
            {"roster_id": 2, "owner_id": "them", "players": ["3"],
             "settings": {"fpts": 20, "waiver_budget_used": 200}},
            {"roster_id": 3, "owner_id": "gone", "players": None,
             "settings": {"eliminated": 1}},
        ],
        "players": {sid: {"full_name": f"Player {sid}", "position": "WR",
                          "fantasy_positions": ["WR"], "team": "NE",
                          "sportradar_id": f"external-{sid}"} for sid in ids},
        "projections": {"season": "2026", "week": "2", "players": [
            {"fpid": sid, "position_id": "WR", "stats": {"rec_rec": int(sid)}} for sid in ids
        ]},
        "projection_players": {"players": [
            {"player_id": sid, "sportsdata_player_id": f"external-{sid}"} for sid in ids
        ]},
        "rest_of_season_rankings": {
            "year": "2026", "ranking_type_name": "ros", "scoring": "PPR",
            "position_id": "ALL", "last_updated": "9/15", "total_experts": 1,
            "players": [{"player_id": sid, "player_position_id": "WR", "pos_rank": f"WR{sid}"} for sid in ids],
        },
        "transactions": [{"type": "chopped", "status": "complete", "leg": 1,
                          "drops": {"4": 3}}],
    }


class GuillotineTest(unittest.TestCase):
    def test_best_ball_matches_exhaustive_legal_lineups(self):
        positions = ["QB", "QB", "RB", "RB", "WR", "WR", "TE"]
        slots = ["QB", "RB", "FLEX", "SUPER_FLEX"]
        scores = np.random.default_rng(11).integers(-3, 30, (12, len(positions))).astype(float)
        eligible = [FLEX_ELIGIBILITY.get(slot, {slot}) for slot in slots]
        lineups = [
            lineup for lineup in itertools.permutations(range(len(positions)), len(slots))
            if all(positions[player] in allowed for player, allowed in zip(lineup, eligible))
        ]
        expected = np.array([max(row[list(lineup)].sum() for lineup in lineups) for row in scores])
        np.testing.assert_array_equal(best_ball_totals(scores, positions, slots), expected)
        # A backup's spike week counts, and an empty required position adds no streamer.
        np.testing.assert_array_equal(
            best_ball_totals(np.array([[5., 25.], [20., 2.]]), ["WR", "WR"], ["WR", "RB"]),
            [25., 20.],
        )
        np.testing.assert_array_equal(best_ball_totals(np.zeros((2, 0)), [], ["WR"]), [0., 0.])

    def test_chop_tiebreak_uses_season_points_and_first_week_draft_order(self):
        rosters = [
            {"settings": {"fpts": 100, "fpts_decimal": 5, "draft_position": 1}},
            {"settings": {"fpts": 100, "fpts_decimal": 4, "draft_position": 2}},
        ]
        totals = np.array([[20., 20.], [10., 11.]])
        np.testing.assert_array_equal(chop_shares(totals, rosters, 2), [[0, 1], [1, 0]])
        np.testing.assert_array_equal(chop_shares(totals, rosters, 1), [[1, 0], [1, 0]])

    def test_spending_limit_covers_all_claims_that_can_win_together(self):
        rows = [dict(player_id=str(i), drop_id=drop, action="consider",
                     risk_reduction=.02 if i < 2 else .007, risk_reduction_standard_error=.001,
                     position="WR", points_gain=10 if i < 2 else 1,
                     rest_of_season_position_rank=2 if i < 2 else 60)
                for i, drop in enumerate(["mayer", "mayer", "black", None, None])]
        plan = spending_plan(rows, 1000, .05, 11)
        self.assertEqual([r["bid_range"] for r in plan["recommendations"]],
                         [[50, 150], [50, 150], [0, 5], [0, 5], None])
        self.assertEqual((plan["weekly_cap"], plan["maximum_plan_spend"]), (160, 160))
        self.assertNotIn("bid_range", rows[0])  # Do not mutate simulation results.
        # Two bids sharing a drop cost at most the higher bid, not their sum.
        chosen = {"0": 20, "1": 15, "2": 3, "3": 1, "4": 1}
        plan = spending_plan(rows, 1000, .05, 11, 25, chosen)
        self.assertEqual(plan["maximum_plan_spend"], 25)
        for subset in itertools.product([False, True], repeat=len(rows)):
            winners = [r for r, wins in zip(plan["recommendations"], subset) if wins]
            groups = [r["claim_group"] for r in winners]
            if len(groups) == len(set(groups)):
                self.assertLessEqual(sum(r["bid_range"][1] for r in winners), 25)
        with self.assertRaisesRegex(ValueError, "can spend.*weekly limit"):
            spending_plan(rows, 1000, .05, 11, 24, chosen)
        with self.assertRaisesRegex(ValueError, "not available"):
            spending_plan(rows, 1000, .05, 11, bids={"unknown": 1})
        for invalid in (-1, 1.5, float("nan"), float("inf"), True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                spending_plan(rows, 1000, .05, 11, invalid)
        self.assertLessEqual(spending_plan(rows, 2, .05, 11)["maximum_plan_spend"], 2)
        self.assertEqual(spending_plan(rows, 0, .05, 11)["maximum_plan_spend"], 0)
        limited = spending_plan(rows, 1000, .05, 11, weekly_cap=5, spent=3)
        self.assertEqual(limited["maximum_plan_spend"], 2)
        self.assertEqual(limited["recommendations"][0]["recommended_bid_range"], [50, 155])
        self.assertIsNone(limited["recommendations"][0]["bid_range"])
        self.assertEqual(spending_plan(rows, 1000, .05, 11, weekly_cap=5, spent=9)["maximum_plan_spend"], 0)
        with self.assertRaisesRegex(ValueError, "remaining weekly limit"):
            spending_plan(rows, 1000, .05, 11, weekly_cap=5, bids={"0": 3}, spent=3)

    def test_lasting_value_roster_fit_urgency_and_stage_change_ranges(self):
        elite = dict(player_id="1", drop_id="mayer", action="consider", position="WR",
                     rest_of_season_position_rank=2, points_gain=11.2,
                     risk_reduction=.0296, risk_reduction_standard_error=.0025)
        self.assertEqual(player_bid_range(elite, 1000, .05, 11), ("Elite starter", [50, 150]))
        core = {**elite, "rest_of_season_position_rank": 20, "points_gain": 5}
        self.assertEqual(player_bid_range(core, 1000, .05, 11), ("Core starter", [10, 35]))
        temporary = {**core, "rest_of_season_position_rank": 50}
        self.assertEqual(player_bid_range(temporary, 1000, .05, 11), ("Short-term upgrade", [5, 20]))
        depth = {**elite, "points_gain": 1.5, "risk_reduction": .0076, "risk_reduction_standard_error": .0017}
        self.assertEqual(player_bid_range(depth, 1000, .05, 11), ("Marginal depth", [0, 5]))
        self.assertEqual(player_bid_range(depth, 1000, .4, 4), ("Marginal depth", [0, 5]))
        self.assertEqual(player_bid_range(elite, 1000, .2, 11), ("Elite starter", [100, 300]))
        self.assertEqual(player_bid_range(elite, 1000, .05, 4), ("Elite starter", [75, 225]))
        self.assertEqual(player_bid_range(elite, 1000, .5, 2), ("Final-week upgrade", [500, 1000]))
        final_week = spending_plan([elite], 50, .5, 2, spent=950)
        self.assertEqual((final_week["weekly_cap"], final_week["weekly_remaining"], final_week["maximum_plan_spend"]),
                         (1000, 50, 50))
        uncertain = {**depth, "risk_reduction": .0006}
        self.assertEqual(player_bid_range(uncertain, 1000, .05, 11), ("Free only", [0, 0]))
        self.assertEqual(player_bid_range({**uncertain, "risk_reduction": 0}, 1000, 0, 11)[1], [0, 0])
        # Future value survives a quiet weekly risk estimate; urgency does not.
        self.assertEqual(player_bid_range({**elite, "risk_reduction": 0}, 1000, 0, 11)[1], [50, 150])
        unranked = {**temporary, "rest_of_season_position_rank": None}
        self.assertEqual(player_bid_range(unranked, 1000, .05, 11)[0], "Short-term upgrade")
        elite["action"] = "pass"
        self.assertIsNone(spending_plan([elite], 1000, .05, 11)["recommendations"][0]["bid_range"])
        with self.assertRaisesRegex(ValueError, "pass candidate"):
            spending_plan([elite], 1000, .05, 11, bids={"1": 0})

    def test_rest_of_season_identity_and_missing_or_wrong_source(self):
        snapshot = fixture()
        self.assertEqual(rest_of_season_ranks(snapshot)["4"], 4)
        snapshot["players"]["4"].update(position="DB", fantasy_positions=["DB", "WR"])
        self.assertEqual(rest_of_season_ranks(snapshot)["4"], 4)
        for field, invalid in (("year", "2025"), ("ranking_type_name", "weekly"), ("scoring", "STD"), ("players", [])):
            changed = {**snapshot, "rest_of_season_rankings": {**snapshot["rest_of_season_rankings"], field: invalid}}
            with self.subTest(field=field), self.assertRaises(ValueError):
                rest_of_season_ranks(changed)
        snapshot["rest_of_season_rankings"]["players"].append(snapshot["rest_of_season_rankings"]["players"][-1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            rest_of_season_ranks(snapshot)
        del snapshot["rest_of_season_rankings"]
        with self.assertRaisesRegex(ValueError, "refresh league inputs"):
            rest_of_season_ranks(snapshot)

    def test_stable_identity_accepts_hunter_wr_eligibility_and_rejects_bad_data(self):
        snapshot = fixture()
        snapshot["players"]["4"].update(position="DB", fantasy_positions=["DB", "WR"])
        self.assertIn("4", projection_map(snapshot, snapshot["players"]))
        snapshot["projections"]["players"].append(snapshot["projections"]["players"][-1])
        with self.assertRaisesRegex(ValueError, "Duplicate projection"):
            projection_map(snapshot, snapshot["players"])
        snapshot["projections"]["week"] = "1"
        with self.assertRaisesRegex(ValueError, "season/week"):
            projection_map(snapshot, snapshot["players"])

    def test_weekly_means_keep_te_premium_and_kicker_distance_scoring(self):
        class Library:
            player_rows = pd.DataFrame([{
                "position": "TE", "targets": 100, "receptions": 80,
                "fumbles": 10, "fumbles_lost": 4,
            }])
            team_rows = pd.DataFrame([{
                "position": "K", "extra_points_missed": 2, "extra_points_made": 100,
                **{f"field_goals_{outcome}_{bucket}": value
                   for outcome, value in (("made", 10), ("missed", 2))
                   for bucket in ("0_19", "20_29", "30_39", "40_49", "50_plus")},
            }])

            def projected_stats(self, player, stats):
                return stats

        player = weekly_player("1", {"full_name": "TE"}, {
            "position_id": "TE", "stats": {"rec_rec": 4, "rec_yds": 50, "fumbles": 0.5},
        }, Library())
        settings = ScoringSettings({"rec": 1, "bonus_rec_te": .5, "rec_yd": .1, "fum_lost": -2})
        self.assertAlmostEqual(player.expected_weekly_score(settings), 10.6)
        self.assertEqual(player.projected_games, 1)
        self.assertEqual(player.season_raw_stats()["targets"], 5)
        kicker = weekly_player("2", {}, {"position_id": "K", "stats": {"fg": 2, "fga": 2.5, "xpt": 3}}, Library())
        stats = kicker.season_raw_stats()
        self.assertAlmostEqual(stats["field_goals_made"], 2)
        self.assertAlmostEqual(stats["field_goals_missed"], .5)
        self.assertAlmostEqual(stats["extra_points_missed"], .06)

    @patch("ffsim.guillotine.EmpiricalLibrary")
    @patch("ffsim.guillotine.pd.read_csv")
    @patch("ffsim.guillotine.weekly_player")
    def test_paired_analysis_drop_selection_open_spot_and_inactive_players(self, make_player, schedule, library):
        schedule.return_value = pd.DataFrame([{
            "season": 2026, "game_type": "REG", "week": 2, "home_team": "NE", "away_team": "NYJ",
        }])

        class Player:
            def __init__(self, sid):
                self.sid = sid

            def calculate_score(self, scoring, week, rng):
                return float({"1": 10, "2": 1, "3": 11, "4": 20}[self.sid])

        make_player.side_effect = lambda sid, *args: Player(sid)
        snapshot = fixture()
        first = analyze(snapshot, simulations=100)
        second = analyze(snapshot, simulations=100)
        self.assertEqual(first, second)
        self.assertEqual(first["teams_remaining"], 2)
        row = first["recommendations"][0]
        self.assertEqual((first["baseline_chop_risk"], row["chop_risk"]), (1, 0))
        self.assertEqual(row["points_gain"], 10)
        self.assertEqual(row["drop_id"], "2")
        self.assertEqual(row["risk_reduction_standard_error"], 0)
        self.assertEqual(row["bid_range"], [450, 900])
        self.assertEqual(first["maximum_plan_spend"], 900)
        rendered = format_report(first)
        self.assertIn("Weekly limit: $900 total", rendered)
        self.assertIn("$450–$900", rendered)
        self.assertNotIn("Suggested", rendered)
        self.assertNotIn("suggested_bid", row)
        snapshot["transactions"].extend([
            {"type": "waiver", "status": "complete", "leg": leg,
             "roster_ids": [roster], "settings": {"waiver_bid": bid}}
            for leg, roster, bid in [(2, 1, 3), (2, 2, 10), (1, 1, 10)]
        ])
        refreshed = analyze(snapshot, simulations=100, weekly_cap=500)
        self.assertEqual((refreshed["weekly_spent"], refreshed["maximum_plan_spend"]), (3, 497))
        # nflverse uses LA while Sleeper uses LAR. This is not a bye.
        snapshot["players"]["1"]["team"] = "LAR"
        schedule.return_value.loc[0, "away_team"] = "LA"
        self.assertEqual(analyze(snapshot, simulations=100)["baseline_expected_points"], 10)
        snapshot["rosters"][0]["players"] = ["1"]
        self.assertIsNone(analyze(snapshot, simulations=100)["recommendations"][0]["drop_id"])
        snapshot["players"]["4"]["injury_status"] = "Out"
        row = analyze(snapshot, simulations=100)["recommendations"][0]
        self.assertEqual((row["bid_range"], row["points_gain"]), (None, 0))
        snapshot["projections"]["players"] = []
        with self.assertRaisesRegex(ValueError, "Missing weekly projection"):
            analyze(snapshot, simulations=100)


if __name__ == "__main__":
    unittest.main()
