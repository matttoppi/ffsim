# Draft Intelligence Implementation Ledger

This file is the current operational state of the project. Keep it short, factual, and updated after every meaningful milestone.

## Current status

**Phase:** Phase 8 — offline coupled draft rollouts and nested evaluation
**State:** Next-turn-aware `needs:vona4:hazard1` future-user policy and auditable opportunity-cost evidence are implemented without changing the coupled championship root objective or season replacement scoring
**Branch:** `feat/draft-intelligence`  
**Implementation code changed:** Yes
**Primary next action:** Restart the local server and run a fresh full mock, then audit VONA policy regret, roster shapes, return/tier calibration, headline stability, and latency against completed `1393836057060978688`. Do not claim real-outcome lift, `WAIT`, `REACH`, or personalization before fresh human-draft validation.

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
- [x] Add one-active-session live monitoring that polls append-only draft state, retries transient source failures, and recalculates candidate recommendations only when the user is on the clock.
- [x] Add a persistent league-wide championship-odds sidebar backed by unforced current-state continuations. It publishes preliminary and refined all-roster rankings after every pick, including opponent turns, while candidate recommendations remain on-clock-only (ADR-017).
- [x] Decouple synchronization from calculation (ADR-014): the sync loop publishes reconciled state every poll while a single worker consumes a one-slot latest-state-wins queue; finished results are discarded unless their draft-state fingerprint still matches, recommendations carry their source pick number, and the UI refuses to render one against a different current pick.
- [x] Poll one picks request per interval (default 1s) with draft metadata/traded picks every fifteenth poll (~68 requests/minute, under Sleeper's documented 1,000/minute guidance) and detect completion from a full pick sheet despite stale cached metadata.
- [x] Publish a full live pick feed (pick, round, player, position, NFL team, slot, roster) with explicit UI states for synchronizing, watching, on the clock, pending, calculating for pick N, ready for pick N, failed, discarded, stopped, and complete, plus last-sync time and pick count.
- [x] Publish an exact preliminary 100-rollout recommendation before adaptive 1,000-rollout refinement, abandon refinement between passes when the draft advances, and retry any sync failure with a forced metadata refresh so mid-draft trades and transient payloads self-heal. The former 12/300-pass latency measurements are historical; benchmark the calibrated budget in the live room.
- [x] Select the best available market player per position before filling by overall ADP, display each candidate's title odds with a signed delta versus the top option, and filter the board by position on the client.
- [x] Expand the candidate window outward from the current pick in exact four-candidate ADP-distance batches while the user stays on the clock (default: nine core candidates then breadth 40). Merged batch evaluations are provably equal to one combined evaluation under coupled randomness. Measured at live-mock pick 73: preliminary board 2.65 s, refined core 10.6 s, ~4.8 s per expansion batch, full 40-candidate board ≈51 s.
- [x] Calibrate live finalist refinement across cached early/mid/late mock states (ADR-018): screen all 40 candidates on 100 coupled continuations, advance at least five plus every paired-confidence co-leader, and refine the adaptive set on 1,000 continuations × three season worlds. The final board keeps eliminated candidates explicitly labeled as screen estimates. The default bank is 300 worlds with balanced seeded traversal; paired intervals that include zero produce one top tier instead of a unique recommendation, and the UI exposes the deterministic run identity.
- [x] Persist each live monitor as a local SQLite telemetry session with synchronized states, observed picks, every published recommendation/equity stage, discarded stale outputs, errors, durations, and complete reproducibility payloads; expose read-only filtering by draft, session, event type, and pick (ADR-023).
- [x] Add an offline `synthetic-drafts --drafts N` command that balances supported cached 10/12-team templates across all 22 draft slots, follows the engine recommendation, samples opponent paths, and stores auditable synthetic provenance, screen/final boards, pick probabilities, state prefixes, final rosters, and season outcomes without calling Sleeper or contaminating human history.
- [x] Fit the opponent softmax temperature (0.11) by maximum likelihood on 286 observed league-mock picks, thread it and three coupled season worlds per continuation through the live path and model version, and fan candidate evaluation across four worker processes with an exactly-equivalent merged result and sequential fallback (ADR-015). Measured at live-mock pick 24: preliminary board 1.93 s, refined core 6.97 s, 2.43 s per expansion batch, full 40-candidate board ≈26 s; the board separates structurally (leader 20.7%, kicker 12.7%, defense 8.0%).
- [x] Guarantee early positional coverage only for QB/RB/WR/TE; K and DEF enter the candidate window purely by ADP distance, so they surface in the late rounds instead of occupying early board slots (the pick-24 board is now entirely skill players and Nabers moves up to evaluation slot 6).
- [x] Drop forced positional coverage entirely per owner direction: the candidate pool is pure best-player-available by market ADP (fallers first, window deepening down the board), with the client-side position chips as the only positional filter (Nabers at evaluation slot 4).
- [x] Make the user's simulated future picks follow projection value over replacement with open-starting-slot awareness instead of market ADP (ADR-016, model tag `vor2`): core skill starters remain need-aware, then bench depth competes directly with K/DEF instead of a hard all-starters-first penalty; duplicate K/DEF are excluded.
- [x] Show each candidate's Sleeper ADP and counterfactual next-pick return chance from its highest-equity alternative root branch; the title-equity ranking already prices that chance through complete ADP-driven continuations.
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
- [x] Reproduce lineup eligibility, replacement streamers, head-to-head/median wins, divisions, 4/6/8-team fixed or round-reseeded playoffs, and championship outcomes.
- [x] Accept exact fantasy schedules or generate deterministic schedule realizations when the pre-draft schedule is unavailable.
- [x] Preserve common season and streamer randomness across roster assignments.
- [x] Return immutable per-world outcome vectors and exact cached/uncached equivalents.
- [x] Match the existing full-season path on a frozen common-world fixture.

## Phase 8 offline baseline completed

- [x] Pair every rollout ID with one deterministic season-world ID shared by all root candidates.
- [x] Evaluate only selected worlds for each completed draft rather than forming a naive draft-by-season cross product.
- [x] Return per-candidate championship/playoff outcomes, expected wins/points, Wilson title intervals, and paired championship deltas.
- [x] Add an explicit post-draft league simulation trigger that re-syncs the completed pick sheet and evaluates the exact observed rosters across every prepared season world, including league-wide title/playoff odds and expected wins/points.
- [x] Keep selected-world and all-world roster evaluation mathematically equivalent with exact cache keys.
- [x] Preserve multiple-draft-continuation enforcement at both rollout and nested-evaluation boundaries.
- [x] Support one or a small distinct batch of season worlds per draft continuation and cluster paired uncertainty by continuation.
- [x] Return versioned, JSON-serializable recommendation summaries with title/playoff equity, expected wins/points, continuation percentiles, paired runner-up deltas, survival detail, and exact sample counts.
- [x] Prevent pathological continuation rosters with QB/TE/K/DEF caps and a remaining-picks lineup-feasibility boundary; keep earlier opponent ADP/reach behavior probabilistic and RB/WR depth uncapped (ADR-024).
- [x] Keep the title-equity argmax as the headline, retain each candidate's deepest racing estimate, and separate refined contenders from the unranked earlier-stage watchlist (ADR-024).
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

Absolute championship percentages from the live baseline were inflated (observed ~58% for the slot-1 manager at pick 1 of a 12-team mock): rollouts originally drafted the user's future picks greedily by ADP while opponents sampled with probability proportional to 1/ADP, so the user systematically out-drafted eleven noisy opponents. A maximum-likelihood grid fit on 286 observed non-user league-mock picks selected softmax temperature 0.11 (mean NLL 2.09 versus 4.15 at the previous fixed 1.0); with the fitted temperature and three coupled season worlds per continuation, the pick-24 board differentiates structurally (leader 20.7%, kicker 12.7%, defense 8.0%) instead of showing noise-ranked ties. The fit is provisional CPU-heavy mock evidence (ADR-015); refit on human drafts before treating absolute equity as calibrated. Paired candidate deltas remain meaningful because every candidate shares the same future policy and coupled randomness. At blank pick 1, a 500-continuation replay put Bijan Robinson at 26.3% and Jahmyr Gibbs at 25.7%, but their paired delta was only +0.6 points with a 95% interval from -1.8 to +3.0; ten independent 50-continuation blocks named Bijan seven times, Christian McCaffrey twice, and Gibbs once. Bijan/Gibbs future user selections were identical across all 50 inspected paired paths, so the instability was Monte Carlo ranking of a genuine tie, not excessive continuation-policy influence. Preliminary 100-rollout boards remain screening estimates and are dimmed; at least five candidates plus every paired-confidence co-leader receive refinement, and any paired interval containing zero is reported as one unordered top tier (ADR-018/024). Fixing absolute calibration still requires refitting opponent dispersion/temperature on human drafts through the existing leakage-safe backtest. The future-user policy is now deterministic conditional-hazard VONA over the same season-VOR input, bounded by roster caps and end-of-draft lineup feasibility; its independence approximation requires fresh telemetry regret auditing (ADR-025).

The official FantasyPros market adapter and uncalibrated Sleeper-ADP choice baseline are operational. Existing completed eligible drafts occurred before the first market snapshot, so the leakage-safe backtest correctly scores zero picks. The attached post-snapshot mock is in progress and must be completed before initial live measurement; one mock is not enough to claim calibration. Phase 3 affinity, pass, board-adherence, calibrated survival, and market-relative `WAIT`/`REACH` work must not be labeled as validated until they beat the market baseline out of sample.

Further bank persistence/memory mapping, confidence-bound early stopping, transposition caching, and accelerator work are intentionally profiling-gated rather than part of this baseline. Add them only after production bank sizing, live timing, and cache-hit measurements show the simpler path is insufficient.

## Handoff note

Phase 1 is complete. Phase 2 now has append-only manual and official FantasyPros multi-platform market snapshots behind a 12-hour request-driven freshness gate, exact/proxy context resolution, and a versioned inverse-ADP Sleeper choice baseline. Its backtest rejects snapshots retrieved after a draft begins. Phase 3 has market-independent descriptive profiles for every member of the real attached league. Phase 4 has exact league and standalone-mock attachment, explicit compatibility, network-free replay, coupled complete redraft rollouts, and survival summaries. Phase 6 produces deterministic, content-versioned, full-pool player-week tensors independently of fantasy ownership. Phase 7 evaluates compact roster assignments with coupled schedules/streamers and immutable per-world results. Phase 8 joins many draft continuations to paired season worlds and emits versioned numeric recommendation summaries. The next product step is completing the attached mock's live replay followed by market-baseline calibration; do not calculate plausible-window passes, board adherence, calibrated personalization, or market-relative action labels without validated time-local evidence.

## Last updated

2026-08-14 — Replaced the static `needs:vor3` future-user policy with next-turn-aware `needs:vona4:hazard1` (ADR-025). At every simulated user turn it compares current season VOR plus probability-weighted best roster-feasible value at the next non-adjacent turn, using the calibrated opponent callback, exact ownership schedule, sequential roster updates, starter needs, and position caps. Candidate evidence reuses full root continuations to report current marginal value, next turn, expected later value, positional drop, top alternative distribution plus remaining mass, return probability, samples, seed, and versions; root ranking remains coupled title equity and `LeagueEvaluator` replacement scoring is unchanged. A four-sample nested prototype was rejected at 27x continuation cost; the conditional-hazard approximation measured 4.0x draft-only on audited pick 49 (1.07s vs 0.27s/50 continuations) and 1.20s vs 0.38s for one 50-continuation × 14-world candidate path. Validation: 175 Python tests/675 subtests, 45 frontend tests, and the production build pass; React Doctor reports only the three existing structural warnings. Fresh human telemetry is still required before claiming outcome improvement.

2026-08-14 — Added the agent-facing telemetry query runbook covering batch discovery, scenario/event completeness, captured synthetic failures, recommendation-policy verification, screen-to-final movement, candidate-board expansion, opponent probability outliers, roster construction, scenario outcomes, and the limits of self-generated evidence. Synthetic run exceptions now persist their type, message, traceback, and pick before the session is marked failed. Every documented SQL block parses against the live schema; all 167 Python tests pass with warnings treated as errors.

2026-08-14 — Added and end-to-end smoke-tested offline synthetic draft telemetry. The command prints the requested hard-coded `450 KB x N` estimate in decimal GB before preparation, discovers supported cached redraft templates, and balances the current 10-team and 12-team formats across every slot. The telemetry audit retained scenario/provenance, model/world/run/state versions, exact pre-pick prefixes, full screen and final boards, uncertainty/reason codes, recommendation-following picks, opponent selection/log probabilities, final roster assignments, and full-bank outcomes. A temporary reduced-budget smoke completed a 12-team slot-4 draft with 180 picks, 15 user states, 15 screen/final board pairs, a forensic summary, and completed-league evaluation; all 166 Python tests pass with `ResourceWarning` promoted to an error.

2026-08-14 — Audited all 17 telemetry-backed recommendations from completed mock `1393836057060978688` and fixed the root rollout/presentation failures (ADR-024). User completions had commonly reached eight or nine TEs, opponent completions frequently omitted required positions, scarcity headlining promoted QB2/QB3/TE3 candidates with high return chances, and the UI mixed refinement depths into one ordinal. The `needs:vor3` model now shares exact flex-aware starter-gap logic across policies and the current candidate pool, applies compact QB/TE/K/DEF caps, and restricts only the must-fill tail while leaving earlier ADP/reach behavior probabilistic. Decision engine v3 headlines the title-equity leader; racing retains each dropped candidate's deepest row; the War Room separates refined contenders from an unranked watchlist. Tests prove complete starting lineups, one K/DEF, at most two QBs/TEs in the representative format, and matching limits on the current recommendation pool. Validation: all 166 current Python tests pass with warnings treated as errors; 45 frontend tests and the production build pass, and React Doctor reports only the existing large-component/prop-state warnings. Exact next step: restart, run another full mock, and compare telemetry against this baseline before adding VONA/tier depletion.

2026-08-13 — Added durable live-draft telemetry (ADR-023) in a dedicated local SQLite store. Every monitor session now retains synchronized full pick prefixes, newly observed picks, every published recommendation/equity stage, the exact post-draft simulation, stale discards, errors, durations, session configuration, and the complete versioned recommendation payload. `GET /api/draft-intel/telemetry` filters chronological results by draft, session, event type, and pick after the process exits. Telemetry failures fail the monitor visibly instead of silently losing its audit trail. All 160 Python tests pass with ResourceWarnings treated as errors.

2026-08-13 — Added the post-draft full-league simulation required by the after-draft flow. Once the monitored pick sheet is complete, the War Room exposes an explicit trigger that re-syncs Sleeper, rejects incomplete drafts, and scores the exact final roster assignment across every world in the prepared `SeasonWorldBank`; it does not reuse ADP continuations or the potentially stale league-roster cache. Results replace the live estimate with final-roster championship/playoff odds and expected wins. All 160 Python and 44 frontend tests pass, the production web build is clean, and React Doctor reports only the existing large-component/prop-state warnings.

2026-08-13 — Vectorized the season evaluator's lineup selection and scoring. `LeagueEvaluator._evaluate` now computes greedy lineups as masked cumulative counts over each roster's fixed (-expected, player-id) order across all (world, week) cells at once, with missing-slot streamer contributions taken from a per-call cumulative-sum of the coupled factors; the per-cell `_lineup` loop is deleted. This is an exact optimization at the decision level: greedy picks are provably the same selection rule, and across 1,050 evaluated worlds (75 completions × 3 cached picks × 14 worlds) win counts and champion indices match the previous implementation exactly, with weekly scores differing only by float64-vs-float32 accumulation order (max 3.3e-5 on ~130-point scores) — no evaluator version bump, no matrix re-collection. Lineup+scoring is 10.6x faster; production e2e survivor trajectories and racing gates are bit-identical to the pre-change run. Measured end to end (production-shaped): final recommendation pick 24 27.2→7.5 s, pick 48 26.6→6.8 s, pick 120 27.6→5.5 s — versus the 34/64/37 s session baseline, that is 4.5x/9.4x/6.7x and inside the 6-12 s target at every stage; first useful board 1.2-1.9 s (from 2.7-4.5 s); complete 40-player screen 3.7-5.4 s. All 156 Python tests pass. Remaining levers if ever needed: vectorize the user's future-pick policy (~half the residual draft-side cost) and the per-world standings loop; the truncated stochastic horizon (workstream D) is NOT needed. Exact next step: restart the local server, re-prepare real draft `1391209065727688704` with league-created mock `1393721396240080896`, and observe stage timings plus speculation hit rate live.

2026-08-13 — Replaced SHA-256 Gumbel sampling with a counter-based splitmix64 mixer and an array callback contract (ADR-022). Shocks stay a pure function of (seed, rollout, pick, roster, player): a mixed 64-bit pick header XOR a per-player key precomputed once per board, with bit-identical scalar (`stable_gumbel`, `_gumbel_choice`) and vectorized (`gumbel_score_array`) paths proven equal by test. `sleeper_adp_choice` now returns aligned (ids, log-probabilities, gumbel keys) numpy arrays, exposes `board_player_ids`, and accepts a caller-maintained availability mask, so `_complete_draft` runs the coupled Gumbel argmax vectorized and updates board availability incrementally instead of rebuilding a ~300-way membership mask per pick (~780M SHA-256 hashes per recommendation eliminated). Continuation cost: pick 24 21.7→5.9 ms, pick 48 17.7→4.9 ms, pick 120 6.7→2.3 ms; the residual is roughly half callback softmax/caps and half the still-dict-based user policy (the next draft-side lever if ever needed). Survival rates are now computed as (count − eliminated)/count, exact multiples of 1/count. This is a criterion-2 change (different uniform source, unchanged model; choice distributions within 1e-12): seed-stability on fresh 300×14 matrices under the new sampler vs the ADR-021 reference gave pick 24 4/4 flat agreement at zero reference regret, pick 48 3/4 at zero regret with improved cross-seed stability (modal 12512 on 4/4 seeds vs 3/4), and pick 120 the familiar flat ~30-candidate tier (old procedure itself 1/4 modal) with regret bounded at 0.211pp — under the 0.5pp stop; the (150, 225, 300) ladder matched flat 12/12. Measured end to end (production-shaped): pick 24 28.6→27.2 s, pick 48 41.4→26.6 s, pick 120 35.0→27.6 s (vs the 34/64/37 s session baseline); first board 5.1-5.5 s; the 40×100 screen is now 16-18 s and ~85% season evaluation, so vectorizing `LeagueEvaluator` is the dominant remaining lever. All 156 Python tests pass. Exact next step: vectorize `LeagueEvaluator._evaluate`/`_lineup` (preserving the 158209f playoff reseeding) and re-benchmark against the 6-12 s target.

2026-08-13 — Reallocated the candidate evaluation budget from 1,000 continuations × 3 season worlds to 300 × 14 (ADR-021) after measuring that paired-delta variance between top candidates is 97-100% season noise at cached picks 24/48/120 (within-continuation σ²ₛ 0.06-0.28 vs draft-side σ²_d ≤ 0.002, /tmp/ffsim_var_decomp2.py pattern) while a continuation costs ~7-22 ms and a season world ~2.3 ms. The new allocation beats the validated 1,000×3 paired standard error on every measured pair (pick-48 leaders: 0.65-0.71pp vs 0.74-0.82pp) at 0.56-0.60x the per-candidate compute, and the doubled screen precision shrinks mid-draft screen co-leader tiers (pick 48: 27-34 → 7-26; pick 24: 8-28 → 5-10). Seed-stability protocol on fresh m=14 observation matrices (4 seeds × 3 picks, /tmp/ffsim_race_obs2_pick*_m14.npz) vs the validated matrices: pick 24 agrees 4/4 with zero reference regret and is cross-seed stable from n=150 (the old allocation needed n=750); pick 48 keeps the same modal leader (12512) and the same 3/4 cross-seed stability at n=300, with every per-seed flip inside the mutually reported 95% co-leader tiers and reference regret ≤ 0.97pp (the old procedure's own outlier seed sits at 0.70pp); pick 120 is a flat ~30-candidate tier (reference spread < 1pp, old leaders differ on 3/4 seeds) where every flip costs ≤ 0.36pp, below the 0.5pp regret stop. n=250 was tested and rejected (leader wobble at pick 48); 300 stands. The racing ladder is recalibrated to (150, 225, 300), matching its own flat refinement 12/12 at 0.54-0.72x the extension work. Survival estimates at n=300 deviate ≤ 3.7pp from n=1,000 (binomial; note the three cached states are slot-1 adjacent double-turns where survival to the next pick is exactly 1, so the bound was measured from a mid-snake roster on unforced completions). League equity keeps 3 worlds (`LIVE_EQUITY_WORLDS_PER_ROLLOUT`); worlds are clamped to the bank size so small preparations remain valid. Measured end to end (production-shaped stages, /tmp/ffsim_perf_e2e3.py with final=300): pick 24 34→28.6 s, pick 48 64→41.4 s, pick 120 37→35.0 s to the final recommendation; refinement collapsed (pick 24 finishes at stage 150 under the regret stop in 2.7 s) and the 40×100 screen is now the dominant cost everywhere (18-25 s, roughly two-thirds of it season evaluation at m=14). All 156 Python tests pass. Remaining levers, in order: replace SHA-256 Gumbel sampling with a vectorized splitmix64 mixer (criterion-2 change, ~5x on the draft side), then vectorize `LeagueEvaluator._evaluate`/`_lineup` (~3-5x on the season side, now the larger share); together they project the screen to ~4 s and end-to-end into the 6-12 s target. Exact next step: land the splitmix64 sampler with a fresh seed-stability collection under the 300×14 allocation.

2026-08-13 — Cut live recommendation latency roughly 4x with exact optimizations plus validated racing refinement and speculative pre-clock screening (ADR-020). Profiling on cached picks 24/48/120 (M5 Max, 300-world bank) put ~88% of the cost in continuation sampling (~0.37 ms per simulated opponent pick: choose 0.19, Gumbel hashing 0.11, redundant renormalization 0.08) and exposed the real driver: the unbounded co-leader tier fed a flat 1,000-rollout refinement, so pick 48 promoted 36/40 finalists and took 556 s end to end on the fixed 4-worker pool (276 s at pick 24, 203 s at pick 120). Changes: worker pool now `min(12, cores-2)` (measured 12 optimal, 16 flat); the opponent-choice callback is a masked vectorized softmax mixture (log-probabilities within 1e-12, coupled Gumbel picks proven identical by test); refinement reuses screen rollout IDs 0-99 exactly via new `merge_rollout_ranges`/`merge_survival_reports` (dataclass-equality tests prove merged [0-99]+[100-999] equals one flat 0-999 evaluation, including survival and run identity; `PlayerSurvival` gained an integer `threat_total`); large ranges fan out in 250-rollout chunks; refinement races in stages (300 then full budget) keeping only the statistically tied tier, with a 0.5pp bounded-regret early stop, and publishes each intermediate stage. Racing validation: offline simulation on collected 1,000-rollout observation matrices (4 seeds x 3 picks) matched flat refinement's final recommendation 12/12 with zero added regret at 0.48-0.91x the work. Speculation: when exactly one opponent pick precedes the user's turn, the monitor screens the model-argmax next state (`DraftState.with_pick` reproduced all 613 cached mock transitions exactly) and reuses it only on an exact state-signature match. Two further validated rounds: `sleeper_adp_choice` declares `returns_final_log_probabilities`, so temperature-1.0 rollouts skip revalidation, the identity renormalization, and the ~11k-player frozenset copy per pick (constant-shift Gumbel argmax, pick sequences proven identical by test); and the racing ladder moved to stages (300, 600, 1000) after offline simulation on the same observation matrices kept 4/4 flat-agreement per pick at 0.42-0.85x the refinement work, while reduced final budgets (600/800) broke agreement and were rejected — 1,000 stands. Worker scaling beyond 12 measured flat (memory-bound), and GPU work remains unjustified: the loop is hash/Python-bound, and the lockstep-batch restructure a GPU needs would change sampled continuations and force recalibration (ADR-009 gate unmet). Measured end to end: pick 24 276→34 s, pick 48 556→64 s, pick 120 203→37 s; first useful board 2.7-4.5 s (or ~0 s on a speculation hit); complete 40-player screen 7-13 s; intermediate refined tiers publish at each stage. All 156 Python tests pass (144 baseline + 12 new). Remaining bottleneck: broad mid-draft ties still extend a ~15-21 candidate tier through the deep stages (~35 s of the pick-48 total); the next lever, if ever needed, is lockstep-batched rollouts with a counter-based RNG (a recalibration-level change). Exact next step: restart the local server, re-prepare real draft `1391209065727688704` with league-created mock `1393721396240080896`, and observe speculation hit rate plus stage timings in a live room.

2026-08-13 — Calibrated live candidate sampling across cached picks 24, 48, and 120. Ten 12-continuation screens produced 29 different finalists with only 0.73/5 mean pairwise overlap. A hard top-five cutoff remained unreliable through 500 screen continuations; at pick 48 even a 100-continuation top-20 screen captured the independent pooled raw leader in only 3/4 seeds. Confidence-tier promotion retained the high-depth leader across every tested seed. Within a fixed 12-player competitive set, 1,000 continuations was the first final budget with one leader across all six seeds at pick 48 (500: 4/6; 750: 5/6; 1,000: 6/6). Live defaults are now a 100-continuation broad screen, adaptive promotion of at least five plus all screen co-leaders, and 1,000-continuation refinement with three season worlds per continuation. All 144 Python tests pass.

2026-08-13 — Added exact Sleeper playoff reseeding for `playoff_seed_type=1` in both the full-season bracket and compact `LeagueEvaluator`; unknown values still fail closed and evaluator versions now include the reseeding rule. The cached 10-team Triton league now passes season-evaluation compatibility. The 15 focused playoff/evaluator/compatibility tests and the direct bracket regression pass. Exact next step: restart the local server and re-prepare real draft `1391209065727688704` with league-created mock `1393721396240080896`.

2026-08-13 — Removed the systematic rest-of-draft biases behind out-of-ADP recommendations (ADR-019). Opponents now mix the fitted sharp board-follower with a 15% reach component at structural temperature 0.3 and respect positional sanity caps (no second K/DEF, QB/TE capped at startable seats plus one), so target survival is no longer near-certain and waiting carries honest risk. Finalist refinement always includes the best remaining market pick and the best value-over-replacement pick, closing the 12-continuation screening lottery; statistically tied co-leaders are headlined by scarcity (lowest next-pick return chance, `SCARCITY_TIEBREAK`) instead of noise-argmax with lexicographic ID ties. Championship intervals now reuse the paired across-rollout standard error, final-pick evaluations skip survival instead of failing, and the position-timing panel applies a reach-displacement cushion before counting a player available at a future turn. The reach rate is a prior — refit it with the temperature on human drafts via the backtest's new `reach_rate` parameter. All 141 Python and 43 frontend tests pass; the production web build is clean.

2026-08-13 — Kept the complete 40-player recommendation window visible after finalist refinement. The top five retain their 300-continuation results while the other 35 remain clearly labeled 12-continuation screen estimates, avoiding both the misleading five-player cap and an 8× compute increase. All 135 Python and 43 frontend tests pass; the production web build is clean.

2026-08-13 — Corrected candidate return probability to use the best alternative root branch instead of the branch that already drafted the player, and surfaced Sleeper ADP plus modeled next-pick survival on every board row. Broad screening tracks the full candidate pool so cross-batch wait probabilities remain available; finalist refinement tracks all finalists. The coupled championship ranking remains authoritative and already includes later selections when a target survives. All 135 Python and 43 frontend tests pass; the production web build is clean.

2026-08-13 — Replaced the broken one-pick cost-of-waiting panel with QB/TE timing recommendations. Adjacent snake picks now form one turn (pick 24 looks ahead to 48, not 25); the UI shows the best projected ADP-available option at the next three turns and recommends the pick before the largest projected falloff. The full championship board remains authoritative across positions. 134 Python and 43 frontend tests pass; the production web build is clean.

2026-08-13 — Reallocated the live recommendation budget from 40 candidates × 50 continuations to a coupled 12-continuation broad screen plus 300 continuations × three season worlds for five finalists (ADR-018). Increased the default bank from 50 to 300 worlds and made traversal exactly balanced before repetition. Paired intervals now gate unique recommendations, with tied finalists shown as one top tier; state/run signatures and exact seed/model/world versions are visible in the War Room. All 134 Python and 43 frontend tests pass with a clean production build; live latency remains to be measured after re-preparation.

2026-08-13 — Calibrated the live opponent model and parallelized candidate evaluation (ADR-015). Grid MLE on 286 observed league-mock picks fit softmax temperature 0.11 (mean NLL 2.09 vs 4.15 at the old fixed 1.0), which deflates the inflated absolute title equity, prices positional scarcity (pick-24 board: leader 20.7%, kicker 12.7%, defense 8.0% instead of noise-ranked 30% ties), and makes deltas structural. Live evaluation now uses three coupled season worlds per continuation and fans candidates across four worker processes with a tested exactly-equivalent merge and sequential fallback: preliminary board 1.93 s, refined core 6.97 s, 2.43 s per four-candidate expansion batch (~26 s to breadth 40, from ~51 s). 126 Python and 41 frontend tests pass with a clean build. Temperature provenance is CPU-heavy mock rooms — refit on human drafts before treating absolutes as calibrated.

2026-08-13 — Added the expanding candidate window: after the nine-candidate core board (preliminary 2.65 s, refined 10.6 s), the worker widens outward from the current pick in exact four-candidate ADP-distance batches (~4.8 s each) up to breadth 40 (~51 s) while the user is on the clock, with a new `expanding` status and evaluated/pool counts in the UI. `merge_evaluations` is tested equal to one combined evaluation. 125 Python and 40 frontend tests pass with a clean build.

2026-08-13 — Fixed the live monitor falling behind fast mocks (UI at pick 18 while Sleeper was at 24): synchronization now publishes immediately every poll while a single latest-state-wins worker calculates recommendations only for the newest on-clock state, discarding fingerprint-stale results (ADR-014). Added a full pick feed with explicit computation states, pick-stamped recommendations the UI refuses to show against another pick, one-picks-request-per-second polling with metadata every fifteenth poll, and completion detection from a full pick sheet. Validated live against mock `1393656492011315200` (sync 155 ms; recommendation 13.32 s profiled, then 6.66 s full / 1.61 s preliminary after the exact ADP-board iteration fix and progressive two-pass publishing); 122 Python tests and frontend tests pass with a clean production build. Exact next step: restart the local server, re-prepare real draft `1389391547115511809` with the current league-created mock, and complete the mock from the web UI so its picks become leakage-free baseline evidence.

2026-08-13 — Reproduced Sleeper's live league-mock payload with 23 picks and null pick `roster_id` values. Standalone snake/linear replay now derives fixed ownership from `draft_slot` and traded-pick overrides while preserving the raw API payload; the live mock synchronized to current pick 24.

2026-08-13 — Switched offensive counting-stat means to the official FantasyPros consensus projection API while retaining PFF only for unpublished fields, K/DST, and future validated modifiers. Projection and ADP caches now share the request-driven 12-hour setup freshness pattern; explicit refresh remains forced.

2026-08-13 — Added and live-validated the Prepare Draft → Start Monitoring web flow against real draft `1389391547115511809` and league-created mock `1393634461312106496`: all 12 managers covered, 297 Sleeper ADP players, a 50-world/609-player bank, exact slot-1 mapping, and zero blockers.

2026-08-13 — Landed the original cost-of-waiting panel; it was later superseded by the three-turn ADP timing curve after adjacent snake picks made the one-pick horizon misleading.

2026-08-13 — Refined the future-user policy to `vor2`: QB/RB/WR/TE/flex openings are filled before bench depth, but K/DEF no longer trigger the hard starter-fill gate and cannot be duplicated. On the frozen pick-24 Nabers branch, pick 96 became skill-position depth in 50/50 continuations; K/DEF usually moved to picks 120–144.

2026-08-13 — Added league-wide live championship rankings (ADR-017): unforced continuations now score every roster from the same draft paths and season worlds; the monitor publishes 12-rollout preliminary and full-budget refined odds after every pick, including opponent turns, while retaining the prior labeled table during recalculation. The responsive sidebar identifies the owner, shows playoff context, and labels absolute odds as uncalibrated. All 132 Python tests and 42 frontend tests pass; the production web build is clean. Live-room latency remains to be measured after server restart/re-preparation.
