#!/usr/bin/env python3
import importlib.util
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

from ffsim.historical_sleeper.continuous_survival import (
    _add_metric,
    _finish_metric,
    _metric_state,
)
from ffsim.historical_sleeper.opponent_model import (
    _clustered_difference,
    _iter_drafts,
    _iter_survival_samples,
)

BASE = Path(__file__).parents[1] / "02_manager_personalization/run.py"
spec = importlib.util.spec_from_file_location("manager_personalization", BASE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.POPULATION_CORRECTED = True
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


def validate(source, market, global_factor, managers):
    population_metric = _metric_state()
    personalized_metric = _metric_state()
    differences = defaultdict(lambda: [0.0, 0])
    drafts = states = samples = 0
    actual_survivals = reference_survivals = reference_samples = 0
    for draft in _iter_drafts(market, (2024,)):
        drafts += 1
        for reference in _iter_survival_samples(draft):
            if reference["gap"] == 0:
                continue
            reference_samples += len(reference["players"])
            reference_survivals += sum(
                int(target["survived"]) for target in reference["players"]
            )
        picks = draft["picks"]
        identities = module.manager_by_pick(source, draft["draft_id"])
        positions, weights, available = module.state(draft)
        population_denominator = np.zeros(len(picks))
        personalized_denominator = np.zeros(len(picks))
        personalized_factors = np.zeros((len(picks), len(module.POSITIONS)))
        pick_index_by_player = {}
        for index, pick in enumerate(picks):
            manager = identities.get(pick["pick_no"])
            record = managers.get(manager)
            factors = (
                record["factor"]
                if record is not None and record["picks"] >= module.MINIMUM_MANAGER_PICKS
                else global_factor
            )
            personalized_factors[index] = factors
            population_denominator[index] = np.sum(
                weights[available] * global_factor[positions[available]]
            )
            personalized_denominator[index] = np.sum(
                weights[available] * factors[positions[available]]
            )
            selected = draft["index"].get(pick["player_id"])
            if selected is not None:
                available[selected] = False
                pick_index_by_player[selected] = index

        next_same = next_pick_indices(picks)
        available[:] = True
        for index, pick in enumerate(picks):
            selected = draft["index"].get(pick["player_id"])
            if selected is not None:
                available[selected] = False
            next_index = next_same[index]
            if next_index is None:
                continue
            targets = np.flatnonzero(available)[:10]
            if not len(targets):
                continue
            future = np.arange(index + 1, next_index)
            if not len(future):
                continue
            states += 1
            target_positions = positions[targets]
            population_numerator = weights[targets] * global_factor[target_positions]
            population_hazard = population_numerator[None, :] / population_denominator[future, None]
            personalized_numerator = (
                weights[targets][None, :]
                * personalized_factors[future][:, target_positions]
            )
            personalized_hazard = personalized_numerator / personalized_denominator[future, None]
            for column, target in enumerate(targets):
                elimination = pick_index_by_player.get(int(target))
                if elimination is not None and elimination < next_index:
                    population_hazard[future > elimination, column] = 0.0
                    personalized_hazard[future > elimination, column] = 0.0
            population_survival = np.prod(1 - np.clip(population_hazard, 0, 1), axis=0)
            personalized_survival = np.prod(1 - np.clip(personalized_hazard, 0, 1), axis=0)
            for column, target in enumerate(targets):
                elimination = pick_index_by_player.get(int(target))
                actual = float(elimination is None or elimination >= next_index)
                actual_survivals += int(actual)
                population_probability = float(population_survival[column])
                personalized_probability = float(personalized_survival[column])
                _add_metric(population_metric, actual, population_probability)
                _add_metric(personalized_metric, actual, personalized_probability)
                differences[draft["draft_id"]][0] += (
                    (personalized_probability - actual) ** 2
                    - (population_probability - actual) ** 2
                )
                differences[draft["draft_id"]][1] += 1
                samples += 1
    if samples != reference_samples or actual_survivals != reference_survivals:
        raise RuntimeError(
            "survival labels differ from the canonical next-turn sample iterator"
        )
    return {
        "counts": {"drafts": drafts, "states": states, "samples": samples},
        "population": _finish_metric(population_metric),
        "personalized": _finish_metric(personalized_metric),
        "differences": differences,
        "label_audit": {
            "definition": "not selected after current pick and before next same-roster pick",
            "samples": samples,
            "survivals": actual_survivals,
            "survival_rate": actual_survivals / samples,
            "matches_canonical_iterator": True,
        },
    }


def main():
    market = sqlite3.connect(f"file:{module.MARKET_DB}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{module.SOURCE_DB}?mode=ro&immutable=1", uri=True)
    try:
        global_factor, managers, training_counts = module.fit(
            source, market, (2021, 2022, 2023)
        )
        validation = validate(source, market, global_factor, managers)
    finally:
        source.close()
        market.close()
    interval = _clustered_difference(
        validation.pop("differences"), seed=SEED, samples=200
    )
    population = validation["population"]
    personalized = validation["personalized"]
    brier_improvement = population["brier"] - personalized["brier"]
    false_safe_improvement = (
        population["false_safe_rate"] - personalized["false_safe_rate"]
    )
    safe_coverage_loss = population["safe_coverage"] - personalized["safe_coverage"]
    passed = (
        brier_improvement >= 0.001
        and interval["high"] < 0
        and false_safe_improvement >= 0.02
        and safe_coverage_loss <= 0.10
    )
    result = {
        "experiment": "manager residual impact on exact player survival",
        "status": "research" if passed else "rejected",
        "train_seasons": [2021, 2022, 2023],
        "validation_seasons": [2024],
        "validation_2024_seen_diagnostic": True,
        "locked_test_loaded": False,
        "training_counts": training_counts,
        "validation": validation,
        "gate": {
            "passes": passed,
            "brier_improvement": brier_improvement,
            "false_safe_improvement": false_safe_improvement,
            "safe_coverage_loss": safe_coverage_loss,
            "paired_brier_difference": interval,
        },
        "limitations": [
            "2024 is a seen downstream diagnostic year",
            "conditional hazards follow the observed board-removal path",
            "marginal player hazards do not model joint tier survival",
            "2025 was not queried for this experiment",
            "no live opponent callback, VONA, WORP, rollout, API, or UI integration",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": result["status"], "gate": result["gate"], "counts": validation["counts"]}, indent=2))


if __name__ == "__main__":
    main()
