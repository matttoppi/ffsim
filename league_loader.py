from sleeper_wrapper import League as SleeperLeague

from league import League, ScoringSettings, LeagueSettings
from fantasy_team import FantasyTeam
from player import Player

class LeagueLoader:
    def __init__(self, league_id, player_loader):
        self.sleeper_league = SleeperLeague(league_id)
        self.league_id = league_id
        self.player_loader = player_loader  # Instance of PlayerLoader

    def load_league(self):
        league_data = self.sleeper_league.get_league()
        # Assuming league_data is a dictionary with league details
        league = League(league_data)  # Pass entire league_data dictionary to League __init__

        # Populate League with rosters, settings, and matchups
        league.rosters = self.load_rosters()
        league.settings = self.load_settings()
        league.matchups = self.load_matchups()

        return league

    def load_rosters(self):
        rosters = []
        for roster_data in self.sleeper_league.get_rosters():
            fantasy_team = FantasyTeam(str(roster_data['owner_id']))  # Assuming 'owner_id' as team name

            # Set team settings from roster_data
            fantasy_team.set_settings(roster_data['settings'])

            # Load players into fantasy_team
            for player_id in roster_data.get('players', []):
                player_details = self.player_loader.get_player(player_id)
                if player_details:
                    player = Player(player_details['name'])  # Initialize Player with name
                    # Dynamically set Player attributes
                    for key, value in player_details.items():
                        setattr(player, key, value) if hasattr(player, key) else None
                    fantasy_team.players.append(player)
            rosters.append(fantasy_team)
        return rosters

    def load_settings(self):
        # Example placeholder, adjust according to how you wish to handle settings
        return self.sleeper_league.get_league_settings()

    def load_matchups(self):
        # Placeholder, adjust to fetch and return matchups data
        return []

