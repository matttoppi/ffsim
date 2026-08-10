class FantasyTeam:
    def __init__(self, name, league, user_data=None):
        user_data = user_data or {}
        self.name = user_data.get("display_name") if name == "Unknown" else name
        self.league = league
        self.roster_id = None
        self.players = []
        self.player_sleeper_ids = []
        self.starters = {}
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        self.total_value_1qb = 0

    def create_season_modifiers(self):
        for player in self.players:
            player.create_players_season_modifiers()

    def add_player(self, player):
        self.players.append(player)
        self.player_sleeper_ids.append(player.sleeper_id)

    def calculate_metadata(self):
        self.total_value_1qb = round(sum(player.value_1qb for player in self.players), 2)

    def update_record(self, won, tied, points_against, points_for):
        if won:
            self.wins += 1
        elif tied:
            self.ties += 1
        else:
            self.losses += 1
        self.points_against += points_against
        self.points_for += points_for

    def fill_starters(self, week):
        slots = {"QB": 1, "RB": 3, "WR": 3, "TE": 1, "FLEX": 3, "K": 1, "DEF": 1}
        self.starters = {position: [] for position in slots}
        available = [
            player
            for player in self.players
            if not player.is_injured(week) or player.is_partially_injured(week)
        ]
        score = (
            (lambda player: player.redraft_value)
            if week == 1
            else (lambda player: player.get_average_weekly_score())
        )
        available.sort(key=score, reverse=True)

        for position in ("QB", "RB", "WR", "TE", "K", "DEF"):
            players = [player for player in available if player.position == position]
            for player in players[: slots[position]]:
                self.starters[position].append(player)
                available.remove(player)

        flex_players = [player for player in available if player.position in {"RB", "WR", "TE"}]
        self.starters["FLEX"] = sorted(flex_players, key=score, reverse=True)[: slots["FLEX"]]

    def get_active_starters(self, week):
        return [
            player
            for players in self.starters.values()
            for player in players
            if not player.is_injured(week) or player.is_partially_injured(week)
        ]

    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        for player in self.players:
            player.reset_season_stats()
