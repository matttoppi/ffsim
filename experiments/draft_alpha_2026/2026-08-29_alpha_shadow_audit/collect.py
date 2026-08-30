#!/usr/bin/env python3
import hashlib
import json
import time
from pathlib import Path
from threading import Thread

from ffsim.api import LiveDraftMonitor, _state_fingerprint
from ffsim.draft_intel.alpha_shadow import load_default_alpha_shadow_collector
from ffsim.draft_intel.live import (
    evaluate_live_candidates,
    live_candidate_pool,
    live_recommendation_payload,
    merge_screen_refinement,
    select_finalists,
)
from ffsim.draft_intel.telemetry import DraftTelemetry
from ffsim.draft_intel.timing_report import build_cached_timing_context
from ffsim.historical_sleeper.hdvn_snapshot import canonical_json

ROOT = Path(__file__).parents[3]
HERE = Path(__file__).parent
CORPUS = ROOT / "experiments/draft_alpha_2026/2026-08-29_multi_state_corpus/corpus.json"


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def wait_for(monitor, field, expected, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = monitor.snapshot()
        if snapshot[field] == expected:
            return snapshot
        if snapshot[field] == "failed":
            raise RuntimeError(
                snapshot.get("alpha_shadow_error")
                or snapshot.get("recommendation_error")
            )
        time.sleep(0.01)
    raise TimeoutError(f"monitor {field} did not reach {expected}")


def collect_state(state_record, telemetry, collector):
    context = build_cached_timing_context(
        ROOT / state_record["config"],
        ROOT / state_record["league_cache"],
        roster_id=state_record["roster_id"],
        draft_cache=ROOT / state_record["draft_cache"],
        world_count=20,
    )
    monitor = LiveDraftMonitor(
        context["prepared"],
        1.0,
        20,
        10,
        candidate_breadth=20,
        telemetry=telemetry,
        alpha_shadow_collector=collector,
        alpha_shadow_status="idle",
    )
    monitor.status = "running"
    telemetry.start_session(
        monitor.session_id,
        context["state"].draft_id,
        {
            "experiment": "six-state-alpha-shadow-audit",
            "corpus_state": state_record,
        },
    )
    monitor.pending_state = context["state"]
    monitor.state_fingerprint = _state_fingerprint(context["state"])
    monitor.calculation_event.set()
    worker = Thread(
        target=monitor.calculate,
        kwargs={
            "candidate_pool": live_candidate_pool,
            "evaluate_candidates": evaluate_live_candidates,
            "recommendation_payload": live_recommendation_payload,
            "select_finalists": select_finalists,
            "merge_refinement": merge_screen_refinement,
        },
    )
    worker.start()
    try:
        recommendation = wait_for(
            monitor, "recommendation_status", "ready"
        )
        before = digest(recommendation["recommendation"])
        shadow = wait_for(monitor, "alpha_shadow_status", "ready")
        after = digest(shadow["recommendation"])
    finally:
        monitor.stop()
        worker.join(10)
        telemetry.finish_session(monitor.session_id, "stopped")
    evidence = shadow["alpha_shadow"]
    return {
        "session_id": monitor.session_id,
        "draft_id": context["state"].draft_id,
        "pick_no": context["state"].current_pick_no,
        "recommendation_unchanged": before == after,
        "alpha_shadow_duration_seconds": shadow[
            "alpha_shadow_duration_seconds"
        ],
        "top_ten_capture_complete": evidence[
            "top_ten_capture_complete"
        ],
        "manager_shadow_status": evidence["manager_shadow"]["status"],
        "manager_shadow_practical": evidence["manager_shadow"].get(
            "shadow_leader_in_terminal_practical_tier"
        ),
        "manager_support": evidence["manager_support"],
        "worker_stopped": not worker.is_alive(),
    }


def main():
    telemetry_path = HERE / "telemetry.sqlite3"
    if telemetry_path.exists():
        raise FileExistsError(f"immutable corpus telemetry exists: {telemetry_path}")
    corpus = json.loads(CORPUS.read_text())
    collector, error = load_default_alpha_shadow_collector()
    if collector is None:
        raise RuntimeError(error)
    telemetry = DraftTelemetry(telemetry_path)
    states = []
    for state_record in corpus["states"]:
        print(f"collecting {state_record['draft_id']}", flush=True)
        states.append(collect_state(state_record, telemetry, collector))
    passed = (
        len(states) == 6
        and all(state["recommendation_unchanged"] for state in states)
        and all(state["top_ten_capture_complete"] for state in states)
        and all(state["manager_shadow_status"] == "ready" for state in states)
        and all(state["worker_stopped"] for state in states)
    )
    result = {
        "experiment": "six-state integrated alpha shadow telemetry collection",
        "status": "research" if passed else "rejected",
        "telemetry_path": str(telemetry_path.relative_to(ROOT)),
        "states": states,
        "gate": {"passes": passed},
    }
    (HERE / "collection.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
