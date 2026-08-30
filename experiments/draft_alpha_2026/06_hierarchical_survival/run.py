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
SHRINKAGE = 100.0
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)


def tables(cells):
    pooled = defaultdict(lambda: [0, 0])
    positioned = defaultdict(lambda: [0, 0])
    total = [0, 0]
    for key, values in cells.items():
        for target in (pooled[key[:3]], positioned[key[:4]], total):
            target[0] += int(values[0])
            target[1] += int(values[1])
    return pooled, positioned, total


def beta_probability(values):
    return (values[0] + 1) / (values[1] + 2)


def probability(model, key):
    pooled, positioned, total = model
    pooled_values = pooled.get(key[:3])
    prior = beta_probability(pooled_values if pooled_values is not None else total)
    direct = positioned.get(key, (0, 0))
    return (direct[0] + SHRINKAGE * prior) / (direct[1] + SHRINKAGE)


def expected_calibration_error(metrics):
    return sum(
        bucket["count"] * abs(bucket["mean_prediction"] - bucket["observed_rate"])
        for bucket in metrics["calibration"]
    ) / metrics["count"]


def validate(connection, years, model):
    metrics = _metric_state()
    drafts = states = samples = 0
    for draft in _iter_drafts(connection, years):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            for target in sample["players"]:
                key = (
                    int(target["rank"]),
                    int(sample["gap"]),
                    int(sample["round"]),
                    str(target["position"]),
                )
                _add_metric(metrics, float(target["survived"]), probability(model, key))
                samples += 1
    finished = _finish_metric(metrics)
    finished["expected_calibration_error"] = expected_calibration_error(finished)
    return {
        "counts": {"drafts": drafts, "states": states, "samples": samples, "coverage": 1.0},
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
            model = tables(aggregates[train_years]["cells"])
            result = validate(connection, validation_years, model)
            metrics = result["metrics"]
            gate = {
                "coverage": result["counts"]["coverage"],
                "brier": metrics["brier"],
                "expected_calibration_error": metrics["expected_calibration_error"],
                "false_safe_rate": metrics["false_safe_rate"],
            }
            gate["passes"] = (
                gate["coverage"] == 1.0
                and gate["brier"] <= 0.12
                and gate["expected_calibration_error"] <= 0.05
                and gate["false_safe_rate"] <= 0.10
            )
            folds[name] = {
                "train_years": list(train_years),
                "validation_years": list(validation_years),
                **result,
                "gate": gate,
            }
        final_model = tables(aggregates[(2021, 2022, 2023)]["cells"])
    finally:
        connection.close()

    elite_key = (2, 18, 1, "RB")
    elite_direct = final_model[1].get(elite_key, (0, 0))
    elite_probability = probability(final_model, elite_key)
    passed = (
        all(fold["gate"]["passes"] for fold in folds.values())
        and elite_direct[1] >= 1_000
        and elite_probability < 0.01
    )
    supported_keys = sorted(final_model[1])
    result = {
        "experiment": "hierarchical position-aware survival",
        "status": "research" if passed else "rejected",
        "shrinkage_observations": SHRINKAGE,
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "folds": folds,
        "gate": {
            "passes": passed,
            "elite_rank2_rb_gap18_round1": {
                "successes": elite_direct[0],
                "count": elite_direct[1],
                "probability": elite_probability,
            },
        },
        "model": {
            "global": final_model[2],
            "pooled_cells": [
                {"key": list(key), "successes": values[0], "count": values[1]}
                for key, values in sorted(final_model[0].items())
            ],
            "position_cells": [
                {"key": list(key), "successes": final_model[1][key][0], "count": final_model[1][key][1]}
                for key in supported_keys
            ],
        },
        "limitations": [
            "offline population survival research only",
            "scoring format, team count, and manager identity are pooled",
            "hierarchical probabilities do not model joint tier survival",
            "2024 and 2025 were not queried",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "gate": result["gate"],
        "folds": {name: fold["gate"] for name, fold in folds.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
