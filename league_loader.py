from sleeper_wrapper import League as SleeperLeague

from league import League, ScoringSettings, LeagueSettings
from fantasy_team import FantasyTeam
from player import Player
from player_loader import PlayerLoader  # Assuming PlayerLoader is in player_loader.py

class LeagueLoader:
    def __init__(self, league_id, player_loader):
        self.sleeper_league = SleeperLeague(league_id)
        self.league_id = league_id
        self.player_loader = player_loader  # This is an instance of PlayerLoader

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
        user_dict = self.load_users()  # Load user data for association with rosters
        self.player_loader.load_players_from_file() # Load players from file
        
        for roster_data in roster_data_list:
            owner_id = roster_data.get("owner_id")
            user_data = user_dict.get(owner_id, {})  # Fetch user data for the roster's owner
            
            
            team_name = user_data.get("metadata", {}).get("team_name", "Unknown")
            
            # Assuming FantasyTeam can store user data; adjust constructor as needed
            fantasy_team = FantasyTeam(team_name, league, user_data)
            
            # Load the players on the roster
            player_ids = roster_data.get("players")
            
            for player_id in player_ids:
                player = self.player_loader.load_player(player_id)
                
                if player:
                    fantasy_team.players.append(player)
                    fantasy_team.player_sleeper_ids.append(player.sleeper_id)
                            
            fantasy_team.calculate_stats()
            
            
            
            # fantasy_team.print_fantasy_team()
            fantasy_team.print_fantasy_team_short()
                
            
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


