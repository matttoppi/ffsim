import itertools
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ffsim.guillotine import (
    analyze, best_ball_totals, bid_limits, chop_shares, projection_map,
    weekly_player,
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

    def test_bid_caps_respect_budget_competition_and_horizon(self):
        self.assertEqual(bid_limits(1000, [1000], 10, 1 / 11, 11, 5), (75, 100))
        self.assertEqual(bid_limits(1000, [30], 1, 0.5, 2, 20), (23, 31))
        self.assertEqual(bid_limits(0, [1000], 10, 0.5, 11, 5), (0, 0))
        self.assertEqual(bid_limits(1000, [1000], 10, 0.5, 11, 0), (0, 0))
        self.assertGreater(bid_limits(1000, [1000], 5, 0.2, 6, 5)[1],
                           bid_limits(1000, [1000], 10, 0.2, 6, 5)[1])
        for kwargs in ({"aggression": float("nan")}, {"rounds_left": 0}):
            arguments = dict(budget=1000, rival_budgets=[1000], rounds_left=10, risk=.2, teams=11, gain=5)
            arguments.update(kwargs)
            with self.assertRaises(ValueError):
                bid_limits(**arguments)

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
        self.assertLessEqual(row["max_bid"], 801)
        # nflverse uses LA while Sleeper uses LAR. This is not a bye.
        snapshot["players"]["1"]["team"] = "LAR"
        schedule.return_value.loc[0, "away_team"] = "LA"
        self.assertEqual(analyze(snapshot, simulations=100)["baseline_expected_points"], 10)
        snapshot["rosters"][0]["players"] = ["1"]
        self.assertIsNone(analyze(snapshot, simulations=100)["recommendations"][0]["drop_id"])
        snapshot["players"]["4"]["injury_status"] = "Out"
        row = analyze(snapshot, simulations=100)["recommendations"][0]
        self.assertEqual((row["max_bid"], row["points_gain"]), (0, 0))
        snapshot["projections"]["players"] = []
        with self.assertRaisesRegex(ValueError, "Missing weekly projection"):
            analyze(snapshot, simulations=100)


if __name__ == "__main__":
    unittest.main()
