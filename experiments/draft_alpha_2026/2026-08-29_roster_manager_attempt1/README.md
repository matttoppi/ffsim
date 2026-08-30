# Roster-aware manager attempt 1: round phase

Hypothesis: a manager's position tendency changes across early rounds 1–5, middle rounds 6–10, and late rounds 11+. Estimate opportunity-aware manager factors inside each phase and shrink them toward the phase population with 50 prior opportunities.

Comparator: the frozen static manager-position residual fitted on the same training years.

Gate: improve seen-manager player-choice log loss by at least 0.005 in both rolling folds, with each draft-clustered paired upper 95% bound below zero. Use 2021–2023 only.