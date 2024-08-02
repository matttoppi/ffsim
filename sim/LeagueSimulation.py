from collections import defaultdict
import random
import math
import requests
import os
from itertools import combinations
import json

from sim.SimulationTracker import SimulationTracker
from sim.SimulationClasses.PlayerSimulator import PlayerSimulator

class LeagueSimulation:
    def __init__(self, league, tracker):
        self.league = league
        self.tracker = tracker
        self.weeks = 18
        
    def run_simulation(self):
        for week in range(1, self.weeks + 1):
            self.simulate_week(week)

    def simulate_week(self, week):
        for team in self.league.rosters:
            team.simulation.check_for_injuries(week)
            team.simulation.simulate_week(week, self.league.scoring_settings)

        # Simulate matchups and update records
        matchups = self.get_matchups(week)
        for home_team, away_team in matchups:
            home_score = home_team.simulation.get_weekly_score(week)
            away_score = away_team.simulation.get_weekly_score(week)

            if home_score > away_score:
                home_team.simulation.update_record(won=True, tied=False, points_against=away_score)
                away_team.simulation.update_record(won=False, tied=False, points_against=home_score)
            elif away_score > home_score:
                home_team.simulation.update_record(won=False, tied=False, points_against=away_score)
                away_team.simulation.update_record(won=True, tied=False, points_against=home_score)
            else:
                home_team.simulation.update_record(won=False, tied=True, points_against=away_score)
                away_team.simulation.update_record(won=False, tied=True, points_against=home_score)

    
    
        
        
    # def load_sleeper_players(self):
    #     try:
    #         with open('sleeper_players.json', 'r') as f:
    #             players_list = json.load(f)
    #             self.sleeper_players = {str(player['player_id']): player for player in players_list if 'player_id' in player}
    #             print(f"Loaded {len(self.sleeper_players)} players from sleeper_players.json")
    #     except FileNotFoundError:
    #         print("sleeper_players.json not found. Player position lookup will not be available.")
    #         self.sleeper_players = {}
    #     except json.JSONDecodeError:
    #         print("Error decoding sleeper_players.json. Please check if the file is valid JSON.")
    #         self.sleeper_players = {}

    # def get_player_position(self, player_id):
    #     player = self.sleeper_players.get(str(player_id))
    #     if player:
    #         return player.get('position') or player.get('fantasy_positions', ['UNKNOWN'])[0]
    #     return 'UNKNOWN'
        
        
    # def fetch_all_matchups(self):
    #     if os.path.exists(self.matchups_file):
    #         print("Loading matchups from local storage...")
    #         try:
    #             with open(self.matchups_file, 'r') as f:
    #                 loaded_matchups = json.load(f)
    #                 # Convert string keys back to integers
    #                 self.matchups = {int(k): v for k, v in loaded_matchups.items()}
    #             print(f"Finished loading matchups from local storage for {len(self.matchups)} weeks.")
                
    #             # Verify the loaded data
    #             if not self.matchups:
    #                 raise ValueError("Loaded matchups dictionary is empty")
    #             sample_week = next(iter(self.matchups))
    #             if not isinstance(self.matchups[sample_week], list):
    #                 raise ValueError(f"Matchup data for week {sample_week} is not a list")
                
    #             # self._print_sample_matchup()
    #         except (json.JSONDecodeError, ValueError) as e:
    #             print(f"Error loading matchups from file: {e}. Fetching from API...")
    #             self._fetch_matchups_from_api()
    #     else:
    #         print("Local matchups file not found. Fetching from API...")
    #         self._fetch_matchups_from_api()

    # def fetch_all_matchups(self):
    #     if os.path.exists(self.matchups_file):
    #         print("Loading matchups from local storage...")
    #         try:
    #             with open(self.matchups_file, 'r') as f:
    #                 loaded_matchups = json.load(f)
    #                 # Convert string keys back to integers
    #                 self.matchups = {int(k): v for k, v in loaded_matchups.items()}
    #             print(f"Finished loading matchups from local storage for {len(self.matchups)} weeks.")
                
    #             # Verify the loaded data
    #             if not self.matchups:
    #                 raise ValueError("Loaded matchups dictionary is empty")
                
    #             # Print matchups for weeks 1 and 2
    #             # self._print_matchups_for_weeks([1, 2])
                
    #         except (json.JSONDecodeError, ValueError) as e:
    #             print(f"Error loading matchups from file: {e}. Fetching from API...")
    #             self._fetch_matchups_from_api()
    #     else:
    #         print("Local matchups file not found. Fetching from API...")
    #         self._fetch_matchups_from_api()

    # def _print_matchups_for_weeks(self, weeks):
    #     for week in weeks:
    #         if week in self.matchups:
    #             print(f"\nMatchups for Week {week}:")
    #             matchups = self.matchups[week]
    #             matchup_pairs = {}
                
    #             for team in matchups:
    #                 matchup_id = team['matchup_id']
    #                 if matchup_id not in matchup_pairs:
    #                     matchup_pairs[matchup_id] = []
    #                 matchup_pairs[matchup_id].append(team)
                
    #             for matchup_id, teams in matchup_pairs.items():
    #                 if len(teams) == 2:
    #                     team1, team2 = teams
    #                     roster1 = self.get_team_by_roster_id(team1['roster_id'])
    #                     roster2 = self.get_team_by_roster_id(team2['roster_id'])
    #                     team1_name = roster1.name if roster1 else f"Unknown Team (Roster ID: {team1['roster_id']})"
    #                     team2_name = roster2.name if roster2 else f"Unknown Team (Roster ID: {team2['roster_id']})"
                        
    #                     print(f"  Matchup {matchup_id}: {team1_name} vs {team2_name}")
    #                     print(f"    {team1_name}: Points - {team1.get('points', 'N/A')}, Starters - {len(team1.get('starters', []))}")
    #                     print(f"    {team2_name}: Points - {team2.get('points', 'N/A')}, Starters - {len(team2.get('starters', []))}")
    #                 else:
    #                     print(f"  Invalid matchup data for matchup ID {matchup_id}")
    #         else:
    #             print(f"\nNo matchup data available for Week {week}")
                
                
                
    # def check_for_injuries(self, player, team, week):
    #     if player.position in ['DEF', 'K']:
    #         return False
        
    #     self.injury_checks += 1
    #     injury_roll = random.random()
    #     injury_probability = player.injury_probability_game

    #     if injury_roll < injury_probability:
    #         self.injuries_occurred += 1
    #         injury_duration = self.generate_injury_duration(player)
    #         injury_time = random.uniform(0, 1)
    #         player.simulation_injury = {
    #             'start_week': week,
    #             'duration': injury_duration,
    #             'injury_time': injury_time
    #         }
    #         self.tracker.record_injury(player, team.name, injury_duration)
    #         return True
    #     return False
    
    # def generate_injury_duration(self, player):
    #     # Generate injury duration based on player's projected_games_missed
    #     base_duration = random.uniform(0.5, player.projected_games_missed * 2)
    #     # Ensure minimum duration of 0.5 games
    #     return max(0.5, base_duration)


    # def simulate_matchup(self, team1, team2, week, starters1, starters2):
        
    #     # Check for injuries
    #     for team in [team1, team2]:
    #         for player in team.players:
    #             self.check_for_injuries(player, team, week)

    #     # Fill starters after injury check
    #     starters1 = self.fill_starters(team1, starters1, week)
    #     starters2 = self.fill_starters(team2, starters2, week)
        
    #     score1, receptions1 = self.calculate_team_score(team1, week, starters1)
    #     score2, receptions2 = self.calculate_team_score(team2, week, starters2)
        
    #     print(f"{team1.name} vs {team2.name} in week {week}: {score1:.2f} - {score2:.2f}")
        
    #     # print the teams starters
    #     print(f"\n{team1.name} starters:")
    #     for player in team1.players:
    #         if player.sleeper_id in starters1:
    #             # only print avg pts per game if its not None
    #             if player.avg_points_per_game is not None:
    #                 print(f"{player.full_name} ({player.position})")
    #                 print(f"  Avg points per game: {player.avg_points_per_game:.2f}")
                
    #     print(f"\n{team2.name} starters:")
    #     for player in team2.players:
    #         if player.sleeper_id in starters2:
    #             if player.avg_points_per_game is not None:
    #                 print(f"{player.full_name} ({player.position}) - {player.avg_points_per_game:.2f}")
                
        
        
    #     if score1 > score2:
    #         team1.wins += 1
    #         team2.losses += 1
    #     elif score2 > score1:
    #         team2.wins += 1
    #         team1.losses += 1
    #     else:
    #         team1.ties += 1
    #         team2.ties += 1
        
    #     team1.points_for += score1
    #     team1.points_against += score2
    #     team2.points_for += score2
    #     team2.points_against += score1
        
    #     print(f"Winner: {team1.name if score1 > score2 else team2.name}")

    #     # Record weekly results
    #     self.tracker.record_team_week(team1.name, week, score1)
    #     self.tracker.record_team_week(team2.name, week, score2)

        
    # def run_simulation(self):
    #     for week in range(1, self.weeks + 1):
    #         self.simulate_week(week)
        
    #     if self.debug:
    #         injury_rate = (self.injuries_occurred / self.injury_checks) * 100 if self.injury_checks > 0 else 0
    #         print(f"Injury checks: {self.injury_checks}, Injuries occurred: {self.injuries_occurred}")
    #         print(f"Injury rate: {injury_rate:.2f}%")

    # def simulate_week(self, week):
    #     # Reset returning_from_injury flag for all players because we're simulating a new week
    #     for team in self.league.rosters:
    #         for player in team.players:
    #             player.returning_from_injury = False
        
    #     matchups_data = self.matchups.get(week)
        
    #     if not matchups_data:
    #         print(f"No matchup data for week {week}")
    #         return

    #     # Group matchups by matchup_id
    #     matchups = defaultdict(list)
        
        
    #     for team_data in matchups_data:
    #         matchups[team_data['matchup_id']].append(team_data)

    #     for matchup_id, teams in matchups.items():
    #         if len(teams) != 2:
    #             print(f"Invalid matchup data for week {week}, matchup_id {matchup_id}")
    #             continue

    #         team1_data, team2_data = teams
    #         team1 = self.get_team_by_roster_id(team1_data['roster_id'])
    #         team2 = self.get_team_by_roster_id(team2_data['roster_id'])

    #         if team1 and team2:
    #             self.simulate_matchup(team1, team2, week, team1_data['starters'], team2_data['starters'])
    #         else:
    #             print(f"Could not find teams for matchup in week {week}, matchup_id {matchup_id}")

    # def get_team_by_roster_id(self, roster_id):
    #     for team in self.league.rosters:
    #         if team.roster_id == roster_id:
    #             return team
    #     return None

    # def is_player_injured(self, player, week):
    #     if player.simulation_injury:
    #         injury_end = player.simulation_injury['start_week'] + player.simulation_injury['duration']
    #         return week < injury_end
    #     return False

    # def fill_starters(self, team, starters, week):
    #     # if team.name == "Toppi":
    #     #     print(f"\nDEBUG: Filling starters for {team.name} for week {week}")
    #     #     self.generate_injury_report(team, week)

    #     slots = {
    #         'QB': 1, 'RB': 3, 'WR': 3, 'TE': 1, 'FLEX': 3, 'K': 1, 'DEF': 1
    #     }
    #     flex_eligible = ['RB', 'WR', 'TE']

    #     current_starters = [self.get_player_by_id(pid) for pid in starters if self.get_player_by_id(pid)]
    

    #     available_players = [p for p in team.players if self.is_player_available(p, week)]
    #     new_lineup = {pos: [] for pos in slots.keys()}
        
    #     # Fill non-FLEX positions
    #     for pos in slots.keys():
    #         if pos != 'FLEX':
    #             eligible = [p for p in available_players if p.position == pos]
    #             eligible.sort(key=lambda p: p.redraft_value if hasattr(p, 'redraft_value') else 0, reverse=True)
    #             new_lineup[pos] = eligible[:slots[pos]]
    #             for player in new_lineup[pos]:
    #                 available_players.remove(player)

    #     # Fill FLEX positions
    #     flex_eligible_players = [p for p in available_players if p.position in flex_eligible]
    #     flex_eligible_players.sort(key=lambda p: p.redraft_value if hasattr(p, 'redraft_value') else 0, reverse=True)
    #     new_lineup['FLEX'] = flex_eligible_players[:slots['FLEX']]

    #     # Ensure all positions are filled
    #     for pos in slots.keys():
    #         while len(new_lineup[pos]) < slots[pos]:
    #             replacement = self.find_replacement(pos, available_players, flex_eligible)
    #             if replacement:
    #                 new_lineup[pos].append(replacement)
    #                 available_players.remove(replacement)
    #             else:
    #                 break

    #     # Flatten the lineup
    #     flat_lineup = [player for pos_list in new_lineup.values() for player in pos_list]

    #     # Determine actual changes
    #     changes = []
    #     for old, new in zip(current_starters, flat_lineup):
    #         if old != new:
    #             changes.append((old, new))

    #     # if team.name == "Toppi":
    #     #     self.print_lineup(team, new_lineup, week)
    #     #     # self.print_lineup_changes(changes, team, week)
            
    #     #     # Print final lineup after changes
    #     #     # print(f"\nFinal lineup for {team.name} in week {week} (after injury checks and changes):")
    #     #     for pos, players in new_lineup.items():
    #     #         for player in players:
    #     #             print(f"{pos}: {player.full_name} ({player.position})")

    #     return [p.sleeper_id for p in flat_lineup]

    # def print_current_lineup(self, team, current_starters, week):
    #     # print(f"\nCurrent lineup for {team.name} in week {week} (before injury checks):")
    #     positions = ['QB', 'RB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'FLEX', 'FLEX', 'K', 'DEF']
    #     for pos, player in zip(positions, current_starters):
    #         print(f"{pos}: {player.full_name} ({player.position})")


    # def print_lineup_changes(self, changes, team, week):
    #     if changes:
    #         # print(f"\nLineup changes for {team.name} in week {week}:")
    #         for old, new in changes:
    #             if old and self.is_player_injured(old, week):
    #                 if old.simulation_injury['start_week'] < week:
    #                     print(f"  Replaced: {old.full_name} ({old.position}, injured in Week {old.simulation_injury['start_week']}) with {new.full_name} ({new.position})")
    #                 else:
    #                     print(f"  {old.full_name} ({old.position}) injured this week, but remains in lineup with reduced points")
    #             elif old and new:
    #                 if old.position != new.position:
    #                     print(f"  Replaced: {old.full_name} ({old.position}) with {new.full_name} ({new.position})")
    #                 else:
    #                     print(f"  Replaced: {old.full_name} with {new.full_name}")
    #             elif new:
    #                 print(f"  Added to lineup: {new.full_name} ({new.position})")
    #     else:
    #         print(f"\nNo lineup changes for {team.name} in week {week}")
    # def print_lineup(self, team, lineup, week):
    #     print(f"\nLineup for {team.name} in week {week}:")
    #     for pos, players in lineup.items():
    #         print(f"{pos}: {', '.join([f'{p.full_name} ({p.position})' for p in players])}")
            
    # def print_injured_players(self, team, week):
    #     injured_players = [p for p in team.players if self.is_player_injured(p, week)]
    #     if injured_players:
    #         print(f"\nInjured players for {team.name} in week {week}:")
    #         for player in injured_players:
    #             injury_end = player.simulation_injury['start_week'] + player.simulation_injury['duration']
    #             games_remaining = max(0, injury_end - week)
    #             print(f"  {player.full_name} ({player.position}): {games_remaining:.2f} games remaining")
    #     else:
    #         print(f"\nNo injured players for {team.name} in week {week}")


    
    # def find_replacement(self, pos, available_players, flex_eligible):
    #     if pos == 'FLEX':
    #         return next((p for p in available_players if p.position in flex_eligible), None)
    #     else:
    #         return next((p for p in available_players if p.position == pos), None)

    # def refill_position(self, position_lists, non_starters, position, flex_eligible):
    #     if position == 'FLEX':
    #         for pos in flex_eligible:
    #             if non_starters and non_starters[0].position == pos:
    #                 position_lists['FLEX'].append(non_starters.pop(0))
    #                 return
    #     elif position in flex_eligible and position_lists['FLEX']:
    #         # Move player from FLEX to required position
    #         for i, player in enumerate(position_lists['FLEX']):
    #             if player.position == position:
    #                 position_lists[position].append(position_lists['FLEX'].pop(i))
    #                 self.refill_position(position_lists, non_starters, 'FLEX', flex_eligible)
    #                 return
        
    #     # If we can't fill from FLEX, try to fill from non_starters
    #     for i, player in enumerate(non_starters):
    #         if player.position == position or (position == 'FLEX' and player.position in flex_eligible):
    #             position_lists[position].append(non_starters.pop(i))
    #             return

    #     print(f"WARNING: Unable to fill {position} position")
    #     x = input("Press Enter to continue...") # Debugging

    # def is_valid_lineup(self, lineup, required_positions, flex_eligible):
    #     position_counts = {pos: 0 for pos in required_positions}
        
    #     for player in lineup:
    #         if player.position in required_positions:
    #             position_counts[player.position] += 1
        
    #     # Check if all required non-FLEX positions are filled
    #     for pos, count in required_positions.items():
    #         if pos != 'FLEX' and position_counts[pos] < count:
    #             return False
        
    #     # Count remaining flex-eligible players
    #     remaining_flex = sum(position_counts[pos] for pos in flex_eligible) - sum(required_positions[pos] for pos in flex_eligible if pos != 'FLEX')
        
    #     # Check if we have enough players for FLEX
    #     if remaining_flex >= required_positions['FLEX']:
    #         print("Debug: Valid lineup found!")
    #         return True
    #     return False

    # def calculate_team_score(self, team, week, starters):
    #     score = 0
    #     total_receptions = 0
    #     points_lost_to_injury = 0
    #     for player in team.players:
    #         if player.sleeper_id in starters:
    #             if self.is_player_injured(player, week):
    #                 points_lost = self.calculate_points_lost_due_to_injury(player)
    #                 points_lost_to_injury += points_lost
    #             else:
    #                 player_score, player_receptions = self.calculate_player_score(player, week)
    #                 score += player_score
    #                 total_receptions += player_receptions

    #     # Record points lost to injury
    #     self.tracker.record_points_lost_to_injury(team.name, week, points_lost_to_injury)

    #     return score, total_receptions
    
    # def get_player_by_id(self, player_id, player_name=None):
    #     player_id = str(player_id).strip()
    #     for team in self.league.rosters:
    #         for player in team.players:
    #             if str(player.sleeper_id).strip() == player_id:
    #                 if player.position == 'UNKNOWN':
    #                     player.position = self.get_player_position(player_id)
    #                 return player
        
    #     # Fallback to name-based lookup if player_name is provided
    #     if player_name:
    #         for team in self.league.rosters:
    #             for player in team.players:
    #                 if player_name.lower() == (player.first_name + " " + player.last_name).lower():
    #                     if player.position == 'UNKNOWN':
    #                         player.position = self.get_player_position(player.sleeper_id)
    #                     return player
    #         print(f"Player not found by name: {player_name}")

    #     return None
    
    # def calculate_player_score(self, player, week):
    #     if player.position == 'DEF':
    #         score = self.add_defense_score()
    #         print(f"DEBUG: {player.full_name} (DEF) scored {score:.2f} points in week {week}")
    #         return score, 0
    #     elif player.position == 'K':
    #         score = self.add_kicker_score()
    #         print(f"DEBUG: {player.full_name} (K) scored {score:.2f} points in week {week}")
    #         return score, 0

    #     proj = player.pff_projections
    #     scoring = self.league.scoring_settings

    #     if not proj:
    #         print(f"DEBUG: No projections for {player.full_name}")
    #         return 0, 0

    #     games = float(proj.get('games', 0))
    #     bye_week = int(proj.get('byeWeek', 0))

    #     if games == 0 or week == bye_week:
    #         print(f"DEBUG: {player.full_name} not playing in week {week} (Games: {games}, Bye: {bye_week})")
    #         return 0, 0

    #     if self.is_player_injured(player, week):
    #         if player.simulation_injury['start_week'] < week:
    #             print(f"DEBUG: {player.full_name} injured before week {week}")
    #             return 0, 0
            
            


    #     # Calculate per-game averages
    #     avg_pass_yds = float(proj.get('passYds', 0)) / games
    #     avg_pass_td = float(proj.get('passTd', 0)) / games
    #     avg_pass_int = float(proj.get('passInt', 0)) / games
    #     avg_rush_yds = float(proj.get('rushYds', 0)) / games
    #     avg_rush_td = float(proj.get('rushTd', 0)) / games
    #     avg_rec_yds = float(proj.get('recvYds', 0)) / games
    #     avg_rec_td = float(proj.get('recvTd', 0)) / games
    #     avg_receptions = float(proj.get('recvReceptions', 0)) / games
    #     rush_att = float(proj.get('rushAtt', 0)) / games

    #     # Add randomness to projections
    #     pass_yds = max(0, random.gauss(avg_pass_yds, avg_pass_yds * 0.25))
    #     pass_td = max(0, random.gauss(avg_pass_td, avg_pass_td * 0.75))
    #     pass_int = max(0, random.gauss(avg_pass_int, avg_pass_int * 0.75))
        
    
        
    #     # calculate receptions
    #     receptions = max(0, random.gauss(avg_receptions, avg_receptions * 0.75))
    #     rush_att = max (0, random.gauss(rush_att, rush_att * 0.75))

    #     # Calculate receiving yards based on receptions
    #     avg_yards_per_reception = avg_rec_yds / avg_receptions if avg_receptions > 0 else 0 # Avoid division by zero 
    #     avg_yards_per_rush = avg_rush_yds / rush_att if rush_att > 0 else 0

    #     base_rec_yds = receptions * avg_yards_per_reception # Base receiving yards based on receptions
    #     rec_yds = max(0, random.gauss(base_rec_yds, base_rec_yds * 0.1))
    #     rec_td = max(0, random.gauss(avg_rec_td, avg_rec_td * 0.3))
        
    #     base_rush_yds = rush_att * avg_yards_per_rush
    #     rush_yds = max(0, random.gauss(base_rush_yds, base_rush_yds * 0.1))
    #     rush_td = max(0, random.gauss(avg_rush_td, avg_rush_td * 0.3))
        
    #     if receptions <= 0:
    #         receptions = 0
    #         rec_yds = 0
    #         rec_td = 0
            
    #     if rush_att <= 0:
    #         rush_att = 0
    #         rush_yds = 0
    #         rush_td = 0

    #     # Round stats to realistic values
    #     pass_yds = round(pass_yds)
    #     pass_td = round(pass_td)
    #     pass_int = round(pass_int)
    #     rush_yds = round(rush_yds)
    #     rush_td = round(rush_td)
    #     rec_yds = round(rec_yds)
    #     rec_td = round(rec_td)
    #     receptions = round(receptions)
        

    #     score = (
    #         pass_yds * scoring.pass_yd +
    #         pass_td * scoring.pass_td +
    #         pass_int * scoring.pass_int +
    #         rush_yds * scoring.rush_yd +
    #         rush_td * scoring.rush_td +
    #         rec_yds * scoring.rec_yd +
    #         rec_td * scoring.rec_td +
    #         receptions * (scoring.te_rec if player.position == 'TE' else scoring.rec)
    #     )
        
    #     # if player.simulation_injury:
    #     #     injury_start = player.simulation_injury['start_week']
    #     #     injury_end = injury_start + player.simulation_injury['duration']
    #     #     if week >= injury_end:
    #     #         player.simulation_injury = None  # Player has recovered
    #     #     elif injury_start == week:
    #     #         # Player got injured this week
    #     #         injury_factor = 1 - player.simulation_injury['injury_time']
    #     #         score *= injury_factor
    #     #         receptions *= injury_factor
    #     #     else:
    #     #         # Player was already injured before this week
    #     #         return 0, 0
            
    #     self.tracker.record_player_score(player.sleeper_id, week, score)
    #     # print(f"DEBUG: {player.full_name} scored {score:.2f} points in week {week}")
    #     # player.avg_points_per_game = score / player.total_simulated_games
    #     player.total_simulated_games += 1
    #     player.total_simulated_points += score
    #     player.avg_points_per_game = player.total_simulated_points / player.total_simulated_games
    #     print(f"DEBUG: {player.full_name} scored {score:.2f} points in week {week}")

    #     return score, receptions

    # def add_defense_score(self):
    #     # randomly generate defense scores bell curve around 15 with min max at -5 and 35
    #     return max(-5, min(35, round(random.gauss(15, 10))))
        
        
    # def add_kicker_score(self):
    #     # randomly generate kicker scores bell curve around 10 with min max at  0 and 20
    #     return max(0, min(20, round(random.gauss(10, 5))))
    
    
    # def calculate_points_lost_due_to_injury(self, player):
    #     # Calculate points lost due to injury for the given player
    #     # This could be based on the player's average points per game or other metrics
    #     if player.avg_points_per_game:
    #         return max(0, random.gauss(player.avg_points_per_game, player.avg_points_per_game * 0.25))
    #     else:
    #         return max(0, random.gauss(player.pff_projections['fantasyPoints'], player.pff_projections['fantasyPoints'] * 0.25))
    
    
    # def generate_injury_report(self, team, week):
    #     print(f"\nWeek {week} Injury Report for {team.name}:")
    #     current_week_injuries = []
    #     new_injuries = []
    #     ongoing_injuries = []
    #     returning_players = []

    #     for player in team.players:
    #         if player.simulation_injury:
    #             injury_start = player.simulation_injury['start_week']
    #             injury_duration = player.simulation_injury['duration']
    #             injury_end = injury_start + injury_duration

    #             if injury_start == week:
    #                 current_week_injuries.append(f"  - {player.full_name} ({player.position}): Injured this week, expected to return Week {math.ceil(injury_end)}")
    #             elif injury_start == week - 1:
    #                 new_injuries.append(f"  - {player.full_name} ({player.position}): Injured last week, out until Week {math.ceil(injury_end)}")
    #             elif week < injury_end:
    #                 ongoing_injuries.append(f"  - {player.full_name} ({player.position}): Expected to return Week {math.ceil(injury_end)}")
    #             elif week == math.ceil(injury_end):
    #                 returning_players.append(f"  - {player.full_name} ({player.position})")
    #             else:
    #                 player.simulation_injury = None  # Clear the injury

    #     if current_week_injuries:
    #         print("  Injuries occurring this week (player still active):")
    #         for injury in current_week_injuries:
    #             print(injury)
    #     if new_injuries:
    #         print("  New Injuries (player inactive from this week):")
    #         for injury in new_injuries:
    #             print(injury)
    #     if ongoing_injuries:
    #         print("  Ongoing Injuries:")
    #         for injury in ongoing_injuries:
    #             print(injury)
    #     if returning_players:
    #         print("  Returning from Injury:")
    #         for player in returning_players:
    #             print(player)
    #     if not (current_week_injuries or new_injuries or ongoing_injuries or returning_players):
    #         print("  No injuries to report.")
            
    # def is_player_available(self, player, week):
    #     if not player.simulation_injury:
    #         return True
    #     injury_start = player.simulation_injury['start_week']
    #     injury_end = injury_start + player.simulation_injury['duration']
    #     return week >= injury_end or injury_start == week