#!/usr/bin/env python3
import importlib.util
import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).parents[1] / "06_hierarchical_survival/run.py"
spec = importlib.util.spec_from_file_location("hierarchical_survival", BASE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    connection = sqlite3.connect(f"file:{module.MARKET_DB}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        aggregate = module._aggregate_samples(connection, (2021, 2022, 2023))
        model = module.tables(aggregate["cells"])
        validation = module.validate(connection, (2024,), model)
    finally:
        connection.close()
    metrics = validation["metrics"]
    elite_key = (2, 18, 1, "RB")
    elite = model[1].get(elite_key, (0, 0))
    elite_probability = module.probability(model, elite_key)
    passed = (
        validation["counts"]["coverage"] == 1.0
        and metrics["brier"] <= 0.12
        and metrics["expected_calibration_error"] <= 0.05
        and metrics["false_safe_rate"] <= 0.10
        and elite[1] >= 1_000
        and elite_probability < 0.01
    )
    result = {
        "experiment": "frozen hierarchical survival 2024 transfer diagnostic",
        "status": "research" if passed else "rejected",
        "train_seasons": [2021, 2022, 2023],
        "validation_seasons": [2024],
        "validation_2024_seen_diagnostic": True,
        "locked_test_loaded": False,
        "shrinkage_observations": module.SHRINKAGE,
        "validation": validation,
        "gate": {
            "passes": passed,
            "coverage": validation["counts"]["coverage"],
            "brier": metrics["brier"],
            "expected_calibration_error": metrics["expected_calibration_error"],
            "false_safe_rate": metrics["false_safe_rate"],
            "elite_rank2_rb_gap18_round1": {
                "successes": elite[0],
                "count": elite[1],
                "probability": elite_probability,
            },
        },
        "limitations": [
            "2024 is a seen transfer diagnostic, not an untouched holdout",
            "scoring format, team count, and manager identity are pooled",
            "hierarchical probabilities do not model joint tier survival",
            "2025 was not queried",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": result["status"], "gate": result["gate"]}, indent=2))


if __name__ == "__main__":
    main()
