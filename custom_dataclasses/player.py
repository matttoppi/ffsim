
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
        
        
        
        # Convert
        # injury probabilities from percentage to decimal
        self.injury_probability_season = float(initial_data.get('probability_of_injury_in_the_season', 10.0)) / 100
        self.projected_games_missed = float(initial_data.get('projected_games_missed', 1.0))
        self.injury_probability_game = float(initial_data.get('probability_of_injury_per_game', 2.5)) / 100

        self.simulation_injury = None
        
        # FantasyCalc data
        self.value_1qb = float(initial_data.get('value_1qb', 0)) if initial_data.get('value_1qb') not in ['', None] else 0.0
        self.redraft_value = float(initial_data.get('redraft_value', 0)) if initial_data.get('redraft_value') not in ['', None] else 0.0

        # PFF projections
        self.pff_projections = {key: initial_data.get(key) for key in [
            "fantasyPointsRank", "teamName", "byeWeek", "games", "fantasyPoints", "auctionValue",
            "passComp", "passAtt", "passYds", "passTd", "passInt", "passSacked",
            "rushAtt", "rushYds", "rushTd", "recvTargets", "recvReceptions", "recvYds",
            "recvTd", "fumbles", "fumblesLost", "twoPt", "returnYds", "returnTd"
        ] if initial_data.get(key) is not None}

    def to_dict(self):
        return {attr: getattr(self, attr) for attr in self.__dict__ if not attr.startswith('_')}

    def print_player(self):
        for key, value in self.to_dict().items():
            print(f"{key}: {value}")

    def print_player_short(self):
         print(f"{self.full_name} - {self.position.upper()} - {self.team} - 1QB: {self.value_1qb} - Redraft: {self.redraft_value}")