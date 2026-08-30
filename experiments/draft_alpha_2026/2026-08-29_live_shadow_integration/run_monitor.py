#!/usr/bin/env python3
import hashlib
import json
import tempfile
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


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def wait_for(monitor, field, expected, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = monitor.snapshot()
        if snapshot[field] == expected:
            return snapshot
        if snapshot[field] == "failed":
            raise RuntimeError(snapshot.get("alpha_shadow_error") or snapshot.get("recommendation_error"))
        time.sleep(0.01)
    raise TimeoutError(f"monitor {field} did not reach {expected}")


def main():
    context = build_cached_timing_context(
        ROOT / "experiments/draft_alpha_2026/2026-08-29_top_ten_capture_attempt2/config.json",
        ROOT / "data/cache/league_1389391547115511808.json",
        roster_id=1,
        draft_cache=ROOT / "data/cache/mock_draft_1393656492011315200.json",
        world_count=20,
    )
    collector, error = load_default_alpha_shadow_collector()
    if collector is None:
        raise RuntimeError(error)
    with tempfile.TemporaryDirectory() as directory:
        telemetry = DraftTelemetry(Path(directory) / "telemetry.sqlite3")
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
            {"experiment": "cached-alpha-shadow-monitor"},
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
        recommendation_snapshot = wait_for(
            monitor, "recommendation_status", "ready"
        )
        recommendation_hash_before = digest(
            recommendation_snapshot["recommendation"]
        )
        shadow_snapshot = wait_for(monitor, "alpha_shadow_status", "ready")
        recommendation_hash_after = digest(
            shadow_snapshot["recommendation"]
        )
        monitor.stop()
        worker.join(10)
        telemetry.finish_session(monitor.session_id, "stopped")
        shadow_events = telemetry.query(
            session_id=monitor.session_id,
            event_type="alpha_shadow",
        )["events"]
    evidence = shadow_snapshot["alpha_shadow"]
    passed = (
        recommendation_hash_before == recommendation_hash_after
        and evidence["decision_active"] is False
        and evidence["top_ten_capture_complete"]
        and evidence["manager_shadow"]["status"] == "ready"
        and len(shadow_events) == 1
        and not worker.is_alive()
    )
    result = {
        "experiment": "cached LiveDraftMonitor alpha shadow flow",
        "status": "research" if passed else "rejected",
        "draft_id": context["state"].draft_id,
        "pick_no": context["state"].current_pick_no,
        "recommendation_hash_before": recommendation_hash_before,
        "recommendation_hash_after": recommendation_hash_after,
        "recommendation_unchanged": (
            recommendation_hash_before == recommendation_hash_after
        ),
        "alpha_shadow_status": shadow_snapshot["alpha_shadow_status"],
        "alpha_shadow_duration_seconds": shadow_snapshot[
            "alpha_shadow_duration_seconds"
        ],
        "alpha_shadow_calculation_count": shadow_snapshot[
            "alpha_shadow_calculation_count"
        ],
        "top_ten_capture_complete": evidence[
            "top_ten_capture_complete"
        ],
        "manager_shadow": evidence["manager_shadow"],
        "manager_support": evidence["manager_support"],
        "telemetry_shadow_events": len(shadow_events),
        "worker_stopped": not worker.is_alive(),
        "gate": {"passes": passed},
    }
    (HERE / "monitor_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
