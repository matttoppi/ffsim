import pandas as pd
import csv


def average_ngs_receiving():
    file_path = 'datarepo/NGS/NGS_2023Recieving.csv'  # Adjust the file path as necessary
    data = pd.read_csv(file_path)

    # Trim whitespace from column names
    data.columns = data.columns.str.strip()

    # Group the data by 'player_gsis_id'
    # Calculate the mean for numeric columns and aggregate weeks into a comma-separated string
    aggregated_data = data.groupby('player_gsis_id').agg({
        'season': 'first',
        'season_type': 'first',
        'player_display_name': 'first',
        'player_position': 'first',
        'team_abbr': 'first',
        # Include other numeric fields as needed with 'mean' or 'sum'
        'week': lambda x: ', '.join(x.astype(str))
    }).reset_index()

    # Specify the file path where you want to save the processed CSV
    output_file_path = 'datarepo/NGS/NGS_2023Receiving_averaged.csv'  # Update this path as needed

    # Saving the final DataFrame to a CSV file
    aggregated_data.to_csv(output_file_path, index=False, quoting=csv.QUOTE_NONNUMERIC)

    print(f"File saved to {output_file_path}")
def average_ngs_rushing():
    file_path = 'datarepo/NGS/NGS_2023Rushing.csv'  # Update this path to your actual file path
    data = pd.read_csv(file_path)

    # Trim whitespace from column names
    data.columns = data.columns.str.strip()

    # Group the data by 'player_gsis_id'
    # Calculate the mean for numeric columns and aggregate weeks into a comma-separated string
    aggregated_data = data.groupby('player_gsis_id').agg({
        'season': 'first',
        'season_type': 'first',
        'player_display_name': 'first',
        'player_position': 'first',
        'team_abbr': 'first',
        # Include other numeric fields as needed with 'mean' or 'sum'
        'week': lambda x: ', '.join(x.astype(str))
    }).reset_index()

    # Specify the file path where you want to save the processed CSV
    output_file_path = 'datarepo/NGS/NGS_2023Rushing_averaged.csv'  # Update this path as needed

    # Saving the final DataFrame to a CSV file
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