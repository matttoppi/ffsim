import random
import math

class FantasyTeam:

    def __init__(self, name, league, user_data=None):
        attributes = [
            'user_id', 'settings', 'metadata', 'league_id', 'is_owner', 'is_bot', 'display_name', 'avatar', 'archived', 'allow_sms', 'allow_pn'
        ]
        
        self.name = name
        self.players = []  # This is a list of players on the team
        self.player_sleeper_ids = []  # This is a list of player ids on the team
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.fantasy_pts_total = 0
        self.fantasy_pts_per_game = 0
        self.points_for = 0
        self.points_against = 0
        self.streak = 0
        self.total_value_1qb = 0
        self.total_value_2qb = 0
        self.average_value_1qb = 0
        self.average_value_2qb = 0
        self.average_age = 0
        self.total_age = 0
        self.league = league
        self.roster_id = None
        self.simulation = None  # We'll initialize this after adding players
        
        self.starters = {
            'QB': [], 'RB': [], 'WR': [], 'TE': [], 'FLEX': [], 'K': [], 'DEF': []
        }
        self.bench = []
        
        self.sim_injured_players = []
        self.weekly_scores = {}
        self.available_players = [p for p in self.players if not p.is_injured(week) or p.is_partially_injured(week)]
        
        
        self.owner_username = user_data.get("display_name")
        if self.name == "Unknown":
            self.name = self.owner_username
        
        for key, value in user_data.items():
            if key in attributes:
                setattr(self, key, value)    
                
        self.calculate_metadata()

    def print_fantasy_team(self):     
        print("\n")   
        print(f"Name: {self.name}")
        print(f"Owner: {self.owner_username}")
        print(f"Total Value 1QB: {self.total_value_1qb}")
        
    def print_fantasy_team_short(self):
        print(f"|{self.owner_username:<16} | Value 1QB: {self.total_value_1qb:<8.2f} |")
        
    def add_player(self, player):
        self.players.append(player)
        self.player_sleeper_ids.append(player.sleeper_id)


    def calculate_metadata(self):
        if len(self.players) <= 0:
            return
        self.total_value_1qb = round(sum(player.value_1qb for player in self.players if player.value_1qb is not None), 2)
        # self.total_value_2qb = round(sum(player.value_2qb for player in self.players if player.value_2qb is not None), 2)
        self.average_value_1qb = round(self.total_value_1qb / len(self.players), 2)
        # self.average_value_2qb = round(self.total_value_2qb / len(self.players), 2)
        self.total_age = sum(player.age for player in self.players if player.age is not None)
        self.average_age = round(self.total_age / len(self.players), 2) if self.total_age else 0
        

    def update_record(self, won, tied, points_against, points_for, week):
        if won:
            self.wins += 1
        elif tied:
            self.ties += 1
        else:
            self.losses += 1
        self.points_against += points_against
        self.points_for += points_for
        self.weekly_scores[week] = points_for

    
    
    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        self.weekly_scores = {}
        for player in self.players:
            player.reset_injury_status()
    


    def get_weekly_score(self, week):
        return self.weekly_scores.get(week, 0)

    def set_weekly_score(self, week, score):
        self.weekly_scores[week] = score
        self.points_for += score


    def update_injury_status(self, week):
        recovered_players = [p for p in self.sim_injured_players if not p.is_injured(week)]
        for player in recovered_players:
            print(f"{player.name} has recovered from injury and is available to play.")
            self.sim_injured_players.remove(player)

    def simulate_player_week(self, player, week, scoring_settings):
        print(f"Simulating week {week} for {player.name}")
        base_score = player.calculate_score(scoring_settings)
        
        # Check for new injury
        if random.random() < player.injury_probability_game:
            injury_duration = max(0.5, random.gauss(player.projected_games_missed, 1))
            player.simulation_injury = {
                'start_week': week,
                'duration': injury_duration,
                'return_week': week + math.ceil(injury_duration)
            }
            # print(f"New injury for {player.name} on {self.name} for {injury_duration:.2f} weeks")
            self.sim_injured_players.append(player)
            print(f"New injury for {player.name} on {self.name} for {injury_duration:.2f} weeks")
                
                
            # Adjust score based on when injury occurred during the game
            injury_time = random.random()
            adjusted_score = base_score * injury_time
            return adjusted_score
        
        print(f"{player.name} scored {base_score} in week {week}")
        
        return base_score

    def manage_injuries(self, week):
        recovered_players = []
        for player in self.players:
            if player.update_injury_status(week):
                recovered_players.append(player)
        
        for player in recovered_players:
            if player in self.sim_injured_players:
                self.sim_injured_players.remove(player)
                


    
    def print_roster(self):
        
        print("Starters:")
        for pos, players in self.starters.items():
            for player in players:
                print(f"{pos}: {player.name} (Redraft Value: {player.redraft_value})")
        print("\nBench:")
        for player in self.bench:
            print(f"{player.name} (Redraft Value: {player.redraft_value})")
        print("\nInjured:")
        for player in self.sim_injured_players:
            print(f"{player.name} (Redraft Value: {player.redraft_value}) - Injured for {player.simulation_injury['duration']:.2f} more weeks. Return week: {player.simulation_injury['return_week']}")
        print("\n")
        

    def fill_starters(self, week):
        self.manage_injuries(week)

        slots = {
            'QB': 1, 'RB': 3, 'WR': 3, 'TE': 1, 'FLEX': 3, 'K': 1, 'DEF': 1
        }
        flex_eligible = ['RB', 'WR', 'TE']

        self.starters = {pos: [] for pos in slots.keys()}

        # Get all available players (not fully injured this week)
        available_players = [p for p in self.players if not p.is_injured(week) or p.is_partially_injured(week)]

        # Sort available players by redraft value
        available_players.sort(key=lambda p: p.redraft_value if hasattr(p, 'redraft_value') else 0, reverse=True)

        # Fill mandatory positions first
        for pos in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            position_players = [p for p in available_players if p.position == pos]
            for _ in range(slots[pos]):
                if position_players:
                    player = position_players.pop(0)
                    self.starters[pos].append(player)
                    available_players.remove(player)

        # Fill FLEX positions
        flex_players = [p for p in available_players if p.position in flex_eligible]
        for _ in range(slots['FLEX']):
            if flex_players:
                player = max(flex_players, key=lambda p: p.redraft_value if hasattr(p, 'redraft_value') else 0)
                self.starters['FLEX'].append(player)
                available_players.remove(player)
                flex_players.remove(player)

        # Set bench players
        self.bench = [p for p in self.players if p not in [player for pos_list in self.starters.values() for player in pos_list] and not p.is_injured(week)]
        
        # Update injured players list
        self.sim_injured_players = [p for p in self.players if p.is_injured(week)]

    def calculate_player_score(self, player, week, scoring_settings):
        if player.is_injured(week):
            return 0
        elif player.is_partially_injured(week):
            base_score = player.calculate_score(scoring_settings, week)
            return base_score * player.simulation_injury['partial_week_factor']
        else:
            return player.calculate_score(scoring_settings, week)

    def get_active_starters(self, week):
        active_starters = []
        for position, players in self.starters.items():
            for player in players:
                if not player.is_injured(week) or player.is_partially_injured(week):
                    active_starters.append(player)
        return active_starters