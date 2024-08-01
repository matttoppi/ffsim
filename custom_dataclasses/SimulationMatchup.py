


class SimulationMatchup:
    def __init__(self, team1, team2, team1_score, team2_score):
        self.team1 = team1
        self.team2 = team2
        self.team1_score = team1_score
        self.team2_score = team2_score

    def __str__(self):
        return f"{self.team1} {self.team1_score} - {self.team2_score} {self.team2}"

    def __repr__(self):
        return f"{self.team1} {self.team1_score} - {self.team2_score} {self.team2}"