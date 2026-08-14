# FFSIM Draft Intelligence

Implementation and research plan for the live fantasy-football draft decision engine.

The full specification is split into chapter files to keep the repository version easy for coding agents and reviewers to navigate. The source specification was developed against `ffsim` `main` at commit `efd2d3c`; audit the local repository before implementation because local commits may be newer.

## Agent entrypoint

A coding agent should **not** begin by reading all specification chapters sequentially and immediately changing code.

Start in this order:

1. [`/AGENTS.md`](../../AGENTS.md) — operating rules, correctness invariants, sequencing, research discipline, and stop conditions.
2. [`IMPLEMENTATION_LEDGER.md`](IMPLEMENTATION_LEDGER.md) — current phase, completed work, validation state, blockers, and exact next tasks.
3. [`DECISIONS.md`](DECISIONS.md) — durable architectural decisions already accepted.
4. The relevant specification chapters below for the active phase.

For a fresh Codex session, [`CODEX_HANDOFF_PROMPT.md`](CODEX_HANDOFF_PROMPT.md) contains the ready-to-paste autonomous handoff prompt.

For live or synthetic SQLite analysis, use
[`TELEMETRY_QUERY_GUIDE.md`](TELEMETRY_QUERY_GUIDE.md).

The specification describes the destination. The implementation ledger describes where the project is now. Git and tests describe what is actually implemented.

## Specification

1. [Product definition, goals, current ffsim baseline, architecture, and domain model](01-product-architecture.md)
2. [Data acquisition, player identity, historical draft normalization, opponent and market modeling](02-data-opponent-market.md)
3. [Live draft state, survival/wait/reach logic, draft completion, coupled randomness, and SeasonWorldBank](03-live-draft-rollouts.md)
4. [Nested Monte Carlo semantics and draft-vs-season uncertainty](04-nested-monte-carlo.md)
5. [Caching, memoization, state hashing, invalidation, and transposition reuse](05-caching-memoization.md)
6. [Decision objective, league-specific value, War Room UX, storage, APIs, performance, confidence, calibration, and backtesting](06-decision-product-system.md)
7. [Testing, failure modes, security/source discipline, phased implementation, release gates, guardrails, and research tasks](07-implementation-validation.md)
8. [Algorithms, recommendation schema, end-to-end flow, future extensions, source registry, and final product definition](08-algorithms-reference.md)

## Core invariant

A root candidate must never be evaluated from a single sampled rest-of-draft completion. For each serious current-pick option, the system must integrate over many probabilistically generated future draft continuations, with the existing/refactored `ffsim` engine's lineup and replacement rules supplying the terminal projected roster value (ADR-026) and its season simulation supplying secondary championship telemetry.

## Starting point for implementation

Begin with the repository/data audit and foundational domain/data layers. Do not attempt the entire specification in one coding-agent pass. Preserve existing `ffsim` behavior and tests while introducing the architectural seams required for historical draft intelligence, live draft state, draft rollouts, and the later `SeasonWorldBank` refactor.
