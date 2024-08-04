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

    def simulate_all_players(self, team, scoring_settings, week):
        total_score = 0
        player_scores = {}
        print(f"DEBUG: Simulating all players for team {team.name} for week {week}")
        for player in team.players:
            score = player.calculate_score(scoring_settings, week)
            player_scores[player.sleeper_id] = score
            if player in team.get_active_starters(week):
                total_score += score
        return total_score, player_scores


    def simulate(self, scoring_settings, tracker):
        self.home_score, home_player_scores = self.simulate_all_players(self.home_team, scoring_settings, self.week)
        self.away_score, away_player_scores = self.simulate_all_players(self.away_team, scoring_settings, self.week)
        
        print(f"DEBUG: Matchup result - {self.home_team.name}: {self.home_score} vs {self.away_team.name}: {self.away_score}")
        
        for player_id, score in home_player_scores.items():
            tracker.record_player_score(player_id, self.week, score)
        
        for player_id, score in away_player_scores.items():
            tracker.record_player_score(player_id, self.week, score)
        
        self.update_records()

    def update_records(self):
        print (f"DEBUG: Records before update - {self.home_team.name}: {self.home_team.wins}-{self.home_team.losses}, {self.away_team.name}: {self.away_team.wins}-{self.away_team.losses}")
        if self.home_score > self.away_score:
            self.home_team.update_record(True, False, self.away_score, self.week)
            self.away_team.update_record(False, False, self.home_score, self.week)
        elif self.away_score > self.home_score:
            self.home_team.update_record(False, False, self.away_score, self.week)
            self.away_team.update_record(True, False, self.home_score, self.week)
        else:
            self.home_team.update_record(False, True, self.away_score, self.week)
            self.away_team.update_record(False, True, self.home_score, self.week)
        print(f"DEBUG: Updated records - {self.home_team.name}: {self.home_team.wins}-{self.home_team.losses}, {self.away_team.name}: {self.away_team.wins}-{self.away_team.losses}")