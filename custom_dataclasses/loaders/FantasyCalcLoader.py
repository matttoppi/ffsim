import requests
import pandas as pd

class FantasyCalcLoader:
    @staticmethod
    def get_and_clean_data():
        response = requests.get("https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=10&ppr=1")
        if response.status_code == 200:
            data = response.json()
            cleaned_data = [
                {
                    "sleeper_id": player_info['player'].get('sleeperId'),
                    "name": player_info['player'].get('name'),
                    "value_1qb": player_info.get('value'),
                    "redraft_value": player_info.get('redraftValue'),
                    "position": player_info['player'].get('position'),
                    "team": player_info['player'].get('maybeTeam'),
                    "age": player_info['player'].get('maybeAge')
                }
                for player_info in data
            ]
            return pd.DataFrame(cleaned_data)
        else:
            print(f"Failed to fetch FantasyCalc data: HTTP {response.status_code}")
            return pd.DataFrame()
