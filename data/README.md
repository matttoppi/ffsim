# Active data

Data status as of 2026-08-10. The simulator is being prepared for the 2026 NFL season: 2026 projections represent future means, while the archived 2024-2025 results are possible future calibration inputs.

## Checked-in inputs

| Path | Season | Purpose | Source/access |
| --- | --- | --- | --- |
| `projections/players.csv` | 2026 projections | Player season means and bye weeks | Manual PFF export; PFF account required |
| `projections/kickers.csv` | 2026 projections | Kicker subset generated from `players.csv` | `python tools/extract_special_teams.py` |
| `projections/defenses.csv` | 2026 projections | D/ST subset generated from `players.csv` | `python tools/extract_special_teams.py` |
| `injuries/risk.csv` | Unverified older snapshot | Injury probability and projected games missed | DraftSharks; current bulk data requires Insider access |

`python -m ffsim refresh` also downloads public Sleeper league/player data and FantasyCalc values. It writes ignored snapshots to `cache/`; neither public source needs an API key.

The injury CSV has no season field and should be replaced with a confirmed 2026 export before its probabilities are trusted.

## Algorithm boundary

`ffsim/models/player.py` derives weekly player scores from the PFF per-game means with hand-tuned lognormal and Poisson distributions. `ffsim/simulation/special_teams.py` uses rank-based random kicker and D/ST scores.

Historical experiments and unintegrated research datasets live under `archive/data/` and do not affect simulations. See [../archive/README.md](../archive/README.md).
