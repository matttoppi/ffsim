# Manager rollout-impact attempt 3

Attempt 2 applied the full roster-aware manager correction and moved the recommendation outside the baseline practical tier. This final attempt uses a fixed conservative mixture:

```text
90% live population choice probability
10% roster-aware manager probability
```

Gate: the shadow leader must remain a baseline practical co-leader, supported manager adjustments and population fallbacks must both execute, and the live callback remains unchanged.