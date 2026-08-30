#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent
EXPECTED = {
    "00_prior_evidence": "ok",
    "01_survival_interaction": "rejected",
    "01b_survival_tree": "rejected",
    "02_manager_personalization": "research",
    "02b_manager_residual": "research",
    "02c_manager_2024_diagnostic": "research",
    "02d_manager_locked_2025": "locked_benchmark_passed",
    "03_vona_vorp_policy": "rejected",
    "04_manager_survival_impact": "rejected",
    "05_pooled_exact_survival": "rejected",
    "05b_position_exact_survival": "rejected",
    "06_hierarchical_survival": "research",
    "06b_hierarchical_2024_diagnostic": "research",
    "06c_hierarchical_vona_vorp": "rejected",
    "06d_hierarchical_comparison": "research",
}
PINNED_HASHES = {
    "02d_manager_locked_2025": "f5dca7e79844e2ffad3935a33d9068f16e29c45a9301bc1b9be919a4e2574fe7",
    "06_hierarchical_survival": "fe4e513a0a25ddcde877968dc9f927d261a72a28178bfc142748d3246b15dea4",
    "06b_hierarchical_2024_diagnostic": "8d47c215c06a932be589f8d1ae85253f135aaede77d934c3ef2ad2f62c5d5d0a",
    "06d_hierarchical_comparison": "fa1518a7c5ddc2803c220e10f6ed274817f289c5e3427def2ee19e4c5809922d",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    results = {}
    failures = []
    for directory, expected_status in EXPECTED.items():
        path = ROOT / directory / "result.json"
        if not path.exists():
            failures.append(f"missing {path.relative_to(ROOT)}")
            continue
        result = json.loads(path.read_text())
        results[directory] = result
        status = result.get("status", "ok" if directory == "00_prior_evidence" else None)
        if status != expected_status:
            failures.append(f"{directory} status {status!r}, expected {expected_status!r}")
        expected_hash = PINNED_HASHES.get(directory)
        if expected_hash and sha256(path) != expected_hash:
            failures.append(f"{directory} pinned result hash changed")

    locked = results.get("02d_manager_locked_2025", {})
    if not locked.get("gate", {}).get("passes") or not locked.get("locked_test_loaded"):
        failures.append("02d locked benchmark evidence is invalid")
    if locked.get("locked_test_evaluation_count") != 1:
        failures.append("02d locked benchmark evaluation count is not one")
    if locked.get("target_manager_coverage", {}).get("eligible_managers") != 12:
        failures.append("02d final-fit target manager count is not 12")
    transfer_manager_count = results.get("02c_manager_2024_diagnostic", {}).get(
        "target_manager_coverage", {}
    ).get("eligible_managers")
    if transfer_manager_count != 11:
        failures.append("02c transfer-fit target manager count is not 11")

    manager_survival = results.get("04_manager_survival_impact", {})
    if not manager_survival.get("validation", {}).get("label_audit", {}).get(
        "matches_canonical_iterator"
    ):
        failures.append("04 survival labels do not match the canonical iterator")
    if manager_survival.get("gate", {}).get("passes"):
        failures.append("04 manager survival gate unexpectedly passes")

    hierarchy = results.get("06_hierarchical_survival", {})
    transfer = results.get("06b_hierarchical_2024_diagnostic", {})
    if not hierarchy.get("gate", {}).get("passes"):
        failures.append("06 rolling hierarchical gate does not pass")
    if not transfer.get("gate", {}).get("passes"):
        failures.append("06b transfer gate does not pass")
    if hierarchy.get("locked_test_loaded") is not False:
        failures.append("06 hierarchical model touched the locked test")
    if transfer.get("locked_test_loaded") is not False:
        failures.append("06b hierarchical transfer touched the locked test")
    comparison = results.get("06d_hierarchical_comparison", {})
    if not comparison.get("gate", {}).get("passes"):
        failures.append("06d hierarchical baseline comparison does not pass")

    vona = results.get("06c_hierarchical_vona_vorp", {})
    if vona.get("gate", {}).get("passes"):
        failures.append("06c incomplete top-ten surface unexpectedly passes")
    if vona.get("counts", {}).get("top_ten_candidates") != 59:
        failures.append("06c saved-state candidate count changed")
    if vona.get("counts", {}).get("complete_top_ten_states") != 5:
        failures.append("06c complete-state count changed")

    if failures:
        raise RuntimeError("; ".join(failures))
    print(json.dumps({
        "verified_results": len(results),
        "locked_benchmark": "passed_once",
        "selected_offline_survival": "06_hierarchical_survival",
        "live_integration": "not_approved",
    }, indent=2))


if __name__ == "__main__":
    main()
