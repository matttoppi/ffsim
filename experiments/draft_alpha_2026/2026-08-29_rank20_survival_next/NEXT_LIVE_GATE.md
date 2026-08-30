# Next live-shadow requirement

The rank-20 model passes offline calibration, six-state coverage, and cached shadow latency. It does not replace the live rank-10 default yet.

Collect at least 30 new ready states from real Sleeper mock or live monitoring sessions that were not used to select either survival model. Use the integrated collector without changing ranking.

Run:

```text
python -m ffsim alpha-shadow-audit
```

Required evidence:

- 30 unique `(session, pick, state signature)` ready states;
- 100% complete selected market-window capture;
- zero shadow calculation failures;
- p95 total shadow duration at most 10 seconds;
- 100% manager practical-tier retention;
- both personalization and population fallback use;
- every event `decision_active: false`;
- rank-20 terminal-candidate return coverage at least 70%;
- recommendation hash unchanged before and after shadow collection.

Route ranking remains prohibited even if the live evidence gate passes. A later ADR can switch the shadow display default from rank 10 to rank 20; it cannot change the terminal pick objective.