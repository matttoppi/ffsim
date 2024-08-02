class SimulationMatchup:
    def __init__(self, home_team, away_team, week):
        self.home_team = home_team
        self.away_team = away_team
        self.week = week
        self.home_score = None
        self.away_score = None
        
        print(f"Matchup scheduled for Week {week}: {home_team.name} vs. {away_team.name}")
    
    def simulate(self, scoring_settings):
        self.home_score = self.home_team.simulate_week(self.week, scoring_settings)
        self.away_score = self.away_team.simulate_week(self.week, scoring_settings)
        
        if self.home_score > self.away_score:
            self.home_team.update_record(True, False, self.away_score, self.week)
            self.away_team.update_record(False, False, self.home_score, self.week)
        elif self.away_score > self.home_score:
            self.home_team.update_record(False, False, self.away_score, self.week)
            self.away_team.update_record(True, False, self.home_score, self.week)
        else:
            self.home_team.update_record(False, True, self.away_score, self.week)
            self.away_team.update_record(False, True, self.home_score, self.week)
        
        print(f"Week {self.week} result: {self.home_team.name} {self.home_score:.2f} - {self.away_score:.2f} {self.away_team.name}")
