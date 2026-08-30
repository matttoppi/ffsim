#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

from ffsim.draft_intel.timing_report import build_cached_timing_context
from ffsim.historical_sleeper.hdvn_snapshot import canonical_json, sha256_file

ROOT = Path(__file__).parents[3]
HERE = Path(__file__).parent
DRAFT_IDS = (
    "1393628519644286976",
    "1393634461312106496",
    "1393656492011315200",
    "1393721396240080896",
    "1393746402558881792",
    "1394035775644913664",
)


def main():
    states = []
    for draft_id in DRAFT_IDS:
        original_path = ROOT / "tmp" / f"timing-{draft_id}.json"
        original = json.loads(original_path.read_text())
        league_id = str(original["league_id"])
        config = HERE / (
            "config-12.json" if league_id == "1389391547115511808" else "config-10.json"
        )
        league = ROOT / "data/cache" / f"league_{league_id}.json"
        draft = ROOT / "data/cache" / f"mock_draft_{draft_id}.json"
        context = build_cached_timing_context(
            config,
            league,
            roster_id=int(original["roster_id"]),
            draft_cache=draft,
            world_count=20,
        )
        state = context["state"]
        if state.current_roster_id != int(original["roster_id"]):
            raise RuntimeError(f"roster is not on the clock for {draft_id}")
        if state.current_pick_no != int(original["pick_no"]):
            raise RuntimeError(f"pick number changed for {draft_id}")
        states.append({
            "draft_id": draft_id,
            "league_id": league_id,
            "roster_id": int(original["roster_id"]),
            "pick_no": int(original["pick_no"]),
            "round": int(original["round"]),
            "gap": int(original["opponent_picks_until_next"]),
            "teams": int(state.teams),
            "config": str(config.relative_to(ROOT)),
            "league_cache": str(league.relative_to(ROOT)),
            "draft_cache": str(draft.relative_to(ROOT)),
            "original_timing_report": str(original_path.relative_to(ROOT)),
            "hashes": {
                "config": sha256_file(config),
                "league_cache": sha256_file(league),
                "draft_cache": sha256_file(draft),
                "original_timing_report": sha256_file(original_path),
            },
        })
    teams = {state["teams"] for state in states}
    rounds = {state["round"] for state in states}
    gaps = [state["gap"] for state in states]
    gate = {
        "six_states": len(states) == 6,
        "team_counts_10_and_12": teams == {10, 12},
        "early_middle_later": (
            any(round_number <= 2 for round_number in rounds)
            and any(3 <= round_number <= 6 for round_number in rounds)
            and any(round_number >= 7 for round_number in rounds)
        ),
        "short_medium_full_turn_gaps": (
            any(gap <= 2 for gap in gaps)
            and any(3 <= gap <= 10 for gap in gaps)
            and any(gap >= 18 for gap in gaps)
        ),
    }
    gate["passes"] = all(gate.values())
    if not gate["passes"]:
        raise RuntimeError(f"multi-state corpus gate failed: {gate}")
    body = {
        "corpus_version": "alpha-multi-state-v1",
        "status": "research",
        "world_count": 20,
        "states": states,
        "gate": gate,
        "limitations": [
            "cached mock states only",
            "no realized draft outcome labels",
            "current projection and market caches are frozen by hash",
        ],
    }
    body["sha256"] = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    (HERE / "corpus.json").write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "states": len(states),
        "team_counts": sorted(teams),
        "rounds": sorted(rounds),
        "gaps": sorted(gaps),
        "gate": gate,
        "sha256": body["sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
