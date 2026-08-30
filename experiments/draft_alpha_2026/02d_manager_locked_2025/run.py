#!/usr/bin/env python3
import importlib.util
import json
import sqlite3
from pathlib import Path

from ffsim.historical_sleeper.opponent_model import _clustered_difference

ROOT = Path(__file__).parents[3]
BASE = Path(__file__).parents[1] / "02_manager_personalization/run.py"
spec = importlib.util.spec_from_file_location("manager_personalization", BASE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.POPULATION_CORRECTED = True


def main():
    market = sqlite3.connect(f"file:{module.MARKET_DB}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{module.SOURCE_DB}?mode=ro&immutable=1", uri=True)
    try:
        global_factor, managers, training_counts = module.fit(
            source, market, (2021, 2022, 2023, 2024)
        )
        validation = module.validate(source, market, (2025,), global_factor, managers)
    finally:
        source.close()
        market.close()
    interval = _clustered_difference(
        validation.pop("differences"), seed=module.SEED, samples=200
    )
    improvement = (
        validation["population_seen"]["log_loss"]
        - validation["personalized_seen"]["log_loss"]
    )
    all_difference = (
        validation["personalized_all"]["log_loss"]
        - validation["population_all"]["log_loss"]
    )
    passed = improvement >= 0.005 and interval["high"] < 0 and all_difference <= 0.001

    local = sqlite3.connect(
        f"file:{ROOT / 'data/cache/draft_intel/history.sqlite3'}?mode=ro&immutable=1",
        uri=True,
    )
    try:
        target_managers = []
        for manager_id, display_name in local.execute(
            "SELECT sleeper_user_id, display_name FROM managers ORDER BY display_name"
        ):
            record = managers.get(manager_id)
            picks = int(record["picks"]) if record else 0
            target_managers.append({
                "manager_id": manager_id,
                "display_name": display_name,
                "training_picks": picks,
                "eligible": picks >= module.MINIMUM_MANAGER_PICKS,
                "position_factors": (
                    dict(zip(module.POSITIONS, map(float, record["factor"])))
                    if record and picks >= module.MINIMUM_MANAGER_PICKS
                    else None
                ),
            })
    finally:
        local.close()
    eligible_targets = sum(manager["eligible"] for manager in target_managers)
    result = {
        "experiment": "frozen manager residual one-time 2025 benchmark",
        "status": "locked_benchmark_passed" if passed else "rejected",
        "train_seasons": [2021, 2022, 2023, 2024],
        "validation_seasons": [2025],
        "locked_test_loaded": True,
        "locked_test_evaluation_count": 1,
        "model": {
            "positions": list(module.POSITIONS),
            "population_position_factors": list(map(float, global_factor)),
            "shrinkage_opportunities": module.SHRINKAGE,
            "minimum_manager_picks": module.MINIMUM_MANAGER_PICKS,
        },
        "training_counts": training_counts,
        "validation": validation,
        "gate": {
            "passes": passed,
            "seen_manager_log_loss_improvement": improvement,
            "all_pick_log_loss_difference": all_difference,
            "paired_seen_log_loss_difference": interval,
        },
        "target_manager_coverage": {
            "configured_managers": len(target_managers),
            "eligible_managers": eligible_targets,
            "coverage": eligible_targets / len(target_managers),
            "minimum_training_picks": module.MINIMUM_MANAGER_PICKS,
            "managers": target_managers,
        },
        "limitations": [
            "offline opponent-choice evidence only",
            "position preference does not model player-specific affinity",
            "only managers with at least 20 prior supported picks receive a factor",
            "a separate architecture decision is required before any live use",
            "no live opponent callback, VONA, WORP, rollout, API, or UI integration",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "status": result["status"],
        "gate": result["gate"],
        "target_manager_coverage": {
            key: value for key, value in result["target_manager_coverage"].items()
            if key != "managers"
        },
    }, indent=2))


if __name__ == "__main__":
    main()
