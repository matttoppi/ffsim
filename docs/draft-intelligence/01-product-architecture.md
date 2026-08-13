# FFSIM Draft Intelligence
## Product and Technical Specification for a Live Fantasy Football Draft Decision Engine

**Document status:** Implementation specification / research handoff  
**Version:** 0.1  
**Date:** August 12, 2026  
**Primary target:** Personal, local-first Sleeper redraft tool  
**Existing engine:** `matttoppi/ffsim` (`main` inspected at commit `efd2d3c`; local commits may be newer)

---

## 1. Executive Summary

FFSIM Draft Intelligence is a live fantasy-football draft decision system whose purpose is not merely to rank players. Its purpose is to answer the decision that actually matters at every pick:

> Given the exact current draft state, my roster, the exact managers selecting before my next turn, what we know about those managers, current platform-specific market behavior, and the distribution of possible NFL seasons, which player should I draft now to maximize my probability of winning this league?

The system combines four layers that should remain conceptually separate:

1. **Market layer:** target-platform draft-room exposure, multi-platform ADP, consensus ranks, dispersion, and movement over time.
2. **Opponent layer:** league-mate draft tendencies learned from their other drafts, with strong protection against overfitting sparse data.
3. **Draft layer:** exact sequential simulation of future picks, including snake geometry, pick ownership, roster construction, positional runs, and the probability a player or tier survives to the user's next pick.
4. **Season layer:** the existing `ffsim` Monte Carlo engine, refactored so completed hypothetical drafts can be evaluated efficiently against a shared bank of season outcomes.

The final decision metric is therefore not a hand-tuned score such as `0.4 * value + 0.3 * scarcity + 0.3 * ADP`. Those quantities remain useful explanatory features, but the terminal objective should be:

```text
argmax(player p) P(championship | draft p now, current information)
```

The key technical insight is that championship probability cannot be evaluated on the partial rosters that exist in Round 2, Round 5, or Round 10. The system must first simulate plausible completions of the rest of the fantasy draft. Each completed roster set can then be evaluated by `ffsim`. The result is a Monte Carlo rollout planner in which the draft simulator models future decisions and `ffsim` supplies the terminal reward.

The other key technical insight is performance. The current `ffsim` implementation generates player performance and evaluates league outcomes together. For live candidate comparison, those concerns should be separated. A **SeasonWorldBank** should pre-generate correlated weekly fantasy outcomes for all relevant players once, then reuse exactly the same worlds across candidate roster configurations. This both reduces compute and produces cleaner candidate comparisons through common random numbers.

A successful live recommendation should be able to say something like:

```text
PICK 4.07 - 14 selections until your next turn

1. PLAYER A - TAKE NOW
   Championship probability: 18.6% (+1.9 pp vs next-best branch)
   Chance to survive to 5.06: 19%
   Chance at least one equivalent tier player survives: 28%
   Main threats: Chris 31% of elimination risk, Ryan 24%
   Expected next-pick outcomes: Player B 33%, Player C 22%, other 45%

2. PLAYER B - WAIT
   Championship probability if taken now: 17.4%
   Chance to survive to 5.06: 76%
   Taking Player A now and waiting on B produces a stronger two-pick branch.
```

The product should explicitly distinguish **player quality**, **draft urgency**, and **confidence**. A player can be excellent but safe to wait on. Another can be a modest reach by market ADP yet still be the optimal selection because the exact managers between the user's picks are unusually likely to select him.

---

## 2. Goals, Non-Goals, and Design Principles

### 2.1 Primary goals

The system must:

- Sync the current Sleeper league, league settings, draft, users, rosters/keepers, draft order, completed picks, and traded picks.
- Discover and ingest relevant historical drafts for every current league mate.
- Deduplicate drafts shared by multiple current league mates.
- Learn manager-level tendencies without pretending that three to eight drafts is a large training set.
- Learn player-specific affinities only when the player was actually available to that manager.
- Treat repeated passes on an available player as negative evidence.
- Weight same-season and same-format drafts much more heavily than old or dissimilar drafts.
- Use current target-platform ADP/default board information and multiple external market sources.
- Snapshot ADP over time so historical reaches are compared against the market that existed at the time of the historical draft.
- Model the exact sequence of managers picking before the user's next turn.
- Continuously update predictions as the live draft unfolds.
- Estimate both exact-player survival and tier survival.
- Explain who is most likely to take a target player before the user's next pick.
- Simulate the rest of the draft for each serious current-pick candidate.
- Apply a consistent future-pick policy to the user's later simulated selections.
- Evaluate completed hypothetical rosters with `ffsim`.
- Compare root candidates using shared draft randomness and shared season worlds when possible.
- Output championship probability, playoff probability, expected wins/points, survival probabilities, and uncertainty.
- Precompute aggressively before the user's clock starts.
- Preserve reproducibility: every recommendation must be reconstructable from input snapshots, model version, and seeds.

### 2.2 Non-goals for the first production version

Do not make these required for V1:

- Auction draft optimization. Auction is a separate decision problem with budgets, nominations, inflation, and maximum bids.
- Dynasty startup or rookie-draft optimization. Data can be ingested, but models must not silently mix those formats with redraft.
- Automatic support for every fantasy platform.
- Season-long waiver, trade, or lineup-management optimization. The current `ffsim` static-roster assumption can remain the terminal season model initially.
- A large language model in the probability or decision path.
- A cloud-hosted multi-user SaaS architecture.
- Deep learning merely because a GPU is available.
- Exact-looking probabilities when data is weak.

### 2.3 Design principles

1. **Championship equity is the objective; ADP is a behavioral prior.** ADP predicts what the room may do, not what the user should do.
2. **Separate value from availability.** Projections and league scoring determine value. Market and manager behavior determine availability.
3. **Sparse personal data should move a strong prior, not replace it.** A manager with two drafts should remain close to the population model.
4. **Availability is sequential.** Picks are not independent Bernoulli events because every selection changes the available pool and every manager's roster.
5. **Opportunity matters.** A manager cannot be credited with passing on a player who was already gone.
6. **Current-context evidence dominates.** A 2026 12-team PPR Sleeper redraft is more relevant to another 2026 12-team PPR Sleeper redraft than a 2024 dynasty startup.
7. **Use paired randomness for comparisons.** When comparing Candidate A and Candidate B, expose both branches to as much of the same random draft and NFL world as possible.
8. **Do not optimize what has not been calibrated.** Personalization should be disabled or shrunk when it fails out-of-sample validation.
9. **Explain every recommendation with auditable factors.** A live user must be able to tell whether the recommendation is driven by player value, survival risk, a specific manager, a tier cliff, or simulation outcome.
10. **Local-first and failure-tolerant.** The draft must remain usable if an external ADP provider fails during the draft.

---

## 3. Existing `ffsim` Baseline and Reuse Strategy

The current repository is a strong starting point rather than something to replace. The inspected `main` branch already contains:

- Sleeper league selection and league snapshot refresh.
- Sleeper roster, matchup, player, and projection ingestion.
- FantasyPros consensus offensive projection ingestion and league-specific rescoring.
- Supplemental PFF fields, K/DST projections, and matchup grades without replacing FantasyPros offensive counting stats.
- FantasyCalc values.
- Injury data ingestion.
- Empirical weekly player-stat sampling using historical nflverse data.
- Parametric fallback sampling.
- Player availability/injury simulation.
- NFL schedule and defensive matchup context.
- Shared game, team, and same-team-position competition factors.
- Weekly fantasy lineup selection.
- Regular-season fantasy matchups and median-game support.
- Standings, seeding, division winners, playoffs, and championship tracking.
- Seeded reproducibility.
- Multiprocessing workers.
- `teams-only` result mode.
- FastAPI endpoints and SSE progress events.
- A React/Vite frontend.
- Scenario overrides.
- A historical backtest path.

The current output already exposes the team metrics needed by the draft tool, including championship probability, playoff probability, division-win probability, average wins, average points, seed distributions, top-two probability, and bottom-two probability.

### 3.1 Current architectural limitation

Current `ffsim` builds fantasy teams from the already-owned Sleeper roster and simulates seasons from those rosters. During a live draft, rosters are incomplete. If the user has drafted three players, running current `ffsim` after adding one candidate would fill missing required slots with replacement-level streamers. This would not represent the team that will exist after the draft.

Therefore, the draft-intelligence layer must not use current partial-roster championship probabilities as the root decision signal.

### 3.2 Required reuse boundary

The desired boundary is:

```text
CURRENT LIVE DRAFT STATE
        |
        v
DRAFT COMPLETION ENGINE
        |
        v
FULL HYPOTHETICAL ROSTERS
        |
        v
FFSIM LEAGUE EVALUATOR
        |
        v
CHAMPIONSHIP / PLAYOFF / POINTS OUTCOMES
```

`ffsim` should become the season-outcome library underneath the new draft layer.

### 3.3 Backward compatibility requirement

The refactor must preserve the existing standalone simulator behavior and CLI/API contracts unless explicitly versioned. Existing `python -m ffsim simulate`, cached snapshot behavior, seeded reproducibility, and result JSON should continue to work. The new draft functionality should be additive and modular.

---

## 4. End-to-End Architecture

### 4.1 Logical components

```text
                              +----------------------+
                              | External market data |
                              | ADP / ECR / ranks    |
                              +----------+-----------+
                                         |
+----------------+             +---------v----------+
| Sleeper API    |------------>| Ingestion + Store  |
| live + history |             | snapshots/history  |
+----------------+             +---------+----------+
                                         |
                              +----------v-----------+
                              | Canonical Player     |
                              | + Draft Data Layer   |
                              +----+-------------+---+
                                   |             |
                          +--------v---+     +----v----------------+
                          | Market     |     | Opponent Choice     |
                          | Prior      |     | Models              |
                          +--------+---+     +----------+----------+
                                   |                    |
                                   +---------+----------+
                                             |
                                     +-------v--------+
                                     | Live Draft     |
                                     | State Engine   |
                                     +-------+--------+
                                             |
                         +-------------------v-------------------+
                         | Draft Rollout / Completion Simulator   |
                         +-------------------+-------------------+
                                             |
                                  completed roster assignments
                                             |
            +-------------------------+-------v-------------------------+
            |                         |                                 |
  +---------v----------+    +---------v----------+           +----------v---------+
  | SeasonWorldBank    |    | League Evaluator   |           | Recommendation     |
  | correlated worlds |--->| lineups/season/PO  |---------->| + explanations     |
  +--------------------+    +--------------------+           +--------------------+
```

### 4.2 Suggested repository organization

Keep the work in the existing repository unless there is a compelling deployment reason to separate it.

```text
ffsim/
  loaders/                    # existing sources; extend carefully
  models/                     # existing league/team/player models
  simulation/                 # existing season engine
  worlds/                     # NEW: correlated season world generation/storage
    generator.py
    bank.py
    metadata.py
  evaluation/                 # NEW: roster assignment -> league outcome
    league_evaluator.py
    lineup_evaluator.py
    result.py
  draft_intel/                # NEW: draft-specific domain
    ingestion/
      sleeper_history.py
      adp/
        base.py
        fantasypros.py
        csv_import.py
        ...
    models/
      draft_state.py
      manager_profile.py
      market.py
      signals.py
    opponent/
      features.py
      choice_model.py
      calibration.py
    rollout/
      draft_simulator.py
      user_policy.py
      coupling.py
      racing.py
    recommendation/
      engine.py
      explanation.py
      confidence.py
    storage/
      db.py
      migrations/
    backtest/
      draft_backtest.py
      metrics.py
  api.py                      # existing API; add versioned routes or routers
web/
  ...                         # existing React app; add Draft War Room route
```

Do not create microservices for these components in V1. They are architectural modules, not deployment boundaries.

---

## 5. Core Domain Model and Terminology

### 5.1 Primary entities

**LeagueContext**
- league ID
- season
- platform
- draft format
- scoring settings
- roster slots and bench size
- team count
- playoff settings
- divisions / median-game rules
- current roster/keeper state
- fantasy schedule if available

**DraftState**
- draft ID
- current pick number
- draft status
- exact pick owner by overall pick
- completed picks
- available-player set
- each manager's current roster
- user's current roster
- picks until user's next selection
- later user pick numbers
- timestamp / source freshness

**ManagerIdentity**
- canonical internal manager ID
- Sleeper user ID
- display name
- optional explicitly linked external-platform IDs
- manual notes/signals

**HistoricalDraft**
- draft ID
- league ID
- season
- platform
- draft type
- scoring metadata
- team count
- roster settings
- start time
- status
- participant mapping
- picks

**MarketSnapshot**
- source
- source type (target-platform board, ADP, ECR, projection rank, manual import)
- player ID
- scoring format
- team count if source-specific
- ADP/rank
- dispersion if known
- observed_at
- retrieval metadata

**ManagerProfile**
- board adherence
- behavioral temperature/volatility
- positional timing curves
- roster-construction tendencies
- player affinities and fades
- rookie/team/stack tendencies
- run-following behavior
- auto-draft likelihood
- data confidence

**SeasonWorldBank**
- model/input hash
- scoring configuration
- seed
- player index
- week index
- correlated simulated weekly scores
- optional availability/status arrays
- world count

**Recommendation**
- root candidate
- championship probability
- playoff probability
- expected wins/points
- next-pick survival
- tier survival
- threat managers
- expected continuation players
- paired delta versus alternatives
- simulation uncertainty
- opponent-data confidence
- reason codes

### 5.2 Important distinction: target-platform board vs ADP

The system must represent these separately when possible:

- **Target-platform board rank:** the order players are visibly presented to drafters by default. This directly affects exposure and auto-draft behavior.
- **Target-platform ADP:** aggregate average pick on that platform.
- **Cross-platform ADP:** broader market behavior.
- **Value rank:** the system's league-specific football value estimate.

If an exact target-platform default board source cannot be obtained legally and reliably, use target-platform ADP as a proxy and mark that assumption in the data-quality report.

---
