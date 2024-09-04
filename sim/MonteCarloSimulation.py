from tqdm import tqdm
from sim.SimulationClasses.SimulationSeason import SimulationSeason
from sim.SimulationTracker import SimulationTracker
from sim.SimulationVisualizer import SimulationVisualizer
from sim.PDFReportGenerator import PDFReportGenerator
import time
import math




class MonteCarloSimulation:


    def __init__(self, league, num_simulations=1000):
        self.league = league
        self.num_simulations = num_simulations
        self.tracker = SimulationTracker(self.league)
        self.tracker.set_num_simulations(num_simulations)
        self.visualizer = SimulationVisualizer(self.league, self.tracker)
        self.pdf_report_generator = PDFReportGenerator(self.league, self.tracker, self.visualizer)
        self.matchups = self.load_matchups()  # Load matchups once

    def load_matchups(self):
        # Create a temporary SimulationSeason instance to use its methods
        temp_season = SimulationSeason(self.league, self.tracker)
        return temp_season.load_or_fetch_matchups()

    def run(self):
        start_time = time.time()
        
        with tqdm(total=self.num_simulations, desc="Running Simulations", unit="sim") as pbar:
            for sim in range(self.num_simulations):
                # Reset all team stats before each simulation
                for team in self.league.rosters:
                    team.reset_stats()
                
                season = SimulationSeason(self.league, self.tracker, self.matchups)  # Pass matchups here
                season.simulate()
                self.record_season_results(season)
                
                # Update progress bar
                pbar.update(1)
                
                # Calculate and display time information
                elapsed_time = time.time() - start_time
                elapsed_mins = elapsed_time / 60
                sims_per_second = (sim + 1) / elapsed_time
                remaining_sims = self.num_simulations - (sim + 1)
                estimated_remaining_time = remaining_sims / sims_per_second
                
                # Convert remaining time to minutes, with one decimal place
                remaining_mins = estimated_remaining_time / 60
                
                pbar.set_postfix({
                    'Elapsed': f'{elapsed_mins:.0f}m {elapsed_time % 60:.0f}s',
                    'Remaining': f'{remaining_mins:.1f}m',
                    'Sims/s': f'{sims_per_second:.1f}'
                })

        self.tracker.calculate_averages()  # Calculate averages after all simulations
        self.visualizer.plot_scoring_distributions(self.tracker)

        total_time = time.time() - start_time
        total_mins = math.ceil(total_time / 60)
        print(f"\nTotal simulation time: {total_mins}m")

    def record_season_results(self, season):
        for team in self.league.rosters:
            self.tracker.record_team_season(
                team.name,
                team.wins,
                team.losses,
                team.ties,
                team.points_for,
                team.points_against,
                team.playoff_result
            )
            if not self.tracker.team_has_seasons(team.name):
                logging.warning(f"No seasons recorded for team {team.name}")
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


    def print_best_season_breakdowns(self):
        print("\nBest Season Breakdowns:")
        for team in self.league.rosters:
            breakdown = self.tracker.get_best_season_breakdown(team.name)
            if breakdown:
                print(f"\n{breakdown['team_name']}:")
                print(f"Record: {breakdown['record']}")
                print(f"Points For: {breakdown['points_for']:.2f}")
                print(f"Points Against: {breakdown['points_against']:.2f}")
                print(f"Playoff Result: {breakdown['playoff_result']}")
                print("\nTop Performers:")
                for i, player in enumerate(breakdown['player_performances'], 1):
                    print(f"{i}. {player['name']} ({player['position']}): {player['total_points']:.2f} pts, {player['avg_points']:.2f} pts/game - Modifier: {player['modifier']:.2f}")
                
            x = input("Press Enter to continue")