# HDVN historical market source audit

**Checked:** 2026-08-27  
**Scope:** Historical point-in-time market and projection inputs for local, non-commercial Historical Draft Value Network (HDVN) research.

## Decision

HDVN V1 uses `market_and_construction_only` inputs.

Use the collected Sleeper draft picks to build a rolling population board. For each target draft, include only exact-context drafts that completed before the target draft started. Do not use an external projection or Average Draft Position (ADP) archive.

This decision accepts real rolling-board construction from a frozen or interim native SQLite snapshot. It does not accept reads from the active crawler database. It does not accept an external data import.

## Source audit

| Source | Authentication and rate limit | Historical timestamp semantics | Format coverage | License and redistribution | Existed before target drafts | Local research decision |
|---|---|---|---|---|---|---|
| Sleeper read-only API and collected draft records | No token. Sleeper states a general limit below 1,000 calls per minute. | Draft and pick records include draft start, completion, and pick times. The local collector preserves these source values. Sleeper does not document an ADP or projection endpoint. | Actual Sleeper league scoring, team count, draft type, and picks. | Free for non-commercial use. Commercial use requires direct licensing. Do not redistribute the raw corpus. | Yes for the recorded 2021–2025 drafts because the records describe actions made on Sleeper at those times. | **Accepted** as the rolling population market source. Exact target and later drafts remain excluded. |
| FantasyPros Public API | `x-api-key`. Premium access is for personal, non-commercial applications. The owner account previously reported a 500-request daily limit and one request per second. | The public endpoints expose season rankings, ADP, and projections. Public documentation does not provide an as-of timestamp query for old draft dates. Historical and bulk access are a Commercial feature. | Current NFL rankings, ADP, and projections across documented scoring parameters. | Personal use is allowed under Premium. Redistribution and historical or bulk access require a Commercial agreement. | The service existed, but a value retrieved now is not evidence that the same snapshot existed before an old draft. | **Rejected for V1 historical features.** A current response cannot prove point-in-time provenance. |
| Fantasy Football Calculator ADP API | No documented authentication. The provider asks clients not to call frequently because data updates once per day. | The API accepts scoring format, team count, year, and position. The official documentation does not expose an as-of cutoff within a season. An archived year response can include drafts after a target draft. | Standard documented endpoint plus scoring, team count, year, and position parameters. | Free for personal and commercial use with requested attribution. | The API predates the target seasons, but the returned aggregate has no documented point-in-time boundary. | **Rejected for V1 historical features.** The year parameter does not prevent target or future draft leakage. |

## Primary evidence

- [Sleeper API introduction](https://docs.sleeper.com/) states that the API is read-only, free for non-commercial use, tokenless, and subject to general guidance below 1,000 calls per minute.
- [FantasyPros Public API](https://www.fantasypros.com/api-data/) documents season rankings, consensus rankings and ADP, and projections. Its pricing terms reserve historical data, bulk access, and redistribution rights for Commercial agreements.
- [Fantasy Football Calculator ADP REST API](https://help.fantasyfootballcalculator.com/article/42-adp-rest-api) documents year, scoring, team-count, and position parameters. It does not document an intra-season as-of timestamp.
- [Sleeper API documentation](https://docs.sleeper.com/) contains no documented ADP, rankings, or projection endpoint as of the check date.

## Accepted provenance contract

A rolling Sleeper board is valid only when all conditions are true:

1. The analytical source is an immutable or disposable native SQLite backup.
2. The source draft differs from the target draft.
3. The source draft completed strictly before the target draft start time.
4. The source and target share season, scoring format, team count, draft type, and draft-range bucket.
5. The output records its target cutoff, latest source completion, support count, context, and source-draft identity hash.
6. Sparse exact contexts return unavailable. They do not use an unrecorded fallback.

## Unresolved prerequisite

Point-in-time historical projections remain unavailable. A later projection-enabled artifact requires an authorized source with exact pre-draft snapshot timestamps and applicable local-use terms. Until then, projection features remain prohibited and the artifact mode remains `market_and_construction_only`.
