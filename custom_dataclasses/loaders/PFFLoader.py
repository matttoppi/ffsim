import pandas as pd

class PFFLoader:
    @staticmethod
    def get_and_clean_data():
        df = pd.read_csv('datarepo/PFFProjections/24PFFProjections.csv')
        
        # Check which desired columns are actually present
        available_columns = [col for col in desired_columns if col in df.columns]
        print("Columns found:", available_columns)
        
        if not available_columns:
            raise ValueError("None of the desired columns are present in the dataframe")
        
        
        # Clean playerName column
        if 'playerName' in df.columns:
            # Remove suffixes like Jr., Sr., III, etc.
            df['playerName'] = df['playerName'].str.replace(r'\s(Jr\.|Sr\.|III|II|IV|V|VI)$', '', regex=True)
            # Remove dots inside names
            df['playerName'] = df['playerName'].str.replace(r'\.', '', regex=True)
        
        return df