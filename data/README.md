# Active data

Data status as of 2026-08-13. The simulator is being prepared for the 2026 NFL season: 2026 projections provide future means and active 2024-2025 results provide weekly distribution shapes.

## Checked-in inputs

| Path | Season | Purpose | Source/access |
| --- | --- | --- | --- |
| `projections/players.csv` | 2026 projections | Supplemental fields plus K/DST means | Manual PFF export; PFF account required |
| `projections/kickers.csv` | 2026 projections | Kicker subset generated from `players.csv` | `python tools/extract_special_teams.py` |
| `projections/defenses.csv` | 2026 projections | D/ST subset generated from `players.csv` | `python tools/extract_special_teams.py` |
| `projections/defense_matchups.csv` | 2026 projections | PFF D/ST projections joined to DI, edge, LB, CB, and safety unit grades | Mike Clay's 2026 projection guide; `python tools/build_defense_matchups.py` |
| `historical/nflverse/` | 2024-2026 | Joint-vector templates, team weeks, IDs, and schedule | Public nflverse releases |
| `historical/nflverse/play_by_play/scoring_*` | 2024-2025 | Compact long-TD, pick-six, blocked-kick, and special-teams turnover events | Derived from nflverse play-by-play |
| `injuries/risk.csv` | 2026 when imported | Injury probability and expected games missed | DraftSharks Insider |

`python -m ffsim refresh` also downloads Sleeper league/player data, Sleeper
2026 stat projections, FantasyCalc values, and FantasyPros consensus preseason
projections. FantasyPros is the primary QB/RB/WR/TE counting-stat source and
requires `FANTASYPROS_API_KEY`; its SportsData IDs are matched to Sleeper's
Sportradar IDs. PFF fills only fields the FantasyPros response omits (currently
targets, sacks suffered, fumbles lost, and return yards) and remains the K/DST
source. Missing FantasyPros offensive players do not silently fall back to PFF.
Ignored derived snapshots are written to `cache/`. League and draft setup use
the same request-driven 12-hour freshness interval for this projection cache
and the FantasyPros ADP cache; there is no background scheduler.

Mike Clay unit-grade source:
`https://g.espncdn.com/s/ffldraftkit/26/NFLDK2026_CS_ClayProjections2026.pdf`.
Weekly QB, RB, WR, and TE means receive a position-specific matchup adjustment
of 2% per composite grade point above or below league average, capped at 8%.

The legacy injury CSV has no season field and remains disabled. To replace it
from an authorized DraftSharks session, save the Injury Predictor page as HTML,
then run:

```bash
python tools/import_draftsharks_injuries.py /path/to/injury-predictor.html
python -m ffsim refresh
```

The importer adds the required `season` and `sleeper_id` fields. A current
profile models injury occurrence separately from conditional duration, keeping
healthy seasons possible while preserving projected average games missed.

The compact scoring-event files were generated from the official nflverse
`pbp` release assets:

- `https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2024.csv.gz`
- `https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.csv.gz`

The raw play-by-play downloads are not runtime dependencies. Regenerate the
checked-in extracts with:

```bash
python tools/extract_scoring_events.py 2024 /path/to/play_by_play_2024.csv.gz
python tools/extract_scoring_events.py 2025 /path/to/play_by_play_2025.csv.gz
```

## Algorithm boundary

`ffsim/simulation/empirical.py` builds normalized joint weekly vectors from
snap-defined played games, including zero-output games, and recenters every
component pool to one. It scales those vectors to the league-rescored projection
per-game means. Kicker and D/ST shapes use nflverse team-week vectors. Availability is
sampled independently at `projected games / 17` per future non-bye week.

Long-touchdown and pick-six rates condition on the primary touchdown and
interception totals. Kick/punt return splits preserve PFF combined return yards,
and exact field-goal yards are sampled within PFF distance buckets. Blocked
kicks and special-teams turnovers use observed 2024-2025 per-game rates because
PFF does not project those categories separately.

The mean-preserving parametric kernel remains a tested baseline. The 2025 PFF
aggregates under `archive/` do not modify 2026 means. See
[../archive/README.md](../archive/README.md).
