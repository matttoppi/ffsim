import math

import numpy as np

from ffsim.scoring import score_raw_stats
from ffsim.simulation.special_teams import sample_special_team_stats


PFF_STAT_FIELDS = {
    "completions": "passComp",
    "attempts": "passAtt",
    "passing_yards": "passYds",
    "passing_tds": "passTd",
    "passing_interceptions": "passInt",
    "sacks_suffered": "passSacked",
    "carries": "rushAtt",
    "rushing_yards": "rushYds",
    "rushing_tds": "rushTd",
    "targets": "recvTargets",
    "receptions": "recvReceptions",
    "receiving_yards": "recvYds",
    "receiving_tds": "recvTd",
    "fumbles": "fumbles",
    "fumbles_lost": "fumblesLost",
    "two_point_conversions": "twoPt",
    "return_yards": "returnYds",
    "return_tds": "returnTd",
    "field_goals_made_0_19": "fgMade019",
    "field_goals_attempted_0_19": "fgAtt019",
    "field_goals_made_20_29": "fgMade2029",
    "field_goals_attempted_20_29": "fgAtt2029",
    "field_goals_made_30_39": "fgMade3039",
    "field_goals_attempted_30_39": "fgAtt3039",
    "field_goals_made_40_49": "fgMade4049",
    "field_goals_attempted_40_49": "fgAtt4049",
    "field_goals_made_50_plus": "fgMade50plus",
    "field_goals_attempted_50_plus": "fgAtt50plus",
    "extra_points_made": "patMade",
    "extra_points_attempted": "patAtt",
    "defense_sacks": "dstSacks",
    "defense_safeties": "dstSafeties",
    "defense_interceptions": "dstInt",
    "defense_fumbles_forced": "dstFumblesForced",
    "defense_fumbles_recovered": "dstFumblesRecovered",
    "defense_tds": "dstTd",
    "defense_return_yards": "dstReturnYds",
    "defense_return_tds": "dstReturnTd",
    "points_allowed_0": "dstPts0",
    "points_allowed_1_6": "dstPts16",
    "points_allowed_7_13": "dstPts713",
    "points_allowed_14_20": "dstPts1420",
    "points_allowed_21_27": "dstPts2127",
    "points_allowed_28_34": "dstPts2834",
    "points_allowed_35_plus": "dstPts35plus",
}


class Player:
    def __init__(self, initial_data):
        self.sleeper_id = initial_data.get("player_id") or initial_data.get("sleeper_id")
        self.first_name = initial_data.get("first_name", "")
        self.last_name = initial_data.get("last_name", "")
        self.full_name = initial_data.get("full_name", "")
        self.name = self.full_name or f"{self.first_name} {self.last_name}".strip()
        self.position = str(initial_data.get("position") or "UNKNOWN").upper().replace("DST", "DEF")
        self.team = initial_data.get("canonical_team") or initial_data.get("team")
        pff_data = initial_data.get("pff_projections")
        self.pff_projections = PFFProjections(pff_data) if pff_data else None
        self.projection_match_status = initial_data.get("projection_match_status", "unmatched")
        self.value_1qb = _number(initial_data.get("value_1qb"))
        self.redraft_value = _number(initial_data.get("redraft_value"))
        self.missed_weeks = set()
        self.total_games_missed_this_season = 0
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        self.empirical_sampler = None

    def to_dict(self):
        return {attribute: value for attribute, value in self.__dict__.items() if attribute != "empirical_sampler"}

    def initialize_empirical_sampler(self, sampler):
        self.empirical_sampler = sampler

    def prepare_availability(self, weeks, rng):
        eligible = [week for week in weeks if week != self.bye_week]
        expected = min(17.0, self.projected_games) * len(eligible) / 17.0
        played = math.floor(expected) + int(rng.random() < expected % 1)
        played = min(played, len(eligible))
        self.missed_weeks = set(eligible) - set(rng.choice(eligible, played, replace=False).tolist()) if played else set(eligible)
        self.total_games_missed_this_season = len(self.missed_weeks)

    @property
    def bye_week(self):
        return int(_number(self.pff_projections.get("byeWeek"))) if self.pff_projections else 0

    @property
    def projected_games(self):
        games = _number(self.pff_projections.get("games")) if self.pff_projections else 0.0
        if not 0 <= games <= 17:
            raise ValueError(f"Projected games must be between 0 and 17 for {self.name}: {games}")
        return games

    def is_available(self, week):
        return bool(self.pff_projections) and week != self.bye_week and week not in self.missed_weeks

    def is_injured(self, week):
        return week in self.missed_weeks

    def is_partially_injured(self, week):
        return False

    def update_injury_status(self, week):
        del week

    def calculate_score(self, scoring_settings, week, rng=None):
        if not self.is_available(week):
            return 0.0
        rng = rng or np.random.default_rng()
        stats = (
            self.empirical_sampler.sample(self, rng)
            if self.empirical_sampler
            else self.sample_parametric_stats(rng)
        )
        score = score_raw_stats(stats, self.position, scoring_settings)
        self.record_weekly_score(score)
        return score

    def calculate_special_team_score(self, scoring_settings, week, rng=None):
        return self.calculate_score(scoring_settings, week, rng)

    def season_raw_stats(self):
        if not self.pff_projections:
            return {}
        stats = {
            stat: _number(self.pff_projections.get(field))
            for stat, field in PFF_STAT_FIELDS.items()
        }
        for suffix in ("0_19", "20_29", "30_39", "40_49", "50_plus"):
            stats[f"field_goals_missed_{suffix}"] = max(
                0.0,
                stats[f"field_goals_attempted_{suffix}"] - stats[f"field_goals_made_{suffix}"],
            )
        stats["field_goals_made"] = sum(
            stats[f"field_goals_made_{suffix}"]
            for suffix in ("0_19", "20_29", "30_39", "40_49", "50_plus")
        )
        stats["field_goals_missed"] = sum(
            stats[f"field_goals_missed_{suffix}"]
            for suffix in ("0_19", "20_29", "30_39", "40_49", "50_plus")
        )
        stats["extra_points_missed"] = max(
            0.0, stats["extra_points_attempted"] - stats["extra_points_made"]
        )
        return stats

    def expected_weekly_score(self, scoring_settings):
        if not self.pff_projections or self.projected_games <= 0:
            return 0.0
        return score_raw_stats(self.season_raw_stats(), self.position, scoring_settings) / self.projected_games

    def projected_season_score(self, scoring_settings):
        return score_raw_stats(self.season_raw_stats(), self.position, scoring_settings)

    def sample_parametric_stats(self, rng):
        games = self.projected_games
        if games <= 0:
            return {}
        means = {stat: value / games for stat, value in self.season_raw_stats().items()}
        if self.position in {"K", "DEF"}:
            return sample_special_team_stats(means, self.position, rng)

        stats = {stat: 0.0 for stat in means}
        stats["passing_yards"] = mean_preserving_lognormal(means["passing_yards"], 0.30, rng)
        stats["rushing_yards"] = mean_preserving_lognormal(means["rushing_yards"], 0.30, rng)
        for stat in (
            "passing_tds", "passing_interceptions", "sacks_suffered", "carries",
            "rushing_tds", "two_point_conversions", "return_tds",
        ):
            stats[stat] = int(rng.poisson(max(0.0, means.get(stat, 0.0))))
        fumbles = int(rng.poisson(max(0.0, means["fumbles"])))
        stats["fumbles"] = fumbles
        lost_rate = min(1.0, means["fumbles_lost"] / means["fumbles"]) if means["fumbles"] else 0.0
        stats["fumbles_lost"] = int(rng.binomial(fumbles, lost_rate))

        completions = int(rng.poisson(max(0.0, means["completions"])))
        stats["completions"] = completions
        stats["attempts"] = completions + int(rng.poisson(max(0.0, means["attempts"] - means["completions"])))
        receptions = int(rng.poisson(max(0.0, means["receptions"])))
        stats["receptions"] = receptions
        stats["targets"] = receptions + int(rng.poisson(max(0.0, means["targets"] - means["receptions"])))
        if receptions:
            stats["receiving_yards"] = (
                receptions * means["receiving_yards"] / means["receptions"]
                * mean_preserving_lognormal(1.0, 0.20, rng)
            ) if means["receptions"] else 0.0
            touchdown_rate = min(1.0, means["receiving_tds"] / means["receptions"]) if means["receptions"] else 0.0
            stats["receiving_tds"] = int(rng.binomial(receptions, touchdown_rate))
        stats["return_yards"] = mean_preserving_lognormal(means["return_yards"], 0.50, rng)
        return stats

    def reset_injury_status(self):
        self.missed_weeks.clear()
        self.total_games_missed_this_season = 0

    def reset_season_stats(self):
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        self.reset_injury_status()

    def record_weekly_score(self, score):
        self.total_simulated_points += score
        self.total_simulated_games += 1

    def get_average_weekly_score(self):
        return self.total_simulated_points / self.total_simulated_games if self.total_simulated_games else 0

    def print_player_short(self):
        print(f"{self.name} - {self.position} - {self.team} - 1QB: {self.value_1qb} - Redraft: {self.redraft_value} - Has PFF: {bool(self.pff_projections)}")


def mean_preserving_lognormal(mean, coefficient_of_variation, rng):
    if mean <= 0:
        return 0.0
    sigma_log = math.sqrt(math.log(1 + coefficient_of_variation**2))
    mu_log = math.log(mean) - 0.5 * sigma_log**2
    return float(rng.lognormal(mu_log, sigma_log))


class PFFProjections:
    def __init__(self, projection_data):
        self.data = projection_data.data.copy() if isinstance(projection_data, PFFProjections) else dict(projection_data)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __getattr__(self, key):
        aliases = {
            "bye_week": "byeWeek",
            "fantasy_points": "fantasyPoints",
            "pass_yds": "passYds",
            "pass_td": "passTd",
            "pass_int": "passInt",
            "rush_yds": "rushYds",
            "rush_td": "rushTd",
            "recv_receptions": "recvReceptions",
            "recv_yds": "recvYds",
            "recv_td": "recvTd",
        }
        return self.data.get(aliases.get(key, key))

    def __bool__(self):
        return _number(self.data.get("games")) > 0

    def __str__(self):
        return f"PFF Projections: {self.data.get('fantasyPoints')} points over {self.data.get('games')} games"


def _number(value):
    try:
        number = float(value)
        return 0.0 if math.isnan(number) else number
    except (TypeError, ValueError):
        return 0.0
