import random
from collections import defaultdict
from sim.LeagueSimulation import LeagueSimulation
from tqdm import tqdm

from sim.SimulationVisualizer import SimulationVisualizer

class MonteCarloSimulation:
    def __init__(self, league, num_simulations=1000):
        self.league = league
        self.num_simulations = num_simulations
        self.results = defaultdict(list)
        self.season_sim = LeagueSimulation(self.league)
        self.season_sim.fetch_all_matchups()  # Fetch matchups once
        self.visualizer = SimulationVisualizer(self.league, self.season_sim)

    def run(self):
        for _ in tqdm(range(self.num_simulations), desc="Running Simulations", unit="sim"):
            self.run_single_simulation()
    
        self.print_results()
        self.print_top_players_by_position()
        self.visualizer.plot_scoring_distributions()  # Use the visualizer here

    def run_single_simulation(self):
        # Reset league stats
        for team in self.league.rosters:
            team.wins = 0
            team.losses = 0
            team.ties = 0
            team.points_for = 0
            team.points_against = 0

        # Reset weekly player scores
        self.season_sim.weekly_player_scores.clear()

        # Run a full season simulation
        self.season_sim.run_simulation()

        # Store results
        for team in self.league.rosters:
            self.results[team.name].append({
                'wins': team.wins,
                'losses': team.losses,
                'ties': team.ties,
                'points_for': team.points_for,
                'points_against': team.points_against
            })

    def print_results(self):
        print("\nMonte Carlo Simulation Results:")
        weeks = 17  # Define the number of weeks in the season
        for team_name, simulations in self.results.items():
            avg_wins = sum(sim['wins'] for sim in simulations) / self.num_simulations
            avg_total_points = sum(sim['points_for'] for sim in simulations) / self.num_simulations
            avg_points_per_week = avg_total_points / weeks
            # makes playoffs if they are a top 6 team for that season
            playoff_appearances = sum(sim['wins'] >= 6 for sim in simulations) / self.num_simulations * 100

            print(f"{team_name}:")
            print(f"  Average Wins: {avg_wins:.2f}")
            print(f"  Average Points per Week: {avg_points_per_week:.2f}")
            print(f"  Playoff Appearance %: {playoff_appearances:.2f}%")
            print("\n")

    def print_average_starter_scores(self):
        self.season_sim.print_average_starter_scores()
        
    def print_top_players_by_position(self, top_n=30):
        print("\nTop Players by Position:")
        positions = ['QB', 'RB', 'WR', 'TE']

        for position in positions:
            print(f"\nTop {top_n} {position}s:")
            players = [player for team in self.league.rosters for player in team.players if player.position == position]
            
            print(f"Total {position}s: {len(players)}")
            
            # Calculate average, lowest, and highest weekly score for each player
            player_stats = []
            for player in players:
                weekly_scores = self.season_sim.weekly_player_scores.get(player.sleeper_id, {})
                all_scores = [score for week_scores in weekly_scores.values() for score in week_scores if score > 0]
                
                if all_scores:
                    avg_score = sum(all_scores) / len(all_scores)
                    lowest_score = min(all_scores)  # This will now be the lowest non-zero score
                    highest_score = max(all_scores)
                    player_stats.append((player, avg_score, lowest_score, highest_score))
                else:
                    # print(f"No scores for {player.full_name} (ID: {player.sleeper_id})")
                    pass

            print(f"Players with scores: {len(player_stats)}")

            # Sort players by average weekly score
            sorted_players = sorted(player_stats, key=lambda x: x[1], reverse=True)[:top_n]

            print(f"{'Rank':<5}{'Player':<30}{'Avg':<8}{'Low':<8}{'High':<8}")
            print("-" * 59)
            for i, (player, avg_score, lowest_score, highest_score) in enumerate(sorted_players, 1):
                player_name = f"{player.first_name} {player.last_name}"
                print(f"{i:<5}{player_name:<30}{avg_score:<8.2f}{lowest_score:<8.2f}{highest_score:<8.2f}")

        
    def print_projected_standings(self):
        print("\nProjected Final Standings:")
        avg_results = []
        for team_name, simulations in self.results.items():
            avg_wins = sum(sim['wins'] for sim in simulations) / self.num_simulations
            avg_points = sum(sim['points_for'] for sim in simulations) / self.num_simulations
            avg_results.append((team_name, avg_wins, avg_points))

        # Sort by average wins, then by average points
        sorted_results = sorted(avg_results, key=lambda x: (x[1], x[2]), reverse=True)

        for i, (team_name, avg_wins, avg_points) in enumerate(sorted_results, 1):
            print(f"{i}. {team_name}: {avg_wins:.2f} wins, {avg_points:.2f} points")