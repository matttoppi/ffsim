"""Small second-pass metrics for a completed synthetic audit batch."""

from collections import Counter, defaultdict
import json
import sys

from audit_synthetic_batch import load_batch, percentile


def summary(values):
    values = sorted(float(value) for value in values if value is not None)
    return {
        "n": len(values),
        "median": percentile(values, 0.5),
        "p10": percentile(values, 0.1),
        "p90": percentile(values, 0.9),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def main(batch_id):
    sessions, configs, events = load_batch(batch_id)
    ready = []
    by_session = {}
    outcomes = []
    for session in sessions:
        session_id = session["session_id"]
        if session["status"] != "completed":
            continue
        config = configs[session_id]["scenario"]
        rows = sorted(
            (
                event for event in events[session_id]
                if event["event_type"] == "recommendation"
                and event["stage"] == "ready"
            ),
            key=lambda event: event["pick_no"],
        )
        by_session[session_id] = rows
        for event in rows:
            payload = event["payload"]
            candidates = payload["candidates"] + payload.get("screened_candidates", [])
            candidate_by_id = {str(row["player_id"]): row for row in candidates}
            head = candidate_by_id[str(payload["recommended_candidate_id"])]
            delta = payload["paired_value_delta_vs_runner_up"]
            ready.append({
                "session": session_id,
                "draft": session["draft_id"],
                "teams": int(config["teams"]),
                "slot": int(config["user_slot"]),
                "round": (int(event["pick_no"]) - 1) // int(config["teams"]) + 1,
                "pick": int(event["pick_no"]),
                "status": payload["decision_status"],
                "co": len(payload["co_leader_candidate_ids"]),
                "head": head,
                "payload": payload,
                "edge": float(delta["projected_value_delta"]),
                "lower": float(delta["interval"][0]),
                "upper": float(delta["interval"][1]),
                "better": float(delta["better_continuation_probability"]),
                "worse": float(delta["worse_continuation_probability"]),
            })
        outcome = next(
            (
                event["payload"] for event in events[session_id]
                if event["event_type"] == "completed_draft_simulation"
            ),
            None,
        )
        if outcome:
            rosters = outcome["rosters"]
            user = next(row for row in rosters if row["is_user"])
            outcomes.append({
                "teams": int(config["teams"]),
                "expected_points_rank": 1 + sum(
                    row["expected_points"] > user["expected_points"] for row in rosters
                ),
                "expected_wins_rank": 1 + sum(
                    row["expected_wins"] > user["expected_wins"] for row in rosters
                ),
                "championship_rank": 1 + sum(
                    row["championship_probability"] > user["championship_probability"]
                    for row in rosters
                ),
                "expected_points": user["expected_points"],
                "expected_wins": user["expected_wins"],
                "championship_probability": user["championship_probability"],
            })

    toss = [row for row in ready if row["status"] == "toss_up"]
    clear = [row for row in ready if row["status"] == "clear_leader"]
    co_by_round = defaultdict(list)
    for row in ready:
        co_by_round[(row["teams"], row["round"])].append(row["co"])

    adjacency = []
    for session_id, rows in by_session.items():
        for old, new in zip(rows, rows[1:]):
            if int(new["pick_no"]) != int(old["pick_no"]) + 1:
                continue
            old_payload, new_payload = old["payload"], new["payload"]
            old_rows = old_payload["candidates"] + old_payload.get("screened_candidates", [])
            new_rows = new_payload["candidates"] + new_payload.get("screened_candidates", [])
            old_by_id = {str(row["player_id"]): row for row in old_rows}
            new_by_id = {str(row["player_id"]): row for row in new_rows}
            old_runner = str(old_payload["runner_up_candidate_id"])
            new_head = str(new_payload["recommended_candidate_id"])
            adjacency.append({
                "session": session_id,
                "from_pick": old["pick_no"],
                "to_pick": new["pick_no"],
                "old_head": old_by_id[str(old_payload["recommended_candidate_id"])]["name"],
                "old_runner": old_by_id[old_runner]["name"],
                "old_runner_position": old_by_id[old_runner]["position"],
                "old_status": old_payload["decision_status"],
                "old_edge": old_payload["paired_value_delta_vs_runner_up"]["projected_value_delta"],
                "old_runner_reconsidered": old_runner in new_by_id,
                "new_head": new_by_id[new_head]["name"],
                "new_head_position": new_by_id[new_head]["position"],
                "new_status": new_payload["decision_status"],
                "new_edge": new_payload["paired_value_delta_vs_runner_up"]["projected_value_delta"],
                "runner_became_head": old_runner == new_head,
            })

    vona_headlines = [
        row for row in ready
        if row["head"]["position"] in ("K", "DEF")
        and (row["head"].get("value_over_next_alternative") or 0) > 1
    ]
    later_rows = [
        row for row in ready if row["head"].get("later_alternatives")
    ]
    output = {
        "decisions": len(ready),
        "tie": {
            "tossups": len(toss),
            "negative_edge": sum(row["edge"] < 0 for row in toss),
            "edge_at_most_minus_point_1": sum(row["edge"] <= -0.1 for row in toss),
            "interval_entirely_below_zero": sum(row["upper"] < 0 for row in toss),
            "absolute_edge_over_1": sum(abs(row["edge"]) > 1 for row in toss),
            "absolute_edge_over_5": sum(abs(row["edge"]) > 5 for row in toss),
            "co_leaders_at_least_20": sum(row["co"] >= 20 for row in toss),
            "edge": summary(row["edge"] for row in toss),
            "absolute_edge": summary(abs(row["edge"]) for row in toss),
            "lower": summary(row["lower"] for row in toss),
            "co_leaders": summary(row["co"] for row in toss),
            "largest": [
                {
                    key: row[key] for key in (
                        "session", "draft", "pick", "round", "teams", "status",
                        "co", "edge", "lower", "upper", "better",
                    )
                } | {
                    "head": row["head"]["name"],
                    "position": row["head"]["position"],
                    "runner": row["payload"].get("runner_up_candidate_id"),
                }
                for row in sorted(toss, key=lambda row: abs(row["edge"]), reverse=True)[:20]
            ],
        },
        "clear": {
            "count": len(clear),
            "edge": summary(row["edge"] for row in clear),
            "lower": summary(row["lower"] for row in clear),
            "lower_point_1_to_point_15": sum(0.1 < row["lower"] <= 0.15 for row in clear),
            "better_below_half": sum(row["better"] < 0.5 for row in clear),
            "high_survival": sum((row["head"].get("survives_to_next_pick") or 0) >= 0.8 for row in clear),
            "better_below_half_examples": [
                {
                    "session": row["session"],
                    "draft": row["draft"],
                    "pick": row["pick"],
                    "head": row["head"]["name"],
                    "edge": row["edge"],
                    "lower": row["lower"],
                    "better": row["better"],
                }
                for row in sorted(clear, key=lambda row: row["better"])[:10]
            ],
        },
        "co_leaders_by_round": {
            f"{teams}t_r{round_no}": summary(values)
            for (teams, round_no), values in sorted(co_by_round.items())
        },
        "explanation": {
            "headline_k_def_vona_over_1": len(vona_headlines),
            "headline_k_def_vona_over_1_by_position": Counter(
                row["head"]["position"] for row in vona_headlines
            ),
            "clear_with_survival_over_point_05": sum(
                (row["head"].get("survives_to_next_pick") or 0) > 0.05 for row in clear
            ),
            "headline_with_later_alternatives": len(later_rows),
            "later_probability_sum": summary(
                sum(float(item.get("probability") or 0) for item in row["head"]["later_alternatives"])
                + float(row["head"].get("later_alternative_other_probability") or 0)
                for row in later_rows
            ),
        },
        "adjacent": {
            "count": len(adjacency),
            "old_runner_reconsidered": sum(row["old_runner_reconsidered"] for row in adjacency),
            "runner_became_head": sum(row["runner_became_head"] for row in adjacency),
            "position_switched_from_runner": sum(
                row["old_runner_position"] != row["new_head_position"] for row in adjacency
            ),
            "examples": adjacency[:30],
        },
        "outcomes": {
            "n": len(outcomes),
            "expected_points_rank": summary(row["expected_points_rank"] for row in outcomes),
            "expected_wins_rank": summary(row["expected_wins_rank"] for row in outcomes),
            "championship_rank": summary(row["championship_rank"] for row in outcomes),
            "first_expected_points": sum(row["expected_points_rank"] == 1 for row in outcomes),
            "first_championship": sum(row["championship_rank"] == 1 for row in outcomes),
        },
    }
    print(json.dumps(output, indent=2, default=dict))


if __name__ == "__main__":
    main(sys.argv[1])
