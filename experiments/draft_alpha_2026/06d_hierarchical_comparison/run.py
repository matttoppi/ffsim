#!/usr/bin/env python3
import importlib.util
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

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

BASE = Path(__file__).parents[1] / "06_hierarchical_survival/run.py"
spec = importlib.util.spec_from_file_location("hierarchical_survival", BASE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SEED = 20260828
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)


def validate(connection, years, model):
    hierarchical = _metric_state()
    baseline = _metric_state()
    differences = defaultdict(lambda: [0.0, 0])
    drafts = samples = 0
    for draft in _iter_drafts(connection, years):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            for target in sample["players"]:
                key = (
                    int(target["rank"]),
                    int(sample["gap"]),
                    int(sample["round"]),
                    str(target["position"]),
                )
                actual = float(target["survived"])
                predicted = module.probability(model, key)
                pooled = model[0].get(key[:3], (0, 0))
                base_probability = (pooled[0] + 2) / (pooled[1] + 4)
                _add_metric(hierarchical, actual, predicted)
                _add_metric(baseline, actual, base_probability)
                differences[draft["draft_id"]][0] += (
                    (predicted - actual) ** 2 - (base_probability - actual) ** 2
                )
                differences[draft["draft_id"]][1] += 1
                samples += 1
    return {
        "counts": {"drafts": drafts, "samples": samples},
        "hierarchical": _finish_metric(hierarchical),
        "baseline": _finish_metric(baseline),
        "differences": differences,
    }


def main():
    connection = sqlite3.connect(f"file:{module.MARKET_DB}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        aggregates = {
            years: module._aggregate_samples(connection, years)
            for years in ((2021,), (2021, 2022))
        }
        folds = {}
        for index, (name, train_years, validation_years) in enumerate(FOLDS):
            model = module.tables(aggregates[train_years]["cells"])
            result = validate(connection, validation_years, model)
            interval = _clustered_difference(
                result.pop("differences"), seed=SEED + index, samples=200
            )
            improvement = result["baseline"]["brier"] - result["hierarchical"]["brier"]
            gate = {
                "brier_improvement": improvement,
                "paired_brier_difference": interval,
                "passes": improvement >= 0.001 and interval["high"] < 0,
            }
            folds[name] = {
                "train_years": list(train_years),
                "validation_years": list(validation_years),
                **result,
                "gate": gate,
            }
    finally:
        connection.close()
    passed = all(fold["gate"]["passes"] for fold in folds.values())
    result = {
        "experiment": "frozen hierarchical survival versus exact population baseline",
        "status": "research" if passed else "rejected",
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "comparator": "Beta(2,2) exact rank-gap-round",
        "folds": folds,
        "gate": {"passes": passed},
        "limitations": [
            "comparison uses rolling development folds only",
            "2024 and 2025 were not queried",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "folds": {name: fold["gate"] for name, fold in folds.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
