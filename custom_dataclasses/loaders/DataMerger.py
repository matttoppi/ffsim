import pandas as pd
from fuzzywuzzy import process
import numpy as np


class DataMerger:
    @staticmethod
    def merge_data(fantasy_calc_df, sleeper_df, pff_df, injury_df):
        # Merge FantasyCalc and Sleeper data
        merged_df = pd.merge(fantasy_calc_df, sleeper_df, left_on='sleeper_id', right_on='player_id', how='outer', suffixes=('_fc', '_sl'))
        
        # Ensure team column exists and is filled correctly
        if 'team_fc' in merged_df.columns and 'team_sl' in merged_df.columns:
            merged_df['team'] = merged_df['team_fc'].fillna(merged_df['team_sl'])
        elif 'team_fc' in merged_df.columns:
            merged_df['team'] = merged_df['team_fc']
        elif 'team_sl' in merged_df.columns:
            merged_df['team'] = merged_df['team_sl']
        else:
            print("Warning: No team data found in FantasyCalc or Sleeper data")
            merged_df['team'] = 'Unknown'
        
        merged_df = merged_df.drop(columns=['team_fc', 'team_sl'], errors='ignore')
        
        # Prepare for merging with PFF data
        merged_df['name_lower'] = merged_df['full_name'].str.lower()
        pff_df['playerName'] = pff_df['playerName'].str.lower()
        
        final_df = pd.merge(merged_df, pff_df, left_on='name_lower', right_on='playerName', how='left', suffixes=('', '_pff'))
        
        if 'position_pff' in final_df.columns:
            final_df['position'] = final_df['position'].fillna(final_df['position_pff'])
            final_df.drop('position_pff', axis=1, inplace=True)
        
        # Prepare for merging with injury data
        injury_df['player_lower'] = injury_df['player'].str.lower().str.strip()
        final_df['name_lower'] = final_df['name'].str.lower().str.strip()
        
        # Ensure the column names match exactly
        injury_df = injury_df.rename(columns={
            'probability_of_injury_in_the_season': 'injury_probability_season',
            'probability_of_injury_per_game': 'injury_probability_game'
        })
        
        # Merge injury data
        final_df = DataMerger.merge_injury_data(final_df, injury_df)
        
        # Clean up the data
        final_df = DataMerger.clean_merged_data(final_df)
        
        return final_df

    @staticmethod
    def merge_injury_data(final_df, injury_df):
        # Function to find the best match
        def find_best_match(name, choices, cutoff=80):
            if pd.isna(name):
                return None
            best_match = process.extractOne(name, choices)
            return best_match[0] if best_match and best_match[1] >= cutoff else None

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