import requests
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import csv
from custom_dataclasses.player import Player
from functools import reduce
import ssl
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
            print(f"FantasyCalc data fetched and cleaned for {len(df)} players.")
            print(f"Columns in FantasyCalc data: {df.columns.tolist()}")
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
        print(f"Sleeper data cleaned for {len(df)} active players.")
        print(f"Columns in Sleeper data: {df.columns.tolist()}")
        return df
        

    def get_and_clean_pff_projections(self):
        df = pd.read_csv('datarepo/PFFProjections/24PFFProjections.csv')
        df = df[self.desired_pff_projections]
        df['playerName'] = df['playerName'].str.lower()
        print(f"PFF projections cleaned for {len(df)} players.")
        return df

    def merge_player_data(self):
        fantasy_calc_df = self.get_and_clean_fantasy_calc_api()
        sleeper_df = self.get_and_clean_sleeper_data()
        pff_df = self.get_and_clean_pff_projections()

        # Merge FantasyCalc and Sleeper data
        merged_df = pd.merge(fantasy_calc_df, sleeper_df, left_on='sleeper_id', right_on='player_id', how='outer', suffixes=('_fc', '_sl'))
        
        # Ensure position column exists and is filled correctly
        if 'position_fc' in merged_df.columns and 'position_sl' in merged_df.columns:
            merged_df['position'] = merged_df['position_fc'].fillna(merged_df['position_sl'])
        elif 'position_fc' in merged_df.columns:
            merged_df['position'] = merged_df['position_fc']
        elif 'position_sl' in merged_df.columns:
            merged_df['position'] = merged_df['position_sl']
        else:
            print("Warning: No position data found in FantasyCalc or Sleeper data")
            merged_df['position'] = 'Unknown'
        
        # Drop the redundant position columns
        merged_df = merged_df.drop(columns=['position_fc', 'position_sl'], errors='ignore')
        
        # Prepare for merging with PFF data
        merged_df['name_lower'] = merged_df['full_name'].str.lower()
        pff_df['playerName'] = pff_df['playerName'].str.lower()
        
        final_df = pd.merge(merged_df, pff_df, left_on='name_lower', right_on='playerName', how='left', suffixes=('', '_pff'))
        
        # Ensure position is preserved after merging with PFF data
        if 'position_pff' in final_df.columns:
            final_df['position'] = final_df['position'].fillna(final_df['position_pff'])
            final_df.drop('position_pff', axis=1, inplace=True)
        
        final_df.drop(['name_lower', 'playerName'], axis=1, inplace=True)
        
        # Ensure 'name' column exists
        final_df['name'] = final_df['full_name'].fillna(final_df['name'])
        
        # Handle NaN values
        for col in final_df.columns:
            if final_df[col].dtype == 'object':
                final_df[col] = final_df[col].fillna('')
            else:
                final_df[col] = final_df[col].fillna(0)
        
        # Specifically handle byeWeek
        final_df['byeWeek'] = final_df['byeWeek'].replace({0: None})

        # Ensure sleeper_id is consistent
        final_df['sleeper_id'] = final_df['sleeper_id'].fillna(final_df['player_id'])

        print(f"Final merged dataframe contains {len(final_df)} players.")
        print(f"Columns in final dataframe: {final_df.columns.tolist()}")
        return final_df

    def get_player(self, sleeper_id):
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        return None
    
    def load_players(self):
        merged_data = self.merge_player_data()
        self.enriched_players = []

        for _, row in merged_data.iterrows():
            player_data = row.to_dict()
            player = Player(player_data)
            self.enriched_players.append(player)

        print(f"Loaded {len(self.enriched_players)} players.")

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