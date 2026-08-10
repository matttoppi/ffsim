import pandas as pd
import numpy as np
from difflib import get_close_matches

class DataMerger:
    @staticmethod
    def merge_data(fantasy_calc_df, sleeper_df, pff_df, injury_df):
        merged_df = pd.merge(fantasy_calc_df, sleeper_df, left_on='sleeper_id', right_on='player_id', how='outer', suffixes=('_fc', '_sl'))

        for column in ('team', 'position', 'age'):
            merged_df[column] = merged_df[f'{column}_sl'].fillna(merged_df[f'{column}_fc'])
        merged_df.drop(
            columns=[f'{column}_{source}' for column in ('team', 'position', 'age') for source in ('fc', 'sl')],
            inplace=True,
        )
        
        merged_df['name_lower'] = merged_df['full_name'].str.lower()
        pff_df['playerName'] = pff_df['playerName'].str.lower()
        
        def fuzzy_match(name, choices, cutoff=80):
            if pd.isna(name):
                return None
            matches = get_close_matches(name, choices, n=1, cutoff=cutoff / 100)
            return choices.index(matches[0]) if matches else None

        pff_names = pff_df['playerName'].tolist()
        merged_df['pff_index'] = merged_df['name_lower'].apply(lambda x: fuzzy_match(x, pff_names))
        
        final_df = pd.merge(merged_df, pff_df, left_on='pff_index', right_index=True, how='left', suffixes=('', '_pff'))
        
        if 'position_pff' in final_df.columns:
            final_df['position'] = final_df.apply(lambda row: row['position_pff'] if pd.isna(row['position']) or row['position'] == 'UNKNOWN' else row['position'], axis=1)
            final_df.drop('position_pff', axis=1, inplace=True)
        
        injury_df['player_lower'] = injury_df['player'].str.lower().str.strip()
        final_df['name_lower'] = final_df['full_name'].str.lower().str.strip()
        
        injury_df = injury_df.rename(columns={
            'probability_of_injury_in_the_season': 'injury_probability_season',
            'probability_of_injury_per_game': 'injury_probability_game'
        })
        
        final_df = DataMerger.merge_injury_data(final_df, injury_df)
        final_df = DataMerger.clean_merged_data(final_df)
        return final_df

    @staticmethod
    def merge_injury_data(final_df, injury_df):
        # Function to find the best match
        def find_best_match(name, choices, cutoff=80):
            if pd.isna(name):
                return None
            matches = get_close_matches(name, list(choices), n=1, cutoff=cutoff / 100)
            return matches[0] if matches else None

        # Create a dictionary of injury data
        injury_dict = injury_df.set_index('player_lower').to_dict('index')
        
        # Function to get injury data
        def get_injury_data(row):
            name = row['name_lower']
            position = row['position'].upper() if pd.notna(row['position']) else ''
            
            if pd.isna(name):
                return pd.Series({col: np.nan for col in injury_df.columns if col != 'player_lower'})
            
            # Try exact match first
            if name in injury_dict and injury_dict[name]['position'].upper() == position:
                return pd.Series({col: injury_dict[name].get(col, np.nan) for col in injury_df.columns if col != 'player_lower'})
            
            # If no exact match, try fuzzy matching
            best_match = find_best_match(name, injury_dict.keys())
            if best_match and injury_dict[best_match]['position'].upper() == position:
                return pd.Series({col: injury_dict[best_match].get(col, np.nan) for col in injury_df.columns if col != 'player_lower'})
            
            # If still no match, return NaN
            return pd.Series({col: np.nan for col in injury_df.columns if col != 'player_lower'})

        # Apply the function to merge injury data
        injury_columns = [col for col in injury_df.columns if col != 'player_lower']
        injury_data = final_df.apply(get_injury_data, axis=1)
        return pd.concat([final_df, injury_data], axis=1)

    @staticmethod
    def clean_merged_data(df):
        injury_columns = ['career_injuries', 'injury_risk', 'probability_of_injury_in_the_season', 
                          'projected_games_missed', 'probability_of_injury_per_game', 'durability']
        for col in df.columns:
            if col in injury_columns:
                if pd.api.types.is_object_dtype(df[col]):
                    df[col] = df[col].fillna('Unknown')
                else:
                    df[col] = df[col].fillna(0)
            else:
                if pd.api.types.is_object_dtype(df[col]):
                    df[col] = df[col].fillna('')
                else:
                    df[col] = df[col].fillna(0)
        
        df['byeWeek'] = df['byeWeek'].replace({0: None})
        df['sleeper_id'] = df['sleeper_id'].fillna(df['player_id'])
        return df
