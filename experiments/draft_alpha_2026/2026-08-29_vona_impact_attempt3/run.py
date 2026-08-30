#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).parents[3]
EXPERIMENT = Path(__file__).parent


def main():
    report = json.loads((
        ROOT
        / "experiments/draft_alpha_2026/2026-08-29_top_ten_capture_attempt2/report.json"
    ).read_text())
    terminal = json.loads((
        ROOT
        / "experiments/draft_alpha_2026/2026-08-29_vona_impact_attempt2/result.json"
    ).read_text())
    terminal_leader = terminal["terminal_leader"]
    leader_row = next(
        row for row in report["players"] if row["player_id"] == terminal_leader
    )
    branch = report["candidate_branches"][terminal_leader]
    alternatives = []
    for player in branch["later_players"]:
        probability = player["probability"]
        label = (
            "safe_to_wait"
            if probability is not None and probability >= 0.70
            else "urgent"
            if probability is not None and probability <= 0.30
            else "uncertain"
        )
        alternatives.append({
            "player_id": player["player_id"],
            "market_rank": player["market_rank"],
            "eligible_next_turn": player["eligible_next_turn"],
            "return_probability": probability,
            "interval_95": player["interval_95"],
            "timing_label": label,
        })
    outside_top_ten_unscored = (
        leader_row["market_rank"] > 10
        and leader_row["return_probability"] is None
        and leader_row["support_status"] == "outside_top_ten"
    )
    recommendation_unchanged = terminal_leader == terminal["terminal_ranking"][0]["player_id"]
    passed = (
        recommendation_unchanged
        and outside_top_ten_unscored
        and branch["top_ten_capture_complete"]
        and report["decision_active"] is False
    )
    result = {
        "experiment": "terminal-first hierarchical timing overlay",
        "status": "research" if passed else "rejected",
        "recommendation": terminal_leader,
        "recommendation_source": "300-rollout completed-roster value",
        "recommendation_changed_by_survival": False,
        "recommended_player_market_rank": leader_row["market_rank"],
        "recommended_player_return_probability": leader_row["return_probability"],
        "shadow_alternatives": alternatives,
        "gate": {
            "passes": passed,
            "recommendation_unchanged": recommendation_unchanged,
            "outside_top_ten_unscored": outside_top_ten_unscored,
            "complete_top_ten_capture": branch["top_ten_capture_complete"],
            "decision_active": report["decision_active"],
        },
        "conclusion": (
            "Use hierarchical survival as explanation-only shadow evidence. "
            "Do not rank candidates by one-turn route value."
        ),
    }
    (EXPERIMENT / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "recommendation": result["recommendation"],
        "market_rank": result["recommended_player_market_rank"],
        "gate": result["gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
