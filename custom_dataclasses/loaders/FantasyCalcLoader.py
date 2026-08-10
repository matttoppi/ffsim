import json
from urllib.request import urlopen

import pandas as pd

class FantasyCalcLoader:
    @staticmethod
    def get_and_clean_data():
        url = "https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=10&ppr=1"
        with urlopen(url, timeout=30) as response:
            data = json.load(response)
        return pd.DataFrame([
            {
                "sleeper_id": item["player"].get("sleeperId"),
                "name": item["player"].get("name"),
                "value_1qb": item.get("value"),
                "redraft_value": item.get("redraftValue"),
                "position": item["player"].get("position"),
                "team": item["player"].get("maybeTeam"),
                "age": item["player"].get("maybeAge"),
            }
            for item in data
        ])
