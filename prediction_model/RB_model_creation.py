import pandas as pd
import numpy as np
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
import matplotlib.pyplot as plt
import pickle

class RBModelCreator:
    def __init__(self, file_path='vectors/RB_feature_vector.csv'):
        self.file_path = file_path
        self.data = None
        self.X = None
        self.y = None
        self.models = None
        self.best_models_per_feature = {}
        
        
    def check_nan_values(self):
        print("NaN values in features (X):")
        print(self.X.isna().sum())
        print("\nNaN values in target variables (y):")
        print(self.y.isna().sum())
        print("\nTotal rows:", len(self.X))

    def load_and_preprocess_data(self):
        self.data = pd.read_csv(self.file_path)
        print(f"Initial data shape: {self.data.shape}")

        self.data = self.data.map(self.replace_values)
        self.data = self.data.apply(pd.to_numeric, errors='coerce')
        self.data.columns = self.data.columns.str.strip()
        print(f"Data shape after initial preprocessing: {self.data.shape}")

        # Define features for RBs
        feature_columns = [
            'efficiency', 'percent_attempts_gte_eight_defenders', 'avg_time_to_los',
            'rush_attempts', 'expected_rush_yards', 'rush_yards_over_expected',
            'avg_rush_yards', 'rush_yards_over_expected_per_att', 'rush_pct_over_expected',
            'Oline_Rank', 'depth_chart_num', 'FPTS/G', 'BRKTKL'
        ]
        
        # Define target variables for RBs
        target_columns = ['rush_yards', 'rush_touchdowns', 'REC_x', 'YDS.1']

        # Select only the required columns
        self.data = self.data[feature_columns + target_columns]
        print(f"Data shape after selecting columns: {self.data.shape}")

        # Print info about NaN values before imputation
        print("NaN values before imputation:")
        print(self.data.isna().sum())

        # Impute missing values
        for column in self.data.columns:
            if self.data[column].isna().sum() > 0:
                if self.data[column].dtype == 'object':
                    self.data[column].fillna(self.data[column].mode()[0], inplace=True)
                else:
                    self.data[column].fillna(self.data[column].median(), inplace=True)

        print("NaN values after imputation:")
        print(self.data.isna().sum())

        self.X = self.data[feature_columns]
        self.y = self.data[target_columns]

        print(f"X type: {type(self.X)}, y type: {type(self.y)}")
        print(f"Shape of X: {self.X.shape}, Shape of y: {self.y.shape}")

        self.check_nan_values()

    @staticmethod
    def replace_values(val):
        if isinstance(val, str):
            stripped_val = val.strip()
            if stripped_val == 'NA':
                return 0
            elif stripped_val.lower() == 'unknown':
                return -1
        return val

    def setup_models(self):
        self.models = {
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

    def train_and_evaluate(self):
        X_train, X_test, y_train, y_test = train_test_split(self.X, self.y, test_size=0.12, random_state=42)
        
        model_rmses = {}
        for name, model_pipeline in self.models.items():
            print(f'Training {name}...')
            rmses_per_feature = self.train_and_evaluate_model(model_pipeline, X_train, y_train, X_test, y_test)
            model_rmses[name] = dict(zip(self.y.columns, rmses_per_feature))

        for feature in self.y.columns:
            best_model = min(model_rmses, key=lambda x: model_rmses[x][feature])
            best_rmse = model_rmses[best_model][feature]
            self.best_models_per_feature[feature] = (best_model, best_rmse)

    @staticmethod
    def train_and_evaluate_model(model, X_train, y_train, X_test, y_test):
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        if isinstance(y_test, pd.DataFrame):
            y_test = y_test.values
        if isinstance(y_pred, pd.DataFrame):
            y_pred = y_pred.values
        rmses_per_feature = np.sqrt(mean_squared_error(y_test, y_pred, multioutput='raw_values'))
        return rmses_per_feature

    def display_results(self):
        std_devs = self.y.std()
        means = self.y.mean()
        
        for feature, (model, rmse) in self.best_models_per_feature.items():
            std_dev = std_devs[feature]
            print(f"\nBest model for {feature}: {model} with RMSE = {rmse:.4f}")
            print(f"Standard Deviation of {feature}: {std_dev:.4f}")
            print(f"RMSE / Standard Deviation: {rmse / std_dev:.4f}")
            print(f"RMSE / Mean: {rmse / means[feature]:.4f}\n")

    def save_best_models(self):
        for feature, (model, _) in self.best_models_per_feature.items():
            self.models[model].fit(self.X, self.y)
            with open(f'models/{feature}_RB_model.pkl', 'wb') as file:
                pickle.dump(self.models[model], file)

    def run(self):
        self.load_and_preprocess_data()
        self.check_nan_values()
        self.setup_models()
        self.train_and_evaluate()
        self.display_results()
        self.save_best_models()

class LowerQuartileImputer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        self.fill_values_ = X.quantile(0.25)
        return self

    def transform(self, X):
        return X.fillna(self.fill_values_)

if __name__ == "__main__":
    rb_model_creator = RBModelCreator()
    rb_model_creator.run()