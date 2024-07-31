import pandas as pd

class InjuryDataLoader:
    @staticmethod
    def get_and_clean_data():
        csv_file_path = 'datarepo/Special/combined_injury_risk_data.csv'
        try:
            injury_df = pd.read_csv(csv_file_path)
            injury_df.columns = injury_df.columns.str.strip().str.lower().str.replace(' ', '_')
            return injury_df
        except FileNotFoundError:
            print(f"Injury data file not found: {csv_file_path}")
            return pd.DataFrame()
