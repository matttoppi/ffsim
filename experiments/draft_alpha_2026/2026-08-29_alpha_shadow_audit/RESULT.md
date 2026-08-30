# Alpha shadow audit result

## Initial six-state audit

- ready states: 6;
- failures: 0;
- discarded: 0;
- top-ten capture: 100%;
- manager practical-tier retention: 100%;
- manager exact agreement: 66.7%;
- p95 latency: `13.5098s`;
- development gate: failed on latency only.

## Latency attempt 1

The live manager shadow kept 20 rollouts and the fixed 10% blend, but reduced its candidate set from ten to the five terminal finalists.

- median total latency: `5.1556s`;
- p95 total latency: `6.7061s`;
- maximum total latency: `6.7076s`;
- hierarchical timing p95: `0.0583s`;
- manager shadow p95: `6.6598s`;
- top-ten capture: 100%;
- manager practical-tier retention: 100%;
- failures: 0;
- development gate: passed.

The optimization confirms that sequential manager rollouts, not hierarchical timing, dominate shadow latency.

## Support and disagreement

- terminal candidate return-probability coverage: 46.3%;
- outside-model terminal candidates: 53.7%;
- direct support minimum: 2;
- direct support median: 869;
- median 95% interval width: 4.81 percentage points;
- personalized callback calls: 397,524;
- population fallback calls: 81,236;
- supported opponent rosters: 48/58 across states;
- shadow leader exactly matches terminal leader: 4/6;
- shadow leader remains in terminal practical tier: 6/6.

The coverage gap is structural: the survival model was trained on the relative market top ten, while many terminal candidates rank outside that market window. The next model experiment should test a separately frozen top-20 survival target. Do not extrapolate the current hierarchy beyond rank 10.

## Release status

The six-state development gate passes after the latency change. The live evidence gate remains blocked at 6/30 new states. Cached mocks include model-selection states and have no realized draft outcomes.