# Live alpha shadow integration contract

## Objective

Make validated draft-timing evidence useful during real drafts without changing the terminal completed-roster recommendation.

## Artifacts

- Hierarchical survival: immutable `research` artifact only.
- Corrected roster-aware manager model: immutable `research` artifact fitted on 2021–2024 without querying 2025.
- Artifact absence or validation failure disables that shadow component explicitly.

## Runtime boundary

1. Publish the final live recommendation first.
2. Start shadow collection on a separate daemon thread.
3. Never pass shadow values into candidate selection, rollouts, practical tiers, recommendation labels, or league equity.
4. Discard a shadow result when the draft-state fingerprint changes.
5. Measure shadow duration and artifact versions.
6. Shadow computation or telemetry failure cannot fail or stop the live monitor.

## Hierarchical timing output

- Capture market ranks 1–10 for every current-pick branch.
- Mark next-turn eligibility separately.
- Report return probability, 95% interval, direct support, pooled support, current marginal value, and route diagnostics.
- Keep one-turn route value diagnostic-only.

## Manager shadow input

- Record the fixed `10%` corrected manager mixture and `90%` live population mixture.
- Record roster-to-manager support without exposing manager IDs to the user interface.
- Record candidate IDs, terminal leader, practical tier, pick geometry, artifact version, and fallback/support counts.
- Persist replay inputs only. Do not run the expensive manager rollout shadow on the recommendation thread.

## Monitor and API state

Expose:

- `alpha_shadow_status`: `disabled`, `pending`, `ready`, `stale`, or `failed`;
- `alpha_shadow_pick_no`;
- `alpha_shadow` compact evidence;
- `alpha_shadow_error`;
- `alpha_shadow_duration_seconds`.

## Product rule

The interface labels the panel `Draft alpha — shadow`. It states that the terminal recommendation remains authoritative. Pending, stale, unavailable, and failed evidence must be visible and must not block the War Room.