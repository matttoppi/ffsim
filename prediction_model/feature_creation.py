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
    
    


# Load datasets
targets_df = pd.read_csv("datarepo/Special/23TargetLeaders.csv")
qb_ngs_df = pd.read_csv("datarepo/NGS/NGS_2023Passing.csv")
wr_ngs_df = pd.read_csv("datarepo/NGS/NGS_2023Receiving.csv")
depth_chart_df = pd.read_csv("datarepo/Special/2023FULLDEPTHCHART_FILTERED.csv")
overall_stats_df = pd.read_csv("datarepo/merged_nfl_players_stats.csv")

print(f"Loaded in datasets")

with open("datarepo/players.json") as f:
    players_json = json.load(f)
players_df = pd.DataFrame(players_json)

# Adjust column names by stripping whitespace and replacing spaces with underscores
wr_ngs_df.columns = wr_ngs_df.columns.str.strip().str.replace(' ', '_')
qb_ngs_df.columns = qb_ngs_df.columns.str.strip().str.replace(' ', '_')
depth_chart_df.columns = depth_chart_df.columns.str.strip().str.replace(' ', '_')

print(f"Adjusted column names")

# Parse weeks and exclude week 0
def parse_weeks(weeks_str):
    weeks_str = str(weeks_str)
    return [int(week) for week in weeks_str.split(',') if int(week) != 0]

qb_ngs_df['weeks_played'] = qb_ngs_df['week'].apply(parse_weeks) # Parse weeks played


qb_ngs_df['week'] = qb_ngs_df['week'].astype(int)  # Convert to int if necessary
qb_ngs_df = qb_ngs_df[qb_ngs_df['week'] != 0]
wr_ngs_df['week'] = wr_ngs_df['week'].astype(int)  # Convert to int if necessary
wr_ngs_df = wr_ngs_df[wr_ngs_df['week'] != 0]


# drop week 0 from the depth chart dataframe
depth_chart_df = depth_chart_df[depth_chart_df['week'] != '0']

# Prepare the depth chart DataFrame
depth_chart_df['week'] = depth_chart_df['week'].astype(str)
depth_chart_df['gsis_id'] = depth_chart_df['gsis_id'].astype(str)


# Use position_depth_num for depth chart position
depth_chart_df_simplified = depth_chart_df[['gsis_id', 'week', 'club_code', 'position_depth_num']]

# Merge WR/TE DataFrame with depth chart DataFrame
wr_ngs_df['week'] = wr_ngs_df['week'].astype(str)
wr_ngs_df = pd.merge(wr_ngs_df, depth_chart_df_simplified, how='left', left_on=['player_gsis_id', 'week', 'team_abbr'], right_on=['gsis_id', 'week', 'club_code'])


# Example for WR/TE NGS stats (adjust according to your needs)
wr_ngs_df = wr_ngs_df[['player_gsis_id', 'week', 'team_abbr', 'avg_cushion', 'avg_separation',
                       'avg_intended_air_yards', 'percent_share_of_intended_air_yards',
                       'receptions', 'targets', 'yards', 'rec_touchdowns', 'avg_yac',
                       'avg_expected_yac', 'avg_yac_above_expectation', 'player_display_name', 'catch_percentage']]

# save depth chart dataframe for review

# Example function to find a QB for a WR/TE for a given week
def find_qb_for_receiver(week, team):
    filtered_qbs = qb_ngs_df[(qb_ngs_df['team_abbr'] == team) & (qb_ngs_df['weeks_played'].apply(lambda weeks: int(week) in weeks))]
    if not filtered_qbs.empty:
        return filtered_qbs.iloc[0]
    else:
        # print(f"No QB found for team {team} in week {week}")  # Debug print
        return None
    
    
def get_depth_chart_position(player_gsis_id, week, team):
    # Ensure inputs are properly formatted
    player_gsis_id = player_gsis_id.strip()
    week_str = str(week).strip()
    team = team.strip()

    # Filter the DataFrame based on conditions
    position_depth_num = depth_chart_df[
        (depth_chart_df['gsis_id'].str.strip() == player_gsis_id) &
        (depth_chart_df['week'].astype(str).str.strip() == week_str) &
        (depth_chart_df['club_code'].str.strip() == team)
    ]['position_depth_num']

    # Return the position depth number if available, else return 'Unknown'
    if not position_depth_num.empty:
        return position_depth_num.iloc[0]
    else:
        return 'Unknown'
    
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


# $print column names of the overall stats dataframe
# print(overall_stats_df.columns)
# print(wr_ngs_df.columns)
# print(qb_ngs_df.columns)
# print(depth_chart_df.columns)

print(f"Dataframes are cleaned and ready for feature creation")

# Create the feature vector dataframe
feature_vectors = []
# After merging, accessing depth_team and depth_position
print(f"Creating feature vectors...")
for index, row in wr_ngs_df.iterrows(): # for each receiver for each week
    # if week is 0 then skip
    if row['week'] == 0:
        continue
    qb_info = find_qb_for_receiver(row['week'], row['team_abbr'])
    depth_chart_postition = get_depth_chart_position(row['player_gsis_id'], row['week'], row['team_abbr'])



    
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
        }
        feature_vectors.append(vector)


feature_vector_df = pd.DataFrame(feature_vectors)

# print(feature_vector_df.head())
feature_vector_df.to_csv("vectors/WR_feature_vector.csv", index=False)

print(f"Feature vectors created and saved to temp/feature_vector.csv")

