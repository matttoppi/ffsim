#!/usr/bin/env python3
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

from ffsim.historical_sleeper.opponent_model import _clustered_difference, _iter_drafts

MARKET_DB = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3"
SOURCE_DB = Path.home() / ".cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")
POSITION_INDEX = {position: index for index, position in enumerate(POSITIONS)}
SHRINKAGE = 50.0
MINIMUM_MANAGER_PICKS = 20
SEED = 20260828
POPULATION_CORRECTED = False
OUTPUT_PATH = Path(__file__).with_name("result.json")
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)


def manager_by_pick(source, draft_id):
    return dict(source.execute(
        "SELECT pick_no, picked_by FROM draft_picks WHERE draft_id = ?", (draft_id,)
    ))


def state(draft):
    positions = np.asarray([
        POSITION_INDEX.get(str(value or "UNKNOWN").upper(), POSITION_INDEX["UNKNOWN"])
        for value in draft["positions"]
    ])
    return positions, 1.0 / np.maximum(draft["adp"], 1e-12), np.ones(len(positions), bool)


def fit(source, market, years):
    expected = np.zeros(len(POSITIONS))
    observed = np.zeros(len(POSITIONS))
    managers = defaultdict(lambda: [np.zeros(len(POSITIONS)), np.zeros(len(POSITIONS)), 0])
    counts = defaultdict(int)
    for draft in _iter_drafts(market, years):
        counts["drafts"] += 1
        identities = manager_by_pick(source, draft["draft_id"])
        positions, weights, available = state(draft)
        for pick in draft["picks"]:
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                counts["missing_board_picks"] += 1
                continue
            distribution = weights * available
            distribution /= distribution.sum()
            opportunity = np.bincount(
                positions, weights=distribution, minlength=len(POSITIONS)
            )
            selected_position = positions[selected]
            observed[selected_position] += 1
            expected += opportunity
            manager = identities.get(pick["pick_no"])
            if manager:
                record = managers[manager]
                record[0][selected_position] += 1
                record[1] += opportunity
                record[2] += 1
            else:
                counts["missing_manager_picks"] += 1
            counts["picks"] += 1
            available[selected] = False
    expected_rate = expected / expected.sum()
    observed_rate = observed / observed.sum()
    prior_observed = observed_rate if POPULATION_CORRECTED else expected_rate
    global_factor = (
        (observed + 1) / (expected + 1)
        if POPULATION_CORRECTED
        else np.ones(len(POSITIONS))
    )
    model = {
        manager: {
            "picks": record[2],
            "factor": ((record[0] + SHRINKAGE * prior_observed) /
                       (record[1] + SHRINKAGE * expected_rate)),
        }
        for manager, record in managers.items()
    }
    counts["managers"] = len(model)
    counts["eligible_managers"] = sum(
        record["picks"] >= MINIMUM_MANAGER_PICKS for record in model.values()
    )
    return global_factor, model, dict(counts)


def probabilities(weights, available, positions, factors):
    result = weights * available * factors[positions]
    return result / result.sum()


def metric():
    return {"count": 0, "log_loss": 0.0, "brier": 0.0, "top_5": 0}


def add(values, distribution, selected):
    target = max(float(distribution[selected]), 1e-15)
    values["count"] += 1
    values["log_loss"] -= math.log(target)
    values["brier"] += float(distribution @ distribution - 2 * target + 1)
    values["top_5"] += int(selected in np.argsort(-distribution)[:5])


def finish(values):
    count = values["count"]
    return {
        "count": count,
        "log_loss": values["log_loss"] / count,
        "multiclass_brier": values["brier"] / count,
        "top_5_accuracy": values["top_5"] / count,
    }


def validate(source, market, years, global_factor, managers):
    metrics = {name: metric() for name in (
        "population_all", "personalized_all", "population_seen", "personalized_seen"
    )}
    differences = defaultdict(lambda: [0.0, 0])
    counts = defaultdict(int)
    buckets = defaultdict(lambda: [0, 0.0])
    for draft in _iter_drafts(market, years):
        counts["drafts"] += 1
        identities = manager_by_pick(source, draft["draft_id"])
        positions, weights, available = state(draft)
        for pick in draft["picks"]:
            selected = draft["index"].get(pick["player_id"])
            if selected is None:
                counts["missing_board_picks"] += 1
                continue
            population = probabilities(weights, available, positions, global_factor)
            record = managers.get(identities.get(pick["pick_no"]))
            eligible = record is not None and record["picks"] >= MINIMUM_MANAGER_PICKS
            personalized = probabilities(
                weights, available, positions, record["factor"]
            ) if eligible else population
            add(metrics["population_all"], population, selected)
            add(metrics["personalized_all"], personalized, selected)
            if eligible:
                add(metrics["population_seen"], population, selected)
                add(metrics["personalized_seen"], personalized, selected)
                difference = -math.log(max(personalized[selected], 1e-15)) + math.log(
                    max(population[selected], 1e-15)
                )
                differences[draft["draft_id"]][0] += difference
                differences[draft["draft_id"]][1] += 1
                bucket = "20-49" if record["picks"] < 50 else "50-99" if record["picks"] < 100 else "100+"
                buckets[bucket][0] += 1
                buckets[bucket][1] += difference
                counts["seen_manager_picks"] += 1
            counts["picks"] += 1
            available[selected] = False
    if not counts["seen_manager_picks"]:
        raise RuntimeError("validation has no eligible seen managers")
    return {
        **{name: finish(values) for name, values in metrics.items()},
        "counts": {
            **dict(counts),
            "seen_manager_coverage": counts["seen_manager_picks"] / counts["picks"],
        },
        "support_buckets": {
            name: {"picks": value[0], "mean_log_loss_difference": value[1] / value[0]}
            for name, value in sorted(buckets.items())
        },
        "differences": differences,
    }


def main():
    market = sqlite3.connect(f"file:{MARKET_DB}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro&immutable=1", uri=True)
    try:
        folds = {}
        for index, (name, train_years, validation_years) in enumerate(FOLDS):
            global_factor, managers, training_counts = fit(source, market, train_years)
            result = validate(source, market, validation_years, global_factor, managers)
            interval = _clustered_difference(
                result.pop("differences"), seed=SEED + index, samples=200
            )
            improvement = result["population_seen"]["log_loss"] - result["personalized_seen"]["log_loss"]
            all_difference = result["personalized_all"]["log_loss"] - result["population_all"]["log_loss"]
            gate = {
                "seen_manager_log_loss_improvement": improvement,
                "all_pick_log_loss_difference": all_difference,
                "paired_seen_log_loss_difference": interval,
                "passes": improvement >= 0.005 and interval["high"] < 0 and all_difference <= 0.001,
            }
            folds[name] = {
                "train_years": list(train_years),
                "validation_years": list(validation_years),
                "training_counts": training_counts,
                **result,
                "gate": gate,
            }
    finally:
        source.close()
        market.close()
    passed = all(fold["gate"]["passes"] for fold in folds.values())
    output = {
        "experiment": (
            "manager residual beyond population position correction"
            if POPULATION_CORRECTED
            else "manager position personalization over inverse ADP"
        ),
        "status": "research" if passed else "rejected",
        "shrinkage_opportunities": SHRINKAGE,
        "population_comparator": (
            "inverse_adp_with_population_position_factor"
            if POPULATION_CORRECTED
            else "inverse_adp"
        ),
        "minimum_manager_picks": MINIMUM_MANAGER_PICKS,
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "folds": folds,
        "gate": {"passes": passed},
        "limitations": [
            "offline opponent-choice research only",
            "manager effect is position preference, not player identity affinity",
            "evaluation covers only managers observed in prior seasons",
            "2024 and 2025 were not queried",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": output["status"],
        "folds": {name: {"counts": fold["counts"], "gate": fold["gate"]}
                  for name, fold in folds.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
