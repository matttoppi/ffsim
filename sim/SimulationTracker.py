from collections import defaultdict
import math
import numpy as np


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
        self.team_season_averages = defaultdict(list)   
        
        self.special_team_scores = defaultdict(lambda: defaultdict(list))
        self.division1_ids = league.division1_ids
        self.division2_ids = league.division2_ids
        self.division_standings = {1: defaultdict(list), 2: defaultdict(list)}
        self.playoff_appearances = defaultdict(int)
        self.division_wins = defaultdict(int)
        self.championships = defaultdict(int)
        self.team_weekly_results = defaultdict(lambda: defaultdict(list))
        self.percentile_breakdowns = {}
        self.team_name_map = {}
        self.player_season_averages = defaultdict(list)
        
        self.average_results = {}  # Initialize the average_results dictionary
        self.best_seasons = {}
        self.worst_seasons = {}
        self.playoff_ranks = {
            "Champion": 1,
            "Runner-up": 2,
            "Lost in Semis": 3,
            "Lost in First Round": 4,
            "Missed Playoffs": 5
        }
    

    def _is_better_season(self, new_season, old_season):
            # First, compare playoff ranks
            if new_season['playoff_rank'] < old_season['playoff_rank']:
                return True
            elif new_season['playoff_rank'] > old_season['playoff_rank']:
                return False
            
            # If playoff ranks are the same (including championships)
            if new_season['playoff_rank'] == old_season['playoff_rank']:
                # Compare wins first
                if new_season['wins'] > old_season['wins']:
                    return True
                elif new_season['wins'] < old_season['wins']:
                    return False
                
                # If wins are equal, compare points
                return new_season['points_for'] > old_season['points_for']
            
            return False

    def record_team_season(self, team_name, wins, losses, ties, points_for, points_against, playoff_result):
        normalized_name = self.normalize_team_name(team_name)
        season_data = {
            'wins': wins,
            'losses': losses,
            'ties': ties,
            'points_for': points_for,
            'points_against': points_against,
            'playoff_result': playoff_result,
            'playoff_rank': self.playoff_ranks.get(playoff_result, 5),
            'record': f"{wins}-{losses}-{ties}",
            'player_performances': {}
        }
        
        # print(f"Team: {team_name} - Wins: {wins} - Losses: {losses} - Ties: {ties} - Points For: {points_for} - Points Against: {points_against} - Playoff Result: {playoff_result} - Playoff Rank: {playoff_rank}")

        self.team_season_results[normalized_name].append(season_data)
        
        # Calculate and record season average
        season_average = points_for / 14  # Assuming 14-week regular season
        self.team_season_averages[normalized_name].append(season_average)

        # Update best season if necessary
        if normalized_name not in self.best_seasons or self._is_better_season(season_data, self.best_seasons[normalized_name]):
            self.best_seasons[normalized_name] = season_data.copy()

        # Update worst season if necessary
        if normalized_name not in self.worst_seasons or self._is_worse_season(season_data, self.worst_seasons[normalized_name]):
            self.worst_seasons[normalized_name] = season_data.copy()
    
    def get_top_performers(self, team_name, n=5):
        team = next((team for team in self.league.rosters if team.name == team_name), None)
        if not team:
            return []
        
        player_scores = []
        for player in team.players:
            avg_score, _, _, _, _ = self.get_player_average_score(player.sleeper_id)
            player_scores.append((player, avg_score))
            
        if n == "all":
            return sorted(player_scores, key=lambda x: x[1], reverse=True)
        
        return sorted(player_scores, key=lambda x: x[1], reverse=True)[:n]

    def get_top_players_by_position(self, position, n=10):
        all_players = [player for team in self.league.rosters for player in team.players if player.position == position]
        
        player_scores = []
        for player in all_players:
            avg_score, _, _, _, _ = self.get_player_average_score(player.sleeper_id)
            player_scores.append((player, avg_score))
        
        return sorted(player_scores, key=lambda x: x[1], reverse=True)[:n]
    


    
    def get_player_avg_injured_games(self, player_id):
        if player_id not in self.player_injuries:
            return 0
        return sum(self.player_injuries[player_id]) / len(self.player_injuries[player_id])
        
        
 
        
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

    def update_best_worst_seasons(self, team_name, wins, points):
        if team_name not in self.best_seasons or wins > self.best_seasons[team_name]['wins'] or \
        (wins == self.best_seasons[team_name]['wins'] and points > self.best_seasons[team_name]['points']):
            self.best_seasons[team_name] = {'wins': wins, 'points': points}
        
        if team_name not in self.worst_seasons or wins < self.worst_seasons[team_name]['wins'] or \
        (wins == self.worst_seasons[team_name]['wins'] and points < self.worst_seasons[team_name]['points']):
            self.worst_seasons[team_name] = {'wins': wins, 'points': points}
    

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
        if player_id is None:
            print(f"Warning: Attempted to record score for player with None ID. Week: {week}, Score: {score}")
            return

        if not isinstance(player_id, (int, str)):
            print(f"Warning: Invalid player_id type. Expected int or str, got {type(player_id)}. Week: {week}, Score: {score}")
            return

        if score is None:
            print(f"Warning: Attempted to record None score for player {player_id} in week {week}")
            return

        if player_id not in self.player_scores:
            self.player_scores[player_id] = {}
        if week not in self.player_scores[player_id]:
            self.player_scores[player_id][week] = []
        self.player_scores[player_id][week].append(score)
        
        # Track that the player played this week (if score > 0)
        if isinstance(score, (int, float)) and score > 0:
            self.player_games_played[player_id] = self.player_games_played.get(player_id, 0) + 1

        # print(f"DEBUG: Recorded score for player {player_id} in week {week}: {score}")

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


            
            
    def print_projected_standings(self):
        print("\nProjected Overall Standings:")
        self._print_standings(self.get_overall_standings())
        
        print("\nProjected Division 1 Standings:")
        self._print_standings(self.get_division_standings(1))
        
        print("\nProjected Division 2 Standings:")
        self._print_standings(self.get_division_standings(2))

    def _print_standings(self, standings):
        for i, (team_name, avg_wins, avg_points) in enumerate(standings, 1):
            avg_weeks = self.average_results[team_name]['avg_weeks']
            points_per_week = avg_points / avg_weeks if avg_weeks > 0 else 0
            print(f"{i}. {team_name}: {avg_wins:.2f} wins | Points per week: {points_per_week:.2f} points")
            
    def print_results(self):
        self.calculate_averages()  # Ensure averages are calculated before printing results
        print("\nMonte Carlo Simulation Results:")
        self.print_projected_standings()
        self.print_playoff_stats()
        self.print_top_players_by_position()
        
        

    

    def _is_worse_season(self, new_season, old_season):
        # First, compare playoff ranks
        if new_season['playoff_rank'] > old_season['playoff_rank']:
            return True
        elif new_season['playoff_rank'] < old_season['playoff_rank']:
            return False
        
        # If playoff ranks are the same (including "missed playoffs")
        if new_season['playoff_rank'] == old_season['playoff_rank']:
            # Compare wins
            if new_season['wins'] < old_season['wins']:
                return True
            elif new_season['wins'] > old_season['wins']:
                return False
            
            # If wins are equal, compare points
            return new_season['points_for'] < old_season['points_for']
        
        return False

    
            

    
    def get_overall_standings(self):
        return sorted(
            [(team_name, stats['avg_wins'], stats['avg_points']) 
             for team_name, stats in self.average_results.items()],
            key=lambda x: (x[1], x[2]),
            reverse=True
        )


        
    def get_player_best_season_average(self, player_id):
        if player_id not in self.player_scores:
            return 0

        best_season_avg = 0
        for sim in range(self.num_simulations):
            season_scores = []
            for week in range(1, 18):  # Assuming 17-week season
                week_scores = self.player_scores[player_id].get(week, [])
                if sim < len(week_scores):
                    season_scores.append(week_scores[sim])
            
            if season_scores:
                season_avg = sum(season_scores) / len(season_scores)
                best_season_avg = max(best_season_avg, season_avg)

        return best_season_avg
    
    
    
    
    def calculate_averages(self):
        for team in self.league.rosters:
            team_name = self.normalize_team_name(team.name)
            seasons = self.team_season_results[team_name]
            if seasons:
                wins = [season['wins'] for season in seasons]
                points_for = [season['points_for'] for season in seasons]
                
                self.percentile_breakdowns[team_name] = {
                    'wins': {
                        'avg': np.mean(wins),
                        '10%': np.percentile(wins, 10),
                        '25%': np.percentile(wins, 25),
                        '75%': np.percentile(wins, 75),
                        '90%': np.percentile(wins, 90)
                    },
                    'points_for': {
                        'avg': np.mean(points_for),
                        '10%': np.percentile(points_for, 10),
                        '25%': np.percentile(points_for, 25),
                        '75%': np.percentile(points_for, 75),
                        '90%': np.percentile(points_for, 90)
                    }
                }
                
                self.average_results[team_name] = {
                    'avg_wins': np.mean(wins),
                    'avg_points': np.mean(points_for),
                    'avg_weeks': len(seasons)
                }
            else:
                self.percentile_breakdowns[team_name] = {
                    'wins': {'avg': 0, '10%': 0, '25%': 0, '75%': 0, '90%': 0},
                    'points_for': {'avg': 0, '10%': 0, '25%': 0, '75%': 0, '90%': 0}
                }
                self.average_results[team_name] = {
                    'avg_wins': 0,
                    'avg_points': 0,
                    'avg_weeks': 0
                }
    
    
    def normalize_team_name(self, name):
        """Normalize team name to ensure consistent key usage."""
        normalized = name.strip().upper()
        self.team_name_map[normalized] = name  # Store original name
        return normalized

    def get_original_team_name(self, normalized_name):
        """Get the original team name from a normalized name."""
        return self.team_name_map.get(normalized_name, normalized_name)



    def calculate_averages(self):
        for team in self.league.rosters:
            normalized_name = self.normalize_team_name(team.name)
            seasons = self.team_season_results[normalized_name]
            if seasons:
                wins = [season['wins'] for season in seasons]
                points_for = [season['points_for'] for season in seasons]
                
                self.percentile_breakdowns[normalized_name] = {
                    'wins': {
                        'avg': np.mean(wins),
                        '10%': np.percentile(wins, 10),
                        '25%': np.percentile(wins, 25),
                        '75%': np.percentile(wins, 75),
                        '90%': np.percentile(wins, 90)
                    },
                    'points_for': {
                        'avg': np.mean(points_for),
                        '10%': np.percentile(points_for, 10),
                        '25%': np.percentile(points_for, 25),
                        '75%': np.percentile(points_for, 75),
                        '90%': np.percentile(points_for, 90)
                    }
                }
                
                self.average_results[normalized_name] = {
                    'avg_wins': np.mean(wins),
                    'avg_points': np.mean(points_for),
                    'avg_weeks': len(seasons)
                }
            else:
                self.percentile_breakdowns[normalized_name] = {
                    'wins': {'avg': 0, '10%': 0, '25%': 0, '75%': 0, '90%': 0},
                    'points_for': {'avg': 0, '10%': 0, '25%': 0, '75%': 0, '90%': 0}
                }
                self.average_results[normalized_name] = {
                    'avg_wins': 0,
                    'avg_points': 0,
                    'avg_weeks': 0
                }

    def get_overall_standings(self):
        return sorted(
            [(self.get_original_team_name(team_name), stats['avg_wins'], stats['avg_points']) 
             for team_name, stats in self.average_results.items()],
            key=lambda x: (x[1], x[2]),
            reverse=True
        )

    def get_division_standings(self, division):
        division_teams = [team for team in self.league.rosters if team.roster_id in getattr(self.league, f'division{division}_ids')]
        standings = []
        for team in division_teams:
            normalized_name = self.normalize_team_name(team.name)
            if normalized_name in self.average_results:
                standings.append((
                    self.get_original_team_name(normalized_name),
                    self.average_results[normalized_name]['avg_wins'],
                    self.average_results[normalized_name]['avg_points']
                ))
            else:
                print(f"Warning: No data found for team '{team.name}' (normalized: '{normalized_name}')")
                standings.append((team.name, 0, 0))  # Add default values
        return sorted(standings, key=lambda x: (x[1], x[2]), reverse=True)

    def get_percentile_breakdowns(self, team_name):
        normalized_name = self.normalize_team_name(team_name)
        return self.percentile_breakdowns.get(normalized_name, {})
    
    def get_player_worst_season_average(self, player_id):
        if player_id in self.player_scores:
            season_averages = []
            for season_scores in self.player_scores[player_id].values():
                if season_scores:  # Check if there are any scores for the season
                    season_average = sum(season_scores) / len(season_scores)
                    if season_average > 0:  # Only append non-zero averages
                        season_averages.append(season_average)
            
            # Return the minimum non-zero average, or 0 if all averages are 0
            return min(season_averages) if season_averages else 0
        return 0

    def get_team_stats(self, team_name):
        normalized_name = self.normalize_team_name(team_name)
        seasons = self.team_season_results[normalized_name]
        season_averages = self.team_season_averages[normalized_name]
        if seasons and season_averages:
            avg_wins = sum(season['wins'] for season in seasons) / len(seasons)
            avg_points = sum(season['points_for'] for season in seasons) / len(seasons)
            non_zero_averages = [avg for avg in season_averages if avg > 0]
            min_season_avg = min(non_zero_averages) if non_zero_averages else 0
            max_season_avg = max(season_averages)
            
            # Get worst non-zero season average for each player
            player_worst_seasons = {}
            player_all_seasons = {}  # Debug: Store all seasons for each player
            for season in seasons:
                for player_id, performance in season['player_performances'].items():
                    if player_id not in player_all_seasons:
                        player_all_seasons[player_id] = []
                    player_all_seasons[player_id].append(performance['avg_points'])
                    
                    if performance['avg_points'] > 0:
                        if player_id not in player_worst_seasons or performance['avg_points'] < player_worst_seasons[player_id]['avg_points']:
                            player_worst_seasons[player_id] = {
                                'avg_points': performance['avg_points'],
                                'total_points': performance['total_points'],
                                'games_played': performance['games_played'],
                                'weekly_scores': performance['weekly_scores'],
                                'season_modifier': performance['season_modifier'],
                                'out_for_season': performance.get('out_for_season', False)
                            }
            
            # Debug: Print all seasons for each player
            # print(f"Debug - All seasons for each player in {team_name}:")
            # for player_id, seasons in player_all_seasons.items():
            #     player = self.get_player_from_sleeper_id(player_id)
            #     print(f"{player.name if player else player_id}: {seasons}")
            
            # # Debug: Print worst seasons before filtering
            # # print(f"\nDebug - Worst seasons before filtering for {team_name}:")
            # for player_id, worst_season in player_worst_seasons.items():
            #     player = self.get_player_from_sleeper_id(player_id)
            #     print(f"{player.name if player else player_id}: {worst_season['avg_points']}")
            
            # Remove any remaining players with 0 average points
            player_worst_seasons = {k: v for k, v in player_worst_seasons.items() if v['avg_points'] > 0}
            
            # # Debug: Print worst seasons after filtering
            # print(f"\nDebug - Worst seasons after filtering for {team_name}:")
            # for player_id, worst_season in player_worst_seasons.items():
            #     player = self.get_player_from_sleeper_id(player_id)
            #     print(f"{player.name if player else player_id}: {worst_season['avg_points']}")
            
            return {
                'avg_wins': avg_wins,
                'avg_points': avg_points,
                'min_season_avg': min_season_avg,
                'max_season_avg': max_season_avg,
                'player_worst_seasons': player_worst_seasons
            }
        return None

    # Update other methods that use team names to use normalized names
    def record_points_lost_to_injury(self, team_name, week, points_lost):
        normalized_name = self.normalize_team_name(team_name)
        self.points_lost_to_injury[normalized_name][week].append(points_lost)

    def update_best_worst_weeks(self, team_name, week, points):
        normalized_name = self.normalize_team_name(team_name)
        if normalized_name not in self.best_weeks or points > self.best_weeks[normalized_name]['points']:
            self.best_weeks[normalized_name] = {'week': week, 'points': points}
        if normalized_name not in self.worst_weeks or points < self.worst_weeks[normalized_name]['points']:
            self.worst_weeks[normalized_name] = {'week': week, 'points': points}

    def record_injury(self, player, team_name, injury_duration):
        normalized_name = self.normalize_team_name(team_name)
        self.injury_stats[normalized_name]['injuries'] += 1
        self.injury_stats[normalized_name]['total_injury_duration'] += injury_duration
        self.injury_stats[normalized_name]['player_injuries'][player.sleeper_id] += 1
        self.injury_stats[normalized_name]['player_durations'][player.sleeper_id] += injury_duration

    def record_injury_impact(self, team_name, week, points_lost):
        normalized_name = self.normalize_team_name(team_name)
        if len(self.injury_impact_stats[normalized_name]['points_lost_per_week']) <= week:
            self.injury_impact_stats[normalized_name]['points_lost_per_week'].extend([0] * (week + 1 - len(self.injury_impact_stats[normalized_name]['points_lost_per_week'])))
        self.injury_impact_stats[normalized_name]['points_lost_per_week'][week] += points_lost
        self.injury_impact_stats[normalized_name]['total_points_lost'] += points_lost

    def record_player_season(self, team_name, player_id, weekly_scores, season_modifier):
        normalized_name = self.normalize_team_name(team_name)
        player = self.get_player_from_sleeper_id(player_id)
        
        if player and player.out_for_season_flag:
            performance = {
                'weekly_scores': {},
                'total_points': 0,
                'avg_points': 0,
                'games_played': 0,
                'season_modifier': season_modifier,
                'out_for_season': True
            }
        else:
            total_points = sum(weekly_scores.values())
            games_played = len([score for score in weekly_scores.values() if score > 0])
            avg_points = total_points / games_played if games_played > 0 else 0
            performance = {
                'weekly_scores': weekly_scores,
                'total_points': total_points,
                'avg_points': avg_points,
                'games_played': games_played,
                'season_modifier': season_modifier,
                'out_for_season': False
            }
        # Record the season average for this player
        self.player_season_averages[player_id].append(performance['avg_points'])

        # Update player performances for the current season
        current_season = self.team_season_results[normalized_name][-1]
        current_season['player_performances'][player_id] = performance

        # Update player performances for best and worst seasons if applicable
        if self.best_seasons[normalized_name] == current_season:
            self.best_seasons[normalized_name]['player_performances'][player_id] = performance.copy()

        if self.worst_seasons[normalized_name] == current_season:
            self.worst_seasons[normalized_name]['player_performances'][player_id] = performance.copy()
            
    def get_best_season_breakdown(self, team_name):
        normalized_name = self.normalize_team_name(team_name)
        if normalized_name not in self.best_seasons:
            return None

        best_season = self.best_seasons[normalized_name]
        breakdown = {
            'team_name': self.get_original_team_name(normalized_name),
            'record': f"{best_season['wins']}-{best_season['losses']}-{best_season['ties']}",
            'points_for': best_season['points_for'],
            'points_against': best_season['points_against'],
            'playoff_result': best_season['playoff_result'],
            'player_performances': []
        }

        for player_id, performance in best_season['player_performances'].items():
            player = self.get_player_from_sleeper_id(player_id)
            if player:
                # Filter out weeks 15, 16, and 17
                filtered_weekly_scores = {week: score for week, score in performance['weekly_scores'].items() if int(week) < 15}
                total_points = sum(filtered_weekly_scores.values())
                games_played = len([score for score in filtered_weekly_scores.values() if score > 0])
                avg_points = total_points / games_played if games_played > 0 else 0

                breakdown['player_performances'].append({
                    'name': player.name,
                    'position': player.position,
                    'total_points': total_points,
                    'avg_points': avg_points,
                    'weekly_scores': filtered_weekly_scores,
                    'modifier': performance['season_modifier'],
                    'games_played': games_played,
                    'out_for_season': performance.get('out_for_season', False)
                })

        breakdown['player_performances'].sort(key=lambda x: x['total_points'], reverse=True)
        # Include players with 0 games played (likely out for season)
        breakdown['player_performances'] = [player for player in breakdown['player_performances']]

        return breakdown

    def get_worst_season_breakdown(self, team_name):
        normalized_name = self.normalize_team_name(team_name)
        if normalized_name not in self.worst_seasons:
            return None

        worst_season = self.worst_seasons[normalized_name]
        breakdown = {
            'team_name': self.get_original_team_name(normalized_name),
            'record': f"{worst_season['wins']}-{worst_season['losses']}-{worst_season['ties']}",
            'points_for': worst_season['points_for'],
            'points_against': worst_season['points_against'],
            'playoff_result': worst_season['playoff_result'],
            'player_performances': []
        }

        for player_id, performance in worst_season['player_performances'].items():
            player = self.get_player_from_sleeper_id(player_id)
            if player:
                # Filter out weeks 15, 16, and 17
                filtered_weekly_scores = {week: score for week, score in performance['weekly_scores'].items() if int(week) < 15}
                total_points = sum(filtered_weekly_scores.values())
                games_played = len([score for score in filtered_weekly_scores.values() if score > 0])
                avg_points = total_points / games_played if games_played > 0 else 0

                breakdown['player_performances'].append({
                    'name': player.name,
                    'position': player.position,
                    'total_points': total_points,
                    'avg_points': avg_points,
                    'weekly_scores': filtered_weekly_scores,
                    'modifier': performance['season_modifier'],
                    'games_played': games_played,
                    'out_for_season': performance.get('out_for_season', False)
                })

        breakdown['player_performances'].sort(key=lambda x: x['total_points'], reverse=True)
        # Include players with 0 games played (likely out for season)
        breakdown['player_performances'] = [player for player in breakdown['player_performances']]

        return breakdown
    
    
    def get_player_season_stats(self, player_id):
        season_averages = self.player_season_averages[player_id]
        if season_averages:
            return {
                'min_season_avg': min(season_averages),
                'max_season_avg': max(season_averages),
                'overall_avg': sum(season_averages) / len(season_averages)
            }
        return None

    def get_team_player_stats(self, team_name):
        team = next((team for team in self.league.rosters if team.name == team_name), None)
        if not team:
            return []
        
        player_stats = []
        for player in team.players:
            stats = self.get_player_season_stats(player.sleeper_id)
            if stats:
                player_stats.append({
                    'name': player.name,
                    'position': player.position,
                    'min_season_avg': stats['min_season_avg'],
                    'max_season_avg': stats['max_season_avg'],
                    'overall_avg': stats['overall_avg']
                })
        
        return sorted(player_stats, key=lambda x: x['overall_avg'], reverse=True)