## 35. Suggested Algorithms and Pseudocode

### 35.1 Historical ingestion

```python
def ingest_manager_history(target_league, seasons):
    managers = sleeper.get_league_users(target_league.id)
    unique_drafts = {}

    for manager in managers:
        for season in seasons:
            for draft_meta in sleeper.get_user_drafts(manager.user_id, season):
                unique_drafts.setdefault(draft_meta.draft_id, draft_meta)

    for draft_id, meta in unique_drafts.items():
        draft = sleeper.get_draft(draft_id)
        picks = sleeper.get_draft_picks(draft_id)
        store_raw_and_normalized(draft, picks)

    rebuild_opportunity_sets()
    rebuild_manager_features()
```

### 35.2 Live state update

```python
def reconcile_live_state(session):
    remote_picks = sleeper.get_draft_picks(session.draft_id)

    for pick in sorted(remote_picks, key=lambda p: p.pick_no):
        if pick.pick_no <= session.last_applied_pick:
            assert_consistent(pick, session)
            continue
        session.apply_pick(pick)

    session.update_room_shifts()
    session.schedule_speculative_recommendation()
```

### 35.3 Opponent pick sampling

```python
def sample_opponent_pick(state, manager, rollout_id):
    candidates = plausible_candidates(state, manager)
    utilities = choice_model.utilities(manager, candidates, state)

    scores = []
    for player, utility in zip(candidates, utilities):
        shock = stable_gumbel(
            seed=state.seed,
            rollout_id=rollout_id,
            pick_no=state.pick_no,
            manager_id=manager.id,
            player_id=player.id,
        )
        scores.append(utility + shock)

    return candidates[argmax(scores)]
```

### 35.4 Rest-of-draft rollout

```python
def complete_draft(root_state, root_candidate, rollout_id):
    state = root_state.lightweight_copy()
    state.force_user_pick(root_candidate)

    while not state.is_complete:
        manager = state.current_pick_owner

        if manager.id == state.user_manager_id:
            player = user_rollout_policy.choose(state)
        else:
            player = sample_opponent_pick(state, manager, rollout_id)

        state.apply_simulated_pick(manager, player)

    return state.roster_assignment()
```

### 35.5 Root candidate evaluation

```python
def evaluate_candidate(candidate, root_state, rollout_ids, world_bank):
    outcomes = []

    for rollout_id in rollout_ids:
        rosters = complete_draft(root_state, candidate, rollout_id)
        world_id = coupled_world_id(root_state.seed, rollout_id)
        result = league_evaluator.evaluate_one_world(
            roster_assignment=rosters,
            world=world_bank[world_id],
            league_context=root_state.league,
        )
        outcomes.append(result.for_user())

    return aggregate_candidate_outcomes(outcomes)
```

### 35.6 Adaptive refinement

```python
candidates = generate_root_candidates(state)
results = evaluate_all(candidates, samples=150)

candidates = keep_plausible_winners(results, max_count=6)
results = refine(candidates, additional_samples=850)

candidates = keep_plausible_winners(results, max_count=3)
while time_budget_remaining() and not decision_separated(results):
    results = refine(candidates, additional_samples=1000)

publish(results)
```

---

## 36. Example Recommendation Object

```json
{
  "draft_id": "...",
  "state_pick_no": 43,
  "user_pick_no": 43,
  "next_user_pick_no": 54,
  "candidate": {
    "player_id": "canonical-123",
    "name": "Player A",
    "position": "RB"
  },
  "action": "TAKE_NOW",
  "market": {
    "target_platform_adp": 49.2,
    "cross_platform_median_adp": 52.7,
    "internal_value_rank": 36,
    "freshness_minutes": 180
  },
  "availability": {
    "survive_to_next_pick": 0.19,
    "tier_survive_to_next_pick": 0.28,
    "expected_tier_players_remaining": 0.42,
    "top_threats": [
      {"manager_id": "chris", "elimination_share": 0.31},
      {"manager_id": "ryan", "elimination_share": 0.24}
    ]
  },
  "season": {
    "championship_probability": 0.186,
    "playoff_probability": 0.714,
    "average_wins": 8.7,
    "paired_delta_vs_next_best": 0.019,
    "paired_delta_ci": [0.006, 0.032]
  },
  "simulation": {
    "joint_outcomes": 8120,
    "draft_model_version": "...",
    "world_bank_hash": "...",
    "seed_family": 2026
  },
  "confidence": {
    "decision": "medium_high",
    "opponent_model": "medium",
    "market": "high"
  },
  "reason_codes": [
    "PAIRED_CHAMPIONSHIP_EDGE",
    "LOW_RETURN_PROBABILITY",
    "HIGH_PERSONALIZED_THREAT",
    "TIER_CLIFF"
  ]
}
```

---

## 37. Example End-to-End User Flow

### Several days before draft

1. User chooses Sleeper league.
2. Tool crawls league mates' current/prior drafts.
3. Tool deduplicates shared drafts.
4. Tool shows data coverage and weak managers.
5. Tool refreshes projections and market snapshots.
6. Tool builds manager profiles.
7. Tool builds SeasonWorldBank.
8. Tool offers manual manager/player notes.

### One hour before draft

1. Refresh target draft metadata/order.
2. Refresh market snapshot.
3. Refresh any same-day completed league-mate drafts.
4. Rebuild affected profiles.
5. Validate world bank against current projection hash.
6. Run preflight benchmark and data-health checks.

### During draft

1. Poll live picks.
2. Reconcile pick state.
3. Update manager roster/needs and live room shifts.
4. Predict likely availability at user's upcoming pick.
5. Speculatively evaluate candidates before user's clock.
6. On user's turn, publish fast pass immediately.
7. Continue refining top candidates.
8. User drafts a player.
9. Real pick is observed/reconciled; loop continues.

### After draft

1. Persist final recommendation history.
2. Compare real picks with survival predictions.
3. Run full completed-roster `ffsim` with high sample count.
4. Produce model audit:
   - where predictions were correct
   - where manager behavior surprised the model
   - calibration errors
5. Add this draft to future current-season manager evidence.

---

## 38. Future Extensions

After V1 is validated:

- Auction draft engine.
- Dynasty/keeper-specific choice models.
- Season-long waiver and trade optimizer using the same title-equity objective.
- Explicit value-of-information recommendations when uncertain manager signals matter.
- Browser extension/overlay on top of Sleeper draft room.
- Mobile companion view.
- Remote 3090 compute worker.
- Full cross-platform identity and draft-history imports for authorized leagues.
- Learned surrogate model approximating expensive championship deltas for future user rollout picks.
- Raw-stat season world bank reusable across different league scoring systems.
- Portfolio-level objective across all leagues rather than per-league independent optimization.

---

## 39. Source Registry and Current External Constraints

The implementation agent must re-check external documentation when coding because APIs and licensing can change.

**[S1] Sleeper API documentation**  
https://docs.sleeper.com/  
Current documented capabilities used by this spec: read-only API without token; users, leagues, rosters, drafts, draft details, picks, traded picks, player map; general guidance to remain under 1000 calls/minute; player map need not be fetched more than daily.

**[S2] FantasyPros API overview**  
https://www.fantasypros.com/api-data/  
Current documented capabilities used by this spec: consensus rankings/ADP, projections, players/external IDs, news, injuries, REST API and API-key access.

**[S3] FantasyPros API reference**  
https://api.fantasypros.com/v2/docs  
Use to verify exact 2026 fields/parameters at implementation time.

**[S4] FantasyPros API access/licensing guidance**  
https://support.fantasypros.com/hc/en-us/articles/49749297704475-How-do-I-request-access-to-the-FantasyPros-API  
Current guidance distinguishes free prototype, personal production/premium, and commercial use.

**[S5] Yahoo Fantasy Sports API**  
https://developer.yahoo.com/fantasysports/guide/  
Current documented REST fantasy API with OAuth authorization.

**[S6] Fleaflicker API reference**  
https://www.fleaflicker.com/api-docs/index.html  
Current documented endpoints include draft board, league rules, rosters, and league activity.

### Existing repository references inspected for this specification

**[R1] Repository**  
https://github.com/matttoppi/ffsim

**[R2] README**  
https://github.com/matttoppi/ffsim/blob/main/README.md

**[R3] Monte Carlo engine**  
https://github.com/matttoppi/ffsim/blob/main/ffsim/simulation/monte_carlo.py

**[R4] Season simulation**  
https://github.com/matttoppi/ffsim/blob/main/ffsim/simulation/season.py

**[R5] Fantasy team model**  
https://github.com/matttoppi/ffsim/blob/main/ffsim/models/team.py

**[R6] League loader**  
https://github.com/matttoppi/ffsim/blob/main/ffsim/loaders/league.py

**[R7] Player loader**  
https://github.com/matttoppi/ffsim/blob/main/ffsim/loaders/players.py

**[R8] Simulation tracker**  
https://github.com/matttoppi/ffsim/blob/main/ffsim/simulation/tracker.py

**[R9] Runtime construction**  
https://github.com/matttoppi/ffsim/blob/main/ffsim/runtime.py

---

## 40. Final Product Definition

The completed system should not answer only:

> Who is the best player available?

It should answer:

> If I take Player A now, how does that change the distribution of what these exact managers will do before I pick again, what roster combinations I am likely to end up with, and ultimately my probability of winning this league compared with taking Player B or waiting on Player A?

The product is successful when it can transform data that is individually weak - a few league-mate drafts, platform ADP differences, current roster needs, exact draft order, live room behavior, projections, injuries, and schedule variance - into one coherent and calibrated decision process without pretending any single signal is stronger than it is.

The highest-value implementation is therefore a **live, manager-conditioned, multi-market draft rollout engine whose terminal objective is paired `ffsim` championship equity**.
