# Historical Sleeper dataset

This package builds a local historical Sleeper NFL dataset without changing the `ffsim` simulation path. It targets completed seasons from 2021 through 2025.

## Architecture

The collector uses one local data directory:

```text
~/.cache/ffsim/historical_sleeper/
├── historical_sleeper.sqlite3
├── raw/
│   └── <hash-prefix>/<sha256>.json.gz
└── exports/
    ├── leagues.parquet
    ├── team_seasons.parquet
    ├── draft_picks.parquet
    └── manifest.json
```

The architecture has three layers:

1. **Raw:** Content-addressed gzip files contain canonical JSON from each Sleeper response. The database maps each endpoint to its retained response hash. Files are immutable after creation.
2. **Canonical:** SQLite stores users, league-seasons, rosters, drafts, picks, matchups, brackets, outcomes, provenance, queues, failures, and quality flags.
3. **Analysis:** The export command creates Parquet tables. It calculates reversible fields such as points-for percentile in the export query. It does not add draft-strategy labels.

SQLite uses write-ahead logging (WAL), a five-second busy timeout, foreign keys, indexed queues, and short transactions. The crawler does not load the full dataset into memory. Parquet export reads 50,000 rows per batch by default.

## Data flow

### Discovery

The user graph is:

```text
seed user
  -> leagues for each target season
  -> league rosters
  -> roster owners
  -> each owner's leagues for each target season
```

Discovery also follows `previous_league_id`. It fetches league users and the league draft list. It does not fetch picks, brackets, or weekly matchups.

Each endpoint is one resumable queue task. A unique queue key deduplicates repeated discoveries. `league_provenance` records the seed, graph depth, discovering user, mechanism, and time. A league-season remains one canonical observation even if many users discover it.

Set `--max-depth` to control graph expansion. If you increase the depth later, the crawler scans retained roster owners and queues the next level. You do not need to repeat completed API calls.

### Candidate selection

Discovery keeps all league-seasons. It marks a league as an initial hydration candidate only when all these conditions hold:

- season is 2021 through 2025;
- league status is `complete`;
- league size is 10 or 12;
- observed `settings.type` is `0`;
- observed `settings.best_ball` is `0`;
- the roster has one `QB` and no `SUPER_FLEX`, `OP`, or individual defensive player slots;
- reception scoring is standard, half-PPR, or PPR;
- at least one complete snake draft exists;
- no retained pick has keeper evidence.

Sleeper's official API documentation does not define the values of `settings.type` or `settings.best_ball`. The collector preserves the raw values and uses the same conservative interpretation already validated in this repository. It records exclusion reasons in `candidate_reasons_json`. Do not treat this flag as a permanent research definition.

### Hydration

Hydration is a separate league-season queue. For each candidate, it retains and normalizes:

- current league, users, and rosters;
- every league draft, its metadata, picks, and traded picks;
- winners and losers brackets;
- weekly matchup rows through `last_scored_leg`;
- team-season regular-season and playoff outcomes.

A partial hydration can stop safely. Completed endpoint responses remain in the raw cache. The retry resumes from the first missing endpoint.

## Install

The crawler and SQLite store use the Python standard library. Parquet export requires PyArrow. Install it in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r ffsim/historical_sleeper/requirements.txt
```

Use `.venv/bin/python` instead of `python3` for the export command.

## Commands

Run commands from the repository root.

### Collect everything

Use this command for normal operation:

```bash
python3 -m ffsim.historical_sleeper collect
```

`collect` adds the default `mtoppi` seed, discovers leagues in bounded batches,
queues qualifying leagues, and hydrates them in bounded batches. It targets
10,000 training-ready leagues and at least 500 from each requested 2021–2025
season by default. When the unprocessed candidate backlog reaches 500, it
pauses discovery and drains hydration first. Hydration claims older seasons
first and new queue batches prioritize the least-covered target years.

The command still stops if the discovery and hydration queues are exhausted,
even when a configured quota is unreachable.

Owner graph expansion stays in SQLite and enters the queue in bounded batches.
The collector does not load all discovered owners or hydration candidates into
Python memory.

After an interrupted or crashed run, restart with the same command:

```bash
python3 -m ffsim.historical_sleeper collect
```

Override the model target, per-year floor, or backlog control when necessary:

```bash
python3 -m ffsim.historical_sleeper collect \
  --target-training-ready 10000 \
  --min-training-ready-per-year 500 \
  --candidate-buffer 500
```

### Add seeds

The default seed is `mtoppi`:

```bash
python3 -m ffsim.historical_sleeper seed
```

Add independent usernames or user IDs in one call:

```bash
python3 -m ffsim.historical_sleeper seed user_one user_two 123456789
```

Each seed queues 2021, 2022, 2023, 2024, and 2025 independently.

### Start or resume discovery

```bash
python3 -m ffsim.historical_sleeper discover --max-depth 2 --workers 8
```

Use `--limit N` for a bounded run. The global default is 750 requests per minute. Concurrency hides network latency but does not bypass the global limiter.

### Hydrate candidates

Queue up to ten candidates and process them:

```bash
python3 -m ffsim.historical_sleeper hydrate --enqueue 10 --limit 10 --workers 4
```

Resume already queued work without adding candidates:

```bash
python3 -m ffsim.historical_sleeper hydrate --workers 4
```

### Stop and resume

Press Control-C once. The process stops claiming work and lets active requests finish. Completed tasks stay complete. A later command resumes pending work. Claims older than 30 minutes return to the pending state automatically after an unclean process exit.

### Inspect progress

```bash
python3 -m ffsim.historical_sleeper status
```

The default dashboard is model-first and reads SQLite every five seconds. It
shows only:

- training-ready progress and championship events still needed;
- the five year-floor counts;
- current hydration and discovery work;
- crawler memory, total SQLite GB, failure count, and data-flag count.

Press Control-C to close the dashboard without stopping collection.

`complete` means the hydration queue finished. `training-ready` is stricter: the
league must still match the candidate cohort, have the expected roster count, a
complete non-keeper snake draft with every pick, every regular-season matchup
row, one team-season per roster, exactly one champion, and no error quality
flag.

Every training-ready league contributes exactly one validated champion event.
The year-floor row prevents a large recent-season sample from hiding inadequate
2021–2023 coverage.

For the full operational inventory:

```bash
python3 -m ffsim.historical_sleeper status --verbose
```

Verbose mode adds complete/candidate counts, users, league-seasons, drafts,
picks, team-seasons, raw objects, year discovery counts, PIDs, SQLite
main/WAL/shared-memory components, and quality-flag codes.

For scripts or one snapshot:

```bash
python3 -m ffsim.historical_sleeper status --once
```

Use `--interval SECONDS` to change the polling interval. Collection progress
prints after the first task and every 25 tasks. Each line labels cumulative
HTTP calls, interval-based request RPM, and newly discovered league-seasons per
minute separately.

### Retry failed work

```bash
python3 -m ffsim.historical_sleeper retry-failures
```

This command returns failed discovery and hydration tasks to their pending queues. It does not delete failure history.

### Validate

```bash
python3 -m ffsim.historical_sleeper validate
```

Validation runs SQLite integrity and foreign-key checks. It also checks roster counts, draft pick counts, scoring value types, matchup groups, missing games, and bracket roster references. Questionable observations remain stored with quality flags.

### Refresh the player dimension

```bash
python3 -m ffsim.historical_sleeper players
```

This command retains Sleeper's NFL player response and updates the `players` table. Draft-pick metadata also adds player references during hydration.

### Create an interim HDVN snapshot

```bash
python3 -m ffsim.historical_sleeper \
  --data-dir ~/.cache/ffsim/historical_sleeper \
  hdvn-snapshot --output /tmp/hdvn-interim.sqlite3
```

The command uses SQLite native backup. It refuses to overwrite the snapshot or
its deterministic JSON manifest. The manifest records the source path, schema,
snapshot time, bytes, SHA-256 hash, canonical and strict-ready counts, quality
and hydration state, raw coverage, and graph provenance.

An interim snapshot is disposable test input. Do not designate it as the final
HDVN-00 training snapshot before the data gate passes.

### Finalize HDVN data and simple baselines

After collection stops and final validation passes, run each command with the
explicit crawler data directory:

```bash
DATA_DIR=/Users/matt/.cache/ffsim/historical_sleeper
SNAPSHOT="$DATA_DIR/snapshots/hdvn-final-20260828.sqlite3"
HDVN="$DATA_DIR/hdvn"

python3 -m ffsim.historical_sleeper --data-dir "$DATA_DIR" \
  hdvn-accept-snapshot \
  --snapshot "$SNAPSHOT" \
  --output "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json"

python3 -m ffsim.historical_sleeper --data-dir "$DATA_DIR" \
  hdvn-feature-manifest \
  --snapshot-manifest "$SNAPSHOT.manifest.json" \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --output "$HDVN/hdvn-features-v1.json"

python3 -m ffsim.historical_sleeper --data-dir "$DATA_DIR" \
  hdvn-market \
  --snapshot "$SNAPSHOT" \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --output "$HDVN" \
  --min-support-drafts 25
```

Use `.venv/bin/python` for the Parquet and baseline commands:

```bash
.venv/bin/python -m ffsim.historical_sleeper --data-dir "$DATA_DIR" \
  hdvn-tables \
  --snapshot "$SNAPSHOT" \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --market-database "$HDVN/market-v1.sqlite3" \
  --market-manifest "$HDVN/market-v1.manifest.json" \
  --output "$HDVN/tables-final-20260828"

.venv/bin/python -m ffsim.historical_sleeper --data-dir "$DATA_DIR" \
  hdvn-labels-split \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --tables-manifest "$HDVN/tables-final-20260828/tables-v1.manifest.json" \
  --team-table "$HDVN/tables-final-20260828/team-v1.parquet" \
  --prefix-table "$HDVN/tables-final-20260828/prefix-v1.parquet" \
  --output "$HDVN/labels-split-final-20260828"
```

`hdvn-baselines` reads only the train and validation partition files. Ordinary
partition loading rejects the locked 2025 file. Do not run a locked benchmark
during fitting or model selection. See
`docs/draft-intelligence/HDVN_IMPLEMENTATION_LEDGER.md` for the accepted
baseline command, hashes, metrics, and exact artifact paths.

### Fit the completed-draft neural research model

Run the fixed HDVN-06 model only after the baseline gate passes:

```bash
.venv/bin/python -m ffsim.historical_sleeper --data-dir "$DATA_DIR" \
  hdvn-neural \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --tables-manifest "$HDVN/tables-final-20260828/tables-v1.manifest.json" \
  --market-manifest "$HDVN/market-v1.manifest.json" \
  --labels-manifest "$HDVN/labels-split-final-20260828/labels-split-v1.manifest.json" \
  --split-manifest "$HDVN/labels-split-final-20260828/split-v1.json" \
  --baseline-manifest "$HDVN/baselines-final2-20260828/baseline-bundle.manifest.json" \
  --output "$HDVN/neural-final-20260828" \
  --code-revision <git-revision-or-working-tree-identity>
```

The command reads only the 2021–2023 train file and the 2024 validation file.
It rejects 2025 access. It writes an immutable model, 2024 predictions,
validation report, and fail-closed artifact manifest. The model uses NumPy
directly. It does not require a neural framework.

HDVN-06 used one fixed seed and architecture. It did not tune or train an
ensemble. The predeclared points-percentile gate rejected the result. See
`docs/draft-intelligence/HDVN_IMPLEMENTATION_LEDGER.md` for the artifact hashes,
metrics, and limitations. Do not start HDVN-07 from this artifact.

### Audit residual alpha beyond the historical market

`hdvn-residual-alpha` reads only the 2021–2023 train partition. It uses rolling
2022 and 2023 folds, grouped out-of-fold market residuals, fixed feature-group
corrections, and one fixed masked sequence network:

```bash
.venv/bin/python -m ffsim.historical_sleeper --data-dir "$DATA_DIR" \
  hdvn-residual-alpha \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --tables-manifest "$HDVN/tables-final-20260828/tables-v1.manifest.json" \
  --market-manifest "$HDVN/market-v1.manifest.json" \
  --labels-manifest "$HDVN/labels-split-final-20260828/labels-split-v1.manifest.json" \
  --split-manifest "$HDVN/labels-split-final-20260828/split-v1.json" \
  --output "$HDVN/residual-alpha-final-20260828" \
  --code-revision <git-revision-or-working-tree-identity>
```

The command fails closed if a source, feature, table, label, split, status, or
file hash differs. It records that 2024 and 2025 were not loaded. The accepted
HDVN-R01 run found no correction that passed both rolling folds. It is an
offline rejected research artifact, not a live model.

### Fit the offline population opponent model

`opponent-model` validates one fixed inverse-ADP choice setting and learns
exact-player and top-three-tier next-turn survival. It fits on 2021–2023 and
validates on 2024. It does not query 2025 or change the live callback.

```bash
.venv/bin/python -W error -m ffsim.historical_sleeper \
  --data-dir "$DATA_DIR" \
  opponent-model \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --market-database "$HDVN/market-v1.sqlite3" \
  --market-manifest "$HDVN/market-v1.manifest.json" \
  --output "$HDVN/opponent-final6-20260828" \
  --code-revision <git-revision-or-working-tree-identity>
```

The compliant choice setting remains fixed at `temperature=1.0` and
`reach_rate=0.0`. OPP-03 corrected the broad `10+` gap bucket with exact player
rank, gap, round, and position keys. The corrected player component missed its
frozen overall Brier gate, so `opponent-final6-20260828` is rejected.
`opponent-final4-20260828` is superseded because its long-gap probabilities are
miscalibrated. No current survival artifact is decision-eligible.

### Fit the continuous training-year survival experiment

`continuous-survival` aggregates exact survival cells, fits one constrained
logistic model, and evaluates rolling 2022 and 2023 folds without querying 2024
or 2025:

```bash
.venv/bin/python -W error -m ffsim.historical_sleeper \
  --data-dir "$DATA_DIR" \
  continuous-survival \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --market-database "$HDVN/market-v1.sqlite3" \
  --market-manifest "$HDVN/market-v1.manifest.json" \
  --output "$HDVN/continuous-survival-final-20260828" \
  --code-revision <git-revision-or-working-tree-identity>
```

OPP-04 passed aggregate rolling-fold Brier, false-safe, and coverage gates, but
failed the frozen elite-RB long-gap regression. Its additive model predicted
26.63% instead of below 1%. The artifact is rejected and cannot supply TIM-01
or live predictions.

### Build the supported exact empirical lookup

`empirical-survival` materializes exact rank/gap/round/position/scoring/team
cells from 2021–2023. It returns unavailable below 250 observations and never
falls back to another context:

```bash
.venv/bin/python -W error -m ffsim.historical_sleeper \
  --data-dir "$DATA_DIR" \
  empirical-survival \
  --acceptance "$DATA_DIR/snapshots/hdvn-final-20260828.acceptance.json" \
  --features "$HDVN/hdvn-features-v1.json" \
  --market-database "$HDVN/market-v1.sqlite3" \
  --market-manifest "$HDVN/market-v1.manifest.json" \
  --output "$HDVN/empirical-survival-final-20260828" \
  --code-revision <git-revision-or-working-tree-identity>
```

OPP-05 passed both training-year support/calibration folds. Each available
result includes raw successes/count, raw rate, Beta(1,1)-smoothed probability,
and a 95% Wilson interval. The artifact is offline `research`; it did not query
2024 or 2025 and is not connected to TIM-01 or live Draft Intelligence.

### Replay offline wait-versus-reach evidence

`wait-reach-replay` compares market-only, historical-player, and current live
conditional modal-hazard survival across historical next-turn states. It
requires a passed, current-version player-survival artifact.

```bash
.venv/bin/python -W error -m ffsim.historical_sleeper \
  --data-dir "$DATA_DIR" \
  wait-reach-replay \
  --market-database "$HDVN/market-v1.sqlite3" \
  --opponent-manifest "$HDVN/<passed-opponent-artifact>/opponent-model.manifest.json" \
  --output "$HDVN/wait-reach-final-20260828" \
  --code-revision <git-revision-or-working-tree-identity>
```

The command writes row-level Parquet predictions, calibration and decision
metrics, draft-clustered intervals, and a fail-closed manifest. Existing
OPP-02 output used the superseded broad-gap artifact and must not guide a
decision. Do not rerun it until a corrected player-survival artifact passes.

### Build an offline 2026 player timing report

`draft-timing-report` is a main `ffsim` command. It reads explicit local cache
files and combines current cached 2026 projections with the passed OPP-05 exact
empirical survival lookup.

```bash
.venv/bin/python -W error -m ffsim draft-timing-report \
  --config config.json \
  --league-cache data/cache/league_<league_id>.json \
  --draft-cache data/cache/mock_draft_<draft_id>.json \
  --roster-id <roster_id_on_clock> \
  --survival-manifest \
    "$HDVN/empirical-survival-final-20260828/empirical-survival.manifest.json" \
  --world-count 50 \
  --candidate-breadth 20 \
  --output /tmp/draft-timing-report.json
```

The command makes no network request. It requires the requested roster to be
on the clock. It writes immutable, self-hashed JSON with projection value,
market rank, exact successes/count, smoothed return probability, Wilson
interval, support, fallback value, take-now route, alternative route, and wait
delta. Unsupported exact cells remain null and are excluded from route
aggregation. The report labels complete, partial, and unavailable route
support. It emits no decision label and changes no live API, UI, VONA, ranking,
callback, or rollout behavior.

### Run the HDVN contract fixture

```bash
python3 -m ffsim.historical_sleeper \
  hdvn-dry-run --output /tmp/hdvn-contract-dry-run
```

This command creates an isolated synthetic database and makes zero Sleeper
calls. It does not initialize or read the configured crawler data directory.
The run checks temporal leakage, team-weight invariants, split isolation,
championship probability sums, and artifact compatibility.

### Export Parquet

```bash
python3 -m ffsim.historical_sleeper export
```

The command writes `leagues.parquet`, `team_seasons.parquet`, `draft_picks.parquet`, and a manifest. DuckDB, pandas, Polars, and Python model pipelines can read these files.

Example DuckDB query:

```sql
SELECT season, round, position, count(*)
FROM read_parquet('~/.cache/ffsim/historical_sleeper/exports/draft_picks.parquet')
GROUP BY ALL;
```

### Rebuild from raw data

Rebuild canonical tables into a separate directory without Sleeper requests:

```bash
python3 -m ffsim.historical_sleeper rebuild \
  --output /tmp/historical-sleeper-rebuild
```

The rebuild replays retained endpoint responses. It never writes over the source database.

### Use another data directory

Put `--data-dir` before the command:

```bash
python3 -m ffsim.historical_sleeper \
  --data-dir /Volumes/data/sleeper-history \
  discover --max-depth 2
```

Use a large local volume for a production crawl.

## Rate-limit and failure behavior

The client uses these defaults:

- 750 globally spaced requests per minute;
- 30-second request timeout;
- five retries;
- exponential backoff capped at 60 seconds;
- random jitter;
- `Retry-After` support;
- retries for HTTP 429, transient 5xx responses, timeouts, and network errors.

Three HTTP 429 responses in 60 seconds open the circuit breaker. The crawler stops new work and exits with status 2 after active requests finish. This behavior avoids an IP block. The failed task remains visible and can be retried later.

Sleeper documents a general limit below 1,000 calls per minute. The API is public, read-only, tokenless, and limited to non-commercial use unless Sleeper grants a license. Source checked: [official Sleeper API documentation](https://docs.sleeper.com/), 2026-08-27.

## Historical integrity

`season` is part of every league, roster, matchup, outcome, and pick context. Annual league IDs and `previous_league_id` preserve renewal chains without merging annual settings or owners. Drafts use exact `draft_id` values because one league can have multiple drafts.

Draft picks retain source `roster_id`, inferred `effective_roster_id`, ownership source, user actor, player ID, round, pick number, slot, keeper state, timestamps, position, team, and source metadata. Source `roster_id` remains authoritative when present.

## Quality flags

The database does not delete questionable data. `quality_flags` can record:

- roster count mismatch;
- duplicate roster or pick identifiers;
- duplicate player selections;
- incomplete completed drafts;
- keeper picks;
- invalid matchup groups;
- missing regular-season games;
- unknown playoff rosters;
- non-numeric scoring settings.

Use flags and candidate reasons to define each analysis cohort.

## Sampling bias

A user graph is not a uniform sample of Sleeper leagues. Connected and long-tenured users can enter the graph more often. The collector reduces avoidable bias in these ways:

- accept multiple independent seeds;
- record the seed, graph depth, and discovery mechanism;
- query every target season for each user;
- follow annual league links;
- deduplicate each league-season before analysis;
- never use discovery frequency as an analytical weight.

These controls do not create a probability sample. Report seed selection and graph depth with research results. Use seed-balanced or cluster-aware sensitivity checks before causal claims.

## Known limits

- Sleeper does not document every league setting. Raw values remain available when a classification changes.
- The initial cohort flag is conservative and excludes custom formats. The source data does not.
- Reported roster wins can include league-median games. The canonical table stores reported records and separately computed head-to-head records.
- Playoff finish uses bracket placement fields. Missing or incomplete brackets produce null outcomes and quality flags rather than guessed results.
- Graph crawl results depend on seed selection and public data availability.
- SQLite is the single-machine operational store. Move analytical work to Parquet or DuckDB instead of running large model scans through the crawl database.
