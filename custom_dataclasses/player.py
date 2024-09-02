import random
import math
from custom_dataclasses.loaders.InjuryDataLoader import InjuryDataLoader
import numpy as np  # Add this import




class Player:
    def __init__(self, initial_data):

        self.sleeper_id = initial_data.get('player_id') or initial_data.get('sleeper_id')
        self.first_name = initial_data.get('first_name', '')
        self.last_name = initial_data.get('last_name', '')
        self.full_name = initial_data.get('full_name', '')
        self.name = self.full_name or f"{self.first_name} {self.last_name}".strip()
        self.position = initial_data.get('position', '')
        self.position = initial_data.get('position', '')
        if not self.position:
            self.position = 'UNKNOWN'
        self.team = initial_data.get('team')
        self.age = initial_data.get('age')
        self.years_exp = initial_data.get('years_exp')
        self.college = initial_data.get('college')
        self.depth_chart_order = initial_data.get('depth_chart_order')
        self.injury_status = initial_data.get('injury_status')
        self.weight = initial_data.get('weight')
        self.height = initial_data.get('height')
        self.number = initial_data.get('number')
        self.status = initial_data.get('status')
        self.birth_date = initial_data.get('birth_date')
        self.on_fantasy_team = False
        # Injury data
        self.career_injuries = initial_data.get('career_injuries', 0)
        self.injury_risk = initial_data.get('injury_risk', 'Medium')
        
        self.pff_projections = initial_data.get('pff_projections', {})
        
        
        self.current_injury_games_missed = 0
        self.total_games_missed_this_season = 0
        self.season_modifier = 1.0
        
        self.never_miss_game_flag = False

        
        
        
    
        # Injury data with careful defaulting
        self.career_injuries = initial_data.get('career_injuries', 0)
        self.injury_risk = initial_data.get('injury_risk', 'Unknown')
        self.durability = initial_data.get('durability', 0)


        self.simulation_injury = None
        self.returning_from_injury = False
        self.avg_points_per_game = 0 
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        self.last_missed_week = 0  # Add this line
        
        
        
        pff_data = initial_data.get('pff_projections', {})
        self.pff_projections = PFFProjections(pff_data) if pff_data else None


        self.weekly_scores = {}

    

        self.games_missed_this_season = 0

        self.simulation_injury_duration = None
        self.avg_points_per_season = None
        self.simulation_game = None
        self.simulation_points_current_season = None
        self.injured_weeks = 0
        pff_data = initial_data.get('pff_projections')
        self.pff_projections = PFFProjections(pff_data) if pff_data and isinstance(pff_data, dict) else None
        
        
        self.projected_games_missed = float(initial_data.get('projected_games_missed', 0))
        self.injury_probability_game = float(initial_data.get('injury_probability_game', 0))    
        
        

        
        # FantasyCalc data
        self.value_1qb = float(initial_data.get('value_1qb', 0)) if initial_data.get('value_1qb') not in ['', None] else 0.0
        self.redraft_value = float(initial_data.get('redraft_value', 0)) if initial_data.get('redraft_value') not in ['', None] else 0.0

        pff_data = initial_data.get('pff_projections', {})
        if isinstance(pff_data, PFFProjections):
            self.pff_projections = pff_data
        else:
            self.pff_projections = PFFProjections(pff_data) if pff_data else None
        
        if self.pff_projections:
            self.print_weekly_projection()
    
        
        self.update_from_dict(initial_data)
        if 'pff_projections' in initial_data and isinstance(initial_data['pff_projections'], dict):
            self.pff_projections = PFFProjections(initial_data['pff_projections'])
        
    def update_pff_projections(self, pff_data):
        if pff_data and isinstance(pff_data, dict):
            self.pff_projections = PFFProjections(pff_data)
        
    
    def to_dict(self):
        return {attr: getattr(self, attr) for attr in self.__dict__ if not attr.startswith('_')}
    
    def initialize_st_scorer(self, special_team_scorer):
        self.special_team_scorer = special_team_scorer
        
        

    def update_injury_status(self, week):
        if self.never_miss_game_flag:
            return
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
                # print(f"DEBUG: {self.full_name} injured in week {week} for {injury_duration:.1f} weeks (partial week factor: {partial_week_factor:.2f})")

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
        # Base weights
        base_weights = [0.5, 0.3, 0.15, 0.05]  # Minor, Moderate, Major, Severe
        
        # Adjust weights based on projected_games_missed
        if self.projected_games_missed <= 1:
            return [0.7, 0.2, 0.08, 0.02]
        elif 1 < self.projected_games_missed <= 2:
            return [0.5, 0.3, 0.15, 0.05]
        elif 2 < self.projected_games_missed <= 4:
            return [0.3, 0.4, 0.2, 0.1]
        else:  # More than 4 games projected to be missed
            return [0.2, 0.3, 0.3, 0.2]

    def is_injured(self, week):
        return self.simulation_injury and self.simulation_injury['start_week'] < week < self.simulation_injury['return_week']

    def is_partially_injured(self, week):
        return self.simulation_injury and self.simulation_injury['start_week'] == week


    def update_from_dict(self, data):
        if 'age' in data and data['age'] is not None:
            self.age = data['age']
        if 'position' in data and data['position'] is not None and data['position'] != 'UNKNOWN':
            self.position = data['position']
        if 'team' in data and data['team'] is not None:
            self.team = data['team']
            
            
    def update_injury_data(self, injury_data):
        self.career_injuries = injury_data.get('career_injuries', 0)
        self.injury_risk = injury_data.get('injury_risk', 'Unknown')
        self.injury_probability_season = injury_data.get('probability_of_injury_in_the_season')
        self.projected_games_missed = float(injury_data.get('projected_games_missed', 0.5))
        self.injury_probability_game = injury_data.get('probability_of_injury_per_game')
        self.durability = float(injury_data.get('durability', 5))

        print(f"DEBUG: {self.full_name} - Updated injury data:")
        print(f"  Career injuries: {self.career_injuries}")
        print(f"  Injury risk: {self.injury_risk}")
        print(f"  Injury probability (season): {self.injury_probability_season}")
        print(f"  Projected games missed: {self.projected_games_missed}")
        print(f"  Injury probability (game): {self.injury_probability_game}")
        print(f"  Durability: {self.durability}")

    def normalize_injury_probability(self):
        if self.injury_probability_game is None or self.injury_probability_game == 0:
            self.injury_probability_game = 0.006  # Default value if no data available

        print(f"Normalized injury probability for {self.full_name}: {self.injury_probability_game:.6f}")

    def print_weekly_projection(self):
        if self.pff_projections:
            weekly_projection = self.pff_projections.get_weekly_projection()
            print(f"{self.full_name} ({self.position}) - Projected weekly points: {weekly_projection:.2f}")
        # else:
            # print(f"{self.full_name} ({self.position}) - No PFF projections available")



    def print_player(self):
        for key, value in self.to_dict().items():
            print(f"{key}: {value}")


    def matches_name(self, pff_name):
        def clean_name(name):
            name = name.lower()
            for suffix in [' jr', ' sr', ' ii', ' iii', ' iv']:
                name = name.replace(suffix, '')
            return name.replace('.', '').replace("'", '').strip()

        clean_self_name = clean_name(self.full_name)
        clean_pff_name = clean_name(pff_name)

        # Check for exact match
        if clean_self_name == clean_pff_name:
            return True

        # Check if last name and first initial match
        self_parts = clean_self_name.split()
        pff_parts = clean_pff_name.split()
        if len(self_parts) > 1 and len(pff_parts) > 1:
            if self_parts[-1] == pff_parts[-1] and self_parts[0][0] == pff_parts[0][0]:
                return True

        return False
    
    def calculate_special_team_score(self):
        # print(f"DEBUG: Calculating special team score for {self.f
        # ull_name} ({self.position}) - Team: {self.team}")
        if self.position.lower() in ['k', 'dst', 'def']:
            score = self.special_team_scorer.get_player_score(self.full_name, self.position, self.team)
            # print(f"DEBUG: Special team score calculated: {score}")
            return score
        else:
            # print(f"DEBUG: Not a special teams player: {self.full_name}")
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
            # print(f"DEBUG: No PFF projections for {self.full_name}")
            # returns a random number between 0 and 1 with a mean of 0.5 and a standard deviation of 0.5
            return random.lognormvariate(0.5, 0.5)
        
        proj = self.pff_projections
        games = float(proj.games or 17)
        bye_week = int(proj.bye_week or 0)

        if week == bye_week:
            # print(f"DEBUG: {self.full_name} - Bye week")
            return None

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
        receptions = max(1, round(full_receptions * partial_week_factor))  # Ensure at least 1 reception if any

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
        rush_td = max(0, np.random.poisson(avg_rush_td))
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

        # # Debug output
        # if self.position == 'QB':
        #     print(f"DEBUG: {self.full_name} - Week {week} - Passing: {pass_yds:.2f} yds, {pass_td} TD, {pass_int} INT - Score: {score:.2f} (Modifier: {self.season_modifier:.2f})")
        # elif self.position == 'RB':
        #     print(f"DEBUG: {self.full_name} - Week {week} - Rushing: {rush_yds:.2f} yds, {rush_td} TD, Receiving: {receptions} rec, {rec_yds:.2f} yds, {rec_td} TD - Score: {score:.2f} (Modifier: {self.season_modifier:.2f})")
        # elif self.position in ['WR', 'TE']:
        #     print(f"DEBUG: {self.full_name} - Week {week} - Receiving: {receptions} rec, {rec_yds:.2f} yds, {rec_td} TD - Score: {score:.2f} (Modifier: {self.season_modifier:.2f})")

        # if partial_week_factor < 1:
        #     print(f"DEBUG: {self.full_name} - Partial week factor: {partial_week_factor:.2f} - Adjusted Score: {score:.2f} (original: {score / partial_week_factor:.2f})")



        self.record_weekly_score(week, score)

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
    
    def clear_injury(self, week):
        if self.simulation_injury and week >= self.simulation_injury['return_week']:
            self.simulation_injury = None
            return True
        return False

    def get_injury_adjustment(self, week):
        if self.simulation_injury and self.simulation_injury['start_week'] == week:
            return self.simulation_injury['injury_time']
        return 1.0

    def simulate_week(self, week, scoring_settings):
        if self.is_injured(week):
            return 0
        base_score = self.calculate_score(scoring_settings, week)
        injury_adjustment = self.get_injury_adjustment(week)
        return base_score * injury_adjustment
    
    def get_games_missed_for_tracking(self):
        if self.current_injury_games_missed > 1:
            return self.current_injury_games_missed
        return 0

    def reset_injury_status(self):
        self.simulation_injury = None
        self.current_injury_games_missed = 0
        self.total_games_missed_this_season = 0
        


    def create_players_season_modifiers(self):
        # Base modifier starts at 1 (no modification)
        
        # 1 in 100 chamce to be out the entire season
        
        if random.random() < 0.01:
            self.season_modifier = 0
            return
        
        # 1 in 12 chance to not miss any games
        if random.random() < 0.083:
            self.never_miss_game_flag = True
        
        modifier = 1.0
        
        

        # Define thresholds for non-QB player tiers
        star_threshold = 4000
        mid_tier_threshold = 1000
        backup_threshold = 500

        # Determine player tier or QB status
        if self.position == 'QB':
            tier = "qb_starter" if self.depth_chart_order == 1 else "qb_backup"
        elif self.redraft_value >= star_threshold:
            tier = "star"
        elif self.redraft_value >= mid_tier_threshold:
            tier = "mid"
        elif self.redraft_value >= backup_threshold:
            tier = "backup"
        else:
            tier = "deep_backup"

        # Basic modifier range based on tier
        if tier == "qb_starter":
            base_range = (0.85, 1.15)
        elif tier == "qb_backup":
            base_range = (0.7, 1.3)
        elif tier == "star":
            base_range = (0.7, 1.3)
        elif tier == "mid":
            base_range = (0.6, 1.35)
        elif tier == "backup":
            base_range = (0.5, 1.7)
        else:  # deep_backup
            base_range = (0.4, 1.8)

        modifier *= random.uniform(*base_range)

        # Additional variance factor
        variance_factor = random.normalvariate(1, 0.2)
        modifier *= variance_factor

        # Experience and potential modifier
        if self.years_exp is not None:
            if 1 <= self.years_exp <= 3:
                modifier *= random.uniform(1, 1.2)
            elif self.years_exp >= 7:
                modifier *= random.uniform(0.9, 1.1)
            elif self.years_exp == 0:
                new_player_boom_chance = 0.1
                if random.random() < new_player_boom_chance:
                    modifier *= random.uniform(1, 2.5)
            
        if tier == "qb_starter":
            breakout_chance = 0.05
            bust_chance = 0.075
        elif tier == "qb_backup":
            breakout_chance = 0.1
            bust_chance = 0.1
        else:
            breakout_chance = 0.2
            bust_chance = 0.2

        # Apply breakout or bust modifiers
        if random.random() < breakout_chance:
            if tier == "qb_starter":
                modifier = random.uniform(0.7, 1.4)
            elif tier == "qb_backup":
                modifier *= random.uniform(1.2, 1.7)
            elif tier == "star":
                modifier *= random.uniform(1.2, 1.5)
            elif tier == "mid":
                modifier *= random.uniform(1.3, 1.8)
            elif tier == "backup":
                modifier *= random.uniform(1, 2)
            else:  # deep_backup
                modifier *= random.uniform(1.5, 3)
        elif random.random() < bust_chance:
            if tier == "qb_starter":
                modifier *= random.uniform(0.7, 0.9)
            elif tier == "qb_backup":
                modifier *= random.uniform(0.6, 0.85)
            elif tier == "star":
                modifier *= random.uniform(0.45, 0.9)
            elif tier == "mid":
                modifier *= random.uniform(0.5, 0.85)
            else:  # backup and deep_backup
                modifier *= random.uniform(0.5, 0.75)
                
        # Position-specific adjustments
        if self.position in ['WR', 'TE']:
            modifier *= random.uniform(0.9, 1.1)

        # Ensure the modifier stays within realistic bounds
        if self.pff_projections != None:
            if self.pff_projections.fantasy_points_rank <= 50 and modifier > 1.8:
                # print(f"DEBUG: {self.full_name} ({self.position}) - Modifier: {modifier:.2f} - Top 50 player")
                modifier = modifier + (1.4 - modifier) * 0.15
                # print(f"new modifier: {modifier:.2f}")
                
            elif 50 < self.pff_projections.fantasy_points_rank <= 175 and modifier > 1.8:
                # print(f"DEBUG: {self.full_name} ({self.position}) - Modifier: {modifier:.2f} - 50 - 150 player")
                modifier = modifier + (1.8 - modifier) * 0.25
                # print(f"new modifier: {modifier:.2f}")

        
    
        if modifier > 1.3 and (tier == "qb_starter"):
            modifier = 1.3 + (modifier - 1.3) * 0.1
            
        modifier = max(0.3, min(modifier, 2.7)) 
        
        if self.pff_projections != None:
            if 5 < self.pff_projections.fantasy_points / 17 < 8:
                # 5% chance to be a giant boom breakout player
                if random.random() < 0.05:
                    modifier = random.uniform(2.5, 3)
                    # print(f"DEBUG: {self.full_name} ({self.position}) - Modifier: {modifier:.2f} - Giant Boom")
            elif self.pff_projections.fantasy_points / 17 < 5:
                if random.random() < 0.05:
                    modifier = random.uniform(4, 5)
                    # print(f"DEBUG: {self.full_name} ({self.position}) - Modifier: {modifier:.2f} - Giant Boom ")
                    
            if self.pff_projections.fantasy_points / 17 > 10 and self.position == 'QB' and modifier < 1.5:
                modifier = modifier + (1.5 - modifier) * 0.1
                    
        # to account for TE premium settings
        if self.position == 'TE':
            if modifier > 1.75:
                modifier = modifier + (1.75 - modifier) * 0.1
 


        # Store the modifier as an attribute of the player
        self.season_modifier = round(modifier, 2)
        
        


        # print(f"DEBUG: {performance_type} - {self.full_name} ({self.position}, {tier.upper()}) - Modifier: {self.season_modifier:.2f}")

        
    def get_average_weekly_score(self):
        """Get the current season's average weekly score."""
        if self.total_simulated_games > 0:
            return self.total_simulated_points / self.total_simulated_games
        return 0
    
    
    
    def record_weekly_score(self, week, score):
        """Record a weekly score for the current season."""
        if score is None:
            print(f"WARNING: Attempted to record None score for player {self.full_name} (ID: {self.sleeper_id}) in week {week}")
            return
        self.weekly_scores[week] = score
        self.total_simulated_points += score
        self.total_simulated_games += 1
        print(f"DEBUG: Recorded score for player {self.full_name} (ID: {self.sleeper_id}) in week {week}: {score}")

    def reset_season_stats(self):
        """Reset the season statistics. Call this at the start of each new simulation."""
        self.weekly_scores = {}
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        self.never_miss_game_flag = False


    
class PFFProjections:
    def __init__(self, projection_data):
        if isinstance(projection_data, PFFProjections): # if already a PFFProjections object
            self.__dict__.update(projection_data.__dict__) # copy over attributes
        else:
            self.fantasy_points_rank = projection_data.get('fantasyPointsRank')
            self.team_name = projection_data.get('teamName')
            self.bye_week = projection_data.get('byeWeek')
            self.games = projection_data.get('games')
            self.fantasy_points = projection_data.get('fantasyPoints')
            self.auction_value = projection_data.get('auctionValue')
            self.pass_comp = projection_data.get('passComp')
            self.pass_att = projection_data.get('passAtt')
            self.pass_yds = projection_data.get('passYds')
            self.pass_td = projection_data.get('passTd')
            self.pass_int = projection_data.get('passInt')
            self.pass_sacked = projection_data.get('passSacked')
            self.rush_att = projection_data.get('rushAtt')
            self.rush_yds = projection_data.get('rushYds')
            self.rush_td = projection_data.get('rushTd')
            self.recv_targets = projection_data.get('recvTargets')
            self.recv_receptions = projection_data.get('recvReceptions')
            self.recv_yds = projection_data.get('recvYds')
            self.recv_td = projection_data.get('recvTd')
            self.fumbles = projection_data.get('fumbles')
            self.fumbles_lost = projection_data.get('fumblesLost')
            self.two_pt = projection_data.get('twoPt')
            self.return_yds = projection_data.get('returnYds')
            self.return_td = projection_data.get('returnTd')
        
        

    def get_weekly_projection(self):
        if self.games and float(self.games) > 0:
            return float(self.fantasy_points) / float(self.games)
        return 0

    def __str__(self):
        return f"PFF Projections: {self.fantasy_points} points over {self.games} games"
    
    
    
    def __bool__(self):
            return self.fantasy_points is not None 
        
        
   
        
    