import pandas as pd
import matplotlib.pyplot as plt
from adjustText import adjust_text
import numpy as np

# Load CSV data from a file path
df = pd.read_csv('datarepo/23expectedfantasypoints.csv')

# Filter to only include players with 'Fantasy Points Pts' over 85
filtered_df = df[df['Fantasy Points Pts'] > 115]

# Further filter to only include WRs
filtered_df = filtered_df[filtered_df['Pos'] == 'WR']

# Plotting
plt.figure(figsize=(20, 12))
plt.scatter(filtered_df['Points Per Game x-PPG'], filtered_df['Points Per Game PPG'], color='blue')
plt.title('Wide Receivers: Fantasy Points Per Game vs Fantasy Expected PFF PPG')
plt.xlabel('PFF Fantasy Points Per Game Expected')
plt.ylabel('Fantasy Points Per Game PPG')

# adjust leftmargin, rightmargin, topmargin, and bottommargin to fit the text
plt.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05)

# Calculate the regression line
m, b = np.polyfit(filtered_df['Points Per Game x-PPG'], filtered_df['Points Per Game PPG'], 1)

# Plot the regression line
plt.plot(filtered_df['Points Per Game x-PPG'], m*filtered_df['Points Per Game x-PPG'] + b, color='red')

# Write the player name on the plot for each player
texts = [plt.text(x, y, s, fontsize=11, ha='right') for x, y, s in zip(filtered_df['Points Per Game x-PPG'], filtered_df['Points Per Game PPG'], filtered_df['Player'])]

# Adjust the text annotations to minimize overlap
adjust_text(texts, arrowprops=dict(arrowstyle='->', color='black'))

plt.grid(True)
# save the plot to a file
plt.savefig('plots/23expectedvsactualWR.png')
plt.show()

# Filter to only include players with 'Fantasy Points Pts' over 115
filtered_df = df[df['Fantasy Points Pts'] > 115]

# Further filter to only include RBs
filtered_df = filtered_df[filtered_df['Pos'] == 'RB']

# Plotting
plt.figure(figsize=(20, 12))
plt.scatter(filtered_df['Points Per Game x-PPG'], filtered_df['Points Per Game PPG'], color='blue')
plt.title('Running Backs: Fantasy Points Per Game vs Fantasy Expected PFF PPG')
plt.xlabel('PFF Fantasy Points Per Game Expected')
plt.ylabel('Fantasy Points Per Game PPG')

# Adjust left margin, right margin, top margin, and bottom margin to fit the text
plt.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05)


# Calculate the regression line
m, b = np.polyfit(filtered_df['Points Per Game x-PPG'], filtered_df['Points Per Game PPG'], 1)

# Plot the regression line
plt.plot(filtered_df['Points Per Game x-PPG'], m*filtered_df['Points Per Game x-PPG'] + b, color='red')

# Write the player name on the plot for each player
texts = [plt.text(x, y, s, fontsize=11, ha='right') for x, y, s in zip(filtered_df['Points Per Game x-PPG'], filtered_df['Points Per Game PPG'], filtered_df['Player'])]

# Adjust the text annotations to minimize overlap
adjust_text(texts, arrowprops=dict(arrowstyle='->', color='black'))

plt.grid(True)

plt.savefig('plots/23expectedvsactualRB.png')
plt.show()
