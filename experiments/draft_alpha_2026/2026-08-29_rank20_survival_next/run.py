#!/usr/bin/env python3
import hashlib
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
from ffsim.historical_sleeper.hdvn_snapshot import canonical_json
from ffsim.historical_sleeper.hierarchical_survival import (
    _ece,
    _probability,
    _tables,
)
from ffsim.historical_sleeper.opponent_model import (
    _clustered_difference,
    _iter_drafts,
    _iter_survival_samples,
)

MARKET = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3"
SHADOW_REPORTS = (
    Path(__file__).parents[1]
    / "2026-08-29_multi_state_decision_impact_attempt2/reports"
)
SEED = 20260828
FOLDS = (
    ("train-2021_validate-2022", (2021,), (2022,)),
    ("train-2021-2022_validate-2023", (2021, 2022), (2023,)),
)


def evaluate_bands(connection, years, model20, model10, seed):
    states = {
        "rank_1_10_model20": _metric_state(),
        "rank_1_10_model10": _metric_state(),
        "rank_11_20_model": _metric_state(),
        "rank_11_20_baseline": _metric_state(),
    }
    top_differences = defaultdict(lambda: [0.0, 0])
    tail_differences = defaultdict(lambda: [0.0, 0])
    counts = defaultdict(int)
    for draft in _iter_drafts(connection, years):
        counts["drafts"] += 1
        for sample in _iter_survival_samples(draft, 20):
            counts["states"] += 1
            for target in sample["players"]:
                rank = int(target["rank"])
                key = (
                    rank,
                    int(sample["gap"]),
                    int(sample["round"]),
                    str(target["position"]),
                )
                actual = float(target["survived"])
                if rank <= 10:
                    predicted20 = _probability(model20, key)
                    predicted10 = _probability(model10, key)
                    _add_metric(states["rank_1_10_model20"], actual, predicted20)
                    _add_metric(states["rank_1_10_model10"], actual, predicted10)
                    top_differences[draft["draft_id"]][0] += (
                        (predicted20 - actual) ** 2
                        - (predicted10 - actual) ** 2
                    )
                    top_differences[draft["draft_id"]][1] += 1
                    counts["rank_1_10_samples"] += 1
                else:
                    predicted = _probability(model20, key)
                    pooled = model20["pooled"].get(key[:3], (0, 0))
                    baseline = (pooled[0] + 2) / (pooled[1] + 4)
                    _add_metric(states["rank_11_20_model"], actual, predicted)
                    _add_metric(states["rank_11_20_baseline"], actual, baseline)
                    tail_differences[draft["draft_id"]][0] += (
                        (predicted - actual) ** 2
                        - (baseline - actual) ** 2
                    )
                    tail_differences[draft["draft_id"]][1] += 1
                    counts["rank_11_20_samples"] += 1
    metrics = {name: _finish_metric(value) for name, value in states.items()}
    for value in metrics.values():
        value["expected_calibration_error"] = _ece(value)
    top_difference = (
        metrics["rank_1_10_model20"]["brier"]
        - metrics["rank_1_10_model10"]["brier"]
    )
    tail_improvement = (
        metrics["rank_11_20_baseline"]["brier"]
        - metrics["rank_11_20_model"]["brier"]
    )
    gate = {
        "rank_1_10_brier_difference": top_difference,
        "rank_1_10_no_material_regression": top_difference <= 0.001,
        "rank_1_10_ece": metrics["rank_1_10_model20"][
            "expected_calibration_error"
        ],
        "rank_11_20_brier_improvement": tail_improvement,
        "rank_11_20_paired_model_minus_baseline": _clustered_difference(
            tail_differences, seed=seed, samples=200
        ),
        "rank_11_20_ece": metrics["rank_11_20_model"][
            "expected_calibration_error"
        ],
        "rank_11_20_false_safe_rate": metrics["rank_11_20_model"][
            "false_safe_rate"
        ],
    }
    gate["passes"] = (
        gate["rank_1_10_no_material_regression"]
        and gate["rank_1_10_ece"] <= 0.05
        and tail_improvement >= 0.001
        and gate["rank_11_20_paired_model_minus_baseline"]["high"] < 0
        and gate["rank_11_20_ece"] <= 0.05
        and gate["rank_11_20_false_safe_rate"] <= 0.10
    )
    return {
        "counts": dict(counts),
        "metrics": metrics,
        "top_band_paired_model20_minus_model10": _clustered_difference(
            top_differences, seed=seed + 100, samples=200
        ),
        "gate": gate,
    }


def compatible_rank10_cells(aggregate10, aggregate20):
    left = {
        key: value for key, value in aggregate10["cells"].items() if key[0] <= 10
    }
    right = {
        key: value for key, value in aggregate20["cells"].items() if key[0] <= 10
    }
    payload = [
        [list(key), list(left[key]), list(right.get(key, ())) ]
        for key in sorted(left)
    ]
    return {
        "passes": left == right,
        "rank_10_cells": len(left),
        "row_equivalence_hash": hashlib.sha256(
            canonical_json(payload).encode()
        ).hexdigest(),
    }


def terminal_coverage():
    candidates = [
        candidate
        for report_path in sorted(SHADOW_REPORTS.glob("*.json"))
        for candidate in json.loads(report_path.read_text()).get("players") or ()
    ]
    rank10 = sum(
        candidate.get("market_rank") is not None
        and int(candidate["market_rank"]) <= 10
        for candidate in candidates
    )
    rank20 = sum(
        candidate.get("market_rank") is not None
        and int(candidate["market_rank"]) <= 20
        for candidate in candidates
    )
    return {
        "candidates": len(candidates),
        "rank_10_coverage": rank10 / len(candidates),
        "rank_20_coverage": rank20 / len(candidates),
        "required_rank_20_coverage": 0.70,
        "passes": rank20 / len(candidates) >= 0.70,
    }


def main():
    connection = sqlite3.connect(f"file:{MARKET}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        aggregates10 = {
            years: _aggregate_samples(connection, years, 10)
            for years in ((2021,), (2021, 2022), (2021, 2022, 2023))
        }
        aggregates20 = {
            years: _aggregate_samples(connection, years, 20)
            for years in ((2021,), (2021, 2022), (2021, 2022, 2023))
        }
        compatibility = {
            "_".join(map(str, years)): compatible_rank10_cells(
                aggregates10[years], aggregates20[years]
            )
            for years in aggregates10
        }
        folds = {}
        for index, (name, train_years, validation_years) in enumerate(FOLDS):
            folds[name] = evaluate_bands(
                connection,
                validation_years,
                _tables(aggregates20[train_years]["cells"]),
                _tables(aggregates10[train_years]["cells"]),
                SEED + index,
            )
        final20 = _tables(aggregates20[(2021, 2022, 2023)]["cells"])
        final10 = _tables(aggregates10[(2021, 2022, 2023)]["cells"])
        transfer = evaluate_bands(
            connection, (2024,), final20, final10, SEED + len(FOLDS)
        )
    finally:
        connection.close()
    elite_key = (2, 18, 1, "RB")
    elite = final20["position"].get(elite_key, (0, 0))
    elite_probability = _probability(final20, elite_key)
    coverage = terminal_coverage()
    passed = (
        all(result["passes"] for result in compatibility.values())
        and all(fold["gate"]["passes"] for fold in folds.values())
        and transfer["gate"]["passes"]
        and elite[1] >= 1_000
        and elite_probability < 0.01
        and coverage["passes"]
    )
    result = {
        "experiment": "rank-20 hierarchical position survival",
        "status": "research" if passed else "rejected",
        "target_count": 20,
        "train_development_seasons": [2021, 2022, 2023],
        "seen_transfer_seasons": [2024],
        "locked_test_loaded": False,
        "rank_10_compatibility": compatibility,
        "folds": folds,
        "transfer_2024": transfer,
        "elite_rank2_rb_gap18_round1": {
            "successes": elite[0],
            "count": elite[1],
            "probability": elite_probability,
        },
        "terminal_candidate_coverage": coverage,
        "gate": {"passes": passed},
        "limitations": [
            "2024 is a seen transfer diagnostic",
            "2025 was not queried",
            "rank-20 remains offline research",
            "no live artifact, callback, ranking, or UI change",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "compatibility": compatibility,
        "folds": {name: fold["gate"] for name, fold in folds.items()},
        "transfer_2024": transfer["gate"],
        "elite": result["elite_rank2_rb_gap18_round1"],
        "coverage": coverage,
        "gate": result["gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
