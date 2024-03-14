class FantasyTeam:

    def __init__(self, name, user_data=None):
        self.name = name
        self.user_data = user_data or {}
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
        
        self.owner_username = self.user_data.get('username', 'Unknown')
        
        
        self.total_value_1qb = round(sum([player.value_1qb for player in self.players if player.value_1qb]), 2)
        self.total_value2qb = round(sum([player.value_2qb for player in self.players if player.value_2qb]), 2)
        
        # unless 0 players, calculate average age and ecr for 1qb and 2qb
        if len(self.players) != 0:
            self.average_age = round(sum([player.age for player in self.players if player.age]) / len(self.players), 2)
            self.average_ecr_1qb = round(sum([player.ecr_1qb for player in self.players if player.ecr_1qb]) / len(self.players), 2)
            self.average_ecr_2qb = round(sum([player.ecr_2qb for player in self.players if player.ecr_2qb]) / len(self.players), 2)
        else:
            self.average_age = 0
            self.average_ecr_1qb = 0
            self.average_ecr_2qb = 0
            
        
    def print_fantasy_team(self):
        print(f"\n\nFantasy Team data:\n")
        for key, value in self.__dict__.items():
            print(f"{key}: {value}")
            
        
        print(f"\n\n")
        
        
        

