## 28. Testing Strategy

### 28.1 Unit tests

Cover:

- snake pick-number/slot mapping
- turn/back-to-back picks
- traded pick ownership
- draft deduplication
- keeper exclusion
- available-player reconstruction
- opportunity counting
- historical market snapshot selection
- manager feature calculation
- player-affinity shrinkage
- softmax/choice normalization
- deterministic stable random-shock generation
- tier survival calculations
- roster legality
- user rollout policy
- next-turn opportunity cost under different ownership gaps and opponent distributions
- adjacent-pick turn grouping and scarce-but-inferior-player rejection
- world-bank hash/invalidation
- lineup optimizer parity
- replacement-level logic
- recommendation reason codes

### 28.2 Property tests

Examples:

- no player can be drafted twice in one rollout
- all picks have exactly one owner
- all completed draft rosters satisfy hard roster limits
- live continuations fill every required starter seat by the final pick
- one-QB/one-TE continuation policies do not exceed their configured backup caps
- survival probability is within [0,1]
- threat shares sum to 1 conditional on elimination
- same seed + same inputs produces identical rollout results
- candidate order should not change merely because root candidates are evaluated in a different loop order

### 28.3 Integration tests

Use frozen Sleeper/API fixtures:

- 10-team normal snake
- 12-team snake
- 1QB PPR
- superflex fixture even if not fully optimized initially
- keeper league
- traded picks
- shared league-mate history
- manager with no historical drafts
- manager with multiple current-season drafts
- stale/missing market source

### 28.4 Live dry-run mode

Support replay of a completed historical draft as if it were live:

```text
python -m ffsim draft-replay --draft-id ... --delay 0
```

This is essential for validating UX and latency without waiting for a real draft.

### 28.5 Performance regression tests

Track benchmark fixtures and fail/warn on major regressions in:

- world generation throughput
- draft rollouts/sec
- league evaluations/sec
- recommendation latency
- memory use

---

## 29. Failure Modes and Edge Cases

| Case | Required behavior |
|---|---|
| Manager has no historical data | Market/population prior only; confidence low |
| Manager has one 2026 draft | Small contextual adjustment; strong shrinkage |
| Same draft found through 5 managers | Fetch/store once; associate participants; no duplicate evidence |
| Player already gone in historical draft | No manager-player opportunity evidence |
| Manager repeatedly passed available player | Negative affinity evidence, context-weighted |
| Keeper pick | Fixed roster state; exclude from voluntary preference training |
| Dynasty/rookie draft | Separate context; exclude from redraft affinity by default |
| Auction | Unsupported by snake engine; explicit message |
| Traded picks | Use actual current pick owner |
| Missing target board rank | Fall back to target-platform ADP; flag assumption |
| One ADP provider unavailable | Reweight remaining sources; keep cached snapshot |
| All external market sources unavailable live | Continue from last good snapshot |
| Sleeper live poll fails | Manual pick mode + backoff + later reconciliation |
| Player ID ambiguous | Fail closed / manual mapping; never silently merge |
| New injury/news during draft | Update source snapshot, invalidate affected worlds/value if material |
| Draft paused | Continue background refinement but stop assuming clock urgency |
| Unknown fantasy schedule | Sample schedules or use explicit schedule-neutral fallback |
| Probable board follower | Strong target-platform prior, but label inference rather than intent |
| Co-managed team | Model roster/team identity; do not assume which person made a pick |
| Short pick timer | Serve speculative fast result immediately; continue refinement |
| World bank stale after major projection update | Rebuild or explicitly use stale bank with warning; never silently mix |
| User manual fade conflicts with title-optimal result | Respect configured hard/soft override and show conflict |
| Player lacks projection | Exclude from title optimization unless a manual/alternate projection is supplied; still model opponent likelihood if market data exists |

---

## 30. Security, Privacy, Licensing, and Source Discipline

### 30.1 Local-first

Store league history, manual manager notes, API keys, and recommendation history locally by default.

### 30.2 Secrets

- Never commit API keys.
- Use environment variables or OS keychain-compatible secret storage.
- Scrub secrets from logs and diagnostic exports.

### 30.3 Public vs authorized data

Sleeper's documented public read-only API can provide league/draft information without authentication. Other platforms may require OAuth or only expose private league data to authorized users. Do not bypass platform access controls.

### 30.4 FantasyPros licensing

The implementation must respect the active API tier. Personal/non-commercial use and commercial/high-volume/redistribution have different requirements. The tool should record source attribution metadata and avoid redistributing raw licensed datasets.

### 30.5 No fragile scraping as a core dependency

If a useful platform-specific ADP exists only on a web page and automated use is not clearly supported:

- prefer official API
- prefer permitted export
- permit manual user import
- treat scraping as a research/legal decision, not an implementation shortcut

---

## 31. Phased Implementation Plan

### Phase 0 - Repository audit and benchmarks

Before changing architecture:

- pull/review the user's local commits that are newer than GitHub `main`
- run current test suite
- benchmark current `teams-only` engine on target M5 hardware for 10- and 12-team leagues
- profile `SimulationSeason.simulate`, player generation, lineup selection, standings, and playoffs
- record baseline memory and throughput

**Exit criteria:** reproducible benchmark report and no unknown local changes that would be overwritten.

### Phase 1 - Draft data audit CLI

Build a read-only command:

```text
python -m ffsim draft-audit --league-id ...
```

Output:

- current managers
- unique historical drafts found
- same-season draft counts per manager
- prior-season draft counts
- shared drafts deduplicated
- draft format breakdown
- keeper/dynasty/auction exclusions
- canonical player match rate
- exact historical ADP coverage
- personalization confidence estimate

**Purpose:** prove the real data volume before building the model.

### Phase 2 - Market snapshot subsystem

Implement:

- source adapter interface
- FantasyPros official API adapter
- manual CSV adapter
- target-platform ADP adapter if a supported source is confirmed
- append-only snapshot store
- canonical player mapping
- freshness/status UI

**Exit criteria:** can reconstruct the market snapshot used for any stored test draft time when data exists.

### Phase 3 - Historical manager profiles

Implement:

- draft normalization
- available-set reconstruction
- opportunity-adjusted player affinity
- repeated-pass evidence
- position timing
- board adherence/temperature
- roster-construction features
- context weights
- manual signals
- confidence reporting

Start with transparent heuristics.

**Exit criteria:** manager cards are explainable and pass unit tests; no machine-learning dependency required yet.

### Phase 4 - Live draft state + survival simulator

Implement:

- target draft polling
- exact pick ownership
- traded picks
- live roster state
- sequential opponent sampling
- next-pick survival
- tier survival
- threat shares
- room-level shifts
- dry-run draft replay

**Exit criteria:** on historical replay, live state exactly matches completed draft and survival model beats simple target-ADP baseline or clearly reports when it does not.

### Phase 5 - Cheap user decision engine

Before championship integration, implement:

- league-specific value
- VONA
- wait/reach labels
- two-pick continuation heuristic
- candidate racing framework
- speculative precompute

This provides a useful War Room while the deeper `ffsim` refactor is underway.

### Phase 6 - SeasonWorldBank extraction

Refactor current `ffsim`:

- separate correlated player/NFL world generation
- store score tensor + metadata
- preserve scenario/injury/game/team/competition effects
- include full draftable pool
- build immutable world-bank API

**Exit criteria:** generated worlds reproduce current player/team distribution behavior within defined tolerances.

### Phase 7 - Lightweight LeagueEvaluator

Implement roster-index based evaluation:

- lineup optimization
- weekly team scores
- fantasy schedule
- standings
- playoffs
- championship

Validate against current `ffsim` on fixed rosters and common worlds.

**Exit criteria:** parity tests pass and evaluator throughput is sufficient for live candidate racing.

### Phase 8 - Full nested rollout championship optimizer

Connect:

```text
root candidate
-> coupled rest-of-draft rollout
-> full roster assignment
-> shared season world
-> league evaluator
-> paired title outcome
```

Add:

- adaptive allocation of draft vs season samples
- paired deltas
- confidence intervals
- root candidate racing
- expected next-pick combinations
- wait/reach based on championship branches

**Exit criteria:** live recommendation is available within performance budget and passes deterministic replay.

### Phase 9 - Learned opponent model + calibration

Only after baseline instrumentation exists:

- fit regularized conditional-choice model
- compare to heuristic baseline
- calibrate survival probabilities
- personalization gating
- ablation tests

Do not ship a learned model merely because it has better in-sample likelihood.

### Phase 10 - Optional GPU / multi-league enhancements

Profile first, then consider:

- Numba/JAX/CUDA backend
- remote 3090 compute service
- raw-stat world bank shared across scoring systems
- Yahoo/Fleaflicker league connectors
- multi-league portfolio exposure
- more advanced manager models

---

## 32. Acceptance Criteria and Release Gates

### 32.1 Data correctness

- No duplicate historical draft counting.
- No duplicate player selection in simulated drafts.
- Keepers correctly distinguished.
- Traded pick owner sequence correct.
- Historical player opportunity sets reconstruct correctly.
- Market snapshot timestamps preserved.
- Ambiguous player IDs do not silently resolve.

### 32.2 Predictive quality

- Personalized survival model is benchmarked against target-platform ADP baseline.
- Calibration metrics are produced.
- Personalization is gated when weak.
- Tier-survival predictions are validated.

### 32.3 Season simulation correctness

- New world-bank/evaluator path matches existing `ffsim` behavior on frozen fixtures within agreed tolerance.
- Shared world generation preserves game/team/competition correlations.
- Same inputs/seed reproduce same results.

### 32.4 Live usability

- Draft state updates automatically.
- Fast recommendation arrives within target latency from warm state.
- User can see exact picks until next turn.
- User can see why a player is a take/wait/reach.
- User can see primary manager threats.
- Manual recovery works without network sync.

### 32.5 Reproducibility

Every stored recommendation records:

```text
league/draft state hash
completed pick prefix
market snapshot IDs
manager model version
projection/world-bank hash
rollout policy version
root candidate set
random seed family
sample counts
result metrics
```

A debug command must be able to replay a stored recommendation.

---

## 33. Implementation Guardrails for the Coding Agent

1. **Inspect local repository state before refactoring.** GitHub `main` may not include the newest local commits.
2. **Do not rewrite `ffsim` wholesale.** Extract clean boundaries while preserving current CLI/API/tests.
3. **Build baselines before sophisticated models.** A transparent market + need model is required for comparison.
4. **No data leakage in backtests.** Use only information available at the historical decision time.
5. **Do not treat source-specific ADP availability as established until verified.** Especially verify exact FantasyPros per-platform API fields and ESPN sourcing.
6. **Do not scrape as a shortcut without explicit approval and terms review.**
7. **Do not use an LLM to generate probabilities.**
8. **Do not deep-copy mutable league/player object graphs inside the hot rollout loop.**
9. **Do not evaluate partial draft rosters as terminal championship rosters.**
10. **Do not discard shared drafts; deduplicate them and model their shared context.**
11. **Do not interpret three selections out of three as certainty.** Use shrinkage and show evidence counts.
12. **Do not compare historical reaches to today's ADP when a time-local snapshot exists.**
13. **Do not show a `TAKE NOW` recommendation without preserving the underlying candidate metrics and reason codes.**
14. **Do not optimize GPU code before profiling the refactored CPU path.**
15. **Preserve common random numbers across candidate comparisons whenever practical.**

---

## 34. Required Research Tasks Before/During Implementation

The implementation agent should explicitly investigate and document these items rather than guessing:

### Data/API research

- Verify Sleeper 2026 draft metadata shapes on real target leagues, including draft order, slots, keepers, and traded picks.
- Determine whether Sleeper exposes a stable official target draft-room/default player ordering distinct from ADP. If not, document the proxy used.
- Verify exact FantasyPros official API payloads for 2026 ADP/ECR and whether source-specific Yahoo/ESPN/Sleeper/etc. ADPs are available through the API key tier being used.
- Verify rate limits and caching expectations for every market provider.
- Research a stable, permitted ESPN-specific ADP source; make it optional if none exists.
- Verify Yahoo OAuth scopes and which draft-history data is accessible for leagues the user is authorized to view.
- Verify Fleaflicker player external-ID support and draft-board history behavior.

### Modeling research

- Quantify actual number of relevant drafts and picks per target manager.
- Determine which manager features have enough support to estimate reliably.
- Backtest current-season-only vs multi-year weighting.
- Compare raw pick frequency with opportunity-adjusted affinity.
- Measure how predictive default-board adherence is.
- Estimate ADP dispersion by range/position/format from available draft data.
- Determine whether cross-platform ADP spread predicts draft variance.
- Determine whether live room shifts materially improve survival calibration.

### Simulation research

- Profile current `ffsim` on M5 Max.
- Measure time spent in player world generation vs lineup/league evaluation.
- Determine minimum world-bank player pool for negligible truncation error.
- Compare score-bank float32 vs float64 results.
- Benchmark memory mapping vs in-memory arrays.
- Measure draft-uncertainty vs season-uncertainty contribution by round.
- Determine optimal candidate racing sample schedule.
- Validate common-random-number variance reduction empirically.
- Evaluate whether Numba materially improves lineup/league evaluation before considering GPU.

### Product research

- Determine actual pick timers in the user's leagues and set latency budgets accordingly.
- Test War Room layout in a real draft replay with the user.
- Identify which explanation fields are useful under time pressure and hide low-value diagnostics behind detail panels.

---
