import requests
import json
import os
from datetime import datetime, timedelta
import requests
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from player import Player
import numpy as np
from functools import reduce

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import requests
import pandas as pd
from datetime import datetime, timedelta
from player import Player

class PlayerLoader:
    def __init__(self):
        self.players_file = 'datarepo/players.json'
        self.refresh_interval = timedelta(days=3)
        self.player_ids_csv_url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
        self.player_values_csv_url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
        self.sleeper_api_url = "https://api.sleeper.app/v1/players/nfl"

        # Download and parse CSVs with the correct indexing
        self.id_mapping = self.download_and_parse_csv(self.player_ids_csv_url, index_col='fantasypros_id')
        self.values_data = self.download_and_parse_csv(self.player_values_csv_url, index_col='fp_id')
        
        # Fetch sleeper data into a dataframe
        self.sleeper_players = pd.DataFrame(self.fetch_sleeper_data())
        self.load_players()

    def download_and_parse_csv(self, csv_url, index_col=None):
        df = pd.read_csv(csv_url, index_col=index_col)
        
        # Drop duplicates, keeping the first occurrence
        df = df[~df.index.duplicated(keep='first')]
        
        return df.to_dict('index')

    def fetch_sleeper_data(self):
        response = requests.get(self.sleeper_api_url)
        if response.status_code == 200:
            data = response.json()
            # Convert the data into a list of dictionaries, including the player_id
            players_data = []
            for player_id, player_info in data.items():
                player_info['player_id'] = player_id  # Add player_id to the dictionary
                players_data.append(player_info)
                
            #write to file
            with open('sleeper_players.json', 'w', encoding='utf-8') as file:
                json.dump(players_data, file, ensure_ascii=False, indent=4)
            
            return players_data
        else:
            print(f"Failed to fetch Sleeper data: HTTP {response.status_code}")
            return []


    def load_players(self):
        print(f"\nLoading players...")
        if os.path.exists(self.players_file) and datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.players_file)) <= self.refresh_interval:
            print(f"\nPlayer data is up to date. Loading from {self.players_file}\n")
            self.load_players_from_file()
            self.load_statistics_from_file()  # Existing call to load stats
            self.load_player_statistics()  # New call to load and attach player statistics
        else:
            print("Player data is outdated, fetching new data.\n")
            self.fetch_players()
            self.load_player_statistics()  # Ensure stats are loaded for newly fetched players too


    def fetch_players(self):
        enriched_players = self.enrich_players_data()
        self.save_players_to_file(enriched_players)

    def enrich_players_data(self):
        enriched_players = []
        if 'player_id' not in self.sleeper_players.columns:
            print("The 'player_id' column is missing from the sleeper_players DataFrame.")
            return enriched_players

        for fp_id, player_values in self.values_data.items():
            # Ensure sleeper_id exists and matches
            sleeper_id = self.id_mapping.get(fp_id, {}).get('sleeper_id')
            if sleeper_id is None:
                continue  # Skip if there's no corresponding sleeper_id

            sleeper_id_str = str(sleeper_id).replace('.0', '')
            if sleeper_id_str not in self.sleeper_players['player_id'].values:
                continue  # Skip if there's no data in sleeper_players for this sleeper_id

            # Fetch data, combine dictionaries, and create Player instance
            sleeper_player_dict = self.sleeper_players[self.sleeper_players['player_id'] == sleeper_id_str].iloc[0].to_dict()
            combined_dict = {**sleeper_player_dict, **player_values, **self.id_mapping[fp_id]}
            player = Player(combined_dict)
            enriched_players.append(player.to_dict())

        return enriched_players

    def save_players_to_file(self, players_data):
        with open(self.players_file, 'w', encoding='utf-8') as file:
            json.dump(players_data, file, ensure_ascii=False, indent=4)
            print("Player data saved successfully.\n")

    def load_players_from_file(self):
        with open(self.players_file, 'r') as file:
            self.enriched_players = json.load(file)
            
            
    def load_player(self, sleeper_id):
        
        for player in self.enriched_players:
            if player.get('sleeper_id') == sleeper_id or str(player.get('sleeper_id')).replace('.0', '') == sleeper_id:
                # print(f"Player found: {player.get('first_name')} {player.get('last_name')}")
                return Player(player)
            
        # print(f"Player not found with sleeper_id: {sleeper_id}")
        
        # search for it in the sleeper data file sleeper_players.json
        with open('sleeper_players.json', 'r') as file:
            sleeper_players = json.load(file)
            for player in sleeper_players:
                if player.get('player_id') == sleeper_id or str(player.get('player_id')).replace('.0', '') == sleeper_id:
                    # print(f"Player found: {player.get('first_name')} {player.get('last_name')}")
                    return Player(player)
        
        return None
    
    
    def load_player_statistics(self, season='2023'):
        stats_df = pd.read_csv('datarepo/merged_nfl_players_stats.csv')
        # Filter for the 2023 season
        stats_df_2023 = stats_df[stats_df['Season'] == season]
        
        for _, row in stats_df_2023.iterrows():
            player_name = row['Player']  # Assuming 'Player' column holds the name
            if player_name in [player['name'] for player in self.enriched_players]:  # Adjust based on your data structure
                # Find the player and add or update their 2023 stats
                for player in self.enriched_players:
                    if player['name'] == player_name:  # Adjust the key based on your player data structure
                        player_object = self.load_player(player['sleeper_id'])  # Adjust based on how you instantiate Player objects
                        player_object.add_season_stats(season, row.to_dict())

    
    def load_statistics_from_file(self):

        

        # Define renaming schemas to address overlapping columns
        # Note: These are hypothetical and need to be adjusted according to your actual datasets' specifics
        rename_schema_general = {
            'YDS': 'GENERAL_YDS',  # Example for general yard stats, adjust based on context
            'TD': 'GENERAL_TD',    # Adjust similarly
        }

        rename_schema_qb = {
            'ATT': 'PASS_ATT',
            'YDS': 'PASS_YDS',
            'TD': 'PASS_TD'
        }

        rename_schema_rb_wr_te = {
            'ATT': 'RUSH_ATT',
            'YDS': 'RUSH_RECEIVE_YDS',  # Adjust if there's a need to distinguish between rushing and receiving yards
            'TD': 'RUSH_RECEIVE_TD'
        }

        rename_schema_advanced = {
            # Advanced stats might overlap with general stats but need specific distinction
            'YDS': 'ADV_YDS',
            'TD': 'ADV_TD'
        }

        rename_schema_target_leaders = {
            'TGT': 'TARGETS',
            'YDS': 'TARGET_YDS',
            'REC': 'RECEPTIONS'
        }

        # Function to load and rename columns for clarity
        # Function to load, normalize player names, and rename columns for clarity
        def load_and_rename(filepath, rename_schema, season=None):
            df = pd.read_csv(filepath)
            
            # Normalize 'Player' names to ensure consistency
            if 'Player' in df.columns:
                df['Player'] = df['Player'].apply(normalize_player_name)
            
            # Add or reinforce the 'Season' column if a season is provided
            if season is not None:
                df['Season'] = season

            df.rename(columns=rename_schema, inplace=True)
            return df


        
        
        def normalize_player_name(name):
            # Check if name is a string instance before attempting to process it
            if isinstance(name, str):
                if '(' in name:
                    # Remove team info and extra spaces
                    name = name.split(' (')[0].strip()
            return name


        # Actual dataset paths
        filepaths = [
            'datarepo/23QB.csv',
            'datarepo/23RB.csv',
            'datarepo/23WR.csv',
            'datarepo/23TE.csv',
            'datarepo/23QBadvanced.csv',
            'datarepo/23RBadvanced.csv',
            'datarepo/23WRadvanced.csv',
            'datarepo/23TEadvanced.csv',
            'datarepo/23TargetLeaders.csv'
        ]

        # Renaming schemas for each dataset type
        schemas = [
            rename_schema_qb,
            rename_schema_rb_wr_te,
            rename_schema_rb_wr_te,
            rename_schema_rb_wr_te,
            rename_schema_advanced,
            rename_schema_advanced,
            rename_schema_advanced,
            rename_schema_advanced,
            rename_schema_target_leaders
        ]

            
        def resolve_duplicates(combined_df):
            # Identify all columns that have been duplicated with '_x' and '_y' suffixes
            duplicated_cols = [col[:-2] for col in combined_df if col.endswith('_x')]
            
            for col in duplicated_cols:
                col_x = f'{col}_x'
                col_y = f'{col}_y'
                
                # Check if both versions of the column exist
                if col_x in combined_df and col_y in combined_df:
                    # Combine columns by prioritizing '_x' values but falling back to '_y' where '_x' is NaN
                    combined_df[col] = combined_df[col_x].combine_first(combined_df[col_y])
                    
                    # Drop the now redundant '_x' and '_y' columns
                    combined_df.drop(columns=[col_x, col_y], inplace=True)
                elif col_x in combined_df:
                    # If only '_x' version exists, rename it to the original column name
                    combined_df.rename(columns={col_x: col}, inplace=True)
                elif col_y in combined_df:
                    # If only '_y' version exists, rename it to the original column name
                    combined_df.rename(columns={col_y: col}, inplace=True)
                    
            return combined_df


        # Load, rename, and store all datasets in a list
        dfs = [load_and_rename(fp, schema) for fp, schema in zip(filepaths, schemas)]
        # Merge all DataFrames on 'Player', using an outer join
        combined_df = reduce(lambda left, right: resolve_duplicates(pd.merge(left, right, on='Player', how='outer', suffixes=('_x', '_y'))), dfs)

        # Remove rows where all columns are NaN
        combined_df.dropna(how='all', inplace=True)

        # Save the merged DataFrame
        combined_df.to_csv('merged_nfl_players_stats.csv', index=False)

        print("Merging complete. The dataset is saved as 'datarepo/merged_nfl_players_stats.csv'.")

