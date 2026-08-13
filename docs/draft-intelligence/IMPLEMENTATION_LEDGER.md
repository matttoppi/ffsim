# Draft Intelligence Implementation Ledger

This file is the current operational state of the project. Keep it short, factual, and updated after every meaningful milestone.

## Current status

**Phase:** Phase 3 — Historical manager profiles
**State:** Market-independent slice complete; market-dependent profiling owner-deferred
**Branch:** `feat/draft-intelligence`  
**Implementation code changed:** Yes
**Primary next action:** Resume Phase 2 historical market collection when the owner supplies data/source access, then compute plausible-window affinity, passes, and board adherence in Phase 3.

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

## Phase 1 completed

- [x] Read-only `draft-audit` command with manager history discovery and normalized draft/pick records.
- [x] Global draft deduplication by `draft_id` and pick deduplication by `(draft_id, pick_no)`.
- [x] Explicit draft inclusion/exclusion classification and keeper-pick exclusion.
- [x] Active Sleeper-ID canonical match reporting and frozen representative API fixtures.
- [x] Content-addressed raw snapshots and idempotent normalized SQLite persistence.
- [x] Persistent canonical players and one-to-one Sleeper external-ID mappings.
- [x] Deduplicated historical league context with best-ball and missing-context exclusions.

## Phase 2 local slice completed

- [x] Append-only, content-addressed market snapshot and observation schema.
- [x] Strict manual CSV import with canonical Sleeper-ID mapping and exact raw-byte preservation.
- [x] Historical latest-at-or-before snapshot lookup with optional maximum staleness.
- [x] Idempotent re-import and historical reconstruction tests.

## Phase 3 in progress

- [x] Reconstruct target-manager roster state and the observed available player pool before each eligible non-keeper pick.
- [x] Seed keeper ownership before pick one regardless of the round containing the keeper row.
- [x] Add transparent position counts, round timing, and first-position timing summaries.
- [x] Add exact season/scoring/team-count context counts and a read-only `manager-audit` command.
- [x] Add keeper-aware, context-weighted roster counts after every observed round.
- [x] Add raw and weighted four-round zero/hero/heavy-RB and WR-heavy start evidence.
- [x] Add raw and weighted QB/TE first-round timing, including drafts without the position.
- [x] Apply transparent per-draft season, scoring-type, and league-size relevance components while retaining raw counts and component values.
- [x] Validate the baseline against 1,507 picks by 9 target managers across 79 eligible historical drafts.
- [x] Validate `manager-audit` against the current cached target context: 2026, 12-team superflex (`2qb`). This supersedes the Phase 0 target description after the configured league changed.

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

- [x] Introduce canonical draft/player/manager domain types without breaking current simulation behavior.
- [x] Add historical Sleeper draft discovery and read-only ingestion.
- [x] Deduplicate shared drafts by `draft_id` and picks by `(draft_id, pick_no)`.
- [x] Normalize historical draft context: season, format, scoring, team count, roster configuration, draft type, timestamps, keeper state.
- [x] Add canonical/external player identity mapping for Sleeper; additional sources remain Phase 2 work.
- [x] Add tests against realistic fixture data.

### Later phases

Follow the dependency order and acceptance criteria in the specification. Do not skip directly to live UI, GPU work, or final championship optimization before the underlying data and probabilistic models are validated.

### Phase 2 — deferred external work

- [ ] Validate and add the FantasyPros adapter with a real owner-provided API key.
- [ ] Add target-platform adapters only where official or authorized data is available.
- [ ] Add a shared adapter protocol when a second source implementation exists.
- [ ] Surface freshness/status in the War Room when that UI phase begins.

## Validation baseline

Record results here after the first local audit.

| Check | Status | Notes |
|---|---|---|
| Existing Python tests | Pass | 76 tests in 19.50s after the market-independent Phase 3 slice |
| Frontend tests/build | Pass | 28 Vitest tests; TypeScript/Vite production build passed |
| Current simulation benchmark | Pass | M5 Max single-worker baselines recorded below |
| Sleeper live API smoke test | Pass | Verified 2026 league, draft, picks, traded picks, roster, and per-user history payloads |
| Historical draft ingestion | Pass | Current configured league: 52,829 picks from 399 unique drafts persisted; 80 draft environments and 14,206 non-keeper picks are model-eligible after league-context filters |
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
- **Current configured-league classification:** The latest full crawl produced 470 discoveries, 399 unique drafts, and 52,829 unique picks. Status/type/scoring/league-context filters retain 80 managed redraft snake environments and 14,206 non-keeper picks. All 14,206 eligible picks and all 534 unique eligible players have known canonical IDs.
- **Undocumented draft field:** Current payloads include `settings.player_type`, but Sleeper's public API documentation does not define its values. The raw integer and roster slots are preserved without inferring rookie/veteran semantics; dynasty drafts are excluded from redraft modeling using `metadata.scoring_type`.
- **Persistence:** Explicit `draft-audit --persist` keeps the default audit read-only while writing a content-addressed raw response snapshot and transactional SQLite rows for managers, leagues, drafts, manager participation, canonical players/external IDs, and picks. The live store contains 399 drafts and 52,829 current picks; 25 unresolved picks retain their Sleeper source IDs with null canonical IDs. Repeated imports replace authoritative picks and upsert cumulative manager evidence.
- **Canonical identity:** The active cache produces 9,412 stable `sleeper:<external_id>` canonical records and one-to-one Sleeper mappings using the existing name/team normalization. Previously seen mappings remain available if a player becomes inactive; conflicting active source IDs fail closed.
- **Historical league context:** The 399 drafts reference 362 unique leagues. Sleeper still serves 318; 44 deleted/missing leagues cover 48 drafts, which fail closed. Thirty-eight leagues produce 39 best-ball draft exclusions, and 14 legacy leagues with no `best_ball` field also fail closed. Every loaded league reports `max_keepers > 0`, so that observed field is preserved but is not treated as proof that keepers were used; explicit keeper picks remain excluded individually.
- **Sources checked:** Sleeper's official API remains tokenless/read-only for non-commercial use with guidance below 1000 calls/minute, and documents no ADP/default-board endpoint. FantasyPros documents keyed consensus ADP/ECR, projections, and external IDs; production personal use requires its premium tier and commercial/redistribution use requires a commercial agreement. Its public schema does not establish platform-specific ADP splits or a numeric quota, and no local key is configured. Yahoo requires OAuth and authorized-user access. Fleaflicker documents draft-board/rules/roster APIs, not market ADP. No official permitted ESPN ADP API was found, so ESPN remains optional/manual.
- **Conclusion:** Phase 1 now provides auditable, deduplicated, context-classified Sleeper history and canonical identity persistence without changing the season engine.

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

External market adapters are intentionally deferred by the owner. A FantasyPros API key is required to validate actual tier-specific response fields and quotas before enabling that adapter. Remaining Phase 3 affinity, pass, and board-adherence work requires time-local market snapshots.

## Handoff note

Phase 1 is complete. Phase 2 has append-only manual market snapshots, strict canonical mapping, and historical reconstruction. Phase 3 has exact pick/roster/observed-availability reconstruction plus keeper-aware, context-weighted roster construction and position timing. External adapters remain owner-deferred; do not calculate plausible-window passes or board adherence without time-local market evidence.

## Last updated

2026-08-12 — Market-independent Phase 3 manager profile slice completed; full Python suite passes 76 tests.
