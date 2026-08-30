#!/usr/bin/env python3
import importlib.util
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

from ffsim.historical_sleeper.continuous_survival import _add_metric, _finish_metric, _metric_state
from ffsim.historical_sleeper.manager_choice import MINIMUM_MANAGER_PICKS, _choice_state, _manager_by_pick, fit_manager_choice
from ffsim.historical_sleeper.opponent_model import _clustered_difference, _iter_drafts

ROSTER_SCRIPT = Path(__file__).parents[1] / "2026-08-29_roster_manager_attempt2/run.py"
spec = importlib.util.spec_from_file_location("roster_manager", ROSTER_SCRIPT)
roster_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roster_manager)
SEED = 20260828


def next_pick_indices(picks):
    result = [None] * len(picks)
    next_by_roster = {}
    for index in range(len(picks) - 1, -1, -1):
        roster_id = picks[index]["roster_id"]
        if roster_id is not None:
            result[index] = next_by_roster.get(roster_id)
            next_by_roster[roster_id] = index
    return result


def validate(source, market, static_population, static_managers, roster_population, roster_managers):
    static_metric = _metric_state()
    roster_metric = _metric_state()
    differences = defaultdict(lambda: [0.0, 0])
    drafts = states = samples = survivals = 0
    for draft in _iter_drafts(market, (2024,)):
        drafts += 1
        picks = draft["picks"]
        identities = _manager_by_pick(source, draft["draft_id"])
        positions, weights, available = _choice_state(draft)
        static_denominator = np.zeros(len(picks))
        roster_denominator = np.zeros(len(picks))
        static_factors = np.zeros((len(picks), len(static_population)))
        roster_factors = np.zeros((len(picks), len(roster_population)))
        roster_counts = defaultdict(lambda: np.zeros(len(static_population), dtype=np.int64))
        pick_index_by_player = {}
        for index, pick in enumerate(picks):
            manager = identities.get(pick["pick_no"])
            static = static_managers.get(manager)
            static_factor = static["factor"] if static is not None and static["picks"] >= MINIMUM_MANAGER_PICKS else static_population
            roster = roster_managers.get(manager)
            counts = roster_counts[pick["roster_id"]]
            buckets = np.minimum(counts, 2)
            source_factors = roster["factor"] if roster is not None and roster["picks"] >= MINIMUM_MANAGER_PICKS else roster_population
            roster_factor = source_factors[np.arange(len(counts)), buckets]
            static_factors[index] = static_factor
            roster_factors[index] = roster_factor
            static_denominator[index] = np.sum(weights[available] * static_factor[positions[available]])
            roster_denominator[index] = np.sum(weights[available] * roster_factor[positions[available]])
            selected = draft["index"].get(pick["player_id"])
            if selected is not None:
                available[selected] = False
                counts[positions[selected]] += 1
                pick_index_by_player[selected] = index

        next_same = next_pick_indices(picks)
        available[:] = True
        for index, pick in enumerate(picks):
            selected = draft["index"].get(pick["player_id"])
            if selected is not None:
                available[selected] = False
            next_index = next_same[index]
            if next_index is None or next_index == index + 1:
                continue
            targets = np.flatnonzero(available)[:10]
            if not len(targets):
                continue
            states += 1
            future = np.arange(index + 1, next_index)
            target_positions = positions[targets]
            static_hazard = weights[targets][None, :] * static_factors[future][:, target_positions] / static_denominator[future, None]
            roster_hazard = weights[targets][None, :] * roster_factors[future][:, target_positions] / roster_denominator[future, None]
            for column, target in enumerate(targets):
                elimination = pick_index_by_player.get(int(target))
                if elimination is not None and elimination < next_index:
                    static_hazard[future > elimination, column] = 0.0
                    roster_hazard[future > elimination, column] = 0.0
            static_survival = np.prod(1 - np.clip(static_hazard, 0, 1), axis=0)
            roster_survival = np.prod(1 - np.clip(roster_hazard, 0, 1), axis=0)
            for column, target in enumerate(targets):
                elimination = pick_index_by_player.get(int(target))
                actual = float(elimination is None or elimination >= next_index)
                survivals += int(actual)
                static_probability = float(static_survival[column])
                roster_probability = float(roster_survival[column])
                _add_metric(static_metric, actual, static_probability)
                _add_metric(roster_metric, actual, roster_probability)
                differences[draft["draft_id"]][0] += (roster_probability - actual) ** 2 - (static_probability - actual) ** 2
                differences[draft["draft_id"]][1] += 1
                samples += 1
    return {
        "counts": {"drafts": drafts, "states": states, "samples": samples, "survival_rate": survivals / samples},
        "static": _finish_metric(static_metric),
        "roster": _finish_metric(roster_metric),
        "differences": differences,
    }


def main():
    market = sqlite3.connect(f"file:{roster_manager.MARKET}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{roster_manager.SOURCE}?mode=ro&immutable=1", uri=True)
    try:
        static_population, static_managers, _ = fit_manager_choice(source, market, (2021, 2022, 2023))
        roster_population, roster_managers = roster_manager.fit_roster_model(source, market, (2021, 2022, 2023))
        result = validate(source, market, static_population, static_managers, roster_population, roster_managers)
    finally:
        source.close()
        market.close()
    interval = _clustered_difference(result.pop("differences"), seed=SEED, samples=200)
    brier_improvement = result["static"]["brier"] - result["roster"]["brier"]
    false_safe_improvement = result["static"]["false_safe_rate"] - result["roster"]["false_safe_rate"]
    safe_coverage_loss = result["static"]["safe_coverage"] - result["roster"]["safe_coverage"]
    passed = brier_improvement >= 0.001 and interval["high"] < 0 and false_safe_improvement >= 0.02 and safe_coverage_loss <= 0.10
    output = {
        "experiment": "position-count manager impact on next-turn survival",
        "status": "research" if passed else "rejected",
        "train_seasons": [2021, 2022, 2023],
        "validation_seasons": [2024],
        "validation_2024_seen_diagnostic": True,
        "locked_test_loaded": False,
        **result,
        "gate": {
            "passes": passed,
            "brier_improvement": brier_improvement,
            "false_safe_improvement": false_safe_improvement,
            "safe_coverage_loss": safe_coverage_loss,
            "paired_roster_minus_static_brier": interval,
        },
        "limitations": ["conditional hazards follow the observed board-removal path", "2024 is a seen diagnostic", "2025 was not queried", "offline research only"],
    }
    Path(__file__).with_name("result.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"], "counts": output["counts"], "gate": output["gate"]}, indent=2))


if __name__ == "__main__":
    main()
