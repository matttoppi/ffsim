import pandas as pd
import csv

import pandas as pd
import csv
import pandas as pd
import csv

def average_ngs_receiving():
    file_path = 'datarepo/NGS/NGS_2023Receiving.csv'
    data = pd.read_csv(file_path)

    # Trim leading and trailing spaces from column names
    data.columns = data.columns.str.strip()
    
    # Trim whitespace from all string-like columns
    data = data.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    
    # Convert numeric columns to numeric type, errors='coerce' will set non-convertible values to NaN
    numeric_columns = [
        'avg_cushion', 'avg_separation', 'avg_intended_air_yards', 
        'percent_share_of_intended_air_yards', 'receptions', 'targets', 
        'catch_percentage', 'yards', 'rec_touchdowns', 'avg_yac', 
        'avg_expected_yac', 'avg_yac_above_expectation'
    ]
    
    for col in numeric_columns:
        if col in data.columns:  # Check if the column exists
            data[col] = pd.to_numeric(data[col], errors='coerce')

    aggregated_data = data.groupby('player_gsis_id').agg({
        'season': 'first',
        'season_type': 'first',
        'week': lambda x: ', '.join(x.astype(str)),
        'player_display_name': 'first',
        'player_position': 'first',
        'team_abbr': 'first',
        'avg_cushion': 'mean',
        'avg_separation': 'mean',
        'avg_intended_air_yards': 'mean',
        'percent_share_of_intended_air_yards': 'mean',
        'receptions': 'sum',
        'targets': 'sum',
        'catch_percentage': 'mean',
        'yards': 'sum',
        'rec_touchdowns': 'sum',
        'avg_yac': 'mean',
        'avg_expected_yac': 'mean',
        'avg_yac_above_expectation': 'mean',
        'player_first_name': 'first',
        'player_last_name': 'first',
        'player_jersey_number': 'first',
        'player_short_name': 'first'
    }).reset_index()

    output_file_path = 'datarepo/NGS/NGS_2023Receiving_averaged.csv'
    aggregated_data.to_csv(output_file_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    print(f"File saved to {output_file_path}")

# average_ngs_receiving()

# Run the function as needed
# average_ngs_receiving()



def average_ngs_rushing():
    file_path = 'datarepo/NGS/NGS_2023Rushing.csv'
    data = pd.read_csv(file_path)
    data.columns = data.columns.str.strip()

    aggregated_data = data.groupby('player_gsis_id').agg({
        'season': 'first',
        'season_type': 'first',
        'week': lambda x: ', '.join(x.astype(str)),
        'player_display_name': 'first',
        'player_position': 'first',
        'team_abbr': 'first',
        'efficiency': 'mean',
        'percent_attempts_gte_eight_defenders': 'mean',
        'avg_time_to_los': 'mean',
        'rush_attempts': 'sum',
        'rush_yards': 'sum',
        'expected_rush_yards': 'sum',
        'rush_yards_over_expected': 'sum',
        'avg_rush_yards': 'mean',
        'rush_yards_over_expected_per_att': 'mean',
        'rush_pct_over_expected': 'mean',
        'rush_touchdowns': 'sum',
        'player_first_name': 'first',
        'player_last_name': 'first',
        'player_jersey_number': 'first',
        'player_short_name': 'first'
    }).reset_index()

    output_file_path = 'datarepo/NGS/NGS_2023Rushing_averaged.csv'
    aggregated_data.to_csv(output_file_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    print(f"File saved to {output_file_path}")


def average_ngs_passing():


    # Adjust the file path to the location of your passing CSV file
    file_path = 'datarepo/NGS/NGS_2023Passing.csv'  # Update this path to your actual file path

    # Read the CSV data from the file path
    data = pd.read_csv(file_path)

    # Trim whitespace from column names
    data.columns = data.columns.str.strip()

    # Group the data by 'player_gsis_id'
    # Calculate the mean for numeric columns only and aggregate weeks into a comma-separated string
    aggregated_data = data.groupby('player_gsis_id').agg({
        'season': 'first',
        'season_type': 'first',
        'player_display_name': 'first',
        'player_position': 'first',
        'team_abbr': 'first',
        'avg_time_to_throw': 'mean',
        'avg_completed_air_yards': 'mean',
        'avg_intended_air_yards': 'mean',
        'avg_air_yards_differential': 'mean',
        'aggressiveness': 'mean',
        'max_completed_air_distance': 'mean',
        'avg_air_yards_to_sticks': 'mean',
        'attempts': 'sum',
        'pass_yards': 'sum',
        'pass_touchdowns': 'sum',
        'interceptions': 'sum',
        'passer_rating': 'mean',
        'completions': 'sum',
        'completion_percentage': 'mean',
        'expected_completion_percentage': 'mean',
        'completion_percentage_above_expectation': 'mean',
        'avg_air_distance': 'mean',
        'max_air_distance': 'mean',
        'player_first_name': 'first',
        'player_last_name': 'first',
        'player_jersey_number': 'first',
        'player_short_name': 'first',
        # Convert the list of weeks to a comma-separated string
        'week': lambda x: ', '.join(x.astype(str))
    })

    # Reset the index to turn 'player_gsis_id' back into a column
    aggregated_data.reset_index(inplace=True)

    # Specify the file path where you want to save the processed CSV
    output_file_path = 'datarepo/NGS/NGS_2023Passing_averaged.csv'  # Update this path as needed

    # Saving the final DataFrame to a CSV file
    aggregated_data.to_csv(output_file_path, index=False, quoting=csv.QUOTE_NONNUMERIC)

    print(f"File saved to {output_file_path}")



# average_ngs_rushing()
average_ngs_passing()
average_ngs_receiving()
average_ngs_rushing()