from tqdm import tqdm
from sim.SimulationClasses.SimulationSeason import SimulationSeason
from sim.SimulationTracker import SimulationTracker
from sim.SimulationVisualizer import SimulationVisualizer

class MonteCarloSimulation:
    def __init__(self, league, num_simulations=1000):
        self.league = league
        self.num_simulations = num_simulations
        self.tracker = SimulationTracker(self.league)

    def run(self):
        for _ in tqdm(range(self.num_simulations), desc="Running Simulations", unit="sim"):
            for team in self.league.rosters:
                team.reset_stats()
            season = SimulationSeason(self.league, self.tracker)
            season.simulate()
            self.record_season_results(season)

    def record_season_results(self, season):
        for team in self.league.rosters:
            self.tracker.record_team_season(
                team.name, team.wins, team.losses, team.ties, team.points_for, team.points_against
            )
            for player in team.players:
                for week, score in player.weekly_scores.items():
                    self.tracker.record_player_score(player.sleeper_id, week, score)


    def print_results(self):
        print("\nMonte Carlo Simulation Results:")
        self.print_team_results()
        self.print_top_players_by_position()
        self.print_projected_standings()

    def print_team_results(self):
        for team_name in self.league.rosters:
            stats = self.tracker.get_team_stats(team_name)
            if stats:
                print(f"\n{team_name}:")
                print(f"  Average Wins: {stats['avg_wins']:.2f}")
                print(f"  Average Points per Season: {stats['avg_points']:.2f}")
                print(f"  Best Season: {stats['best_season']['wins']} wins, {stats['best_season']['points_for']:.2f} points")
                print(f"  Worst Season: {stats['worst_season']['wins']} wins, {stats['worst_season']['points_for']:.2f} points")

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

    def print_projected_standings(self):
        print("\nProjected Final Standings:")
        avg_results = []
        for team in self.league.rosters:
            stats = self.tracker.get_team_stats(team.name)
            if stats:
                avg_wins = stats['avg_wins']
                avg_points = stats['avg_points']
                avg_results.append((team.name, avg_wins, avg_points))

        sorted_results = sorted(avg_results, key=lambda x: (x[1], x[2]), reverse=True)

        for i, (team_name, avg_wins, avg_points) in enumerate(sorted_results, 1):
            print(f"{i}. {team_name}: {avg_wins:.2f} wins, {avg_points:.2f} points")