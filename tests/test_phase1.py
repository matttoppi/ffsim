import json
import io
import pickle
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import patch

import numpy as np
import pandas as pd

from ffsim.loaders.data_merger import DataMerger
from ffsim.loaders.league import LeagueLoader
from ffsim.models.league import League
from ffsim.models.player import PFFProjections, Player, mean_preserving_lognormal
from ffsim.models.team import FantasyTeam
from ffsim.scoring import DIRECT_KEYS, ScoringSettings, score_raw_stats
from ffsim.simulation.monte_carlo import MonteCarloSimulation
from ffsim.simulation.scenarios import apply_scenario
from ffsim.simulation.season import SimulationSeason, refresh_matchups
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
    def test_unmatched_rostered_player_is_reported_but_ambiguity_fails(self):
        snapshot = {
            "league": {"league_id": "x", "name": "League", "roster_positions": []},
            "rosters": [{"roster_id": 1, "owner_id": "u", "players": ["p"]}],
            "users": [{"user_id": "u", "display_name": "Owner", "metadata": {}}],
        }

        class Loader:
            def __init__(self, status):
                self.status = status
            def ensure_players_loaded(self):
                pass
            def load_player(self, player_id):
                return Player({
                    "player_id": player_id,
                    "full_name": "Missing Player",
                    "position": "WR",
                    "team": "BUF",
                    "projection_match_status": self.status,
                })

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "league_x.json").write_text(json.dumps(snapshot))
            with patch("ffsim.loaders.league.CACHE_DIR", Path(directory)):
                output = io.StringIO()
                with redirect_stdout(output):
                    league = LeagueLoader("x", Loader("unmatched")).load_league()
                self.assertEqual(league.rosters[0].players[0].name, "Missing Player")
                self.assertIn("without 2026 projections", output.getvalue())
                with self.assertRaisesRegex(ValueError, "no unique position-consistent"):
                    LeagueLoader("x", Loader("ambiguous")).load_league()

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
        split = {"kick_return_yards": 10, "punt_return_yards": 5}
        self.assertEqual(score_raw_stats(split, "RB", {"kr_yd": 0.05, "pr_yd": 0.1}), 1)
        with self.assertRaisesRegex(ValueError, "Separate kick_return_yards"):
            score_raw_stats({"return_yards": 10}, "RB", {"kr_yd": 0.1, "pr_yd": 0.05})

    def test_long_pass_yards_allowed_and_60_plus_kick_league_is_supported(self):
        settings = ScoringSettings({
            "pass_td": 4, "pass_td_40p": 1, "pass_td_50p": 0.5, "fgm_60p": 1,
            "yds_allow_0_100": 5, "yds_allow_350_399": -1, "yds_allow_550p": -7,
        })
        stats = {
            "passing_tds": 3, "passing_tds_40_plus": 2, "passing_tds_50_plus": 1,
            "yards_allowed_350_399": 1, "field_goals_made_60_plus": 1,
        }
        self.assertEqual(score_raw_stats(stats, "QB", settings), 12 + 2 + 0.5 - 1 + 1)

    def test_yards_allowed_bins_partition_all_outcomes(self):
        from ffsim.simulation.empirical import YARDS_ALLOWED_BINS

        edges = [bounds for _, *bounds in YARDS_ALLOWED_BINS]
        self.assertEqual(edges[0][0], 0)
        self.assertEqual(edges[-1][1], float("inf"))
        for (_, upper), (lower, _) in zip(edges, edges[1:]):
            self.assertEqual(upper, lower)

    def test_unsupported_nonzero_keys_are_listed(self):
        with self.assertRaisesRegex(ValueError, "bonus_pass_yd_300, pass_fd"):
            ScoringSettings({"pass_fd": 0.5, "bonus_pass_yd_300": 1})

    def test_position_compilation_keeps_only_relevant_nonzero_terms(self):
        settings = ScoringSettings({"pass_yd": 0.04, "pass_td": 4, "rush_yd": 0.1})
        subject = player(position="QB", passYds=4250, passTd=34)
        expected = score_raw_stats(subject.modeled_weekly_raw_stats(), "QB", settings)

        settings.compile_positions([subject])

        self.assertEqual(
            settings.direct_coefficients_by_position["QB"],
            (("passing_yards", 0.04), ("passing_tds", 4.0)),
        )
        self.assertEqual(score_raw_stats(subject.modeled_weekly_raw_stats(), "QB", settings), expected)

    def test_scoring_and_projection_models_survive_worker_serialization(self):
        settings = pickle.loads(pickle.dumps(ScoringSettings({"rec": 1})))
        projections = pickle.loads(pickle.dumps(PFFProjections({"games": 17})))

        self.assertEqual(settings.rec, 1)
        self.assertTrue(projections)


class CenteringAndAvailabilityTest(unittest.TestCase):
    def test_scenario_combines_projections_and_controls_availability(self):
        subject = player(name="Scenario", recvReceptions=100, recvYds=1000)
        league = League({"roster_positions": ["WR"], "scoring_settings": {"rec": 1, "rec_yd": 0.1}})
        team = FantasyTeam("Team", league)
        team.add_player(subject)
        league.rosters = [team]
        pff_points = subject.projected_season_score(league.scoring_settings)

        apply_scenario(league, {"players": {"Scenario": {
            "projection_points": [pff_points * 1.2],
            "projected_games": 12,
            "play_probability": {"1": 0, "2": 1},
            "missed_weeks": [3],
        }}})
        subject.prepare_availability([1, 2, 3], np.random.default_rng(1))

        self.assertEqual(subject.projection_multiplier, 1.0)
        self.assertAlmostEqual(subject.season_cv, np.hypot(0.2, 0.1))
        self.assertEqual(subject.projected_games, 12)
        self.assertEqual(subject.missed_weeks, {1, 3})

    def test_scenario_blends_sleeper_projection_without_narrowing_uncertainty(self):
        subject = player(name="Consensus", recvReceptions=170, recvYds=1700)
        subject.sleeper_projections = {"rec": 204}
        league = League({"roster_positions": ["WR"], "scoring_settings": {"rec": 1, "rec_yd": 0.1}})
        league.rosters = [SimpleNamespace(players=[subject])]

        apply_scenario(league, {"use_sleeper_projections": True})

        self.assertEqual(subject.projection_multiplier, 1.0)
        self.assertAlmostEqual(subject.season_cv, np.hypot(0.2, 0.1))

    def test_injury_risk_preserves_healthy_seasons_and_expected_games_missed(self):
        subject = player(name="Risk", byeWeek=18)
        subject.injury_probability = 0.5
        subject.projected_injury_games_missed = 3
        rng = np.random.default_rng(12)
        missed = []
        for _ in range(20_000):
            subject.prepare_availability(range(1, 18), rng)
            missed.append(len(subject.missed_weeks))

        self.assertAlmostEqual(np.mean(missed), 3, delta=0.08)
        self.assertAlmostEqual(np.mean(np.array(missed) == 0), 0.5, delta=0.02)
        restored = Player(subject.to_dict())
        self.assertEqual(restored.projected_injury_games_missed, 3)

    def test_recurring_injury_risk_can_create_separate_absences(self):
        subject = player(name="Recurring", byeWeek=18)
        subject.injury_probability = 0.5
        subject.injury_probability_per_game = 0.04
        subject.injuries_per_season = 2
        subject.projected_injury_games_missed = 2
        rng = np.random.default_rng(8)

        absences = []
        for _ in range(5_000):
            subject.prepare_availability(range(1, 18), rng)
            weeks = sorted(subject.missed_weeks)
            absences.append(sum(right > left + 1 for left, right in zip(weeks, weeks[1:])))

        self.assertGreater(sum(absences), 0)

    def test_game_and_competition_factors_preserve_shared_and_group_means(self):
        league = League({"scoring_settings": {"rec": 1}})
        opponents = [
            player(name="NE", team="NE", recvReceptions=170),
            player(name="SEA", team="SEA", recvReceptions=170),
        ]
        league.rosters = [SimpleNamespace(players=opponents)]
        season = SimulationSeason.__new__(SimulationSeason)
        season.league = league
        season.rng = np.random.default_rng(2)
        season.nfl_games = {(1, "NE"): "game", (1, "SEA"): "game"}
        season.nfl_opponents = {}
        season.defense_matchups = {}
        season.average_defense = {}
        season.scenario = {"game_environment_cv": 0.2}
        season.prepare_week_factors(1)
        self.assertEqual(opponents[0].week_factor, opponents[1].week_factor)

        competitors = [
            player(name="WR1", team="NE", recvReceptions=170),
            player(name="WR2", team="NE", recvReceptions=85),
        ]
        league.rosters = [SimpleNamespace(players=competitors)]
        season.scenario = {"competition_cv": 0.3}
        season.prepare_week_factors(1)
        weights = [subject.expected_weekly_score(league.scoring_settings) for subject in competitors]
        self.assertAlmostEqual(np.average([subject.week_factor for subject in competitors], weights=weights), 1)

    def test_shared_environment_factors_are_drawn_once(self):
        league = League({"scoring_settings": {"rec": 1}})
        teammates = [
            player(name="WR1", team="NE", recvReceptions=170),
            player(name="WR2", team="NE", recvReceptions=85),
        ]
        league.rosters = [SimpleNamespace(players=teammates)]
        season = SimulationSeason.__new__(SimulationSeason)
        season.league = league
        season.rng = np.random.default_rng(2)
        season.nfl_games = {(1, "NE"): "game"}
        season.nfl_opponents = {}
        season.defense_matchups = {}
        season.average_defense = {}
        season.scenario = {"game_environment_cv": 0.2, "team_environment_cv": 0.1}

        with patch(
            "ffsim.simulation.season.mean_preserving_lognormal", return_value=1.0
        ) as draw:
            season.prepare_week_factors(1)

        self.assertEqual(draw.call_count, 2)

    def test_matchup_grades_apply_position_specific_capped_factors(self):
        subjects = [player(name=position, position=position, team="NE") for position in ("QB", "RB", "WR", "TE", "K")]
        league = League({})
        league.rosters = [SimpleNamespace(players=subjects)]
        season = SimulationSeason.__new__(SimulationSeason)
        season.league = league
        season.rng = np.random.default_rng(1)
        season.scenario = {}
        season.nfl_games = {}
        season.nfl_opponents = {(1, "NE"): "SEA"}
        season.defense_matchups = {"SEA": {position: 10 for position in ("QB", "RB", "WR", "TE")}}
        season.average_defense = {position: 5 for position in ("QB", "RB", "WR", "TE")}

        season.prepare_week_factors(1)

        self.assertEqual([subject.week_factor for subject in subjects], [0.92, 0.92, 0.92, 0.92, 1.0])

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

    def test_empty_lineup_slot_gets_waiver_replacement_score(self):
        league = League({"roster_positions": ["K"], "scoring_settings": {"xpm": 1}})
        league.rosters = [FantasyTeam("Team", league)]
        waiver_players = [
            player(f"Kicker {index}", position="K", patMade=points * 17)
            for index, points in enumerate((3, 5, 7))
        ]
        league.set_replacement_levels(waiver_players)
        team = league.rosters[0]
        team.fill_starters(1)

        self.assertEqual(league.replacement_scores["K"], 7)
        self.assertGreater(team.streamer_score(np.random.default_rng(1)), 0)

    def test_tracker_keeps_zero_and_negative_played_scores(self):
        tracker = SimulationTracker(None, 1)
        for score in (0, -2, 4):
            tracker.record_player_score("p", 1, score, played=True)
        tracker.record_player_score("p", 2, 0, played=False)
        self.assertEqual(tracker.get_player_average_score("p"), (2 / 3, 2, 3, -2, 4))


class CompletedAndReproducibilityTest(unittest.TestCase):
    def test_matchup_refresh_explicitly_preserves_cached_week_on_sleeper_404(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "matchups_x.json")
            path.write_text(json.dumps({"2": [{"cached": True}]}))
            response = io.StringIO("[]")
            error = HTTPError("url", 404, "Not Found", None, io.BytesIO())
            with (
                patch("ffsim.simulation.season.CACHE_DIR", Path(directory)),
                patch("ffsim.simulation.season.urlopen", side_effect=[response, error]),
                redirect_stdout(io.StringIO()),
            ):
                refresh_matchups("x", 2)
            self.assertEqual(json.loads(path.read_text()), {"1": [], "2": [{"cached": True}]})
            error.close()

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
        league = SimpleNamespace(league_id="x", name="L", rosters=teams, divisions={1: [0, 1, 2], 2: [3, 4, 5]}, roster_slots={})

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
        events = []
        with patch("ffsim.simulation.monte_carlo.SimulationSeason", FakeSeason):
            first = simulation.run(
                on_simulation_complete=events.append, show_progress=False
            )
            second = simulation.run()
        self.assertEqual(first, second)
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0]["champion"], "T0")


if __name__ == "__main__":
    unittest.main()
