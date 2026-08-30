# Historical Draft Value Network Implementation Ledger

This ledger tracks the planned Historical Draft Value Network (HDVN) research project. The specification is [`HISTORICAL_DRAFT_VALUE_NETWORK.md`](HISTORICAL_DRAFT_VALUE_NETWORK.md).

## Project state

**State:** HDVN-06 and HDVN-R01 rejected their frozen gates; HDVN remains separate from live recommendations
**Live eligibility:** None
**Primary next ticket:** None
**Current blocker:** No tested completed-draft correction found stable alpha beyond the historical market

## Status vocabulary

- `Blocked`: A named prerequisite is unavailable.
- `Ready`: Dependencies pass and work can start.
- `In progress`: Active implementation.
- `Review`: Implementation exists but its acceptance gate is not complete.
- `Done`: Acceptance evidence is recorded.
- `Rejected`: The experiment failed its gate and will not advance.

## Ticket summary

| Ticket | Status | Depends on | Deliverable |
|---|---|---|---|
| HDVN-00 | Done | Frozen-data and year-balance gate | Frozen source snapshot and audit |
| HDVN-01 | Done | HDVN-00 | Point-in-time feature/provenance contract |
| HDVN-02 | Done | HDVN-00, HDVN-01 | Leakage-safe rolling market board |
| HDVN-03 | Done | HDVN-01, HDVN-02 | Versioned team-draft and prefix tables |
| HDVN-04 | Done | HDVN-00, HDVN-03 | Outcome labels and immutable split manifest |
| HDVN-05 | Done | HDVN-03, HDVN-04 | Context, linear, and boosted baselines |
| HDVN-06 | Rejected | HDVN-05, neural prototype data gate | Completed-draft neural model |
| HDVN-R01 | Rejected | HDVN-05, HDVN-06 result | Training-year residual-alpha discovery |
| HDVN-07 | Blocked | HDVN-06 | Prefix sampling and partial-value experiment |
| HDVN-08 | Blocked | HDVN-06, HDVN-07 | Ensemble uncertainty and calibration |
| HDVN-09 | Blocked | HDVN-07, HDVN-08 | Offline candidate-scoring experiment |
| HDVN-10 | Blocked | HDVN-05–HDVN-09 | Locked benchmark against existing methods |
| HDVN-11 | Blocked | HDVN-10 passes | Read-only shadow artifact and telemetry |
| HDVN-12 | Blocked | HDVN-11 evidence | Integration decision or rejection |

Preparatory tooling still requires each named final-corpus gate. HDVN-00 passed
its gate on 2026-08-28. HDVN-01 can now run against the accepted snapshot.

| Preparatory area | Evidence | Final ticket gate still pending |
|---|---|---|
| Native snapshot and provenance | `hdvn_snapshot.py` and disposable snapshot tests | HDVN-00 immutable final snapshot and readiness counts |
| Point-in-time feature contract | `hdvn_contract.py`, registry hash, and rejection tests | HDVN-01 validation against the final source manifest |
| Historical market source | Archived 2026-08-27 source audit | Point-in-time projection source remains unavailable |
| Rolling market board | `hdvn_market.py` exact-cutoff implementation and synthetic future-draft test | HDVN-02 final-snapshot coverage and stability reports |
| Team and prefix tables | `hdvn_tables.py`, bounded iterators, and deterministic sampling tests | HDVN-03 final-snapshot materialization |
| Labels and temporal split | `hdvn_labels.py` and synthetic label/split tests | HDVN-04 final labels and immutable 2025 ID manifest |
| Metrics, model protocol, and artifact contract | `hdvn_evaluation.py`, `hdvn_neural.py`, and fail-closed tests | HDVN-05 passed; HDVN-06 rejected its frozen gate |
| End-to-end dry run | `hdvn_synthetic.py` and `hdvn-dry-run` | No real fitting, selection, benchmark, shadow, or integration |

## Final corpus evidence

### HDVN-00 acceptance — 2026-08-28

- Source data directory: `/Users/matt/.cache/ffsim/historical_sleeper`.
- Snapshot: `/Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3`.
- Snapshot manifest: `/Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3.manifest.json`.
- Acceptance sidecar: `/Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json`.
- Snapshot SHA-256: `c672898ff06819602fe52d06c606a01492194b053614f47d618876e6332579a5`.
- Snapshot manifest SHA-256: `e53ea52eb6f6e023a5f0e424c0452f248e632a3431098a8316521024aa870b82`.
- Acceptance sidecar SHA-256: `85a82b2b7db5996e31d168c19b98ab981f1096171104098f64dc9111004c3e01`.
- Source identity: device `16777231`, inode `8414480`, 5,258,244,096 bytes.
- Snapshot identity: device `16777231`, inode `15395854`, 5,258,244,096 bytes.
- SQLite acceptance: integrity `ok`; zero foreign-key errors; immutable read-only journal mode `delete`; no WAL or shared-memory dependency.
- Strict-ready cohort: 10,013 league-seasons. Year counts are 928 (2021), 1,539 (2022), 2,151 (2023), 2,570 (2024), and 2,825 (2025).
- Hydration states: 10,097 done and 570 failed. Quality flags contain 90 error-level and two information-level rows.
- Raw trace `hdvn-raw-trace-v1`: 5,738,039 canonical references, 535,641 distinct referenced hashes, and 646,241 registered objects. All registered objects decompressed and matched their byte count and SHA-256.
- Raw trace errors: zero missing database references, missing files, corrupt gzip files, wrong byte counts, wrong hashes, unsafe paths, and duplicate registrations. The audit records 110,600 registered objects without canonical-table references and 22 unregistered raw files.
- Graph provenance remains in the snapshot manifest by seed, discovery depth, and mechanism.
- Acceptance command: `python3 -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-accept-snapshot --snapshot /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3 --output /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json`.
- The snapshot, manifest, and acceptance sidecar have mode `0444`. A repeated `hdvn-snapshot` command failed with `FileExistsError`.

### HDVN-01 acceptance — 2026-08-28

- Final manifest: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json`.
- Registry hash: `5d39815ccbe3dfcf39b76ec2b7d3da2243391c062dd92aff03f1fd4195a13a57`.
- Manifest file SHA-256: `9c8ff84d9d079983fa15260f398c6361d32fb5829988d136300f531a7065af43`.
- Source snapshot SHA-256: `c672898ff06819602fe52d06c606a01492194b053614f47d618876e6332579a5`.
- Source manifest SHA-256: `e53ea52eb6f6e023a5f0e424c0452f248e632a3431098a8316521024aa870b82`.
- Source acceptance SHA-256: `85a82b2b7db5996e31d168c19b98ab981f1096171104098f64dc9111004c3e01`.
- The `market_and_construction_only` registry contains 71 entries. Each entry records its source, type, observation rule, transformation, null meaning, leakage class, completed-draft availability, prefix availability, and model eligibility.
- The materialized contract registers 48 team columns and 36 sampled-prefix columns. It names 31 team and 19 prefix model-eligible columns.
- Focused tests reject labels, prohibited facts, audit-only player IDs, post-draft observations, unregistered materialized columns, unused eligible columns, and feature-manifest overwrite.
- Finalization command: `python3 -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-feature-manifest --snapshot-manifest /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3.manifest.json --acceptance /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json --output /Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json`.
- The manifest has mode `0444`. Repeating the finalization command failed with `FileExistsError`.

### HDVN-02 acceptance — 2026-08-28

- Market database: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3`.
- Market report: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.report.json`.
- Market manifest: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.manifest.json`.
- Manifest contract hash: `540ef8748897e616d31c2ad8ead3e56ff3018a95a5b0819f8c28b82bd77f6092`.
- Manifest file SHA-256: `4d3ce97addb646b16c9abd52b3fd745c3239bbee6546011050e1c8483e80be2d`.
- Database SHA-256: `45650d7c42d1d18b6dd39a67143abe12d79ce880e8ba1854aa81365894a31157`.
- Report SHA-256: `0bfafb55f906b241bb2765e435192e94bc3b4b9882b62be032813707e0084d56`.
- Rows: 10,013 target boards, 3,764,969 target-player rows, and 1,731,266 market-only pick-baseline rows.
- Exact-context support threshold: 25 prior drafts. The final artifact provides 8,712 boards and returns 1,301 sparse boards unavailable without fallback.
- Coverage by year is 657/928 (2021), 1,299/1,539 (2022), 1,878/2,151 (2023), 2,320/2,570 (2024), and 2,558/2,825 (2025).
- Prior-draft support has minimum 0, 25th percentile 59, median 195, 75th percentile 437, and maximum 1,431.
- Staleness has minimum 15 ms, median 2,278,075.5 ms, 75th percentile 11,464,351 ms, and maximum 11,184,366,117 ms for 9,902 supported source histories.
- Consecutive-board mean absolute rank change has median 0.04194 and 75th percentile 0.39543 across 8,671 comparisons.
- The generator uses one chronological source pass, 72 bounded context accumulators, zero per-target history queries, and 10,013 indexed target-pick queries.
- Target/future exclusion violations: zero. Synthetic tests include a future draft that changes rank when leaked, a target with anomalous pre-start completion metadata, and duplicate player observations within one source draft.
- A repeated full generation produced identical database and report SHA-256 values and identical board, player, and market-pick row hashes. The repeated manifest differs only because it records the distinct output command.
- Finalization command: `python3 -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-market --snapshot /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3 --acceptance /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json --features /Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json --output /Users/matt/.cache/ffsim/historical_sleeper/hdvn --min-support-drafts 25`.

### HDVN-03 acceptance — 2026-08-28

- Output directory: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828`.
- Table manifest contract hash: `b68b9d4a2821991d36cebf437098048ce457c9a592fa81965fd8e50ecf34d79e`.
- Table manifest file SHA-256: `d671622144953ea023e36def19c3319d2dc9091a8313b7ec64345888690f7765`.
- Team table: 113,646 rows, 24,465,339 bytes, SHA-256 `8dbd443dd20304b777d7e3ce399a2dedd2db6d565e63e5fc6d81763f0bc0deed`, row-equivalence hash `1412affd863dbf551cac4275b7b912e5dd1ba21fb8176ed51661038fef045c8d`.
- Team eligibility: 113,634 rows are eligible. Twelve rows from one league have `missing_team_picks`; the exclusion applies to the full league for partition and championship-loss safety.
- Prefix table: 113,634 rows, 21,742,367 bytes, SHA-256 `ddc64ba3ab01712327fc581df5b0724f7baf585571d007d4dcc2b03845a08c4f`, row-equivalence hash `8e802e7e020e304bd069ca464a52be98b4b309cd238d7a1d4e00f32e40260f19`.
- Prefix sampling uses seed 20,260,828 and epoch 0. It produced one row and weight 1.0 for each eligible team-season. Total weight is 113,634.
- Bucket counts are 37,884 early, 37,875 middle, and 37,875 late. The deterministic cyclic bucket assignment differs by at most one before unavailable-team exclusions and by nine on the final cohort.
- The canonical team table contains no strategy labels. Inverse-prefix weighting remains a named, non-materialized benchmark.
- Market-supported rows: 99,078 team rows and 99,122 sampled-prefix rows.
- Hydration-cohort exclusions: 570 not hydrated, 45 incomplete draft, 43 not strict-ready, 41 error-quality, two keeper draft, two keeper-pick cohort, and two unsupported-format flags. Reasons can overlap.
- Both tables record full schemas, context counts by year/scoring/team count/draft slot, source/feature/label/market versions, file hashes, and deterministic commands.
- Parquet writers use 10,000-row batches. Team generation retains one draft at a time. Direct prefix sampling builds only the selected prefix and does not materialize the full prefix corpus in Python memory.
- A repeated full generation produced identical Parquet file SHA-256 values and identical team/prefix row-equivalence hashes. The repeated manifest differs only because it records the distinct output command.
- Finalization command: `.venv/bin/python -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-tables --snapshot /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.sqlite3 --acceptance /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json --features /Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json --market-database /Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.sqlite3 --market-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.manifest.json --output /Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828 --seed 20260828 --epoch 0 --batch-size 10000`.

### HDVN-04 acceptance — 2026-08-28

- Output directory: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828`.
- Label contract hash: `45fdf276a87eddf47443ff911d76affdc0052a8b55b2aea7c4dfaa11506747b2`.
- Label/split manifest contract hash: `2156478cd6f01c81abc2232302afa0f0e8fe5d16e4424bed7157a9e91d988713`.
- Label/split manifest file SHA-256: `11b4f06a0660b1d60fc3c29ac29f3e44125569a96f219c2f754c7126653d666c`.
- Labels table: 113,646 rows, 1,245,403 bytes, SHA-256 `354ce60f8201b4a1185a7370a2619402708663855d21f6fde8049f54855b3e4a`.
- Label acceptance reproduces 10,013 league-seasons and 10,013 champion events. It has zero null labels and zero leagues without exactly one champion.
- Points percentile uses commissioner-adjusted matchup points. Head-to-head win percentage gives ties half a win. Raw source facts remain in the frozen SQLite snapshot; the labels table contains only identities, versions, and derived labels.
- Split manifest contract hash: `be325518a01e0a7a1cf0fa22d961a687c750ba13b2fa6152204f2edd6ae6505f`. File SHA-256: `0b338926d1fc8df8d8ec4d6a021a764049bbb2c4da4b660dc6a3267f5dcb5d41`.
- Train has 4,617 league-seasons, 51,980 teams, and 4,617 champion events from 2021–2023.
- Validation has 2,570 league-seasons, 29,178 teams, and 2,570 champion events from 2024.
- Locked test has 2,825 league-seasons, 32,476 teams, and 2,825 champion events from 2025.
- One 12-team 2021 league is excluded from every fitted partition because its draft has a roster with no owned picks. The label audit retains this league, but the team/prefix model cohort does not.
- The split records 30 year/scoring/team-count contexts and 36 partition/draft-slot slices. Team and prefix isolation checks pass against the exact league-season ID lists.
- Locked 2025 manifest contract hash: `f757a127de02e33ff3d4f263a24eb97f45a75dea6c58c2fa12376f84fae80d04`. File SHA-256: `85aa805331958763b5d037d61cdc7bbaecef61c32b88fe909c282ed44c3fd01f`.
- Partition files: train SHA-256 `feb4acfc5d322040ded79b03e4619d490b32903f5cc5fbace7a1eafa1ad8987d`; validation SHA-256 `30f0d54212bf153cd81c76c514a38923d1e614fb4990028619ed3255e0e8db00`; locked test SHA-256 `d787c5473031ee62303b8a3232515c6dd5d883e8638e49d20a7e037ef6c0fbb5`.
- The split, locked manifest, locked Parquet file, and aggregate manifest have mode `0444`.
- Ordinary `load_team_partition(..., "locked_test")` failed before opening the locked Parquet file with `PermissionError: locked 2025 test access requires the locked-benchmark command`.
- Finalization command: `.venv/bin/python -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-labels-split --acceptance /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json --features /Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json --tables-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828/tables-v1.manifest.json --team-table /Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828/team-v1.parquet --prefix-table /Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828/prefix-v1.parquet --output /Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828 --batch-size 10000`.

### HDVN-05 acceptance — 2026-08-28

- Output directory: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/baselines-final2-20260828`.
- Bundle contract hash: `1b52634159e610d18561e53233b5913165d3536447fb051178d87625e99dcc1a`.
- Bundle manifest file SHA-256: `5bbedcfbb3cda5a7fd94f48a786639348d2d3f2760be40e1e082cfa3d4bac919`.
- Model bundle SHA-256: `3ba67417fa60ba6a436b0a4dbe89526d28e620cb9682d077ce5d877b170378ea`.
- 2024 predictions SHA-256: `4da8193b823c223e24e7a617cbd0e0ccc944f0dd36a164491115ea0a1149aa5c`.
- Validation report SHA-256: `a592c1ea3970f57fa1a2451eb97c2cd0477e64a051937606f0299aee2c414ae4`.
- Fitting loaded 51,980 teams from 4,617 train league-seasons (2021–2023). Evaluation loaded 29,178 teams from 2,570 validation league-seasons (2024).
- Loaded partitions are exactly `train` and `validation`. The manifest records `locked_test_loaded: false`. The prediction Parquet file contains only season 2024.
- All five artifact statuses are `research`. There is no live status or live loader.

| Baseline | Points MAE, 95% cluster interval | Points RMSE, 95% cluster interval | Playoff log loss, 95% cluster interval | Playoff Brier, 95% cluster interval | Championship log loss, 95% cluster interval | Roster concordance |
|---|---:|---:|---:|---:|---:|---:|
| Uniform championship | 27.41657 [27.40945, 27.42630] | 31.53469 [31.52716, 31.54497] | 0.691206 [0.690842, 0.691497] | 0.249030 [0.248848, 0.249175] | 2.425954 [2.422194, 2.428720] | 0.50000 |
| Draft slot and context | 27.39550 [27.38640, 27.40422] | 31.51013 [31.50080, 31.51970] | 0.686660 [0.686156, 0.687112] | 0.246776 [0.246526, 0.246999] | 2.410790 [2.406013, 2.414589] | 0.54505 |
| Historical market value | 27.18046 [27.15163, 27.21311] | 31.32440 [31.29532, 31.35486] | 0.684163 [0.683353, 0.685013] | 0.245545 [0.245152, 0.245961] | 2.403916 [2.397180, 2.412434] | 0.54495 |
| Regularized linear/logistic | 27.32122 [27.26638, 27.37973] | 31.62356 [31.56702, 31.68584] | 0.688887 [0.687807, 0.690238] | 0.247858 [0.247344, 0.248504] | 2.420150 [2.414696, 2.424168] | 0.51990 |
| Gradient-boosted trees | 27.62277 [27.54662, 27.70668] | 32.08419 [32.00851, 32.16096] | 0.687449 [0.685860, 0.689358] | 0.247142 [0.246370, 0.248071] | 2.433596 [2.428057, 2.438173] | 0.50354 |

- Bootstrap intervals use 200 league-season cluster resamples with fixed per-baseline seeds.
- Championship probabilities are normalized within each league and pass the exact sum-to-one check.
- The context model has zero missing-feature rows. Market, regularized, and boosted models report 2,782 validation rows without a supported rolling market board. All models emit predictions for every validation row.
- Deterministic feature orders are stored for context, market, full regularized, and full boosted inputs. The full inputs use only registered point-in-time context, construction, and rolling-market features.
- Championship temperature calibration used 2024 only: 0.5 for context and market models, and 2.0 for regularized and boosted models.
- A second full fit produced identical model, prediction, and validation-report SHA-256 values. Its manifest differs only because it records a distinct output command.
- Fail-closed bundle loading verified the manifest hash, every file hash, allowed statuses, expected feature hash, and `locked_test_loaded: false`.
- Point-in-time projections remain unavailable. Current projections, deterministic projection lookahead, and coupled `ffsim` rollouts were not substituted.
- Pinned research dependencies are `numpy==2.5.2`, `pyarrow==25.0.1`, and `scikit-learn==1.9.0`.
- Fit command: `.venv/bin/python -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-baselines --acceptance /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json --features /Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json --tables-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828/tables-v1.manifest.json --market-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.manifest.json --labels-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828/labels-split-v1.manifest.json --split-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828/split-v1.json --output /Users/matt/.cache/ffsim/historical_sleeper/hdvn/baselines-final2-20260828 --code-revision fa216d2ece2e633002911621be8a19d9b5d2a562+working-tree --seed 20260828 --bootstrap-samples 200`.

### HDVN-06 rejection — 2026-08-28

- Frozen primary gate: 2024 points-percentile MAE at most `27.08046` and the upper bound of each fixed-seed 95% league-season clustered interval for neural-minus-baseline absolute error below zero against context, historical-market, regularized-linear, and boosted-tree baselines.
- Result: `Rejected`. Neural MAE is `27.24022`; it exceeds the threshold by `0.15976`. The paired difference against the strongest historical-market baseline is `+0.05976` with interval `[+0.01488, +0.10715]`.
- Output directory: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/neural-final-20260828`.
- Artifact contract hash: `6d7adcf3a24c3670e19e664f202313563bfe55d9d2fcd7955f99f4938d553a7a`.
- Artifact manifest file SHA-256: `54b9457fc6b41838a50b32862c5568f83d00dd9b5c54c011060b5a28b153efab`.
- Model SHA-256: `0c4996a7f23f8de00b2ef069720ff5529024aa7c7fdca915a1b48d3a63def4b8`.
- 2024 predictions SHA-256: `cb3fc2384cda45b7fbf1bc52cc385265cc6233fc543f1241db458b2ee648e33d`.
- Validation report SHA-256: `4c2168e48f069a10385799cba01a184425695990c28835d8242d717ffe906b1e`.
- Source, feature, market, table, label, split, and baseline contract hashes are `c672898ff06819602fe52d06c606a01492194b053614f47d618876e6332579a5`, `5d39815ccbe3dfcf39b76ec2b7d3da2243391c062dd92aff03f1fd4195a13a57`, `540ef8748897e616d31c2ad8ead3e56ff3018a95a5b0819f8c28b82bd77f6092`, `b68b9d4a2821991d36cebf437098048ce457c9a592fa81965fd8e50ecf34d79e`, `45fdf276a87eddf47443ff911d76affdc0052a8b55b2aea7c4dfaa11506747b2`, `be325518a01e0a7a1cf0fa22d961a687c750ba13b2fa6152204f2edd6ae6505f`, and `1b52634159e610d18561e53233b5913165d3536447fb051178d87625e99dcc1a`.
- Code revision is `fa216d2ece2e633002911621be8a19d9b5d2a562+working-tree`; `hdvn_neural.py` SHA-256 is `4593580b397035fe7cbdfb9f44c73676714a04f966c7f19834a6c117a4fa2f06`.
- Architecture: 20-feature player-ID-free pick vector, shared `20 -> 32` rectified linear unit encoder, explicit-mask mean/max pooling, 16 league/rolling-market context features, shared `80 -> 48` multilayer perceptron, and points/playoff/within-league championship heads. Trainable parameters: 4,707.
- Optimizer: Adam, learning rate `0.001`, betas `0.9/0.999`, epsilon `1e-8`, L2 `1e-5`. Loss weights are points `1.0`, playoff `0.1`, and championship `0.1`. Seed: `20260828`. Batch size: 128 complete league-seasons.
- Early stopping used 2024 points-percentile MAE, maximum 40 epochs, patience six, and minimum improvement `0.001`. The selected checkpoint is epoch 7; training stopped after epoch 13. Fixed 2024 calibration selected playoff and championship temperatures of `1.0`.
- Fitting loaded 51,980 teams from 4,617 train league-seasons (2021–2023). Evaluation loaded 29,178 teams from 2,570 validation league-seasons (2024).

| Neural metric | 2024 estimate | 95% league-season cluster interval |
|---|---:|---:|
| Points-percentile MAE | 27.24022 | [27.18108, 27.30409] |
| Points-percentile RMSE | 31.57994 | [31.50989, 31.64294] |
| Playoff log loss | 0.685758 | [0.684501, 0.686974] |
| Playoff Brier | 0.246334 | [0.245713, 0.246931] |
| Within-league championship log loss | 2.417689 | [2.410969, 2.423548] |
| Within-league roster concordance | 0.53090 | Not bootstrapped |

| Baseline | Baseline points MAE | Neural minus baseline absolute-error mean, 95% cluster interval |
|---|---:|---:|
| Uniform championship | 27.41657 | -0.17634 [-0.23439, -0.10692] |
| Draft slot and context | 27.39550 | -0.15528 [-0.22080, -0.08875] |
| Historical market value | 27.18046 | +0.05976 [+0.01488, +0.10715] |
| Regularized linear/logistic | 27.32122 | -0.08099 [-0.13123, -0.03449] |
| Gradient-boosted trees | 27.62277 | -0.38254 [-0.44168, -0.33413] |

- Calibration buckets, all scoring-format/team-count/draft-slot slices, and every baseline metric are in `validation-report.json`. Playoff buckets cover 29,178 rows; championship buckets cover 29,178 rows.
- Scoring-format points MAE is `27.25871` for half-PPR (3,542 rows), `27.23923` for PPR (25,484), and `26.97630` for standard (152). Team-count points MAE is `27.50655` for 10 teams (8,310) and `27.13417` for 12 teams (20,868).
- Draft-slot points MAE for slots 1 through 12 is `28.51672`, `26.81960`, `26.77276`, `27.47728`, `27.36600`, `26.99054`, `27.08227`, `26.93045`, `27.34508`, `27.50925`, `26.92015`, and `26.93141`.
- Market support covers 26,396 validation rows. The 2,782 missing-feature rows are 9.5346% of validation. Mean pick-level market coverage is 0.90264; support-draft minimum/median/maximum is 0/271/1,224. Every row still has every prediction.
- The maximum absolute within-league championship probability-sum error is `4.440892098500626e-16`.
- Repeated prediction generation produced the identical SHA-256 `cb3fc2384cda45b7fbf1bc52cc385265cc6233fc543f1241db458b2ee648e33d`.
- The loader opened only `team-train-v1.parquet` and `team-validation-v1.parquet`. The artifact records `locked_test_loaded: false`; no 2025 file or row was opened.
- Fail-closed loading verifies the manifest and file hashes, exact source/feature/market/table/label/split/status expectations, deterministic feature order, parameter shapes, and parameter count.
- Limitations: no accepted point-in-time historical projections; market-and-construction inputs only; completed drafts only; one model and no ensemble/tuning; offline research only.
- Fit command: `.venv/bin/python -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-neural --acceptance /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json --features /Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json --tables-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828/tables-v1.manifest.json --market-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.manifest.json --labels-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828/labels-split-v1.manifest.json --split-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828/split-v1.json --baseline-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/baselines-final2-20260828/baseline-bundle.manifest.json --output /Users/matt/.cache/ffsim/historical_sleeper/hdvn/neural-final-20260828 --code-revision fa216d2ece2e633002911621be8a19d9b5d2a562+working-tree --seed 20260828 --batch-size 128 --bootstrap-samples 200`.

### HDVN-R01 rejection — 2026-08-28

- Result: `Rejected`. No frozen correction improved points-percentile MAE by at least `0.05` in both rolling training-year folds.
- Output directory: `/Users/matt/.cache/ffsim/historical_sleeper/hdvn/residual-alpha-final-20260828`.
- Artifact contract hash: `d16de077fa54c66f17a940f72c952b5369208e4254338c3aed4c268a145182ed`.
- Artifact manifest file SHA-256: `a9bcd9752c5e32e49711d94ca39d0f834a09753f265343de1f92a25b872be38b`.
- Predictions SHA-256: `8a1f15f2901d5ecd2d0262cf533ba760a6f4db702a751395d5cbe285b3b5c71a`.
- Report SHA-256: `4c990c624b8f8e79aab91242d3cf102f8a35246908c647f4dbfab0a698787c03`.
- Code revision is `fa216d2ece2e633002911621be8a19d9b5d2a562+working-tree`; `hdvn_residual.py` SHA-256 is `8df9e01e2b6dcdf0aedff8e2de465a1f5482c02ba9f191db99746a9ed6a461b1`.
- Fold one trained on 10,402 teams from 927 league-seasons in 2021 and validated on 17,360 teams from 1,539 league-seasons in 2022.
- Fold two trained on 27,762 teams from 2,466 league-seasons in 2021–2022 and validated on 24,218 teams from 2,151 league-seasons in 2023.

| Method | 2022 MAE, improvement | 2023 MAE, improvement | Pooled correction-minus-market absolute-error difference, 95% cluster interval |
|---|---:|---:|---:|
| Historical market | 27.36880, baseline | 27.32529, baseline | baseline |
| Roster-summary Ridge correction | 27.75808, -0.38928 | 27.30511, +0.02018 | +0.15078 [+0.10540, +0.19311] |
| Pick-sequence Ridge correction | 28.26274, -0.89394 | 27.39986, -0.07457 | +0.41668 [+0.32170, +0.50626] |
| Combined Ridge correction | 28.24695, -0.87815 | 27.40774, -0.08245 | +0.41468 [+0.33547, +0.49865] |
| Masked sequence neural correction | 27.61633, -0.24753 | 27.37384, -0.04855 | +0.13163 [+0.08548, +0.18529] |

- Pooled across both folds, market MAE/RMSE is `27.34346/31.58203`. Roster Ridge is `27.49424/31.88492`; sequence Ridge is `27.76014/32.41716`; combined Ridge is `27.75814/32.41728`; sequence neural is `27.47509/31.92132`.
- The only feature slice with positive correction in both years was an exploratory standard-scoring roster-Ridge slice: `+0.23779` MAE improvement on 188 rows in 2022 and `+0.25840` on 176 rows in 2023. It covers only 31 league-seasons, and its pooled paired interval `[-0.67398, +0.12954]` includes zero. It is not validated alpha.
- The report contains all season, scoring-format, team-count, draft-slot, market-support, missing-feature, and method slices. The 41,578 validation-fold rows contain 5,750 missing-market rows; support-draft minimum/median/maximum is 0/163/956.
- Five-fold league-season-grouped out-of-fold market predictions supplied training residuals. Corrections used fixed feature groups and methods declared before fitting.
- Both neural fits repeated exactly. Repeated Parquet generation produced the identical SHA-256 `8a1f15f2901d5ecd2d0262cf533ba760a6f4db702a751395d5cbe285b3b5c71a`.
- The loader opened only `team-train-v1.parquet`. It did not open the 2024 validation file or the 2025 locked-test file. The artifact records `validation_2024_loaded: false` and `locked_test_loaded: false`.
- The result rejects these frozen residual corrections. It does not discard the historical corpus or authorize a post-hoc slice model.
- Command: `.venv/bin/python -m ffsim.historical_sleeper --data-dir /Users/matt/.cache/ffsim/historical_sleeper hdvn-residual-alpha --acceptance /Users/matt/.cache/ffsim/historical_sleeper/snapshots/hdvn-final-20260828.acceptance.json --features /Users/matt/.cache/ffsim/historical_sleeper/hdvn/hdvn-features-v1.json --tables-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/tables-final-20260828/tables-v1.manifest.json --market-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/market-v1.manifest.json --labels-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828/labels-split-v1.manifest.json --split-manifest /Users/matt/.cache/ffsim/historical_sleeper/hdvn/labels-split-final-20260828/split-v1.json --output /Users/matt/.cache/ffsim/historical_sleeper/hdvn/residual-alpha-final-20260828 --code-revision fa216d2ece2e633002911621be8a19d9b5d2a562+working-tree --seed 20260828 --bootstrap-samples 200`.


## Final verification — 2026-08-28

- `.venv/bin/python -W error -m unittest ffsim.historical_sleeper.test_hdvn_residual` passed four focused HDVN-R01 tests.
- `.venv/bin/python -W error -m unittest ffsim.historical_sleeper.test_hdvn ffsim.historical_sleeper.test_hdvn_neural ffsim.historical_sleeper.test_historical_sleeper` passed 60 tests.
- `.venv/bin/python -W error -m unittest tests.test_live tests.test_api tests.test_simulation tests.test_draft_history tests.test_draft_state` passed 77 tests.
- Final snapshot acceptance, feature/table/label/split artifacts, baseline fitting, HDVN-06, and HDVN-R01 all used the explicit `/Users/matt/.cache/ffsim/historical_sleeper` data directory.
- HDVN-R01 repeated both neural fits and prediction generation exactly.
- HDVN-R01 opened only the train partition. It did not open the 2024 validation file or 2025 locked-test file.
- HDVN-06 and HDVN-R01 are `Rejected`. HDVN-07 remains blocked and was not initialized.
- No hyperparameter tuning, ensemble, locked benchmark, shadow mode, or live artifact was created.
- No simulation, API, live recommendation, VONA, WORP, frontend, or ranking implementation file changed for HDVN. The 77 live boundary tests pass.
- The separate OPP-01 offline choice/survival slice reused the accepted market corpus without changing HDVN ticket status. Its compliant run queried 2021–2024 only; 2025 remained untouched.
- No commit is safe. The complete `ffsim/historical_sleeper` package and HDVN documents were already untracked before this work, while the main implementation ledger already had unrelated user changes. Git cannot separate the pre-existing unpublished content from this slice without committing user work.

## Ticket details

### HDVN-00 — Freeze and audit the research dataset

**Goal:** Create a reproducible source boundary before feature work.

**Dependencies:**

- at least 2,500 strict training-ready league-seasons;
- at least 500 strict ready league-seasons from every target year;
- collector validation passes;
- active database copied with SQLite native backup.

**Work:**

- snapshot the historical SQLite database without stopping collection;
- record database hash, schema version, table counts, year/context counts, quality flags, and raw-object coverage;
- verify canonical key uniqueness and training-ready predicates;
- record graph seed/depth provenance and sampling limitations.

**Acceptance:**

- one immutable snapshot and manifest reproduce all recorded counts;
- no error-level training row enters the ready cohort;
- every team, pick, and prefix can be traced to raw source hashes;
- the snapshot is not the active crawler database.

### HDVN-01 — Define the point-in-time feature contract

**Goal:** Make every training feature auditable at the historical draft timestamp.

**Work:**

- list each V1 league, pick, roster, board, and prefix feature;
- classify each feature as source, derived-before-draft, label, or prohibited;
- define missing/unknown handling without fallback guessing;
- version feature normalization and categorical vocabularies;
- explicitly exclude current projections and post-season facts from draft-time inputs.

**Acceptance:**

- every feature has source, observation time, transformation, null semantics, and leakage classification;
- automated fixtures reject features observed after the target draft;
- player identity is not required by the primary cross-season model.

### HDVN-02 — Build a leakage-safe historical market board

**Goal:** Supply market-relative draft features without future information.

**Work:**

- verify whether an authorized timestamped historical board is available;
- otherwise build rolling population ranks from drafts completed before each target draft;
- isolate by season, format, team count, and observation time where coverage permits;
- define partial-pooling behavior for sparse contexts;
- record board support and staleness per target draft.

**Acceptance:**

- no target or later draft contributes to its market board;
- reconstruction is deterministic from the snapshot;
- coverage, rank stability, and missing-context rates are reported by year;
- a simple market-only pick baseline can consume the board.

### HDVN-03 — Create team-draft and prefix training tables

**Goal:** Produce bounded, analysis-ready training inputs.

**Work:**

- create one completed-draft row per team-season with sequence and summary features;
- create prefix records with current roster, pick geometry, and remaining-board summary;
- retain league-season, team, draft, pick, feature-version, and source-manifest keys;
- implement one sampled prefix per team per epoch;
- add optional inverse-prefix weighting as a named benchmark only.

**Acceptance:**

- total training weight per team-season is constant;
- no prefix crosses its league-season partition;
- early/middle/late prefix coverage is reported;
- table generation streams or batches and does not load the corpus into memory;
- repeated generation is byte- or row-equivalent for the same manifest.

### HDVN-04 — Define labels and immutable temporal splits

**Goal:** Make outcome and holdout semantics explicit.

**Work:**

- define points-for percentile, win percentage, playoff, and champion labels;
- verify exactly one champion per included league-season;
- create 2021–2023 train, 2024 validation, and 2025 locked-test manifests;
- retain whole leagues in one partition;
- define seed/depth sensitivity partitions.

**Acceptance:**

- label fixtures cover ties, custom points, incomplete brackets, and excluded quality flags;
- no team or prefix from one league-season appears in two partitions;
- the 2025 manifest hash is recorded before model selection;
- split counts and champion events are reported by context.

### HDVN-05 — Train required simple baselines

**Goal:** Establish the bar a neural network must beat.

**Work:**

- context-only points/playoff/championship baselines;
- market-and-construction regularized linear/logistic models;
- gradient-boosted tree benchmark;
- uniform `1 / team_count` championship baseline;
- current projection/`ffsim` comparisons only where point-in-time projections are valid.

**Acceptance:**

- all baselines use identical feature and split manifests;
- points mean absolute error, playoff/championship log loss, Brier score, calibration, and league ranking are reported;
- bootstrap uncertainty is clustered by league-season;
- baseline artifacts and predictions are reproducible.

### HDVN-06 — Train the completed-draft neural model

**Goal:** Test whether a small neural model improves completed-draft outcome scoring.

**Dependencies:**

- HDVN-05 done;
- at least 5,000 strict training-ready leagues;
- at least 500 ready leagues per target year;
- leakage-safe market coverage passes.

**Work:**

- implement shared pick encoding and permutation-aware roster pooling;
- keep V1 below 100,000 trainable parameters unless a decision records why not;
- train points, playoff, and within-league championship heads;
- record optimizer, loss weights, seeds, stopping rule, and parameter count.

**Acceptance:**

- model beats context-only and market/linear baselines on validation;
- neural versus boosted-tree comparison is complete;
- championship probabilities sum to one within each league;
- calibration and context slices are reported;
- failure to beat the simple baselines marks the ticket `Rejected` and blocks neural expansion.

**Frozen pass rule — 2026-08-28, before neural fitting:**

- The primary gate is 2024 points-for-percentile mean absolute error (MAE).
- The neural MAE must be at least 0.10 percentile points lower than every required fitted simple baseline. The strongest current bar is the historical-market MAE of 27.18046, so the fixed threshold is MAE `<= 27.08046`.
- For each required context, historical-market, regularized-linear, and boosted-tree comparison, the upper bound of the fixed-seed 95% league-season clustered bootstrap interval for `neural absolute error - baseline absolute error` must be below zero.
- Points root mean squared error (RMSE), playoff and championship losses, calibration, within-league ranking, support, coverage, and context slices are secondary reported metrics. They cannot rescue a failed primary gate.
- Dataset isolation, championship normalization, deterministic repetition, the parameter limit, and fail-closed artifact checks are mandatory validity gates. A validity failure rejects the experiment.
- The rule was selected from the specification and accepted HDVN-05 baselines. No neural validation result or 2025 data was inspected.

### HDVN-R01 — Find residual alpha beyond the historical market

**Goal:** Determine whether draft structure predicts points-percentile residuals
that the leakage-safe historical-market baseline does not explain.

**Boundary:**

- This is a new owner-approved research ticket, not a retry or status change for
  rejected HDVN-06.
- Use only the train partition and rolling temporal folds: train 2021 then
  validate 2022; train 2021–2022 then validate 2023.
- Do not open the 2024 validation Parquet file. Prior aggregate HDVN-06 results
  are known, so 2024 is not an untouched validation year for a future model.
- Do not open 2025. The locked-test manifest and Parquet file remain untouched.
- Do not initialize HDVN-07, train an ensemble, change live behavior, or select
  a final production model.

**Frozen methods — before residual fitting:**

1. Fit the accepted historical-market Ridge feature contract inside each
   temporal fold.
2. Generate training residual labels from five-fold league-season-grouped
   out-of-fold market predictions.
3. Fit fixed Ridge corrections for roster-summary, flattened pick-sequence, and
   combined feature groups.
4. Fit one fixed masked sequence residual network with the HDVN-06 encoder,
   optimizer, seed, loss weights, and parameter limit. The points head predicts
   only the correction to the fold market prediction.
5. Compare every correction with its fold-specific market baseline using paired
   league-season clustered intervals. Report scoring-format, team-count,
   draft-slot, market-support, and missing-feature slices.

**Frozen discovery gate — before residual fitting:**

- A correction contains stable candidate alpha only if it lowers
  points-percentile MAE by at least `0.05` in both the 2022 and 2023 folds.
- The pooled estimate of `corrected absolute error - market absolute error`
  must be at most `-0.05`, and its fixed-seed 95% league-season clustered upper
  bound must be below zero.
- The same method and feature order must pass both folds. A post-hoc choice of
  different methods by year does not pass.
- Reproducibility, train-only file access, feature/split hash agreement, and
  fail-closed artifact checks are mandatory.
- Passing identifies a research candidate for a later frozen 2021–2024 fit and
  one-time 2025 review. It does not authorize 2025 access in this ticket.

**Outcome:**

- Mark `Done` if at least one frozen correction passes the discovery gate and
  record the eligible method without fitting it on 2024.
- Mark `Rejected` if no correction passes. Preserve all diagnostics as evidence.

### HDVN-07 — Run the partial-prefix value experiment

**Goal:** Test whether partial draft states have useful conditional outcome signal.

**Work:**

- train with one sampled prefix per team per epoch;
- balance prefix rounds without increasing team-season weight;
- include remaining-board context;
- score observed held-out prefixes and supported candidate substitutions;
- quantify continuation-manager and out-of-distribution risk.

**Acceptance:**

- error is reported by prefix round and remaining picks;
- confidence worsens as historical support falls;
- candidate substitutions outside support are rejected or flagged;
- repeated-prefix labels do not narrow uncertainty as if independent;
- the experiment beats a market-and-current-roster prefix baseline before advancing.

### HDVN-08 — Add ensemble uncertainty and calibration

**Goal:** Make score confidence honest and reproducible.

**Work:**

- train a small seed/bootstrap ensemble;
- cluster bootstrap samples by league-season;
- calibrate playoff and championship outputs on validation only;
- define comparable-state support and out-of-distribution metrics;
- create a versioned artifact manifest.

**Acceptance:**

- ensemble mean, dispersion, support, and model count are exposed;
- low support prevents confident unique ordering;
- calibration improves or remains neutral on validation and is checked once on locked test;
- cached artifact loading reproduces uncached predictions.

### HDVN-09 — Build an offline candidate-scoring experiment

**Goal:** Measure whether historical prefix value helps pick timing without changing live behavior.

**Work:**

- replay saved draft prefixes;
- score legal observed-market candidates with the prefix artifact;
- add empirical next-turn player/tier survival as supporting evidence;
- compare candidate ordering with immediate roster marginal value and terminal rollouts;
- keep historical outcome score and live projected value separately labeled.

**Acceptance:**

- no post-draft label enters the live feature payload;
- candidate output includes support, uncertainty, and artifact versions;
- no candidate is evaluated from one continuation;
- conservative screening retains every terminal finalist in the named replay corpus;
- this ticket exposes no live API or UI behavior.

### HDVN-10 — Run the locked benchmark

**Goal:** Decide whether any historical artifact adds out-of-sample value.

**Comparisons:**

- market ADP;
- best available projection;
- static VORP;
- deterministic projection lookahead;
- current full coupled `ffsim` rollouts;
- simple historical baselines;
- completed and prefix neural models.

**Acceptance:**

- 2025 is read exactly once after model selection is frozen;
- results include uncertainty and context/year slices;
- no claim relies on accuracy alone;
- any proposed advancement names the exact metric and practical improvement;
- failure to beat required baselines marks the relevant artifact `Rejected`.

### HDVN-11 — Add read-only shadow mode

**Goal:** Collect real live-state evidence without affecting recommendations.

**Dependencies:** HDVN-10 passes and a separate implementation approval is recorded.

**Work:**

- load one versioned artifact outside the live scoring path;
- emit shadow predictions and timing evidence to telemetry;
- measure latency, coverage, support, and disagreement with current decisions;
- guarantee shadow failure cannot fail the live monitor.

**Acceptance:**

- shadow output cannot alter ranking, candidate selection, rollouts, or UI recommendation state;
- telemetry records feature, artifact, state, and run identities;
- latency stays within its named budget;
- missing or invalid artifacts disable shadow output explicitly.

### HDVN-12 — Decide integration or rejection

**Goal:** Make a durable decision from shadow evidence.

**Dependencies:** HDVN-11 evidence is complete.

**Possible outcomes:**

- reject HDVN for live use and retain it as research/reporting;
- approve explanation-only use;
- approve conservative screening under a proved finalist-retention gate;
- propose a later residual calibration experiment;
- approve no direct replacement of the terminal completed-roster objective.

**Acceptance:**

- a new ADR names the selected outcome, evidence, artifact version, limits, and rollback behavior;
- no alias, fallback, or silent integration path is introduced;
- any live change receives its own implementation tickets and validation gates.

## Dependency order

```text
HDVN-00
  -> HDVN-01
      -> HDVN-02
          -> HDVN-03
              -> HDVN-04
                  -> HDVN-05
                      -> HDVN-06
                          -> HDVN-07
                              -> HDVN-08
                                  -> HDVN-09
                                      -> HDVN-10
                                          -> HDVN-11
                                              -> HDVN-12
```

Schemas, protocols, disposable native snapshots, and synthetic checks can precede
HDVN-00. Real feature materialization and model fitting cannot skip HDVN-00
through HDVN-05.

## Data gates

| Gate | Requirement | Current effect |
|---|---|---|
| Development | 2,500 ready leagues; 500 per target year | Unlocks HDVN-00–HDVN-05 |
| Neural prototype | 5,000 ready; 500 per year; baselines complete | Unlocks HDVN-06 |
| Serious evaluation | 10,000 ready; per-year floor; locked 2025 | Unlocks HDVN-10 review |
| Live shadow | HDVN-10 passes and approval recorded | Unlocks HDVN-11 |

If the crawler exhausts available candidates before a gate passes, record the exact shortfall. Do not silently lower a gate.

## Deferred integration boundary

All HDVN tickets through HDVN-10 are offline. HDVN has no live route, no live model fallback, no recommendation-mode option, and no effect on candidate ranking.

The existing terminal objective, many-continuation invariant, coupled randomness, projection lookahead, and full simulation remain unchanged. Any future use requires HDVN-11 shadow evidence and HDVN-12’s explicit decision.

## Evidence log

### 2026-08-27 — Safe pre-crawl preparation

- Added immutable SQLite native-backup tooling with deterministic manifests,
  hashes, canonical counts, strict-ready context counts, quality and hydration
  state, raw coverage, and graph provenance.
- Added feature registry `hdvn-features-v1`. The registry classifies labels and
  prohibited inputs as model-ineligible and rejects observations after the
  target draft.
- Accepted collected Sleeper drafts as the rolling population market source for
  local non-commercial research. The audit is
  [`archive/research/hdvn-market-source-audit-2026-08-27.md`](archive/research/hdvn-market-source-audit-2026-08-27.md).
  No authorized point-in-time historical projection source was accepted, so V1
  remains `market_and_construction_only`.
- Added exact-context prior-draft boards, bounded team and prefix generators,
  one-prefix-per-team deterministic sampling, versioned labels, whole-league
  temporal splits, metrics, model protocols, and fail-closed artifact manifests.
- Added a network-free synthetic dry run. It produced 30 team rows, 90 prefix
  rows, 30 sampled prefix rows, and total team weight 30.0. It rejected
  deliberate leakage and validated within-league championship probability sums.
- Synthetic evidence hashes:
  - source snapshot: `dd96cae912f9732ce14ca7fae884171acddf728421c53473e6cb7f946e39a873`;
  - feature manifest: `916c772973c8cb198f6362835e60425026e72be96683cbdbbe5b4c320589d43e`;
  - split manifest: `7d50acd9e945ff487fd6c3ca4c9cb7b1390d01aea7bff328a8e54e8fb56f4bfb`;
  - artifact manifest: `b885acecbd4609c05a70a09edfa41e9604af302d735b046936bac7f25c060c42`.
- Disposable interim snapshot evidence:
  `python3 -m ffsim.historical_sleeper hdvn-snapshot --output
  /tmp/ffsim-hdvn-interim-20260827T195000Z.sqlite3` completed from SQLite
  native backup. The snapshot is 1,581,015,040 bytes, passed integrity and
  foreign-key checks, and has SHA-256
  `db2c76e10c46e2d614b6778cecbfa9ce913969ea09c9991ba883639e7efd97e9`.
  It recorded 4,259 strict-ready league-seasons: 219 in 2021, 562 in 2022,
  857 in 2023, 1,175 in 2024, and 1,446 in 2025.
- Current gate effect: total readiness exceeds the 2,500 development total but
  2021 is 281 leagues below the 500-per-year floor. The snapshot remains
  disposable and does not complete HDVN-00. Neural training remains blocked
  below 5,000 total and before real baselines.
- Focused verification:
  `python3 -W error::ResourceWarning -m unittest
  ffsim.historical_sleeper.test_historical_sleeper
  ffsim.historical_sleeper.test_hdvn` passed 40 tests.
- Live-boundary verification:
  `.venv/bin/python -W error::ResourceWarning -m unittest
  tests.test_decision tests.test_live tests.test_roster_value` passed 47 tests.
  The preparation changes only historical-research and documentation paths;
  existing unrelated live worktree changes remain untouched.
- HDVN-00 through HDVN-12 remain blocked. No real model was trained, tuned,
  selected, approved, benchmarked, shadowed, or integrated.
