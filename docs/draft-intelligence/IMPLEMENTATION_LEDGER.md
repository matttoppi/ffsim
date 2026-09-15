# Draft Intelligence Implementation Ledger

This file is the current operational state of the project. Keep it short, factual, and updated after every meaningful milestone.

## Guillotine calculator — 2026-09-15

Owner-requested standalone `python -m ffsim.guillotine` command. It reads
Sleeper Chopped best ball rosters, elimination flags, budgets, and chop
transactions; imports current FantasyPros weekly projections by stable ID;
and reuses the empirical player sampler for paired next-week chop comparisons.
The best ball scorer has no hypothetical waiver replacements. Current
FantasyPros rest-of-season position ranks now identify lasting starter tiers.
Explicit percentage ranges distinguish elite starters, core starters, current
week upgrades, and $0–$5 marginal depth. Roster fit, survival urgency, and teams
remaining adjust upgrade ranges. These are declared heuristics, not learned
auction prices. The blanket $5 weekly limit has been removed.

The automatic weekly allowance funds the largest range plus $10 for depth.
Completed purchases reduce it; explicit weekly caps and player bids remain
available. Valuation ranges and funded claim ranges are separate. Shared drops
count once at the largest offer; independent claims count separately. New input
snapshots include current rest-of-season rankings and their source metadata.
Older snapshots without rankings require a refresh. See ADR-049 and README.

Validation: all 276 Python tests pass, including eight focused calculator tests
for lasting value, roster fit, risk and stage adjustments, separate valuation
and allocation limits, source validation, and weekly spend carryover. A final
focused check also verifies that final-week spending can use the funds remaining
after earlier purchases. The fresh Week 2 report completed 5,000 simulations:
Puka $50–$150, Nico $30–$105, Corum/Worthy $0–$5, and a $160 automatic allowance.
The input snapshot preserves all 408 source ranks; offline replay exactly matches
the fresh report. Claims that can succeed together remain within the allowance.
No claims are submitted.

## Current status

**Phase:** Phase 8 — offline coupled draft rollouts and nested evaluation
**State:** Candidates are ranked by mean projected completed-roster value across paired continuations (ADR-026); with the future-user policy aligned to the terminal scorer (ADR-031) that ranking is exactly the take-vs-wait regret ordering, and the practical-tie gate is 0.1 points sized to the measured residual (ADR-032). RACE-01 uses one final leader-minus-candidate practical-tier predicate (ADR-033), and decision engine v9 keeps every selected finalist through the 300-rollout maximum because intermediate stochastic confidence intervals are non-monotone (ADR-036). Focused tests and the corrected one-state smoke pass; the all-2,384-state run remains pending, so RACE-01 is not releasable. WHY-01 makes War Room evidence branch-named and field-derived (ADR-034). MKT-01 preserves canonical historical scoring/provenance and separates requested league context from the selected market board (ADR-035); implementation and validation are complete. Compact recommendation-stage telemetry is schema version 2. The opponent market model is `sleeper-adp-inverse-rank-v2`; no decision-engine, draft/VONA-model, roster-scorer, `SeasonWorldBank`, or cache version advances for MKT-01. Decision engine v9.
**Branch:** `feat/draft-intelligence`
**Implementation code changed:** Yes
**Primary next action:** Recover the exact world-bank input bundle used by batch `20260815T043426-52dba2d4`, or generate and freeze a replacement corpus before rerunning the all-state RACE-01 validator. Refinement optimization belongs to PERF-01.

**RACE-01 validator blocker — 2026-08-28:** The full validator was attempted twice. The first attempt failed because template preparation selected a newer exact-team-count market snapshot instead of the snapshot recorded by telemetry. The validator now loads the recorded snapshot by immutable ID; focused market and validator tests pass 12/12. The second attempt then failed before state evaluation because the recorded `SeasonWorldBank` version `f300c1bf66636ce4465210aeafad1f59fea7e86cefd54ec9bd4c6c21abec8ef7` does not match the only retained player/projection cache, which builds version `5e394919bdad453ca3a9f18f348dd86f20da7c6721c1a15987b0361184cc936a`. The checkpoint JSONL remains empty because no state evaluation started. The telemetry snapshot did not preserve the original world-bank inputs, and no old `players.json` copy exists in the repository, cache, `tmp`, `archive`, or `output`. Do not remove the identity check. RACE-01 remains pending and not releasable.

## ALPHA-2026 — Offline model search

**State:** Offline research implementation complete; no live integration approved.

- Added isolated, frozen-gate experiments under `experiments/draft_alpha_2026/`.
- Audited the immutable 10,013-league-season Sleeper corpus, current 2026 projection sources, cached SQLite stores, and available APIs.
- Reconfirmed that the 4,707-parameter completed-draft neural network and residual corrections do not beat the historical-market outcome baseline.
- Manager-position residuals improved seen-manager player-choice log loss in both rolling folds, the seen 2024 transfer, and the one-time 2025 benchmark. The 2025 improvement was `0.031930` with paired draft-clustered difference `-0.031930 [-0.033745, -0.030163]`. The 2021–2023 transfer fit covers 11 of 25 configured managers (`02c_manager_2024_diagnostic/result.json`); the final 2021–2024 locked-benchmark fit covers 12 of 25 (`02d_manager_locked_2025/result.json`). Both use the fixed 20-pick threshold.
- Rejected live manager use: downstream exact-player survival Brier improved only `0.000338`, below the fixed `0.001` gate, and false-safe rate worsened by `0.000095`.
- A fixed hierarchical `(relative rank, gap, round, position)` survival model passed both rolling folds and the seen 2024 transfer. Rolling Brier was `0.070530` and `0.074189`; 2024 Brier was `0.094496`. Against the prior exact rank-gap-round baseline, rolling Brier improved by `0.013158 [-0.013779, -0.012584]` and `0.004754 [-0.005608, -0.003960]`, where intervals are paired model-minus-baseline differences. The elite rank-2 RB, round-1, gap-18 estimate is `0.621%` from 2,006 direct observations.
- Rejected VONA route ranking. Timing report v3 now captures ranks 1–10 for every candidate branch, including next-turn-ineligible players, but one-turn route value selected Los Angeles DEF at terminal rank 23. Trevor Lawrence led the 300-rollout completed-roster evaluation by `12.4938 [11.9047, 13.0829]` paired points; route-versus-terminal rank correlation was `0.0791`. Hierarchical timing remains terminal-subordinate explanation only.
- `DATA_INVENTORY.md` records sources, API boundaries, model results, assumptions, and the selected offline architecture.
- Built immutable hierarchical-survival artifact `0ee13d56a87c5c8206a5c437879b3a8c1419dfd4d4d7c0dc591905d58faf9d91`, static manager artifact `eaa845cf7e258fca95f51e9ee253f41f75a3d403041f90f4263361ba8580eab1`, and corrected roster-manager artifact `b1a99ee7cbce2d0fd59dd383aeff7ad0438adc875cf169c26bfc6b87a5abfd93`. All remain `research`; only the fail-isolated shadow collector can load the hierarchical and corrected roster artifacts.
- Round-phase manager factors improve static manager log loss by `0.02038` and `0.01401` in rolling folds. Corrected position-count reconstruction adds board-unsupported source picks to roster state and improves the round model by `0.01404` and `0.01397`, then by `0.01612` in the seen 2024 transfer; the validations apply 916, 956, and 965 missing-board state updates. The marginal-hazard approximation still worsens, and the full manager callback leaves the baseline practical tier. Across six frozen cached states at the full 300-rollout budget, a fixed 10% mixture retains the same leader as baseline in all six states, exercises 11,939,538 personalized and 2,439,628 population-fallback callback calls, and keeps every shadow leader inside the baseline practical tier. One-turn route ranking remains practical in only three states.
- Audited three historical projection sources. The local PFF file lacks authoritative provider timing and IDs; Sleeper rows were updated after each season; FantasyPros responses lack observation timestamps and personal access does not authorize historical bulk use. No source entered training. Added a fail-closed `historical-projection-import` path requiring approved timestamp, authorization, Sleeper IDs, raw hash, and draft-time cutoff evidence.
- Added asynchronous live alpha shadow collection after the terminal recommendation is published. It captures branch-specific return evidence, runs a 20-rollout fixed 10% manager shadow, persists replay inputs and support/fallback counts, discards stale results, and cannot fail the monitor when calculation or telemetry fails.
- Added `GET /api/draft-intel/alpha-shadow` and a War Room `Draft alpha — shadow` panel with ready, pending, stale, disabled, and failed states. The panel names return probabilities and intervals, manager agreement, and top next-turn alternatives while stating that terminal ranking remains authoritative.
- Cached `LiveDraftMonitor` verification keeps the recommendation hash identical before and after shadow collection, records one telemetry event, captures the full top ten, exercises eight supported and three fallback opponent rosters, and finishes the serialized shadow in `5.3425` seconds. The 20-rollout manager shadow leader remains inside the terminal practical tier.
- Added `alpha-shadow-audit` module, CLI, read-only API, immutable report output, and War Room aggregate summary. The audit deduplicates state identity and reports latency, failure/discard rates, top-ten capture, manager agreement and practical retention, support/fallback calls, return coverage, artifact versions, rounds, and pick gaps without modifying telemetry.
- The initial six-state audit failed only latency: median `10.2911s`, p95 `13.5098s`. Limiting the 20-rollout manager shadow to the five terminal finalists reduces median to `5.1556s`, p95 to `6.7061s`, and maximum to `6.7076s`; hierarchical timing p95 is `0.0583s` and manager-shadow p95 is `6.6598s`. The optimized development gate passes with zero failures, 100% top-ten capture, 100% manager practical-tier retention, personalization and fallback use, and `decision_active: false`.
- The audit exposes the next support problem: only `46.3%` of terminal candidates have rank-10 survival estimates, `53.7%` are outside the model, direct support ranges from 2 to a median 869, and exact manager/terminal agreement is `4/6` while practical retention is `6/6`. The live evidence gate remains blocked at 6/30 new states.
- A separately frozen rank-20 hierarchy passes every rolling model gate. Rank-1–10 cells are row-equivalent to the current model, rolling rank-1–10 Brier changes stay within `±0.000001`, and the elite rank-2 RB gap-18 estimate remains `0.621%`. Rank-11–20 Brier improves by `0.010101` and `0.001517` in rolling folds with paired upper bounds below zero; the seen 2024 improvement is `0.008718`. False-safe rates remain below `0.092` and expected calibration error below `0.035`.
- Immutable rank-20 artifact `055517e675b968c32da4af629bc38b7c1ae335152639df86c648e007e02e3437` raises six-state terminal-candidate return coverage from `43.4%` to `88.2%`. Its integrated shadow candidate passes the cached development gate with p95 `6.8113s`, zero failures, 100% manager practical retention, and the live rank-10 default unchanged.
- Rank-20 route ranking remains rejected. It matches the terminal leader in four of six states but loses by `11.4544 [10.2695, 12.6394]` and `17.3812 [16.0095, 18.7528]` paired points in the other two. Rank-20 is evidence-only research and cannot rank picks.
- Added a simple `Projected points` view to projection monitoring. It shows the top ten undrafted players at each position by league-scored season points, including players outside current roster-feasibility filters. QB/RB/WR/TE use FantasyPros as the primary projection source; K/DEF use PFF. The existing VORP, WORP, roster-value, ADP, and lookahead table remains available through `Full value`.

**Next model step:** Collect at least 30 new real live-shadow states before deciding whether rank-20 replaces rank-10 for evidence display. Keep route ranking disabled and terminal completed-roster value authoritative. Separately recover the RACE-01 world-bank input bundle.

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

## Audit remediation in progress

- [x] TEL-01: use WAL, a bounded five-second writer wait, visible failures, and native SQLite snapshots for long audits.
- [x] TEL-02: persist compact live/synthetic recommendation stages, exact work and conditional-selection counts, branch provenance, and only broad-screen/ready full boards.
- [ ] RACE-01: make staged refinement agree with true flat evaluation under the final 0.1-point practical gate.
  - [x] Implement the shared predicate and pass focused and full Python tests.
  - [x] Pass the named actual racing-versus-flat replay gate and six extra recorded mismatch-state checks.
  - [x] Add the checkpointed full-corpus validator; its one-state smoke found an unsafe elimination.
  - [x] Replace intermediate elimination and early stopping with full-budget finalist refinement; 73/73 focused tests and the corrected one-state smoke pass.
  - [ ] Pass the exact staged-versus-true-flat comparison across all 2,384 corpus states.
- [x] WHY-01: make every War Room claim branch-named and field-derived; telemetry schema version 2 is the only version change.
- [x] MKT-01: preserve canonical historical context and distinguish the target league from the selected market board (ADR-035).
  - [x] Implement scoring/provenance persistence, detailed context hashing, exact-team-count board preference, explicit generic fallback, and session-config telemetry.
  - [x] Pass final focused and full validation.
- [ ] PERF-01: recover refinement efficiency without using intermediate stochastic confidence intervals as irreversible elimination or stop gates.

## Phase 1 completed

- [x] Read-only `draft-audit` command with manager history discovery and normalized draft/pick records.
- [x] Global draft deduplication by `draft_id` and pick deduplication by `(draft_id, pick_no)`.
- [x] Explicit draft inclusion/exclusion classification and keeper-pick exclusion.
- [x] Active Sleeper-ID canonical match reporting and frozen representative API fixtures.
- [x] Content-addressed raw snapshots and idempotent normalized SQLite persistence.
- [x] Persistent canonical players and one-to-one Sleeper external-ID mappings.
- [x] Deduplicated historical league context with best-ball and missing-context exclusions.
- [x] Preserve complete canonical numeric league scoring settings, including zero and unsupported keys, plus conservative draft provenance.

## Phase 2 local slice completed

- [x] Append-only, content-addressed market snapshot and observation schema.
- [x] Strict manual CSV import with canonical Sleeper-ID mapping and exact raw-byte preservation.
- [x] Historical latest-at-or-before snapshot lookup with optional maximum staleness.
- [x] Idempotent re-import and historical reconstruction tests.
- [x] Validate the official FantasyPros Premium `type=ADP` payload with the owner-provided key.
- [x] Store consensus and returned ESPN/CBS/Yahoo/RTSports/Fantrax/Sleeper/FFPC boards from one request per format context.
- [x] Refresh only missing or at-least-12-hour-old 1QB STD/HALF/PPR and half-PPR superflex contexts; no background loop.
- [x] Map FantasyPros players through `sportsdata_id` to Sleeper `sportradar_id`, map DST by team, and report ambiguous/unmatched identities without guessing.
- [x] Resolve separate target and base-board contexts, prefer exact team count, and label generic-team-count, tight-end-premium, reception, and format proxies explicitly.
- [x] Select only snapshots both observed and retrieved before the evaluation time.
- [x] Provide a versioned inverse-ADP Sleeper choice callback directly compatible with coupled draft rollouts.
- [x] Add a read-only `market-backtest` command with log loss, reciprocal rank, top-K accuracy, coverage, context, snapshot, and skip reporting.

## Phase 3 in progress

- [x] Reconstruct target-manager roster state and the observed available player pool before each eligible non-keeper pick.
- [x] Seed keeper ownership before pick one regardless of the round containing the keeper row.
- [x] Add transparent position counts, round timing, and first-position timing summaries.
- [x] Add season, draft scoring-label, and team-count context counts plus a read-only `manager-audit` command.
- [x] Add keeper-aware, context-weighted roster counts after every observed round.
- [x] Add raw and weighted four-round zero/hero/heavy-RB and WR-heavy start evidence.
- [x] Add raw and weighted QB/TE first-round timing, including drafts without the position.
- [x] Apply transparent per-draft season, scoring-type, and league-size relevance components while retaining raw counts and component values.
- [x] Validate the descriptive baseline against 2,197 picks by 20 stored managers; every member of the attached real league has eligible history.
- [x] Validate `manager-audit` against the current target context: 2026, 12-team PPR.

### OPP-01 — Offline population choice and survival calibration

**State:** Offline slice complete. Fixed choice and exact-player survival passed;
top-three tier survival failed, so the joint artifact is rejected and offline.

**Frozen contract before fitting:**

- Read the accepted rolling-market database for 2021–2024 only. Fit on
  2021–2023, validate on 2024, and never query 2025.
- Reconstruct each supported draft sequentially. Remove every observed pick
  from the target draft's leakage-safe pre-draft market board.
- Use the existing accepted inverse-ADP baseline as the one fixed population
  choice setting: `temperature=1.0`, `reach_rate=0.0`. Do not fit or search
  choice parameters in OPP-01.
- Compare that fixed setting only with the current provisional live prior
  (`temperature=0.11`, reach rate `0.15`).
- Build exact observed next-turn samples after each roster pick. Track the top
  ten remaining market players and the top-three market tier until that
  roster's next pick.
- Player survival uses a Beta-smoothed market-rank/gap baseline. The frozen
  population model adds position and round bucket with shrinkage strength 50.
  Tier survival uses the same gap/round/context hierarchy.
- Report choice log loss, multiclass Brier score, top-K accuracy, calibration,
  exact-player survival log loss/Brier/calibration, tier survival
  log loss/Brier/calibration, context support, and draft-clustered intervals.
- Choice passes only with at least `0.01` lower 2024 log loss than the
  provisional live prior and an upper 95% draft-clustered paired interval below
  zero.
- Player and tier survival pass only with at least `0.001` lower 2024 Brier
  than their market-only baselines and upper paired interval bounds below zero.
- A passing offline artifact is still `research`. Live use requires a separate
  decision, exact callback-equivalence tests, and no regression in coupled
  rollout behavior.

**Boundary correction:**

- `opponent-final-20260828` and `opponent-final2-20260828` evaluated a 70-cell
  temperature/reach grid. They are exploratory, rejected for boundary
  noncompliance, and cannot support a model claim or live decision.
- The accepted corrective run uses only the pre-existing inverse-ADP setting
  (`temperature=1.0`, no reach). Its manifest records one temperature and one
  reach rate.

**Accepted OPP-01 result — 2026-08-28:**

- Training used 3,834 drafts, 657,321 supported choices, 617,061 next-turn
  states, and 6,170,610 exact-player survival samples from 2021–2023.
- Validation used 2,320 drafts, 401,978 supported choices, 376,694 next-turn
  states, and 3,766,940 player survival samples from 2024.
- The fixed inverse-ADP choice model passed against the current provisional
  live prior. Its 2024 log loss was `5.44151` versus `11.03484`; paired
  difference was `-5.59333 [-5.69700, -5.47563]`. Coverage was 99.72%.
  This is strong evidence that the mock-fitted live temperature does not
  transfer to the historical human corpus, but OPP-01 does not change it live.
- The exact-player population survival model passed: Brier `0.094609` versus
  `0.120211`, improvement `0.025603`, with paired draft-clustered difference
  `-0.025603 [-0.026916, -0.024012]`. Log loss improved from `0.390470` to
  `0.310143`.
- The top-three tier model failed its Brier gate: `0.036796` versus `0.036520`,
  difference `+0.000276 [-0.000453, +0.000889]`. Its log loss improved, but
  secondary log loss cannot rescue the frozen Brier gate.
- Choice and exact-player survival passed. The joint artifact remains
  `rejected` because tier survival failed. The passed components remain offline
  research evidence for separately gated integration work.
- Output: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/opponent-final4-20260828`.
  Contract hash: `5d1a7e1896d84d2b9f697c58f3e9b3c5300ffe4eb149d87787e863b9f1fd5c50`.
  Manifest file SHA-256:
  `c2408d9f886a8a8593d9cf29ae7c3a5658476ee97324e28543831fbd3c9e3595`.
  Model SHA-256:
  `d58ecda5d98c8bb84773157aae7a7ee07a1a4ac6ad28577edf542dd761e239ba`.
  Report SHA-256:
  `a96433dfe6cd750a680d71d2a6b976c46e8b43a0f82809dd5385a39a701e8cac`.
- `opponent_model.py` SHA-256:
  `cb9c6b570e366908467220cf6cabfaebfa70cf894167fb3f7bd797e77105ad56`.
- The accepted fit ran with warnings promoted to errors. It queried only
  seasons 2021–2024 and records `locked_test_loaded: false`; 2025 was not
  queried.
- Warning-strict verification passed two focused OPP-01 tests, 66 historical-package tests, and 77 live boundary tests.

### OPP-02 — Offline wait-versus-reach replay

**State:** Replay complete and `rejected` by its frozen coverage gate. The
diagnostic found materially fewer false-safe calls but became too conservative.

**Frozen contract before replay:**

- Replay 2024 historical next-turn states only. OPP-01 already used 2024, so
  this is downstream diagnostic evidence, not a new independent holdout.
- Never query 2025.
- After each observed roster pick, track the top ten remaining market players
  until that roster's next pick. Preserve whole-draft clustering.
- Compare three probabilities: the market-rank/gap survival baseline, the
  passed OPP-01 exact-player predictor, and the current live
  `temperature=0.11`/reach-`0.15` conditional modal-hazard approximation.
- Classify `safe to wait` at survival probability `>= 0.70` and `urgent` at
  probability `<= 0.30`. Do not tune these thresholds.
- Report Brier score, log loss, calibration, safe/urgent coverage, false-safe
  rate, false-urgent rate, elimination-pick offset, and realized fallback
  market-rank loss.
- The OPP-01 predictor passes the replay gate only if its false-safe rate is at
  least `0.02` lower than the market baseline, its safe coverage is no more
  than `0.10` lower, and its upper 95% draft-clustered paired Brier interval is
  below zero.
- A pass creates only an offline `research` replay artifact. Live use requires
  a separate decision and coupled-rollout equivalence tests.

**OPP-02 result — 2026-08-28:**

- Replayed 376,694 next-turn states and 3,766,940 top-ten player targets from
  2,320 complete 2024 drafts.
- The historical player model reduced Brier score from `0.120211` to `0.094609`
  with paired difference `-0.025603 [-0.027146, -0.024197]`, and reduced log
  loss from `0.390470` to `0.310143`.
- At the frozen 0.70 safe threshold, the market baseline called every target
  safe and was wrong 14.86% of the time. The historical model called 79.60%
  safe and was wrong 7.10% of the time: a 7.76 percentage-point false-safe
  improvement.
- The historical model's safe coverage fell by 20.40 percentage points, above
  the frozen 10-point maximum. It therefore failed the replay gate despite
  better calibration and false-safe behavior.
- Historical-model false-safe players disappeared after a mean 5.26
  intervening picks and incurred mean fallback market-rank loss 0.73. Its
  urgent coverage was 8.34%; 33.58% of urgent calls survived.
- The current live conditional modal-hazard approximation was severely
  over-urgent: Brier `0.555425`, log loss `10.08411`, safe coverage 25.11%,
  urgent coverage 64.57%, and false-urgent rate 82.89%. This is diagnostic
  evidence only; no live behavior changed.
- Output: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/wait-reach-final-20260828`.
  Contract hash: `0a31bd84d6a7f88ce04dc2f00096ca1ba09f1ad3c6128958dea0c5579d932c03`.
  Manifest file SHA-256:
  `ab59c38fc540a65bfdd564decb522cb925b8636c60b74ed52db1980606279195`.
  Predictions SHA-256:
  `bcb60bcf63ca1e9788d6aa313f7afca4ffb02b9b271925c738862a3cc257f8e9`.
  Report SHA-256:
  `c7a173d515e859fc415a5ad94a42e19338611979d97bedbb4c077d9972ca316b`.
  `wait_reach_replay.py` SHA-256:
  `01a323324e63317abc5075c5fe58c7ddadb52087803c5beb76c5ece3a2f170ff`.
- The artifact records `seen_validation_diagnostic: true` and
  `locked_test_loaded: false`. It did not query 2025 and is not live-eligible.
- Warning-strict verification passed four focused opponent/replay tests, 68 historical-package tests, and 77 live boundary tests.

### OPP-03 — Correct long-gap player survival pooling

**State:** Rejected. Exact-context keys fixed the elite-player estimate, but
the corrected position model did not pass its frozen overall validation gate.

**Observed defect:**

- The accepted OPP-01 model pooled every gap of ten or more picks and rounds
  one through three into one player cell.
- That broad `rank 2-3 / gap 10+ / RB / early` training cell reported
  `6,088 / 38,290 = 15.90%` survival.
- The exact 2021–2023 context for a rank-2 RB, round 1, gap 18 is
  `7 / 2,006 = 0.349%`.
- The same exact 2024 diagnostic context is `1 / 387 = 0.258%`.
- Therefore, the 15.99% Bijan output is a model aggregation error, not ordinary
  uncertainty. `opponent-final4`, OPP-02 long-gap outputs, and existing TIM-01
  reports must not be used for long-gap player decisions.

**Frozen corrective contract before refitting:**

- Keep the fixed inverse-ADP choice setting, target definition, Beta prior,
  shrinkage strength, feature hashes, train years, and 2024 diagnostic boundary
  unchanged.
- Key player baseline counts by exact integer `(rank, gap, round)`.
- Key player population counts by exact integer
  `(rank, gap, round, position)`.
- Do not change tier-survival keys or gates.
- Keep the existing player gate: at least `0.001` lower 2024 Brier than the
  exact rank/gap/round baseline and an upper draft-clustered paired bound below
  zero.
- Add a regression invariant that the rank-2 RB, round-1, gap-18 training cell
  remains `7 / 2,006` and its shrunk prediction remains below 1%.
- `opponent-final5-20260828` is rejected by this invariant: it predicted 1.55%
  because it still combined ranks 2–3 and shrank toward a prior pooled across
  rounds. It cannot support downstream reports.
- Refit on 2021–2023, rerun the seen-2024 diagnostic, and never query 2025.
- Regenerate OPP-02 and all saved TIM-01 reports. Old artifacts remain
  immutable but are explicitly superseded for player survival.

**OPP-03 result — 2026-08-28:**

- `opponent-final6-20260828` uses exact player rank, gap, round, and position.
- The rank-2 RB, round-1, gap-18 prediction fell from the invalid 15.99% to
  `0.489%`, with exact training support `7 / 2,006 = 0.349%`. The seen-2024
  rate remains `1 / 387 = 0.258%`.
- Overall 2024 player Brier was `0.095891` versus the exact
  rank/gap/round baseline `0.096149`: improvement `0.000257`, paired difference
  `-0.000257 [-0.001195, +0.000768]`. This misses the frozen `0.001`
  improvement and the interval crosses zero.
- Log loss improved from `0.320074` to `0.312949`, but secondary log loss
  cannot rescue the Brier gate.
- The corrected artifact is `rejected`; player survival, OPP-02, and TIM-01
  were not regenerated. No current artifact is eligible for a 2026 timing
  decision.
- Output:
  `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/opponent-final6-20260828`.
  Contract hash:
  `a80036f95a386220b82089c3b0d2417c4d5642db91119ce892aa3ce2675be663`.
  Manifest file SHA-256:
  `5cca9e22df084ae04f0ce3f9eab9c398d409d36112c74fd7c6a7a819cbef8f88`.
  Model SHA-256:
  `2e62d9b94ff40cf343491b22f68016f9919445a511d5b843cb96895016841a1f`.
  Report SHA-256:
  `33c183a939ff8f1090621e649124df7494787024ab66b02bd1cd5ce8d3b9b2e3`.
- The fit queried 2021–2024 only and records `locked_test_loaded: false`.
- Warning-strict verification passed seven focused survival/replay/timing tests, including the permanent rank-2 RB round-1 gap-18 regression, plus 68 historical-package tests and 79 live/timing boundary tests.

### OPP-04 — Continuous monotonic player survival

**State:** Rejected. Both rolling folds passed aggregate policy metrics, but the
fixed additive model failed the frozen elite long-gap regression.

**Frozen contract before fitting:**

- Query only 2021–2023 rolling-market drafts. Use train-2021/validate-2022 and
  train-2021–2022/validate-2023 folds. Do not query 2024 or 2025.
- Keep the OPP survival target and top-ten candidate construction unchanged.
- Fit one aggregated binomial logistic model with fixed features:
  `log1p(market_rank)`, `log1p(exact_gap)`, exact round, position one-hot,
  scoring-format one-hot, and team count.
- Constrain the market-rank coefficient nonnegative and the gap coefficient
  nonpositive. Use L-BFGS-B, L2 `0.001`, maximum 200 iterations, and no
  architecture or hyperparameter search.
- Compare with a Beta(2,2)-smoothed exact `(rank, gap, round)` empirical
  baseline fitted inside each fold.
- Keep policy thresholds fixed at safe `>= 0.70` and urgent `<= 0.30`.
- In both folds, require at least `0.001` lower Brier, at least `0.02` lower
  false-safe rate, no more than `0.10` safe-coverage loss, and a pooled upper
  95% draft-clustered paired Brier bound below zero.
- Preserve the rank-2 RB, round-1, gap-18 regression below 1% with at least
  1,000 training observations.
- A pass produces only an offline `research` artifact trained on 2021–2023.
  It does not authorize 2024/2025 access, TIM-01 regeneration, or live use.


**OPP-04 result — 2026-08-28:**

- Fold one trained on 1,057,250 samples from 657 drafts in 2021 and validated
  on 2,098,920 samples from 1,299 drafts in 2022.
- Fold two trained on 3,156,170 samples from 1,956 drafts in 2021–2022 and
  validated on 3,014,440 samples from 1,878 drafts in 2023.
- Both rolling folds passed aggregate gates. Brier improvement was `0.019284`
  in 2022 and `0.004943` in 2023; false-safe improvement was `0.031779` and
  `0.023562`; safe-coverage loss was `0.028430` and `0.056641`.
- Pooled paired Brier difference was
  `-0.010829 [-0.012063, -0.009705]` across 3,177 validation drafts.
- The fixed additive model predicted `26.63%` survival for the rank-2 RB,
  round-1, gap-18 regression despite 2,006 training observations. It cannot
  represent the required rank-by-gap tail interaction and fails the frozen
  sub-1% invariant.
- The artifact is `rejected`. It did not query 2024 or 2025, and it cannot
  regenerate TIM-01 or affect live behavior.
- Output:
  `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/continuous-survival-final-20260828`.
  Contract hash:
  `1e91e0b2ee001917216d27168eb4d5603649307356ba08bdc23f20fb45b7559a`.
  Manifest file SHA-256:
  `faf90e2c771b249eaf1a941953c13128c7c5174183cbf2c65531539fd4b6e470`.
  Model SHA-256:
  `c06641f54d0c7ac6d8d1ae5fdfdd2e1bd13f11e4b9e4907f0c46ad813b49109c`.
  Report SHA-256:
  `727e1303c9f2a620bf889712f716ef661a04acbbbb073aa22c2dc85fb14391a8`.
- Warning-strict verification passed nine focused survival/replay/timing tests, 71 historical-package tests, and 79 live/timing boundary tests.

### OPP-05 — Supported exact empirical survival lookup

**State:** Passed as an offline `research` lookup with transparent exact rates
and fail-closed support. No live or TIM-01 integration is authorized.

**Frozen contract before materialization:**

- Query only 2021–2023 rolling-market drafts. Use train-2021/validate-2022 and
  train-2021–2022/validate-2023 support/calibration folds. Do not query 2024 or
  2025.
- Key every player cell by exact
  `(market rank, pick gap, round, position, scoring format, team count)`.
- Require at least 250 training observations. Return `unavailable` below that
  threshold; do not interpolate, pool, or fall back to another cell.
- Report raw successes/count, raw rate, Laplace-smoothed Beta(1,1) probability,
  and a 95% Wilson interval.
- Require at least 10% supported validation coverage, supported-cell Brier at
  most `0.15`, and expected calibration error at most `0.05` in both folds.
- Preserve exact rank-2 RB, round-1, gap-18 PPR regression cells: 10-team
  `5 / 696`, 12-team `2 / 1,101`, both supported and smoothed below 1%.
- A pass creates only an offline `research` lookup trained on 2021–2023. It
  does not authorize 2024/2025 access, TIM-01 regeneration, or live use.

**OPP-05 result — 2026-08-28:**

- Materialized 62,684 exact cells from 6,170,610 player observations across
  3,834 training-year drafts. The support-250 gate retains 8,115 cells and
  4,156,593 observations.
- Fold-one coverage was `10.07%`, Brier `0.006563`, and expected calibration
  error `0.000280`. Fold-two coverage was `28.32%`, Brier `0.065135`, and
  expected calibration error `0.043743`. Both frozen gates passed.
- The 10-team PPR rank-2 RB, round-1, gap-18 cell reports `5 / 696 = 0.718%`,
  smoothed probability `0.860%`, and Wilson interval `[0.307%, 1.671%]`.
- The 12-team PPR equivalent reports `2 / 1,101 = 0.182%`, smoothed probability
  `0.272%`, and Wilson interval `[0.050%, 0.660%]`.
- The 10-team half-PPR equivalent has only 49 observations and returns
  `unavailable`; no context fallback is applied.
- The artifact status is `research`. It used 2021–2023 only and records
  `validation_2024_loaded: false` and `locked_test_loaded: false`.
- Output:
  `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/empirical-survival-final-20260828`.
  Contract hash:
  `88f11d19aa4d719b43e1d8258d614f6277e42e94624e1b237f948f2d758f609d`.
  Manifest file SHA-256:
  `cb5029023e7df434040af8284b94b06d6c30fc6cfefdf9e89c78f4e2ea0a99eb`.
  Lookup SHA-256:
  `0e9a68a8057445d852f4ee9a857aeac9183b03690ae3b9d2b5782fc9a077dbd2`.
  Report SHA-256:
  `e94087f39a1b3b0f361742d9fba11c0b6db2bcd31fbaba2ccf48cb8224462f0f`.
- Warning-strict verification passed 11 focused lookup/survival/replay/timing tests, 73 historical-package tests, and 79 live/timing boundary tests.

### TIM-01 — Offline 2026 player timing report

**State:** Suspended. The command remains available, but every existing report uses the superseded broad-gap artifact and must not guide a draft decision.

**Frozen contract before implementation:**

- Load explicit cached league and draft payloads. Make no Sleeper, projection,
  or market network request.
- Use the current cached 2026 market board for availability and the current
  cached 2026 projection world bank for roster-specific marginal value.
- Load only the passed exact-player component from the compliant fixed-parameter
  OPP-01 artifact.
- Require the requested roster to be on the clock in a supported snake or
  linear draft.
- Evaluate the normal candidate pool with default breadth 20. For each current
  candidate, add the player to the roster, inspect the top ten remaining market
  players, and combine their historical survival probabilities with the
  terminal-aligned marginal values.
- Compute one-turn diagnostic route value as current marginal value plus
  expected best next-turn marginal value. The expected-best calculation uses
  an explicit independence approximation over the supported top-ten players.
- For every target, report current value, current 2026 market rank, historical
  return probability in its best alternative branch, expected fallback value,
  take-now route, best wait route, and signed wait delta.
- Do not emit an automatic `TAKE`, `WAIT`, or `REACH` label. Do not call the
  result a recommendation or use it to reorder the live board.
- Write deterministic JSON with exact cache, artifact, market snapshot,
  world-bank, feature-support, and code identities.

**TIM-01 result — 2026-08-28:**

- Added `draft-timing-report`, which loads explicit local league/draft caches,
  cached 2026 players/projections/market data, and the compliant OPP-01
  artifact without network access.
- The report preserves existing roster feasibility and terminal-aligned
  marginal-value semantics. It does not modify VONA, rankings, projection
  inputs, opponent callbacks, or coupled rollouts.
- Each candidate row records projected points, replacement points,
  roster-specific current value, current market rank, take-now route, best
  alternative route, wait delta, historical/market return probabilities,
  support, expected fallback value, and value loss if the target disappears.
- Historical survival is emitted only for the top-ten market region validated
  by OPP-01. Deeper candidates are explicitly `outside_top_ten`; the command
  does not extrapolate.
- A real cached 2026 mock smoke passed at draft `1394035775644913664`, roster
  9, pick 49, with two opponent picks until pick 52. It used 20 deterministic
  worlds over 607 players and market snapshot
  `1f0341577327b9e813908cc0b5a2bbc957c464c4309cb84f1d1403398b5b5b1f`.
- Smoke report: `tmp/timing-1394035775644913664.json`; contract hash
  `724e5db2aa1b643a4289f7f1136fc3ad278e63712b1fe4659ca6586cd61de299`;
  file SHA-256
  `ae93c9f0f38d2f83bc9266fa36fd2c1cde7565e17874b5e613adecff7d3225bd`.
- The output is immutable, self-hashed, labeled `offline_research`, and records
  `decision_active: false`.
- Warning-strict verification passed two focused TIM-01 tests, 68 historical-package tests, and 79 live/timing boundary tests.
- Saved-state verification passed six active caches: two 10-team pre-draft states at pick 1, 10-team states at picks 16 and 49, and 12-team states at picks 24 and 73. A completed 170-pick cache failed closed because no roster was on the clock.
- OPP-03 invalidates the survival fields in all six reports, including the 15.99% Bijan value. Current code fails closed on the superseded artifact version. TIM-01 remains unavailable until a corrected player-survival model passes its frozen gate.

### TIM-02 — Empirical lookup timing integration

**State:** Complete as an offline `research` integration. No decision label or
live behavior was added.

**Frozen contract before implementation:**

- Replace the superseded OPP model input with exact OPP-05 artifact
  `88f11d19aa4d719b43e1d8258d614f6277e42e94624e1b237f948f2d758f609d`.
- Query by exact current branch market rank, picks to next turn, round,
  position, scoring format, and team count.
- Preserve the OPP-05 support-250 rule, Beta(1,1) probability, Wilson interval,
  and `unavailable` result without fallback or interpolation.
- Exclude unavailable cells from expected-next-turn probability aggregation.
  Keep their support state explicit in every candidate row.
- Preserve current cached projection scoring, roster feasibility, candidate
  pool, one-turn route formula, and all input hashes unchanged.
- Decision thresholds: none. Emit no `TAKE`, `WAIT`, `REACH`, recommendation,
  or live rank.
- Offline gate: regenerate the six previously proven 10/12-team saved states;
  preserve completed-state rejection; produce a supported 10-team PPR
  rank-2/round-1/gap-18 estimate of 0.860%; and make no network, 2024, 2025,
  API, UI, VONA, callback, ranking, or rollout change.

**TIM-02 result — 2026-08-28:**

- Cleanly replaced the superseded model input with OPP-05 exact lookup
  `88f11d19aa4d719b43e1d8258d614f6277e42e94624e1b237f948f2d758f609d`.
- Six saved 10/12-team reports completed at picks 1, 16, 24, 49, and 73. A
  completed 170-pick state still failed closed because no roster was on clock.
- The 10-team PPR Bijan branch at pick 1 now reports `5 / 696`, raw `0.718%`,
  smoothed `0.860%`, interval `[0.307%, 1.671%]`, and support status
  `available`.
- Unsupported cells return null probability/rate/interval and zero support.
  Routes with no supported next-turn cells now return null instead of treating
  unavailable players as zero-value outcomes.
- Report support varied by saved state: 10 of 21 candidates at both 10-team
  pick-1 states, 6 of 24 at pick 16, 5 of 26 at pick 49, 0 of 21 at the
  12-team pick-24 state, and 7 of 23 at the 12-team pick-73 state.
- Reports:
  - `tmp/timing3-1393628519644286976.json` —
    `622a27c2d7a8ce3042ae912a18fea50cb5aa0db79c830976aeca01c3a739cefc`.
  - `tmp/timing3-1393721396240080896.json` —
    `d7a95463d3d298fb14f83d84aaf26dc57b770cbcc0278f4068a2cee50d1eb8b1`.
  - `tmp/timing3-1393746402558881792.json` —
    `31f43ec4bbc809e4c8cb7d1f4d48cd9af271f6026dab591e4dfbf0704387867a`.
  - `tmp/timing3-1394035775644913664.json` —
    `a5b0f39f0e6fbf946973263c3de833ccbf92079d3ce462fa9853fa3d6471b8f7`.
  - `tmp/timing3-1393634461312106496.json` —
    `449ba77015e3519361ef8a2c1ff4705a2cdc55413ea09240f3bc43f72d2d6b01`.
  - `tmp/timing3-1393656492011315200.json` —
    `aa5da7f71ecb76aa723172eb25109f35adcb674203ff67e137c13c2095523357`.
- Reports are version `offline-2026-player-timing-v2`, self-hashed,
  `decision_active: false`, and record code SHA-256
  `74f6838c4ae79d2a46e2b9651d823b1a5e7f57aa3c5f1d8431251c537514acf1`.
- The command made no network request and did not query 2024 or 2025. It did
  not change API/UI behavior, VONA, rankings, callbacks, or rollouts.
- Warning-strict verification passed 12 focused lookup/survival/replay/timing tests, 73 historical-package tests, and 80 live/timing boundary tests.

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

Phase 1 is complete. Phase 2 now has append-only manual and official FantasyPros multi-platform market snapshots behind a 12-hour request-driven freshness gate, separate target/base context reporting, exact-team-count preference, an explicit unchanged generic fallback, and a versioned inverse-ADP Sleeper choice baseline. Its backtest rejects snapshots retrieved after a draft begins. Phase 3 has market-independent descriptive profiles for every member of the real attached league. Phase 4 has exact league and standalone-mock attachment, explicit compatibility, network-free replay, coupled complete redraft rollouts, and survival summaries. Phase 6 produces deterministic, content-versioned, full-pool player-week tensors independently of fantasy ownership. Phase 7 evaluates compact roster assignments with coupled schedules/streamers and immutable per-world results. Phase 8 joins many draft continuations to paired season worlds and emits versioned numeric recommendation summaries. The next product step is completing the attached mock's live replay followed by market-baseline calibration; do not calculate plausible-window passes, board adherence, calibrated personalization, or market-relative action labels without validated time-local evidence.

## Last updated

2026-08-30 — Replaced the falloff's deterministic ADP-threshold lookahead with survival-weighted expected best (projection board v3), answering the owner's "cost to wait against the very next pick, or value left on the board?" question with the principled middle: values stay marginal and seat-aware (an aggregate remaining-value sum double-counts players you cannot roster), but each future turn now prices the EXPECTATION over who lasts instead of the single ADP-threshold survivor, and the headline `take_now_edge` is the cost of optimal deferral (best now minus the best expected future turn). Survival comes from a new mean-field without-replacement propagation (`_future_turn_survival`): at every intervening pick the ADR-019 sharp+reach market mixture removes exactly one player in expectation via unconditional pick mass `s_i x w_i / sum s w` per component, clamped at each player's availability and renormalized — no sampled path, no argmax conditioning, no conditional-probability double-discounting. Three candidate updates were benchmarked against exact without-replacement enumeration before implementation; the shipped renormalized form conserves one pick per step exactly with max survival error 0.12 and expected-best within ~4% (conservative) on adversarially sharp boards, and a unit test pins the enumeration comparison and conservation. Payload: `availability_model: market_mixture_mean_field_survival`, new `survival_model`, per-turn `survival_probability`/`probability_best`, `edge_vs_next_turn` renamed `edge_vs_waiting`; the UI shows each wait target's chance of lasting and the copy names expectations instead of ADP order. Replayed live pick-72 state: WR is the scarce position (edge 2.2), K waiting costs 1.5 (Aubrey 57% survival at 96, expected K value 8.05), and DEF collapses into "No cost to wait" at 99% survival. Validation: full Python suite 259/259, frontend 64/64, production build clean. The one-turn route-value plan and the authoritative terminal simulation ranking are unchanged.

2026-08-30 — Fixed the round-7 K/DEF domination at its root in the value basis (ADR-048, `ROSTER_VALUE_VERSION` 6), owner-directed after the recorded pick-72 finding. `flat_season_scores` now credits streamer coverage: in worlds where a rostered player misses an otherwise-playable week, the week scores `mean + (1 - played_share) x position cutline` — what the per-world `_evaluate` lineup already does with bench/waiver streamers — so cross-world injury risk discounts a player's edge over the streamer instead of his whole score. The cutline stays on the healthy `expected_scores` basis: measured across the 300-world bank, healthy conditional world means match `expected_scores` within sampling noise (position mean ratios 0.991-1.000), so no cutline-basis change is justified. Replayed pick-72 evidence: Warren 0.0 -> +8.8, Pierce +18.7, Harrison +16.5, Purdy +14.7, Caleb +13.8; K/DEF fall from the top five values to honest mid-board (LAR +10.9, Aubrey +9.6); policy matches exact scorer deltas with only the pre-existing POL-02 bye-complement band (max 1.21 = one bye week x the flex-TE cutline gap). Validation: new coverage unit test, all ADR-046 offset and cached/uncached equivalence tests unchanged, full suite 257/257, and synthetic smoke batch `20260830T235016-9d48e23e` (2/2 twelve-team drafts, zero errors, DEF rounds 14-15, K round 8, mixed RB/WR benches); a five-draft batch or the frozen-corpus decision-impact replay remains the release-grade behavioral gate. The smoke run exposed and fixed a broken-since-2026-08-27 harness defect: ADR-037's `recommendation_mode` dataclass field shifted `LiveDraftMonitor`'s positional order, so synthetic sessions crashed at the first telemetry write (`'str' object has no attribute 'record'`); the constructor call is now keyword-based and the mocked regression test asserts the keyword contract. The owner's live monitor session on the real draft (started 23:58 UTC) still runs pre-fix code; the owner chooses when to restart `ffsim serve` and re-prepare (safe between picks in the slow draft).

2026-08-30 — Reworked the overall-table heading help twice at owner request, landing on an above-anchored bubble. The first attempt swapped the section subtitle for the help text, but the owner reported flashing: the swap changed the header height under the cursor, shifting the table and re-triggering hover — a feedback loop. Final form: the persistent subtitle ("Top 40 across positions · sorted by X · hover a heading for its meaning") never changes; hovering or focusing a heading (or the WORP header) renders a help bubble ABOVE the table — an out-of-flow `position: absolute` card anchored to a new `.projection-table-anchor` wrapper that is a sibling of the `overflow: auto` scroll wrap, so nothing clips it, and `pointer-events: none` plus zero layout shift eliminate the flicker (`.projection-overall` overrides the section's `overflow: hidden` so the bubble may extend upward). `data-help` stays on the header cells as the accessible source; the bubble has `role="status"`. Verified: frontend test hovers VORP (bubble appears, subtitle unchanged) and leaves (bubble removed, subtitle unchanged); 63/63 tests and the production build pass.

2026-08-30 — Fixed the owner's pick-72 projection-board absurdity ("who tf is Brayden Willis") at its root in the terminal scorer (ADR-047, `ROSTER_VALUE_VERSION` 5, VONA tag `next-turn-vona-v3:terminal-marginal-flex-streamer`). Reproduced the live state bit-exactly offline (same world-bank version `c56c1800…`, offsets hash, mock draft, and 71 picks; 534 board rows matched the running server with max difference 0.0), then proved the inversion with exact scorer deltas: adding Willis (TE101, 10.4 points, 8 available weeks) scored -8.44 while Likely/Kittle/Kelce scored -18.09, because the greedy lineup force-seated any added TE in the open flex at his TE-cutline floor (10.03/week) below the flex streamer (11.24/week), a loss that scales with available weeks — so the least-available player ranked best. Flex seats now include the streamer option in the deterministic scorer (`seat_floors` in `_lineup_totals`; `_evaluate` unchanged), and the future-user policy mirrors it in `_seat_summary`/`_terminal_marginal`/`_roster_feasible_values`. `position_caps` was audited and is NOT the K/DEF bug: it caps K/DEF at their one slot and only ever excludes players. After the fix the replayed board has no negative marginal, Willis prices 0.0, and the best-now TE is a startable TE. New scorer and parity regressions plus the full 256-test Python suite pass. Activation requires a backend restart and re-preparation.

2026-08-30 — Recorded (not yet fixed) the second measured defect behind the round-7 K/DEF domination: the value basis and its cutline are on different availability bases. `flat_season_scores` dilutes each flat by cross-world injury availability (mean over ALL worlds, zeros where out) while `_starter_cutline_replacement` uses healthy `expected_scores`; the ~4-17% dilution exceeds nearly every mid-round skill edge, so flats floor to exactly the cutline and whole positions price 0.0 (measured at pick 72: Warren, board RB1, VORP +12.8, `starter_points` 179.3 = 16 x 11.206 exactly floored, value 0.0; Likely/Kittle/Kelce likewise 0.0), while injury-free K/DEF keep full value (Aubrey +9.56, LAR +10.9) and hold the top of every mid-draft board. Candidate fix, pending an explicit objective decision and validation: streamer-coverage crediting — in worlds where a rostered starter misses an otherwise-playable week, credit his seat at the position cutline (what the per-world `_evaluate` lineup already does with bench/waiver streamers), so availability discounts the edge over the streamer instead of the whole score. Hand-decomposed on the replayed state this restores Kittle ~+14.7, Harrison ~+6.5, Dart ~+5.6 while K/DEF are unchanged; players whose bank healthy mean sits below the expected-basis cutline (Warren, -0.05/week) stay 0.0 — a residual third-basis gap (bank world means versus `expected_scores`) that any redesign must also address. This changes ADR-026 terminal-objective behavior and must ship as its own ADR with before/after evidence (recommended gate: decision-impact replay on the frozen multi-state corpus), not ride along with ADR-047.

2026-08-30 — Added an owner-requested forced FantasyPros refresh for tonight's draft, plus the falloff horizon-copy nit. Setup form: a new "Pull the latest FantasyPros data" checkbox posts `force_refresh: true` with the prepare request; the help text states it ignores the 12-hour cache and downloads base projections and ADP before boosts and calculations apply. Plumbing: `DraftPrepareRequest.force_refresh` (default false) → `prepare_draft(force_refresh=)` → `PlayerLoader.refresh_if_stale(force=)` and `refresh_fantasypros_adp(force=)`, which fetches every context regardless of TTL freshness; the separate `/api/draft-intel/history/refresh` path is unchanged. Falloff copy: the card edge now reads "18.4 · roster value lost if you wait until pick 24 · seats", naming both the metric and the horizon. Verified with bare runs: full Python suite 253 passed + 683 subtests (new force-fetch market test, prepare-forwarding API test), frontend 63/63 (checkbox POST-body test, horizon-copy test), production build clean. The supervised `ffsim-api` process was restarted onto the new code and reports ready, so the flag is live for tonight.

2026-08-30 — Third falloff clarity pass after an owner screenshot showed the section still confusing late-draft: five cards, four reading "+0.0 lost if you wait", repeated zero-value turn rows, and per-turn numbers clipping at the card edge. Changes: (1) zero-cost positions (edge < 0.05) no longer render cards — they collapse into one "No cost to wait:" strip with badge, best-now player, and points, so cards only appear where waiting actually loses value; (2) the card edge is unsigned and names its horizon ("18.4" + "lost if you wait until pick 19 · 2 seats open"), and each turn row names its metrics on a second line — "roster value 63.6 · down 18.4" — with the direction clause omitted below 0.05 so "−0.0" noise disappears; (3) the section explanation is concrete ("If you skip a position now, the model expects a weaker best option at your next pick. The red number is the roster value that wait costs."); (4) `.falloff-turns li` moved from flex to a two-line `auto minmax(0,1fr)` grid so long names truncate and the labeled numbers get their own line instead of clipping at the card edge. Verified: PositionOutlook tests cover the safe strip (zero-edge K collapses; costly RB/QB stay cards), the labeled turn-row format, the horizon wording, and unsigned card edges; direct `npm test` (63/63) and `npm run build` pass.

2026-08-30 — Follow-up UX pass on the projection board at owner request. (1) Header help now renders as an instant CSS tooltip: the sortable overall-table headings moved their ASD-STE100 explanations from the slow native `title` attribute to `data-help` on the header cell, shown as a styled card under the sticky header on hover or keyboard focus (the sticky `th` is the positioned containing block; `position: relative` was deliberately not added because it would override sticky at higher specificity and un-pin the header). (2) "Value & roster fit" is now the default projection-board view (ADR-045 amended); "Points only" stays one click away. (3) The confusing positional-falloff section was rewritten in plain language: heading "Cost of waiting — by position", a one-sentence explanation of the cards, edge label "lost if you wait", "Best now: … roster value", per-turn rows "value · −drop vs now", a market-view footnote, and the metric glossary entry renamed "Cost of waiting (positional falloff)". Verified: updated PositionOutlook and DraftIntel tests cover the new copy, the value default, and the `data-help` attributes; direct `npm test` (63/63) and `npm run build` pass. Limitation: browser hover placement of the CSS tooltip was not visually verified — the headless probe timed out twice and was abandoned; placement rests on the sticky-th containing-block analysis.

2026-08-30 — Added the owner-requested flat cross-position ranking to the projection board's "Value & roster fit" view ("hard to see who the next best pick would be without going into the positions specifically"), then made its metric headings clickable sorts with hover help at the owner's follow-ups. The "Overall · next best pick" table (accessible region name `Overall ranking`) renders above the per-position tables: top 40 remaining players across positions with an overall Rank column (1, 2, …), sorted by roster value by default. Clicking Projected, VORP, Roster value, or ADP re-sorts by that metric — ADP ascends in market order, the rest descend, `aria-sort` marks the active column, and the header notes the active sort; each sortable heading carries an ASD-STE100 explanation via `data-help` CSS tooltips (initially the native `title` attribute, replaced the same day — see the tooltip entry above), and the WORP column (shown only when validated) stays non-interactive with its own hover help. After the clicked metric, the fixed roster-value/VORP/projected/ADP/player-ID chain keeps every ordering deterministic through the 0.0-roster-value tail. Columns match the position tables plus an inline position badge; the table respects the shared All/Skill filters and hides when a single-position chip is active. Display-only reuse of existing `projection_board.players` fields — no API, model, or ranking change. Verified: the extended value-view frontend test asserts the default roster-value order, re-sorting by Projected/ADP (QB first) and back to Roster value (RB first), the VORP/ADP hover-help text, the third VORP header, and the single-position hide; direct `npm test` (63/63) and `npm run build` pass.

2026-08-30 — Fixed the owner's MacBook-viewport container overflow ("next pick lists are out of their box") with three CSS containment rules in `web/src/styles.css`. (1) The falloff "Targets and later turns" table's nowrap cells forced a ~380px minimum width past its ~320px card; it now uses `table-layout: fixed` (name column 38%, ellipsized cells, wrapping headers). (2) `.timing-card li span` (QB/TE market-timing rows) gained `min-width: 0` so long player strings stop pushing the nowrap drop label outside the card. (3) `.draft-rail > *` gained the `min-width: 0` grid-item guard its sibling grids already had. Verified: 63/63 frontend tests, clean production build, and a headless-Chromium static probe of the built stylesheet at 1512×982 showing both fixed containers contained at a 250px track — at or below every real track minimum (`minmax(250px,1fr)` falloff, `minmax(280px,1fr)` timing), which bounds the 1280-wide case where the rail still renders. Limitation: the full live-state dashboard composition was not browser-rendered at 1280×800/1440×900.

2026-08-30 — Centralized the ADR-046 offset transforms at owner request ("the offset should only be applied to the player's season-long projected points"). Two helpers now hold the whole rule: `LeagueEvaluator.adjusted_flat_season_scores(personal_values)` (pre-floor shift by `offset / available weeks`, identical cutline floor, memoized per offset board, no-offset players bit-identical; replaces the one-day `flat_season_scores_raw` accessor) feeds both the future-user policy and the scorer's preference path, and `personal_ranks.adjusted_projection` (`base + offset`) feeds the policy's projection map and the board's points/VORP/WORP display. `live_candidate_pool` keeps its raw-basis market head and inline entrant ordering per ADR-046 — deliberately untouched. Behavior is unchanged; the pick-25 harness reproduces the identical decomposition and the full suite passes (341 + 691 subtests).

2026-08-30 — Fixed the future-user policy's boost over-credit the owner hit live at pick 25 (Ferguson TE17 proposed over Loveland). `next_turn_user_policy` summed the FLOORED flat scores and then added the offset, so every sub-cutline player's roster value equaled his offset at 100% pass-through, while the terminal scorer shifts pre-floor raw flats and re-floors. Decomposition on the replayed pick-25 mock state (23 feed picks + Nabers at 24, 300-world bank, TE season cutline 170.5, 16 available weeks × 10.028 weekly cut = 160.4): Ferguson raw 111.8 → floored 160.4 → old value 30.0 (== his +30); Likely 130.3 → 20.0; Pitts 145.3 → 10.0; Loveland raw 189.5 → 29.1. After the fix the policy shifts `flat_season_scores_raw` by `offset / available weeks` and re-floors (new `LeagueEvaluator.flat_season_scores_raw` accessor): Ferguson/Likely/Pitts value 0.0 — exactly the scorer's `projected_roster_value(..., personal_values)` marginals — and Loveland (29.08) outranks them in policy `current_values` and the board's TE plan (leader Trey McBride, 56.0). No-offset players are bit-identical; the bare-evaluator fallback path is unchanged. Audited the other offset consumers: board Roster value/route plans consume the policy (fixed transitively); board VORP/WORP display and `live_candidate_pool` value entrants are raw-basis by design, not floored — no defect. New policy regression `tests/test_vona.py::test_sub_cutline_offsets_cannot_pass_the_floor`; existing +50-starter, bench-passthrough, and policy-shift tests pass unchanged; full suite 341 passed + 691 subtests. ADR-046 amended with the corrected pre-floor semantics.

2026-08-30 — Replaced the full-credit preference sum with a lineup-consistent utility after review correctly rejected the "cannot materially distort" claim. Measurement on the owner's real pick-24 mock state (23 replayed picks, 300-world bank, 60 coupled rollouts, his 93 stored offsets): completed user rosters accumulated 150–180 offset points with a 35-point cross-candidate spread, and full-weight crediting over-stated bench/sub-floor boosts ~3× (corrected candidate shifts +48.9/+44.8/+15.2 for Nabers/Olave/Rice versus sums of +167/+182/+152). Fix: `LeagueEvaluator.projected_roster_value` accepts `personal_values` and rescoring shifts each rostered player's pre-floor flat weekly scores by offset/available-weeks, then applies the identical cutline floor, raw seating order, bench discount, and streamer baseline; `evaluate_candidates` now uses this adjusted scorer per continuation instead of `raw + Σ offsets`, so a starter boost passes through fully, a bench boost earns the bench-asset fraction, and a sub-cutline boost that cannot clear the floor earns nothing — exactly matching the future-user policy's floored values (ADR-031 alignment preserved; raw metrics and bank untouched; `_mean_scores_raw` cached alongside the floored flats and initialized in `__init__`). Corrected ranking on the live state: Nabers 302.7 > Olave 299.4 > Rice 284.6 (raw leader was Rice). ADR-046 rewritten accordingly. New bench-passthrough decision test (+40 sub-cutline → exactly zero shift; floor-clearing boost < full credit); the +50 starter pass-through test still holds; full suites pass (340 Python, 63 frontend).

2026-08-30 — Resolved the owner's live falloff confusion ("why Rashee Rice over Malik/Zay/Olave") and a real mixed-basis display bug. The falloff card had picked Rice correctly on raw market value (48.2 before the owner's −25 fade; Nabers' 61.1 board value includes his +25 boost) but displayed boost-adjusted points ("243 pts") beside raw values in one line. Falloff rows (headline, per-turn targets, top players) now display raw projected points and carry `personal_offset`, and the UI renders the boost/fade chip beside every falloff name, so a faded market target reads as "Rashee Rice ⟨−25⟩ · raw pts" instead of contradicting the personal board. Glossary "Roster value" entry corrected per review: 0.0 now reads "no value above streaming after availability and your adjustment," covering fades that floor small positives to zero (verified live: Irving 1.9−5→0, DeVonta 3.6−10→0, while Maye/Lamar/Kittle are genuinely sub-cutline in a 1-QB league where the weekly cutline is QB13). Regression test extended to pin raw falloff points plus the separated offset field; full suites pass (339 Python, 63 frontend, tsc, production build).

2026-08-30 — Fixed the between-pick refresh/lag the owner hit live ("page refreshes on picks, registers my pick 5–10 s late"). Measured causes: (1) the monitor cleared `projection_board` on every state change and the UI unmounted the whole Live board tab until the replacement published — the visible flash; (2) the frontend replaced the entire monitor object every 500 ms because `last_sync_at`/`sync_count` always change, re-rendering the ~600-row board tables twice a second — the jank that made pick registration feel seconds late (board compute itself measured 10 ms against the real 300-world bank; preliminary equity 0.42 s, so in-process calc work compounds but was not primary). Fixes: the monitor keeps the last board across state changes (the new one lands ~10 ms later in the same iteration); the frontend stabilizes poll payloads — unchanged sections (state, recommendation, board, equity, shadow, progress) reuse their previous object references via serialized comparison, clock-only polls skip the state update entirely, the sync clock moved to its own state, and `ProjectionBoard`/`PositionOutlook` are memoized so they re-render only on real changes; the Live board shows a small gold "updating for pick N" chip instead of unmounting when its pick lags the room. New frontend regression test proves a stale-pick board stays mounted with the chip; 63 frontend tests, tsc, production build, and the full 339-test Python suite pass. Owner must restart `ffsim serve` and hard-refresh.

2026-08-30 — Second UX pass, focused on the first-run flow and loop closure. The empty draft-setup screen now opens with a three-step strip (1 "Set your boosts" — a link that switches to the My ranks tab, wired via a new `onOpenRanks` prop from App; 2 "Prepare draft · ~1–2 min · projections, worlds, your boosts"; 3 "Start monitoring"), shown only before preparation. The post-prepare readiness grid gained a "Your boosts" cell fed by the preparation summary's `personal_ranks.players` (new field in the `DraftPreparation` type), so the owner can confirm his board actually loaded. My ranks header now reads "93 rated · 53 boosts · 40 fades" (was a bare rated count) and Escape clears the player search. Verified: setup strip renders and its boosts link navigates to My ranks in headless Chromium against the live backend; tsc clean, 62 frontend tests (new assertions for the strip and navigation, updated count-copy assertions), production build clean.

2026-08-30 — Fixed the "small screen" complaint: the UI used fixed pixel type (15/16px), so large monitors rendered a tiny dashboard. The root font now scales with the viewport (`html { font-size: clamp(15px, 12px + 0.3vw, 19px) }` — ~16.3px at 1440w, ~17.8px at 1920w, 19px from ~2330w), the body font moved to rem so everything rem-sized scales together, and `.shell` gained a 2400px ultrawide reading cap with centered margins. Verified in headless Chromium at 2560×1400 (root 19px, proportionally larger throughout, no overflow) and 1440×900 (16.3px, layout unchanged, no horizontal overflow); tsc, 62 frontend tests, and the production build pass.

2026-08-30 — UX clarity pass at owner request; net inline copy shrank while the metric glossary became the single explanation home. Consistent vocabulary: personal offsets are "boosts" (+, gold) and "fades" (−, violet) everywhere. A compact BoostChip now marks every number that already includes an offset (both projection-board tables and simulation candidate rows, which also show a small "yours <preference value>" when it differs from the raw ranking value); the Points callout switches to "Your projected points · FantasyPros baseline + your adjustments" only when boosted rows are visible. Market views that deliberately ignore boosts (positional falloff, driven by `value_basis: raw_projection`, and the renamed "When to draft QB / TE · market timing" cards) carry one "market view · ignores boosts" chip instead of paragraphs. Jargon cuts: "Fast projection route" → "Best pick by projections" with a plain route sentence; five dense footnotes reduced to one-line state with their definitions moved into the glossary (new "Your boosts" entry names exactly where offsets do and do not apply); the redundant contenders hint merged into the screened-section label. My Ranks: duplicate "my call" column removed (single sign-tinted badge), buttons renamed Boost/Fade, picker hints "← fade / boost →", and saves during monitoring surface "Saved — applies after next draft prep" from the API `applied` field. api.ts types gained personal_offset/preference_adjusted_value/value_basis/applied. Verified: tsc clean, 62 frontend tests pass, production build clean, and headless-browser review of the My Ranks tab against the owner's real 93-offset board (an accidental test click on Bijan was reverted to unrated).

2026-08-30 — Fixed the offset/board incoherence the owner hit mid-mock (boosted dart throws dominating positional falloff with all-zero drops, raw points shown beside adjusted values). Boundaries now (ADR-046 amended): the projection board displays personal numbers — `projected_points`, VORP, and WORP in both Points and Value tables are `base projection + offset` against the raw replacement baseline, `personal_offset` on every row, and board current/route values come from the personalized policy, whose internal projection map (seating, candidate selection, tiebreaks) is also adjusted per the same convention. The positional falloff / cost-of-waiting diagnostic and QB/TE timing outlook deliberately stay on a separate raw-projection policy (`position_outlook.value_basis: "raw_projection"`): cost of waiting measures market scarcity, so a +30 on a late dart throw can no longer become the positional target or flatten drops to zero. New regression test proves adjusted board points/resort plus byte-identical falloff targets and edges versus the raw board; full suite 339 Python tests pass. Owner must restart `ffsim serve` and re-prepare to pick up the fix.

2026-08-30 — Reworked personal rankings to season-point semantics after owner clarification, superseding the same-day pick-space slice (ADR-046 rewritten). Offsets (±5…±50 points, 0 clears; positive = like/more points) persist in `data/cache/draft_intel/personal_ranks.json` keyed by Sleeper ID via `GET/POST /api/personal-ranks` and the "My ranks" tab (368-player cached ADP board, immediate save, point-semantics copy). Integration is user-side and counted exactly once per player: the future-user policy applies `base projection + offset` before the cutline floor (replacement levels, seating, and the shared `SeasonWorldBank` stay raw); `evaluate_candidates` computes a per-continuation preference-adjusted utility (raw roster value + offsets of the user's completed roster) that drives `rank_candidates`, co-leader/toss-up detection via `paired_preference_delta`, and the recommendation, while raw `projected_roster_value` metrics remain untouched for telemetry; candidate-pool value entrants rank by `projection + offset` (market-ADP head unchanged); the live draft model version gains a `:ranks<hash>` suffix so evaluation identity and rollout-range merges cannot mix boards. Prepare-time load with atomic idle hot-swap; an active monitor keeps its immutable board (`applied: live | next_prepare`). Validated: decision test flips the leader with +50 and shows the utility shifts by exactly the offset with raw metrics identical and exact range merges; policy test flips the simulated future pick; pool test promotes value entrants only; API round-trip and live browser save verified. Full suite 338 Python + 61 frontend tests pass with clean tsc.

2026-08-30 — Clarity pass on the live War Room after owner feedback that the combined view was confusing. The live view now has two owner-switched sub-tabs under one shared position filter: "Live board" (pure projection math — falloff cards and the projection board, noted as updating after every synced pick including other managers') and "Simulation advice" (contenders, Why panel, with the championship odds and experimental evidence shown only in this view; the tab gains a ✓ when advice is final). Panels stay mounted and toggle with `hidden`, so nothing shifts on data arrival and the command strip keeps the one-line answer visible in both views. Plain-language renames: "Screened watchlist" → "More candidates · rough early estimates" (rows say "rough est."), board views → "Points only" / "Value & roster fit", alpha panel → "Return odds · experimental" with chip "Evidence only — never changes the pick"; run/seed/engine/world/model identifiers moved into a collapsed "Run details" disclosure. Separately confirmed the owner's own 13:54 server already runs the new backend (managers endpoint live, `position_outlook` present, simulation mode), so every-pick board updates are active — the perceived staleness was the draft waiting on the owner's own pick; a supervised duplicate server failed to bind on 8000 and was left stopped without touching the owner's process. Verified both sub-tabs against the live backend with real pick-25 data (falloff leader Rashee Rice +37.8, simulation final suggestion Rashee Rice +4.9 vs next, zero console errors, no overflow at 1440 or 390); 56 frontend tests (four assertions updated for renames), tsc, production build, and React Doctor (pre-existing findings only) pass.

2026-08-30 — Superseded note for the two entries below: their "activation requires a backend restart" caveats are resolved. The owner's own `ffsim serve` process (started 13:54) was probed and runs the new code — `GET /api/draft-intel/managers` returns 200 and the monitor payload carries `position_outlook` with `recommendation_mode: simulation`. The every-pick off-clock board refresh is therefore deployed on the running server; that specific behavior is proven by the backend unit tests (opponent-state and completed-state board regressions), and has not yet been observed against a live opponent pick because the draft has been waiting on the owner's own pick throughout the session.

2026-08-30 — Added a positional falloff analysis ("cost of waiting") to the projection board at owner request. For every position, `projection_value_board` now reports the first-seat marginal roster value of the best available player now versus the deterministically selected best remaining player (ADP-threshold, not a probability-weighted expectation) at each of the user's actual future turns, using the existing live reach cushion (ADR-019) and the flex- and bench-aware current-roster scorer. The payload declares its assumptions (`availability_model`, `roster_assumption`, `edge_basis: first_marginal_seat`, `reach_rate`, the exact future turn picks) and flex-aware demand per position (`open_dedicated_slots`, `eligible_open_flex_slots` marked shared, `remaining_starting_opportunities`); positions are ordered purely by computed take-now edge — no strategy is hardcoded, so patterns like early double-RB emerge from the math only when the falloff supports them. Top-five per-position targets carry each player's marginal value and edge versus the next turn. The UI renders sorted falloff cards above the projection board, respects the shared Skill/position filter, shows positive waiting costs as positive numbers (a sign-rendering bug caught in review was fixed with a regression test), and states that the analysis is not a survival probability and stays subordinate to the terminal simulation. Validation: 232 Python tests (new falloff identities: drops equal best-now minus turn value, edges match first-turn drops, ordering is descending, no-flex leagues report zero shared flex seats), 56 frontend tests, tsc, production build, and React Doctor (pre-existing findings only). The browser layout check rendered a fixture `position_outlook` injected over the running app because no prepared monitor exists on a new-code server yet; no console errors or overflow. Activation still requires the backend restart noted in the concurrent-engines entry.

2026-08-30 — Added a League scouting tab so the Phase 3 manager-history work is usable during a real draft. New read-only `GET /api/draft-intel/managers` joins the attached league snapshot (users, rosters, draft order) with `summarize_manager_profiles` for the target context and caches per league/draft; the response marks managers without eligible history as population-model-only and carries `MANAGER_PROFILE_MODEL_STATUS` (descriptive only, not decision-eligible). The tab renders per-manager cards in draft-slot order: history depth (drafts, picks, context weight — no confidence labels), first-QB/first-TE typical round with selected/draft counts, four-round start style (Zero-RB/Hero-RB/RB-heavy plus WR-heavy counts), and most-drafted positions; the component fetches only when the tab is opened. Verified against the real league data through a second server instance running the new code (12 managers, 2,265 historical picks, correct slot order) with no console errors or overflow; 232 Python tests (new endpoint join test), 54 frontend tests (new component test), tsc, and the production build pass.

2026-08-30 — Reorganized the War Room around concurrent engines at owner request. Backend: `projection_value_board` now publishes after every synchronized pick, including opponent picks — remaining-pool tables (points, VORP, WORP, roster value, ADP) update off the clock while the pick-anchored current-turn plan and route values still publish only on the user's clock; a completed pick sheet returns None cleanly, and the off-clock next-turn anchor was corrected (the current opponent pick now counts as the intervening opponent). The monitor's `recommendation_mode` API contract is unchanged. Frontend: the engine selector is gone — monitoring always starts the simulation engine, which runs in the background with its staged progress while the projection board displays immediately; the live view is organized into labeled sections ("Pick advice · full simulation" and "Live board · projections"), a shared position filter with a new Skill (RB/WR/TE) toggle governs both boards, a collapsible "What the metrics mean" glossary defines projected roster value, title/playoff odds, VORP, WORP, VONA-style opportunity/urgency, route value, ADP, and next-turn availability using existing verified copy, UI polling tightened from 1s to 500ms (backend poll interval unchanged at 1s), and the shell is now full-width. Validation: 231 Python tests plus new off-clock/completed-state board regressions, 53 frontend tests (three updated for the removed selector and glossary), tsc, production build, and React Doctor (only pre-existing findings). Browser-verified at 1440 and 390 widths with fixtures for the concurrent refining state and against the real running backend for compatibility; no console errors or overflow. The running backend process still executes the old board gate — restart `ffsim serve` and re-prepare after the current live draft to activate every-pick projection updates.

2026-08-30 — Superseded note for the entry below: the engine selector, its lock notice, and the command-strip engine label were removed later the same day when the UI moved to concurrent engines (see the concurrent-engines entry above). The "Board view" labeling of the projection toggle remains.

2026-08-30 — Made the two recommendation engines legible in the UI after the owner could not tell them apart during a live draft. The command strip now names the active engine ("Full simulation · rest-of-draft evaluation" or "Projection lookahead · no simulation") during monitoring; the setup selector shows permanent side-by-side descriptions for both engines with `aria-pressed` state and a gold lock notice explaining that the engine is fixed while monitoring runs; the projection board's Projected points / Full value switch is now labeled "Board view" so it cannot be mistaken for the engine selector. Verified against the live in-progress draft (pick 25, projection mode) in headless Chromium with no console errors; 53 frontend tests, tsc, and the production build pass.

2026-08-30 — Overhauled the frontend palette from navy to a warm charcoal-leather scheme at owner request: warm near-black surfaces, chalk-white text, unchanged FFSim gold as the sole brand accent, bronze data bars replacing steel blue, and a muted violet reserved for the experimental alpha-shadow panel. Position-badge and race-board hues (semantic per-position and per-team colors) are unchanged. All CSS token mirrors (shadcn variables) were remapped; no blue literals remain in the stylesheet. Verified in headless Chromium at 1440 and 390 widths (setup against the real backend, live board against injected fixtures) with no console errors or overflow; 53 frontend tests and the production build pass. The stopped backend was restarted as a persistent supervised process.

2026-08-30 — Rebuilt the War Room frontend as a full-width desktop dashboard without changing any API contract or model behavior. A sticky app bar carries the league, tool navigation, and league switching; the live view leads with a command strip that shows the current pick, on-the-clock state, sync freshness, and the primary recommendation (name, position, projected roster value, edge versus next, final/refining state), which stays visible during refinement and position filtering. Candidate rows gained a column header, one merged telemetry line (title/playoffs/wins/ADP), and a collapsed opportunity-evidence disclosure; championship odds, the subordinate alpha shadow, and the pick feed moved to a right rail. Geometry is square throughout, decorative gradients are flattened (a faint yard-line background texture remains), JetBrains Mono renders all tabular numerics, and setup collapses into a summary once monitoring starts. Verification, all through the Vite dev server in a real headless Chromium: against the real running backend — startup, offline banner with retry, draft-setup form, league-picker search against the live Sleeper API including its empty-result and cancel paths, and the season-simulator tab, with zero console errors and a visible keyboard focus ring; against API fixtures injected into the page (no live draft was running) — the on-clock ready board with rail, refining pipeline with persistent recommendation, and projection mode, at 1440/1280/768/390 widths with no horizontal overflow. 53 frontend tests, tsc, and the production build pass; one filter test was updated for the intentionally persistent command-strip recommendation. React Doctor reports only pre-existing findings (DraftIntel component size, prop-sync effect, LeaguePicker state cluster). Remaining limitation: live on-clock behavior has not yet been observed against a real Sleeper mock draft.

2026-08-28 — Completed TIM-02 as an offline integration of the passed OPP-05 exact lookup. Six saved 10/12-team reports regenerated with exact probabilities, raw rates, Wilson intervals, and fail-closed support. The 10-team PPR Bijan branch now reports 5/696, smoothed 0.860%. A 12-team pick-24 state with no supported cells emits null routes instead of false zero-value assumptions. Reports remain `decision_active: false`; no network, 2024/2025, API/UI, VONA, ranking, callback, or rollout behavior changed.

2026-08-28 — Passed OPP-05 as an offline exact empirical lookup. Support-250 cells cover 4,156,593 training observations and passed both 2022/2023 support-calibration folds. The 10-team PPR rank-2 RB/round-1/gap-18 cell reports 5/696, smoothed 0.860%; the 12-team cell reports 2/1,101, smoothed 0.272%. Unsupported contexts return unavailable without fallback. The lookup used 2021–2023 only; 2024 and 2025 remained untouched. TIM-01 and live Draft Intelligence remain unchanged.

2026-08-28 — Rejected OPP-04 after training-year-only rolling development. The fixed monotonic logistic model passed both aggregate fold gates and improved pooled Brier by 0.010829 [0.009705, 0.012063], but predicted 26.63% survival for the frozen rank-2 RB/round-1/gap-18 case with 2,006 observations. The additive form cannot represent the required rank-by-gap tail interaction. It did not query 2024 or 2025 and cannot supply TIM-01 or live predictions.

2026-08-28 — Rejected OPP-03 after correcting the `10+` gap-bucket defect with exact rank, gap, round, and position keys. The rank-2 RB, round-1, gap-18 estimate fell from an invalid 15.99% to 0.489%, close to the raw 0.349% training rate and 0.258% seen-2024 rate. Overall position-model Brier improved by only 0.000257 with an interval crossing zero, below the frozen gate. `opponent-final4`, OPP-02 long-gap evidence, and all existing TIM-01 reports are superseded and must not guide decisions. 2025 remained untouched.

2026-08-28 — TIM-01 remains implemented but suspended. Its six saved-state reports proved the offline cache/projection adapter works across 10- and 12-team states, but they used the superseded broad-gap OPP-01 artifact. Current code rejects that artifact version; no timing report is decision-eligible until a corrected player-survival model passes.

2026-08-28 — Completed OPP-02 across 376,694 historical next-turn states and 3,766,940 player targets. The OPP-01 exact-player model cut false-safe calls from 14.86% to 7.10% and improved Brier by 0.025603, but safe coverage fell from 100% to 79.60%, beyond the frozen 10-point loss limit. The replay artifact is `rejected`. The provisional live modal-hazard approximation was severely over-urgent and remains unchanged. This is seen-2024 diagnostic evidence; 2025 remained untouched. Any threshold calibration requires a new training-year development contract before one frozen 2025 test.

2026-08-28 — Completed the compliant OPP-01 fixed-parameter rerun on the accepted historical market corpus. The inverse-ADP choice baseline beat the provisional live prior on 2024 log loss, and the population exact-player survival model passed with Brier 0.094609 versus 0.120211 and paired difference -0.025603 [-0.026916, -0.024012]. Top-three tier survival missed its Brier gate, so the joint artifact is `rejected` and remains offline. Two earlier 70-cell exploratory artifacts are explicitly noncompliant and rejected. No live callback changed; 2025 remained untouched.

2026-08-28 — Rejected the separately approved HDVN-R01 residual-alpha discovery after train-only rolling validation. Fixed roster-summary Ridge, pick-sequence Ridge, combined Ridge, and masked neural corrections all failed to improve the historical-market baseline in both 2022 and 2023. The strongest correction, roster Ridge, improved 2023 MAE by only 0.02018 and worsened 2022 by 0.38928; its pooled paired difference was +0.15078 [0.10540, 0.19311]. The command opened only the 2021–2023 train Parquet file. It did not open 2024 or 2025. No live behavior changed.

2026-08-28 — Rejected HDVN-06 under its predeclared 2024 points-percentile gate. One fixed 4,707-parameter masked roster model trained on 51,980 teams from 4,617 league-seasons in 2021–2023 and validated on 29,178 teams from 2,570 league-seasons in 2024. Its points MAE was 27.24022 [27.18108, 27.30409], above the 27.08046 threshold and worse than the historical-market baseline by 0.05976 [0.01488, 0.10715]. The locked 2025 file was not opened. The artifact status is `rejected`; HDVN-07 was not initialized; no live behavior changed.

2026-08-27 — Completed safe HDVN pre-crawl preparation without changing live recommendation behavior. The isolated historical package now has immutable SQLite backup manifests, the `hdvn-features-v1` point-in-time registry, an accepted rolling Sleeper market-source audit, an exact-cutoff rolling market board, bounded team and prefix generators, one-prefix-per-team sampling, versioned labels and temporal splits, metric and model protocols, fail-closed artifact loading, and a deterministic network-free dry run. The focused warning-strict HDVN suite passes 16 tests. HDVN-00 through HDVN-12 remain blocked by their final data, fitting, benchmark, approval, or integration gates. No real model was trained, selected, shadowed, or integrated.

2026-08-27 — Reorganized draft-intelligence documentation without changing code or model behavior. The directory README is now the canonical navigation map for current control, stable specification, active research, operations, and historical evidence. `VALUE_MODEL_BOUNDARIES.md` defines ownership and allowed interactions for the live terminal objective, VONA, WORP, and HDVN: VONA stays live next-turn evidence, WORP stays exact-context win telemetry, and both remain outside the planned neural network. HDVN retains its own specification and HDVN-00–HDVN-12 ledger. Resolved positional research and the 2026-08-15 audit/remediation pair moved under `archive/`, with index and internal links preserved.

2026-08-27 — Planned the separate Historical Draft Value Network research project (ADR-040). `HISTORICAL_DRAFT_VALUE_NETWORK.md` defines completed-draft and partial-prefix outcome experiments, strict separation from live projected value, point-in-time feature and leakage rules, one-prefix-per-team-per-epoch weighting, league-season temporal splits, simple-model baselines, uncertainty, artifacts, and release gates. `HDVN_IMPLEMENTATION_LEDGER.md` tracks HDVN-00 through HDVN-12 from frozen data snapshot to baselines, neural experiments, locked benchmark, optional read-only shadow mode, and a later integration-or-rejection decision. No model is trained, no artifact is live-eligible, and no recommendation behavior changes.

2026-08-27 — Added the gated WORP calibration pipeline (ADR-039). `worp-calibrate` reads regular-season matchup margins from the isolated historical Sleeper store, fits exact `(team_count, scoring_format)` points-to-win curves with league-season holdout isolation, and records source hashes, sample counts, thresholds, curves, and holdout errors. Passing the default 1,000-train/250-holdout gates produces only a candidate artifact. `worp-approve` requires an exact context and architecture-decision reference before the live loader accepts it; missing, candidate, failed, malformed, unapproved, and mismatched artifacts leave WORP unavailable without fallback. Projection board v2 can convert approved-context VORP to regular-season WORP and otherwise shows calibration status. It now labels route value as approximate ADP opponent-choice lookahead, not a full expected-value distribution. Full warning-strict Python tests pass 227/227; full frontend tests pass 49/49 and the production build passes. Browser verification confirms candidate WORP stays absent and visibly pending. Real-data fitting and holdout validation remain pending completion of the historical download.

2026-08-27 — Added an isolated historical Sleeper research collector (ADR-038) under `ffsim/historical_sleeper`. `collect` runs at 750 requests/minute, targets 10,000 strict training-ready leagues plus at least 500 from each requested 2021–2025 season, pauses discovery above a 500-candidate hydration backlog, drains 50 candidates per cycle, and prioritizes older deficient years. The default five-second status is one compact hierarchy with target, hydration, discovery, health, and ready-by-year rows; `status --verbose` adds full inventory and exact detail, while `status --once` retains JSON. Progress logs now distinguish cumulative HTTP calls, interval-based HTTP RPM, and new league-seasons/min so high discovery fan-out cannot be mistaken for request rate. Twenty-four fixture-backed tests pass, including target/year stopping, discovery pause, deficient-year priority, strict readiness, compact/verbose rendering, 750-RPM circuit breaking, RPM labeling, and bounded-memory coverage.

2026-08-27 — Added the optional deterministic projection lookahead (ADR-037). The live monitor now accepts `simulation` or `projection`; projection mode skips candidate rollouts, the worker executor, and league-equity calculations, while simulation mode remains unchanged and can show both boards. Projection board v1 ranks every eligible available player within position from prepared league-scored season points, reports the league-wide replacement cutline and VORP, reports roster-aware terminal marginal value, and compares each position's best current pick by deterministic ADP lookahead through the next non-adjacent user pick. WORP is intentionally absent because prepared points do not define a validated points-to-head-to-head-wins conversion; full simulation remains the source of expected wins. Focused Python tests pass 71/71; the full warning-strict Python suite passes 223/223. Draft Intelligence frontend tests pass 19/19; the full frontend suite passes 49/49 and the production build passes. Browser verification covers the live positional tables, filters, full-width layout, and absent league-equity sidebar.

2026-08-17 — Added a Recent trades panel to the Season simulator. League refreshes now cache the 30 newest completed Sleeper trades across the current season, and the existing league response resolves team names, players, draft picks, and FAAB by receiving roster. The panel uses the cached data and shows an explicit empty state. All 221 warning-strict Python tests, 47 frontend tests, and the production build pass. React Doctor reports only the three existing DraftIntel/LeaguePicker warnings.

2026-08-15 — Corrected RACE-01's unsafe intermediate elimination (ADR-036, decision engine v9). Intermediate stochastic confidence intervals are non-monotone, so every selected finalist now reaches the 300-rollout maximum; the 150- and 225-rollout stages still publish progress, and the final board applies the unchanged 0.1-point gate. Focused tests pass 73/73, and the full warning-strict Python suite passes 220/220. A fresh checkpoint-schema-3 staged-versus-true-flat smoke reused the frozen corpus input and passed with 5,000/5,000 candidate-rollouts, a 1.0 work ratio, zero outcome mismatches, zero unsafe mismatches, and player `9488` retained for its observed re-entry. Each record is bound to the snapshot hash, model/scorer/evaluator versions, seed, budgets, and runtime configuration; changed inputs and prior schemas fail closed on resume. The earlier failed smoke remains recorded below. The exact all-2,384-state run is pending, so RACE-01 is not complete or releasable. Exact next step: run that checkpointed corpus comparison; PERF-01 owns any later refinement optimization.

2026-08-15 — Completed MKT-01 (ADR-035). Historical ingestion now preserves each league's complete canonical numeric scoring map, including zero-valued and currently unsupported keys, in `scoring_settings_json`; detailed scoring enters the draft context hash, and `draft_provenance` records `real_league`, `mock`, `cpu_bot`, or `unknown`. Market resolution records separate target and immutable base-board contexts, prefers an exact-team-count snapshot, and uses the unchanged null-team-count board only as an explicit generic fallback. A nonzero or unknown tight-end reception premium remains proxy because the snapshot schema has no premium dimension. Live and synthetic session configurations preserve base, target, proxy, calibration, and model metadata. Only the opponent market model advances to `sleeper-adp-inverse-rank-v2` because board selection can change; MKT-01 does not advance the decision engine, roster scorer, or `SeasonWorldBank`. Warning-strict focused tests and the full 220/220 Python suite pass. At `2026-08-14T18:00:00Z`, the 10-team PPR +0.5 TEP and 12-team PPR templates retain distinct targets while honestly sharing generic snapshot `6f9bbe…ba43`; the local 48-snapshot store has no team-count-specific board. RACE-01's exact all-2,384-state comparison remains pending.

2026-08-15 — Added the checkpointed `tools/validate_racing_corpus.py` gate for RACE-01. It snapshots live SQLite telemetry, rebuilds recorded states by session, reruns independent racing and flat-300 passes, records exact outcome/work/timing comparisons as crash-safe JSONL, and exits nonzero on mismatches or errors. Pure mismatch, aggregation, and resume tests pass 3/3. A one-state `--limit 1` smoke on batch `20260815T043426-52dba2d4` found one unsafe elimination at session `4253a402-ea84-4465-ad9b-382245f26819`, pick 4: racing removed player `9488` at 150 rollouts, while flat evaluation restored that player to the practical tier at 225 and 300. The displayed headline and status still matched; racing used 4,550 candidate-rollouts versus flat's 5,000 (0.91 ratio). The full 2,384-state run has not started and RACE-01 is not releasable. Exact next step: remove unsafe candidate elimination as required by the remediation gate, then run the full checkpointed validator.

2026-08-15 — Completed WHY-01 (ADR-034). The evidence contract separates named-root paired Q and higher/tied/lower shares, alternative-root availability and conditional-selection counts, and candidate-root local opportunity evidence. It defines projected roster value as best-legal-lineup points over replacement plus `BENCH_ASSET_FACTOR`-discounted positive bench value, keeps K/DEF effective urgency at zero while retaining raw VONA as diagnostic, names the urgency/market-ADP/engine-rank basis for practical toss-ups, and labels ADP as a market draft-position proxy rather than modeled trade value. Compact `recommendation_stage` telemetry advances to schema version 2 for additive `headline_tie_break_basis` and the correct survival-branch `target_rollout_count`; no decision-engine, draft/VONA-model, roster-scorer, or cache version changes. Warning-strict Python tests pass 210/210, frontend tests pass 46/46, and the production build passes. React Doctor reported only three pre-existing, out-of-scope component/state-structure warnings. RACE-01's exact all-2,384-state comparison remains pending. Exact next step: build and run that RACE-01 corpus gate; MKT-01 context correction may proceed independently.

2026-08-15 — Implemented RACE-01 (ADR-033, decision engine v8) and passed its named gate. Final recommendations and racing use one leader-minus-candidate predicate: retain a candidate when the paired lower bound is at most 0.1 points, continue only while that interval straddles 0.1, and stop with a bounded practical tie when every retained upper bound is at most 0.1. Intermediate and final watchlists omit stale screen-time `is_top_tier` markers. Warning-strict focused decision/live/API tests pass 52/52; the full warning-strict Python suite passes 207/207 in 25.937 seconds. Named actual racing-versus-flat replays agree for `b053` pick 30 (Breece singleton at 225), `597` pick 40 (Skattebo singleton at 225), and `99dfa` pick 35 (Skattebo/Loveland/Jacobs practical tier at 300), with `outside_survivors` empty at every evaluated stage. Flat checks on six extra known recorded mismatch states also keep `outside_survivors` empty at every stage. The exact all-2,384-state corpus comparison remains pending, so RACE-01 is not complete or releasable. Exact next step: build and run that comparison; WHY-01 may proceed independently.

2026-08-15 — Completed TEL-01 and TEL-02 without changing decision engine v7. Telemetry now uses WAL with a five-second busy timeout, remains fail-visible after that bound, and documents native backup snapshots for long reads. Live and synthetic runs share compact `recommendation_stage` events with phase timing, exact candidate-rollout work, leaders, paired bounds, post-gate survivors, stop reasons, speculation results, branch roots, and integer conditional availability/selection counts; full boards remain at broad-screen and ready boundaries. Validation passes: all 207 Python tests, including the 72-test remediation suite and six focused telemetry checks, with `ResourceWarning` promoted to an error. An isolated 10-team, 17-round full draft (`20260815T155054-77e350f7`) completed in 158.8 seconds with 17/17 compact ready stages agreeing with the full ready boards. Its 71 stage events held 287,553 serialized payload bytes (7,280-byte maximum); after `VACUUM`, they added 380,928 bytes (+16.8%) to the same 2,273,280-byte database without stage rows, for a 2,654,208-byte total. The printed storage estimate is therefore raised from 1,700 to 2,800 KB per draft, 5.5% above this measured full draft. Exact next step: implement RACE-01 with one shared practical-tier predicate and verify zero racing-versus-flat mismatches on the preregistered v7 corpus.

2026-08-14 — Decided how urgency enters the ranking (ADR-032, decision engine v7): it stays inside the rollout measure, and the practical-tie gate shrinks from 0.5 to 0.1 points with the racing regret stop redefined as the gate itself. Measured first on 14 recorded states (new `designs` mode in `tools/draft_policy_alignment_harness.py`, 150 coupled rollouts x 8 ready-board candidates, sessions `7482e87c`/`19aa5ad8`/`5e61ae8e`/`7a45e07c`/`2083d7b9`): the mean paired take-vs-wait delta equals the Q difference for every candidate pair to float precision (max identity error 6.6e-14), so ranking by mean paired completed-roster value already is ranking by expected regret of passing — the explicit take-vs-wait objective (design b) is the current objective, not a new mechanism. The composite `Q + w*max(0, VONA)` (design a) was rejected on measured double-counting: paired deltas already carry ~46% of VONA differences (pooled slope 0.458, n=68, R² 0.405), and everywhere the composite disagrees with Q it flips a genuine leader toward a streamable-position VONA artifact (pick 96: Hunter Henry +0.225/lb +0.132 loses to a DEF at w>=0.5; pick 38: Nabers +4.04/lb +2.98 loses at w=1.0). Post-ADR-031 residual bias on the recorded phantom archetypes measures 0.000-0.065 points (Kelce +0.000/lb -0.015, Pierce +0.001), so 0.1 covers the residual with margin while the genuine Henry edge — flattened into a tie by the old 0.5 gate — becomes a clear leader. Archetype headlines verified through the production payload path: Josh Allen state (`7482e87c` pick 26) stays a clear leader (+5.89 over Nico Collins, lb +4.74, `PAIRED_VALUE_EDGE`); Fannin-type state (`19aa5ad8` pick 78) is an honest 4-way toss-up headlined by the scarce 15%-survival WR (Mike Evans) while 94-97%-survival co-leaders are deferred. The Why panel headline now explains the paired edge as take-now over the best wait plan with survival-based language. Re-baselined on a fresh 5-draft synthetic batch under v7 (`20260814T205948-67f958bc`, 744.3 s, 5/5 completed, 77 decisions, 0 policy mismatches): ready latency median 9.28 s / p95 19.88 s / max 24.50 s (one outlier above 20 s; consistent with the ~9 s ADR-031 projection), no K/DEF headline before pick 60, decisions 32 clear / 45 toss-up with the healthy shape (early 19/26 clear, late 19/25 toss-up on sub-replacement ties); the toss-up rise versus the v6-era 40/81 confounds ADR-031's phantom-edge collapse with the smaller gate and needs the 22-scenario batch to separate. Finalist adjacent-pick continuity: 129/139 still-available previous finalists re-evaluated; all 10 exclusions verified as TE/K cap removals after the user filled the seat or end-of-draft feasibility at picks 170/178. 201/201 warning-strict Python tests (new: paired-delta/Q identity, sub-half-point clear leader, residual-scale tie, racing-stop-equals-gate), 47 frontend tests, and the production build pass. Exact next step: validate scarce-over-survivor headlining and the 0.1 gate on the next live Sleeper mock, and run a full 22-scenario synthetic batch to re-baseline toss-up rates and latency at scale.

2026-08-14 — Aligned the rollout future-user policy with the terminal roster scorer (ADR-031, VONA model `next-turn-vona-v2:terminal-marginal`, live model `needs:vona5:hazard1`). Measured first: on recorded synthetic states, the wait branch failed to harvest the root candidate at the next turn even when he survived (Kelce archetype `5e61ae8e` pick 68: available in 148/150 wait rollouts, taken 0/148, +0.39-0.40 points of phantom paired edge — nearly the whole ADR-030 epsilon), and the policy's ordering disagreed with marginal `projected_roster_value` on 33.9% of value-separated top-10 pairs (7/18 top-1 mismatches, concentrated in rounds 2-10 TE/QB/K/DEF). Three mechanisms, fixed in order: (1) static unfloored season VOR replaced by the scorer's own case structure — open dedicated seat pays floored value over the cutline, open flex seat pays the availability-adjusted value over the seat streamer, displacement is decided by raw projection exactly as `_lineup_order` seats players and priced in floored units with the displaced starter keeping `BENCH_ASSET_FACTOR`, bench pays the discounted fraction, plus a deterministic 1e-9 projection tiebreak so zero-value late ties draft the better player instead of the smallest ID; (2) the mid-draft "core starters first" position gate removed (it was the direct harvest blocker: open QB/RB seats excluded TE entirely), leaving only the end-of-draft feasibility guard and the QB/TE/K/DEF caps; (3) the value basis switched from `bank.expected_scores x weeks` to the scorer's availability-discounted, cutline-floored flat scores, exposed as `LeagueEvaluator.flat_season_scores()` — raw projections had a projection-favored TE priced +11.8 that the scorer scores -6.6 because his across-world availability-discounted mean sits below the durable incumbent's. Merged opportunity costs now recompute VONA/positional drop from merged expectations (bit-exact chunked/flat equality), root evidence prices the candidate against the root roster on the same scale, and the War Room line reads "Adds N to your roster". Validation on the four recorded sub-half-point phantom states: Kelce edge collapses to -0.000 with 148/148 harvests and 0.000 leakage; Alec Pierce +0.000 with 109/110 harvests; Hunter Henry +0.225 (correctly inside the ADR-030 tie gate; forcing the harvest is worse, so the residual is genuine); the pick-78 kicker "clear leader" (+0.81) reverses to -1.62 — the scarce RB runner-up wins before any tie gate, the scarce-over-survivor direction the owner called for. Ordinal disagreement fell to 6.6% (9/137) with 4/18 top-1 mismatches, and the residual mismatches are deferred streamable K/DEF (VONA timing, not value error). Cost, measured on a cold-pool production-shaped harness (41x100 screen + 5x[100-300) refinement, 12 workers): early state 19.5→23.8 s, mid 15.0→15.8 s, late flat (draft-side 50-continuation medians 0.98→1.36 s early, 0.63→0.65 s mid, 0.03 s late) after inlining the per-player marginal into per-position piecewise parameters (profiled: 1.3M `_terminal_marginal` calls per 50 continuations; exact equivalence asserted over all 507 priced players). The regression is the necessary correctness cost of pricing every position in the lookahead; the last batch's real ready median (7.2 s) projects to ~9 s, inside the 10-20 s envelope. 197/197 warning-strict Python tests (new: policy-vs-scorer exact marginal consistency on a real evaluator, flex-TE-over-backup-QB harvest regression, projection tiebreak, updated gate/merge cases), 45 frontend tests, and the production build pass. Reproduction/measurement harness committed as `tools/draft_policy_alignment_harness.py` (trace/ordinal/bench against local telemetry sessions). Exact next step: run a 5-draft synthetic batch under `needs:vona5:hazard1` to re-baseline the real ready-latency distribution and confirm K/DEF timing and roster shapes hold under the aligned policy; ADR-030's 0.5-point practical-tie epsilon can be revisited (shrunk) only after that batch, and Objective 2 (baking VONA into the ranking) builds on the now-terminal-consistent VONA scale.

2026-08-14 — Added the practical-equivalence tie gate (ADR-030, decision engine v6) after a live board headlined Harold Fannin as a "clear leader" on a +0.4-point paired edge (interval 0.0-0.8, ahead in 3% of continuations) despite 99% next-pick survival, when the correct play — as the owner identified — is drafting the scarce alternative now and Fannin at the next turn. Co-leadership now requires the leader's paired lower bound to exceed 0.5 projected points (the racing regret stop); smaller edges are ties ordered by any-position VONA urgency and market ADP, which defers high-survival candidates. Also clarified the Why panel's VONA scope labels: the waiting-cost line is explicitly any-position, and the positional-cliff line states it is the same-position gap that the roster math does not force you to pay. 194/194 Python and 45 frontend tests pass with a clean build. Exact next step: re-validate on the next live mock; consider aligning the rollout future-user policy with the terminal scorer to shrink the epsilon if knife-edge cases persist.

2026-08-14 — Floored rostered players at the position cutline (`ROSTER_VALUE_VERSION` 4) after the second v3 batch showed all-WR late boards over twenty available RBs: the greedy lineup started sub-replacement RB backups on bye weeks at their real score, so bench RBs scored ~0.2 points below bench WRs and were excluded from the statistical tie before the market tie-break could order them. Verified on a 5-draft v4 batch (`20260814T164028-297dae4d`, 5/5 completed, zero errors): benches now mix late-round RBs (RB picks in rounds 14-17 across four of five drafts), sub-replacement picks tie exactly and follow best market ADP, and K/DEF moved to rounds 7-9 — the honest points calculation (elite K/DEF starter edge over the streamer beats near-replacement bench stashes), which the owner accepted explicitly. Added the first "Why this pick" War Room panel; its original wait/harvest wording was later replaced by WHY-01's branch-named evidence contract. 194/194 Python tests, 45 frontend tests (new panel assertions), and the production build pass. Exact next step: validate against a real Sleeper league mock; tune `BENCH_ASSET_FACTOR` only if live boards contradict the owner's judgment.

2026-08-14 — Added discounted positive bench value (ADR-029, `ROSTER_VALUE_VERSION` 3). `projected_roster_value` now credits bench players with 0.25x their positive points over the fixed position cutline (available-but-unchosen weeks from the shared greedy lineup mask, which `_lineup_totals` now returns), so once the lineup is filled the draft chases the highest value-over-replacement player on the board instead of scoring all bench picks zero — the mechanism behind the measured 2-4-round-early K/DEF picks and a nine-WR/two-RB bench in the v2 batch. Statistically tied co-leaders are now ordered by `tier_order` (VONA quantized to whole points, then market ADP, then rank) in both the headline and the payload. ADP is only a market draft-position proxy among value-equivalent candidates and never touches base projected value; the system does not model trade value. Exact bench-credit tests replace the old zero-bench equalities; 194/194 warning-strict Python tests, 45 frontend tests, and the production build pass. Exact next step: run a 5-draft synthetic batch under v3 and calibrate `BENCH_ASSET_FACTOR` against opponent-median K/DEF timing (target rounds 13-15) and bench position mix.

2026-08-14 — Audited the first 5-draft synthetic batch under `ROSTER_VALUE_VERSION` 2 (batch `20260814T143437-f1efc019`, 659.7 s, 5/5 completed across 10- and 12-team slots, zero errors, 81/81 user picks matching final recommendations). Roster shapes normalized to 2 QB / 2 TE / 1 K / 1 DEF everywhere with no QB or TE hoarding. Six ready boards still carried three-plus QBs while a QB was rostered; each was verified legitimate — either a genuine starting-QB upgrade (e.g. Bo Nix over rostered Caleb Williams, ~1 point/week × 17 weeks matching the observed ~18-point gap) or flat late-round ties where a backup QB is honestly comparable to bench depth. Adjacent-pick continuity: of 162 still-available previous finalists, 153 were re-evaluated at the next pick and the 9 exclusions were all correct QB/TE/DEF position-cap removals after the user filled the seat; drops out of the displayed top five were rank changes among evaluated candidates, not window lottery. Decisiveness improved sharply versus the five-cycle championship-era baseline: 41/81 clear leaders (was ~4%), with the VONA tiebreak firing on 25 of 40 toss-ups and tier rows ordered by VONA as designed. Ready latency median 7.2 s, max 20.6 s over 76 measured boards — no regression, one marginal outlier above 20 s. No defect emerged. Exact next step: run a full 22-scenario batch when convenient to re-baseline at scale, and collect the next real Sleeper draft to confirm the QB-pile-up and adjacent-pick-flip symptoms are gone live.

2026-08-14 — Fixed the two roster-value distortions exposed by the first real Sleeper league draft (session `7ae93a0e`, draft `1393988224606568448`) and made recommendations continuous across adjacent picks (ADR-027, ADR-028). Telemetry showed four of five top options were QBs on the turn after the user drafted a QB in a strict 1QB league (systematic ~+10-point edge, SE ~1.1), a second TE recommended at pick 69, and the eventual #1 at pick 132 (ADP-187 RB) absent from the pick-129 window entirely. Offline reproduction on the drafted rosters isolated two mechanisms in `projected_roster_value` v1: matchup-varying weekly means credited perfect-foresight start/sit between same-position teammates (second TE: +47 marginal points), and the assignment-derived streamer pool credited denial value for removing good backups from waivers (backup rookie QB beat the best undrafted WR by 6.5 points). v2 scores flat per-player across-available-week means against a fixed league starter-cutline replacement; re-measured, the backup QB's marginal value is -1.4 and every skill-position swap beats him, while a second TE keeps only genuine FLEX value (+38 behind two FLEX seats). `live_candidate_pool` now always admits the previous pick's still-eligible finalists (monitor-tracked, cleared per session) plus the top ten value-over-replacement players (never K/DEF), so an ADP cutoff cannot flip recommendations between adjacent turns while the board is unchanged. Within a statistically tied co-leader tier, the headline and payload order now use VONA (`PROJECTED_VALUE_TIE`/`VONA_TIEBREAK`) instead of the noise-ranked projected-value argmax, and the War Room labels the tier ordering, shows VONA on tied rows, and renames the buried "Draft value" line to "Value over replacement". Validation: 194/194 warning-strict Python tests (pool stickiness/value-entrant and updated cutline-replacement cases), 45 frontend tests, and the production build pass. Exact next step: run a 5-draft synthetic batch under `ROSTER_VALUE_VERSION` 2 and audit position mix, tier stability, and adjacent-pick recommendation continuity against the 2026-08-14 live baseline.

2026-08-14 — Replaced the root recommendation objective (ADR-026, decision engine v5): candidates are now ranked by `Q(candidate) = mean projected value of the completed user roster across paired draft completions conditioned on selecting the candidate now`, where each completed roster is scored deterministically by `LeagueEvaluator.projected_roster_value` — the existing greedy legal-lineup rule (shared `_lineup_totals` engine, QB/RB/WR/TE/FLEX/SUPER_FLEX/K/DEF eligibility) applied per week to the bank's across-world mean player-week points with bye/never-available weeks masked, unfilled seats credited at the existing streamer replacement level (the lognormal factor's mean is exactly 1), minus the all-streamer baseline. Co-leader tiers, refinement survivors, runner-up, and reason codes (`PROJECTED_VALUE_LEADER`/`PAIRED_VALUE_EDGE`) use paired projected-value deltas, which are deterministic per continuation, so the decision carries draft uncertainty only; the racing regret stop is 0.5 projected points. Championship/playoff/wins/points remain computed on the unchanged 300×14 budget and are published as labeled secondary telemetry; the league-equity sidebar and post-draft simulation are unchanged. `ROSTER_VALUE_VERSION` is folded into the evaluator version hash (streamer seeding untouched), so run signatures and caches invalidate without changing any stochastic numbers. Before/after on recorded synthetic states (10-team slot 6 picks 15/86/155, 12-team slot 2 picks 23/95/167, four seeds, production screen→racing budgets): the value leader was seed-stable 4/4 at picks 15/23/95/155 while the championship argmax flipped across seeds at picks 15, 95, 155 (three different leaders), and 167 (a kicker headline twice — the value objective ranks him 3.3 points behind with a paired interval excluding zero); the two value-side splits (picks 86 and 167) were sub-point paired ties correctly labeled toss-ups. Value-vs-championship recommendation differences ranged +0.3 to +5.6 projected points with secondary championship deltas of −0.1 to −1.2pp (noise-level). Regret versus a 600-continuation reference on the two tie states was ≤0.012 points across all eight seed runs. Latency on the 24 shadow runs: screen median/p95/max 6.12/12.61/13.00 s, ready 8.09/16.71/17.17 s — no regression versus the audit baseline and no state above 20 s. Validation: 194/194 warning-strict Python tests (11 new: bench exclusion, filled-QB versus scarce starter, FLEX/SUPER_FLEX eligibility, exact replacement marginal value, bye streaming, determinism, value argmax headline, value-over-championship ranking, defer-the-survivor/select-the-scarce case, board-changes-survival-not-value), 45 frontend tests, production build, and `git diff --check` all pass; cached/uncached equality covers the new fields through dataclass equality. Remaining limitations: the deterministic scorer ignores season variance by design (championship telemetry still carries it); the season-world budget is now spent only on secondary telemetry and could be reduced, but only after a separate convergence study; absolute championship calibration caveats (ADR-015) persist on the secondary fields; synthetic states cannot show human predictive improvement. Exact next step: run a fresh 22-draft synthetic batch under decision engine v5 to re-baseline screen-to-ready leader churn, toss-up rates, storage, and latency under the projected-value objective.

2026-08-14 — Synthetic audit Cycle 5 completed batch `20260814T112337-233b9a3e`: 22/22 sessions/scenarios completed in 4,068.89 s with 350/350 matching decisions; SQLite grew 35,733,504 bytes, 4.5% below estimate. All integrity, feasibility/cap, candidate-board, outcome, trace/version, sampling-probability, and path-variation checks passed. Screen-to-ready changed 184/350 leaders; 337 were uncertainty toss-ups, maximum top-equity movement was 2.26 points, and no screen/ready interval was disjoint. The minimum opponent draw (`:0020` pick 17 Troy Franklin, `1.45e-6`) was investigated against all five cycles: only five of 17,550 opponent selections were below `1e-5`, within the categorical full-support model's plausible range, with exact probability/log-probability agreement. Feasible ten-RB/ten-WR concentrations recurred but remain an intentionally uncapped model limitation without human evidence. Screen median/p95/max was 6.702/14.228/18.504 s; ready was 12.275/19.720/26.787 s. No actionable defect or architecture change emerged. Validation: 183/183 warning-strict Python tests pass and `git diff --check` is clean.

2026-08-14 — Five-cycle loop complete: 110/110 required drafts and scenarios completed in 19,938.43 s (5.54 h of successful batch runtime), adding 176,254,976 bytes of SQLite telemetry. Across 1,720 recommendation states, aggregate screen median/p95/max was 6.639/14.207/18.790 s and ready was 12.300/19.751/29.063 s; 83 ready events exceeded 20 s and no screen did. The loop eliminated legal DEF/K root-evidence failure, short-tail screen retention failure, 30 missing adjacent snake decisions, and the 3.33x storage-estimate error. The latter four complete batches stayed 4.0–4.6% under the recalibrated estimate. Rare full-support opponent reaches, RB/WR-heavy feasible benches, broad late-draft toss-up tiers, and VONA-heavy early/middle ready outliers recurred; none supports cosmetic model tuning or a human-behavior claim. Exact next step: collect leakage-safe human draft evidence for opponent/reach calibration; if the owner restores a hard 20-second release gate, profile a recorded early endpoint state and pursue exact callback/rollout batching without reducing statistical budgets.

2026-08-14 — Synthetic audit Cycle 4 completed batch `20260814T101135-1f160c08`: 22/22 sessions/scenarios completed in 4,057.08 s with 350/350 matching decisions; SQLite grew 35,905,536 bytes, 4.0% below estimate. Integrity, lineup/cap feasibility, complete candidate boards, outcome conservation, recorded probability/log-probability equality, trace/version fields, and path variation all passed. Screen-to-ready changed 193/350 leaders; 337 were correctly retained as uncertainty toss-ups, the maximum top-equity movement was 2.12 points, and no screen/ready intervals were disjoint. The minimum opponent selection was `:0010` pick 32 Troy Franklin at `6.08e-6`; feasible nine-RB/ten-WR concentrations and broad late tiers recurred without new human-calibration evidence. Mean user title equity remained 22.53% (10-team) and 18.64% (12-team). Overall screen median/p95/max was 6.434/14.207/18.720 s; ready was 12.179/20.547/26.872 s, with 19 ready events above 20 s. No actionable defect or architectural decision emerged. Validation: 183/183 warning-strict Python tests pass and `git diff --check` is clean. Exact next step: run the fifth and final cycle, then calculate aggregate metrics and remaining concerns.

2026-08-14 — Synthetic audit Cycle 3 completed batch `20260814T085707-78d3a2cc`: 22/22 sessions and scenarios completed in 4,106.49 s with 350/350 matching user decisions; SQLite grew 35,753,984 bytes, 4.6% below estimate. No invalid session, roster, lineup, capped candidate, outcome sum, board, trace, probability/log-probability, or repeated full path was found. Screen-to-ready changed 184/350 leaders; 333 were toss-ups and the maximum top-equity movement was 2.38 points with overlapping intervals. A leading uncertainty hypothesis at `:0005` pick 170 was disproved: its recorded runner-up lost significantly, but candidate `12469` remained a coupled co-leader, so the toss-up label was correct. The lowest opponent draw was `:0004` pick 70 Tennessee DEF at `2.96e-5`; recurrent rare reaches and a 10-RB opponent roster remain feasible self-play observations, not a basis for human-model tuning. User mean title equity remained above equal share in both templates (22.93% 10-team, 18.69% 12-team), but no predictive claim follows. Overall screen median/p95/max was 6.624/14.236/18.786 s; ready was 13.056/19.533/26.863 s, with 14 ready events above 20 s. No actionable defect or architectural decision emerged. Validation: 183/183 warning-strict Python tests pass and `git diff --check` is clean. Exact next step: run Cycle 4 and continue cross-cycle recurrence and performance checks.

2026-08-14 — Synthetic audit Cycle 2 completed batch `20260814T074403-c3423403`: 22/22 sessions and all 22 league-size/slot scenarios completed in 4,050.71 s with 350/350 matching user picks, screens, ready decisions, and on-clock states; the Cycle 1 adjacent-turn defect is eliminated. SQLite grew 35,852,288 bytes (1,629,649 bytes/draft), 4.3% below the new 37.4 MB estimate. All 220 rosters satisfy lineup feasibility and QB/TE/K/DEF caps, every candidate board respects the same caps, all outcome totals balance, all 350 screen/ready state signatures pair, trace fields are complete/unique, and all 22 full paths are unique. Screen-to-ready changed 178 leaders; 333 decisions were paired-uncertainty toss-ups, with no status/interval violation, no disjoint screen/ready top intervals, and a maximum 2.14-point top-equity movement. Opponent probabilities exactly match their recorded log probabilities; the minimum (`:0014` pick 41, Shedeur Sanders) was `1.39e-5`. Feasible 10-RB/10-WR opponent benches and rare low-probability reaches recurred, but RB/WR are intentionally uncapped and synthetic self-play cannot establish human implausibility, so no model tuning is justified. Overall screen median/p95/max was 6.671/14.198/18.790 s and ready was 12.094/20.307/26.607 s versus Cycle 1's 6.537/14.139/18.685 and 11.952/19.506/29.063; the extra 30 required decisions increased batch time 10.8% without a material per-decision regression. No code fix or new architectural decision was warranted. Validation: 183/183 warning-strict Python tests pass and `git diff --check` is clean. Exact next step: run Cycle 3 and continue recurrence, calibration, and latency comparisons.

2026-08-14 — Synthetic audit Cycle 1 completed batch `20260814T062407-b443c073`: 22/22 sessions completed across all ten 10-team slots and twelve 12-team slots in 3,655.27 s; SQLite grew 33,009,664 bytes. All drafts had the expected 170/180 picks, screen/ready pairs, summary, and final outcome, but the 350 user picks had only 320 authoritative recommendations. Thirty endpoint picks falsely repeated the preceding recommendation (`:0008` pick 21 selected `8130` after pick 20 recommended `11604`; `:0011` pick 13 selected `8112` after pick 12 recommended `12527`). Exact coverage isolated the defect to slots 1/10 and 1/12; interior slots and pick ownership were correct. `complete_drafts.next_user_pick_no` intentionally groups adjacent owned picks as one VONA turn, while synthetic replay incorrectly used that boundary and consumed the second pick through the future-user policy. Relabeling telemetry was rejected because it would preserve the missing decision; changing VONA turn geometry was rejected because ADR-025 needs the grouped horizon. Synthetic replay now retains the forced root pick and stops before every later user-owned pick. Tests add endpoint, ordinary snake, opponent-start, and linear cases; the prior failure-only synthetic tests never exercised adjacent ownership. The corrected grid will produce 350/350 recommendation/user-pick pairs at an expected 9.4% batch-work increase without changing any statistical budget.

2026-08-14 — The same Cycle 1 audit found no invalid roster, cap, lineup, candidate-board, outcome-accounting, signature, probability/log-probability, or paired-uncertainty violation. Screen-to-ready changed 159/320 leaders, but the maximum top-equity movement was 2.45 points with no disjoint intervals; 299/320 decisions were correctly labeled toss-ups. All 22 full paths were unique (all diverged by pick 10), and the minimum sampled opponent probability (`:0005` pick 8, Travis Kelce, `5.61e-6`) exactly matched `exp(log_probability)`. RB/WR-heavy feasible benches and rare low-probability reaches remain model/statistical observations, not evidence of human behavior or a demonstrated defect. User title equity exceeded equal share across both templates, but the simulator-versus-itself design cannot establish human predictive lift. Overall screen median/p95/max was 6.537/14.139/18.685 s; ready was 11.952/19.506/29.063 s, with 14 ready outliers above 20 s. Those residual VONA-heavy outliers remain accepted for this loop by owner direction after the preceding exact 34–49% optimization; no budget was reduced.

2026-08-14 — Cycle 1 also disproved the original 450 KB/draft SQLite planning assumption: 320 screen/ready/state triples contributed 27.72 MiB and the file grew 1,500,439 decimal bytes/draft, 3.33x the printed estimate. Adding the 30 corrected decision triples projects 1,624,302 bytes/draft, so the deterministic fresh-database estimate is now 1,700 KB/draft (4.66% headroom); history-dependent estimation and dropping forensic telemetry were rejected. The five-cycle prompt is recalibrated to 0.187 GB. Validation after both fixes: 183/183 Python tests pass with `ResourceWarning` promoted to an error outside the semaphore-restricted sandbox; focused VONA cached/uncached equivalence, rollout, and synthetic tests pass; `git diff --check` is clean. Exact next step: run Cycle 2's 22-draft batch and verify 350/350 fresh recommendations, storage calibration, latency movement, and recurrence of Cycle 1 observations.

2026-08-14 — Synthetic-loop retry `20260814T061617-aaf5c107` completed every recommendation through 10-team slot-10 pick 150, then failed at the final turn (pick 170) because the synthetic trace required a 40-candidate screen even when tail feasibility produced a smaller valid pool. Full screens are now identified by `candidates_evaluated == candidate_pool`; partial first batches and refined payloads remain excluded. The completed prefix measured screen median/max 9.20/17.02 s and ready median/max 16.52/26.67 s after VONA optimization; the remaining early/mid outliers are accepted for this audit loop per owner direction. Validation: 179 warning-clean Python tests pass. The failed batch does not count toward the five required cycles.

2026-08-14 — The first synthetic-loop attempt (`20260814T052751-d79fa0f9`) failed at 12-team slot-6 pick 54 when legal DEF root `LAR` was incorrectly repriced through the future-user feasibility filter; root opportunity evidence now uses the same precomputed marginal VOR value while future selections retain all needs/caps. The attempt also measured screen median/max 14.75/18.53 s and ready median/max 22.99/25.52 s. Profiling attributed 1.175/1.761 s of an exact 50-rollout candidate evaluation to VONA policy work, not SQLite or season evaluation. Precomputed masked softmax weights/position masks, positional-composition need caching, reusable roster/availability inputs, and board-indexed hazard arrays cut cold early/middle/late 12-team continuation medians 45–49% and the exact recorded evaluation 34%; 30 paired old/new paths matched with maximum pick-probability drift `4.44e-16`. Validation: 177 Python tests pass with `ResourceWarning` promoted to an error; cached/uncached and coupled-pick equivalence remain covered. The failed batch does not count toward the five required cycles.

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
