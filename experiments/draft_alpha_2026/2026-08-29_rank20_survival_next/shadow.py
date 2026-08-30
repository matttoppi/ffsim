#!/usr/bin/env python3
import json
from pathlib import Path

from ffsim.draft_intel.alpha_shadow import DEFAULT_HIERARCHICAL_MANIFEST
from ffsim.draft_intel.timing_report import (
    build_cached_timing_context,
    build_timing_report,
)
from ffsim.historical_sleeper.hierarchical_survival import (
    load_hierarchical_survival_artifact,
)
from ffsim.historical_sleeper.rank20_survival import (
    load_rank20_survival_artifact,
)

ROOT = Path(__file__).parents[3]
HERE = Path(__file__).parent
CORPUS = ROOT / "experiments/draft_alpha_2026/2026-08-29_multi_state_corpus/corpus.json"
RANK20 = Path.home() / ".cache/ffsim/historical_sleeper/hdvn/rank20-survival-final-20260829/rank20-survival.manifest.json"
EXPECTED_RANK10 = "0ee13d56a87c5c8206a5c437879b3a8c1419dfd4d4d7c0dc591905d58faf9d91"
EXPECTED_RANK20 = "055517e675b968c32da4af629bc38b7c1ae335152639df86c648e007e02e3437"


def main():
    rank10 = load_hierarchical_survival_artifact(
        DEFAULT_HIERARCHICAL_MANIFEST, expected={"status": "research"}
    )
    rank20 = load_rank20_survival_artifact(
        RANK20, expected={"status": "research"}
    )
    corpus = json.loads(CORPUS.read_text())
    reports = []
    candidates = measured = 0
    output_directory = HERE / "reports"
    output_directory.mkdir(exist_ok=True)
    for state_record in corpus["states"]:
        context = build_cached_timing_context(
            ROOT / state_record["config"],
            ROOT / state_record["league_cache"],
            roster_id=state_record["roster_id"],
            draft_cache=ROOT / state_record["draft_cache"],
            world_count=20,
        )
        report = build_timing_report(
            context["prepared"],
            context["state"],
            RANK20,
            input_hashes=context["input_hashes"],
            candidate_breadth=20,
        )
        report_path = output_directory / f"{state_record['draft_id']}.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        reports.append({
            "draft_id": state_record["draft_id"],
            "pick_no": state_record["pick_no"],
            "fallback_breadth": report["fallback_breadth"],
            "decision_active": report["decision_active"],
            "top_ten_capture_complete": report["top_ten_capture_complete"],
            "market_window_capture_complete": report[
                "market_window_capture_complete"
            ],
            "candidate_count": len(report["players"]),
            "measured_candidates": sum(
                row["return_probability"] is not None
                for row in report["players"]
            ),
            "route_leader": max(
                (
                    row for row in report["players"]
                    if row["take_now_route_value"] is not None
                ),
                key=lambda row: (
                    row["take_now_route_value"], row["player_id"]
                ),
            )["player_id"],
        })
        candidates += len(report["players"])
        measured += reports[-1]["measured_candidates"]
    coverage = measured / candidates
    passed = (
        rank10["sha256"] == EXPECTED_RANK10
        and rank20["sha256"] == EXPECTED_RANK20
        and DEFAULT_HIERARCHICAL_MANIFEST != RANK20
        and coverage >= 0.70
        and all(not report["decision_active"] for report in reports)
        and all(report["fallback_breadth"] == 20 for report in reports)
        and all(report["top_ten_capture_complete"] for report in reports)
        and all(report["market_window_capture_complete"] for report in reports)
    )
    result = {
        "experiment": "rank-20 offline shadow boundary",
        "status": "research" if passed else "rejected",
        "rank_10_manifest_hash": rank10["sha256"],
        "rank_20_manifest_hash": rank20["sha256"],
        "live_default_is_rank_10": DEFAULT_HIERARCHICAL_MANIFEST != RANK20,
        "candidate_count": candidates,
        "measured_candidates": measured,
        "return_coverage": coverage,
        "reports": reports,
        "gate": {"passes": passed},
        "limitations": [
            "rank-20 is explicit offline shadow only",
            "one-turn route leaders remain diagnostic",
            "no live artifact default or recommendation changed",
        ],
    }
    (HERE / "shadow-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
