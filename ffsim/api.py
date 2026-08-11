"""HTTP and SSE plumbing for interactive simulation clients."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field, replace
import json
import logging
import os
from pathlib import Path
from threading import Condition, Lock, Thread
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ffsim.config import AppConfig
from ffsim.paths import CACHE_DIR
from ffsim.runtime import create_simulation


LOGGER = logging.getLogger(__name__)
TERMINAL_STATUSES = {"completed", "failed"}


class LeagueRequest(BaseModel):
    league_id: str = Field(min_length=1)


class SimulationRequest(BaseModel):
    simulations: int | None = Field(default=None, ge=1, le=10_000)
    seed: int | None = None
    workers: int | None = Field(default=None, ge=1, le=32)
    teams_only: bool = False


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

    def set_status(self, status, teams=()):
        with self.condition:
            self.status = status
            if status == "running":
                self.started_at = time.time()
            for team in teams:
                self.championships[team] = 0
                self.playoff_appearances[team] = 0
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


def _run_job(job, base_config):
    try:
        job.set_status("loading")
        config = replace(base_config, simulations=job.total, seed=job.seed)
        simulation = create_simulation(
            config,
            workers=job.workers,
            track_players=not job.teams_only,
        )
        job.set_status("running", [team.name for team in simulation.league.rosters])
        results = simulation.run(on_simulation_complete=job.record, show_progress=False)
        job.complete(results)
    except Exception as error:
        LOGGER.exception("Simulation job %s failed", job.id)
        job.fail(error)


def _run_refresh(state, league_id, weeks):
    try:
        from ffsim.loaders.league import refresh_league
        from ffsim.loaders.players import PlayerLoader
        from ffsim.simulation.season import refresh_matchups

        PlayerLoader().refresh()
        refresh_league(league_id)
        refresh_matchups(league_id, weeks)
        state.refresh = {"status": "ready", "league_id": league_id, "error": None}
    except Exception as error:
        LOGGER.exception("League refresh failed for %s", league_id)
        state.refresh = {"status": "failed", "league_id": league_id, "error": str(error)}


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

    app.state.refresh = {"status": "idle", "league_id": None, "error": None}
    app.state.refresh_lock = Lock()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/league")
    def current_league():
        try:
            league_id = AppConfig.from_file(app.state.config_path).league_id
        except ValueError:
            league_id = None
        name = None
        if league_id:
            cache = CACHE_DIR / f"league_{league_id}.json"
            if cache.exists():
                name = json.loads(cache.read_text()).get("league", {}).get("name")
        return {
            "league_id": league_id,
            "name": name,
            "ready": name is not None,
            "refresh": dict(app.state.refresh),
        }

    @app.get("/api/leagues")
    def find_leagues(username: str, season: int = 2026):
        from ffsim.loaders.league import leagues_for_username

        try:
            leagues = leagues_for_username(username, season)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        return [
            {
                "league_id": str(league["league_id"]),
                "name": league.get("name") or "Unnamed",
                "status": league.get("status", "unknown"),
                "total_rosters": league.get("total_rosters"),
                "season": league.get("season"),
            }
            for league in leagues
        ]

    @app.post("/api/league", status_code=202)
    def select_league(request: LeagueRequest):
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
            app.state.refresh = {
                "status": "running",
                "league_id": request.league_id,
                "error": None,
            }
        path = Path(app.state.config_path)
        data = json.loads(path.read_text())
        data["league_id"] = str(request.league_id)
        path.write_text(json.dumps(data, indent=2) + "\n")
        weeks = AppConfig.from_file(app.state.config_path).regular_season_weeks + 3
        Thread(
            target=_run_refresh, args=(app.state, request.league_id, weeks), daemon=True
        ).start()
        return {"status": "running", "league_id": request.league_id}

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
