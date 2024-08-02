class SimulationMatchup:
    def __init__(self, team1, team2, team1_score, team2_score):
        self.team1 = team1
        self.team2 = team2
        self.team1_score = None
        self.team2_score = None
        
        print(f"Matchup scheduled (created): {team1} vs. {team2}")
        
