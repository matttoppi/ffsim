# Value Model Boundaries

This document is the short map for the project’s value terms. It defines which system owns each score and prevents unrelated values from being blended into one opaque recommendation.

## Summary

| Value | Purpose | Live role | Trained by HDVN? | Canonical source |
|---|---|---|---|---|
| Projected completed-roster value | Rank serious root candidates by expected final roster quality | Primary decision objective | No | ADR-026 and specification chapter 06 |
| VONA | Explain current value versus realistic next-turn alternatives | Policy feature and evidence | No | Specification chapter 06 §20.3 and ADR-025/028/032 |
| WORP | Convert league-wide projected VORP into expected regular-season win gain | Optional approved telemetry | No | ADR-039 and `ffsim/draft_intel/worp.py` |
| HDVN outcome score | Test whether historical draft structure predicts later outcomes | Offline research only | This is HDVN | ADR-040 and `HISTORICAL_DRAFT_VALUE_NETWORK.md` |

## Projected completed-roster value

The existing live objective remains expected projected value of the completed user roster across draft uncertainty.

Serious candidate evaluation requires:

- many probabilistic completed-draft continuations;
- the modeled conditional draft distribution;
- common/coupled randomness across candidates;
- the current `ffsim` roster evaluator;
- paired differences, uncertainty, and sample counts.

No historical outcome score replaces this objective in the current architecture.

## VONA

Value Over Next Availability (VONA) measures the opportunity around the next user turn. It compares current marginal value with expected realistic alternatives available later within a named candidate-taken branch.

VONA is:

- a future-user policy feature;
- a scarcity and opportunity diagnostic;
- an explanation for why a player may be urgent;
- local to the branch and roster state that produced it.

VONA is not:

- the root recommendation objective;
- a championship model;
- a player’s static value;
- evidence that a surviving player will be selected;
- an HDVN training target.

Historical drafts can improve player and tier survival estimates used near VONA. They do not turn VONA itself into a neural-network output.

### VONA next work

Keep VONA in the existing decision system. Validate it through frozen draft replays:

- next-turn survival calibration;
- fallback-value error;
- false “safe to wait” frequency;
- agreement with terminal coupled-rollout decisions;
- conservative finalist retention near timing ties.

Do not move VONA into HDVN.

## WORP

Wins Over Replacement Player (WORP) is a two-stage calibration:

1. League-specific projected VORP supplies projected points above the starter replacement cutline.
2. An exact-context empirical score-margin curve maps weekly point advantage to expected head-to-head win gain.

WORP is:

- regular-season expected-win telemetry;
- exact to team count and scoring format;
- unavailable until its context passes holdout gates and explicit approval;
- derived from current projections plus a historical matchup-margin curve.

WORP is not:

- the terminal candidate objective;
- playoff or championship probability;
- roster-aware marginal value;
- VONA;
- an HDVN neural head or input feature.

### WORP next work

Keep WORP separate from HDVN:

1. Finish or snapshot the historical crawl.
2. Fit exact `(team_count, scoring_format)` curves.
3. Preserve league-season holdout isolation.
4. Review training/holdout game and league counts.
5. Approve only exact contexts with a decision reference.
6. Continue to show unavailable/pending for every other context.

HDVN can later compare historical outcome calibration with WORP as a benchmark. It does not absorb or retrain WORP.

## HDVN

The Historical Draft Value Network (HDVN) is a planned offline experiment with two artifacts:

- completed-draft historical outcome scoring;
- partial-prefix conditional value research.

Its primary target is points-for percentile. Playoff and within-league championship heads are secondary.

HDVN remains separate because later outcomes contain injury, schedule, playoff, manager, and continuation noise. It must beat context, regularized, boosted-tree, market, and current `ffsim` baselines under locked temporal validation before shadow consideration.

HDVN output cannot:

- replace current live projected value;
- become a silent fallback;
- directly blend with WORP or VONA;
- alter candidate ranking before a later architecture decision.

## Allowed interactions

```text
Current projections
    -> league-scored player value
    -> completed-roster terminal objective
    -> live recommendation

Current roster + next-turn availability
    -> VONA policy/evidence
    -> timing explanation

Current league-wide VORP + approved historical margin curve
    -> WORP
    -> regular-season win telemetry

Historical draft-time features + later outcome labels
    -> HDVN research artifact
    -> offline score / benchmark / possible shadow evidence
```

The systems may be compared in backtests. Their values remain separately named and versioned.

## Documentation ownership

| Change | Update first |
|---|---|
| Live root objective or terminal scorer | ADR-026 family, chapter 06, implementation ledger |
| VONA definition or branch semantics | Chapter 06 §20.3 and relevant VONA ADR |
| WORP fitting, approval, or context semantics | ADR-039 and WORP tests/code documentation |
| HDVN features, architecture, or gates | `HISTORICAL_DRAFT_VALUE_NETWORK.md` |
| HDVN ticket state | `HDVN_IMPLEMENTATION_LEDGER.md` |
| Durable cross-system boundary | `DECISIONS.md` and this document |

Do not copy a full definition into multiple files. Other documents should link to the canonical owner.
