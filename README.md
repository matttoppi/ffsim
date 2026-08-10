# Fantasy Football Simulator

Run repeatable Monte Carlo simulations for a Sleeper fantasy football league. Data refreshes are explicit, so simulations use stable local snapshots instead of changing API responses.

## Project layout

```text
ffsim/              Application package and command-line entry point
  loaders/          Sleeper, FantasyCalc, PFF, and injury ingestion
  models/           League, team, and player models
  simulation/       Season, matchup, playoff, tracking, and plotting logic
data/               Active runtime inputs and ignored generated snapshots
tests/              Automated tests
tools/              Maintained data-preparation utilities
archive/            Unused historical, research, and obsolete files
output/             Ignored simulation results and plots
```

Files under `archive/` are retained for reference but are not imported or read by the application. See [archive/README.md](archive/README.md) for the inventory.

## Setup

Python 3.12 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Edit `config.json` with the Sleeper league ID and desired simulation settings:

```json
{
  "league_id": "1048288271089983488",
  "simulations": 150,
  "seed": 2026,
  "regular_season_weeks": 14,
  "results_file": "output/results.json"
}
```

## Refresh data

Before the first simulation, and whenever source data changes, run:

```bash
python -m ffsim refresh
```

This fetches Sleeper league, roster, matchup, and player data plus FantasyCalc values. It combines those sources with these checked-in files:

- `data/projections/players.csv`
- `data/projections/kickers.csv`
- `data/projections/defenses.csv`
- `data/injuries/risk.csv`

Generated player, league, and matchup snapshots are written to the ignored `data/cache/` directory. See [data/README.md](data/README.md) for source and season details.

When a new PFF projection export replaces `data/projections/players.csv`, regenerate the kicker and defense subsets:

```bash
python tools/extract_special_teams.py
```

## Run simulations

```bash
python -m ffsim simulate
```

The run reads only local snapshots and writes structured output to `output/results.json`. The seed makes repeated runs against the same snapshots reproducible.

Command-line options can override the config without editing it:

```bash
python -m ffsim simulate --simulations 1000 --seed 42
python -m ffsim simulate --output output/week-1.json
python -m ffsim simulate --plots
```

The JSON result is the intended boundary for a future API or website: it contains run metadata plus team probabilities and player summaries.

## Hosting and performance

Do not run the simulation for every page view. Precompute the result after refreshing inputs, then serve the JSON with a static website. This avoids server cold starts and keeps hobby-scale hosting free.

Recommended schedule:

- During the season, refresh and simulate once each morning.
- Run again after projections, injuries, trades, or rosters change.
- In the offseason, run only when an input changes.
- Do not rerun unchanged inputs. A fixed seed produces the same result from the same snapshots.

For a casual league, 5,000 simulations is a good hosted default. The approximate 95% margin below applies to an outcome whose true probability is near 50%, where Monte Carlo estimates are least precise:

| Simulations | Approximate margin |
| ---: | ---: |
| 150 | +/- 8 percentage points |
| 1,000 | +/- 3 percentage points |
| 5,000 | +/- 1.4 percentage points |
| 10,000 | +/- 1 percentage point |

A representative synthetic benchmark took about 1-2 seconds for 150 simulations, 8 seconds for 1,000, and 80 seconds for 10,000 on a development machine. These are directional figures, not production guarantees. A scheduled run remains inexpensive, while each website visit only downloads the generated JSON.

Before rewriting the simulator in Rust:

- Load and parse matchup snapshots once per run instead of once per simulated season.
- Precompute immutable per-player distribution parameters.
- Track running aggregates instead of retaining every score when plots are not requested.
- Import refresh and plotting dependencies only for commands that use them.

Consider extracting the simulation kernel into Rust only if users need uncached, interactive scenarios and profiling shows that optimized Python cannot meet the latency target. Rust compiled to WebAssembly could then run in the browser while preserving static hosting.

### Current in-season limitation

The simulator uses Sleeper matchup snapshots to determine pairings, but it starts every simulated season at 0-0 and does not incorporate completed matchup scores or current standings. Frequent in-season recomputation will not produce true rest-of-season playoff odds until completed weeks are preserved and only future weeks are simulated.

## Checks

```bash
python -m unittest discover -s tests -v
python -m compileall -q ffsim tests tools
```

Tests cover scoring regressions, roster-derived lineups, configuration, playoff scheduling, and JSON result generation.
