from collections import defaultdict

class SimulationTracker:
    def __init__(self, league):
        self.league = league
        self.weekly_player_scores = defaultdict(lambda: defaultdict(list))
        self.team_season_results = defaultdict(list)
        self.team_weekly_results = defaultdict(lambda: defaultdict(list))
        self.season_standings = defaultdict(list)
        self.best_seasons = {}
        self.worst_seasons = {}
        self.best_weeks = {}
        self.worst_weeks = {}

    def record_player_score(self, player_id, week, score):
        self.weekly_player_scores[player_id][week].append(score)

    def record_team_season(self, team_name, wins, losses, ties, points_for, points_against):
        self.team_season_results[team_name].append({
            'wins': wins,
            'losses': losses,
            'ties': ties,
            'points_for': points_for,
            'points_against': points_against
        })
        self.update_best_worst_seasons(team_name, wins, points_for)

    def record_team_week(self, team_name, week, points):
        self.team_weekly_results[team_name][week].append(points)
        self.update_best_worst_weeks(team_name, week, points)

    def update_best_worst_seasons(self, team_name, wins, points):
        if team_name not in self.best_seasons or wins > self.best_seasons[team_name]['wins']:
            self.best_seasons[team_name] = {'wins': wins, 'points': points}
        if team_name not in self.worst_seasons or wins < self.worst_seasons[team_name]['wins']:
            self.worst_seasons[team_name] = {'wins': wins, 'points': points}

    def update_best_worst_weeks(self, team_name, week, points):
        if team_name not in self.best_weeks or points > self.best_weeks[team_name]['points']:
            self.best_weeks[team_name] = {'week': week, 'points': points}
        if team_name not in self.worst_weeks or points < self.worst_weeks[team_name]['points']:
            self.worst_weeks[team_name] = {'week': week, 'points': points}

    def get_player_stats(self, player_id):
        all_scores = [score for week_scores in self.weekly_player_scores[player_id].values() for score in week_scores if score > 0]
        if all_scores:
            return {
                'avg_score': sum(all_scores) / len(all_scores),
                'min_score': min(all_scores),
                'max_score': max(all_scores)
            }
        return None

    def record_season_standings(self, standings):
        for position, team_data in enumerate(standings, 1):
            team_name, wins, points = team_data
            self.season_standings[team_name].append((position, wins, points))

    def update_best_worst_seasons(self, team_name, wins, points):
        standings = self.season_standings[team_name]
        if not standings:
            return

        current_season = standings[-1]  # Get the most recent season's data
        position = current_season[0]

        if team_name not in self.best_seasons or wins > self.best_seasons[team_name]['wins'] or \
           (wins == self.best_seasons[team_name]['wins'] and points > self.best_seasons[team_name]['points']):
            self.best_seasons[team_name] = {'wins': wins, 'points': points, 'position': position}

        if team_name not in self.worst_seasons or wins < self.worst_seasons[team_name]['wins'] or \
           (wins == self.worst_seasons[team_name]['wins'] and points < self.worst_seasons[team_name]['points']):
            self.worst_seasons[team_name] = {'wins': wins, 'points': points, 'position': position}

    def get_team_stats(self, team_name):
        seasons = self.team_season_results[team_name]
        if seasons:
            avg_wins = sum(season['wins'] for season in seasons) / len(seasons)
            avg_points = sum(season['points_for'] for season in seasons) / len(seasons)
            return {
                'avg_wins': avg_wins,
                'avg_points': avg_points,
                'best_season': self.best_seasons[team_name],
                'worst_season': self.worst_seasons[team_name],
                'best_week': self.best_weeks[team_name],
                'worst_week': self.worst_weeks[team_name]
            }
        return None