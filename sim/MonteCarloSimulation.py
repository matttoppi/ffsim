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

    def run(self):
        for _ in tqdm(range(self.num_simulations), desc="Running Simulations", unit="sim"):
            for team in self.league.rosters:  # Changed from .values() to direct iteration
                team.reset_stats()
            season = SimulationSeason(self.league, self.tracker)
            season.simulate()
            self.record_season_results(season)
        self.tracker.print_results()
        self.tracker.print_player_average_scores()
            
    def record_season_results(self, season):
        print("DEBUG: Recording season results")
        for team in self.league.rosters:  # Changed from .values() to direct iteration
            self.tracker.record_team_season(
                team.name, team.wins, team.losses, team.ties, team.points_for, team.points_against
            )
            print(f"DEBUG: Recorded season for {team.name} - W: {team.wins}, L: {team.losses}, T: {team.ties}, PF: {team.points_for}, PA: {team.points_against}")
            for player in team.players:
                for week, score in player.weekly_scores.items():
                    self.tracker.record_player_score(player.sleeper_id, week, score)
    

    def print_team_results(self):
        for team_name in self.league.rosters:
            stats = self.tracker.get_team_stats(team_name)
            if stats:
                print(f"\n{team_name}:")
                print(f"  Average Wins: {stats['avg_wins']:.2f}")
                print(f"  Average Points per Season: {stats['avg_points']:.2f}")
                print(f"  Best Season: {stats['best_season']['wins']} wins, {stats['best_season']['points_for']:.2f} points")
                print(f"  Worst Season: {stats['worst_season']['wins']} wins, {stats['worst_season']['points_for']:.2f} points")

