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

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import requests
import pandas as pd
from datetime import datetime, timedelta
from player import Player

class PlayerLoader:
    def __init__(self):
        self.players_file = 'players.json'
        self.refresh_interval = timedelta(days=7)
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
            
            return players_data
        else:
            print(f"Failed to fetch Sleeper data: HTTP {response.status_code}")
            return []


    def load_players(self):
        if os.path.exists(self.players_file) and datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.players_file)) <= self.refresh_interval:
            self.load_players_from_file()
        else:
            print("Player data is outdated, fetching new data.")
            self.fetch_players()

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
            print("Player data saved successfully.")

    def load_players_from_file(self):
        with open(self.players_file, 'r') as file:
            self.enriched_players = json.load(file)
            
