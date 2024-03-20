import pandas as pd
import json

# Load RB-specific datasets
rb_projections_df = pd.read_csv("datarepo/projections/23RB_proj.csv") # projections for 2023
rb_ngs_df = pd.read_csv("datarepo/NGS/NGS_2023Rushing.csv") # NGS data for 2023
oline_rankings_df = pd.read_csv("datarepo/Special/oline_ranks_23.csv") # O-line rankings for 2023

# Load other datasets as needed (e.g., depth charts, overall stats)
depth_chart_df = pd.read_csv("datarepo/Special/2023FULLDEPTHCHART_FILTERED.csv") # depth chart for 2023
overall_stats_df = pd.read_csv("datarepo/merged_nfl_players_stats.csv") # overall stats for all players

with open("datarepo/players.json") as f:
    players_json = json.load(f)
players_df = pd.DataFrame(players_json)


# for each dataframe 
    # print head and colums

# array of df names
names = ["rb_projections_df", "rb_ngs_df", "oline_rankings_df", "depth_chart_df", "overall_stats_df", "players_df"]
    
x = 0
for df in [rb_projections_df, rb_ngs_df, oline_rankings_df, depth_chart_df, overall_stats_df, players_df]:
    print(f"Dataframe: {names[x]}")
    print(df.head())
    print(df.columns)
    print("\n\n")
    x += 1
    
    
#drop any row where the week is 0 as a int64
rb_ngs_df = rb_ngs_df[rb_ngs_df["week"] != 0]
    
# NGS data df: efficiency,percent_attempts_gte_eight_defenders,avg_time_to_los,rush_attempts,rush_yards,expected_rush_yards,rush_yards_over_expected,avg_rush_yards,rush_yards_over_expected_per_att,rush_pct_over_expected,rush_touchdowns,player_gsis_id,player_first_name,player_last_name,player_jersey_number,player_short_name,
# projcection df : "Player","Team","23REC","23RecYDS","23RecTDS","23RushATT","23RushYDS","23RushTDS","FL","FPTS"
# oline df : Rank,Team,Abbreviation
# depth df :season,club_code,week,game_type,position_depth_num,last_name,first_name,football_name,formation,gsis_id,jersey_number,position,elias_id,depth_position,full_name
# merged data df: Player,PassTD,INT,SACKS,RecTD,RUSH_ATT,RushTD,RUSH_RECEIVE_TD,TD.1,LG,20+,FL,FPTS,FPTS/G,ROST,AIR/A,PKT TIME,SK,KNCK,HRRY,BLITZ,POOR,RZ ATT,RTG,CMP,PassATT,PCT,PassYDS,Y/A,Y/ATT,YBCON,YBCON/ATT,YACON/ATT,TK LOSS,TK LOSS YDS,LNG TD,YACON.1,RushATT,RushYDS,YBC,YBC/R,AIR/R,YAC,YAC/R,YACON/R,% TM,CATCHABLE,RecYDS,Y/R,AIR,DROP,YACON,BRKTKL,LNG,RZ TGT,REC,TGT,10+ YDS,20+ YDS,30+ YDS,40+ YDS,50+ YDS,Rank,G,Pos,Team,week1Targets,week2Targets,week3Targts,week4Targets,week5Targets,week6Targets,week7Targets,week8Targets,week9Targets,week10Targets,week11Targets,week12Targets,week13Targets,week14Targets,week15Targets,week16Targets,week17Targets,week18Targets,TTL,AVG


# Adjusted function signature to include 'week'
def get_oline_rank(team, week, oline_rankings_df):
    try:
        team_oline_rank = oline_rankings_df[(oline_rankings_df["Abbreviation"] == team)].iloc[0]["Rank"]
        # print(team_oline_rank)
        return team_oline_rank
    except:
        # print("No Oline Rank")
        return None

# Adjust the lambda function to pass the week as well

def get_depth_chart_number(week, club_code, gsis, position, depth_chart_df):
    try:
        # Ensure the data types of the columns match those of the arguments being passed, especially 'week'
        depth_chart_df['week'] = depth_chart_df['week'].astype(str)  # Convert to string if necessary
        week = str(week)  # Ensure 'week' is also a string

        # Now using 'gsis' in the query instead of 'player'
        depth_chart_num = depth_chart_df[
            (depth_chart_df["week"] == week) & 
            (depth_chart_df["club_code"] == club_code) & 
            (depth_chart_df["gsis_id"] == gsis) & 
            (depth_chart_df["depth_position"] == position)
        ].iloc[0]["position_depth_num"]

        print(depth_chart_num)  # For debugging
        return depth_chart_num
    except Exception as e:  # Catching the exception can help identify the issue
        # print(f"No Depth Chart Number found: {e}")  # Print the exception to identify the issue
        return "-1"


# wanted_features = ["Name", "Team", "Position", "Age", "Height", "Weight", "Week", "Efficiency", "Percent_Attempts_GTE_Eight_Defenders", "Avg_Time_To_LOS", "Rush_Attempts", "Rush_Yards", "Expected_Rush_Yards", "Rush_Yards_Over_Expected", "Avg_Rush_Yards", "Rush_Yards_Over_Expected_Per_Att", "Rush_Pct_Over_Expected", "Rush_Touchdowns", "Oline_Rank", "Depth_Chart_Number", "Proj23REC", "Proj23RecYDS", "Proj23RecTDS", "Proj23RushATT", "Proj23RushYDS", "Proj23RushTDS", "FL"] # feature list


# start with the NGS data 

feature_df = rb_ngs_df[["player_gsis_id", "player_first_name", "player_last_name", "player_jersey_number", "player_short_name", "team_abbr", "week", "efficiency", "percent_attempts_gte_eight_defenders", "avg_time_to_los", "rush_attempts", "rush_yards", "expected_rush_yards", "rush_yards_over_expected", "avg_rush_yards", "rush_yards_over_expected_per_att", "rush_pct_over_expected", "rush_touchdowns"]]
# assert that the player_short_name is never empty  
print("Added NGS data")

print(feature_df["week"].dtype)


# drop any row where the week is 0 as a str
feature_df = feature_df[feature_df["week"] != 0]



# now add the projections
# left is the NGS data, right is the projections
feature_df = rb_ngs_df.merge(rb_projections_df, how="left", left_on="player_display_name", right_on="Player")
# rename the columns we just added to have proj in front of them
print("Added Projections")

# now add the oline rankings
feature_df["Oline_Rank"] = feature_df.apply(lambda x: get_oline_rank(x["team_abbr"], x["week"], oline_rankings_df), axis=1)
# assert that the player_short_name is never empty
print("Added Oline Rankings")


# Example adjustment for team_abbr format (if needed)
# This step assumes 'team_abbr' needs to match 'club_code' format in 'depth_chart_df'
# If 'team_abbr' is already in the correct format, you can skip this step


feature_df["depth_chart_num"] = feature_df.apply(lambda x: get_depth_chart_number(
    str(x["week"]),  # Ensuring 'week' is a string
    x["team_abbr"],
    x["player_gsis_id"],
    "RB",  # Assuming this is correct and matches depth_chart_df
    depth_chart_df), axis=1)



# Regex to match common Roman numerals (simplified for common cases like I, II, III, IV, V, etc.)
regex_pattern = r'\s?(?:I{1,3}|IV|V|VI{0,3})$'

# Remove Roman numerals from the "Player" column
overall_stats_df["Player"] = overall_stats_df["Player"].str.replace(regex_pattern, '', regex=True)



feature_df = feature_df.merge(overall_stats_df, how="left", left_on="player_display_name", right_on="Player")


# save the feature_df to a csv
feature_df.to_csv("vectors/RB_feature_vector.csv", index=False)
print("Saved feature_df to csv")