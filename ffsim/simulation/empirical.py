"""Normalized joint weekly-vector sampling from active nflverse history."""

from collections import Counter, defaultdict
import math

import numpy as np
import pandas as pd

from ffsim.loaders.pff import canonical_team
from ffsim.models.player import PFF_STAT_FIELDS
from ffsim.paths import DATA_DIR


HISTORICAL_DIR = DATA_DIR / "historical" / "nflverse"
PLAYER_COLUMNS = {
    "completions": "completions",
    "attempts": "attempts",
    "passing_yards": "passing_yards",
    "passing_tds": "passing_tds",
    "passing_interceptions": "passing_interceptions",
    "sacks_suffered": "sacks_suffered",
    "carries": "carries",
    "rushing_yards": "rushing_yards",
    "rushing_tds": "rushing_tds",
    "targets": "targets",
    "receptions": "receptions",
    "receiving_yards": "receiving_yards",
    "receiving_tds": "receiving_tds",
    "fumbles": "fumbles_total",
    "fumbles_lost": "fumbles_lost_total",
    "return_yards": ("punt_return_yards", "kickoff_return_yards"),
    "return_tds": "special_teams_tds",
    "two_point_conversions": (
        "passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions"
    ),
}
PLAYER_EMPIRICAL_STATS = (
    "kick_return_yards",
    "punt_return_yards",
    "fumble_recovery_tds",
    "special_teams_fumbles_forced",
    "special_teams_fumbles_recovered",
)
PLAYER_CONDITIONAL_STATS = (
    "receiving_tds_40_plus",
    "receiving_tds_50_plus",
    "rushing_tds_40_plus",
    "rushing_tds_50_plus",
    "passing_tds_40_plus",
    "passing_tds_50_plus",
    "pick_sixes_thrown",
)
TEAM_EMPIRICAL_STATS = {
    "blocked_kicks",
    "defense_kick_return_yards",
    "defense_punt_return_yards",
    "defense_special_teams_fumbles_forced",
    "defense_special_teams_fumbles_recovered",
}
PBP_PLAYER_STATS = (
    *PLAYER_CONDITIONAL_STATS,
    "fumble_recovery_tds",
    "special_teams_fumbles_forced",
    "special_teams_fumbles_recovered",
)
PBP_TEAM_STATS = (
    "blocked_kicks",
    "defense_special_teams_fumbles_forced",
    "defense_special_teams_fumbles_recovered",
)
COUNT_STATS = {
    stat for stat in PFF_STAT_FIELDS
    if not stat.endswith("yards") and stat not in {"passing_yards", "rushing_yards", "receiving_yards"}
}
DERIVED_KICKING_STATS = {
    "field_goals_made",
    "field_goals_missed",
    "extra_points_missed",
    "field_goals_missed_0_19",
    "field_goals_missed_20_29",
    "field_goals_missed_30_39",
    "field_goals_missed_40_49",
    "field_goals_missed_50_plus",
}
COUNT_STATS.update(DERIVED_KICKING_STATS)
COUNT_STATS.update(PLAYER_CONDITIONAL_STATS)
COUNT_STATS.update(PLAYER_EMPIRICAL_STATS[2:])
COUNT_STATS.update(TEAM_EMPIRICAL_STATS - {"defense_kick_return_yards", "defense_punt_return_yards"})
VOLUME_STATS = ("attempts", "carries", "targets")
PLAYER_SCALED_STATS = (
    "attempts", "completions", "carries", "targets", "receptions",
    "passing_yards", "rushing_yards", "receiving_yards", "return_yards",
    "kick_return_yards", "punt_return_yards",
)
DEFENSE_YARDAGE_STATS = ("defense_return_yards", "defense_kick_return_yards", "defense_punt_return_yards")
DEFENSE_EVENT_STATS = (
    "defense_sacks", "defense_safeties", "defense_interceptions",
    "defense_fumbles_forced", "defense_fumbles_recovered", "defense_tds",
    "defense_return_tds", "blocked_kicks",
    "defense_special_teams_fumbles_forced", "defense_special_teams_fumbles_recovered",
)
POINTS_ALLOWED_BINS = (
    "points_allowed_0", "points_allowed_1_6", "points_allowed_7_13",
    "points_allowed_14_20", "points_allowed_21_27", "points_allowed_28_34",
    "points_allowed_35_plus",
)
# (stat, inclusive lower bound, exclusive upper bound) for opponent net yards.
YARDS_ALLOWED_BINS = (
    ("yards_allowed_0_100", 0, 100),
    ("yards_allowed_100_199", 100, 200),
    ("yards_allowed_200_299", 200, 300),
    ("yards_allowed_300_349", 300, 350),
    ("yards_allowed_350_399", 350, 400),
    ("yards_allowed_400_449", 400, 450),
    ("yards_allowed_450_499", 450, 500),
    ("yards_allowed_500_549", 500, 550),
    ("yards_allowed_550_plus", 550, float("inf")),
)
YARDS_ALLOWED_STATS = tuple(stat for stat, _, _ in YARDS_ALLOWED_BINS)
FIELD_GOAL_SUFFIXES = ("0_19", "20_29", "30_39", "40_49", "50_plus")
KICKER_FACTOR_STATS = tuple(
    f"field_goals_{outcome}_{suffix}"
    for suffix in FIELD_GOAL_SUFFIXES
    for outcome in ("made", "missed")
) + ("extra_points_made", "extra_points_missed")
TEAM_FACTOR_STATS = {"K": KICKER_FACTOR_STATS, "DEF": DEFENSE_YARDAGE_STATS}
OFFENSE_EXCLUDED_STATS = {*PLAYER_CONDITIONAL_STATS, "field_goal_yards_over_30"}
OFFENSE_EVENT_STATS = (
    "passing_tds", "passing_interceptions", "rushing_tds", "receiving_tds",
    "fumbles", "fumbles_lost", "sacks_suffered", "two_point_conversions",
    "return_tds", *PLAYER_EMPIRICAL_STATS[2:],
)


class EmpiricalLibrary:
    # The 2024->2025 ablation rejected finite personal-history shrinkage.
    def __init__(self, seasons=(2024, 2025), shrinkage=float("inf")):
        self.seasons = tuple(seasons)
        self.shrinkage = float(shrinkage)
        self.corrections = Counter()
        self.samples = 0
        self.player_rows = self._load_player_rows()
        self.tier_cutoffs = self._tier_cutoffs(self.player_rows[self.player_rows.season == min(self.seasons)])
        self.player_stats = [*PLAYER_COLUMNS, *PLAYER_EMPIRICAL_STATS]
        self.player_event_rates = self._player_event_rates()
        self.player_vectors = self._normalize(
            self.player_rows,
            ("source_id", "season"),
            self.player_stats,
        )
        self.player_pools = self._build_player_pools()
        self.player_pool_samples = {
            key: self._compile(group, PLAYER_SCALED_STATS) for key, group in self.player_pools.items()
        }
        self.personal_pools = {} if np.isinf(self.shrinkage) else {
            (str(player_id), position): group.reset_index(drop=True)
            for (player_id, position), group in self.player_vectors.groupby(["sleeper_id", "position"])
            if str(player_id) not in {"", "nan", "None"}
        }
        self.personal_samples = {
            key: self._compile(group, PLAYER_SCALED_STATS) for key, group in self.personal_pools.items()
        }
        self.personal_profiles = {
            key: (
                len(group),
                group.loc[group.season == group.season.max(), list(VOLUME_STATS)]
                .mean()
                .sum(),
            )
            for key, group in self.personal_pools.items()
        }
        self.team_rows = self._load_team_rows()
        self.team_event_rates = {
            stat: float(self.team_rows.loc[self.team_rows.position == "DEF", stat].mean())
            for stat in PBP_TEAM_STATS
        }
        defense_rows = self.team_rows[self.team_rows.position == "DEF"]
        kick_returns = defense_rows.defense_kick_return_yards.sum()
        all_returns = kick_returns + defense_rows.defense_punt_return_yards.sum()
        self.defense_kick_return_share = float(kick_returns / all_returns)
        self.field_goal_distances = self._field_goal_distances()
        self.field_goal_extra_means = {
            suffix: float(distances.mean())
            for suffix, distances in self.field_goal_distances.items()
        }
        # Distances are stored minus 30, so a 60+ yard make reads as >= 30.
        self.field_goal_60_plus_share = float(
            (self.field_goal_distances["50_plus"] >= 30).mean()
        )
        # Yards allowed has no PFF projection; model it through the projected
        # points-allowed distribution with the historical joint P(yards | points).
        marginal = defense_rows[list(YARDS_ALLOWED_STATS)].sum().to_numpy(dtype=float)
        self.yards_allowed_by_points = {}
        for points_stat in POINTS_ALLOWED_BINS:
            counts = (
                defense_rows.loc[defense_rows[points_stat] == 1, list(YARDS_ALLOWED_STATS)]
                .sum()
                .to_numpy(dtype=float)
            )
            if counts.sum() == 0:
                counts = marginal
            self.yards_allowed_by_points[points_stat] = counts / counts.sum()
        team_stats = sorted(
            set(self.team_rows.columns)
            & (set(PFF_STAT_FIELDS) | DERIVED_KICKING_STATS | TEAM_EMPIRICAL_STATS)
        )
        self.team_vectors = self._normalize(self.team_rows, ("team", "season"), team_stats)
        self.team_pools = {
            position: self._recenter(group.reset_index(drop=True), team_stats)
            for position, group in self.team_vectors.groupby("position")
        }
        self.personal_team_pools = {} if np.isinf(self.shrinkage) else {
            (team, position): group.reset_index(drop=True)
            for (team, position), group in self.team_vectors.groupby(["team", "position"])
        }
        self.team_pool_samples = {
            key: self._compile(group, TEAM_FACTOR_STATS[key])
            for key, group in self.team_pools.items()
            if key in TEAM_FACTOR_STATS
        }
        self.personal_team_samples = {
            key: self._compile(group, TEAM_FACTOR_STATS[key[1]])
            for key, group in self.personal_team_pools.items()
            if key[1] in TEAM_FACTOR_STATS
        }
        self.stat_ceilings = self._stat_ceilings()
        self.stat_ceilings_by_position = defaultdict(dict)
        for (position, stat), ceiling in self.stat_ceilings.items():
            self.stat_ceilings_by_position[position][stat] = ceiling

    def __getstate__(self):
        state = self.__dict__.copy()
        for name in (
            "player_rows", "player_vectors", "player_pools", "personal_pools",
            "team_rows", "team_vectors", "team_pools",
        ):
            state[name] = None
        return state

    def _stat_ceilings(self):
        # A ratio-transfer sampler can compose a stat line no one has ever
        # produced (10 passing touchdowns; the NFL record is 7). Bound every
        # stat at 1.2x the most extreme game in the library: enough headroom
        # for a new record without turning a 509-yard passing ceiling into
        # 763 yards.
        # ponytail: 1.2x headroom on a two-season window. Widen the seasons
        # before widening the multiplier if the ceilings ever start binding.
        # The nested long-touchdown stats are excluded: they are drawn from
        # the touchdown count that is already capped, and a separate ceiling
        # would break the 50+ <= 40+ <= total nesting.
        ceilings = {}
        for rows in (self.player_rows, self.team_rows):
            numeric = rows.select_dtypes("number").drop(columns=list(PLAYER_CONDITIONAL_STATS), errors="ignore")
            for position, group in numeric.groupby(rows.position):
                for stat, value in group.max().items():
                    if value > 0:
                        ceiling = float(value) * 1.2
                        ceilings[(position, stat)] = math.ceil(ceiling) if stat in COUNT_STATS else ceiling
        return ceilings

    def _apply_ceilings(self, stats, position, fields=None):
        ceilings = self.stat_ceilings_by_position[position]
        for stat in fields or stats:
            value = stats.get(stat, 0.0)
            if value <= 0:
                continue
            ceiling = ceilings.get(stat)
            if ceiling is not None and value > ceiling:
                stats[stat] = int(ceiling) if stat in COUNT_STATS else ceiling
                self.corrections[f"ceiling_{stat}"] += 1

    def sample(self, player, rng):
        factor = player.season_factor * player.week_factor
        means = {
            stat: value * factor
            for stat, value in player.modeled_weekly_raw_stats().items()
        }
        if player.position == "K":
            stats = self._sample_kicker_stats(player, means, rng)
        elif player.position == "DEF":
            stats = self._sample_defense_stats(player, means, rng)
        else:
            stats = self._sample_offense_stats(player, means, rng)
        self._apply_ceilings(
            stats,
            player.position,
            OFFENSE_EVENT_STATS if player.position not in {"K", "DEF"} else None,
        )
        self._reconcile_return_yards(stats, player.position)
        self._add_conditional_stats(stats, means, player.position, rng)
        self.samples += 1
        return stats

    def _sample_offense_stats(self, player, means, rng):
        # Empirical joint factors set volume and yardage; discrete scoring
        # events then ride on the sampled volume at the projected
        # per-opportunity rate. Ratio-to-mean transfer has the wrong tail
        # shape for rare counts — it manufactures 5-interception and
        # 5-touchdown games that have never happened.
        factors = self._sample_player_factors(player, means, rng)
        stats = {stat: 0.0 for stat in means if stat not in OFFENSE_EXCLUDED_STATS}
        for stat in PLAYER_SCALED_STATS:
            if means.get(stat, 0.0) > 0:
                stats[stat] = self._scale(means[stat], factors.get(stat, 1.0), stat, rng)
        self._correct(stats)
        # Cap volume before the scoring events ride on it, so a runaway
        # completion count cannot manufacture touchdowns downstream.
        self._apply_ceilings(stats, player.position, PLAYER_SCALED_STATS)
        if means.get("passing_tds"):
            stats["passing_tds"] = _event_count(
                rng, stats["completions"], means["passing_tds"], means.get("completions", 0.0)
            )
        if means.get("passing_interceptions"):
            stats["passing_interceptions"] = _event_count(
                rng,
                stats["attempts"] - stats["completions"],
                means["passing_interceptions"],
                max(0.0, means.get("attempts", 0.0) - means.get("completions", 0.0)),
            )
        if means.get("rushing_tds"):
            stats["rushing_tds"] = _event_count(
                rng, stats["carries"], means["rushing_tds"], means.get("carries", 0.0)
            )
        if means.get("receiving_tds"):
            stats["receiving_tds"] = _event_count(
                rng, stats["receptions"], means["receiving_tds"], means.get("receptions", 0.0)
            )
        if means.get("fumbles"):
            touches = stats["attempts"] + stats["carries"] + stats["receptions"]
            mean_touches = (
                means.get("attempts", 0.0)
                + means.get("carries", 0.0)
                + means.get("receptions", 0.0)
            )
            stats["fumbles"] = _event_count(rng, touches, means["fumbles"], mean_touches)
        if means.get("fumbles_lost"):
            stats["fumbles_lost"] = _event_count(
                rng, stats["fumbles"], means["fumbles_lost"], means.get("fumbles", 0.0)
            )
        if means.get("sacks_suffered"):
            dropback_ratio = stats["attempts"] / means["attempts"] if means.get("attempts") else 0.0
            stats["sacks_suffered"] = int(rng.poisson(means["sacks_suffered"] * dropback_ratio))
        for stat in ("two_point_conversions", "return_tds", *PLAYER_EMPIRICAL_STATS[2:]):
            if means.get(stat, 0.0) > 0:
                stats[stat] = int(rng.poisson(means[stat]))
        return stats

    def _reconcile_return_yards(self, stats, position):
        prefix = "defense_" if position == "DEF" else ""
        combined = f"{prefix}return_yards"
        kick, punt = f"{prefix}kick_return_yards", f"{prefix}punt_return_yards"
        split_total = stats.get(kick, 0) + stats.get(punt, 0)
        if split_total:
            total = stats.get(combined, 0)
            ceilings = self.stat_ceilings_by_position[position]
            kick_cap = ceilings.get(kick, total)
            punt_cap = ceilings.get(punt, total)
            stats[kick] = min(kick_cap, max(total - punt_cap, total * stats[kick] / split_total))
            stats[punt] = total - stats[kick]

    def _sample_kicker_stats(self, player, means, rng):
        factors = self._sample_team_factors(player, rng)
        stats = {stat: 0.0 for stat in means if stat != "field_goal_yards_over_30"}
        for suffix in FIELD_GOAL_SUFFIXES:
            for outcome in ("made", "missed"):
                stat = f"field_goals_{outcome}_{suffix}"
                stats[stat] = self._scale(
                    means.get(stat, 0.0), factors.get(stat, 1.0), stat, rng
                )
            stats[f"field_goals_attempted_{suffix}"] = (
                stats[f"field_goals_made_{suffix}"] + stats[f"field_goals_missed_{suffix}"]
            )
        for stat in ("extra_points_made", "extra_points_missed"):
            stats[stat] = self._scale(
                means.get(stat, 0.0), factors.get(stat, 1.0), stat, rng
            )
        stats["extra_points_attempted"] = stats["extra_points_made"] + stats["extra_points_missed"]
        self._correct(stats)
        return stats

    def _sample_defense_stats(self, player, means, rng):
        factors = self._sample_team_factors(player, rng)
        stats = {stat: 0.0 for stat in means}
        for stat in DEFENSE_YARDAGE_STATS:
            if stat in means:
                stats[stat] = self._scale(means[stat], factors.get(stat, 1.0), stat, rng)
        for stat in DEFENSE_EVENT_STATS:
            if means.get(stat, 0.0) > 0:
                stats[stat] = int(rng.poisson(means[stat]))
        weights = np.array([max(0.0, means.get(stat, 0.0)) for stat in POINTS_ALLOWED_BINS])
        if weights.sum() > 0:
            chosen = int(rng.choice(len(POINTS_ALLOWED_BINS), p=weights / weights.sum()))
            for index, stat in enumerate(POINTS_ALLOWED_BINS):
                stats[stat] = int(index == chosen)
            # Yards allowed rides the sampled points bucket through the
            # historical joint distribution, preserving their correlation.
            yards_weights = self.yards_allowed_by_points[POINTS_ALLOWED_BINS[chosen]]
            yards_chosen = int(rng.choice(len(YARDS_ALLOWED_STATS), p=yards_weights))
            for index, stat in enumerate(YARDS_ALLOWED_STATS):
                stats[stat] = int(index == yards_chosen)
        return stats

    def projected_stats(self, player, base_stats):
        stats = dict(base_stats)
        if player.position in {"QB", "RB", "WR", "TE"}:
            volume = sum(stats.get(stat, 0) for stat in VOLUME_STATS) / player.projected_games
            rates = self.player_event_rates[(player.position, self._tier(player.position, volume))]
            return_yards = stats.get("return_yards", 0)
            return_share = rates["kick_return_share"]
            if return_yards and return_share is None:
                raise ValueError(f"No historical return split for {player.position}")
            stats["kick_return_yards"] = return_yards * (return_share or 0)
            stats["punt_return_yards"] = stats.get("return_yards", 0) - stats["kick_return_yards"]
            for event, source in (
                ("receiving_tds_40_plus", "receiving_tds"),
                ("receiving_tds_50_plus", "receiving_tds"),
                ("rushing_tds_40_plus", "rushing_tds"),
                ("rushing_tds_50_plus", "rushing_tds"),
                ("passing_tds_40_plus", "passing_tds"),
                ("passing_tds_50_plus", "passing_tds"),
                ("pick_sixes_thrown", "passing_interceptions"),
            ):
                source_total = stats.get(source, 0)
                if source_total and rates[event] is None:
                    raise ValueError(f"No historical {event} rate for {player.position}")
                stats[event] = source_total * (rates[event] or 0)
            for event in PLAYER_EMPIRICAL_STATS[2:]:
                stats[event] = player.projected_games * rates[event]
        elif player.position == "K":
            stats["field_goal_yards_over_30"] = sum(
                stats.get(f"field_goals_made_{suffix}", 0)
                * self.field_goal_extra_means[suffix]
                for suffix in self.field_goal_distances
            )
            stats["field_goals_made_60_plus"] = (
                stats.get("field_goals_made_50_plus", 0) * self.field_goal_60_plus_share
            )
        elif player.position == "DEF":
            total = stats.get("defense_return_yards", 0)
            stats["defense_kick_return_yards"] = total * self.defense_kick_return_share
            stats["defense_punt_return_yards"] = total - stats["defense_kick_return_yards"]
            for event, rate in self.team_event_rates.items():
                stats[event] = player.projected_games * rate
            for index, yards_stat in enumerate(YARDS_ALLOWED_STATS):
                stats[yards_stat] = sum(
                    stats.get(points_stat, 0) * self.yards_allowed_by_points[points_stat][index]
                    for points_stat in POINTS_ALLOWED_BINS
                )
        return stats

    def correction_report(self):
        return {
            "samples": self.samples,
            "corrections": dict(sorted(self.corrections.items())),
            "rates": {
                key: count / self.samples if self.samples else 0.0
                for key, count in sorted(self.corrections.items())
            },
        }

    def _sample_player_factors(self, player, means, rng):
        tier = self._tier(player.position, sum(means.get(stat, 0) for stat in VOLUME_STATS))
        pool_key = (player.position, tier)
        pool_sample = self.player_pool_samples.get(pool_key)
        if pool_sample is None:
            raise ValueError(f"No empirical history pool for {player.position} tier {tier}")
        if not self.personal_samples:
            return self._sample_factors(pool_sample, rng)
        personal_key = (str(player.sleeper_id), player.position)
        use_personal = False
        if personal_key in self.personal_samples:
            effective_n, historical_volume = self.personal_profiles[personal_key]
            if self._tier(player.position, historical_volume) != tier:
                effective_n /= 2
            use_personal = rng.random() < effective_n / (effective_n + self.shrinkage)
        return self._sample_factors(
            self.personal_samples[personal_key] if use_personal else pool_sample, rng
        )

    def _sample_team_factors(self, player, rng):
        pool_sample = self.team_pool_samples[player.position]
        if not self.personal_team_samples:
            return self._sample_factors(pool_sample, rng)
        personal = self.personal_team_pools.get((canonical_team(player.team), player.position))
        use_personal = personal is not None and rng.random() < len(personal) / (len(personal) + self.shrinkage)
        return self._sample_factors(
            self.personal_team_samples[(canonical_team(player.team), player.position)] if use_personal else pool_sample,
            rng,
        )

    @staticmethod
    def _sample_factors(source, rng):
        # A NaN means this donor did not do this thing at a rate worth
        # normalizing. Filling it from an independent draw destroys the joint
        # structure that is the whole point of vector sampling: it pairs a
        # pocket passer's best throwing day with some other player's best
        # rushing day. Fall back to the pool-average multiplier instead -
        # mean-preserving, and it keeps the impossible pairings out.
        stats, matrix = source
        row = matrix[int(rng.integers(len(matrix)))]
        return dict(zip(stats, row))

    @staticmethod
    def _compile(rows, stats):
        matrix = rows[[f"z_{stat}" for stat in stats]].to_numpy(dtype=float, copy=True)
        matrix[np.isnan(matrix)] = 1.0
        return stats, matrix

    @staticmethod
    def _scale(mean, factor, stat, rng):
        value = max(0.0, mean * factor)
        if stat not in COUNT_STATS:
            return value
        integer = int(np.floor(value))
        return integer + int(rng.random() < value - integer)

    def _add_conditional_stats(self, stats, means, position, rng):
        def nested_counts(total, source, long_40, long_50):
            if not total or not means.get(source):
                return 0, 0
            probability_40 = min(1.0, means.get(long_40, 0) / means[source])
            probability_50 = min(probability_40, means.get(long_50, 0) / means[source])
            count_50 = int(rng.binomial(total, probability_50))
            remaining_probability = (
                (probability_40 - probability_50) / (1 - probability_50)
                if probability_50 < 1
                else 0
            )
            count_40 = count_50 + int(
                rng.binomial(total - count_50, remaining_probability)
            )
            return count_40, count_50

        if position in {"QB", "RB", "WR", "TE"}:
            receiving_40, receiving_50 = nested_counts(
                int(stats.get("receiving_tds", 0)),
                "receiving_tds",
                "receiving_tds_40_plus",
                "receiving_tds_50_plus",
            )
            rushing_40, rushing_50 = nested_counts(
                int(stats.get("rushing_tds", 0)),
                "rushing_tds",
                "rushing_tds_40_plus",
                "rushing_tds_50_plus",
            )
            passing_40, passing_50 = nested_counts(
                int(stats.get("passing_tds", 0)),
                "passing_tds",
                "passing_tds_40_plus",
                "passing_tds_50_plus",
            )
            stats.update(
                receiving_tds_40_plus=receiving_40,
                receiving_tds_50_plus=receiving_50,
                rushing_tds_40_plus=rushing_40,
                rushing_tds_50_plus=rushing_50,
                passing_tds_40_plus=passing_40,
                passing_tds_50_plus=passing_50,
            )
            interceptions = int(stats.get("passing_interceptions", 0))
            probability = (
                min(1.0, means.get("pick_sixes_thrown", 0) / means["passing_interceptions"])
                if means.get("passing_interceptions")
                else 0
            )
            stats["pick_sixes_thrown"] = int(rng.binomial(interceptions, probability))
        if position == "K":
            yards_over_30 = 0.0
            sixty_plus = 0
            for suffix in self.field_goal_distances:
                count = int(stats.get(f"field_goals_made_{suffix}", 0))
                if not count:
                    continue
                draws = rng.choice(self.field_goal_distances[suffix], count)
                yards_over_30 += float(draws.sum())
                if suffix == "50_plus":
                    # Stored distances are minus 30, so 60+ yards reads as >= 30.
                    sixty_plus = int((draws >= 30).sum())
            stats["field_goal_yards_over_30"] = yards_over_30
            stats["field_goals_made_60_plus"] = sixty_plus
            self._apply_ceilings(stats, position, ("field_goal_yards_over_30",))

    def _correct(self, stats):
        if "field_goals_made_0_19" in stats:
            stats["field_goals_made"] = sum(
                stats.get(f"field_goals_made_{suffix}", 0) for suffix in FIELD_GOAL_SUFFIXES
            )
            stats["field_goals_missed"] = sum(
                stats.get(f"field_goals_missed_{suffix}", 0) for suffix in FIELD_GOAL_SUFFIXES
            )
        for lower, upper, name in (
            ("receptions", "targets", "receptions_over_targets"),
            ("completions", "attempts", "completions_over_attempts"),
        ):
            if stats.get(lower, 0) > stats.get(upper, 0):
                stats[upper] = stats[lower]
                self.corrections[name] += 1
        if stats.get("receiving_tds", 0) > stats.get("receptions", 0):
            stats["receiving_tds"] = stats["receptions"]
            self.corrections["receiving_tds_over_receptions"] += 1
        if stats.get("receptions", 0) == 0:
            for stat in ("receiving_yards", "receiving_tds"):
                if stats.get(stat, 0) != 0:
                    stats[stat] = 0
                    self.corrections[f"zero_reception_{stat}"] += 1

    def _build_player_pools(self):
        rows = self.player_vectors.copy()
        rows["tier_volume"] = rows.groupby(["source_id", "season"])[list(VOLUME_STATS)].transform("mean").sum(axis=1)
        rows["tier"] = rows.apply(
            lambda row: self._tier(row.position, row.tier_volume), axis=1
        )
        return {
            key: self._recenter(group.reset_index(drop=True), self.player_stats)
            for key, group in rows.groupby(["position", "tier"])
        }

    def _player_event_rates(self):
        rows = self.player_rows.copy()
        rows["tier_volume"] = (
            rows.groupby(["source_id", "season"])[list(VOLUME_STATS)]
            .transform("mean")
            .sum(axis=1)
        )
        rows["tier"] = rows.apply(
            lambda row: self._tier(row.position, row.tier_volume), axis=1
        )

        def rates(group):
            return {
                "receiving_tds_40_plus": _ratio(group.receiving_tds_40_plus.sum(), group.receiving_tds.sum()),
                "receiving_tds_50_plus": _ratio(group.receiving_tds_50_plus.sum(), group.receiving_tds.sum()),
                "rushing_tds_40_plus": _ratio(group.rushing_tds_40_plus.sum(), group.rushing_tds.sum()),
                "rushing_tds_50_plus": _ratio(group.rushing_tds_50_plus.sum(), group.rushing_tds.sum()),
                "passing_tds_40_plus": _ratio(group.passing_tds_40_plus.sum(), group.passing_tds.sum()),
                "passing_tds_50_plus": _ratio(group.passing_tds_50_plus.sum(), group.passing_tds.sum()),
                "pick_sixes_thrown": _ratio(group.pick_sixes_thrown.sum(), group.passing_interceptions.sum()),
                "kick_return_share": _ratio(
                    group.kick_return_yards.sum(),
                    group.kick_return_yards.sum() + group.punt_return_yards.sum(),
                ),
                **{stat: float(group[stat].mean()) for stat in PLAYER_EMPIRICAL_STATS[2:]},
            }

        position_rates = {
            position: rates(group) for position, group in rows.groupby("position")
        }
        result = {}
        for key, group in rows.groupby(["position", "tier"]):
            values = rates(group)
            result[key] = {
                stat: position_rates[key[0]][stat] if value is None else value
                for stat, value in values.items()
            }
        return result

    def _field_goal_distances(self):
        distances = {suffix: [] for suffix in ("0_19", "20_29", "30_39", "40_49", "50_plus")}
        for value in self.team_rows.loc[
            self.team_rows.position == "K", "field_goal_made_list"
        ].dropna():
            for raw_distance in str(value).split(";"):
                distance = int(raw_distance)
                suffix = (
                    "0_19" if distance < 20 else
                    "20_29" if distance < 30 else
                    "30_39" if distance < 40 else
                    "40_49" if distance < 50 else
                    "50_plus"
                )
                distances[suffix].append(max(0, distance - 30))
        for suffix in ("30_39", "40_49", "50_plus"):
            if not distances[suffix]:
                raise ValueError(f"No historical made field-goal distances for {suffix}")
        distances["0_19"] = distances["0_19"] or [0]
        distances["20_29"] = distances["20_29"] or [0]
        return {suffix: np.asarray(values, dtype=float) for suffix, values in distances.items()}

    def _tier_cutoffs(self, rows):
        seasons = rows.groupby(["source_id", "season", "position"])[list(VOLUME_STATS)].mean().reset_index()
        seasons["volume"] = seasons[list(VOLUME_STATS)].sum(axis=1)
        # Octiles, not quartiles: a weekly ratio is only transferable between
        # players at a comparable usage level. The top quartile of TEs spans
        # 1.9 to 7.4 receptions per game, so a legitimate 11-catch game by the
        # low end became a 4.7x factor and a 29-catch game for Trey McBride.
        # Octiles cap that at 2.8x while keeping every pool above 45 rows.
        return {
            position: tuple(group.volume.quantile(np.arange(1, 8) / 8).to_numpy())
            for position, group in seasons.groupby("position")
        }

    def _tier(self, position, volume):
        cutoffs = self.tier_cutoffs[position]
        return sum(volume > cutoff for cutoff in cutoffs)

    @staticmethod
    def _normalize(rows, groups, stats):
        # Ratios to a near-zero personal mean are noise (a 6-yard scramble
        # against a 0.06-yard average is a 100x factor that, applied to a
        # dual-threat QB projection, invents 4,000-yard rushing seasons).
        # Only trust a season's own shape for a stat when it accrues at least
        # half the position-wide rate; below that the z is NaN and sampling
        # falls back to the pool of players who actually do the thing.
        result = rows.copy()
        means = result.groupby(list(groups))[stats].transform("mean")
        floors = result.groupby("position")[stats].transform("mean") / 2
        for stat in stats:
            valid = means[stat].where((means[stat] != 0) & (means[stat] >= floors[stat]), np.nan)
            result[f"z_{stat}"] = result[stat] / valid
        return result

    @staticmethod
    def _recenter(rows, stats):
        rows = rows.copy()
        for stat in stats:
            column = f"z_{stat}"
            mean = rows[column].mean()
            if pd.notna(mean) and mean:
                rows[column] /= mean
        return rows

    def _load_player_rows(self):
        ids = pd.read_csv(HISTORICAL_DIR / "reference" / "db_playerids.csv", low_memory=False)
        ids = (
            ids.dropna(subset=["pfr_id", "gsis_id"])
            .sort_values("db_season")
            .drop_duplicates("pfr_id", keep="last")[["pfr_id", "gsis_id", "sleeper_id"]]
        )
        frames = []
        stat_columns = sorted({column for value in PLAYER_COLUMNS.values() for column in ((value,) if isinstance(value, str) else value)})
        for season in self.seasons:
            snaps = pd.read_csv(HISTORICAL_DIR / "snap_counts" / f"snap_counts_{season}.csv", low_memory=False)
            snaps = snaps[
                (snaps.game_type == "REG")
                & snaps.position.isin(("QB", "RB", "WR", "TE"))
                & (snaps.offense_snaps > 0)
            ][["game_id", "season", "week", "pfr_player_id", "position", "team", "offense_snaps"]]
            snaps = snaps.merge(ids, left_on="pfr_player_id", right_on="pfr_id", how="left", validate="m:1")
            stats = pd.read_csv(
                HISTORICAL_DIR / "weekly_stats" / f"stats_player_week_{season}.csv",
                usecols=["game_id", "player_id", *stat_columns],
                low_memory=False,
            )
            frame = snaps.merge(
                stats,
                left_on=["game_id", "gsis_id"],
                right_on=["game_id", "player_id"],
                how="left",
                validate="m:1",
                indicator="weekly_join",
            )
            frame[stat_columns] = frame[stat_columns].fillna(0)
            events = pd.read_csv(
                HISTORICAL_DIR / "play_by_play" / f"scoring_player_week_{season}.csv"
            ).rename(columns={"player_id": "gsis_id"})
            frame = frame.merge(
                events[["game_id", "gsis_id", *PBP_PLAYER_STATS]],
                on=["game_id", "gsis_id"],
                how="left",
                validate="m:1",
            )
            frame[list(PBP_PLAYER_STATS)] = frame[list(PBP_PLAYER_STATS)].fillna(0)
            for stat, source in PLAYER_COLUMNS.items():
                frame[stat] = frame[list(source)].sum(axis=1) if isinstance(source, tuple) else frame[source]
            frame["kick_return_yards"] = frame.kickoff_return_yards
            frames.append(frame)
        rows = pd.concat(frames, ignore_index=True)
        rows["team"] = rows.team.map(canonical_team)
        rows["sleeper_id"] = rows.sleeper_id.astype("Int64").astype(str).fillna("").replace({"<NA>": "", "nan": ""})
        rows["source_id"] = rows.gsis_id.fillna(rows.pfr_player_id)
        return rows

    def _load_team_rows(self):
        games = pd.read_csv(HISTORICAL_DIR / "reference" / "games.csv", low_memory=False)
        games = games[(games.season.isin(self.seasons)) & (games.game_type == "REG")]
        scores = {}
        for row in games.itertuples():
            scores[(row.game_id, canonical_team(row.home_team))] = row.away_score
            scores[(row.game_id, canonical_team(row.away_team))] = row.home_score
        frames = []
        for season in self.seasons:
            source = pd.read_csv(
                HISTORICAL_DIR / "weekly_team_stats" / f"stats_team_week_{season}.csv",
                low_memory=False,
            )
            source = source[source.season_type == "REG"].copy()
            source["team"] = source.team.map(canonical_team)
            events = pd.read_csv(
                HISTORICAL_DIR / "play_by_play" / f"scoring_team_week_{season}.csv"
            )
            events["team"] = events.team.map(canonical_team)
            source = source.merge(
                events[["game_id", "team", *PBP_TEAM_STATS]],
                on=["game_id", "team"],
                how="left",
                validate="1:1",
            )
            source[list(PBP_TEAM_STATS)] = source[list(PBP_TEAM_STATS)].fillna(0)
            source["points_allowed"] = [scores[(game, team)] for game, team in zip(source.game_id, source.team)]
            # Opponent net yards: official total yards is gross passing minus
            # sack yardage plus rushing.
            source["offense_yards"] = (
                source.passing_yards - source.sack_yards_lost + source.rushing_yards
            )
            source["yards_allowed"] = (
                source.groupby("game_id").offense_yards.transform("sum")
                - source.offense_yards
            )
            for position in ("K", "DEF"):
                frame = source[["season", "week", "game_id", "team"]].copy()
                frame["position"] = position
                if position == "K":
                    _add_kicker_stats(frame, source)
                else:
                    _add_defense_stats(frame, source)
                frames.append(frame)
        return pd.concat(frames, ignore_index=True)


def _add_kicker_stats(frame, source):
    for suffix, made_columns, missed_columns in (
        ("0_19", ("fg_made_0_19",), ("fg_missed_0_19",)),
        ("20_29", ("fg_made_20_29",), ("fg_missed_20_29",)),
        ("30_39", ("fg_made_30_39",), ("fg_missed_30_39",)),
        ("40_49", ("fg_made_40_49",), ("fg_missed_40_49",)),
        ("50_plus", ("fg_made_50_59", "fg_made_60_"), ("fg_missed_50_59", "fg_missed_60_")),
    ):
        frame[f"field_goals_made_{suffix}"] = source[list(made_columns)].sum(axis=1)
        frame[f"field_goals_missed_{suffix}"] = source[list(missed_columns)].sum(axis=1)
    frame["field_goals_made"] = source.fg_made
    frame["field_goals_missed"] = source.fg_missed
    frame["extra_points_made"] = source.pat_made
    frame["extra_points_missed"] = source.pat_missed
    frame["field_goal_made_list"] = source.fg_made_list
    frame["field_goal_yards_over_30"] = source.fg_made_list.map(
        lambda value: sum(
            max(0, int(distance) - 30)
            for distance in str(value).split(";")
            if distance and distance != "nan"
        )
    )


def _add_defense_stats(frame, source):
    mappings = {
        "defense_sacks": "def_sacks",
        "defense_safeties": "def_safeties",
        "defense_interceptions": "def_interceptions",
        "defense_fumbles_forced": "def_fumbles_forced",
        "defense_fumbles_recovered": "def_fumbles",
        "defense_tds": "def_tds",
        "defense_return_tds": "special_teams_tds",
    }
    for stat, column in mappings.items():
        frame[stat] = source[column]
    frame["defense_return_yards"] = source.punt_return_yards + source.kickoff_return_yards
    frame["defense_kick_return_yards"] = source.kickoff_return_yards
    frame["defense_punt_return_yards"] = source.punt_return_yards
    for stat in PBP_TEAM_STATS:
        frame[stat] = source[stat]
    bins = (
        ("points_allowed_0", source.points_allowed == 0),
        ("points_allowed_1_6", source.points_allowed.between(1, 6)),
        ("points_allowed_7_13", source.points_allowed.between(7, 13)),
        ("points_allowed_14_20", source.points_allowed.between(14, 20)),
        ("points_allowed_21_27", source.points_allowed.between(21, 27)),
        ("points_allowed_28_34", source.points_allowed.between(28, 34)),
        ("points_allowed_35_plus", source.points_allowed >= 35),
    )
    for stat, values in bins:
        frame[stat] = values.astype(int)
    for stat, lower, upper in YARDS_ALLOWED_BINS:
        frame[stat] = ((source.yards_allowed >= lower) & (source.yards_allowed < upper)).astype(int)


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator else None


def _event_count(rng, trials, mean_events, mean_trials):
    """Draw a rare scoring event off the volume that was actually sampled.

    Mean-preserving: E[binomial(T, mean_events / mean_trials)] == mean_events
    whenever E[T] == mean_trials.
    """
    if mean_events <= 0:
        return 0
    if mean_trials <= 0:
        return int(rng.poisson(mean_events))
    return int(rng.binomial(max(0, int(trials)), min(1.0, mean_events / mean_trials)))


def validate_2026_schedule():
    games = pd.read_csv(HISTORICAL_DIR / "reference" / "games.csv", low_memory=False)
    games = games[(games.season == 2026) & (games.game_type == "REG")]
    if len(games) != 272:
        raise ValueError(f"Expected 272 2026 regular-season games, found {len(games)}")
    teams = sorted(set(games.home_team.map(canonical_team)) | set(games.away_team.map(canonical_team)))
    failures = []
    byes = {}
    for team in teams:
        weeks = set(games.loc[
            games.home_team.map(canonical_team).eq(team) | games.away_team.map(canonical_team).eq(team),
            "week",
        ])
        byes[team] = (set(range(1, 19)) - weeks).pop() if len(weeks) == 17 else None
        if len(weeks) != 17 or byes[team] is None:
            failures.append(team)
    if len(teams) != 32 or failures:
        raise ValueError(f"Invalid 2026 schedule teams: {', '.join(failures)}")
    return byes
