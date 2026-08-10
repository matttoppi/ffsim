from collections import Counter


class ScoringSettings:
    def __init__(self, scoring_data):
        for key, value in scoring_data.items():
            setattr(self, key, value)

        self.rec = scoring_data.get("rec", 1)
        self.te_rec = scoring_data.get("te_rec", 2)


class League:
    def __init__(self, league_data):
        self.name = league_data.get("name")
        self.league_id = league_data.get("league_id")
        self.rosters = []
        self.divisions = {}
        self.scoring_settings = ScoringSettings(league_data.get("scoring_settings", {}))
        self.roster_slots = Counter(
            position
            for position in league_data.get("roster_positions", [])
            if position not in {"BN", "IR", "TAXI"}
        )
        self.playoff_teams = int(league_data.get("settings", {}).get("playoff_teams", 6))

    def print_rosters_ids(self):
        for team in self.rosters:
            print(f"{team.name}: {team.roster_id}")

    def print_rosters(self):
        for team in self.rosters:
            sorted_players = sorted(team.players, key=lambda player: player.value_1qb, reverse=True)
            print(f"\n\nTeam: {team.name}")
            for player in sorted_players:
                player.print_player_short()
            print(f"  Total value 1QB: {team.total_value_1qb}")
