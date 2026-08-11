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
            self.home_team, scoring_settings, self.week, tracker.track_players
        )
        self.away_score, away_scores = self.simulate_all_players(
            self.away_team, scoring_settings, self.week, tracker.track_players
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

    def simulate_all_players(self, team, scoring_settings, week, track_players=True):
        total_score = 0.0
        player_scores = {}
        starters = team.get_active_starters(week)
        starter_set = set(starters)
        for player in team.players if track_players else starters:
            available = player.is_available(week)
            score = player.calculate_score(scoring_settings, week, self.rng) if available else 0.0
            player_scores[player.sleeper_id] = score
            self.player_availability[player.sleeper_id] = available
            if player in starter_set:
                total_score += score
        total_score += team.streamer_score(self.rng)
        return total_score, player_scores
