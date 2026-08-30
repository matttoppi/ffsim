# Next alpha experiment: rank-20 hierarchical survival

## Problem

The integrated audit shows only `46.3%` of terminal candidates receive return probabilities. `53.7%` are outside the current relative market top-ten model. Extrapolation is prohibited.

## Hypothesis

A separately materialized top-20 survival target can improve terminal-candidate timing coverage without degrading the calibrated rank-1–10 hierarchy or the elite long-gap tail.

## Frozen data boundary

- Build new samples from relative market ranks 1–20.
- Train only on 2021–2023 rolling folds.
- Use train-2021/validate-2022 and train-2021–2022/validate-2023.
- Run the unchanged selected model on the seen 2024 transfer only after both folds pass.
- Do not query 2025.
- Keep the rank-10 artifact immutable and live-shadow eligible while research runs.

## Comparators

- ranks 1–10: current hierarchical rank-10 model;
- ranks 11–20: Beta(2,2)-smoothed exact `(rank, gap, round)` population baseline;
- all ranks: market-only exact baseline and calibration slices.

## Gate

1. Ranks 1–10 Brier cannot worsen by more than `0.001` in either rolling fold.
2. Ranks 11–20 must improve baseline Brier by at least `0.001` in both folds, with each draft-clustered paired upper 95% bound below zero.
3. Ranks 11–20 false-safe rate must be at most `0.10`.
4. Expected calibration error must be at most `0.05` for ranks 1–10 and 11–20 separately.
5. Rank-2 RB, round-1, gap-18 must remain below `1%` with at least 1,000 direct observations.
6. Six-state terminal-candidate return coverage must rise from `46.3%` to at least `70%`.
7. No live ranking, route, callback, or UI change occurs unless a later decision-impact gate passes.

## Real-draft interpretation

Rank 11–20 is useful because terminal roster value can elevate players beyond the market top ten. The model still predicts availability only; completed-roster value remains the pick objective.