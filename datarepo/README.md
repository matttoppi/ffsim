# Data inventory

Data status as of 2026-08-10. The simulator is being prepared for the **2026
NFL season**: 2026 projections represent future means, while 2024-2025 results
are historical inputs for variance and calibration.

## Used by the simulator now

| Path | Season | Purpose | Source/access |
| --- | --- | --- | --- |
| `PFFProjections/projections.csv` | 2026 projections | Player, kicker, and D/ST season means and bye weeks | Manual PFF export; PFF account required, no API key |
| `PFFProjections/kickers.csv` | 2026 projections | Kicker subset generated from `projections.csv` | Local extractor |
| `PFFProjections/dsts.csv` | 2026 projections | D/ST subset generated from `projections.csv` | Local extractor |
| `Special/combined_injury_risk_data.csv` | Unverified/older snapshot | Injury probability and projected games missed | DraftSharks; current bulk data requires Insider access |

`python main.py refresh` also downloads public Sleeper league/player data and
FantasyCalc values, then writes ignored local snapshots. Neither needs an API
key. The injury CSV has no season field and should be replaced with a confirmed
2026 export before its probabilities are trusted.

## Available but not integrated yet

| Path | Season | Purpose | Notes |
| --- | --- | --- | --- |
| `PFFStats/2025/fantasy-stats-passing.csv` | 2025 actuals | Passing and QB rushing production | Season aggregate; no week column |
| `PFFStats/2025/fantasy-stats-receiving.csv` | 2025 actuals | Receiving plus RB/WR/TE rushing, red-zone, and efficiency data | A separate rushing export is unnecessary |
| `PFFStats/2025/fantasy-stats-dst.csv` | 2025 actuals | Team defense production | Season aggregate |
| `nflverse/weekly_stats/` | 2024-2025 actuals | Weekly player stat vectors for empirical variance | Includes regular and postseason rows; filter `season_type` |
| `nflverse/weekly_team_stats/` | 2024-2025 actuals | Weekly team, D/ST, and kicking outcomes | Suitable for K/DST variance |
| `nflverse/snap_counts/` | 2024-2025 actuals | Participation and played-but-zero-output weeks | Prevents survivorship bias in weekly samples |
| `nflverse/reference/games.csv` | 1999-2026 | NFL team/opponent schedule | Contains all 272 2026 regular-season games, Weeks 1-18 |
| `nflverse/reference/db_playerids.csv` | Current mapping | GSIS-to-Sleeper/PFF IDs | 99.8%/100% Sleeper coverage for relevant 2024/2025 players |

All nflverse files are public and need no account or API key. See
[`nflverse/README.md`](nflverse/README.md) for exact source URLs and refresh
cadence. No 2026 weekly results exist until the games are played.

## Legacy files

The remaining 2023-2024 projections, NGS files, depth charts, expected-points
files, and merged datasets are historical experiments and are not read by the
current runtime. Do not silently substitute them for the 2026 projection or
2024-2025 weekly datasets.

## Current algorithm boundary

`custom_dataclasses/player.py` currently derives weekly player scores from the
2026 PFF per-game means with hand-tuned lognormal and Poisson distributions.
`sim/SimulationClasses/SpecialTeamScorer.py` uses rank-based random K/DST
scores. The staged PFF actuals, nflverse weekly outcomes, snap counts, ID map,
and NFL opponent schedule do **not** affect simulations yet.
