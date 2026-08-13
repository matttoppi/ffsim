## 11. Live Draft State Engine

### 11.0 Exact league/draft attachment

The selected Sleeper source is the exact `(league_id, draft_id)` pair. Do not
assume `league.draft_id` is authoritative because Sleeper can return multiple
drafts from `GET /league/{league_id}/drafts`.

Attachment must preserve the source league `settings`, `scoring_settings`, and
`roster_positions`, plus the selected draft `type`, `settings`, `metadata`,
`draft_order`, picks, and traded picks. League/draft attachment is
format-agnostic; downstream model eligibility is a separate status. V1 model
eligibility is redraft without keeper evidence, but snake, auction, and linear
draft payloads must all remain selectable and inspectable.

Expose compatibility independently for attachment, deterministic draft replay,
future draft rollout, and season evaluation. Attachment remains supported even
when a downstream capability is unsupported. Known blockers must use explicit
reason codes, including auction future ownership, best ball, keeper evidence,
unsupported scoring keys, unsupported roster slots, playoff rules, and
league/draft team-count mismatches.

### 11.1 Exact draft geometry

The engine must construct an ordered `pick_owner[pick_no]` mapping for the entire draft. Do not infer future owners only from initial slot positions when traded picks can exist.

For every user turn, calculate:

- current overall pick
- user's current pick
- user's next pick
- number of opponent selections until next pick
- ordered list of those pick owners
- how many times each manager selects before user's next turn
- whether a manager has back-to-back/turn picks
- user's next two or three future picks

This is the foundation of the "who is close to me" logic.

### 11.2 Live state reconciliation

Keep source polling separate from the deterministic state transition. Saved
draft, pick, traded-pick, and player-pool payloads must be sufficient to replay
and test the same state without network access. A later snapshot may append
picks but must fail closed if it rewrites or removes an already observed pick.

Snake and linear drafts have predetermined future pick ownership, including
traded-pick overrides. Auction drafts expose completed winning rosters and bid
amounts, but not a predetermined future winning roster; retain that owner as
unknown rather than inventing snake-like geometry.

Use each completed league-draft pick's `roster_id` as the authoritative owning
team. Sleeper league-created standalone snake/linear mocks can return null
`roster_id` values; preserve that raw payload and derive replay ownership from
the fixed `draft_slot` plus traded-pick overrides. Preserve `picked_by` as actor
metadata only: co-managed teams can produce a picker whose own draft-order
identity does not match the roster receiving the player.

On every poll:

1. Fetch current draft picks.
2. Compare to locally known completed pick numbers.
3. Append only new picks.
4. Validate no conflicting player/pick mapping.
5. Remove selected players from availability.
6. Update the selecting manager's roster.
7. Recalculate manager needs.
8. Update live room-level behavior.
9. Invalidate only affected recommendation caches.
10. Trigger or refine speculative candidate evaluation.

If multiple picks arrive between polls, replay them in exact order.

Normal live polling issues one picks request per interval (default one
second) and re-fetches draft metadata and traded picks only every fifteenth
poll and at monitor start, reusing the cached payloads otherwise. That is
roughly 68 requests per minute at the default cadence, far below Sleeper's
documented guidance to stay under 1,000 API calls per minute (checked
2026-08-13). Completion is detected from a full pick sheet as well as the
draft status so a stale cached metadata payload cannot leave the monitor
stuck. State publication must never wait for recommendation calculation:
the monitor publishes the reconciled state immediately after every poll and
queues at most one pending calculation for the newest state. League-wide
championship equity is calculated after every pick from an unforced
continuation of the current draft state; candidate recommendations are
calculated only when the user is on the clock. Any finished result whose
draft-state fingerprint no longer matches is discarded. The worker publishes
a quick preliminary league-equity pass (12 rollouts), does the same for the
core candidate window when applicable, refines both with the full rollout
budget, then keeps widening the candidate window outward from the current
pick in four-candidate ADP-distance batches (default breadth 40) while the
state holds. Rollout IDs are deterministic prefixes and candidate results
are independent of their batch, so every published board is exactly equal
to one large evaluation of the same candidates; work is abandoned between
steps if the draft advances. A sync failure
of any kind is retried on the next poll with a forced metadata refresh so a
mid-draft traded pick or transient bad payload heals itself. Every published
recommendation carries the pick number it was computed for, and the UI must
refuse to display it against any other current pick.

### 11.3 Live room adaptation

Maintain room-level shifts such as:

```text
QB going 6 picks earlier than market
WR going 4 picks later
rookies being pushed earlier
target-platform board adherence is unusually high
```

Estimate these from completed current-draft picks while regularizing toward zero early in the draft.

Manager-specific current-draft behavior is highly relevant, but do not overreact to one surprising pick. The manager's actual roster state should update immediately; behavioral priors should update gradually.

### 11.4 Manual recovery mode

If live polling fails:

- Show source status prominently.
- Allow manual entry of the latest drafted player and manager/pick.
- Continue simulations from local state.
- Reconcile automatically when the API recovers.

A live draft tool must never become unusable because one API is temporarily unavailable.

---

## 12. Player Survival, Wait, Reach, and Threat Modeling

### 12.1 Exact-player survival

For every serious available player `p`, estimate:

```text
P(p survives until user's next pick | current state)
```

This should come from sequential draft rollouts, not independent multiplication of manager probabilities.

### 12.2 Exact pick hazard

Record the distribution of where the player disappears:

```text
P(selected at pick k)
```

This helps distinguish "almost certainly gone in the next two picks" from "usually goes near the turn."

### 12.3 Manager threat share

For all rollouts where player `p` is taken before the user's next turn, record who took him.

```text
ThreatShare(manager, p)
  = eliminations of p by manager
    / all simulated eliminations of p before next user pick
```

Expose the top two or three threats.

### 12.4 Tier survival

Exact player survival is not sufficient. If four nearly equivalent WRs remain, losing one player is not urgent.

For each value tier:

- probability at least one player remains at next pick
- probability at least N players remain
- expected number remaining
- probability tier is exhausted

Tiers can come from:

- FantasyPros ECR tiers if available
- internal league-specific value clustering
- large discontinuities in projected marginal lineup value
- manually configured tiers

Internal league-specific tiers should ultimately be preferred for decision logic.

### 12.5 Strategic wait value

For target player `p`, "wait" means there exists a different player to select now such that the expected continuation, including the chance to take `p` later, is better than selecting `p` immediately.

The system should estimate:

```text
Q_take_now(p)
Q_best_wait_path(p)
WaitDelta(p) = Q_best_wait_path(p) - Q_take_now(p)
```

where `Q` is expected championship probability under the modeled future draft and season outcomes.

### 12.6 Strategic reach

A reach is not inherently bad. Define market reach distance separately from strategic value.

```text
MarketReach = market_expected_pick(p) - current_pick
```

A **justified reach** occurs when:

- the player is earlier than market expectation,
- the player's survival probability is low enough that waiting is dangerous,
- the player's root championship branch is better than the best alternative branch by a meaningful amount.

The UI should be capable of saying:

```text
REACH IS JUSTIFIED
Market ADP suggests you are 9 picks early, but the player survives to your
next pick in only 14% of personalized rollouts. Taking him now increases
estimated title equity by 1.3 percentage points versus the best wait branch.
```

### 12.7 Safe wait

A high-value player can still be labeled `WAIT` when:

- survival is high,
- equivalent tier depth is high,
- a different current player has much greater loss-of-waiting risk,
- paired championship simulations favor the two-pick combination created by waiting.

---

## 13. Draft Completion Simulator

### 13.1 Why full draft completions are required

`ffsim` needs realistic complete rosters. Therefore every root decision branch must generate plausible future fantasy draft outcomes before season evaluation.

For candidate `A`:

```text
Current draft state
-> force user selects A
-> simulate every remaining draft pick
-> produce full roster assignment for all teams
-> evaluate that roster assignment in season worlds
```

Repeat across multiple stochastic future drafts.

### 13.2 Sequential opponent picks

At every simulated opponent pick:

1. Determine current available players.
2. Determine manager's roster at that exact moment.
3. Construct plausible candidate set.
4. Calculate manager-specific choice probabilities.
5. Sample one player.
6. Update manager roster and available pool.
7. Advance to next pick owner.

A manager selecting twice at a snake turn must have the second choice conditioned on the first.

### 13.3 User future-pick policy

The current root decision receives expensive evaluation. The user's later simulated selections need a consistent rollout policy that is good but cheaper.

The rollout policy should consider:

- league-specific internal value
- current roster and starting-slot marginal value
- VONA / replacement impact
- positional tier scarcity
- probability candidate survives another turn
- roster construction constraints
- player correlation/stacking only when empirically useful
- optional portfolio exposure preference

The rollout policy must be identical across root candidates except where the root pick changes the user's roster and available pool.

Do not let one root candidate receive a smarter future policy than another.

### 13.4 Candidate-set generation for opponent picks

For speed, an opponent does not need a probability over every active NFL player. Build a plausible set from:

- top players by target-platform exposure
- top players by cross-platform market
- manager-specific affinity targets
- positional needs
- manual targets
- K/DST candidates in relevant rounds

Ensure the historical selected player is always included during model training/evaluation even if the heuristic candidate generator would omit it.

### 13.5 Draft legality and roster constraints

Honor platform/league roster rules where they constrain drafting. Distinguish:

- hard platform constraints
- soft strategic roster needs

Do not force all managers into an artificially rational roster structure. If the platform allows six RBs, an RB-heavy manager must be able to draft six RBs.

### 13.6 Keepers

Keepers are fixed initial roster assignments and unavailable players. They should not count as voluntary historical picks when training manager preferences unless an explicit keeper-decision model is added later.

### 13.7 Last-round simplification

Full draft completion is the correctness baseline. If profiling shows late K/DST/bench rounds dominate runtime, an optional approximation can replace low-impact tail picks with a calibrated policy. This optimization must be validated against full-draft results before use.

### 13.8 Probability distribution over future draft completions

A root candidate must be evaluated across **many plausible remaining-draft completions**, not one sampled completion. The future draft is itself a probability distribution conditioned on the root pick and current state.

For a root candidate `A`:

```text
P(championship | A)
  = sum_D P(D | A, current_state) * P(championship | A, D)
```

In Monte Carlo form, sample draft continuations `D_i` from the target conditional draft model. Every future opponent pick is sampled from that manager's current choice distribution, so likely sequences appear more often and unlikely sequences appear less often. If continuations are sampled directly from the target distribution, equal weighting of those samples is correct.

**Hard invariant: never evaluate a root candidate from a single sampled remaining-draft completion, regardless of how many season worlds are run afterward.** A single lucky or unlucky draft continuation can dominate the apparent value of the current pick and produce a fundamentally biased recommendation.

If the implementation intentionally oversamples rare draft scenarios for coverage or stress testing, those samples must not be averaged equally. Use importance weights:

```text
w_i = P_target(D_i) / P_sampling(D_i)
EV(A) = sum_i w_i * V(A, D_i) / sum_i w_i
```

The rollout engine must preserve the probability of each future choice, or enough information to reconstruct the rollout likelihood, whenever the sampling policy differs from the target opponent model.

---

## 14. Coupled Randomness Across Draft Branches

Independent random rollouts create unnecessary noise when comparing root candidates. Use common random numbers wherever possible.

### 14.1 Season-world coupling

Candidate A and Candidate B should be evaluated against the same NFL/player season worlds.

### 14.2 Draft-choice coupling

Use stable random variates for future simulated picks across root branches. A useful approach is the Gumbel-max construction:

```text
selected_player = argmax(U(manager, player, state) + GumbelShock(rollout, pick, player))
```

Generate or deterministically hash the Gumbel shock from stable identifiers such as:

```text
(seed, rollout_id, pick_no, manager_id, player_id)
```

When Candidate A removes a player from the available set, the other players retain the same random shocks. This keeps counterfactual branches correlated rather than allowing unrelated random future drafts to dominate the comparison.

### 14.3 User-policy coupling

If the user's rollout policy includes random tie-breaking, use stable paired randomness as well. Prefer deterministic tie-breaking unless stochasticity is intentionally modeling uncertainty.

### 14.4 Result

The quantity of interest is the paired difference:

```text
Outcome(A, rollout_i, world_i) - Outcome(B, rollout_i, world_i)
```

rather than the difference between two unrelated Monte Carlo samples.

---

## 15. `ffsim` SeasonWorldBank Refactor

### 15.1 Current issue

Current `SimulationSeason` combines:

- generation of player availability and performance
- game/team/competition factors
- fantasy lineup selection
- fantasy matchup scoring
- standings
- playoffs

That is correct for one roster configuration, but wasteful for thousands of hypothetical draft rosters.

### 15.2 Required separation

Refactor into:

```text
Player/NFL world generation            Fantasy roster evaluation
---------------------------            -------------------------
projection uncertainty                 roster ownership
injuries/availability                  starting lineup selection
game factors                           fantasy schedule
team factors                           matchup outcomes
competition factors                    standings
NFL matchup effects                    playoffs
weekly player scoring                  champion
         |                                     ^
         v                                     |
    SeasonWorldBank ---------------------------+
```

### 15.3 World bank representation

V1 can use a league-scoring-specific score tensor:

```text
scores[world, player, week] : float32
```

Optional supporting arrays:

```text
available[world, player, week] : bool/bitset
metadata
player_index
week_index
world_seed/index
```

At 350 relevant players and 17 weeks, float32 score storage is roughly:

- 10,000 worlds: ~0.22 GiB
- 20,000 worlds: ~0.44 GiB
- 50,000 worlds: ~1.11 GiB

This is practical on a 48 GB local machine. The real memory profile will also include indexes, draft rollouts, and evaluator scratch space, so benchmark before choosing defaults.

### 15.4 Preserve correlations

The world generator must create an entire NFL/player world jointly. Do not pre-generate each player independently, because the current model intentionally includes shared game factors, team factors, and same-team-position competition factors.

A `world_id` therefore represents one coherent NFL season realization.

### 15.5 Draftable player pool

The current `SimulationSeason` primarily iterates rostered players. The draft world bank must include the complete fantasy-relevant draftable pool, including currently undrafted players.

Define a relevance filter such as:

- all players with valid projections in supported positions
- all players within a configurable market rank threshold
- every player who appears in a target/historical/manual signal
- all K/DST as required by format

Do not exclude a player only because he is not currently rostered in Sleeper during the draft.

### 15.6 World bank invalidation hash

A bank is valid only for the inputs/model that generated it. Hash at least:

- player projection snapshot versions
- injury input snapshot
- scoring settings
- scenario settings
- NFL schedule/matchup data version
- empirical sampler/model version
- random seed family
- code/model version

Store the hash in metadata and refuse silent reuse when incompatible.

### 15.7 Multi-league reuse

V1: build a scored world bank per distinct scoring configuration. This is simplest and keeps league evaluation cheap.

Future optimization: generate raw-stat worlds once and rescore for multiple leagues. This may be valuable for many leagues but increases storage and complexity. Only implement after profiling.

### 15.8 Storage

Preferred V1 options:

- `.npy` arrays with memory mapping
- simple metadata JSON

Avoid introducing a large storage framework unless required. A memory-mapped world bank allows large banks to persist between app runs and avoids regeneration during the draft.

---

## 16. League Evaluator Refactor

### 16.1 Input

The evaluator should consume lightweight roster assignments instead of deep-copied mutable `League`/`FantasyTeam`/`Player` object graphs.

```text
RosterAssignment
  roster_id -> array[player_index]
```

### 16.2 Why IDs/indices matter

Current `FantasyTeam` and `Player` instances contain mutable simulation state. Deep-copying the league for thousands of branches would be expensive and error-prone.

The draft evaluator should keep canonical player/world data immutable and vary only ownership arrays.

### 16.3 Weekly lineup optimization

For each world/week/team:

1. Gather rostered player scores/availability.
2. Fill non-flex starting positions.
3. Fill flex/superflex positions from remaining eligible players.
4. Use streamer/replacement logic only for unfilled required slots.
5. Sum score.

Correctness comes before aggressive vectorization. Once verified against current `FantasyTeam.fill_starters`, optimize with NumPy/Numba/tensors.

### 16.4 Replacement levels

Do not compute replacement levels from a partial live draft and reuse them for terminal championship evaluation.

For a completed hypothetical draft:

- identify remaining undrafted pool
- derive replacement/streamer expectations under the league's scoring/settings

If recomputing exact replacement levels for every rollout is expensive, validate a stable league-size/position approximation. The approximation must not materially change candidate ordering in backtests.

### 16.5 Fantasy schedule unavailable pre-draft

If the target league's fantasy schedule is not yet available:

- preferred: generate schedule realizations consistent with league rules and include schedule randomness in evaluation
- fallback: use schedule-neutral team-strength/playoff approximations only if explicitly labeled

Do not invent a fixed schedule and present it as exact.

### 16.6 Preserve existing playoff behavior

The new evaluator should reproduce current `ffsim` season/playoff results for a fixed roster assignment and common world sample within tolerance. This parity test is a release gate.

---
