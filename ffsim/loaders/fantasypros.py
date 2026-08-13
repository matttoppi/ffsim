import json
import math
import os
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from ffsim.loaders.pff import canonical_team, normalized_name
from ffsim.paths import DATA_DIR, PROJECT_ROOT


FANTASYPROS_PROJECTIONS_URL = "https://api.fantasypros.com/public/v2/json/nfl/{season}/projections"
FANTASYPROS_PLAYERS_URL = "https://api.fantasypros.com/public/v2/json/nfl/players"
FANTASYPROS_REFRESH_INTERVAL = timedelta(hours=12)
OFFENSIVE_POSITIONS = ("QB", "RB", "WR", "TE")
FANTASYPROS_STAT_FIELDS = {
    "pass_cmp": "passComp",
    "pass_att": "passAtt",
    "pass_yds": "passYds",
    "pass_tds": "passTd",
    "pass_ints": "passInt",
    "rush_att": "rushAtt",
    "rush_yds": "rushYds",
    "rush_tds": "rushTd",
    "rec_rec": "recvReceptions",
    "rec_yds": "recvYds",
    "rec_tds": "recvTd",
    "fumbles": "fumbles",
    "2pt_tds": "twoPt",
    "ret_tds": "returnTd",
}


class FantasyProsLoader:
    @staticmethod
    def get_and_clean_data(sleeper_df, season=2026, api_key=None):
        api_key = api_key or fantasypros_api_key()
        projections = _fetch_json(
            FANTASYPROS_PROJECTIONS_URL.format(season=season),
            api_key,
            {"positions": ":".join(OFFENSIVE_POSITIONS), "week": 0},
        )
        time.sleep(1)  # FantasyPros personal API limit: one request per second.
        players = _fetch_json(FANTASYPROS_PLAYERS_URL, api_key)
        return normalize_fantasypros_projections(
            projections,
            players,
            sleeper_df,
            season=season,
            bye_weeks=_bye_weeks(season),
        )


def normalize_fantasypros_projections(response, player_response, sleeper_df, *, season, bye_weeks):
    expected_positions = set(OFFENSIVE_POSITIONS)
    positions = set(str(response.get("positions") or "").split(","))
    players = response.get("players")
    if (
        str(response.get("season")) != str(season)
        or str(response.get("week")) != "0"
        or positions != expected_positions
        or not isinstance(players, list)
    ):
        raise ValueError("FantasyPros returned an invalid preseason offensive projection response")

    metadata = player_response.get("players")
    if not isinstance(metadata, list):
        raise ValueError("FantasyPros returned invalid player metadata")
    sportsdata_by_fpid = {
        str(player.get("player_id")): str(player.get("sportsdata_player_id") or "")
        for player in metadata
        if player.get("player_id")
    }
    sleeper_by_sportsdata = _unique_mapping(
        sleeper_df,
        source="sportradar_id",
        target="player_id",
    )

    rows = []
    unmapped = []
    for player in players:
        position = str(player.get("position_id") or "").upper()
        stats = player.get("stats")
        sportsdata_id = sportsdata_by_fpid.get(str(player.get("fpid")), "")
        sleeper_id = sleeper_by_sportsdata.get(sportsdata_id)
        if position not in expected_positions or not isinstance(stats, dict):
            continue
        if sleeper_id is None:
            unmapped.append({
                "fantasypros_id": str(player.get("fpid") or ""),
                "name": str(player.get("name") or ""),
                "position": position,
                "team": canonical_team(player.get("team_id")),
                "sportsdata_id": sportsdata_id or None,
            })
            continue
        row = {
            "sleeperId": sleeper_id,
            "playerName": str(player.get("name") or ""),
            "teamName": canonical_team(player.get("team_id")),
            "position": position,
            "games": 17,
            "byeWeek": bye_weeks.get(canonical_team(player.get("team_id"))),
            "fantasyPoints": _number(stats.get("points")),
            "projectionSource": "fantasypros:consensus",
            "projectionSeason": season,
            "projectionWeek": 0,
        }
        row.update({
            target: _number(stats[source])
            for source, target in FANTASYPROS_STAT_FIELDS.items()
            if source in stats
        })
        row["normalized_name"] = normalized_name(row["playerName"])
        row["canonical_team"] = canonical_team(row["teamName"])
        rows.append(row)
    if not rows:
        raise ValueError("FantasyPros projections did not map to any active Sleeper players")
    result = pd.DataFrame(rows)
    result.attrs["mapping_report"] = {
        "returned": len(players),
        "mapped": len(rows),
        "unmapped": unmapped,
    }
    return result


def combine_with_pff(fantasypros_df, pff_by_sleeper_id):
    rows = []
    primary_ids = set()
    for primary in fantasypros_df.to_dict("records"):
        primary = {key: value for key, value in primary.items() if pd.notna(value)}
        sleeper_id = str(primary["sleeperId"])
        rows.append({**pff_by_sleeper_id.get(sleeper_id, {}), **primary})
        primary_ids.add(sleeper_id)
    for sleeper_id, pff in pff_by_sleeper_id.items():
        position = str(pff.get("position") or "").upper().replace("DST", "DEF")
        if sleeper_id not in primary_ids and position in {"K", "DEF"}:
            rows.append({**pff, "sleeperId": sleeper_id, "projectionSource": "pff"})
    return pd.DataFrame(rows)


def fantasypros_api_key(env_path=None):
    key = os.environ.get("FANTASYPROS_API_KEY")
    env_path = Path(env_path or PROJECT_ROOT / ".env")
    if not key and env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            name, separator, value = raw_line.partition("=")
            if separator and name.strip() == "FANTASYPROS_API_KEY":
                key = value.strip().strip("'\"")
                break
    if not key:
        raise ValueError("FANTASYPROS_API_KEY is missing from the environment or .env")
    if any(character.isspace() for character in key):
        raise ValueError("FANTASYPROS_API_KEY contains whitespace")
    return key


def _fetch_json(url, api_key, query=None):
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(url, headers={
        "x-api-key": api_key,
        "Cache-Control": "no-cache",
        "User-Agent": "ffsim/1.0",
    })
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _unique_mapping(data, *, source, target):
    rows = data[[source, target]].dropna().astype(str)
    duplicates = set(rows.loc[rows[source].duplicated(keep=False), source])
    return {
        getattr(row, source): getattr(row, target)
        for row in rows.itertuples(index=False)
        if getattr(row, source) not in duplicates and getattr(row, source)
    }


def _bye_weeks(season):
    games = pd.read_csv(
        DATA_DIR / "historical" / "nflverse" / "reference" / "games.csv",
        usecols=["season", "game_type", "week", "away_team", "home_team"],
    )
    games = games[(games.season == season) & (games.game_type == "REG")]
    weeks = set(range(1, 19))
    teams = set(games.away_team) | set(games.home_team)
    return {
        team: next(iter(weeks - set(games.loc[
            (games.away_team == team) | (games.home_team == team), "week"
        ].astype(int))))
        for team in teams
    }


def _number(value):
    number = float(value or 0)
    if not math.isfinite(number):
        raise ValueError(f"FantasyPros returned an invalid projection value: {value}")
    return number
