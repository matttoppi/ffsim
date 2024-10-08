from tqdm import tqdm
from sim.SimulationClasses.SimulationSeason import SimulationSeason
from sim.SimulationTracker import SimulationTracker
from sim.SimulationVisualizer import SimulationVisualizer




class MonteCarloSimulation:
    def __init__(self, league, num_simulations=1000):
        self.league = league
        self.num_simulations = num_simulations
        self.tracker = SimulationTracker(self.league)
        self.tracker.set_num_simulations(num_simulations)
        self.visualizer = SimulationVisualizer(self.league, self.tracker)


    def run(self):
        for sim in tqdm(range(self.num_simulations), desc="Running Simulations", unit="sim"):
            # Reset all team stats before each simulation
            for team in self.league.rosters:
                team.reset_stats()
            
            season = SimulationSeason(self.league, self.tracker)
            season.simulate()
            self.record_season_results(season)
            print(f"DEBUG: Simulation {sim + 1} completed")
        
        self.tracker.calculate_averages()  # Calculate averages after all simulations
        self.tracker.print_results()
        self.tracker.print_player_average_scores()
        self.visualizer.plot_scoring_distributions(self.tracker)

    def record_season_results(self, season):
        for team in self.league.rosters:
            self.tracker.record_team_season(
                team.name, team.wins, team.losses, team.ties, team.points_for, team.points_against
            )
            for player in team.players:
                for week, score in player.weekly_scores.items():
                    self.tracker.record_player_score(player.sleeper_id, week, score)
        
        # Record playoff results
        playoff_sim = season.playoff_sim
        self.tracker.record_playoff_results(
            playoff_sim.bracket.teams,
            [playoff_sim.bracket.division1_winner, playoff_sim.bracket.division2_winner],
            playoff_sim.champion
        )

    def print_team_results(self):
        for team_name in self.league.rosters:
            stats = self.tracker.get_team_stats(team_name)
            if stats:
                print(f"\n{team_name}:")
                print(f"  Average Wins: {stats['avg_wins']:.2f}")
                print(f"  Average Points per Season: {stats['avg_points']:.2f}")
                print(f"  Best Season: {stats['best_season']['wins']} wins, {stats['best_season']['points_for']:.2f} points")
                print(f"  Worst Season: {stats['worst_season']['wins']} wins, {stats['worst_season']['points_for']:.2f} points")


