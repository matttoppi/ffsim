import json
from pathlib import Path

import numpy as np

from ffsim.scoring import DIRECT_KEYS, score_raw_stats


def load_scenario(path):
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or not isinstance(data.get("players", {}), dict):
        raise ValueError("Scenario must be an object with an optional players object")
    for key in ("game_environment_cv", "team_environment_cv", "competition_cv"):
        value = float(data.get(key, 0))
        if value < 0:
            raise ValueError(f"{key} cannot be negative")
        data[key] = value
    if not isinstance(data.get("use_sleeper_projections", False), bool):
        raise ValueError("use_sleeper_projections must be true or false")
    return data


def apply_scenario(league, scenario):
    players = {
        str(player.sleeper_id): player
        for team in league.rosters
        for player in team.players
    }
    unknown = sorted(set(scenario.get("players", {})) - set(players))
    if unknown:
        raise ValueError(f"Scenario contains unknown Sleeper player IDs: {', '.join(unknown)}")

    configured = scenario.get("players", {})
    for player_id, player in players.items():
        values = configured.get(player_id, {})
        if not isinstance(values, dict):
            raise ValueError(f"Scenario player {player_id} must be an object")
        pff_points = (
            player.projected_season_score(league.scoring_settings)
            if player.pff_projections and player.projected_games > 0
            else 0.0
        )
        external = [float(value) for value in values.get("projection_points", [])]
        projection_ratios = [1.0, *(value / pff_points for value in external)] if pff_points else []
        if pff_points > 0 and scenario.get("use_sleeper_projections") and player.sleeper_projections:
            shared_settings = {
                key: value
                for key, value in league.scoring_settings.values.items()
                if key in player.sleeper_projections
                and key not in {"pass_2pt", "rush_2pt", "rec_2pt"}
            }
            two_point_keys = ("pass_2pt", "rush_2pt", "rec_2pt")
            if any(key in player.sleeper_projections for key in two_point_keys):
                shared_settings.update(
                    {key: league.scoring_settings.pass_2pt for key in two_point_keys}
                )
            sleeper_points = _sleeper_score(
                player.sleeper_projections, player.position, shared_settings
            )
            comparable_pff_points = score_raw_stats(
                player.modeled_season_raw_stats(), player.position, shared_settings
            )
            if sleeper_points > 0 and comparable_pff_points > 0:
                projection_ratios.append(sleeper_points / comparable_pff_points)
        if external:
            if pff_points <= 0 or any(value < 0 for value in external):
                raise ValueError(f"Invalid projection_points for {player.name}")
        if len(projection_ratios) > 1:
            disagreement = float(np.std(projection_ratios))
            player.season_cv = float(np.hypot(player.season_cv, disagreement))
        if "projection_multiplier" in values:
            player.projection_multiplier = float(values["projection_multiplier"])
        if "season_cv" in values:
            player.season_cv = float(values["season_cv"])
        if "projected_games" in values:
            player.projected_games_override = float(values["projected_games"])
        player.week_play_probabilities = {
            int(week): float(probability)
            for week, probability in values.get("play_probability", {}).items()
        }
        player.forced_missed_weeks = {int(week) for week in values.get("missed_weeks", [])}
        if player.projection_multiplier < 0 or player.season_cv < 0:
            raise ValueError(f"Projection multiplier and season CV cannot be negative for {player.name}")
        if any(not 0 <= probability <= 1 for probability in player.week_play_probabilities.values()):
            raise ValueError(f"Play probabilities must be between 0 and 1 for {player.name}")
        player._modeled_weekly_stats = None
        player._expected_score_for = None


def _sleeper_score(stats, position, scoring_settings):
    raw = {
        stat: float(stats.get(key, 0) or 0)
        for key, stat in DIRECT_KEYS.items()
    }
    raw["two_point_conversions"] = sum(
        float(stats.get(key, 0) or 0) for key in ("pass_2pt", "rush_2pt", "rec_2pt")
    )
    for source, target in (
        ("kr_yd", "kick_return_yards"),
        ("pr_yd", "punt_return_yards"),
        ("def_kr_yd", "defense_kick_return_yards"),
        ("def_pr_yd", "defense_punt_return_yards"),
    ):
        if source in stats:
            raw[target] = float(stats[source] or 0)
    return score_raw_stats(raw, position, scoring_settings)
