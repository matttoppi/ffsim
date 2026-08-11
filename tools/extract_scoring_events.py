"""Reduce nflverse play-by-play to the scoring events used by ffsim."""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffsim.loaders.pff import canonical_team


COLUMNS = [
    "season", "season_type", "week", "game_id", "posteam", "defteam",
    "yards_gained", "touchdown", "pass_touchdown", "rush_touchdown",
    "return_touchdown", "interception", "passer_player_id", "td_player_id",
    "fumble", "special_teams_play", "punt_blocked", "field_goal_result",
    "extra_point_result", "forced_fumble_player_1_team",
    "forced_fumble_player_1_player_id", "forced_fumble_player_2_team",
    "forced_fumble_player_2_player_id", "fumbled_1_team", "fumbled_2_team",
    "fumble_recovery_1_team", "fumble_recovery_1_player_id",
    "fumble_recovery_2_team", "fumble_recovery_2_player_id",
]
PLAYER_KEYS = ["season", "week", "game_id", "player_id"]
TEAM_KEYS = ["season", "week", "game_id", "team"]


def _events(rows, identifier, stat, keys):
    frame = rows.loc[rows[identifier].notna(), [*keys[:-1], identifier]].copy()
    frame.rename(columns={identifier: keys[-1]}, inplace=True)
    frame[stat] = 1
    return frame


def extract(source, season):
    plays = pd.read_csv(source, usecols=COLUMNS, low_memory=False)
    plays = plays[(plays.season == season) & plays.season_type.eq("REG")].copy()
    player_events = []

    for stat, mask in (
        ("receiving_tds_40_plus", plays.pass_touchdown.eq(1) & plays.yards_gained.ge(40)),
        ("receiving_tds_50_plus", plays.pass_touchdown.eq(1) & plays.yards_gained.ge(50)),
        ("rushing_tds_40_plus", plays.rush_touchdown.eq(1) & plays.yards_gained.ge(40)),
        ("rushing_tds_50_plus", plays.rush_touchdown.eq(1) & plays.yards_gained.ge(50)),
    ):
        player_events.append(_events(plays[mask], "td_player_id", stat, PLAYER_KEYS))

    for stat, mask in (
        ("passing_tds_40_plus", plays.pass_touchdown.eq(1) & plays.yards_gained.ge(40)),
        ("passing_tds_50_plus", plays.pass_touchdown.eq(1) & plays.yards_gained.ge(50)),
    ):
        player_events.append(_events(plays[mask], "passer_player_id", stat, PLAYER_KEYS))

    pick_six = plays.interception.eq(1) & plays.return_touchdown.eq(1)
    player_events.append(
        _events(plays[pick_six], "passer_player_id", "pick_sixes_thrown", PLAYER_KEYS)
    )
    fumble_td = (
        plays.fumble.eq(1)
        & plays.touchdown.eq(1)
        & plays.pass_touchdown.ne(1)
        & plays.rush_touchdown.ne(1)
        & plays.return_touchdown.ne(1)
    )
    player_events.append(
        _events(plays[fumble_td], "td_player_id", "fumble_recovery_tds", PLAYER_KEYS)
    )

    special = plays.special_teams_play.eq(1)
    for number in (1, 2):
        player_events.append(
            _events(
                plays[special],
                f"forced_fumble_player_{number}_player_id",
                "special_teams_fumbles_forced",
                PLAYER_KEYS,
            )
        )
        recovery = (
            special
            & plays[f"fumble_recovery_{number}_player_id"].notna()
            & plays[f"fumble_recovery_{number}_team"].ne(plays.fumbled_1_team)
        )
        player_events.append(
            _events(
                plays[recovery],
                f"fumble_recovery_{number}_player_id",
                "special_teams_fumbles_recovered",
                PLAYER_KEYS,
            )
        )

    players = pd.concat(player_events, ignore_index=True).fillna(0)
    player_stats = [column for column in players if column not in PLAYER_KEYS]
    players = players.groupby(PLAYER_KEYS, as_index=False)[player_stats].sum()

    team_events = []
    blocked = (
        plays.punt_blocked.eq(1)
        | plays.field_goal_result.eq("blocked")
        | plays.extra_point_result.eq("blocked")
    )
    team_events.append(_events(plays[blocked], "defteam", "blocked_kicks", TEAM_KEYS))
    for number in (1, 2):
        team_events.append(
            _events(
                plays[special],
                f"forced_fumble_player_{number}_team",
                "defense_special_teams_fumbles_forced",
                TEAM_KEYS,
            )
        )
        recovery = (
            special
            & plays[f"fumble_recovery_{number}_team"].notna()
            & plays[f"fumble_recovery_{number}_team"].ne(plays.fumbled_1_team)
        )
        team_events.append(
            _events(
                plays[recovery],
                f"fumble_recovery_{number}_team",
                "defense_special_teams_fumbles_recovered",
                TEAM_KEYS,
            )
        )
    teams = pd.concat(team_events, ignore_index=True).fillna(0)
    team_stats = [column for column in teams if column not in TEAM_KEYS]
    teams = teams.groupby(TEAM_KEYS, as_index=False)[team_stats].sum()
    teams["team"] = teams.team.map(canonical_team)
    return players.sort_values(PLAYER_KEYS), teams.sort_values(TEAM_KEYS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("season", type=int)
    parser.add_argument("source", help="nflverse play_by_play_<season>.csv.gz")
    parser.add_argument(
        "--output-dir", default="data/historical/nflverse/play_by_play"
    )
    args = parser.parse_args()

    players, teams = extract(args.source, args.season)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    players.to_csv(output / f"scoring_player_week_{args.season}.csv", index=False)
    teams.to_csv(output / f"scoring_team_week_{args.season}.csv", index=False)
    print(f"Extracted {len(players)} player rows and {len(teams)} team rows for {args.season}.")


if __name__ == "__main__":
    main()
