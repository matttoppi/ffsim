#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path.home() / ".cache/ffsim/historical_sleeper/hdvn"
REPORTS = {
    "completed_draft_neural": ROOT / "neural-final-20260828/validation-report.json",
    "additive_survival": ROOT / "continuous-survival-final-20260828/rolling-fold-report.json",
    "exact_empirical_survival": ROOT / "empirical-survival-final-20260828/rolling-fold-report.json",
}
EXPECTED_HASHES = {
    "completed_draft_neural": "4c2168e48f069a10385799cba01a184425695990c28835d8242d717ffe906b1e",
    "additive_survival": "727e1303c9f2a620bf889712f716ef661a04acbbbb073aa22c2dc85fb14391a8",
    "exact_empirical_survival": "e94087f39a1b3b0f361742d9fba11c0b6db2bcd31fbaba2ccf48cb8224462f0f",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    reports = {}
    for name, path in REPORTS.items():
        actual_hash = sha256(path)
        if actual_hash != EXPECTED_HASHES[name]:
            raise RuntimeError(f"{name} report hash changed: {actual_hash}")
        reports[name] = json.loads(path.read_text())

    neural = reports["completed_draft_neural"]
    additive = reports["additive_survival"]
    empirical = reports["exact_empirical_survival"]
    checks = {
        "neural rejection": neural["status"] == "rejected" and not neural["gate"]["passed"],
        "additive rejection": (
            additive["status"] == "rejected" and not additive["gate"]["passes"]
        ),
        "additive elite failure": (
            additive["gate"]["elite_rb_gap18_prediction"] >= 0.01
        ),
        "empirical pass": (
            empirical["status"] == "research" and empirical["gate"]["passes"]
        ),
        "neural locked-test isolation": not neural["locked_test_loaded"],
        "additive year isolation": (
            not additive["validation_2024_loaded"]
            and not additive["locked_test_loaded"]
        ),
        "empirical year isolation": (
            not empirical["validation_2024_loaded"]
            and not empirical["locked_test_loaded"]
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"prior evidence checks failed: {', '.join(failed)}")

    result = {
        "completed_draft_neural": {
            "status": neural["status"],
            "points_mae": neural["gate"]["points_mae"],
            "required_mae": neural["gate"]["predeclared_points_mae_threshold"],
        },
        "additive_survival": {
            "status": additive["status"],
            "rolling_fold_gates": additive["gate"]["folds"],
            "elite_rb_gap18_prediction": additive["gate"]["elite_rb_gap18_prediction"],
            "elite_rb_gap18_support": additive["gate"]["elite_rb_gap18_support"],
        },
        "exact_empirical_survival": {
            "status": empirical["status"],
            "rolling_fold_gates": empirical["gate"]["folds"],
            "elite_cells": empirical["gate"]["elite_cells"],
        },
        "locked_2025_loaded": False,
    }
    output = Path(__file__).with_name("result.json")
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
