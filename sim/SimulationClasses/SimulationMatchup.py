import random

class SimulationMatchup:
    def __init__(self, home_team, away_team, week):
        self.home_team = home_team
        self.away_team = away_team
        self.week = week
        self.home_score = None
        self.away_score = None
        
    def simulate_team(self, team, scoring_settings, week):
        team.fill_starters(week)
        total_score = 0
        player_scores = {}
        print(f"DEBUG: Simulating team {team.name} for week {week}")
        for player in team.get_active_starters(week):
            score = player.calculate_score(scoring_settings, week)
            total_score += score
            player_scores[player.sleeper_id] = score
        return total_score, player_scores

    def simulate(self, scoring_settings, tracker):
        self.home_score, home_player_scores = self.simulate_team(self.home_team, scoring_settings, self.week)
        self.away_score, away_player_scores = self.simulate_team(self.away_team, scoring_settings, self.week)
        
        for player_id, score in home_player_scores.items():
            tracker.record_player_score(player_id, self.week, score)
        
        for player_id, score in away_player_scores.items():
            tracker.record_player_score(player_id, self.week, score)
    
    def update_records(self):
        if self.home_score > self.away_score:
            self.home_team.update_record(True, False, self.away_score, self.week)
            self.away_team.update_record(False, False, self.home_score, self.week)
        elif self.away_score > self.home_score:
            self.home_team.update_record(False, False, self.away_score, self.week)
            self.away_team.update_record(True, False, self.home_score, self.week)
        else:
            self.home_team.update_record(False, True, self.away_score, self.week)
            self.away_team.update_record(False, True, self.home_score, self.week)