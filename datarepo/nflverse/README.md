# nflverse data

Public CSV snapshots used to model weekly fantasy variance. No account or API
key is required.

| Files | Purpose | Source |
| --- | --- | --- |
| `weekly_stats/stats_player_week_2024.csv`, `stats_player_week_2025.csv` | Player-level weekly outcomes | https://github.com/nflverse/nflverse-data/releases/tag/stats_player |
| `weekly_team_stats/stats_team_week_2024.csv`, `stats_team_week_2025.csv` | Weekly team, D/ST, and kicking outcomes | https://github.com/nflverse/nflverse-data/releases/tag/stats_team |
| `snap_counts/snap_counts_2024.csv`, `snap_counts_2025.csv` | Offensive participation, including played-but-zero-output weeks | https://github.com/nflverse/nflverse-data/releases/tag/snap_counts |
| `reference/games.csv` | Historical and future NFL schedules, including all 272 2026 regular-season games | https://github.com/nflverse/nfldata/blob/master/data/games.csv |
| `reference/db_playerids.csv` | GSIS, Sleeper, PFF, and other player-ID mappings | https://github.com/dynastyprocess/data/blob/master/files/db_playerids.csv |

Snapshots were downloaded on 2026-08-10. During the season, nflverse player
and team stats update after game days, schedules update throughout the season,
and snap counts update several times daily. Refresh these snapshots before a
simulation run that should include newly completed games.

2026 weekly results do not exist until games are played. PFF projections and
DraftSharks injury probabilities are separate member-gated inputs.
