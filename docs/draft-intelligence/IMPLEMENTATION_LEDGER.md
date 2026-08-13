# Draft Intelligence Implementation Ledger

This file is the current operational state of the project. Keep it short, factual, and updated after every meaningful milestone.

## Current status

**Phase:** Phase 8 — offline coupled draft rollouts and nested evaluation
**State:** Offline nested baseline, official ADP ingestion, FantasyPros-first offensive projections, and an uncalibrated Sleeper-ADP choice baseline are complete; the owner's real 2026 league draft is attached pre-draft and its league-created mock is live
**Branch:** `feat/draft-intelligence`  
**Implementation code changed:** Yes
**Primary next action:** Restart the local server, re-prepare real draft `1389391547115511809` with the current league-created mock, resume monitoring from the live mock's current pick, and complete it so its picks can become leakage-free baseline evidence. Do not use generic desktop mock `1393628519644286976`, whose settings do not match the real 12-team PPR league. Do not claim `WAIT`, `REACH`, or personalization from one mock or before out-of-sample calibration. The owner's next requested feature is a league-wide live equity sidebar (per-roster championship probability updated as the draft progresses); it requires a continuation mode without a forced user root pick, so opponent-turn rollouts have a concrete documented reason before that work starts.

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
- [x] Validate the official FantasyPros Premium `type=ADP` payload with the owner-provided key.
- [x] Store consensus and returned ESPN/CBS/Yahoo/RTSports/Fantrax/Sleeper/FFPC boards from one request per format context.
- [x] Refresh only missing or at-least-12-hour-old 1QB STD/HALF/PPR and half-PPR superflex contexts; no background loop.
- [x] Map FantasyPros players through `sportsdata_id` to Sleeper `sportradar_id`, map DST by team, and report ambiguous/unmatched identities without guessing.
- [x] Resolve raw Sleeper reception/QB settings to exact, explicit proxy, or unsupported market contexts without mislabeling FantasyPros coverage.
- [x] Select only snapshots both observed and retrieved before the evaluation time.
- [x] Provide a versioned inverse-ADP Sleeper choice callback directly compatible with coupled draft rollouts.
- [x] Add a read-only `market-backtest` command with log loss, reciprocal rank, top-K accuracy, coverage, context, snapshot, and skip reporting.

## Phase 3 in progress

- [x] Reconstruct target-manager roster state and the observed available player pool before each eligible non-keeper pick.
- [x] Seed keeper ownership before pick one regardless of the round containing the keeper row.
- [x] Add transparent position counts, round timing, and first-position timing summaries.
- [x] Add exact season/scoring/team-count context counts and a read-only `manager-audit` command.
- [x] Add keeper-aware, context-weighted roster counts after every observed round.
- [x] Add raw and weighted four-round zero/hero/heavy-RB and WR-heavy start evidence.
- [x] Add raw and weighted QB/TE first-round timing, including drafts without the position.
- [x] Apply transparent per-draft season, scoring-type, and league-size relevance components while retaining raw counts and component values.
- [x] Validate the descriptive baseline against 2,197 picks by 20 stored managers; every member of the attached real league has eligible history.
- [x] Validate `manager-audit` against the current target context: 2026, 12-team PPR.

## Phase 4 foundation completed

- [x] Treat the selected Sleeper source as an exact `(league_id, draft_id)` pair.
- [x] Discover drafts from the authoritative league draft-list endpoint rather than assuming `league.draft_id` is unique.
- [x] Preserve raw league settings, scoring settings, roster positions, draft type/settings/metadata, picks, and traded picks.
- [x] Support explicit draft selection in CLI setup, backend API, and the web picker without filtering snake, auction, or linear formats.
- [x] Separate attachment from V1 redraft/no-keeper eligibility; dynasty/keeper evidence remains visible and unmodified.
- [x] Make manager-profile target context use the exact attached draft rather than inferring format from reception scoring and roster slots.
- [x] Validate a custom-scoring, custom-roster, best-ball auction fixture and a live Sleeper league with multiple linear/snake drafts.
- [x] Add immutable, network-free Sleeper draft-state replay from saved payloads.
- [x] Reconstruct exact snake/linear pick ownership, including third-round reversal and traded-pick overrides, plus roster state, availability, current/next turns, opponent counts, and turn picks.
- [x] Reconstruct auction winners, rosters, and remaining budgets while leaving future winning ownership explicitly unknown.
- [x] Fail closed on keeper rows, gaps, duplicates, ownership conflicts, missing players, budget violations, and rewrites/removals of observed picks.
- [x] Keep `roster_id` authoritative for pick ownership and preserve `picked_by` only as actor metadata because co-managed teams can legitimately mismatch draft-order identity.
- [x] Save league/draft attachments atomically and test discovery, selection, readiness, invalid drafts, and failed writes at the backend endpoint boundary.
- [x] Attach standalone mocks by exact draft ID in an isolated cache and reject rewrites or removals of previously observed picks.
- [x] Preserve null `roster_id` values returned by league-created mocks while deriving fixed snake/linear replay ownership from draft slots and traded-pick overrides.
- [x] Add a dedicated Draft intelligence tab with one-click preparation that resolves the real league from its draft ID, verifies the Sleeper user and optional league-created mock, refreshes players/history/stale ADP, and warms coupled season worlds.
- [x] Add one-active-session live monitoring that polls append-only draft state, retries transient source failures, and recalculates the uncalibrated baseline only when the user is on the clock.
- [x] Decouple synchronization from calculation (ADR-014): the sync loop publishes reconciled state every poll while a single worker consumes a one-slot latest-state-wins queue; finished results are discarded unless their draft-state fingerprint still matches, recommendations carry their source pick number, and the UI refuses to render one against a different current pick.
- [x] Poll one picks request per interval (default 1s) with draft metadata/traded picks every fifteenth poll (~68 requests/minute, under Sleeper's documented 1,000/minute guidance) and detect completion from a full pick sheet despite stale cached metadata.
- [x] Publish a full live pick feed (pick, round, player, position, NFL team, slot, roster) with explicit UI states for synchronizing, watching, on the clock, pending, calculating for pick N, ready for pick N, failed, discarded, stopped, and complete, plus last-sync time and pick count.
- [x] Publish an exact preliminary 12-rollout recommendation (~1.6 s) before the full pass (~6.7 s after cutting the choice callback from the ~11k-player pool to the 297-player ADP board), abandon refinement between passes when the draft advances, and retry any sync failure with a forced metadata refresh so mid-draft trades and transient payloads self-heal.
- [x] Select the best available market player per position before filling by overall ADP, display each candidate's title odds with a signed delta versus the top option, and filter the board by position on the client.
- [x] Expand the candidate window outward from the current pick in exact four-candidate ADP-distance batches while the user stays on the clock (default: nine core candidates then breadth 40). Merged batch evaluations are provably equal to one combined evaluation under coupled randomness. Measured at live-mock pick 73: preliminary board 2.65 s, refined core 10.6 s, ~4.8 s per expansion batch, full 40-candidate board ≈51 s.
- [x] Attach real draft `1389391547115511809`: 12-team PPR snake, owner slot 1/roster 8, no keepers, and every attachment/replay/rollout/season capability supported.
- [x] Score Sleeper's `fgm_50_59` setting from the modeled 50-plus bucket after subtracting modeled 60-plus makes.
- [x] Add reproducible CI geometry cases for observed 10/12/14-team snake, third-round reversal, linear, and auction formats.
- [x] Mark manager-profile heuristics descriptive-only and decision-ineligible until out-of-sample market-baseline calibration exists.
- [x] Run frontend tests/build and ResourceWarning-clean Python tests in CI.
- [x] Report attachment, draft replay, future rollout, and season-evaluation compatibility independently with precise downstream reason codes.
- [x] Recognize 1QB, superflex, receiver flex, RB/WR flex, custom supported scoring, snake, and linear redrafts without collapsing raw settings.
- [x] Keep auction, best-ball, IDP/taxi, unsupported scoring/playoff rules, keeper evidence, and inconsistent team counts attachable while failing unsupported downstream capabilities explicitly.
- [x] Sample complete snake/linear redraft continuations from injected conditional choice utilities without implying an external market source.
- [x] Enforce two or more unique continuations per root candidate and couple opponent choices with stable Gumbel shocks keyed by seed, rollout, pick, roster, and player.
- [x] Update every simulated turn sequentially and derive exact-player survival, pick hazards, manager threat shares, and tier remaining/exhaustion distributions from the sampled paths.

## Phase 6 foundation started

- [x] Make FantasyPros consensus the primary QB/RB/WR/TE counting-stat source, preserve PFF separately, and allow PFF to fill only unpublished fields plus K/DST.
- [x] Map FantasyPros projections through official SportsData/Sportradar IDs and fail closed instead of falling back to PFF for missing offensive players.
- [x] Refresh projection and ADP caches from league/live-draft setup under the same request-driven 12-hour freshness gate; keep explicit refresh forced.
- [x] Separate correlated player/NFL world preparation from fantasy matchup, standings, and playoff evaluation without changing the existing `SimulationSeason` path.
- [x] Add a versioned, deterministic, read-only `SeasonWorldBank` score/availability tensor for a caller-supplied draftable player pool.
- [x] Preserve shared game, team, competition, projection, availability, scoring, scenario, and seed behavior in the extracted generator.
- [x] Derive the bank input hash from the exact cached player, schedule, defensive-matchup, identity, snap, weekly-stat, and play-by-play files.
- [x] Select the full supported projected pool independently of current fantasy ownership (528 players in the current cache).
- [x] Preserve deterministic seed-family extension: a larger bank retains the exact prefix of a smaller compatible bank.
- [x] Match the existing fixed-seed fantasy matchup player scores exactly on a common world fixture.

## Phase 7 functional slice completed

- [x] Evaluate compact `roster_id -> player_index` assignments without copying mutable player/team graphs.
- [x] Reproduce lineup eligibility, replacement streamers, head-to-head/median wins, divisions, 4/6/8-team record-seeded playoffs, and championship outcomes.
- [x] Accept exact fantasy schedules or generate deterministic schedule realizations when the pre-draft schedule is unavailable.
- [x] Preserve common season and streamer randomness across roster assignments.
- [x] Return immutable per-world outcome vectors and exact cached/uncached equivalents.
- [x] Match the existing full-season path on a frozen common-world fixture.

## Phase 8 offline baseline completed

- [x] Pair every rollout ID with one deterministic season-world ID shared by all root candidates.
- [x] Evaluate only selected worlds for each completed draft rather than forming a naive draft-by-season cross product.
- [x] Return per-candidate championship/playoff outcomes, expected wins/points, Wilson title intervals, and paired championship deltas.
- [x] Keep selected-world and all-world roster evaluation mathematically equivalent with exact cache keys.
- [x] Preserve multiple-draft-continuation enforcement at both rollout and nested-evaluation boundaries.
- [x] Support one or a small distinct batch of season worlds per draft continuation and cluster paired uncertainty by continuation.
- [x] Return versioned, JSON-serializable recommendation summaries with title/playoff equity, expected wins/points, continuation percentiles, paired runner-up deltas, survival detail, and exact sample counts.
- [x] Omit market-dependent `WAIT`/`REACH` labels when no validated market snapshot exists.
- [x] Complete a realistic offline 12-team superflex/16-round throughput check using an explicitly benchmark-only projection board.

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

### Phase 2 — external market work

- [x] Validate and add the FantasyPros adapter with a real owner-provided API key.
- [ ] Add target-platform adapters only where official or authorized data is available.
- [ ] Add a shared adapter protocol when a second source implementation exists.
- [ ] Surface freshness/status in the War Room when that UI phase begins.

## Validation baseline

Record results here after the first local audit.

| Check | Status | Notes |
|---|---|---|
| Existing Python tests | Pass | 115 tests with `ResourceWarning` promoted to an error |
| Frontend tests/build | Pass | 29 Vitest tests; TypeScript/Vite production build passed and both now run in CI |
| Current simulation benchmark | Pass | M5 Max single-worker baselines recorded below |
| Sleeper live API smoke test | Pass | Verified 2026 league, draft, picks, traded picks, roster, and per-user history payloads |
| Offline draft geometry | Pass | CI covers representative observed 10/12/14-team snake, third-round reversal, linear, auction, trade, and co-manager actor cases. Supplemental local saved-payload validation covers 243 snake, 144 linear, and 11 auction drafts; one legacy IDP source inconsistency fails closed. |
| Historical draft ingestion | Pass | 53,587 picks from 407 unique drafts persisted; 81 draft environments and 14,366 non-keeper picks are model-eligible. The current 12 managers produced 142 discoveries deduplicated to 34 drafts; all 12 have eligible history. |
| ADP source validation | Pass | Premium payload validated live; four format contexts and all returned platform boards persisted, with an immediate repeat producing zero requests |
| Sleeper ADP baseline | Live mock in progress | One-click preparation verified mock `1393634461312106496` as an exact league-created match with zero blockers and zero FantasyPros calls while fresh. Live synchronization reproduced 23 completed picks/current pick 24 after handling Sleeper's null standalone-mock `roster_id` values. Existing completed eligible drafts predate the first market retrieval and are correctly skipped. |
| Live monitor latency | Measured 2026-08-13 | Against live league mock `1393656492011315200` at pick 73 (72 null-`roster_id` picks reconciled): picks-only sync 155 ms, full metadata sync 346 ms, one-time 50-world bank build 6.78 s at prepare. Recommendation calculation profiled at 13.32 s for 50 rollouts × 5 candidates, 97% in continuation sampling; iterating the 297-player ADP board instead of the full ~11k-player availability pool (exact, identical output) cut the full pass to 6.66 s, and the published preliminary 12-rollout pass lands in 1.61 s. Synchronization stays at poll cadence because calculation runs on a separate latest-state-wins worker (ADR-014). |

## Phase 0 audit — 2026-08-12

- **Git:** Worktree was clean. Fetched `origin/main` at `022d1db` and merged it as `a287e35`; no conflicts or unpublished local changes were found.
- **Runtime boundary:** `PlayerLoader` builds one active Sleeper/PFF player map; `LeagueLoader` snapshots league/users/rosters but no draft data; mutable `Player`/`FantasyTeam` objects currently combine weekly world generation with lineup, standings, and playoff evaluation. Draft ingestion can be additive, while the later `SeasonWorldBank` seam belongs between player-week score generation and roster evaluation.
- **Benchmark environment:** Apple M5 Max, 48 GB, arm64 macOS 26.5.1, Python 3.14.6. Command shape: `python -m ffsim simulate --league-id ID --simulations 100 --seed 2026 --workers 1 --teams-only`.
- **10-team baseline:** 0.472s load, 3.810s simulation, 26.25 simulations/s, 278 MB process peak RSS.
- **12-team baseline:** 0.470s load, 3.378s simulation, 29.60 simulations/s, 278 MB process peak RSS. Different league settings/rosters explain why team count alone does not order runtime.
- **Profile:** A 30-simulation 12-team `cProfile` run took 3.755s including load/import overhead. `SimulationSeason.simulate` used 2.439s; player sampling/scoring 1.812s cumulative; lineup filling 0.277s; playoffs 0.156s; standings were negligible. This supports world reuse before lineup micro-optimization.
- **World-bank/evaluator smoke:** The current 12-team local snapshot produced a 528-player, 50-world bank in 5.672s. One full 50-world roster evaluation took 0.123s and an exact cache hit took 0.000030s. This validates the boundary, not the final live throughput target; Phase 8 should evaluate selected world/continuation pairs rather than every world for every unique completed draft.
- **Nested offline smoke:** A synthetic 16-round redraft using the cached 12-team superflex rules, 528 players, 20 season worlds, 3 root candidates, 50 draft continuations per candidate, and 2 season worlds per continuation built the bank in 2.287s and evaluated 300 joint outcomes in 1.992s (150.6 outcomes/s). The board was projection-ordered and benchmark-only; this is a throughput result, not opponent-model validation. Profiling justified one exact SHA-prefix reuse in Gumbel sampling and did not justify a custom RNG, multiprocessing, Numba, or GPU work.
- **Sleeper target:** The attached real draft is a 12-team PPR snake, 15 rounds, scheduled for 2026-08-30 at 7:00 PM EDT. The owner has draft slot 1 and roster ID 8. The league permits one keeper but all roster keeper arrays and draft picks are empty; permission and observed keeper use remain distinct.
- **Sleeper ownership:** Completed traded picks retain the original `draft_slot` but the pick row's `roster_id`/`picked_by` identify the actual recipient. Real pick rows contain `draft_id`, `pick_no`, `round`, `draft_slot`, `roster_id`, `picked_by`, `player_id`, `is_keeper`, and player metadata.
- **History coverage:** A bounded crawl of the 10 target managers over 2024-2026 produced 104 draft discoveries but only 63 unique `draft_id` values: 41 duplicate discoveries removed and 12 drafts shared by multiple target managers. Nineteen completed snake drafts are provisional redraft candidates pending keeper/best-ball/context filters; manager coverage is sparse (1-7 candidates each), reinforcing partial pooling.
- **Current configured-league classification:** The latest full crawl produced 470 discoveries, 399 unique drafts, and 52,829 unique picks. Status/type/scoring/league-context filters retain 80 managed redraft snake environments and 14,206 non-keeper picks. All 14,206 eligible picks and all 534 unique eligible players have known canonical IDs.
- **Undocumented draft field:** Current payloads include `settings.player_type`, but Sleeper's public API documentation does not define its values. The raw integer and roster slots are preserved without inferring rookie/veteran semantics; dynasty drafts are excluded from redraft modeling using `metadata.scoring_type`.
- **Persistence:** Explicit `draft-audit --persist` keeps the default audit read-only while writing a content-addressed raw response snapshot and transactional SQLite rows for managers, leagues, drafts, manager participation, canonical players/external IDs, and picks. The live store contains 399 drafts and 52,829 current picks; 25 unresolved picks retain their Sleeper source IDs with null canonical IDs. Repeated imports replace authoritative picks and upsert cumulative manager evidence.
- **Canonical identity:** The active cache produces 9,412 stable `sleeper:<external_id>` canonical records and one-to-one Sleeper mappings using the existing name/team normalization. Previously seen mappings remain available if a player becomes inactive; conflicting active source IDs fail closed.
- **Historical league context:** The 399 drafts reference 362 unique leagues. Sleeper still serves 318; 44 deleted/missing leagues cover 48 drafts, which fail closed. Thirty-eight leagues produce 39 best-ball draft exclusions, and 14 legacy leagues with no `best_ball` field also fail closed. Every loaded league reports `max_keepers > 0`, so that observed field is preserved but is not treated as proof that keepers were used; explicit keeper picks remain excluded individually.
- **Exact attachment verification:** [Sleeper's official API documentation](https://docs.sleeper.com/) (checked 2026-08-12) states that a league can have multiple drafts and exposes the authoritative `GET /league/{league_id}/drafts` list. The currently configured live league returned two distinct 2026 drafts (`linear` and `snake`), proving the league-level convenience `draft_id` cannot select safely by itself. The live structure also confirms draft picks and traded picks are separate resources. No current draft was auto-attached because the inspected league is dynasty and the owner's active scope is redraft without keepers.
- **Sources checked:** Sleeper's official API remains tokenless/read-only for non-commercial use, documents no ADP/default-board endpoint, and supplies the player identity map. The owner's FantasyPros Premium personal/non-commercial key was validated live on 2026-08-13: 500 requests/day, one request/second, complete official `type=ADP` responses, and platform ranks in `players[].experts`. Verified response coverage is 1QB STD/HALF/PPR and half-PPR superflex; STD/PPR `OP` probes returned empty Premium payloads and are explicitly unsupported. Returned boards include ESPN, CBS, Yahoo, RTSports, Fantrax, Sleeper, and FFPC depending on context. Commercial use or redistribution still requires separate licensing.
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

The official FantasyPros market adapter and uncalibrated Sleeper-ADP choice baseline are operational. Existing completed eligible drafts occurred before the first market snapshot, so the leakage-safe backtest correctly scores zero picks. The attached post-snapshot mock is in progress and must be completed before initial live measurement; one mock is not enough to claim calibration. Phase 3 affinity, pass, board-adherence, calibrated survival, and market-relative `WAIT`/`REACH` work must not be labeled as validated until they beat the market baseline out of sample.

Further bank persistence/memory mapping, candidate racing, transposition caching, multiprocessing, and accelerator work are intentionally profiling-gated rather than part of this baseline. Add them only after production bank sizing, live timing, and cache-hit measurements show the simpler path is insufficient.

## Handoff note

Phase 1 is complete. Phase 2 now has append-only manual and official FantasyPros multi-platform market snapshots behind a 12-hour request-driven freshness gate, exact/proxy context resolution, and a versioned inverse-ADP Sleeper choice baseline. Its backtest rejects snapshots retrieved after a draft begins. Phase 3 has market-independent descriptive profiles for every member of the real attached league. Phase 4 has exact league and standalone-mock attachment, explicit compatibility, network-free replay, coupled complete redraft rollouts, and survival summaries. Phase 6 produces deterministic, content-versioned, full-pool player-week tensors independently of fantasy ownership. Phase 7 evaluates compact roster assignments with coupled schedules/streamers and immutable per-world results. Phase 8 joins many draft continuations to paired season worlds and emits versioned numeric recommendation summaries. The next product step is completing the attached mock's live replay followed by market-baseline calibration; do not calculate plausible-window passes, board adherence, calibrated personalization, or market-relative action labels without validated time-local evidence.

## Last updated

2026-08-13 — Added the expanding candidate window: after the nine-candidate core board (preliminary 2.65 s, refined 10.6 s), the worker widens outward from the current pick in exact four-candidate ADP-distance batches (~4.8 s each) up to breadth 40 (~51 s) while the user is on the clock, with a new `expanding` status and evaluated/pool counts in the UI. `merge_evaluations` is tested equal to one combined evaluation. 125 Python and 40 frontend tests pass with a clean build.

2026-08-13 — Fixed the live monitor falling behind fast mocks (UI at pick 18 while Sleeper was at 24): synchronization now publishes immediately every poll while a single latest-state-wins worker calculates recommendations only for the newest on-clock state, discarding fingerprint-stale results (ADR-014). Added a full pick feed with explicit computation states, pick-stamped recommendations the UI refuses to show against another pick, one-picks-request-per-second polling with metadata every fifteenth poll, and completion detection from a full pick sheet. Validated live against mock `1393656492011315200` (sync 155 ms; recommendation 13.32 s profiled, then 6.66 s full / 1.61 s preliminary after the exact ADP-board iteration fix and progressive two-pass publishing); 122 Python tests and frontend tests pass with a clean production build. Exact next step: restart the local server, re-prepare real draft `1389391547115511809` with the current league-created mock, and complete the mock from the web UI so its picks become leakage-free baseline evidence.

2026-08-13 — Reproduced Sleeper's live league-mock payload with 23 picks and null pick `roster_id` values. Standalone snake/linear replay now derives fixed ownership from `draft_slot` and traded-pick overrides while preserving the raw API payload; the live mock synchronized to current pick 24.

2026-08-13 — Switched offensive counting-stat means to the official FantasyPros consensus projection API while retaining PFF only for unpublished fields, K/DST, and future validated modifiers. Projection and ADP caches now share the request-driven 12-hour setup freshness pattern; explicit refresh remains forced.

2026-08-13 — Added and live-validated the Prepare Draft → Start Monitoring web flow against real draft `1389391547115511809` and league-created mock `1393634461312106496`: all 12 managers covered, 297 Sleeper ADP players, a 50-world/609-player bank, exact slot-1 mapping, and zero blockers.
