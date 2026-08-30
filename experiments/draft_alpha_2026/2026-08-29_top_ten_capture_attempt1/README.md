# Top-ten capture attempt 1

Goal: verify that a real cached mock-draft state captures all ten market players for every legal current-pick branch, including players that are not roster-feasible at the next turn.

Inputs:

- draft `1393656492011315200`, pick 73, roster 1;
- immutable hierarchical-survival artifact `0ee13d56a87c5c8206a5c437879b3a8c1419dfd4d4d7c0dc591905d58faf9d91`;
- cached 2026 projections and league scoring.

Gate: every candidate branch has `captured_market_players == 10`, every branch has market ranks 1 through 10, and the report remains `decision_active == false`.