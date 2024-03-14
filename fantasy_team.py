class FantasyTeam:

    def __init__(self, name, user_data=None):
        
        
        # user_data: {'user_id': '413785390642630656', 'settings': None, 'metadata': {'team_name': 'Toppi', 'show_mascots': 'on', 'mention_pn': 'on', 'mascot_message_emotion_leg_1': 'idle', 'mascot_item_type_id_leg_9': 'panpan', 'mascot_item_type_id_leg_8': 'panpan', 'mascot_item_type_id_leg_7': 'panpan', 'mascot_item_type_id_leg_6': 'panpan', 'mascot_item_type_id_leg_5': 'panpan', 'mascot_item_type_id_leg_4': 'panpan', 'mascot_item_type_id_leg_3': 'panpan', 'mascot_item_type_id_leg_2': 'panpan', 'mascot_item_type_id_leg_18': 'panpan', 'mascot_item_type_id_leg_17': 'panpan', 'mascot_item_type_id_leg_16': 'panpan', 'mascot_item_type_id_leg_15': 'panpan', 'mascot_item_type_id_leg_14': 'panpan', 'mascot_item_type_id_leg_13': 'panpan', 'mascot_item_type_id_leg_12': 'panpan', 'mascot_item_type_id_leg_11': 'panpan', 'mascot_item_type_id_leg_10': 'panpan', 'mascot_item_type_id_leg_1': 'panpan', 'avatar': 'https://sleepercdn.com/uploads/8a81a8b96dfa73de0fb68683a0c592ab.jpg', 'archived': 'off', 'allow_sms': 'on', 'allow_pn': 'on'}, 'league_id': '1048288271089983488', 'is_owner': True, 'is_bot': False, 'display_name': 'matttoppi1', 'avatar': 'a3e0328d1eed0c5b72a52d9f7499d731'}
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
        
        self.owner_username = user_data.get("display_name")
        if self.name == "Unknown":
            self.name =  self.owner_username
        
        
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
        
        for key, value in user_data.items():
            if key in attributes:
                setattr(self, key, value)            
        
    def print_fantasy_team(self):
        print(f"\n\nFantasy Team data:\n")
        
        print(f"Name: {self.name}")
        print(f"Owner: {self.owner_username}")
        print(f"Wins: {self.wins}")
        print(f"Losses: {self.losses}")
        
        print(f"\nPlayers: ")
        for player in self.players:
            # player.print_player()
            player.print_player_short()
            
            
        
        print(f"\n\n")
        
        
        

