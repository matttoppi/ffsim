# Agent Operating Instructions

These instructions apply to all coding agents working in this repository, especially on the `feat/draft-intelligence` initiative.

## Mandatory startup sequence

Before changing code:

1. Inspect the current local repository and Git state. Do not assume the GitHub snapshot or this document is newer than local work.
2. Read `docs/draft-intelligence/README.md`.
3. Read `docs/draft-intelligence/IMPLEMENTATION_LEDGER.md`.
4. Read only the specification chapters relevant to the current phase, plus any cross-references they depend on.
5. Read `docs/draft-intelligence/DECISIONS.md` for architectural decisions already made.
6. Run the existing relevant test suite before making structural changes when practical, and record any pre-existing failures.

## Source-of-truth hierarchy

Use the following order when resolving conflicts:

1. Working code, tests, and current repository state.
2. Explicit architectural decisions in `docs/draft-intelligence/DECISIONS.md`.
3. The draft-intelligence specification under `docs/draft-intelligence/`.
4. The implementation ledger for current progress and sequencing.

If the current code and specification disagree because the code has evolved, do not blindly force the old design. Record the discrepancy, determine whether the newer code already satisfies the underlying requirement, and update the ledger/decision log as needed.

## Project goal

Build a live fantasy-football draft decision engine that combines:

- league-mate historical draft behavior,
- sparse-data opponent modeling,
- target-platform and cross-platform ADP,
- exact draft order and roster state,
- personalized player/tier survival probabilities,
- wait-versus-reach decision logic,
- probabilistic rest-of-draft rollouts,
- and `ffsim` season/championship simulation as the terminal objective.

The final decision target is the expected projected value of the completed user roster across draft uncertainty (ADR-026) — deterministic best-legal-lineup points over replacement under `ffsim`'s rules — not a static player ranking. Championship equity across football-season uncertainty remains secondary telemetry.

## Non-negotiable correctness invariants

Do not violate these to gain speed or simplify implementation:

- Never evaluate a current-pick candidate from a single sampled rest-of-draft completion.
- Future draft continuations must be sampled from the modeled conditional draft distribution, or explicitly reweighted if a different sampling distribution is used.
- Use common/coupled randomness where specified so candidate comparisons are not dominated by Monte Carlo noise.
- Preserve the separation between player-value modeling and opponent-choice/availability modeling.
- Shared Sleeper drafts must be deduplicated by draft identity; do not multiply evidence because several league mates appear in the same historical draft.
- Player-specific affinity must be opportunity-aware: unavailable players provide no positive/negative evidence; repeated passes when available are negative evidence.
- Personalization must shrink toward market priors when manager-specific evidence is sparse.
- `SeasonWorldBank` inputs and cache keys must be versioned; live draft picks must not invalidate football worlds that are independent of roster ownership.
- Cached and uncached evaluation paths must be mathematically equivalent for the same deterministic inputs.
- Do not invent unsupported API behavior, historical ADP availability, or source licensing assumptions.
- Do not silently degrade `ffsim` simulation correctness to hit a latency target.

## Work sequencing

Work phase-by-phase in dependency order. Do not implement later-stage UI or optimization around unstable foundations.

For each phase:

1. Restate the phase objective internally from the spec and ledger.
2. Inspect the relevant existing code before designing new abstractions.
3. Implement the smallest coherent vertical slice that advances the phase.
4. Add or update tests.
5. Run relevant tests, static checks, and benchmarks where applicable.
6. Update `IMPLEMENTATION_LEDGER.md` with completed work, validation, blockers, and the exact next step.
7. Add an entry to `DECISIONS.md` only for durable architectural decisions or intentional departures from the spec.
8. Make coherent commits. Avoid large mixed-purpose commits.
9. Continue to the next unblocked task without asking for confirmation unless user input is genuinely required.

## When to stop and ask for input

Do not stop for routine implementation choices that can be resolved from the spec, code, tests, or reasonable engineering judgment.

Stop only for a genuine blocker such as:

- a product choice with materially different user behavior and no preference encoded in the spec,
- credentials, paid API access, or legal/licensing decisions requiring the owner,
- destructive migration or irreversible repository action,
- a conflict between local unpublished work and the intended architecture that cannot be safely reconciled,
- or a correctness tradeoff that would weaken a non-negotiable invariant.

When blocked, update the ledger first with the blocker, options, evidence, and recommended default.

## Research discipline

Where the spec marks an item for research or verification:

- Prefer official APIs, documentation, source code, or primary datasets.
- Record source, date checked, constraints, rate limits, auth, and licensing implications.
- Separate verified behavior from assumptions.
- Build source adapters so one unavailable provider does not block the entire product unless it is explicitly required.
- Do not make unsupported scraping a hard dependency.

## Performance discipline

Optimize in this order unless profiling justifies a different path:

1. Correct architecture and state boundaries.
2. Reuse of immutable/precomputed data.
3. `SeasonWorldBank` and common random numbers.
4. Exact memoization/transposition reuse.
5. Vectorization/batching.
6. Multiprocessing.
7. Profiling-guided Numba/JAX/CUDA/GPU work.

Do not move the simulation to the RTX 3090 merely because a GPU exists. Establish that the relevant kernel is tensorizable and CPU/vectorized performance is insufficient first.

## Testing expectations

At minimum, maintain tests for:

- deterministic seeding and reproducibility,
- historical draft deduplication,
- player identity normalization,
- opportunity-adjusted manager signals,
- draft-order ownership and snake geometry,
- choice-distribution normalization,
- survival/tier-exhaustion calculations,
- coupled rollout behavior,
- nested draft/season integration,
- cache key correctness and invalidation,
- cached-versus-uncached equivalence,
- and preservation of existing `ffsim` behavior.

Use rolling/backtest validation when behavior is statistical rather than exactly deterministic. Do not claim personalization improves predictions until it beats the specified baselines out-of-sample.

## Documentation hygiene

`IMPLEMENTATION_LEDGER.md` is the operational state, not a duplicate specification. Keep it concise and current.

`DECISIONS.md` is a durable architecture log, not a daily journal.

When code changes make the specification inaccurate, update the relevant chapter rather than leaving contradictory guidance for the next agent.
