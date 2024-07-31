import requests
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import csv
from custom_dataclasses.player import Player
from functools import reduce
import ssl
from fuzzywuzzy import process

import numpy as np
ssl._create_default_https_context = ssl._create_unverified_context


class PlayerLoader:
    def __init__(self):
        self.players_file = 'datarepo/players.json'
        self.refresh_interval = timedelta(days=3)
        self.enriched_players = []
        
        
        self.desired_from_fantasycalcapi = [
            "sleeperID",
            "name",
            "value",
            "redraft_value",
            "position"
        ]
        
        self.desired_pff_projections = [
            "fantasyPointsRank",
            "playerName",
            "teamName",
            "position",
            "byeWeek",
            "games",
            "fantasyPoints",
            "auctionValue",
            "passComp",
            "passAtt",
            "passYds",
            "passTd",
            "passInt",
            "passSacked",
            "rushAtt",
            "rushYds",
            "rushTd",
            "recvTargets",
            "recvReceptions",
            "recvYds",
            "recvTd",
            "fumbles",
            "fumblesLost",
            "twoPt",
            "returnYds",
            "returnTd",
        ]

        self.sleeper_desired_columns = [
            "full_name",
            "position",
            "team",
            "age",
            "years_exp",
            "college",
            "sleeper_id",  # Changed from "player_id" to "sleeper_id"
            "depth_chart_order",
            "injury_status",
            "weight",
            "height"
        ]
        
        self.load_players()

    def get_and_clean_fantasy_calc_api(self):
        response = requests.get("https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=10&ppr=1")
        if response.status_code == 200:
            data = response.json()
            cleaned_data = []
            for player_info in data:
                cleaned_player = {
                    "sleeper_id": player_info['player'].get('sleeperId'),
                    "name": player_info['player'].get('name'),
                    "value_1qb": player_info.get('value'),
                    "redraft_value": player_info.get('redraftValue'),
                    "position": player_info['player'].get('position'),
                    "team": player_info['player'].get('maybeTeam'),
                    "age": player_info['player'].get('maybeAge')
                }
                cleaned_data.append(cleaned_player)
            df = pd.DataFrame(cleaned_data)
            # print(f"FantasyCalc data fetched and cleaned for {len(df)} players.")
            # print(f"Columns in FantasyCalc data: {df.columns.tolist()}")  # Debug statement
            print(f"FantasyCalc data...\n")
            return df
            
        else:
            print(f"Failed to fetch FantasyCalc data: HTTP {response.status_code}")
            return pd.DataFrame()

    def get_and_clean_sleeper_data(self):
        with open('sleeper_players.json', 'r') as file:
            sleeper_data = json.load(file)
        
        cleaned_data = []
        for player in sleeper_data:
            if player.get('active', False):
                cleaned_player = {
                    'player_id': player.get('player_id'),
                    'first_name': player.get('first_name'),
                    'last_name': player.get('last_name'),
                    'full_name': player.get('full_name'),
                    'position': player.get('position'),
                    'team': player.get('team'),
                    'age': player.get('age'),
                    'years_exp': player.get('years_exp'),
                    'college': player.get('college'),
                    'depth_chart_order': player.get('depth_chart_order'),
                    'injury_status': player.get('injury_status'),
                    'weight': player.get('weight'),
                    'height': player.get('height'),
                    'number': player.get('number'),
                    'status': player.get('status'),
                    'birth_date': player.get('birth_date')
                }
                cleaned_data.append(cleaned_player)
        
        df = pd.DataFrame(cleaned_data)
        # print(f"Sleeper data cleaned for {len(df)} active players.")
        # print(f"Columns in Sleeper data: {df.columns.tolist()}")  # Debug statement
        print(f"Sleeper data...\n")
        return df
        

    def get_and_clean_pff_projections(self):
        df = pd.read_csv('datarepo/PFFProjections/24PFFProjections.csv')
        df = df[self.desired_pff_projections]
        df['playerName'] = df['playerName'].str.lower()
        # print(f"PFF projections cleaned for {len(df)} players.")
        print(f"PFF Projections...\n")
        return df
    
    def load_injury_data(self):
        csv_file_path = 'datarepo/Special/combined_injury_risk_data.csv'
        try:
            injury_df = pd.read_csv(csv_file_path)
            injury_df.columns = injury_df.columns.str.strip().str.lower().str.replace(' ', '_')
            print(f"Injury data...\n")
            return injury_df
        except FileNotFoundError:
            print(f"Injury data file not found: {csv_file_path}")
            return pd.DataFrame()
        
    def merge_player_data(self):
        fantasy_calc_df = self.get_and_clean_fantasy_calc_api()
        sleeper_df = self.get_and_clean_sleeper_data()
        pff_df = self.get_and_clean_pff_projections()
        injury_df = self.load_injury_data()

        # Print heads and shapes of all DataFrames
        print("\nFantasyCalc DataFrame:")
        print(fantasy_calc_df.head())
        print(f"Shape: {fantasy_calc_df.shape}")

        print("\nSleeper DataFrame:")
        print(sleeper_df.head())
        print(f"Shape: {sleeper_df.shape}")

        print("\nPFF DataFrame:")
        print(pff_df.head())
        print(f"Shape: {pff_df.shape}")

        print("\nInjury DataFrame:")
        print(injury_df.head())
        print(f"Shape: {injury_df.shape}")

        # Merge FantasyCalc and Sleeper data
        merged_df = pd.merge(fantasy_calc_df, sleeper_df, left_on='sleeper_id', right_on='player_id', how='outer', suffixes=('_fc', '_sl'))
        
        print("\nMerged DataFrame (FantasyCalc + Sleeper):")
        print(merged_df.head())
        print(f"Shape: {merged_df.shape}")

        # Ensure team column exists and is filled correctly
        if 'team_fc' in merged_df.columns and 'team_sl' in merged_df.columns:
            merged_df['team'] = merged_df['team_fc'].fillna(merged_df['team_sl'])
        elif 'team_fc' in merged_df.columns:
            merged_df['team'] = merged_df['team_fc']
        elif 'team_sl' in merged_df.columns:
            merged_df['team'] = merged_df['team_sl']
        else:
            print("Warning: No team data found in FantasyCalc or Sleeper data")
            merged_df['team'] = 'Unknown'
        
        merged_df = merged_df.drop(columns=['team_fc', 'team_sl'], errors='ignore')
        
        # Prepare for merging with PFF data
        merged_df['name_lower'] = merged_df['full_name'].str.lower()
        pff_df['playerName'] = pff_df['playerName'].str.lower()
        
        final_df = pd.merge(merged_df, pff_df, left_on='name_lower', right_on='playerName', how='left', suffixes=('', '_pff'))
        
        print("\nFinal DataFrame (after merging with PFF):")
        print(final_df.head())
        print(f"Shape: {final_df.shape}")
        
        if 'position_pff' in final_df.columns:
            final_df['position'] = final_df['position'].fillna(final_df['position_pff'])
            final_df.drop('position_pff', axis=1, inplace=True)
        
        # Prepare for merging with injury data
        injury_df['player_lower'] = injury_df['player'].str.lower().str.strip()
        final_df['name_lower'] = final_df['name'].str.lower().str.strip()
        
        # Function to find the best match
        def find_best_match(name, choices, cutoff=80):
            if pd.isna(name):
                return None
            best_match = process.extractOne(name, choices)
            return best_match[0] if best_match and best_match[1] >= cutoff else None

        # Create a dictionary of injury data
        injury_dict = injury_df.set_index('player_lower').to_dict('index')
        
        # Function to get injury data
        def get_injury_data(row):
            name = row['name_lower']
            position = row['position'].upper() if pd.notna(row['position']) else ''
            
            if pd.isna(name):
                return pd.Series({col: np.nan for col in injury_df.columns if col != 'player_lower'})
            
            # Try exact match first
            if name in injury_dict and injury_dict[name]['position'].upper() == position:
                return pd.Series({col: injury_dict[name].get(col, np.nan) for col in injury_df.columns if col != 'player_lower'})
            
            # If no exact match, try fuzzy matching
            best_match = find_best_match(name, injury_dict.keys())
            if best_match and injury_dict[best_match]['position'].upper() == position:
                return pd.Series({col: injury_dict[best_match].get(col, np.nan) for col in injury_df.columns if col != 'player_lower'})
            
            # If still no match, return NaN
            return pd.Series({col: np.nan for col in injury_df.columns if col != 'player_lower'})

        # Apply the function to merge injury data
        injury_columns = [col for col in injury_df.columns if col != 'player_lower']
        injury_data = final_df.apply(get_injury_data, axis=1)
        final_df = pd.concat([final_df, injury_data], axis=1)

        # Print debugging information
        print("\nPlayers with injury data:")
        print(final_df[final_df['probability_of_injury_per_game'].notnull()][['name', 'position', 'probability_of_injury_per_game']])
        
        print("\nPlayers without injury data (sample):")
        print(final_df[final_df['probability_of_injury_per_game'].isnull()][['name', 'position']].head(20))

        # Fill NaN values
        injury_columns = ['career_injuries', 'injury_risk', 'probability_of_injury_in_the_season', 
                        'projected_games_missed', 'probability_of_injury_per_game', 'durability']
        for col in final_df.columns:
            if col in injury_columns:
                if pd.api.types.is_object_dtype(final_df[col]):
                    final_df[col] = final_df[col].fillna('Unknown')
                else:
                    final_df[col] = final_df[col].fillna(0)
            else:
                if pd.api.types.is_object_dtype(final_df[col]):
                    final_df[col] = final_df[col].fillna('')
                else:
                    final_df[col] = final_df[col].fillna(0)
        
        final_df['byeWeek'] = final_df['byeWeek'].replace({0: None})
        final_df['sleeper_id'] = final_df['sleeper_id'].fillna(final_df['player_id'])
        
        # Print final debugging information
        print("\nFinal DataFrame (after cleaning):")
        print(final_df[['name', 'position', 'team', 'probability_of_injury_per_game']].head())
        print(f"Shape: {final_df.shape}")

        return final_df
                                          
                                          
    def get_player(self, sleeper_id):
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        return None
    
    def load_players(self):
        final_df = self.merge_player_data()
        for index, row in final_df.iterrows():
            player_data = row.to_dict()
            player = Player(player_data)
            self.enriched_players.append(player)
        # print(f"Total players loaded: {len(self.enriched_players)}")
        print(f"Players...")

    def load_players_from_file(self):
        if os.path.exists(self.players_file) and datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.players_file)) <= self.refresh_interval:
            print(f"Loading players from file: {self.players_file}")
            with open(self.players_file, 'r') as file:
                player_data = json.load(file)
            self.enriched_players = [Player(data) for data in player_data]
            print(f"Loaded {len(self.enriched_players)} players from file.")
        else:
            print("Player data file not found or outdated. Fetching new data...")
            self.load_players()
            self.save_players_to_file()

    def save_players_to_file(self):
        os.makedirs(os.path.dirname(self.players_file), exist_ok=True)
        with open(self.players_file, 'w', encoding='utf-8') as file:
            json.dump([player.to_dict() for player in self.enriched_players], file, ensure_ascii=False, indent=4)
        print(f"Player data saved to {self.players_file}")

    def load_player(self, sleeper_id):
        if not self.enriched_players:
            self.load_players_from_file()
        
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        print(f"Player not found with sleeper_id: {sleeper_id}")
        return None

    def ensure_players_loaded(self):
        if not self.enriched_players:
            self.load_players_from_file()