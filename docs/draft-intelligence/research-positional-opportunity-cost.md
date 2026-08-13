# Research note — positional opportunity cost (the "Josh Allen bias")

**Date:** 2026-08-13
**Status:** Resolved — Option A landed as ADR-016 (`vor2`); Option C landed
as the cost-of-waiting panel. Validation results at the bottom.

## Symptom

Live recommendations over-favor elite QBs (Josh Allen) even when comparable
QB production is available many rounds later, i.e. the engine underprices
"what can I still get at this position at my next picks."

## Root cause

Opportunity cost is *supposed* to emerge from the rollout machinery: every
candidate branch completes the whole draft and simulates full seasons, so
"skip Allen, take an RB, draft a QB later" should be priced automatically.
It is not, because of how the user's own future picks are played inside
continuations (`rollout.py::_complete_draft`, `market_model.py::sleeper_adp_choice`):

1. **Need-blind.** `sleeper_adp_choice` explicitly discards
   `roster_id, pick_no, rosters`. Your future self never looks at its roster.
2. **Deterministic ADP argmax.** User picks in continuations take the top
   remaining ADP player, always (opponents sample at T=0.11; the user does not
   even sample).

So the counterfactual branch is played by a drafter who only takes a QB when
a QB happens to top the remaining ADP board at your slot, may double up on
positions already filled, and never *deliberately* waits on QB to harvest
late-round value. The strategy the recommendation is supposed to weigh —
"get ~80% of Allen's production 8–9 rounds later and spend this pick on a
scarcer position" — is literally unreachable in every continuation, for every
candidate. With both branches played equally badly, the paired delta
degenerates toward "the root pick's standalone season points on a generic
roster," which is BPA-by-projection — and elite QBs are the highest-point,
lowest-variance players in the pool.

This is the same failure family as ADR-015's temperature fix: there the
*opponents* were too soft, making scarcity free; here the *user continuation*
is too dumb, making patience worthless.

## Mechanism options

### A. Need-aware user continuation policy (recommended first step)

Replace the user branch of the continuation policy with a roster-aware
utility. Cheapest credible version: keep the ADP board as the candidate
ordering, but score each available player by **marginal expected starter
points** — projected points × probability the player actually starts given
the roster already drafted in this continuation (filled QB slot ⇒ a second
QB's marginal utility collapses to bench/bye value). Pick argmax of that.

- Fixes the root cause inside the existing machinery; no VORP/VONA constant
  tables, no new data sources, no change to opponents or to the evaluator.
- Rollouts then *realize* late QB value: the skip-Allen branch actually
  drafts a starting QB at the value point, and Allen's paired delta shrinks
  to its true marginal equity.
- Cost: user picks are ~1/12 of continuation picks; marginal-starter scoring
  over the small ADP board is cheap.
- Risk: the user policy becomes a model choice that belongs in
  `draft_model_version` (same treatment as temperature in ADR-015).

### B. Nested Monte Carlo user policy (doc 04)

Future user picks chosen by shallow rollout optimization instead of a static
policy. Strictly more principled, orders of magnitude more compute; already
sketched in `04-nested-monte-carlo.md`. Only pursue if A measurably
under-corrects.

### C. VONA surfacing (display layer, complements A)

The survival machinery (`SurvivalReport.survives_to_next_pick`) already
estimates who is gone by your next pick. Surface, per position:
best-available-now vs expected-best-available-at-next-pick point delta
("waiting on QB costs ~9 pts; waiting on RB costs ~31 pts"). This explains
recommendations to the human but does not change them; it is not a substitute
for A.

## Validation

- A/B the same frozen draft states with old vs new user policy: Allen's
  paired delta vs the best RB/WR should shrink; K/DEF should not re-enter
  early windows (regression guard from ADR-015).
- Backtest hook already exists (`backtest_sleeper_adp`); the user-policy
  change does not affect opponent NLL, so temperature fit is untouched.
- Sanity: in continuations under A, count rosters with 0 or 2+ starting QBs
  drafted before the last three rounds — should drop to ~0.

## Resolution — 2026-08-13 (ADR-016)

Option A was implemented as `_projection_user_policy`: the user's future
picks maximize projection value over positional replacement with open-slot
awareness (replacement derived from a deterministic league-wide starter fill
including flex seats — no constant tables, no new data sources). Opponents
and the temperature fit are untouched; the policy is tagged `vor2` in
`draft_model_version` per the risk item above.

Validation on the frozen mock states:

- Allen A/B (pick 1): Allen grades last of the top-four BPA plus himself —
  15.3% vs Chase 25.3%, Gibbs 22.0%, Robinson 20.7%, Nacua 16.7%. The
  skip-Allen branches now draft a starting QB at the value point.
- Nabers (pick 24): the ADP-argmax double-charge disappeared, 11.3% → 18.0%.
- QB sanity: 18/20 continuations draft exactly one starting QB before the
  last three rounds (2/20 outliers, versus ~0 target — monitor).
- K/DEF guard: early windows stay skill-only under the pure-BPA pool.

The `vor2` refinement keeps the QB/RB/WR/TE/flex need-aware gate but lets
bench depth compete directly with K/DEF once that core lineup is complete;
it also excludes duplicate K/DEF. On the frozen current-mock pick-24 Nabers
branch, pick 96 became skill-position depth in all 50 continuations, while
K/DEF usually moved to picks 120–144.

Option B remains unpursued (A did not measurably under-correct).

Option C landed first as a one-pick display, then was superseded after the
live snake turn exposed a bad horizon: at pick 24, the owner also held pick
25, so every position appeared approximately free. The current display
groups adjacent selections into one turn and shows QB/TE value across the
next three real turns. For each turn it selects the highest-projected player
whose Sleeper ADP is at or after that pick, then recommends taking now or
targeting the pick immediately before the largest incremental projection
drop. This is intentionally an ADP/projection timing curve with no forced-wait
rollouts; the coupled championship board remains the cross-position decision.
Each board row also shows Sleeper ADP and the player's modeled next-pick return
chance from that player's best alternative root branch. This reuses the same
coupled completions that determine title equity; it does not apply a separate
ADP penalty or report the mechanically zero survival from taking the player now.
