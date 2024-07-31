import json
import pandas as pd

class SleeperLoader:
    @staticmethod
    def get_and_clean_data():
        with open('sleeper_players.json', 'r') as file:
            sleeper_data = json.load(file)
        
        cleaned_data = [
            {
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
            for player in sleeper_data if player.get('active', False)
        ]
        return pd.DataFrame(cleaned_data)
