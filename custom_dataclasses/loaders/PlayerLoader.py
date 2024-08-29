import requests
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from fuzzywuzzy import process
from custom_dataclasses.player import Player, PFFProjections
from custom_dataclasses.loaders.SleeperLoader import SleeperLoader
from custom_dataclasses.loaders.PFFLoader import PFFLoader
from custom_dataclasses.loaders.InjuryDataLoader import InjuryDataLoader
from custom_dataclasses.loaders.FantasyCalcLoader import FantasyCalcLoader
from custom_dataclasses.loaders.DataMerger import DataMerger
from sim.SimulationClasses.SpecialTeamScorer import SpecialTeamScorer



import os
from datetime import datetime, timedelta
import json
from custom_dataclasses.player import Player



class PlayerLoader:
    def __init__(self, print_projections=False):
        self.players_file = 'datarepo/players.json'
        self.sleeper_players_file = 'sleeper_players.json'
        self.refresh_interval = timedelta(days=3)
        self.enriched_players = []
        self.search_name_to_player = {}
        self.pff_projections = None
        self.print_projections = print_projections
        self.sleeper_players = self.load_sleeper_players()
        self.special_team_scorer = SpecialTeamScorer('datarepo/PFFProjections/kickers.csv', 'datarepo/PFFProjections/dsts.csv')

    def load_sleeper_players(self):
        try:
            with open(self.sleeper_players_file, 'r') as f:
                players_list = json.load(f)
                return {str(player['player_id']): player for player in players_list if 'player_id' in player}
        except FileNotFoundError:
            print(f"{self.sleeper_players_file} not found. Player position updates will not be available.")
            return {}
        except json.JSONDecodeError:
            print(f"Error decoding {self.sleeper_players_file}. Please check if the file is valid JSON.")
            return {}

    def load_players_from_file(self):
        if os.path.exists(self.players_file) and datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.players_file)) <= self.refresh_interval:
            print(f"Loading players from file: {self.players_file}")
            with open(self.players_file, 'r') as file:
                player_data = json.load(file)
            
            self.enriched_players = []
            players_updated = 0
            for data in player_data:
                sleeper_id = str(data.get('sleeper_id'))
                if sleeper_id in self.sleeper_players:
                    sleeper_player = self.sleeper_players[sleeper_id]
                    current_position = data.get('position')
                    if not isinstance(current_position, str) or current_position in ['0', 'UNKNOWN']:
                        new_position = sleeper_player.get('position')
                        if new_position:
                            data['position'] = new_position
                            players_updated += 1
                
                # Ensure position is always a string
                if 'position' in data:
                    data['position'] = str(data['position'])
                
                pff_data = data.get('pff_projections', {})
                data['pff_projections'] = PFFProjections(pff_data) if pff_data else None
                player = Player(data)
                player.initialize_st_scorer(self.special_team_scorer)
                self.enriched_players.append(player)
            
            self.search_name_to_player = {Player.clean_name(p.full_name): p for p in self.enriched_players}
            print(f"Loaded {len(self.enriched_players)} players from file.")
            print(f"Updated positions for {players_updated} players.")
            
            if players_updated > 0:
                self.save_players_to_file()
            
            self.update_with_sleeper_data()
            self.load_and_update_pff_data()
        else:
            print("Player data file not found or outdated. Fetching new data...")
            self.load_players()
            self.save_players_to_file()

    def load_players(self):
        print("Loading player data...")
        fantasy_calc_df = FantasyCalcLoader.get_and_clean_data()
        sleeper_df = SleeperLoader.get_and_clean_data()
        self.load_pff_projections()
        injury_df = InjuryDataLoader.get_and_clean_data()

        for df in [fantasy_calc_df, sleeper_df, self.pff_projections, injury_df]:
            if 'full_name' in df.columns:
                df['full_name'] = df['full_name'].apply(Player.clean_name)
            if 'first_name' in df.columns:
                df['first_name'] = df['first_name'].apply(Player.clean_name)
            if 'last_name' in df.columns:
                df['last_name'] = df['last_name'].apply(Player.clean_name)

        final_df = DataMerger.merge_data(fantasy_calc_df, sleeper_df, self.pff_projections, injury_df)

        self.load_sleeper_players()

        self.enriched_players = []
        for _, row in final_df.iterrows():
            player_data = row.to_dict()
            
            # Ensure position is a valid string before creating Player object
            if 'position' not in player_data or not isinstance(player_data['position'], str) or player_data['position'] in ['0', 'UNKNOWN']:
                player_data['position'] = 'UNKNOWN'
            
            player = Player(player_data)
            player.normalize_injury_probability()
            player.initialize_st_scorer(self.special_team_scorer)
            self.enriched_players.append(player)

    

        print(f"Total players loaded: {len(self.enriched_players)}")
        self.search_name_to_player = {Player.clean_name(p.full_name): p for p in self.enriched_players}

    def save_players_to_file(self):
        os.makedirs(os.path.dirname(self.players_file), exist_ok=True)
        with open(self.players_file, 'w', encoding='utf-8') as file:
            player_data = []
            for player in self.enriched_players:
                player_dict = self.to_serializable(player.to_dict())
                player_data.append(player_dict)
            json.dump(player_data, file, ensure_ascii=False, indent=4)
        print(f"Player data saved to {self.players_file}")
        
    def load_pff_projections(self):
        pff_loader = PFFLoader()
        self.pff_projections = pff_loader.get_and_clean_data()
        # print(self.pff_projections.columns)
        
        


    def load_player(self, sleeper_id):
        self.ensure_players_loaded()
        
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        
        # print(f"Player not found with sleeper_id: {sleeper_id}")
        return None
    
    
    
    def get_player(self, sleeper_id):
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        return None
        
            
    def ensure_players_loaded(self):
        if not self.enriched_players:
            self.load_players_from_file()
            
    def load_and_update_pff_data(self):
        print("Loading and updating PFF and injury data...")
        self.load_pff_projections()
        injury_df = InjuryDataLoader.get_and_clean_data()
        
        for player in self.enriched_players:
            # Update PFF data
            pff_row = self.pff_projections[
                (self.pff_projections['playerName'].str.lower() == player.full_name.lower())
            ]
            if not pff_row.empty:
                pff_data = pff_row.iloc[0].to_dict()
                player.update_pff_projections(pff_data)
                # print(f"DEBUG: PFF data assigned to {player.full_name} ({player.position})")
            else:
                # print(f"DEBUG: No PFF data found for {player.full_name} ({player.position})")
                pass
            
            # Update injury data
            injury_key = Player.clean_name(player.full_name)
            if injury_key in injury_df.index:
                injury_data = injury_df.loc[injury_key].to_dict()
                player.update_injury_data(injury_data)
                # print(f"DEBUG: Injury data assigned to {player.full_name}")
            else:
                # print(f"DEBUG: No injury data found for {player.full_name}")
                pass
        
        self.save_players_to_file()
                
    def update_with_sleeper_data(self):
        sleeper_loader = SleeperLoader()
        sleeper_df = sleeper_loader.get_and_clean_data()
        
        players_updated = 0
        for player in self.enriched_players:
            sleeper_data = sleeper_df[sleeper_df['player_id'] == player.sleeper_id]
            if not sleeper_data.empty:
                sleeper_row = sleeper_data.iloc[0]
                if pd.isna(player.age) and not pd.isna(sleeper_row['age']):
                    player.age = sleeper_row['age']
                if player.position == 'UNKNOWN' and not pd.isna(sleeper_row['position']):
                    player.position = sleeper_row['position']
                if pd.isna(player.team) and not pd.isna(sleeper_row['team']):
                    player.team = sleeper_row['team']
                # Add any other fields you want to update from Sleeper
                players_updated += 1
        
        print(f"Updated {players_updated} players with Sleeper data")
        
        
    # def apply_default_injury_values(self):
    #     default_values = {
    #         'injury_risk': 'Medium',
    #         'durability': 5,
    #         'injury_probability_season': 10,  # 10% chance per season
    #         'projected_games_missed': 1.5,
    #         'injury_probability_game':   # Approx. 10% chance per season (10 / 17 weeks)
    #     }
        
    #     for player in self.enriched_players:
    #         if player.injury_risk == 'Unknown':
    #             player.update_injury_data(default_values)
                
                
    def to_serializable(self, obj):
        if isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        elif isinstance(obj, dict):
            return {k: self.to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.to_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return self.to_serializable(obj.__dict__)
        else:
            return str(obj)