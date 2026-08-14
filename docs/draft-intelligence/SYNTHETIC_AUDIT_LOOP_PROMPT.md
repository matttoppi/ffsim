# Synthetic Draft Audit Loop Prompt

This prompt runs 110 synthetic drafts across five investigation-and-fix cycles.
At 22 drafts per cycle, the current 22-scenario grid is covered once each time.
The first complete VONA batch took about one hour; fresh recommendations at
adjacent snake picks add roughly 9% more work. The calibrated planning estimate
is `0.187 GB` of additional SQLite telemetry across all 110 drafts.

```text
Work autonomously in the current ffsim repository until five complete synthetic-draft investigation-and-fix cycles have finished.

Objective:
Run 22 synthetic drafts, deeply audit that batch's telemetry, use subagents to fix evidence-backed problems, verify the fixes, and repeat this entire process five times. Target less than six hours of total wall-clock time without skipping required validation.

Mandatory startup:
1. Inspect the current repository and Git state. Preserve unrelated or pre-existing changes.
2. Read:
   - AGENTS.md
   - docs/draft-intelligence/README.md
   - docs/draft-intelligence/IMPLEMENTATION_LEDGER.md
   - docs/draft-intelligence/DECISIONS.md
   - docs/draft-intelligence/TELEMETRY_QUERY_GUIDE.md
   - Relevant specification chapters for any code you change
3. Run the relevant baseline tests and record pre-existing failures.
4. Treat the correctness invariants in AGENTS.md as non-negotiable.

Investigation standard:
- Think broadly about causes across state construction, draft geometry, market and opponent models, sampling, candidate evaluation, caching, telemetry, and presentation. Generate multiple plausible hypotheses when the evidence permits; do not stop at the first explanation that fits.
- Be rigorous about what happened, where it happened, the mechanism that produced it, and why that mechanism exists. Trace adjacent callers, callees, types, cache keys, versions, and tests until the root cause is demonstrated rather than inferred from one suspicious output.
- Try to disprove the leading hypothesis with another draft, scenario, query, deterministic reproduction, or focused test. Separate confirmed defects, model limitations, expected stochastic variation, and unsupported speculation.
- Think outside the box when forming hypotheses and designing experiments. Implement solutions in the standard correct way: reuse existing code and native facilities, prefer simple well-understood algorithms, preserve architectural boundaries, and avoid clever one-off patches or speculative abstractions.
- Compare credible solutions on correctness, explanatory power, simplicity, maintainability, statistical validity, and measured performance. Choose the smallest solution that fixes the demonstrated root cause without weakening an invariant.

Performance contract:
- Correctness comes first, but every material change must be benchmarked. Never assume a change is cheap because it looks local.
- Before fixes, record recommendation `screen` and `ready` latency by scenario and draft phase, including median, p95, and maximum. Re-run representative deterministic early-, middle-, and late-draft states after each performance-sensitive fix using the same seeds, inputs, rollout counts, world counts, and cache mode.
- Target a final `ready` recommendation within 10 seconds. Slower outliers may be acceptable up to 20 seconds. Any representative suggestion over 20 seconds is a release blocker for the loop and must be profiled and corrected before continuing.
- A small measured regression is acceptable for a necessary correctness fix only when recommendations remain inside the 10–20 second envelope and the tradeoff is documented. Do not accept a large regression, hide it by reducing simulation correctness, or change statistical budgets without the validation required by AGENTS.md.
- Measure cached and uncached behavior where relevant. Attribute regressions with profiling before optimizing, and prefer reuse, batching, vectorization, and exact memoization in the repository's documented order.

Run exactly five completed cycles.

For each cycle:

A. Generate telemetry
- Run this command in the foreground:

  python -m ffsim synthetic-drafts --drafts 22

- Do not return early or leave it running unattended in the background.
- If the command yields a long-running terminal/session ID, use the runtime's
  native wait mechanism with a 15-minute wake interval. At each interval,
  query the latest batch read-only and post one compact report containing the
  cycle, completed/22 drafts, running/failed counts, active pick, elapsed time,
  and estimated remaining time. Report failures and batch completion
  immediately. Do not narrate unchanged polls between these checkpoints.
- If native waiting cannot provide timed wake-ups, spawn one bounded watcher
  subagent to perform the same 15-minute reporting and immediate
  failure/completion notification, then exit. Do not busy-poll or create
  multiple watchers.
- Record the printed batch_id, elapsed time, scenario count, estimate, exit status, and SQLite file size before and after.
- A cycle does not count if the batch fails or is incomplete. Investigate and fix the failure, then rerun that cycle.

B. Audit only the new batch
Use read-only SQLite queries and the workflow in TELEMETRY_QUERY_GUIDE.md.

At minimum, investigate:

1. Batch integrity
   - All 22 sessions exist and completed.
   - Scenario coverage includes the expected league formats and draft slots.
   - Pick, screen, ready, summary, and outcome event counts are complete.
   - Every synthetic user pick matches its final ready recommendation.
   - Inspect every synthetic_error or incomplete session.

2. Recommendation quality
   - Screen-to-ready recommendation changes.
   - Toss-up frequency and co-leader sizes.
   - Suspicious reason codes.
   - Candidate ranking versus ADP, position, next-pick survival, roster need, rollout depth, and title equity.
   - Recommendations that appear to violate roster caps, lineup feasibility, positional value, or wait/reach logic.
   - Large equity changes unsupported by paired uncertainty.
   - Runtime outliers and stages that appear incomplete or stale, including median, p95, and maximum `screen` and `ready` duration by scenario and draft phase.

3. Opponent and draft behavior
   - Lowest-probability opponent selections.
   - Position hoarding, missing required positions, impossible rosters, or unrealistic timing.
   - Behavior differences by league size, template, slot, round, and roster state.
   - Repeated or deterministic-looking paths that should vary.
   - Any mismatch between recorded probabilities and observed sampling.

4. Final outcomes
   - Final roster construction by position.
   - Championship, playoff, and expected-win distributions by scenario and slot.
   - Extreme or structurally implausible outcomes.
   - Whether recommendation improvements are consistent across scenarios rather than concentrated in one template.

5. Reproducibility and telemetry
   - Confirm suspicious findings can be traced through the recorded pre-pick state, seed, state signature, run signature, model versions, and candidate board.
   - Identify any missing telemetry that prevents root-cause analysis.

Compare every cycle with all previous cycles. Track whether earlier findings disappear, regress, or move to another scenario.

Do not treat synthetic drafts as evidence that the model predicts human behavior. They can expose internal inconsistencies, simulator pathologies, scenario sensitivity, and regressions only.

C. Prioritize findings
Produce an evidence-backed list ranked by:

1. Correctness invariant violations
2. Invalid or impossible draft/roster behavior
3. Recommendation logic defects
4. Telemetry or reproducibility gaps
5. Performance regressions
6. Statistical oddities that require more evidence

Every finding must cite its batch_id and representative draft_id, pick number, event type/stage, and relevant observed values.

For every actionable finding, document the symptom, mechanism, demonstrated root cause, alternative hypotheses tested, why existing tests did not catch it, candidate solutions considered, and why the selected solution is best under the correctness and performance contracts.

Do not invent work when the evidence is clean. Do not tune the model merely to make synthetic outputs look nicer.

D. Fix through subagents
After the main agent completes the audit, spawn subagents for the independent actionable findings.

Subagent rules:
- Give each subagent one concrete, bounded finding with telemetry evidence and expected behavior.
- Assign non-overlapping file ownership when running agents concurrently.
- Require each subagent to trace the root cause before editing.
- Require the smallest correct fix, a focused regression test, and a before/after benchmark for performance-sensitive paths.
- Subagents must not weaken simulation correctness, alter unrelated code, or silently add fallback behavior.
- Subagents must report changed files, tests run, and unresolved concerns.
- Do not delegate conflicting changes concurrently.
- If findings depend on each other, fix them sequentially.
- The main agent owns integration, reviews every diff, resolves interactions, and rejects unsupported fixes.

E. Verify before the next cycle
- Run focused tests for every fix.
- Run the complete Python suite with ResourceWarnings treated as errors:

  .venv/bin/python -W error::ResourceWarning -m unittest discover -s tests

- Run frontend tests/build if frontend code changed.
- Run git diff --check.
- Confirm cached and uncached paths remain mathematically equivalent where applicable.
- Compare before/after median, p95, and maximum recommendation latency. Do not continue if representative final suggestions exceed 20 seconds; investigate any meaningful movement away from the 10-second target.
- Update IMPLEMENTATION_LEDGER.md with evidence, validation, remaining issues, and the exact next step.
- Update DECISIONS.md only for durable architectural decisions.
- Only after integration and verification succeeds should the next 22-draft cycle begin.

Persistence:
- Continue until five completed and audited batches have been produced.
- Do not stop merely because a command takes a long time.
- Do not ask for routine implementation decisions that can be resolved from the code, tests, specifications, or telemetry.
- Stop only for a genuine blocker defined by AGENTS.md.
- Do not deploy, push, delete telemetry, or perform unrelated external actions.

Final report:
Provide a compact table with one row per cycle containing:
- cycle number
- batch_id
- completed drafts
- scenario count
- runtime
- SQLite growth
- major findings
- fixes applied
- validation performed

Then summarize:
- Problems eliminated across cycles
- Problems that recurred
- Before/after metrics
- Per-cycle and final median, p95, and maximum `screen` and `ready` latency
- Remaining evidence-backed concerns
- Telemetry limitations
- Exact files changed
- Final test results
- Total drafts generated and total SQLite growth
```
