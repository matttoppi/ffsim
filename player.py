

class Player:
    def __init__(self, initial_data):
        # Initialize all attributes from the provided data
        for key, value in initial_data.items():
            if "id" in key and isinstance(value, str) and value.endswith('.0'):
                value = value[:-2]  # Remove the trailing '.0'
            setattr(self, key, value)
        # Ensure all possible attributes are initialized
        self.initialize_missing_attributes()

    def initialize_missing_attributes(self):
        # Defines all potential attributes for a Player
        all_attributes = [
            'position', 'mfl_id', 'sportradar_id', 'fantasypros_id', 
            'gsis_id', 'pff_id', 'sleeper_id', 'nfl_id', 'espn_id', 'yahoo_id', 
            'fleaflicker_id', 'cbs_id', 'pfr_id', 'cfbref_id', 'rotowire_id', 
            'rotoworld_id', 'ktc_id', 'stats_id', 'stats_global_id', 
            'fantasy_data_id', 'swish_id', 'merge_name', 'team', 'birthdate', 
            'age', 'draft_year', 'draft_round', 'draft_pick', 'draft_ovr', 
            'twitter_username', 'height', 'weight', 'college', 'db_season', 
            'number', 'depth_chart_position', 'status', 'sport', 
            'fantasy_positions', 'search_last_name', 'injury_start_date', 
            'practice_participation', 'last_name', 'search_full_name', 
            'birth_country', 'search_rank', 'first_name', 'depth_chart_order', 
            'search_first_name', 'current_fantasy_team', 'current_season_fantasy_pts', 
            'previous_season_fantasy_pts', 
            'injury_risk', 
            'player_potential', 'ecr_1qb', 'ecr_2qb', 'ecr_pos', 'value_1qb', 
            'value_2qb', 'scrape_date', 'fp_id'
        ]
        # Initialize missing attributes to None
        for attribute in all_attributes:
            if not hasattr(self, attribute):
                setattr(self, attribute, None)
                
        if self.position is None:
            self.position = "UNKNOWN"
            
        if self.value_1qb is None:
            self.value_1qb = 0
        
        if self.value_2qb is None:
            self.value_2qb = 0

    def update_with_sleeper_data(self, sleeper_data):
        # This method should be called to update the player with Sleeper API data
        # Map the Sleeper data to player attributes
        for key, value in sleeper_data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def apply_id_mapping(self, mapping):
        # Update player with ID mapping data, ensuring no overwrites of existing data
        for key, value in mapping.items():
            if hasattr(self, key) and getattr(self, key) is None:
                setattr(self, key, value)

    def to_dict(self):
        # Convert the player object to a dictionary
        # Only include attributes listed in initialize_missing_attributes for consistency
        all_attributes = [
            'position', 'mfl_id', 'sportradar_id', 'fantasypros_id', 
            'gsis_id', 'pff_id', 'sleeper_id', 'nfl_id', 'espn_id', 'yahoo_id', 
            'fleaflicker_id', 'cbs_id', 'pfr_id', 'cfbref_id', 'rotowire_id', 
            'rotoworld_id', 'ktc_id', 'stats_id', 'stats_global_id', 
            'fantasy_data_id', 'swish_id', 'merge_name', 'team', 'birthdate', 
            'age', 'draft_year', 'draft_round', 'draft_pick', 'draft_ovr', 
            'twitter_username', 'height', 'weight', 'college', 'db_season', 
            'number', 'depth_chart_position', 'status', 'sport', 
            'fantasy_positions', 'search_last_name', 'injury_start_date', 
            'practice_participation', 'last_name', 'search_full_name', 
            'birth_country', 'search_rank', 'first_name', 'depth_chart_order', 
            'search_first_name', 'current_fantasy_team', 'current_season_fantasy_pts', 
            'previous_season_fantasy_pts', 
            'injury_risk', 
            'player_potential', 'ecr_1qb', 'ecr_2qb', 'ecr_pos', 'value_1qb', 
            'value_2qb', 'scrape_date', 'fp_id'
        ]
        return {attr: getattr(self, attr) for attr in all_attributes if hasattr(self, attr)}
    
    
    def print_player(self):
        for key, value in self.to_dict().items():
            print(f"{key}: {value}")
            
    def print_player_short(self):
        print(f"{self.first_name} {self.last_name} - {self.position} - {self.team} - {self.value_1qb}")