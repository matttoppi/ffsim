# Multi-state decision-impact attempt 1

## Inputs

- Frozen six-state corpus `alpha-multi-state-v1`.
- Hierarchical survival artifact `0ee13d56a87c5c8206a5c437879b3a8c1419dfd4d4d7c0dc591905d58faf9d91`.
- Corrected position-count manager model fitted on 2021–2024 without querying 2025.
- Current live population callback as comparator.
- 100 coupled draft continuations per candidate for this preliminary multi-state gate.

## Terminal-first timing gate

- Every timing branch captures ranks 1–10.
- Every timing report remains `decision_active: false`.
- The recommendation always comes from completed-roster terminal evaluation.
- One-turn route ranking is diagnostic only. Report, but do not rescue, every route leader outside the terminal practical tier.

## Fixed manager mixture gate

Use the predeclared mixture:

```text
90% live population choice probability
10% corrected roster-aware manager probability
```

For each state, evaluate the baseline terminal top ten under the shadow callback. Every shadow leader must remain a practical co-leader under the baseline paired 0.1-point gate. The corpus must exercise both supported-manager personalization and explicit population fallback.

A failure is a completed policy attempt. Command or serialization errors are not model attempts.