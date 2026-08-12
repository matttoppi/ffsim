# Draft Intelligence Implementation Ledger

This file is the current operational state of the project. Keep it short, factual, and updated after every meaningful milestone.

## Current status

**Phase:** Phase 1 — Foundational draft intelligence data layer
**State:** In progress
**Branch:** `feat/draft-intelligence`  
**Implementation code changed:** Yes
**Primary next action:** Persist canonical player and external-ID records for the active Sleeper map, while retaining unresolved historical source IDs.

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
- [x] Explicit draft inclusion/exclusion classification and keeper-pick exclusion.
- [x] Active Sleeper-ID canonical match reporting and frozen representative API fixtures.
- [x] Content-addressed raw snapshots and idempotent normalized SQLite persistence.

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
- [x] Add tests against realistic fixture data.

### Later phases

Follow the dependency order and acceptance criteria in the specification. Do not skip directly to live UI, GPU work, or final championship optimization before the underlying data and probabilistic models are validated.

## Validation baseline

Record results here after the first local audit.

| Check | Status | Notes |
|---|---|---|
| Existing Python tests | Pass | 71 tests in 20.97s after local persistence slice |
| Frontend tests/build | Pass | 28 Vitest tests; TypeScript/Vite production build passed |
| Current simulation benchmark | Pass | M5 Max single-worker baselines recorded below |
| Sleeper live API smoke test | Pass | Verified 2026 league, draft, picks, traded picks, roster, and per-user history payloads |
| Historical draft ingestion | Partial/pass | Current configured league: 52,803 picks from 399 unique drafts persisted; 107 draft environments and 19,594 non-keeper picks are model-eligible |
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
- **Current configured-league classification:** The latest full crawl produced 470 discoveries, 399 unique drafts, and 52,803 unique picks. Explicit status/type/scoring filters retain 107 completed non-dynasty, non-IDP snake drafts and 19,594 non-keeper picks. Active Sleeper-ID coverage is 19,593/19,594 eligible picks (99.99%) and 626/627 unique eligible players (99.84%).
- **Undocumented draft field:** Current payloads include `settings.player_type`, but Sleeper's public API documentation does not define its values. The raw integer and roster slots are preserved without inferring rookie/veteran semantics; dynasty drafts are excluded from redraft modeling using `metadata.scoring_type`.
- **Persistence:** Explicit `draft-audit --persist` keeps the default audit read-only while writing a content-addressed raw response snapshot and transactional SQLite rows for managers, drafts, manager participation, and picks. The live store contains 399 drafts and 52,803 current picks; 25 unresolved picks retain their Sleeper source IDs with null canonical IDs. Repeated imports replace authoritative picks and upsert cumulative manager evidence.
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

Phase 0 is complete against merged `main` commit `022d1db`. `python -m ffsim draft-audit` now provides normalized records, deduplication, exclusions, keeper handling, active-ID coverage, and opt-in raw/SQLite persistence. Next, persist the canonical player/external-ID layer before historical league-context enrichment.

## Last updated

2026-08-12 — Phase 1 raw/normalized persistence validated against 399 live drafts and the full 71-test suite.
