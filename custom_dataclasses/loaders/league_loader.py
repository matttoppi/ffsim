import json
from urllib.request import urlopen

from custom_dataclasses.fantasy_team import FantasyTeam
from custom_dataclasses.league import League


class LeagueLoader:
    def __init__(self, league_id, player_loader):
        self.league_id = league_id
        self.player_loader = player_loader
        self.player_loader.ensure_players_loaded()

    def _get(self, path):
        with urlopen(f"https://api.sleeper.app/v1/{path}", timeout=30) as response:
            return json.load(response)

    def load_league(self):
        league = League(self._get(f"league/{self.league_id}"))
        league.rosters = self.load_rosters(league)
        league.print_rosters_ids()
        print(f"\nLeague {league.name} loaded with {len(league.rosters)} teams.")
        return league

    def load_rosters(self, league):
        users = {user["user_id"]: user for user in self._get(f"league/{self.league_id}/users")}
        rosters = []
        for roster_data in self._get(f"league/{self.league_id}/rosters"):
            user_data = users.get(roster_data.get("owner_id"), {})
            team_name = user_data.get("metadata", {}).get("team_name", "Unknown")
            team = FantasyTeam(team_name, league, user_data)
            team.roster_id = roster_data.get("roster_id")

            for player_id in roster_data.get("players", []):
                player = self.player_loader.load_player(player_id)
                if player:
                    team.add_player(player)

            team.calculate_metadata()
            rosters.append(team)
        return rosters
