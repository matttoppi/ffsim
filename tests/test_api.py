import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from ffsim.api import (
    DraftMonitorRequest,
    DraftPrepareRequest,
    LeagueRequest,
    LiveDraftMonitor,
    SimulationJob,
    SimulationRequest,
    _run_draft_preparation,
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


def endpoint(app, path, method):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path
        and method in getattr(route, "methods", ())
    )


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
        self.assertIn("/api/draft-intel/prepare", paths)
        self.assertIn("/api/draft-intel/monitor", paths)
        self.assertIn("/api/draft-intel/monitor/stop", paths)
        with self.assertRaises(ValidationError):
            SimulationRequest(simulations=0)
        with self.assertRaises(ValidationError):
            LeagueRequest(league_id="", draft_id="draft")
        with self.assertRaises(ValidationError):
            LeagueRequest(league_id="league", draft_id="")
        with self.assertRaises(ValidationError):
            LeagueRequest(league_id=" ", draft_id="draft")
        self.assertEqual(
            LeagueRequest(league_id=" league ", draft_id=" draft ").model_dump(),
            {"league_id": "league", "draft_id": "draft"},
        )
        self.assertEqual(
            DraftPrepareRequest(
                draft_id=" real ",
                mock_draft_id=" mock ",
                username=" matt ",
            ).model_dump()["mock_draft_id"],
            "mock",
        )
        with self.assertRaises(ValidationError):
            DraftMonitorRequest(rollout_count=1)

    def test_refresh_runner_updates_state_on_success_and_failure(self):
        state = SimpleNamespace(refresh={
            "status": "running",
            "league_id": "1",
            "draft_id": "draft-1",
            "error": None,
        })
        with (
            patch(
                "ffsim.draft_intel.market.refresh_fantasypros_adp",
                return_value={"fresh": True},
            ) as refresh_market,
            patch("ffsim.loaders.players.PlayerLoader") as loader,
            patch("ffsim.loaders.league.refresh_league") as refresh_league,
            patch("ffsim.simulation.season.refresh_matchups") as refresh_matchups,
        ):
            _run_refresh(state, "1", "draft-1", 17)

        loader.return_value.refresh_if_stale.assert_called_once_with(season=2026)
        refresh_league.assert_called_once_with("1", "draft-1")
        refresh_matchups.assert_called_once_with("1", 17)
        self.assertEqual(state.refresh["status"], "ready")
        self.assertEqual(state.refresh["market"], {"fresh": True})
        self.assertIs(state.refresh["projection"], loader.return_value.refresh_if_stale.return_value)
        refresh_market.assert_called_once_with(
            season=2026,
            sleeper_players_path=loader.return_value.sleeper_players_file,
        )

        with patch(
            "ffsim.loaders.league.refresh_league",
            side_effect=OSError("sleeper down"),
        ):
            with self.assertLogs("ffsim.api", level="ERROR"):
                _run_refresh(state, "2", "draft-2", 17)

        self.assertEqual(state.refresh["status"], "failed")
        self.assertIn("sleeper down", state.refresh["error"])

    def test_league_draft_endpoints_preserve_selection_and_fail_closed(self):
        league = {
            "league_id": "league",
            "name": "Custom",
            "status": "pre_draft",
            "settings": {"type": 0, "custom": 1},
            "scoring_settings": {"rec": 0.25},
            "roster_positions": ["QB", "REC_FLEX", "BN"],
        }
        draft = {
            "draft_id": "draft",
            "league_id": "league",
            "type": "auction",
            "status": "pre_draft",
            "settings": {"teams": 8, "rounds": 20},
            "metadata": {"scoring_type": "custom_redraft"},
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                '{"league_id": "old", "regular_season_weeks": 14}\n'
            )
            app = create_app(config_path)
            find_drafts = endpoint(app, "/api/leagues/{league_id}/drafts", "GET")
            select_league = endpoint(app, "/api/league", "POST")
            current_league = endpoint(app, "/api/league", "GET")

            with patch(
                "ffsim.loaders.league.league_and_drafts",
                return_value=(league, [draft]),
            ):
                found = find_drafts("league")
                self.assertEqual(found["league"]["scoring_settings"], {"rec": 0.25})
                self.assertEqual(found["drafts"][0]["draft_type"], "auction")
                with patch("ffsim.api.Thread") as thread:
                    selected = select_league(LeagueRequest(
                        league_id="league",
                        draft_id="draft",
                    ))

            self.assertEqual(selected, {
                "status": "running",
                "league_id": "league",
                "draft_id": "draft",
            })
            self.assertEqual(
                (json.loads(config_path.read_text())["league_id"],
                 json.loads(config_path.read_text())["draft_id"]),
                ("league", "draft"),
            )
            self.assertEqual(thread.call_args.kwargs["args"], (
                app.state,
                "league",
                "draft",
                17,
            ))
            thread.return_value.start.assert_called_once_with()

            cache = Path(directory) / "league_league.json"
            cache.write_text(json.dumps({
                "league": league,
                "draft_summary": found["drafts"][0],
            }))
            with patch("ffsim.api.CACHE_DIR", Path(directory)):
                current = current_league()
            self.assertTrue(current["ready"])
            self.assertEqual(current["draft_id"], "draft")
            self.assertEqual(current["market_context"]["status"], "proxy")
            self.assertEqual(current["market_context"]["scoring"], "STD")

            app.state.refresh["status"] = "idle"
            before = config_path.read_text()
            with patch(
                "ffsim.loaders.league.league_and_drafts",
                return_value=(league, [draft]),
            ):
                with self.assertRaises(HTTPException) as error:
                    select_league(LeagueRequest(
                        league_id="league",
                        draft_id="other",
                    ))
            self.assertEqual(error.exception.status_code, 400)
            self.assertEqual(config_path.read_text(), before)

            with (
                patch(
                    "ffsim.loaders.league.league_and_drafts",
                    return_value=(league, [draft]),
                ),
                patch(
                    "ffsim.api.save_league_attachment",
                    side_effect=OSError("disk full"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    select_league(LeagueRequest(
                        league_id="league",
                        draft_id="draft",
                    ))
            self.assertEqual(app.state.refresh["status"], "idle")
            self.assertEqual(config_path.read_text(), before)

    def test_draft_preparation_and_monitor_endpoints_use_one_prepared_session(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text('{"league_id": "old"}\n')
            app = create_app(config_path)
            start_prepare = endpoint(app, "/api/draft-intel/prepare", "POST")
            prepare_status = endpoint(app, "/api/draft-intel/prepare", "GET")
            start_monitor = endpoint(app, "/api/draft-intel/monitor", "POST")
            monitor_status = endpoint(app, "/api/draft-intel/monitor", "GET")
            stop_monitor = endpoint(app, "/api/draft-intel/monitor/stop", "POST")

            request = DraftPrepareRequest(
                draft_id="real",
                mock_draft_id="mock",
                username="matt",
            )
            with patch("ffsim.api.Thread") as thread:
                started = start_prepare(request)
            self.assertEqual(started["status"], "running")
            self.assertEqual(prepare_status()["mock_draft_id"], "mock")
            self.assertEqual(
                thread.call_args.kwargs["args"],
                (app.state, config_path, request),
            )

            prepared = SimpleNamespace(
                live_draft_id="mock",
                summary={"status": "ready", "monitor_ready": True, "blockers": []},
            )
            app.state.prepared_draft = prepared
            app.state.draft_preparation = dict(prepared.summary)
            with patch("ffsim.api.Thread") as thread:
                monitoring = start_monitor(DraftMonitorRequest())
            self.assertEqual(monitoring["status"], "starting")
            self.assertEqual(monitor_status()["draft_id"], "mock")
            thread.return_value.start.assert_called_once_with()
            self.assertEqual(stop_monitor()["status"], "starting")
            self.assertTrue(app.state.live_monitor.stopped.is_set())

    def test_draft_preparation_runner_publishes_success_and_failure(self):
        state = SimpleNamespace(
            prepare_lock=__import__("threading").Lock(),
            prepared_draft=None,
            draft_preparation={"status": "running", "stage": "Starting"},
        )
        request = DraftPrepareRequest(draft_id="real", username="matt")
        prepared = SimpleNamespace(summary={"status": "ready", "monitor_ready": True})
        with patch("ffsim.draft_intel.live.prepare_draft", return_value=prepared):
            _run_draft_preparation(state, "config.json", request)
        self.assertIs(state.prepared_draft, prepared)
        self.assertEqual(state.draft_preparation["stage"], "Ready")

        with patch(
            "ffsim.draft_intel.live.prepare_draft",
            side_effect=ValueError("wrong mock"),
        ):
            with self.assertLogs("ffsim.api", level="ERROR"):
                _run_draft_preparation(state, "config.json", request)
        self.assertIsNone(state.prepared_draft)
        self.assertEqual(state.draft_preparation["status"], "failed")
        self.assertEqual(state.draft_preparation["error"], "wrong mock")

    def test_live_monitor_recovers_from_a_transient_sync_failure(self):
        prepared = SimpleNamespace(live_draft_id="mock")
        state = SimpleNamespace(
            status="complete",
            completed_picks=(),
            current_roster_id=None,
        )
        monitor = LiveDraftMonitor(prepared, 0, 2, 2)
        with (
            patch(
                "ffsim.draft_intel.live.sync_prepared_draft",
                side_effect=[OSError("Sleeper unavailable"), SimpleNamespace(state=state)],
            ),
            patch("ffsim.draft_intel.live.calculate_live_recommendation", return_value=None),
            patch("ffsim.draft_intel.live.live_state_summary", return_value={"complete": True}),
        ):
            monitor.run()

        self.assertEqual(monitor.status, "completed")
        self.assertEqual(monitor.sync_count, 1)
        self.assertIsNone(monitor.error)

if __name__ == "__main__":
    unittest.main()
