"""HTTP and SSE plumbing for interactive simulation clients."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field, replace
import json
import logging
import os
from pathlib import Path
from threading import Condition, Event, Lock, Thread
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ffsim.config import AppConfig, save_league_attachment
from ffsim.paths import CACHE_DIR
from ffsim.runtime import create_simulation


LOGGER = logging.getLogger(__name__)
TERMINAL_STATUSES = {"completed", "failed"}


class LeagueRequest(BaseModel):
    league_id: str = Field(min_length=1)
    draft_id: str = Field(min_length=1)

    @field_validator("league_id", "draft_id")
    @classmethod
    def strip_required_id(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Sleeper IDs cannot be blank")
        return value


class SimulationRequest(BaseModel):
    simulations: int | None = Field(default=None, ge=1, le=10_000)
    seed: int | None = None
    workers: int | None = Field(default=None, ge=1, le=32)
    teams_only: bool = False


class DraftPrepareRequest(BaseModel):
    draft_id: str = Field(min_length=1)
    username: str = Field(min_length=1)
    mock_draft_id: str | None = None
    season: int = Field(default=2026, ge=2020, le=2100)
    world_count: int = Field(default=50, ge=2, le=500)

    @field_validator("draft_id", "username", "mock_draft_id")
    @classmethod
    def strip_draft_inputs(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Draft setup values cannot be blank")
        return value


class DraftMonitorRequest(BaseModel):
    poll_seconds: float = Field(default=2.0, ge=0.5, le=30)
    rollout_count: int = Field(default=50, ge=2, le=500)
    candidate_count: int = Field(default=5, ge=2, le=12)


@dataclass
class SimulationJob:
    id: str
    total: int
    seed: int
    workers: int
    teams_only: bool
    status: str = "queued"
    completed: int = 0
    championships: dict = field(default_factory=lambda: defaultdict(int))
    playoff_appearances: dict = field(default_factory=lambda: defaultdict(int))
    division_wins: dict = field(default_factory=lambda: defaultdict(int))
    results: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    events: list = field(default_factory=list, repr=False)
    condition: Condition = field(default_factory=Condition, repr=False)

    def __post_init__(self):
        self.publish("queued", self.snapshot())

    def snapshot(self):
        with self.condition:
            end = self.finished_at or time.time()
            elapsed = end - self.started_at if self.started_at else 0.0
            return {
                "id": self.id,
                "status": self.status,
                "completed": self.completed,
                "total": self.total,
                "progress": self.completed / self.total,
                "seed": self.seed,
                "workers": self.workers,
                "teams_only": self.teams_only,
                "elapsed_seconds": elapsed,
                "simulations_per_second": self.completed / elapsed if elapsed else 0.0,
                "championships": dict(self.championships),
                "playoff_appearances": dict(self.playoff_appearances),
                "division_wins": dict(self.division_wins),
                "error": self.error,
            }

    def set_status(self, status, teams=(), division_teams=()):
        with self.condition:
            self.status = status
            if status == "running":
                self.started_at = time.time()
            for team in teams:
                self.championships[team] = 0
                self.playoff_appearances[team] = 0
            for team in division_teams:
                self.division_wins[team] = 0
            self._publish_locked("status", self.snapshot())

    def record(self, result):
        with self.condition:
            self.completed += 1
            self.championships[result["champion"]] += 1
            for team in result["playoff_teams"]:
                self.playoff_appearances[team] += 1
            for team in result["division_winners"]:
                self.division_wins[team] += 1
            data = self.snapshot()
            data["last_result"] = result
            self._publish_locked("progress", data)

    def complete(self, results):
        with self.condition:
            self.status = "completed"
            self.finished_at = time.time()
            self.results = results
            self._publish_locked("complete", self.snapshot())

    def fail(self, error):
        with self.condition:
            self.status = "failed"
            self.finished_at = time.time()
            self.error = str(error)
            self._publish_locked("failed", self.snapshot())

    def publish(self, event, data):
        with self.condition:
            self._publish_locked(event, data)

    def _publish_locked(self, event, data):
        self.events.append({"id": len(self.events) + 1, "event": event, "data": data})
        self.condition.notify_all()

    def event_at(self, index, timeout=15):
        with self.condition:
            if index >= len(self.events) and self.status not in TERMINAL_STATUSES:
                self.condition.wait(timeout)
            return self.events[index] if index < len(self.events) else None


@dataclass
class LiveDraftMonitor:
    prepared: object
    poll_seconds: float
    rollout_count: int
    candidate_count: int
    status: str = "starting"
    state: dict | None = None
    recommendation: dict | None = None
    error: str | None = None
    sync_count: int = 0
    calculation_count: int = 0
    last_sync_at: float | None = None
    lock: Lock = field(default_factory=Lock, repr=False)
    stopped: Event = field(default_factory=Event, repr=False)

    def snapshot(self):
        with self.lock:
            return {
                "status": self.status,
                "draft_id": self.prepared.live_draft_id,
                "poll_seconds": self.poll_seconds,
                "sync_count": self.sync_count,
                "calculation_count": self.calculation_count,
                "last_sync_at": self.last_sync_at,
                "state": self.state,
                "recommendation": self.recommendation,
                "error": self.error,
            }

    def run(self):
        from ffsim.draft_intel.live import (
            calculate_live_recommendation,
            live_state_summary,
            sync_prepared_draft,
        )

        fingerprint = None
        try:
            with self.lock:
                self.status = "running"
            while not self.stopped.is_set():
                sync = sync_prepared_draft(self.prepared)
                state = sync.state
                current = (
                    state.status,
                    len(state.completed_picks),
                    state.current_roster_id,
                )
                recommendation = self.recommendation
                calculated = False
                if current != fingerprint:
                    recommendation = calculate_live_recommendation(
                        self.prepared,
                        state,
                        self.rollout_count,
                        self.candidate_count,
                    )
                    calculated = recommendation is not None
                    fingerprint = current
                with self.lock:
                    self.state = live_state_summary(self.prepared, state)
                    self.recommendation = recommendation
                    self.sync_count += 1
                    self.calculation_count += int(calculated)
                    self.last_sync_at = time.time()
                    if state.status == "complete":
                        self.status = "completed"
                        return
                self.stopped.wait(self.poll_seconds)
            with self.lock:
                if self.status != "completed":
                    self.status = "stopped"
        except Exception as error:
            LOGGER.exception("Live draft monitor failed for %s", self.prepared.live_draft_id)
            with self.lock:
                self.status = "failed"
                self.error = str(error)

    def stop(self):
        self.stopped.set()


def _run_job(job, base_config):
    try:
        job.set_status("loading")
        config = replace(base_config, simulations=job.total, seed=job.seed)
        simulation = create_simulation(
            config,
            workers=job.workers,
            track_players=not job.teams_only,
        )
        teams = [team.name for team in simulation.league.rosters]
        job.set_status("running", teams, teams if simulation.league.divisions else ())
        results = simulation.run(on_simulation_complete=job.record, show_progress=False)
        job.complete(results)
    except Exception as error:
        LOGGER.exception("Simulation job %s failed", job.id)
        job.fail(error)


def _run_refresh(state, league_id, draft_id, weeks, season=2026):
    try:
        from ffsim.draft_intel.market import refresh_fantasypros_adp
        from ffsim.loaders.league import refresh_league
        from ffsim.loaders.players import PlayerLoader
        from ffsim.simulation.season import refresh_matchups

        refresh_league(league_id, draft_id)
        player_loader = PlayerLoader()
        player_loader.refresh()
        refresh_matchups(league_id, weeks)
        market = refresh_fantasypros_adp(
            season=season,
            sleeper_players_path=player_loader.sleeper_players_file,
        )
        state.refresh = {
            "status": "ready",
            "league_id": league_id,
            "draft_id": draft_id,
            "market": market,
            "error": None,
        }
    except Exception as error:
        LOGGER.exception("League refresh failed for %s", league_id)
        state.refresh = {
            "status": "failed",
            "league_id": league_id,
            "draft_id": draft_id,
            "market": None,
            "error": str(error),
        }


def _run_draft_preparation(state, config_path, request):
    from ffsim.draft_intel.live import prepare_draft

    def progress(stage):
        with state.prepare_lock:
            state.draft_preparation["stage"] = stage

    try:
        prepared = prepare_draft(
            config_path,
            request.draft_id,
            request.username,
            mock_draft_id=request.mock_draft_id,
            season=request.season,
            world_count=request.world_count,
            progress=progress,
        )
        with state.prepare_lock:
            state.prepared_draft = prepared
            state.draft_preparation = {
                **prepared.summary,
                "stage": "Ready",
                "error": None,
            }
    except Exception as error:
        LOGGER.exception("Draft preparation failed for %s", request.draft_id)
        with state.prepare_lock:
            state.prepared_draft = None
            state.draft_preparation.update({
                "status": "failed",
                "error": str(error),
            })
def create_app(config_path="config.json"):
    app = FastAPI(title="FFSim API", version="1.0")
    # ponytail: open CORS is for the local UI; restrict origins before public hosting.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.config_path = config_path
    app.state.jobs = {}
    app.state.jobs_lock = Lock()

    def get_job(job_id):
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Simulation job not found")
        return job

    app.state.refresh = {
        "status": "idle",
        "league_id": None,
        "draft_id": None,
        "market": None,
        "error": None,
    }
    app.state.refresh_lock = Lock()
    app.state.prepare_lock = Lock()
    app.state.prepared_draft = None
    app.state.draft_preparation = {
        "status": "idle",
        "stage": None,
        "error": None,
    }
    app.state.live_monitor = None

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/league")
    def current_league():
        try:
            config = AppConfig.from_file(app.state.config_path)
            league_id = config.league_id
            draft_id = config.draft_id
        except ValueError:
            league_id = None
            draft_id = None
        name = None
        draft = None
        market_context = None
        if league_id:
            cache = CACHE_DIR / f"league_{league_id}.json"
            if cache.exists():
                snapshot = json.loads(cache.read_text())
                league = snapshot.get("league", {})
                name = league.get("name")
                from ffsim.draft_intel.market_model import resolve_league_market_context

                market_context = resolve_league_market_context(league)
                if draft_id and (snapshot.get("draft_summary") or {}).get("draft_id") == draft_id:
                    draft = snapshot["draft_summary"]
        return {
            "league_id": league_id,
            "draft_id": draft_id,
            "name": name,
            "draft": draft,
            "market_context": market_context,
            "ready": name is not None and (draft_id is None or draft is not None),
            "refresh": dict(app.state.refresh),
        }

    @app.get("/api/leagues")
    def find_leagues(username: str, season: int = 2026):
        from ffsim.loaders.league import leagues_for_username

        try:
            leagues = leagues_for_username(username, season)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        from ffsim.loaders.league import league_summary

        return [league_summary(league) for league in leagues]

    @app.get("/api/leagues/{league_id}/drafts")
    def find_drafts(league_id: str):
        from ffsim.loaders.league import draft_summary, league_and_drafts, league_summary

        try:
            league, drafts = league_and_drafts(league_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        return {
            "league": league_summary(league),
            "drafts": [draft_summary(league, draft) for draft in drafts],
        }

    @app.post("/api/league", status_code=202)
    def select_league(request: LeagueRequest):
        from ffsim.loaders.league import league_and_drafts

        try:
            _, drafts = league_and_drafts(request.league_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        if not any(str(draft["draft_id"]) == request.draft_id for draft in drafts):
            raise HTTPException(
                status_code=400,
                detail=f"Draft {request.draft_id} does not belong to league {request.league_id}",
            )
        with app.state.refresh_lock:
            if app.state.refresh["status"] == "running":
                raise HTTPException(status_code=409, detail="A league refresh is already running")
            with app.state.jobs_lock:
                if any(
                    job.status not in TERMINAL_STATUSES
                    for job in app.state.jobs.values()
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="A simulation is running; wait for it to finish",
                    )
            config = save_league_attachment(
                app.state.config_path,
                request.league_id,
                request.draft_id,
            )
            app.state.refresh = {
                "status": "running",
                "league_id": request.league_id,
                "draft_id": request.draft_id,
                "market": None,
                "error": None,
            }
        weeks = config.regular_season_weeks + 3
        Thread(
            target=_run_refresh,
            args=(app.state, request.league_id, request.draft_id, weeks),
            daemon=True,
        ).start()
        return {
            "status": "running",
            "league_id": request.league_id,
            "draft_id": request.draft_id,
        }

    @app.post("/api/draft-intel/prepare", status_code=202)
    def start_draft_preparation(request: DraftPrepareRequest):
        with app.state.prepare_lock:
            if app.state.draft_preparation["status"] == "running":
                raise HTTPException(status_code=409, detail="Draft preparation is already running")
            if app.state.live_monitor and app.state.live_monitor.snapshot()["status"] in {
                "starting", "running"
            }:
                raise HTTPException(status_code=409, detail="Stop live monitoring before preparing")
            app.state.prepared_draft = None
            app.state.draft_preparation = {
                "status": "running",
                "stage": "Starting",
                "draft_id": request.draft_id,
                "mock_draft_id": request.mock_draft_id,
                "error": None,
            }
        Thread(
            target=_run_draft_preparation,
            args=(app.state, app.state.config_path, request),
            daemon=True,
        ).start()
        return dict(app.state.draft_preparation)

    @app.get("/api/draft-intel/prepare")
    def draft_preparation_status():
        with app.state.prepare_lock:
            return dict(app.state.draft_preparation)

    @app.post("/api/draft-intel/monitor", status_code=202)
    def start_draft_monitor(request: DraftMonitorRequest):
        with app.state.prepare_lock:
            prepared = app.state.prepared_draft
            preparation = dict(app.state.draft_preparation)
        if prepared is None or preparation.get("status") != "ready":
            raise HTTPException(status_code=409, detail="Prepare the draft first")
        if not preparation.get("monitor_ready"):
            blockers = ", ".join(preparation.get("blockers") or ())
            raise HTTPException(status_code=409, detail=f"Draft is not monitor-ready: {blockers}")
        existing = app.state.live_monitor
        if existing and existing.snapshot()["status"] in {"starting", "running"}:
            raise HTTPException(status_code=409, detail="Live monitoring is already running")
        monitor = LiveDraftMonitor(
            prepared,
            request.poll_seconds,
            request.rollout_count,
            request.candidate_count,
        )
        app.state.live_monitor = monitor
        Thread(target=monitor.run, daemon=True).start()
        return monitor.snapshot()

    @app.get("/api/draft-intel/monitor")
    def draft_monitor_status():
        monitor = app.state.live_monitor
        return monitor.snapshot() if monitor else {"status": "idle"}

    @app.post("/api/draft-intel/monitor/stop")
    def stop_draft_monitor():
        monitor = app.state.live_monitor
        if monitor is None:
            return {"status": "idle"}
        monitor.stop()
        return monitor.snapshot()

    @app.post("/api/simulations", status_code=202)
    def start_simulation(request: SimulationRequest):
        config = AppConfig.from_file(app.state.config_path)
        job = SimulationJob(
            id=uuid4().hex,
            total=request.simulations or config.simulations,
            seed=config.seed if request.seed is None else request.seed,
            workers=request.workers or min(4, os.cpu_count() or 1),
            teams_only=request.teams_only,
        )
        with app.state.jobs_lock:
            if any(
                existing.status not in TERMINAL_STATUSES
                for existing in app.state.jobs.values()
            ):
                raise HTTPException(status_code=409, detail="A simulation is already running")
            app.state.jobs[job.id] = job
        Thread(target=_run_job, args=(job, config), daemon=True).start()
        return job.snapshot()

    @app.get("/api/simulations/{job_id}")
    def simulation_status(job_id: str):
        return get_job(job_id).snapshot()

    @app.get("/api/simulations/{job_id}/results")
    def simulation_results(job_id: str):
        job = get_job(job_id)
        if job.status == "failed":
            raise HTTPException(status_code=500, detail=job.error)
        if job.status != "completed":
            raise HTTPException(status_code=409, detail="Simulation is not complete")
        return job.results

    @app.get("/api/simulations/{job_id}/events")
    async def simulation_events(job_id: str, request: Request):
        job = get_job(job_id)
        try:
            index = max(0, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            index = 0

        async def stream():
            nonlocal index
            while not await request.is_disconnected():
                event = await asyncio.to_thread(job.event_at, index)
                if event is None:
                    yield ": keep-alive\n\n"
                    continue
                index += 1
                yield (
                    f"id: {event['id']}\n"
                    f"event: {event['event']}\n"
                    f"data: {json.dumps(event['data'], separators=(',', ':'))}\n\n"
                )
                if event["event"] in {"complete", "failed"}:
                    break

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
