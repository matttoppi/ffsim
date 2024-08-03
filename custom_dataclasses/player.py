import random
import math



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
        
        # Injury data
        self.career_injuries = initial_data.get('career_injuries', 0)
        self.injury_risk = initial_data.get('injury_risk', 'Medium')
        
        self.durability = initial_data.get('durability', 0)
        self.pff_projections = initial_data.get('pff_projections', {})
        
        
        
    
        # Injury data with careful defaulting
        self.career_injuries = initial_data.get('career_injuries', 0)
        self.injury_risk = initial_data.get('injury_risk', 'Unknown')
        self.durability = initial_data.get('durability', 0)
        self.injury_probability_season = self.convert_to_decimal(initial_data.get('injury_probability_season', 0))
        self.projected_games_missed = float(initial_data.get('projected_games_missed', 0))
        self.injury_probability_game = self.convert_to_decimal(initial_data.get('injury_probability_game', 0))

        self.simulation_injury = None
        self.returning_from_injury = False
        self.avg_points_per_game = 0 
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        
        self.weekly_scores = {}  # Add this to store weekly scores



        self.simulation_injury_duration = None
        self.avg_points_per_season = None
        self.simulation_game = None
        self.simulation_points_current_season = None
        
        # FantasyCalc data
        self.value_1qb = float(initial_data.get('value_1qb', 0)) if initial_data.get('value_1qb') not in ['', None] else 0.0
        self.redraft_value = float(initial_data.get('redraft_value', 0)) if initial_data.get('redraft_value') not in ['', None] else 0.0

        pff_data = initial_data.get('pff_projections', {})
        if isinstance(pff_data, PFFProjections):
            self.pff_projections = pff_data
        else:
            self.pff_projections = PFFProjections(pff_data) if pff_data else None
        
        self.print_weekly_projection()
        
        self.update_from_dict(initial_data)

    def update_from_dict(self, data):
        if 'age' in data and data['age'] is not None:
            self.age = data['age']
        if 'position' in data and data['position'] is not None and data['position'] != 'UNKNOWN':
            self.position = data['position']
        if 'team' in data and data['team'] is not None:
            self.team = data['team']
            
            
    def update_injury_data(self, injury_data):
        # Only update if the new value is not None and not 0
        if injury_data.get('career_injuries'):
            self.career_injuries = injury_data['career_injuries']
        if injury_data.get('injury_risk') and injury_data['injury_risk'] != 'Unknown':
            self.injury_risk = injury_data['injury_risk']
        if injury_data.get('durability'):
            self.durability = injury_data['durability']
        if injury_data.get('injury_probability_season'):
            self.injury_probability_season = self.convert_to_decimal(injury_data['injury_probability_season'])
        if injury_data.get('projected_games_missed'):
            self.projected_games_missed = float(injury_data['projected_games_missed'])
        if injury_data.get('injury_probability_game'):
            self.injury_probability_game = self.convert_to_decimal(injury_data['injury_probability_game'])
            
    def update_injury_status(self, week):
        if self.simulation_injury:
            self.simulation_injury['duration'] -= 1
            if self.simulation_injury['duration'] <= 0:
                print(f"{self.name} has recovered from injury and is available to play.")
                self.simulation_injury = None
                return True
        return False

    def is_injured(self, week):
        return self.simulation_injury is not None and self.simulation_injury['duration'] > 0

    def print_weekly_projection(self):
        if self.pff_projections:
            weekly_projection = self.pff_projections.get_weekly_projection()
            print(f"{self.full_name} ({self.position}) - Projected weekly points: {weekly_projection:.2f}")
        # else:
            # print(f"{self.full_name} ({self.position}) - No PFF projections available")


    def to_dict(self):
        return {attr: getattr(self, attr) for attr in self.__dict__ if not attr.startswith('_')}

    def print_player(self):
        for key, value in self.to_dict().items():
            print(f"{key}: {value}")

    def print_player_short(self):
         print(f"{self.full_name} - {self.position.upper()} - {self.team} - 1QB: {self.value_1qb} - Redraft: {self.redraft_value}")
         
         
    @staticmethod
    def convert_to_decimal(value):
        if value is None or value == '':
            return 0
        if isinstance(value, str):
            value = value.replace('%', '').strip()
        try:
            float_value = float(value)
            return float_value / 100 if float_value > 1 else float_value
        except ValueError:
            return 0
        
    def update_pff_projections(self, pff_data):
        self.pff_projections = PFFProjections(pff_data)
        # # Debug print
        # print(f"Updated PFF projections for {self.full_name}")
        # print(f"  Fantasy Points: {self.pff_projections.fantasy_points}")
        # print(f"  Games: {self.pff_projections.games}")
        
        

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
        games = float(proj.games or 0)
        bye_week = int(proj.bye_week or 0)

        if games == 0 or week == bye_week:
            return 0

        # Calculate per-game averages and add randomness
        pass_yds = max(0, random.gauss(float(proj.pass_yds or 0) / games, float(proj.pass_yds or 0) / games * 0.25))
        pass_td = max(0, random.gauss(float(proj.pass_td or 0) / games, float(proj.pass_td or 0) / games * 0.75))
        pass_int = max(0, random.gauss(float(proj.pass_int or 0) / games, float(proj.pass_int or 0) / games * 0.75))
        rush_yds = max(0, random.gauss(float(proj.rush_yds or 0) / games, float(proj.rush_yds or 0) / games * 0.25))
        rush_td = max(0, random.gauss(float(proj.rush_td or 0) / games, float(proj.rush_td or 0) / games * 0.75))
        receptions = max(0, random.gauss(float(proj.recv_receptions or 0) / games, float(proj.recv_receptions or 0) / games * 0.75))
        rec_yds = max(0, random.gauss(float(proj.recv_yds or 0) / games, float(proj.recv_yds or 0) / games * 0.25))
        rec_td = max(0, random.gauss(float(proj.recv_td or 0) / games, float(proj.recv_td or 0) / games * 0.75))
        
        # Round stats to realistic values
        pass_yds, pass_td, pass_int = round(pass_yds), round(pass_td), round(pass_int)
        rush_yds, rush_td = round(rush_yds), round(rush_td)
        receptions, rec_yds, rec_td = round(receptions), round(rec_yds), round(rec_td)

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

        return score

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

    def check_for_injury(self, week):
        if random.random() < self.injury_probability_game:
            injury_duration = self.generate_injury_duration()
            self.simulation_injury = {
                'start_week': week,
                'duration': injury_duration,
                'return_week': week + math.ceil(injury_duration)
            }
            return True
        return False

    def generate_injury_duration(self):
        return max(0.5, random.gauss(self.projected_games_missed, 1))
    
    
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