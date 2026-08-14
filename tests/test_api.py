import json
import tempfile
import time
from threading import Event, Thread
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
    _state_fingerprint,
    create_app,
)
from ffsim.config import AppConfig
from ffsim.draft_intel.decision import _state_signature
from tests.test_decision import draft_state


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
        prepare = DraftPrepareRequest(
            draft_id=" real ",
            mock_draft_id=" mock ",
            username=" matt ",
        )
        self.assertEqual(prepare.model_dump()["mock_draft_id"], "mock")
        self.assertEqual(prepare.world_count, 300)
        self.assertEqual(DraftMonitorRequest().rollout_count, 1_000)
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
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        state = SimpleNamespace(
            status="complete",
            completed_picks=(),
            current_pick_no=None,
            current_roster_id=None,
            pick_owners=(),
        )
        monitor = LiveDraftMonitor(prepared, 0, 2, 2)
        with (
            patch(
                "ffsim.draft_intel.live.sync_prepared_draft",
                side_effect=[OSError("Sleeper unavailable"), SimpleNamespace(state=state)],
            ),
            patch("ffsim.draft_intel.live.live_state_summary", return_value={"complete": True}),
        ):
            monitor.run()

        self.assertEqual(monitor.status, "completed")
        self.assertEqual(monitor.sync_count, 1)
        self.assertIsNone(monitor.error)

    def test_live_monitor_syncs_while_a_stale_recommendation_is_calculating(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        calculating = Event()
        release = Event()
        on_clock = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        complete = SimpleNamespace(
            status="complete",
            completed_picks=(object(),),
            current_pick_no=None,
            current_roster_id=None,
            pick_owners=(1,),
        )
        calls = 0

        def sync(_prepared, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return SimpleNamespace(state=on_clock)
            self.assertTrue(calculating.wait(5))
            return SimpleNamespace(state=complete)

        def evaluate(*_args):
            calculating.set()
            release.wait(5)
            return {"pick": 1}

        monitor = LiveDraftMonitor(prepared, 0, 2, 2)
        try:
            with (
                patch("ffsim.draft_intel.live.sync_prepared_draft", side_effect=sync),
                patch(
                    "ffsim.draft_intel.live.live_candidate_pool",
                    return_value=["c1", "c2"],
                ),
                patch(
                    "ffsim.draft_intel.live.evaluate_live_candidates",
                    side_effect=evaluate,
                ),
                patch(
                    "ffsim.draft_intel.live.live_recommendation_payload",
                    side_effect=lambda _prepared, _state, evaluations, _count: evaluations[-1],
                ),
                patch(
                    "ffsim.draft_intel.live.live_state_summary",
                    side_effect=lambda _prepared, state: {"status": state.status},
                ),
            ):
                monitor.run()
        finally:
            release.set()

        self.assertEqual(monitor.status, "completed")
        self.assertEqual(monitor.sync_count, 2)
        self.assertEqual(monitor.state, {"status": "complete"})
        self.assertIsNone(monitor.recommendation)
        self.assertEqual(monitor.calculation_count, 0)

    def test_rapid_picks_coalesce_to_the_newest_calculation_state(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 2, 2)
        states = [
            SimpleNamespace(
                status="drafting",
                completed_picks=(object(),) * picks,
                current_pick_no=picks + 1,
                current_roster_id=1,
                pick_owners=(1, 1, 1),
            )
            for picks in range(3)
        ]
        first_calculating = Event()
        release_first = Event()
        calculated = []

        def evaluate(_prepared, state, *_args):
            calculated.append(state)
            if len(calculated) == 1:
                first_calculating.set()
                self.assertTrue(release_first.wait(5))
            return {"pick": state.current_pick_no}

        def sync(_prepared, **_kwargs):
            call = sync.calls = getattr(sync, "calls", 0) + 1
            if call == 1:
                return SimpleNamespace(state=states[0])
            if call == 2:
                self.assertTrue(first_calculating.wait(5))
                return SimpleNamespace(state=states[1])
            if call == 3:
                return SimpleNamespace(state=states[2])
            if call == 4:
                release_first.set()
                deadline = time.time() + 5
                while (
                    monitor.snapshot()["recommendation_status"] != "ready"
                    and time.time() < deadline
                ):
                    time.sleep(0.001)
                monitor.stopped.set()
            return SimpleNamespace(state=states[2])

        with (
            patch("ffsim.draft_intel.live.sync_prepared_draft", side_effect=sync),
            patch("ffsim.draft_intel.live.live_candidate_pool", return_value=["c"]),
            patch(
                "ffsim.draft_intel.live.evaluate_live_candidates",
                side_effect=evaluate,
            ),
            patch(
                "ffsim.draft_intel.live.live_recommendation_payload",
                side_effect=lambda _prepared, _state, evaluations, _count: evaluations[-1],
            ),
            patch(
                "ffsim.draft_intel.live.live_state_summary",
                side_effect=lambda _prepared, state: {"pick": state.current_pick_no},
            ),
        ):
            monitor.run()

        self.assertEqual(monitor.status, "stopped")
        self.assertEqual(calculated, [states[0], states[2]])
        self.assertEqual(monitor.recommendation, {"pick": 3})
        self.assertEqual(monitor.recommendation_status, "ready")
        self.assertEqual(monitor.recommendation_pick_no, 3)
        self.assertIsNone(monitor.recommendation_discarded_pick_no)
        self.assertEqual(monitor.calculation_count, 1)

    def test_calculation_publishes_a_preliminary_pass_then_refines(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 1_000, 5)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        monitor.pending_state = state
        monitor.state_fingerprint = ("drafting", 0, 1, (1,))
        monitor.calculation_event.set()
        observed = []

        def evaluate(_prepared, _state, rollout_count, candidates, *_args):
            observed.append(
                (rollout_count, monitor.recommendation, monitor.recommendation_status)
            )
            return {
                "rollout_count": rollout_count,
                "candidates": [
                    {"player_id": candidate_id} for candidate_id in candidates
                ],
            }

        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: ["a", "b", "c", "d", "e"],
                evaluate,
                lambda _prepared, _state, evaluations, _count: evaluations[-1],
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_status"] != "ready"
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(observed, [
            (100, None, "calculating"),
            (
                1_000,
                {
                    "rollout_count": 100,
                    "candidates": [
                        {"player_id": candidate_id}
                        for candidate_id in ["a", "b", "c", "d", "e"]
                    ],
                },
                "refining",
            ),
        ])
        self.assertEqual(monitor.recommendation["rollout_count"], 1_000)
        self.assertEqual(monitor.recommendation_status, "ready")
        self.assertEqual(monitor.calculation_count, 1)

    def test_opponent_turn_calculates_league_equity_without_a_recommendation(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 50, 2)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(object(),),
            current_pick_no=2,
            current_roster_id=2,
            pick_owners=(1, 2),
        )
        monitor.pending_state = state
        monitor.state_fingerprint = ("drafting", 1, 2, (1, 2))
        monitor.calculation_event.set()
        candidate_calls = []
        equity_calls = []

        def evaluate_equity(_prepared, _state, count, _temperature):
            equity_calls.append(count)
            return {"count": count}

        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: candidate_calls.append("pool"),
                lambda *_args: candidate_calls.append("evaluate"),
                lambda *_args: {},
                evaluate_equity,
                lambda _prepared, evaluation: {"rosters": [], **evaluation},
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["league_equity_status"] != "ready"
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(candidate_calls, [])
        self.assertEqual(equity_calls, [12, 50])
        self.assertEqual(monitor.recommendation_status, "idle")
        self.assertEqual(monitor.league_equity, {"rosters": [], "count": 50})
        self.assertEqual(monitor.league_equity_calculation_count, 1)

    def test_the_broad_screen_keeps_all_options_after_refining_five_finalists(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 1_000, 2, 6)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        monitor.pending_state = state
        monitor.state_fingerprint = ("drafting", 0, 1, (1,))
        monitor.calculation_event.set()
        evaluated = []
        published = []

        def evaluate(_prepared, _state, rollout_count, batch, *_args):
            evaluated.append((rollout_count, list(batch), list(_args[-1])))
            return {"batch": list(batch)}

        def payload(_prepared, _state, evaluations, pool_count):
            batches = [evaluation["batch"] for evaluation in evaluations]
            candidates = list(reversed([
                candidate_id for batch in batches for candidate_id in batch
            ]))
            published.append((
                batches,
                pool_count,
                monitor.recommendation_status,
            ))
            return {
                "batches": len(evaluations),
                "candidates": [
                    {"player_id": candidate_id} for candidate_id in candidates
                ],
            }

        worker = Thread(
            target=monitor.calculate,
            args=(lambda *_args: ["a", "b", "c", "d", "e", "f"], evaluate, payload),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_status"] != "ready"
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(evaluated, [
            (100, ["a", "b"], ["a", "b", "c", "d", "e", "f"]),
            (100, ["c", "d", "e", "f"], ["a", "b", "c", "d", "e", "f"]),
            (1_000, ["f", "e", "d", "c", "b"], ["f", "e", "d", "c", "b"]),
        ])
        self.assertEqual(published, [
            ([["a", "b"]], 6, "calculating"),
            ([["a", "b"], ["c", "d", "e", "f"]], 6, "expanding"),
            ([["f", "e", "d", "c", "b"]], 6, "refining"),
        ])
        self.assertEqual(monitor.recommendation["batches"], 1)
        self.assertEqual(
            monitor.recommendation["screened_candidates"],
            [{"player_id": "a"}],
        )
        self.assertEqual(monitor.recommendation["screened_rollout_count"], 100)
        self.assertEqual(monitor.recommendation["candidates_evaluated"], 6)
        self.assertEqual(monitor.recommendation_status, "ready")
        self.assertEqual(monitor.calculation_count, 1)

    def test_refinement_extends_screen_rollouts_when_merge_is_available(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 1_000, 5)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        monitor.pending_state = state
        monitor.state_fingerprint = ("drafting", 0, 1, (1,))
        monitor.calculation_event.set()
        evaluated = []
        merged = []

        def evaluate(_prepared, _state, rollout_ids, batch, *_args):
            evaluated.append((rollout_ids, tuple(batch)))
            return {
                "candidates": [
                    {"player_id": candidate_id} for candidate_id in batch
                ],
            }

        def merge(screen_evaluations, extension):
            merged.append((tuple(screen_evaluations), extension))
            return extension

        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: ["a", "b", "c", "d", "e"],
                evaluate,
                lambda _prepared, _state, evaluations, _count: evaluations[-1],
                None,
                None,
                None,
                merge,
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_status"] != "ready"
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        # Refinement evaluates only the unseen rollout IDs, in stages, and
        # merges them with the screen instead of recomputing 0-99.
        self.assertEqual(evaluated, [
            (100, ("a", "b", "c", "d", "e")),
            (range(100, 300), ("a", "b", "c", "d", "e")),
            (range(300, 600), ("a", "b", "c", "d", "e")),
            (range(600, 1_000), ("a", "b", "c", "d", "e")),
        ])
        self.assertEqual(len(merged), 3)
        self.assertEqual(monitor.recommendation_status, "ready")

    def test_racing_refinement_drops_dominated_candidates_and_stops_on_ties(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        evaluated = []

        def evaluate(_prepared, _state, rollout_ids, batch, *_args):
            evaluated.append((rollout_ids, tuple(batch)))
            return {
                "candidates": [
                    {"player_id": candidate_id} for candidate_id in batch
                ],
            }

        def run(survivors_result, advantage):
            monitor = LiveDraftMonitor(prepared, 0, 1_000, 5)
            monitor.pending_state = state
            monitor.state_fingerprint = ("drafting", 0, 1, (1,))
            monitor.calculation_event.set()
            worker = Thread(
                target=monitor.calculate,
                args=(
                    lambda *_args: ["a", "b", "c", "d", "e"],
                    evaluate,
                    lambda _prepared, _state, evaluations, _count: evaluations[-1],
                    None,
                    None,
                    None,
                    lambda _screen, extension: extension,
                    None,
                    lambda _evaluation: (survivors_result, advantage),
                ),
            )
            worker.start()
            deadline = time.time() + 5
            while (
                monitor.snapshot()["recommendation_status"] != "ready"
                and time.time() < deadline
            ):
                time.sleep(0.001)
            monitor.stop()
            worker.join(5)
            return monitor

        # Dominated candidates are dropped before the deeper extensions.
        monitor = run(("a", "b"), 0.05)
        self.assertEqual(evaluated, [
            (100, ("a", "b", "c", "d", "e")),
            (range(100, 300), ("a", "b", "c", "d", "e")),
            (range(300, 600), ("a", "b")),
            (range(600, 1_000), ("a", "b")),
        ])
        self.assertEqual(
            [row["player_id"] for row in monitor.recommendation["screened_candidates"]],
            ["c", "d", "e"],
        )

        # A statistically bounded toss-up stops at the intermediate stage.
        evaluated.clear()
        monitor = run(("a", "b", "c", "d", "e"), 0.001)
        self.assertEqual(evaluated, [
            (100, ("a", "b", "c", "d", "e")),
            (range(100, 300), ("a", "b", "c", "d", "e")),
        ])
        self.assertEqual(monitor.recommendation["screened_candidates"], [])
        self.assertEqual(monitor.recommendation_status, "ready")

    def test_speculative_screen_is_reused_only_for_the_realized_state(self):
        prepared = SimpleNamespace(
            live_draft_id="mock", user_roster_id=2, player_details={}
        )
        monitor = LiveDraftMonitor(prepared, 0, 100, 2)
        waiting = draft_state()
        evaluated = []

        def evaluate(_prepared, state_arg, rollout_count, batch, *_args):
            evaluated.append(
                (state_arg.current_pick_no, rollout_count, tuple(batch))
            )
            return SimpleNamespace(
                state_signature=_state_signature(state_arg), candidates=[]
            )

        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: ["a", "b", "c"],
                evaluate,
                lambda _prepared, _state, _evaluations, _count: {"candidates": []},
                None,
                None,
                None,
                None,
                lambda _prepared, state_arg, _temperature: state_arg.with_pick("p1"),
            ),
        )
        monitor.pending_state = waiting
        monitor.state_fingerprint = _state_fingerprint(waiting)
        monitor.calculation_event.set()
        worker.start()
        deadline = time.time() + 5
        while monitor.speculative is None and time.time() < deadline:
            time.sleep(0.001)
        # The opponent is on the clock, so the screen ran speculatively
        # against the predicted next state (pick 2, user on the clock).
        self.assertEqual(evaluated, [(2, 100, ("a", "b")), (2, 100, ("c",))])

        realized = waiting.with_pick("p1")
        with monitor.lock:
            monitor.pending_state = realized
            monitor.state_fingerprint = _state_fingerprint(realized)
        monitor.calculation_event.set()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_status"] != "ready"
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(monitor.recommendation_status, "ready")
        # The realized state matched the prediction exactly: nothing recomputed.
        self.assertEqual(len(evaluated), 2)
        self.assertIsNone(monitor.speculative)

    def test_speculative_screen_is_discarded_when_the_prediction_missed(self):
        prepared = SimpleNamespace(
            live_draft_id="mock", user_roster_id=2, player_details={}
        )
        monitor = LiveDraftMonitor(prepared, 0, 100, 2)
        realized = draft_state().with_pick("p2")
        evaluated = []

        def evaluate(_prepared, state_arg, rollout_count, batch, *_args):
            evaluated.append(tuple(batch))
            return SimpleNamespace(
                state_signature=_state_signature(state_arg), candidates=[]
            )

        monitor.speculative = {
            "signature": _state_signature(draft_state().with_pick("p1")),
            "candidates": ("a", "b", "c"),
            "evaluations": [SimpleNamespace(candidates=[])],
        }
        monitor.pending_state = realized
        monitor.state_fingerprint = _state_fingerprint(realized)
        monitor.calculation_event.set()
        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: ["a", "b", "c"],
                evaluate,
                lambda _prepared, _state, _evaluations, _count: {"candidates": []},
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_status"] != "ready"
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(monitor.recommendation_status, "ready")
        # A missed prediction is discarded and the screen recomputed fresh.
        self.assertEqual(evaluated, [("a", "b"), ("c",)])

    def test_refinement_evaluates_the_injected_finalist_selection(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 1_000, 5)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        monitor.pending_state = state
        monitor.state_fingerprint = ("drafting", 0, 1, (1,))
        monitor.calculation_event.set()
        evaluated = []
        selected = []

        def evaluate(_prepared, _state, rollout_count, batch, *_args):
            evaluated.append((rollout_count, tuple(batch)))
            return {
                "candidates": [
                    {"player_id": candidate_id} for candidate_id in batch
                ],
            }

        def selector(prepared_arg, state_arg, rows, count):
            selected.append((
                prepared_arg,
                state_arg,
                [row["player_id"] for row in rows],
                count,
            ))
            return ("e", "a")

        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: ["a", "b", "c", "d", "e"],
                evaluate,
                lambda _prepared, _state, evaluations, _count: evaluations[-1],
                None,
                None,
                selector,
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_status"] != "ready"
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(evaluated, [
            (100, ("a", "b", "c", "d", "e")),
            (1_000, ("e", "a")),
        ])
        self.assertEqual(selected, [
            (prepared, state, ["a", "b", "c", "d", "e"], 5),
        ])
        self.assertEqual(
            monitor.recommendation["screened_candidates"],
            [{"player_id": "b"}, {"player_id": "c"}, {"player_id": "d"}],
        )
        self.assertEqual(monitor.recommendation_status, "ready")

    def test_refinement_is_abandoned_when_the_draft_advances(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 1_000, 5)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        monitor.pending_state = state
        monitor.state_fingerprint = ("drafting", 0, 1, (1,))
        monitor.calculation_event.set()
        passes = []

        def evaluate(_prepared, _state, rollout_count, _candidates, *_args):
            passes.append(rollout_count)
            with monitor.lock:
                monitor.state_fingerprint = ("drafting", 1, 2, (1,))
            return {"rollout_count": rollout_count}

        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: ["a", "b", "c", "d", "e"],
                evaluate,
                lambda _prepared, _state, evaluations, _count: evaluations[-1],
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_discarded_pick_no"] is None
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(passes, [100])
        self.assertIsNone(monitor.recommendation)
        self.assertEqual(monitor.recommendation_discarded_pick_no, 1)
        self.assertEqual(monitor.calculation_count, 0)

    def test_a_result_for_an_advanced_draft_is_marked_discarded(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        monitor = LiveDraftMonitor(prepared, 0, 2, 2)
        monitor.pending_state = SimpleNamespace(
            status="drafting",
            completed_picks=(),
            current_pick_no=1,
            current_roster_id=1,
            pick_owners=(1,),
        )
        monitor.state_fingerprint = ("drafting", 1, 2, (1,))
        monitor.calculation_event.set()
        calls = []

        def evaluate(*args):
            calls.append(args)
            return {"pick": 1}

        worker = Thread(
            target=monitor.calculate,
            args=(
                lambda *_args: ["c"],
                evaluate,
                lambda _prepared, _state, evaluations, _count: evaluations[-1],
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while (
            monitor.snapshot()["recommendation_discarded_pick_no"] is None
            and time.time() < deadline
        ):
            time.sleep(0.001)
        monitor.stop()
        worker.join(5)

        self.assertEqual(calls, [])
        self.assertIsNone(monitor.recommendation)
        self.assertEqual(monitor.recommendation_discarded_pick_no, 1)
        self.assertEqual(monitor.calculation_count, 0)

    def test_a_full_pick_sheet_completes_despite_stale_draft_metadata(self):
        prepared = SimpleNamespace(live_draft_id="mock", user_roster_id=1)
        state = SimpleNamespace(
            status="drafting",
            completed_picks=(object(),) * 4,
            current_pick_no=None,
            current_roster_id=None,
            pick_owners=(1,) * 4,
        )
        monitor = LiveDraftMonitor(prepared, 0, 2, 2)
        with (
            patch(
                "ffsim.draft_intel.live.sync_prepared_draft",
                return_value=SimpleNamespace(state=state),
            ),
            patch("ffsim.draft_intel.live.live_state_summary", return_value={}),
        ):
            monitor.run()
        self.assertEqual(monitor.status, "completed")


if __name__ == "__main__":
    unittest.main()
