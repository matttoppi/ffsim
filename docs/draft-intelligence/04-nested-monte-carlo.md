## 17. Nested Monte Carlo Strategy

There are two uncertainty layers:

1. **Draft uncertainty:** which players each manager will select in the remaining draft.
2. **Season uncertainty:** how NFL players perform and how the fantasy season/playoffs unfold.

The objective is:

```text
P(championship | root candidate)
  = E_draft [ E_season [ championship | completed rosters ] ]
```

### 17.1 Avoid naive full cross products

Do not automatically evaluate 5,000 draft completions x 20,000 season worlds for every candidate.

Use joint/stratified sampling:

- sample **many** draft continuations from `P(D | root_candidate, current_state)`
- associate each continuation with one or a small batch of shared season world IDs
- accumulate paired outcomes across both uncertainty dimensions
- weight samples according to the target draft distribution when the sampling policy is not identical to that target distribution

For finalists, increase either the number of draft continuations, season worlds per continuation, or both depending on which variance component dominates. The implementation must never substitute "one draft continuation x many season worlds" for integrating over draft uncertainty.

### 17.2 Variance decomposition research task

Measure whether candidate uncertainty is dominated by:

- opponent draft behavior
- NFL/season randomness
- playoff randomness

Allocate compute adaptively. Early rounds may require more draft-continuation diversity; late rounds may require more season worlds because the remaining draft is shorter.

### 17.3 Candidate racing / successive halving

Never spend equal compute on every available player.

Suggested warm-run strategy:

**Pass 0: candidate generation**
- 10-20 plausible serious candidates.

**Pass 1: screening**
- ~100-200 paired joint rollouts each.
- Eliminate clearly dominated candidates.

**Pass 2: refinement**
- ~1,000 effective paired outcomes for top 4-6.

**Pass 3: final**
- 5,000-20,000+ effective paired outcomes for top 2-3 if the draft clock allows and uncertainty remains meaningful.

Numbers are initial targets, not hard requirements. Benchmark on the M5 Max.

The live V1 uses a 12-rollout coupled screen across the 40-player market
window, followed by 300 draft continuations and three season worlds per
continuation for the top five. This preserves roughly the prior live compute
budget while moving it from obviously dominated candidates to plausible
winners.

### 17.4 Early stopping

Stop spending compute on a candidate when its upper confidence bound is safely below a stronger candidate's lower confidence bound, subject to a minimum sample size.

### 17.5 Speculative compute

Start before the user is on the clock.

When the user's next pick is three selections away:

- predict likely availability
- evaluate likely candidate roots in advance
- cache results keyed by live draft state prefix

As intervening picks occur:

- discard impossible candidates
- preserve results whose underlying state assumptions remain valid
- quickly refine the new top set

The goal is for a useful recommendation to be available immediately when the user's timer begins, with confidence improving during the clock.

### 17.6 Draft-path robustness and continuation dependency

Do not report only the mean championship probability of a root candidate. The system must also measure how dependent that candidate is on favorable future draft outcomes. For each serious candidate, report or retain:

- mean championship probability across future-draft uncertainty
- median and 10th/90th percentile conditional championship equity across draft continuations
- probability of a strong continuation, using a calibrated definition rather than an arbitrary fixed threshold
- probability that at least one acceptable player from each important target tier survives to the user's next turn
- probability that a specific high-priority player or one of an equivalent set survives
- primary failure mode, such as an RB tier being exhausted before the next pick
- the future manager(s) and picks responsible for most of that downside risk

This allows the UI to distinguish a candidate with slightly higher average equity but fragile continuation requirements from a robust candidate whose value survives many board shapes.

### 17.7 Separate draft uncertainty from season uncertainty

Treat the nested simulation as two explicit axes:

```text
                 Season worlds
              W1   W2   W3  ...
Draft D1      ...  ...  ...
Draft D2      ...  ...  ...
Draft D3      ...  ...  ...
...
```

The engine should be able to estimate:

- variance caused by the remaining fantasy draft
- variance caused by NFL/player performance and injuries
- variance caused by fantasy schedule/playoff randomness when separately measurable
- paired candidate differences within the same draft continuation and season world

This decomposition is useful both for compute allocation and explanation. For example, Candidate A may beat Candidate B mainly because A creates better likely next-turn combinations, while two otherwise similar candidates may differ mostly because of football-outcome uncertainty.

### 17.8 Nested-simulation correctness invariants

The following are release-blocking invariants:

1. Every root candidate is evaluated across multiple remaining-draft continuations.
2. Continuation probabilities come from the manager-conditioned draft model at each sequential pick.
3. A manager's later pick is conditioned on all earlier simulated picks and the resulting roster/availability state.
4. User future picks branch according to the same rollout policy across root candidates.
5. Root candidates use coupled draft randomness and shared season worlds wherever possible.
6. Equal averaging is used only for samples drawn from the target continuation distribution; deliberately biased/stratified sampling uses appropriate weights.
7. Recommendation confidence incorporates both draft-path and season-world uncertainty.
8. Tests must fail if a code path attempts to estimate root championship equity from only one future draft completion.

---
