## 19. Decision Objective and Recommendation Logic

### 19.1 Primary objective

For root candidate `p`:

```text
Q(p) = estimated championship probability after selecting p now
       and following the configured future user policy
```

Select the candidate with the highest sufficiently supported `Q(p)`.

When paired uncertainty makes several candidates statistically
interchangeable, retain the raw `Q(p)` leader as the headline and present the
co-leaders as an unordered low-confidence tier. A secondary metric such as
exact-player return probability must not silently replace the primary leader.

### 19.2 Secondary metrics

Report, but do not silently blend into the primary objective unless configured:

- playoff probability
- average wins
- average points
- top-two seed probability
- downside/bottom-two probability
- next-pick survival
- tier survival
- expected next-pick value
- portfolio exposure

If championship deltas are statistically indistinguishable, secondary metrics can be tie-breakers or the UI can state that the decision is effectively a toss-up.

### 19.3 Paired championship delta

For top candidate A versus B:

```text
DeltaChamp(A,B) = mean(ChampOutcome_A_i - ChampOutcome_B_i)
```

Because each individual outcome is binary, also track paired win/loss/tie style comparisons across coupled rollouts/worlds:

- A wins branch, B does not
- B wins branch, A does not
- both win / both lose

Use bootstrap or an appropriate paired uncertainty estimator to derive a confidence interval for the difference.

### 19.4 No fake precision

Display whole percentages by default. For small differences, display uncertainty explicitly.

Good:

```text
Achane: 18.6%
Nabers: 18.3%
Difference: +0.3 percentage points
Decision confidence: LOW
```

Bad:

```text
Achane 18.6127% > Nabers 18.2984%, therefore definitely draft Achane.
```

### 19.5 Recommendation labels

Labels are explanatory, not the objective function:

- `TAKE NOW`
- `WAIT`
- `JUSTIFIED REACH`
- `SAFE VALUE`
- `TIER CLIFF`
- `LOW-CONFIDENCE TOSS-UP`
- `MANUAL TARGET CONFLICT`

Every label must be derivable from stored metrics/reason codes.

---

## 20. League-Specific Player Value

### 20.1 Reuse `ffsim` scoring

The system already rescales projections to the league's Sleeper scoring. Continue to use league-specific scoring rather than generic PPR rank wherever possible.

### 20.2 Marginal lineup value

Player value depends on roster context:

- starting slot availability
- flex/superflex eligibility
- replacement level
- bench depth
- existing roster strengths
- injury/bye coverage

A third RB has a different marginal value on a roster with two elite RBs than on a roster with none.

### 20.3 VONA

Define value over next availability:

```text
VONA(p) = value(p now)
          - E[value(best realistic alternative at next user pick)]
```

Adjacent user picks are one turn; the horizon is the first user pick after an
opponent has selected. The expectation must use the conditional opponent model,
exact pick ownership, current roster, available pool, starter needs, and caps.
The future policy compares current value plus expected later roster value rather
than ranking positions by VONA alone, so a scarce but materially inferior player
does not win mechanically. VONA remains a policy feature and explanation; the
root recommendation is still coupled championship equity.

### 20.4 Correlation and stacking

Do not automatically reward stacks just because they are popular. The existing season world model already creates some natural player correlations through shared game/team factors. Additional draft-level stack preference should affect the user's value only if backtesting or simulation demonstrates portfolio/championship benefit under the league structure.

### 20.5 Injury and projection uncertainty

Preserve current `ffsim` projection uncertainty and injury/availability modeling in season worlds. Do not double-penalize injury risk in both player value and season simulation unless the components are explicitly separated.

---

## 21. Live War Room UX

The UI should optimize for a 60-90 second decision, not for displaying every model feature simultaneously.

### 21.1 Pre-draft setup screen

Show:

- selected Sleeper league
- draft date/time/status
- user team/slot
- league format summary
- data-source status
- last ADP refresh time
- projection/world-bank hash and freshness
- league-mate history coverage

### 21.2 Data-quality report

Example:

| Manager | Relevant drafts | 2026 drafts | Shared drafts | Personalization confidence |
|---|---:|---:|---:|---|
| Chris | 7 | 4 | 3 | High |
| Ryan | 3 | 1 | 2 | Low |
| John | 6 | 3 | 0 | Medium |

Make weak data obvious before the draft starts.

### 21.3 Manager cards

Compact profile:

```text
CHRIS - MEDIUM/HIGH CONFIDENCE
Board adherence: Low
Draft volatility: High
First QB: usually R5-R7
Early rounds: WR-heavy
Repeat-player tendency: High
2026 elevated targets: A, B, C
Current live roster: WR, WR, RB
```

### 21.4 Main on-the-clock view

Top area:

```text
YOU ARE ON THE CLOCK - PICK 4.07
14 selections until 5.06
Live sync: healthy - last pick 0.8s ago
Recommendation confidence: medium
```

A persistent league rail shows every roster ranked by current championship
probability, plus playoff probability. It updates after every synchronized
pick, including opponent turns, and remains visible with an explicit
preliminary/refining state while the newest calculation runs. These absolute
odds must retain the uncalibrated-model label until backtesting supports a
calibration claim.

Candidate table/card fields (rank only candidates evaluated to the same
refinement depth; earlier-stage estimates belong in a separate unranked
watchlist):

- rank
- player
- position/team
- action label
- championship probability
- delta vs best alternative
- playoff probability
- chance player returns
- chance tier survives
- current marginal value and expected best next-turn alternative
- expected positional/value drop and alternative distribution
- target-platform ADP/board
- cross-platform median
- main threat manager(s)
- confidence

### 21.5 Candidate detail panel

For a selected candidate:

- Why take/wait.
- Exact survival curve to next pick.
- Threat managers and their reasons.
- Manager history evidence counts, not just percentages.
- Expected next two-pick combinations.
- Tier alternatives.
- Championship-delta uncertainty.
- What assumptions are low-confidence.
- Opportunity sample count and policy/model version.

### 21.6 "What changed?" panel

After every real pick, explain recommendation movement:

```text
Player B was drafted by Chris.
- WR tier survival dropped from 71% to 42%.
- Ryan now has two RBs, reducing his modeled Player A risk.
- Player C moved from WAIT to TAKE NOW.
```

### 21.7 Draft-order threat rail

Show the exact managers before the user's next pick in order, with small badges for:

- likely position
- high-affinity target
- board-following confidence

This directly visualizes why "close to me" matters.

### 21.8 Manual controls

Allow:

- pin target
- fade/do-not-draft
- override personal rank
- add manager signal
- temporarily ignore one market source
- force manual current pick if sync is broken
- choose objective mode (championship-first by default)

### 21.9 Performance UX

Recommendations may refine over time. Show this honestly:

```text
FAST PASS complete
1,120 paired outcomes
Refining top 3 candidates...
```

Never block the interface waiting for a final high-sample result.

---

## 22. Multi-League Portfolio Mode

This is optional for the initial live tool but strategically useful when drafting many leagues.

Track user exposure:

```text
Player A: 4 / 6 leagues
Player B: 0 / 6 leagues
Player C: 3 / 6 leagues
```

Configurable modes:

**Maximize each league independently**
- default
- no exposure penalty

**Moderate diversification**
- use exposure only as a tie-breaker among near-equal championship branches

**High-conviction concentration**
- allow repeated exposure when internal value strongly exceeds market

Do not sacrifice a major single-league title-equity edge merely to diversify unless the user explicitly selects that objective.

Earlier completed drafts should also become fresh current-season opponent evidence for later drafts against the same managers.

---

## 23. Storage and Database Design

The current project uses local cached files. Keep those for raw source snapshots and world-bank arrays. Add a lightweight relational store for normalized history and model outputs.

For a personal local-first app, **SQLite** is preferred for V1. PostgreSQL can be introduced later if multi-user hosting requires it.

### 23.1 Core tables

```text
managers
  id PK
  sleeper_user_id UNIQUE
  display_name
  created_at

manager_external_identities
  manager_id
  platform
  external_id
  verified

leagues
  id PK
  platform_league_id
  season
  platform
  name
  format_hash
  raw_snapshot_path/hash

league_managers
  league_id
  manager_id
  roster_id

historical_drafts
  id PK
  platform_draft_id UNIQUE
  league_id nullable
  season
  platform
  draft_type
  scoring_type
  team_count
  rounds
  start_time
  context_hash
  raw_snapshot_path/hash

historical_draft_participants
  draft_id
  manager_id
  draft_slot
  roster_id

historical_picks
  draft_id
  pick_no
  round
  draft_slot
  manager_id
  canonical_player_id nullable
  source_player_id
  is_keeper
  picked_at nullable
  PRIMARY KEY(draft_id, pick_no)

market_snapshots
  id PK
  source
  source_type
  season
  scoring
  team_count nullable
  observed_at
  raw_snapshot_path/hash

market_observations
  snapshot_id
  canonical_player_id
  adp nullable
  rank nullable
  std_dev nullable
  tier nullable

manager_features
  manager_id
  model_version
  feature_name
  value
  evidence_count
  confidence

manager_player_affinity
  manager_id
  canonical_player_id
  model_version
  opportunities
  selections
  plausible_passes
  shrunk_effect
  confidence

manual_signals
  id PK
  manager_id nullable
  canonical_player_id nullable
  signal_type
  strength
  confidence
  note
  created_at
  expires_at nullable

live_draft_sessions
  id PK
  platform_draft_id
  started_at
  status
  input_hash

live_pick_events
  session_id
  pick_no
  manager_id
  canonical_player_id
  observed_at
  source

recommendations
  id PK
  session_id
  state_pick_no
  root_player_id
  model_version
  championship_probability
  playoff_probability
  next_pick_survival
  tier_survival
  sample_count
  confidence_json
  reasons_json
  created_at
```

### 23.2 Raw payload storage

Keep raw API responses in timestamped cache files or a content-addressed snapshot directory. The normalized database should reference hash/path metadata. This preserves auditability without inflating SQLite with multi-megabyte player payloads and world arrays.

---

## 24. API Design

Extend the existing FastAPI service rather than creating a second backend.

Suggested routes:

```text
GET  /api/draft-intel/leagues?username=...
POST /api/draft-intel/setup
GET  /api/draft-intel/setup/{league_id}/coverage
POST /api/draft-intel/market/refresh
POST /api/draft-intel/history/refresh
POST /api/draft-intel/worlds/build
GET  /api/draft-intel/worlds/status

POST /api/draft-intel/sessions
GET  /api/draft-intel/sessions/{session_id}
GET  /api/draft-intel/sessions/{session_id}/events      # SSE
GET  /api/draft-intel/sessions/{session_id}/state
GET  /api/draft-intel/sessions/{session_id}/recommendations
GET  /api/draft-intel/sessions/{session_id}/managers
POST /api/draft-intel/sessions/{session_id}/manual-pick
POST /api/draft-intel/signals
DELETE /api/draft-intel/signals/{signal_id}

POST /api/draft-intel/backtests
GET  /api/draft-intel/backtests/{id}
```

### 24.1 Event types

Reuse the existing SSE pattern. Add events such as:

```text
draft_sync
pick
model_update
recommendation_fast
recommendation_refined
recommendation_final
source_warning
world_bank_status
error
```

### 24.2 One active session first

The current backend already assumes limited in-memory active simulation state. V1 can support one active live draft session. Design the session object cleanly so multi-session support can be added later without changing model interfaces.

---

## 25. Performance and Compute Strategy

### 25.1 Primary hardware target

Optimize the first production version for the user's M5 Max MacBook Pro with 48 GB RAM.

The current repo benchmark reports approximately 41 ms per simulation in a cached 10-team development league in teams-only mode, with multiprocessing already implemented. Treat that as a directional baseline, not a live-draft performance guarantee.

### 25.2 Optimization order

Do not jump directly to CUDA.

1. Correct modular architecture.
2. Pre-generated shared season worlds.
3. Lightweight roster assignments instead of object copies.
4. Vectorized NumPy lineup/league evaluation.
5. Candidate racing and speculative compute.
6. Multiprocessing where it reduces wall time.
7. Profile.
8. Numba/JAX/CuPy/PyTorch only where profiling justifies it.

### 25.3 Warm-start requirement

Before the draft begins, precompute:

- market snapshots
- manager profiles
- opponent model parameters
- canonical player map
- season world bank
- baseline candidate values

The live loop should not perform expensive external ingestion unless explicitly refreshed.

### 25.4 Performance targets

Initial engineering targets on the M5 Max, subject to benchmark revision:

- live pick detection/reconciliation: < 500 ms after API response
- usable fast-pass recommendation after state change: <= 2 seconds from warm cache
- refined top-candidate recommendation: <= 10 seconds
- continuous refinement thereafter
- no UI blocking while simulation runs

If the timer is short, cached/speculative results are more important than a giant final sample.

### 25.5 RTX 3090 path

The current Python/object simulation will not automatically benefit from a 3090. GPU acceleration becomes useful only after the hot path is represented as large array/tensor operations.

Potential later architecture:

```text
ComputeBackend
  CpuNumpyBackend
  CpuNumbaBackend
  CudaBackend
```

The 3090 can be particularly useful for large `[world, player, week]` generation/evaluation if the kernel is tensorized. If the GPU is on a separate PC, run the entire compute service there and return compact recommendation results over the network; do not shuttle giant tensors back and forth to the Mac.

### 25.6 Apple GPU path

Do not make Metal/MLX acceleration a dependency. Research only if CPU profiling shows a real bottleneck after world-bank/vectorization work.

---

## 26. Confidence, Calibration, and Explainability

### 26.1 Separate confidence dimensions

Do not collapse all uncertainty into one number. Track at least:

**Opponent-model confidence**
- how much relevant manager history exists?
- are the observations current and format-matched?

**Market-data confidence**
- source freshness
- source count
- platform disagreement

**Season-model uncertainty**
- Monte Carlo standard error / paired CI
- projection uncertainty

**Decision confidence**
- how separated are the top root candidates after paired evaluation?

### 26.2 Evidence counts

Whenever a manager-specific claim appears, show evidence counts:

Good:

```text
Chris selected Player X in 3 of 3 plausible 2026 opportunities.
```

Bad:

```text
Chris has a 93.7% affinity for Player X.
```

unless that 93.7% is a properly calibrated posterior and the UI still exposes the evidence.

### 26.3 Reason codes

Persist structured reasons such as:

```text
HIGH_PERSONALIZED_THREAT
TARGET_PLATFORM_PUSH
CROSS_PLATFORM_VALUE
TIER_CLIFF
HIGH_RETURN_PROBABILITY
ROSTER_NEED
MANUAL_MANAGER_SIGNAL
LOW_HISTORY_CONFIDENCE
MARKET_SOURCE_STALE
PAIRED_CHAMPIONSHIP_EDGE
```

Human-readable explanations should be generated from these deterministic inputs. An LLM can optionally improve wording, but it must not create facts or probabilities.

---

## 27. Backtesting and Model Validation

This is a release requirement, not a future nice-to-have.

### 27.1 Rolling historical evaluation

For each historical target draft:

1. Set the clock to immediately before the draft.
2. Train only on drafts/data available before that time.
3. Use only market snapshots available before that time.
4. Replay the draft pick by pick.
5. At each test point, predict manager choices and player survival.
6. Compare to actual outcomes.

Never train on later picks from the same test draft.

### 27.2 Train/test split unit

Split by entire `draft_id`, not random pick rows, to prevent leakage from shared draft environments.

### 27.3 Metrics

**Player survival Brier score**
- calibration of `P(player survives to user's next pick)`.

**Survival calibration curve**
- among 70% predictions, approximately 70% should survive.

**Pick log loss**
- probability assigned to the player actually selected by a manager.

**Top-K pick recall**
- whether actual player was in top 3/5/10 predicted choices.

**Position-choice accuracy**
- predicted position distribution vs actual.

**Tier depletion error**
- expected vs actual number of players remaining in a tier.

**ADP baseline lift**
- compare personalized model against target-platform ADP-only.

**Decision regret**
- for historical draft states, compare recommended continuation value with alternatives where possible.

### 27.4 Baselines

Every advanced model must beat or justify itself against:

1. target-platform ADP only
2. cross-platform consensus only
3. target-platform + roster needs
4. generic room simulation without manager personalization
5. manager model without player-specific affinity
6. full model

### 27.5 Ablations

Run without:

- multi-platform ADP
- player affinity
- position timing
- live room shifts
- manual signals
- prior-season data

This identifies which features create real predictive lift.

### 27.6 Personalization gating

If a manager-specific model does not improve held-out prediction, shrink it further or use the population prior. Personalization is not automatically beneficial.

### 27.7 `ffsim` parity and calibration

Separately validate the season refactor:

- current `ffsim` vs new world-bank evaluator on identical fixed rosters
- same seed/world inputs
- expected points/wins/playoff/championship distributions within tolerance

Do not tune draft models until the season evaluator is trusted.

---
