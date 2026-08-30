# Multi-state cached decision-impact corpus

Freeze six cached 2026 mock-draft states before multi-state timing and manager-shadow evaluation.

Coverage requirements:

- both configured 10-team and 12-team leagues;
- early, middle, and later draft rounds;
- short, medium, and full-turn pick gaps;
- exact league, draft, roster, and pick identity;
- SHA-256 for config, league cache, draft cache, and original timing report;
- user roster must be on the clock when each state is rebuilt.

The corpus is a regression and decision-impact set. It is not an outcome-labeled backtest.