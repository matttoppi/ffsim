# Historical Draft Value Network

## Status

HDVN-00 through HDVN-05 are complete on the accepted 2026-08-28 source
snapshot. HDVN-06 rejected one fixed completed-draft model under its
predeclared 2024 gate. The separately approved HDVN-R01 training-year
residual-alpha audit also found no stable correction beyond the historical
market baseline. HDVN-07 remains blocked. No HDVN model is live-eligible.

Implementation work is tracked in
[`HDVN_IMPLEMENTATION_LEDGER.md`](HDVN_IMPLEMENTATION_LEDGER.md). The durable
separation decision is ADR-040 in [`DECISIONS.md`](DECISIONS.md).

## Purpose

The Historical Draft Value Network (HDVN) tests whether historical draft states contain outcome signal that is not already captured by market value, simple roster-construction rules, or the current `ffsim` projection and rollout system.

The project has two research artifacts:

1. **Completed-draft outcome score:** Score and rank completed team drafts from draft-time information.
2. **Partial-draft value experiment:** Estimate the expected historical outcome associated with a partial draft prefix and a candidate action.

The partial model is a learned conditional expectation over historical continuations. It is not a causal estimate of one player’s effect, and it does not replace the live terminal completed-roster objective.

## Non-goals

HDVN V1 does not:

- replace `ffsim` projections, `SeasonWorldBank`, or the terminal roster evaluator;
- use post-season player results as live input features;
- claim that Zero RB, Hero RB, or another strategy causes championships;
- predict the exact next selection by each opponent;
- evaluate a serious live candidate from one sampled draft continuation;
- activate a live recommendation path before locked-year validation and an explicit architecture decision;
- use player identity as the primary cross-season representation.

## Score separation

Three scores remain distinct.

### Live projected completed-roster value

This is the existing ex-ante decision objective. It uses current point-in-time projections, league rules, roster feasibility, replacement levels, many probabilistic draft continuations, and coupled randomness. Historical post-season outcomes do not enter this score.

### Historical outcome score

This is an out-of-sample research score learned from draft-time features and later team outcomes. Its primary target is regular-season points-for percentile. Playoff and championship outputs are secondary calibration heads.

### Championship benchmark

The championship head is normalized within each league so roster probabilities sum to one:

$$
P(i\text{ champion}) = \frac{\exp(s_i)}{\sum_{j \in \text{league}} \exp(s_j)}.
$$

This is a calibrated historical benchmark, not a guaranteed championship probability and not a replacement for full season simulation.

## Relationship to VONA and WORP

[`VALUE_MODEL_BOUNDARIES.md`](VALUE_MODEL_BOUNDARIES.md) is the canonical
cross-system map.

- VONA remains a live next-turn opportunity feature and explanation. It is not
  an HDVN target or neural output.
- WORP remains an exact-context conversion from current projected VORP to
  regular-season expected wins. It is not an HDVN head or input.
- HDVN may compare against VONA evidence and WORP telemetry in offline
  benchmarks, but it does not absorb or silently blend either value.

## Primary target

The V1 Draft Outcome Score is predicted regular-season points-for percentile on a 0–100 scale.

- 50 means an average expected historical roster in its context.
- 70 means an expected top-30% roster.
- 90 means an expected top-10% roster.

Points-for percentile is primary because it is closer to roster strength and less sensitive than championships to schedule and playoff luck.

Secondary targets are:

- regular-season win percentage;
- made playoffs;
- champion.

## Input contract

Every feature must be known at the historical draft timestamp or be derived only from earlier observations.

### League context

- season;
- team count;
- scoring format and complete scoring settings hash;
- roster slots and flex structure;
- draft slot;
- draft type and round count.

### Draft sequence

For each observed team pick:

- round and overall pick;
- source position;
- market rank or tier available before the pick;
- pick delta versus the leakage-safe market board;
- roster position counts before the pick;
- starter, flex, and bench coverage after the pick;
- remaining picks and lineup-feasibility state.

### Roster-construction summaries

- positional sequence through each observed round;
- first QB, RB, WR, and TE round;
- position counts through rounds 3, 5, and 8;
- starter and flex coverage;
- bench distribution;
- duplicate K/DEF and other roster-feasibility indicators;
- cumulative market value captured.

### Remaining-board summary for prefixes

A partial state must include enough market information to distinguish identical rosters facing different boards:

- current overall pick and next user pick;
- available-player counts by position and tier;
- best remaining market rank by position;
- recent position-run counts;
- distance from current pick to each relevant tier boundary.

## Leakage rules

### Historical market data

The [2026-08-27 source audit](archive/research/hdvn-market-source-audit-2026-08-27.md)
accepts collected Sleeper drafts for a rolling population board in local,
non-commercial research. Each board uses only exact-context drafts that
completed before the target draft start. Sparse contexts return unavailable
without an unrecorded fallback.

FantasyPros and Fantasy Football Calculator do not expose a documented
intra-season as-of query that proves a value predates an old target draft.
Neither source is accepted for V1 historical features.

### Historical projections

Projected points, VORP, and projected roster value are valid historical
features only when the exact projection snapshot was observed before the draft.
Current projections and post-season actuals are prohibited as historical
inputs.

No authorized point-in-time historical projection source is accepted for V1.
The artifact mode is `market_and_construction_only`.

### Outcome data

Season points, wins, playoff results, championships, injuries learned after the draft, and post-draft roster changes are labels or later diagnostics. They are not draft-time input features.

## Dataset unit and split boundary

The independent unit is a league-season. Every roster, pick, prefix, and outcome from one league-season stays in one partition.

The planned locked temporal split is:

```text
Training:   2021–2023
Validation: 2024
Locked test: 2025
```

The split manifest is immutable for one model version and records exact league IDs, source hashes, feature version, and label version.

Graph provenance remains available for seed/depth sensitivity checks. Rows are never weighted by discovery frequency.

## Prefix sampling safeguard

One completed team draft can produce many prefixes with the same final label. Those prefixes are correlated and must not be treated as independent evidence.

V1 uses one sampled prefix per team per epoch. The prefix length is sampled from the supported round distribution, with explicit balancing so early, middle, and late draft states all appear.

An alternative inverse-prefix weighting experiment is allowed only as a named benchmark. In every method:

- the total weight per team-season is constant;
- every team from one league-season remains in one split;
- uncertainty is clustered by league-season;
- reported sample counts distinguish league-seasons, teams, and prefix examples.


The executable V1 feature registry is `hdvn-features-v1` in
`ffsim/historical_sleeper/hdvn_contract.py`. It records source, observation-time
rule, transformation, null meaning, leakage class, availability, and model
eligibility for each feature. Team, prefix, label, split, and artifact versions
remain separate.

## Model ladder

A neural network is not accepted unless it beats simpler models under the same features and splits.

### Baseline A: context only

Draft slot, team count, scoring format, roster configuration, and year.

### Baseline B: market and roster construction

Regularized linear or logistic models using the complete V1 feature set.

### Baseline C: gradient-boosted trees

A tabular nonlinear benchmark using the same point-in-time feature boundary.

### Model D: completed-draft neural model

A small pick encoder and permutation-aware roster pooler feed separate outcome heads. The initial network stays below 100,000 trainable parameters unless profiling and validation justify expansion.

### Model E: partial-draft value network

The same encoder accepts a prefix plus remaining-board context. It estimates the historical conditional expectation under observed continuation behavior.

Model E is research-only even when Model D passes. Counterfactual candidate substitutions can be out of distribution and require separate validation.

## Neural architecture

V1 uses a small set/sequence architecture:

```text
pick feature vector
    -> shared pick encoder
    -> masked/permutation-aware roster pooling
    -> league and board context
    -> small multilayer perceptron
    -> points, playoff, and championship heads
```

Player IDs are excluded from the primary representation. Position, round, market-relative value, tier, and roster-state features provide cross-season generalization.

The primary loss is points-percentile regression. Playoff binary cross-entropy and within-league championship softmax losses are auxiliary. Loss weights must be calibrated on validation data and recorded in the artifact; they are not silently tuned on the locked test year.

## Uncertainty

Use a small ensemble with different seeds and league-season bootstrap samples. Candidate output reports:

- ensemble mean;
- ensemble dispersion;
- number of supporting league-seasons;
- number of comparable states;
- feature-distance or out-of-distribution warning;
- model and feature versions.

A low-support or out-of-distribution candidate cannot receive a confident unique recommendation.

## Pick-timing research use

The eventual research evaluator can query the prefix model after adding each legal candidate:

$$
Q_{hist}(S,p) = V_{hist}(S+p).
$$

Historical availability supplies only the next-turn survival and fallback distribution. The historical score can screen or explain timing hypotheses, but it does not replace the live terminal projected completed-roster value.

A serious live candidate still requires the existing invariant:

- many probabilistic completed-draft continuations;
- coupled/common randomness across candidates;
- the current terminal roster evaluator;
- paired differences, uncertainty, and exact sample counts.

The prefix model may become a cheap screen only after tests prove that conservative screening never removes a terminal finalist. Candidates near the screen cutoff, practical-tie boundary, or roster-feasibility edge remain eligible for terminal evaluation.

## Evaluation

### Completed-draft score

Compare all models with:

- mean absolute error for points-for percentile;
- playoff log loss and Brier score;
- within-league championship log loss;
- calibration by probability bucket;
- within-league roster ranking;
- year, team-count, scoring-format, and draft-slot stability.

### Prefix value experiment

Evaluate:

- error by prefix round;
- calibration by remaining-pick count;
- stability under candidate substitutions;
- support and out-of-distribution coverage;
- whether predicted candidate ordering agrees with held-out completed-draft score ordering;
- whether a conservative screen retains every finalist selected by independent terminal rollouts.

### Baselines

HDVN must compare against:

- uniform $1 / \text{team_count}$ championship probability;
- draft slot and context only;
- historical market value captured;
- regularized linear/logistic models;
- gradient-boosted trees;
- current projection roster value when point-in-time projections are valid;
- current deterministic projection lookahead;
- current full `ffsim` terminal rollouts.

### Pre-crawl implementation boundary

Before the final data gate passes, implementation is limited to schemas,
protocols, manifests, fixtures, deterministic generators, leakage checks, and
bounded native-snapshot tooling. Disposable interim snapshots can verify these
contracts. They are not final training snapshots.

Real feature materialization, baseline fitting, neural training, model
selection, and locked-test use require their named ticket and data gates.

## Data gates

### Development gate

Production feature materialization and real baseline fitting begin on an
immutable snapshot after:

- at least 2,500 strict training-ready league-seasons;
- at least 500 strict ready league-seasons from every target year;
- exact source and split manifests are generated.

### Neural prototype gate

Train Model D only after:

- at least 5,000 strict training-ready league-seasons;
- at least 500 ready league-seasons from every requested target year;
- leakage-safe market features exist;
- baselines A–C are complete.

### Serious evaluation gate

Run the locked decision review after:

- at least 10,000 strict training-ready league-seasons;
- the per-year floor passes;
- the 2025 partition remains untouched during model selection;
- calibration and uncertainty artifacts are complete.

If discovery queues exhaust before a year floor passes, record the shortfall and revise the split or data target by explicit decision. Do not silently weaken the floor.

## Artifact contract

Every model artifact records:

- schema and model version;
- code revision;
- feature and label versions;
- source database snapshot hash;
- split manifest hash;
- market/projection provenance;
- training-ready counts by year and context;
- prefix sampling method and total team weight;
- architecture and parameter count;
- optimizer, seed, loss weights, and stopping rule;
- baseline and holdout metrics;
- calibration metrics;
- known limitations and eligibility status.

Statuses are:

```text
research
candidate
validated_shadow
rejected
```

There is no `live` status in this project plan. Live eligibility requires a later ADR after shadow evidence.

The common offline model protocol, metric definitions, and fail-closed artifact
manifest validation are in `ffsim/historical_sleeper/hdvn_evaluation.py`.
Artifact status does not load or activate live recommendation behavior.

## Release gates

HDVN remains separate unless all gates pass:

1. Data leakage audit passes.
2. League-season temporal split and source hashes are reproducible.
3. The neural model beats regularized and boosted baselines on validation.
4. The chosen model beats required baselines on the untouched 2025 test.
5. Championship probabilities are calibrated within league.
6. Prefix confidence falls when support falls.
7. Conservative screening retains every terminal finalist in the named replay corpus.
8. Cached and uncached artifact loading is equivalent.
9. Shadow mode has no effect on live recommendations.
10. An explicit architecture decision approves any later integration.

## Open questions

- Can an authorized point-in-time historical projection source be obtained?
- Is a rolling prior-draft market board sufficiently stable by draft date and format?
- Does a completed-draft neural model beat gradient-boosted trees?
- Does partial-prefix value add signal beyond current roster marginal value and market state?
- How much continuation-manager skill remains after context controls?
- Which out-of-distribution measure best protects counterfactual candidate scoring?
- Can the historical score improve explanation without changing the live objective?
