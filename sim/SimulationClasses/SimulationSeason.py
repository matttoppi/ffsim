class SimulationSeason:
    def __init__(self, year: int, season: str):
        self.year = year
        self.season = season

    def __str__(self):
        return f"{self.season} {self.year}"