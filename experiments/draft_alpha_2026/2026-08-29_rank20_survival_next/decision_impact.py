#!/usr/bin/env python3
import json
from pathlib import Path

from ffsim.draft_intel.decision import PRACTICAL_TIE_POINTS
from ffsim.draft_intel.live import evaluate_live_candidates
from ffsim.draft_intel.timing_report import build_cached_timing_context

ROOT = Path(__file__).parents[3]
HERE = Path(__file__).parent
CORPUS = ROOT / "experiments/draft_alpha_2026/2026-08-29_multi_state_corpus/corpus.json"
TERMINAL = ROOT / "experiments/draft_alpha_2026/2026-08-29_multi_state_decision_impact_attempt2/conclusion.json"


def main():
    corpus = json.loads(CORPUS.read_text())
    terminal = json.loads(TERMINAL.read_text())
    shadow = json.loads((HERE / "shadow-result.json").read_text())
    baseline_by_draft = {
        state["draft_id"]: state["baseline_leader"]
        for state in terminal["state_summaries"]
    }
    route_by_draft = {
        state["draft_id"]: state["route_leader"]
        for state in shadow["reports"]
    }
    states = []
    for state_record in corpus["states"]:
        draft_id = state_record["draft_id"]
        baseline_leader = baseline_by_draft[draft_id]
        route_leader = route_by_draft[draft_id]
        context = build_cached_timing_context(
            ROOT / state_record["config"],
            ROOT / state_record["league_cache"],
            roster_id=state_record["roster_id"],
            draft_cache=ROOT / state_record["draft_cache"],
            world_count=20,
        )
        candidate_ids = tuple(dict.fromkeys((baseline_leader, route_leader)))
        evaluation = evaluate_live_candidates(
            context["prepared"],
            context["state"],
            300,
            candidate_ids,
            survival_ids=candidate_ids,
        )
        delta = evaluation.paired_value_delta(
            baseline_leader, route_leader
        )
        practical = delta.interval[0] <= PRACTICAL_TIE_POINTS
        states.append({
            "draft_id": draft_id,
            "pick_no": state_record["pick_no"],
            "baseline_leader": baseline_leader,
            "rank20_route_leader": route_leader,
            "same_leader": baseline_leader == route_leader,
            "baseline_minus_route": {
                "estimate": delta.projected_value_delta,
                "standard_error": delta.standard_error,
                "interval": list(delta.interval),
            },
            "route_is_terminal_practical_co_leader": practical,
        })
    passed = all(
        state["route_is_terminal_practical_co_leader"] for state in states
    )
    result = {
        "experiment": "rank-20 route versus terminal paired check",
        "status": "research" if passed else "rejected",
        "rollouts": 300,
        "practical_tie_points": PRACTICAL_TIE_POINTS,
        "states": states,
        "gate": {"passes": passed},
        "limitations": [
            "route ranking remains diagnostic",
            "cached mock states only",
            "no manager mixture or live ranking change",
        ],
    }
    (HERE / "decision-impact-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
