# VONA decision-impact attempt 3

Attempt 2 proved that one-turn route value is unsafe as a ranking objective: it selected a defense ranked 23rd by completed-roster value with a 12.49-point paired regret.

This attempt tests the safe architecture. The 300-rollout terminal leader remains the recommendation. Hierarchical survival is attached only to supported top-ten next-turn alternatives. It must not infer a probability for an outside-top-ten candidate or change the recommendation.