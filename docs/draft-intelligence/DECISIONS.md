# Draft Intelligence Architecture Decisions

Record only durable architectural decisions, major reversals, or intentional departures from the specification. Do not use this file as a daily progress log.

## ADR-001 — Reuse `ffsim` as terminal season evaluator

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

The draft-intelligence system will reuse and evolve the existing `ffsim` engine to estimate playoff/championship outcomes. It will not create a separate simplified championship model solely for draft recommendations.

### Rationale

`ffsim` already models league scoring, weekly outcomes, lineups, schedules, standings, playoffs, projection uncertainty, player availability, and related football variance. Reusing that engine keeps the final optimization target tied to the same simulation model used elsewhere in the project.

### Consequences

- Draft recommendation work must preserve `ffsim` correctness.
- The season evaluator needs a cleaner boundary so many hypothetical completed draft rosters can be scored efficiently.
- Existing behavior remains a regression target throughout the refactor.

---

## ADR-002 — Evaluate many future draft completions, never one

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

A current-pick candidate must be evaluated across many plausible future draft continuations. A single sampled rest-of-draft completion is never sufficient, regardless of how many season simulations are run afterward.

### Rationale

One continuation can arbitrarily make later players fall or disappear and therefore dominate the apparent value of the current pick. The desired quantity is expected championship equity integrated over future draft uncertainty.

### Consequences

- Future picks are sampled from conditional opponent-choice distributions.
- If continuations are sampled from the target distribution, sample frequency supplies probability weighting naturally.
- If rare scenarios are deliberately oversampled, importance weighting is required.
- Recommendation output should expose draft-path robustness and continuation dependency, not just a mean.

---

## ADR-003 — Separate draft uncertainty from season uncertainty

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

The engine will model two distinct uncertainty axes:

1. future fantasy-draft outcomes;
2. football-season outcomes after rosters are complete.

The final objective integrates over both.

### Rationale

This makes it possible to distinguish a pick that is fragile because of future board behavior from one that is volatile because of football outcomes.

### Consequences

- Results should support decomposition/diagnostics by draft path and season world.
- A continuation may use one or a small fixed batch of season worlds; confidence calculations treat the draft continuation as the independent cluster.
- Compute allocation can be adapted based on which uncertainty source dominates.

---

## ADR-004 — Introduce a reusable `SeasonWorldBank`

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

Refactor toward generating stochastic player/week football worlds independently of fantasy roster ownership, then reuse those worlds to evaluate many hypothetical roster assignments.

### Rationale

Player outcomes do not depend on which fantasy manager drafted them. Reusing the same football worlds reduces repeated work and enables common-random-number comparisons between candidate picks.

### Consequences

- World-bank versioning must include all football-outcome inputs that affect generated worlds.
- Input identity is derived from the exact cached player, schedule, matchup, and
  empirical-history files rather than trusted caller labels.
- Live fantasy draft picks should not invalidate an otherwise valid world bank.
- Roster evaluation should increasingly operate on immutable player/world data and compact roster assignments rather than deeply copied mutable league graphs.

---

## ADR-005 — Use coupled/common randomness for candidate comparisons

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

Candidate A and Candidate B should, where mathematically valid, be evaluated with the same underlying football worlds and coupled draft random streams.

### Rationale

The target quantity is the difference in expected value between current-pick choices. Shared randomness reduces variance in that difference and avoids one candidate appearing better merely because it received luckier random draws.

### Consequences

- Seeds/random streams become part of reproducibility guarantees.
- Candidate branches use the same rollout IDs, deterministic Gumbel keys, season-world IDs, schedule worlds, and streamer worlds.
- Paired-difference uncertainty should be preferred over comparing independent confidence intervals.

---

## ADR-006 — Keep player value and opponent-choice prediction separate

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

Do not collapse player quality, ADP, and opponent behavior into one opaque ranking model.

### Rationale

The system must answer two different questions:

- How valuable is this player to this roster under this league's rules?
- How likely is this player/tier to disappear before the user's next pick?

Separating these preserves interpretability and lets each model be independently validated.

### Consequences

- Market/platform ADP primarily informs availability and exposure.
- Projections, league scoring, replacement level, roster construction, and simulation inform value.
- The final decision layer combines both through rollouts/championship equity rather than arbitrary static weights when the full evaluator is available.

---

## ADR-007 — Manager personalization uses partial pooling

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

Manager-specific models must shrink toward league/global market priors when evidence is sparse.

### Rationale

Most league mates may have only a handful of relevant drafts. Raw frequencies would produce false certainty.

### Consequences

- Player affinity is opportunity-adjusted.
- Repeated passes can be negative evidence; unavailable players are not evidence.
- Stable tendencies such as positional timing and board adherence may receive more weight than player-specific signals with tiny samples.
- Personalization should be gated by out-of-sample calibration/lift.

---

## ADR-008 — Exact caching before approximate state compression

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

Use exact memoization, deterministic state hashing, and transposition-table reuse before introducing approximate state aggregation.

### Rationale

Different draft sequences can converge to the same meaningful state. Exact reuse is safe and can provide large gains without introducing approximation error.

### Consequences

- Cache keys must include all state and model/version inputs that affect outputs.
- Cached and uncached paths must produce equivalent results.
- Approximate state merging is a later optimization only if profiling proves exact reuse insufficient.

---

## ADR-009 — GPU acceleration is optional and profiling-driven

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

The initial implementation targets correct architecture, shared worlds, vectorization, caching, and CPU parallelism. The RTX 3090 is not a mandatory dependency.

### Rationale

The current simulator contains Python objects and control flow that will not become fast merely by introducing CUDA. GPU work is valuable only after the hot path is expressed as suitable batched/tensor operations.

### Consequences

- Establish M5 Max CPU/vectorized benchmarks first.
- Consider JAX/PyTorch/CUDA only after profiling.
- Preserve a CPU execution path even if GPU acceleration is later added.

---

## ADR-010 — Source adapters must tolerate missing platform data

**Status:** Accepted  
**Date:** 2026-08-12

### Decision

Platform ADP/default-board data is accessed through normalized source adapters. No unsupported or unstable scraping source should be a hard dependency for the product to function.

### Rationale

Official API coverage, auth, licensing, and historical data availability vary across Sleeper, Yahoo, ESPN, Fleaflicker, FantasyPros, and other providers.

### Consequences

- Missing sources are explicitly represented and remaining weights renormalized.
- Every snapshot records source, format, timestamp, and freshness.
- Source-specific legal/licensing validation is part of Phase 0 research.

---

## ADR-011 — Attach exact Sleeper league and draft identities

**Status:** Accepted
**Date:** 2026-08-12

### Decision

A Sleeper attachment is identified by an explicit `(league_id, draft_id)` pair
selected from the league's authoritative draft list. Raw league and draft
settings are preserved; attachment is separate from recommendation-model
eligibility.

### Rationale

Sleeper leagues can expose multiple drafts, and the convenience `draft_id` on a
league is not sufficient to choose among them. League size, scoring keys,
roster slots, best-ball settings, and draft type also vary and must not be
collapsed into a fixed PPR/snake schema.

### Consequences

- CLI and API/UI selection require an exact draft after league selection.
- Standalone mocks with `league_id: null` attach by exact draft ID in an isolated
  cache. They support draft replay but do not impersonate missing league data.
- League-created standalone snake/linear mocks may omit pick `roster_id`; their
  raw payload remains unchanged while replay ownership is derived from the fixed
  `draft_slot` and traded-pick overrides. League-backed and auction picks remain
  strict because their ownership cannot be inferred by this rule.
- Snake, auction, linear, and future unknown draft types remain attachable as
  raw source structures.
- Deterministic state replay supports Sleeper's snake, linear, and auction
  redraft structures. Auction winners and budgets are reconstructed, but future
  winning rosters remain unknown because they are not predetermined.
- V1 recommendation eligibility is redraft without keeper evidence; dynasty or
  keeper evidence is reported explicitly rather than silently transformed.
- Compatibility is reported separately for attachment, deterministic replay,
  future draft rollout, and season evaluation. A downstream rejection includes
  stable reason codes but never prevents attachment and source inspection.

---

## ADR-012 — Refresh FantasyPros ADP on demand with a 12-hour freshness gate

**Status:** Accepted
**Date:** 2026-08-13

### Decision

Explicit market refreshes and league-attachment refreshes check the last successful FantasyPros retrieval per supported format context. Only missing or at-least-12-hour-old contexts are fetched. There is no background refresh loop.

Each official bulk ADP response is persisted once and normalized into its consensus and returned platform-specific boards.

### Rationale

The Premium personal plan allows 500 requests/day at one request/second. Four context requests per stale refresh cover the verified 1QB STD/HALF/PPR and half-PPR superflex boards, so a twice-daily cadence costs at most eight successful API requests rather than one request per platform.

### Consequences

- Fresh explicit refreshes perform no Sleeper or FantasyPros network calls.
- Retrieval time, provider observation time, raw content hash, context, and source remain append-only and auditable.
- Source identity uses FantasyPros `sportsdata_id` to Sleeper `sportradar_id`, with DST mapped by team; ambiguous IDs fail closed per player and are reported.
- Only boards actually returned by the official API are stored; missing platforms are not synthesized.

---

## ADR-013 — Use FantasyPros offensive means with PFF only as a supplement

**Status:** Accepted
**Date:** 2026-08-13

### Decision

FantasyPros consensus preseason projections are the primary QB/RB/WR/TE
counting-stat means. PFF may supply fields the FantasyPros response does not
publish and remains the K/DST source, but a PFF offensive value never overrides
a counting stat returned by FantasyPros. The original PFF row is retained
separately for later validated variance, injury, floor/ceiling, or grade-based
modifiers.

### Rationale

This preserves the boundary between a consensus base forecast and optional PFF
signals while allowing the existing league-specific raw-stat scoring and
season-world generation to remain unchanged.

### Consequences

- Refresh uses the official preseason projection and player-metadata endpoints.
- League and draft setup refresh projections under the same request-driven
  12-hour freshness interval as FantasyPros ADP; explicit refresh remains forced.
- FantasyPros player IDs map through SportsData/Sportradar IDs to Sleeper IDs.
- Missing offensive FantasyPros projections fail closed for title optimization;
  there is no silent PFF projection fallback.
- Provider disagreement and advanced PFF metrics do not change variance until a
  specific adjustment is defined and backtested.
- The derived player cache remains part of the `SeasonWorldBank` input hash.

---

## ADR-014 — Live synchronization never waits for recommendation calculation

**Status:** Accepted
**Date:** 2026-08-13

### Decision

The live monitor separates Sleeper synchronization from recommendation
calculation. The sync loop polls picks every interval and publishes the
reconciled draft state immediately. A single worker thread consumes a
one-slot pending state: when a new pick arrives, the previous recommendation
is cleared, any in-flight calculation is allowed to finish but its result is
discarded unless its exact draft-state fingerprint still matches, and only
the newest state can be calculated next. There is no FIFO queue of
calculations. League equity runs for every state; candidate recommendations
run only when the user's roster is on the clock.

### Rationale

A recommendation pass takes on the order of ten seconds while a fast mock
produces picks every few seconds. Calculating inline froze the published
state several picks behind Sleeper, which was observed live (UI at pick 18
while Sleeper was at pick 24).

### Consequences

- The monitor exposes explicit recommendation states (idle, pending,
  calculating, ready, failed) plus the pick a result was computed for and the
  last discarded pick, so the UI never shows vague or stale activity.
- Every recommendation carries its source pick number; the frontend refuses
  to render it against a different current pick.
- League equity carries its source state, publishes preliminary and refined
  results after every pick, and keeps the previous labeled result visible
  while the new state is calculating.
- Hard thread cancellation is not attempted; obsolete work is abandoned
  between passes and finished stale results are discarded.
- The worker publishes an exact preliminary pass (12 rollouts) before the
  full budget; rollout IDs are deterministic prefixes, so refinement uses the
  same coupled randomness and supersedes the preliminary result exactly.
- After the core window is ready, the candidate window keeps expanding
  outward from the current pick in small ADP-distance batches while the user
  remains on the clock. Candidate evaluations are independent of their batch
  under coupled randomness, so merged boards are exactly equal to one large
  evaluation; parallel worker processes remain profiling-gated.
- Normal polling uses one picks request per interval; draft metadata and
  traded picks refresh every fifteenth poll, and completion is detected from
  a full pick sheet even when the cached metadata status is stale.

---

## ADR-015 — Fitted opponent temperature and parallel candidate evaluation

**Status:** Accepted
**Date:** 2026-08-13

### Decision

The live opponent-choice softmax temperature is a fitted model parameter, not
a fixed constant. The current default (0.11) is the maximum-likelihood grid
fit on 286 observed non-user picks from this league's Sleeper mocks and must
be refit as real human draft evidence accumulates; it is exposed as a monitor
request parameter and included in the recommendation model version.

Live candidate evaluation fans out across a small process pool (default four
workers), one candidate per task, and merges the per-candidate evaluations.
Because candidates are independent under coupled deterministic randomness,
the merged result is exactly equal to one sequential batch evaluation, which
remains the fallback when no executor is available. Each draft continuation
is paired with three coupled season worlds.

### Rationale

At temperature 1.0 opponents picked the consensus best player only ~16% of
the time, which inflated the greedy user's absolute title equity (observed
58% at pick 1) and made positional scarcity nearly free, letting a kicker
grade even with elite skill players at pick 24. Fitted sharpness (mean NLL
2.09 at T=0.11 versus 4.15 at T=1.0) restores real opportunity cost.
Continuation sampling is single-core Python and profiling showed remaining
exact single-core wins were small, so per-candidate process parallelism is
the profiling-justified step (AGENTS.md performance ordering).

### Consequences

- The temperature provenance is CPU-heavy league-mock rooms; treat absolute
  equity as provisional until refit on human drafts, and never present it as
  calibrated confidence.
- Recommendation cache keys and model versions include the temperature.
- Worker processes hold the market snapshot and season evaluator once via
  the pool initializer; per-worker evaluator caches are process-local.
- Parallel and sequential paths must remain exactly equivalent (tested).

---

## ADR-016 — The user's simulated future picks follow the model, not the market

**Status:** Accepted
**Date:** 2026-08-13

### Decision

In live candidate rollouts, the user's simulated future picks are chosen by
projection value over positional replacement with open-starting-slot
awareness, built from the SeasonWorldBank projections and the league's slot
structure. Core QB/RB/WR/TE/flex openings are filled before bench depth; once
the core lineup is complete, bench players compete directly with K/DEF on
value, and K/DEF are never duplicated. Opponents keep the calibrated ADP
softmax. Root candidates remain forced. The recommendation model version
carries a `vor2` tag because this policy changes results.

### Rationale

The previous greedy-by-market-ADP future self inherited market mispricing:
observed live at mock pick 24, the Nabers branch drafted Love (projected 256)
at pick 25 while Rice (projected 273) was still available — a follow-up the
real user would never make — double-charging Nabers (11.3% before, 18.0%
after). Raw projected points alone would over-draft quarterbacks, so the
policy uses value over replacement, where replacement level comes from a
deterministic league-wide starter fill including flex seats, and players who
no longer fill an open starting slot rank below all who do.

### Consequences

- Candidate deltas compress: with a strong future policy, good follow-ups
  partially repair any current pick, so near-tier candidates genuinely grade
  close — the honest picture, not a defect.
- Back-to-back snake-turn candidates no longer tie exactly, because the
  follow-up pick maximizes model value instead of scooping the runner-up.
- The policy is deterministic and shared across candidate branches,
  preserving paired comparisons and coupled randomness.
- K/DEF are not mechanically drafted before useful bench depth merely because
  their starting slots remain open.
- Absolute equity remains provisional until the opponent temperature is
  refit on human drafts (ADR-015).

---

## ADR-017 — League equity uses unforced current-state continuations

**Status:** Accepted
**Date:** 2026-08-13

### Decision

League-wide live championship odds are evaluated without forcing a root
candidate. Each rollout continues from the exact current pick: the configured
user policy selects future user picks, the opponent model samples every other
roster's picks, and one completed assignment is scored for every roster in the
same coupled season worlds. The monitor runs a preliminary and refined pass
after every synchronized pick, not only when the user is on the clock.

### Rationale

Candidate evaluation answers a counterfactual question conditioned on one
forced user pick, so it cannot provide neutral league standings and cannot run
on opponent turns. The league evaluator already returns outcomes for every
roster; retaining those results from one unforced continuation batch supplies
the requested rankings without multiplying work by roster count.

### Consequences

- All roster odds share the same sampled draft continuations and season worlds.
- Candidate recommendations remain on-clock-only and keep their forced-root
  semantics.
- The sidebar may show the prior labeled result while the newest state is
  pending, then replaces it with preliminary and refined current-state odds.
- Absolute percentages remain explicitly uncalibrated under ADR-015.
