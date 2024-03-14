class ScoringSettings:
    def __init__(self, scoring_data):
        for key, value in scoring_data.items():
            setattr(self, key, value)
            
    def print_scoring_settings(self):
        print(f"\n\nScoring data:\n")
        for key, value in self.__dict__.items():
            print(f"{key}: {value}")
        

class LeagueSettings:
    def __init__(self, settings_data):
        print(f"Loading league settings...")
        for key, value in settings_data.items():
            setattr(self, key, value)
        print(f"League settings loaded.\n")
            
            
    def print_settings(self):
        print(f"\n\nSettings data:\n")
        for key, value in self.__dict__.items():
            print(f"{key}: {value}")

class League:
    def __init__(self, league_data):
        self.name = league_data.get("name")
        self.total_rosters = league_data.get("total_rosters")
        self.roster_positions = league_data.get("roster_positions")
        self.loser_bracket_id = league_data.get("loser_bracket_id")
        self.group_id = league_data.get("group_id")
        self.bracket_id = league_data.get("bracket_id")
        self.previous_league_id = league_data.get("previous_league_id")
        self.league_id = league_data.get("league_id")
        self.draft_id = league_data.get("draft_id")
        self.last_read_id = league_data.get("last_read_id")
        self.last_pinned_message_id = league_data.get("last_pinned_message_id")
        self.last_message_time = league_data.get("last_message_time")
        self.last_message_text_map = league_data.get("last_message_text_map")
        self.last_message_attachment = league_data.get("last_message_attachment")
        self.last_author_is_bot = league_data.get("last_author_is_bot")
        self.last_author_id = league_data.get("last_author_id")
        self.last_author_display_name = league_data.get("last_author_display_name")
        self.last_author_avatar = league_data.get("last_author_avatar")
        self.scoring_settings = ScoringSettings(league_data.get("scoring_settings", {}))
        self.settings = LeagueSettings(league_data.get("settings", {}))
        self.sport = league_data.get("sport")
        self.season_type = league_data.get("season_type")
        self.season = league_data.get("season")
        self.shard = league_data.get("shard")
        self.last_message_id = league_data.get("last_message_id")
        self.company_id = league_data.get("company_id")
        self.avatar = league_data.get("avatar")
        self.metadata = league_data.get("metadata", {})
        self.status = league_data.get("status")
        self.rosters = None
        
        #get the amount of starters from the roster_positions. anything not a bench slot is a starter
        # example: ['QB', 'RB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'FLEX', 'FLEX', 'K', 'DEF', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN', 'BN']

        self.number_of_starters = 0
        for position in self.roster_positions:
            if position != "BN" and position != "IR" and position != "TAXI" and position != "K" and position != "DEF":
                self.number_of_starters += 1
            
        
    def print_league(self):
        print(f"\n\nLeague data:\n")
        for key, value in self.__dict__.items():
            print(f"{key}: {value}")
            
        print(self.scoring_settings.print_scoring_settings())
        print(self.settings.print_settings())
        
        
        
        
    

    def print_rosters(self):
        for team in self.rosters:
            print(f"Team: {team.name}")
            for player in team.players:
                print(f"  Player: {player.name} - {player.position} - {player.nfl_team} - {player.value_1qb}")
            
            print(f"  Total value 1QB: {team.total_value_1qb}")
            print(f"  Total value 2QB: {team.total_value_2qb}")
            print(f"  Average age: {team.average_age}") 
                
            
            
# # Example usage:
# import json

# league_json_str = 'your JSON string here'
# league_data = json.loads(league_json_str)
# league = League(league_data)

# # You can now access any attribute of the league object, for example:
# print(league.name)
# print(league.season)
# print(league.scoring_settings.pass_td)
# print(league.settings.reserve_slots)
