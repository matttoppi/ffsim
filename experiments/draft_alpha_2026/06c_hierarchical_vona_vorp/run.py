#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

from scipy.stats import beta

ROOT = Path(__file__).parents[3]
MODEL_PATH = Path(__file__).parents[1] / "06_hierarchical_survival/result.json"
DIAGNOSTIC_PATH = (
    Path(__file__).parents[1] / "06b_hierarchical_2024_diagnostic/result.json"
)
EXPECTED_DIAGNOSTIC_SHA256 = (
    "8d47c215c06a932be589f8d1ae85253f135aaede77d934c3ef2ad2f62c5d5d0a"
)


def scoring_format(league):
    reception = float(league["scoring_settings"].get("rec", 0.0))
    return "PPR" if reception >= 0.75 else "HALF_PPR" if reception > 0 else "STD"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_best(players, key):
    result = 0.0
    better_gone = 1.0
    for player in sorted(players, key=lambda item: (-item["value"], item["player_id"])):
        survives = player[key]
        result += player["value"] * survives * better_gone
        better_gone *= 1 - survives
    return result


def load_model():
    artifact = json.loads(MODEL_PATH.read_text())
    if artifact["status"] != "research" or not artifact["gate"]["passes"]:
        raise RuntimeError("hierarchical survival artifact did not pass")
    if sha256(DIAGNOSTIC_PATH) != EXPECTED_DIAGNOSTIC_SHA256:
        raise RuntimeError("hierarchical 2024 diagnostic hash changed")
    diagnostic = json.loads(DIAGNOSTIC_PATH.read_text())
    if diagnostic["status"] != "research" or not diagnostic["gate"]["passes"]:
        raise RuntimeError("hierarchical 2024 diagnostic did not pass")
    payload = artifact["model"]
    return {
        "global": payload["global"],
        "pooled": {tuple(cell["key"]): (cell["successes"], cell["count"]) for cell in payload["pooled_cells"]},
        "position": {tuple(cell["key"]): (cell["successes"], cell["count"]) for cell in payload["position_cells"]},
        "shrinkage": float(artifact["shrinkage_observations"]),
        "sha256": sha256(MODEL_PATH),
    }


def survival(model, rank, gap, round_, position):
    pooled = model["pooled"].get((rank, gap, round_), model["global"])
    prior = (pooled[0] + 1) / (pooled[1] + 2)
    direct = model["position"].get((rank, gap, round_, position), (0, 0))
    alpha = direct[0] + model["shrinkage"] * prior
    beta_value = direct[1] - direct[0] + model["shrinkage"] * (1 - prior)
    return {
        "probability": alpha / (alpha + beta_value),
        "probability_low": float(beta.ppf(0.025, alpha, beta_value)),
        "probability_high": float(beta.ppf(0.975, alpha, beta_value)),
        "direct_successes": direct[0],
        "direct_count": direct[1],
        "pooled_successes": pooled[0],
        "pooled_count": pooled[1],
    }


def main():
    model = load_model()
    states = []
    skipped = []
    total_candidates = stable_marginal = stable_vorp = 0
    for path in sorted((ROOT / "tmp").glob("timing-*.json")):
        report = json.loads(path.read_text())
        if "players" not in report:
            skipped.append({"source": str(path.relative_to(ROOT)), "reason": "not_timing_report"})
            continue
        league_path = ROOT / "data/cache" / f"league_{report['league_id']}.json"
        if not league_path.exists():
            skipped.append({"source": str(path.relative_to(ROOT)), "reason": "missing_league_cache"})
            continue
        league = json.loads(league_path.read_text())["league"]
        candidates = {}
        for player in report["players"]:
            rank = int(player["market_rank"])
            if rank <= 10:
                candidates.setdefault(rank, player)
        candidates = [candidates[rank] for rank in sorted(candidates)]
        total_candidates += len(candidates)
        marginal = []
        vorp = []
        player_rows = []
        for player in candidates:
            estimate = survival(
                model,
                int(player["market_rank"]),
                int(report["opponent_picks_until_next"]),
                int(report["round"]),
                str(player["position"]),
            )
            common = {"player_id": player["player_id"], **estimate}
            marginal.append({**common, "value": float(player["current_roster_value"])})
            vorp.append({
                **common,
                "value": float(player["projected_points"] - player["replacement_points"]),
            })
            player_rows.append({
                "player_id": player["player_id"],
                "name": player["name"],
                "market_rank": player["market_rank"],
                "position": player["position"],
                "terminal_marginal_value": float(player["current_roster_value"]),
                "static_vorp": float(player["projected_points"] - player["replacement_points"]),
                **estimate,
            })
        def value_summary(players):
            best = max(player["value"] for player in players)
            later = {
                name: expected_best(players, key)
                for name, key in (
                    ("low", "probability_low"),
                    ("mid", "probability"),
                    ("high", "probability_high"),
                )
            }
            interval = [best - later["high"], best - later["low"]]
            return {
                "best_current": best,
                "expected_best_later": later,
                "value_over_next_alternative_interval": interval,
                "stable_sign": interval[0] * interval[1] > 0,
            }
        marginal_summary = value_summary(marginal)
        vorp_summary = value_summary(vorp)
        stable_marginal += int(marginal_summary["stable_sign"])
        stable_vorp += int(vorp_summary["stable_sign"])
        states.append({
            "source": str(path.relative_to(ROOT)),
            "source_sha256": sha256(path),
            "draft_id": report["draft_id"],
            "pick_no": report["pick_no"],
            "round": report["round"],
            "gap": report["opponent_picks_until_next"],
            "scoring_format": scoring_format(league),
            "team_count": league["total_rosters"],
            "candidate_count": len(player_rows),
            "players": player_rows,
            "terminal_marginal_vona": marginal_summary,
            "static_vorp_vona": vorp_summary,
        })
    expected_candidates = len(states) * 10
    coverage = total_candidates / expected_candidates if expected_candidates else 0.0
    complete_states = sum(len(state["players"]) == 10 for state in states)
    passed = coverage == 1.0 and complete_states == len(states) and bool(states)
    result = {
        "experiment": "hierarchical survival with current 2026 VONA and static VORP",
        "status": "offline_analysis_ready" if passed else "rejected",
        "model_sha256": model["sha256"],
        "diagnostic_sha256": EXPECTED_DIAGNOSTIC_SHA256,
        "gate": {"passes": passed, "top_ten_coverage": coverage, "required_coverage": 1.0},
        "counts": {
            "states": len(states),
            "top_ten_candidates": total_candidates,
            "complete_top_ten_states": complete_states,
            "stable_terminal_marginal_states": stable_marginal,
            "stable_static_vorp_states": stable_vorp,
        },
        "states": states,
        "skipped_files": skipped,
        "limitations": [
            "current 2026 states are a coverage and sensitivity audit, not an outcome backtest",
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
