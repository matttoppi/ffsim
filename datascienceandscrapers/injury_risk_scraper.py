import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

def scrape_position(url):
    # Fetch the HTML content
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Initialize a list to store the extracted data
    injury_data = []

    # Loop through each main row to extract the required fields
    for row in soup.select('tr:has(td)'):
        cells = row.find_all('td')
        if len(cells) >= 10:  # Ensure there are enough cells
            player_name = cells[1].get_text(strip=True)
            
            # Skip rows that start with a date
            if re.match(r'\w{3}\s+\d{1,2},\s+\d{4}', player_name):
                continue
            
            career_injuries = cells[2].select_one('span.injury-count').get_text(strip=True) if cells[2].select_one('span.injury-count') else ''
            injury_risk = cells[4].get_text(strip=True)
            prob_injury_season = cells[5].select_one('span.injury-percent').get_text(strip=True) if cells[5].select_one('span.injury-percent') else ''
            proj_games_missed = cells[6].select_one('span.proj-games-missed').get_text(strip=True) if cells[6].select_one('span.proj-games-missed') else ''
            prob_injury_game = cells[7].select_one('span.prob-injury-per-game').get_text(strip=True) if cells[7].select_one('span.prob-injury-per-game') else ''
            durability = cells[8].select_one('span.durability-score').get_text(strip=True) if cells[8].select_one('span.durability-score') else ''
            ppr_points = cells[9].select_one('span.proj-points').get_text(strip=True) if cells[9].select_one('span.proj-points') else ''
            
            injury_data.append({
                'Player': player_name,
                'Career Injuries': career_injuries,
                'Injury Risk': injury_risk,
                'Probability of Injury In the Season': prob_injury_season,
                'Projected Games Missed': proj_games_missed,
                'Probability of Injury Per Game': prob_injury_game,
                'Durability': durability,
                'PPR Points': ppr_points
            })

    # Convert the injury data to a DataFrame
    df = pd.DataFrame(injury_data)

    # Clean up the data
    df['Player'] = df['Player'].apply(lambda x: re.sub(r',\s*[A-Z]{2,3}\s+[A-Z]{2,3}$', '', x))
    df['Injury Risk'] = df['Injury Risk'].str.replace('Risk', '').str.strip()
    df['Probability of Injury In the Season'] = df['Probability of Injury In the Season'].str.rstrip('%')
    df['Probability of Injury Per Game'] = df['Probability of Injury Per Game'].str.rstrip('%')

    # Convert numeric columns to appropriate types
    numeric_columns = ['Career Injuries', 'Probability of Injury In the Season', 'Projected Games Missed', 
                       'Probability of Injury Per Game', 'Durability', 'PPR Points']
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Convert column names to lowercase and underscore-separated
    df.columns = df.columns.str.lower().str.replace(' ', '_')

    return df

urls = {
    'RB': 'https://www.draftsharks.com/injury-predictor/rb',
    'TE': 'https://www.draftsharks.com/injury-predictor/te',
    'QB': 'https://www.draftsharks.com/injury-predictor/qb',
    'WR': 'https://www.draftsharks.com/injury-predictor/wr'
}

all_data = []

for position, url in urls.items():
    print(f"Scraping {position}...")
    df = scrape_position(url)
    df['Position'] = position
    all_data.append(df)

# Combine all DataFrames
combined_df = pd.concat(all_data, ignore_index=True)

# Save the combined DataFrame to a CSV file
csv_file_path = 'combined_injury_risk_data.csv'
combined_df.to_csv(csv_file_path, index=False)

print(f"Data has been successfully saved to {csv_file_path}")
