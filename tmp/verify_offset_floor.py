"""One-off: decompose the ADR-046 sub-cutline offset over-credit on the
owner's replayed pick-25 mock state (Ferguson/Likely/Pitts/Loveland).
Prints the policy-path decomposition before/after the pre-floor fix, the
terminal scorer's adjusted marginal, corrected policy current_values, and
the projection board's TE plan. Diagnostic only."""
import json

from ffsim.config import AppConfig
from ffsim.paths import CACHE_DIR
from ffsim.loaders.players import PlayerLoader
from ffsim.models.league import League
from ffsim.simulation.world_bank import build_season_world_bank, draftable_players
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.draft_intel.live import (
    PreparedDraft, _bank_market_snapshot, _live_opponent_choice,
    _live_market_snapshot, projection_value_board, LIVE_TEMPERATURE,
)
from ffsim.draft_intel.market_model import load_league_market_snapshot
from ffsim.draft_intel.opportunity import (
    next_turn_user_policy, season_value_over_replacement,
)
from ffsim.draft_intel.personal_ranks import load_offsets
from ffsim.draft_intel.state import replay_sleeper_draft

config = AppConfig.from_file("config.json")
snapshot = json.loads((CACHE_DIR / f"league_{config.league_id}.json").read_text())
league_model = League(snapshot["league"])
loader = PlayerLoader()
loader.load_players()
bank = build_season_world_bank(
    league_model, draftable_players(loader.enriched_players), 300,
    weeks=config.regular_season_weeks + 3, seed=config.seed,
)
evaluator = LeagueEvaluator(
    league_model, bank, range(1, 13), config.regular_season_weeks,
    seed=config.seed,
)
market = load_league_market_snapshot(snapshot["league"], season=2026, max_age=None)
prepared = PreparedDraft(
    summary={"market_context": market["context"]}, live_draft_id="verify",
    league_id=config.league_id, standalone=False, user_roster_id=1,
    market_snapshot=_live_market_snapshot(market["snapshot"]),
    evaluator=evaluator, player_details={}, personal_ranks=load_offsets(),
)
details = json.loads((CACHE_DIR / "sleeper_players.json").read_text())
bank_ids = set(bank.player_ids)
name_to_bank = {}
for pid, p in details.items():
    if p.get("full_name") and pid in bank_ids:
        name_to_bank.setdefault(p["full_name"], pid)
feed = [
    "Bijan Robinson", "Jahmyr Gibbs", "Puka Nacua", "Ja'Marr Chase",
    "Christian McCaffrey", "Jaxon Smith-Njigba", "Jonathan Taylor",
    "Amon-Ra St. Brown", "Justin Jefferson", "CeeDee Lamb", "James Cook",
    "Drake London", "Omarion Hampton", "De'Von Achane", "Saquon Barkley",
    "A.J. Brown", "Chase Brown", "Ashton Jeanty", "Derrick Henry",
    "Josh Allen", "Brock Bowers", "Kenneth Walker", "Nico Collins",
    "Malik Nabers",  # user's pick 24 -> the replayed state is pick 25
]
owners = []
for rnd in range(15):
    row = list(range(1, 13))
    owners.extend(row if rnd % 2 == 0 else row[::-1])
picks = tuple(
    {"draft_id": "verify25", "pick_no": n + 1, "round": n // 12 + 1,
     "draft_slot": owners[n], "roster_id": owners[n],
     "player_id": name_to_bank[feed[n]]}
    for n in range(24)
)
draft = {
    "draft_id": "verify25", "type": "snake", "status": "drafting",
    "settings": {"teams": 12, "rounds": 15, "reversal_round": 0},
    "draft_order": {str(r): r for r in range(1, 13)},
    "slot_to_roster_id": {str(r): r for r in range(1, 13)},
}
state = replay_sleeper_draft(
    draft, picks=picks, traded_picks=(), player_ids=bank.player_ids,
)
offsets = {str(k): float(v) for k, v in prepared.personal_ranks.items()}
snap = _bank_market_snapshot(prepared)
choose = _live_opponent_choice(snap, evaluator, state, LIVE_TEMPERATURE)

targets = {
    "Ferguson": name_to_bank["Terrance Ferguson"],
    "Likely": name_to_bank["Isaiah Likely"],
    "Pitts": name_to_bank["Kyle Pitts"],
    "Loveland": name_to_bank["Colston Loveland"],
}

projection, position_of, replacement = season_value_over_replacement(evaluator)
weeks = len(evaluator.bank.weeks)
weekly_cut = {p: v / weeks for p, v in replacement.items()}
scores, available = evaluator.flat_season_scores()
raw = evaluator._mean_scores_raw  # diagnostic-only pre-floor basis
adj_scores, _ = evaluator.adjusted_flat_season_scores(offsets)
index = {pid: i for i, pid in enumerate(evaluator.bank.player_ids)}

base_rosters = {
    rid: [index[p] for p in players] for rid, players in state.rosters
}
base_value = evaluator.projected_roster_value(base_rosters, 1, offsets)

print(f"TE replacement (season): {replacement['TE']:.1f}  "
      f"weekly cut: {weekly_cut['TE']:.3f}")
print(f"{'player':9s} {'off':>5s} {'raw':>7s} {'aw':>3s} {'aw*cut':>7s} "
      f"{'floored':>8s} {'OLD fval':>8s} {'NEW sp':>8s} {'NEW fval':>8s} "
      f"{'scorer\u0394':>8s}")
for name, pid in targets.items():
    i = index[pid]
    off = offsets.get(pid, 0.0)
    aw = int(available[i].sum())
    cut = weekly_cut.get(position_of[pid], 0.0)
    raw_season = float(raw[i].sum())
    floored_season = float(scores[i].sum())
    old_sp = floored_season + off
    old_fval = max(0.0, old_sp - aw * cut)
    new_sp = float(adj_scores[i].sum())
    new_fval = max(0.0, new_sp - aw * cut)
    with_player = {r: list(p) for r, p in base_rosters.items()}
    with_player[1].append(i)
    scorer_delta = (
        evaluator.projected_roster_value(with_player, 1, offsets) - base_value
    )
    print(f"{name:9s} {off:+5.0f} {raw_season:7.1f} {aw:3d} {aw*cut:7.1f} "
          f"{floored_season:8.1f} {old_fval:8.1f} {new_sp:8.1f} "
          f"{new_fval:8.1f} {scorer_delta:8.1f}")

policy = next_turn_user_policy(evaluator, state, choose, offsets)
values = policy.current_values(1, state.rosters, state.available_player_ids)
print("\npolicy current_values (post-fix):")
for name, pid in targets.items():
    print(f"  {name:9s} {values.get(pid, float('nan')):8.2f}")
te_leader = max(
    (pid for pid in values if position_of.get(pid) == "TE"),
    key=lambda pid: (values[pid], pid),
)
print(f"TE current-value leader: "
      f"{next(n for n, p in targets.items() if p == te_leader) if te_leader in targets.values() else te_leader}")

board = projection_value_board(prepared, state)
te_plan = [row for row in board["plans"] if row["position"] == "TE"]
print("\nboard TE plan:", te_plan)
