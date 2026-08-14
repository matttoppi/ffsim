import unittest
from types import SimpleNamespace

from ffsim.simulation.playoffs import PlayoffSimulation
from ffsim.simulation.season import SimulationSeason


def team(seed, wins, points):
    return SimpleNamespace(
        name=f"T{seed}", roster_id=seed, wins=wins, points_for=points
    )


def league(teams, playoff_teams, divisions=None, **settings):
    return SimpleNamespace(
        rosters=teams,
        divisions=divisions or {},
        division_count=len(divisions or {}),
        playoff_teams=playoff_teams,
        playoff_round_type=settings.get("playoff_round_type", 0),
        playoff_seed_type=settings.get("playoff_seed_type", 0),
    )


def pairs(bracket):
    return [(match.home_team.name, match.away_team.name) for match in bracket.matches]


class PlayoffFormatTest(unittest.TestCase):
    def setup(self, teams, playoff_teams, divisions=None, **settings):
        simulation = PlayoffSimulation(
            league(teams, playoff_teams, divisions, **settings),
            teams,
            SimpleNamespace(weeks=14),
        )
        simulation.setup_playoffs()
        return simulation.bracket

    def test_four_team_no_division_seeding_and_bracket(self):
        teams = [team(4, 7, 900), team(2, 9, 1000), team(1, 10, 900), team(3, 9, 950)]

        bracket = self.setup(teams, 4)

        self.assertEqual([entry.name for entry in bracket.teams], ["T1", "T2", "T3", "T4"])
        self.assertEqual(bracket.division_winners, [])
        self.assertEqual(pairs(bracket), [("T1", "T4"), ("T2", "T3")])

    def test_eight_team_fixed_bracket(self):
        teams = [team(seed, 20 - seed, 1000 - seed) for seed in range(1, 9)]
        bracket = self.setup(teams, 8)

        self.assertEqual(
            pairs(bracket),
            [("T1", "T8"), ("T2", "T7"), ("T3", "T6"), ("T4", "T5")],
        )
        winners = [team(seed, 0, 0) for seed in (11, 12, 13, 14)]
        bracket.matches = []
        bracket.create_next_round(winners, 16)
        self.assertEqual(pairs(bracket), [("T11", "T14"), ("T12", "T13")])

    def test_six_team_bracket_preserves_existing_pairing_order(self):
        teams = [team(seed, 20 - seed, 1000 - seed) for seed in range(1, 7)]
        bracket = self.setup(teams, 6, {1: [1, 3, 5], 2: [2, 4, 6]})

        self.assertEqual([entry.name for entry in bracket.division_winners], ["T1", "T2"])
        self.assertEqual(pairs(bracket), [("T3", "T6"), ("T4", "T5")])
        winners = [team(3, 0, 0), team(4, 0, 0)]
        bracket.matches = []
        bracket.create_next_round(winners, 16)
        self.assertEqual(pairs(bracket), [("T1", "T4"), ("T2", "T3")])

    def test_six_team_bracket_reseeds_after_an_upset(self):
        teams = [team(seed, 20 - seed, 1000 - seed) for seed in range(1, 7)]
        bracket = self.setup(teams, 6, playoff_seed_type=1)

        bracket.matches = []
        bracket.create_next_round([teams[5], teams[3]], 16)

        self.assertEqual(pairs(bracket), [("T1", "T6"), ("T2", "T4")])

    def test_division_and_wild_card_ties_break_on_points(self):
        teams = [
            team(1, 8, 900),
            team(2, 8, 950),
            team(3, 9, 800),
            team(4, 9, 850),
            team(5, 7, 1000),
            team(6, 7, 900),
        ]
        bracket = self.setup(teams, 4, {1: [1, 2, 5], 2: [3, 4, 6]})

        self.assertEqual([entry.name for entry in bracket.division_winners], ["T4", "T2"])
        self.assertEqual([entry.name for entry in bracket.teams], ["T4", "T2", "T3", "T1"])

    def test_unsupported_sleeper_settings_fail_explicitly(self):
        teams = [team(seed, seed, seed) for seed in range(1, 9)]
        cases = (
            ({"playoff_teams": 5}, "playoff_teams=5"),
            ({"playoff_teams": 4, "playoff_round_type": 1}, "playoff_round_type=1"),
            ({"playoff_teams": 4, "playoff_seed_type": 2}, "playoff_seed_type=2"),
        )
        for settings, message in cases:
            with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, message):
                self.setup(teams, **settings)

    def test_completed_sleeper_bracket_is_preserved_without_divisions(self):
        teams = [team(seed, 10 - seed, 1000 - seed) for seed in range(1, 5)]
        completed_league = league(teams, 4)
        completed_league.winners_bracket = [
            {"r": 1, "t1": 1, "t2": 4, "w": 1, "l": 4},
            {"r": 1, "t1": 2, "t2": 3, "w": 2, "l": 3},
            {"r": 2, "t1": 1, "t2": 2, "w": 2, "l": 1},
        ]
        season = SimulationSeason.__new__(SimulationSeason)
        season.league = completed_league
        season.teams_by_roster_id = {entry.roster_id: entry for entry in teams}

        playoffs = season._completed_playoffs()

        self.assertEqual(playoffs.champion.name, "T2")
        self.assertEqual([entry.name for entry in playoffs.bracket.teams], ["T1", "T2", "T3", "T4"])
        self.assertEqual(playoffs.bracket.division_winners, [])


if __name__ == "__main__":
    unittest.main()
