#!/usr/bin/env python3
import importlib.util
import json
import sqlite3
from pathlib import Path

from ffsim.historical_sleeper.manager_choice import fit_manager_choice
from ffsim.historical_sleeper.opponent_model import _clustered_difference

SOURCE_SCRIPT = Path(__file__).parents[1] / "2026-08-29_roster_manager_attempt2/run.py"
spec = importlib.util.spec_from_file_location("roster_manager", SOURCE_SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    market = sqlite3.connect(f"file:{module.MARKET}?mode=ro&immutable=1", uri=True)
    market.row_factory = sqlite3.Row
    source = sqlite3.connect(f"file:{module.SOURCE}?mode=ro&immutable=1", uri=True)
    try:
        _, static_managers, _ = fit_manager_choice(
            source, market, (2021, 2022, 2023)
        )
        _, phase_managers = module.round_manager.fit_round_model(
            source, market, (2021, 2022, 2023)
        )
        _, roster_managers = module.fit_roster_model(
            source, market, (2021, 2022, 2023)
        )
        result = module.validate(
            source,
            market,
            (2024,),
            static_managers,
            phase_managers,
            roster_managers,
        )
    finally:
        source.close()
        market.close()
    interval = _clustered_difference(
        result.pop("differences"), seed=module.SEED, samples=200
    )
    passed = result["improvement"] >= 0.005 and interval["high"] < 0
    output = {
        "experiment": "frozen position-count manager 2024 transfer",
        "status": "research" if passed else "rejected",
        "train_seasons": [2021, 2022, 2023],
        "validation_seasons": [2024],
        "validation_2024_seen_diagnostic": True,
        "locked_test_loaded": False,
        **result,
        "gate": {
            "passes": passed,
            "improvement": result["improvement"],
            "paired_roster_minus_phase": interval,
        },
        "limitations": [
            "2024 is a seen transfer diagnostic",
            "2025 was not queried",
            "offline research only",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": output["status"], "gate": output["gate"]}, indent=2))


if __name__ == "__main__":
    main()
