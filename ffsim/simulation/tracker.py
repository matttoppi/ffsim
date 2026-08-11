from collections import defaultdict
import math

import numpy as np


class SimulationTracker:
    def __init__(
        self,
        league,
        num_simulations,
        regular_season_weeks=14,
        track_players=True,
        keep_samples=False,
    ):
        self.league = league
        self.num_simulations = num_simulations
        self.regular_season_weeks = regular_season_weeks
        self.track_players = track_players
        self.keep_samples = keep_samples
        self.team_season_results = defaultdict(list)
        self.player_scores = defaultdict(lambda: defaultdict(list))
        self.player_stats = defaultdict(lambda: [0.0, 0, None, None])
        self.player_games_missed = defaultdict(int)
        self.playoff_appearances = defaultdict(int)
        self.division_wins = defaultdict(int)
        self.championships = defaultdict(int)
        self.seeds = defaultdict(lambda: defaultdict(int))
        self.average_results = {}

    def calculate_averages(self):
        for team_name, seasons in self.team_season_results.items():
            self.average_results[team_name] = {
                "avg_wins": sum(season["wins"] for season in seasons) / len(seasons),
                "avg_points": sum(season["points_for"] for season in seasons) / len(seasons),
            }

    def get_overall_standings(self):
        return sorted(
            [
                (team_name, stats["avg_wins"], stats["avg_points"])
                for team_name, stats in self.average_results.items()
            ],
            key=lambda result: (result[1], result[2]),
            reverse=True,
        )

    def get_division_standings(self, division):
        roster_ids = self.league.divisions[division]
        return sorted(
            [
                (
                    team.name,
                    self.average_results[team.name]["avg_wins"],
                    self.average_results[team.name]["avg_points"],
                )
                for team in self.league.rosters
                if team.roster_id in roster_ids
            ],
            key=lambda result: (result[1], result[2]),
            reverse=True,
        )

    def get_player_average_score(self, player_id):
        total, games, minimum, maximum = self.player_stats[player_id]
        if not games:
            return 0, 0, 0, 0, 0
        return total / games, total, games, minimum, maximum

    def record_player_score(self, player_id, week, score, played=True):
        if not self.track_players or not played:
            return
        stats = self.player_stats[player_id]
        stats[0] += score
        stats[1] += 1
        stats[2] = score if stats[2] is None else min(stats[2], score)
        stats[3] = score if stats[3] is None else max(stats[3], score)
        if self.keep_samples:
            self.player_scores[player_id][week].append(score)

    def print_player_average_scores(self, top_n=5):
        print(f"\nTop {top_n} Players by Average Score for Each Team:")
        header = f"{'Player':<25}{'Pos':<5}{'Avg':<8}{'Wks/Ssn':<10}{'Min':<8}{'Max':<8}"
        separator = "-" * 64

        for team in self.league.rosters:
            print(f"\n{team.name}:\n{separator}\n{header}\n{separator}")
            player_scores = []
            for player in team.players:
                average, _, games, minimum, maximum = self.get_player_average_score(player.sleeper_id)
                if games:
                    player_scores.append(
                        (player, average, math.ceil(games / self.num_simulations), minimum, maximum)
                    )

            for player, average, weeks, minimum, maximum in sorted(
                player_scores, key=lambda result: result[1], reverse=True
            )[:top_n]:
                print(
                    f"{player.name:<25}{player.position:<5}{average:<8.2f}"
                    f"{weeks:<10}{minimum:<8.2f}{maximum:<8.2f}"
                )
            print(separator)

    def record_player_games_missed(self, player_id, games_missed):
        if self.track_players:
            self.player_games_missed[player_id] += games_missed

    def get_player_avg_games_missed(self, player_id):
        return self.player_games_missed[player_id] / self.num_simulations

    def print_top_players_by_position(self, top_n=30):
        print("\nTop Players by Position:")
        for position in ["QB", "RB", "WR", "TE", "K", "DEF"]:
            print(f"\nTop {top_n} {position}s:")
            self._print_position_players(position, top_n)

    def _print_position_players(self, position, top_n):
        stats = []
        for team in self.league.rosters:
            for player in team.players:
                if player.position != position:
                    continue
                average, _, games, minimum, maximum = self.get_player_average_score(player.sleeper_id)
                if games:
                    stats.append(
                        (
                            player,
                            average,
                            minimum,
                            maximum,
                            self.get_player_avg_games_missed(player.sleeper_id),
                        )
                    )

        print(f"{'Rank':<5}{'Player':<30}{'Avg':<8}{'Min':<8}{'Max':<8}{'Avg Miss':<12}")
        print("-" * 71)
        for rank, (player, average, minimum, maximum, missed) in enumerate(
            sorted(stats, key=lambda result: result[1], reverse=True)[:top_n], 1
        ):
            print(
                f"{rank:<5}{player.name:<30}{average:<8.2f}{minimum:<8.2f}"
                f"{maximum:<8.2f}{missed:<12.5f}"
            )

    def record_playoff_results(self, playoff_teams, division_winners, champion):
        for team in playoff_teams:
            self.playoff_appearances[team.name] += 1
        for team in division_winners:
            self.division_wins[team.name] += 1
        self.championships[champion.name] += 1

    def print_results(self):
        print("\nMonte Carlo Simulation Results:")
        self.print_projected_standings()
        self.print_playoff_stats()
        if self.track_players:
            self.print_top_players_by_position()

    def to_dict(self, seed):
        teams = {}
        for team in self.league.rosters:
            averages = self.average_results[team.name]
            teams[team.name] = {
                "average_wins": float(averages["avg_wins"]),
                "average_points": float(averages["avg_points"]),
                "average_points_per_week": float(
                    averages["avg_points"] / self.regular_season_weeks
                ),
                "playoff_probability": self.playoff_appearances[team.name]
                / self.num_simulations,
                "division_win_probability": self.division_wins[team.name]
                / self.num_simulations,
                "championship_probability": self.championships[team.name]
                / self.num_simulations,
                "win_percentiles": _percentiles(
                    [season["wins"] for season in self.team_season_results[team.name]]
                ),
                "points_percentiles": _percentiles(
                    [season["points_for"] for season in self.team_season_results[team.name]]
                ),
                "seed_probabilities": {
                    str(seed): count / self.num_simulations
                    for seed, count in sorted(self.seeds[team.name].items())
                },
                "top_two_probability": sum(
                    self.seeds[team.name][seed] for seed in (1, 2)
                ) / self.num_simulations,
                "bottom_two_probability": sum(
                    self.seeds[team.name][seed]
                    for seed in range(max(1, len(self.league.rosters) - 1), len(self.league.rosters) + 1)
                ) / self.num_simulations,
            }

        results = {
            "league": {"id": self.league.league_id, "name": self.league.name},
            "simulations": self.num_simulations,
            "seed": seed,
            "teams": teams,
        }
        if self.track_players:
            results["players"] = self._players_to_dict()
        return results

    def _players_to_dict(self):
        players = {}
        for team in self.league.rosters:
            for player in team.players:
                average, total, games, minimum, maximum = self.get_player_average_score(
                    player.sleeper_id
                )
                players[str(player.sleeper_id)] = {
                    "name": player.name,
                    "team": team.name,
                    "position": player.position,
                    "average_score": float(average),
                    "total_score": float(total),
                    "games_per_simulation": games / self.num_simulations,
                    "minimum_score": float(minimum),
                    "maximum_score": float(maximum),
                    "average_games_missed": self.get_player_avg_games_missed(
                        player.sleeper_id
                    ),
                }
        return players

    def print_playoff_stats(self):
        print(f"\nPlayoff Statistics (Total Simulations: {self.num_simulations}):")
        print(f"{'Team':<25}{'Playoff Appearances':<23}{'Division Wins':<19}{'Championships':<15}")
        print("-" * 82)
        teams = sorted(
            self.league.rosters,
            key=lambda team: self.playoff_appearances[team.name],
            reverse=True,
        )
        for team in teams:
            appearances = self.playoff_appearances[team.name]
            division_wins = self.division_wins[team.name]
            championships = self.championships[team.name]
            print(
                f"{team.name:<25}{appearances:>3} ({appearances / self.num_simulations * 100:>6.1f}%)"
                f"          {division_wins:>3} ({division_wins / self.num_simulations * 100:>6.1f}%)"
                f"     {championships:>3} ({championships / self.num_simulations * 100:>6.1f}%)"
            )

    def record_team_season(self, team_name, wins, points_for, seed=None):
        self.team_season_results[team_name].append({"wins": wins, "points_for": points_for})
        if seed is not None:
            self.seeds[team_name][seed] += 1

    def print_projected_standings(self):
        print("\nProjected Overall Standings:")
        self._print_standings(self.get_overall_standings())
        for division in sorted(self.league.divisions):
            print(f"\nProjected Division {division} Standings:")
            self._print_standings(self.get_division_standings(division))

    def _print_standings(self, standings):
        for rank, (team_name, average_wins, average_points) in enumerate(standings, 1):
            print(
                f"{rank}. {team_name}: {average_wins:.2f} wins | "
                f"Points per week: {average_points / self.regular_season_weeks:.2f} points"
            )


def _percentiles(values):
    return {
        str(percentile): float(value)
        for percentile, value in zip((10, 25, 50, 75, 90), np.percentile(values, (10, 25, 50, 75, 90)))
    }
