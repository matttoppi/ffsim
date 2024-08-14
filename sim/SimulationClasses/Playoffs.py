import random

class PlayoffMatch:
    def __init__(self, home_team, away_team, week, simulation_season):
        self.home_team = home_team
        self.away_team = away_team
        self.week = week
        self.simulation_season = simulation_season
        self.winner = None

    def simulate(self, scoring_settings):
        # Update injury status for both teams
        for team in [self.home_team, self.away_team]:
            for player in team.players:
                player.update_injury_status(self.week)
            team.fill_starters(self.week)

        home_score = self.simulation_season.simulate_team_week(self.home_team, self.week)
        away_score = self.simulation_season.simulate_team_week(self.away_team, self.week)
        
        self.winner = self.home_team if home_score > away_score else self.away_team
        
        # Record scores in the tracker
        self.simulation_season.tracker.record_team_week(self.home_team.name, self.week, home_score)
        self.simulation_season.tracker.record_team_week(self.away_team.name, self.week, away_score)
        
        return self.winner
    
class PlayoffBracket:
    def __init__(self, teams, division1_winner, division2_winner, simulation_season):
        self.teams = teams
        self.division1_winner = division1_winner
        self.division2_winner = division2_winner
        self.matches = []
        self.simulation_season = simulation_season

    def create_bracket(self):
        # Determine bye week teams
        bye_teams = [self.division1_winner, self.division2_winner]
        non_bye_teams = [team for team in self.teams if team not in bye_teams]

        # Create first round matches
        if len(non_bye_teams) >= 4:
            self.matches.append(PlayoffMatch(non_bye_teams[0], non_bye_teams[-1], 15, self.simulation_season))
            self.matches.append(PlayoffMatch(non_bye_teams[1], non_bye_teams[-2], 15, self.simulation_season))
        elif len(non_bye_teams) == 3:
            # Only one first round match
            self.matches.append(PlayoffMatch(non_bye_teams[1], non_bye_teams[2], 15, self.simulation_season))
        elif len(non_bye_teams) <= 2:
            # Not enough teams for first round, move directly to semifinals
            self.create_semifinal(non_bye_teams, 16)

    def simulate_round(self, week, scoring_settings):
        results = []
        for match in self.matches:
            winner = match.simulate(scoring_settings)
            results.append(winner)
        self.matches = []  # Clear current round matches
        return results

    def create_semifinal(self, first_round_winners, week):
        if len(first_round_winners) == 2:
            # Normal scenario with two first round winners
            self.matches.append(PlayoffMatch(self.division1_winner, first_round_winners[1], week, self.simulation_season))
            self.matches.append(PlayoffMatch(self.division2_winner, first_round_winners[0], week, self.simulation_season))
        elif len(first_round_winners) == 1:
            # Only one first round winner
            self.matches.append(PlayoffMatch(self.division1_winner, first_round_winners[0], week, self.simulation_season))
            self.matches.append(PlayoffMatch(self.division2_winner, self.teams[2], week, self.simulation_season))  # 3rd best team overall
        else:
            # No first round winners, use 3rd and 4th best teams overall
            self.matches.append(PlayoffMatch(self.division1_winner, self.teams[3], week, self.simulation_season))
            self.matches.append(PlayoffMatch(self.division2_winner, self.teams[2], week, self.simulation_season))

    def create_final(self, semifinal_winners, week):
        if len(semifinal_winners) == 2:
            self.matches.append(PlayoffMatch(semifinal_winners[0], semifinal_winners[1], week, self.simulation_season))
        else:
            print("Error: Not enough semifinal winners for the final match.")
            
            
            
class PlayoffSimulation:
    def __init__(self, league, season_standings, simulation_season):
        self.league = league
        self.season_standings = season_standings
        self.simulation_season = simulation_season
        self.bracket = None
        self.champion = None
        self.runner_up = None
        self.semifinalists = []

    def simulate_playoffs(self):
        # First round (if necessary)
        if len(self.bracket.matches) > 0:
            first_round_winners = self.bracket.simulate_round(15, self.league.scoring_settings)
            self.bracket.create_semifinal(first_round_winners, 16)
        else:
            self.bracket.create_semifinal([], 16)  # No first round, create semifinals directly
        
        # Semifinals
        semifinal_winners = self.bracket.simulate_round(16, self.league.scoring_settings)
        self.semifinalists = [match.home_team for match in self.bracket.matches] + [match.away_team for match in self.bracket.matches]
        
        # Final
        self.bracket.create_final(semifinal_winners, 17)
        final_matches = self.bracket.matches  # Assuming this is a list with one final match
        if final_matches:
            final_match = final_matches[0]
            self.champion = self.bracket.simulate_round(17, self.league.scoring_settings)[0]
            self.runner_up = final_match.home_team if self.champion == final_match.away_team else final_match.away_team
        else:
            print("Error: No final match created")
            self.champion = None
            self.runner_up = None
        
        # Update injury status for all players after playoffs
        for team in self.league.rosters:
            for player in team.players:
                games_missed = player.get_games_missed_for_tracking()
                if games_missed > 0:
                    self.simulation_season.tracker.record_player_games_missed(player.sleeper_id, games_missed)
                self.simulation_season.tracker.record_total_games_missed(player.sleeper_id, player.total_games_missed_this_season)
        
        
        
        # Set playoff results for all teams
        for team in self.league.rosters:
            # if team == self.champion:
            #     team.set_playoff_result("Champion")
            # elif team == self.runner_up:
            #     team.set_playoff_result("Runner-up")
            # elif team in self.semifinalists:
            #     team.set_playoff_result("Lost in Semis")
            # elif team in self.bracket.teams:
            #     team.set_playoff_result("Lost in First Round")
            # else:
            #     team.set_playoff_result("Missed Playoffs")
            
            if team == self.champion:
                team.playoff_result = "Champion"
            elif team == self.runner_up:
                team.playoff_result = "Runner-up"
            elif team in self.semifinalists:
                team.playoff_result = "Lost in Semis"
            elif team in self.bracket.teams:
                team.playoff_result = "Lost in First Round"
            else:
                team.playoff_result = "Missed Playoffs"
        
        return self.champion
        
        return self.champion
    def setup_playoffs(self):
        # Determine division winners
        division1_teams = [team for team in self.season_standings if team.roster_id in self.league.division1_ids]
        division2_teams = [team for team in self.season_standings if team.roster_id in self.league.division2_ids]
        
        division1_winner = max(division1_teams, key=lambda t: (t.wins, t.points_for))
        division2_winner = max(division2_teams, key=lambda t: (t.wins, t.points_for))
        
        # Order division winners based on record
        if (division1_winner.wins, division1_winner.points_for) < (division2_winner.wins, division2_winner.points_for):
            division1_winner, division2_winner = division2_winner, division1_winner

        # Remove division winners from the standings
        remaining_teams = [team for team in self.season_standings if team not in [division1_winner, division2_winner]]
        
        # Select the next best teams to fill the bracket (minimum 2, maximum 4)
        wild_card_teams = sorted(remaining_teams, key=lambda t: (t.wins, t.points_for), reverse=True)[:min(4, len(remaining_teams))]
        
        # Combine division winners and wild card teams to get the playoff teams (minimum 4)
        playoff_teams = [division1_winner, division2_winner] + wild_card_teams
        
        # Sort playoff teams by record (wins, then points for)
        playoff_teams = sorted(playoff_teams, key=lambda t: (t.wins, t.points_for), reverse=True)
        
        self.bracket = PlayoffBracket(playoff_teams, division1_winner, division2_winner, self.simulation_season)
        self.bracket.create_bracket()

    
    