# Codex Handoff Prompt

Paste the prompt below into a fresh Codex session after checking out `feat/draft-intelligence` locally.

---

Read `/AGENTS.md`, then `docs/draft-intelligence/README.md`, `docs/draft-intelligence/IMPLEMENTATION_LEDGER.md`, and `docs/draft-intelligence/DECISIONS.md` before changing code.

Continue the Draft Intelligence project from the current ledger state.

First, audit the current local repository carefully. Local commits may be newer than the GitHub baseline used when the specification was written, so inspect Git status/history/diffs and reconcile any unpublished or newer local work before applying architectural changes. Treat working code and tests as authoritative evidence; do not blindly rewrite newer code to match an older spec if the underlying requirement is already satisfied.

Run the existing relevant test suite and record any pre-existing failures. Inspect the current simulation architecture and profile enough of the hot path to understand where time is actually spent before doing performance refactors.

Then work through the implementation phases in dependency order, beginning with Phase 0 in `IMPLEMENTATION_LEDGER.md`. Read the relevant specification chapters for each phase before implementing it. Do not attempt to implement the whole project as one giant patch, and do not skip ahead to UI, GPU acceleration, or final optimization before the foundational data/model layers are validated.

Operate autonomously:

- make reasonable implementation decisions from the code, tests, specification, and engineering evidence without asking me for routine confirmation;
- preserve existing `ffsim` correctness and behavior unless an intentional change is explicitly documented;
- add tests for every important new invariant;
- research external APIs/data sources from primary/official sources before encoding assumptions;
- keep `docs/draft-intelligence/IMPLEMENTATION_LEDGER.md` updated after every meaningful milestone with completed work, validation status, blockers, and the exact next step;
- add durable architectural decisions or intentional spec departures to `docs/draft-intelligence/DECISIONS.md`;
- update the specification if implementation discoveries make it materially inaccurate;
- make coherent, reviewable commits as you progress;
- continue from one unblocked task to the next rather than stopping after each commit.

The core product invariants are mandatory:

1. Never evaluate a current-pick candidate from only one sampled rest-of-draft completion. Integrate over many probabilistically generated future draft continuations.
2. Keep draft uncertainty and football-season uncertainty distinct, then integrate both into expected championship equity.
3. Use common/coupled randomness where specified so candidate comparisons are not dominated by Monte Carlo noise.
4. Reuse/refactor the existing `ffsim` engine as the terminal season/championship evaluator rather than replacing it with a toy model.
5. Move toward a reusable, versioned `SeasonWorldBank` so player/week outcome worlds can be shared across hypothetical roster assignments.
6. Deduplicate shared historical drafts and use opportunity-adjusted manager-player signals.
7. Shrink sparse manager-specific evidence toward market/global priors and validate personalization out-of-sample.
8. Keep player-value estimation separate from opponent-choice/availability prediction.
9. Use exact memoization, deterministic state hashing, and transposition reuse with correct invalidation. Cached and uncached results must be equivalent.
10. Treat GPU acceleration as optional and profiling-driven; prioritize architecture, shared worlds, vectorization, caching, and CPU parallelism first.
11. Do not invent API capabilities, historical ADP data, default-board access, or licensing permissions. Record verified sources and limitations.

Only stop and ask me for input if you hit a genuine blocker that cannot safely be resolved from the repository/specification/research, such as credentials or paid API access, a destructive/irreversible choice, a material product decision with no encoded preference, or a correctness tradeoff that would violate a core invariant. Before stopping, update the implementation ledger with the blocker, evidence, options, and your recommended default.

Otherwise, keep working phase by phase until the implementation plan is complete or a genuine blocker is reached. At the end of each substantial work session, leave the repository in a clean, testable state and ensure the ledger tells the next agent exactly where to resume.

---
