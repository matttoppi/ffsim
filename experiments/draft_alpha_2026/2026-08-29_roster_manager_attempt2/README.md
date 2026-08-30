# Roster-aware manager attempt 2: position counts

Attempt 1 passed with round phases. This attempt tests a more realistic state: each manager's current count at QB, RB, WR, TE, K, and DEF, bucketed as zero, one, or two-plus.

Each position-count tendency is opportunity-aware and shrinks toward the population with 50 prior opportunities. Comparator: the passed round-phase model fitted on the same years.

Gate: at least 0.005 lower seen-manager choice log loss in both rolling folds and paired upper 95% bounds below zero. Use 2021–2023 only.