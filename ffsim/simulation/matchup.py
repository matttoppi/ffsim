class SimulationMatchup:
    def __init__(self, home_team, away_team, week, rng=None):
        self.home_team = home_team
        self.away_team = away_team
        self.week = week
        self.rng = rng
        self.home_score = None
        self.away_score = None
        self.player_availability = {}

    def simulate(self, scoring_settings, tracker):
        self.home_score, home_scores = self.simulate_all_players(
            self.home_team, scoring_settings, self.week, tracker
        )
        self.away_score, away_scores = self.simulate_all_players(
            self.away_team, scoring_settings, self.week, tracker
        )
        for player_id, score in {**home_scores, **away_scores}.items():
            tracker.record_player_score(
                player_id, self.week, score, played=self.player_availability[player_id]
            )
        self.update_records()

    def update_records(self):
        if self.home_score > self.away_score:
            self.home_team.update_record(True, False, self.away_score, self.home_score)
            self.away_team.update_record(False, False, self.home_score, self.away_score)
        elif self.away_score > self.home_score:
            self.home_team.update_record(False, False, self.away_score, self.home_score)
            self.away_team.update_record(True, False, self.home_score, self.away_score)
        else:
            self.home_team.update_record(False, True, self.away_score, self.home_score)
            self.away_team.update_record(False, True, self.home_score, self.away_score)

    def simulate_all_players(self, team, scoring_settings, week, tracker):
        total_score = 0.0
        player_scores = {}
        starters = set(team.get_active_starters(week))
        for player in team.players:
            available = player.is_available(week)
            score = player.calculate_score(scoring_settings, week, self.rng) if available else 0.0
            player_scores[player.sleeper_id] = score
            self.player_availability[player.sleeper_id] = available
            if available and player.position in {"K", "DEF"} and tracker:
                position = "KICKER" if player.position == "K" else "DEFENSE"
                tracker.record_special_team_score(team.name, position, week, score)
            if player in starters:
                total_score += score
        return total_score, player_scores
