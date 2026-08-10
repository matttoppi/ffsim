import unittest

from custom_dataclasses.fantasy_team import FantasyTeam
from sim.SimulationClasses.SimulationMatchup import SimulationMatchup
from sim.SimulationTracker import SimulationTracker


class FakePlayer:
    def __init__(self, player_id, score, partial=False):
        self.sleeper_id = player_id
        self.position = "WR"
        self.score = score
        self.partial = partial

    def is_injured(self, week):
        return False

    def is_partially_injured(self, week):
        return self.partial

    def calculate_score(self, scoring_settings, week):
        return self.score


class FakeTeam:
    def __init__(self, starter, bench):
        self.players = [starter, bench]
        self.starter = starter

    def get_active_starters(self, week):
        return [self.starter]


class SimulationTest(unittest.TestCase):
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

    def test_games_missed_are_averaged_across_all_simulations(self):
        tracker = SimulationTracker(None, num_simulations=2)
        tracker.record_player_games_missed("player", 1)
        tracker.record_player_games_missed("player", 3)

        self.assertEqual(tracker.get_player_avg_games_missed("player"), 2)


if __name__ == "__main__":
    unittest.main()
