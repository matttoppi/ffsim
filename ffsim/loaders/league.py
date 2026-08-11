import json
from urllib.parse import quote
from urllib.request import urlopen

from ffsim.models.league import League
from ffsim.models.team import FantasyTeam
from ffsim.paths import CACHE_DIR


def _fetch_json(path):
    with urlopen(f"https://api.sleeper.app/v1/{path}", timeout=30) as response:
        return json.load(response)


def leagues_for_username(username, season=2026):
    username = username.strip()
    if not username:
        raise ValueError("Sleeper username cannot be empty")

    user = _fetch_json(f"user/{quote(username, safe='')}")
    if not user or not user.get("user_id"):
        raise ValueError(f"Sleeper user not found: {username}")

    leagues = _fetch_json(f"user/{user['user_id']}/leagues/nfl/{season}")
    return sorted(
        leagues,
        key=lambda league: (
            league.get("name", "").casefold(),
            str(league.get("league_id", "")),
        ),
    )


def league_id_for_username(username, season=2026):
    leagues = leagues_for_username(username, season)
    if not leagues:
        raise ValueError(f"No {season} NFL leagues found for Sleeper user {username}")
    if len(leagues) > 1:
        choices = ", ".join(
            f"{league.get('name', 'Unnamed')} ({league['league_id']})"
            for league in leagues
        )
        raise ValueError(
            f"Multiple {season} NFL leagues found for {username}; "
            f"use --league-id: {choices}"
        )
    return str(leagues[0]["league_id"])


def refresh_league(league_id):
    snapshot = {
        "league": _fetch_json(f"league/{league_id}"),
        "rosters": _fetch_json(f"league/{league_id}/rosters"),
        "users": _fetch_json(f"league/{league_id}/users"),
        "winners_bracket": _fetch_json(f"league/{league_id}/winners_bracket"),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"league_{league_id}.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n")


class LeagueLoader:
    def __init__(self, league_id, player_loader):
        path = CACHE_DIR / f"league_{league_id}.json"
        if not path.exists():
            raise FileNotFoundError("League cache is missing. Run `python -m ffsim refresh` first.")
        self.snapshot = json.loads(path.read_text())
        self.player_loader = player_loader
        self.player_loader.ensure_players_loaded()
        self.unmatched_rostered = []

    def load_league(self):
        league = League(self.snapshot["league"])
        league.rosters = self.load_rosters(league)
        league.winners_bracket = self.snapshot.get("winners_bracket", [])
        print(f"League {league.name} loaded with {len(league.rosters)} teams.")
        if self.unmatched_rostered:
            print("Rostered players without 2026 projections are unavailable:")
            for player in sorted(self.unmatched_rostered, key=lambda player: (player.name, str(player.sleeper_id))):
                print(f"  {player.name} ({player.position}, {player.team}, Sleeper {player.sleeper_id})")
        return league

    def load_rosters(self, league):
        users = {user["user_id"]: user for user in self.snapshot["users"]}
        rosters = []
        for roster_data in self.snapshot["rosters"]:
            user_data = users.get(roster_data.get("owner_id"), {})
            team_name = user_data.get("metadata", {}).get("team_name", "Unknown")
            team = FantasyTeam(team_name, league, user_data)
            team.roster_id = roster_data.get("roster_id")
            division = roster_data.get("settings", {}).get("division")
            if division is not None:
                league.divisions.setdefault(int(division), []).append(team.roster_id)

            for player_id in roster_data.get("players", []):
                player = self.player_loader.load_player(player_id)
                if player:
                    if player.position in {"QB", "RB", "WR", "TE", "K", "DEF"} and player.projection_match_status in {"ambiguous", "position_mismatch"}:
                        raise ValueError(
                            f"Rostered player has no unique position-consistent PFF projection: "
                            f"{player.name} ({player.position}, {player.team}, Sleeper {player.sleeper_id})"
                        )
                    if player.position in {"QB", "RB", "WR", "TE", "K", "DEF"} and player.projection_match_status == "unmatched":
                        self.unmatched_rostered.append(player)
                    team.add_player(player)

            team.calculate_metadata()
            rosters.append(team)
        return rosters
