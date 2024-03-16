import pandas as pd

# Assuming 'datarepo/NGS_2023Recieving.csv' is the correct path to your CSV file
file_path = 'datarepo/NGS_2023Recieving.csv'

# Read the CSV data from the file path
data = pd.read_csv(file_path)

# Check if 'week' column exists before attempting to drop it
if 'week' in data.columns:
    data.drop('week', axis=1, inplace=True)

# Group the data by 'player_gsis_id' and calculate the mean for numeric columns
average_stats = data.groupby('player_gsis_id').mean()

# For non-numeric columns that need to be preserved, grabbing them with a 'first' aggregation
non_numeric = data.groupby('player_gsis_id').agg({
    'season': 'first',
    'season_type': 'first',
    'player_display_name': 'first',
    'player_position': 'first',
    'team_abbr': 'first',
    'player_first_name': 'first',
    'player_last_name': 'first',
    'player_jersey_number': 'first',
    'player_short_name': 'first'
}).reset_index()

# Merging the numeric and non-numeric dataframes
final_stats = pd.merge(non_numeric, average_stats, on='player_gsis_id')

# Specify the file path where you want to save the CSV
output_file_path = 'datarepo/NGS_2023WR_averaged.csv'

# Saving the final DataFrame to a CSV file
final_stats.to_csv(output_file_path, index=False)

print(f"File saved to {output_file_path}")
