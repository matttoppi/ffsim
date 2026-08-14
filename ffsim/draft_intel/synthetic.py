"""Offline synthetic drafts persisted through the live telemetry schema."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
import random
from threading import Thread
import time
import traceback
from uuid import uuid4

from ffsim.api import LiveDraftMonitor, _state_fingerprint
from ffsim.config import AppConfig
from ffsim.draft_intel.live import (
    LIVE_TEMPERATURE,
    PreparedDraft,
    _bank_market_snapshot,
    _live_market_snapshot,
    _live_opponent_choice,
    _player_details,
    _projection_user_policy,
    _roster_details,
    completed_league_simulation,
    create_live_executor,
    evaluate_live_candidates,
    live_candidate_pool,
    live_recommendation_payload,
    live_state_summary,
    merge_screen_refinement,
    refinement_survivors,
    select_finalists,
)
from ffsim.draft_intel.market_model import load_league_market_snapshot
from ffsim.draft_intel.rollout import complete_drafts
from ffsim.draft_intel.state import replay_sleeper_draft
from ffsim.draft_intel.telemetry import DraftTelemetry
from ffsim.loaders.players import PlayerLoader
from ffsim.models.league import League
from ffsim.paths import CACHE_DIR
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.simulation.world_bank import build_season_world_bank, draftable_players


ESTIMATED_TELEMETRY_KB_PER_DRAFT = 450
SYNTHETIC_ROLLOUT_COUNT = 300
SYNTHETIC_CANDIDATE_COUNT = 9
SYNTHETIC_CANDIDATE_BREADTH = 40


@dataclass(frozen=True)
class SyntheticTemplate:
    prepared: PreparedDraft
    state: object
    scenario: dict


class _RecommendationTrace:
    """Keep the full screen and final board; intermediate racing rows are redundant."""

    def __init__(self):
        self.screen = None

    def reset(self):
        self.screen = None

    def record(
        self,
        session_id,
        draft_id,
        event_type,
        payload,
        *,
        pick_no=None,
        stage=None,
        duration_seconds=None,
    ):
        del session_id, draft_id, pick_no
        if (
            event_type == "recommendation"
            and "screened_candidates" not in payload
            and payload.get("candidates_evaluated") == SYNTHETIC_CANDIDATE_BREADTH
        ):
            self.screen = (payload, stage, duration_seconds)


def estimated_telemetry_gb(draft_count):
    if draft_count < 1:
        raise ValueError("draft_count must be positive")
    return ESTIMATED_TELEMETRY_KB_PER_DRAFT * draft_count / 1_000_000


def run_synthetic_drafts(
    config_path,
    draft_count,
    *,
    telemetry_path=None,
    print_fn=print,
):
    """Run recommendation-following drafts across cached leagues and slots."""
    estimate = estimated_telemetry_gb(draft_count)
    print_fn(
        f"Estimated SQLite addition: {estimate:.6f} GB "
        f"({ESTIMATED_TELEMETRY_KB_PER_DRAFT} KB x {draft_count} drafts)"
    )
    templates = _load_templates(config_path)
    scenarios = [
        (template, slot, roster_id)
        for template in templates
        for slot, roster_id in template.scenario["rosters_by_slot"]
    ]
    if not scenarios:
        raise ValueError("No supported cached synthetic draft scenarios were found")

    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    batch_seed = int(uuid4().hex[:16], 16)
    random.Random(batch_seed).shuffle(scenarios)
    telemetry = DraftTelemetry(telemetry_path)
    print_fn(
        f"Loaded {len(scenarios)} league-size/slot scenarios from "
        f"{len(templates)} cached league templates."
    )

    started = time.monotonic()
    for draft_index in range(draft_count):
        template, user_slot, user_roster_id = scenarios[draft_index % len(scenarios)]
        draft_id = f"synthetic:{batch_id}:{draft_index + 1:04d}"
        scenario = {
            **template.scenario,
            "user_slot": user_slot,
            "user_roster_id": user_roster_id,
        }
        roster_details = {
            roster_id: {**details, "is_user": roster_id == user_roster_id}
            for roster_id, details in template.prepared.roster_details.items()
        }
        prepared = replace(
            template.prepared,
            live_draft_id=draft_id,
            user_roster_id=user_roster_id,
            roster_details=roster_details,
            summary={
                **template.prepared.summary,
                "live_draft_id": draft_id,
                "live_user_roster_id": user_roster_id,
                "user_slot": user_slot,
            },
        )
        state = replace(template.state, draft_id=draft_id)
        _run_one_draft(
            prepared,
            state,
            telemetry,
            scenario,
            batch_id,
            batch_seed,
            draft_index,
        )
        elapsed = time.monotonic() - started
        print_fn(
            f"Completed synthetic draft {draft_index + 1}/{draft_count} "
            f"({scenario['teams']}-team, slot {user_slot}) in {elapsed:.1f}s total."
        )

    return {
        "batch_id": batch_id,
        "drafts": draft_count,
        "scenario_count": len(scenarios),
        "estimated_sqlite_gb": estimate,
        "telemetry_path": str(telemetry.path),
        "elapsed_seconds": time.monotonic() - started,
    }


def _run_one_draft(
    prepared,
    state,
    telemetry,
    scenario,
    batch_id,
    batch_seed,
    draft_index,
):
    session_id = str(uuid4())
    sample_rollout_ids = (draft_index * 2, draft_index * 2 + 1)
    config = {
        "source": "synthetic",
        "batch_id": batch_id,
        "scenario": scenario,
        "policy": "recommended_candidate_id",
        "opponent_seed": batch_seed,
        "opponent_rollout_id": sample_rollout_ids[0],
        "telemetry_profile": "screen_final_states_picks_outcome",
        "prepared": prepared.summary,
        "monitor": {
            "rollout_count": SYNTHETIC_ROLLOUT_COUNT,
            "candidate_count": SYNTHETIC_CANDIDATE_COUNT,
            "candidate_breadth": SYNTHETIC_CANDIDATE_BREADTH,
            "temperature": LIVE_TEMPERATURE,
        },
    }
    trace = _RecommendationTrace()
    monitor = LiveDraftMonitor(
        prepared,
        0,
        SYNTHETIC_ROLLOUT_COUNT,
        SYNTHETIC_CANDIDATE_COUNT,
        SYNTHETIC_CANDIDATE_BREADTH,
        LIVE_TEMPERATURE,
        trace,
        session_id,
    )
    monitor.executor = create_live_executor(prepared)
    calculation = Thread(
        target=monitor.calculate,
        args=(
            live_candidate_pool,
            evaluate_live_candidates,
            live_recommendation_payload,
            None,
            None,
            select_finalists,
            merge_screen_refinement,
            None,
            refinement_survivors,
        ),
        daemon=True,
    )
    calculation.start()
    recommendation_count = 0
    opponent_log_probability = 0.0
    telemetry_started = False
    try:
        telemetry.start_session(session_id, state.draft_id, config)
        telemetry_started = True
        while state.current_pick_no is not None:
            if state.current_roster_id != prepared.user_roster_id:
                state, picks = _sample_to_next_user(
                    prepared,
                    state,
                    None,
                    sample_rollout_ids,
                    batch_seed,
                )
                opponent_log_probability += _record_picks(
                    telemetry,
                    session_id,
                    prepared,
                    state,
                    picks,
                    sample_rollout_ids[0],
                )
                continue

            summary = live_state_summary(prepared, state)
            telemetry.record(
                session_id,
                state.draft_id,
                "draft_state",
                summary,
                pick_no=state.current_pick_no,
                stage="on_clock",
            )
            trace.reset()
            recommendation, duration = _recommend(monitor, calculation, state)
            recommendation_count += 1
            if trace.screen is None:
                raise RuntimeError("Synthetic recommendation did not retain its full screen")
            screen, _, screen_duration = trace.screen
            telemetry.record(
                session_id,
                state.draft_id,
                "recommendation",
                screen,
                pick_no=state.current_pick_no,
                stage="screen",
                duration_seconds=screen_duration,
            )
            telemetry.record(
                session_id,
                state.draft_id,
                "recommendation",
                recommendation,
                pick_no=state.current_pick_no,
                stage="ready",
                duration_seconds=duration,
            )
            state, picks = _sample_to_next_user(
                prepared,
                state,
                recommendation["recommended_candidate_id"],
                sample_rollout_ids,
                batch_seed,
            )
            opponent_log_probability += _record_picks(
                telemetry,
                session_id,
                prepared,
                state,
                picks,
                sample_rollout_ids[0],
                recommendation["recommended_candidate_id"],
            )

        state = replace(state, status="complete")
        telemetry.record(
            session_id,
            state.draft_id,
            "draft_state",
            live_state_summary(prepared, state),
            stage="complete",
        )
        telemetry.record(
            session_id,
            state.draft_id,
            "synthetic_summary",
            {
                "scenario": scenario,
                "recommendation_count": recommendation_count,
                "followed_recommendations": recommendation_count,
                "opponent_log_probability": opponent_log_probability,
                "final_rosters": [
                    {"roster_id": roster_id, "player_ids": list(player_ids)}
                    for roster_id, player_ids in state.rosters
                ],
            },
            stage="final",
        )
        telemetry.record(
            session_id,
            state.draft_id,
            "completed_draft_simulation",
            completed_league_simulation(prepared, state),
            stage="final",
        )
    except BaseException as error:
        if telemetry_started:
            telemetry.record(
                session_id,
                state.draft_id,
                "synthetic_error",
                {
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                },
                pick_no=state.current_pick_no,
                stage="failed",
            )
            telemetry.finish_session(session_id, "failed")
        raise
    else:
        telemetry.finish_session(session_id, "completed")
    finally:
        monitor.stop()
        calculation.join()
        monitor.executor.shutdown(wait=True, cancel_futures=True)
        prepared.evaluator._cache.clear()


def _recommend(monitor, calculation, state):
    started = time.monotonic()
    with monitor.lock:
        monitor.state_fingerprint = _state_fingerprint(state)
        monitor.pending_state = state
        monitor.recommendation = None
        monitor.recommendation_status = "pending"
        monitor.recommendation_error = None
        monitor.recommendation_pick_no = state.current_pick_no
    monitor.calculation_event.set()
    while True:
        with monitor.lock:
            status = monitor.recommendation_status
            recommendation = monitor.recommendation
            error = monitor.recommendation_error
        if status == "ready" and recommendation is not None:
            return recommendation, time.monotonic() - started
        if status == "failed":
            raise RuntimeError(error or "Synthetic recommendation failed")
        if not calculation.is_alive():
            raise RuntimeError("Synthetic recommendation worker stopped unexpectedly")
        time.sleep(0.01)


def _sample_to_next_user(
    prepared,
    state,
    root_candidate_id,
    rollout_ids,
    seed,
):
    temperature = LIVE_TEMPERATURE
    snapshot = _bank_market_snapshot(prepared)
    choose = _live_opponent_choice(snapshot, prepared.evaluator, state, temperature)
    completions = complete_drafts(
        state,
        root_candidate_id,
        prepared.user_roster_id,
        rollout_ids,
        choose,
        _projection_user_policy(prepared.evaluator, state, choose),
        seed=seed,
        temperature=1.0,
    )
    picks = []
    for pick in completions[0].picks:
        if (
            completions[0].next_user_pick_no is not None
            and pick.pick_no >= completions[0].next_user_pick_no
        ):
            break
        picks.append(pick)
        state = state.with_pick(
            pick.player_id,
            position=prepared.player_details.get(pick.player_id, {}).get("position"),
        )
    return state, tuple(picks)


def _record_picks(
    telemetry,
    session_id,
    prepared,
    state,
    picks,
    sample_rollout_id,
    recommended_candidate_id=None,
):
    summaries = {
        pick["pick_no"]: pick
        for pick in live_state_summary(prepared, state)["recent_picks"]
    }
    opponent_log_probability = 0.0
    for pick in picks:
        is_user = pick.roster_id == prepared.user_roster_id
        if not is_user:
            opponent_log_probability += math.log(pick.probability)
        telemetry.record(
            session_id,
            state.draft_id,
            "pick",
            {
                **summaries[pick.pick_no],
                "source": (
                    "synthetic_recommendation" if is_user else "synthetic_opponent_model"
                ),
                "selection_probability": pick.probability,
                "selection_log_probability": math.log(pick.probability),
                "sample_rollout_id": sample_rollout_id,
                "recommended_candidate_id": (
                    recommended_candidate_id if is_user else None
                ),
                "followed_recommendation": bool(is_user),
            },
            pick_no=pick.pick_no,
            stage="user" if is_user else "opponent",
        )
    return opponent_log_probability


def _load_templates(config_path):
    config = AppConfig.from_file(config_path)
    player_loader = PlayerLoader()
    player_loader.load_players()
    players = draftable_players(player_loader.enriched_players)
    sleeper_players_path = player_loader.sleeper_players_file
    sleeper_players = json.loads(sleeper_players_path.read_text())
    player_ids = tuple(sleeper_players)
    player_details = _player_details(sleeper_players_path)
    banks = {}
    templates = []

    for path in sorted(CACHE_DIR.glob("league_*.json")):
        snapshot = json.loads(path.read_text())
        summary = snapshot.get("draft_summary") or {}
        compatibility = summary.get("compatibility") or {}
        draft = snapshot.get("draft") or {}
        league = snapshot.get("league") or {}
        if (
            compatibility.get("status") != "supported"
            or not compatibility.get("redraft_eligible")
            or draft.get("type") not in {"snake", "linear"}
        ):
            continue

        blank_draft = {**draft, "status": "drafting"}
        state = replay_sleeper_draft(
            blank_draft,
            [],
            snapshot.get("traded_picks") or (),
            player_ids,
        )
        season = int(league.get("season") or datetime.now().year)
        market = load_league_market_snapshot(
            league,
            season=season,
            max_age=None,
        )
        market_snapshot = _live_market_snapshot(market["snapshot"])
        if market_snapshot is None or not market_snapshot.get("observations"):
            raise ValueError(f"Cached league {state.draft_id} has no usable market snapshot")

        league_model = League(league)
        roster_by_slot = {
            int(slot): int(roster_id)
            for slot, roster_id in (draft.get("slot_to_roster_id") or {}).items()
        }
        slot_by_roster = {roster_id: slot for slot, roster_id in roster_by_slot.items()}
        for roster in snapshot.get("rosters") or ():
            division = (roster.get("settings") or {}).get("division")
            if division is not None:
                league_model.divisions.setdefault(int(division), []).append(
                    roster_by_slot[slot_by_roster[int(roster["roster_id"])]]
                )
        bank_key = json.dumps(league.get("scoring_settings") or {}, sort_keys=True)
        bank = banks.get(bank_key)
        if bank is None:
            bank = build_season_world_bank(
                league_model,
                players,
                300,
                weeks=config.regular_season_weeks + 3,
                seed=config.seed,
            )
            banks[bank_key] = bank
        evaluator = LeagueEvaluator(
            league_model,
            bank,
            roster_by_slot.values(),
            config.regular_season_weeks,
            seed=config.seed,
        )
        roster_details = _roster_details(
            roster_by_slot,
            roster_by_slot,
            snapshot.get("rosters") or (),
            snapshot.get("users") or (),
            None,
        )
        scenario = {
            "template_league_id": str(league.get("league_id")),
            "template_draft_id": state.draft_id,
            "league_name": league.get("name"),
            "teams": state.teams,
            "rounds": state.rounds,
            "draft_type": state.draft_type,
            "market_context": market["context"],
            "roster_positions": list(league.get("roster_positions") or ()),
            "rosters_by_slot": sorted(roster_by_slot.items()),
        }
        prepared = PreparedDraft(
            summary={
                "status": "ready",
                "source": "synthetic_cache",
                "league_id": scenario["template_league_id"],
                "draft_id": scenario["template_draft_id"],
                "live_draft_id": scenario["template_draft_id"],
                "league_name": scenario["league_name"],
                "draft_type": state.draft_type,
                "teams": state.teams,
                "rounds": state.rounds,
                "market_context": market["context"],
                "market_snapshot_id": market_snapshot.get("snapshot_id"),
                "market_players": len(market_snapshot["observations"]),
                "world_bank": {
                    "version": bank.version,
                    "worlds": bank.world_count,
                    "players": len(bank.player_ids),
                },
            },
            live_draft_id=state.draft_id,
            league_id=scenario["template_league_id"],
            standalone=True,
            user_roster_id=None,
            market_snapshot=market_snapshot,
            evaluator=evaluator,
            player_details=player_details,
            roster_details=roster_details,
        )
        templates.append(SyntheticTemplate(prepared, state, scenario))

    return tuple(templates)
