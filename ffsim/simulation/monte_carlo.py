import random

import numpy as np
from tqdm import tqdm
from ffsim.simulation.season import SimulationSeason
from ffsim.simulation.tracker import SimulationTracker
from ffsim.simulation.visualizer import SimulationVisualizer


class MonteCarloSimulation:
    def __init__(self, league, num_simulations=1000, seed=2026, regular_season_weeks=14):
        self.league = league
        self.num_simulations = num_simulations
        self.seed = seed
        self.regular_season_weeks = regular_season_weeks
        self.tracker = SimulationTracker(self.league, num_simulations, regular_season_weeks)
        self.visualizer = SimulationVisualizer(self.league, self.tracker)

    def run(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        for _ in tqdm(range(self.num_simulations), desc="Running Simulations", unit="sim"):
            for team in self.league.rosters:
                team.reset_stats()

            season = SimulationSeason(self.league, self.tracker, self.regular_season_weeks)
            season.simulate()
            self.record_season_results(season)

        self.tracker.calculate_averages()
        return self.tracker.to_dict(self.seed)

    def record_season_results(self, season):
        for team in self.league.rosters:
            self.tracker.record_team_season(team.name, team.wins, team.points_for)

        playoff_sim = season.playoff_sim
        self.tracker.record_playoff_results(
            playoff_sim.bracket.teams,
            [playoff_sim.bracket.division1_winner, playoff_sim.bracket.division2_winner],
            playoff_sim.champion,
        )
