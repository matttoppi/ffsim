import requests
import json
import os
from datetime import datetime, timedelta
import requests
import json
import os
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
from functools import reduce
import csv

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import requests
import pandas as pd
from datetime import datetime, timedelta
from custom_dataclasses.player import Player

class PlayerLoader:

    def __init__(self):
        self.players_file = 'datarepo/players.json'
        self.refresh_interval = timedelta(days=3)
        self.player_ids_csv_url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
        self.player_values_csv_url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
        self.sleeper_api_url = "https://api.sleeper.app/v1/players/nfl"

        # Define renaming schemas
        self.rename_schema_qb = {
            'ATT': 'PASS_ATT',
            'YDS': 'PASS_YDS',
            'TD': 'PASS_TD'
        }
        self.rename_schema_rb_wr_te = {
            'ATT': 'RUSH_ATT',
            'YDS': 'RUSH_RECEIVE_YDS',
            'TD': 'RUSH_RECEIVE_TD'
        }
        self.rename_schema_advanced = {
            'YDS': 'ADV_YDS',
            'TD': 'ADV_TD'
        }
        self.rename_schema_target_leaders = {
            'TGT': 'TARGETS',
            'YDS': 'TARGET_YDS',
            'REC': 'RECEPTIONS'
        }

        # Define filepaths and schemas
        self.filepaths = [
            'datarepo/OLD/Traditional/23QB.csv',
            'datarepo/OLD/Traditional/23RB.csv',
            'datarepo/OLD/Traditional/23WR.csv',
            'datarepo/OLD/Traditional/23TE.csv',
            'datarepo/OLD/Advanced/23QBadvanced.csv',
            'datarepo/OLD/Advanced/23RBadvanced.csv',
            'datarepo/OLD/Advanced/23WRadvanced.csv',
            'datarepo/OLD/Advanced/23TEadvanced.csv',
            'datarepo/Special/23TargetLeaders.csv'
        ]
        self.schemas = [
            self.rename_schema_qb,
            self.rename_schema_rb_wr_te,
            self.rename_schema_rb_wr_te,
            self.rename_schema_rb_wr_te,
            self.rename_schema_advanced,
            self.rename_schema_advanced,
            self.rename_schema_advanced,
            self.rename_schema_advanced,
            self.rename_schema_target_leaders
        ]

        # Download and parse CSVs with the correct indexing
        self.id_mapping = self.download_and_parse_csv(self.player_ids_csv_url, index_col='fantasypros_id')
        self.values_data = self.download_and_parse_csv(self.player_values_csv_url, index_col='fp_id')
        
        # Fetch sleeper data into a dataframe
        self.sleeper_players = pd.DataFrame(self.fetch_sleeper_data())
        
        # Load PFF projections
        self.pff_projections = self.load_pff_projections('datarepo/PFFProjections/24PFFProjections.csv')
        
        self.load_players()

    @staticmethod
    def load_pff_projections(file_path):
        projections = {}
        with open(file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Print out the column names

            # print(reader.fieldnames)
            
            # Find the correct column name for player names
            name_column = next((col for col in reader.fieldnames if 'name' in col.lower()), None)
            
            if not name_column:
                print("Error: Could not find a column for player names in the PFF projections file.")
                return projections

            for row in reader:
                player_name = row[name_column]
                projections[player_name] = row
        
        print(f"Loaded {len(projections)} players from PFF projections.")
        return projections
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
        else:
            print("Player data is outdated, fetching new data.\n")
            self.fetch_players()
        
        self.load_statistics_from_file()  # Existing call to load stats
        self.load_player_statistics()  # New call to load and attach player statistics
    def update_pff_projections(self):
        pff_projections_lower = {name.lower(): proj for name, proj in self.pff_projections.items()}
        updated_count = 0
        
        for player in self.enriched_players:
            player_name = f"{player['first_name']} {player['last_name']}".lower()
            if player_name in pff_projections_lower:
                player['pff_projections'] = pff_projections_lower[player_name]
                updated_count += 1
        
        # print(f"Updated PFF projections for {updated_count} players.")

    def fetch_players(self):
        self.enriched_players = self.enrich_players_data()
        # self.save_players_to_file(self.enriched_players)
        print(f"Fetched and enriched {len(self.enriched_players)} players.")

    def enrich_players_data(self):
        enriched_players = []
        if 'player_id' not in self.sleeper_players.columns:
            print("The 'player_id' column is missing from the sleeper_players DataFrame.")
            return enriched_players
        
        fantasycalc_api_url = "https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=10&ppr=1"
        
        response = requests.get(fantasycalc_api_url)
        if response.status_code == 200:
            fantasy_calc_data = {player['player']['sleeperId']: player for player in response.json()}
            print(f"FantasyCalc data fetched successfully for {len(fantasy_calc_data)} players.")
        else:
            print(f"Failed to fetch FantasyCalc data: HTTP {response.status_code}")
            return enriched_players

        # Create a dictionary of PFF projections with lowercase names as keys
        pff_projections_lower = {name.lower(): proj for name, proj in self.pff_projections.items()}

        for _, sleeper_player in self.sleeper_players.iterrows():
            sleeper_id = str(sleeper_player['player_id'])
            
            if sleeper_id in fantasy_calc_data:
                fc_data = fantasy_calc_data[sleeper_id]
                
                # Prepare the combined dictionary
                combined_dict = sleeper_player.to_dict()
                combined_dict.update({
                    'value_1qb': fc_data['value'],
                    'value_2qb': fc_data.get('superflex_value', fc_data['value']),
                    'first_name': fc_data['player']['name'].split()[0],
                    'last_name': ' '.join(fc_data['player']['name'].split()[1:]),
                    'position': fc_data['player']['position'],
                    'team': fc_data['player']['maybeTeam'],
                    'age': fc_data['player']['maybeAge']
                })
                
                # Create Player instance
                player = Player(combined_dict)
                
                # Add PFF projections
                player_name = f"{player.first_name} {player.last_name}".lower()
                if player_name in pff_projections_lower:
                    # print(f"Adding PFF projections for {player.first_name} {player.last_name} - {pff_projections_lower[player_name]}")
                    player.add_pff_projections(pff_projections_lower[player_name])
                    
                else:
                    print(f"No PFF projections found for {player.first_name} {player.last_name}")
                
                # Add additional data from id_mapping if available
                fp_id = next((k for k, v in self.id_mapping.items() if str(v.get('sleeper_id')).replace('.0', '') == sleeper_id), None)
                if fp_id:
                    player.apply_id_mapping(self.id_mapping[fp_id])
                
                enriched_players.append(player.to_dict())
                print(f"Enriched player: {player.first_name} {player.last_name}, FantasyCalc value: {player.value_1qb}, PFF projections: {'Added' if player.pff_projections else 'Not found'}")

        print(f"Enriched {len(enriched_players)} players with FantasyCalc data.")
        print(f"Players with PFF projections: {sum(1 for p in enriched_players if p.get('pff_projections'))}")
        
        # Print a few examples of players with and without PFF projections
        with_pff = next((p for p in enriched_players if p.get('pff_projections')), None)
        without_pff = next((p for p in enriched_players if not p.get('pff_projections')), None)
        
        if with_pff:
            print(f"Example player with PFF projections: {with_pff['first_name']} {with_pff['last_name']}")
            print(f"PFF projections: {with_pff['pff_projections']}")
        
        if without_pff:
            print(f"Example player without PFF projections: {without_pff['first_name']} {without_pff['last_name']}")

        return enriched_players
    def save_players_to_file(self, players_data):
        with open(self.players_file, 'w', encoding='utf-8') as file:
            json.dump(players_data, file, ensure_ascii=False, indent=4)
            print("Player data saved successfully.\n")

    def load_players_from_file(self):
        with open(self.players_file, 'r') as file:
            self.enriched_players = json.load(file)
        print(f"Loaded {len(self.enriched_players)} players from file.")
            
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
        
        print(f"Loaded {len(stats_df)} player statistics.")
        
        # Strip whitespace from column names
        stats_df.columns = stats_df.columns.str.strip()
        
        updated_count = 0
        
        if not hasattr(self, 'enriched_players'):
            print("Warning: enriched_players not found. Initializing as empty list.")
            self.enriched_players = []

        for _, row in stats_df.iterrows():
            player_name = str(row['Player']).strip()  # Convert to string and remove whitespace
            
            # Iterate through all players in self.enriched_players
            for player in self.enriched_players:
                if player.get('full_name', '').strip() == player_name:
                    player_object = self.load_player(player.get('sleeper_id'))
                    
                    if player_object:
                        # Convert row to dict, handling potential NaN values
                        stats_dict = row.where(pd.notnull(row), None).to_dict()
                        
                        # Remove the 'Player' key from stats_dict as it's not a stat
                        stats_dict.pop('Player', None)
                        
                        player_object.add_season_stats(season, stats_dict)
                        updated_count += 1
                        break  # Stop searching once we've found a match

        print(f"Updated statistics for {updated_count} players.")
        
    def load_players_from_file(self):
        with open(self.players_file, 'r') as file:
            self.enriched_players = json.load(file)
        print(f"Loaded {len(self.enriched_players)} players from file.")
        
        # Reload PFF projections and update players
        pff_projections_lower = {name.lower(): proj for name, proj in self.pff_projections.items()}
        
        updated_count = 0
        for player in self.enriched_players:
            player_name = f"{player['first_name']} {player['last_name']}".lower()
            if player_name in pff_projections_lower:
                player['pff_projections'] = pff_projections_lower[player_name]
                updated_count += 1
        
        print(f"Updated PFF projections for {updated_count} players.")

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


        
        
    def normalize_player_name(self, name):
        if isinstance(name, str):
            if '(' in name:
                name = name.split(' (')[0].strip()
        return name

   
        
    def resolve_duplicates(self, combined_df):
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

    def load_statistics_from_file(self):
        def load_and_rename(filepath, rename_schema, season=None):
            df = pd.read_csv(filepath)
            
            if 'Player' in df.columns:
                df['Player'] = df['Player'].apply(self.normalize_player_name)
            
            if season is not None:
                df['Season'] = season

            df.rename(columns=rename_schema, inplace=True)
            return df

        # Load, rename, and store all datasets in a list
        dfs = [load_and_rename(fp, schema) for fp, schema in zip(self.filepaths, self.schemas)]
        
        # Merge all DataFrames on 'Player', using an outer join
        combined_df = reduce(lambda left, right: self.resolve_duplicates(pd.merge(left, right, on='Player', how='outer', suffixes=('_x', '_y'))), dfs)

        # Remove rows where all columns are NaN
        combined_df.dropna(how='all', inplace=True)

        # Save the merged DataFrame
        combined_df.to_csv('datarepo/merged_nfl_players_stats.csv', index=False)

        print("Merging complete. The dataset is saved as 'datarepo/merged_nfl_players_stats.csv'.")