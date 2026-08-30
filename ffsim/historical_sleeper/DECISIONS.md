# Historical Sleeper dataset decisions

## Keep the collector isolated from simulation code

**Decision:** Put the collector, tests, fixtures, commands, and documentation in `ffsim/historical_sleeper`. Run it with `python -m ffsim.historical_sleeper`.

**Reason:** Historical collection is an offline operational workload. It must not change simulation behavior, API startup, or live draft latency.

## Use SQLite and content-addressed gzip files

**Decision:** Use SQLite as the canonical operational database. Store raw responses as SHA-256-addressed gzip JSON files and reference them from SQLite.

**Reason:** SQLite supports a reliable single-machine queue and tens of millions of indexed rows without a database service. Files keep large source payloads outside database pages and make duplicate payloads share storage.

**Consequence:** Use Parquet for large analytical scans. Reassess the operational database only if one-machine write throughput or database size becomes a measured limit.

## Separate discovery from hydration

**Decision:** Discovery fetches user league lists, league settings, rosters, users, and draft lists. Hydration fetches picks, traded picks, brackets, and weekly matchups.

**Reason:** Graph expansion is cheap relative to full weekly and draft history. A separate durable queue prevents downloads for formats outside the first research cohort.

## Provide one normal collection command

**Decision:** `collect` targets 10,000 training-ready league-seasons and at
least 500 from each requested target year by default. It pauses discovery when
500 candidates are awaiting or in hydration, drains 50 candidates per cycle,
prioritizes the least-covered years when queueing, and claims older pending
seasons first.

**Reason:** Discovery and hydration must stay separate durable phases, but
unbounded graph expansion is wasteful and a total-only target can produce an
analytically unusable dataset dominated by recent seasons.

**Consequence:** Collection stops only when the total and per-year floors pass,
or when all queues are exhausted. Remaining discovery tasks stay resumable.
Operators can override the total, per-year floor, buffer, and batch sizes.

## Bound graph expansion in SQLite

**Decision:** Existing roster-owner expansion uses one SQL-side, deduplicated
owner batch. New roster payloads enqueue their small owner sets with one batched
transaction. Hydration candidates use `INSERT ... SELECT` without Python
materialization.

**Reason:** Loading every owner/provenance row and multiplying it by five
seasons on each collection cycle caused unbounded process memory growth.

**Consequence:** Owner selection excludes already queued seasons, advances
deterministically across batches, and lowers an existing task depth when a
shorter path appears.

## Poll status from the local database

**Decision:** `status` defaults to a compact, model-first dashboard with target
progress, year floors, current queue work, memory/storage, and aggregate
health. `status --verbose` adds operational inventory and exact flag detail.
`status --once` preserves the full machine-readable JSON fields.

**Reason:** The operator's primary questions are whether collection is healthy,
what it is doing now, and how close the championship dataset is to readiness.
Detailed crawl inventory remains available without crowding the default view.

## Cache completed endpoints for resume

**Decision:** A completed endpoint maps to its retained raw object. Retries and restarts reuse that response unless the operator passes `--refresh`.

**Reason:** Completed historical seasons are stable. Endpoint-level checkpoints prevent a partial league hydration from repeating its earlier requests.

**Consequence:** Use `--refresh` only when source correction is more important than strict first-observation reproducibility. The content-addressed raw object remains immutable, but the endpoint cache can point to the refreshed observation.

## Limit requests to 750 per minute

**Decision:** Space all concurrent requests through one global 750-per-minute limiter. Stop after three HTTP 429 responses in 60 seconds.

**Reason:** Sleeper's official guidance is below 1,000 requests per minute. A 25% operating margin retains headroom while reducing collection time.

## Keep season in every analytical identity

**Decision:** Use `(league_id, season, roster_id)` for team-season facts and retain `previous_league_id` as an edge.

**Reason:** Annual settings, owners, roster IDs, and league sizes can change. A renewal chain is not one permanent league observation.

## Keep source and effective pick ownership separate

**Decision:** Preserve source `roster_id`. Add `effective_roster_id` only when a fixed draft slot map can resolve a missing source value. Record the ownership source.

**Reason:** Source fidelity and usable team joins are both necessary. `picked_by` is an actor and can differ from roster ownership for co-managed teams.

## Treat the initial cohort as reversible

**Decision:** Store all discovered formats. Mark an initial hydration candidate with explicit reason codes instead of deleting excluded leagues.

**Reason:** Sleeper does not document all setting values, and research definitions can change. Raw settings and picks must remain available for a later cohort job.

## Preserve both reported and reconstructed records

**Decision:** Store Sleeper roster records and separately reconstruct head-to-head records from weekly matchups.

**Reason:** Some leagues add median games to reported wins. Replacing the source record with a head-to-head calculation would lose league behavior.

## Export Parquet in bounded batches

**Decision:** Use PyArrow to write leagues, team-seasons, and draft picks in 50,000-row batches.

**Reason:** CSV loses types and is inefficient at the target size. Batching prevents tens of millions of picks from entering memory at once.
