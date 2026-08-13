import unittest
from unittest.mock import patch

import numpy as np

from ffsim.models.league import League
from ffsim.simulation.season import PlayerWorldGenerator
from ffsim.simulation.world_bank import build_season_world_bank


class FakePlayer:
    def __init__(self, player_id):
        self.sleeper_id = player_id
        self.position = "WR"
        self.team = "NE"
        self.pff_projections = True
        self.projected_games = 17
        self.week_factor = 1.0
        self.season_factor = 1.0
        self.missed_weeks = set()

    def modeled_weekly_raw_stats(self):
        return {"receptions": 1}

    def expected_weekly_score(self, scoring_settings):
        return 1.0

    def prepare_availability(self, weeks, rng):
        self.missed_weeks = set()
        self.season_factor = float(rng.uniform(0.5, 1.5))

    def is_available(self, week):
        return week not in self.missed_weeks

    def calculate_score(self, scoring_settings, week, rng):
        return self.season_factor * self.week_factor

    def reset_season_stats(self):
        self.missed_weeks.clear()


class WorldBankTest(unittest.TestCase):
    def test_bank_is_reproducible_correlated_versioned_and_immutable(self):
        league = League({"scoring_settings": {"rec": 1}})
        players = [FakePlayer("b"), FakePlayer("a")]
        versions = {"projections": "p1", "injuries": "i1", "schedule": "s1"}

        with (
            patch.object(
                PlayerWorldGenerator,
                "_load_nfl_schedule",
                return_value=({(1, "NE"): "shared"}, {}),
            ),
            patch.object(
                PlayerWorldGenerator,
                "_load_defense_matchups",
                return_value=({}, {}),
            ),
        ):
            first = build_season_world_bank(
                league,
                players,
                3,
                weeks=2,
                seed=7,
                scenario={"game_environment_cv": 0.2},
                source_versions=versions,
            )
            second = build_season_world_bank(
                league,
                players,
                3,
                weeks=2,
                seed=7,
                scenario={"game_environment_cv": 0.2},
                source_versions=versions,
            )
            changed = build_season_world_bank(
                league,
                players,
                3,
                weeks=2,
                seed=7,
                source_versions={**versions, "injuries": "i2"},
            )

        self.assertEqual(first.player_ids, ("a", "b"))
        np.testing.assert_array_equal(first.scores, second.scores)
        np.testing.assert_array_equal(first.available, second.available)
        self.assertEqual(first.version, second.version)
        self.assertNotEqual(first.version, changed.version)
        np.testing.assert_allclose(
            first.scores[:, 0, :] / first.scores[:, 1, :],
            np.array([
                [first.scores[index, 0, 0] / first.scores[index, 1, 0]] * 2
                for index in range(3)
            ]),
            rtol=1e-6,
        )
        with self.assertRaises(ValueError):
            first.scores[0, 0, 0] = 0


if __name__ == "__main__":
    unittest.main()
