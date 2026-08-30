"""Read-only forensic summary for one synthetic-draft telemetry batch.

Usage:
    .venv/bin/python tools/audit_synthetic_batch.py BATCH_ID

Run only after the batch has finished; large JSON scans can contend with the
SQLite writer while synthetic drafts are still being recorded.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sqlite3
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[1]
TELEMETRY = ROOT / "data/cache/draft_intel/telemetry.sqlite3"
HISTORY = ROOT / "data/cache/draft_intel/history.sqlite3"
PLAYERS = ROOT / "data/cache/players.json"
SLEEPER_PLAYERS = ROOT / "data/cache/sleeper_players.json"


def connect_readonly(path: Path):
    database = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    return database


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def stats(values):
    values = [float(value) for value in values if value is not None]
    return {
        "n": len(values),
        "median": median(values) if values else None,
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values) if values else None,
        "over_10": sum(value > 10 for value in values),
        "over_20": sum(value > 20 for value in values),
    }


def phase(round_no, rounds):
    if round_no <= math.ceil(rounds / 3):
        return "early"
    if round_no <= math.ceil(2 * rounds / 3):
        return "middle"
    return "late"


def roster_counts(picks, roster_id, before=None):
    return Counter(
        pick["position"]
        for pick in picks
        if pick["roster_id"] == roster_id
        and (before is None or pick["pick_no"] < before)
    )


def skill_starters_filled(counts, flexes):
    return (
        counts["RB"] >= 2
        and counts["WR"] >= 2
        and counts["TE"] >= 1
        and counts["RB"] + counts["WR"] + counts["TE"] >= 5 + flexes
    )


def dedicated_core_filled(counts):
    return (
        counts["QB"] >= 1
        and counts["RB"] >= 2
        and counts["WR"] >= 2
        and counts["TE"] >= 1
    )


def starter_need_count(counts, flexes):
    needs = sum(max(target - counts[position], 0) for position, target in (
        ("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1), ("K", 1), ("DEF", 1),
    ))
    surplus = sum(max(counts[position] - target, 0) for position, target in (
        ("RB", 2), ("WR", 2), ("TE", 1),
    ))
    return needs + max(flexes - surplus, 0)


def calibration(rows):
    if not rows:
        return {"n": 0}
    bins = []
    for lower, upper in ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)):
        bucket = [
            row for row in rows
            if lower <= row["predicted"] < upper
            or upper == 1.0 and row["predicted"] == 1.0
        ]
        if bucket:
            bins.append({
                "range": f"{lower:.1f}-{lower + 0.2:.1f}",
                "n": len(bucket),
                "predicted": mean(row["predicted"] for row in bucket),
                "realized": mean(row["realized"] for row in bucket),
            })
    return {
        "n": len(rows),
        "brier": mean((row["predicted"] - row["realized"]) ** 2 for row in rows),
        "mean_predicted": mean(row["predicted"] for row in rows),
        "mean_realized": mean(row["realized"] for row in rows),
        "bins": bins,
    }


def load_batch(batch_id):
    database = connect_readonly(TELEMETRY)
    sessions = database.execute(
        "SELECT * FROM live_draft_sessions "
        "WHERE json_extract(config_json, '$.batch_id')=? ORDER BY started_at",
        (batch_id,),
    ).fetchall()
    if not sessions:
        raise SystemExit(f"Unknown batch: {batch_id}")

    configs = {row["session_id"]: json.loads(row["config_json"]) for row in sessions}
    events = defaultdict(list)
    placeholders = ",".join("?" for _ in sessions)
    for row in database.execute(
        f"SELECT * FROM live_draft_events WHERE session_id IN ({placeholders}) ORDER BY id",
        tuple(configs),
    ):
        events[row["session_id"]].append({
            **dict(row),
            "payload": json.loads(row["payload_json"]),
        })
    database.close()
    return sessions, configs, events


def market_adp(snapshot_ids):
    database = connect_readonly(HISTORY)
    result = {}
    for snapshot_id in snapshot_ids:
        result[snapshot_id] = {
            row["canonical_player_id"].removeprefix("sleeper:"): row["adp"]
            for row in database.execute(
                "SELECT canonical_player_id, adp FROM market_observations "
                "WHERE snapshot_id=?",
                (snapshot_id,),
            )
        }
    database.close()
    return result


def human_benchmark():
    """Position-only exact/near comparison from local human PPR drafts."""
    database = connect_readonly(HISTORY)
    drafts = {}
    for row in database.execute(
        "SELECT draft_id, season, team_count, rounds, roster_slots_json "
        "FROM historical_drafts WHERE included=1 AND status='complete' "
        "AND draft_type='snake' AND scoring_type='ppr' AND team_count IN (10,12)"
    ):
        slots = dict(json.loads(row["roster_slots_json"]))
        teams = int(row["team_count"])
        expected = {
            "qb": 1, "rb": 2, "wr": 2, "te": 1,
            "flex": 2 if teams == 10 else 1, "k": 1, "def": 1,
        }
        if {key: value for key, value in slots.items() if key != "bn" and value} != expected:
            continue
        if not 14 <= int(row["rounds"]) <= 17:
            continue
        exact = (
            int(row["rounds"]) == (17 if teams == 10 else 15)
            and slots.get("bn") == (7 if teams == 10 else 6)
        )
        drafts[row["draft_id"]] = {**dict(row), "slots": slots, "exact": exact}

    picks = defaultdict(list)
    if drafts:
        placeholders = ",".join("?" for _ in drafts)
        for row in database.execute(
            f"SELECT * FROM historical_picks WHERE draft_id IN ({placeholders}) "
            "AND COALESCE(is_keeper,0)=0 AND roster_id IS NOT NULL ORDER BY draft_id,pick_no",
            tuple(drafts),
        ):
            picks[(row["draft_id"], row["roster_id"])].append(dict(row))
    database.close()

    positions = ("QB", "RB", "WR", "TE", "K", "DEF")

    def summarize(teams, exact):
        draft_ids = {
            draft_id for draft_id, draft in drafts.items()
            if draft["team_count"] == teams and (not exact or draft["exact"])
        }
        roster_rows, phase_counts = [], Counter()
        for (draft_id, _), rows in picks.items():
            if draft_id not in draft_ids:
                continue
            counts, running = Counter(row["position"] for row in rows), Counter()
            dedicated_fill = skill_fill = None
            backup_before_holes = k_def_before_core = 0
            for row in rows:
                position = row["position"]
                if position in ("QB", "TE") and running[position] >= 1 and (
                    running["RB"] < 2 or running["WR"] < 2
                ):
                    backup_before_holes += 1
                if position in ("K", "DEF") and not dedicated_core_filled(running):
                    k_def_before_core += 1
                running[position] += 1
                if dedicated_fill is None and dedicated_core_filled(running):
                    dedicated_fill = row["round"]
                if skill_fill is None and dedicated_core_filled(running) and skill_starters_filled(
                    running, 2 if teams == 10 else 1
                ):
                    skill_fill = row["round"]
                band = "r1_4" if row["round"] <= 4 else "r5_10" if row["round"] <= 10 else "r11_13" if row["round"] <= 13 else "r14_plus"
                phase_counts[(band, position)] += 1
            roster_rows.append({
                "positions": counts,
                "first_round": {
                    position: next((row["round"] for row in rows if row["position"] == position), None)
                    for position in positions
                },
                "dedicated_fill": dedicated_fill,
                "skill_fill": skill_fill,
                "backup_before_holes": backup_before_holes,
                "k_def_before_core": k_def_before_core,
                "k_def_by_10": any(
                    row["position"] in ("K", "DEF") and row["round"] <= 10
                    for row in rows
                ),
            })

        def round_stats(key, position=None):
            values = [
                row[key][position] if position else row[key]
                for row in roster_rows
                if (row[key][position] if position else row[key]) is not None
            ]
            return {
                "median": median(values) if values else None,
                "p90": percentile(values, 0.9),
            }

        return {
            "drafts": len(draft_ids),
            "draft_ids": sorted(draft_ids),
            "rosters": len(roster_rows),
            "final_position_means": {
                position: mean(row["positions"].get(position, 0) for row in roster_rows)
                if roster_rows else None
                for position in positions
            },
            "final_position_distributions": {
                position: Counter(row["positions"].get(position, 0) for row in roster_rows)
                for position in positions
            },
            "first_round": {position: round_stats("first_round", position) for position in positions},
            "dedicated_core_fill_round": round_stats("dedicated_fill"),
            "complete_skill_fill_round": round_stats("skill_fill"),
            "rosters_with_backup_before_rb_wr": sum(row["backup_before_holes"] > 0 for row in roster_rows),
            "rosters_with_k_def_before_core": sum(row["k_def_before_core"] > 0 for row in roster_rows),
            "rosters_with_k_def_by_round_10": sum(row["k_def_by_10"] for row in roster_rows),
            "phase_position_share": {
                band: {
                    position: phase_counts[(band, position)] / max(
                        1, sum(phase_counts[(band, value)] for value in positions)
                    )
                    for position in positions
                }
                for band in ("r1_4", "r5_10", "r11_13", "r14_plus")
            },
        }

    return {
        str(teams): {
            "exact": summarize(teams, True),
            "near": summarize(teams, False),
        }
        for teams in (10, 12)
    }


def audit(batch_id, *, details=False):
    sessions, configs, events = load_batch(batch_id)
    player_rows = json.loads(PLAYERS.read_text())
    players = {str(row["sleeper_id"]): row for row in player_rows}
    sleeper_players = json.loads(SLEEPER_PLAYERS.read_text())
    adp_by_snapshot = market_adp({
        str(config["prepared"]["market_snapshot_id"]) for config in configs.values()
    })
    human = human_benchmark()

    integrity = []
    decisions = []
    calibration_rows = []
    opponent_rows = []
    roster_rows = []
    continuity = []
    explanation_errors = []
    scenario_counts = Counter()

    for session in sessions:
        session_id = session["session_id"]
        config = configs[session_id]
        scenario = config["scenario"]
        teams, rounds = int(scenario["teams"]), int(scenario["rounds"])
        user_roster_id = int(scenario["user_roster_id"])
        scenario_counts[(scenario["template_league_id"], scenario["user_slot"])] += 1
        session_events = events[session_id]
        picks = [event["payload"] for event in session_events if event["event_type"] == "pick"]
        picks.sort(key=lambda pick: pick["pick_no"])
        ready_events = [
            event for event in session_events
            if event["event_type"] == "recommendation" and event["stage"] == "ready"
        ]
        screen_by_pick = {
            event["pick_no"]: event
            for event in session_events
            if event["event_type"] == "recommendation" and event["stage"] == "screen"
        }
        counts = Counter(event["event_type"] for event in session_events)
        board_count_mismatches = sum(
            len({
                str(row["player_id"])
                for row in payload.get("candidates", []) + payload.get("screened_candidates", [])
            }) != payload.get("candidates_evaluated")
            for payload in (event["payload"] for event in ready_events)
        )
        integrity.append({
            "session_id": session_id,
            "draft_id": session["draft_id"],
            "status": session["status"],
            "picks": counts["pick"],
            "screen": sum(event["event_type"] == "recommendation" and event["stage"] == "screen" for event in session_events),
            "ready": len(ready_events),
            "summaries": counts["synthetic_summary"],
            "outcomes": counts["completed_draft_simulation"],
            "errors": counts["synthetic_error"],
            "error_payloads": [
                event["payload"] for event in session_events
                if event["event_type"] == "synthetic_error"
            ],
            "user_picks": sum(pick.get("source") == "synthetic_recommendation" for pick in picks),
            "pick_sequence_ok": [pick["pick_no"] for pick in picks] == list(range(1, teams * rounds + 1)),
            "unique_players": len({str(pick["player_id"]) for pick in picks}) == len(picks),
            "board_count_mismatches": board_count_mismatches,
            "wrong_engine_versions": sum(event["payload"].get("decision_engine_version") != 7 for event in ready_events),
            "policy_mismatches": sum(
                pick.get("source") == "synthetic_recommendation"
                and (
                    not pick.get("followed_recommendation")
                    or pick.get("player_id") != pick.get("recommended_candidate_id")
                )
                for pick in picks
            ),
        })
        if session["status"] != "completed":
            continue

        ready_events.sort(key=lambda event: event["pick_no"])
        for index, event in enumerate(ready_events):
            payload = event["payload"]
            pick_no = int(event["pick_no"])
            round_no = (pick_no - 1) // teams + 1
            before = roster_counts(picks, user_roster_id, pick_no)
            all_candidates = payload.get("candidates", []) + payload.get("screened_candidates", [])
            by_id = {str(row["player_id"]): row for row in all_candidates}
            recommended_id = str(payload["recommended_candidate_id"])
            if recommended_id not in by_id:
                explanation_errors.append((session_id, pick_no, "headline_missing"))
                continue
            head = by_id[recommended_id]
            runner_id = str(payload["runner_up_candidate_id"]) if payload.get("runner_up_candidate_id") is not None else None
            runner = by_id.get(runner_id)
            tags = []
            position = head.get("position")
            survival = head.get("survives_to_next_pick")
            flexes = scenario["roster_positions"].count("FLEX")
            remaining_user_picks = rounds - sum(before.values())
            must_fill = remaining_user_picks <= starter_need_count(before, flexes)
            reach_rounds = (
                (float(head["adp"]) - pick_no) / teams if head.get("adp") is not None else None
            )
            next_turn = head.get("next_turn_pick_no") or payload.get("next_user_pick_no")
            if position in ("K", "DEF") and round_no <= rounds - 3:
                tags.append("early_k_def")
            if position in ("K", "DEF") and round_no <= 10:
                tags.append("k_def_by_round_10")
            if position in ("K", "DEF") and not dedicated_core_filled(before):
                tags.append("k_def_before_core")
            if position in ("QB", "TE") and before[position] >= 1 and (before["RB"] < 2 or before["WR"] < 2):
                tags.append("backup_before_rb_wr")
            if position == "QB" and before["QB"] >= 1 and not skill_starters_filled(before, flexes):
                tags.append("qb2_before_skill_lineup")
            if position in ("QB", "TE") and before[position] >= 2:
                tags.append("third_qb_te")
            if position in ("QB", "TE") and before[position] == 0 and round_no > 10:
                tags.append("late_first_qb_te")
            if position in ("QB", "TE") and before[position] == 0 and round_no > 12:
                tags.append("severely_late_first_qb_te")
            if (
                reach_rounds is not None
                and reach_rounds >= 2
                and next_turn is not None
                and float(head["adp"]) >= int(next_turn)
                and (survival or 0) >= 0.7
                and (head.get("positional_value_drop") or 0) < 8.5
                and not must_fill
            ):
                tags.append("avoidable_two_round_reach")
            depth = (sleeper_players.get(recommended_id) or {}).get("depth_chart_order")
            head_team = (sleeper_players.get(recommended_id) or {}).get("team")
            same_team = any(
                head_team is not None and pick.get("team") == head_team
                for pick in picks
                if pick["roster_id"] == user_roster_id and pick["pick_no"] < pick_no
            )
            if (
                position == "RB"
                and depth is not None
                and int(depth) >= 2
                and same_team
                and (before["RB"] < 2 or before["WR"] < 2)
            ):
                tags.append("handcuff_before_rb_wr")

            delta = payload.get("paired_value_delta_vs_runner_up")
            tied = len(payload.get("co_leader_candidate_ids") or []) > 1
            if tied != (payload.get("decision_status") == "toss_up"):
                explanation_errors.append((session_id, pick_no, "co_leader_status"))
            if delta and runner:
                q_difference = float(head["projected_roster_value"]) - float(runner["projected_roster_value"])
                if abs(q_difference - float(delta["projected_value_delta"])) > 1e-8:
                    explanation_errors.append((session_id, pick_no, "paired_q_identity"))
                if delta.get("candidate_id") != recommended_id or str(delta.get("baseline_candidate_id")) != runner_id:
                    explanation_errors.append((session_id, pick_no, "paired_ids"))
                lower = float(delta["interval"][0])
                if payload["decision_status"] == "clear_leader" and lower <= 0.1:
                    explanation_errors.append((session_id, pick_no, "clear_below_gate"))
            probability_sum = sum(
                float(row.get("probability") or 0) for row in head.get("later_alternatives", [])
            ) + float(head.get("later_alternative_other_probability") or 0)
            if probability_sum > 1.000000001:
                explanation_errors.append((session_id, pick_no, "later_probability_sum"))

            screen = screen_by_pick.get(pick_no)
            decision = {
                "session_id": session_id,
                "draft_id": session["draft_id"],
                "pick": pick_no,
                "round": round_no,
                "phase": phase(round_no, rounds),
                "teams": teams,
                "rounds": rounds,
                "player_id": recommended_id,
                "name": head.get("name"),
                "position": position,
                "team": head_team,
                "adp": head.get("adp"),
                "reach_rounds": reach_rounds,
                "survival": survival,
                "vona": head.get("value_over_next_alternative"),
                "positional_drop": head.get("positional_value_drop"),
                "current_marginal": head.get("current_marginal_value"),
                "next_turn": next_turn,
                "must_fill": must_fill,
                "depth_chart_order": depth,
                "status": payload.get("decision_status"),
                "reason_codes": payload.get("reason_codes"),
                "co_leaders": len(payload.get("co_leader_candidate_ids") or []),
                "q": head.get("projected_roster_value"),
                "runner": runner.get("name") if runner else None,
                "runner_position": runner.get("position") if runner else None,
                "edge": delta.get("projected_value_delta") if delta else None,
                "edge_interval": delta.get("interval") if delta else None,
                "better_probability": delta.get("better_continuation_probability") if delta else None,
                "ready_seconds": event["duration_seconds"],
                "screen_seconds": screen["duration_seconds"] if screen else None,
                "screen_changed": bool(screen and screen["payload"].get("recommended_candidate_id") != recommended_id),
                "max_rollouts": max((row.get("rollout_count") or 0 for row in payload.get("candidates", [])), default=0),
                "refined_drops": sum((row.get("rollout_count") or 0) > 100 for row in payload.get("screened_candidates", [])),
                "tags": tags,
                "roster_before": dict(before),
            }
            decisions.append(decision)

            next_pick = payload.get("next_user_pick_no")
            if next_pick:
                intervening = [
                    pick for pick in picks
                    if pick_no < pick["pick_no"] < int(next_pick)
                ]
                gone = {
                    str(pick["player_id"]): pick
                    for pick in intervening
                }
                no_user_intervening = not any(
                    pick["roster_id"] == user_roster_id for pick in intervening
                )
                for candidate in payload.get("candidates", []):
                    candidate_id = str(candidate["player_id"])
                    predicted = candidate.get("survives_to_next_pick")
                    if candidate_id == recommended_id or predicted is None:
                        continue
                    row = {
                        "session_id": session_id,
                        "draft_id": session["draft_id"],
                        "pick": pick_no,
                        "round": round_no,
                        "teams": teams,
                        "position": candidate.get("position"),
                        "player_id": candidate_id,
                        "name": candidate.get("name"),
                        "predicted": float(predicted),
                        "realized": float(candidate_id not in gone),
                        "strict_branch": (
                            str(candidate.get("best_wait_candidate_id")) == recommended_id
                            and no_user_intervening
                        ),
                        "is_top_tier": bool(candidate.get("is_top_tier")),
                        "q_gap_to_selected": (
                            float(candidate["projected_roster_value"])
                            - float(head["projected_roster_value"])
                        ),
                        "vona": candidate.get("value_over_next_alternative"),
                        "positional_drop": candidate.get("positional_value_drop"),
                        "gone_at": gone.get(candidate_id, {}).get("pick_no"),
                        "gone_to": gone.get(candidate_id, {}).get("roster_id"),
                    }
                    calibration_rows.append(row)

            if index:
                previous = ready_events[index - 1]["payload"]
                previous_pick = int(ready_events[index - 1]["pick_no"])
                taken = {
                    str(pick["player_id"])
                    for pick in picks
                    if previous_pick <= pick["pick_no"] < pick_no
                }
                current_pool = {str(row["player_id"]) for row in all_candidates}
                previous_finalists = {
                    str(row["player_id"])
                    for row in previous.get("candidates", [])
                    if str(row["player_id"]) not in taken
                }
                missing = sorted(previous_finalists - current_pool)
                continuity.append({
                    "session_id": session_id,
                    "from_pick": previous_pick,
                    "to_pick": pick_no,
                    "available_previous_finalists": len(previous_finalists),
                    "re_evaluated": len(previous_finalists) - len(missing),
                    "missing": missing,
                })

        snapshot = str(config["prepared"]["market_snapshot_id"])
        adp = adp_by_snapshot[snapshot]
        for pick in picks:
            if pick.get("source") != "synthetic_opponent_model":
                continue
            opponent_rows.append({
                "session_id": session_id,
                "draft_id": session["draft_id"],
                "pick": pick["pick_no"],
                "round": pick["round"],
                "teams": teams,
                "name": pick.get("name"),
                "player_id": str(pick["player_id"]),
                "position": pick.get("position"),
                "probability": pick.get("selection_probability"),
                "adp": adp.get(str(pick["player_id"])),
                "reach_rounds": (
                    (adp[str(pick["player_id"])] - pick["pick_no"]) / teams
                    if adp.get(str(pick["player_id"])) is not None else None
                ),
            })

        counts = roster_counts(picks, user_roster_id)
        user_picks = [pick for pick in picks if pick["roster_id"] == user_roster_id]
        first_round = {
            position: next((pick["round"] for pick in user_picks if pick["position"] == position), None)
            for position in ("QB", "RB", "WR", "TE", "K", "DEF")
        }
        fill_round = None
        dedicated_fill_round = None
        all_starters_fill_round = None
        running = Counter()
        flexes = scenario["roster_positions"].count("FLEX")
        for pick in user_picks:
            running[pick["position"]] += 1
            if dedicated_fill_round is None and dedicated_core_filled(running):
                dedicated_fill_round = pick["round"]
            if fill_round is None and running["QB"] >= 1 and skill_starters_filled(running, flexes):
                fill_round = pick["round"]
            if (
                all_starters_fill_round is None
                and running["QB"] >= 1
                and skill_starters_filled(running, flexes)
                and running["K"] >= 1
                and running["DEF"] >= 1
            ):
                all_starters_fill_round = pick["round"]
        byes = defaultdict(list)
        for pick in user_picks:
            projection = (players.get(str(pick["player_id"])) or {}).get("projections") or {}
            bye = projection.get("byeWeek")
            if isinstance(bye, (int, float)) and math.isfinite(bye) and bye > 0:
                byes[int(bye)].append({
                    "player_id": str(pick["player_id"]),
                    "name": pick.get("name"),
                    "position": pick["position"],
                    "team": pick.get("team"),
                })
        roster_rows.append({
            "session_id": session_id,
            "draft_id": session["draft_id"],
            "teams": teams,
            "slot": scenario["user_slot"],
            "positions": dict(counts),
            "first_round": first_round,
            "dedicated_core_fill_round": dedicated_fill_round,
            "complete_skill_fill_round": fill_round,
            "all_starters_fill_round": all_starters_fill_round,
            "legal_starters": starter_need_count(counts, flexes) == 0,
            "cap_violation": any(counts[position] > cap for position, cap in (("QB", 2), ("TE", 2), ("K", 1), ("DEF", 1))),
            "thin_rb_wr_with_backup": (
                (counts["RB"] <= 2 or counts["WR"] <= 2)
                and (counts["QB"] >= 2 or counts["TE"] >= 2)
            ),
            "max_same_bye": max(map(len, byes.values()), default=0),
            "bye_groups": {str(week): rows for week, rows in byes.items() if len(rows) >= 2},
        })

    strict_calibration = [row for row in calibration_rows if row["strict_branch"]]
    by_position = {
        position: calibration([row for row in strict_calibration if row["position"] == position])
        for position in ("QB", "RB", "WR", "TE", "K", "DEF")
    }
    by_position_phase = {
        f"{position}:{phase}": calibration([
            row for row in strict_calibration
            if row["position"] == position
            and (
                "r1_5" if row["round"] <= 5
                else "r6_10" if row["round"] <= 10
                else "r11_plus"
            ) == phase
        ])
        for position in ("QB", "RB", "WR", "TE", "K", "DEF")
        for phase in ("r1_5", "r6_10", "r11_plus")
    }
    decision_positions = Counter((row["teams"], row["round"], row["position"]) for row in decisions)
    position_by_round = [
        {"teams": teams, "round": round_no, "position": position, "count": count}
        for (teams, round_no, position), count in sorted(decision_positions.items())
    ]

    output = {
        "batch_id": batch_id,
        "sessions": len(sessions),
        "completed": sum(row["status"] == "completed" for row in sessions),
        "failed": sum(row["status"] == "failed" for row in sessions),
        "started_at": min(row["started_at"] for row in sessions),
        "finished_at": max((row["finished_at"] for row in sessions if row["finished_at"]), default=None),
        "scenario_counts": [
            {"template": template, "slot": slot, "drafts": count}
            for (template, slot), count in sorted(scenario_counts.items())
        ],
        "integrity_failures": [
            row for row in integrity
            if row["status"] != "completed"
            or row["picks"] != int(configs[row["session_id"]]["scenario"]["teams"]) * int(configs[row["session_id"]]["scenario"]["rounds"])
            or row["screen"] != row["ready"]
            or row["ready"] != int(configs[row["session_id"]]["scenario"]["rounds"])
            or row["user_picks"] != row["ready"]
            or row["summaries"] != 1
            or row["outcomes"] != 1
            or row["errors"]
            or not row["pick_sequence_ok"]
            or not row["unique_players"]
            or row["board_count_mismatches"]
            or row["wrong_engine_versions"]
            or row["policy_mismatches"]
        ],
        "decisions": len(decisions),
        "decision_status": Counter(row["status"] for row in decisions),
        "co_leader_size": Counter(row["co_leaders"] for row in decisions),
        "reason_codes": Counter(code for row in decisions for code in row["reason_codes"]),
        "headline_positions": Counter(row["position"] for row in decisions),
        "position_by_round": position_by_round,
        "latency_ready": stats(row["ready_seconds"] for row in decisions),
        "latency_screen": stats(row["screen_seconds"] for row in decisions),
        "latency_by_phase": {
            name: stats(row["ready_seconds"] for row in decisions if row["phase"] == name)
            for name in ("early", "middle", "late")
        },
        "screen_changes": sum(row["screen_changed"] for row in decisions),
        "racing_depth": Counter(row["max_rollouts"] for row in decisions),
        "early_stops_by_status": Counter(
            f"{row['max_rollouts']}:{row['status']}" for row in decisions
        ),
        "refined_drops": sum(row["refined_drops"] for row in decisions),
        "explanation_errors": explanation_errors,
        "headline_anomalies": [row for row in decisions if row["tags"]],
        "longest_ready": sorted(decisions, key=lambda row: row["ready_seconds"] or 0, reverse=True)[:25],
        "clear_high_survival": [
            row for row in decisions
            if row["status"] == "clear_leader" and (row["survival"] or 0) >= 0.8
        ],
        "passed_low_survival_gone": sorted(
            (
                row for row in strict_calibration
                if row["is_top_tier"] and row["realized"] == 0 and row["predicted"] <= 0.35
            ),
            key=lambda row: (-(row["positional_drop"] or 0), row["predicted"]),
        )[:100],
        "false_wait_candidates": sorted(
            (
                row for row in strict_calibration
                if row["realized"] == 0
                and row["predicted"] >= 0.7
                and row["is_top_tier"]
                and row["q_gap_to_selected"] >= -0.1
            ),
            key=lambda row: (
                -(row["positional_drop"] or 0),
                -row["predicted"],
            ),
        )[:100],
        "survival_calibration_strict": calibration(strict_calibration),
        "survival_calibration_by_position": by_position,
        "survival_calibration_by_position_phase": by_position_phase,
        "survival_observations_all": len(calibration_rows),
        "continuity": {
            "transitions": len(continuity),
            "available_previous_finalists": sum(row["available_previous_finalists"] for row in continuity),
            "re_evaluated": sum(row["re_evaluated"] for row in continuity),
            "missing": [row for row in continuity if row["missing"]],
        },
        "user_rosters": roster_rows,
        "user_final_position_means": {
            str(teams): {
                position: (
                    mean(row["positions"].get(position, 0) for row in roster_rows if row["teams"] == teams)
                    if any(row["teams"] == teams for row in roster_rows)
                    else None
                )
                for position in ("QB", "RB", "WR", "TE", "K", "DEF")
            }
            for teams in (10, 12)
        },
        "human_benchmark": {key: value for key, value in human.items() if key != "timing"},
        "lowest_probability_opponent_picks": sorted(opponent_rows, key=lambda row: row["probability"])[:100],
        "largest_opponent_reaches": sorted(
            (row for row in opponent_rows if row["reach_rounds"] is not None),
            key=lambda row: row["reach_rounds"],
            reverse=True,
        )[:100],
    }
    if details:
        output["details"] = {
            "integrity": integrity,
            "decisions": decisions,
            "strict_calibration": strict_calibration,
            "opponent_picks": opponent_rows,
            "continuity": continuity,
        }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_id")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        audit(args.batch_id, details=args.details),
        indent=2,
        sort_keys=True,
        default=dict,
    ))


if __name__ == "__main__":
    main()
