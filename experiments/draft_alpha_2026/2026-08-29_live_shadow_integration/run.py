#!/usr/bin/env python3
import hashlib
import json
import time
from pathlib import Path

from ffsim.draft_intel.alpha_shadow import load_default_alpha_shadow_collector
from ffsim.draft_intel.live import (
    evaluate_live_candidates,
    live_candidate_pool,
    live_recommendation_payload,
)
from ffsim.draft_intel.timing_report import build_cached_timing_context
from ffsim.historical_sleeper.hdvn_snapshot import canonical_json

ROOT = Path(__file__).parents[3]
HERE = Path(__file__).parent


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def main():
    context = build_cached_timing_context(
        ROOT / "experiments/draft_alpha_2026/2026-08-29_top_ten_capture_attempt2/config.json",
        ROOT / "data/cache/league_1389391547115511808.json",
        roster_id=1,
        draft_cache=ROOT / "data/cache/mock_draft_1393656492011315200.json",
        world_count=20,
    )
    candidate_ids = tuple(
        live_candidate_pool(context["prepared"], context["state"], 12)
    )
    evaluation = evaluate_live_candidates(
        context["prepared"],
        context["state"],
        20,
        candidate_ids,
        survival_ids=candidate_ids,
    )
    recommendation = live_recommendation_payload(
        context["prepared"],
        context["state"],
        [evaluation],
        len(candidate_ids),
    )
    before = digest(recommendation)
    collector, error = load_default_alpha_shadow_collector()
    if collector is None:
        raise RuntimeError(error)
    started = time.monotonic()
    shadow = collector.collect(
        context["prepared"], context["state"], recommendation
    )
    duration = time.monotonic() - started
    after = digest(recommendation)
    manager = shadow["manager_shadow"]
    passed = (
        before == after
        and shadow["decision_active"] is False
        and shadow["top_ten_capture_complete"]
        and manager["status"] == "ready"
        and shadow["manager_support"]["total_opponent_rosters"] == 11
    )
    result = {
        "experiment": "cached live alpha shadow integration smoke",
        "status": "research" if passed else "rejected",
        "draft_id": context["state"].draft_id,
        "pick_no": context["state"].current_pick_no,
        "baseline_rollouts": 20,
        "duration_seconds": duration,
        "recommendation_hash_before": before,
        "recommendation_hash_after": after,
        "recommendation_unchanged": before == after,
        "terminal_recommendation_id": shadow["terminal_recommendation_id"],
        "top_ten_capture_complete": shadow["top_ten_capture_complete"],
        "candidate_count": len(shadow["candidates"]),
        "next_turn_count": len(shadow["recommended_branch_next_turn"]),
        "manager_support": shadow["manager_support"],
        "manager_shadow": manager,
        "gate": {"passes": passed},
        "limitations": [
            "cached mock state",
            "20-rollout live collector budget",
            "shadow output does not alter the recommendation",
        ],
    }
    (HERE / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
