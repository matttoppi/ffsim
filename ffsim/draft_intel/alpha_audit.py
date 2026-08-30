import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import median

from ffsim.historical_sleeper.hdvn_snapshot import canonical_json, sha256_file

ALPHA_SHADOW_AUDIT_VERSION = "alpha-shadow-audit-v1"


def build_alpha_shadow_audit(
    telemetry_path,
    *,
    draft_id=None,
    session_id=None,
):
    telemetry_path = Path(telemetry_path).resolve()
    if not telemetry_path.exists():
        raise FileNotFoundError(f"telemetry database not found: {telemetry_path}")
    database = sqlite3.connect(f"file:{telemetry_path}?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    try:
        sessions = database.execute(
            """SELECT session_id, draft_id, started_at, finished_at, status
               FROM live_draft_sessions
               WHERE (? IS NULL OR draft_id = ?)
                 AND (? IS NULL OR session_id = ?)
               ORDER BY started_at, session_id""",
            (draft_id, draft_id, session_id, session_id),
        ).fetchall()
        filters = [
            "event_type IN ('alpha_shadow', 'alpha_shadow_error', 'alpha_shadow_discarded')"
        ]
        values = []
        if draft_id is not None:
            filters.append("draft_id = ?")
            values.append(str(draft_id))
        if session_id is not None:
            filters.append("session_id = ?")
            values.append(str(session_id))
        events = database.execute(
            f"""SELECT id, session_id, draft_id, event_type, pick_no,
                       occurred_at, duration_seconds, payload_json
                FROM live_draft_events
                WHERE {' AND '.join(filters)}
                ORDER BY id""",
            values,
        ).fetchall()
    finally:
        database.close()
    decoded = [
        {
            **{key: row[key] for key in row.keys() if key != "payload_json"},
            "payload": json.loads(row["payload_json"]),
        }
        for row in events
    ]
    ready_events = [event for event in decoded if event["event_type"] == "alpha_shadow"]
    failed_events = [
        event for event in decoded if event["event_type"] == "alpha_shadow_error"
    ]
    discarded_events = [
        event for event in decoded if event["event_type"] == "alpha_shadow_discarded"
    ]
    deduplicated = {}
    for event in ready_events:
        payload = event["payload"]
        key = (
            event["session_id"],
            event["pick_no"],
            payload.get("state_signature"),
        )
        deduplicated[key] = event
    ready = list(deduplicated.values())
    durations = [
        float(event["duration_seconds"])
        for event in ready
        if event["duration_seconds"] is not None
    ]
    component_durations = {
        component: [
            float(event["payload"]["component_duration_seconds"][component])
            for event in ready
            if component in (
                event["payload"].get("component_duration_seconds") or {}
            )
        ]
        for component in ("hierarchical_timing", "manager_shadow")
    }
    candidates = [
        candidate
        for event in ready
        for candidate in event["payload"].get("candidates") or ()
    ]
    measured_candidates = [
        candidate for candidate in candidates
        if candidate.get("return_probability") is not None
    ]
    direct_support = [
        int(candidate.get("direct_support") or 0)
        for candidate in measured_candidates
    ]
    interval_widths = [
        float(interval[1]) - float(interval[0])
        for candidate in measured_candidates
        if (interval := candidate.get("return_interval_95")) is not None
    ]
    manager_shadows = [
        event["payload"].get("manager_shadow") or {}
        for event in ready
        if (event["payload"].get("manager_shadow") or {}).get("status") == "ready"
    ]
    callback_calls = Counter()
    for shadow in manager_shadows:
        callback_calls.update(shadow.get("callback_calls") or {})
    manager_support = Counter()
    for event in ready:
        support = event["payload"].get("manager_support") or {}
        manager_support["supported_rosters"] += int(
            support.get("supported_rosters") or 0
        )
        manager_support["population_fallback_rosters"] += int(
            support.get("population_fallback_rosters") or 0
        )
        manager_support["total_opponent_rosters"] += int(
            support.get("total_opponent_rosters") or 0
        )
    practical_retained = sum(
        shadow.get("shadow_leader_in_terminal_practical_tier") is True
        for shadow in manager_shadows
    )
    exact_agreement = sum(
        shadow.get("shadow_leader_candidate_id")
        == shadow.get("terminal_leader_candidate_id")
        for shadow in manager_shadows
    )
    ready_fail_denominator = len(ready) + len(failed_events)
    metrics = {
        "sessions": len({row["session_id"] for row in sessions}),
        "ready_states": len(ready),
        "raw_ready_events": len(ready_events),
        "duplicate_ready_events": len(ready_events) - len(ready),
        "failed_events": len(failed_events),
        "discarded_events": len(discarded_events),
        "failure_rate": (
            len(failed_events) / ready_fail_denominator
            if ready_fail_denominator
            else None
        ),
        "duration_seconds": {
            "median": median(durations) if durations else None,
            "p95": _percentile(durations, 0.95),
            "maximum": max(durations) if durations else None,
        },
        "component_duration_seconds": {
            component: {
                "median": median(values) if values else None,
                "p95": _percentile(values, 0.95),
                "maximum": max(values) if values else None,
            }
            for component, values in component_durations.items()
        },
        "top_ten_capture_rate": _rate(
            event["payload"].get("top_ten_capture_complete") is True
            for event in ready
        ),
        "decision_inactive_rate": _rate(
            event["payload"].get("decision_active") is False
            for event in ready
        ),
        "candidate_return_coverage": (
            len(measured_candidates) / len(candidates) if candidates else None
        ),
        "outside_model_candidate_rate": _rate(
            candidate.get("timing_label") == "outside_model"
            for candidate in candidates
        ),
        "direct_support": {
            "minimum": min(direct_support) if direct_support else None,
            "median": median(direct_support) if direct_support else None,
        },
        "return_interval_median_width": (
            median(interval_widths) if interval_widths else None
        ),
        "manager_shadow_states": len(manager_shadows),
        "manager_exact_agreement_rate": (
            exact_agreement / len(manager_shadows) if manager_shadows else None
        ),
        "manager_practical_retention_rate": (
            practical_retained / len(manager_shadows)
            if manager_shadows
            else None
        ),
        "manager_callback_calls": dict(sorted(callback_calls.items())),
        "manager_roster_support": dict(manager_support),
        "rounds": dict(sorted(Counter(
            str(event["payload"].get("round")) for event in ready
        ).items())),
        "opponent_pick_gaps": dict(sorted(Counter(
            str(event["payload"].get("opponent_picks_until_next"))
            for event in ready
        ).items())),
    }
    development_gate = {
        "six_ready_states": metrics["ready_states"] >= 6,
        "complete_top_ten": metrics["top_ten_capture_rate"] == 1.0,
        "no_shadow_failures": metrics["failure_rate"] == 0.0,
        "manager_practical_retention": (
            metrics["manager_practical_retention_rate"] == 1.0
        ),
        "p95_duration_at_most_10_seconds": (
            metrics["duration_seconds"]["p95"] is not None
            and metrics["duration_seconds"]["p95"] <= 10.0
        ),
        "personalization_executed": (
            callback_calls["personalized"] > 0
        ),
        "population_fallback_executed": (
            callback_calls["population"] > 0
        ),
        "decision_inactive": metrics["decision_inactive_rate"] == 1.0,
    }
    development_gate["passes"] = all(development_gate.values())
    live_gate = {
        **{key: value for key, value in development_gate.items() if key != "six_ready_states"},
        "thirty_new_ready_states": metrics["ready_states"] >= 30,
    }
    live_gate["passes"] = all(
        value for key, value in live_gate.items() if key != "passes"
    )
    state_summaries = [
        _state_summary(event) for event in ready
    ]
    return {
        "audit_version": ALPHA_SHADOW_AUDIT_VERSION,
        "status": "research",
        "source": {
            "telemetry_path": str(telemetry_path),
            "telemetry_sha256": sha256_file(telemetry_path),
            "draft_id": draft_id,
            "session_id": session_id,
        },
        "metrics": metrics,
        "development_gate": development_gate,
        "live_evidence_gate": live_gate,
        "artifact_versions": {
            "survival": sorted({
                str(event["payload"].get("survival_manifest_hash"))
                for event in ready
            }),
            "manager": sorted({
                str(event["payload"].get("manager_manifest_hash"))
                for event in ready
            }),
            "manager_blends": sorted({
                event["payload"].get("manager_probability_blend")
                for event in ready
                if event["payload"].get("manager_probability_blend") is not None
            }),
        },
        "states": state_summaries,
        "limitations": [
            "shadow events do not contain realized draft outcomes",
            "20-rollout manager results are telemetry, not release evidence",
            "live integration requires at least 30 new states",
        ],
    }


def write_alpha_shadow_audit(report, output_path):
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError(f"alpha shadow audit is immutable: {output_path}")
    body = dict(report)
    body["sha256"] = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    output_path.chmod(0o444)
    return body


def _state_summary(event):
    payload = event["payload"]
    manager = payload.get("manager_shadow") or {}
    return {
        "session_id": event["session_id"],
        "draft_id": event["draft_id"],
        "pick_no": event["pick_no"],
        "state_signature": payload.get("state_signature"),
        "round": payload.get("round"),
        "opponent_picks_until_next": payload.get(
            "opponent_picks_until_next"
        ),
        "duration_seconds": event["duration_seconds"],
        "terminal_recommendation_id": payload.get(
            "terminal_recommendation_id"
        ),
        "shadow_leader_candidate_id": manager.get(
            "shadow_leader_candidate_id"
        ),
        "shadow_leader_in_terminal_practical_tier": manager.get(
            "shadow_leader_in_terminal_practical_tier"
        ),
        "top_ten_capture_complete": payload.get(
            "top_ten_capture_complete"
        ),
        "manager_support": payload.get("manager_support"),
    }


def _percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _rate(values):
    values = list(values)
    return sum(values) / len(values) if values else None
