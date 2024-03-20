import pandas as pd
import json


# various data sets:

# 2023 season weekly targets for each player
# "Player","Pos","Team","week1Targets","week2Targets","week3Targts","week4Targets","week5Targets","week6Targets","week7Targets","week8Targets","week9Targets","week10Targets","week11Targets","week12Targets","week13Targets","week14Targets","week15Targets","week16Targets","week17Targets","week18Targets","TTL","AVG"
# datarepo/Special/23TargetLeaders.csv


# 2023 next gen stats for QBs(passing)
# "player_gsis_id","season","season_type","player_display_name","player_position","team_abbr","avg_time_to_throw","avg_completed_air_yards","avg_intended_air_yards","avg_air_yards_differential","aggressiveness","max_completed_air_distance","avg_air_yards_to_sticks","attempts","pass_yards","pass_touchdowns","interceptions","passer_rating","completions","completion_percentage","expected_completion_percentage","completion_percentage_above_expectation","avg_air_distance","max_air_distance","player_first_name","player_last_name","player_jersey_number","player_short_name","week"
# week columns is a string of numbers separated by commas and represetns which weeks the player played. Needs to be parsed and put into better format
# datarepo/NGS/NGS_2023Passing_averaged.csv


# 2023 next gen stats for WRs and TEs (receiveing)
# "player_gsis_id","season","season_type","week","player_display_name","player_position","team_abbr","avg_cushion","avg_separation","avg_intended_air_yards","percent_share_of_intended_air_yards","receptions","targets","catch_percentage","yards","rec_touchdowns","avg_yac","avg_expected_yac","avg_yac_above_expectation","player_first_name","player_last_name","player_jersey_number","player_short_name"
# week columns is a string of numbers separated by commas and represents which weeks the player played. Needs to be parsed and put into better format


# depth charts for each week of the 2023 season
# season,club_code,week,game_type,depth_team,last_name,first_name,football_name,formation,gsis_id,jersey_number,position,elias_id,depth_position,full_name
# datarepo/Special/2023FULLDEPTHCHART_FILTERED.csv


# overall player stats with some advanced stats for the 2023 season
# Player,PassTD,INT,SACKS,RecTD,RUSH_ATT,RushTD,RUSH_RECEIVE_TD,TD.1,LG,20+,FL,FPTS,FPTS/G,ROST,AIR/A,PKT TIME,SK,KNCK,HRRY,BLITZ,POOR,RZ ATT,RTG,CMP,PassATT,PCT,PassYDS,Y/A,Y/ATT,YBCON,YBCON/ATT,YACON/ATT,TK LOSS,TK LOSS YDS,LNG TD,YACON.1,RushATT,RushYDS,YBC,YBC/R,AIR/R,YAC,YAC/R,YACON/R,% TM,CATCHABLE,RecYDS,Y/R,AIR,DROP,YACON,BRKTKL,LNG,RZ TGT,REC,TGT,10+ YDS,20+ YDS,30+ YDS,40+ YDS,50+ YDS,Rank,G,Pos,Team,week1Targets,week2Targets,week3Targts,week4Targets,week5Targets,week6Targets,week7Targets,week8Targets,week9Targets,week10Targets,week11Targets,week12Targets,week13Targets,week14Targets,week15Targets,week16Targets,week17Targets,week18Targets,TTL,AVG
# datarepo/merged_nfl_players_stats.csv

# 2024 data for each player in json format
# # {
#         "nfl_team": null,
#         "position": "WR",
#         "mfl_id": 14836,
#         "sportradar_id": "4131d4ee-0318-4bb5-832a-4dec80668a4f",
#         "fantasypros_id": null,
#         "gsis_id": "00-0036322",
#         "pff_id": 61398.0,
#         "sleeper_id": 6794.0,
#         "nfl_id": NaN,
#         "espn_id": 4262921.0,
#         "yahoo_id": 32692.0,
#         "fleaflicker_id": NaN,
#         "cbs_id": 2871343.0,
#         "pfr_id": "JeffJu00",
#         "cfbref_id": "justin-jefferson-1",
#         "rotowire_id": 14509.0,
#         "rotoworld_id": NaN,
#         "ktc_id": 542.0,
#         "stats_id": 32692.0,
#         "stats_global_id": 0.0,
#         "fantasy_data_id": 21685.0,
#         "swish_id": 1069535.0,
#         "merge_name": "justin jefferson",
#         "team": "MIN",
#         "birthdate": "1999-06-16",
#         "age": 24.7,
#         "draft_year": 2020.0,
#         "draft_round": 1.0,
#         "draft_pick": 22.0,
#         "draft_ovr": 22.0,
#         "twitter_username": "JJettas2",
#         "height": 73.0,
#         "weight": 195.0,
#         "college": "LSU",
#         "db_season": 2023,
#         "number": 18.0,
#         "depth_chart_position": "LWR",
#         "status": "Active",
#         "sport": "nfl",
#         "fantasy_positions": [
#             "WR"
#         ],
#         "search_last_name": "jefferson",
#         "injury_start_date": NaN,
#         "practice_participation": null,
#         "last_name": "Jefferson",
#         "search_full_name": "justinjefferson",
#         "birth_country": NaN,
#         "search_rank": 1.0,
#         "first_name": "Justin",
#         "depth_chart_order": 1.0,
#         "search_first_name": "justin",
#         "current_fantasy_team": null,
#         "current_season_fantasy_pts": null,
#         "previous_season_fantasy_pts": null,
#         "injury_risk": null,
#         "player_potential": null,
#         "ecr_1qb": 1.3,
#         "ecr_2qb": 5.3,
#         "ecr_pos": 1.2,
#         "value_1qb": 10184,
#         "value_2qb": 9270,
#         "scrape_date": "2024-02-23",
#         "fp_id": null
#     },
# datarepo/players.json


#  feature vector for each week for a player
# { 
    # player name
    # week
    # team
    # targets for that week
    # depth chart position
    # catches 
    # yards
    # position
    # avg_cushion
    # avg_separation
    # avg_intended_air_yards
    # percent_share_of_intended_air_yards
    # avg_yac
    # avg_expected_yac
    # avg_yac_above_expectation
    # agressiveness
    # RecTD: Receiving Touchdowns - Important for wide receivers and tight ends, showing scoring ability.
    # RUSH_ATT: Rushing Attempts - Reflects on a player's role in the running game.
    # RushTD: Rushing Touchdowns - Indicates effectiveness in the running game.
    # Y/A or Y/ATT: Yards per Attempt - Efficiency for both rushers and passers.
    # FPTS/G: Fantasy Points per Game - A composite measure of a player's overall performance.
    # QBs CMP% or PCT: Completion Percentage - Accuracy for quarterbacks.
    # PassYDS: Passing Yards - Total offensive output for quarterbacks.
    # RZ ATT: Red Zone Attempts - Scoring opportunity metrics for quarterbacks and skill position players.
    # 20+: Number of 20+ yard gains - Big play ability.
    # CATCHABLE percentage
    # WR gsis id
    
    # below is for the qb of the reciever for that week
    # Qb name
    # Qb team
    # Qb Time to throw
    # Qb completed air yards
    # Qb intended air yards
    # Qb air yards differential
    # Qb aggressiveness
    # Qb max completed air distance
    # Qb avg air yards to sticks
    # Qb attempts
    # Qb pass yards
    # Qb pass touchdowns
    # Qb interceptions
    # Qb passer rating
    # Qb completions
    # Qb completion percentage
    # Qb expected completion percentage
    # Qb completion percentage above expectation
    # QBs PassTD full seasonn: Passing Touchdowns - For quarterbacks, this indicates scoring efficiency.
    # QBs INT full season: Interceptions - A measure of a quarterback's decision-making.
    # Qb gsis id    
# }
    
    

# Step 1: Load datasets
targets_df = pd.read_csv("datarepo/Special/23TargetLeaders.csv")
qb_ngs_df = pd.read_csv("datarepo/NGS/NGS_2023Passing.csv")
wr_ngs_df = pd.read_csv("datarepo/NGS/NGS_2023Receiving.csv")
depth_chart_df = pd.read_csv("datarepo/Special/2023FULLDEPTHCHART_FILTERED.csv")
overall_stats_df = pd.read_csv("datarepo/merged_nfl_players_stats.csv")
projected_df = pd.read_csv("datarepo/projections/23WR_proj.csv")  # Load projections early for preparation

#convert the projected_df to lower case
projected_df['Player'] = projected_df['Player'].str.lower()

with open("datarepo/players.json") as f:
    players_json = json.load(f)
players_df = pd.DataFrame(players_json)

print("Loaded in datasets")

# Step 2: Adjust column names
wr_ngs_df.columns = wr_ngs_df.columns.str.strip().str.replace(' ', '_')
wr_ngs_df['team_abbr'] = wr_ngs_df['team_abbr'].str.upper()  # Example, adjust based on actual data

qb_ngs_df.columns = qb_ngs_df.columns.str.strip().str.replace(' ', '_')
depth_chart_df.columns = depth_chart_df.columns.str.strip().str.replace(' ', '_')


def parse_weeks(weeks_str):
    return [int(week) for week in str(weeks_str).split(',') if int(week) != 0]
print("Adjusted column names")

qb_ngs_df['week'] = qb_ngs_df['week'].astype(int)
qb_ngs_df = qb_ngs_df[qb_ngs_df['week'] != 0]


qb_ngs_df['weeks_played'] = qb_ngs_df['week'].apply(parse_weeks)
# convert the team_abbr to lower case
qb_ngs_df['team_abbr'] = qb_ngs_df['team_abbr'].str.lower()
# convert the player_display_name to lower case
qb_ngs_df['player_display_name'] = qb_ngs_df['player_display_name'].str.lower()
# convert the week to a string
qb_ngs_df['week'] = qb_ngs_df['week'].astype(str)

# print the details of the depth chart
print("The depth chart details")
print(depth_chart_df.head())
print(depth_chart_df.columns)



def get_depth_chart_position(player_gsis_id, week):
    # Ensure inputs are properly formatted
    player_gsis_id = player_gsis_id.strip()
    week_str = str(week).strip()  # Convert week to string and strip any whitespace

    # Filter the DataFrame based on conditions
    position_depth_num = depth_chart_df[
        (depth_chart_df['gsis_id'].str.strip() == player_gsis_id) &
        (depth_chart_df['week'].astype(str).str.strip() == week_str)
    ]['position_depth_num']

    # Return the position depth number if available, else return 'Unknown'
    if not position_depth_num.empty:
        return position_depth_num.iloc[0]
    else:
        return 'Unknown'


# Exclude week 0 for WR and depth chart data
wr_ngs_df['week'] = wr_ngs_df['week'].astype(str)
wr_ngs_df = wr_ngs_df[wr_ngs_df['week'] != 0]
depth_chart_df = depth_chart_df[depth_chart_df['week'] != '0']
depth_chart_df['week'] = depth_chart_df['week'].astype(str)


depth_chart_df['gsis_id'] = depth_chart_df['gsis_id'].astype(str)
depth_chart_df_simplified = depth_chart_df[['full_name', 'week', 'club_code', 'position_depth_num']]


projected_df['Player'] = projected_df['Player'].astype(str).str.strip().str.lower()
projected_df['Team'] = projected_df['Team'].astype(str).str.strip().str.lower()

# Step 5: Merge the projected stats with the wr_ngs_df
wr_ngs_df['player_display_name'] = wr_ngs_df['player_display_name'].astype(str).str.strip().str.lower()
wr_ngs_df['team_abbr'] = wr_ngs_df['team_abbr'].astype(str).str.strip().str.lower()
wr_ngs_df = pd.merge(wr_ngs_df, projected_df, how='left', left_on=['player_display_name', 'team_abbr'], right_on=['Player', 'Team'])

# confirm the merge
print("Merged the projected stats with the wr_ngs_df")
print(wr_ngs_df.head())

# print(wr_ngs_df.head())
wr_ngs_df.to_csv("temp.csv", index=False)


#print the weeks_played column
print("The weeks_played column from the qb_ngs_df")
print(qb_ngs_df['weeks_played'])

def find_qb_for_receiver(week, team):
    # Ensure 'week' is a string, since your logic might be based on string comparisons
    week_str = str(week)
    # Ensure 'team' is properly formatted as uppercase and stripped of leading/trailing spaces
    team = team.upper().strip()
    
    # Debugging print statements
    print(f"Looking for QB for Team: {team}, Week: {week_str}")

    # Assuming weeks_played is already a list of integers
    filtered_qbs = qb_ngs_df[(qb_ngs_df['team_abbr'].str.upper().str.strip() == team) & 
                             (qb_ngs_df['weeks_played'].apply(lambda weeks: int(week_str) in weeks))]
    
    if not filtered_qbs.empty:
        print("QB Found")
        return filtered_qbs.iloc[0]
    else:
        print(f"No QB found for Team: {team}, Week: {week_str}")
        return None

    

def calculate_fantasy_points(rec_touchdowns, yards, receptions):
    # Calculate fantasy points
    # 0.1 points per receiving yard
    # 6 points per receiving touchdown
    # 0.5 points per reception
    if rec_touchdowns is None:
        rec_touchdowns = 0
    if receptions is None:
        receptions = 0
        
    # Check if yards is a valid numeric string before attempting to convert
    if yards is not None and yards.strip().isdigit():
        yards = int(yards.strip())
    else:
        # If yards is not a valid numeric string, set it to 0
        yards = 0
    
    
    # Calculate fantasy points
    fantasy_points = (0.1 * yards) + (6 * rec_touchdowns) + (1.0 * receptions)
    
    # Round fantasy points to the hundredths place
    rounded_fantasy_points = round(fantasy_points, 2)
    
    return rounded_fantasy_points

def get_player_year_projections(player_name):
    player_name = player_name.strip().lower()

    player_projections = projected_df[
        (projected_df['Player'].str.lower() == player_name)
    ]
    
    # Ensure the default values match the keys you're trying to access later
    if not player_projections.empty:
        return player_projections.iloc[0].to_dict()
    else:
        print(f"No projections found for {player_name}. Returning default values.")
        return {
            '23RecTDS': -1,  # Adjusted key to match your access pattern
            '23RecYDS': -1,
            '23REC': -1,
            '23RushTDS': -1,
            '23RushYDS': -1,
            '23RushATT': -1
        }



print(f"Dataframes are cleaned and ready for feature creation")

# Create the feature vector dataframe
feature_vectors = []
# After merging, accessing depth_team and depth_position
print(f"Creating feature vectors...")
for index, row in wr_ngs_df.iterrows(): # for each receiver for each week
    # print(f"Creating feature vector for {row['player_display_name']} for week {row['week']}")
    if row['week'] == 0:
        print(f"Skipping week 0 for {row['player_display_name']}")  # Debug print
        continue
    
    
    qb_info = find_qb_for_receiver(row['week'], row['team_abbr'])
    if qb_info is None:
        # print(f"No QB found for {row['team_abbr']} in week {row['week']}")
        continue
    depth_chart_postition = get_depth_chart_position(row['player_gsis_id'], row['week'])

    player_projections = get_player_year_projections(row['player_display_name'])

    
    if qb_info is not None:
        vector = {
            "player_name": row['player_display_name'],
            "fantay_points": calculate_fantasy_points(row['rec_touchdowns'], row['yards'], row['receptions']),
            "week": row['week'],
            "team": row['team_abbr'],
            "depth_chart_position": depth_chart_postition,
            "players_qb_name": qb_info['player_display_name'],
            "targets": row['targets'],
            "catches": row['receptions'],
            "yards": row['yards'],
            "avg_cushion": row['avg_cushion'],
            "avg_separation": row['avg_separation'],
            "avg_intended_air_yards": row['avg_intended_air_yards'],
            "percent_share_of_intended_air_yards": row['percent_share_of_intended_air_yards'],
            "avg_yac": row['avg_yac'],
            "avg_expected_yac": row['avg_expected_yac'],
            "avg_yac_above_expectation": row['avg_yac_above_expectation'],
            "qb_team": qb_info['team_abbr'],
            "qb_time_to_throw": qb_info['avg_time_to_throw'],
            "qb_completed_air_yards": qb_info['avg_completed_air_yards'],
            "qb_intended_air_yards": qb_info['avg_intended_air_yards'],
            "qb_air_yards_differential": qb_info['avg_air_yards_differential'],
            "qb_aggressiveness": qb_info['aggressiveness'],
            "qb_max_completed_air_distance": qb_info['max_completed_air_distance'],
            "qb_avg_air_yards_to_sticks": qb_info['avg_air_yards_to_sticks'],
            "qb_attempts": qb_info['attempts'],
            "qb_pass_yards": qb_info['pass_yards'],
            "qb_pass_touchdowns": qb_info['pass_touchdowns'],
            "qb_interceptions": qb_info['interceptions'],
            "qb_passer_rating": qb_info['passer_rating'],
            "qb_completions": qb_info['completions'],
            "qb_completion_percentage": qb_info['completion_percentage'],
            "qb_expected_completion_percentage": qb_info['expected_completion_percentage'],
            "qb_completion_percentage_above_expectation": qb_info['completion_percentage_above_expectation'],
            "QB gsis id": qb_info['player_gsis_id'],
            "RecTD": row['rec_touchdowns'], # Receiving Touchdowns from wr_ngs_df
            "Catch percentage": row['catch_percentage'], # Catch percentage from wr_ngs_df
            "WR gsis id": row['player_gsis_id'],
            
            
            #"Player","Team","23REC","23RecYDS","23RecTDS","23RushATT","23RushYDS","23RushTDS","FL","FPTS"
            "ProjRecTD_SZN": player_projections['23RecTDS'],  # Note the adjusted key
            "ProjRecYards_SZN": player_projections['23RecYDS'],
            "ProjRec_SZn": player_projections['23REC'],
            "ProjRushTD_SZN": player_projections['23RushTDS'],
            "ProjRushYDS_SZN": player_projections['23RushYDS'],
            "ProjRushATT_SZN": player_projections['23RushATT'],
            
        }
        feature_vectors.append(vector)


feature_vector_df = pd.DataFrame(feature_vectors)

# print(feature_vector_df.head())
feature_vector_df.to_csv("vectors/WR_feature_vector.csv", index=False)

print(f"Feature vectors created and saved to vectors/WR_feature_vector.csv")

