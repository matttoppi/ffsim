# Draft-intelligence v7 audit remediation ledger

| Field | Value |
|---|---|
| Source audit | [`AUDIT_20260815T043426-52dba2d4.md`](AUDIT_20260815T043426-52dba2d4.md) |
| Batch | `20260815T043426-52dba2d4` |
| Branch investigated | `feat/draft-intelligence` |
| Base commit | `253ff4e8c5c59b3ff8f86779c2222718e5f51806` |
| Decision engine | `DECISION_ENGINE_VERSION = 7` |
| Roster scorer | `ROSTER_VALUE_VERSION = 4` |
| Future-user policy | `VONA_MODEL_VERSION = next-turn-vona-v2:terminal-marginal` |
| Opponent model | `sleeper-adp-inverse-rank-v1` |
| Investigation date | 2026-08-15 |
| Status | Investigation complete; no remediation implemented |

## Purpose

This is the implementation handoff for the version-7 accuracy audit. It turns the audit findings into ordered work items with source seams, research gates, tests, acceptance criteria, versioning consequences, and explicit anti-fixes.

This document is deliberately separate from `IMPLEMENTATION_LEDGER.md`. The investigation did not change the engine, policy, scorer, frontend, tests, operational ledger, or decision log. The implementing agent should update those sources only as each coherent change is actually completed.

The central constraint is unchanged: fix the advisor's external draft accuracy, not its ability to agree with its own synthetic room. Batch `20260815T043426-52dba2d4` is a regression corpus, not a tuning set.

## How to use this ledger

Work in dependency order. Do not select one visible symptom, add a positional rule, and rerun six hours of synthetic drafts. The batch exposed three different classes of work:

- **Confirmed implementation defects:** the racing bound, Why-panel branch semantics, and telemetry reader locking have identifiable source-level causes and may be fixed directly.
- **Measured product failures with interacting causes:** early K/DEF, late core completion, excess depth, and high-survival reaches need controlled ablations before a behavior change is chosen.
- **Calibration gaps:** opponent realism and player-level survival cannot be called human-calibrated until time-local human drafts and market snapshots exist.

Status labels used below:

| Status | Meaning |
|---|---|
| `READY` | Cause and smallest change seam are established; implementation may begin. |
| `RESEARCH` | The failure is established, but the responsible mechanism or correct product behavior is not. |
| `DATA-BLOCKED` | Current local data cannot support the required claim or fit. |
| `DEPENDENT` | Do not begin until named prerequisite work has landed. |

## Executive repair order

| Order | Item | Priority | Status | Outcome |
|---:|---|---|---|---|
| 1 | TEL-01 — writer-safe telemetry snapshots | P0 operational | `READY` | Audits cannot kill a batch. |
| 2 | TEL-02 — compact stage and branch telemetry | P1 observability | `READY` | Racing, latency, and harvest behavior become auditable without replay. |
| 3 | RACE-01 — make racing equivalent to the 0.1 gate | P0 correctness | `READY` | Early stopping cannot discard a still-practical candidate. |
| 4 | WHY-01 — correct the evidence contract | P0 trust | `READY` | Copy and fields state only what the recorded branches prove. |
| 5 | VAL-01 — build a faithful human validation gate | P0 validation | `DATA-BLOCKED` | Production opponent and survival behavior can be evaluated out of sample. |
| 6 | MKT-01 — represent league market context honestly | P0/P1 modeling | `READY` for context; calibration remains blocked | Ten-team TEP and team count stop masquerading as generic PPR. |
| 7 | OPP-01 — calibrate the opponent distribution | P1 accuracy | `DEPENDENT` on VAL-01/MKT-01 | Remove nonhuman reaches and roster shapes using held-out human evidence. |
| 8 | OPP-02 — calibrate tier/cliff evidence | P2 evidence | `DEPENDENT` on OPP-01/data | Exact-player and tier survival stop being conflated. |
| 9 | RV-00 — causal roster-value ablations | P0 prerequisite | `RESEARCH` | Separate scorer, policy, room, and replacement effects before tuning. |
| 10 | RV-01 — calibrate K/DEF value and streamability | P0 accuracy | `DEPENDENT` on RV-00; then `DATA-BLOCKED` | Clear early K/DEF calls are corrected at the value source. |
| 11 | RV-02 — revalidate replacement and bench economics | P1 accuracy | `DEPENDENT` on RV-00/RV-01/OPP-01 | Core timing and final depth improve without hard roster scripts. |
| 12 | POL-01 — test exact weekly future-policy marginals | P1 correctness | `DEPENDENT` on RV-00 | Quantify whether ADR-031 approximation errors change advice. |
| 13 | POL-02 — classify bye coverage versus preference | P2 product | `DEPENDENT` on POL-01/RV-02 | Fix exact coverage errors without inventing a blanket bye rule. |
| 14 | URG-01 — replay take-versus-wait and harvest behavior | P1 accuracy | `DEPENDENT` on OPP-01/POL-01 and promoted RV changes | High-survival reaches are judged from complete paired branches. |
| 15 | TIE-01 — decide toss-up headline policy | P2 product | `RESEARCH` | Practical ties remain honest and useful to a drafter. |
| 16 | PERF-01 — remove the early-round latency tail | P1 release | `DEPENDENT` on TEL-02/RACE-01 | Meet latency targets without weakening rollouts. |
| 17 | REL-01 — staged release audit | P0 release | `DEPENDENT` on each promoted slice | A changed engine or product slice earns release from applicable evidence. |

Rows at the same dependency depth may run in parallel. A data-blocked row does not stop unrelated `READY` or `RESEARCH` work.

The dependency chain is:

```text
TEL-01 ──> safe investigation
TEL-02 ──> RACE-01 ──> PERF-01
         └> WHY-01

VAL-01 + MKT-01 ──> OPP-01 ─┬─> RV-02 ─┐
RV-00 ──────────────> RV-01 ─┘          ├─> URG-01 ─> REL-01
      └────────────────> POL-01 ────────┘
OPP-02 ─────────────────────────────────┘  (tier conclusions only)

TIE-01 may run as research in parallel; behavior changes join REL-01.
```

### Primary source map

| Concern | Existing implementation seams | Main checks/handoff artifacts |
|---|---|---|
| Telemetry safety/stages | `ffsim/draft_intel/telemetry.py`, `ffsim/api.py`, `ffsim/draft_intel/synthetic.py` | `TELEMETRY_QUERY_GUIDE.md`, telemetry/API tests |
| Racing and final gate | `ffsim/draft_intel/live.py`, `ffsim/draft_intel/decision.py`, `ffsim/api.py` | `tests/test_live.py`, `tests/test_api.py`, `tools/audit_synthetic_state.py` |
| Why evidence | `ffsim/draft_intel/opportunity.py`, `ffsim/draft_intel/live.py`, `web/src/DraftIntel.tsx` | `web/src/DraftIntel.test.tsx` |
| Human market validation | `ffsim/draft_intel/market_model.py`, `ffsim/__main__.py`, `ffsim/draft_intel/history.py`, `ffsim/draft_intel/storage.py` | current `market-backtest`, historical/market tests |
| Opponent choice/context | `ffsim/draft_intel/market_model.py`, `ffsim/draft_intel/market.py`, `ffsim/draft_intel/live.py`, `ffsim/draft_intel/profiles.py` | choice, survival, and cached/uncached tests |
| Roster value/future policy | `ffsim/simulation/evaluator.py`, `ffsim/draft_intel/opportunity.py`, `ffsim/draft_intel/live.py` | `tools/draft_policy_alignment_harness.py`, `tests/test_roster_value.py`, `tests/test_vona.py` |
| Latency | `ffsim/api.py`, `ffsim/draft_intel/live.py`, `ffsim/draft_intel/rollout.py`, `ffsim/draft_intel/opportunity.py`, `ffsim/simulation/evaluator.py` | TEL-02 stage telemetry and representative state profiles |

### ADR boundaries

- Preserve ADR-006's separation of player value from opponent availability.
- Preserve ADR-023's durable, fail-visible telemetry while making readers safe.
- Treat ADR-027's fixed replacement baseline and ADR-029's bench factor as hypotheses to revalidate, not bugs to delete on sight.
- Do not restore ADR-031's removed mid-draft core gate; first measure the exact-policy and replacement alternatives without reviving survivor-harvest failure.
- Retain ADR-032's 0.1 practical gate during RACE-01. The confirmed defect is that racing used a different bound.
- Treat ADR-015's temperature and ADR-019's reach support as provisional artifacts that need held-out human fitting, not constants to tune against synthetic outcomes.

## Evidence and decision rules

### Regression baseline

The implementation must retain these baseline facts rather than silently changing denominators:

- 150/150 authoritative sessions completed, with 2,384 user decisions and 23,946 opponent picks.
- All user and opponent rosters were legal; caps and paired-Q payload identities passed.
- 223/300 K/DEF selections occurred before the final three rounds; 98 occurred before the dedicated `QB/RB2/WR2/TE` core, including 70 clear calls.
- 100/150 user rosters took TE2 before QB1; 117 QB/TE backup headlines occurred while a dedicated starter hole remained.
- Opponents made 1,004 picks at least five rounds ahead of ADP and 27 round-2–5 K/DEF picks.
- The final board was a toss-up at 1,344/2,384 decisions; 498 toss-up headlines had a paired interval wholly below the Q leader.
- Ready latency was median 9.172 seconds, P95 20.107, maximum 26.592; 124 decisions exceeded 20 seconds.
- A preliminary batch was orphaned after an external read transaction blocked a telemetry commit.

### What counts as proof

- Use draft-level splits and confidence intervals. Picks and rosters inside one draft are correlated observations.
- Use the exact and near-format human cohorts only for coarse position timing and roster shape. The exact cohort contains three drafts, so it is an alert baseline, not a fitted target.
- Use time-local market snapshots for player-level ADP, survival, and reach validation. Do not join a 2026 board to an old draft and call it calibration.
- Keep deterministic player value separate from opponent availability, as required by ADR-006.
- Keep recorded paired Q, modeled availability, conditional future-user selection, local marginal evidence, and realized next-board alternatives as separate quantities.
- Use common rollout IDs and fixed seeds for mechanism ablations. A changed synthetic room is not a controlled comparison.
- Do not promote a hypothesis because one named replay flips. Require the implicated metric to move across the preregistered state set.

### Global anti-fixes

Do not:

- tune coefficients against this 150-draft synthetic batch;
- hard-ban K/DEF, same-bye backups, or backup QB/TE as a substitute for value-model evidence;
- restore the removed mid-draft core gate without resolving ADR-031's survivor-harvest regressions;
- add hard RB/WR caps to imitate the small human sample;
- inject ADP into the player-value objective;
- use the scorer's TE premium to make opponents value TE unless human draft evidence supports that opponent behavior;
- lower opponent reach support by eye;
- cut candidates, continuations, or season worlds to make latency charts look better;
- describe same-generator synthetic calibration as human calibration;
- add a second rollout implementation, tier engine, or audit database when an existing seam or SQLite feature suffices.

## TEL-01 — Make telemetry safe for concurrent readers

**Priority:** P0 operational reliability

**Status:** `READY`
**Finding:** the excluded batch `20260815T042038-86a81000` was orphaned at pick 69 after a long read transaction blocked a writer commit. `DraftTelemetry._connect()` uses SQLite's default rollback journal; its in-process lock cannot protect against another process.

### Confirmed source seam

- `ffsim/draft_intel/telemetry.py`: `DraftTelemetry._connect()` enables foreign keys but does not select WAL or an explicit busy policy.
- `docs/draft-intelligence/TELEMETRY_QUERY_GUIDE.md`: current query workflow does not require a native snapshot for long post-batch scans.
- ADR-023 requires durable, fail-visible telemetry. Any change must preserve that contract.

### Smallest correct change

1. Enable WAL once during telemetry database initialization.
2. Set an explicit bounded connection timeout or `busy_timeout` on every connection.
3. Continue to fail visibly after that bounded wait; do not swallow writes or fall back to memory.
4. Add a small native SQLite-backup helper or documented command for immutable post-batch analysis. Long audits should query the snapshot, not the active writer database.
5. Update the telemetry guide with the safe live-query and snapshot procedures.

### Required checks

- A newly initialized database reports WAL mode and still enforces foreign keys.
- Opening an existing rollback-journal database migrates safely on initialization.
- Hold a read transaction on a second connection while `record()` commits; the event becomes queryable within a bounded time.
- Existing start, record, query, and finish tests still pass.
- Simulate writer failure beyond the bound and verify it remains visible.

### Acceptance

- A long-lived read transaction does not block normal event commits within the configured timeout.
- The post-batch audit instructions use a snapshot for expensive joins.
- No telemetry event is silently dropped.

### Version/docs

No decision-engine bump. Amend ADR-023 and `TELEMETRY_QUERY_GUIDE.md` when implemented.

## TEL-02 — Record compact recommendation stages and branch provenance

**Priority:** P1 observability

**Status:** `READY`

**Dependencies:** TEL-01 should land first so measurement does not destabilize runs.

### Gap

Live telemetry records cumulative duration and a generic `refining` status. Synthetic `_RecommendationTrace` keeps only the completed broad screen, and the synthetic runner writes only `screen` and `ready`. The audit therefore cannot reconstruct:

- the first useful board latency;
- stage leaders, paired bounds, survivor sets, or stop reasons;
- speculative reuse;
- whether an available future target was actually selected;
- full batch-wide false-stop and non-harvest rates without expensive replay.

### Existing seams to reuse

- `ffsim/api.py`: `LiveDraftMonitor._publish_recommendation()` and staged `calculate()` flow.
- `ffsim/draft_intel/synthetic.py`: `_RecommendationTrace` and synthetic event recording.
- Existing append-only telemetry event payloads; no new database or continuation dump is needed.
- Existing survival counters and `merge_survival_reports()` for integer-backed aggregation.

### Smallest correct change

Add compact `recommendation_stage` events shared by live and synthetic execution. Record only summaries:

- phase: `first_board`, `full_screen`, `refinement_150`, `refinement_225`, or `ready`;
- cumulative and stage duration;
- evaluated/refined candidate IDs and rollout count;
- Q leader, displayed headline, and practical co-leaders;
- paired lower/upper bounds against the Q leader;
- survivor set after the gate;
- stop reason: `bounded_practical_tie`, `single_clear_survivor`, `max_budget`, or `state_advanced`;
- actual candidate-rollout work;
- speculation attempted/hit/miss;
- survival branch root and opportunity-evidence branch root;
- integer `target_available_count` and `target_selected_when_available_count` at the next user pick.

Do not store full continuation arrays or duplicate the full candidate board at every stage.

### Required checks

- One query can reproduce each ready result's stage order, survivor set, headline, and status without replay.
- The final stage agrees with the ready payload.
- Live and synthetic runs emit the same schema.
- Selection counts merge correctly across rollout chunks and satisfy `target_selected_when_available_count <= target_available_count <= total`.
- Telemetry size growth is reported for one full draft and remains bounded.

### Acceptance

- First-board, broad-screen, refinement, and ready latency are separately measurable.
- RACE-01's flat-versus-racing check can diagnose the exact elimination stage.
- WHY-01 can distinguish “available” from “selected when available.”

### Version/docs

No engine bump. Amend ADR-023 and the telemetry query guide.

## RACE-01 — Make racing use the final 0.1 practical gate

**Priority:** P0 correctness

**Status:** `READY`

**Dependencies:** TEL-02 for production-scale evidence; the source correction itself is already established.

### Evidence

- Seven of 2,384 ready states eliminated a candidate still marked practical at its deepest recorded stage.
- Production stopped at 150 rollouts in 1,194 toss-ups.
- At session `b0537364-c590-4bb5-be73-a68a707e41f0`, draft `:0123`, pick 30, production headlined Rashee Rice at a paired mean of `-2.070` versus Breece Hall, CI `[-4.097, -0.043]`. Flat 300 made Breece clear at `+2.333`, lower bound `+0.870`.
- At session `59719bcd…`, draft `:0080`, pick 40, a 150-rollout toss-up became a clear Cam Skattebo call at flat 300.
- At session `99dfa900…`, draft `:0112`, pick 35, Josh Jacobs remained practical at flat 300 after racing had removed him.

### Confirmed cause

- `ffsim/draft_intel/decision.py`: `recommendation_summary()` admits candidate `C` when the lower bound of `leader - C` is at most `PRACTICAL_TIE_POINTS = 0.1`.
- `ffsim/draft_intel/live.py`: `refinement_survivors()` keeps `C` only when the upper bound of `C - leader` is at least zero, equivalent to requiring the lower bound of `leader - C` to be at most zero.
- `ffsim/api.py`: early stopping asks whether a rival can plausibly beat the leader, but not whether more samples could establish that the current leader clears the 0.1 gate.

ADR-032's claimed equivalence is therefore false in the implementation.

### Smallest correct change

1. Define one practical-tier predicate in the decision layer and call it from both final summary and racing.
2. Use `leader_delta = paired_value_delta(leader, candidate)` consistently.
3. Retain `candidate` while `leader_delta.interval[0] <= 0.1`.
4. With multiple retained candidates, continue refinement while any retained comparison straddles the practical boundary: lower `<= 0.1 <` upper.
5. Stop early only when there is one clear survivor or every retained comparison is bounded at or below the practical margin.
6. If a fixed-budget corpus still shows unsafe mismatches, remove the early-stop/elimination optimization before adding any empirical safety fudge.
7. Do not carry an eliminated candidate's stale `is_top_tier=true` marker into the ready watchlist. Remove that final-scope field or rename it to `was_top_tier_at_rollout_count`; only final `co_leader_candidate_ids` represents ready-tier membership.

### Required checks

- Boundary candidate with `CI_upper(candidate - leader)` in `[-0.1, 0)` survives.
- Wide `CI(leader - candidate) = [0.04, 4.10]` continues refining.
- A genuinely bounded interval within the 0.1 practical margin may stop as a toss-up.
- A lower bound above 0.1 removes a dominated candidate.
- Replace the non-boundary survivor test in `tests/test_live.py` with explicit interval cases.
- Preserve the monitor-stage behavior covered in `tests/test_api.py`.
- Replay the three named states.
- Compare racing with flat 300 on all 2,384 recorded states using identical finalists, seeds, rollout IDs, and cache mode. Report headline, status, practical-tier mismatches, work ratio, and latency. The release target on this corpus is zero mismatches.

### Acceptance

- Racing and the final summary use the same predicate and interval direction.
- Named replay outcomes agree with the configured full-budget evaluator.
- No candidate is eliminated merely because it fails a zero-point test while still passing the 0.1-point gate.
- Screened/watchlist metadata cannot represent an earlier-stage practical tier as the final tier.
- Coupling, minimum rollout counts, and cached/uncached equivalence remain intact.

### Version/docs

Advance `DECISION_ENGINE_VERSION` from 7 because recommendations can change. Add an ADR that corrects ADR-032's racing-equivalence claim while retaining the 0.1 gate unless TIE-01 later changes it.

## WHY-01 — Correct the Why-panel evidence contract

**Priority:** P0/P1 user trust

**Status:** `READY`

**Dependencies:** TEL-02 supplies conditional-selection evidence; the false current claims can be removed independently.

### Evidence

- Candidate payload structure was internally consistent, but 2,222 headlines attached later alternatives from a branch that the UI described incorrectly.
- On 589 clear calls, the UI asserted that a player surviving to the next turn would be drafted there. Telemetry measured availability, not conditional selection.
- At draft `:0150`, pick 71, Oronde Gadsden had 100% modeled survival; the reconstructed wait path took Harold Fannin at the next turn and never took Gadsden.
- 208 K/DEF headlines exposed raw VONA over one point although K/DEF urgency is deliberately neutralized in tie ordering.
- Every toss-up received a “strongest asset to hold or trade” claim despite no trade model.
- Of 1,040 clear calls, 250 won fewer than half of paired continuations; mean expected value and majority-path wins are different facts.

### Confirmed branch semantics

- `evaluate_candidates()` and `opportunity_evidence()` derive current marginal and later alternatives from the candidate-taken root completions.
- `live_recommendation_payload()` derives exact-player survival from the best-other-root branch.
- `web/src/DraftIntel.tsx` combines those facts into “if you pass” and “passing still drafts him” prose.
- Paired Q is the valid take-versus-alternative-root comparison. VONA is local opportunity evidence, not an additive regret term.

### Smallest correct change

1. Describe paired Q precisely as the comparison between taking the headline root and taking the named alternative root; label the resulting mean “best expected completed-roster value.” The named alternative is not a universal wait action.
2. Show continuation win/tie/loss share when a positive mean is carried by a minority of larger wins.
3. Describe survival as “available at the next turn under the [named alternative-root] branch.”
4. Do not say a surviving player is selected unless TEL-02 records conditional selection.
5. Label later alternatives as candidate-taken-branch local opportunity evidence, never as the paired pass branch.
6. Preserve raw K/DEF VONA as labeled diagnostic telemetry, but never present it as effective user-facing urgency where product logic neutralizes it.
7. Say “projected roster value,” and disclose that the objective includes discounted bench-asset value; do not say “starting-lineup value” alone.
8. Replace the unsupported trade claim with the actual market-ADP tie-break claim.
9. Add explicit branch-provenance and effective tie-break fields so the frontend does not infer semantics from numbers.

### Required checks

- A 100%-available/0%-selected Gadsden-style case never claims later selection.
- Candidate-taken later alternatives are never rendered as pass-branch evidence.
- A clear expected-value call with win share below 50% uses risk-neutral expected-value wording.
- Raw K/DEF VONA remains available as labeled diagnostic telemetry but is absent from effective user-facing urgency.
- The bench term and market proxy are described accurately.
- Update `web/src/DraftIntel.test.tsx`, whose current assertions enforce the false harvest copy.

### Acceptance

- Every sentence can be reconstructed from one named payload field and branch.
- The panel separates expected Q, win share, survival, conditional selection, and local opportunity evidence.
- No unmodeled trade or statistical-equality claim remains.

### Version/docs

Copy and payload corrections do not require an engine bump. A headline-selection behavior change belongs to TIE-01 and does.

## VAL-01 — Build a faithful held-out human validation gate

**Priority:** P0; blocks opponent tuning and human-calibration claims

**Status:** `DATA-BLOCKED`

### Confirmed blocker

Running `.venv/bin/python -m ffsim market-backtest` considered 83 included historical drafts and scored zero. Every draft predates the stored market snapshots: the latest included draft ended August 10, while snapshots begin August 13.

The command also does not evaluate production behavior:

- `backtest_sleeper_adp()` defaults to temperature `1.0` and reach rate `0.0`, while live uses `0.11` and `0.15`.
- The query lacks exact roster ownership/state and position context.
- Caps and terminal feasibility are not faithfully replayed.
- Output is limited to pick log loss/top-K, without survival, positional timing, reach tails, or final roster shape.

The existing 2024/2025 drafts remain useful for coarse roster-shape priors. They cannot validate 2026 player-level survival against a current board.

### Data gate

Use authorized, already-captured snapshots whose provider observation time **and** local retrieval time both predate the matched draft, or collect future drafts after append-only snapshot capture is in place. A newly downloaded historical board does not satisfy the repository's leakage rule. Preserve:

- draft provenance: real league, mock, CPU/bot, or unknown;
- exact pick ownership and available set;
- scoring settings and roster slots;
- manager identity when known; 206/14,810 included local picks currently have null `manager_id`, which must remain unknown;
- snapshot source, timestamp, context, and candidate coverage.

Do not fabricate old ADP from today's market.

### Smallest implementation path after data exists

Extend the existing backtest rather than creating another opponent implementation:

1. Reconstruct sequential roster state and exact pick ownership.
2. Call the same `sleeper_adp_choice` configuration artifact used in production, including caps and terminal feasibility.
3. Evaluate next-turn survival sequentially with the existing survival machinery.
4. Split chronologically and bootstrap by whole `draft_id`.
5. Report candidate-set coverage, log loss, top-K, position-choice error, ADP residual tails, exact-player survival Brier/calibration by position × round × context, tier depletion when available, and final-roster shape.
6. Compare at least target ADP, target ADP plus roster needs, and the proposed population model. Personalization remains a later gate.

### Acceptance

- Output names the exact production model/version, parameter artifact, training cutoff, snapshot IDs, league context, and draft-level split.
- No later snapshot or later pick leaks into training.
- Missing selected-player coverage is reported, not silently skipped.
- `model_status` remains the current `uncalibrated_sleeper_adp_baseline` until held-out human gates pass, unless the contract is intentionally versioned.
- Synthetic calibration is labeled same-generator validation only.

### Version/docs

Backtest-only work does not bump the engine. Schema/provenance changes require migrations and documentation but not a decision version unless live behavior changes.

## MKT-01 — Represent league market context honestly

**Priority:** P0/P1 modeling

**Status:** `READY` for context correctness; effect calibration remains blocked on VAL-01

### Evidence and confirmed cause

- The ten-team template is full PPR with `+0.5` per TE reception, but `resolve_league_market_context()` reads ordinary receptions only and labels it generic PPR.
- `load_league_market_snapshot()` hardcodes `team_count=None` even though manual imports can carry team count.
- Both ten- and twelve-team drafts therefore use the same 334-row generic FantasyPros/Sleeper board.
- Historical raw payloads preserve scoring settings, but normalized `HistoricalLeague`, storage, and `_context_hash` discard them.

This proves a context-label defect and a latent exact-selection gap. No contextual board existed in this batch, so the evidence does not show that an available exact board was selected incorrectly or quantify the direction of TEP/team-count survival bias.

### Smallest correct change

1. Normalize and persist canonical league scoring settings and draft provenance.
2. Include relevant scoring and roster context in the historical context hash.
3. Resolve team count and TE reception premium explicitly.
4. Load an exact team-count/scoring board when one exists.
5. Otherwise keep the provider board unchanged and label it as an explicit generic proxy with stable reason codes.
6. Record base-board context, target league context, proxy reasons, calibration artifact, and model status in telemetry.
7. Apply any learned team-count/TEP adjustment in the opponent model artifact, not by rewriting provider observations.

### Required checks

- Ten-team `+0.5` TEP is not labeled exact generic PPR.
- Ten- and twelve-team contexts remain distinct even when both fall back to one provider snapshot.
- Exact selection and generic-proxy fallback are deterministic and tested.
- Context hashes change when relevant scoring or team count changes.
- Raw provider rows remain immutable and retain provenance.

### Anti-fixes

- Do not place scorer-derived TE values into opponent-choice utility.
- Do not call FantasyPros expert-rank dispersion observed draft-position dispersion.
- Do not claim a generic board has exact TEP/team-count semantics.

### Version/docs

Context metadata alone does not bump the engine. Selecting a different live board or applying a context adjustment does; version the market artifact, invalidate affected caches, and record an ADR.

## OPP-01 — Replace the nonhuman opponent distribution

**Priority:** P1 external accuracy

**Status:** `DEPENDENT` on VAL-01 and MKT-01

### Confirmed current mechanism

- `sleeper_adp_choice` uses only `-log(ADP)` utility before structural filters.
- Live uses a global temperature `0.11` plus a 15% full-support reach component at reach temperature `0.3`.
- The choice model explicitly discards `pick_no`.
- Before terminal must-fill, it has no position-by-round, starter-need, roster-shape, league-context, or manager effect.
- K/DEF are eligible from pick 1, RB/WR are uncapped, and terminal feasibility acts only near the end.
- The same callback generates synthetic opponent picks and forecast survival, so the audit's strong Brier score is same-generator consistency.

This mechanism directly explains nonzero extreme reach support and permits nonhuman roster tails. Its causal contribution to user headline errors must still be measured by fixed-state ablation.

### Baseline evidence to preserve

- 1,004/23,946 opponent picks were at least five rounds ahead of ADP.
- Twenty-seven round-2–5 K/DEF picks appeared in 27/150 drafts.
- Indianapolis DEF went at pick 17 with ADP 225 and recorded probability `3.412e-6`.
- Ten-team opponent rosters had RB7+ in 99/603 cases and WR8+ in 132/603; near-format humans were 0/80 and 2/80.
- All 1,516 opponent rosters were legal. The replacement must retain legality.

### Smallest evidence-led path

1. Fit the existing temperature/reach family on chronological training drafts and evaluate it on untouched held-out drafts.
2. If that family still misses the preregistered tail, timing, or roster-shape gates, add only supported population effects at the existing `sleeper_adp_choice.choose()` seam:
   - position by round/context;
   - soft roster-count or starter-need offset;
   - empirically fitted ADP residual/dispersion.
3. Preserve caps and terminal feasibility. Keep RB/WR depth soft, not hard-capped.
4. Run fixed-state, common-random-number ablations:
   - refitted reach only;
   - plus position timing;
   - plus roster shape;
   - plus team-count/TEP context.
5. Promote the smallest model that clears held-out gates.

Reuse the existing market-choice seam. From `profiles.py`, reuse only context-weighting and descriptive position summaries: `load_pick_observations()` contains target-manager picks and an observed-draftee set, not the complete time-local market choice set, so it is not direct conditional-choice training data. The current profiles remain descriptive-only until held-out lift is established.

### Required checks

- Choice probabilities normalize after every filter.
- The selected historical player remains in the evaluated candidate set.
- Roster legality, caps, terminal feasibility, determinism, coupling, and cached/uncached equivalence remain intact.
- Preregister a noninferiority margin; require noninferiority to target ADP plus positive lift on a primary metric or a documented, preregistered roster-realism tradeoff.
- Position timing, five-round reach tails, early K/DEF, and extreme RB/WR roster rates fall within held-out human prediction intervals.
- Fixed-state ablation reports how much the new room changes the user recommendation, rather than assuming it does.

### Anti-fixes

- Do not lower `reach_rate` by eye; ADR-019 added support after near-certain survival failures.
- Do not zero off-window support without measuring missed human selections.
- Do not tune on the synthetic audit batch.
- Do not force every opponent to fill starters in one prescribed order.
- Do not wire descriptive manager profiles into production as a shortcut.

### Version/docs

A production-distribution change supersedes or amends ADR-015 and ADR-019, versions the opponent artifact and caches, and advances the decision-engine version. Preserve ADR-006 and ADR-024 unless human evidence justifies a durable change.

## OPP-02 — Add calibrated tier and cliff evidence

**Priority:** P2

**Status:** `DEPENDENT` on OPP-01 and time-local human data

### Existing seam

Consensus observations can retain `rank_std` and `tier`; platform-specific Sleeper observations currently contain neither. `evaluate_candidates()` already accepts tier groups and `summarize_survival()` already calculates depletion, but the live batch passes no tiers.

### Work

1. Estimate draft-position dispersion from time-local human outcomes by ADP range, position, and context.
2. If a contemporaneous consensus tier is joined to a Sleeper board, retain source/timestamp provenance and call it a consensus tier.
3. Reuse the existing tier argument and survival summary rather than building a second depletion engine.
4. Validate tier remaining-count and exhaustion probabilities out of sample before making user-facing cliff claims.

### Acceptance

- Payload and copy distinguish exact-player survival from tier survival.
- Held-out tier-depletion error is reported.
- Generic tiers never masquerade as league-specific TEP tiers.

## RV-00 — Run causal roster-value ablations before changing behavior

**Priority:** prerequisite for RV-01, RV-02, and POL-01

**Status:** `RESEARCH`

### Why this is necessary

The batch establishes a product failure but not one isolated cause. Clear early K/DEF, late QB/core completion, TE2 timing, and RB-heavy benches can interact through:

- full-season deterministic K/DEF projection gaps;
- the fixed starter-cutline replacement baseline;
- the additive 0.25 bench-asset factor;
- end-only feasibility;
- the ADR-031 marginal approximation;
- and the nonhuman opponent room.

Changing all of them together would make the result uninterpretable.

### Existing machinery to extend

Use `tools/draft_policy_alignment_harness.py` and the audit state-replay tool. Do not create a parallel simulator. Rebuild fixed states with identical seeds, candidate sets, common rollout IDs, flat 300-rollout evaluation, and cache mode.

At minimum, compare:

- current scorer/current future policy;
- exact weekly scorer marginals in the future policy;
- current and human-calibrated opponent distributions;
- current and candidate-independent waiver-replacement assumptions;
- bench-asset factor/model variants;
- evidence-backed K/DEF reliability/streaming variants.

### Required state set

| Session/draft/pick | Behavior to isolate |
|---|---|
| `b0537364… / :0123 / 71,111` | LAR DEF and Harrison Mevis before QB/RB2 |
| `b6a31c74… / :0090 / 95,115` | TE2 before WR2 and RB7 handcuff |
| `394482cd… / :0062 / 95` | QB2 before WR2 |
| `a25f1ffb… / :0040 / 74` | QB2 with an open flex |
| `719bd796… / :0100 / 83` | same-bye TE2 |
| `0f6ef660… / :0058 / 81` | large TE marginal-approximation error |
| `fc347ed1… / :0008 / 54` | TE2 without root approximation overpricing |
| `4a6d0aab… / :0056 / 110` | exact Mevis value while QB remained empty |

Record headline/status/tier flips, paired-Q movement, future-policy choices, final position counts, conditional harvest, and latency. A mechanism becomes causal only when its isolated ablation moves the implicated behavior across the preregistered set.

## RV-01 — Calibrate K/DEF value and streamability

**Priority:** P0 draft accuracy

**Status:** `DEPENDENT` on RV-00, then `DATA-BLOCKED` until historical preseason K/DEF projection/outcome evidence is available

### Confirmed mechanism boundary

K/DEF tie urgency is already set to zero inside practical-tier ordering. That affects which tied player is displayed, but it cannot cause the 70 clear K/DEF-before-core calls. Those calls come from completed-roster Q under the scorer and future policy.

`LeagueEvaluator.projected_roster_value()` credits a deterministic season-long edge over a fixed positional cutline. A template scan found top K edges of about 5–9 points and top DEF edges of about 6–10 points. At `4a6d0aab… / :0056 / pick 110`, Harrison Mevis had an exact marginal of `+7.591` while all evaluated QBs had zero. K/DEF projections use the PFF fallback path, and no local preseason out-of-sample rank-persistence validation supports treating those small edges as durable.

The leading hypothesis is that the objective overstates preseason K/DEF ordering reliability and understates weekly waiver/streaming flexibility. This is not yet proven.

### Smallest defensible path

1. Obtain historical preseason K/DEF projections and realized weekly/season outcomes with source and timestamp provenance.
2. Measure out-of-sample rank persistence and points-over-replacement gaps.
3. Compare the current scorer against simple evidence-backed alternatives:
   - shrink K/DEF edges toward a fixed streaming cutline; or
   - score rostered K/DEF against an explicit candidate-independent weekly streaming option.
4. Use the same chosen semantics in the authoritative scorer and future-user policy.
5. Keep ADP out of player value.

If projection research cannot be obtained, stop for an explicit owner decision about a hard product rule. Do not smuggle that product preference into a “calibration” coefficient.

### Required checks

- Add scorer tests for K/DEF reliability or streaming marginal and unchanged offensive marginals.
- Add policy/scorer alignment tests under the new semantics.
- Retain one legal K and DEF by draft completion.
- Preserve candidate independence, branch independence, deterministic replay, and cache equivalence.
- Confirm that raw K/DEF VONA remains hidden in WHY-01 even after Q behavior changes.

### Acceptance

- The selected transformation beats the unshrunk projection baseline out of sample.
- In a fresh confirmatory batch, K/DEF-before-core falls within a preregistered draft-clustered human tolerance; use 5% only as a provisional alert ceiling, not a fitted target.
- First-K/DEF medians are approximately within one round of exact-format human medians.
- Every final roster remains legal with one K and one DEF.

### Anti-fixes

- Do not zero VONA again and declare the clear-call problem solved.
- Do not hide K/DEF from the candidate pool until a fixed round.
- Do not increase bench value merely to outweigh special teams.
- Do not insert ADP into the scorer.

### Version/docs

A scorer change increments `ROSTER_VALUE_VERSION`, the decision engine, relevant model tags/cache keys, and requires a new ADR or explicit supersession of ADR-029/031.

## RV-02 — Reassess the replacement baseline and bench economics

**Priority:** P1 roster construction

**Status:** `DEPENDENT` on RV-00, RV-01, and OPP-01

### Confirmed current behavior

- `_starter_cutline_replacement()` reserves only league starter and flex seats, not normal bench demand.
- Unfilled slots and rostered weekly scores are floored at that fixed cutline.
- Every available, unchosen player-week receives `0.25 × positive points over cutline`; bye and unavailable weeks receive no bench credit.
- The bench term is additive with no same-position depth decay; RB/WR are uncapped.
- At `b6a31c74… / :0090 / pick 95`, displayed QB/WR exact marginals were zero, Kelce was `+0.748`, and kickers were `+3.910` and `+5.300`.
- At `394482cd… / :0062 / pick 95`, Jaxson Dart was zero while Philadelphia DEF was `+8.632`.

The fixed starter cutline may make waiting on depleted offensive positions artificially cheap, while the linear bench term may value RB7 like RB3. Neither mechanism alone has been proven to cause the batch-wide roster shape. ADR-027/029 deliberately chose these semantics, and ADR-029's factor evidence was synthetic rather than external.

### Investigation A — candidate-independent replacement

Compare the current starter-only cutline with a league-specific waiver cutline derived from held-out human end-roster demand. Keep it fixed across candidate branches so the ADR-027 denial-value bug cannot return. Evaluate separate fixed concepts for:

- lineup streaming replacement; and
- bench/asset replacement.

Do not derive replacement from each simulated assignment.

### Investigation B — bench asset

After RV-01, compare factor zero, current `0.25`, and—only if supported—a simple monotone depth decay. Measure lineup coverage, injury-contingent usefulness, and held-out final roster shape. Prefer removing or reducing an unvalidated linear proxy over inventing trade value the model does not possess. Do not add RB/WR caps.

### Required checks

- Changing another team's branch assignment cannot change the same user roster's value.
- An empty roster remains zero against its fixed baseline.
- No return of ADR-027 backup-QB denial value, all-zero late boards, all-WR boards, or clear early K/DEF.
- Core timing, WR/RB depth, and K/DEF timing are evaluated jointly.
- Retain legal final rosters and cached/uncached equivalence.

### Acceptance

- Core median is no later than the human median plus one round and P90 no later than plus two, using preregistered draft-level checks.
- TE2-before-QB1 and QB2/TE2-with-core-hole rates materially decline and either clear the preregistered held-out interval or trigger human adjudication; do not tune to the provisional 5% alert.
- Ten-team RB7+ and low-WR extremes fall within held-out human prediction intervals.
- Mean WR counts are within a preregistered tolerance; the current exact-cohort gap of roughly 0.67 in twelve-team rooms must materially close.
- The chosen objective variant improves held-out roster utility/shape without relying on the synthetic batch as its target.

### Version/docs

Any scorer-semantic change increments `ROSTER_VALUE_VERSION`, the decision engine, model tags/cache keys, and revises ADR-027/029 as appropriate.

## POL-01 — Quantify and, only if material, remove ADR-031 marginal approximation error

**Priority:** P1 policy correctness

**Status:** `DEPENDENT` on RV-00

### Evidence

`_seat_summary()` collapses the roster to season-total seat state. `_terminal_marginal()` and `_roster_feasible_values()` use constant-time cases and do not re-solve weekly bye/availability seating. The authoritative scorer does.

Across 96,366 root candidate-stage rows, the audit found mean absolute marginal error `0.078`; 3,065 rows exceeded one point and 195 were overprices above three. Among 2,384 headlines, 130 exceeded one point. TE rows dominate. This proves a policy-input and evidence-field approximation error. It does not prove recommendation flips or explain every TE2 headline.

### Smallest decision path

1. Add an exact-oracle mode to the existing policy-alignment harness.
2. Count top-per-position changes, future user-pick changes, paired-Q changes, final-headline changes, and latency on the fixed state set.
3. If behavior changes materially, add one shared vectorized “all available candidate marginals for this roster” scorer primitive and reuse it from future policy and opportunity evidence.
4. If recommendation effects are immaterial, retain the hot-loop approximation and make only root user-facing marginal evidence exact or label it approximate.

Do not call `projected_roster_value()` once per player at every simulated future user pick. The policy performs roughly 1.3 million marginal evaluations per 50 continuations; an unprofiled exact loop would worsen an existing release blocker.

### Required checks

- Extend `tests/test_vona.py` to different-bye backups, flex displacement, multiple flex seats, same-position depth, and negative displacement.
- Use `tests/test_roster_value.py` as the oracle.
- Preserve candidate-input-order invariance, deterministic path, chunked-versus-flat, cached-versus-uncached, and ADR-031 survivor-harvest regressions.
- Benchmark representative early, middle, and late states.

### Acceptance

- If replaced, recorded marginal error falls to numerical tolerance.
- The exact path does not materially worsen representative latency, or the measured optimization pays for it.
- Preserve the `5e61ae8e` pick-68 survivor-harvest regression.
- Recompute the 0.1 residual after any alignment change.

### Version/docs

A future-policy change advances the string `VONA_MODEL_VERSION` tag and the decision engine. Amend ADR-031; add a new ADR if a durable vectorized scorer API becomes part of the architecture.

## POL-02 — Resolve bye coverage only after scorer/policy alignment

**Priority:** P2 roster quality

**Status:** `DEPENDENT` on POL-01 and RV-02

### What is and is not known

The full scorer models weekly player availability, so different-bye backups can carry real coverage. The ADR-031 approximation collapses that information. The additive bench term can still value a same-bye backup as an asset. The root objective has no independent preference against stacking several starters on one bye.

The audit found 15/122 same-bye QB2 builds and 28/150 rosters with at least four likely starters on one bye under a projection proxy. It did not establish a local human bye baseline or prove that all such stacks reduce terminal value.

### Work

1. Correct or quantify exact policy/scorer disagreement first.
2. Reaudit same-bye choices.
3. Classify survivors as:
   - **coverage error:** exact different-bye marginal was higher but the policy missed it; or
   - **product preference:** candidates were point-equivalent but the owner wants diversification.
4. Only the second class justifies a new practical-tier bye tiebreak or objective term.

### Required checks

- With equal projections, same- versus different-bye policy marginal matches the scorer.
- A materially better same-bye player can still win on terminal value.
- Intentional same-team correlations remain legal.

### Anti-fix

Do not add a blanket same-bye ban or generic starter-stack penalty.

### Version/docs

An exactness fix amends ADR-031. A new bye-risk preference changes ADR-026/029 product semantics and requires an owner decision, ADR, and engine version.

## URG-01 — Measure complete take-versus-wait and conditional harvest

**Priority:** P1 urgency accuracy

**Status:** `DEPENDENT` on OPP-01 and POL-01; rerun after any promoted RV-01/RV-02 change. Tier-level conclusions additionally depend on OPP-02.

### Why this remains open

Same-generator strict-branch survival was well calibrated in aggregate, but that does not establish human validity. Thirty-five high-confidence runner waits realized as “gone” had a next-board same-position marginal shortfall averaging 4.11 points, with median zero. The next alternative's ADP minus the missed player's ADP averaged `-11.17` picks and had median `-15`. The severe gaps were engine-marginal diagnostics; ADP did not independently confirm market cliffs. This is not complete counterfactual roster regret.

Likewise, the 112 high-survival/low-local-cliff reaches are a review set, not 112 proven mistakes. A candidate can survive often and still have positive expected Q from rare costly losses or portfolio effects.

### Work

1. Extend existing state replay to run both root actions with the same full continuation seeds and flat budget.
2. For each branch record:
   - completed-roster Q distribution;
   - `target_available_count` at the next user turn;
   - `target_selected_when_available_count`;
   - next-turn selected and best same-position alternatives;
   - final roster shape and legality;
   - player-level and tier-level survival when calibrated tiers exist.
3. Stratify by position, round, league context, survival band, paired-Q status, and root alternative.
4. Revisit the 112-state reach set after K/DEF value and opponent calibration change. Do not carry the original labels forward unchanged.
5. Human-score a preregistered sample of remaining high-Q/high-survival disagreements.

### Required named replays

- `2651565d… / :0096 / pick 47`: Jameson Williams over Harold Fannin; Fannin forecast 97.3%, then gone, next-board marginal gap 15.58.
- `4253a402… / :0001 / pick 57`: Jameson Williams over Fannin; forecast 94%, next-board gap 15.58.
- `08955443… / :0064 / pick 19`: Trey McBride over Derrick Henry; forecast 87.3%, next-board RB gap 18.19.
- `394482cd… / :0062 / pick 23`: Derrick Henry over Rashee Rice; forecast 91.3%, next-board WR gap 11.66.
- `8e68b036-02a8-4758-88c2-b6df22258f6a / :0150 / pick 71`: Gadsden/Fannin conditional-harvest case.

### Acceptance

- Model-relative wait/urgency disagreement rates use complete paired branches and draft-clustered intervals; call them human-facing errors only with held-out human outcomes or preregistered human adjudication.
- Survival calibration is reported by position × round × league context on held-out human drafts, not only separate marginal tables.
- Explanations never substitute survival for conditional selection or a next-board marginal gap for final-roster regret.
- Any new urgency feature improves preregistered human adjudication or another external decision criterion without degrading paired-Q value; historical drafts alone cannot reveal counterfactual completed-roster value. Otherwise do not add it.

## TIE-01 — Decide the user-facing headline policy inside practical tiers

**Priority:** P2 product trust

**Status:** `RESEARCH`; keep the 0.1 admission gate during investigation

### Evidence and cause

`recommendation_summary()` forms the practical tier, then orders it by effective urgency and market. This can headline a non-Q leader. In the batch:

- 1,344/2,384 calls were toss-ups;
- median practical tier size was about 34;
- 835 states tied every refined candidate;
- 737 displayed headlines had a lower paired mean than the Q leader;
- 498 had their entire paired interval below the Q leader;
- 298 were worse by at least 0.1 in point estimate.

The current reason code says `VONA_TIEBREAK` whenever the headline differs from the Q leader, even when zero/equal effective urgency means market rank actually decided. The UI's “statistical tie” wording is independently incorrect and is handled by WHY-01.

### Immediate metadata correction

- Expose the Q-leader ID.
- Emit the actual effective tie-break basis: `urgency`, `market`, or engine rank.
- Use distinct reason codes; do not infer urgency from “headline differs.”
- Call the set a “practical toss-up under the 0.1-point decision gate.”

### Research gate before changing behavior

Human-score a preregistered sample containing wholly negative headline intervals, large mean gaps, giant late tiers, and true near-zero gaps. Compare:

1. current practical-tier headline;
2. always headline the Q leader;
3. a two-axis admission rule that also limits expected regret.

Do not derive a second numerical threshold from this synthetic batch. Large late tiers were already anticipated in ADR-021; their prevalence is new, not the underlying phenomenon.

### Acceptance

- Reason codes and UI identify the Q leader and true tie-break source.
- A behavior change is supported by human scoring or held-out product evidence, not intuition alone.
- Any changed rule preserves coupled paired comparison and is preregistered before a confirmatory batch.

### Version/docs

Metadata/copy changes do not bump the engine. Changing tier admission or headline selection does and requires an ADR.

## PERF-01 — Remove the early-round latency tail without weakening inference

**Priority:** P1 release blocker

**Status:** `DEPENDENT` on TEL-02 and RACE-01

### Evidence

- Ready median 9.172 seconds, P95 20.107, maximum 26.592.
- 1,068/2,384 calls exceeded 10 seconds; 124/2,384 exceeded 20.
- All >20-second calls occurred in rounds 1–5: 124/750 early states.
- Broad-screen median was 7.208 seconds; refinement added median 1.381.
- The prior v7 batch had nearly the same >20-second rate.
- The recorded synthetic `screen` event is the completed broad screen, not the first nine-candidate publication, so the warm first-board target is currently unmeasured.

### Hot-path candidates, not yet conclusions

- `LiveDraftMonitor.calculate()` evaluates the first nine and the remainder as sequential phases.
- `evaluate_live_candidates()` fans one 100-rollout task per screen candidate across 12 workers.
- Early states simulate the longest remaining draft.
- Every future user turn invokes terminal-marginal/hazard planning.
- `evaluate_candidates()` blocks primary Q publication on secondary season outcome evaluation.

### Required investigation order

1. Land TEL-02 and measure browser-perceived first-board, full-screen, and ready latency separately on warm cache.
2. Land RACE-01 and establish the corrected work budget before optimizing it.
3. Profile deterministic early, middle, and late states with identical seeds, candidate sets, 300×14 budget, cache mode, and worker count.
4. Attribute time among continuation/opponent loop, future-user policy, roster scorer, secondary season evaluator, serialization, and process scheduling.
5. Apply only the first exact optimization supported by the profile:
   - reuse or batch existing immutable inputs;
   - remove avoidable object copies;
   - improve worker utilization across first/remainder screening;
   - or publish primary Q before asynchronously filling secondary season telemetry if secondary evaluation is material.
6. Re-run flat/racing, chunked/flat, deterministic-path, and cached/uncached equivalence.

### Acceptance

- Warm first useful board is at most two seconds under the browser/state-change clock.
- Ready median is at most ten seconds and no representative/full-batch result exceeds 20 seconds.
- Exact optimizations produce zero headline, status, practical-tier, and value changes.
- If secondary telemetry is deferred, final values remain identical and the UI exposes the incomplete secondary state.

### Anti-fixes

- Do not reduce candidates, rollout continuations, season worlds, or coupling merely for latency.
- Do not rely on speculative hits to satisfy baseline latency.
- Do not introduce GPU work or a dependency before CPU profiling identifies a suitable bottleneck.

### Version/docs

An exact scheduling optimization does not bump the engine. Splitting primary and secondary publication is a durable product contract and requires an ADR, but not an engine bump if decision math remains identical.

## REL-01 — Validate and release promoted slices

**Priority:** P0 release

**Status:** `DEPENDENT` on each promoted slice's own gate

### Promotion order

Do not wait for every research idea in this ledger. Promote only coherent changes that pass their own gate:

1. telemetry concurrency and compact stage events;
2. racing/final-gate equivalence;
3. truthful payload and Why copy;
4. faithful market context and human validation harness;
5. the smallest held-out-calibrated opponent change;
6. the smallest validated K/DEF/scorer change;
7. only causally supported replacement, bench, or future-policy changes;
8. exact performance work;
9. headline-policy behavior only if its research gate passes.

Each behavior-changing slice should be independently reviewable and versioned. Do not bundle racing, opponent, scorer, and UI behavior into one commit or one uninterpretable batch comparison.

### Verification ladder

For each slice:

1. Run the narrow unit and invariant tests named by its work item.
2. Run fixed-state common-seed replays.
3. Run the full Python suite:

   ```text
   .venv/bin/python -W error::ResourceWarning -m unittest discover -s tests
   ```

4. For web changes, run:

   ```text
   cd web
   npm test
   npm run build
   ```

5. Run `git diff --check`.
6. When execution or telemetry changes, run one draft for event-contract inspection and then one pass across the 22 unique template/slot scenarios.
7. Before a behavior-changing release, freeze code, model artifacts, thresholds, and hypotheses, then run a fresh 150-draft confirmatory batch. Do not draw conclusions from a partial run.

### Gates for every promoted slice

- Narrow and full relevant suites pass, with no new resource warnings or unexplained environment errors.
- All touched deterministic, normalization, legality, and cache invariants pass.
- Version and ADR consequences are handled for that slice only.
- Unrelated data-blocked work remains explicitly uncalibrated; it does not block a telemetry-, racing-, or copy-only release.

### Telemetry, racing, and explanation gates

- TEL-01 passes its concurrent-reader commit test and remains fail-visible.
- TEL-02 stage/ready identities and conditional-selection count invariants pass.
- RACE-01 has zero racing-versus-flat mismatches on the preregistered v7 corpus.
- WHY-01 payload and frontend branch-semantic assertions pass.
- Report latency and external-accuracy metrics as non-regression evidence; do not require unrelated held-out opponent/scorer calibration for these slices.

### Opponent, market, scorer, and policy gates

- VAL-01 provides time-local, held-out human evidence for any promoted opponent or market-calibration artifact.
- Opponent reach tails, position timing, and roster shape meet held-out human intervals; synthetic results remain secondary.
- Human survival calibration includes sample counts and intervals by position × round × context before a claim ships; aggregate or suppress underpowered cells rather than implying unsupported precision.
- K/DEF and roster-timing rates meet preregistered human-comparator tolerances before the responsible scorer/policy change is promoted.
- The promoted ablation improves its named external metric without breaking legality, paired-Q identities, deterministic replay, or cache equivalence.

### Performance gates

- Warm first-board and ready latency meet PERF-01 only when performance work is promoted.
- Exact performance changes have zero decision-output differences.

### Confirmatory-batch gates for behavior changes

- 150/150 complete; zero failed, orphaned, malformed, wrong-version, or recommendation-following sessions.
- All final rosters legal and all caps preserved.
- Zero paired-Q identity, stage/ready, deterministic-replay, or cache-equivalence failures.
- Applicable human-facing alerts below pass for the behavior changed by the slice.
- The full report lists any remaining “a human would not do this” states with session, draft, pick, players, and numbers.

### Provisional human-facing alerts

These are release alerts, not parameters to optimize:

- K/DEF before dedicated core: at most 5% of drafts pending a larger human baseline.
- Backup QB/TE while a dedicated RB/WR starter hole remains: at most 5%.
- TE2-before-QB1: at most 5%.
- Core completion: median no later than matched-human median plus one round; P90 no later than plus two.
- First K/DEF median: within approximately one round of exact-format human medians.
- Extreme RB/WR final counts: within draft-clustered held-out human prediction intervals.

The current human sample is small and correlated. If a larger, exact-context sample changes these bands, update the preregistration before the confirmatory run, not after seeing its result.

### Versioning checklist

Before a behavior-changing release:

- advance `DECISION_ENGINE_VERSION` from its current value for each behavior-changing release; version 7 is this audit's baseline;
- increment `ROSTER_VALUE_VERSION` if scorer semantics change;
- advance the string `VONA_MODEL_VERSION` tag if future-user policy semantics change;
- version opponent artifacts and invalidate dependent caches if the room distribution changes;
- record training cutoff, artifact hash, league context, proxy reasons, and calibration status;
- add or amend ADRs for racing equivalence, market/opponent calibration, scorer semantics, future-policy exactness, and any changed headline policy;
- update `IMPLEMENTATION_LEDGER.md` with actual completed work and validation, not this plan.

## Explicitly deferred work

The following ideas do not yet earn implementation:

- manager personalization: current profiles are descriptive-only and have no held-out lift;
- a new tier engine: existing tier/depletion hooks are sufficient once calibrated inputs exist;
- hard positional schedules, bans, or RB/WR caps;
- a bespoke trade-value model solely to justify current UI copy;
- GPU simulation or a new performance dependency;
- a new practical-tie threshold derived from the synthetic batch;
- a general bye-stack penalty without an owner preference and exact policy/scorer evidence.

## Handoff checklist for the implementing agent

- [ ] Repeat the mandatory startup sequence and inspect local unpublished work.
- [ ] Treat the source audit, audit tools, and batch ID as the immutable v7 baseline.
- [ ] Start with TEL-01/TEL-02; never run long reads against a live rollback-journal database.
- [ ] Implement RACE-01 as a shared predicate, not two synchronized copies.
- [ ] Keep WHY-01's branch labels exact even if conditional-selection telemetry is not yet available.
- [ ] Do not tune OPP-01 until VAL-01 has time-local human data.
- [ ] Run RV-00 before selecting any scorer, replacement, bench, or policy change.
- [ ] Keep K/DEF display artifacts separate from clear completed-roster Q behavior.
- [ ] Reassess reach and roster rates after opponent and K/DEF changes before adding more policy.
- [ ] Profile before optimizing latency; preserve statistical budgets and coupling.
- [ ] Make one coherent commit per promoted slice, with narrow tests and version/docs updates.
- [ ] Run the 22-scenario smoke grid before committing another six-hour 150-draft batch.
- [ ] Preregister the final metrics, then run and audit the complete batch.

## Workspace handoff

At investigation close, the branch has no modified tracked files. These audit artifacts are untracked local work and must be preserved deliberately:

- `docs/draft-intelligence/archive/audits/AUDIT_20260815T043426-52dba2d4.md`;
- this remediation ledger;
- `tools/audit_synthetic_batch.py`;
- `tools/audit_synthetic_deep_metrics.py`;
- `tools/audit_synthetic_state.py`.

Do not fold them into an unrelated implementation commit or overwrite them while preparing a clean worktree.

## Investigation validation

This ledger was produced from source tracing, the full version-7 audit, fixed-state replay evidence already recorded by the audit tools, and read-only diagnostic checks. During the remediation investigation:

- `.venv/bin/python -m ffsim market-backtest` confirmed the zero-scored-draft data blocker described in VAL-01;
- `tests.test_roster_value` and `tests.test_vona` passed 27/27 in the roster-value investigation;
- 45 combined roster-value/live tests completed without assertion failure; two multiprocessing cases could not start because the sandbox denied semaphore creation;
- no engine, policy, scorer, frontend, test, implementation-ledger, or decision-log file was changed.
