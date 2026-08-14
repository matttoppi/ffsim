"""Offline harness: rebuild recorded synthetic states and measure policy/scorer mismatch.

Written for the ADR-031 policy/terminal-scorer alignment. The recorded
session prefixes reference local telemetry (data/cache/draft_intel/
telemetry.sqlite3) from the 2026-08-14 synthetic batches; adjust PHANTOMS /
ORDINAL_STATES to fresh session prefixes when re-validating.

Usage (from the repo root):
  .venv/bin/python -m tools.draft_policy_alignment_harness trace    # phantom-edge wait-branch tracing
  .venv/bin/python -m tools.draft_policy_alignment_harness ordinal  # policy-vs-scorer ordinal disagreement
  .venv/bin/python -m tools.draft_policy_alignment_harness bench    # continuation-sampling latency
  .venv/bin/python -m tools.draft_policy_alignment_harness designs  # Objective-2 ranking-design comparison
"""

import json
import sqlite3
import sys
import time
from dataclasses import replace
from statistics import mean

from ffsim.draft_intel.live import (
    _bank_market_snapshot,
    _live_opponent_choice,
    LIVE_TEMPERATURE,
)
from ffsim.draft_intel.opportunity import next_turn_user_policy, season_value_over_replacement
from ffsim.draft_intel.rollout import complete_drafts
from ffsim.draft_intel.synthetic import _load_templates

DB = "data/cache/draft_intel/telemetry.sqlite3"
SEED = 2026

_TEMPLATES = None


def templates():
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = {t.scenario["template_league_id"]: t for t in _load_templates("config.json")}
    return _TEMPLATES


def rebuild(session_prefix, pick_no):
    """Return (prepared, state, ready_payload) for a recorded synthetic state."""
    db = sqlite3.connect(DB)
    sid, cfg = db.execute(
        "select session_id, config_json from live_draft_sessions where session_id like ?",
        (session_prefix + "%",),
    ).fetchone()
    scenario = json.loads(cfg)["scenario"]
    template = templates()[scenario["template_league_id"]]
    prepared = replace(template.prepared, user_roster_id=scenario["user_roster_id"])
    state = template.state
    picks = db.execute(
        "select pick_no, payload_json from live_draft_events where session_id=? and event_type='pick' "
        "and pick_no<? order by pick_no",
        (sid, pick_no),
    ).fetchall()
    for no, pj in picks:
        p = json.loads(pj)
        state = state.with_pick(p["player_id"], position=p["position"])
    assert state.current_pick_no == pick_no, (state.current_pick_no, pick_no)
    ready = db.execute(
        "select payload_json from live_draft_events where session_id=? and event_type='recommendation' "
        "and stage in ('ready','final') and pick_no=? order by id desc limit 1",
        (sid, pick_no),
    ).fetchone()
    return prepared, state, json.loads(ready[0]) if ready else None


def policy_pair(prepared, state):
    snapshot = _bank_market_snapshot(prepared)
    choose = _live_opponent_choice(snapshot, prepared.evaluator, state, LIVE_TEMPERATURE)
    return choose, next_turn_user_policy(prepared.evaluator, state, choose)


def roster_value(prepared, rosters_map):
    ev = prepared.evaluator
    index = {pid: i for i, pid in enumerate(ev.bank.player_ids)}
    assignment = {
        rid: [index[p] for p in players if p in index]
        for rid, players in rosters_map.items()
    }
    for rid in ev.roster_ids:
        assignment.setdefault(rid, [])
    return ev.projected_roster_value(assignment, prepared.user_roster_id)


def paired_values(prepared, state, candidate, rollouts=150, forced=None):
    """Mean terminal roster value forcing `candidate` at the root.

    forced: optional dict {pick_no: player_id} forcing the user policy at later turns.
    """
    choose, policy = policy_pair(prepared, state)
    if forced:
        base_policy = policy

        def policy_wrapper(roster_id, pick_no, rosters, available):
            want = forced.get(pick_no)
            if want is not None and want in available:
                return {want: 1.0}
            return base_policy(roster_id, pick_no, rosters, available)

        policy = policy_wrapper
    completions = complete_drafts(
        state, candidate, prepared.user_roster_id, range(rollouts), choose, policy,
        seed=SEED, temperature=1.0,
    )
    values = []
    for completion in completions:
        values.append(roster_value(prepared, dict(completion.rosters)))
    return completions, values


PHANTOMS = [
    # (session, pick, leader, runner_up) from the telemetry sweep
    ("5e61ae8e", 68, "1466", "LAR"),      # Kelce TE +0.29, 98.7% survival
    ("19aa5ad8", 78, "11533", "12489"),   # Aubrey K +0.81 lb 0.497, 98.7% survival
    ("7a45e07c", 71, "8142", "8121"),     # Pierce WR +0.09, toss-up
    ("2083d7b9", 96, "3214", "12507"),    # Hunter Henry TE +0.27, 84.7% survival
]


def resolve_runner(ready):
    return ready["runner_up_candidate_id"]


def cmd_trace():
    for session, pick, leader, _ in PHANTOMS:
        prepared, state, ready = rebuild(session, pick)
        runner = ready["runner_up_candidate_id"]
        leader_id = ready["recommended_candidate_id"]
        cand = {c["player_id"]: c for c in ready["candidates"]}
        next_turn = ready.get("next_user_pick_no")
        print(f"\n=== {session} pick {pick}: leader {cand[leader_id]['name']} vs runner {cand.get(runner, {}).get('name', runner)} (next turn {next_turn})")
        cl, vl = paired_values(prepared, state, leader_id)
        cr, vr = paired_values(prepared, state, runner)
        deltas = [a - b for a, b in zip(vl, vr)]
        print(f"reproduced paired edge (leader-runner): {mean(deltas):+.3f} "
              f"(telemetry {ready['paired_value_delta_vs_runner_up']['projected_value_delta']:+.3f})")
        # wait branch = runner branch; how often does the policy skip the leader
        # when he is available at the next user turn?
        avail = harvested = 0
        for completion in cr:
            user_picks = {p.pick_no: p.player_id for p in completion.picks if p.user_pick}
            # leader available at next turn iff no one picked him before it
            taken_before = any(
                p.player_id == leader_id and p.pick_no < next_turn for p in completion.picks
            )
            if not taken_before:
                avail += 1
                if user_picks.get(next_turn) == leader_id:
                    harvested += 1
        print(f"leader available at next turn in {avail}/{len(cr)} wait rollouts; policy took him {harvested}/{avail}")
        # counterfactual: force the leader at the next user turn in the wait branch
        _, vf = paired_values(prepared, state, runner, forced={next_turn: leader_id})
        forced_deltas = [a - b for a, b in zip(vl, vf)]
        print(f"paired edge after forcing leader harvest at next turn: {mean(forced_deltas):+.3f}  "
              f"(policy leakage {mean(deltas) - mean(forced_deltas):+.3f})")


ORDINAL_STATES = [
    ("5e61ae8e", 8), ("5e61ae8e", 28), ("5e61ae8e", 48), ("5e61ae8e", 68),
    ("5e61ae8e", 93), ("5e61ae8e", 108), ("5e61ae8e", 128), ("5e61ae8e", 148),
    ("2083d7b9", 24), ("2083d7b9", 48), ("2083d7b9", 72), ("2083d7b9", 96),
    ("2083d7b9", 120), ("2083d7b9", 145),
    ("19aa5ad8", 38), ("19aa5ad8", 78), ("19aa5ad8", 118), ("19aa5ad8", 158),
]


def cmd_ordinal():
    total = dis = 0
    by_pos = {}
    for session, pick in ORDINAL_STATES:
        prepared, state, _ = rebuild(session, pick)
        ev = prepared.evaluator
        _, policy = policy_pair(prepared, state)
        rosters = {rid: list(players) for rid, players in state.rosters}
        available = frozenset(state.available_player_ids)
        roster_view = tuple((rid, tuple(p)) for rid, p in sorted(rosters.items()))
        utilities = policy(prepared.user_roster_id, state.current_pick_no, roster_view, available)
        # marginal terminal value for the top-30 policy candidates plus top-30 by projection
        projection, position_of, _ = season_value_over_replacement(ev)
        pool = sorted(utilities, key=lambda p: -utilities[p])[:20]
        base = roster_value(prepared, rosters)
        marg = {}
        for p in pool:
            with_p = {**rosters, prepared.user_roster_id: rosters[prepared.user_roster_id] + [p]}
            marg[p] = roster_value(prepared, with_p) - base
        pol_rank = sorted(pool, key=lambda p: -utilities[p])
        val_rank = sorted(pool, key=lambda p: -marg[p])
        round_no = (state.current_pick_no - 1) // state.teams + 1
        top_match = pol_rank[0] == val_rank[0]
        # pairwise disagreement on current-value component is what we can act on;
        # report top-1 and Kendall-ish inversions among top 10 by value
        inv = n = 0
        top = val_rank[:10]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, b = top[i], top[j]
                if abs(marg[a] - marg[b]) < 0.5:
                    continue
                n += 1
                if (utilities[a] - utilities[b]) * (marg[a] - marg[b]) < 0:
                    inv += 1
                    key = (round_no <= 5 and "early" or round_no <= 10 and "mid" or "late",
                           position_of.get(a), position_of.get(b))
                    by_pos[key] = by_pos.get(key, 0) + 1
        total += n
        dis += inv
        print(f"{session} pick {pick} (round {round_no}): top1 {'match' if top_match else 'MISMATCH'} "
              f"inversions {inv}/{n}  policy-top {pol_rank[0]} value-top {val_rank[0]}")
    print(f"\noverall pairwise inversion rate: {dis}/{total} = {dis / max(total, 1):.1%}")
    for k, v in sorted(by_pos.items(), key=lambda kv: -kv[1])[:15]:
        print(k, v)


def cmd_bench():
    for session, pick in (("5e61ae8e", 28), ("2083d7b9", 96), ("19aa5ad8", 158)):
        prepared, state, ready = rebuild(session, pick)
        leader = ready["recommended_candidate_id"]
        choose, policy = policy_pair(prepared, state)
        start = time.perf_counter()
        complete_drafts(state, leader, prepared.user_roster_id, range(50), choose, policy,
                        seed=SEED, temperature=1.0)
        print(f"{session} pick {pick}: 50 continuations in {time.perf_counter() - start:.3f}s")


# Objective-2 design comparison (ADR-032): recorded states used to decide how
# urgency enters the ranking. Includes the decisive-QB (Josh-Allen-type) and
# scarce-vs-survivor (Fannin-type, pick 78) archetypes plus a round spread.
DESIGN_STATES = [
    ("7482e87c", 26),   # Josh-Allen-type: decisive QB leader
    ("19aa5ad8", 78),   # Fannin-type: scarce RB vs high-survival kicker
    ("5e61ae8e", 68),   # Kelce phantom (post-ADR-031: collapsed)
    ("7a45e07c", 71),   # Pierce toss-up
    ("2083d7b9", 96),   # Hunter Henry genuine residual
    ("5e61ae8e", 8), ("5e61ae8e", 28), ("5e61ae8e", 108), ("5e61ae8e", 148),
    ("2083d7b9", 24), ("2083d7b9", 72), ("2083d7b9", 145),
    ("19aa5ad8", 38), ("19aa5ad8", 158),
]


def cmd_designs(rollouts=150, cands=8):
    """Compare urgency-in-the-ranking designs on recorded states.

    Per state: current ranking (Q = mean paired terminal roster value), the
    design-b identity (mean paired delta == Q difference), composite-score
    (design a) leader flips at a w grid, and co-leader counts at candidate
    epsilons (design c). Pools a paired-delta ~ dVONA regression at the end:
    the slope measures how much of VONA the aligned rollouts already price.
    """
    from ffsim.draft_intel.decision import (
        evaluate_candidates, rank_candidates, candidate_vona,
    )
    from ffsim.draft_intel.live import _live_model_version

    results = []
    for session, pick in DESIGN_STATES:
        prepared, state, ready = rebuild(session, pick)
        cand_ids = []
        for c in ready["candidates"]:
            pid = c["player_id"]
            if pid in state.available_player_ids and pid not in cand_ids:
                cand_ids.append(pid)
            if len(cand_ids) >= cands:
                break
        choose, policy = policy_pair(prepared, state)
        snapshot = _bank_market_snapshot(prepared)
        ev = evaluate_candidates(
            state, cand_ids, prepared.user_roster_id, range(rollouts), choose,
            policy, prepared.evaluator,
            draft_model_version=_live_model_version(snapshot, LIVE_TEMPERATURE),
            survival_player_ids=cand_ids, season_worlds_per_rollout=1,
            temperature=1.0,
        )
        ranked = rank_candidates(ev)
        leader = ranked[0]
        names = {c["player_id"]: (c.get("name"), c.get("position"))
                 for c in ready["candidates"]}
        rows = []
        for cand in ranked:
            delta = None if cand is leader else ev.paired_value_delta(
                leader.candidate_id, cand.candidate_id)
            surv = None
            if cand.survival:
                for p in cand.survival.players:
                    if p.player_id == cand.candidate_id:
                        surv = p.survives_to_next_pick
            rows.append({
                "id": cand.candidate_id,
                "name": names.get(cand.candidate_id, (cand.candidate_id, "?"))[0],
                "pos": names.get(cand.candidate_id, (None, "?"))[1],
                "q": cand.projected_roster_value,
                "vona": candidate_vona(cand),
                "survival": surv,
                "delta_vs_leader": None if delta is None else delta.projected_value_delta,
                "delta_lb": None if delta is None else delta.interval[0],
                "delta_se": None if delta is None else delta.standard_error,
            })
        identity_err = max(
            abs((leader.projected_roster_value - cand.projected_roster_value)
                - ev.paired_value_delta(
                    leader.candidate_id, cand.candidate_id).projected_value_delta)
            for cand in ranked[1:]
        )
        composite_top = {
            w: sorted(ranked, key=lambda c: -(
                c.projected_roster_value
                + w * max(0.0, candidate_vona(c) or 0.0)))[0].candidate_id
            for w in (0.25, 0.5, 1.0)
        }
        co_leaders = {
            eps: sum(
                1 for cand in ranked
                if cand is leader or ev.paired_value_delta(
                    leader.candidate_id, cand.candidate_id).interval[0] <= eps
            )
            for eps in (0.5, 0.25, 0.1)
        }
        results.append({"session": session, "pick": pick, "rows": rows,
                        "identity_err": identity_err,
                        "composite_top": composite_top,
                        "co_leaders": co_leaders})
        r0 = rows[0]
        print(f"\n=== {session} pick {pick}: leader {r0['name']} ({r0['pos']}) "
              f"Q={r0['q']:.2f} vona={r0['vona']}")
        for r in rows[1:4]:
            print(f"   vs {r['name']} ({r['pos']}): delta {r['delta_vs_leader']:+.3f} "
                  f"lb {r['delta_lb']:+.3f} se {r['delta_se']:.3f} "
                  f"vona {r['vona'] if r['vona'] is None else round(r['vona'], 2)} "
                  f"surv {r['survival']}")
        print(f"   identity_err {identity_err:.2e}  composite_top {composite_top}  "
              f"co_leaders {co_leaders}")

    xs, ys = [], []
    for res in results:
        lead = res["rows"][0]
        if lead["vona"] is None:
            continue
        for r in res["rows"][1:]:
            if r["vona"] is None or r["delta_vs_leader"] is None:
                continue
            xs.append(lead["vona"] - r["vona"])
            ys.append(r["delta_vs_leader"])
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    print(f"\npooled regression paired_delta ~ dVONA: n={len(xs)} "
          f"slope={slope:.3f} intercept={intercept:.3f} "
          f"R2={1 - ss_res / ss_tot:.3f}")
    return results


if __name__ == "__main__":
    {"trace": cmd_trace, "ordinal": cmd_ordinal, "bench": cmd_bench,
     "designs": cmd_designs}[sys.argv[1]]()
