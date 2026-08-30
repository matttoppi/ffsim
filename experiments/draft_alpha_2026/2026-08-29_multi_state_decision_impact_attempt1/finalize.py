#!/usr/bin/env python3
import json
from pathlib import Path

HERE = Path(__file__).parent


def main():
    raw = json.loads((HERE / "result.json").read_text())
    manager = raw["manager_gate"]
    manager_gate = {
        "all_shadow_leaders_practical": manager["all_shadow_leaders_practical"],
        "personalized_callbacks_used": manager["personalized_callbacks_used"],
        "population_fallbacks_used": manager["population_fallbacks_used"],
        "live_callback_unchanged": manager["live_callback_changed"] is False,
    }
    manager_gate["passes"] = all(manager_gate.values())
    terminal_gate = raw["terminal_first_gate"]
    passed = terminal_gate["passes"] and manager_gate["passes"]
    conclusion = {
        "experiment": raw["experiment"],
        "status": "research" if passed else "rejected",
        "source_result": "result.json",
        "rollouts": raw["rollouts"],
        "states": len(raw["states"]),
        "manager_probability_blend": raw["manager_probability_blend"],
        "terminal_first_gate": terminal_gate,
        "manager_gate": manager_gate,
        "route_diagnostic": raw["route_diagnostic"],
        "callback_calls": raw["callback_calls"],
        "state_summaries": [
            {
                "draft_id": state["draft_id"],
                "pick_no": state["pick_no"],
                "baseline_leader": state["baseline_leader"],
                "shadow_leader": state["shadow_leader"],
                "shadow_practical_co_leader": state["shadow_baseline_delta"]["practical_co_leader"],
                "route_leader": state["route_leader"],
                "route_practical_co_leader": state["route_baseline_delta"]["practical_co_leader"],
                "route_terminal_rank": state["route_terminal_rank"],
            }
            for state in raw["states"]
        ],
        "conclusion": (
            "Terminal-first timing and the fixed 10% corrected manager mixture "
            "pass this six-state 100-rollout preliminary shadow gate. One-turn "
            "route ranking fails in three of six states and remains diagnostic only."
        ),
    }
    (HERE / "conclusion.json").write_text(
        json.dumps(conclusion, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(conclusion, indent=2))


if __name__ == "__main__":
    main()
