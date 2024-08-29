import pandas as pd
from fuzzywuzzy import process
import numpy as np
from custom_dataclasses.loaders.InjuryDataLoader import InjuryDataLoader

class DataMerger:
    @staticmethod
    def merge_data(fantasy_calc_df, sleeper_df, pff_df, injury_df):
        merged_df = pd.merge(fantasy_calc_df, sleeper_df, left_on='sleeper_id', right_on='player_id', how='outer', suffixes=('_fc', '_sl'))

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
        
        merged_df['name_lower'] = merged_df['full_name'].str.lower()
        pff_df['playerName'] = pff_df['playerName'].str.lower()
        
        def fuzzy_match(name, choices, cutoff=80):
            if pd.isna(name):
                return None
            match = process.extractOne(name, choices)
            if match and len(match) >= 2 and match[1] >= cutoff:
                return choices.index(match[0])
            return None

        pff_names = pff_df['playerName'].tolist()
        merged_df['pff_index'] = merged_df['name_lower'].apply(lambda x: fuzzy_match(x, pff_names))
        
        final_df = pd.merge(merged_df, pff_df, left_on='pff_index', right_index=True, how='left', suffixes=('', '_pff'))
        
        if 'position_pff' in final_df.columns:
            final_df['position'] = final_df.apply(lambda row: row['position_pff'] if pd.isna(row['position']) or row['position'] == 'UNKNOWN' else row['position'], axis=1)
            final_df.drop('position_pff', axis=1, inplace=True)
        
        injury_df['player_lower'] = injury_df['player'].str.lower().str.strip()
        final_df['name_lower'] = final_df['name'].str.lower().str.strip()
        
        injury_df = injury_df.rename(columns={
            'probability_of_injury_in_the_season': 'injury_probability_season',
            'probability_of_injury_per_game': 'injury_probability_game'
        })
        
        # Convert injury probabilities to proper decimals
        injury_df['injury_probability_season'] = injury_df['injury_probability_season']
        injury_df['injury_probability_game'] = injury_df['injury_probability_game']
        # ['injury_probability_game'].apply(DataMerger.convert_to_decimal)
        
        final_df = DataMerger.merge_injury_data(final_df, injury_df)
        
        final_df = DataMerger.clean_merged_data(final_df)
        
        lamar_row = final_df[(final_df['full_name'].str.lower() == 'lamar jackson') & (final_df['team'] == 'BAL')]
        
        no_pff = final_df[final_df['fantasyPoints'].isna()]
        print("Players without PFF projections:")
        print(no_pff[['full_name', 'position', 'team']])
        
        return final_df

    @staticmethod
    def convert_to_decimal(value):
        if value is None or value == '':
            return 0
        if isinstance(value, str):
            value = value.replace('%', '').strip()
        try:
            float_value = float(value)
            return float_value / 100 if float_value > 1 else float_value
        except ValueError:
            return 0
    
    @staticmethod
    def merge_pff_data(merged_df, pff_df):
        def clean_name(name):
            name = str(name).lower()
            for suffix in [' jr', ' sr', ' ii', ' iii', ' iv']:
                name = name.replace(suffix, '')
            return name.replace('.', '').replace("'", '').strip()

        merged_df['clean_name'] = merged_df['full_name'].apply(clean_name)
        pff_df['clean_name'] = pff_df['playerName'].apply(clean_name)

        # First, try exact matching
        exact_match = pd.merge(merged_df, pff_df, on='clean_name', how='left', suffixes=('', '_pff'))

        # For unmatched players, try fuzzy matching
        unmatched = exact_match[exact_match['playerName'].isna()]
        matched = exact_match[~exact_match['playerName'].isna()]

        def fuzzy_match(name, choices, cutoff=80):
            match = process.extractOne(name, choices)
            return match[2] if match and match[1] >= cutoff else None

        pff_names = pff_df['clean_name'].tolist()
        unmatched['pff_index'] = unmatched['clean_name'].apply(lambda x: fuzzy_match(x, pff_names))
        
        fuzzy_matched = unmatched[unmatched['pff_index'].notna()].merge(
            pff_df, left_on='pff_index', right_index=True, how='left', suffixes=('', '_pff')
        )

        final_df = pd.concat([matched, fuzzy_matched], ignore_index=True)

        # Clean up
        final_df.drop(columns=['clean_name', 'pff_index', 'playerName'], inplace=True, errors='ignore')

        print(f"Total players: {len(merged_df)}")
        print(f"Exact matches: {len(matched)}")
        print(f"Fuzzy matches: {len(fuzzy_matched)}")
        print(f"Unmatched: {len(merged_df) - len(matched) - len(fuzzy_matched)}")

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