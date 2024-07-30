import pandas as pd
import pickle
import os
from sklearn.base import BaseEstimator, TransformerMixin


class LowerQuartileImputer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        self.fill_values_ = X.quantile(0.25)
        return self

    def transform(self, X):
        return X.fillna(self.fill_values_)


class CustomUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if name == 'LowerQuartileImputer':
            return LowerQuartileImputer
        return super().find_class(module, name)


class RBPredictor:
    def __init__(self, models_dir='models'):
        self.models_dir = models_dir
        self.models = {}
        self.load_models()

    def load_models(self):
        """Load all RB models from the models directory."""
        for filename in os.listdir(self.models_dir):
            if filename.endswith('_RB_model.pkl'):
                model_path = os.path.join(self.models_dir, filename)
                with open(model_path, 'rb') as file:
                    model = CustomUnpickler(file).load()
                stat_name = filename.split('_')[0]  # e.g., 'rush_yards' from 'rush_yards_RB_model.pkl'
                self.models[stat_name] = model
        print("Available models:", list(self.models.keys()))


    def preprocess_input(self, input_data):
        """Preprocess the input data to match the format used during training."""
        # Convert dictionary to DataFrame
        df = pd.DataFrame([input_data])
        
        # Ensure all required columns are present
        required_columns = [
            'efficiency', 'percent_attempts_gte_eight_defenders', 'avg_time_to_los',
            'rush_attempts', 'expected_rush_yards', 'rush_yards_over_expected',
            'avg_rush_yards', 'rush_yards_over_expected_per_att', 'rush_pct_over_expected',
            'Oline_Rank', 'depth_chart_num', 'FPTS/G', 'BRKTKL'
        ]
        
        for col in required_columns:
            if col not in df.columns:
                df[col] = np.nan  # or some default value
        
        # Reorder columns to match the order used in training
        df = df[required_columns]
        
        return df

    def predict(self, player_data):
        """Make predictions for a single player."""
        processed_data = self.preprocess_input(player_data)
        predictions = {}
        for stat, model in self.models.items():
            predictions[stat] = model.predict(processed_data)[0]
        return predictions

    def predict_multiple(self, players_data):
        """Make predictions for multiple players."""
        results = {}
        for player_name, player_data in players_data.items():
            results[player_name] = self.predict(player_data)
        return results

    def get_feature_importance(self, stat):
        """Get feature importance for a specific stat if the model supports it."""
        if stat not in self.models:
            raise ValueError(f"No model found for stat: {stat}. Available stats: {list(self.models.keys())}")
        
        model = self.models[stat]
        
        # If it's a pipeline, get the last step (assuming it's the actual model)
        if hasattr(model, 'steps'):
            model = model.steps[-1][1]
        
        # If it's a MultiOutputRegressor, get the first estimator
        if hasattr(model, 'estimators_'):
            model = model.estimators_[0]
        
        if hasattr(model, 'feature_importances_'):
            return model.feature_importances_
        elif hasattr(model, 'coef_'):
            return model.coef_
        else:
            return None

import pandas as pd
import numpy as np

if __name__ == "__main__":
    predictor = RBPredictor()
    
    # Example player data
    example_player_data = {
        'efficiency': 0.5,
        'percent_attempts_gte_eight_defenders': 0.3,
        'avg_time_to_los': 2.5,
        'rush_attempts': 200,
        'expected_rush_yards': 900,
        'rush_yards_over_expected': 50,
        'avg_rush_yards': 4.5,
        'rush_yards_over_expected_per_att': 0.25,
        'rush_pct_over_expected': 5.5,
        'Oline_Rank': 10,
        'depth_chart_num': 1,
        'FPTS/G': 15.5,
        'BRKTKL': 20
    }
    
    print("Input Player Data:")
    for key, value in example_player_data.items():
        print(f"{key}: {value}")
    print("\n")

    predictions = predictor.predict(example_player_data)
    print("Predictions:")
    for stat, values in predictions.items():
        if stat == 'rush':
            print(f"  Rushing:")
            print(f"    Yards: {values[0]:.2f}")
            print(f"    Touchdowns: {values[1]:.2f}")
            print(f"    Attempts: {values[2]:.2f}")
            print(f"    Yards per Attempt: {values[3]:.2f}")
        elif stat == 'REC':
            print(f"  Receiving:")
            print(f"    Receptions: {values[0]:.2f}")
            print(f"    Touchdowns: {values[1]:.2f}")
            print(f"    Targets: {values[2]:.2f}")
            print(f"    Yards: {values[3]:.2f}")
        elif stat == 'YDS.1':
            print(f"  Total Yards from Scrimmage: {values[3]:.2f}")
    print("\n")

    print("Feature Importances:")
    feature_names = list(example_player_data.keys())
    for stat in predictor.models.keys():
        importance = predictor.get_feature_importance(stat)
        if importance is not None:
            print(f"  {stat}:")
            importances = sorted(zip(feature_names, importance), key=lambda x: x[1], reverse=True)
            for feature, imp in importances:
                print(f"    {feature}: {imp:.4f}")
        else:
            print(f"  No feature importance available for {stat}")
        print()