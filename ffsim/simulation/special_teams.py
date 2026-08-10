"""Mean-preserving parametric fallback for kicker and team-defense vectors."""

import math


FIELD_GOAL_BUCKETS = ("0_19", "20_29", "30_39", "40_49", "50_plus")
POINTS_ALLOWED = (
    "points_allowed_0", "points_allowed_1_6", "points_allowed_7_13",
    "points_allowed_14_20", "points_allowed_21_27", "points_allowed_28_34",
    "points_allowed_35_plus",
)


def sample_special_team_stats(means, position, rng):
    stats = {stat: 0.0 for stat in means}
    if position == "K":
        for suffix in FIELD_GOAL_BUCKETS:
            made = int(rng.poisson(max(0.0, means[f"field_goals_made_{suffix}"])))
            missed = int(rng.poisson(max(0.0, means[f"field_goals_missed_{suffix}"])))
            stats[f"field_goals_made_{suffix}"] = made
            stats[f"field_goals_missed_{suffix}"] = missed
        stats["field_goals_made"] = sum(stats[f"field_goals_made_{suffix}"] for suffix in FIELD_GOAL_BUCKETS)
        stats["field_goals_missed"] = sum(stats[f"field_goals_missed_{suffix}"] for suffix in FIELD_GOAL_BUCKETS)
        stats["extra_points_made"] = int(rng.poisson(max(0.0, means["extra_points_made"])))
        stats["extra_points_missed"] = int(rng.poisson(max(0.0, means["extra_points_missed"])))
        return stats

    for stat in (
        "defense_sacks", "defense_safeties", "defense_interceptions",
        "defense_fumbles_forced", "defense_fumbles_recovered", "defense_tds",
        "defense_return_tds",
    ):
        stats[stat] = int(rng.poisson(max(0.0, means[stat])))
    mean = means["defense_return_yards"]
    if mean > 0:
        sigma = math.sqrt(math.log(1 + 0.50**2))
        stats["defense_return_yards"] = float(rng.lognormal(math.log(mean) - 0.5 * sigma**2, sigma))
    probabilities = [max(0.0, means[stat]) for stat in POINTS_ALLOWED]
    total = sum(probabilities)
    if total:
        stats[POINTS_ALLOWED[int(rng.choice(len(POINTS_ALLOWED), p=[value / total for value in probabilities]))]] = 1
    return stats
