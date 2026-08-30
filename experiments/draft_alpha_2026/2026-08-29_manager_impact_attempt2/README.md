# Manager rollout-impact attempt 2

Attempt 1 showed that position-count personalization worsens the marginal-hazard survival approximation. This attempt tests the manager model where it belongs: the sequential opponent-choice distribution inside full draft rollouts.

Map the cached template league's real managers to synthetic roster slots. Compare 100 coupled-rollout candidate evaluations under the live population callback and a shadow position-count callback fitted on 2021–2024.

Gate: the shadow leader must remain a practical co-leader under the baseline evaluation, all unsupported managers must use an explicit population distribution, and at least one supported manager distribution must be applied. No live callback changes.