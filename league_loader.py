# Make sure you've defined all necessary imports
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
        league = League(league_data)

        league.rosters = self.load_rosters()
        league.settings = self.load_settings()
        league.matchups = self.load_matchups()

        return league

    def load_rosters(self):
        rosters = []
        roster_data_list = self.sleeper_league.get_rosters()
        for roster_data in roster_data_list:
            fantasy_team = FantasyTeam(str(roster_data['owner_id']))  # Assuming 'owner_id' can serve as team name
            fantasy_team.set_settings(roster_data['settings'])  # Make sure this method exists in FantasyTeam

            for player_id in roster_data.get('players', []):
                player_details = self.player_loader.get_player(player_id)
                if player_details:
                    player = Player(player_details)  # Pass the entire dictionary to Player __init__
                    fantasy_team.players.append(player)
            rosters.append(fantasy_team)
        return rosters

    def load_settings(self):
        # Placeholder for loading settings
        return self.sleeper_league.get_league_settings()

    def load_matchups(self):
        # Placeholder for loading matchups
        return []

# # Example Usage
# # First, create an instance of PlayerLoader and load players
# player_loader = PlayerLoader()
# player_loader.load_players()

# # Then, create an instance of LeagueLoader, passing in the league ID and player_loader
# league_id = "your_league_id_here"
# league_loader = LeagueLoader(league_id, player_loader)

# # Now, you can load the league
# league = league_loader.load_league()

# # Access
