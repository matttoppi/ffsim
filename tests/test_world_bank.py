import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ffsim.models.league import League
from ffsim.models.team import FantasyTeam
from ffsim.simulation.season import PlayerWorldGenerator
from ffsim.simulation.tracker import SimulationTracker
from ffsim.simulation.world_bank import (
    build_season_world_bank,
    draftable_players,
    world_bank_input_hash,
)


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

        with (
            patch(
                "ffsim.simulation.world_bank.world_bank_input_hash",
                return_value="inputs-v1",
            ),
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
            )
            second = build_season_world_bank(
                league,
                players,
                3,
                weeks=2,
                seed=7,
                scenario={"game_environment_cv": 0.2},
            )
            extended = build_season_world_bank(
                league,
                players,
                4,
                weeks=2,
                seed=7,
                scenario={"game_environment_cv": 0.2},
            )

        self.assertEqual(first.player_ids, ("a", "b"))
        np.testing.assert_array_equal(first.scores, second.scores)
        np.testing.assert_array_equal(first.available, second.available)
        self.assertEqual(first.version, second.version)
        np.testing.assert_array_equal(first.scores, extended.scores[:3])
        self.assertNotEqual(first.version, extended.version)
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

    def test_input_hash_and_draftable_pool_follow_actual_inputs(self):
        eligible = FakePlayer("eligible")
        unsupported = FakePlayer("idp")
        unsupported.position = "LB"
        unprojected = FakePlayer("unprojected")
        unprojected.pff_projections = False
        self.assertEqual(
            [player.sleeper_id for player in draftable_players([
                unprojected, unsupported, eligible
            ])],
            ["eligible"],
        )

        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory, "first")
            second = Path(directory, "second")
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            with (
                patch("ffsim.simulation.world_bank.DATA_DIR", Path(directory)),
                patch(
                    "ffsim.simulation.world_bank.WORLD_INPUT_FILES",
                    (first, second),
                ),
            ):
                before = world_bank_input_hash()
                second.write_bytes(b"changed")
                self.assertNotEqual(before, world_bank_input_hash())

    def test_bank_matches_the_existing_fixed_seed_matchup_path(self):
        league = League({
            "league_id": "league",
            "roster_positions": ["WR"],
            "scoring_settings": {"rec": 1},
        })
        players = [FakePlayer("a"), FakePlayer("b")]
        teams = [FantasyTeam("A", league), FantasyTeam("B", league)]
        for roster_id, team, player in zip((1, 2), teams, players):
            team.roster_id = roster_id
            team.add_player(player)
        league.rosters = teams
        stream = np.random.SeedSequence(11).spawn(1)[0]

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "matchups_league.json").write_text(json.dumps({
                "1": [
                    {"roster_id": 1, "matchup_id": 1},
                    {"roster_id": 2, "matchup_id": 1},
                ]
            }))
            with (
                patch("ffsim.simulation.season.CACHE_DIR", Path(directory)),
                patch(
                    "ffsim.simulation.world_bank.world_bank_input_hash",
                    return_value="inputs-v1",
                ),
                patch.object(
                    PlayerWorldGenerator,
                    "_load_nfl_schedule",
                    return_value=({}, {}),
                ),
                patch.object(
                    PlayerWorldGenerator,
                    "_load_defense_matchups",
                    return_value=({}, {}),
                ),
            ):
                bank = build_season_world_bank(league, players, 1, weeks=1, seed=11)
                tracker = SimulationTracker(league, 1, keep_samples=True)
                from ffsim.simulation.season import SimulationSeason
                season = SimulationSeason(
                    league,
                    tracker,
                    weeks=1,
                    rng=np.random.default_rng(stream),
                )
                for player in season.players:
                    player.prepare_availability((1,), season.rng)
                season.simulate_week(1)

        expected = np.array([
            tracker.player_scores[player_id][1][0]
            for player_id in bank.player_ids
        ], dtype=np.float32)
        np.testing.assert_array_equal(bank.scores[0, :, 0], expected)


if __name__ == "__main__":
    unittest.main()
