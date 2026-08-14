# Draft Telemetry Query Guide

Use this runbook to audit live or synthetic draft runs in
`data/cache/draft_intel/telemetry.sqlite3`. Synthetic batches use the same
session and event tables as live drafts.

Open the database read-only:

```bash
sqlite3 -readonly data/cache/draft_intel/telemetry.sqlite3
```

Useful SQLite shell settings:

```sql
.headers on
.mode box
.parameter init
.parameter set @batch 'synthetic-YYYYMMDDTHHMMSS-xxxxxxxx'
```

Replace the example batch ID with the `batch_id` printed by
`python -m ffsim synthetic-drafts --drafts N`.

## Schema and event contract

- `live_draft_sessions` has one row per draft. `config_json` contains the
  synthetic `batch_id`, source, scenario, policy, seed, and model settings.
- `live_draft_events` is the ordered event stream. Join it to sessions by
  `session_id`; `id` is the durable event order.
- Synthetic drafts record `draft_state`, every `pick`, `recommendation` at
  `screen` and `ready`, `synthetic_summary`, and
  `completed_draft_simulation`. Failures record `synthetic_error`.
- Recommendation `payload_json` contains the decision, uncertainty, reason
  codes, versions, and full candidate board. `ready` is authoritative;
  `screen` is retained to diagnose refinement changes.

The HTTP telemetry endpoint is convenient for one draft, but direct read-only
SQLite queries are better for a batch because the endpoint is capped at 5,000
events.

## 1. Find a batch and verify coverage

List synthetic batches:

```sql
SELECT
  json_extract(config_json, '$.batch_id') AS batch_id,
  count(*) AS drafts,
  sum(status = 'completed') AS completed,
  sum(status = 'failed') AS failed,
  min(started_at) AS started_at,
  max(finished_at) AS finished_at
FROM live_draft_sessions
WHERE json_extract(config_json, '$.source') = 'synthetic'
GROUP BY batch_id
ORDER BY started_at DESC;
```

Check the scenario mix. Drafts are intentionally distributed across every
cached supported league format and user slot:

```sql
SELECT
  json_extract(config_json, '$.scenario.template_league_id') AS template,
  json_extract(config_json, '$.scenario.teams') AS teams,
  json_extract(config_json, '$.scenario.rounds') AS rounds,
  json_extract(config_json, '$.scenario.user_slot') AS user_slot,
  count(*) AS drafts
FROM live_draft_sessions
WHERE json_extract(config_json, '$.batch_id') = @batch
GROUP BY template, teams, rounds, user_slot
ORDER BY teams, template, user_slot;
```

Check that each completed draft has the expected forensic event families:

```sql
SELECT
  s.draft_id,
  s.status,
  sum(e.event_type = 'pick') AS picks,
  sum(e.event_type = 'recommendation' AND e.stage = 'screen') AS screens,
  sum(e.event_type = 'recommendation' AND e.stage = 'ready') AS ready,
  sum(e.event_type = 'synthetic_summary') AS summaries,
  sum(e.event_type = 'completed_draft_simulation') AS outcomes
FROM live_draft_sessions AS s
LEFT JOIN live_draft_events AS e USING (session_id)
WHERE json_extract(s.config_json, '$.batch_id') = @batch
GROUP BY s.session_id
ORDER BY s.draft_id;
```

For a completed draft, `picks` should equal `teams * rounds`, `screens` should
equal `ready`, and there should be one summary and one outcome.

## 2. Start with failures and policy violations

Show failed sessions and their captured exception:

```sql
SELECT
  s.draft_id,
  e.pick_no,
  json_extract(e.payload_json, '$.error_type') AS error_type,
  json_extract(e.payload_json, '$.message') AS message
FROM live_draft_sessions AS s
LEFT JOIN live_draft_events AS e
  ON e.session_id = s.session_id AND e.event_type = 'synthetic_error'
WHERE json_extract(s.config_json, '$.batch_id') = @batch
  AND s.status = 'failed'
ORDER BY s.draft_id;
```

Verify that the synthetic user always selected the final recommendation:

```sql
SELECT draft_id, pick_no, payload_json
FROM live_draft_events
WHERE session_id IN (
  SELECT session_id
  FROM live_draft_sessions
  WHERE json_extract(config_json, '$.batch_id') = @batch
)
  AND event_type = 'pick'
  AND stage = 'user'
  AND (
    json_extract(payload_json, '$.followed_recommendation') != 1
    OR json_extract(payload_json, '$.player_id')
       != json_extract(payload_json, '$.recommended_candidate_id')
  );
```

This query should return no rows.

## 3. Inspect recommendations

Review every final decision with its uncertainty and timing:

```sql
SELECT
  e.draft_id,
  e.pick_no,
  json_extract(e.payload_json, '$.recommended_candidate_id') AS player_id,
  json_extract(e.payload_json, '$.decision_status') AS decision_status,
  round(100 * json_extract(e.payload_json, '$.championship_probability'), 2)
    AS title_pct,
  json_extract(e.payload_json, '$.reason_codes') AS reason_codes,
  round(e.duration_seconds, 2) AS seconds
FROM live_draft_events AS e
JOIN live_draft_sessions AS s USING (session_id)
WHERE json_extract(s.config_json, '$.batch_id') = @batch
  AND e.event_type = 'recommendation'
  AND e.stage = 'ready'
ORDER BY e.draft_id, e.pick_no;
```

Find decisions where refinement changed the recommended player:

```sql
WITH screens AS (
  SELECT session_id, pick_no,
         json_extract(payload_json, '$.recommended_candidate_id') AS player_id
  FROM live_draft_events
  WHERE event_type = 'recommendation' AND stage = 'screen'
), ready AS (
  SELECT session_id, draft_id, pick_no,
         json_extract(payload_json, '$.recommended_candidate_id') AS player_id,
         json_extract(payload_json, '$.decision_status') AS decision_status
  FROM live_draft_events
  WHERE event_type = 'recommendation' AND stage = 'ready'
)
SELECT ready.draft_id, ready.pick_no,
       screens.player_id AS screen_player,
       ready.player_id AS final_player,
       ready.decision_status
FROM ready
JOIN screens USING (session_id, pick_no)
JOIN live_draft_sessions AS s USING (session_id)
WHERE json_extract(s.config_json, '$.batch_id') = @batch
  AND screens.player_id != ready.player_id
ORDER BY ready.draft_id, ready.pick_no;
```

Expand the final candidate boards for deeper analysis:

```sql
SELECT
  e.draft_id,
  e.pick_no,
  json_extract(c.value, '$.player_id') AS player_id,
  json_extract(c.value, '$.name') AS name,
  json_extract(c.value, '$.position') AS position,
  json_extract(c.value, '$.adp') AS adp,
  json_extract(c.value, '$.rollout_count') AS rollouts,
  json_extract(c.value, '$.championship_probability') AS title_probability,
  json_extract(c.value, '$.survives_to_next_pick') AS next_pick_survival,
  json_extract(c.value, '$.is_top_tier') AS top_tier
FROM live_draft_events AS e
JOIN live_draft_sessions AS s USING (session_id)
JOIN json_each(e.payload_json, '$.candidates') AS c
WHERE json_extract(s.config_json, '$.batch_id') = @batch
  AND e.event_type = 'recommendation'
  AND e.stage = 'ready'
ORDER BY e.draft_id, e.pick_no, title_probability DESC;
```

The final payload can also contain `screened_candidates`; those are the
unranked watchlist rows that did not receive the final refinement depth.

## 4. Find model and roster anomalies

Lowest-probability opponent choices are useful starting points for implausible
draft behavior:

```sql
SELECT
  e.draft_id,
  e.pick_no,
  json_extract(e.payload_json, '$.name') AS player,
  json_extract(e.payload_json, '$.position') AS position,
  json_extract(e.payload_json, '$.roster_id') AS roster_id,
  json_extract(e.payload_json, '$.selection_probability') AS probability
FROM live_draft_events AS e
JOIN live_draft_sessions AS s USING (session_id)
WHERE json_extract(s.config_json, '$.batch_id') = @batch
  AND e.event_type = 'pick'
  AND e.stage = 'opponent'
ORDER BY probability ASC
LIMIT 100;
```

Summarize final roster construction by position:

```sql
SELECT
  e.draft_id,
  json_extract(p.value, '$.roster_id') AS roster_id,
  json_extract(p.value, '$.position') AS position,
  count(*) AS players
FROM live_draft_events AS e
JOIN live_draft_sessions AS s USING (session_id)
JOIN json_each(e.payload_json, '$.recent_picks') AS p
WHERE json_extract(s.config_json, '$.batch_id') = @batch
  AND e.event_type = 'draft_state'
  AND e.stage = 'complete'
GROUP BY e.draft_id, roster_id, position
ORDER BY e.draft_id, roster_id, position;
```

Compare the final user outcome by scenario:

```sql
SELECT
  json_extract(s.config_json, '$.scenario.teams') AS teams,
  json_extract(s.config_json, '$.scenario.user_slot') AS user_slot,
  count(*) AS drafts,
  round(100 * avg(json_extract(r.value, '$.championship_probability')), 2)
    AS mean_title_pct,
  round(100 * avg(json_extract(r.value, '$.playoff_probability')), 2)
    AS mean_playoff_pct,
  round(avg(json_extract(r.value, '$.expected_wins')), 2) AS mean_wins
FROM live_draft_events AS e
JOIN live_draft_sessions AS s USING (session_id)
JOIN json_each(e.payload_json, '$.rosters') AS r
WHERE json_extract(s.config_json, '$.batch_id') = @batch
  AND e.event_type = 'completed_draft_simulation'
  AND json_extract(r.value, '$.is_user') = 1
GROUP BY teams, user_slot
ORDER BY teams, user_slot;
```

## Agent audit order

1. Confirm batch status, scenario coverage, and event completeness.
2. Inspect failures and verify every user pick followed its `ready` decision.
3. Rank screen-to-ready changes, toss-ups, long durations, and unusually low
   opponent selection probabilities.
4. Expand candidate boards around suspicious picks and compare ADP, title
   equity, next-pick survival, top-tier membership, reason codes, and rollout
   depth.
5. Check final roster position counts and compare outcomes by league size,
   template, and user slot.
6. Reproduce a finding from the recorded pre-pick `draft_state`, seed, model
   versions, state signature, and run signature before changing the simulator.

Synthetic results measure the simulator against its own generated draft
distribution. They are useful for finding internal inconsistencies, policy
pathologies, scenario sensitivity, and regressions; they are not evidence
that the model predicts human drafters accurately.

For an autonomous five-cycle generate, audit, fix, and verify workflow, use
[`SYNTHETIC_AUDIT_LOOP_PROMPT.md`](SYNTHETIC_AUDIT_LOOP_PROMPT.md).
