import random
import math
import numpy as np


class Player:
    def __init__(self, initial_data):
        self.sleeper_id = initial_data.get('player_id') or initial_data.get('sleeper_id')
        self.first_name = initial_data.get('first_name', '')
        self.last_name = initial_data.get('last_name', '')
        self.full_name = initial_data.get('full_name', '')
        self.name = self.full_name or f"{self.first_name} {self.last_name}".strip()
        self.position = str(initial_data.get('position') or 'UNKNOWN').upper()
        self.team = initial_data.get('team')
        self.age = initial_data.get('age')
        self.years_exp = initial_data.get('years_exp')
        self.depth_chart_order = initial_data.get('depth_chart_order')

        pff_data = initial_data.get('pff_projections')
        self.pff_projections = PFFProjections(pff_data) if pff_data else None
        self.projected_games_missed = float(initial_data.get('projected_games_missed', 0))
        self.injury_probability_game = float(initial_data.get('injury_probability_game', 0))
        self.current_injury_games_missed = 0
        self.total_games_missed_this_season = 0
        self.season_modifier = 1.0
        self.simulation_injury = None
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        self.value_1qb = float(initial_data.get('value_1qb', 0)) if initial_data.get('value_1qb') not in ['', None] else 0.0
        self.redraft_value = float(initial_data.get('redraft_value', 0)) if initial_data.get('redraft_value') not in ['', None] else 0.0
        
    def update_pff_projections(self, pff_data):
        if pff_data and isinstance(pff_data, dict):
            self.pff_projections = PFFProjections(pff_data)
        
    
    def to_dict(self):
        return {attr: getattr(self, attr) for attr in self.__dict__ if not attr.startswith('_')}
    
    def initialize_st_scorer(self, special_team_scorer):
        self.special_team_scorer = special_team_scorer
        
        

    def update_injury_status(self, week):
        if self.simulation_injury:
            if week < self.simulation_injury['return_week']:
                self.current_injury_games_missed += 1
                self.total_games_missed_this_season += 1
            elif week == self.simulation_injury['return_week']:
                self.simulation_injury = None
                self.current_injury_games_missed = 0
        else:
            injury_roll = random.random()
            if injury_roll < self.injury_probability_game:
                injury_duration = self.generate_injury_duration()
                partial_week = injury_duration % 1
                
                # Ensure partial_week_factor is at least 0.25
                partial_week_factor = max(0.25, 1 - partial_week)
                
                self.simulation_injury = {
                    'start_week': week,
                    'duration': math.ceil(injury_duration),
                    'return_week': week + math.ceil(injury_duration),
                    'partial_week_factor': partial_week_factor
                }
                self.current_injury_games_missed = 1
                self.total_games_missed_this_season += 1

    def generate_injury_duration(self):
        severity_weights = self.calculate_severity_weights()
        severity = random.choices(['Minor', 'Moderate', 'Major', 'Severe'], weights=severity_weights)[0]
        
        if severity == 'Minor':
            return random.uniform(0.1, 1.5)  # 0.1 to 1.5 weeks
        elif severity == 'Moderate':
            return random.uniform(1.5, 4)    # 1.5 to 4 weeks
        elif severity == 'Major':
            return random.uniform(4, 8)      # 4 to 8 weeks
        else:  # Severe
            return random.uniform(8, 16)     # 8 to 16 weeks

    def calculate_severity_weights(self):
        if self.projected_games_missed <= 1:
            return [0.7, 0.2, 0.08, 0.02]
        if self.projected_games_missed <= 2:
            return [0.5, 0.3, 0.15, 0.05]
        if self.projected_games_missed <= 4:
            return [0.3, 0.4, 0.2, 0.1]
        return [0.2, 0.3, 0.3, 0.2]

    def is_injured(self, week):
        return self.simulation_injury and self.simulation_injury['start_week'] < week < self.simulation_injury['return_week']

    def is_partially_injured(self, week):
        return self.simulation_injury and self.simulation_injury['start_week'] == week


    def update_injury_data(self, injury_data):
        self.projected_games_missed = float(injury_data.get('projected_games_missed', 0.5))
        self.injury_probability_game = injury_data.get('probability_of_injury_per_game')

    def normalize_injury_probability(self):
        if self.injury_probability_game is None or self.injury_probability_game == 0:
            self.injury_probability_game = 0.006  # Default value if no data available


    def print_player_short(self):
        has_pff = self.pff_projections is not None and hasattr(self.pff_projections, 'fantasy_points')
        print(f"{self.full_name} - {self.position.upper()} - {self.team} - 1QB: {self.value_1qb} - Redraft: {self.redraft_value} - Has PFF: {has_pff}")
        

    def calculate_special_team_score(self):
        if self.position.lower() in ['k', 'dst', 'def']:
            return self.special_team_scorer.get_player_score(self.full_name, self.position, self.team)
        return 0
    
    @staticmethod
    def clean_name(name):
        if name is None:
            return ''
        suffixes = [' jr', ' sr', ' ii', ' iii', ' iv']
        name = str(name).lower()
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.replace('.', '').replace("'", '').strip().title()
    
    def calculate_score(self, scoring_settings, week):
        if not self.pff_projections:
            return 0

        proj = self.pff_projections
        games = float(proj.games or 17)
        bye_week = int(proj.bye_week or 0)

        if week == bye_week:
            return 0

        # Calculate per-game averages
        avg_pass_yds = max(0, float(proj.pass_yds or 0) / games)
        avg_pass_td = max(0, float(proj.pass_td or 0) / games)
        avg_pass_int = max(0, float(proj.pass_int or 0) / games)
        avg_rush_yds = max(0, float(proj.rush_yds or 0) / games)
        avg_rush_td = max(0, float(proj.rush_td or 0) / games)
        avg_receptions = max(0, float(proj.recv_receptions or 0) / games)
        avg_rec_yds = max(0, float(proj.recv_yds or 0) / games)
        avg_rec_td = max(0, float(proj.recv_td or 0) / games)

        # Adjust log-normal parameters
        shift_amount = 0.1
        adjustment_factor = 0.8

        # Check for partial week injury
        partial_week_factor = 1.0
        if self.simulation_injury and self.simulation_injury['start_week'] == week:
            partial_week_factor = self.simulation_injury['partial_week_factor']

        # Generate stats using log-normal distribution
        pass_yds = self.log_normal(avg_pass_yds * partial_week_factor, avg_pass_yds * 0.3, shift_amount, adjustment_factor)
        rush_yds = self.log_normal(avg_rush_yds * partial_week_factor, avg_rush_yds * 0.3, shift_amount, adjustment_factor)
        
        # Adjust receptions for partial week
        full_receptions = round(self.log_normal(avg_receptions, avg_receptions * 0.3, shift_amount, adjustment_factor))
        receptions = max(0, round(full_receptions * partial_week_factor))

        # Calculate receiving yards based on adjusted receptions
        avg_yards_per_reception = avg_rec_yds / avg_receptions if avg_receptions > 0 else 10
        yards_per_reception = self.log_normal(avg_yards_per_reception, avg_yards_per_reception * 0.2, shift_amount, adjustment_factor)
        rec_yds = max(0, receptions * yards_per_reception)

        # Adjust touchdown probabilities for partial week
        adj_avg_pass_td = avg_pass_td * partial_week_factor
        adj_avg_rush_td = avg_rush_td * partial_week_factor
        adj_avg_rec_td = avg_rec_td * partial_week_factor

        # Generate touchdowns using adjusted Poisson distribution
        pass_td = max(0, np.random.poisson(adj_avg_pass_td))
        rush_td = max(0, np.random.poisson(adj_avg_rush_td))
        rec_td = max(0, np.random.poisson(adj_avg_rec_td))

        # Interceptions (using Poisson distribution, adjusted for partial week)
        pass_int = max(0, np.random.poisson(avg_pass_int * partial_week_factor))

        # Calculate score based on league scoring settings
        score = (
            pass_yds * scoring_settings.pass_yd +
            pass_td * scoring_settings.pass_td +
            pass_int * scoring_settings.pass_int +
            rush_yds * scoring_settings.rush_yd +
            rush_td * scoring_settings.rush_td +
            rec_yds * scoring_settings.rec_yd +
            rec_td * scoring_settings.rec_td +
            receptions * (scoring_settings.te_rec if self.position == 'TE' else scoring_settings.rec)
        )

        # Apply season modifier
        score *= self.season_modifier

        # Apply a very gentle cap to limit extreme outliers
        max_score = 50
        if score > max_score:
            excess = score - max_score
            score = max_score + (excess * 0.1)  # Allow scores to exceed max_score, but at a much slower rate

        self.record_weekly_score(score)

        return score

    def log_normal(self, mean, sigma, shift, adjustment_factor):
        if mean <= 0 or sigma <= 0:
            return 0
        try:
            mu = math.log(mean**2 / math.sqrt(mean**2 + sigma**2))
            sigma = math.sqrt(math.log(1 + (sigma**2 / mean**2))) * adjustment_factor
            return max(0, random.lognormvariate(mu, sigma)) + shift
        except (ValueError, ZeroDivisionError):
            return 0
    
    def reset_injury_status(self):
        self.simulation_injury = None
        self.current_injury_games_missed = 0
        self.total_games_missed_this_season = 0
        
    def create_players_season_modifiers(self):
        # Base modifier starts at 1 (no modification)
        modifier = 1.0

        # Age modifier
        if self.age is not None:
            if self.age < 25:
                # Younger players have higher boom potential
                modifier += random.uniform(0, 0.15)  # Reduced from 0.25
            elif self.age > 28:
                # Older players have higher bust potential
                modifier -= random.uniform(0, 0.05)  # Reduced from 0.1

        # Injury proneness modifier
        if hasattr(self, 'injury_probability_game') and self.injury_probability_game is not None:
            if self.injury_probability_game > 0.1:  # Assuming 0.1 is a high injury probability
                modifier -= random.uniform(0, 0.05)  
            elif self.injury_probability_game < 0.05:  # Assuming 0.05 is a low injury probability
                modifier += random.uniform(0, 0.03) 

        # Experience modifier
        if self.years_exp is not None:
            if self.years_exp == 1 or self.years_exp == 2:
                # Second and third year players have higher boom potential
                modifier += random.uniform(0, 0.05)  # Reduced from 0.1

        # Depth chart modifier
        if self.depth_chart_order is not None:
            if self.depth_chart_order > 1:
                # Players lower on the depth chart have a chance for a significant boom
                boom_chance = 0.03 + (0.02 * (self.depth_chart_order - 1))  # Reduced from 0.05 + 0.05
                if random.random() < boom_chance:
                    boom_factor = random.uniform(1.3, 3)  # Reduced from 1.5 to 5
                    modifier *= boom_factor
                else:
                    # Non-boom scenario for non-starters: higher variance
                    modifier *= random.uniform(0.7, 1.3)  # Reduced from 0.5 to 1.5
            else:
                # Starters (depth_chart_order == 1) have more conservative modifiers
                modifier *= random.uniform(0.9, 1.1)  # Reduced from 0.8 to 1.2

        # Random factor for unpredictability
        modifier += random.uniform(-0.03, 0.03)  # Reduced from -0.05 to 0.05

        # Ensure the modifier doesn't go below 0.7 for non-boom scenarios
        if modifier < 1.3:
            modifier = max(0.7, modifier)  # Increased minimum from 0.5 to 0.7

        # Cap the modifier at 3 for extreme cases
        modifier = min(modifier, 3)  # Reduced from 5 to 3

        # Override probability of injury
        # 0.5% chance of season ending injury (reduced from 1%)
        if random.random() < 0.005:
            self.season_modifier = 0
            return

        # 2% chance of being a bust (modifier = 0.7) (reduced from 3% and 0.5)
        if random.random() < 0.02:
            modifier = 0.7

        self.season_modifier = modifier
        
        
        
        
    def reset_season_stats(self):
        """Reset the season statistics. Call this at the start of each new simulation."""
        self.total_simulated_points = 0
        self.total_simulated_games = 0

    def record_weekly_score(self, score):
        """Record a weekly score for the current season."""
        self.total_simulated_points += score
        self.total_simulated_games += 1

    def get_average_weekly_score(self):
        """Get the current season's average weekly score."""
        if self.total_simulated_games > 0:
            return self.total_simulated_points / self.total_simulated_games
        return 0



    
class PFFProjections:
    def __init__(self, projection_data):
        if isinstance(projection_data, PFFProjections):
            projection_data = projection_data.__dict__
        fields = {
            'bye_week': 'byeWeek',
            'games': 'games',
            'fantasy_points': 'fantasyPoints',
            'pass_yds': 'passYds',
            'pass_td': 'passTd',
            'pass_int': 'passInt',
            'rush_yds': 'rushYds',
            'rush_td': 'rushTd',
            'recv_receptions': 'recvReceptions',
            'recv_yds': 'recvYds',
            'recv_td': 'recvTd',
        }
        for attribute, key in fields.items():
            setattr(self, attribute, projection_data.get(key, projection_data.get(attribute)))

    def __str__(self):
        return f"PFF Projections: {self.fantasy_points} points over {self.games} games"

    def __bool__(self):
        return self.fantasy_points is not None
