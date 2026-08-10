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
    "st_td": "return_tds",
    "fgm": "field_goals_made",
    "fgmiss": "field_goals_missed",
    "fgm_0_19": "field_goals_made_0_19",
    "fgm_20_29": "field_goals_made_20_29",
    "fgm_30_39": "field_goals_made_30_39",
    "fgm_40_49": "field_goals_made_40_49",
    "fgm_50p": "field_goals_made_50_plus",
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
    "pts_allow_0": "points_allowed_0",
    "pts_allow_1_6": "points_allowed_1_6",
    "pts_allow_7_13": "points_allowed_7_13",
    "pts_allow_14_20": "points_allowed_14_20",
    "pts_allow_21_27": "points_allowed_21_27",
    "pts_allow_28_34": "points_allowed_28_34",
    "pts_allow_35p": "points_allowed_35_plus",
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

    def get(self, key):
        return self.values.get(key, 0.0)

    def __getattr__(self, key):
        return self.get(key)


def unsupported_scoring_keys(settings):
    nonzero = {key for key, value in settings.items() if float(value) != 0}
    supported = set(DIRECT_KEYS) | set(POSITION_RECEPTION_BONUSES.values())

    if _equal_coefficients(settings, ("pass_2pt", "rush_2pt", "rec_2pt")):
        supported.update(("pass_2pt", "rush_2pt", "rec_2pt"))
    if _equal_coefficients(settings, ("kr_yd", "pr_yd")):
        supported.update(("kr_yd", "pr_yd"))
    if _equal_coefficients(settings, ("def_kr_yd", "def_pr_yd")):
        supported.update(("def_kr_yd", "def_pr_yd"))
    return sorted(nonzero - supported)


def score_raw_stats(stats, position, scoring_settings):
    settings = scoring_settings if isinstance(scoring_settings, ScoringSettings) else ScoringSettings(scoring_settings)
    score = sum(stats.get(stat, 0) * settings.get(key) for key, stat in DIRECT_KEYS.items())

    position = str(position).upper()
    score += stats.get("receptions", 0) * settings.get(POSITION_RECEPTION_BONUSES.get(position, ""))
    score += stats.get("two_point_conversions", 0) * settings.get("pass_2pt")
    score += stats.get("return_yards", 0) * settings.get("kr_yd")
    score += stats.get("defense_return_yards", 0) * settings.get("def_kr_yd")
    return float(score)


def _equal_coefficients(settings, keys):
    values = [float(settings.get(key, 0)) for key in keys]
    return not any(values) or len(set(values)) == 1
