"""Checkpointed racing-versus-flat validation for a synthetic telemetry batch."""

import argparse
from collections import defaultdict
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

from ffsim.api import FINALIST_COUNT, SCREEN_ROLLOUT_COUNT
from ffsim.draft_intel.decision import DECISION_ENGINE_VERSION, rank_candidates
from ffsim.draft_intel.live import (
    LIVE_EVALUATION_WORKERS,
    LIVE_REACH_RATE,
    LIVE_ROLLOUT_CHUNK,
    LIVE_SEASON_WORLDS_PER_ROLLOUT,
    LIVE_TEMPERATURE,
    _live_market_snapshot,
    create_live_executor,
    evaluate_live_candidates,
    live_recommendation_payload,
    merge_screen_refinement,
    select_finalists,
)
from ffsim.draft_intel.market import load_market_snapshot_by_id
from ffsim.draft_intel.market_model import (
    MODEL_VERSION as OPPONENT_MARKET_MODEL_VERSION,
)
from ffsim.draft_intel.opportunity import VONA_MODEL_VERSION
from ffsim.draft_intel.synthetic import _load_templates
from ffsim.paths import CACHE_DIR
from ffsim.simulation.evaluator import ROSTER_VALUE_VERSION


SCHEMA_VERSION = 3
SEED = 2026
REFINEMENT_STAGES = (150, 225, 300)
DEFAULT_TELEMETRY = CACHE_DIR / "draft_intel" / "telemetry.sqlite3"


def compare_outcomes(racing, flat):
    """Compare the four release-gate outcomes for one state."""
    headline_match = racing["headline_candidate_id"] == flat["headline_candidate_id"]
    status_match = racing["decision_status"] == flat["decision_status"]
    practical_match = (
        set(racing["practical_co_leader_candidate_ids"])
        == set(flat["practical_co_leader_candidate_ids"])
    )
    unsafe = sorted(
        set(flat["practical_co_leader_candidate_ids"])
        - set(racing["survivor_candidate_ids"])
    )
    mismatch = not headline_match or not status_match or not practical_match or bool(unsafe)
    return {
        "headline_match": headline_match,
        "decision_status_match": status_match,
        "practical_co_leaders_match": practical_match,
        "unsafe_eliminated_candidate_ids": unsafe,
        "mismatch": mismatch,
    }


def resume_keys(records, batch_id, run_identity):
    """Validate checkpoint identity and return its completed state keys."""
    keys = set()
    for record in records:
        if record.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Checkpoint schema version does not match")
        if record.get("batch_id") != batch_id:
            raise ValueError("Checkpoint contains a different batch ID")
        if record.get("run_identity") != run_identity:
            raise ValueError("Checkpoint run identity does not match")
        if record.get("status") not in {"ok", "mismatch", "error"}:
            raise ValueError("Checkpoint contains an unknown status")
        key = (str(record["session_id"]), int(record["pick_no"]))
        if key in keys:
            raise ValueError(f"Checkpoint contains duplicate state {key}")
        keys.add(key)
    return keys


def aggregate_records(records, batch_ready_states=None):
    """Aggregate checkpoint records without reading telemetry or rerunning work."""
    completed = [record for record in records if record.get("status") != "error"]
    errors = [record for record in records if record.get("status") == "error"]
    mismatches = [
        record for record in completed if record["comparison"]["mismatch"]
    ]
    unsafe = [
        record for record in completed
        if record["comparison"]["unsafe_eliminated_candidate_ids"]
    ]
    work = {
        mode: sum(record[mode]["work"]["total"] for record in completed)
        for mode in ("racing", "flat")
    }
    timings = {
        mode: {
            field: sum(
                record[mode]["timing_seconds"][field] for record in completed
            )
            for field in ("screen", "refinement", "total")
        }
        for mode in ("racing", "flat")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "run_identity": (
            records[0].get("run_identity") if records else None
        ),
        "batch_ready_states": batch_ready_states,
        "records": len(records),
        "completed": len(completed),
        "errors": len(errors),
        "mismatches": len(mismatches),
        "unsafe_elimination_states": len(unsafe),
        "unsafe_eliminated_candidates": sum(
            len(record["comparison"]["unsafe_eliminated_candidate_ids"])
            for record in unsafe
        ),
        "candidate_rollout_work": work,
        "racing_to_flat_work_ratio": (
            work["racing"] / work["flat"] if work["flat"] else None
        ),
        "timing_seconds": timings,
    }


def _snapshot_database(source, destination):
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f"Telemetry database not found: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Snapshot path must differ from the telemetry database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
    )
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        source_uri = source.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as live_database:
            with sqlite3.connect(temporary) as snapshot:
                live_database.backup(snapshot)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _run_identity(snapshot_path):
    digest = hashlib.sha256()
    with Path(snapshot_path).open("rb") as snapshot:
        for chunk in iter(lambda: snapshot.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "snapshot_sha256": digest.hexdigest(),
        "decision_engine_version": DECISION_ENGINE_VERSION,
        "opponent_market_model_version": OPPONENT_MARKET_MODEL_VERSION,
        "roster_scorer_version": ROSTER_VALUE_VERSION,
        "vona_model_version": VONA_MODEL_VERSION,
        "seed": SEED,
        "screen_rollout_count": SCREEN_ROLLOUT_COUNT,
        "finalist_count": FINALIST_COUNT,
        "refinement_stages": list(REFINEMENT_STAGES),
        "season_worlds_per_rollout": LIVE_SEASON_WORLDS_PER_ROLLOUT,
        "evaluation_workers": LIVE_EVALUATION_WORKERS,
        "rollout_chunk": LIVE_ROLLOUT_CHUNK,
        "live_temperature": LIVE_TEMPERATURE,
        "live_reach_rate": LIVE_REACH_RATE,
    }


def _prepare_snapshot(source, destination, resuming):
    destination = Path(destination)
    if resuming:
        if not destination.is_file():
            raise FileNotFoundError(
                f"Checkpoint snapshot not found: {destination}"
            )
        return "Reusing telemetry snapshot"
    _snapshot_database(source, destination)
    return "Telemetry snapshot"


def _read_checkpoint(path):
    """Read valid records and trim an interrupted final append."""
    path = Path(path)
    if not path.exists():
        return []
    data = path.read_bytes()
    records = []
    valid_bytes = 0
    lines = data.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.endswith(b"\n"):
            if index != len(lines) - 1:
                raise ValueError("Checkpoint contains a malformed line")
            with path.open("r+b") as output:
                output.truncate(valid_bytes)
            break
        try:
            records.append(json.loads(line))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Checkpoint contains invalid JSON on line {index + 1}") from error
        valid_bytes += len(line)
    return records


def _append_record(output, record):
    output.write(
        json.dumps(record, separators=(",", ":"), sort_keys=True, allow_nan=False)
        + "\n"
    )
    output.flush()
    os.fsync(output.fileno())


def _load_batch(snapshot_path, batch_id):
    snapshot_uri = Path(snapshot_path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(snapshot_uri, uri=True) as database:
        database.row_factory = sqlite3.Row
        sessions = database.execute(
            "SELECT session_id, draft_id, started_at, config_json "
            "FROM live_draft_sessions "
            "WHERE status='completed' "
            "AND json_extract(config_json, '$.batch_id')=? "
            "ORDER BY started_at, session_id",
            (batch_id,),
        ).fetchall()
        if not sessions:
            raise ValueError(f"No completed sessions found for batch {batch_id}")
        placeholders = ",".join("?" for _ in sessions)
        events = database.execute(
            "SELECT id, session_id, event_type, pick_no, stage, payload_json "
            f"FROM live_draft_events WHERE session_id IN ({placeholders}) "
            "AND (event_type='pick' OR "
            "(event_type='recommendation' AND stage IN ('screen','ready'))) "
            "ORDER BY session_id, id",
            tuple(row["session_id"] for row in sessions),
        ).fetchall()

    by_session = defaultdict(list)
    for row in events:
        by_session[row["session_id"]].append(row)
    result = []
    for session in sessions:
        session_id = session["session_id"]
        config = json.loads(session["config_json"])
        if config.get("source") != "synthetic":
            raise ValueError(f"Session {session_id} is not synthetic")
        picks = []
        screens = {}
        ready = {}
        for event in by_session[session_id]:
            payload = json.loads(event["payload_json"])
            if event["event_type"] == "pick":
                picks.append(payload)
                continue
            pick_no = int(event["pick_no"])
            target = screens if event["stage"] == "screen" else ready
            if pick_no in target:
                raise ValueError(
                    f"Session {session_id} has duplicate {event['stage']} state {pick_no}"
                )
            target[pick_no] = payload
        if not ready:
            raise ValueError(f"Completed session {session_id} has no ready states")
        states = []
        for pick_no, payload in sorted(ready.items()):
            screen = screens.get(pick_no)
            if screen is None:
                raise ValueError(
                    f"Session {session_id} pick {pick_no} has no broad screen"
                )
            candidate_ids = tuple(
                str(candidate["player_id"])
                for candidate in screen.get("candidates", ())
            )
            if not candidate_ids or len(set(candidate_ids)) != len(candidate_ids):
                raise ValueError(
                    f"Session {session_id} pick {pick_no} has invalid screen candidates"
                )
            states.append({
                "pick_no": pick_no,
                "candidate_ids": candidate_ids,
                "recorded_ready": {
                    "headline_candidate_id": payload.get(
                        "recommended_candidate_id"
                    ),
                    "decision_status": payload.get("decision_status"),
                    "practical_co_leader_candidate_ids": sorted(
                        map(str, payload.get("co_leader_candidate_ids", ()))
                    ),
                    "decision_engine_version": payload.get(
                        "decision_engine_version"
                    ),
                    "league_evaluator_version": payload.get(
                        "league_evaluator_version"
                    ),
                    "run_signature": payload.get("run_signature"),
                },
            })
        result.append({
            "session_id": session_id,
            "draft_id": session["draft_id"],
            "config": config,
            "picks": tuple(sorted(picks, key=lambda pick: int(pick["pick_no"]))),
            "states": states,
        })
    return result


def _rebuild_states(session, template, selected_pick_nos):
    scenario = session["config"].get("scenario") or {}
    recorded = session["config"].get("prepared") or {}
    current = template.prepared.summary
    checks = {
        "template draft": (
            str(scenario.get("template_draft_id")),
            str(template.scenario.get("template_draft_id")),
        ),
        "market snapshot": (
            recorded.get("market_snapshot_id"),
            current.get("market_snapshot_id"),
        ),
        "world bank": (
            (recorded.get("world_bank") or {}).get("version"),
            (current.get("world_bank") or {}).get("version"),
        ),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(
                f"Session {session['session_id']} {label} changed: "
                f"recorded {expected}, loaded {actual}"
            )
    recorded_evaluator_versions = {
        item["recorded_ready"]["league_evaluator_version"]
        for item in session["states"]
    }
    current_evaluator_version = template.prepared.evaluator.version
    if recorded_evaluator_versions != {current_evaluator_version}:
        raise ValueError(
            f"Session {session['session_id']} league evaluator changed: "
            f"recorded {sorted(map(str, recorded_evaluator_versions))}, "
            f"loaded {current_evaluator_version}"
        )
    monitor = session["config"].get("monitor") or {}
    if (
        int(monitor.get("rollout_count", 0)) != REFINEMENT_STAGES[-1]
        or float(monitor.get("temperature", -1)) != LIVE_TEMPERATURE
    ):
        raise ValueError(
            f"Session {session['session_id']} used a different monitor budget"
        )
    user_roster_id = int(scenario["user_roster_id"])
    prepared = replace(
        template.prepared,
        live_draft_id=session["draft_id"],
        user_roster_id=user_roster_id,
    )
    state = replace(template.state, draft_id=session["draft_id"])
    picks = iter(session["picks"])
    next_pick = next(picks, None)
    rebuilt = []
    for item in session["states"]:
        pick_no = item["pick_no"]
        while next_pick is not None and int(next_pick["pick_no"]) < pick_no:
            recorded_pick_no = int(next_pick["pick_no"])
            if state.current_pick_no != recorded_pick_no:
                raise ValueError(
                    f"Session {session['session_id']} expected pick "
                    f"{state.current_pick_no}, recorded {recorded_pick_no}"
                )
            state = state.with_pick(
                str(next_pick["player_id"]),
                position=next_pick.get("position"),
            )
            next_pick = next(picks, None)
        if state.current_pick_no != pick_no:
            raise ValueError(
                f"Session {session['session_id']} rebuilt pick "
                f"{state.current_pick_no}, expected {pick_no}"
            )
        if state.current_roster_id != user_roster_id:
            raise ValueError(
                f"Session {session['session_id']} pick {pick_no} is not the user turn"
            )
        if pick_no in selected_pick_nos:
            rebuilt.append({**item, "state": state})
    return prepared, rebuilt


def _evaluate_state(prepared, item, executor, mode):
    if mode not in {"racing", "flat"}:
        raise ValueError(f"Unknown validation mode: {mode}")
    started = time.monotonic()
    screen_started = time.monotonic()
    candidate_ids = item["candidate_ids"]
    screen = evaluate_live_candidates(
        prepared,
        item["state"],
        SCREEN_ROLLOUT_COUNT,
        candidate_ids,
        executor=executor,
        survival_ids=candidate_ids,
        seed=SEED,
    )
    screen_payload = live_recommendation_payload(
        prepared,
        item["state"],
        [screen],
        len(candidate_ids),
    )
    finalists = select_finalists(
        prepared,
        item["state"],
        screen_payload["candidates"],
        FINALIST_COUNT,
    )
    if not finalists:
        raise ValueError("Screen selected no finalists")
    screen_seconds = time.monotonic() - screen_started

    refinement_started = time.monotonic()
    previous = [screen]
    previous_count = SCREEN_ROLLOUT_COUNT
    evaluation = None
    payload = None
    refinement_work = 0
    stages = []
    refinement_stages = (
        REFINEMENT_STAGES
        if mode == "racing"
        else (REFINEMENT_STAGES[-1],)
    )
    for stage in refinement_stages:
        evaluated_ids = finalists
        extension = evaluate_live_candidates(
            prepared,
            item["state"],
            range(previous_count, stage),
            evaluated_ids,
            executor=executor,
            survival_ids=evaluated_ids,
            seed=SEED,
        )
        refinement_work += len(evaluated_ids) * (stage - previous_count)
        evaluation = merge_screen_refinement(previous, extension)
        payload = live_recommendation_payload(
            prepared,
            item["state"],
            [evaluation],
            len(candidate_ids),
        )
        ranked = rank_candidates(evaluation)
        q_leader = ranked[0]
        gate_bounds = [
            {
                "candidate_id": candidate.candidate_id,
                "lower_bound": delta.interval[0],
                "upper_bound": delta.interval[1],
            }
            for candidate in ranked[1:]
            for delta in (
                evaluation.paired_value_delta(
                    q_leader.candidate_id,
                    candidate.candidate_id,
                ),
            )
        ]
        stop_reason = (
            "max_budget" if stage == REFINEMENT_STAGES[-1] else None
        )
        stages.append({
            "rollout_count": stage,
            "evaluated_candidate_ids": list(evaluated_ids),
            "q_leader_candidate_id": q_leader.candidate_id,
            "leader_minus_candidate_bounds": gate_bounds,
            "practical_co_leader_candidate_ids": sorted(
                map(str, payload["co_leader_candidate_ids"])
            ),
            "survivor_candidate_ids": list(finalists),
            "stop_reason": stop_reason,
        })
        previous = [evaluation]
        previous_count = stage

    finished = time.monotonic()
    screen_work = len(candidate_ids) * SCREEN_ROLLOUT_COUNT
    return {
        "headline_candidate_id": payload["recommended_candidate_id"],
        "decision_status": payload["decision_status"],
        "practical_co_leader_candidate_ids": sorted(
            map(str, payload["co_leader_candidate_ids"])
        ),
        "finalist_candidate_ids": list(finalists),
        "survivor_candidate_ids": list(finalists),
        "final_rollout_count": stages[-1]["rollout_count"],
        "stages": stages,
        "work": {
            "screen": screen_work,
            "refinement": refinement_work,
            "total": screen_work + refinement_work,
        },
        "timing_seconds": {
            "screen": screen_seconds,
            "refinement": finished - refinement_started,
            "total": finished - started,
        },
    }


class _StateFailure(Exception):
    def __init__(self, mode, item, error):
        super().__init__(str(error))
        self.mode = mode
        self.item = item
        self.error = error


def _run_session_pass(prepared, items, mode):
    prepared.evaluator._cache.clear()
    results = {}
    with create_live_executor(prepared) as executor:
        for item in items:
            try:
                results[item["pick_no"]] = _evaluate_state(
                    prepared, item, executor, mode
                )
            except Exception as error:
                raise _StateFailure(mode, item, error) from error
    return results


def _error_record(batch_id, session, failure, run_identity):
    return {
        "schema_version": SCHEMA_VERSION,
        "run_identity": run_identity,
        "batch_id": batch_id,
        "session_id": session["session_id"],
        "draft_id": session["draft_id"],
        "pick_no": failure.item["pick_no"],
        "status": "error",
        "error": {
            "mode": failure.mode,
            "type": type(failure.error).__name__,
            "message": str(failure.error),
        },
    }


def _pin_recorded_market_snapshots(templates, sessions):
    expected = defaultdict(set)
    for session in sessions:
        scenario = session["config"].get("scenario") or {}
        prepared = session["config"].get("prepared") or {}
        expected[str(scenario.get("template_league_id"))].add(
            prepared.get("market_snapshot_id")
        )
    result = []
    for template in templates:
        template_id = str(template.scenario.get("template_league_id"))
        snapshot_ids = expected.get(template_id, set())
        if len(snapshot_ids) != 1 or None in snapshot_ids:
            raise ValueError(
                f"Synthetic template {template_id} has inconsistent recorded market snapshots"
            )
        snapshot_id = next(iter(snapshot_ids))
        snapshot = _live_market_snapshot(load_market_snapshot_by_id(snapshot_id))
        if snapshot is None or not snapshot.get("observations"):
            raise ValueError(f"Recorded market snapshot is unavailable: {snapshot_id}")
        summary = {
            **template.prepared.summary,
            "market_snapshot_id": snapshot_id,
            "market_players": len(snapshot["observations"]),
        }
        result.append(replace(
            template,
            prepared=replace(
                template.prepared,
                summary=summary,
                market_snapshot=snapshot,
            ),
        ))
    return tuple(result)


def validate(args):
    output_path = Path(args.output) if args.output else (
        CACHE_DIR / "draft_intel" / f"racing-corpus-{args.batch_id}.jsonl"
    )
    snapshot_path = Path(args.snapshot) if args.snapshot else output_path.with_suffix(
        ".snapshot.sqlite3"
    )
    if output_path.resolve() == snapshot_path.resolve():
        raise ValueError("Checkpoint output and telemetry snapshot must differ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = _read_checkpoint(output_path)
    snapshot_status = _prepare_snapshot(args.telemetry, snapshot_path, bool(records))
    print(f"{snapshot_status}: {snapshot_path}", file=sys.stderr, flush=True)
    run_identity = _run_identity(snapshot_path)
    seen = resume_keys(records, args.batch_id, run_identity)

    sessions = _load_batch(snapshot_path, args.batch_id)
    all_states = [
        (session["session_id"], item["pick_no"])
        for session in sessions
        for item in session["states"]
    ]
    selected_keys = set(all_states[:args.limit] if args.limit else all_states)
    unknown = seen - set(all_states)
    if unknown:
        raise ValueError(f"Checkpoint contains states outside the batch: {sorted(unknown)}")
    if any(record["status"] == "error" for record in records):
        print(json.dumps(aggregate_records(records, len(all_states)), sort_keys=True))
        return 1
    pending = selected_keys - seen
    if not pending:
        summary = aggregate_records(records, len(all_states))
        print(json.dumps(summary, sort_keys=True))
        return int(bool(summary["errors"] or summary["mismatches"]))

    templates = {
        template.scenario["template_league_id"]: template
        for template in _pin_recorded_market_snapshots(
            _load_templates(args.config), sessions
        )
    }
    with output_path.open("a", encoding="utf-8") as output:
        for session in sessions:
            session_keys = {
                (session["session_id"], item["pick_no"])
                for item in session["states"]
            }
            todo_keys = pending & session_keys
            if not todo_keys:
                continue
            scenario = session["config"].get("scenario") or {}
            template_id = str(scenario.get("template_league_id"))
            template = templates.get(template_id)
            if template is None:
                raise ValueError(f"Synthetic template not found: {template_id}")
            prepared, items = _rebuild_states(
                session,
                template,
                {pick_no for _, pick_no in todo_keys},
            )
            prepared.evaluator.flat_season_scores()
            try:
                racing = _run_session_pass(prepared, items, "racing")
                flat = _run_session_pass(prepared, items, "flat")
            except _StateFailure as failure:
                record = _error_record(
                    args.batch_id, session, failure, run_identity
                )
                _append_record(output, record)
                records.append(record)
                print(json.dumps(aggregate_records(records, len(all_states)), sort_keys=True))
                return 1

            for item in items:
                pick_no = item["pick_no"]
                racing_result = racing[pick_no]
                flat_result = flat[pick_no]
                if (
                    racing_result["finalist_candidate_ids"]
                    != flat_result["finalist_candidate_ids"]
                ):
                    failure = _StateFailure(
                        "comparison",
                        item,
                        AssertionError("Racing and flat selected different finalists"),
                    )
                    record = _error_record(
                        args.batch_id, session, failure, run_identity
                    )
                    _append_record(output, record)
                    records.append(record)
                    print(
                        json.dumps(
                            aggregate_records(records, len(all_states)),
                            sort_keys=True,
                        )
                    )
                    return 1
                comparison = compare_outcomes(racing_result, flat_result)
                record = {
                    "schema_version": SCHEMA_VERSION,
                    "run_identity": run_identity,
                    "batch_id": args.batch_id,
                    "session_id": session["session_id"],
                    "draft_id": session["draft_id"],
                    "pick_no": pick_no,
                    "status": "mismatch" if comparison["mismatch"] else "ok",
                    "screen_candidate_ids": list(item["candidate_ids"]),
                    "recorded_ready": item["recorded_ready"],
                    "racing": racing_result,
                    "flat": flat_result,
                    "comparison": comparison,
                    "racing_to_flat_work_ratio": (
                        racing_result["work"]["total"]
                        / flat_result["work"]["total"]
                    ),
                }
                _append_record(output, record)
                records.append(record)
                print(
                    f"{session['session_id']} pick {pick_no}: {record['status']}",
                    file=sys.stderr,
                    flush=True,
                )

    summary = aggregate_records(records, len(all_states))
    print(json.dumps(summary, sort_keys=True))
    return int(bool(summary["errors"] or summary["mismatches"]))


def _positive_limit(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("limit must be positive")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_id")
    parser.add_argument("--telemetry", default=DEFAULT_TELEMETRY, type=Path)
    parser.add_argument("--config", default=Path("config.json"), type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--limit", type=_positive_limit)
    args = parser.parse_args(argv)
    try:
        return validate(args)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
