# Draft Intelligence Implementation Ledger

This file is the current operational state of the project. Keep it short, factual, and updated after every meaningful milestone.

## Current status

**Phase:** Phase 1 — Foundational draft intelligence data layer
**State:** In progress
**Branch:** `feat/draft-intelligence`  
**Implementation code changed:** Yes
**Primary next action:** Add explicit historical-draft inclusion/exclusion classification and canonical player match coverage to `draft-audit`; then freeze representative API fixtures before adding persistence.

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
- [x] Phase 0 repository, test, performance, API, source, and target-history audit completed.

## In progress

- [x] Read-only `draft-audit` command with manager history discovery and normalized draft/pick records.
- [x] Global draft deduplication by `draft_id` and pick deduplication by `(draft_id, pick_no)`.
- [ ] Context classification, canonical player match reporting, frozen realistic fixtures, and raw/normalized persistence.

## Next tasks

### Phase 0 — repository/data audit

- [x] Inspect local Git status, branches, unpublished commits, and diffs relative to `origin/feat/draft-intelligence` and `origin/main`.
- [x] Reconcile newer `main` work before applying this plan.
- [x] Run the existing test suite and record the baseline.
- [x] Profile the current simulation path sufficiently to identify actual cost centers before performance refactors.
- [x] Inventory current models/loaders/simulation APIs and map them to the proposed boundaries in the spec.
- [x] Verify current Sleeper league/draft endpoint behavior needed by the project.
- [x] Audit accessible ADP/projection sources, auth, published rate guidance, and licensing constraints; real-key FantasyPros payload validation remains a Phase 2 prerequisite.
- [x] Record what exists, what must change, and revised assumptions below.

### Phase 1 — foundational draft intelligence data layer

Do not begin until Phase 0 is complete and reconciled.

- [ ] Introduce canonical draft/player/manager domain types without breaking current simulation behavior.
- [x] Add historical Sleeper draft discovery and read-only ingestion.
- [x] Deduplicate shared drafts by `draft_id` and picks by `(draft_id, pick_no)`.
- [ ] Normalize historical draft context: season, format, scoring, team count, roster configuration, draft type, timestamps, keeper state.
- [ ] Add canonical/external player identity mapping.
- [ ] Add tests against realistic fixture data.

### Later phases

Follow the dependency order and acceptance criteria in the specification. Do not skip directly to live UI, GPU work, or final championship optimization before the underlying data and probabilistic models are validated.

## Validation baseline

Record results here after the first local audit.

| Check | Status | Notes |
|---|---|---|
| Existing Python tests | Pass | 70 tests in 20.26s after the first Phase 1 slice |
| Frontend tests/build | Pass | 28 Vitest tests; TypeScript/Vite production build passed |
| Current simulation benchmark | Pass | M5 Max single-worker baselines recorded below |
| Sleeper live API smoke test | Pass | Verified 2026 league, draft, picks, traded picks, roster, and per-user history payloads |
| Historical draft ingestion | Partial/pass | Live audit normalized 6,031 picks from 63 unique drafts; persistence and full classification remain |
| ADP source validation | Partial by design | Official consensus/manual paths identified; provider-key payload checks deferred to Phase 2 |

## Phase 0 audit — 2026-08-12

- **Git:** Worktree was clean. Fetched `origin/main` at `022d1db` and merged it as `a287e35`; no conflicts or unpublished local changes were found.
- **Runtime boundary:** `PlayerLoader` builds one active Sleeper/PFF player map; `LeagueLoader` snapshots league/users/rosters but no draft data; mutable `Player`/`FantasyTeam` objects currently combine weekly world generation with lineup, standings, and playoff evaluation. Draft ingestion can be additive, while the later `SeasonWorldBank` seam belongs between player-week score generation and roster evaluation.
- **Benchmark environment:** Apple M5 Max, 48 GB, arm64 macOS 26.5.1, Python 3.14.6. Command shape: `python -m ffsim simulate --league-id ID --simulations 100 --seed 2026 --workers 1 --teams-only`.
- **10-team baseline:** 0.472s load, 3.810s simulation, 26.25 simulations/s, 278 MB process peak RSS.
- **12-team baseline:** 0.470s load, 3.378s simulation, 29.60 simulations/s, 278 MB process peak RSS. Different league settings/rosters explain why team count alone does not order runtime.
- **Profile:** A 30-simulation 12-team `cProfile` run took 3.755s including load/import overhead. `SimulationSeason.simulate` used 2.439s; player sampling/scoring 1.812s cumulative; lineup filling 0.277s; playoffs 0.156s; standings were negligible. This supports world reuse before lineup micro-optimization.
- **Sleeper target:** The discovered upcoming league is a 10-team PPR snake draft, 16 rounds, 90-second timer. Before draft-order assignment, `draft_order` is `null` while `slot_to_roster_id` is populated. The league allows one keeper but currently reports none; these states must remain distinct.
- **Sleeper ownership:** Completed traded picks retain the original `draft_slot` but the pick row's `roster_id`/`picked_by` identify the actual recipient. Real pick rows contain `draft_id`, `pick_no`, `round`, `draft_slot`, `roster_id`, `picked_by`, `player_id`, `is_keeper`, and player metadata.
- **History coverage:** A bounded crawl of the 10 target managers over 2024-2026 produced 104 draft discoveries but only 63 unique `draft_id` values: 41 duplicate discoveries removed and 12 drafts shared by multiple target managers. Nineteen completed snake drafts are provisional redraft candidates pending keeper/best-ball/context filters; manager coverage is sparse (1-7 candidates each), reinforcing partial pooling.
- **Sources checked:** Sleeper's official API remains tokenless/read-only for non-commercial use with guidance below 1000 calls/minute, and documents no ADP/default-board endpoint. FantasyPros documents keyed consensus ADP/ECR, projections, and external IDs; production personal use requires its premium tier and commercial/redistribution use requires a commercial agreement. Its public schema does not establish platform-specific ADP splits or a numeric quota, and no local key is configured. Yahoo requires OAuth and authorized-user access. Fleaflicker documents draft-board/rules/roster APIs, not market ADP. No official permitted ESPN ADP API was found, so ESPN remains optional/manual.
- **Conclusion:** Existing identity matching can be reused for current active Sleeper IDs, but historical ingestion must preserve inactive/unresolved source IDs and cannot rely on the active-player table alone. Phase 1 should add draft-specific records and ingestion without changing the season engine.

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

None. A FantasyPros API key will be needed in Phase 2 to validate actual tier-specific response fields and quotas; it does not block Sleeper ingestion.

## Handoff note

Phase 0 is complete against merged `main` commit `022d1db`. The first Phase 1 slice adds `python -m ffsim draft-audit`, normalized records, and deduplication without season-simulation changes. Next, report explicit exclusions and active canonical-ID coverage, then freeze representative real payload shapes before persistence.

## Last updated

2026-08-12 — Phase 0 completed; first Phase 1 Sleeper history/deduplication slice validated live and locally.
