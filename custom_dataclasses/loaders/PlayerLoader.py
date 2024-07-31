import requests
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from fuzzywuzzy import process
from custom_dataclasses.player import Player
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
    def __init__(self):
        self.players_file = 'datarepo/players.json'
        self.refresh_interval = timedelta(days=3)
        self.enriched_players = []
        self.search_name_to_player = {}  # New dictionary for search_full_name lookups
        self.desired_pff_projections = [
            "fantasyPointsRank", "playerName", "teamName", "position", "byeWeek", "games",
            "fantasyPoints", "auctionValue", "passComp", "passAtt", "passYds", "passTd",
            "passInt", "passSacked", "rushAtt", "rushYds", "rushTd", "recvTargets",
            "recvReceptions", "recvYds", "recvTd", "fumbles", "fumblesLost", "twoPt",
            "returnYds", "returnTd",
        ]
        self.load_players()

    def load_players(self):
        fantasy_calc_df = FantasyCalcLoader.get_and_clean_data()
        sleeper_df = SleeperLoader.get_and_clean_data()
        pff_df = PFFLoader.get_and_clean_data(self.desired_pff_projections)
        injury_df = InjuryDataLoader.get_and_clean_data()

        final_df = DataMerger.merge_data(fantasy_calc_df, sleeper_df, pff_df, injury_df)

        self.load_sleeper_players()

        for _, row in final_df.iterrows():
            player_data = row.to_dict()
            sleeper_id = str(player_data['sleeper_id'])
            
            sleeper_player = self.sleeper_players.get(sleeper_id)
            if not sleeper_player or not sleeper_player.get('team'):
                # Try to find player by search_full_name if ID lookup fails or team is missing
                search_name = (player_data['first_name'] + player_data['last_name']).lower()
                sleeper_player = self.search_name_to_player.get(search_name)

            if sleeper_player:
                # Update player data with Sleeper information
                fantasy_positions = sleeper_player.get('fantasy_positions')
                if fantasy_positions is None:
                    fantasy_positions = []
                
                player_data['position'] = (sleeper_player.get('position') or 
                                        (fantasy_positions + ['UNKNOWN'])[0])
                player_data['team'] = sleeper_player.get('team') or player_data.get('team')
                player_data['full_name'] = sleeper_player.get('full_name') or player_data.get('full_name')
            
            # if player_data['position'] == 'UNKNOWN':
            #     print(f"Warning: Unknown position for player {player_data['full_name']} (Sleeper ID: {sleeper_id})")
            
            player = Player(player_data)
            self.enriched_players.append(player)

        print(f"Total players loaded: {len(self.enriched_players)}")

    def get_player(self, sleeper_id):
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        return None

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