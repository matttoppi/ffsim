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
