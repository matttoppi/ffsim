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
        self.injury_stats = defaultdict(lambda: {'injuries': 0, 'total_injury_duration': 0, 'player_injuries': defaultdict(int), 'player_durations': defaultdict(int)})
        self.injury_impact_stats = defaultdict(lambda: {'points_lost_per_week': [], 'total_points_lost': 0})
        self.num_simulations = 0
        self.points_lost_to_injury = defaultdict(lambda: defaultdict(list))
        self.player_scores = defaultdict(lambda: defaultdict(list))
        self.player_weekly_scores = defaultdict(lambda: defaultdict(list))
        
        

        
    def record_points_lost_to_injury(self, team_name, week, points_lost):
        self.points_lost_to_injury[team_name][week].append(points_lost)
        
        
    def get_injury_impact_stats(self, team_name):
        weekly_averages = []
        for week in range(1, 18):  # Assuming a 17-week season
            week_losses = self.points_lost_to_injury[team_name][week]
            print(week_losses)
            if week_losses:
                avg_loss = sum(week_losses) / len(week_losses)
                weekly_averages.append(avg_loss)
        
        if weekly_averages:
            return {
                'avg_points_lost_per_week': sum(weekly_averages) / len(weekly_averages),
                'max_points_lost_in_week': max(weekly_averages),
                'total_points_lost_per_season': sum(weekly_averages)
            }
        return None

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
        all_scores = [score for week_scores in self.player_scores[player_id].values() for score in week_scores if score > 0]
        if all_scores:
            return {
                'avg_score': sum(all_scores) / len(all_scores),
                'min_score': min(all_scores),
                'max_score': max(all_scores),
                'all_scores': all_scores  # Add this line to include all scores
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


    def record_injury(self, player, team_name, injury_duration):
        self.injury_stats[team_name]['injuries'] += 1
        self.injury_stats[team_name]['total_injury_duration'] += injury_duration
        self.injury_stats[team_name]['player_injuries'][player.sleeper_id] += 1
        self.injury_stats[team_name]['player_durations'][player.sleeper_id] += injury_duration

    def record_injury_impact(self, team_name, week, points_lost):
        if len(self.injury_impact_stats[team_name]['points_lost_per_week']) <= week:
            self.injury_impact_stats[team_name]['points_lost_per_week'].extend([0] * (week + 1 - len(self.injury_impact_stats[team_name]['points_lost_per_week'])))
        self.injury_impact_stats[team_name]['points_lost_per_week'][week] += points_lost
        self.injury_impact_stats[team_name]['total_points_lost'] += points_lost

    def get_injury_stats(self):
        overall_stats = {
            'avg_injuries_per_season': 0,
            'avg_injury_duration': 0,
            'team_injury_stats': {}
        }
        total_injuries = 0
        total_duration = 0
        for team_name, stats in self.injury_stats.items():
            total_injuries += stats['injuries']
            total_duration += stats['total_injury_duration']
            avg_duration = stats['total_injury_duration'] / stats['injuries'] if stats['injuries'] > 0 else 0
            most_injured_player = max(stats['player_injuries'], key=stats['player_injuries'].get, default=None)
            overall_stats['team_injury_stats'][team_name] = {
                'avg_injury_duration': avg_duration,
                'player_id': most_injured_player
            }
        overall_stats['avg_injuries_per_season'] = total_injuries / self.num_simulations
        overall_stats['avg_injury_duration'] = total_duration / total_injuries if total_injuries > 0 else 0
        return overall_stats
    
    def set_num_simulations(self, num_simulations):
        self.num_simulations = num_simulations
        
        
    def get_injury_impact_stats(self, team_name):
        weekly_losses = self.points_lost_to_injury[team_name]
        if not weekly_losses:
            return {
                'avg_points_lost_per_week': 0,
                'max_points_lost_in_week': 0,
                'total_points_lost_per_season': 0
            }
        
        total_weeks = len(weekly_losses)
        total_points_lost = sum(sum(week_losses) for week_losses in weekly_losses.values())
        
        avg_points_lost_per_week = total_points_lost / (total_weeks * self.num_simulations) if total_weeks > 0 else 0
        max_points_lost_in_week = max(max(week_losses) for week_losses in weekly_losses.values()) if weekly_losses else 0
        
        return {
            'avg_points_lost_per_week': avg_points_lost_per_week,
            'max_points_lost_in_week': max_points_lost_in_week,
            'total_points_lost_per_season': total_points_lost / self.num_simulations
        }
        
        
    def record_team_season(self, team_name, wins, losses, ties, points_for, points_against):
        self.team_season_results[team_name].append({
            'wins': wins,
            'losses': losses,
            'ties': ties,
            'points_for': points_for,
            'points_against': points_against
        })


    def get_team_stats(self, team_name):
        seasons = self.team_season_results[team_name]
        if seasons:
            avg_wins = sum(season['wins'] for season in seasons) / len(seasons)
            avg_points = sum(season['points_for'] for season in seasons) / len(seasons)
            best_season = max(seasons, key=lambda x: (x['wins'], x['points_for']))
            worst_season = min(seasons, key=lambda x: (x['wins'], x['points_for']))
            return {
                'avg_wins': avg_wins,
                'avg_points': avg_points,
                'best_season': best_season,
                'worst_season': worst_season
            }
        return None

    def get_player_stats(self, player_id):
        all_scores = [score for week_scores in self.player_scores[player_id].values() for score in week_scores if score > 0]
        if all_scores:
            return {
                'avg_score': sum(all_scores) / len(all_scores),
                'min_score': min(all_scores),
                'max_score': max(all_scores)
            }
        return None

    def set_num_simulations(self, num_simulations):
        self.num_simulations = num_simulations
        
        
        
    def record_player_score(self, player_id, week, score):
        self.player_weekly_scores[player_id][week].append(score)

    def get_player_average_score(self, player_id):
        scores = [score for week_scores in self.player_weekly_scores[player_id].values() for score in week_scores]
        avg = sum(scores) / len(scores) if scores else 0
        return avg