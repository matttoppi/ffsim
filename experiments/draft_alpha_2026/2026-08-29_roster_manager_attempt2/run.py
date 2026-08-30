#!/usr/bin/env python3
import importlib.util
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

PRIOR = Path(__file__).parents[1] / "2026-08-29_roster_manager_attempt1/run.py"
spec = importlib.util.spec_from_file_location("round_manager", PRIOR)
round_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(round_manager)
MARKET = round_manager.MARKET
SOURCE = round_manager.SOURCE
SEED = round_manager.SEED
FOLDS = round_manager.FOLDS


def fit_roster_model(source, market, years):
    observed = np.zeros((len(POSITIONS), 3))
    expected = np.zeros((len(POSITIONS), 3))
    managers = defaultdict(
        lambda: {
            "observed": np.zeros((len(POSITIONS), 3)),
            "expected": np.zeros((len(POSITIONS), 3)),
            "picks": 0,
        }
    )
    for draft in _iter_drafts(market, years):
        identities = _manager_by_pick(source, draft["draft_id"])
        positions, weights, available = _choice_state(draft)
        roster_counts = defaultdict(lambda: np.zeros(len(POSITIONS), dtype=np.int64))
        for pick in draft["picks"]:
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                continue
            distribution = weights * available
            distribution /= distribution.sum()
            opportunity = np.bincount(
                positions, weights=distribution, minlength=len(POSITIONS)
            )
            roster_id = pick["roster_id"]
            counts = roster_counts[roster_id]
            buckets = np.minimum(counts, 2)
            for position, mass in enumerate(opportunity):
                expected[position, buckets[position]] += mass
            selected_position = positions[selected]
            selected_bucket = buckets[selected_position]
            observed[selected_position, selected_bucket] += 1
            manager = identities.get(pick["pick_no"])
            if manager:
                record = managers[manager]
                for position, mass in enumerate(opportunity):
                    record["expected"][position, buckets[position]] += mass
                record["observed"][selected_position, selected_bucket] += 1
                record["picks"] += 1
            counts[selected_position] += 1
            available[selected] = False
    observed_rate = observed / observed.sum()
    expected_rate = expected / expected.sum()
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
    result = weights * available * factors
    return result / result.sum()


def validate(source, market, years, static_managers, phase_managers, roster_managers):
    phase_loss = roster_loss = picks = 0
    differences = defaultdict(lambda: [0.0, 0])
    for draft in _iter_drafts(market, years):
        identities = _manager_by_pick(source, draft["draft_id"])
        positions, weights, available = _choice_state(draft)
        roster_counts = defaultdict(lambda: np.zeros(len(POSITIONS), dtype=np.int64))
        for pick in draft["picks"]:
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                continue
            manager = identities.get(pick["pick_no"])
            static = static_managers.get(manager)
            phased = phase_managers.get(manager)
            roster = roster_managers.get(manager)
            roster_id = pick["roster_id"]
            counts = roster_counts[roster_id]
            if (
                static is not None
                and static["picks"] >= MINIMUM_MANAGER_PICKS
                and phased is not None
                and roster is not None
            ):
                round_bucket = round_manager.phase(
                    math.ceil(pick["pick_no"] / draft["team_count"])
                )
                phase_factors = phased["factor"][round_bucket][positions]
                buckets = np.minimum(counts, 2)
                roster_factors = roster["factor"][positions, buckets[positions]]
                phase_probabilities = adjusted(
                    weights, available, positions, phase_factors
                )
                roster_probabilities = adjusted(
                    weights, available, positions, roster_factors
                )
                phase_pick_loss = -math.log(
                    max(phase_probabilities[selected], 1e-15)
                )
                roster_pick_loss = -math.log(
                    max(roster_probabilities[selected], 1e-15)
                )
                phase_loss += phase_pick_loss
                roster_loss += roster_pick_loss
                differences[draft["draft_id"]][0] += (
                    roster_pick_loss - phase_pick_loss
                )
                differences[draft["draft_id"]][1] += 1
                picks += 1
            counts[positions[selected]] += 1
            available[selected] = False
    return {
        "picks": picks,
        "phase_log_loss": phase_loss / picks,
        "roster_log_loss": roster_loss / picks,
        "improvement": (phase_loss - roster_loss) / picks,
        "differences": differences,
    }


def main():
    market = sqlite3.connect(f"file:{MARKET}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{SOURCE}?mode=ro&immutable=1", uri=True)
    try:
        folds = {}
        for index, (name, train_years, validation_years) in enumerate(FOLDS):
            _, static_managers, _ = fit_manager_choice(source, market, train_years)
            _, phase_managers = round_manager.fit_round_model(
                source, market, train_years
            )
            _, roster_managers = fit_roster_model(source, market, train_years)
            result = validate(
                source,
                market,
                validation_years,
                static_managers,
                phase_managers,
                roster_managers,
            )
            interval = _clustered_difference(
                result.pop("differences"), seed=SEED + index, samples=200
            )
            gate = {
                "improvement": result["improvement"],
                "paired_roster_minus_phase": interval,
                "passes": result["improvement"] >= 0.005 and interval["high"] < 0,
            }
            folds[name] = {**result, "gate": gate}
    finally:
        source.close()
        market.close()
    passed = all(fold["gate"]["passes"] for fold in folds.values())
    output = {
        "experiment": "position-count manager residual",
        "status": "research" if passed else "rejected",
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "folds": folds,
        "gate": {"passes": passed},
        "limitations": [
            "position counts do not encode league-specific starting slots",
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
