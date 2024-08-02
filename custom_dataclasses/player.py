
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
        self.print_weekly_projection()
        
        
        
        # Injury data
        self.career_injuries = initial_data.get('career_injuries', 0)
        self.injury_risk = initial_data.get('injury_risk', 'Medium')
        self.durability = initial_data.get('durability', 0)

        # Convert injury probabilities from percentage to decimal
        self.injury_probability_season = self.convert_to_decimal(initial_data.get('injury_probability_season', 12))
        self.projected_games_missed = float(initial_data.get('projected_games_missed', 2))
        self.injury_probability_game = self.convert_to_decimal(initial_data.get('injury_probability_game', 3))


        self.simulation_injury_duration = None
        self.avg_points_per_season = None
        self.simulation_game = None
        self.simulation_points_current_season = None
        
        self.simulation_injury = None
        self.returning_from_injury = False
        self.avg_points_per_game = 0 
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        
        # FantasyCalc data
        self.value_1qb = float(initial_data.get('value_1qb', 0)) if initial_data.get('value_1qb') not in ['', None] else 0.0
        self.redraft_value = float(initial_data.get('redraft_value', 0)) if initial_data.get('redraft_value') not in ['', None] else 0.0

        pff_data = initial_data.get('pff_projections', {})
        if isinstance(pff_data, PFFProjections):
            self.pff_projections = pff_data
        else:
            self.pff_projections = PFFProjections(pff_data) if pff_data else None
        
        self.print_weekly_projection()
        
    def print_weekly_projection(self):
        if self.pff_projections:
            weekly_projection = self.pff_projections.get_weekly_projection()
            print(f"{self.full_name} ({self.position}) - Projected weekly points: {weekly_projection:.2f}")
        # else:
        #     print(f"{self.full_name} ({self.position}) - No PFF projections available")


    def to_dict(self):
        return {attr: getattr(self, attr) for attr in self.__dict__ if not attr.startswith('_')}

    def print_player(self):
        for key, value in self.to_dict().items():
            print(f"{key}: {value}")

    def print_player_short(self):
         print(f"{self.full_name} - {self.position.upper()} - {self.team} - 1QB: {self.value_1qb} - Redraft: {self.redraft_value}")
         
         
    @staticmethod
    def convert_to_decimal(value):
        if isinstance(value, str):
            value = value.replace('%', '').strip()
        try:
            float_value = float(value)
            return float_value / 100 if float_value > 1 else float_value
        except ValueError:
            return 0.01  # Default to 1% if conversion fails
        
        

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