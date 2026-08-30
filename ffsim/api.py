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
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ffsim.config import AppConfig, save_league_attachment
from ffsim.draft_intel.decision import PRACTICAL_TIE_POINTS
from ffsim.draft_intel.decision import _state_signature as _decision_state_signature
from ffsim.draft_intel.telemetry import DraftTelemetry
from ffsim.paths import CACHE_DIR
from ffsim.runtime import create_simulation


LOGGER = logging.getLogger(__name__)
TERMINAL_STATUSES = {"completed", "failed"}
PRELIMINARY_ROLLOUT_COUNT = 12
SCREEN_ROLLOUT_COUNT = 100
FINALIST_COUNT = 5
LEAGUE_EQUITY_ROLLOUT_COUNT = 50
# Fixed-budget refinement publishes intermediate stages while keeping every
# finalist through the configured rollout budget.
REFINEMENT_STAGE_ROLLOUT_COUNTS = (150, 225)
# Legacy diagnostic threshold retained for audit-tool compatibility. Production
# does not eliminate or stop on an intermediate confidence interval.
REFINEMENT_REGRET_STOP = PRACTICAL_TIE_POINTS
# Stages announced by prepare_draft via its progress callback; the world-bank
# stage is skipped when blockers exist, so a blocked run tops out at 5/6.
PREPARATION_STAGE_COUNT = 6


def _state_fingerprint(state):
    return (
        state.status,
        len(state.completed_picks),
        state.current_roster_id,
        tuple(state.pick_owners),
    )


def _watchlist_candidate(row):
    """Drop stage-local tier membership from a screen-only candidate."""
    return {key: value for key, value in row.items() if key != "is_top_tier"}


def _recommendation_stage_payload(
    recommendation,
    *,
    phase,
    cumulative_duration_seconds,
    stage_duration_seconds,
    evaluated_candidate_ids,
    refined_candidate_ids,
    survivor_candidate_ids,
    stop_reason,
    stage_candidate_rollout_work,
    cumulative_candidate_rollout_work,
    speculation_attempted,
    speculation_hit,
    speculation_miss,
):
    rows = {
        str(row["player_id"]): row
        for row in recommendation.get("candidates", ())
    }
    headline_id = recommendation.get("recommended_candidate_id")
    headline = rows.get(str(headline_id), {})
    return {
        "schema_version": 2,
        "phase": phase,
        "cumulative_duration_seconds": cumulative_duration_seconds,
        "stage_duration_seconds": stage_duration_seconds,
        "rollout_count": recommendation.get("rollout_count"),
        "evaluated_candidate_ids": list(evaluated_candidate_ids),
        "refined_candidate_ids": list(refined_candidate_ids),
        "q_leader_candidate_id": recommendation.get("q_leader_candidate_id"),
        "displayed_headline_candidate_id": headline_id,
        "decision_status": recommendation.get("decision_status"),
        "headline_tie_break_basis": recommendation.get(
            "headline_tie_break_basis"
        ),
        "practical_co_leader_candidate_ids": list(
            recommendation.get("co_leader_candidate_ids", ())
        ),
        "paired_value_bounds_vs_q_leader": list(
            recommendation.get("paired_value_bounds_vs_q_leader", ())
        ),
        "survivor_candidate_ids": list(survivor_candidate_ids),
        "stop_reason": stop_reason,
        "stage_candidate_rollout_work": stage_candidate_rollout_work,
        "cumulative_candidate_rollout_work": cumulative_candidate_rollout_work,
        "speculation_attempted": speculation_attempted,
        "speculation_hit": speculation_hit,
        "speculation_miss": speculation_miss,
        "target_candidate_id": headline_id,
        "survival_branch_root_candidate_id": headline.get(
            "survival_branch_root_candidate_id"
        ),
        "opportunity_evidence_branch_root_candidate_id": headline.get(
            "opportunity_evidence_branch_root_candidate_id"
        ),
        "target_available_count": headline.get("target_available_count"),
        "target_selected_when_available_count": headline.get(
            "target_selected_when_available_count"
        ),
        "target_rollout_count": headline.get("target_rollout_count"),
        "run_signature": recommendation.get("run_signature"),
    }


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


class PersonalRankRequest(BaseModel):
    player_id: str = Field(min_length=1)
    offset: int


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
    world_count: int = Field(default=300, ge=2, le=500)
    force_refresh: bool = False

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
    poll_seconds: float = Field(default=1.0, ge=0.5, le=30)
    rollout_count: int = Field(default=300, ge=2, le=2_000)
    candidate_count: int = Field(default=9, ge=2, le=12)
    candidate_breadth: int = Field(default=40, ge=2, le=100)
    temperature: float | None = Field(default=None, gt=0, le=5)
    recommendation_mode: Literal["simulation", "projection"] = "simulation"


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
    candidate_breadth: int = 40
    temperature: float | None = None
    recommendation_mode: str = "simulation"
    telemetry: DraftTelemetry | None = field(default=None, repr=False)
    alpha_shadow_collector: object | None = field(default=None, repr=False)
    session_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "starting"
    state: dict | None = None
    projection_board: dict | None = None
    projection_board_error: str | None = None
    recommendation: dict | None = None
    recommendation_status: str = "idle"
    recommendation_pick_no: int | None = None
    recommendation_error: str | None = None
    recommendation_discarded_pick_no: int | None = None
    recommendation_progress: dict | None = None
    previous_finalists: tuple = ()
    league_equity: dict | None = None
    league_equity_status: str = "idle"
    league_equity_progress: dict | None = None
    league_equity_pick_no: int | None = None
    league_equity_error: str | None = None
    alpha_shadow: dict | None = None
    alpha_shadow_status: str = "disabled"
    alpha_shadow_pick_no: int | None = None
    alpha_shadow_error: str | None = None
    alpha_shadow_duration_seconds: float | None = None
    alpha_shadow_calculation_count: int = 0
    error: str | None = None
    sync_count: int = 0
    calculation_count: int = 0
    league_equity_calculation_count: int = 0
    last_sync_at: float | None = None
    lock: Lock = field(default_factory=Lock, repr=False)
    stopped: Event = field(default_factory=Event, repr=False)
    calculation_event: Event = field(default_factory=Event, repr=False)
    alpha_shadow_thread: Thread | None = field(default=None, repr=False)
    alpha_shadow_pending: tuple | None = field(default=None, repr=False)
    executor: object | None = field(default=None, repr=False)
    pending_state: object | None = field(default=None, repr=False)
    state_fingerprint: tuple | None = field(default=None, repr=False)
    speculative: dict | None = field(default=None, repr=False)
    speculation_attempted: bool = field(default=False, repr=False)

    def snapshot(self):
        with self.lock:
            return {
                "status": self.status,
                "session_id": self.session_id,
                "draft_id": self.prepared.live_draft_id,
                "poll_seconds": self.poll_seconds,
                "sync_count": self.sync_count,
                "calculation_count": self.calculation_count,
                "recommendation_mode": self.recommendation_mode,
                "last_sync_at": self.last_sync_at,
                "state": self.state,
                "projection_board": self.projection_board,
                "projection_board_error": self.projection_board_error,
                "recommendation": self.recommendation,
                "recommendation_status": self.recommendation_status,
                "recommendation_pick_no": self.recommendation_pick_no,
                "recommendation_error": self.recommendation_error,
                "recommendation_discarded_pick_no": self.recommendation_discarded_pick_no,
                "recommendation_progress": self.recommendation_progress,
                "league_equity": self.league_equity,
                "league_equity_status": self.league_equity_status,
                "league_equity_progress": self.league_equity_progress,
                "league_equity_pick_no": self.league_equity_pick_no,
                "league_equity_error": self.league_equity_error,
                "league_equity_calculation_count": self.league_equity_calculation_count,
                "alpha_shadow": self.alpha_shadow,
                "alpha_shadow_status": self.alpha_shadow_status,
                "alpha_shadow_pick_no": self.alpha_shadow_pick_no,
                "alpha_shadow_error": self.alpha_shadow_error,
                "alpha_shadow_duration_seconds": (
                    self.alpha_shadow_duration_seconds
                ),
                "alpha_shadow_calculation_count": (
                    self.alpha_shadow_calculation_count
                ),
                "error": self.error,
            }

    def _record(
        self,
        event_type,
        payload,
        *,
        pick_no=None,
        stage=None,
        duration_seconds=None,
    ):
        if self.telemetry is None:
            return
        try:
            self.telemetry.record(
                self.session_id,
                self.prepared.live_draft_id,
                event_type,
                payload,
                pick_no=pick_no,
                stage=stage,
                duration_seconds=duration_seconds,
            )
        except Exception as error:
            with self.lock:
                self.status = "failed"
                self.error = f"Telemetry failed: {error}"
            self.stopped.set()
            raise

    def _record_alpha_shadow(
        self,
        event_type,
        payload,
        *,
        pick_no,
        duration_seconds,
    ):
        if self.telemetry is None:
            return
        try:
            self.telemetry.record(
                self.session_id,
                self.prepared.live_draft_id,
                event_type,
                payload,
                pick_no=pick_no,
                stage="shadow",
                duration_seconds=duration_seconds,
            )
        except Exception:
            LOGGER.exception(
                "Alpha shadow telemetry failed for %s",
                self.prepared.live_draft_id,
            )

    def _queue_alpha_shadow(
        self,
        fingerprint,
        pick_no,
        state,
        recommendation,
    ):
        if self.alpha_shadow_collector is None:
            return
        worker = None
        with self.lock:
            if (
                self.state_fingerprint != fingerprint
                or self.stopped.is_set()
                or (
                    self.alpha_shadow_pick_no == pick_no
                    and self.alpha_shadow_status in {"pending", "ready"}
                )
            ):
                return
            self.alpha_shadow = None
            self.alpha_shadow_status = "pending"
            self.alpha_shadow_pick_no = pick_no
            self.alpha_shadow_error = None
            self.alpha_shadow_duration_seconds = None
            self.alpha_shadow_pending = (
                fingerprint,
                pick_no,
                state,
                recommendation,
            )
            if (
                self.alpha_shadow_thread is None
                or not self.alpha_shadow_thread.is_alive()
            ):
                worker = Thread(
                    target=self._drain_alpha_shadow,
                    daemon=True,
                )
                self.alpha_shadow_thread = worker
        if worker is not None:
            worker.start()

    def _drain_alpha_shadow(self):
        while True:
            with self.lock:
                pending = self.alpha_shadow_pending
                self.alpha_shadow_pending = None
                if pending is None:
                    self.alpha_shadow_thread = None
                    return
            self._collect_alpha_shadow(*pending)

    def _collect_alpha_shadow(
        self,
        fingerprint,
        pick_no,
        state,
        recommendation,
    ):
        started_at = time.monotonic()
        try:
            payload = self.alpha_shadow_collector.collect(
                self.prepared,
                state,
                recommendation,
            )
        except Exception as error:
            duration = time.monotonic() - started_at
            LOGGER.exception(
                "Alpha shadow calculation failed for %s",
                self.prepared.live_draft_id,
            )
            with self.lock:
                current = (
                    self.state_fingerprint == fingerprint
                    and not self.stopped.is_set()
                )
                if current:
                    self.alpha_shadow = None
                    self.alpha_shadow_status = "failed"
                    self.alpha_shadow_error = str(error)
                    self.alpha_shadow_duration_seconds = duration
            self._record_alpha_shadow(
                "alpha_shadow_error" if current else "alpha_shadow_discarded",
                {"error": str(error)},
                pick_no=pick_no,
                duration_seconds=duration,
            )
            return
        duration = time.monotonic() - started_at
        payload = {**payload, "duration_seconds": duration}
        with self.lock:
            current = (
                self.state_fingerprint == fingerprint
                and not self.stopped.is_set()
            )
            if current:
                self.alpha_shadow = payload
                self.alpha_shadow_status = "ready"
                self.alpha_shadow_error = None
                self.alpha_shadow_duration_seconds = duration
                self.alpha_shadow_calculation_count += 1
        self._record_alpha_shadow(
            "alpha_shadow" if current else "alpha_shadow_discarded",
            payload,
            pick_no=pick_no,
            duration_seconds=duration,
        )

    def _sticky_finalists(self):
        """Previous pick's finalists, carried into the next candidate window."""
        with self.lock:
            return self.previous_finalists

    def _record_recommendation_stage(
        self,
        recommendation,
        pick_no,
        phase,
        calculation_started,
        stage_started,
        *,
        evaluated_candidate_ids,
        refined_candidate_ids=(),
        survivor_candidate_ids=(),
        stop_reason=None,
        stage_candidate_rollout_work=0,
        cumulative_candidate_rollout_work=0,
        speculation_attempted=False,
        speculation_hit=False,
        speculation_miss=False,
    ):
        recorded_at = time.monotonic()
        cumulative_duration = recorded_at - calculation_started
        self._record(
            "recommendation_stage",
            _recommendation_stage_payload(
                recommendation,
                phase=phase,
                cumulative_duration_seconds=cumulative_duration,
                stage_duration_seconds=recorded_at - stage_started,
                evaluated_candidate_ids=evaluated_candidate_ids,
                refined_candidate_ids=refined_candidate_ids,
                survivor_candidate_ids=survivor_candidate_ids,
                stop_reason=stop_reason,
                stage_candidate_rollout_work=stage_candidate_rollout_work,
                cumulative_candidate_rollout_work=(
                    cumulative_candidate_rollout_work
                ),
                speculation_attempted=speculation_attempted,
                speculation_hit=speculation_hit,
                speculation_miss=speculation_miss,
            ),
            pick_no=pick_no,
            stage=phase,
            duration_seconds=cumulative_duration,
        )
        return recorded_at

    def _publish_recommendation(
        self,
        fingerprint,
        pick_no,
        recommendation,
        status,
        started_at,
        *,
        final=False,
        progress=None,
        record_full=True,
    ):
        with self.lock:
            if self.state_fingerprint != fingerprint or self.stopped.is_set():
                self.recommendation_discarded_pick_no = pick_no
                published = False
            else:
                self.recommendation = recommendation
                self.recommendation_status = status
                self.recommendation_pick_no = pick_no
                self.previous_finalists = tuple(
                    str(row["player_id"])
                    for row in recommendation.get("candidates", ())[:FINALIST_COUNT]
                )
                if progress is not None:
                    self.recommendation_progress = progress
                self.calculation_count += int(final)
                published = True
        duration = time.monotonic() - started_at
        if record_full:
            self._record(
                "recommendation" if published else "recommendation_discarded",
                recommendation,
                pick_no=pick_no,
                stage=status,
                duration_seconds=duration,
            )
        return published

    def calculate(
        self,
        candidate_pool,
        evaluate_candidates,
        recommendation_payload,
        evaluate_equity=None,
        equity_payload=None,
        select_finalists=None,
        merge_refinement=None,
        predict_next_state=None,
    ):
        while not self.stopped.is_set():
            self.calculation_event.wait()
            self.calculation_event.clear()
            if self.stopped.is_set():
                return
            with self.lock:
                state = self.pending_state
                self.pending_state = None
                if state is None:
                    continue
                fingerprint = _state_fingerprint(state)
                pick_no = state.current_pick_no
                on_clock = state.current_roster_id == self.prepared.user_roster_id
                self.recommendation_status = "calculating" if on_clock else "idle"
                self.recommendation_discarded_pick_no = None
                self.recommendation_progress = None
                if (
                    self.alpha_shadow_pick_no is not None
                    and self.alpha_shadow_pick_no != pick_no
                    and self.alpha_shadow_status in {"pending", "ready"}
                ):
                    self.alpha_shadow_status = "stale"
                if evaluate_equity is not None and equity_payload is not None:
                    self.league_equity_status = "calculating"
                    self.league_equity_progress = None
            calculation_started = time.monotonic()
            recommendation_stage_started = calculation_started

            def update_equity(rollout_count, final):
                started_at = time.monotonic()
                try:
                    evaluation = evaluate_equity(
                        self.prepared,
                        state,
                        rollout_count,
                        self.temperature,
                    )
                    payload = equity_payload(self.prepared, evaluation)
                except Exception as error:
                    LOGGER.exception(
                        "Live draft league equity failed for %s",
                        self.prepared.live_draft_id,
                    )
                    with self.lock:
                        current = self.state_fingerprint == fingerprint
                        if current:
                            self.league_equity_status = "failed"
                            self.league_equity_error = str(error)
                    if current:
                        self._record(
                            "league_equity_error",
                            {"error": str(error)},
                            pick_no=pick_no,
                            stage="final" if final else "preliminary",
                            duration_seconds=time.monotonic() - started_at,
                        )
                    return current
                with self.lock:
                    if self.state_fingerprint != fingerprint or self.stopped.is_set():
                        published = False
                    else:
                        self.league_equity = payload
                        self.league_equity_status = "ready" if final else "calculating"
                        self.league_equity_progress = {
                            "done": rollout_count,
                            "total": equity_rollout_count,
                        }
                        self.league_equity_error = None
                        self.league_equity_calculation_count += int(final)
                        published = True
                self._record(
                    "league_equity" if published else "league_equity_discarded",
                    payload,
                    pick_no=pick_no,
                    stage="final" if final else "preliminary",
                    duration_seconds=time.monotonic() - started_at,
                )
                return published

            equity_enabled = evaluate_equity is not None and equity_payload is not None
            equity_finalized = not equity_enabled
            equity_rollout_count = min(
                self.rollout_count, LEAGUE_EQUITY_ROLLOUT_COUNT
            )
            if equity_enabled:
                with self.lock:
                    if self.state_fingerprint == fingerprint:
                        self.league_equity_progress = {
                            "done": 0,
                            "total": equity_rollout_count,
                        }
                preliminary = min(equity_rollout_count, PRELIMINARY_ROLLOUT_COUNT)
                equity_finalized = preliminary == equity_rollout_count
                if not update_equity(preliminary, equity_finalized):
                    if on_clock:
                        with self.lock:
                            self.recommendation_discarded_pick_no = pick_no
                    continue

            candidates = ()
            if on_clock:
                try:
                    candidates = candidate_pool(
                        self.prepared,
                        state,
                        max(self.candidate_breadth, self.candidate_count),
                        sticky=self._sticky_finalists(),
                    )
                except Exception as error:
                    LOGGER.exception(
                        "Live draft candidate selection failed for %s",
                        self.prepared.live_draft_id,
                    )
                    with self.lock:
                        if self.state_fingerprint == fingerprint:
                            self.recommendation_status = "failed"
                            self.recommendation_error = str(error)
                    self._record(
                        "recommendation_error",
                        {"error": str(error)},
                        pick_no=pick_no,
                        stage="candidate_selection",
                        duration_seconds=time.monotonic() - calculation_started,
                    )
            # Screen broadly, then refine at least five candidates plus every
            # statistically tied screen leader.
            first = tuple(candidates[: self.candidate_count])
            remainder = tuple(candidates[len(first):])
            screen_evaluations = []
            recommendation = None
            screen_failed = False
            screen_count = min(self.rollout_count, SCREEN_ROLLOUT_COUNT)
            # Progress in candidate-rollout units: every candidate screened at
            # screen depth, then the finalists extended to the full depth.
            recommendation_total = len(candidates) * screen_count + max(
                self.rollout_count - screen_count, 0
            ) * min(FINALIST_COUNT, len(candidates))
            if on_clock and candidates:
                with self.lock:
                    if self.state_fingerprint == fingerprint:
                        self.recommendation_progress = {
                            "done": 0,
                            "total": recommendation_total,
                        }
            attempted, self.speculation_attempted = self.speculation_attempted, False
            speculative, self.speculative = self.speculative, None
            speculated = (
                tuple(speculative["evaluations"])
                if on_clock
                and speculative is not None
                and speculative["signature"] == _decision_state_signature(state)
                and speculative["candidates"] == tuple(candidates)
                else ()
            )
            attempted = on_clock and (attempted or speculative is not None)
            speculation = {
                "speculation_attempted": attempted,
                "speculation_hit": bool(speculated),
                "speculation_miss": attempted and not speculated,
            }
            screened_units = 0
            full_screen_stage_work = 0
            screened_candidate_ids = ()
            for batch_index, batch in enumerate(filter(None, (first, remainder))):
                with self.lock:
                    if self.state_fingerprint != fingerprint or self.stopped.is_set():
                        # ponytail: no hard thread cancel; obsolete work is
                        # abandoned between steps and stale results discarded.
                        self.recommendation_discarded_pick_no = pick_no
                        break
                try:
                    # A speculative screen computed while the previous
                    # opponent deliberated is reused only when the realized
                    # state matches the predicted one exactly.
                    evaluation = (
                        speculated[batch_index]
                        if batch_index < len(speculated)
                        else evaluate_candidates(
                            self.prepared,
                            state,
                            screen_count,
                            batch,
                            self.temperature,
                            self.executor,
                            candidates,
                        )
                    )
                    screen_evaluations.append(evaluation)
                    recommendation = recommendation_payload(
                        self.prepared,
                        state,
                        screen_evaluations,
                        len(candidates),
                    )
                except Exception as error:
                    LOGGER.exception(
                        "Live draft recommendation failed for %s",
                        self.prepared.live_draft_id,
                    )
                    with self.lock:
                        if self.state_fingerprint == fingerprint:
                            self.recommendation_status = "failed"
                            self.recommendation_error = str(error)
                        else:
                            self.recommendation_discarded_pick_no = pick_no
                    screen_failed = True
                    self._record(
                        "recommendation_error",
                        {"error": str(error)},
                        pick_no=pick_no,
                        stage="screen",
                        duration_seconds=time.monotonic() - calculation_started,
                    )
                    break
                batch_work = len(batch) * screen_count
                screened_units += batch_work
                screen_complete = batch_index == int(bool(remainder))
                refine = screen_complete and self.rollout_count > screen_count
                final = screen_complete and not refine
                status = "ready" if final else ("refining" if refine else "expanding")
                published = self._publish_recommendation(
                    fingerprint,
                    pick_no,
                    recommendation,
                    status,
                    calculation_started,
                    final=final,
                    progress={"done": screened_units, "total": recommendation_total},
                    record_full=screen_complete,
                )
                screened_candidate_ids = tuple(
                    str(row["player_id"])
                    for row in recommendation.get("candidates", ())
                )
                practical_ids = tuple(
                    str(candidate_id)
                    for candidate_id in recommendation.get(
                        "co_leader_candidate_ids", ()
                    )
                )
                if not published:
                    recommendation_stage_started = self._record_recommendation_stage(
                        recommendation,
                        pick_no,
                        "full_screen" if screen_complete else "first_board",
                        calculation_started,
                        recommendation_stage_started,
                        evaluated_candidate_ids=screened_candidate_ids,
                        survivor_candidate_ids=practical_ids,
                        stop_reason="state_advanced",
                        stage_candidate_rollout_work=batch_work,
                        cumulative_candidate_rollout_work=screened_units,
                        **speculation,
                    )
                    break
                if batch_index == 0:
                    recommendation_stage_started = self._record_recommendation_stage(
                        recommendation,
                        pick_no,
                        "first_board",
                        calculation_started,
                        recommendation_stage_started,
                        evaluated_candidate_ids=screened_candidate_ids,
                        survivor_candidate_ids=practical_ids,
                        stage_candidate_rollout_work=batch_work,
                        cumulative_candidate_rollout_work=screened_units,
                        **speculation,
                    )
                if screen_complete:
                    full_screen_stage_work = 0 if batch_index == 0 else batch_work
                    if final:
                        recommendation_stage_started = self._record_recommendation_stage(
                            recommendation,
                            pick_no,
                            "full_screen",
                            calculation_started,
                            recommendation_stage_started,
                            evaluated_candidate_ids=screened_candidate_ids,
                            survivor_candidate_ids=practical_ids,
                            stage_candidate_rollout_work=full_screen_stage_work,
                            cumulative_candidate_rollout_work=screened_units,
                            **speculation,
                        )
                        recommendation_stage_started = self._record_recommendation_stage(
                            recommendation,
                            pick_no,
                            "ready",
                            calculation_started,
                            recommendation_stage_started,
                            evaluated_candidate_ids=screened_candidate_ids,
                            survivor_candidate_ids=practical_ids,
                            stop_reason="max_budget",
                            cumulative_candidate_rollout_work=screened_units,
                            **speculation,
                        )

            if (
                recommendation is not None
                and not screen_failed
                and self.rollout_count > screen_count
            ):
                with self.lock:
                    current = (
                        self.state_fingerprint == fingerprint
                        and not self.stopped.is_set()
                    )
                if current:
                    try:
                        screened_candidates = recommendation["candidates"]
                        deepest_candidates = {
                            row["player_id"]: row for row in screened_candidates
                        }
                        finalists = (
                            tuple(select_finalists(
                                self.prepared,
                                state,
                                screened_candidates,
                                FINALIST_COUNT,
                            ))
                            if select_finalists is not None
                            else tuple(
                                row["player_id"]
                                for row in screened_candidates[:FINALIST_COUNT]
                            )
                        )
                        recommendation_total = screened_units + len(finalists) * max(
                            self.rollout_count - screen_count, 0
                        )
                        with self.lock:
                            if self.state_fingerprint == fingerprint:
                                self.recommendation_progress = {
                                    "done": screened_units,
                                    "total": recommendation_total,
                                }
                        recommendation_stage_started = self._record_recommendation_stage(
                            recommendation,
                            pick_no,
                            "full_screen",
                            calculation_started,
                            recommendation_stage_started,
                            evaluated_candidate_ids=screened_candidate_ids,
                            survivor_candidate_ids=finalists,
                            stage_candidate_rollout_work=full_screen_stage_work,
                            cumulative_candidate_rollout_work=screened_units,
                            **speculation,
                        )
                        if merge_refinement is not None:
                            # The screen already evaluated rollout IDs
                            # 0..screen_count-1 for every finalist; extend in
                            # fixed stages. Every finalist reaches the full
                            # budget because an intermediate stochastic
                            # interval can reverse at a later stage.
                            refined_ids = finalists
                            previous_evaluations = screen_evaluations
                            previous_count = screen_count
                            evaluation = None
                            candidate_rollout_work = screened_units
                            final_stop_reason = "max_budget"
                            state_advanced = False
                            ready_stage_work = 0
                            for stage in dict.fromkeys((
                                *(
                                    count
                                    for count in REFINEMENT_STAGE_ROLLOUT_COUNTS
                                    if screen_count < count < self.rollout_count
                                ),
                                self.rollout_count,
                            )):
                                with self.lock:
                                    if (
                                        self.state_fingerprint != fingerprint
                                        or self.stopped.is_set()
                                    ):
                                        self.recommendation_discarded_pick_no = pick_no
                                        phase = (
                                            "ready"
                                            if stage == self.rollout_count
                                            else f"refinement_{stage}"
                                        )
                                        recommendation_stage_started = (
                                            self._record_recommendation_stage(
                                                recommendation,
                                                pick_no,
                                                phase,
                                                calculation_started,
                                                recommendation_stage_started,
                                                evaluated_candidate_ids=(
                                                    screened_candidate_ids
                                                ),
                                                survivor_candidate_ids=finalists,
                                                stop_reason="state_advanced",
                                                cumulative_candidate_rollout_work=(
                                                    candidate_rollout_work
                                                ),
                                                **speculation,
                                            )
                                        )
                                        state_advanced = True
                                        break
                                extension = evaluate_candidates(
                                    self.prepared,
                                    state,
                                    range(previous_count, stage),
                                    finalists,
                                    self.temperature,
                                    self.executor,
                                    finalists,
                                )
                                stage_work = len(finalists) * (stage - previous_count)
                                candidate_rollout_work += stage_work
                                evaluation = merge_refinement(
                                    previous_evaluations, extension
                                )
                                previous_evaluations = [evaluation]
                                previous_count = stage
                                if stage < self.rollout_count:
                                    # Publish each intermediate stage so the
                                    # user sees the partially refined tier
                                    # while deeper stages run.
                                    interim = recommendation_payload(
                                        self.prepared,
                                        state,
                                        [evaluation],
                                        len(candidates),
                                    )
                                    deepest_candidates.update(
                                        (row["player_id"], row)
                                        for row in interim["candidates"]
                                    )
                                    interim_ids = set(refined_ids)
                                    interim["screened_candidates"] = [
                                        _watchlist_candidate(
                                            deepest_candidates[row["player_id"]]
                                        )
                                        for row in screened_candidates
                                        if row["player_id"] not in interim_ids
                                    ]
                                    interim["screened_rollout_count"] = screen_count
                                    interim["candidates_evaluated"] = len(
                                        screened_candidates
                                    )
                                    published = self._publish_recommendation(
                                        fingerprint,
                                        pick_no,
                                        interim,
                                        "refining",
                                        calculation_started,
                                        progress={
                                            "done": candidate_rollout_work,
                                            "total": recommendation_total,
                                        },
                                        record_full=False,
                                    )
                                    recommendation_stage_started = (
                                        self._record_recommendation_stage(
                                            interim,
                                            pick_no,
                                            f"refinement_{stage}",
                                            calculation_started,
                                            recommendation_stage_started,
                                            evaluated_candidate_ids=(
                                                screened_candidate_ids
                                            ),
                                            refined_candidate_ids=refined_ids,
                                            survivor_candidate_ids=finalists,
                                            stop_reason=(
                                                None if published else "state_advanced"
                                            ),
                                            stage_candidate_rollout_work=stage_work,
                                            cumulative_candidate_rollout_work=(
                                                candidate_rollout_work
                                            ),
                                            **speculation,
                                        )
                                    )
                                    if not published:
                                        state_advanced = True
                                        break
                                if stage == self.rollout_count:
                                    ready_stage_work = stage_work
                            if state_advanced:
                                continue
                        else:
                            evaluation = evaluate_candidates(
                                self.prepared,
                                state,
                                self.rollout_count,
                                finalists,
                                self.temperature,
                                self.executor,
                                finalists,
                            )
                            refined_ids = finalists
                            candidate_rollout_work = (
                                screened_units + len(finalists) * self.rollout_count
                            )
                            ready_stage_work = len(finalists) * self.rollout_count
                            final_stop_reason = "max_budget"
                        recommendation = recommendation_payload(
                            self.prepared, state, [evaluation], len(candidates)
                        )
                        deepest_candidates.update(
                            (row["player_id"], row)
                            for row in recommendation["candidates"]
                        )
                        finalist_ids = set(
                            refined_ids if merge_refinement is not None else finalists
                        )
                        recommendation["screened_candidates"] = [
                            _watchlist_candidate(
                                deepest_candidates[row["player_id"]]
                            )
                            for row in screened_candidates
                            if row["player_id"] not in finalist_ids
                        ]
                        recommendation["screened_rollout_count"] = screen_count
                        recommendation["candidates_evaluated"] = len(screened_candidates)
                    except Exception as error:
                        LOGGER.exception(
                            "Live draft recommendation failed for %s",
                            self.prepared.live_draft_id,
                        )
                        with self.lock:
                            if self.state_fingerprint == fingerprint:
                                self.recommendation_status = "failed"
                                self.recommendation_error = str(error)
                            else:
                                self.recommendation_discarded_pick_no = pick_no
                        self._record(
                            "recommendation_error",
                            {"error": str(error)},
                            pick_no=pick_no,
                            stage="refinement",
                            duration_seconds=time.monotonic() - calculation_started,
                        )
                    else:
                        published = self._publish_recommendation(
                            fingerprint,
                            pick_no,
                            recommendation,
                            "ready",
                            calculation_started,
                            final=True,
                            progress={
                                "done": recommendation_total,
                                "total": recommendation_total,
                            },
                        )
                        self._record_recommendation_stage(
                            recommendation,
                            pick_no,
                            "ready",
                            calculation_started,
                            recommendation_stage_started,
                            evaluated_candidate_ids=screened_candidate_ids,
                            refined_candidate_ids=refined_ids,
                            survivor_candidate_ids=finalists,
                            stop_reason=(
                                final_stop_reason
                                if published
                                else "state_advanced"
                            ),
                            stage_candidate_rollout_work=ready_stage_work,
                            cumulative_candidate_rollout_work=(
                                candidate_rollout_work
                            ),
                            **speculation,
                        )
                else:
                    with self.lock:
                        self.recommendation_discarded_pick_no = pick_no
                    self._record_recommendation_stage(
                        recommendation,
                        pick_no,
                        "full_screen",
                        calculation_started,
                        recommendation_stage_started,
                        evaluated_candidate_ids=screened_candidate_ids,
                        survivor_candidate_ids=practical_ids,
                        stop_reason="state_advanced",
                        stage_candidate_rollout_work=full_screen_stage_work,
                        cumulative_candidate_rollout_work=screened_units,
                        **speculation,
                    )
            if on_clock and recommendation is not None:
                with self.lock:
                    shadow_ready = (
                        self.state_fingerprint == fingerprint
                        and not self.stopped.is_set()
                        and self.recommendation_status == "ready"
                        and self.recommendation_pick_no == pick_no
                    )
                if shadow_ready:
                    self._queue_alpha_shadow(
                        fingerprint,
                        pick_no,
                        state,
                        recommendation,
                    )

            if not equity_finalized:
                with self.lock:
                    current = self.state_fingerprint == fingerprint and not self.stopped.is_set()
                if current:
                    update_equity(equity_rollout_count, True)

            # Real rooms leave long opponent deliberations before the user's
            # clock starts; spend that idle time screening the most likely
            # next state instead of waiting.
            if (
                not on_clock
                and predict_next_state is not None
                and state.status == "drafting"
                and state.current_pick_no is not None
            ):
                turn = state.turn_for(self.prepared.user_roster_id)
                if turn.user_next_pick_no == state.current_pick_no + 1:
                    self._speculate(
                        state,
                        fingerprint,
                        candidate_pool,
                        evaluate_candidates,
                        predict_next_state,
                    )

    def _speculate(
        self,
        state,
        fingerprint,
        candidate_pool,
        evaluate_candidates,
        predict_next_state,
    ):
        self.speculation_attempted = True
        try:
            hypothetical = predict_next_state(self.prepared, state, self.temperature)
        except Exception:
            LOGGER.exception(
                "Speculative pick prediction failed for %s",
                self.prepared.live_draft_id,
            )
            return
        if (
            hypothetical is None
            or hypothetical.current_roster_id != self.prepared.user_roster_id
        ):
            return
        try:
            candidates = tuple(candidate_pool(
                self.prepared,
                hypothetical,
                max(self.candidate_breadth, self.candidate_count),
                sticky=self._sticky_finalists(),
            ))
        except Exception:
            LOGGER.exception(
                "Speculative candidate selection failed for %s",
                self.prepared.live_draft_id,
            )
            return
        first = tuple(candidates[: self.candidate_count])
        remainder = tuple(candidates[len(first):])
        screen_count = min(self.rollout_count, SCREEN_ROLLOUT_COUNT)
        evaluations = []
        signature = None
        for batch in filter(None, (first, remainder)):
            with self.lock:
                if (
                    self.state_fingerprint != fingerprint
                    or self.stopped.is_set()
                    or self.pending_state is not None
                ):
                    break
            try:
                evaluation = evaluate_candidates(
                    self.prepared,
                    hypothetical,
                    screen_count,
                    batch,
                    self.temperature,
                    self.executor,
                    candidates,
                )
            except Exception:
                LOGGER.exception(
                    "Speculative screen failed for %s",
                    self.prepared.live_draft_id,
                )
                return
            evaluations.append(evaluation)
            signature = evaluation.state_signature
        if evaluations:
            # Partial screens still save the completed batches on a hit.
            self.speculative = {
                "signature": signature,
                "candidates": candidates,
                "evaluations": evaluations,
            }

    def run(self):
        from ffsim.draft_intel.live import (
            create_live_executor,
            evaluate_live_candidates,
            evaluate_live_league_equity,
            live_candidate_pool,
            live_league_equity_payload,
            live_recommendation_payload,
            live_state_summary,
            merge_screen_refinement,
            predicted_next_state,
            projection_value_board,
            select_finalists,
            sync_prepared_draft,
        )

        inputs_available = getattr(self.prepared, "evaluator", None) is not None
        simulation_enabled = self.recommendation_mode == "simulation"
        telemetry_started = False
        try:
            if simulation_enabled and inputs_available:
                self.executor = create_live_executor(self.prepared)
        except Exception:
            LOGGER.exception("Falling back to sequential candidate evaluation")
            self.executor = None
        if self.telemetry is not None:
            try:
                self.telemetry.start_session(
                    self.session_id,
                    self.prepared.live_draft_id,
                    {
                        "prepared": self.prepared.summary,
                        "monitor": {
                            "poll_seconds": self.poll_seconds,
                            "rollout_count": self.rollout_count,
                            "recommendation_mode": self.recommendation_mode,
                            "candidate_breadth": self.candidate_breadth,
                            "temperature": self.temperature,
                        },
                    },
                )
                telemetry_started = True
            except Exception as error:
                LOGGER.exception("Draft telemetry failed to start")
                with self.lock:
                    self.status = "failed"
                    self.error = str(error)
                self.stopped.set()
                if self.executor is not None:
                    self.executor.shutdown(wait=False, cancel_futures=True)
                return
        if simulation_enabled:
            Thread(
                target=self.calculate,
                args=(
                    live_candidate_pool,
                    evaluate_live_candidates,
                    live_recommendation_payload,
                    evaluate_live_league_equity if inputs_available else None,
                    live_league_equity_payload if inputs_available else None,
                    select_finalists if inputs_available else None,
                    merge_screen_refinement,
                    predicted_next_state if inputs_available else None,
                ),
                daemon=True,
            ).start()
        try:
            with self.lock:
                self.status = "running"
            refresh_metadata = True
            while not self.stopped.is_set():
                try:
                    # One picks request per poll; draft metadata and traded
                    # picks refresh every 15th poll (~15s at the 1s default),
                    # far below Sleeper's documented 1000 calls/minute, plus
                    # on the first poll and after any failure so a mid-draft
                    # trade or transient bad payload heals on the next poll.
                    sync = sync_prepared_draft(
                        self.prepared,
                        refresh_metadata=refresh_metadata
                        or self.sync_count % 15 == 0,
                    )
                except (OSError, ValueError, KeyError) as error:
                    refresh_metadata = True
                    with self.lock:
                        self.error = str(error)
                    self._record("sync_error", {"error": str(error)})
                    self.stopped.wait(self.poll_seconds)
                    continue
                refresh_metadata = False
                state = sync.state
                current = _state_fingerprint(state)
                state_summary = live_state_summary(self.prepared, state)
                changed = False
                with self.lock:
                    previous_pick_count = (
                        self.state.get("completed_picks", len(state.completed_picks))
                        if self.state is not None
                        else len(state.completed_picks)
                    )
                    self.state = state_summary
                    self.sync_count += 1
                    self.last_sync_at = time.time()
                    self.error = None
                    if current != self.state_fingerprint:
                        changed = True
                        self.state_fingerprint = current
                        self.recommendation = None
                        self.recommendation_status = "idle"
                        self.recommendation_pick_no = None
                        self.recommendation_error = None
                        self.recommendation_discarded_pick_no = None
                        # Keep the last projection board visible while the
                        # replacement computes (~10 ms later this iteration);
                        # the UI shows a stale-pick chip instead of a blank.
                        self.pending_state = state if simulation_enabled else None
                        self.league_equity_status = (
                            "pending"
                            if simulation_enabled and inputs_available
                            else "failed"
                            if simulation_enabled
                            else "idle"
                        )
                        self.league_equity_pick_no = state.current_pick_no
                        self.league_equity_error = None
                        if (
                            simulation_enabled
                            and state.current_roster_id == self.prepared.user_roster_id
                        ):
                            self.recommendation_status = "pending"
                            self.recommendation_pick_no = state.current_pick_no
                        if simulation_enabled:
                            self.calculation_event.set()
                    # A full pick sheet ends the draft even while the cached
                    # metadata payload still reports a stale "drafting" status.
                    complete = state.status == "complete" or state.current_pick_no is None
                if changed:
                    for pick in state_summary.get("recent_picks", ())[previous_pick_count:]:
                        self._record(
                            "pick",
                            pick,
                            pick_no=pick["pick_no"],
                            stage=(
                                "user"
                                if pick["roster_id"] == self.prepared.user_roster_id
                                else "opponent"
                            ),
                        )
                    self._record(
                        "draft_state",
                        state_summary,
                        pick_no=state.current_pick_no,
                        stage=(
                            "on_clock"
                            if state.current_roster_id == self.prepared.user_roster_id
                            else "watching"
                        ),
                    )
                    if inputs_available:
                        try:
                            board = projection_value_board(
                                self.prepared,
                                state,
                                self.temperature,
                            )
                            board_error = None
                        except Exception as error:
                            LOGGER.exception(
                                "Live projection board failed for %s",
                                self.prepared.live_draft_id,
                            )
                            board = None
                            board_error = str(error)
                        with self.lock:
                            if self.state_fingerprint == current:
                                self.projection_board = board
                                self.projection_board_error = board_error
                if complete:
                    if not simulation_enabled:
                        with self.lock:
                            self.status = "completed"
                        return
                    while not self.stopped.is_set():
                        with self.lock:
                            if self.league_equity_status in {"ready", "failed"}:
                                self.status = "completed"
                                return
                        time.sleep(0.01)
                self.stopped.wait(self.poll_seconds)
            with self.lock:
                if self.status not in TERMINAL_STATUSES:
                    self.status = "stopped"
        except Exception as error:
            LOGGER.exception("Live draft monitor failed for %s", self.prepared.live_draft_id)
            with self.lock:
                self.status = "failed"
                self.error = str(error)
        finally:
            self.stopped.set()
            self.calculation_event.set()
            if self.executor is not None:
                self.executor.shutdown(wait=False, cancel_futures=True)
            if telemetry_started:
                try:
                    self.telemetry.finish_session(self.session_id, self.status)
                except Exception as error:
                    LOGGER.exception("Draft telemetry failed to finish")
                    with self.lock:
                        self.status = "failed"
                        self.error = f"Telemetry failed: {error}"

    def stop(self):
        self.stopped.set()
        self.calculation_event.set()


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
        projection = player_loader.refresh_if_stale(season=season)
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
            "projection": projection,
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
            preparation = state.draft_preparation
            preparation["stage"] = stage
            preparation["stage_no"] = (preparation.get("stage_no") or 0) + 1
            preparation["stage_count"] = PREPARATION_STAGE_COUNT

    try:
        prepared = prepare_draft(
            config_path,
            request.draft_id,
            request.username,
            mock_draft_id=request.mock_draft_id,
            season=request.season,
            world_count=request.world_count,
            progress=progress,
            force_refresh=request.force_refresh,
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
def create_app(config_path="config.json", telemetry_path=None):
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
    app.state.draft_telemetry = DraftTelemetry(telemetry_path)

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
        recent_trades = []
        if league_id:
            cache = CACHE_DIR / f"league_{league_id}.json"
            if cache.exists():
                snapshot = json.loads(cache.read_text())
                league = snapshot.get("league", {})
                name = league.get("name")
                players_path = CACHE_DIR / "sleeper_players.json"
                players = (
                    json.loads(players_path.read_text())
                    if players_path.exists()
                    else {}
                )
                from ffsim.loaders.league import recent_trade_summaries

                recent_trades = recent_trade_summaries(snapshot, players)
                from ffsim.draft_intel.market_model import resolve_league_market_context

                market_context = resolve_league_market_context(league)
                if draft_id and (snapshot.get("draft_summary") or {}).get("draft_id") == draft_id:
                    draft = snapshot["draft_summary"]
        return {
            "league_id": league_id,
            "draft_id": draft_id,
            "name": name,
            "draft": draft,
            "recent_trades": recent_trades,
            "market_context": market_context,
            "ready": name is not None and (draft_id is None or draft is not None),
            "refresh": dict(app.state.refresh),
        }

    @app.get("/api/personal-ranks")
    def personal_ranks_board():
        from ffsim.draft_intel.live import _live_market_snapshot, _player_details
        from ffsim.draft_intel.market_model import load_league_market_snapshot
        from ffsim.draft_intel.personal_ranks import ALLOWED_OFFSETS, load_offsets

        try:
            league_id = AppConfig.from_file(app.state.config_path).league_id
        except ValueError:
            league_id = None
        if not league_id:
            raise HTTPException(
                status_code=409,
                detail="Select a league before setting personal ranks",
            )
        cache = CACHE_DIR / f"league_{league_id}.json"
        if not cache.exists():
            raise HTTPException(
                status_code=409,
                detail="League cache is missing; select the league again",
            )
        league = json.loads(cache.read_text()).get("league") or {}
        season = int(league.get("season") or 2026)
        market = load_league_market_snapshot(league, season=season, max_age=None)
        snapshot = _live_market_snapshot(market["snapshot"])
        if snapshot is None or not snapshot.get("observations"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "No cached ADP board for this league yet; "
                    "refresh the league or prepare a draft once"
                ),
            )
        players_path = CACHE_DIR / "sleeper_players.json"
        details = _player_details(players_path) if players_path.exists() else {}
        offsets = load_offsets()
        adp_by_player = {}
        for observation in snapshot["observations"]:
            player_id = str(observation.get("canonical_player_id") or "")
            try:
                adp = float(observation.get("adp"))
            except (TypeError, ValueError):
                continue
            if player_id and adp > 0:
                adp_by_player[player_id] = adp
        players = [
            {
                "player_id": player_id,
                "name": details.get(player_id, {}).get("name", player_id),
                "position": details.get(player_id, {}).get("position"),
                "team": details.get(player_id, {}).get("team"),
                "adp": adp_by_player.get(player_id),
                "offset": offsets.get(player_id, 0),
            }
            for player_id in adp_by_player.keys() | offsets.keys()
        ]
        players.sort(
            key=lambda row: (
                row["adp"] is None,
                row["adp"] if row["adp"] is not None else 0.0,
                row["player_id"],
            )
        )
        return {
            "allowed_offsets": list(ALLOWED_OFFSETS),
            "count": len(offsets),
            "players": players,
        }

    @app.post("/api/personal-ranks")
    def set_personal_rank(request: PersonalRankRequest):
        from ffsim.draft_intel.personal_ranks import offsets_hash, save_offset

        try:
            offsets = save_offset(request.player_id, request.offset)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        # An idle prepared draft swaps to the new board atomically. A running
        # monitor keeps its immutable snapshot — hot-swapping mid-cycle could
        # mix boards inside one payload — so edits made during monitoring
        # apply at the next prepare.
        applied = "next_prepare"
        monitor = app.state.live_monitor
        monitor_active = monitor is not None and monitor.snapshot()["status"] in {
            "starting", "running"
        }
        if not monitor_active:
            with app.state.prepare_lock:
                prepared = app.state.prepared_draft
                if prepared is not None:
                    app.state.prepared_draft = replace(
                        prepared,
                        summary={
                            **prepared.summary,
                            "personal_ranks": {
                                "players": len(offsets),
                                "hash": offsets_hash(offsets),
                            },
                        },
                        personal_ranks=offsets,
                    )
                    applied = "live"
        return {
            "player_id": request.player_id.strip(),
            "offset": offsets.get(request.player_id.strip(), 0),
            "count": len(offsets),
            "applied": applied,
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
                "stage_no": 0,
                "stage_count": PREPARATION_STAGE_COUNT,
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
        from ffsim.draft_intel.alpha_shadow import (
            load_default_alpha_shadow_collector,
        )

        alpha_collector, alpha_error = load_default_alpha_shadow_collector()
        monitor = LiveDraftMonitor(
            prepared,
            request.poll_seconds,
            request.rollout_count,
            request.candidate_count,
            request.candidate_breadth,
            request.temperature,
            request.recommendation_mode,
            app.state.draft_telemetry,
            alpha_shadow_collector=alpha_collector,
            alpha_shadow_status=(
                "idle" if alpha_collector is not None else "disabled"
            ),
            alpha_shadow_error=alpha_error,
        )
        app.state.live_monitor = monitor
        Thread(target=monitor.run, daemon=True).start()
        return monitor.snapshot()

    @app.get("/api/draft-intel/monitor")
    def draft_monitor_status():
        monitor = app.state.live_monitor
        return monitor.snapshot() if monitor else {"status": "idle"}

    @app.get("/api/draft-intel/alpha-shadow")
    def draft_alpha_shadow():
        monitor = app.state.live_monitor
        if monitor is None:
            return {
                "status": "disabled",
                "pick_no": None,
                "evidence": None,
                "error": None,
                "duration_seconds": None,
            }
        snapshot = monitor.snapshot()
        return {
            "status": snapshot["alpha_shadow_status"],
            "pick_no": snapshot["alpha_shadow_pick_no"],
            "evidence": snapshot["alpha_shadow"],
            "error": snapshot["alpha_shadow_error"],
            "duration_seconds": snapshot[
                "alpha_shadow_duration_seconds"
            ],
            "calculation_count": snapshot[
                "alpha_shadow_calculation_count"
            ],
        }

    @app.get("/api/draft-intel/alpha-shadow/audit")
    def draft_alpha_shadow_audit(
        draft_id: str | None = None,
        session_id: str | None = None,
    ):
        from ffsim.draft_intel.alpha_audit import (
            build_alpha_shadow_audit,
        )

        try:
            return build_alpha_shadow_audit(
                app.state.draft_telemetry.path,
                draft_id=draft_id,
                session_id=session_id,
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/draft-intel/managers")
    def draft_manager_profiles():
        from ffsim.draft_intel.profiles import (
            MANAGER_PROFILE_MODEL_STATUS,
            load_pick_observations,
            load_target_context,
            summarize_manager_profiles,
        )

        config = AppConfig.from_file(app.state.config_path)
        if not config.league_id or not config.draft_id:
            raise HTTPException(
                status_code=409, detail="Attach a league and draft first"
            )
        cache_key = (config.league_id, config.draft_id)
        cached = getattr(app.state, "manager_profiles", None)
        if cached and cached.get("key") == cache_key:
            return cached["payload"]
        snapshot_path = Path(CACHE_DIR) / f"league_{config.league_id}.json"
        try:
            snapshot = json.loads(snapshot_path.read_text())
            season = int((snapshot.get("draft") or {}).get("season") or 0)
            observations = load_pick_observations()
            target_context = load_target_context(app.state.config_path, season)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        profiles = summarize_manager_profiles(
            observations,
            target_season=target_context["season"],
            target_scoring_type=target_context["scoring_type"],
            target_team_count=target_context["team_count"],
        )
        users = {
            str(user.get("user_id")): user
            for user in snapshot.get("users") or []
        }
        draft_order = (snapshot.get("draft") or {}).get("draft_order") or {}
        managers = []
        for roster in snapshot.get("rosters") or []:
            owner_id = (
                str(roster["owner_id"])
                if roster.get("owner_id") is not None
                else None
            )
            user = users.get(owner_id, {})
            profile = profiles.get(owner_id)
            managers.append({
                "user_id": owner_id,
                "roster_id": roster.get("roster_id"),
                "display_name": (
                    user.get("display_name")
                    or (profile or {}).get("display_name")
                    or f"Roster {roster.get('roster_id')}"
                ),
                "team_name": (user.get("metadata") or {}).get("team_name"),
                "draft_slot": draft_order.get(owner_id),
                "history": {
                    "draft_count": profile["draft_count"],
                    "pick_count": profile["pick_count"],
                    "weighted_draft_count": profile["context"][
                        "weighted_draft_count"
                    ],
                    "qb_te_timing": profile["qb_te_timing"],
                    "four_round_starts": profile["four_round_starts"],
                    "position_picks": profile["position_picks"],
                }
                if profile
                else None,
            })
        managers.sort(
            key=lambda row: (row["draft_slot"] is None, row["draft_slot"] or 0)
        )
        payload = {
            "model_status": MANAGER_PROFILE_MODEL_STATUS,
            "target_context": target_context,
            "observation_count": len(observations),
            "managers": managers,
        }
        app.state.manager_profiles = {"key": cache_key, "payload": payload}
        return payload

    @app.get("/api/draft-intel/telemetry")
    def draft_telemetry(
        draft_id: str | None = None,
        session_id: str | None = None,
        event_type: str | None = None,
        pick_no: int | None = None,
        limit: int = 1_000,
    ):
        try:
            return app.state.draft_telemetry.query(
                draft_id=draft_id,
                session_id=session_id,
                event_type=event_type,
                pick_no=pick_no,
                limit=limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/draft-intel/monitor/stop")
    def stop_draft_monitor():
        monitor = app.state.live_monitor
        if monitor is None:
            return {"status": "idle"}
        monitor.stop()
        return monitor.snapshot()

    @app.post("/api/draft-intel/simulation")
    def simulate_completed_draft():
        from ffsim.draft_intel.live import (
            completed_league_simulation,
            sync_prepared_draft,
        )

        with app.state.prepare_lock:
            prepared = app.state.prepared_draft
            preparation = dict(app.state.draft_preparation)
        if prepared is None or preparation.get("status") != "ready":
            raise HTTPException(status_code=409, detail="Prepare the draft first")
        try:
            state = sync_prepared_draft(prepared, refresh_metadata=True).state
            result = completed_league_simulation(prepared, state)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        monitor = app.state.live_monitor
        if (
            monitor is not None
            and monitor.prepared.live_draft_id == prepared.live_draft_id
        ):
            monitor._record(
                "completed_draft_simulation",
                result,
                stage="final",
            )
        return result

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
