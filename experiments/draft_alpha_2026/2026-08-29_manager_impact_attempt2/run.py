#!/usr/bin/env python3
import importlib.util
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np

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
from ffsim.draft_intel.timing_report import build_cached_timing_context
from ffsim.historical_sleeper.manager_choice import MINIMUM_MANAGER_PICKS

ROOT = Path(__file__).parents[3]
ROSTER_SCRIPT = Path(__file__).parents[1] / "2026-08-29_roster_manager_attempt2/run.py"
spec = importlib.util.spec_from_file_location("roster_manager", ROSTER_SCRIPT)
roster_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roster_manager)


def manager_mapping(league_path, draft_path):
    league = json.loads(Path(league_path).read_text())
    draft = json.loads(Path(draft_path).read_text())
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


def shadow_choice(prepared, state, manager_by_roster, population, managers, counters):
    base = _live_opponent_choice(
        _bank_market_snapshot(prepared), prepared.evaluator, state, LIVE_TEMPERATURE
    )
    position_by_id = dict(
        zip(prepared.evaluator.bank.player_ids, prepared.evaluator.bank.player_positions)
    )

    def choose(roster_id, pick_no, rosters, available, mask=None):
        ids, log_probabilities, keys = base(
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
                roster_manager.POSITIONS.index(
                    position_by_id.get(player_id, "UNKNOWN")
                )
            ]
            for player_id in ids
        ])
        probabilities = np.exp(log_probabilities) * factors
        probabilities /= probabilities.sum()
        counters["personalized" if record is not None and record["picks"] >= MINIMUM_MANAGER_PICKS else "population"] += 1
        return ids, np.log(probabilities), keys

    choose.returns_final_log_probabilities = True
    choose.returns_log_probability_arrays = True
    choose.board_player_ids = base.board_player_ids
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
    baseline_result = json.loads((
        ROOT / "experiments/draft_alpha_2026/2026-08-29_vona_impact_attempt2/result.json"
    ).read_text())
    candidate_ids = tuple(
        row["player_id"] for row in baseline_result["terminal_ranking"][:10]
    )
    market = sqlite3.connect(
        f"file:{roster_manager.MARKET}?mode=ro&immutable=1", uri=True
    )
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(
        f"file:{roster_manager.SOURCE}?mode=ro&immutable=1", uri=True
    )
    try:
        population, managers = roster_manager.fit_roster_model(
            source, market, (2021, 2022, 2023, 2024)
        )
    finally:
        source.close()
        market.close()
    counters = Counter()
    choose = shadow_choice(
        context["prepared"],
        context["state"],
        manager_mapping(league_path, draft_path),
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
        draft_model_version="shadow-roster-manager-v1",
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
        "experiment": "roster-aware manager shadow rollout impact",
        "status": "research" if passed else "rejected",
        "draft_id": context["state"].draft_id,
        "pick_no": context["state"].current_pick_no,
        "rollouts": 100,
        "candidate_ids": list(candidate_ids),
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
            "real manager IDs are mapped by template draft slot",
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
