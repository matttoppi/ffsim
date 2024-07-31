from sleeper_wrapper import League as SleeperLeague

from custom_dataclasses.fantasy_team import FantasyTeam
from custom_dataclasses.player import Player
from custom_dataclasses.player_loader import PlayerLoader, Player
from custom_dataclasses.league import League
from custom_dataclasses.fantasy_team import FantasyTeam

class LeagueLoader:
    def __init__(self, league_id, player_loader):
        self.sleeper_league = SleeperLeague(league_id)
        self.league_id = league_id
        self.player_loader = player_loader
        self.player_loader.ensure_players_loaded()  # Ensure players are loaded

    def load_league(self):
        league_data = self.sleeper_league.get_league()
        
        # print(league_data)
        
        league = League(league_data)
        
        league.rosters = self.load_rosters(league)
        #TODO: matchups
        # league.matchups = self.load_matchups()
        
        print(f"\nLeague {league.name} loaded.")
        
        return league

    def load_rosters(self, league):
        print(f"Loading rosters...")
        rosters = []
        roster_data_list = self.sleeper_league.get_rosters()
        user_dict = self.load_users()
        
        for roster_data in roster_data_list:
            owner_id = roster_data.get("owner_id")
            user_data = user_dict.get(owner_id, {})
            
            team_name = user_data.get("metadata", {}).get("team_name", "Unknown")
            
            fantasy_team = FantasyTeam(team_name, league, user_data)
            fantasy_team.roster_id = roster_data.get("roster_id")
            
            player_ids = roster_data.get("players")
            
            for player_id in player_ids:
                player = self.player_loader.load_player(player_id)
                
                if player:
                    print(f"Adding {player.full_name} to {fantasy_team.name}")
                    fantasy_team.add_player(player)
            
            fantasy_team.calculate_stats()
            
            rosters.append(fantasy_team)
            
        return rosters


        

    def load_settings(self):
        # Placeholder for loading settings
        return self.sleeper_league.get_league_settings()

    def load_matchups(self):
        # Placeholder for loading matchups
        return []


    def load_users(self):
        users = self.sleeper_league.get_users()
        user_dict = {user["user_id"]: user for user in users}
        return user_dict


