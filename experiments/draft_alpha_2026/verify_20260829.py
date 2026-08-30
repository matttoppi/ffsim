#!/usr/bin/env python3
import json
from pathlib import Path

from ffsim.draft_intel.alpha_shadow import DEFAULT_HIERARCHICAL_MANIFEST
from ffsim.draft_intel.timing_report import load_timing_report
from ffsim.historical_sleeper.hierarchical_survival import (
    load_hierarchical_survival_artifact,
)
from ffsim.historical_sleeper.manager_choice import load_manager_choice_artifact
from ffsim.historical_sleeper.rank20_survival import (
    load_rank20_survival_artifact,
)
from ffsim.historical_sleeper.roster_manager_choice import (
    load_roster_manager_choice_artifact,
)

ROOT = Path(__file__).parent
HIERARCHICAL = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/hierarchical-survival-final-20260829/hierarchical-survival.manifest.json"
MANAGER = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/manager-choice-final-20260829/manager-choice.manifest.json"
ROSTER_MANAGER = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/roster-manager-choice-final-20260829/roster-manager-choice.manifest.json"
RANK20 = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/rank20-survival-final-20260829/rank20-survival.manifest.json"


def result(directory):
    return json.loads((ROOT / directory / "result.json").read_text())


def main():
    failures = []
    hierarchical = load_hierarchical_survival_artifact(
        HIERARCHICAL, expected={"status": "research"}
    )
    manager = load_manager_choice_artifact(MANAGER, expected={"status": "research"})
    if hierarchical["sha256"] != "0ee13d56a87c5c8206a5c437879b3a8c1419dfd4d4d7c0dc591905d58faf9d91":
        failures.append("hierarchical artifact hash changed")
    if manager["sha256"] != "eaa845cf7e258fca95f51e9ee253f41f75a3d403041f90f4263361ba8580eab1":
        failures.append("manager artifact hash changed")
    roster_manager = load_roster_manager_choice_artifact(
        ROSTER_MANAGER, expected={"status": "research"}
    )
    if (
        roster_manager["sha256"]
        != "b1a99ee7cbce2d0fd59dd383aeff7ad0438adc875cf169c26bfc6b87a5abfd93"
    ):
        failures.append("corrected roster-manager artifact hash changed")
    rank20_artifact = load_rank20_survival_artifact(
        RANK20, expected={"status": "research"}
    )
    if (
        rank20_artifact["sha256"]
        != "055517e675b968c32da4af629bc38b7c1ae335152639df86c648e007e02e3437"
    ):
        failures.append("rank-20 artifact hash changed")

    timing = load_timing_report(
        ROOT / "2026-08-29_top_ten_capture_attempt2/report.json"
    )
    if timing["decision_active"] is not False or not timing["top_ten_capture_complete"]:
        failures.append("timing report is active or incomplete")
    for player_id, branch in timing["candidate_branches"].items():
        if [row["market_rank"] for row in branch["later_players"]] != list(range(1, 11)):
            failures.append(f"branch {player_id} does not capture ranks 1-10")

    vona2 = result("2026-08-29_vona_impact_attempt2")
    vona3 = result("2026-08-29_vona_impact_attempt3")
    if vona2["status"] != "rejected" or vona2["route_terminal_rank"] != 23:
        failures.append("unsafe VONA route result changed")
    if vona2["paired_terminal_leader_minus_route"]["interval"][0] <= 0.1:
        failures.append("unsafe VONA route no longer has a decisive terminal loss")
    if not vona3["gate"]["passes"] or vona3["recommendation_changed_by_survival"]:
        failures.append("terminal-first timing overlay failed")

    for directory in (
        "2026-08-29_roster_manager_attempt1",
        "2026-08-29_roster_manager_attempt2",
        "2026-08-29_roster_manager_attempt3",
    ):
        if not result(directory)["gate"]["passes"]:
            failures.append(f"{directory} predictive gate failed")
    manager1 = result("2026-08-29_manager_impact_attempt1")
    manager2 = result("2026-08-29_manager_impact_attempt2")
    manager3 = result("2026-08-29_manager_impact_attempt3")
    if manager1["status"] != "rejected" or manager2["status"] != "rejected":
        failures.append("unsafe manager impact attempt changed")
    if not manager3["gate"]["passes"] or manager3["manager_probability_blend"] != 0.10:
        failures.append("conservative manager shadow blend failed")
    if manager3["baseline_leader"] != manager3["shadow_leader"]:
        failures.append("conservative manager blend changed the measured leader")

    source_root = ROOT / "2026-08-29_historical_projection_sources"
    for directory in (
        "attempt1_pff_local",
        "attempt2_sleeper_api",
        "attempt3_fantasypros_api",
    ):
        source = json.loads((source_root / directory / "result.json").read_text())
        if source["accepted_for_training"] is not False:
            failures.append(f"unproved source {directory} became accepted")

    corrected = result("2026-08-29_roster_manager_corrected")
    if not corrected["gate"]["passes"]:
        failures.append("corrected roster manager gate failed")
    if not all(
        fold["gate"]["passes"] for fold in corrected["folds"].values()
    ) or not corrected["transfer_2024"]["gate"]["passes"]:
        failures.append("corrected roster rolling or transfer gate failed")
    if corrected["locked_test_loaded"] is not False:
        failures.append("corrected roster manager touched 2025")

    corpus = json.loads((
        ROOT / "2026-08-29_multi_state_corpus/corpus.json"
    ).read_text())
    if (
        corpus["sha256"]
        != "7ee9267de2531b61293a03fb1435c32d136508349ab0530b555f3b499742d52f"
        or not corpus["gate"]["passes"]
        or len(corpus["states"]) != 6
    ):
        failures.append("multi-state corpus changed or failed")
    impact_root = ROOT / "2026-08-29_multi_state_decision_impact_attempt1"
    conclusion = json.loads((impact_root / "conclusion.json").read_text())
    if (
        conclusion["status"] != "research"
        or not conclusion["terminal_first_gate"]["passes"]
        or not conclusion["manager_gate"]["passes"]
        or conclusion["states"] != 6
        or conclusion["route_diagnostic"]["practical_co_leader_states"] != 3
    ):
        failures.append("multi-state decision-impact conclusion failed")
    for report_path in sorted((impact_root / "reports").glob("*.json")):
        report = load_timing_report(report_path)
        if report["decision_active"] is not False or not report[
            "top_ten_capture_complete"
        ]:
            failures.append(f"invalid multi-state timing report {report_path.name}")
    if len(tuple((impact_root / "reports").glob("*.json"))) != 6:
        failures.append("multi-state timing report count is not six")
    full_root = ROOT / "2026-08-29_multi_state_decision_impact_attempt2"
    full = json.loads((full_root / "conclusion.json").read_text())
    if (
        full["status"] != "research"
        or full["rollouts"] != 300
        or full["states"] != 6
        or not full["terminal_first_gate"]["passes"]
        or not full["manager_gate"]["passes"]
        or full["route_diagnostic"]["practical_co_leader_states"] != 3
        or not all(
            state["baseline_leader"] == state["shadow_leader"]
            and state["shadow_practical_co_leader"]
            for state in full["state_summaries"]
        )
    ):
        failures.append("full-budget multi-state gate failed")
    for report_path in sorted((full_root / "reports").glob("*.json")):
        report = load_timing_report(report_path)
        if report["decision_active"] is not False or not report[
            "top_ten_capture_complete"
        ]:
            failures.append(f"invalid full-budget timing report {report_path.name}")
    if len(tuple((full_root / "reports").glob("*.json"))) != 6:
        failures.append("full-budget timing report count is not six")

    integration_root = ROOT / "2026-08-29_live_shadow_integration"
    direct_shadow = json.loads((integration_root / "result.json").read_text())
    monitor_shadow = json.loads(
        (integration_root / "monitor_result.json").read_text()
    )
    if (
        not direct_shadow["gate"]["passes"]
        or not direct_shadow["recommendation_unchanged"]
        or direct_shadow["manager_shadow"]["status"] != "ready"
    ):
        failures.append("direct alpha shadow integration smoke failed")
    if (
        not monitor_shadow["gate"]["passes"]
        or not monitor_shadow["recommendation_unchanged"]
        or monitor_shadow["alpha_shadow_status"] != "ready"
        or monitor_shadow["telemetry_shadow_events"] != 1
        or monitor_shadow["manager_shadow"]["status"] != "ready"
    ):
        failures.append("LiveDraftMonitor alpha shadow flow failed")
    initial_audit = json.loads((
        ROOT / "2026-08-29_alpha_shadow_audit/audit.json"
    ).read_text())
    optimized_root = ROOT / "2026-08-29_alpha_shadow_latency_attempt1"
    optimized_collection = json.loads(
        (optimized_root / "collection.json").read_text()
    )
    optimized_audit = json.loads((optimized_root / "audit.json").read_text())
    if (
        initial_audit["development_gate"]["passes"]
        or initial_audit["metrics"]["duration_seconds"]["p95"] <= 10
    ):
        failures.append("initial latency failure evidence changed")
    if (
        not optimized_collection["gate"]["passes"]
        or not all(
            state["recommendation_unchanged"]
            for state in optimized_collection["states"]
        )
        or not optimized_audit["development_gate"]["passes"]
        or optimized_audit["live_evidence_gate"]["passes"]
        or optimized_audit["metrics"]["duration_seconds"]["p95"] > 10
        or optimized_audit["metrics"]["manager_practical_retention_rate"] != 1
        or optimized_audit["metrics"]["top_ten_capture_rate"] != 1
    ):
        failures.append("optimized six-state alpha audit failed")

    rank20_root = ROOT / "2026-08-29_rank20_survival_next"
    rank20_result = json.loads((rank20_root / "result.json").read_text())
    rank20_shadow = json.loads(
        (rank20_root / "shadow-result.json").read_text()
    )
    rank20_decision = json.loads(
        (rank20_root / "decision-impact-result.json").read_text()
    )
    if (
        not rank20_result["gate"]["passes"]
        or rank20_result["locked_test_loaded"] is not False
        or not rank20_shadow["gate"]["passes"]
        or not rank20_shadow["live_default_is_rank_10"]
        or rank20_shadow["return_coverage"] < 0.70
        or rank20_decision["gate"]["passes"]
        or sum(
            state["route_is_terminal_practical_co_leader"]
            for state in rank20_decision["states"]
        )
        != 4
    ):
        failures.append("rank-20 research or boundary evidence failed")

    rank20_live_root = ROOT / "2026-08-29_rank20_live_shadow_attempt1"
    rank20_live_collection = json.loads(
        (rank20_live_root / "collection.json").read_text()
    )
    rank20_live_audit = json.loads(
        (rank20_live_root / "audit.json").read_text()
    )
    if (
        not rank20_live_collection["gate"]["passes"]
        or not rank20_live_audit["development_gate"]["passes"]
        or rank20_live_audit["metrics"]["candidate_return_coverage"] < 0.70
        or rank20_live_audit["metrics"]["duration_seconds"]["p95"] > 10
        or rank20_live_audit["metrics"]["manager_practical_retention_rate"] != 1
        or DEFAULT_HIERARCHICAL_MANIFEST == RANK20
    ):
        failures.append("rank-20 live-shadow candidate evidence failed")



    if failures:
        raise RuntimeError("; ".join(failures))
    print(json.dumps({
        "hierarchical_artifact": "verified_research",
        "manager_artifact": "verified_research",
        "roster_manager_artifact": "verified_research",
        "rank20_survival_artifact": "verified_offline_research",
        "top_ten_branches": len(timing["candidate_branches"]),
        "vona_route": "rejected",
        "manager_full_callback": "rejected",
        "manager_10_percent_shadow": "passed_six_state_full_budget",
        "historical_projection_sources_accepted": 0,
        "live_model_change": False,
        "live_shadow_collector": "verified_cached_fail_isolated",
        "alpha_shadow_audit": "six_state_development_pass",
        "alpha_shadow_p95_seconds": optimized_audit["metrics"][
            "duration_seconds"
        ]["p95"],
        "alpha_live_evidence_gate": "pending_30_new_states",
        "rank20_terminal_coverage": rank20_shadow["return_coverage"],
        "rank20_route_practical_states": 4,
        "rank20_shadow_coverage": rank20_live_audit["metrics"][
            "candidate_return_coverage"
        ],
        "rank20_shadow_p95_seconds": rank20_live_audit["metrics"][
            "duration_seconds"
        ]["p95"],
        "live_default_survival": "rank10_unchanged",
    }, indent=2))


if __name__ == "__main__":
    main()
