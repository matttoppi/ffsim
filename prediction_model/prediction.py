
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
    
    
    


import pandas as pd
import numpy as np

# Function to parse the week column into a binary representation
def parse_weeks(week_str):
    total_weeks = 18

    played_weeks = [int(w) for w in week_str.split(',')]
    return [1 if week in played_weeks else 0 for week in range(1, total_weeks + 1)]

def fix_weeks_passing():
    # this is the QB data
    # read from csv
    
    ngs_passing_data = pd.read_csv('datarepo/NGS/NGS_2023Passing_averaged.csv')


    # Apply the function to the week column
    ngs_passing_data['parsed_weeks'] = ngs_passing_data['week'].apply(parse_weeks)

    # Show the updated dataframe with parsed weeks
    ngs_passing_data[['player_display_name', 'week', 'parsed_weeks']]
    
    ngs_passing_data.head()
    
    # print(ngs_passing_data.head())
    
    return ngs_passing_data

def fix_weeks_receiving():
    # this is the WR and TE data
    
    # read from csv
    
    ngs_receiving_data = pd.read_csv('datarepo/NGS/NGS_2023Receiving_averaged.csv')

    # Apply the function to the week column
    ngs_receiving_data['parsed_weeks'] = ngs_receiving_data['week'].apply(parse_weeks)

    # Show the updated dataframe with parsed weeks
    ngs_receiving_data[['player_display_name', 'week', 'parsed_weeks']]
    
    # output just the first few rows to make sure it worked
    ngs_receiving_data.head()
    
    # print(ngs_receiving_data.head())
    
    return ngs_receiving_data
 


# Define functions to clean and prepare datasets
def clean_targets(filepath):
    targets_df = pd.read_csv(filepath)
    target_columns = ['week1Targets', 'week2Targets', 'week3Targts', 'week4Targets', 'week5Targets', 
                      'week6Targets', 'week7Targets', 'week8Targets', 'week9Targets', 'week10Targets', 
                      'week11Targets', 'week12Targets', 'week13Targets', 'week14Targets', 'week15Targets', 
                      'week16Targets', 'week17Targets', 'week18Targets']
    targets_df[target_columns] = targets_df[target_columns].apply(pd.to_numeric, errors='coerce')
    targets_df.fillna(0, inplace=True)
    return targets_df

def fix_weeks(file_path):
    df = pd.read_csv(file_path)
    df['parsed_weeks'] = df['week'].apply(lambda x: [1 if str(week) in x.split(',') else 0 for week in range(1, 19)])
    return df




def model():
    # get the WR data from the merged stats
    
    # for each WR in the data 
    
        # get the QB for next season 
        
        # for each week in the season
            # get the QB data for that week
            # get the depth chart for that week
            # get the targets for that week
            # get catches for that week
            # get yards for that week
            
            # adjust the stats based on the QB, depth chart
            # if the qb is good, the WR will get more targets
            # if the WR is higher on the depth chart, they will get more targets
            
            # use the adjusted stats to predict the WR's performance for that week
            # store the predictions in a new dataframe
            
    return predictions