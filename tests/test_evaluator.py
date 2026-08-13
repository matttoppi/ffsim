import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ffsim.models.league import League
from ffsim.models.team import FantasyTeam
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.simulation.season import PlayerWorldGenerator, SimulationSeason
from ffsim.simulation.tracker import SimulationTracker
from ffsim.simulation.world_bank import SeasonWorldBank


def bank(scores, positions=None, expected=None):
    scores = np.asarray(scores, dtype=np.float32)
    players = scores.shape[1]
    return SeasonWorldBank(
        version="bank-v1",
        seed=1,
        player_ids=tuple(f"p{index}" for index in range(players)),
        player_positions=tuple(positions or ["WR"] * players),
        expected_scores=np.asarray(expected or [10.0] * players),
        weeks=tuple(range(1, scores.shape[2] + 1)),
        input_hash="inputs-v1",
        scores=scores,
        available=np.ones_like(scores, dtype=bool),
    )


def league(playoff_teams=4, slots=None):
    return League({
        "league_id": "league",
        "roster_positions": slots or ["WR"],
        "settings": {
            "playoff_teams": playoff_teams,
            "playoff_round_type": 0,
            "playoff_seed_type": 0,
        },
    })


class BankPlayer:
    def __init__(self, world_bank, index):
        self.bank = world_bank
        self.index = index
        self.sleeper_id = world_bank.player_ids[index]
        self.name = self.sleeper_id
        self.position = world_bank.player_positions[index]
        self.team = f"NFL{index}"
        self.pff_projections = True
        self.projected_games = 17
        self.total_games_missed_this_season = 0

    def modeled_weekly_raw_stats(self):
        return {"receptions": 1}

    def expected_weekly_score(self, scoring_settings):
        return float(self.bank.expected_scores[self.index])

    def prepare_availability(self, weeks, rng):
        pass

    def is_available(self, week):
        return bool(self.bank.available[0, self.index, week - 1])

    def calculate_score(self, scoring_settings, week, rng):
        return float(self.bank.scores[0, self.index, week - 1])

    def reset_season_stats(self):
        pass


class LeagueEvaluatorTest(unittest.TestCase):
    def test_fixed_world_matches_existing_full_season_path_and_cache(self):
        world_bank = bank([[[100, 10, 10], [90, 20, 20], [80, 30, 50], [70, 40, 40]]])
        subject = league()
        teams = []
        for roster_id in range(1, 5):
            team = FantasyTeam(f"T{roster_id}", subject)
            team.roster_id = roster_id
            team.add_player(BankPlayer(world_bank, roster_id - 1))
            teams.append(team)
        subject.rosters = teams
        schedule = {1: [(1, 4), (2, 3)]}
        evaluator = LeagueEvaluator(subject, world_bank, range(1, 5), 1, schedule=schedule)
        assignment = {roster_id: [roster_id - 1] for roster_id in range(1, 5)}

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "matchups_league.json").write_text(json.dumps({
                "1": [
                    {"roster_id": 1, "matchup_id": 1},
                    {"roster_id": 4, "matchup_id": 1},
                    {"roster_id": 2, "matchup_id": 2},
                    {"roster_id": 3, "matchup_id": 2},
                ]
            }))
            with (
                patch("ffsim.simulation.season.CACHE_DIR", Path(directory)),
                patch.object(PlayerWorldGenerator, "_load_nfl_schedule", return_value=({}, {})),
                patch.object(PlayerWorldGenerator, "_load_defense_matchups", return_value=({}, {})),
            ):
                season = SimulationSeason(
                    subject,
                    SimulationTracker(subject, 1),
                    weeks=1,
                    rng=np.random.default_rng(1),
                )
                season.simulate()

        result = evaluator.evaluate(assignment)
        cached = evaluator.evaluate(assignment)
        uncached = evaluator.evaluate(assignment, use_cache=False)
        champion = evaluator.roster_ids[result.champion_indices[0]]
        self.assertEqual(champion, season.playoff_sim.champion.roster_id)
        self.assertIs(cached, result)
        np.testing.assert_array_equal(result.wins[0], [team.wins for team in teams])
        np.testing.assert_array_equal(result.points[0], [team.points_for for team in teams])
        np.testing.assert_array_equal(result.champion_indices, uncached.champion_indices)
        self.assertEqual((evaluator.cache_hits, evaluator.cache_misses), (1, 2))

    def test_superflex_lineup_and_generated_schedule_are_deterministic(self):
        scores = np.array([[
            [20, 20, 20], [15, 15, 15], [10, 10, 10],
            [18, 18, 18], [14, 14, 14],
            [17, 17, 17], [13, 13, 13],
            [16, 16, 16], [12, 12, 12],
        ]])
        world_bank = bank(
            scores,
            positions=["QB", "QB", "WR", "QB", "QB", "QB", "QB", "QB", "QB"],
            expected=[20, 15, 15, 18, 14, 17, 13, 16, 12],
        )
        subject = league(slots=["QB", "SUPER_FLEX"])
        assignment = {1: [0, 1, 2], 2: [3, 4], 3: [5, 6], 4: [7, 8]}
        first = LeagueEvaluator(subject, world_bank, assignment, 1, seed=9)
        second = LeagueEvaluator(subject, world_bank, assignment, 1, seed=9)

        result = first.evaluate(assignment)

        self.assertEqual(result.weekly_scores[0, 0, 0], 35)
        self.assertEqual(first.schedules, second.schedules)
        self.assertEqual(first.version, second.version)
        self.assertEqual(int(result.playoffs[0].sum()), 4)

    def test_selected_worlds_preserve_bank_identity_and_exact_cache_keys(self):
        world_bank = bank([
            [[1, 1, 4], [2, 2, 3], [3, 3, 2], [4, 4, 1]],
            [[10, 10, 40], [20, 20, 30], [30, 30, 20], [40, 40, 10]],
        ])
        assignment = {roster_id: [roster_id - 1] for roster_id in range(1, 5)}
        evaluator = LeagueEvaluator(
            league(),
            world_bank,
            assignment,
            regular_season_weeks=1,
            seed=3,
        )

        selected = evaluator.evaluate(assignment, world_indices=(1,))
        cached = evaluator.evaluate(assignment, world_indices=(1,))
        full = evaluator.evaluate(assignment)

        self.assertEqual(selected.world_indices, (1,))
        self.assertEqual(full.world_indices, (0, 1))
        self.assertIs(selected, cached)
        np.testing.assert_array_equal(selected.weekly_scores[0], full.weekly_scores[1])
        with self.assertRaisesRegex(ValueError, "valid SeasonWorldBank"):
            evaluator.evaluate(assignment, world_indices=())

    def test_all_playoff_sizes_divisions_and_median_games(self):
        for playoff_teams in (4, 6, 8):
            with self.subTest(playoff_teams=playoff_teams):
                weeks = 3 if playoff_teams == 4 else 4
                scores = [[
                    [100 - player] * weeks for player in range(playoff_teams)
                ]]
                world_bank = bank(scores)
                subject = league(playoff_teams)
                subject.league_average_match = True
                if playoff_teams == 6:
                    subject.divisions = {1: [1, 3, 5], 2: [2, 4, 6]}
                    subject.division_count = 2
                assignment = {
                    roster_id: [roster_id - 1]
                    for roster_id in range(1, playoff_teams + 1)
                }
                evaluator = LeagueEvaluator(
                    subject,
                    world_bank,
                    assignment,
                    regular_season_weeks=1,
                    seed=3,
                )

                result = evaluator.evaluate(assignment)

                self.assertEqual(
                    evaluator.roster_ids[result.champion_indices[0]],
                    1,
                )
                self.assertEqual(int(result.playoffs[0].sum()), playoff_teams)
                self.assertEqual(
                    int(result.division_wins[0].sum()),
                    2 if playoff_teams == 6 else 0,
                )


if __name__ == "__main__":
    unittest.main()
