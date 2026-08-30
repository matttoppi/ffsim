# Corrected roster-aware manager model

## Hypothesis

Manager position preference depends on the roster already drafted. Reconstructing every prior roster pick, including picks absent from the rolling market board, will retain the position-count model's choice-log-loss improvement over the passed round-phase model.

## Frozen state contract

- Fit only on market-supported choices.
- Before each choice, reconstruct position counts from every earlier source draft pick.
- For a board-unsupported pick, update roster counts from immutable source `draft_picks.position` but do not create a choice-loss observation.
- Bucket each position count as zero, one, or two-plus.
- Shrink manager cells toward the population with 50 prior opportunities.
- Use train-2021/validate-2022 and train-2021–2022/validate-2023 rolling folds.
- After the rolling gate, fit 2021–2023 and run the seen 2024 transfer.
- Do not query 2025.

## Gate

The corrected model must lower seen-manager choice log loss by at least `0.005` versus the round-phase model in both rolling folds and the 2024 transfer. Every draft-clustered paired upper 95% bound must be below zero.