# Historical Sleeper data dictionary

The canonical database is `<data-dir>/historical_sleeper.sqlite3`. The default data directory is `~/.cache/ffsim/historical_sleeper`. JSON columns preserve source structures that do not need a separate relational table.

## Raw and operations

### `raw_objects`

One immutable, gzip-compressed source response per SHA-256 content hash.

- `content_hash`: Hash of canonical response JSON.
- `endpoint`: Sleeper endpoint that first returned this object.
- `relative_path`: File path below the data directory.
- `fetched_at`: UTC retrieval time.
- `byte_count`: Uncompressed byte count.
- `http_status`: Source HTTP status.

### `endpoint_cache`

Maps each completed endpoint to its retained raw object. A retry can resume without another request.

### `crawl_queue`

One endpoint-level discovery task.

- `task_type`: `user_leagues`, `league`, `league_rosters`, `league_users`, or `league_drafts`.
- `entity_id`, `season`: Stable task identity.
- `depth`, `seed_user_id`, `mechanism`: Crawl provenance.
- `status`: `pending`, `in_progress`, `done`, or `failed`.
- `attempts`, timestamps, `last_error`: Resume and audit state.

### `hydration_queue`

One expensive hydration task per `(league_id, season)`. It uses the same status and attempt semantics as `crawl_queue`.

### `request_failures`

Append-only request attempt failures. It stores queue identity, endpoint, attempt, HTTP status, error, and UTC time.

## Discovery provenance

### `users`

One Sleeper user ID. Names and avatars can be null because roster responses can identify an owner before a user response is available.

### `seeds`

Explicit graph roots. `source` records how the seed entered the crawl.

### `league_provenance`

Discovery observations for a league-season.

- `seed_user_id`: Root seed.
- `discovery_depth`: User-graph depth.
- `discovering_user_id`: User whose season list returned the league.
- `source_league_id`: Reserved for a direct historical edge source.
- `mechanism`: `seed`, `user_graph`, `roster_owner`, `previous_league`, `hydration`, or `raw_rebuild`.

Discovery counts are provenance. They are not analytical weights.

## Canonical source facts

### `league_seasons`

One row per `(league_id, season)`.

Important fields:

- exact Sleeper IDs and annual `previous_league_id`;
- status, size, season type, and draft ID;
- observed league type, best-ball, keeper, playoff, and scoring fields;
- complete `settings_json`, `scoring_settings_json`, and `roster_positions_json`;
- reversible `scoring_format` summary;
- `is_candidate` and `candidate_reasons_json` for the initial hydration cohort;
- raw hash and first/last observation times.

### `rosters`

One row per `(league_id, season, roster_id)`.

It retains owner, co-owner, player, starter, reserve, and complete roster settings data. Roster settings are the source for Sleeper-reported records and points.

### `drafts`

One row per exact `draft_id`.

It retains league-season context, status, type, team count, rounds, timestamps, scoring type, draft order, slot-to-roster map, settings, metadata, and raw hash.

### `draft_picks`

One row per `(draft_id, pick_no)`.

- `roster_id`: Source roster ID. It can be null.
- `effective_roster_id`: Source roster ID, or the fixed slot-map owner when the source value is absent.
- `ownership_source`: `source_roster_id`, `slot_map`, or `unknown`.
- `picked_by`: Source user actor. It is not used as roster ownership.
- `player_id`: Stable Sleeper player ID.
- `round`, `pick_no`, `draft_slot`, `is_keeper`, `picked_at_ms`: Source draft facts.
- `position`, `nfl_team`, `metadata_json`: Retained pick metadata.

### `traded_draft_picks`

One row per `(draft_id, round, original roster_id)`. It keeps original, previous, and current roster ownership plus the complete source object.

### `players`

One row per Sleeper player ID. The table keeps identity, position, NFL team, status, active state, age-related source fields, complete JSON, and raw hash. It does not use names as keys.

### `weekly_matchups`

One row per `(league_id, season, week, roster_id)`. It keeps matchup ID, source and commissioner-adjusted points, starters, players, and raw hash.

### `playoff_matches`

One row per `(league_id, season, bracket_type, match_id)`.

It keeps bracket round, teams, winner, loser, placement, complete source JSON, and raw hash. `bracket_type` is `winners` or `losers`.

## Canonical outcomes

### `team_seasons`

One row per `(league_id, season, roster_id)`.

- `reported_*`: Sleeper roster settings, including wins, losses, ties, points for, and points against.
- `h2h_*`: Reconstructed head-to-head results from regular-season matchup pairs.
- `matchup_points_for`: Reconstructed regular-season points with commissioner overrides.
- `regular_season_games`: Number of valid reconstructed head-to-head games.
- `made_playoffs`: Roster appears in the winners bracket.
- `champion`, `runner_up`: Result of the bracket match with placement `1`.
- `final_finish`: Winner placement or loser placement plus one when Sleeper supplies a placement match.

Null means the source did not support a safe result. It does not mean false or zero.

## Quality

### `quality_flags`

One active flag per `(scope, entity_key, code)`.

- `scope`: `league_season`, `league_week`, or `draft`.
- `entity_key`: Stable composite source identity.
- `code`: Machine-readable quality condition.
- `severity`: `info` or `error`.
- `details_json`: Counts or source IDs needed to inspect the condition.
- `detected_at`: Last validation time.

Flags do not delete or rewrite source observations.

## Parquet outputs

### `leagues.parquet`

One row per league-season with full configuration JSON and the initial cohort flag.

### `team_seasons.parquet`

One row per fantasy team-season. It joins league context and adds reproducible win percentage and within-league points-for percentile.

### `draft_picks.parquet`

One row per draft selection. It joins draft, player, and league context. It retains source and effective roster ownership separately.
