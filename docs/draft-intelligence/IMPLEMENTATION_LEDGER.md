# Draft Intelligence Implementation Ledger

This file is the current operational state of the project. Keep it short, factual, and updated after every meaningful milestone.

## Current status

**Phase:** Phase 0 — Repository and data audit  
**State:** Not started  
**Branch:** `feat/draft-intelligence`  
**Implementation code changed:** No  
**Primary next action:** Audit the current local repository against the specification and any unpublished local commits before introducing new architecture.

## Project entrypoints

Read in this order:

1. `/AGENTS.md`
2. `docs/draft-intelligence/README.md`
3. this ledger
4. `docs/draft-intelligence/DECISIONS.md`
5. relevant spec chapters for the active phase

## Completed

- [x] Product and technical specification written.
- [x] Specification split into agent-friendly Markdown chapters.
- [x] Nested draft/season Monte Carlo semantics made explicit.
- [x] Caching, memoization, state hashing, transposition reuse, and invalidation rules specified.
- [x] Feature branch `feat/draft-intelligence` created from the then-current GitHub `main` baseline.
- [x] Agent operating instructions added.
- [x] Implementation ledger added.
- [x] Architecture decision log initialized.
- [x] Ready-to-paste Codex handoff prompt added.

## In progress

None. No production implementation should be considered started yet.

## Next tasks

### Phase 0 — repository/data audit

- [ ] Inspect local Git status, branches, unpublished commits, and diffs relative to `origin/feat/draft-intelligence` and `origin/main`.
- [ ] Reconcile any newer local `ffsim` work before applying this plan.
- [ ] Run the existing test suite and record baseline failures, if any.
- [ ] Profile the current simulation path sufficiently to identify actual cost centers before performance refactors.
- [ ] Inventory current models/loaders/simulation APIs and map them to the proposed boundaries in the spec.
- [ ] Verify current Sleeper league/draft endpoint behavior needed by the project.
- [ ] Verify accessible ADP/projection sources, especially source-level platform ADP, auth, rate limits, and licensing constraints.
- [ ] Produce a short audit note in this ledger: what already exists, what must change, and what spec assumptions need revision.

### Phase 1 — foundational draft intelligence data layer

Do not begin until Phase 0 is complete and reconciled.

- [ ] Introduce canonical draft/player/manager domain types without breaking current simulation behavior.
- [ ] Add historical Sleeper draft discovery and ingestion.
- [ ] Deduplicate shared drafts by `draft_id` and picks by `(draft_id, pick_no)`.
- [ ] Normalize historical draft context: season, format, scoring, team count, roster configuration, draft type, timestamps, keeper state.
- [ ] Add canonical/external player identity mapping.
- [ ] Add tests against realistic fixture data.

### Later phases

Follow the dependency order and acceptance criteria in the specification. Do not skip directly to live UI, GPU work, or final championship optimization before the underlying data and probabilistic models are validated.

## Validation baseline

Record results here after the first local audit.

| Check | Status | Notes |
|---|---|---|
| Existing Python tests | Not run in this branch handoff | Run locally before structural changes |
| Frontend tests/build | Not run in this branch handoff | Run if local web app remains present |
| Current simulation benchmark | Not re-run | README contains historical directional benchmarks only |
| Sleeper live API smoke test | Not run | Verify during Phase 0 |
| Historical draft ingestion | Not implemented | Phase 1 |
| ADP source validation | Not completed | Phase 0 research |

## Non-negotiable invariants to watch

- Never score a root candidate using only one future draft completion.
- Integrate over draft uncertainty and season uncertainty separately and jointly.
- Preserve common/coupled randomness for candidate comparisons.
- Do not count the same shared historical draft multiple times.
- Sparse manager evidence must shrink toward market priors.
- Do not confuse ADP/availability prediction with player-value estimation.
- Do not invalidate `SeasonWorldBank` for state changes unrelated to football outcomes.
- Cache hits must never change numerical results relative to uncached execution.

## Open research questions

These are research tasks, not blockers to repository audit.

- What source provides the most reliable and permissible 2026 platform-specific ADP snapshots for Sleeper, Yahoo, ESPN, Fleaflicker, and other useful markets?
- Which sources expose historical timestamped ADP versus only current values?
- Is the actual default player ordering visible in each platform available through an official/authorized interface, and how closely does it correspond to published ADP?
- What empirical dispersion model best converts each ADP source into a pick distribution by format and draft range?
- How much manager-specific history is available in the owner's actual leagues, and which features demonstrate out-of-sample predictive lift?
- At what point does vectorized CPU evaluation become insufficient enough to justify JAX/CUDA/3090 work?

## Decisions made so far

See `DECISIONS.md`. The foundational decisions currently include:

- use `ffsim` as the terminal football/season evaluator rather than building a separate toy championship model;
- refactor toward reusable `SeasonWorldBank` generation and roster evaluation;
- model rest-of-draft outcomes probabilistically rather than choosing one deterministic future;
- use exact memoization/transposition reuse before approximate state aggregation;
- keep GPU acceleration optional and profiling-driven.

## Blockers

None.

## Handoff note

The GitHub specification was originally developed against `ffsim` `main` at commit `efd2d3c`. Local commits may be newer. The first coding agent must treat local repository state as potentially authoritative and reconcile it before implementation.

## Last updated

2026-08-12 — project execution layer initialized; implementation not started.
