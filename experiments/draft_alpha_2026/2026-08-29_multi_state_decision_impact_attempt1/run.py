#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from ffsim.draft_intel.decision import (
    PRACTICAL_TIE_POINTS,
    evaluate_candidates,
    rank_candidates,
)
from ffsim.draft_intel.live import (
    LIVE_SEASON_WORLDS_PER_ROLLOUT,
    LIVE_TEMPERATURE,
    _bank_market_snapshot,
    _live_opponent_choice,
    evaluate_live_candidates,
)
from ffsim.draft_intel.opportunity import next_turn_user_policy
from ffsim.draft_intel.timing_report import (
    build_cached_timing_context,
    build_timing_report,
)
from ffsim.historical_sleeper.hdvn_snapshot import canonical_json
from ffsim.historical_sleeper.manager_choice import MINIMUM_MANAGER_PICKS

ROOT = Path(__file__).parents[3]
HERE = Path(__file__).parent
CORPUS_PATH = ROOT / "experiments/draft_alpha_2026/2026-08-29_multi_state_corpus/corpus.json"
SURVIVAL_MANIFEST = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/hierarchical-survival-final-20260829/hierarchical-survival.manifest.json"
ROSTER_SCRIPT = ROOT / "experiments/draft_alpha_2026/2026-08-29_roster_manager_corrected/run.py"
spec = importlib.util.spec_from_file_location("corrected_roster_manager", ROSTER_SCRIPT)
roster_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roster_manager)
MANAGER_BLEND = 0.10
ROLLOUTS = 100


def load_corpus():
    corpus = json.loads(CORPUS_PATH.read_text())
    stored = corpus.pop("sha256")
    actual = hashlib.sha256(canonical_json(corpus).encode()).hexdigest()
    if stored != actual or actual != "7ee9267de2531b61293a03fb1435c32d136508349ab0530b555f3b499742d52f":
        raise RuntimeError("multi-state corpus hash changed")
    corpus["sha256"] = stored
    return corpus


def manager_mapping(league_path, draft_path):
    league = json.loads(league_path.read_text())
    draft = json.loads(draft_path.read_text())
    owner_by_real_roster = {
        int(roster["roster_id"]): str(roster.get("owner_id") or "")
        for roster in league["rosters"]
    }
    real_by_slot = {
        int(slot): int(roster_id)
        for slot, roster_id in league["draft"]["slot_to_roster_id"].items()
    }
    synthetic_by_slot = {
        int(slot): int(roster_id)
        for slot, roster_id in draft["draft"]["slot_to_roster_id"].items()
    }
    return {
        synthetic_by_slot[slot]: owner_by_real_roster.get(real_roster, "")
        for slot, real_roster in real_by_slot.items()
        if slot in synthetic_by_slot
    }


def blended_choice(prepared, state, manager_by_roster, population, managers, counters):
    population_choice = _live_opponent_choice(
        _bank_market_snapshot(prepared), prepared.evaluator, state, LIVE_TEMPERATURE
    )
    position_by_id = dict(
        zip(prepared.evaluator.bank.player_ids, prepared.evaluator.bank.player_positions)
    )

    def choose(roster_id, pick_no, rosters, available, mask=None):
        ids, population_logs, keys = population_choice(
            roster_id, pick_no, rosters, available, mask=mask
        )
        manager_id = manager_by_roster.get(roster_id, "")
        record = managers.get(manager_id)
        roster = tuple(dict(rosters)[roster_id])
        counts = Counter(position_by_id.get(player_id) for player_id in roster)
        buckets = np.minimum(
            np.asarray([counts.get(position, 0) for position in roster_manager.POSITIONS]),
            2,
        )
        source = (
            record["factor"]
            if record is not None and record["picks"] >= MINIMUM_MANAGER_PICKS
            else population
        )
        factors_by_position = source[np.arange(len(buckets)), buckets]
        factors = np.asarray([
            factors_by_position[
                roster_manager.POSITIONS.index(position_by_id.get(player_id, "UNKNOWN"))
            ]
            for player_id in ids
        ])
        population_probabilities = np.exp(population_logs)
        manager_probabilities = population_probabilities * factors
        manager_probabilities /= manager_probabilities.sum()
        probabilities = (
            (1 - MANAGER_BLEND) * population_probabilities
            + MANAGER_BLEND * manager_probabilities
        )
        probabilities /= probabilities.sum()
        counters[
            "personalized"
            if record is not None and record["picks"] >= MINIMUM_MANAGER_PICKS
            else "population"
        ] += 1
        return ids, np.log(probabilities), keys

    choose.returns_final_log_probabilities = True
    choose.returns_log_probability_arrays = True
    choose.board_player_ids = population_choice.board_player_ids
    return choose


def evaluate_state(state_record, population, managers):
    config = ROOT / state_record["config"]
    league_path = ROOT / state_record["league_cache"]
    draft_path = ROOT / state_record["draft_cache"]
    context = build_cached_timing_context(
        config,
        league_path,
        roster_id=state_record["roster_id"],
        draft_cache=draft_path,
        world_count=20,
    )
    timing = build_timing_report(
        context["prepared"],
        context["state"],
        SURVIVAL_MANIFEST,
        input_hashes=context["input_hashes"],
        candidate_breadth=20,
    )
    route_rows = [
        row for row in timing["players"] if row["take_now_route_value"] is not None
    ]
    route_rows.sort(key=lambda row: (-row["take_now_route_value"], row["player_id"]))
    candidate_ids = tuple(row["player_id"] for row in route_rows)
    baseline = evaluate_live_candidates(
        context["prepared"], context["state"], ROLLOUTS, candidate_ids
    )
    baseline_ranked = rank_candidates(baseline)
    baseline_leader = baseline_ranked[0].candidate_id
    route_leader = route_rows[0]["player_id"]
    route_delta = baseline.paired_value_delta(baseline_leader, route_leader)
    route_practical = route_delta.interval[0] <= PRACTICAL_TIE_POINTS
    route_values = {
        row["player_id"]: row["take_now_route_value"] for row in route_rows
    }
    correlation = float(spearmanr(
        [route_values[candidate.candidate_id] for candidate in baseline_ranked],
        [candidate.projected_roster_value for candidate in baseline_ranked],
    ).statistic)

    shadow_candidates = tuple(
        candidate.candidate_id for candidate in baseline_ranked[:10]
    )
    counters = Counter()
    choose = blended_choice(
        context["prepared"],
        context["state"],
        manager_mapping(league_path, draft_path),
        population,
        managers,
        counters,
    )
    shadow = evaluate_candidates(
        context["state"],
        shadow_candidates,
        context["prepared"].user_roster_id,
        range(ROLLOUTS),
        choose,
        next_turn_user_policy(
            context["prepared"].evaluator, context["state"], choose
        ),
        context["prepared"].evaluator,
        draft_model_version="shadow-corrected-roster-manager-blend-0.10-v1",
        survival_player_ids=shadow_candidates,
        seed=2026,
        temperature=1.0,
        season_worlds_per_rollout=min(
            LIVE_SEASON_WORLDS_PER_ROLLOUT,
            context["prepared"].evaluator.bank.world_count,
        ),
    )
    shadow_ranked = rank_candidates(shadow)
    shadow_leader = shadow_ranked[0].candidate_id
    shadow_delta = baseline.paired_value_delta(baseline_leader, shadow_leader)
    shadow_practical = shadow_delta.interval[0] <= PRACTICAL_TIE_POINTS
    return {
        "draft_id": state_record["draft_id"],
        "league_id": state_record["league_id"],
        "pick_no": state_record["pick_no"],
        "round": state_record["round"],
        "gap": state_record["gap"],
        "timing_report": timing,
        "baseline_leader": baseline_leader,
        "route_leader": route_leader,
        "route_terminal_rank": next(
            index for index, candidate in enumerate(baseline_ranked, 1)
            if candidate.candidate_id == route_leader
        ),
        "route_spearman": correlation,
        "route_baseline_delta": {
            "estimate": route_delta.projected_value_delta,
            "standard_error": route_delta.standard_error,
            "interval": list(route_delta.interval),
            "practical_co_leader": route_practical,
        },
        "shadow_leader": shadow_leader,
        "shadow_baseline_delta": {
            "estimate": shadow_delta.projected_value_delta,
            "standard_error": shadow_delta.standard_error,
            "interval": list(shadow_delta.interval),
            "practical_co_leader": shadow_practical,
        },
        "callback_calls": dict(counters),
        "baseline_ranking": [candidate.candidate_id for candidate in baseline_ranked],
        "shadow_ranking": [candidate.candidate_id for candidate in shadow_ranked],
        "terminal_first_recommendation": baseline_leader,
        "terminal_first_changed_by_timing": False,
    }


def main():
    corpus = load_corpus()
    market = sqlite3.connect(
        f"file:{roster_manager.MARKET}?mode=ro&immutable=1", uri=True
    )
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(
        f"file:{roster_manager.SOURCE}?mode=ro&immutable=1", uri=True
    )
    try:
        population, managers, training_counts = roster_manager.fit_roster_model(
            source, market, (2021, 2022, 2023, 2024)
        )
    finally:
        source.close()
        market.close()
    states = []
    for state_record in corpus["states"]:
        print(f"evaluating {state_record['draft_id']}", flush=True)
        states.append(evaluate_state(state_record, population, managers))
    terminal_gate = {
        "complete_top_ten_capture": all(
            state["timing_report"]["top_ten_capture_complete"] for state in states
        ),
        "all_reports_shadow_only": all(
            state["timing_report"]["decision_active"] is False for state in states
        ),
        "recommendations_terminal_first": all(
            state["terminal_first_recommendation"] == state["baseline_leader"]
            and not state["terminal_first_changed_by_timing"]
            for state in states
        ),
    }
    terminal_gate["passes"] = all(terminal_gate.values())
    personalized_calls = sum(
        state["callback_calls"].get("personalized", 0) for state in states
    )
    population_calls = sum(
        state["callback_calls"].get("population", 0) for state in states
    )
    manager_gate = {
        "all_shadow_leaders_practical": all(
            state["shadow_baseline_delta"]["practical_co_leader"] for state in states
        ),
        "personalized_callbacks_used": personalized_calls > 0,
        "population_fallbacks_used": population_calls > 0,
        "live_callback_changed": False,
    }
    manager_gate["passes"] = all(manager_gate.values())
    route_practical = sum(
        state["route_baseline_delta"]["practical_co_leader"] for state in states
    )
    result = {
        "experiment": "six-state terminal timing and manager shadow impact",
        "status": "research" if terminal_gate["passes"] and manager_gate["passes"] else "rejected",
        "corpus_sha256": corpus["sha256"],
        "rollouts": ROLLOUTS,
        "manager_probability_blend": MANAGER_BLEND,
        "manager_training_counts": training_counts,
        "states": states,
        "terminal_first_gate": terminal_gate,
        "manager_gate": manager_gate,
        "route_diagnostic": {
            "practical_co_leader_states": route_practical,
            "total_states": len(states),
            "mean_spearman": sum(state["route_spearman"] for state in states) / len(states),
        },
        "callback_calls": {
            "personalized": personalized_calls,
            "population": population_calls,
        },
        "limitations": [
            "six cached mock states",
            "100-rollout preliminary budget",
            "no realized draft outcome labels",
            "shadow models do not change the live callback or recommendation",
        ],
    }
    (HERE / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    reports = HERE / "reports"
    reports.mkdir(exist_ok=True)
    for state in states:
        (reports / f"{state['draft_id']}.json").write_text(
            json.dumps(state["timing_report"], indent=2, sort_keys=True) + "\n"
        )
    print(json.dumps({
        "status": result["status"],
        "terminal_first_gate": terminal_gate,
        "manager_gate": manager_gate,
        "route_diagnostic": result["route_diagnostic"],
        "callback_calls": result["callback_calls"],
    }, indent=2))


if __name__ == "__main__":
    main()
