# Manager rollout-impact attempt 1

Goal: test whether the passed position-count manager model improves exact top-ten player survival to the next same-roster pick on the seen 2024 diagnostic year.

Comparator: the locked-benchmark-backed static manager-position model. Both fit on 2021–2023 for this transfer.

Gate: Brier improvement at least 0.001, draft-clustered paired upper 95% bound below zero, false-safe improvement at least 0.02 at probability 0.70, and safe-coverage loss no greater than 0.10. Do not query 2025.