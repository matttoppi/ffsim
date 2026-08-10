import json
from pathlib import Path
from urllib.request import urlopen

from custom_dataclasses.fantasy_team import FantasyTeam
from custom_dataclasses.league import League


def refresh_league(league_id):
    def fetch(path):
        with urlopen(f"https://api.sleeper.app/v1/{path}", timeout=30) as response:
            return json.load(response)

    snapshot = {
        "league": fetch(f"league/{league_id}"),
        "rosters": fetch(f"league/{league_id}/rosters"),
        "users": fetch(f"league/{league_id}/users"),
    }
    path = Path(f"datarepo/league_{league_id}.json")
    path.write_text(json.dumps(snapshot, indent=2) + "\n")


class LeagueLoader:
    def __init__(self, league_id, player_loader):
        path = Path(f"datarepo/league_{league_id}.json")
        if not path.exists():
            raise FileNotFoundError("League cache is missing. Run `python main.py refresh` first.")
        self.snapshot = json.loads(path.read_text())
        self.player_loader = player_loader
        self.player_loader.ensure_players_loaded()

    def load_league(self):
        league = League(self.snapshot["league"])
        league.rosters = self.load_rosters(league)
        print(f"League {league.name} loaded with {len(league.rosters)} teams.")
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
                    team.add_player(player)

            team.calculate_metadata()
            rosters.append(team)
        return rosters
