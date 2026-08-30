#!/usr/bin/env python3
import importlib.util
import json
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np

from ffsim.draft_intel.decision import PRACTICAL_TIE_POINTS, evaluate_candidates, rank_candidates
from ffsim.draft_intel.live import (
    LIVE_SEASON_WORLDS_PER_ROLLOUT,
    LIVE_TEMPERATURE,
    _bank_market_snapshot,
    _live_opponent_choice,
    evaluate_live_candidates,
)
from ffsim.draft_intel.opportunity import next_turn_user_policy
from ffsim.draft_intel.timing_report import build_cached_timing_context

ROOT = Path(__file__).parents[3]
SOURCE = Path(__file__).parents[1] / "2026-08-29_manager_impact_attempt2/run.py"
spec = importlib.util.spec_from_file_location("manager_impact", SOURCE)
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)
MANAGER_BLEND = 0.10


def blended_choice(prepared, state, manager_by_roster, population, managers, counters):
    population_choice = _live_opponent_choice(
        _bank_market_snapshot(prepared), prepared.evaluator, state, LIVE_TEMPERATURE
    )
    personalized_choice = base_module.shadow_choice(
        prepared, state, manager_by_roster, population, managers, counters
    )

    def choose(roster_id, pick_no, rosters, available, mask=None):
        ids, population_logs, keys = population_choice(
            roster_id, pick_no, rosters, available, mask=mask
        )
        personalized_ids, personalized_logs, personalized_keys = personalized_choice(
            roster_id, pick_no, rosters, available, mask=mask
        )
        if not np.array_equal(ids, personalized_ids) or not np.array_equal(
            keys, personalized_keys
        ):
            raise RuntimeError("population and personalized choice boards differ")
        probabilities = (
            (1 - MANAGER_BLEND) * np.exp(population_logs)
            + MANAGER_BLEND * np.exp(personalized_logs)
        )
        probabilities /= probabilities.sum()
        return ids, np.log(probabilities), keys

    choose.returns_final_log_probabilities = True
    choose.returns_log_probability_arrays = True
    choose.board_player_ids = population_choice.board_player_ids
    return choose


def main():
    config = ROOT / "experiments/draft_alpha_2026/2026-08-29_top_ten_capture_attempt2/config.json"
    league_path = ROOT / "data/cache/league_1389391547115511808.json"
    draft_path = ROOT / "data/cache/mock_draft_1393656492011315200.json"
    context = build_cached_timing_context(
        config,
        league_path,
        roster_id=1,
        draft_cache=draft_path,
        world_count=20,
    )
    prior = json.loads((
        ROOT / "experiments/draft_alpha_2026/2026-08-29_vona_impact_attempt2/result.json"
    ).read_text())
    candidate_ids = tuple(row["player_id"] for row in prior["terminal_ranking"][:10])
    market = sqlite3.connect(
        f"file:{base_module.roster_manager.MARKET}?mode=ro&immutable=1", uri=True
    )
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(
        f"file:{base_module.roster_manager.SOURCE}?mode=ro&immutable=1", uri=True
    )
    try:
        population, managers = base_module.roster_manager.fit_roster_model(
            source, market, (2021, 2022, 2023, 2024)
        )
    finally:
        source.close()
        market.close()
    counters = Counter()
    choose = blended_choice(
        context["prepared"],
        context["state"],
        base_module.manager_mapping(league_path, draft_path),
        population,
        managers,
        counters,
    )
    baseline = evaluate_live_candidates(
        context["prepared"], context["state"], 100, candidate_ids
    )
    shadow = evaluate_candidates(
        context["state"],
        candidate_ids,
        context["prepared"].user_roster_id,
        range(100),
        choose,
        next_turn_user_policy(
            context["prepared"].evaluator, context["state"], choose
        ),
        context["prepared"].evaluator,
        draft_model_version="shadow-roster-manager-blend-0.10-v1",
        survival_player_ids=candidate_ids,
        seed=2026,
        temperature=1.0,
        season_worlds_per_rollout=min(
            LIVE_SEASON_WORLDS_PER_ROLLOUT,
            context["prepared"].evaluator.bank.world_count,
        ),
    )
    baseline_ranked = rank_candidates(baseline)
    shadow_ranked = rank_candidates(shadow)
    baseline_leader = baseline_ranked[0].candidate_id
    shadow_leader = shadow_ranked[0].candidate_id
    delta = baseline.paired_value_delta(baseline_leader, shadow_leader)
    practical = delta.interval[0] <= PRACTICAL_TIE_POINTS
    passed = practical and counters["personalized"] > 0 and counters["population"] > 0
    result = {
        "experiment": "conservative roster-aware manager rollout blend",
        "status": "research" if passed else "rejected",
        "manager_probability_blend": MANAGER_BLEND,
        "draft_id": context["state"].draft_id,
        "pick_no": context["state"].current_pick_no,
        "rollouts": 100,
        "baseline_leader": baseline_leader,
        "shadow_leader": shadow_leader,
        "callback_calls": dict(counters),
        "baseline_paired_leader_minus_shadow": {
            "estimate": delta.projected_value_delta,
            "standard_error": delta.standard_error,
            "interval": list(delta.interval),
        },
        "gate": {
            "passes": passed,
            "shadow_leader_is_baseline_practical_co_leader": practical,
            "personalized_callback_used": counters["personalized"] > 0,
            "population_fallback_used": counters["population"] > 0,
            "live_callback_changed": False,
        },
        "baseline_ranking": [candidate.candidate_id for candidate in baseline_ranked],
        "shadow_ranking": [candidate.candidate_id for candidate in shadow_ranked],
        "limitations": [
            "one cached mock state",
            "100-rollout diagnostic budget",
            "fixed 10% manager mixture",
            "shadow callback only; live rollout distribution is unchanged",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "baseline_leader": baseline_leader,
        "shadow_leader": shadow_leader,
        "callback_calls": result["callback_calls"],
        "gate": result["gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
