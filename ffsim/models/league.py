from collections import Counter
from statistics import median

from ffsim.scoring import ScoringSettings


class League:
    def __init__(self, league_data):
        settings = league_data.get("settings", {})
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
        self.playoff_teams = settings.get("playoff_teams")
        self.playoff_teams = int(self.playoff_teams) if self.playoff_teams is not None else None
        self.playoff_round_type = settings.get("playoff_round_type")
        self.playoff_seed_type = settings.get("playoff_seed_type")
        self.division_count = int(settings.get("divisions", 0) or 0)
        self.league_average_match = bool(settings.get("league_average_match", 0))
        self.status = league_data.get("status")
        self.last_scored_week = int(settings.get("last_scored_leg", 0) or 0)
        self.winners_bracket = []
        self.completed_starters = {}
        self.replacement_scores = {}

    def set_replacement_levels(self, players):
        rostered = {
            str(player.sleeper_id)
            for team in self.rosters
            for player in team.players
        }
        for position in {"QB", "RB", "WR", "TE", "K", "DEF"}:
            scores = sorted(
                (
                    player.expected_weekly_score(self.scoring_settings)
                    for player in players
                    if str(player.sleeper_id) not in rostered
                    and player.position == position
                    and player.projections
                ),
                reverse=True,
            )[: len(self.rosters)]
            if scores:
                self.replacement_scores[position] = median(scores)

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
