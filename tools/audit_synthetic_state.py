"""Read-only deep dives for a completed synthetic-draft telemetry state.

Usage:
    .venv/bin/python -m tools.audit_synthetic_state margin SESSION PICK
    .venv/bin/python -m tools.audit_synthetic_state wait SESSION PICK [PLAYER]
    .venv/bin/python -m tools.audit_synthetic_state racing SESSION PICK [--flat]

Do not run while synthetic telemetry is being written.
"""

import argparse
import json
import sqlite3

from ffsim.api import (
    FINALIST_COUNT,
    REFINEMENT_REGRET_STOP,
    REFINEMENT_STAGE_ROLLOUT_COUNTS,
    SCREEN_ROLLOUT_COUNT,
)
from ffsim.draft_intel.decision import PRACTICAL_TIE_POINTS, rank_candidates
from ffsim.draft_intel.live import (
    create_live_executor,
    evaluate_live_candidates,
    live_recommendation_payload,
    merge_screen_refinement,
    refinement_survivors,
    select_finalists,
)
from ffsim.draft_intel.rollout import complete_drafts
from tools.draft_policy_alignment_harness import (
    DB,
    policy_pair,
    rebuild,
    roster_value,
)


def payload_rows(ready):
    seen = set()
    for row in (*ready["candidates"], *ready.get("screened_candidates", ())):
        if row["player_id"] not in seen:
            seen.add(row["player_id"])
            yield row


def session_config(prefix):
    with sqlite3.connect(DB) as database:
        rows = database.execute(
            "SELECT config_json FROM live_draft_sessions WHERE session_id LIKE ?",
            (prefix + "%",),
        ).fetchall()
    if len(rows) != 1:
        raise ValueError(f"Session prefix matched {len(rows)} sessions")
    return json.loads(rows[0][0])


def recorded_screen_ids(prefix, pick_no):
    with sqlite3.connect(DB) as database:
        sessions = database.execute(
            "SELECT session_id FROM live_draft_sessions WHERE session_id LIKE ?",
            (prefix + "%",),
        ).fetchall()
        if len(sessions) != 1:
            raise ValueError(f"Session prefix matched {len(sessions)} sessions")
        row = database.execute(
            "SELECT payload_json FROM live_draft_events "
            "WHERE session_id=? AND event_type='recommendation' "
            "AND stage='screen' AND pick_no=? ORDER BY id DESC LIMIT 1",
            (sessions[0][0], pick_no),
        ).fetchone()
    if row is None:
        raise ValueError("Recorded screen not found")
    return tuple(
        candidate["player_id"]
        for candidate in json.loads(row[0])["candidates"]
    )


def exact_marginals(session, pick, player_id=None):
    session_config(session)
    prepared, state, ready = rebuild(session, pick)
    rosters = {roster_id: list(players) for roster_id, players in state.rosters}
    base = roster_value(prepared, rosters)
    results = []
    for row in payload_rows(ready):
        payload = row.get("current_marginal_value")
        if payload is None or player_id is not None and row["player_id"] != player_id:
            continue
        with_player = {
            **rosters,
            prepared.user_roster_id: [
                *rosters[prepared.user_roster_id], row["player_id"],
            ],
        }
        exact = roster_value(prepared, with_player) - base
        results.append((abs(exact - payload), row, exact, payload))
    for _, row, exact, payload in sorted(results, key=lambda result: -result[0]):
        print(
            f"{row['player_id']:>6} {row['position']:<3} {row['name']:<24} "
            f"exact={exact:8.3f} payload={payload:8.3f} "
            f"exact-payload={exact - payload:+8.3f}"
        )


def actual_wait_path(session, pick, player_id=None):
    config = session_config(session)
    prepared, state, ready = rebuild(session, pick)
    rows = {row["player_id"]: row for row in payload_rows(ready)}
    target_id = player_id or ready["recommended_candidate_id"]
    target = rows[target_id]
    wait_id = target["best_wait_candidate_id"]
    next_turn = target["next_turn_pick_no"]
    if wait_id is None or next_turn is None:
        raise ValueError("Target has no recorded wait branch")

    rollout_id = int(config["opponent_rollout_id"])
    choose, policy = policy_pair(prepared, state)
    completion = complete_drafts(
        state,
        wait_id,
        prepared.user_roster_id,
        (rollout_id, rollout_id + 1),
        choose,
        policy,
        seed=int(config["opponent_seed"]),
        temperature=1.0,
    )[0]
    target_pick = next(
        (value for value in completion.picks if value.player_id == target_id),
        None,
    )
    survived = target_pick is None or target_pick.pick_no >= next_turn
    harvested_at_next = bool(
        target_pick and target_pick.user_pick and target_pick.pick_no == next_turn
    )
    harvested_same_turn = bool(
        target_pick and target_pick.user_pick and target_pick.pick_no < next_turn
    )
    name = lambda value: prepared.player_details.get(value, {}).get("name", value)
    print(
        f"target={name(target_id)} wait_root={name(wait_id)} "
        f"seed={config['opponent_seed']} rollout={rollout_id}"
    )
    print(
        f"predicted_survival={target.get('survives_to_next_pick')} "
        f"realized_survival={survived} "
        f"policy_harvested_same_turn={harvested_same_turn} "
        f"policy_harvested_at_next_turn={harvested_at_next} "
        f"target_pick={target_pick.pick_no if target_pick else None} "
        f"target_taker={'user' if target_pick and target_pick.user_pick else 'opponent' if target_pick else None}"
    )
    for path_pick in completion.picks:
        if path_pick.pick_no > next_turn:
            break
        print(
            f"pick={path_pick.pick_no:3} roster={path_pick.roster_id:2} "
            f"user={str(path_pick.user_pick):5} p={path_pick.probability:.4f} "
            f"{name(path_pick.player_id)}"
        )


def report_stage(evaluation, stage, prepared, mode):
    ranked = rank_candidates(evaluation)
    leader = ranked[0]
    racing_ids, max_advantage = refinement_survivors(evaluation)
    practical_ids = {
        candidate.candidate_id
        for candidate in ranked
        if candidate is leader
        or evaluation.paired_value_delta(
            leader.candidate_id, candidate.candidate_id
        ).interval[0] <= PRACTICAL_TIE_POINTS
    }
    outside_survivors = practical_ids - set(racing_ids)
    applied_drop = stage < 300 and max_advantage >= REFINEMENT_REGRET_STOP
    name = lambda candidate: prepared.player_details.get(
        candidate.candidate_id, {}
    ).get("name", candidate.candidate_id)
    print(
        f"mode={mode} stage={stage} leader={name(leader)} racing={list(racing_ids)} "
        f"practical={sorted(practical_ids)} max_advantage={max_advantage:.3f} "
        f"would_stop={max_advantage < REFINEMENT_REGRET_STOP} "
        f"outside_survivors={sorted(outside_survivors)} "
        f"production_drop_would_apply={applied_drop}"
    )
    for candidate in ranked:
        if candidate is leader:
            print(f"  {candidate.candidate_id:>6} {name(candidate):<24} LEADER")
            continue
        edge = evaluation.paired_value_delta(
            leader.candidate_id, candidate.candidate_id
        )
        print(
            f"  {candidate.candidate_id:>6} {name(candidate):<24} "
            f"leader_edge={edge.projected_value_delta:+.3f} "
            f"lb={edge.interval[0]:+.3f} "
            f"race={'keep' if candidate.candidate_id in racing_ids else 'drop'} "
            f"gate={'tie' if candidate.candidate_id in practical_ids else 'out'}"
        )
    return racing_ids, max_advantage


def racing(session, pick, flat):
    session_config(session)
    prepared, state, _ = rebuild(session, pick)
    candidate_ids = recorded_screen_ids(session, pick)
    with create_live_executor(prepared) as executor:
        screen = evaluate_live_candidates(
            prepared,
            state,
            SCREEN_ROLLOUT_COUNT,
            candidate_ids,
            executor=executor,
            survival_ids=candidate_ids,
        )
        screen_payload = live_recommendation_payload(
            prepared, state, [screen], len(candidate_ids)
        )
        finalists = select_finalists(
            prepared, state, screen_payload["candidates"], FINALIST_COUNT
        )
        print(f"screen={SCREEN_ROLLOUT_COUNT} finalists={list(finalists)}")
        active, previous, previous_count = finalists, [screen], SCREEN_ROLLOUT_COUNT
        for stage in (*REFINEMENT_STAGE_ROLLOUT_COUNTS, 300):
            extension = evaluate_live_candidates(
                prepared,
                state,
                range(previous_count, stage),
                active,
                executor=executor,
                survival_ids=active,
            )
            evaluation = merge_screen_refinement(previous, extension)
            survivors, max_advantage = report_stage(
                evaluation,
                stage,
                prepared,
                "flat_counterfactual" if flat else "production",
            )
            previous, previous_count = [evaluation], stage
            if max_advantage < REFINEMENT_REGRET_STOP and not flat:
                break
            active = finalists if flat else survivors


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("margin", "wait"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("session")
        subparser.add_argument("pick", type=int)
        subparser.add_argument("player_id", nargs="?")
    subparser = subparsers.add_parser("racing")
    subparser.add_argument("session")
    subparser.add_argument("pick", type=int)
    subparser.add_argument("--flat", action="store_true")
    args = parser.parse_args()
    if args.command == "margin":
        exact_marginals(args.session, args.pick, args.player_id)
    elif args.command == "wait":
        actual_wait_path(args.session, args.pick, args.player_id)
    else:
        racing(args.session, args.pick, args.flat)


if __name__ == "__main__":
    main()
