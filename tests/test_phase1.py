import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from ffsim.loaders.data_merger import DataMerger
from ffsim.models.league import League
from ffsim.models.player import Player, mean_preserving_lognormal
from ffsim.models.team import FantasyTeam
from ffsim.scoring import DIRECT_KEYS, ScoringSettings, score_raw_stats
from ffsim.simulation.monte_carlo import MonteCarloSimulation
from ffsim.simulation.season import SimulationSeason
from ffsim.simulation.tracker import SimulationTracker


def projection(**values):
    data = {
        "games": 17,
        "byeWeek": 18,
        "fantasyPoints": 0,
        "passComp": 0,
        "passAtt": 0,
        "passYds": 0,
        "passTd": 0,
        "passInt": 0,
        "passSacked": 0,
        "rushAtt": 0,
        "rushYds": 0,
        "rushTd": 0,
        "recvTargets": 0,
        "recvReceptions": 0,
        "recvYds": 0,
        "recvTd": 0,
        "fumbles": 0,
        "fumblesLost": 0,
        "twoPt": 0,
        "returnYds": 0,
        "returnTd": 0,
        "fgMade019": 0,
        "fgAtt019": 0,
        "fgMade2029": 0,
        "fgAtt2029": 0,
        "fgMade3039": 0,
        "fgAtt3039": 0,
        "fgMade4049": 0,
        "fgAtt4049": 0,
        "fgMade50plus": 0,
        "fgAtt50plus": 0,
        "patMade": 0,
        "patAtt": 0,
        "dstSacks": 0,
        "dstSafeties": 0,
        "dstInt": 0,
        "dstFumblesForced": 0,
        "dstFumblesRecovered": 0,
        "dstTd": 0,
        "dstReturnYds": 0,
        "dstReturnTd": 0,
        "dstPts0": 0,
        "dstPts16": 0,
        "dstPts713": 0,
        "dstPts1420": 0,
        "dstPts2127": 0,
        "dstPts2834": 0,
        "dstPts35plus": 0,
    }
    data.update(values)
    return data


def player(name="Player", position="WR", team="BUF", **values):
    return Player(
        {
            "player_id": name,
            "full_name": name,
            "position": position,
            "team": team,
            "projection_match_status": "matched",
            "pff_projections": projection(**values),
        }
    )


class ProjectionJoinTest(unittest.TestCase):
    def test_exact_name_position_team_join_has_no_collision_borrowing(self):
        sleeper = pd.DataFrame(
            [
                {"player_id": "1", "full_name": "Jalen Hurd", "position": "WR", "team": "SF"},
                {"player_id": "2", "full_name": "Jalen Hurts", "position": "QB", "team": "PHI"},
                {"player_id": "3", "full_name": "Josh Johnson", "position": "QB", "team": "BLT"},
                {"player_id": "4", "full_name": "Roschon Johnson", "position": "RB", "team": "CHI"},
            ]
        )
        pff = pd.DataFrame(
            [
                {"playerName": "Jalen Hurts", "position": "QB", "teamName": "PHI", "games": 17, "byeWeek": 1, "normalized_name": "jalenhurts", "canonical_team": "PHI"},
                {"playerName": "Roschon Johnson", "position": "RB", "teamName": "CHI", "games": 17, "byeWeek": 1, "normalized_name": "roschonjohnson", "canonical_team": "CHI"},
                {"playerName": "Josh Johnson", "position": "RB", "teamName": "BLT", "games": 17, "byeWeek": 1, "normalized_name": "joshjohnson", "canonical_team": "BAL"},
            ]
        )
        fantasy = pd.DataFrame(columns=["sleeper_id", "value_1qb", "redraft_value"])

        merged = DataMerger.merge_data(fantasy, sleeper, pff)
        statuses = dict(zip(merged.player_id, merged.projection_match_status))
        first_report = json.dumps(DataMerger.last_projection_report, sort_keys=True)
        DataMerger.merge_data(fantasy, sleeper, pff)

        self.assertEqual(statuses, {"1": "unmatched", "2": "matched", "3": "unmatched", "4": "matched"})
        self.assertEqual(first_report, json.dumps(DataMerger.last_projection_report, sort_keys=True))
        self.assertTrue(all(merged.loc[merged.player_id.isin(["2", "4"]), "position"] == merged.loc[merged.player_id.isin(["2", "4"]), "position_pff"]))

    def test_duplicate_active_identity_is_ambiguous(self):
        sleeper = pd.DataFrame([
            {"player_id": "1", "full_name": "Same Name", "position": "WR", "team": "LA"},
            {"player_id": "2", "full_name": "Same Name", "position": "WR", "team": "LAR"},
        ])
        pff = pd.DataFrame([{"playerName": "Same Name", "position": "WR", "teamName": "LA", "games": 17, "byeWeek": 1, "normalized_name": "samename", "canonical_team": "LAR"}])
        merged = DataMerger.merge_data(pd.DataFrame(columns=["sleeper_id"]), sleeper, pff)
        self.assertEqual(set(merged.projection_match_status), {"ambiguous"})
        self.assertTrue(merged._projection_index.isna().all())

    def test_stable_id_wins_when_team_changed_but_position_matches(self):
        sleeper = pd.DataFrame([{"player_id": "9", "full_name": "New Name", "position": "WR", "team": "BUF"}])
        pff = pd.DataFrame([{"sleeperId": "9", "playerName": "Old Name", "position": "WR", "teamName": "KC", "games": 17, "byeWeek": 1, "normalized_name": "oldname", "canonical_team": "KC"}])
        merged = DataMerger.merge_data(pd.DataFrame(columns=["sleeper_id"]), sleeper, pff)
        self.assertEqual(merged.iloc[0].projection_match_status, "matched")


class ScoringTest(unittest.TestCase):
    def test_every_direct_scoring_key_has_a_golden_raw_stat(self):
        for key, stat in DIRECT_KEYS.items():
            with self.subTest(key=key):
                self.assertEqual(score_raw_stats({stat: 3}, "QB", {key: 2}), 6)

    def test_reception_bonus_adds_to_base_reception_score(self):
        self.assertEqual(score_raw_stats({"receptions": 4}, "TE", {"rec": 1, "bonus_rec_te": 0.5}), 6)

    def test_combined_projection_fields_require_equal_league_coefficients(self):
        settings = {"pass_2pt": 2, "rush_2pt": 2, "rec_2pt": 2, "kr_yd": 0.1, "pr_yd": 0.1}
        self.assertEqual(score_raw_stats({"two_point_conversions": 1, "return_yards": 10}, "RB", settings), 3)
        with self.assertRaisesRegex(ValueError, "kr_yd, pr_yd"):
            ScoringSettings({"kr_yd": 0.1, "pr_yd": 0.05})

    def test_unsupported_nonzero_keys_are_listed(self):
        with self.assertRaisesRegex(ValueError, "bonus_pass_yd_300, rec_td_50p"):
            ScoringSettings({"rec_td_50p": 2, "bonus_pass_yd_300": 1})


class CenteringAndAvailabilityTest(unittest.TestCase):
    def test_lognormal_arithmetic_mean_is_centered(self):
        rng = np.random.default_rng(4)
        samples = [mean_preserving_lognormal(12, 0.5, rng) for _ in range(100_000)]
        self.assertAlmostEqual(float(np.mean(samples)), 12, delta=0.12)

    def test_parametric_player_vector_is_centered_and_logical(self):
        subject = player(
            position="QB", passComp=340, passAtt=510, passYds=4250, passTd=34,
            passInt=12, rushAtt=85, rushYds=510, rushTd=5, recvTargets=17,
            recvReceptions=8.5, recvYds=85, recvTd=1.7, fumbles=8.5,
            fumblesLost=3.4, twoPt=1.7,
        )
        rng = np.random.default_rng(5)
        samples = [subject.sample_parametric_stats(rng) for _ in range(100_000)]
        means = subject.season_raw_stats()
        for stat in ("completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries", "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds", "fumbles", "fumbles_lost", "two_point_conversions"):
            with self.subTest(stat=stat):
                self.assertAlmostEqual(np.mean([row[stat] for row in samples]), means[stat] / 17, delta=max(0.015, means[stat] / 1700))
        self.assertTrue(all(row["completions"] <= row["attempts"] and row["receptions"] <= row["targets"] for row in samples))
        self.assertTrue(all((row["receptions"] > 0 or (row["receiving_yards"] == 0 and row["receiving_tds"] == 0)) for row in samples))

    def test_reduced_games_preserve_reduced_season_total(self):
        subject = player(games=8.5, recvTargets=102, recvReceptions=85, recvYds=850)
        settings = ScoringSettings({"rec": 1, "rec_yd": 0.1})
        totals = []
        root = np.random.SeedSequence(8)
        for stream in root.spawn(10_000):
            rng = np.random.default_rng(stream)
            subject.prepare_availability(range(1, 19), rng)
            totals.append(sum(subject.calculate_score(settings, week, rng) for week in range(1, 19)))
            subject.reset_season_stats()
        self.assertAlmostEqual(np.mean(totals), subject.projected_season_score(settings), delta=1.7)

    def test_kicker_and_defense_fallback_means_are_centered(self):
        kicker = player(position="K", fgMade2029=17, fgAtt2029=20.4, fgMade50plus=8.5, fgAtt50plus=10.2, patMade=34, patAtt=37.4)
        defense = player(position="DEF", dstSacks=51, dstInt=17, dstTd=3.4, dstPts0=1.7, dstPts16=3.4, dstPts713=5.1, dstPts1420=3.4, dstPts2127=1.7, dstPts2834=0.85, dstPts35plus=0.85)
        settings = ScoringSettings({"fgm": 3, "fgm_50p": 2, "fgmiss": -1, "xpm": 1, "xpmiss": -1, "sack": 1, "int": 2, "def_td": 6, "pts_allow_0": 10, "pts_allow_1_6": 7, "pts_allow_7_13": 4, "pts_allow_14_20": 1, "pts_allow_28_34": -1, "pts_allow_35p": -4})
        rng = np.random.default_rng(9)
        for subject in (kicker, defense):
            scores = [score_raw_stats(subject.sample_parametric_stats(rng), subject.position, settings) for _ in range(150_000)]
            self.assertAlmostEqual(np.mean(scores), subject.expected_weekly_score(settings), delta=0.08)
        self.assertLess(min(score_raw_stats(defense.sample_parametric_stats(rng), "DEF", settings) for _ in range(10_000)), 0)


class LineupAndTrackerTest(unittest.TestCase):
    def test_bye_player_cannot_start_or_score(self):
        league = League({"roster_positions": ["WR"], "scoring_settings": {"rec": 1}})
        team = FantasyTeam("Team", league)
        bye = player("Bye", byeWeek=6, recvReceptions=170)
        replacement = player("Replacement", byeWeek=7, recvReceptions=17)
        team.add_player(bye)
        team.add_player(replacement)
        team.fill_starters(6)
        self.assertEqual(team.starters["WR"], [replacement])
        self.assertEqual(bye.calculate_score(league.scoring_settings, 6, np.random.default_rng(1)), 0)

    def test_kicker_and_defense_byes_also_force_replacements(self):
        league = League({"roster_positions": ["K", "DEF"], "scoring_settings": {"xpm": 1, "sack": 1}})
        team = FantasyTeam("Team", league)
        players = (
            player("Bye K", position="K", byeWeek=6, patMade=170),
            player("Active K", position="K", byeWeek=7, patMade=17),
            player("Bye DEF", position="DEF", byeWeek=6, dstSacks=170),
            player("Active DEF", position="DEF", byeWeek=7, dstSacks=17),
        )
        for subject in players:
            team.add_player(subject)
        team.fill_starters(6)
        self.assertEqual([subject.name for subject in team.starters["K"]], ["Active K"])
        self.assertEqual([subject.name for subject in team.starters["DEF"]], ["Active DEF"])

    def test_lineup_uses_projection_not_realized_history(self):
        league = League({"roster_positions": ["WR"], "scoring_settings": {"rec": 1}})
        team = FantasyTeam("Team", league)
        strong = player("Strong", recvReceptions=170)
        weak = player("Weak", recvReceptions=17)
        weak.record_weekly_score(100)
        team.add_player(strong)
        team.add_player(weak)
        team.fill_starters(2)
        self.assertEqual(team.starters["WR"], [strong])

    def test_tracker_keeps_zero_and_negative_played_scores(self):
        tracker = SimulationTracker(None, 1)
        for score in (0, -2, 4):
            tracker.record_player_score("p", 1, score, played=True)
        tracker.record_player_score("p", 2, 0, played=False)
        self.assertEqual(tracker.get_player_average_score("p"), (2 / 3, 2, 3, -2, 4))


class CompletedAndReproducibilityTest(unittest.TestCase):
    def test_completed_sleeper_week_is_applied_exactly(self):
        league = League({"league_id": "x", "settings": {"last_scored_leg": 1}, "roster_positions": []})
        home, away = FantasyTeam("Home", league), FantasyTeam("Away", league)
        home.roster_id, away.roster_id = 1, 2
        league.rosters = [home, away]
        snapshot = {"1": [
            {"roster_id": 1, "matchup_id": 1, "points": 101.25, "custom_points": None, "starters": ["a"]},
            {"roster_id": 2, "matchup_id": 1, "points": 99.75, "custom_points": None, "starters": ["b"]},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "matchups_x.json").write_text(json.dumps(snapshot))
            with patch("ffsim.simulation.season.CACHE_DIR", Path(directory)):
                season = SimulationSeason(league, SimulationTracker(league, 1), weeks=1, rng=np.random.default_rng(1))
                season._apply_completed_regular_season(1)
        self.assertEqual((home.wins, home.points_for, home.points_against), (1, 101.25, 99.75))
        self.assertEqual(league.completed_starters[(1, 1)], ("a",))

    def test_same_seed_and_reused_object_are_identical(self):
        teams = [SimpleNamespace(name=f"T{i}", roster_id=i, wins=0, losses=0, ties=0, points_for=0.0, points_against=0.0, players=[], reset_stats=lambda: None) for i in range(6)]
        league = SimpleNamespace(league_id="x", name="L", rosters=teams, divisions={1: [0, 1, 2], 2: [3, 4, 5]})

        class FakeSeason:
            def __init__(self, league, tracker, weeks, rng):
                self.league, self.tracker, self.rng = league, tracker, rng
            def simulate(self):
                for team in self.league.rosters:
                    team.wins = int(self.rng.integers(0, 15))
                    team.points_for = float(self.rng.integers(1000, 2000))
                bracket = SimpleNamespace(teams=self.league.rosters, division1_winner=self.league.rosters[0], division2_winner=self.league.rosters[3])
                self.playoff_sim = SimpleNamespace(bracket=bracket, champion=self.league.rosters[0])

        simulation = MonteCarloSimulation(league, num_simulations=4, seed=42)
        with patch("ffsim.simulation.monte_carlo.SimulationSeason", FakeSeason):
            first = simulation.run()
            second = simulation.run()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
