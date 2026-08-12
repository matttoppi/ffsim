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

The checked-in ID is a completed 2024 league. Supply the correct 2026 Sleeper
league ID before live verification; the simulator does not invent or roll a
league ID forward.

## Refresh data

Select a 2026 league interactively the first time:

```bash
python -m ffsim setup
```

The setup prompt asks for a Sleeper username, lists that user's leagues, and
saves the selected league ID to `config.json`.

Before the first simulation, and whenever source data changes, run:

```bash
python -m ffsim refresh
```

This fetches Sleeper league, roster, matchup, and player data plus FantasyCalc values. It combines those sources with these checked-in files:

- `data/projections/players.csv`
- `data/projections/kickers.csv`
- `data/projections/defenses.csv`
- `data/historical/nflverse/`

Generated player, league, and matchup snapshots are written to the ignored `data/cache/` directory. See [data/README.md](data/README.md) for source and season details.

When a new PFF projection export replaces `data/projections/players.csv`, regenerate the kicker and defense subsets:

```bash
python tools/extract_special_teams.py
```

## Run simulations

```bash
python -m ffsim simulate
```

The run reads only local snapshots and writes structured output to `output/results.json`. The seed makes repeated runs against the same snapshots reproducible, including repeated calls on one simulation object.

Command-line options can override the config without editing it:

```bash
python -m ffsim refresh --username YOUR_SLEEPER_USERNAME
python -m ffsim simulate --username YOUR_SLEEPER_USERNAME
python -m ffsim simulate --simulations 300 --seed 42
python -m ffsim simulate --output output/week-1.json
python -m ffsim simulate --plots
python -m ffsim simulate --teams-only
python -m ffsim simulate --teams-only
python -m ffsim simulate --workers 1
```

Audit the current league's managers and their Sleeper draft history without changing local data:

```bash
python -m ffsim draft-audit --league-id YOUR_LEAGUE_ID --season 2026
```

The audit checks the requested season and two prior seasons, fetches every shared draft once, and reports normalized draft/pick counts and format coverage.

Normal runs keep aggregate player summaries without retaining every sampled
score. `--plots` retains the raw samples needed for histograms. `--teams-only`
skips bench-player score generation and omits the `players` result object when
only standings and playoff probabilities are needed. Simulations use up to
four worker processes by default; `--workers 1` disables multiprocessing.

## Backend API

Start the local backend without a frontend:

```bash
python -m ffsim serve
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.
The backend accepts one active simulation at a time and keeps job state in
memory.

```http
POST /api/simulations
Content-Type: application/json

{"simulations": 300, "seed": 2026, "workers": 4, "teams_only": false}
```

The response contains a job `id`. A frontend can then use:

- `GET /api/simulations/{id}` for the latest counters and status.
- `GET /api/simulations/{id}/events` for an SSE stream.
- `GET /api/simulations/{id}/results` for the final result object.

SSE event types are `queued`, `status`, `progress`, `complete`, and `failed`.
Every `progress` event includes the completed count, speed, championship
counts, playoff appearances, division wins, and the latest simulated outcome.

## Web frontend

A live dashboard for running and watching simulations lives in `web/`
(Vite + React + TypeScript).

```bash
python -m ffsim serve          # terminal 1: backend on http://127.0.0.1:8000
cd web
npm install
npm run dev                    # terminal 2: frontend on http://localhost:5173
```

The dashboard includes league selection: enter a Sleeper username, pick one
of that user's 2026 leagues, and the backend saves it to `config.json` and
refreshes its data snapshots (`GET /api/leagues?username=...`,
`POST /api/league`, `GET /api/league`).

The backend URL defaults to `http://127.0.0.1:8000`; override it with
`VITE_API_URL` (for example in `web/.env.local`). Frontend checks:

```bash
cd web
npm test                       # vitest unit tests
npm run build                  # type-check and production build
```

Use `--scenario scenarios.json` (or `scenario_file` in `config.json`) for
forward-looking assumptions:

```json
{
  "use_sleeper_projections": true,
  "game_environment_cv": 0.08,
  "team_environment_cv": 0.05,
  "competition_cv": 0.10,
  "players": {
    "SLEEPER_PLAYER_ID": {
      "projection_points": [275, 290],
      "projected_games": 14,
      "play_probability": {"1": 0.5, "2": 0.8},
      "missed_weeks": [3]
    }
  }
}
```

When `use_sleeper_projections` is true, refresh downloads Sleeper's current
season stat projections and the simulator rescores them under the league's
settings. `projection_points` adds other external full-season projections; the
simulator averages them with its league-rescored PFF total and uses their
disagreement to widen season uncertainty. Direct `projection_multiplier` and
`season_cv` values can override that calculation. Play probabilities and
missed weeks express player-specific availability. Game factors are shared by
both NFL opponents, team factors move teammates together, and competition
factors redistribute outcomes among same-team, same-position players while
preserving their projected group mean. All fields are optional and scenarios
are assumptions, not calibrated probabilities.

Username lookup uses the 2026 NFL season by default. If the user belongs to
multiple leagues, the command lists their names and IDs and requires an
explicit `--league-id`; it never guesses which league to simulate.

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

A cached 10-team development league with 418 rostered players took about 84 ms
per simulation with player summaries and 41 ms with `--teams-only`. Four workers
ran 100 simulations in 3.7 and 2.5 seconds respectively, including startup and
data loading. These are directional figures, not production guarantees. A
scheduled run remains inexpensive, while each website visit only downloads the
generated JSON.

The Python simulator already:

- Loads and parses matchup snapshots once per run.
- Precomputes immutable per-player distribution parameters and scoring coefficients.
- Tracks running aggregates unless plots require raw samples.
- Imports refresh and plotting dependencies only for commands that use them.

Consider extracting the simulation kernel into Rust only if users need uncached,
interactive scenarios and another profile shows that optimized Python cannot
meet the latency target. Rust compiled to WebAssembly could then run in the
browser while preserving static hosting.

## Correctness and calibration

PFF raw season projections are rescored under the cached league's Sleeper
settings. Nonzero settings that cannot be calculated from the checked-in
inputs fail with the unsupported keys listed. Compact 2024-2025 nflverse
play-by-play extracts support long-touchdown bonuses (rushing, receiving, and
passing), pick-sixes, blocked kicks, fumble-recovery touchdowns, and
special-teams turnovers. Defense yards-allowed buckets are modeled through the
projected points-allowed distribution using the historical joint
yards-versus-points table, and 60+ yard field-goal bonuses reuse the same
historical kick-distance draws as the yardage bonus. Historical
kick distances distribute PFF field-goal buckets, while historical return
splits divide PFF's combined kick/punt return-yard totals without changing
their combined mean.

Projection joins prefer a stable Sleeper ID when an input supplies one;
otherwise they require exact normalized name, position, and canonical team.
Refresh writes `data/cache/projection_matches.json`. A rostered player without
one unique, position-consistent projection is reported and unavailable. An
ambiguous or position-mismatched rostered projection still stops league
loading rather than borrowing another player's projection.

Weekly outcomes use normalized joint 2024-2025 nflverse vectors centered on
league-rescored 2026 PFF means. The corrected mean-preserving parametric kernel
remains the explicit baseline when a `Player` has no runtime empirical library.
The old injury CSV and age, depth-chart, boom/bust, injury, rank, and score-cap
modifiers are inactive.

Availability is separate from weekly shape. Across `H` future non-bye fantasy
weeks, a player projected for `G` of the NFL's 17 games has expected games
`H * G / 17`; stochastic rounding avoids fractional-game bias. A 14-week
fantasy regular season plus Weeks 15-17 playoffs covers 16 eligible games
because one NFL bye occurs in Weeks 1-14. Current rest-of-season projections
are required after completed games; preseason totals are not current ROS means.
When a current DraftSharks profile is imported, its season injury probability
decides whether an injury occurs and its projected games missed determines the
conditional absence length; this replaces the PFF-games availability path for
that player.

Completed Sleeper matchup points and starters are preserved and only future
weeks are simulated. Fully completed playoff brackets are preserved. A
partially completed fantasy playoff fails explicitly instead of being
resimulated.

## Backtest

```bash
python tools/backtest.py --samples 100
```

The split trains on 2024 and evaluates 2025. Because no 2025 preseason PFF
snapshot is present, this is explicitly an "oracle-mean distribution-shape"
backtest, not an end-to-end preseason forecast. Its JSON report includes bias,
error, dispersion, percentiles, skew, zero/bust/boom rates, CRPS, PIT,
coverage, Brier scores, correlations, and the Phase 3 feature grids.

The checked-in calibration keeps position/volume-tier joint vectors. Finite
personal-history shrinkage worsened 2025 CRPS, opponent weight 0 won its grid,
and a shared team factor failed to materially improve CRPS while worsening team
variance before repairing stack correlation, so those features are not active.

## Checks

```bash
python -m unittest discover -s tests -v
python -m compileall -q ffsim tests tools
```

Tests cover scoring regressions, roster-derived lineups, configuration, playoff scheduling, and JSON result generation.
