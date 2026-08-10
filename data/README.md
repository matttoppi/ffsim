# Active data

Data status as of 2026-08-10. The simulator is being prepared for the 2026 NFL season: 2026 projections provide future means and active 2024-2025 results provide weekly distribution shapes.

## Checked-in inputs

| Path | Season | Purpose | Source/access |
| --- | --- | --- | --- |
| `projections/players.csv` | 2026 projections | Player season means and bye weeks | Manual PFF export; PFF account required |
| `projections/kickers.csv` | 2026 projections | Kicker subset generated from `players.csv` | `python tools/extract_special_teams.py` |
| `projections/defenses.csv` | 2026 projections | D/ST subset generated from `players.csv` | `python tools/extract_special_teams.py` |
| `historical/nflverse/` | 2024-2026 | Joint-vector templates, team weeks, IDs, and schedule | Public nflverse releases |
| `injuries/risk.csv` | Unverified older snapshot | Disabled provenance only | DraftSharks; current bulk data requires Insider access |

`python -m ffsim refresh` also downloads public Sleeper league/player data and FantasyCalc values. It writes ignored snapshots to `cache/`; neither public source needs an API key.

The injury CSV has no season field and is disabled by default. It does not
change availability or production.

## Algorithm boundary

`ffsim/simulation/empirical.py` builds normalized joint weekly vectors from
snap-defined played games, including zero-output games, and recenters every
component pool to one. It scales those vectors to league-rescored PFF per-game
means. Kicker and D/ST shapes use nflverse team-week vectors. Availability is
sampled independently at `projected games / 17` per future non-bye week.

The mean-preserving parametric kernel remains a tested baseline. The 2025 PFF
aggregates under `archive/` do not modify 2026 means. See
[../archive/README.md](../archive/README.md).
