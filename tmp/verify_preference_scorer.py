"""One-off: compare corrected preference utility vs the old full-credit sum
on the owner's real pick-24 mock state. Diagnostic only."""
import json
import time

from ffsim.config import AppConfig
from ffsim.paths import CACHE_DIR
from ffsim.loaders.players import PlayerLoader
from ffsim.models.league import League
from ffsim.simulation.world_bank import build_season_world_bank, draftable_players
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.draft_intel.decision import evaluate_candidates, rank_candidates
from ffsim.draft_intel.live import (
    PreparedDraft, _bank_market_snapshot, _live_market_snapshot,
    _live_opponent_choice, LIVE_TEMPERATURE,
)
from ffsim.draft_intel.market_model import load_league_market_snapshot
from ffsim.draft_intel.opportunity import next_turn_user_policy
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
evaluator = LeagueEvaluator(league_model, bank, range(1, 13), config.regular_season_weeks, seed=config.seed)
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
]
owners = []
for rnd in range(15):
    row = list(range(1, 13))
    owners.extend(row if rnd % 2 == 0 else row[::-1])
picks = tuple(
    {"draft_id": "verify24", "pick_no": n + 1, "round": n // 12 + 1,
     "draft_slot": owners[n], "roster_id": owners[n],
     "player_id": name_to_bank[feed[n]]}
    for n in range(23)
)
draft = {
    "draft_id": "verify24", "type": "snake", "status": "drafting",
    "settings": {"teams": 12, "rounds": 15, "reversal_round": 0},
    "draft_order": {str(r): r for r in range(1, 13)},
    "slot_to_roster_id": {str(r): r for r in range(1, 13)},
}
state = replay_sleeper_draft(draft, picks=picks, traded_picks=(), player_ids=bank.player_ids)
offsets = {str(k): float(v) for k, v in prepared.personal_ranks.items()}
snap = _bank_market_snapshot(prepared)
choose = _live_opponent_choice(snap, evaluator, state, LIVE_TEMPERATURE)
policy = next_turn_user_policy(evaluator, state, choose, offsets)
cands = [name_to_bank[n] for n in ("Malik Nabers", "Rashee Rice", "Chris Olave")]
names = dict(zip(cands, ("Nabers", "Rice", "Olave")))

t0 = time.time()
evaluation = evaluate_candidates(
    state, cands, 1, range(60), choose, policy, evaluator,
    draft_model_version="verify-v1", seed=2026, temperature=1.0,
    personal_values=offsets,
)
print(f"evaluated in {time.time()-t0:.1f}s")
for cand in rank_candidates(evaluation):
    raw = cand.projected_roster_value
    pref = cand.preference_adjusted_value
    print(f"{names[cand.candidate_id]:7s} raw={raw:8.1f}  preference(lineup-consistent)={pref:8.1f}  shift={pref-raw:+7.1f}")
