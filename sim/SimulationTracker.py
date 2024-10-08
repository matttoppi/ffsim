from collections import defaultdict
import math


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
        self.player_injuries = defaultdict(list)  # Add this line
        self.player_games_missed = defaultdict(list)
        self.player_total_games_missed = defaultdict(int)
        
        self.special_team_scores = defaultdict(lambda: defaultdict(list))
        self.division1_ids = league.division1_ids
        self.division2_ids = league.division2_ids
        self.division_standings = {1: defaultdict(list), 2: defaultdict(list)}
        self.playoff_appearances = defaultdict(int)
        self.division_wins = defaultdict(int)
        self.championships = defaultdict(int)
        self.team_weekly_results = defaultdict(lambda: defaultdict(list))
        
        self.average_results = {}  # Initialize the average_results dictionary
        
    


    
    def calculate_averages(self):
        for team_name, seasons in self.team_season_results.items():
            avg_wins = sum(season['wins'] for season in seasons) / len(seasons)
            avg_points = sum(season['points_for'] for season in seasons) / len(seasons)
            self.average_results[team_name] = {
                'avg_wins': avg_wins,
                'avg_points': avg_points
            }

    def get_overall_standings(self):
        
        return sorted(
            [(team_name, stats['avg_wins'], stats['avg_points']) 
             for team_name, stats in self.average_results.items()],
            key=lambda x: (x[1], x[2]),
            reverse=True
        )

    def get_division_standings(self, division):
        division_teams = [team for team in self.league.rosters if team.roster_id in getattr(self, f'division{division}_ids')]
        return sorted(
            [(team.name, self.average_results[team.name]['avg_wins'], self.average_results[team.name]['avg_points']) 
             for team in division_teams],
            key=lambda x: (x[1], x[2]),
            reverse=True
        )
    
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


    def update_best_worst_weeks(self, team_name, week, points):
        if team_name not in self.best_weeks or points > self.best_weeks[team_name]['points']:
            self.best_weeks[team_name] = {'week': week, 'points': points}
        if team_name not in self.worst_weeks or points < self.worst_weeks[team_name]['points']:
            self.worst_weeks[team_name] = {'week': week, 'points': points}


    # def record_season_standings(self, standings):
    #     for position, team_data in enumerate(standings, 1):
    #         team_name, wins, points = team_data
    #         self.season_standings[team_name].append((position, wins, points))

    def update_best_worst_seasons(self, team_name, wins, points):
        if team_name not in self.best_seasons or wins > self.best_seasons[team_name]['wins'] or \
        (wins == self.best_seasons[team_name]['wins'] and points > self.best_seasons[team_name]['points']):
            self.best_seasons[team_name] = {'wins': wins, 'points': points}
        
        if team_name not in self.worst_seasons or wins < self.worst_seasons[team_name]['wins'] or \
        (wins == self.worst_seasons[team_name]['wins'] and points < self.worst_seasons[team_name]['points']):
            self.worst_seasons[team_name] = {'wins': wins, 'points': points}
        


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
        
    
    def set_num_simulations(self, num_simulations):
        self.num_simulations = num_simulations

    
    def get_player_average_score(self, player_id):
        if player_id not in self.player_scores:
            return 0, 0, 0, 0, 0

        all_scores = [score for week_scores in self.player_scores[player_id].values() for score in week_scores if score > 0]
        games_played = self.player_games_played.get(player_id, 0)

        if not all_scores or games_played == 0:
            return 0, 0, 0, 0, 0

        avg_score = sum(all_scores) / games_played
        total_scores = sum(all_scores)
        min_score = min(all_scores) if all_scores else 0
        max_score = max(all_scores) if all_scores else 0

        return avg_score, total_scores, games_played, min_score, max_score

    def get_player_from_sleeper_id(self, sleeper_id):
        for team in self.league.rosters:
            for player in team.players:
                if str(player.sleeper_id) == str(sleeper_id):
                    return player
        return None
    
        
    def record_player_score(self, player_id, week, score):
        if player_id not in self.player_scores:
            self.player_scores[player_id] = {}
        if week not in self.player_scores[player_id]:
            self.player_scores[player_id][week] = []
        self.player_scores[player_id][week].append(score)
        
        # Track that the player played this week (if score > 0)
        if score > 0:
            self.player_games_played[player_id] = self.player_games_played.get(player_id, 0) + 1
            

    

    def print_player_average_scores(self, top_n=5):
        print(f"\nTop {top_n} Players by Average Score for Each Team:")
        
        header = f"{'Player':<25}{'Pos':<5}{'Avg':<8}{'Wks/Ssn':<10}{'Min':<8}{'Max':<8}"
        separator = "-" * 64

        for team in self.league.rosters:
            print(f"\n{team.name}:")
            print(separator)
            print(header)
            print(separator)
            
            player_scores = []
            for player in team.players:
                avg_score, total_scores, total_weeks, min_score, max_score = self.get_player_average_score(player.sleeper_id)
                if total_weeks > 0:
                    weeks_per_season = total_weeks / self.num_simulations
                    player_scores.append((player, avg_score, weeks_per_season, min_score, max_score))
            
            top_players = sorted(player_scores, key=lambda x: x[1], reverse=True)
            
            for player, avg_score, weeks_per_season, min_score, max_score in top_players:
                weeks_per_season = math.ceil(weeks_per_season)
                print(f"{player.name:<25}{player.position:<5}{avg_score:<8.2f}{weeks_per_season:<10}{min_score:<8.2f}{max_score:<8.2f}")
            
            print(separator)
    
    def record_player_injury(self, player_id, games_missed):
        self.player_injuries[player_id].append(games_missed)

    def record_player_games_missed(self, player_id, games_missed):
        if games_missed > 1:
            self.player_games_missed[player_id].append(games_missed)
            player = self.get_player_from_sleeper_id(player_id)
            # print(f"DEBUG: Recorded {games_missed} missed games for {player.full_name}")

    def record_total_games_missed(self, player_id, total_games_missed):
        self.player_total_games_missed[player_id] += total_games_missed

    def get_player_avg_games_missed(self, player_id):
        if player_id not in self.player_games_missed:
            return 0
        total_missed = sum(self.player_games_missed[player_id])
        num_simulations = self.num_simulations
        avg_missed = total_missed / num_simulations
        player = self.get_player_from_sleeper_id(player_id)
        # print(f"Player {player.name} missed total of {total_missed} games (injuries > 1 game) over {num_simulations} simulations. Average: {avg_missed:.5f}")
        return avg_missed

    def get_player_total_avg_games_missed(self, player_id):
        total_missed = self.player_total_games_missed[player_id]
        avg_missed = total_missed / self.num_simulations
        player = self.get_player_from_sleeper_id(player_id)
        # print(f"Player {player.name} missed total of {total_missed} games (all injuries) over {self.num_simulations} simulations. Average: {avg_missed:.5f}")
        return avg_missed
    
    
    
    def get_player_stats(self, player_id):
        if player_id not in self.player_scores:
            print(f"DEBUG: No scores recorded for player ID {player_id}")
            return None

        all_scores = [score for week_scores in self.player_scores[player_id].values() for score in week_scores]
        games_played = len(all_scores)

        if not all_scores:
            print(f"DEBUG: No scores recorded for player ID {player_id}")
            return None

        return {
            'avg_score': sum(all_scores) / games_played,
            'min_score': min(all_scores),
            'max_score': max(all_scores),
            'games_played': games_played,
            'all_scores': all_scores  # Include all scores in the stats
        }

    def print_top_players_by_position(self, top_n=30):
        print("\nTop Players by Position:")
        positions = ['QB', 'RB', 'WR', 'TE', 'KICKER', 'DEFENSE']

        for position in positions:
            print(f"\nTop {top_n} {position}s:")
            
            if position in ['KICKER', 'DEFENSE']:
                team_stats = []
                for team in self.league.rosters:
                    stats = self.get_special_team_stats(team.name, position)
                    if stats:
                        if position == 'DEFENSE':
                            defense_names = self.get_defense_names(team.name)
                            for defense_name in defense_names:
                                team_stats.append((defense_name, stats['avg_score'], stats['min_score'], stats['max_score'], 0))
                        else:
                            team_name = f"{team.name} {position}"
                            team_stats.append((team_name, stats['avg_score'], stats['min_score'], stats['max_score'], 0))
                    else:
                        print(f"DEBUG: No stats for {position} of {team.name}")

                sorted_stats = sorted(team_stats, key=lambda x: x[1], reverse=True)[:top_n]

                print(f"{'Rank':<5}{'Team':<30}{'Avg':<8}{'Min':<8}{'Max':<8}{'Avg Miss':<12}")
                print("-" * 71)
                for i, (team_name, avg_score, min_score, max_score, _) in enumerate(sorted_stats, 1):
                    print(f"{i:<5}{team_name:<30}{avg_score:<8.2f}{min_score:<8.2f}{max_score:<8.2f}{'N/A':<12}")
            else:
                players = [player for team in self.league.rosters for player in team.players if player.position == position]

                player_stats = []
                for player in players:
                    avg_score, total_score, games_played, min_score, max_score = self.get_player_average_score(player.sleeper_id)
                    avg_games_missed = self.get_player_avg_games_missed(player.sleeper_id)
                    if games_played > 0:
                        player_stats.append((player, avg_score, min_score, max_score, avg_games_missed))

                sorted_players = sorted(player_stats, key=lambda x: x[1], reverse=True)[:top_n]

                print(f"{'Rank':<5}{'Player':<30}{'Avg':<8}{'Min':<8}{'Max':<8}{'Avg Miss':<12}")
                print("-" * 71)
                for i, (player, avg_score, min_score, max_score, avg_missed) in enumerate(sorted_players, 1):
                    player_name = f"{player.first_name} {player.last_name}"
                    print(f"{i:<5}{player_name:<30}{avg_score:<8.2f}{min_score:<8.2f}{max_score:<8.2f}{avg_missed:<12.5f}")
                
        
        
        
    def get_defense_names(self, team_name):
        defenses = []
        for team in self.league.rosters:
            if team.name == team_name:
                for player in team.players:
                    if player.position.upper() == 'DEF':
                        defenses.append(f"{player.team} {player.position}")
        return defenses if defenses else [f"{team_name} DEF"]  # Fallback if not found
    
    
    
    def record_special_team_score(self, team_name, position, week, score):
        if position == 'DEFENSE':
            defenses = self.get_defense_names(team_name)
            for defense in defenses:
                key = f"{position}_{defense}"
                self.special_team_scores[key][week].append(score)
        else:
            key = f"{position}_{team_name}"
            self.special_team_scores[key][week].append(score)

    def get_special_team_stats(self, team_name, position):
        if position == 'DEFENSE':
            defenses = self.get_defense_names(team_name)
            all_scores = []
            for defense in defenses:
                key = f"{position}_{defense}"
                if key in self.special_team_scores:
                    all_scores.extend([score for week_scores in self.special_team_scores[key].values() for score in week_scores])
        else:
            key = f"{position}_{team_name}"
            if key not in self.special_team_scores:
                print(f"DEBUG: No scores recorded for {position} of {team_name}")
                return None
            all_scores = [score for week_scores in self.special_team_scores[key].values() for score in week_scores]
        
        if not all_scores:
            print(f"DEBUG: No non-zero scores for {position} of {team_name}")
            return None
        
        return {
            'avg_score': sum(all_scores) / len(all_scores),
            'min_score': min(all_scores),
            'max_score': max(all_scores),
            'games_played': len(all_scores)
        }
        
        
        
    
    def record_playoff_results(self, playoff_teams, division_winners, champion):
        for team in playoff_teams:
            self.playoff_appearances[team.name] += 1
        for winner in division_winners:
            self.division_wins[winner.name] += 1
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
        
        # Create a list of teams with their stats, sorted by playoff appearances
        team_stats = []
        for team in self.league.rosters:
            appearances = self.playoff_appearances[team.name]
            div_wins = self.division_wins[team.name]
            champs = self.championships[team.name]
            appearance_rate = appearances / self.num_simulations * 100
            div_win_rate = div_wins / self.num_simulations * 100
            champ_rate = champs / self.num_simulations * 100
            team_stats.append((team.name, appearances, appearance_rate, div_wins, div_win_rate, champs, champ_rate))
        
        # Sort the list by playoff appearances (descending)
        team_stats.sort(key=lambda x: x[1], reverse=True)
        
        # Print the sorted and formatted stats
        for team_name, appearances, appearance_rate, div_wins, div_win_rate, champs, champ_rate in team_stats:
            print(f"{team_name:<25}{appearances:>3} ({appearance_rate:>6.1f}%)          {div_wins:>3} ({div_win_rate:>6.1f}%)     {champs:>3} ({champ_rate:>6.1f}%)")
        
    def print_champions(self):
        print("\nChampionship Results:")
        sorted_champs = sorted(self.championships.items(), key=lambda x: x[1], reverse=True)
        for team, wins in sorted_champs:
            win_rate = wins / self.num_simulations * 100
            print(f"{team}: {wins} championships ({win_rate:.1f}%)")
        

    def record_team_week(self, team_name, week, points):
        self.team_weekly_results[team_name][week].append(points)

    def get_team_stats(self, team_name):
        seasons = self.team_season_results[team_name]
        if seasons:
            avg_wins = sum(season['wins'] for season in seasons) / len(seasons)
            avg_points = sum(season['points_for'] for season in seasons) / len(seasons)
            return {
                'avg_wins': avg_wins,
                'avg_points': avg_points,
            }
        return None

            
            
    def record_team_season(self, team_name, wins, losses, ties, points_for, points_against):
        print(f"DEBUG: Recording season results for {team_name} - {wins} wins, {points_for:.2f} points")
        self.team_season_results[team_name].append({
            'wins': wins,
            'losses': losses,
            'ties': ties,
            'points_for': points_for,
            'points_against': points_against
        })
        
        # Record division standings
        roster_id = next((team.roster_id for team in self.league.rosters if team.name == team_name), None)
        if roster_id in self.division1_ids:
            self.division_standings[1][team_name].append((wins, points_for))
        elif roster_id in self.division2_ids:
            self.division_standings[2][team_name].append((wins, points_for))


            
    def print_projected_standings(self):
        print("\nProjected Overall Standings:")
        self._print_standings(self.get_overall_standings())
        
        print("\nProjected Division 1 Standings:")
        self._print_standings(self.get_division_standings(1))
        
        print("\nProjected Division 2 Standings:")
        self._print_standings(self.get_division_standings(2))

    def _print_standings(self, standings):
        for i, (team_name, avg_wins, avg_points) in enumerate(standings, 1):
            print(f"{i}. {team_name}: {avg_wins:.2f} wins | Points per week: {avg_points/14:.2f} points")



    