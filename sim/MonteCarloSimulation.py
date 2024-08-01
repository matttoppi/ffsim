from sim.SimulationTracker import SimulationTracker
import random
from collections import defaultdict
from sim.LeagueSimulation import LeagueSimulation
from tqdm import tqdm

from sim.SimulationVisualizer import SimulationVisualizer


class MonteCarloSimulation:
    def __init__(self, league, num_simulations=1000, debugging=False):
        self.league = league
        self.num_simulations = num_simulations
        self.season_sim = LeagueSimulation(self.league, debug=debugging)
        self.season_sim.fetch_all_matchups()
        self.tracker = self.season_sim.tracker
        self.tracker.set_num_simulations(num_simulations)
        self.visualizer = SimulationVisualizer(self.league, self.tracker)  # Pass tracker directly



    def run_single_simulation(self):
        # Reset league stats and player injury statuses
        for team in self.league.rosters:
            team.wins = 0
            team.losses = 0
            team.ties = 0
            team.points_for = 0
            team.points_against = 0
            for player in team.players:
                player.simulation_injury = None


        # Run a full season simulation
        self.season_sim.run_simulation()

        # Calculate standings
        standings = sorted(
            [(team.name, team.wins, team.points_for) for team in self.league.rosters],
            key=lambda x: (x[1], x[2]),  # Sort by wins, then points
            reverse=True
        )

        # Record standings
        self.tracker.record_season_standings(standings)

        # Store results
        for team in self.league.rosters:
            self.tracker.record_team_season(
                team.name, team.wins, team.losses, team.ties, team.points_for, team.points_against
            )

    def run(self):
        for sim_num in tqdm(range(self.num_simulations), desc="Running Simulations", unit="sim"):
            # print(f"\nStarting simulation {sim_num + 1}")
            self.run_single_simulation()
        
        self.print_results()
        self.print_injury_stats()
        self.print_injury_impact()

        
        self.visualizer.plot_scoring_distributions() 
        
    def print_results(self):
        print("\nMonte Carlo Simulation Results:")
        for team_name in self.tracker.team_season_results.keys():
            stats = self.tracker.get_team_stats(team_name)
            if stats:
                print(f"{team_name}:")
                print(f"  Average Wins: {stats['avg_wins']:.2f}")
                print(f"  Average Points per Season: {stats['avg_points']:.2f}")
                print(f"  Best Season: {stats['best_season']['wins']} wins, {stats['best_season']['points']:.2f} points (Position: {stats['best_season']['position']})")
                print(f"  Worst Season: {stats['worst_season']['wins']} wins, {stats['worst_season']['points']:.2f} points (Position: {stats['worst_season']['position']})")
                print(f"  Best Week: Week {stats['best_week']['week']}, {stats['best_week']['points']:.2f} points")
                print(f"  Worst Week: Week {stats['worst_week']['week']}, {stats['worst_week']['points']:.2f} points")
                print("\n")
                
    def print_injury_stats(self):
        injury_stats = self.tracker.get_injury_stats()
        if injury_stats:
            print("\nInjury Statistics:")
            # print(f"Average Injuries per Season: {injury_stats['avg_injuries_per_season']:.2f}")
            # print(f"Average Injury Duration: {injury_stats['avg_injury_duration']:.2f} games")
            
            print("\nMost Injured Player per Team:")
            for team_name, team_stats in injury_stats['team_injury_stats'].items():
                most_injured_player = self.get_player_by_id(team_stats['player_id'])
                if most_injured_player:
                    print(f"\n{team_name}:")
                    print(f"  Player: {most_injured_player.full_name}")
                    print(f"  Team Average injury duration: {team_stats['avg_injury_duration']:.2f} games")
                else:
                    print(f"\n{team_name}: No player data found")

    def print_projected_standings(self):
        print("\nProjected Final Standings:")
        avg_results = []
        for team_name in self.tracker.team_season_results.keys():
            stats = self.tracker.get_team_stats(team_name)
            if stats:
                avg_wins = stats['avg_wins']
                avg_points = stats['avg_points']
                avg_results.append((team_name, avg_wins, avg_points))

        # Sort by average wins, then by average points
        sorted_results = sorted(avg_results, key=lambda x: (x[1], x[2]), reverse=True)

        for i, (team_name, avg_wins, avg_points) in enumerate(sorted_results, 1):
            print(f"{i}. {team_name}: {avg_wins:.2f} wins, {avg_points:.2f} points")

    def print_top_players_by_position(self, top_n=30):
        print("\nTop Players by Position:")
        positions = ['QB', 'RB', 'WR', 'TE']

        for position in positions:
            print(f"\nTop {top_n} {position}s:")
            players = [player for team in self.league.rosters for player in team.players if player.position == position]
            
            player_stats = []
            for player in players:
                stats = self.tracker.get_player_stats(player.sleeper_id)
                if stats:
                    player_stats.append((player, stats['avg_score'], stats['min_score'], stats['max_score']))

            sorted_players = sorted(player_stats, key=lambda x: x[1], reverse=True)[:top_n]

            print(f"{'Rank':<5}{'Player':<30}{'Avg':<8}{'Min':<8}{'Max':<8}")
            print("-" * 59)
            for i, (player, avg_score, min_score, max_score) in enumerate(sorted_players, 1):
                player_name = f"{player.first_name} {player.last_name}"
                print(f"{i:<5}{player_name:<30}{avg_score:<8.2f}{min_score:<8.2f}{max_score:<8.2f}")


    def get_player_by_id(self, player_id):
        for team in self.league.rosters:
            for player in team.players:
                if str(player.sleeper_id) == str(player_id):
                    return player
        return None
    
    def print_injury_impact(self):
        print("\nInjury Impact on Team Scores:")
        for team in self.league.rosters:
            stats = self.tracker.get_injury_impact_stats(team.name)
            if stats:
                print(f"\n{team.name}:")
                print(f"  Average points lost per week: {stats['avg_points_lost_per_week']:.2f}")
                print(f"  Maximum points lost in a week: {stats['max_points_lost_in_week']:.2f}")
                print(f"  Total points lost per season: {stats['total_points_lost_per_season']:.2f}")
            else:
                print(f"\n{team.name}: No injury impact data available")