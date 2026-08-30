#!/usr/bin/env python3
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from ffsim.historical_sleeper.continuous_survival import (
    _add_metric,
    _aggregate_samples,
    _baseline_table,
    _cell_support,
    _finish_metric,
    _metric_state,
)
from ffsim.historical_sleeper.opponent_model import (
    _clustered_difference,
    _iter_drafts,
    _iter_survival_samples,
)

MARKET_DB = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3"
SEED = 20260828
BOOTSTRAP_SAMPLES = 200
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")
SCORING_FORMATS = ("STD", "HALF_PPR", "PPR")
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)


def features(rank, gap, round_, position, scoring_format, team_count):
    position = position if position in POSITIONS else "UNKNOWN"
    scoring_format = scoring_format if scoring_format in SCORING_FORMATS else "STD"
    return np.asarray(
        [
            rank,
            gap,
            round_,
            team_count,
            *(float(position == value) for value in POSITIONS),
            *(float(scoring_format == value) for value in SCORING_FORMATS),
        ],
        dtype=np.float64,
    )


def fit_model(cells):
    rows = []
    labels = []
    weights = []
    for key in sorted(cells):
        successes, count = cells[key]
        failures = count - successes
        row = features(*key)
        if successes:
            rows.append(row)
            labels.append(1)
            weights.append(successes)
        if failures:
            rows.append(row)
            labels.append(0)
            weights.append(failures)
    model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=100,
        max_leaf_nodes=15,
        max_depth=3,
        min_samples_leaf=20,
        l2_regularization=1.0,
        monotonic_cst=[1, -1, 0, 0, *([0] * (len(POSITIONS) + len(SCORING_FORMATS)))],
        random_state=SEED,
    )
    model.fit(np.asarray(rows), np.asarray(labels), sample_weight=np.asarray(weights))
    return model


def probability(model, rank, gap, round_, position, scoring_format, team_count):
    row = features(rank, gap, round_, position, scoring_format, team_count)
    return float(model.predict_proba(row.reshape(1, -1))[0, 1])


def validate(connection, years, model, baseline, validation_cells):
    model_state = _metric_state()
    baseline_state = _metric_state()
    differences = defaultdict(lambda: [0.0, 0])
    drafts = states = samples = 0
    keys = sorted(validation_cells)
    rows = np.asarray([features(*key) for key in keys])
    prediction_cache = dict(zip(keys, model.predict_proba(rows)[:, 1]))
    for draft in _iter_drafts(connection, years):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            for target in sample["players"]:
                rank = int(target["rank"])
                gap = int(sample["gap"])
                round_ = int(sample["round"])
                actual = float(target["survived"])
                key = (
                    rank,
                    gap,
                    round_,
                    target["position"],
                    sample["scoring_format"],
                    sample["team_count"],
                )
                predicted = float(prediction_cache[key])
                base_successes, base_count = baseline.get((rank, gap, round_), (0.0, 0))
                base_probability = (base_successes + 2.0) / (base_count + 4.0)
                _add_metric(model_state, actual, predicted)
                _add_metric(baseline_state, actual, base_probability)
                differences[draft["draft_id"]][0] += (
                    (predicted - actual) ** 2 - (base_probability - actual) ** 2
                )
                differences[draft["draft_id"]][1] += 1
                samples += 1
    return {
        "counts": {"drafts": drafts, "states": states, "samples": samples},
        "model": _finish_metric(model_state),
        "baseline": _finish_metric(baseline_state),
        "draft_differences": differences,
    }


def main():
    connection = sqlite3.connect(f"file:{MARKET_DB}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        aggregates = {
            years: _aggregate_samples(connection, years)
            for years in (
                (2021,),
                (2022,),
                (2023,),
                (2021, 2022),
                (2021, 2022, 2023),
            )
        }
        folds = {}
        pooled = defaultdict(lambda: [0.0, 0])
        for name, train_years, validation_years in FOLDS:
            training = aggregates[train_years]
            model = fit_model(training["cells"])
            validation = validate(
                connection,
                validation_years,
                model,
                _baseline_table(training["cells"]),
                aggregates[validation_years]["cells"],
            )
            for draft_id, values in validation.pop("draft_differences").items():
                pooled[draft_id][0] += values[0]
                pooled[draft_id][1] += values[1]
            model_metrics = validation["model"]
            baseline_metrics = validation["baseline"]
            gate = {
                "brier_improvement": baseline_metrics["brier"] - model_metrics["brier"],
                "false_safe_improvement": baseline_metrics["false_safe_rate"] - model_metrics["false_safe_rate"],
                "safe_coverage_loss": baseline_metrics["safe_coverage"] - model_metrics["safe_coverage"],
            }
            gate["passes"] = (
                gate["brier_improvement"] >= 0.001
                and gate["false_safe_improvement"] >= 0.02
                and gate["safe_coverage_loss"] <= 0.10
            )
            folds[name] = {
                "train_years": list(train_years),
                "validation_years": list(validation_years),
                "training_counts": training["counts"],
                **validation,
                "gate": gate,
            }
        final_training = aggregates[(2021, 2022, 2023)]
        final_model = fit_model(final_training["cells"])
    finally:
        connection.close()

    elite_support = _cell_support(
        final_training["cells"], rank=2, gap=18, round_=1, position="RB"
    )
    elite_prediction = probability(final_model, 2, 18, 1, "RB", "PPR", 10)
    pooled_interval = _clustered_difference(
        pooled, seed=SEED, samples=BOOTSTRAP_SAMPLES
    )
    passed = (
        all(fold["gate"]["passes"] for fold in folds.values())
        and pooled_interval["high"] < 0
        and elite_support >= 1_000
        and elite_prediction < 0.01
    )
    result = {
        "experiment": "shallow monotonic boosted survival tree",
        "status": "research" if passed else "rejected",
        "parameters": {
            "learning_rate": 0.05,
            "max_iter": 100,
            "max_leaf_nodes": 15,
            "max_depth": 3,
            "min_samples_leaf": 20,
            "l2_regularization": 1.0,
            "monotonic_rank": 1,
            "monotonic_gap": -1,
        },
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "folds": folds,
        "gate": {
            "passes": passed,
            "pooled_paired_brier_difference": pooled_interval,
            "elite_rb_gap18_support": elite_support,
            "elite_rb_gap18_prediction": elite_prediction,
        },
        "limitations": [
            "offline population survival research only",
            "top-ten relative market rank only",
            "2024 and 2025 were not queried",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    output = Path(__file__).with_name("result.json")
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "gate": result["gate"], "folds": {name: fold["gate"] for name, fold in folds.items()}}, indent=2))


if __name__ == "__main__":
    main()
