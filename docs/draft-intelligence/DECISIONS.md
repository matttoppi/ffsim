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
  calculating, expanding, refining, ready, failed) plus the pick a result was
  computed for and the last discarded pick, so the UI never shows vague or
  stale activity.
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
- The core window publishes first, then the remainder of the broad market
  window is screened with the same coupled rollout IDs. Only screening
  finalists receive the full rollout budget (ADR-018).
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

---

## ADR-018 — Screen broadly, refine finalists, and gate statistical ties

**Status:** Accepted
**Date:** 2026-08-13

### Decision

The live monitor evaluates the nine-player core immediately with 100 coupled
draft continuations, then screens the rest of the 40-player market window with
the same continuations. At least five candidates advance, plus every candidate
whose paired championship interval overlaps the screen leader. The adaptive
finalist set receives 1,000 continuations. Each continuation uses three season
worlds from a default 300-world bank. World selection walks one seeded
permutation, distributing uses evenly before repeating.

A raw title-equity leader is not presented as a unique recommendation when
its paired 95% championship-delta interval against another finalist includes
zero. Those candidates form one low-confidence top tier. Recommendation
payloads expose deterministic state and run signatures plus the seed, model,
world-bank, and evaluator versions.

League-wide equity retains its separate 50-continuation ceiling so increasing
candidate depth does not multiply every-pick background latency.

### Rationale

The previous live pass gave every candidate the same 50 continuations, so
most compute went to the bottom of a 40-player board while near-equal leaders
remained noisy. In a 500-continuation blank-draft replay, Bijan Robinson and
Jahmyr Gibbs differed by 0.6 percentage points with a paired 95% interval of
-1.8 to +3.0 points; ten disjoint 50-continuation blocks named three different
leaders. Their future user selections were identical, showing statistical
indistinguishability rather than excessive rest-of-draft influence.

### Consequences

- The broad screen remains visibly provisional.
- The final UI retains eliminated candidates as explicitly labeled
  100-continuation screen estimates rather than hiding them or presenting them
  as refined.
- Finalist count is evidence-driven rather than fixed: confidence-bound
  promotion can cost more when the board is genuinely indistinguishable, but
  a noisy rank cutoff cannot silently discard plausible winners.
- Decision engine version 2 identifies the balanced world mapping and
  confidence-gated recommendation contract.

---

## ADR-019 — Opponent reach mixture, positional caps, and scarcity-aware recommendations

**Status:** Accepted
**Date:** 2026-08-13

### Decision

Opponent picks are a two-component mixture. With probability `1 - reach_rate`
(default 0.15) an opponent follows the sharp fitted board model (ADR-015
temperature); with probability `reach_rate` they reach, drawn from the same
inverse-ADP utilities at a structural temperature of 0.3, which concentrates
most reach mass within roughly the next ten board spots while keeping a real
tail. The choice callback now owns the full distribution and returns final
log-probabilities, so rollouts run at temperature 1.0 and the fitted
temperature is a callback parameter. Opponents also respect positional sanity
caps derived from the league's slot structure: K/DEF are capped at their slot
counts and QB/TE at startable seats (including eligible flex) plus one; players
at capped positions are excluded unless nothing else remains on the board.

Finalist selection guarantees that the best remaining market pick (lowest ADP)
and the best remaining value-over-replacement pick refine alongside the screen
leaders. Among statistically tied co-leaders, the recommended candidate is the
one least likely to return at the user's next pick, measured from a branch that
passed on them, tagged `SCARCITY_TIEBREAK`; the board payload leads with the
recommendation. Marginal championship intervals use the same across-rollout
standard error that backs the paired deltas (the Wilson interval keyed to the
rollout count is removed), survival summaries are skipped on the user's final
pick instead of failing, and the position-timing outlook counts a player as
available at a future turn only when their ADP clears the pick plus
`reach_rate` times the number of intervening picks.

### Rationale

The fitted sharp softmax is calibrated on bot-heavy mock rooms and assigns
near-zero probability to the off-board reaches real humans make, so targets
"always" survived to the next pick, waiting looked free, and market discipline
stopped constraining the ranking. With true candidate deltas compressed below
one point by the strong future-self policy (ADR-016), the former
12-continuation screen (standard error near five points on 36 outcomes)
promoted noise into the finalist set, and exactly tied branches broke on
lexicographic candidate IDs. Each fix targets the decision the user actually faces: honest snipe
hazard, impossible opponent rosters removed, the sensible picks always in the
refined comparison, and ties resolved by which player cannot be recovered.

### Consequences

- The recommendation model version carries `reach`/`caps` tags and the reach
  rate invalidates caches like the temperature does.
- `reach_rate` is a prior, not a fit: the mock rooms that fit the temperature
  cannot show human reach behavior. The backtest accepts `reach_rate`, so both
  parameters refit together once real human drafts accumulate in the store.
- Survival numbers shown in the UI are no longer near-binary; waiting on a
  target carries visible risk.
- Among co-leaders the headline is scarcity-driven and deterministic, and a
  `toss_up` status still marks the tier as statistically tied.

## ADR-020 — Racing refinement, exact rollout-range reuse, and speculative pre-clock screening

**Status:** Accepted
**Date:** 2026-08-13

### Decision

Live refinement no longer gives every promoted finalist a flat 1,000
continuations. Refinement extends the screen's coupled observations in stages
(300, then the full budget), reusing the screen's rollout IDs 0–99 exactly
instead of recomputing them (spec §18.5). At each intermediate stage the
racing gate keeps the leader plus every candidate whose paired 95% interval
still overlaps the leader — the same tier definition the recommendation
already uses — and only survivors receive the next extension. If no
survivor's paired upper bound exceeds `REFINEMENT_REGRET_STOP` (0.5
percentage points), refinement stops early and reports the bounded toss-up
tier. Range merging (`merge_rollout_ranges`, `merge_survival_reports`) is
exact: evaluating IDs 0–99 and 100–999 separately and merging equals one
0–999 evaluation, including survival reports, intervals, ranking, and run
identity, enforced by dataclass-equality tests. `PlayerSurvival` carries an
integer `threat_total` so reports from disjoint ranges merge without float
drift. Large ranges are chunked (250 rollouts per worker task) so a handful
of finalists saturates the pool, and the pool is sized `min(12, cores - 2)`.

While an opponent deliberates directly before the user's turn, the monitor
speculatively screens the most likely next state: the opponent model's argmax
pick is applied via `DraftState.with_pick` (validated to reproduce replayed
states exactly across all 613 cached mock transitions) and the normal
two-batch screen runs against that hypothetical state. The result is reused
only when the realized state's exact signature matches the prediction;
a miss discards it. The opponent-choice callback itself is vectorized
(masked NumPy softmax mixture) with log-probabilities within 1e-12 of the
dict implementation and provably identical coupled Gumbel picks.

### Rationale

Profiling on cached picks 24/48/120 showed ~88% of latency in continuation
sampling and, decisively, that the unbounded co-leader tier feeds the flat
refinement budget: at pick 48, 36 of 40 screened candidates tied the screen
leader, making refinement 36,000 continuations (~9 minutes on the old
4-worker pool). Offline seed-stability simulation on collected 1,000-rollout
observation matrices (4 seeds × picks 24/48/120) showed the racing procedure
selects the identical final recommendation as flat refinement in 12/12 runs
at 0.48–0.91× the rollout work, with zero added regret. Real rooms leave
30–90 seconds of opponent deliberation before the user's clock; speculation
converts that idle time into completed screens with no correctness risk
because reuse is signature-gated.

### Consequences

- Statistically dominated finalists stop at 300 continuations and fall back
  to their labeled screen rows on the board; the full budget concentrates on
  candidates that can still win the comparison.
- A bounded toss-up (every survivor within 0.5pp plausible advantage) may
  finish at 300 continuations and is reported as a tier, consistent with the
  toss-up invariant.
- The regret stop rarely fires at stage 300 with current interval widths; it
  is a safety valve, not the main saving.
- Speculation hit rate depends on opponent-model top-1 accuracy and exact
  metadata reconstruction; misses cost only idle-time compute. Refit hit
  rates once real human drafts accumulate.
- Cached/uncached and merged/flat equivalence remains enforced by tests;
  numerical results of the vectorized callback differ from the dict
  implementation only below 1e-12 log-probability.

## ADR-021 — Variance-driven reallocation: 300 continuations × 14 season worlds

**Status:** Accepted
**Date:** 2026-08-13

### Decision

Candidate evaluation replaces the 1,000-continuation × 3-season-world budget
(ADR-018) with 300 coupled continuations × 14 coupled season worlds per
continuation, uniformly across the screen and refinement so exact rollout-range
reuse (ADR-020) is preserved. The racing ladder becomes (150, 225, 300).
League-wide equity keeps 3 worlds per continuation
(`LIVE_EQUITY_WORLDS_PER_ROLLOUT`): it reports marginal odds, not paired
candidate decisions, and runs single-process on every pick. Worlds per rollout
are clamped to the bank size so small `world_count` preparations stay valid.

### Rationale

Measured paired-delta variance between top candidates at cached picks
24/48/120 is 97–100% season noise (within-continuation σ²ₛ 0.06–0.28 versus
draft-side σ²_d ≤ 0.002), while a draft continuation costs ~7–22 ms and a
season world ~2.3 ms. The nested-MC optimum therefore buys season worlds, not
continuations. 300 × 14 beats the validated 1,000 × 3 paired standard error on
every measured pair (e.g. pick 48 leaders: 0.65–0.71pp versus 0.74–0.82pp) at
0.56–0.60× the per-candidate compute, and doubles screen precision, shrinking
the mid-draft co-leader tiers that fed refinement.

Seed-stability protocol (4 seeds × 3 picks, m=14 observation matrices versus
the validated 1,000 × 3 matrices): pick 24 agrees 4/4 with zero reference
regret and is cross-seed stable from n=150 (the old allocation needed n=750);
pick 48 keeps the same modal leader and the same 3/4 cross-seed stability,
with every per-seed flip inside the mutually reported 95% co-leader tiers and
reference regret ≤ 0.97pp against the old procedure's own 0.70pp outlier
seed; pick 120 is a flat ~30-candidate tier (reference spread < 1pp) where
the old procedure itself picks a different leader on 3 of 4 seeds and every
flip costs ≤ 0.36pp — below the 0.5pp regret stop. The (150, 225, 300) ladder
matched its own flat refinement 12/12 at 0.54–0.72× the extension work.
Survival at n=300 deviates from n=1,000 by at most 3.7pp (binomial noise; the
cached states themselves are adjacent snake double-turns where survival is
exactly 1, so the bound was measured from a mid-snake roster).

### Consequences

- `rollout_count` defaults to 300; joint outcomes per candidate rise from
  3,000 to 4,200 while refinement compute roughly halves.
- The screen costs ~2× more per candidate (the 14 worlds attach to all 100
  screen continuations) but returns twice the precision; the full-board and
  first-board latencies trade against a much smaller refinement tier. The
  season evaluator is now the dominant cost and is the next vectorization
  target.
- Argmax stability inside statistically tied tiers remains luck at any sane
  budget; the product's honest outputs stay the toss-up tier and the scarcity
  headline, and flips across procedures were shown to stay inside those tiers.
- The m=14 observation matrices (`/tmp/ffsim_race_obs2_pick*_m14.npz`,
  patterns in the ledger) are the new reference for future criterion-2
  sampler changes.
