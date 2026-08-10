"""Normalized joint weekly-vector sampling from active nflverse history."""

from collections import Counter, defaultdict

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
VOLUME_STATS = ("attempts", "carries", "targets")


class EmpiricalLibrary:
    # The 2024->2025 ablation rejected finite personal-history shrinkage.
    def __init__(self, seasons=(2024, 2025), shrinkage=float("inf")):
        self.seasons = tuple(seasons)
        self.shrinkage = float(shrinkage)
        self.corrections = Counter()
        self.samples = 0
        self.player_rows = self._load_player_rows()
        self.tier_cutoffs = self._tier_cutoffs(self.player_rows[self.player_rows.season == min(self.seasons)])
        self.player_vectors = self._normalize(
            self.player_rows,
            ("source_id", "season"),
            list(PLAYER_COLUMNS),
        )
        self.position_pools = {
            position: self._recenter(group.reset_index(drop=True), list(PLAYER_COLUMNS))
            for position, group in self.player_vectors.groupby("position")
        }
        self.player_pools = self._build_player_pools()
        self.player_pool_samples = {
            key: self._compile(group, list(PLAYER_COLUMNS)) for key, group in self.player_pools.items()
        }
        self.position_pool_samples = {
            key: self._compile(group, list(PLAYER_COLUMNS)) for key, group in self.position_pools.items()
        }
        self.personal_pools = {
            (str(player_id), position): group.reset_index(drop=True)
            for (player_id, position), group in self.player_vectors.groupby(["sleeper_id", "position"])
            if str(player_id) not in {"", "nan", "None"}
        }
        self.personal_samples = {
            key: self._compile(group, list(PLAYER_COLUMNS)) for key, group in self.personal_pools.items()
        }
        self.team_rows = self._load_team_rows()
        team_stats = sorted(
            set(self.team_rows.columns)
            & (set(PFF_STAT_FIELDS) | DERIVED_KICKING_STATS)
        )
        self.team_vectors = self._normalize(self.team_rows, ("team", "season"), team_stats)
        self.team_pools = {
            position: self._recenter(group.reset_index(drop=True), team_stats)
            for position, group in self.team_vectors.groupby("position")
        }
        self.personal_team_pools = {
            (team, position): group.reset_index(drop=True)
            for (team, position), group in self.team_vectors.groupby(["team", "position"])
        }
        self.team_pool_samples = {
            key: self._compile(group, team_stats) for key, group in self.team_pools.items()
        }
        self.personal_team_samples = {
            key: self._compile(group, team_stats) for key, group in self.personal_team_pools.items()
        }

    def sample(self, player, rng):
        means = {
            stat: value / player.projected_games
            for stat, value in player.season_raw_stats().items()
        }
        if player.position in {"K", "DEF"}:
            factors = self._sample_team_factors(player, rng)
        else:
            factors = self._sample_player_factors(player, means, rng)
        stats = {
            stat: self._scale(means.get(stat, 0.0), factors.get(stat, 1.0), stat, rng)
            for stat in means
        }
        self.samples += 1
        self._correct(stats)
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
        pool = self.player_pools.get(pool_key)
        if pool is None or pool.empty:
            raise ValueError(f"No empirical history pool for {player.position} tier {tier}")
        personal = self.personal_pools.get((str(player.sleeper_id), player.position))
        use_personal = False
        if personal is not None and not personal.empty:
            effective_n = len(personal)
            latest = personal[personal.season == personal.season.max()]
            historical_volume = latest[list(VOLUME_STATS)].mean().sum()
            if self._tier(player.position, historical_volume) != tier:
                effective_n /= 2
            use_personal = rng.random() < effective_n / (effective_n + self.shrinkage)
        return self._sample_factors(
            self.personal_samples[(str(player.sleeper_id), player.position)] if use_personal else self.player_pool_samples[pool_key],
            self.player_pool_samples[pool_key],
            rng,
            self.position_pool_samples[player.position],
        )

    def _sample_team_factors(self, player, rng):
        pool = self.team_pools[player.position]
        personal = self.personal_team_pools.get((canonical_team(player.team), player.position))
        use_personal = personal is not None and rng.random() < len(personal) / (len(personal) + self.shrinkage)
        pool_sample = self.team_pool_samples[player.position]
        return self._sample_factors(
            self.personal_team_samples[(canonical_team(player.team), player.position)] if use_personal else pool_sample,
            pool_sample,
            rng,
            pool_sample,
        )

    @staticmethod
    def _sample_factors(source, fallback, rng, secondary):
        stats, matrix, _ = source
        row = matrix[int(rng.integers(len(matrix)))].copy()
        for index, value in enumerate(row):
            if np.isnan(value):
                values = fallback[2][index]
                if not len(values):
                    values = secondary[2][index]
                row[index] = values[int(rng.integers(len(values)))] if len(values) else 1.0
        return dict(zip(stats, row))

    @staticmethod
    def _compile(rows, stats):
        matrix = rows[[f"z_{stat}" for stat in stats]].to_numpy(dtype=float)
        return stats, matrix, [matrix[:, index][~np.isnan(matrix[:, index])] for index in range(len(stats))]

    @staticmethod
    def _scale(mean, factor, stat, rng):
        value = max(0.0, mean * factor)
        if stat not in COUNT_STATS:
            return value
        integer = int(np.floor(value))
        return integer + int(rng.random() < value - integer)

    def _correct(self, stats):
        field_goal_suffixes = ("0_19", "20_29", "30_39", "40_49", "50_plus")
        if "field_goals_made_0_19" in stats:
            stats["field_goals_made"] = sum(
                stats.get(f"field_goals_made_{suffix}", 0) for suffix in field_goal_suffixes
            )
            stats["field_goals_missed"] = sum(
                stats.get(f"field_goals_missed_{suffix}", 0) for suffix in field_goal_suffixes
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
        stats = list(PLAYER_COLUMNS)
        return {
            key: self._recenter(group.reset_index(drop=True), stats)
            for key, group in rows.groupby(["position", "tier"])
        }

    def _tier_cutoffs(self, rows):
        seasons = rows.groupby(["source_id", "season", "position"])[list(VOLUME_STATS)].mean().reset_index()
        seasons["volume"] = seasons[list(VOLUME_STATS)].sum(axis=1)
        return {
            position: tuple(group.volume.quantile([0.25, 0.5, 0.75]).to_numpy())
            for position, group in seasons.groupby("position")
        }

    def _tier(self, position, volume):
        cutoffs = self.tier_cutoffs[position]
        return sum(volume > cutoff for cutoff in cutoffs)

    @staticmethod
    def _normalize(rows, groups, stats):
        result = rows.copy()
        means = result.groupby(list(groups))[stats].transform("mean")
        for stat in stats:
            result[f"z_{stat}"] = result[stat] / means[stat].where(means[stat] != 0, np.nan)
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
            for stat, source in PLAYER_COLUMNS.items():
                frame[stat] = frame[list(source)].sum(axis=1) if isinstance(source, tuple) else frame[source]
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
            source["points_allowed"] = [scores[(game, team)] for game, team in zip(source.game_id, source.team)]
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
