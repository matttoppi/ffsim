#!/usr/bin/env python3
import json
from pathlib import Path

from scipy.stats import spearmanr

from ffsim.draft_intel.decision import PRACTICAL_TIE_POINTS, rank_candidates
from ffsim.draft_intel.live import evaluate_live_candidates
from ffsim.draft_intel.timing_report import (
    build_cached_timing_context,
    load_timing_report,
)

ROOT = Path(__file__).parents[3]
EXPERIMENT = Path(__file__).parent


def main():
    report = load_timing_report(
        ROOT
        / "experiments/draft_alpha_2026/2026-08-29_top_ten_capture_attempt2/report.json"
    )
    context = build_cached_timing_context(
        EXPERIMENT.parent
        / "2026-08-29_top_ten_capture_attempt2/config.json",
        ROOT / "data/cache/league_1389391547115511808.json",
        roster_id=1,
        draft_cache=ROOT / "data/cache/mock_draft_1393656492011315200.json",
        world_count=20,
    )
    route_rows = [
        row for row in report["players"] if row["take_now_route_value"] is not None
    ]
    route_rows.sort(
        key=lambda row: (-row["take_now_route_value"], row["player_id"])
    )
    candidate_ids = tuple(row["player_id"] for row in route_rows)
    evaluation = evaluate_live_candidates(
        context["prepared"],
        context["state"],
        300,
        candidate_ids,
        survival_ids=candidate_ids,
    )
    terminal = rank_candidates(evaluation)
    terminal_by_id = {candidate.candidate_id: candidate for candidate in terminal}
    route_leader = route_rows[0]["player_id"]
    terminal_leader = terminal[0].candidate_id
    delta = evaluation.paired_value_delta(terminal_leader, route_leader)
    practical_co_leader = delta.interval[0] <= PRACTICAL_TIE_POINTS
    route_values = [
        next(row["take_now_route_value"] for row in route_rows if row["player_id"] == candidate.candidate_id)
        for candidate in terminal
    ]
    terminal_values = [candidate.projected_roster_value for candidate in terminal]
    correlation = float(spearmanr(route_values, terminal_values).statistic)
    complete_capture = all(
        branch["top_ten_capture_complete"]
        for branch in report["candidate_branches"].values()
    )
    passed = practical_co_leader and complete_capture
    result = {
        "experiment": "hierarchical one-turn VONA versus completed-roster value",
        "status": "research" if passed else "rejected",
        "draft_id": report["draft_id"],
        "pick_no": report["pick_no"],
        "rollouts": 300,
        "season_worlds_per_rollout": evaluation.season_worlds_per_rollout,
        "route_leader": route_leader,
        "terminal_leader": terminal_leader,
        "route_terminal_rank": next(
            index for index, candidate in enumerate(terminal, 1)
            if candidate.candidate_id == route_leader
        ),
        "route_terminal_value": terminal_by_id[route_leader].projected_roster_value,
        "terminal_leader_value": terminal[0].projected_roster_value,
        "paired_terminal_leader_minus_route": {
            "estimate": delta.projected_value_delta,
            "standard_error": delta.standard_error,
            "interval": list(delta.interval),
        },
        "spearman_route_vs_terminal": correlation,
        "gate": {
            "passes": passed,
            "practical_co_leader": practical_co_leader,
            "practical_tie_points": PRACTICAL_TIE_POINTS,
            "complete_top_ten_capture": complete_capture,
        },
        "terminal_ranking": [
            {
                "rank": index,
                "player_id": candidate.candidate_id,
                "projected_roster_value": candidate.projected_roster_value,
                "route_value": next(
                    row["take_now_route_value"]
                    for row in route_rows
                    if row["player_id"] == candidate.candidate_id
                ),
                "vona": (
                    candidate.opportunity_cost.value_over_next_alternative
                    if candidate.opportunity_cost is not None
                    else None
                ),
            }
            for index, candidate in enumerate(terminal, 1)
        ],
        "limitations": [
            "one cached mock state only",
            "hierarchical route remains shadow-only",
            "full completed-roster value remains the recommendation objective",
        ],
    }
    (EXPERIMENT / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "route_leader": route_leader,
        "terminal_leader": terminal_leader,
        "route_terminal_rank": result["route_terminal_rank"],
        "paired_delta": result["paired_terminal_leader_minus_route"],
        "spearman": correlation,
        "gate": result["gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
