import requests
import json
import os
from datetime import datetime, timedelta
import requests
import json
import os
import pandas as pd
from datetime import datetime, timedelta

class PlayerLoader:
    def __init__(self):
        self.players_file = 'players.json'
        self.csv_file = 'player_data.csv'  # Local storage for CSV data
        self.players = {}
        self.refresh_interval = timedelta(days=7)
        self.player_ids_csv_url = "https://github.com/dynastyprocess/data/raw/master/files/db_playerids.csv"
        self.player_values_csv_url = "https://github.com/dynastyprocess/data/raw/master/files/values-players.csv"
        self.load_players()

    def download_and_parse_csv(self, csv_url, index_col=None):
        df = pd.read_csv(csv_url)
        if index_col:
            df.set_index(index_col, inplace=True)
        return df.T.to_dict('dict')

    def load_players(self):
        """Loads players from the local file or fetches from the API if the file is outdated or doesn't exist. Also handles CSV data."""
        need_to_update = False
        if os.path.exists(self.players_file):
            file_mod_time = datetime.fromtimestamp(os.path.getmtime(self.players_file))
            if datetime.now() - file_mod_time > self.refresh_interval:  # File is outdated
                need_to_update = True
        else:
            need_to_update = True

        if need_to_update:
            print("Player data is outdated, fetching new data.")
            self.fetch_players()
            self.csv_data = self.download_and_parse_csv(self.player_ids_csv_url)
            self.values_data = self.download_and_parse_csv(self.player_values_csv_url, index_col='fp_id')
        else:
            self.load_players_from_file()

    def fetch_players(self):
        """Fetches all players from the Sleeper API and merges them with data from both CSVs."""
        url = "https://api.sleeper.app/v1/players/nfl"
        response = requests.get(url)
        if response.status_code == 200:
            sleeper_players = response.json()
            # Assuming CSV data is already loaded in self.csv_data and self.values_data
            for player_id, details in sleeper_players.items():
                # Merge with player IDs CSV data
                if player_id in self.csv_data:
                    details.update(self.csv_data[player_id])
                # Merge with player values CSV data using fantasypros_id (fp_id) as the link
                fp_id = details.get('fantasypros_id')
                if fp_id and fp_id in self.values_data:
                    details.update(self.values_data[fp_id])
            self.players = sleeper_players
            self.save_players_to_file()
        else:
            raise Exception(f"Failed to fetch players data: HTTP {response.status_code}")

    def save_players_to_file(self):
        """Saves the current players dictionary to a file."""
        with open(self.players_file, 'w') as file:
            json.dump(self.players, file)

    def load_players_from_file(self):
        """Loads the players dictionary from a file."""
        with open(self.players_file, 'r') as file:
            self.players = json.load(file)

    def get_player(self, player_id):
        """Gets a single player's details by ID."""
        return self.players.get(player_id, None)



def download_and_parse_csv(csv_url):
    df = pd.read_csv(csv_url)
    # Convert DataFrame to a dictionary where the key is the 'sleeper_id' and the value is the rest of the player data
    players_dict = df.set_index('sleeper_id').T.to_dict('dict')
    return players_dict
