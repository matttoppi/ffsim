## 18. Caching, Memoization, and State Hashing

Caching is a core architectural requirement for live use, not an optional late optimization. The engine repeatedly evaluates overlapping states while the underlying projections, league rules, manager profiles, and season worlds change much less frequently than the live draft board. The implementation must reuse deterministic work aggressively while making stale-result reuse impossible.

### 18.1 Design goals

The caching subsystem must:

- make a useful recommendation available immediately or very shortly after each real pick
- preserve expensive work across root candidates when the relevant state is identical
- preserve expensive work across live-pick updates when the cached state's assumptions still hold
- separate long-lived pre-draft artifacts from short-lived live-draft search artifacts
- use deterministic, versioned keys rather than object identity or mutable Python object hashes
- make invalidation explicit and testable
- bound memory use and expose cache-hit/miss/eviction metrics
- never change statistical semantics merely to obtain a cache hit

The primary rule is:

> Cache the result of a pure computation keyed by all inputs that can change that result. If those inputs cannot be represented completely and deterministically in the key, do not reuse the result.

### 18.2 Cache hierarchy

Use distinct caches with different lifetimes and invalidation rules.

**Long-lived snapshot/precomputation cache**

Examples:

- normalized player identity mappings
- league-scoring compilation
- league-specific rescored projections
- ADP snapshots and normalized ADP distributions
- historical draft normalization and opportunity sets
- manager feature vectors and player-affinity posteriors
- player tiers and replacement-level support data
- precomputed NFL schedule/matchup context

These can persist across application restarts and should be versioned by their source snapshot timestamps/hashes and model version.

**SeasonWorldBank cache**

The expensive player/NFL outcome tensor or equivalent immutable world representation must be generated once for a compatible input version and reused across root candidates, future-draft continuations, and candidate-refinement passes.

A conceptual key is:

```text
SeasonWorldBankKey = hash(
    league_scoring_version,
    projection_snapshot_version,
    injury_snapshot_version,
    nfl_schedule_version,
    matchup_model_version,
    scenario_version,
    world_generator_version,
    seed_family,
    world_count
)
```

A new real fantasy draft pick does **not** invalidate the world bank because player football outcomes do not depend on fantasy roster ownership. A projection, injury, schedule, scoring, or world-generation-model change does.

If the requested final-pass world count is larger than an existing bank, prefer deterministic extension of the same seed family when technically practical rather than regenerating unrelated worlds.

**Live opponent-choice cache**

Cache manager choice distributions when the exact decision state is identical. The key should include at minimum:

```text
OpponentChoiceKey = hash(
    manager_id,
    pick_no,
    manager_roster_signature,
    available_player_bitset_hash,
    league_format_version,
    target_platform_market_version,
    manager_model_version,
    live_room_adjustment_version,
    manual_intelligence_version
)
```

Do not key only on round or roster need. Two states with the same positional counts but different available players can have materially different choice probabilities.

**Draft transposition cache**

The remaining-draft process forms a huge tree, but different pick sequences can converge to the same meaningful state. If two paths produce the same next pick owner, available pool, and roster assignments, all future transition probabilities are the same under the same model versions and coupled-randomness inputs.

Represent an exact state fingerprint such as:

```text
DraftStateKey = hash(
    next_pick_no,
    pick_owner_schedule_version,
    available_player_bitset,
    canonical_roster_assignment,
    keeper_and_traded_pick_state,
    league_format_version,
    opponent_model_version,
    live_room_adjustment_version,
    manual_intelligence_version
)
```

Example convergence:

```text
Path A: Chris selects WR X, Dan selects RB Y
Path B: Dan selects RB Y, Chris selects WR X

If both paths now have the same roster assignments, available pool, and next picker,
they are the same future decision problem and should share one continuation evaluation.
```

This is an **exact transposition**, not an approximation. Root-candidate identity need not be part of the transition key when the complete resulting state already captures its consequences; root identity should remain attached to accounting/statistics outside the cached pure transition result.

**Completed-roster season-evaluation cache**

A completed fantasy roster assignment evaluated against a fixed world bank should never be recomputed unnecessarily.

```text
RosterEvaluationKey = hash(
    world_bank_version,
    canonical_roster_assignment,
    league_schedule_or_schedule_world_version,
    playoff_rules_version,
    league_evaluator_version,
    replacement_level_version
)
```

The cached result may include championship/playoff outcome vectors by world rather than only aggregate percentages. Keeping the per-world outcome vector allows paired candidate deltas and uncertainty calculations to be derived later without rerunning the evaluator.

**Candidate/search cache**

Store intermediate root-candidate estimates, rollout samples, confidence intervals, and sufficient statistics keyed by the exact live state plus model/world versions. This enables progressive refinement: a 200-sample screening result can be extended to 1,000 samples instead of restarted.

### 18.3 Canonical state representation

Cache correctness depends on canonicalization. Never hash mutable object addresses, unordered Python containers without normalization, display names, or fields that can differ while representing the same logical state.

Recommended representations:

- assign every fantasy-relevant player a stable dense integer index
- represent the available pool as a fixed-length bitset or packed integer array
- represent each roster as a sorted tuple/array of canonical player indices
- represent all rosters in stable roster-ID order
- represent draft pick ownership as a stable pick-number-to-roster-ID array
- represent model/source versions with content hashes or immutable version IDs
- use a stable serialization format before hashing

A hash collision must never silently produce an incorrect result. For high-value caches, store enough canonical key material alongside the hash to verify equality on lookup, or use a collision-resistant digest such as BLAKE2/BLAKE3/SHA-256 with deterministic serialization.

### 18.4 Incremental invalidation matrix

Invalidation should be dependency-driven rather than `clear_all()` by default.

| Event | Preserve | Invalidate / supersede |
|---|---|---|
| New real draft pick | projections, ADP snapshots, manager historical features, SeasonWorldBank | cached branches incompatible with the new available pool/rosters; obsolete root-state summaries |
| Unexpected position run | SeasonWorldBank, historical features | live-room-adjusted choice distributions and descendant draft-state results whose live-room version changed |
| Manual note added/edited | SeasonWorldBank, projections | affected manager choice cache and descendant draft states using the prior manual-intelligence version |
| ADP refresh | SeasonWorldBank if football inputs unchanged | market-derived choice distributions, player market features, downstream draft-continuation caches |
| Projection update | historical manager model, ADP | league-specific value calculations, SeasonWorldBank, roster evaluations, candidate championship results |
| Injury/news update affecting player model | historical manager model, raw ADP | player value, SeasonWorldBank, roster evaluations, candidate championship results |
| League scoring/rules change | raw historical picks/ADP snapshots | rescoring, values, world bank where scoring affects generated scores, evaluator, all recommendation outputs |
| Opponent-model code/version change | SeasonWorldBank | manager-choice, draft-continuation, candidate-search caches |
| League-evaluator code/version change | draft-history/manager model, world bank if representation remains compatible | roster-evaluation and downstream candidate-result caches |

A new live pick should therefore behave approximately like:

```text
new real pick
-> update canonical draft state
-> keep immutable source/model artifacts
-> keep compatible SeasonWorldBank
-> keep exact transposition/evaluation entries that remain reachable and version-compatible
-> prune or naturally stop referencing incompatible branches
-> continue/refine candidate work from the new state
```

Do not physically delete every unreachable entry synchronously on the draft clock. Logical versioning plus bounded eviction is preferable unless memory pressure requires immediate reclamation.

### 18.5 Progressive memoization and sufficient statistics

Candidate racing should accumulate results rather than rerun them.

For each candidate retain sufficient statistics such as:

- number of joint draft/season samples
- weighted sum and weighted squared sum of championship outcomes/deltas
- rollout likelihood/importance-weight totals where applicable
- draft-path conditional equity summaries
- tier-survival counts
- threat-manager elimination counts
- per-world paired outcome vectors when needed for exact paired comparisons

If Pass 1 evaluated 200 samples and Pass 2 requests 1,000, generate the next 800 deterministic sample IDs. Do not repeat the first 200.

The same principle applies to world-bank size and draft-rollout count when deterministic extension is possible.

### 18.6 Coupled-randomness compatibility

Memoization must preserve the coupled-randomness scheme from Section 14. A cache hit must return results for the same deterministic rollout/world identifiers expected by the caller.

Do not cache only an aggregate `18.4% championship probability` when a later paired comparison requires the world-by-world outcomes. Prefer caching reusable sufficient detail at the lowest expensive boundary and aggregating upward.

Stable random identifiers should be derived from immutable coordinates such as:

```text
(base_seed, root_state_version, rollout_id, pick_no, manager_id, player_id)
(base_seed, world_id, player_id, week)
```

Caching must not alter which random variate a logical sample receives.

### 18.7 Exact memoization versus approximate state aggregation

**V1 must use exact memoization only.**

Approximate aggregation - for example treating two states as equivalent because they have the same positional counts and similar remaining tiers - may eventually reduce compute, but it changes the modeled process and can bias recommendations. It is a model approximation, not caching.

If approximate state aggregation is researched later:

- isolate it behind a feature flag
- measure recommendation-order disagreement against exact evaluation
- quantify championship-equity error
- never mix approximate and exact cache entries under the same key namespace
- disable it automatically when the top candidates are close

### 18.8 Memory policy and storage tiers

Use a bounded hierarchy rather than allowing the live search to consume unbounded RAM.

Suggested tiers:

1. **In-memory hot cache:** current live-state opponent distributions, active transposition table, candidate sufficient statistics, hot roster evaluations.
2. **Memory-mapped/array-backed world bank:** large immutable numerical tensors when appropriate.
3. **Persistent local cache/database:** historical features, normalized source snapshots, model artifacts, optional completed-roster evaluations worth preserving across sessions.

For in-memory caches:

- use configurable size/memory limits
- prefer LRU/LFU or generation-based eviction for unreachable old draft states
- pin the current state's active candidate work during the user's clock
- expose bytes/entry counts, not only object counts
- avoid retaining large Python object graphs when compact NumPy arrays/bitsets suffice

On the M5 Max with 48 GB unified memory, memory is generous but should still be treated as finite because large world banks and Python object overhead can grow quickly. The implementation should benchmark actual bytes per world, per roster evaluation, and per transposition entry before selecting defaults.

### 18.9 Concurrency and cache safety

Multiple candidate workers may request the same expensive value concurrently. Avoid duplicate work and partially written entries.

Requirements:

- use single-flight/request coalescing for expensive identical keys where practical
- publish cache entries only after successful complete computation
- immutable cache values are strongly preferred
- worker-local caches may be used for extremely hot tiny computations, but shared expensive results need a controlled shared layer
- cache failures/exceptions only deliberately and briefly; do not persist transient API/network failures as valid data
- multiprocessing serialization overhead must be measured before introducing a central manager-process cache

The preferred architecture may differ between the M5 Max CPU implementation and a future vectorized/GPU evaluator. Profile rather than assuming a shared Python dictionary is optimal.

### 18.10 Persistence and reproducibility

Every persisted computed artifact should record:

- artifact type
- schema version
- model/code version
- complete dependency version set
- creation time
- seed/seed-family metadata when stochastic
- sample/world counts
- content hash where useful

A recommendation snapshot must be reproducible from its stored input versions, seeds, and model versions. Cache presence or absence may affect runtime, but it must not change the mathematical result for a fixed deterministic run.

### 18.11 Observability

Expose cache metrics in development/profiling mode:

```text
cache_name
lookups
hits
misses
hit_rate
evictions
entries
estimated_bytes
compute_time_avoided_ms
compute_time_spent_on_misses_ms
single_flight_collisions
stale/version_mismatch_rejections
```

Also measure end-to-end reuse:

- percentage of candidate evaluation time spent generating new season worlds
- percentage spent on new draft continuations
- transposition-table hit rate by round
- completed-roster evaluation hit rate
- fraction of speculative pre-clock work reused after each real pick

Do not optimize for hit rate alone. A cache with a 99% hit rate on trivial operations can be less valuable than a 20% hit rate on an expensive roster evaluation.

### 18.12 Correctness tests and release gates

Caching needs explicit tests because stale-state bugs can silently produce convincing recommendations.

Required tests:

1. Identical canonical draft states produce identical state keys regardless of insertion/order history.
2. Materially different available pools or roster assignments never produce the same verified key.
3. A new live pick preserves the SeasonWorldBank but prevents reuse of incompatible draft-state results.
4. Updating a manager model invalidates affected opponent-choice/draft-continuation results but not unrelated football worlds.
5. Updating projections or injuries invalidates world-bank-dependent championship evaluations.
6. Cached and uncached execution produce bit-for-bit identical results for deterministic test fixtures where feasible, otherwise numerically identical outputs within an explicitly justified tolerance.
7. Progressive refinement from 200 -> 1,000 samples produces the same sample set/result as a clean deterministic 1,000-sample run.
8. A transposition reached through two legal pick orders returns the same future distribution/evaluation.
9. Cache eviction changes latency only, never recommendation mathematics.
10. Corrupted, schema-mismatched, or dependency-version-mismatched persistent entries are rejected rather than silently loaded.
11. Coupled candidate comparisons retain the same rollout/world IDs after cache hits.
12. Concurrent identical expensive requests compute once or return equivalent complete values without race-dependent partial state.

### 18.13 Initial performance targets

Benchmark before locking numbers, but the implementation should aim for:

- no historical-feature recomputation on the live draft clock
- no SeasonWorldBank regeneration because of an ordinary fantasy draft pick
- no duplicate completed-roster evaluation within the same compatible world bank
- immediate reuse of speculative candidate work when the new real pick leaves that work state-compatible
- measurable transposition reuse in the middle/late draft where state convergence is more common
- recommendation latency dominated by genuinely new uncertainty sampling, not repeated deterministic preprocessing

If profiling shows a large share of live latency comes from a deterministic function that repeatedly receives identical inputs, it should be treated as a caching/memoization defect until proven otherwise.

---
