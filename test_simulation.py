import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from config import AppConfig
from custom_dataclasses.fantasy_team import FantasyTeam
from custom_dataclasses.league import League
from sim.SimulationClasses.Playoffs import PlayoffBracket
from sim.SimulationClasses.SimulationMatchup import SimulationMatchup
from sim.SimulationTracker import SimulationTracker


class FakePlayer:
    def __init__(self, player_id, score, partial=False, position="WR"):
        self.sleeper_id = player_id
        self.name = player_id.title()
        self.position = position
        self.score = score
        self.redraft_value = score
        self.partial = partial

    def is_injured(self, week):
        return False

    def is_partially_injured(self, week):
        return self.partial

    def calculate_score(self, scoring_settings, week):
        return self.score

    def get_average_weekly_score(self):
        return self.score


class FakeTeam:
    def __init__(self, starter, bench):
        self.players = [starter, bench]
        self.starter = starter

    def get_active_starters(self, week):
        return [self.starter]


class SimulationTest(unittest.TestCase):
    def test_config_loads_and_validates_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "league_id": 123,
                        "simulations": 25,
                        "seed": 7,
                        "regular_season_weeks": 17,
                    }
                )
            )

            config = AppConfig.from_file(path)

        self.assertEqual(config.league_id, "123")
        self.assertEqual(config.simulations, 25)
        self.assertEqual(config.seed, 7)
        self.assertEqual(config.regular_season_weeks, 17)

        with self.assertRaises(ValueError):
            AppConfig(league_id="", simulations=1)

    def test_team_initializes_and_records_a_win(self):
        team = FantasyTeam("Unknown", None, {"display_name": "Owner"})
        team.update_record(True, False, points_against=90, points_for=100)

        self.assertEqual(team.name, "Owner")
        self.assertEqual((team.wins, team.losses, team.ties), (1, 0, 0))
        self.assertEqual((team.points_for, team.points_against), (100, 90))

    def test_bench_player_does_not_count_when_partially_injured(self):
        starter = FakePlayer("starter", 10)
        bench = FakePlayer("bench", 20, partial=True)
        matchup = SimulationMatchup(FakeTeam(starter, bench), None, week=1)

        total, scores = matchup.simulate_all_players(matchup.home_team, None, 1, None)

        self.assertEqual(total, 10)
        self.assertEqual(scores, {"starter": 10, "bench": 20})

    def test_lineup_uses_league_roster_slots(self):
        league = League(
            {
                "roster_positions": ["QB", "RB", "WR", "FLEX", "BN", "IR"],
            }
        )
        team = FantasyTeam("Team", league)
        for player in (
            FakePlayer("quarterback", 10, position="QB"),
            FakePlayer("running back", 20, position="RB"),
            FakePlayer("backup running back", 5, position="RB"),
            FakePlayer("receiver", 30, position="WR"),
            FakePlayer("tight end", 25, position="TE"),
        ):
            team.add_player(player)

        team.fill_starters(1)

        self.assertEqual(team.starters["QB"][0].sleeper_id, "quarterback")
        self.assertEqual(team.starters["RB"][0].sleeper_id, "running back")
        self.assertEqual(team.starters["WR"][0].sleeper_id, "receiver")
        self.assertEqual(team.starters["FLEX"][0].sleeper_id, "tight end")

    def test_games_missed_are_averaged_across_all_simulations(self):
        tracker = SimulationTracker(None, num_simulations=2)
        tracker.record_player_games_missed("player", 1)
        tracker.record_player_games_missed("player", 3)

        self.assertEqual(tracker.get_player_avg_games_missed("player"), 2)

    def test_tracker_returns_json_serializable_results(self):
        player = FakePlayer("player", 12, position="RB")
        team = SimpleNamespace(name="Team", roster_id=1, players=[player])
        league = SimpleNamespace(
            league_id="league",
            name="League",
            rosters=[team],
            divisions={1: [1]},
        )
        tracker = SimulationTracker(league, num_simulations=2, regular_season_weeks=14)
        tracker.record_team_season("Team", 8, 1400)
        tracker.record_team_season("Team", 10, 1680)
        tracker.record_player_score("player", 1, 10)
        tracker.record_player_score("player", 1, 14)
        tracker.record_playoff_results([team], [team], team)
        tracker.calculate_averages()

        results = tracker.to_dict(seed=42)

        self.assertEqual(results["seed"], 42)
        self.assertEqual(results["teams"]["Team"]["average_wins"], 9)
        self.assertEqual(results["teams"]["Team"]["playoff_probability"], 0.5)
        self.assertEqual(results["players"]["player"]["average_score"], 12)
        json.dumps(results)

    def test_playoffs_start_after_the_configured_regular_season(self):
        teams = [object() for _ in range(6)]
        bracket = PlayoffBracket(
            teams,
            division1_winner=teams[0],
            division2_winner=teams[1],
            simulation_season=SimpleNamespace(weeks=17),
        )

        bracket.create_bracket()

        self.assertEqual(bracket.first_week, 18)
        self.assertEqual([match.week for match in bracket.matches], [18, 18])
        with self.assertRaises(ValueError):
            bracket.create_final([], 20)


if __name__ == "__main__":
    unittest.main()
