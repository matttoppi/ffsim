# Alpha shadow telemetry audit contract

## Purpose

Turn shadow events from real and mock draft monitoring into repeatable evidence. The audit never changes recommendations.

## State identity

Deduplicate by `(session_id, pick_no, state_signature)`. Keep the latest ready event for that identity. Count discarded and failed events separately.

## Metrics

- sessions, draft states, ready, failed, discarded, and stale events;
- calculation duration median, p95, and maximum;
- complete branch top-ten capture rate;
- terminal recommendation and manager-shadow leader agreement;
- manager-shadow leader retention inside the terminal practical tier;
- personalized and population-fallback callback calls;
- supported, fallback, and total opponent rosters;
- candidate return-probability coverage;
- outside-model candidate rate;
- direct-support median and minimum;
- return-interval median width;
- manager artifact, survival artifact, and blend versions;
- pick rounds and opponent-gap coverage.

## Development gate

The six-state cached monitor corpus passes only if:

- six unique ready states exist;
- ready top-ten capture is 100%;
- shadow calculation failure is 0%;
- manager practical-tier retention is 100%;
- p95 shadow duration is at most 10 seconds;
- both personalization and population fallback execute;
- every event is `decision_active: false`.

## Live evidence gate

Live opponent-distribution integration remains blocked until at least 30 new ready states not used for model selection pass the same gates at the full offline replay budget. Cached mocks and low-cost 20-rollout shadow results are telemetry, not release evidence.

## Output

Emit one immutable JSON report with source telemetry hash, filters, state identities, metrics, gates, artifact versions, and limitations. Expose the latest aggregate through a read-only API and War Room summary.