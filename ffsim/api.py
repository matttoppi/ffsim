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
# Racing refinement: extend finalists in stages, eliminating candidates whose
# paired interval falls below the leader, and stop early when no survivor's
# plausible advantage over the leader exceeds the regret bound. Validated by
# offline seed-stability simulation on cached picks 24/48/120 (see ledger).
# Stages recalibrated for the 300-continuation x 14-world allocation: the
# (150, 225, 300) ladder matched its flat refinement 12/12 at 0.54-0.72x the
# extension work on the m=14 observation matrices.
REFINEMENT_STAGE_ROLLOUT_COUNTS = (150, 225)
REFINEMENT_REGRET_STOP = 0.005
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
    world_count: int = Field(default=300, ge=2, le=500)

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
    telemetry: DraftTelemetry | None = field(default=None, repr=False)
    session_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "starting"
    state: dict | None = None
    recommendation: dict | None = None
    recommendation_status: str = "idle"
    recommendation_pick_no: int | None = None
    recommendation_error: str | None = None
    recommendation_discarded_pick_no: int | None = None
    recommendation_progress: dict | None = None
    league_equity: dict | None = None
    league_equity_status: str = "idle"
    league_equity_progress: dict | None = None
    league_equity_pick_no: int | None = None
    league_equity_error: str | None = None
    error: str | None = None
    sync_count: int = 0
    calculation_count: int = 0
    league_equity_calculation_count: int = 0
    last_sync_at: float | None = None
    lock: Lock = field(default_factory=Lock, repr=False)
    stopped: Event = field(default_factory=Event, repr=False)
    calculation_event: Event = field(default_factory=Event, repr=False)
    executor: object | None = field(default=None, repr=False)
    pending_state: object | None = field(default=None, repr=False)
    state_fingerprint: tuple | None = field(default=None, repr=False)
    speculative: dict | None = field(default=None, repr=False)

    def snapshot(self):
        with self.lock:
            return {
                "status": self.status,
                "session_id": self.session_id,
                "draft_id": self.prepared.live_draft_id,
                "poll_seconds": self.poll_seconds,
                "sync_count": self.sync_count,
                "calculation_count": self.calculation_count,
                "last_sync_at": self.last_sync_at,
                "state": self.state,
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
    ):
        with self.lock:
            if self.state_fingerprint != fingerprint or self.stopped.is_set():
                self.recommendation_discarded_pick_no = pick_no
                published = False
            else:
                self.recommendation = recommendation
                self.recommendation_status = status
                if progress is not None:
                    self.recommendation_progress = progress
                self.calculation_count += int(final)
                published = True
        duration = time.monotonic() - started_at
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
        refine_survivors=None,
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
                if evaluate_equity is not None and equity_payload is not None:
                    self.league_equity_status = "calculating"
                    self.league_equity_progress = None
            calculation_started = time.monotonic()

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
            # Early refinement stops simply jump the bar to complete.
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
            speculative, self.speculative = self.speculative, None
            speculated = (
                tuple(speculative["evaluations"])
                if on_clock
                and speculative is not None
                and speculative["signature"] == _decision_state_signature(state)
                and speculative["candidates"] == tuple(candidates)
                else ()
            )
            screened_units = 0
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
                screened_units += len(batch) * screen_count
                screen_complete = batch_index == int(bool(remainder))
                refine = screen_complete and self.rollout_count > screen_count
                final = screen_complete and not refine
                status = "ready" if final else ("refining" if refine else "expanding")
                if not self._publish_recommendation(
                    fingerprint,
                    pick_no,
                    recommendation,
                    status,
                    calculation_started,
                    final=final,
                    progress={"done": screened_units, "total": recommendation_total},
                ):
                    break

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
                        if merge_refinement is not None:
                            # The screen already evaluated rollout IDs
                            # 0..screen_count-1 for every finalist; extend in
                            # racing stages, dropping candidates whose paired
                            # interval falls below the leader and stopping
                            # early when the surviving tier is a statistically
                            # bounded toss-up (max plausible regret below
                            # REFINEMENT_REGRET_STOP).
                            survivors = finalists
                            refined_ids = finalists
                            previous_evaluations = screen_evaluations
                            previous_count = screen_count
                            evaluation = None
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
                                        break
                                extension = evaluate_candidates(
                                    self.prepared,
                                    state,
                                    range(previous_count, stage),
                                    survivors,
                                    self.temperature,
                                    self.executor,
                                    survivors,
                                )
                                evaluation = merge_refinement(
                                    previous_evaluations, extension
                                )
                                refined_ids = survivors
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
                                        deepest_candidates[row["player_id"]]
                                        for row in screened_candidates
                                        if row["player_id"] not in interim_ids
                                    ]
                                    interim["screened_rollout_count"] = screen_count
                                    interim["candidates_evaluated"] = len(
                                        screened_candidates
                                    )
                                    if not self._publish_recommendation(
                                        fingerprint,
                                        pick_no,
                                        interim,
                                        "refining",
                                        calculation_started,
                                        progress={
                                            "done": screened_units
                                            + (stage - screen_count)
                                            * min(FINALIST_COUNT, len(candidates)),
                                            "total": recommendation_total,
                                        },
                                    ):
                                        break
                                if (
                                    refine_survivors is not None
                                    and stage < self.rollout_count
                                ):
                                    survivors, max_advantage = refine_survivors(
                                        evaluation
                                    )
                                    if max_advantage < REFINEMENT_REGRET_STOP:
                                        break
                            if evaluation is None:
                                with self.lock:
                                    self.recommendation_discarded_pick_no = pick_no
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
                            deepest_candidates[row["player_id"]]
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
                        self._publish_recommendation(
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
                else:
                    with self.lock:
                        self.recommendation_discarded_pick_no = pick_no

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
            refinement_survivors,
            select_finalists,
            sync_prepared_draft,
        )

        equity_available = getattr(self.prepared, "evaluator", None) is not None
        telemetry_started = False
        try:
            if equity_available:
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
                            "candidate_count": self.candidate_count,
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
        Thread(
            target=self.calculate,
            args=(
                live_candidate_pool,
                evaluate_live_candidates,
                live_recommendation_payload,
                evaluate_live_league_equity if equity_available else None,
                live_league_equity_payload if equity_available else None,
                select_finalists if equity_available else None,
                merge_screen_refinement,
                predicted_next_state if equity_available else None,
                refinement_survivors,
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
                        self.pending_state = state
                        self.league_equity_status = "pending" if equity_available else "failed"
                        self.league_equity_pick_no = state.current_pick_no
                        self.league_equity_error = None
                        if state.current_roster_id == self.prepared.user_roster_id:
                            self.recommendation_status = "pending"
                            self.recommendation_pick_no = state.current_pick_no
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
                if complete:
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
        monitor = LiveDraftMonitor(
            prepared,
            request.poll_seconds,
            request.rollout_count,
            request.candidate_count,
            request.candidate_breadth,
            request.temperature,
            app.state.draft_telemetry,
        )
        app.state.live_monitor = monitor
        Thread(target=monitor.run, daemon=True).start()
        return monitor.snapshot()

    @app.get("/api/draft-intel/monitor")
    def draft_monitor_status():
        monitor = app.state.live_monitor
        return monitor.snapshot() if monitor else {"status": "idle"}

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
