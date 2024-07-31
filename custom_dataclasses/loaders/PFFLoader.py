import pandas as pd


class PFFLoader:
    @staticmethod
    def get_and_clean_data(desired_columns):
        df = pd.read_csv('datarepo/PFFProjections/24PFFProjections.csv')
        df = df[desired_columns]
        df['playerName'] = df['playerName'].str.lower()
        return df

