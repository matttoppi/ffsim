from tqdm import tqdm
from sim.SimulationClasses.SimulationSeason import SimulationSeason
from sim.SimulationTracker import SimulationTracker
from sim.SimulationVisualizer import SimulationVisualizer




class MonteCarloSimulation:
    def __init__(self, league, num_simulations=1000):
        self.league = league
        self.num_simulations = num_simulations
        self.tracker = SimulationTracker(self.league, num_simulations)
        self.visualizer = SimulationVisualizer(self.league, self.tracker)


    def run(self):
        for _ in tqdm(range(self.num_simulations), desc="Running Simulations", unit="sim"):
            # Reset all team stats before each simulation
            for team in self.league.rosters:
                team.reset_stats()
            
            season = SimulationSeason(self.league, self.tracker)
            season.simulate()
            self.record_season_results(season)

        self.tracker.calculate_averages()
        self.tracker.print_results()
        self.tracker.print_player_average_scores()
        self.visualizer.plot_scoring_distributions()

    def record_season_results(self, season):
        for team in self.league.rosters:
            self.tracker.record_team_season(
                team.name, team.wins, team.points_for
            )

        # Record playoff results
        playoff_sim = season.playoff_sim
        self.tracker.record_playoff_results(
            playoff_sim.bracket.teams,
            [playoff_sim.bracket.division1_winner, playoff_sim.bracket.division2_winner],
            playoff_sim.champion
        )
