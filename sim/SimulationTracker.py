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
        self.player_games_played = defaultdict(int)
        self.player_games_missed = defaultdict(list)  # Add this line
        self.player_injuries = defaultdict(list)  # Add this line


    def get_player_avg_injured_games(self, player_id):
        if player_id not in self.player_injuries:
            return 0
        return sum(self.player_injuries[player_id]) / len(self.player_injuries[player_id])
        
        

        
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

    

    def record_team_week(self, team_name, week, points):
        self.team_weekly_results[team_name][week].append(points)
        self.update_best_worst_weeks(team_name, week, points)


    def update_best_worst_weeks(self, team_name, week, points):
        if team_name not in self.best_weeks or points > self.best_weeks[team_name]['points']:
            self.best_weeks[team_name] = {'week': week, 'points': points}
        if team_name not in self.worst_weeks or points < self.worst_weeks[team_name]['points']:
            self.worst_weeks[team_name] = {'week': week, 'points': points}


    def record_season_standings(self, standings):
        for position, team_data in enumerate(standings, 1):
            team_name, wins, points = team_data
            self.season_standings[team_name].append((position, wins, points))

    def update_best_worst_seasons(self, team_name, wins, points):
        if team_name not in self.best_seasons or wins > self.best_seasons[team_name]['wins'] or \
        (wins == self.best_seasons[team_name]['wins'] and points > self.best_seasons[team_name]['points']):
            self.best_seasons[team_name] = {'wins': wins, 'points': points}
        
        if team_name not in self.worst_seasons or wins < self.worst_seasons[team_name]['wins'] or \
        (wins == self.worst_seasons[team_name]['wins'] and points < self.worst_seasons[team_name]['points']):
            self.worst_seasons[team_name] = {'wins': wins, 'points': points}
            
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
                'worst_season': worst_season,
                'best_week': self.best_weeks.get(team_name, {'week': 0, 'points': 0}),
                'worst_week': self.worst_weeks.get(team_name, {'week': 0, 'points': 0})
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
        self.update_best_worst_seasons(team_name, wins, points_for)


    # def get_team_stats(self, team_name):
    #     seasons = self.team_season_results[team_name]
    #     if seasons:
    #         avg_wins = sum(season['wins'] for season in seasons) / len(seasons)
    #         avg_points = sum(season['points_for'] for season in seasons) / len(seasons)
    #         best_season = max(seasons, key=lambda x: (x['wins'], x['points_for']))
    #         worst_season = min(seasons, key=lambda x: (x['wins'], x['points_for']))
    #         return {
    #             'avg_wins': avg_wins,
    #             'avg_points': avg_points,
    #             'best_season': best_season,
    #             'worst_season': worst_season
    #         }
    #     return None
    
    def set_num_simulations(self, num_simulations):
        self.num_simulations = num_simulations

    def get_player_stats(self, player_id):
        all_scores = [score for week_scores in self.player_scores[player_id].values() for score in week_scores if score > 0]
        games_played = self.player_games_played[player_id]
        if all_scores:
            return {
                'avg_score': sum(all_scores) / len(all_scores),
                'min_score': min(all_scores),
                'max_score': max(all_scores),
                'games_played': games_played
            }
        return None
        
    def get_player_average_score(self, player_id):
        # if player_id not in self.player_weekly_scores:
        #     player = self.get_player_from_sleeper_id(player_id)
        #     print(f"DEBUG: No scores recorded for player {player.full_name} ({player.position})")
        #     return 0
        scores = [score for week_scores in self.player_weekly_scores[player_id].values() for score in week_scores]
        avg = sum(scores) / len(scores) if scores else 0
        # player = self.get_player_from_sleeper_id(player_id)
        # print(f"DEBUG: Player {player.full_name} ({player.position}) average score: {avg:.2f} from {len(scores)} recorded scores")
        return avg

    def get_player_from_sleeper_id(self, sleeper_id):
        for team in self.league.rosters:
            for player in team.players:
                if str(player.sleeper_id) == str(sleeper_id):
                    return player
        return None
    
    
    
    def print_top_players_by_position(self, top_n=30):
        print("\nTop Players by Position:")
        positions = ['QB', 'RB', 'WR', 'TE']

        for position in positions:
            print(f"\nTop {top_n} {position}s:")
            players = [player for team in self.league.rosters for player in team.players if player.position == position]
            
            player_stats = []
            for player in players:
                stats = self.get_player_stats(player.sleeper_id)
                avg_games_missed = self.get_player_avg_games_missed(player.sleeper_id)
                if stats:
                    player_stats.append((player, stats['avg_score'], stats['min_score'], stats['max_score'], avg_games_missed))

            sorted_players = sorted(player_stats, key=lambda x: x[1], reverse=True)[:top_n]

            print(f"{'Rank':<5}{'Player':<30}{'Avg':<8}{'Min':<8}{'Max':<8}{'Avg Miss':<8}")
            print("-" * 67)
            for i, (player, avg_score, min_score, max_score, avg_missed) in enumerate(sorted_players, 1):
                player_name = f"{player.first_name} {player.last_name}"
                print(f"{i:<5}{player_name:<30}{avg_score:<8.2f}{min_score:<8.2f}{max_score:<8.2f}{avg_missed:<8.2f}")
                
    def print_projected_standings(self):
        print("\nProjected Final Standings:")
        avg_results = []
        for team in self.league.rosters:
            stats = self.get_team_stats(team.name)
            if stats:
                avg_wins = stats['avg_wins']
                avg_points = stats['avg_points']
                avg_results.append((team.name, avg_wins, avg_points))
            else:
                print(f"DEBUG: No stats found for {team.name}")

        sorted_results = sorted(avg_results, key=lambda x: (x[1], x[2]), reverse=True)

        for i, (team_name, avg_wins, avg_points) in enumerate(sorted_results, 1):
            print(f"{i}. {team_name}: {avg_wins:.2f} wins | Points per week: {avg_points/18:.2f} points")
            
            


    def print_results(self):
        print("\nMonte Carlo Simulation Results:")
        self.print_top_players_by_position()
        self.print_projected_standings()
        
        
        
    def record_player_score(self, player_id, week, score):
        if player_id not in self.player_scores:
            self.player_scores[player_id] = {}
        if week not in self.player_scores[player_id]:
            self.player_scores[player_id][week] = []
        self.player_scores[player_id][week].append(score)

    def get_player_average_score(self, player_id):
        if player_id not in self.player_scores:
            return 0, 0, 0
        
        all_scores = [score for week_scores in self.player_scores[player_id].values() for score in week_scores]
        total_scores = sum(all_scores)
        total_weeks = sum(len(week_scores) for week_scores in self.player_scores[player_id].values())
        avg_score = total_scores / len(all_scores) if all_scores else 0
        
        return avg_score, total_scores, total_weeks

    def print_player_average_scores(self):
        print("\nAverage Scores Per Week for Each Player:")
        for team in self.league.rosters:
            print(f"\n{team.name}:")
            for player in team.players:
                avg_score, total_scores, total_weeks = self.get_player_average_score(player.sleeper_id)
                print(f"  {player.name} ({player.position}): Avg: {avg_score:.2f}, Total: {total_scores:.2f}, Weeks: {total_weeks}")
                
            

    def record_player_games_missed(self, player_id, games_missed):
        self.player_games_missed[player_id].append(games_missed)

    def get_player_avg_games_missed(self, player_id):
        if player_id not in self.player_games_missed:
            return 0
        return sum(self.player_games_missed[player_id]) / len(self.player_games_missed[player_id])

    def record_player_injury(self, player_id, injured_weeks):
        self.player_injuries[player_id].append(injured_weeks)