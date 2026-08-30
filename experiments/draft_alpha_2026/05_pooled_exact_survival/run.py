#!/usr/bin/env python3
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from ffsim.historical_sleeper.continuous_survival import (
    _add_metric,
    _aggregate_samples,
    _finish_metric,
    _metric_state,
)
from ffsim.historical_sleeper.opponent_model import _iter_drafts, _iter_survival_samples

MARKET_DB = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3"
MINIMUM_SUPPORT = 250
KEY_LENGTH = 3
EXPERIMENT = "pooled exact rank-gap-round survival"
POOLING_LIMITATION = (
    "position, scoring format, team count, and manager identity are intentionally pooled"
)
OUTPUT_PATH = Path(__file__).with_name("result.json")
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)


def pooled_cells(cells):
    result = defaultdict(lambda: [0, 0])
    for key, values in cells.items():
        pooled = result[key[:KEY_LENGTH]]
        pooled[0] += int(values[0])
        pooled[1] += int(values[1])
    return result


def probability(values):
    return (values[0] + 1) / (values[1] + 2)

def cell_key(target, sample):
    key = (int(target["rank"]), int(sample["gap"]), int(sample["round"]))
    return key + (str(target["position"]),) if KEY_LENGTH == 4 else key


def expected_calibration_error(metrics):
    count = metrics["count"]
    return sum(
        bucket["count"]
        * abs(bucket["mean_prediction"] - bucket["observed_rate"])
        / count
        for bucket in metrics["calibration"]
    )


def validate(connection, years, cells):
    metrics = _metric_state()
    drafts = states = total = supported = 0
    for draft in _iter_drafts(connection, years):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            for target in sample["players"]:
                total += 1
                values = cells.get(cell_key(target, sample))
                if values is None or values[1] < MINIMUM_SUPPORT:
                    continue
                _add_metric(metrics, float(target["survived"]), probability(values))
                supported += 1
    finished = _finish_metric(metrics)
    finished["expected_calibration_error"] = expected_calibration_error(finished)
    return {
        "counts": {
            "drafts": drafts,
            "states": states,
            "samples": total,
            "supported_samples": supported,
            "coverage": supported / total,
        },
        "metrics": finished,
    }


def main():
    connection = sqlite3.connect(f"file:{MARKET_DB}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        aggregates = {
            years: _aggregate_samples(connection, years)
            for years in ((2021,), (2021, 2022), (2021, 2022, 2023))
        }
        folds = {}
        for name, train_years, validation_years in FOLDS:
            cells = pooled_cells(aggregates[train_years]["cells"])
            result = validate(connection, validation_years, cells)
            metrics = result["metrics"]
            gate = {
                "coverage": result["counts"]["coverage"],
                "brier": metrics["brier"],
                "expected_calibration_error": metrics["expected_calibration_error"],
                "false_safe_rate": metrics["false_safe_rate"],
            }
            gate["passes"] = (
                gate["coverage"] >= 0.70
                and gate["brier"] <= 0.12
                and gate["expected_calibration_error"] <= 0.05
                and gate["false_safe_rate"] <= 0.10
            )
            folds[name] = {
                "train_years": list(train_years),
                "validation_years": list(validation_years),
                "training_cells": len(cells),
                **result,
                "gate": gate,
            }
        final_cells = pooled_cells(aggregates[(2021, 2022, 2023)]["cells"])
    finally:
        connection.close()

    elite_key = (2, 18, 1, "RB") if KEY_LENGTH == 4 else (2, 18, 1)
    elite = final_cells.get(elite_key, (0, 0))
    elite_probability = probability(elite)
    passed = (
        all(fold["gate"]["passes"] for fold in folds.values())
        and elite[1] >= 1_000
        and elite_probability < 0.01
    )
    supported_cells = [
        {
            "key": list(key),
            "successes": values[0],
            "count": values[1],
            "probability": probability(values),
        }
        for key, values in sorted(final_cells.items())
        if values[1] >= MINIMUM_SUPPORT
    ]
    result = {
        "experiment": EXPERIMENT,
        "status": "research" if passed else "rejected",
        "minimum_support": MINIMUM_SUPPORT,
        "prior": [1, 1],
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "folds": folds,
        "gate": {
            "passes": passed,
            "elite_rank2_gap18_round1": {
                "successes": elite[0],
                "count": elite[1],
                "probability": elite_probability,
            },
        },
        "supported_cells": supported_cells,
        "limitations": [
            "offline exact-cell evidence only",
            POOLING_LIMITATION,
            "unsupported cells return unavailable without interpolation or fallback",
            "2024 and 2025 were not queried",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    OUTPUT_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "gate": result["gate"],
        "folds": {name: fold["gate"] for name, fold in folds.items()},
        "supported_cells": len(supported_cells),
    }, indent=2))


if __name__ == "__main__":
    main()
