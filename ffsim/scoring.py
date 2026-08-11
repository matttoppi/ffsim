"""Sleeper scoring for the raw statistics available in this repository."""


DIRECT_KEYS = {
    "pass_cmp": "completions",
    "pass_att": "attempts",
    "pass_yd": "passing_yards",
    "pass_td": "passing_tds",
    "pass_int": "passing_interceptions",
    "pass_sack": "sacks_suffered",
    "rush_att": "carries",
    "rush_yd": "rushing_yards",
    "rush_td": "rushing_tds",
    "rec": "receptions",
    "rec_yd": "receiving_yards",
    "rec_td": "receiving_tds",
    "fum": "fumbles",
    "fum_lost": "fumbles_lost",
    "fum_rec_td": "fumble_recovery_tds",
    "pass_int_td": "pick_sixes_thrown",
    "rec_td_40p": "receiving_tds_40_plus",
    "rec_td_50p": "receiving_tds_50_plus",
    "rush_td_40p": "rushing_tds_40_plus",
    "rush_td_50p": "rushing_tds_50_plus",
    "pass_td_40p": "passing_tds_40_plus",
    "pass_td_50p": "passing_tds_50_plus",
    "st_td": "return_tds",
    "st_ff": "special_teams_fumbles_forced",
    "st_fum_rec": "special_teams_fumbles_recovered",
    "fgm": "field_goals_made",
    "fgm_yds_over_30": "field_goal_yards_over_30",
    "fgmiss": "field_goals_missed",
    "fgm_0_19": "field_goals_made_0_19",
    "fgm_20_29": "field_goals_made_20_29",
    "fgm_30_39": "field_goals_made_30_39",
    "fgm_40_49": "field_goals_made_40_49",
    "fgm_50p": "field_goals_made_50_plus",
    "fgm_60p": "field_goals_made_60_plus",
    "fgmiss_0_19": "field_goals_missed_0_19",
    "fgmiss_20_29": "field_goals_missed_20_29",
    "fgmiss_30_39": "field_goals_missed_30_39",
    "fgmiss_40_49": "field_goals_missed_40_49",
    "fgmiss_50p": "field_goals_missed_50_plus",
    "xpm": "extra_points_made",
    "xpmiss": "extra_points_missed",
    "sack": "defense_sacks",
    "int": "defense_interceptions",
    "ff": "defense_fumbles_forced",
    "fum_rec": "defense_fumbles_recovered",
    "safe": "defense_safeties",
    "def_td": "defense_tds",
    "def_st_td": "defense_return_tds",
    "blk_kick": "blocked_kicks",
    "def_st_ff": "defense_special_teams_fumbles_forced",
    "def_st_fum_rec": "defense_special_teams_fumbles_recovered",
    "pts_allow_0": "points_allowed_0",
    "pts_allow_1_6": "points_allowed_1_6",
    "pts_allow_7_13": "points_allowed_7_13",
    "pts_allow_14_20": "points_allowed_14_20",
    "pts_allow_21_27": "points_allowed_21_27",
    "pts_allow_28_34": "points_allowed_28_34",
    "pts_allow_35p": "points_allowed_35_plus",
    "yds_allow_0_100": "yards_allowed_0_100",
    "yds_allow_100_199": "yards_allowed_100_199",
    "yds_allow_200_299": "yards_allowed_200_299",
    "yds_allow_300_349": "yards_allowed_300_349",
    "yds_allow_350_399": "yards_allowed_350_399",
    "yds_allow_400_449": "yards_allowed_400_449",
    "yds_allow_450_499": "yards_allowed_450_499",
    "yds_allow_500_549": "yards_allowed_500_549",
    "yds_allow_550p": "yards_allowed_550_plus",
}

POSITION_RECEPTION_BONUSES = {"TE": "bonus_rec_te", "RB": "bonus_rec_rb", "WR": "bonus_rec_wr"}


class ScoringSettings:
    def __init__(self, scoring_data=None):
        self.values = {key: float(value) for key, value in (scoring_data or {}).items()}
        unsupported = unsupported_scoring_keys(self.values)
        if unsupported:
            raise ValueError(
                "Unsupported nonzero Sleeper scoring keys for available projection data: "
                + ", ".join(unsupported)
            )
        self.direct_coefficients = tuple(
            (stat, self.get(key)) for key, stat in DIRECT_KEYS.items()
        )
        self.direct_coefficients_by_position = {}
        self.reception_bonuses = {
            position: self.get(key) for position, key in POSITION_RECEPTION_BONUSES.items()
        }
        self.two_point_coefficient = self.get("pass_2pt")
        self.return_coefficients = {
            "": (self.get("kr_yd"), self.get("pr_yd")),
            "def_": (self.get("def_kr_yd"), self.get("def_pr_yd")),
        }

    def compile_positions(self, players):
        stats_by_position = {}
        for player in players:
            if not player.pff_projections or player.projected_games <= 0:
                continue
            stats_by_position.setdefault(player.position, set()).update(
                stat for stat, value in player.modeled_weekly_raw_stats().items() if value
            )
        self.direct_coefficients_by_position = {
            position: tuple(
                (stat, coefficient)
                for stat, coefficient in self.direct_coefficients
                if coefficient and stat in stats
            )
            for position, stats in stats_by_position.items()
        }

    def get(self, key):
        return self.values.get(key, 0.0)

    def __getattr__(self, key):
        values = self.__dict__.get("values")
        if values is None:
            raise AttributeError(key)
        return values.get(key, 0.0)


def unsupported_scoring_keys(settings):
    nonzero = {key for key, value in settings.items() if float(value) != 0}
    supported = (
        set(DIRECT_KEYS)
        | set(POSITION_RECEPTION_BONUSES.values())
        | {"kr_yd", "pr_yd", "def_kr_yd", "def_pr_yd"}
    )

    if _equal_coefficients(settings, ("pass_2pt", "rush_2pt", "rec_2pt")):
        supported.update(("pass_2pt", "rush_2pt", "rec_2pt"))
    return sorted(nonzero - supported)


def score_raw_stats(stats, position, scoring_settings):
    settings = scoring_settings if isinstance(scoring_settings, ScoringSettings) else ScoringSettings(scoring_settings)
    position = str(position).upper()
    score = sum(
        stats.get(stat, 0) * coefficient
        for stat, coefficient in settings.direct_coefficients_by_position.get(
            position, settings.direct_coefficients
        )
    )

    score += stats.get("receptions", 0) * settings.reception_bonuses.get(position, 0.0)
    score += stats.get("two_point_conversions", 0) * settings.two_point_coefficient
    score += _return_score(stats, settings, "", "return_yards")
    score += _return_score(stats, settings, "defense_", "defense_return_yards", "def_")
    return float(score)


def _return_score(stats, settings, stat_prefix, combined_stat, setting_prefix=""):
    kick = f"{stat_prefix}kick_return_yards"
    punt = f"{stat_prefix}punt_return_yards"
    if kick in stats or punt in stats:
        coefficients = settings.return_coefficients[setting_prefix]
        return (
            stats.get(kick, 0) * coefficients[0]
            + stats.get(punt, 0) * coefficients[1]
        )
    coefficients = settings.return_coefficients[setting_prefix]
    if coefficients[0] != coefficients[1] and stats.get(combined_stat, 0):
        raise ValueError(
            f"Separate {kick} and {punt} are required when return-yard coefficients differ"
        )
    return stats.get(combined_stat, 0) * coefficients[0]


def _equal_coefficients(settings, keys):
    values = [float(settings.get(key, 0)) for key in keys]
    return not any(values) or len(set(values)) == 1
