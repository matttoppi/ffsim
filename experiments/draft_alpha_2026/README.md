# 2026 draft alpha research

This directory contains offline experiments for 2026 draft decisions. Each hypothesis has a separate subdirectory, a frozen gate, executable code, and machine-readable results.

## Source boundary

- Historical source: immutable Sleeper snapshot `c672898ff06819602fe52d06c606a01492194b053614f47d618876e6332579a5`.
- Historical market: leakage-safe rolling boards in `market-v1.sqlite3`.
- Development years: 2021–2023 with rolling validation.
- Seen diagnostic year: 2024. Do not use it for model selection.
- Locked year: 2025. Do not read it in these experiments.
- Current value inputs: 2026 FantasyPros projections, PFF supplements, Sleeper projections, league scoring, and the existing deterministic VORP and VONA code.

No experiment in this directory changes the live API, user interface, VONA, WORP, opponent callback, rollout ranking, or terminal projected-roster objective.

## Hypotheses and frozen gates

### `00_prior_evidence`

Verify the immutable reports before new work. This experiment must confirm:

- the completed-draft neural network did not beat the historical-market baseline;
- the additive survival model passed aggregate rolling metrics but failed the elite long-gap invariant;
- the exact empirical survival lookup passed its support and calibration gates.

### `01_survival_interaction`

Hypothesis: a fixed rank-by-gap interaction can retain the additive model's broad calibration improvement and represent elite long-gap tails.

Use only 2021–2023. Fit on 2021 and validate on 2022, then fit on 2021–2022 and validate on 2023. Compare with the exact `(rank, gap, round)` empirical baseline.

Pass only if both folds have:

- Brier improvement of at least `0.001`;
- false-safe improvement of at least `0.02` at probability `0.70`;
- safe-coverage loss no greater than `0.10`;

and the pooled upper 95% draft-clustered Brier-difference bound is below zero. The final rank-2 RB, round-1, gap-18 prediction must be below `0.01` with at least 1,000 observations.

### `01b_survival_tree`

Hypothesis: a fixed shallow monotonic boosted tree can model the rank, gap, and round interaction that the additive and rank-specific-slope models missed.

Use `HistGradientBoostingClassifier` with 15 leaves, depth 3, 100 iterations, learning rate 0.05, L2 1.0, and 20-cell minimum leaves. Constrain survival to increase with relative market rank and decrease with pick gap. Use the same years, comparator, and gate as `01_survival_interaction`.

### `02_manager_personalization`

Hypothesis: an opportunity-aware, shrunk manager-position preference improves player-choice log loss for managers observed in prior seasons.

Use the inverse-ADP population probability as the offset. Estimate manager position multipliers from observed selections versus the population probability mass available at those selections. Use fixed shrinkage of 50 prior opportunities. Evaluate the same two rolling folds.

Pass only if seen managers with at least 20 prior supported picks improve mean choice log loss by at least `0.005` in both folds, each paired draft-clustered upper 95% bound is below zero, and the model does not worsen all-pick log loss by more than `0.001` in either fold.

### `02b_manager_residual`

Hypothesis: manager-specific position preference adds signal beyond a population position correction, rather than only fixing a population bias in inverse ADP.

Use the same rolling folds and support gate as `02_manager_personalization`. Compare the manager posterior with inverse ADP multiplied by a training-only population position factor. Shrink each manager toward that population factor with 50 prior opportunities. Require at least `0.005` seen-manager log-loss improvement in both folds and paired upper bounds below zero.

### `02c_manager_2024_diagnostic`

Freeze the passed `02b` method. Fit once on 2021–2023 and run a seen-year 2024 transfer diagnostic. Use the same `0.005` log-loss improvement and paired upper-bound gate. Report how many of the 25 configured 2026 target managers have at least 20 supported training picks. Do not query 2025.

### `02d_manager_locked_2025`

Select the unchanged `02b` method after it passes both rolling folds and the 2024 transfer diagnostic. Fit on 2021–2024 and run one one-time 2025 locked evaluation. Require at least `0.005` seen-manager log-loss improvement, a paired upper 95% bound below zero, and no more than `0.001` all-pick degradation. This result remains offline.

### `03_vona_vorp_policy`

The passed exact empirical lookup is the only eligible survival source. Historical point-in-time projections are unavailable, so this experiment cannot claim historical projection alpha.

Apply the lookup to saved current 2026 timing states. Use league-scored static VORP (`projected_points - replacement_points`) and roster-specific terminal marginal value from the existing VONA path. Compute the independent-survival expected best next-turn value only when all top-ten cells are supported.

Pass the coverage gate only if at least 70% of top-ten candidates and at least 50% of saved states have exact support. At least 80% of fully supported states must keep the same best take-versus-wait sign across the stored 95% survival intervals. A pass remains offline and does not establish historical projection alpha.

### `04_manager_survival_impact`

Test whether the frozen manager residual improves the timing quantity that matters: exact top-ten player survival to the user's next pick. Fit manager factors on 2021–2023 and replay the seen 2024 diagnostic year. Use the observed board path only to update which players remain; compute population and personalized conditional hazards before each intervening pick.

Pass only with at least `0.001` Brier improvement, a paired draft-clustered upper 95% bound below zero, at least `0.02` lower false-safe rate at probability `0.70`, and no more than `0.10` safe-coverage loss. This is downstream diagnostic evidence, not a new untouched holdout.

### `05_pooled_exact_survival`

Test a transparent exact `(relative market rank, pick gap, round)` lookup with Beta(1,1) smoothing and without position, scoring, or team-count fragmentation. Require 250 training observations per cell. In both rolling folds, require at least 70% coverage, Brier at most `0.12`, expected calibration error at most `0.05`, and false-safe rate at most `0.10`. Preserve the rank-2, gap-18, round-1 prediction below 1% with at least 1,000 observations. Do not interpolate or fall back below support.

### `05b_position_exact_survival`

Retain position in the exact lookup after `05` shows that cross-position pooling corrupts elite long-gap estimates. Use exact `(relative market rank, pick gap, round, position)` cells with Beta(1,1) smoothing and 250-observation support. Use the same rolling calibration, coverage, false-safe, and elite gates as `05`. Continue to pool scoring format and team count.

### `06_hierarchical_survival`

Test fixed hierarchical position pooling after `05b` shows accurate supported cells but insufficient coverage. For each `(rank, gap, round, position)` cell, shrink its observed rate toward the Beta(1,1)-smoothed `(rank, gap, round)` rate with 100 prior observations. An unseen pooled cell uses the training-global Beta(1,1) rate as the explicit top-level prior. This is one explicit model, not a runtime fallback. Require 100% lookup coverage, Brier at most `0.12`, expected calibration error at most `0.05`, and false-safe rate at most `0.10` in both rolling folds. Preserve rank-2 RB, gap-18, round-1 below 1% with at least 1,000 direct observations.

### `06b_hierarchical_2024_diagnostic`

Freeze `06` after both rolling folds pass. Fit on 2021–2023 and evaluate the unchanged model on the seen 2024 diagnostic year. Use the same Brier, calibration, false-safe, coverage, and elite gates. Do not query 2025.

### `06c_hierarchical_vona_vorp`

If `06b` passes, apply the frozen hierarchy to the saved 2026 timing states. Require 100% top-ten coverage. Use the hierarchy's effective Beta posterior counts for 95% survival intervals, then recompute current roster-specific VONA and static VORP sensitivity. Keep this offline because historical point-in-time projection labels remain unavailable.

### `06d_hierarchical_comparison`

Compare the frozen `06` hierarchy with the Beta(2,2)-smoothed exact `(rank, gap, round)` baseline used by the prior continuous-survival work. In both rolling folds, require at least `0.001` Brier improvement and a draft-clustered paired upper 95% bound below zero. Use 2021–2023 only. This comparison does not change `06` or its gates.

## Interpretation rules

- A failed gate rejects that hypothesis. Do not rescue it with a secondary metric or a post-hoc slice.
- A passed development gate creates an offline research candidate only.
- Do not blend historical outcome scores into VONA, WORP, or terminal projected-roster value.
- Do not open the 2025 locked partition until one model and its one-time gate are frozen.