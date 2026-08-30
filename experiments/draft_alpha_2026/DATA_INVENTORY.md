# Data and model inventory

## Historical Sleeper corpus

Immutable snapshot:

`/Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3`

SHA-256: `c672898ff06819602fe52d06c606a01492194b053614f47d618876e6332579a5`

The accepted strict-ready cohort contains 10,013 league-seasons:

| Season | League-seasons |
|---|---:|
| 2021 | 928 |
| 2022 | 1,539 |
| 2023 | 2,151 |
| 2024 | 2,570 |
| 2025 | 2,825 |

The source schema contains:

- 1,848,180 draft picks across 2021–2025;
- 1,946,738 weekly matchup rows;
- 114,580 team-season outcome rows;
- draft ownership, traded-pick, roster, scoring, playoff, and raw-object provenance;
- 47,938 distinct non-null draft manager IDs;
- 6,879 managers observed in at least three seasons;
- 3,250 managers observed in at least four seasons.

The leakage-safe rolling-market database contains 10,013 target boards and 3,764,969 player-board rows. It has 8,712 supported exact-context boards. Development uses 2021–2023. The 2024 transfer result is seen diagnostic evidence. Experiment `02d` is the one-time 2025 model evaluation.

## Current 2026 projection inputs

| Input | Rows | Use |
|---|---:|---|
| `data/projections/players.csv` | 542 | PFF supplemental fields and K/DST means |
| `data/projections/defenses.csv` | 32 | 2026 D/ST projections |
| `data/projections/kickers.csv` | 32 | 2026 kicker projections |
| `data/projections/defense_matchups.csv` | 32 | Defense unit grades and matchup adjustment |
| `data/injuries/risk.csv` | 325 | 2026 injury occurrence and duration inputs |
| nflverse 2024–2025 extracts | checked in | Empirical weekly outcome shapes |

FantasyPros supplies the primary 2026 QB/RB/WR/TE counting-stat means. PFF fills targets, sacks suffered, fumbles lost, and return yards. Missing FantasyPros offensive players do not fall back to PFF.

These inputs support current 2026 VORP, roster-specific terminal marginal value, VONA, coupled draft completion, and `ffsim` season simulation. They do not provide historical point-in-time projection panels for 2021–2025.

## Available APIs and licensed inputs

| Source | Access | Current use | Research limit |
|---|---|---|---|
| Sleeper API | Public, read-only, tokenless | Leagues, users, rosters, drafts, picks, matchups, players, projections | Non-commercial use and general rate guidance below 1,000 calls/minute |
| FantasyPros API | `FANTASYPROS_API_KEY` | 2026 projections, players, consensus ADP by format | Current snapshots only; no accepted historical point-in-time source |
| FantasyCalc API | Public current endpoint | Dynasty and redraft market values | Fixed 10-team, 1-QB, PPR loader context |
| PFF export | Account/manual export | 2026 supplemental projections, kicker, D/ST | No automated historical point-in-time feed |
| DraftSharks export | Authorized session/manual import | 2026 injury risk | Current injury input only |
| nflverse releases | Public release assets | 2024–2025 empirical weekly shapes and scoring events | Outcome data, not preseason projections |
| Mike Clay 2026 guide | Manual PDF-derived grades | Defense matchup context | 2026 only |

## Model evidence

| Model | Result | Effect |
|---|---|---|
| Completed-draft neural network, 4,707 parameters | Rejected; points-percentile MAE `27.2402` versus historical-market `27.1805` | No historical outcome score in live recommendations |
| HDVN residual Ridge and neural corrections | Rejected in both discovery folds | No stable completed-roster correction beyond market |
| Exact empirical player survival | Passed support and calibration gates | Offline exact-cell evidence only; unavailable below 250 observations |
| Additive continuous survival | Rejected; elite long-gap prediction `26.63%` | No interpolation into unsupported timing cells |
| Rank-specific interaction logistic model | Rejected; elite long-gap prediction `36.92%` | No use |
| Shallow monotonic boosted survival tree | Rejected; elite long-gap prediction `17.50%` and one fold missed its gate | No use |
| Manager position over inverse ADP | Passed 2022 and 2023 rolling folds | Contains population and manager position signal |
| Manager residual beyond population position | Passed 2022 and 2023 rolling folds, 2024 transfer, and one-time 2025 benchmark | Strongest verified candidate |
| Manager residual survival impact | Rejected; Brier improved only `0.000338` and false-safe rate worsened | Choice log-loss alpha does not yet justify timing integration |
| Pooled rank-gap-round survival | Rejected; elite RB long-gap probability `6.07%` | Cross-position pooling corrupts the elite tail |
| Position-exact survival | Rejected; correct elite tail but only 37.4% and 56.8% rolling coverage | Accurate supported cells are too sparse |
| Hierarchical position survival | Passed both rolling folds and the seen 2024 transfer; 100% model lookup coverage | Strongest direct timing candidate; offline only |
| Hierarchical survival plus current VONA/VORP | Rejected saved-state surface gate; 59 of 60 required candidates | Five complete states are stable, but the current audit surface is incomplete |
| Exact survival plus current VONA/VORP | Rejected; 64.4% candidate and 33.3% full-state coverage | Do not fill unsupported cells or drive live timing |

The one-time 2025 manager-residual benchmark improved seen-manager player-choice log loss by `0.03193`. The paired draft-clustered difference was `-0.03193 [-0.03374, -0.03016]`. It improved all-pick log loss by `0.01429`. The trained model covers 12 of 25 configured 2026 managers at the fixed 20-pick support threshold.

## Main conclusion

The corpus has verified predictive alpha in opponent behavior. It does not yet have broad end-to-end pick-decision validation.

The locked static manager-position residual improves choice log loss but worsens top-five accuracy and the marginal-hazard survival approximation. Round phase improves static log loss by `0.02038` and `0.01401`. Corrected position-count state, including board-unsupported source picks, improves the round model by `0.01404` and `0.01397`, plus `0.01612` on the seen 2024 transfer. A full shadow callback leaves the baseline practical tier. At the full 300-rollout budget, the fixed 10% mixture retains the baseline leader in all six cached states and keeps every shadow leader inside the baseline practical tier.

The hierarchical position-survival model is the strongest direct timing candidate. Its Brier scores were `0.07053` and `0.07419` in the two rolling folds and `0.09450` in the seen 2024 diagnostic. Against the prior exact rank-gap-round baseline, rolling Brier improved by `0.01316` and `0.00475`; both paired draft-clustered upper bounds were below zero. Expected calibration error stayed below `0.038`, false-safe rate stayed below `0.069`, and the rank-2 RB, round-1, gap-18 estimate was `0.621%` from 2,006 direct observations. It has no untouched 2025 model-specific benchmark.

The safe 2026 architecture is:

1. Keep current projections, league scoring, VORP, coupled rollouts, and terminal projected-roster value as the live decision path.
2. Use the integrated fail-isolated `Draft alpha — shadow` panel for branch-specific return evidence and low-cost manager disagreement telemetry.
3. Do not rank candidates by one-turn route value. It selected terminal rank 23 with `12.49` paired points of regret in the measured state.
4. Keep the fixed 10% corrected roster-aware manager mixture offline until real live-shadow validation passes.
5. Do not use the completed-draft neural model.

Historical point-in-time projections remain the main missing dataset. The local PFF file lacks authoritative source timing and IDs. Sleeper historical rows were updated after each season. FantasyPros personal responses have no observation timestamps, and official historical access is Commercial. The strict importer is ready, but no source is accepted.

Keep player value and opponent behavior separate:

- current 2026 projections and league scoring determine player value;
- VORP measures projected points above the starter replacement cutline;
- VONA measures current roster-specific value over the next available alternative;
- the manager model estimates who opponents are likely to select;
- coupled rollouts and terminal projected-roster value remain the recommendation objective.

Hierarchical survival has complete branch capture, but it remains terminal-subordinate. It cannot replace coupled draft continuations or supply a standalone recommendation objective.

## Real-draft limits found in implementation review

- Next-turn survival must use exact snake/traded-pick geometry from the current draft state. A generic round gap is not sufficient.
- The branch top ten is a market state, not a legal-candidate list. Timing report v3 captures every market player, then marks next-turn eligibility separately.
- One-turn VONA route value is not a ranking objective. It can prefer a streamable position while ignoring the completed roster.
- Manager identity must map through the target draft's real roster ownership. Synthetic slot mapping is valid only for shadow experiments with the same template league.
- Corrected roster reconstruction updates board-unsupported historical picks from immutable source positions. The rolling and transfer results remain stable, but the model was selected after the one-time 2025 benchmark and has no untouched locked test.
- The 10% manager mixture passes six cached mock states at the full 300-rollout budget. This is full-budget cached-shadow evidence, not proof of average live-draft benefit.
- The 10% mixture was selected after inspecting draft `1393656492011315200`, which is one of the six corpus states. Only five states are new to the mixture, so the six-state result is not an independent holdout.
- The corpus contains cached mocks and has no realized user-draft outcome labels. Real live-shadow collection remains required.
- The integrated collector runs only after terminal publication, uses a separate daemon thread, discards stale states, and leaves the recommendation hash unchanged in cached monitor verification.
- Its 20-rollout manager result is telemetry, not a replacement for the full 300-rollout offline gate.
- Shadow jobs are serialized and coalesce to the newest pending state, so they do not overlap. They still share host CPU with the monitor; real telemetry must confirm that the measured five-second shadow does not delay a later pick calculation.
- The War Room exposes only aggregate manager support and fallback counts. Manager IDs remain internal replay inputs.
- No historical projection source passed point-in-time provenance. The importer must remain empty until an approved source exists.

## Integrated shadow audit

The first six-state integrated audit passed every correctness gate but failed latency with p95 `13.5098s`. Restricting the 20-rollout live manager comparison to the five terminal finalists reduces p95 to `6.7061s` and passes the development gate. Hierarchical timing itself has p95 `0.0583s`; manager simulation is the dominant cost.

The optimized audit records:

- six ready states and zero failures or discards;
- 100% complete top-ten capture;
- 100% manager practical-tier retention;
- 66.7% exact manager/terminal leader agreement;
- 397,524 personalized and 81,236 fallback callback calls;
- 48 supported and 10 fallback opponent-roster observations;
- 46.3% terminal-candidate return coverage;
- 53.7% terminal candidates outside the rank-10 model;
- direct support minimum 2 and median 869;
- median return-interval width 4.81 percentage points.

The development gate passes. The live evidence gate remains blocked at 6/30 new states. The current rank-10 hierarchy remains the live default while the validated rank-20 candidate is evaluated separately.

## Rank-20 survival candidate

The separately frozen rank-20 model fixes the terminal-candidate coverage gap without changing rank-1–10 behavior:

- all rank-1–10 materialized cells are row-equivalent;
- rolling rank-1–10 Brier changes are below `0.000001`;
- rank-11–20 Brier improves by `0.010101` and `0.001517`;
- seen 2024 rank-11–20 Brier improves by `0.008718`;
- rank-11–20 false-safe rates remain below `9.2%`;
- rank-band expected calibration error remains below `3.5%`;
- elite rank-2 RB gap-18 probability remains `0.621%`;
- six-state terminal-candidate coverage increases to `88.2%`;
- cached shadow p95 latency is `6.8113s`.

The rank-20 route objective still fails two terminal checks by 11.45 and 17.38 paired points. Use rank-20 only for return evidence. The live default remains the immutable rank-10 artifact until 30 new live states pass.

## Simple projected-points board

Projection monitoring now defaults to a simple top-ten list for each position. It ranks all undrafted players by league-scored projected season points. FantasyPros is the primary source for QB, RB, WR, and TE. PFF supplies K and DEF. The list ignores roster fit and replacement value by design. The detailed VORP, WORP, roster-value, ADP, and lookahead board remains available through `Full value`.