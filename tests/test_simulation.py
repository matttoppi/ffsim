import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from ffsim.__main__ import setup_league
from ffsim.config import AppConfig, save_league_attachment
from ffsim.loaders.league import (
    draft_summary,
    league_and_drafts,
    league_id_for_username,
    refresh_league,
)
from ffsim.models.league import League
from ffsim.models.team import FantasyTeam
from ffsim.simulation.matchup import SimulationMatchup
from ffsim.simulation.playoffs import PlayoffBracket
from ffsim.simulation.tracker import SimulationTracker


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

    def is_available(self, week):
        return True

    def is_partially_injured(self, week):
        return self.partial

    def calculate_score(self, scoring_settings, week, rng=None):
        return self.score

    def expected_weekly_score(self, scoring_settings):
        return self.score

    def get_average_weekly_score(self):
        return self.score


class FakeTeam:
    def __init__(self, starter, bench):
        self.players = [starter, bench]
        self.starter = starter

    def get_active_starters(self, week):
        return [self.starter]

    def streamer_score(self, rng):
        return 0


class SimulationTest(unittest.TestCase):
    @patch("ffsim.loaders.league.league_and_drafts")
    @patch("ffsim.loaders.league.leagues_for_username")
    def test_setup_prompts_until_a_valid_league_and_draft_are_selected(
        self,
        leagues,
        drafts,
    ):
        leagues.return_value = [
            {"league_id": "1", "name": "A League", "status": "pre_draft"},
            {"league_id": "2", "name": "B League", "status": "in_season"},
        ]
        drafts.return_value = (
            {"league_id": "2", "name": "B League", "settings": {"type": 0}},
            [{
                "draft_id": "draft-2",
                "league_id": "2",
                "type": "auction",
                "status": "pre_draft",
                "settings": {"teams": 8, "rounds": 20},
                "metadata": {"scoring_type": "custom"},
            }],
        )
        answers = iter(["matt", "nope", "2", "bad", "1"])
        output = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"league_id": "old", "simulations": 10}\n')

            setup_league(path, input_fn=lambda _: next(answers), print_fn=output.append)

            config = json.loads(path.read_text())
            self.assertEqual(config["league_id"], "2")
            self.assertEqual(config["draft_id"], "draft-2")

        self.assertIn("Enter a number from 1 to 2.", output)
        self.assertIn("Enter a number from 1 to 1.", output)
        leagues.assert_called_once_with("matt", 2026)
        drafts.assert_called_once_with("2")

    def test_draft_attachment_preserves_arbitrary_redraft_structure(self):
        league = {
            "league_id": "league",
            "name": "Custom League",
            "status": "pre_draft",
            "season": "2026",
            "total_rosters": 8,
            "settings": {"type": 0, "best_ball": 1, "custom_setting": 17},
            "scoring_settings": {"rec": 0.25, "bonus_rec_te": 1.75},
            "roster_positions": ["QB", "RB", "WR", "REC_FLEX", "BN"],
        }
        draft = {
            "draft_id": "draft",
            "league_id": "league",
            "type": "auction",
            "status": "pre_draft",
            "season": "2026",
            "settings": {"teams": 8, "rounds": 20, "nomination_timer": 30},
            "metadata": {"scoring_type": "custom_redraft", "custom": "kept"},
        }
        payloads = {
            "league/league": league,
            "league/league/drafts": [draft],
            "draft/draft": draft,
            "draft/draft/picks": [],
            "draft/draft/traded_picks": [],
            "league/league/rosters": [],
            "league/league/users": [],
            "league/league/winners_bracket": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            refresh_league(
                "league",
                "draft",
                fetch_json=payloads.__getitem__,
                cache_dir=directory,
            )
            snapshot = json.loads((Path(directory) / "league_league.json").read_text())

        self.assertEqual(snapshot["league"]["scoring_settings"], league["scoring_settings"])
        self.assertEqual(snapshot["league"]["roster_positions"], league["roster_positions"])
        self.assertEqual(snapshot["draft"]["settings"], draft["settings"])
        self.assertEqual(snapshot["draft_summary"]["draft_type"], "auction")
        self.assertTrue(snapshot["draft_summary"]["redraft_eligible"])
        self.assertEqual(
            draft_summary(league, draft, [{"is_keeper": True}])[
                "redraft_ineligibility_reasons"
            ],
            ["keeper_picks"],
        )

        wrong_draft = {**draft, "league_id": "other"}
        with self.assertRaisesRegex(ValueError, "belongs to league other"):
            league_and_drafts(
                "league",
                {"league/league": league, "league/league/drafts": [wrong_draft]}.__getitem__,
            )

    @patch("ffsim.loaders.league._fetch_json")
    def test_username_resolves_one_league_and_rejects_ambiguous_leagues(self, fetch):
        fetch.side_effect = [
            {"user_id": "user-1"},
            [{"league_id": "123", "name": "Home League"}],
        ]
        self.assertEqual(league_id_for_username(" matt ", 2026), "123")
        self.assertEqual(
            fetch.call_args_list,
            [call("user/matt"), call("user/user-1/leagues/nfl/2026")],
        )

        fetch.side_effect = [
            {"user_id": "user-1"},
            [
                {"league_id": "2", "name": "Z League"},
                {"league_id": "1", "name": "A League"},
            ],
        ]
        with self.assertRaisesRegex(ValueError, r"A League \(1\), Z League \(2\)"):
            league_id_for_username("matt", 2026)

    def test_config_loads_and_validates_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "league_id": 123,
                        "draft_id": 456,
                        "simulations": 25,
                        "seed": 7,
                        "regular_season_weeks": 17,
                    }
                )
            )

            config = AppConfig.from_file(path)

        self.assertEqual(config.league_id, "123")
        self.assertEqual(config.draft_id, "456")
        self.assertEqual(config.simulations, 25)
        self.assertEqual(config.seed, 7)
        self.assertEqual(config.regular_season_weeks, 17)

        with self.assertRaises(ValueError):
            AppConfig(league_id="", simulations=1)
        with self.assertRaises(ValueError):
            AppConfig(league_id="league", draft_id="")

    def test_league_attachment_replaces_config_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"league_id": "old", "simulations": 25}\n')

            config = save_league_attachment(path, "new", "draft")

            self.assertEqual((config.league_id, config.draft_id), ("new", "draft"))
            self.assertEqual(json.loads(path.read_text()), {
                "league_id": "new",
                "draft_id": "draft",
                "simulations": 25,
            })
            original = path.read_text()
            with patch("ffsim.config.os.replace", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    save_league_attachment(path, "other", "other-draft")
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(Path(directory).glob(".config.json.*")), [])
            with self.assertRaises(ValueError):
                save_league_attachment(path, " ", "draft")
            self.assertEqual(path.read_text(), original)

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

        total, scores = matchup.simulate_all_players(matchup.home_team, None, 1)

        self.assertEqual(total, 10)
        self.assertEqual(scores, {"starter": 10, "bench": 20})

    def test_team_only_matchup_does_not_simulate_bench_players(self):
        starter = FakePlayer("starter", 10)
        bench = FakePlayer("bench", 20)
        matchup = SimulationMatchup(FakeTeam(starter, bench), None, week=1)

        total, scores = matchup.simulate_all_players(
            matchup.home_team, None, 1, track_players=False
        )

        self.assertEqual(total, 10)
        self.assertEqual(scores, {"starter": 10})

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
        self.assertEqual(results["teams"]["Team"]["win_percentiles"]["50"], 9)
        self.assertEqual(results["teams"]["Team"]["points_percentiles"]["50"], 1540)
        self.assertEqual(results["players"]["player"]["average_score"], 12)
        self.assertEqual(tracker.player_scores, {})
        json.dumps(results)

    def test_tracker_keeps_raw_samples_only_when_requested(self):
        tracker = SimulationTracker(None, 1, keep_samples=True)

        tracker.record_player_score("player", 2, 12)

        self.assertEqual(tracker.player_scores["player"][2], [12])

    def test_tracker_merges_process_results(self):
        tracker = SimulationTracker(None, 2)
        worker = SimulationTracker(None, 2)
        tracker.record_player_score("player", 1, 4)
        worker.record_player_score("player", 1, -2)
        worker.player_games_missed["player"] = 3

        tracker.merge_worker_state(worker.worker_state())

        self.assertEqual(tracker.get_player_average_score("player"), (1, 2, 2, -2, 4))
        self.assertEqual(tracker.get_player_avg_games_missed("player"), 1.5)

    def test_playoffs_start_after_the_configured_regular_season(self):
        teams = [object() for _ in range(6)]
        bracket = PlayoffBracket(
            teams,
            division_winners=teams[:2],
            simulation_season=SimpleNamespace(weeks=17),
        )

        bracket.create_bracket()

        self.assertEqual(bracket.first_week, 18)
        self.assertEqual([match.week for match in bracket.matches], [18, 18])


if __name__ == "__main__":
    unittest.main()
