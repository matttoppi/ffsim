# FFSIM Draft Intelligence Documentation

This directory contains the live draft engine specification, current project
state, durable decisions, research plans, and historical audit artifacts.

## Start here

Read only what the task needs:

1. [`/AGENTS.md`](../../AGENTS.md) — operating rules and correctness invariants.
2. [`IMPLEMENTATION_LEDGER.md`](IMPLEMENTATION_LEDGER.md) — current operational
   state, blockers, and next work.
3. [`VALUE_MODEL_BOUNDARIES.md`](VALUE_MODEL_BOUNDARIES.md) — short map of
   projected roster value, VONA, WORP, and HDVN.
4. [`DECISIONS.md`](DECISIONS.md) — durable architecture decisions.
5. The relevant specification, research, or operations document below.

Git and tests describe what is implemented. The specification describes the
destination. A research plan does not imply implementation or live eligibility.

## Documentation map

### Current project control

| Document | Owns |
|---|---|
| [`IMPLEMENTATION_LEDGER.md`](IMPLEMENTATION_LEDGER.md) | Current project state and handoff |
| [`DECISIONS.md`](DECISIONS.md) | Accepted durable architecture decisions |
| [`VALUE_MODEL_BOUNDARIES.md`](VALUE_MODEL_BOUNDARIES.md) | Ownership of projected value, VONA, WORP, and HDVN |
| [`CODEX_HANDOFF_PROMPT.md`](CODEX_HANDOFF_PROMPT.md) | Fresh-session autonomous handoff |

### Stable product specification

1. [`01-product-architecture.md`](01-product-architecture.md) — product,
   architecture, baseline, and domain model.
2. [`02-data-opponent-market.md`](02-data-opponent-market.md) — data,
   identity, historical normalization, opponent behavior, and market inputs.
3. [`03-live-draft-rollouts.md`](03-live-draft-rollouts.md) — live state,
   survival, wait/reach, continuations, coupling, and `SeasonWorldBank`.
4. [`04-nested-monte-carlo.md`](04-nested-monte-carlo.md) — draft and season
   uncertainty.
5. [`05-caching-memoization.md`](05-caching-memoization.md) — cache identity,
   invalidation, and transposition reuse.
6. [`06-decision-product-system.md`](06-decision-product-system.md) — terminal
   objective, player value, VONA, WORP, UX, APIs, and backtesting.
7. [`07-implementation-validation.md`](07-implementation-validation.md) —
   tests, failure modes, security, phases, and release gates.
8. [`08-algorithms-reference.md`](08-algorithms-reference.md) — algorithms,
   schemas, end-to-end flow, and source registry.

### Active research projects

| Project | Specification | Work ledger | Live status |
|---|---|---|---|
| Historical Draft Value Network (HDVN) | [`HISTORICAL_DRAFT_VALUE_NETWORK.md`](HISTORICAL_DRAFT_VALUE_NETWORK.md) | [`HDVN_IMPLEMENTATION_LEDGER.md`](HDVN_IMPLEMENTATION_LEDGER.md) | Pre-crawl tooling; none live |
| WORP calibration | ADR-039 and chapter 06 §20.2.1 | Main implementation ledger | Candidate fitting only |

The neural-network plan has its own specification and ticket ledger. It remains
separate from live recommendations under ADR-040.

### Operations and analysis

| Document | Use |
|---|---|
| [`TELEMETRY_QUERY_GUIDE.md`](TELEMETRY_QUERY_GUIDE.md) | Query live and synthetic SQLite telemetry |
| [`SYNTHETIC_AUDIT_LOOP_PROMPT.md`](SYNTHETIC_AUDIT_LOOP_PROMPT.md) | Run the bounded synthetic audit workflow |
| [`ffsim/historical_sleeper/README.md`](../../ffsim/historical_sleeper/README.md) | Operate the historical Sleeper collector |
| [`ffsim/historical_sleeper/DATA_DICTIONARY.md`](../../ffsim/historical_sleeper/DATA_DICTIONARY.md) | Historical database schema and fields |

### Historical and resolved artifacts

These files preserve evidence. They are not current architecture sources:

- [`archive/research/research-positional-opportunity-cost.md`](archive/research/research-positional-opportunity-cost.md)
  — resolved positional-opportunity investigation.
- [`archive/research/hdvn-market-source-audit-2026-08-27.md`](archive/research/hdvn-market-source-audit-2026-08-27.md)
  — accepted historical market-source and licensing audit for HDVN V1.
- [`archive/audits/AUDIT_20260815T043426-52dba2d4.md`](archive/audits/AUDIT_20260815T043426-52dba2d4.md)
  — historical audit report.
- [`archive/audits/AUDIT_REMEDIATION_LEDGER_20260815T043426-52dba2d4.md`](archive/audits/AUDIT_REMEDIATION_LEDGER_20260815T043426-52dba2d4.md)
  — historical remediation evidence.

## Core invariants

- Never evaluate a serious root candidate from one rest-of-draft completion.
- Integrate over many modeled draft continuations.
- Use common/coupled randomness for candidate comparisons.
- Keep player value separate from opponent choice and availability.
- Keep live projected value separate from historical outcome labels.
- VONA is next-turn opportunity evidence, not the root objective.
- WORP is approved exact-context regular-season win telemetry, not championship
  probability.
- HDVN is offline research until locked validation and a later architecture
  decision.
- Keep cached and uncached evaluation mathematically equivalent.

## Documentation maintenance

- Update one canonical owner; link from other documents instead of copying full
  definitions.
- Put durable decisions in `DECISIONS.md`, not daily notes.
- Keep current status in the relevant implementation ledger.
- Mark resolved research and audits as historical evidence.
- Do not describe a planned model as implemented, validated, or live.
