import requests
import json
import os
from datetime import datetime, timedelta
import requests
import json
import os
import pandas as pd
from datetime import datetime, timedelta

import ssl
ssl._create_default_https_context = ssl._create_unverified_context



class PlayerLoader:
    def __init__(self):
        self.players_file = 'players.json'
        # Initialize csv_data and values_data here to ensure they always exist
        self.csv_data = {}
        self.values_data = {}
        self.players = {}
        self.refresh_interval = timedelta(days=7)
        self.player_ids_csv_url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
        self.player_values_csv_url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
        self.load_players()

    def load_players(self):
        """Loads players from the local file or fetches from the API if the file is outdated or doesn't exist. Also handles CSV data."""
        need_to_update = False
        if os.path.exists(self.players_file):
            file_mod_time = datetime.fromtimestamp(os.path.getmtime(self.players_file))
            if datetime.now() - file_mod_time > self.refresh_interval:
                need_to_update = True
        else:
            need_to_update = True

        self.csv_data = self.download_and_parse_csv(self.player_ids_csv_url)
        self.values_data = self.download_and_parse_csv(self.player_values_csv_url, index_col='fp_id')

        if need_to_update:
            print("Player data is outdated, fetching new data.")
            self.fetch_players()
        else:
            self.load_players_from_file()

    def fetch_players(self):
        url = "https://api.sleeper.app/v1/players/nfl"
        response = requests.get(url)
        if response.status_code == 200:
            sleeper_players = response.json()
            for player_id, details in sleeper_players.items():
                if player_id in self.csv_data:
                    details.update(self.csv_data[player_id])
                fp_id = details.get('fantasypros_id')
                if fp_id and fp_id in self.values_data:
                    details.update(self.values_data[fp_id])

            # Update self.players with the fetched and merged data
            self.players = sleeper_players

            # Now that self.players has been updated, save it to file
            self.save_players_to_file()
        else:
            print(f"Failed to fetch players data: HTTP {response.status_code}")


    def save_players_to_file(self):
        """Saves the current players dictionary to a file."""
        if not self.players:
            print("Warning: Attempting to save empty player data.")
        else:
            print(f"Saving {len(self.players)} players data to file...")
            try:
                with open(self.players_file, 'w', encoding='utf-8') as file:
                    json.dump(self.players, file, ensure_ascii=False, indent=4)
                    print(f"Player data saved to {self.players_file} successfully.")
            except Exception as e:
                print(f"Error saving players data to file: {e}")


    def load_players_from_file(self):
        """Loads the players dictionary from a file."""
        with open(self.players_file, 'r') as file:
            self.players = json.load(file)

    def get_player(self, player_id):
        """Gets a single player's details by ID."""
        return self.players.get(player_id, None)
    
    def download_and_parse_csv(self, csv_url, index_col=None):
        df = pd.read_csv(csv_url)
        if index_col:
            df.set_index(index_col, inplace=True)
        return df.T.to_dict('dict')



def download_and_parse_csv(csv_url):
    df = pd.read_csv(csv_url)
    # Convert DataFrame to a dictionary where the key is the 'sleeper_id' and the value is the rest of the player data
    players_dict = df.set_index('sleeper_id').T.to_dict('dict')
    return players_dict
