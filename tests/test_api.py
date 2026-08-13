import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from ffsim.api import (
    LeagueRequest,
    SimulationJob,
    SimulationRequest,
    _run_job,
    _run_refresh,
    create_app,
)
from ffsim.config import AppConfig


RESULT = {
    "champion": "Alpha",
    "playoff_teams": ["Alpha", "Beta"],
    "division_winners": ["Alpha", "Beta"],
}


class ApiTest(unittest.TestCase):
    def test_job_aggregates_live_results_and_publishes_events(self):
        job = SimulationJob("job", total=2, seed=7, workers=1, teams_only=True)
        job.set_status("running", ["Alpha", "Beta"])
        job.record(RESULT)

        snapshot = job.snapshot()

        self.assertEqual(snapshot["completed"], 1)
        self.assertEqual(snapshot["championships"], {"Alpha": 1, "Beta": 0})
        self.assertEqual([event["event"] for event in job.events], ["queued", "status", "progress"])

    def test_runner_completes_job_with_structured_results(self):
        class FakeSimulation:
            league = SimpleNamespace(
                rosters=[SimpleNamespace(name="Alpha"), SimpleNamespace(name="Beta")],
                divisions={},
            )

            def run(self, on_simulation_complete, show_progress):
                self.callback = on_simulation_complete
                self.show_progress = show_progress
                on_simulation_complete({**RESULT, "division_winners": []})
                return {"teams": {"Alpha": {}, "Beta": {}}}

        job = SimulationJob("job", total=1, seed=7, workers=1, teams_only=True)
        with patch("ffsim.api.create_simulation", return_value=FakeSimulation()):
            _run_job(job, AppConfig(league_id="league", simulations=1))

        self.assertEqual(job.status, "completed")
        self.assertEqual(job.completed, 1)
        self.assertEqual(job.results, {"teams": {"Alpha": {}, "Beta": {}}})
        self.assertEqual(job.division_wins, {})

    def test_api_contract_and_request_limits(self):
        paths = create_app("config.json").openapi()["paths"]

        self.assertIn("/api/simulations", paths)
        self.assertIn("/api/simulations/{job_id}/events", paths)
        self.assertIn("/api/simulations/{job_id}/results", paths)
        self.assertIn("/api/league", paths)
        self.assertIn("/api/leagues", paths)
        self.assertIn("/api/leagues/{league_id}/drafts", paths)
        with self.assertRaises(ValidationError):
            SimulationRequest(simulations=0)
        with self.assertRaises(ValidationError):
            LeagueRequest(league_id="", draft_id="draft")
        with self.assertRaises(ValidationError):
            LeagueRequest(league_id="league", draft_id="")

    def test_refresh_runner_updates_state_on_success_and_failure(self):
        state = SimpleNamespace(refresh={
            "status": "running",
            "league_id": "1",
            "draft_id": "draft-1",
            "error": None,
        })
        with (
            patch("ffsim.loaders.players.PlayerLoader") as loader,
            patch("ffsim.loaders.league.refresh_league") as refresh_league,
            patch("ffsim.simulation.season.refresh_matchups") as refresh_matchups,
        ):
            _run_refresh(state, "1", "draft-1", 17)

        loader.return_value.refresh.assert_called_once_with()
        refresh_league.assert_called_once_with("1", "draft-1")
        refresh_matchups.assert_called_once_with("1", 17)
        self.assertEqual(state.refresh["status"], "ready")

        with patch(
            "ffsim.loaders.league.refresh_league",
            side_effect=OSError("sleeper down"),
        ):
            _run_refresh(state, "2", "draft-2", 17)

        self.assertEqual(state.refresh["status"], "failed")
        self.assertIn("sleeper down", state.refresh["error"])

if __name__ == "__main__":
    unittest.main()
