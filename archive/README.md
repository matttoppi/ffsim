# Archive

These files are retained for provenance and possible future research. Nothing under `archive/` is imported or read by the current application.

## `data/legacy/`

- 2023-2024 projections and PFF exports
- 2023 NGS data
- Historical depth charts, expected-points, offensive-line, target, and merged datasets
- The unused combined kicker/D/ST export

These files must not be substituted for the active 2026 inputs without explicitly updating the loaders and season labels.

## `data/research/`

- `pff_stats/`: 2025 PFF passing, receiving, and D/ST season aggregates

The nflverse weekly data, IDs, and schedule moved to
`data/historical/nflverse/` because they are active runtime and backtesting
inputs. The archived PFF aggregates remain research-only and do not modify
2026 means.

## `scripts/`

- `injury_risk_scraper.py`: obsolete DraftSharks scraper retained as a reference; it is not part of the supported refresh workflow
