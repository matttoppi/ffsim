import pandas as pd

class InjuryDataLoader:
    @staticmethod
    def get_and_clean_data():
        csv_file_path = 'datarepo/Special/combined_injury_risk_data.csv'
        try:
            injury_df = pd.read_csv(csv_file_path)
            injury_df.columns = injury_df.columns.str.strip().str.lower().str.replace(' ', '_')
            
            # Clean player_name column
            if 'player_name' in injury_df.columns:
                # Remove suffixes like Jr., Sr., III, etc.
                injury_df['player_name'] = injury_df['player_name'].str.replace(r'\s(Jr\.|Sr\.|III|II|IV|V|VI)$', '', regex=True)
                # Remove dots inside names
                injury_df['player_name'] = injury_df['player_name'].str.replace(r'\.', '', regex=True)
            
            return injury_df
        except FileNotFoundError:
            print(f"Injury data file not found: {csv_file_path}")
            return pd.DataFrame()
