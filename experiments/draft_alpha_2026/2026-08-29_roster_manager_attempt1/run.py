#!/usr/bin/env python3
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

from ffsim.historical_sleeper.manager_choice import (
    MINIMUM_MANAGER_PICKS,
    POSITIONS,
    SHRINKAGE,
    _choice_state,
    _manager_by_pick,
    fit_manager_choice,
)
from ffsim.historical_sleeper.opponent_model import _clustered_difference, _iter_drafts

MARKET = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3"
SOURCE = Path.home() / ".cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3"
SEED = 20260828
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)


def phase(round_number):
    return 0 if round_number <= 5 else 1 if round_number <= 10 else 2


def fit_round_model(source, market, years):
    observed = np.zeros((3, len(POSITIONS)))
    expected = np.zeros((3, len(POSITIONS)))
    managers = defaultdict(
        lambda: {
            "observed": np.zeros((3, len(POSITIONS))),
            "expected": np.zeros((3, len(POSITIONS))),
            "picks": 0,
        }
    )
    for draft in _iter_drafts(market, years):
        identities = _manager_by_pick(source, draft["draft_id"])
        positions, weights, available = _choice_state(draft)
        for pick in draft["picks"]:
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                continue
            distribution = weights * available
            distribution /= distribution.sum()
            opportunity = np.bincount(
                positions, weights=distribution, minlength=len(POSITIONS)
            )
            bucket = phase(math.ceil(pick["pick_no"] / draft["team_count"]))
            observed[bucket, positions[selected]] += 1
            expected[bucket] += opportunity
            manager = identities.get(pick["pick_no"])
            if manager:
                record = managers[manager]
                record["observed"][bucket, positions[selected]] += 1
                record["expected"][bucket] += opportunity
                record["picks"] += 1
            available[selected] = False
    observed_rate = observed / observed.sum(axis=1, keepdims=True)
    expected_rate = expected / expected.sum(axis=1, keepdims=True)
    population = (observed + 1) / (expected + 1)
    fitted = {
        manager: {
            "picks": record["picks"],
            "factor": (
                (record["observed"] + SHRINKAGE * observed_rate)
                / (record["expected"] + SHRINKAGE * expected_rate)
            ),
        }
        for manager, record in managers.items()
    }
    return population, fitted


def adjusted(weights, available, positions, factors):
    result = weights * available * factors[positions]
    return result / result.sum()


def validate(source, market, years, static_population, static_managers, phase_population, phase_managers):
    static_loss = phase_loss = picks = 0
    differences = defaultdict(lambda: [0.0, 0])
    for draft in _iter_drafts(market, years):
        identities = _manager_by_pick(source, draft["draft_id"])
        positions, weights, available = _choice_state(draft)
        for pick in draft["picks"]:
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                continue
            manager = identities.get(pick["pick_no"])
            static = static_managers.get(manager)
            phased = phase_managers.get(manager)
            if static is None or static["picks"] < MINIMUM_MANAGER_PICKS or phased is None:
                available[selected] = False
                continue
            bucket = phase(math.ceil(pick["pick_no"] / draft["team_count"]))
            static_probabilities = adjusted(
                weights, available, positions, static["factor"]
            )
            phase_probabilities = adjusted(
                weights, available, positions, phased["factor"][bucket]
            )
            static_pick_loss = -math.log(max(static_probabilities[selected], 1e-15))
            phase_pick_loss = -math.log(max(phase_probabilities[selected], 1e-15))
            static_loss += static_pick_loss
            phase_loss += phase_pick_loss
            differences[draft["draft_id"]][0] += phase_pick_loss - static_pick_loss
            differences[draft["draft_id"]][1] += 1
            picks += 1
            available[selected] = False
    return {
        "picks": picks,
        "static_log_loss": static_loss / picks,
        "phase_log_loss": phase_loss / picks,
        "improvement": (static_loss - phase_loss) / picks,
        "differences": differences,
    }


def main():
    market = sqlite3.connect(f"file:{MARKET}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{SOURCE}?mode=ro&immutable=1", uri=True)
    try:
        folds = {}
        for index, (name, train_years, validation_years) in enumerate(FOLDS):
            static_population, static_managers, _ = fit_manager_choice(
                source, market, train_years
            )
            phase_population, phase_managers = fit_round_model(
                source, market, train_years
            )
            result = validate(
                source,
                market,
                validation_years,
                static_population,
                static_managers,
                phase_population,
                phase_managers,
            )
            interval = _clustered_difference(
                result.pop("differences"), seed=SEED + index, samples=200
            )
            gate = {
                "improvement": result["improvement"],
                "paired_phase_minus_static": interval,
                "passes": result["improvement"] >= 0.005 and interval["high"] < 0,
            }
            folds[name] = {**result, "gate": gate}
    finally:
        source.close()
        market.close()
    passed = all(fold["gate"]["passes"] for fold in folds.values())
    output = {
        "experiment": "round-phase manager position residual",
        "status": "research" if passed else "rejected",
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "folds": folds,
        "gate": {"passes": passed},
        "limitations": [
            "round phase is a coarse roster-state proxy",
            "2024 and 2025 were not queried",
            "offline research only",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": output["status"],
        "folds": {name: fold["gate"] for name, fold in folds.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
