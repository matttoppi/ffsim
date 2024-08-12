import pandas as pd

class InjuryDataLoader:
    @staticmethod
    def convert_to_decimal(value):
        if value is None or value == '':
            return 0
        if isinstance(value, str):
            value = value.replace('%', '').strip()
        try:
            float_value = float(value)
            return float_value / 100  # Always convert to decimal
        except ValueError:
            return 0

    @staticmethod
    def get_and_clean_data():
        csv_file_path = 'datarepo/Special/combined_injury_risk_data.csv'
        try:
            injury_df = pd.read_csv(csv_file_path)
            injury_df.columns = injury_df.columns.str.strip().str.lower().str.replace(' ', '_')
            
            # Convert probabilities to decimals
            for col in ['probability_of_injury_in_the_season', 'probability_of_injury_per_game']:
                injury_df[col] = injury_df[col].apply(InjuryDataLoader.convert_to_decimal)
            
            print("DEBUG: First few rows of processed injury data:")
            print(injury_df[['player', 'probability_of_injury_in_the_season', 'probability_of_injury_per_game']].head())
            
            return injury_df
        except FileNotFoundError:
            print(f"Injury data file not found: {csv_file_path}")
            return pd.DataFrame()