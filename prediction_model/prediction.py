
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




import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.metrics import mean_squared_error
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from catboost import CatBoostRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
# Make sure to import other necessary classes and functions as well


import numpy as np
import matplotlib.pyplot as plt

from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
import pickle


def scatter_plot_with_line_of_perfect_fit(actual, predicted, model_name):
    plt.figure(figsize=(10, 6))
    plt.scatter(actual, predicted, alpha=0.3)
    plt.xlabel('Actual')
    plt.ylabel('Predicted')
    plt.title(f'{model_name} Predictions vs. Actual')
    max_val = max(actual.max(), predicted.max())
    min_val = min(actual.min(), predicted.min())
    plt.plot([min_val, max_val], [min_val, max_val], 'k--')  # Line of perfect fit
    plt.grid(True)
    plt.show()

def plot_residuals(actual, predicted, model_name):
    residuals = actual - predicted
    plt.figure(figsize=(10, 6))
    plt.scatter(actual, residuals, alpha=0.5)
    plt.xlabel('Actual')
    plt.ylabel('Residuals')
    plt.title(f'{model_name} Residuals')
    plt.axhline(y=0, color='r', linestyle='--')
    plt.grid(True)
    plt.show()

def plot_error_density(actual, predicted, model_name):
    errors = predicted - actual
    plt.figure(figsize=(10, 6))
    plt.hist(errors, bins=30, density=True, alpha=0.6, color='b')
    plt.xlabel('Error')
    plt.ylabel('Density')
    plt.title(f'Error Density for {model_name}')
    plt.grid(True)
    plt.show()


def plot_error_boxplots(all_errors, model_names):
    plt.figure(figsize=(12, 8))
    plt.boxplot(all_errors, labels=model_names, showmeans=True)
    plt.xlabel('Model')
    plt.ylabel('Error')
    plt.title('Model Error Comparison')
    plt.grid(True, axis='y')
    plt.show()
    
import matplotlib.pyplot as plt
import pickle

def plot_model_errors(rmses):
    """
    Plots a bar chart of RMSE values for each model.

    Parameters:
    - rmses: A dictionary with model names as keys and RMSE values as values.
    """
    model_names = list(rmses.keys())
    errors = list(rmses.values())

    plt.figure(figsize=(14, 7))
    bars = plt.bar(model_names, errors, color='skyblue')
    plt.xlabel('Model', fontsize=14)
    plt.ylabel('RMSE', fontsize=14)
    plt.xticks(rotation=45, ha="right", fontsize=12)
    plt.yticks(fontsize=12)
    plt.title('Model Error Comparison (RMSE)', fontsize=16)

    # Adding the text labels on the bars
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval, round(yval, 2), va='bottom')  # va: vertical alignment

    plt.tight_layout()
    plt.show()



def predict_with_best_models(X_new, best_models_per_feature, trained_models):
    predictions = pd.DataFrame(index=X_new.index, columns=best_models_per_feature.keys())

    for feature, (model_name, _) in best_models_per_feature.items():
        model = trained_models[model_name]
        predictions[feature] = model.predict(X_new)[:, feature_names.get_loc(feature)]

    return predictions




def train_and_evaluate_model(model, X_train, y_train, X_test, y_test):
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    rmses_per_feature = np.sqrt(mean_squared_error(y_test, y_pred, multioutput='raw_values'))
    return rmses_per_feature

class LowerQuartileImputer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        # Calculate the 25th percentile (lower quartile) directly with numpy
        self.fill_values_ = np.nanquantile(X, 0.25, axis=0)
        return self

    def transform(self, X):
        # Use numpy's functionality to fill NaN values with the calculated quartiles
        # np.where is used to replace NaN values with the corresponding fill value
        for i in range(X.shape[1]):
            X[:, i] = np.where(np.isnan(X[:, i]), self.fill_values_[i], X[:, i])
        return X

if __name__ == "__main__":
    file_path = 'vectors/WR_feature_vector.csv'
    
    
    def load_and_preprocess_data(file_path):
        data = pd.read_csv(file_path)
        data = data.map(replace_values)
        data = data.apply(pd.to_numeric, errors='coerce')
        
        return data

    def replace_values(val):
        if isinstance(val, str):
            stripped_val = val.strip()
            if stripped_val == 'NA':
                return 0
            elif stripped_val.lower() == 'unknown':
                return -1
        return val

    data = load_and_preprocess_data(file_path)
    
    #TODO: refine the features and labels to be used in the model. What data do we have and what do we want to predict?
    # maybe we can add ADP/ECR data to the features to see if that helps the model
    
    
    data.columns = data.columns.str.strip()
    # Define features and labels ProjRecTD_SZN,ProjRecYards_SZN,ProjRec_SZn,ProjRushTD_SZN,ProjRushYDS_SZN,ProjRushATT_SZN
    X = data[['qb_time_to_throw', 'qb_completed_air_yards', 'qb_intended_air_yards', 'qb_air_yards_differential', 'qb_aggressiveness', 'qb_max_completed_air_distance', 'qb_avg_air_yards_to_sticks', 'qb_attempts', 'qb_pass_yards', 'qb_pass_touchdowns', 'qb_interceptions', 'qb_passer_rating', 'qb_completions', 'qb_completion_percentage', 'qb_expected_completion_percentage', 'qb_completion_percentage_above_expectation', 'avg_cushion', 'avg_separation','Catch percentage', 'avg_yac', 'depth_chart_position', 'ProjRecTD_SZN', 'ProjRecYards_SZN', 'ProjRec_SZn', 'ProjRushTD_SZN', 'ProjRushYDS_SZN', 'ProjRushATT_SZN']]
    y = data[['catches', 'yards', 'RecTD','targets']]

    # Splitting dataset into training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.12, random_state=42)
    
    imputer = SimpleImputer(strategy='median')
    X_train_imputed = imputer.fit_transform(X_train)
    X_test_imputed = imputer.transform(X_test)

    # Define your models, integrating LowerQuartileImputer in each pipeline
    models = {
        'Linear Regression': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(LinearRegression())),
        ]),
        'Ridge': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(Ridge())),
        ]),
        'Lasso': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(Lasso())),
        ]),
        'ElasticNet': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(ElasticNet())),
        ]),
        'Random Forest': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', RandomForestRegressor(n_estimators=1000, max_depth=None)),
        ]),
        'Gradient Boosting': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(GradientBoostingRegressor(n_estimators=500, learning_rate=0.01))),
        ]),
        'XGBoost': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', XGBRegressor(n_estimators=1000, learning_rate=0.01, max_depth=6, verbosity=0)),
        ]),
        'LightGBM': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(LGBMRegressor(num_leaves=31, learning_rate=0.01, n_estimators=1000, verbose=-1))),
        ]),
        'CatBoost': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', CatBoostRegressor(iterations=1000, learning_rate=0.01, depth=6, loss_function='MultiRMSE', verbose=0)),
        ]),
        'SVR': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(SVR())),
        ]),
        'MLPRegressor': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', MultiOutputRegressor(MLPRegressor(hidden_layer_sizes=(100, 100), max_iter=1000))),
        ]),
        'KNeighbors': Pipeline([
            ('imputer', LowerQuartileImputer()),
            ('model', KNeighborsRegressor()),
        ]),
    }

    # Update models to include an imputation step
    for name, model in models.items():
        models[name] = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),  # Apply imputation
            ('model', model),
        ])

    # Train and evaluate models
    model_rmses = {}
    for name, model_pipeline in models.items():
        print(f'Training {name}...')
        rmses_per_feature = train_and_evaluate_model(model_pipeline, X_train, y_train, X_test, y_test)
        model_rmses[name] = dict(zip(y.columns, rmses_per_feature))

    best_models_per_feature = {}
    for feature in y.columns:
        best_model = min(model_rmses, key=lambda x: model_rmses[x][feature])
        best_rmse = model_rmses[best_model][feature]
        best_models_per_feature[feature] = (best_model, best_rmse)


    std_devs = y.std()
    means = y.mean()
    
    # Display the best model for each feature and compare RMSE to standard deviation
    for feature, (model, rmse) in best_models_per_feature.items():
        std_dev = std_devs[feature]
        print(f"\nBest model for {feature}: {model} with RMSE = {rmse:.4f}")
        print(f"Standard Deviation of {feature}: {std_dev:.4f}")
        print(f"RMSE / Standard Deviation: {rmse / std_dev:.4f}")
        print(f"RSME / Mean: {rmse / means[feature]:.4f}\n")
        
        
    # save the best models to files to be used later
    for feature, (model, rmse) in best_models_per_feature.items(): # for each feature
        models[model].fit(X, y) # fit the model on the entire dataset
        with open(f'models/{feature}_WR_model.pkl', 'wb') as file:
            pickle.dump(models[model], file) 
        
        
        
# for utilizing the models later

# we can find the average of the x data for the QBs and use that to predict the targets for the WRs
