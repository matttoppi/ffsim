# Fantasy Football Simulator

Run repeatable Monte Carlo simulations for a Sleeper fantasy football league. Data refreshes are explicit, so simulation runs use stable local snapshots instead of changing API responses.

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
  "results_file": "results.json"
}
```

## Refresh data

Before the first simulation, and whenever source data changes, run:

```bash
python main.py refresh
```

This fetches Sleeper league, roster, matchup, player, and FantasyCalc data. It combines those sources with these checked-in files:

- `datarepo/PFFProjections/projections.csv`
- `datarepo/PFFProjections/kickers.csv`
- `datarepo/PFFProjections/dsts.csv`
- `datarepo/Special/combined_injury_risk_data.csv`

The generated player, league, and matchup snapshots are ignored by Git.

See [`datarepo/README.md`](datarepo/README.md) for the complete data inventory,
season labels, source/access requirements, and which files are not integrated yet.

## Run simulations

```bash
python main.py simulate
```

The run reads only local snapshots and writes structured output to `results.json`. The seed makes repeated runs against the same snapshots reproducible.

Command-line options can override the config without editing it:

```bash
python main.py simulate --simulations 1000 --seed 42 --output results/week-1.json
python main.py simulate --plots
```

The JSON result is the intended boundary for a future API or website: it contains run metadata plus team probabilities and player summaries.

## Checks

```bash
python -m unittest -v
python -m compileall -q .
```

Tests cover scoring regressions, roster-derived lineups, configuration, playoff scheduling, and JSON result generation.
