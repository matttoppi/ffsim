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



import os
from datetime import datetime, timedelta
import json
from custom_dataclasses.player import Player
class PlayerLoader:
    def __init__(self, print_projections=False):
        self.players_file = 'datarepo/players.json'
        self.refresh_interval = timedelta(days=3)
        self.enriched_players = []
        self.search_name_to_player = {}
        self.pff_projections = None
        
        # 
        self.print_projections = print_projections

    def load_pff_projections(self):
        pff_loader = PFFLoader()
        self.pff_projections = pff_loader.get_and_clean_data()
        print(f"Loaded PFF projections: {len(self.pff_projections)} rows")  # Add this line for debugging

    def load_players(self):
        print("Loading player data...")
        fantasy_calc_df = FantasyCalcLoader.get_and_clean_data()
        sleeper_df = SleeperLoader.get_and_clean_data()
        self.load_pff_projections()
        injury_df = InjuryDataLoader.get_and_clean_data()

        # Clean names in all dataframes
        for df in [fantasy_calc_df, sleeper_df, self.pff_projections, injury_df]:
            if 'full_name' in df.columns:
                df['full_name'] = df['full_name'].apply(Player.clean_name)
            if 'first_name' in df.columns:
                df['first_name'] = df['first_name'].apply(Player.clean_name)
            if 'last_name' in df.columns:
                df['last_name'] = df['last_name'].apply(Player.clean_name)

        final_df = DataMerger.merge_data(fantasy_calc_df, sleeper_df, self.pff_projections, injury_df)

        self.load_sleeper_players()

        for _, row in final_df.iterrows():
            player_data = row.to_dict()
            
            # Extract PFF projections
            pff_columns = [col for col in row.index if col.startswith('pff_')]
            pff_data = {col.replace('pff_', ''): row[col] for col in pff_columns}
            player_data['pff_projections'] = pff_data

            player = Player(player_data)
            self.enriched_players.append(player)

        print(f"Total players loaded: {len(self.enriched_players)}")

    def load_player(self, sleeper_id):
        self.ensure_players_loaded()
        
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        
        print(f"Player not found with sleeper_id: {sleeper_id}")
        return None
    
    
    
    def get_player(self, sleeper_id):
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        return None

    def save_players_to_file(self):
        os.makedirs(os.path.dirname(self.players_file), exist_ok=True)
        with open(self.players_file, 'w', encoding='utf-8') as file:
            player_data = []
            for player in self.enriched_players:
                player_dict = player.to_dict()
                if player.pff_projections:
                    player_dict['pff_projections'] = player.pff_projections.__dict__
                player_data.append(player_dict)
            json.dump(player_data, file, ensure_ascii=False, indent=4)
        print(f"Player data saved to {self.players_file}")
            
    def load_sleeper_players(self):
        try:
            with open('sleeper_players.json', 'r') as f:
                players_list = json.load(f)
                self.sleeper_players = {
                    str(player['player_id']): player for player in players_list
                    if 'player_id' in player and player.get('active', False)
                }
                # Create a search_full_name-based lookup
                self.search_name_to_player = {
                    player['search_full_name']: player
                    for player in players_list if 'search_full_name' in player
                }
            print(f"Loaded {len(self.sleeper_players)} active players from sleeper_players.json")
        except FileNotFoundError:
            print("sleeper_players.json not found. Player position lookup will not be available.")
            self.sleeper_players = {}
            self.search_name_to_player = {}
        except json.JSONDecodeError:
            print("Error decoding sleeper_players.json. Please check if the file is valid JSON.")
            self.sleeper_players = {}
            self.search_name_to_player = {}
            
            
            
            
            
    def ensure_players_loaded(self):
        if not self.enriched_players:
            self.load_players_from_file()

    def load_players_from_file(self):
        if os.path.exists(self.players_file) and datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.players_file)) <= self.refresh_interval:
            print(f"Loading players from file: {self.players_file}")
            with open(self.players_file, 'r') as file:
                player_data = json.load(file)
            self.enriched_players = []
            for data in player_data:
                pff_data = data.get('pff_projections', {})
                data['pff_projections'] = PFFProjections(pff_data) if pff_data else None
                player = Player(data)
                self.enriched_players.append(player)
            self.search_name_to_player = {Player.clean_name(p.full_name): p for p in self.enriched_players}
            print(f"Loaded {len(self.enriched_players)} players from file.")
            
            # Load and update PFF and injury data
            self.load_and_update_pff_data()
            
            # Update with Sleeper data
            self.update_with_sleeper_data()
            
            # Apply default values to players with no injury data
            self.apply_default_injury_values()
        else:
            print("Player data file not found or outdated. Fetching new data...")
            self.load_players()
            self.save_players_to_file()
            
    def load_and_update_pff_data(self):
        print("Loading and updating PFF and injury data...")
        self.load_pff_projections()
        injury_df = InjuryDataLoader.get_and_clean_data()
        
        # Create dictionaries for quick player lookup
        player_dict = {Player.clean_name(p.full_name): p for p in self.enriched_players}
        injury_dict = {Player.clean_name(row['player']): row.to_dict() for _, row in injury_df.iterrows()}
        
        players_updated = 0
        for player_name, player in player_dict.items():
            # Update PFF data
            pff_row = self.pff_projections[self.pff_projections['playerName'] == player_name]
            if not pff_row.empty:
                player.update_pff_projections(pff_row.iloc[0].to_dict())
            
            # Update injury data
            if player_name in injury_dict:
                player.update_injury_data(injury_dict[player_name])
            
            players_updated += 1
        
        print(f"Updated PFF and injury data for {players_updated} players")
  
        
    def update_with_sleeper_data(self):
        print("Updating players with Sleeper data...")
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
        
        
    def apply_default_injury_values(self):
        default_values = {
            'injury_risk': 'Medium',
            'durability': 5,
            'injury_probability_season': 0.1,
            'projected_games_missed': 1,
            'injury_probability_game': 0.08
        }
        
        for player in self.enriched_players:
            if player.injury_risk == 'Unknown':
                player.update_injury_data(default_values)