import random

class SimulationMatchup:
    def __init__(self, home_team, away_team, week):
        self.home_team = home_team
        self.away_team = away_team
        self.week = week
        self.home_score = None
        self.away_score = None


    def update_records(self):
        if self.home_score > self.away_score:
            self.home_team.update_record(won=True, tied=False, points_against=self.away_score, points_for=self.home_score, week=self.week)
            self.away_team.update_record(won=False, tied=False, points_against=self.home_score, points_for=self.away_score, week=self.week)
        elif self.away_score > self.home_score:
            self.home_team.update_record(won=False, tied=False, points_against=self.away_score, points_for=self.home_score, week=self.week)
            self.away_team.update_record(won=True, tied=False, points_against=self.home_score, points_for=self.away_score, week=self.week)
        else:
            self.home_team.update_record(won=False, tied=True, points_against=self.away_score, points_for=self.home_score, week=self.week)
            self.away_team.update_record(won=False, tied=True, points_against=self.home_score, points_for=self.away_score, week=self.week)

    def simulate_team(self, team, scoring_settings, week):
        team.fill_starters(week)
        total_score = 0
        player_scores = {}
        # print(f"DEBUG: Simulating team {team.name} for week {week}")
        for player in team.get_active_starters(week):
            score = player.calculate_score(scoring_settings, week)
            total_score += score
            player_scores[player.sleeper_id] = score
        return total_score, player_scores


    def simulate_all_players(self, team, scoring_settings, week, tracker):
        total_score = 0
        player_scores = {}
        # print(f"DEBUG: Simulating all players for team {team.name} in week {week}")

        def is_player_available(player):
            is_not_injured = not player.is_injured(week)
            is_not_on_bye = not hasattr(player, 'pff_projections') or \
                            player.pff_projections is None or \
                            not hasattr(player.pff_projections, 'bye_week') or \
                            player.pff_projections.bye_week is None or \
                            int(player.pff_projections.bye_week) != week
            return is_not_injured and is_not_on_bye

        active_starters = team.get_active_starters(week)

        for player in team.players:
            # print(f"DEBUG: Processing player {player.name} (ID: {player.sleeper_id})")
            
            if is_player_available(player):
                if player.position.lower() in ['k', 'dst', 'def']:
                    score = player.calculate_special_team_score()
                    position = 'KICKER' if player.position.lower() == 'k' else 'DEFENSE'
                    tracker.record_special_team_score(team.name, position, week, score)
                else:
                    score = player.calculate_score(scoring_settings, week)
                
                if score is not None:
                    player_scores[player.sleeper_id] = score
                    if player in active_starters:
                        total_score += score
                        
                else:
                    print(f"WARNING: Score is None for player {player.name} (ID: {player.sleeper_id})")
                    print(f"Player details: Position: {player.position}, Starter: {player in active_starters}")
                    player_scores[player.sleeper_id] = 0
            else:
                player_scores[player.sleeper_id] = 0
                

        # print(f"DEBUG: Total score for team {team.name}: {total_score}")
        return total_score, player_scores
    
    def simulate(self, scoring_settings, tracker):
        self.home_score, home_player_scores = self.simulate_all_players(self.home_team, scoring_settings, self.week, tracker)
        self.away_score, away_player_scores = self.simulate_all_players(self.away_team, scoring_settings, self.week, tracker)

        # Record player scores
        self.record_player_scores(self.home_team, home_player_scores, tracker)
        self.record_player_scores(self.away_team, away_player_scores, tracker)

        self.update_records()
        
        # Record the weekly scores for each team
        tracker.record_team_week(self.home_team.name, self.week, self.home_score)
        tracker.record_team_week(self.away_team.name, self.week, self.away_score)
        
        # print(f"DEBUG: Matchup result - {self.home_team.name}: {self.home_score:.2f}, {self.away_team.name}: {self.away_score:.2f}")

    def record_player_scores(self, team, player_scores, tracker):
        for player_id, score in player_scores.items():
            tracker.record_player_score(player_id, self.week, score)
            player = next((p for p in team.players if p.sleeper_id == player_id), None)
            if player:
                player.record_weekly_score(self.week, score)