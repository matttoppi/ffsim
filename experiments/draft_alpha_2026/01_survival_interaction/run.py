#!/usr/bin/env python3
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from ffsim.historical_sleeper.continuous_survival import (
    _add_metric,
    _aggregate_samples,
    _baseline_table,
    _cell_support,
    _finish_metric,
    _metric_state,
    _sigmoid,
)
from ffsim.historical_sleeper.opponent_model import (
    _clustered_difference,
    _iter_drafts,
    _iter_survival_samples,
)

MARKET_DB = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3"
SEED = 20260828
L2 = 0.001
BOOTSTRAP_SAMPLES = 200
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")
SCORING_FORMATS = ("STD", "HALF_PPR", "PPR")
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)
FEATURE_ORDER = (
    "intercept",
    *(f"rank_{rank}" for rank in range(2, 11)),
    *(f"rank_{rank}_log1p_gap" for rank in range(1, 11)),
    "round_div_10",
    "team_count_div_12",
    *(f"position_{position}" for position in POSITIONS),
    *(f"scoring_{scoring}" for scoring in SCORING_FORMATS),
)
GAP_SLOPE = slice(10, 20)


def features(rank, gap, round_, position, scoring_format, team_count):
    position = position if position in POSITIONS else "UNKNOWN"
    scoring_format = scoring_format if scoring_format in SCORING_FORMATS else "STD"
    log_gap = math.log1p(gap)
    return np.asarray(
        [
            1.0,
            *(float(rank == value) for value in range(2, 11)),
            *(log_gap if rank == value else 0.0 for value in range(1, 11)),
            round_ / 10.0,
            team_count / 12.0,
            *(float(position == value) for value in POSITIONS),
            *(float(scoring_format == value) for value in SCORING_FORMATS),
        ],
        dtype=np.float64,
    )


def fit_model(cells):
    keys = sorted(cells)
    x = np.asarray([features(*key) for key in keys], dtype=np.float64)
    successes = np.asarray([cells[key][0] for key in keys], dtype=np.float64)
    counts = np.asarray([cells[key][1] for key in keys], dtype=np.float64)
    total = counts.sum()
    rate = successes.sum() / total
    initial = np.zeros(len(FEATURE_ORDER), dtype=np.float64)
    initial[0] = math.log(rate / (1 - rate))
    initial[GAP_SLOPE] = -1.0

    def objective(coefficients):
        logits = x @ coefficients
        loss = np.sum(counts * np.logaddexp(0.0, logits) - successes * logits) / total
        loss += 0.5 * L2 * float(coefficients[1:] @ coefficients[1:])
        probabilities = _sigmoid(logits)
        gradient = x.T @ (counts * probabilities - successes) / total
        gradient[1:] += L2 * coefficients[1:]
        return float(loss), gradient

    bounds = [(None, None)] * len(FEATURE_ORDER)
    for index in range(GAP_SLOPE.start, GAP_SLOPE.stop):
        bounds[index] = (None, 0.0)
    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        bounds=bounds,
        options={"maxiter": 300, "ftol": 1e-12, "gtol": 1e-8},
    )
    if not result.success:
        raise RuntimeError(f"optimizer failed: {result.message}")
    return np.asarray(result.x), {
        "iterations": int(result.nit),
        "objective": float(result.fun),
    }


def probability(coefficients, rank, gap, round_, position, scoring_format, team_count):
    return float(_sigmoid(features(rank, gap, round_, position, scoring_format, team_count) @ coefficients))


def validate(connection, years, coefficients, baseline):
    model_state = _metric_state()
    baseline_state = _metric_state()
    differences = defaultdict(lambda: [0.0, 0])
    drafts = states = samples = 0
    for draft in _iter_drafts(connection, years):
        drafts += 1
        for sample in _iter_survival_samples(draft):
            states += 1
            for target in sample["players"]:
                rank = int(target["rank"])
                gap = int(sample["gap"])
                round_ = int(sample["round"])
                actual = float(target["survived"])
                predicted = probability(
                    coefficients,
                    rank,
                    gap,
                    round_,
                    target["position"],
                    sample["scoring_format"],
                    sample["team_count"],
                )
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
            for years in ((2021,), (2021, 2022), (2021, 2022, 2023))
        }
        folds = {}
        pooled = defaultdict(lambda: [0.0, 0])
        for name, train_years, validation_years in FOLDS:
            training = aggregates[train_years]
            coefficients, optimizer = fit_model(training["cells"])
            validation = validate(
                connection,
                validation_years,
                coefficients,
                _baseline_table(training["cells"]),
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
                "optimizer": optimizer,
                **validation,
                "gate": gate,
            }
        final_training = aggregates[(2021, 2022, 2023)]
        final_coefficients, final_optimizer = fit_model(final_training["cells"])
    finally:
        connection.close()

    elite_support = _cell_support(
        final_training["cells"], rank=2, gap=18, round_=1, position="RB"
    )
    elite_prediction = probability(final_coefficients, 2, 18, 1, "RB", "PPR", 10)
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
        "experiment": "rank-specific monotonic gap survival",
        "status": "research" if passed else "rejected",
        "train_development_seasons": [2021, 2022, 2023],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "feature_order": list(FEATURE_ORDER),
        "l2": L2,
        "folds": folds,
        "final_optimizer": final_optimizer,
        "gate": {
            "passes": passed,
            "pooled_paired_brier_difference": pooled_interval,
            "elite_rb_gap18_support": elite_support,
            "elite_rb_gap18_prediction": elite_prediction,
        },
        "coefficients": final_coefficients.tolist(),
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
