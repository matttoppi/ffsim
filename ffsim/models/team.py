FLEX_ELIGIBILITY = {
    "FLEX": {"RB", "WR", "TE"},
    "REC_FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}


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
        slots = self.league.roster_slots
        self.starters = {position: [] for position in slots}
        available = [
            player
            for player in self.players
            if player.is_available(week)
        ]
        score = lambda player: player.expected_weekly_score(self.league.scoring_settings)
        available.sort(key=score, reverse=True)

        for position, count in slots.items():
            if position in FLEX_ELIGIBILITY:
                continue
            players = [player for player in available if player.position == position]
            for player in players[:count]:
                self.starters[position].append(player)
                available.remove(player)

        for position, eligible in FLEX_ELIGIBILITY.items():
            if position not in slots:
                continue
            players = sorted(
                (player for player in available if player.position in eligible),
                key=score,
                reverse=True,
            )[: slots[position]]
            self.starters[position] = players
            for player in players:
                available.remove(player)

    def get_active_starters(self, week):
        return [
            player
            for players in self.starters.values()
            for player in players
            if player.is_available(week)
        ]

    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        for player in self.players:
            player.reset_season_stats()
