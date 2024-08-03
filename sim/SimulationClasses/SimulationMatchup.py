import random

class SimulationMatchup:
    def __init__(self, home_team, away_team, week):
        self.home_team = home_team
        self.away_team = away_team
        self.week = week
        self.home_score = None
        self.away_score = None

    def simulate(self, scoring_settings, tracker):
        self.home_score = self.simulate_team(self.home_team, scoring_settings, self.week)
        self.away_score = self.simulate_team(self.away_team, scoring_settings, self.week)
        
        self.update_records()
        
        tracker.record_team_week(self.home_team.name, self.week, self.home_score)
        tracker.record_team_week(self.away_team.name, self.week, self.away_score)
        
        print(f"Week {self.week} result: {self.home_team.name} {self.home_score:.2f} - {self.away_score:.2f} {self.away_team.name}")

    def simulate_team(self, team, scoring_settings, week):
        team.fill_starters(week)
        return sum(player.simulate_week(week, scoring_settings) for player in team.get_active_starters(week))

    def calculate_team_score(self, team, scoring_settings):
        total_score = 0
        for position, players in team.starters.items():
            for player in players:
                total_score += player.calculate_score(scoring_settings, self.week)
        return total_score
    
    
    def check_injuries_and_fill_starters(self, team):
        for player in team.players:
            self.check_for_injuries(player, team)
        team.fill_starters(self.week)

    def check_for_injuries(self, player, team):
        if player.position in ['DEF', 'K']:
            return

        injury_roll = random.random()
        if injury_roll < player.injury_probability_game:
            injury_duration = self.generate_injury_duration(player)
            injury_time = random.uniform(0, 1)  # When during the game the injury occurred
            player.simulation_injury = {
                'start_week': self.week,
                'duration': injury_duration,
                'return_week': self.week + injury_duration,
                'injury_time': injury_time
            }
            team.sim_injured_players.append(player)
            print(f"New injury for {player.name} on {team.name} for {injury_duration:.2f} weeks")

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