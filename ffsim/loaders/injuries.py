import pandas as pd

from ffsim.paths import DATA_DIR


class InjuryDataLoader:
    @staticmethod
    def get_and_clean_data(season=2026):
        path = DATA_DIR / "injuries" / "risk.csv"
        if not path.exists():
            return pd.DataFrame()
        data = pd.read_csv(path)
        required = {
            "season", "sleeper_id", "injury_probability", "projected_games_missed"
        }
        if not required <= set(data.columns):
            return pd.DataFrame()
        data = data[data.season == season].copy()
        data["sleeper_id"] = data.sleeper_id.astype(str)
        return data
