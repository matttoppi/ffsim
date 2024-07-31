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
        
        self.owner_username = user_data.get("display_name")
        if self.name == "Unknown":
            self.name = self.owner_username
        
        for key, value in user_data.items():
            if key in attributes:
                setattr(self, key, value)    
                
        self.calculate_stats()

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

    def calculate_stats(self):
        if len(self.players) <= 0:
            return
        self.total_value_1qb = round(sum(player.value_1qb for player in self.players if player.value_1qb is not None), 2)
        # self.total_value_2qb = round(sum(player.value_2qb for player in self.players if player.value_2qb is not None), 2)
        self.average_value_1qb = round(self.total_value_1qb / len(self.players), 2)
        # self.average_value_2qb = round(self.total_value_2qb / len(self.players), 2)
        self.total_age = sum(player.age for player in self.players if player.age is not None)
        self.average_age = round(self.total_age / len(self.players), 2) if self.total_age else 0