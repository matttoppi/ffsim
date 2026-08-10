import json
import os
from datetime import datetime, timedelta
from urllib.request import urlopen
import pandas as pd
from custom_dataclasses.player import Player, PFFProjections
from custom_dataclasses.loaders.SleeperLoader import SleeperLoader
from custom_dataclasses.loaders.PFFLoader import PFFLoader
from custom_dataclasses.loaders.InjuryDataLoader import InjuryDataLoader
from custom_dataclasses.loaders.FantasyCalcLoader import FantasyCalcLoader
from custom_dataclasses.loaders.DataMerger import DataMerger
from sim.SimulationClasses.SpecialTeamScorer import SpecialTeamScorer


class PlayerLoader:
    def __init__(self):
        self.players_file = 'datarepo/players.json'
        self.sleeper_players_file = 'sleeper_players.json'
        self.refresh_interval = timedelta(days=3)
        self.enriched_players = []
        self.pff_projections = None
        self.sleeper_players = self.load_sleeper_players()
        self.special_team_scorer = SpecialTeamScorer('datarepo/PFFProjections/kickers.csv', 'datarepo/PFFProjections/dsts.csv')

    def load_sleeper_players(self):
        fresh = (
            os.path.exists(self.sleeper_players_file)
            and datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.sleeper_players_file))
            <= self.refresh_interval
        )
        if fresh:
            with open(self.sleeper_players_file, 'r') as f:
                players_list = json.load(f)
        else:
            with urlopen("https://api.sleeper.app/v1/players/nfl", timeout=30) as response:
                players = json.load(response)
            players_list = []
            for player_id, player in players.items():
                player["player_id"] = player.get("player_id") or player_id
                players_list.append(player)
            with open(self.sleeper_players_file, "w") as file:
                json.dump(players_list, file)
        return {str(player['player_id']): player for player in players_list if 'player_id' in player}

    def load_players_from_file(self):
        if os.path.exists(self.players_file) and datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.players_file)) <= self.refresh_interval:
            print(f"Loading players from file: {self.players_file}")
            with open(self.players_file, 'r') as file:
                player_data = json.load(file)
                
            
            self.enriched_players = []
            players_updated = 0
            for data in player_data:
                # Update position if necessary
                sleeper_id = str(data.get('sleeper_id'))
                if sleeper_id in self.sleeper_players:
                    sleeper_player = self.sleeper_players[sleeper_id]
                    current_position = data.get('position')
                    if isinstance(current_position, int) or current_position == '0' or current_position == 'UNKNOWN':
                        new_position = sleeper_player.get('position')
                        if new_position:
                            data['position'] = new_position
                            players_updated += 1
                
                pff_data = data.get('pff_projections', {})
                data['pff_projections'] = PFFProjections(pff_data) if pff_data else None
                player = Player(data)
                player.initialize_st_scorer(self.special_team_scorer)
                self.enriched_players.append(player)
            
            print(f"Loaded {len(self.enriched_players)} players from file.")
            print(f"Updated positions for {players_updated} players.")
            
            if players_updated > 0:
                self.save_players_to_file()
            
            # Rest of your method (update with Sleeper data, load PFF data, etc.)
            self.update_with_sleeper_data()
            self.load_and_update_pff_data()
        else:
            print("Player data file not found or outdated. Fetching new data...")
            self.load_players()
            self.save_players_to_file()

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
        print(f"Loaded PFF projections: {len(self.pff_projections)} rows")  # Add this line for debugging

    def load_players(self):
        print("Loading player data...")
        fantasy_calc_df = FantasyCalcLoader.get_and_clean_data()
        sleeper_df = SleeperLoader.get_and_clean_data(self.sleeper_players.values())
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

        for _, row in final_df.iterrows():
            player_data = row.to_dict()
            player_data['pff_projections'] = player_data.copy()
            player = Player(player_data)
            player.normalize_injury_probability()
            player.initialize_st_scorer(self.special_team_scorer)
            self.enriched_players.append(player)

        print(f"Total players loaded: {len(self.enriched_players)}")

    def load_player(self, sleeper_id):
        self.ensure_players_loaded()
        
        for player in self.enriched_players:
            if str(player.sleeper_id) == str(sleeper_id):
                return player
        
        print(f"Player not found with sleeper_id: {sleeper_id}")
        return None
    
    
    
    def ensure_players_loaded(self):
        if not self.enriched_players:
            self.load_players_from_file()
            
    def load_and_update_pff_data(self):
        print("Loading and updating PFF and injury data...")
        self.load_pff_projections()
        injury_df = InjuryDataLoader.get_and_clean_data()
        injury_df.index = injury_df['player'].apply(Player.clean_name)
        
        for player in self.enriched_players:
            # Update PFF data
            pff_row = self.pff_projections[
                (self.pff_projections['playerName'].str.lower() == player.full_name.lower())
            ]
            if not pff_row.empty:
                pff_data = pff_row.iloc[0].to_dict()
                player.update_pff_projections(pff_data)
            
            # Update injury data
            injury_key = Player.clean_name(player.full_name)
            if injury_key in injury_df.index:
                injury_data = injury_df.loc[injury_key].to_dict()
                player.update_injury_data(injury_data)
        
        self.save_players_to_file()
                
    def update_with_sleeper_data(self):
        print("Updating players with Sleeper data...")
        sleeper_df = SleeperLoader.get_and_clean_data(self.sleeper_players.values())
        
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
                players_updated += 1
        
        print(f"Updated {players_updated} players with Sleeper data")

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
