#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

from ffsim.historical_sleeper.empirical_survival import (
    load_empirical_survival_lookup,
    lookup_survival,
)

ROOT = Path(__file__).parents[3]
TIMING_REPORTS = ROOT / "tmp"
LOOKUP_MANIFEST = (
    Path.home()
    / ".cache/ffsim/historical_sleeper/hdvn/empirical-survival-final-20260828/empirical-survival.manifest.json"
)


def scoring_format(league):
    reception = float(league["scoring_settings"].get("rec", 0.0))
    if reception >= 0.75:
        return "PPR"
    if reception > 0:
        return "HALF_PPR"
    return "STD"


def expected_best(players, probability_key):
    result = 0.0
    better_gone = 1.0
    for player in sorted(players, key=lambda item: (-item["value"], item["player_id"])):
        survives = player[probability_key]
        result += player["value"] * survives * better_gone
        better_gone *= 1 - survives
    return result


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    lookup = load_empirical_survival_lookup(
        LOOKUP_MANIFEST, expected={"status": "research"}
    )
    reports = sorted(TIMING_REPORTS.glob("timing-*.json"))
    if not reports:
        raise RuntimeError("no saved timing reports")
    states = []
    total_candidates = supported_candidates = fully_supported = stable_states = 0
    skipped = []
    for path in reports:
        report = json.loads(path.read_text())
        if "players" not in report:
            skipped.append({"source": str(path.relative_to(ROOT)), "reason": "not_timing_report"})
            continue
        league_path = ROOT / "data/cache" / f"league_{report['league_id']}.json"
        if not league_path.exists():
            skipped.append({"source": str(path.relative_to(ROOT)), "reason": "missing_league_cache"})
            continue
        league = json.loads(league_path.read_text())["league"]
        context = {
            "gap": int(report["opponent_picks_until_next"]),
            "round_": int(report["round"]),
            "scoring_format": scoring_format(league),
            "team_count": int(league["total_rosters"]),
        }
        candidates = sorted(
            (player for player in report["players"] if int(player["market_rank"]) <= 10),
            key=lambda player: (int(player["market_rank"]), player["player_id"]),
        )
        by_rank = {}
        for player in candidates:
            by_rank.setdefault(int(player["market_rank"]), player)
        candidates = [by_rank[rank] for rank in sorted(by_rank)]
        total_candidates += len(candidates)
        marginal = []
        vorp = []
        support = []
        for player in candidates:
            cell = lookup_survival(
                lookup,
                market_rank=player["market_rank"],
                position=player["position"],
                **context,
            )
            available = cell["status"] == "available"
            supported_candidates += int(available)
            support.append({
                "player_id": player["player_id"],
                "name": player["name"],
                "market_rank": player["market_rank"],
                "position": player["position"],
                **cell,
            })
            if not available:
                continue
            common = {
                "player_id": player["player_id"],
                "probability": cell["probability"],
                "probability_low": cell["interval_95"][0],
                "probability_high": cell["interval_95"][1],
            }
            marginal.append({**common, "value": float(player["current_roster_value"])})
            vorp.append({
                **common,
                "value": float(player["projected_points"] - player["replacement_points"]),
            })
        state = {
            "source": str(path.relative_to(ROOT)),
            "source_sha256": sha256(path),
            "draft_id": report["draft_id"],
            "pick_no": report["pick_no"],
            "context": context,
            "candidate_count": len(candidates),
            "supported_count": len(marginal),
            "support": support,
        }
        if len(marginal) == len(candidates) == 10:
            fully_supported += 1
            best_marginal = max(player["value"] for player in marginal)
            best_vorp = max(player["value"] for player in vorp)
            marginal_wait = {
                key: expected_best(marginal, probability_key)
                for key, probability_key in (
                    ("low", "probability_low"),
                    ("mid", "probability"),
                    ("high", "probability_high"),
                )
            }
            vorp_wait = {
                key: expected_best(vorp, probability_key)
                for key, probability_key in (
                    ("low", "probability_low"),
                    ("mid", "probability"),
                    ("high", "probability_high"),
                )
            }
            marginal_interval = [
                best_marginal - marginal_wait["high"],
                best_marginal - marginal_wait["low"],
            ]
            vorp_interval = [best_vorp - vorp_wait["high"], best_vorp - vorp_wait["low"]]
            stable = (
                marginal_interval[0] * marginal_interval[1] > 0
                and vorp_interval[0] * vorp_interval[1] > 0
            )
            stable_states += int(stable)
            state["vona"] = {
                "terminal_marginal": {
                    "best_current": best_marginal,
                    "expected_best_later": marginal_wait,
                    "value_over_next_alternative_interval": marginal_interval,
                },
                "static_vorp": {
                    "best_current": best_vorp,
                    "expected_best_later": vorp_wait,
                    "value_over_next_alternative_interval": vorp_interval,
                },
                "stable_signs": stable,
            }
        states.append(state)
    candidate_coverage = supported_candidates / total_candidates
    state_coverage = fully_supported / len(states)
    stability = stable_states / fully_supported if fully_supported else 0.0
    passed = candidate_coverage >= 0.70 and state_coverage >= 0.50 and stability >= 0.80
    result = {
        "experiment": "exact survival coverage for current VONA and static VORP",
        "status": "offline_analysis_ready" if passed else "rejected",
        "lookup_status": lookup["status"],
        "lookup_model_version": lookup["model_version"],
        "gate": {
            "passes": passed,
            "candidate_coverage": candidate_coverage,
            "required_candidate_coverage": 0.70,
            "fully_supported_state_coverage": state_coverage,
            "required_state_coverage": 0.50,
            "stable_sign_rate": stability,
            "required_stable_sign_rate": 0.80,
        },
        "counts": {
            "states": len(states),
            "top_ten_candidates": total_candidates,
            "supported_candidates": supported_candidates,
            "fully_supported_states": fully_supported,
            "stable_states": stable_states,
        },
        "states": states,
        "skipped_files": skipped,
        "limitations": [
            "saved current 2026 states are a coverage and sensitivity audit, not an outcome backtest",
            "historical point-in-time projections are unavailable",
            "expected-best values assume independent player survival",
            "static VORP and roster-specific terminal marginal value remain separate",
            "no live VONA, WORP, rollout, API, or UI integration",
        ],
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": result["status"], "gate": result["gate"], "counts": result["counts"]}, indent=2))


if __name__ == "__main__":
    main()
