import pandas as pd

# Load CSV data from a file path
df = pd.read_csv('datarepo/special/2023FULLDEPTHCHART.csv')

# Define the positions you want to keep
positions = ["QB", "RB", "WR", "TE"]

# Filter the DataFrame to only include the specified positions
# and exclude rows where the 'formation' column is 'Special Teams'
filtered_df = df[df['position'].isin(positions) & ~df['formation'].str.contains('Special Teams', na=False)]

# Save the filtered DataFrame to a CSV file
filtered_df.to_csv('datarepo/special/2023FULLDEPTHCHART_FILTERED.csv', index=False)
