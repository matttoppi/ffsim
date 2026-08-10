from collections import defaultdict
import math


class SimulationTracker:
    def __init__(self, league, num_simulations):
        self.league = league
        self.num_simulations = num_simulations
        self.team_season_results = defaultdict(list)
        self.player_scores = defaultdict(lambda: defaultdict(list))
        self.player_games_missed = defaultdict(list)
        self.special_team_scores = defaultdict(lambda: defaultdict(list))
        self.playoff_appearances = defaultdict(int)
        self.division_wins = defaultdict(int)
        self.championships = defaultdict(int)
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
        roster_ids = getattr(self.league, f"division{division}_ids")
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
        scores = [
            score
            for weekly_scores in self.player_scores[player_id].values()
            for score in weekly_scores
            if score > 0
        ]
        if not scores:
            return 0, 0, 0, 0, 0
        return sum(scores) / len(scores), sum(scores), len(scores), min(scores), max(scores)

    def record_player_score(self, player_id, week, score):
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
        if games_missed:
            self.player_games_missed[player_id].append(games_missed)

    def get_player_avg_games_missed(self, player_id):
        return sum(self.player_games_missed[player_id]) / self.num_simulations

    def print_top_players_by_position(self, top_n=30):
        print("\nTop Players by Position:")
        for position in ["QB", "RB", "WR", "TE", "KICKER", "DEFENSE"]:
            print(f"\nTop {top_n} {position}s:")
            if position in {"KICKER", "DEFENSE"}:
                self._print_special_teams(position, top_n)
            else:
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

    def _print_special_teams(self, position, top_n):
        stats = []
        for team in self.league.rosters:
            team_stats = self.get_special_team_stats(team.name, position)
            if not team_stats:
                continue
            names = self.get_defense_names(team.name) if position == "DEFENSE" else [f"{team.name} {position}"]
            for name in names:
                stats.append((name, team_stats["avg_score"], team_stats["min_score"], team_stats["max_score"]))

        print(f"{'Rank':<5}{'Team':<30}{'Avg':<8}{'Min':<8}{'Max':<8}{'Avg Miss':<12}")
        print("-" * 71)
        for rank, (name, average, minimum, maximum) in enumerate(
            sorted(stats, key=lambda result: result[1], reverse=True)[:top_n], 1
        ):
            print(f"{rank:<5}{name:<30}{average:<8.2f}{minimum:<8.2f}{maximum:<8.2f}{'N/A':<12}")

    def get_defense_names(self, team_name):
        names = [
            f"{player.team} {player.position}"
            for team in self.league.rosters
            if team.name == team_name
            for player in team.players
            if player.position.upper() == "DEF"
        ]
        return names or [f"{team_name} DEF"]

    def record_special_team_score(self, team_name, position, week, score):
        names = self.get_defense_names(team_name) if position == "DEFENSE" else [team_name]
        for name in names:
            self.special_team_scores[f"{position}_{name}"][week].append(score)

    def get_special_team_stats(self, team_name, position):
        names = self.get_defense_names(team_name) if position == "DEFENSE" else [team_name]
        scores = [
            score
            for name in names
            for weekly_scores in self.special_team_scores[f"{position}_{name}"].values()
            for score in weekly_scores
        ]
        if not scores:
            return None
        return {
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
        }

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
        self.print_top_players_by_position()

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

    def record_team_season(self, team_name, wins, points_for):
        self.team_season_results[team_name].append({"wins": wins, "points_for": points_for})

    def print_projected_standings(self):
        print("\nProjected Overall Standings:")
        self._print_standings(self.get_overall_standings())
        print("\nProjected Division 1 Standings:")
        self._print_standings(self.get_division_standings(1))
        print("\nProjected Division 2 Standings:")
        self._print_standings(self.get_division_standings(2))

    @staticmethod
    def _print_standings(standings):
        for rank, (team_name, average_wins, average_points) in enumerate(standings, 1):
            print(
                f"{rank}. {team_name}: {average_wins:.2f} wins | "
                f"Points per week: {average_points / 14:.2f} points"
            )
