from collections import defaultdict
import random
import math
import requests
class LeagueSimulation:
    def __init__(self, league):
        self.league = league
        self.weeks = 17
        self.starter_scores = defaultdict(list)
        self.starter_receptions = defaultdict(list)
        self.weekly_player_scores = defaultdict(lambda: defaultdict(list))
        self.matchups = {}  
        
    def fetch_all_matchups(self):
        print("Fetching matchups for all weeks...")
        for week in range(1, self.weeks + 1):
            url = f"https://api.sleeper.app/v1/league/{self.league.league_id}/matchups/{week}"
            response = requests.get(url)
            if response.status_code == 200:
                self.matchups[week] = response.json()
            else:
                print(f"Failed to fetch matchups for week {week}")
        print("Finished fetching matchups.")
        
    def run_simulation(self):
        for week in range(1, self.weeks + 1):
            self.simulate_week(week)

    def simulate_week(self, week):
        matchups_data = self.matchups.get(week)
        if not matchups_data:
            print(f"No matchup data for week {week}")
            return

        # Group matchups by matchup_id
        matchups = defaultdict(list)
        for team_data in matchups_data:
            matchups[team_data['matchup_id']].append(team_data)

        for matchup_id, teams in matchups.items():
            if len(teams) != 2:
                print(f"Invalid matchup data for week {week}, matchup_id {matchup_id}")
                continue

            team1_data, team2_data = teams
            team1 = self.get_team_by_roster_id(team1_data['roster_id'])
            team2 = self.get_team_by_roster_id(team2_data['roster_id'])

            if team1 and team2:
                self.simulate_matchup(team1, team2, week, team1_data['starters'], team2_data['starters'])
            else:
                print(f"Could not find teams for matchup in week {week}, matchup_id {matchup_id}")

    def get_team_by_roster_id(self, roster_id):
        for team in self.league.rosters:
            if team.roster_id == roster_id:
                return team
        return None

    def simulate_matchup(self, team1, team2, week, starters1, starters2):
        starters1 = self.fill_starters(team1, starters1)
        starters2 = self.fill_starters(team2, starters2)
        
        score1, receptions1 = self.calculate_team_score(team1, week, starters1)
        score2, receptions2 = self.calculate_team_score(team2, week, starters2)
        
        if score1 > score2:
            team1.wins += 1
            team2.losses += 1
        elif score2 > score1:
            team2.wins += 1
            team1.losses += 1
        else:
            team1.ties += 1
            team2.ties += 1
        
        team1.points_for += score1
        team1.points_against += score2
        team2.points_for += score2
        team2.points_against += score1

    def fill_starters(self, team, starters):
        required_positions = {
            'QB': 1,
            'WR': 3,
            'RB': 3,
            'FLEX': 3,
            'K': 1,
            'DEF': 1
        }
        
        filled_starters = []
        position_counts = defaultdict(int)
        flex_eligible = ['WR', 'RB', 'TE']

        # First, fill in the existing starters
        for player_id in starters:
            player = self.get_player_by_id(player_id)
            if player:
                if player.position in required_positions or player.position in flex_eligible:
                    filled_starters.append(player_id)
                    if player.position in required_positions:
                        position_counts[player.position] += 1
                    elif player.position in flex_eligible:
                        if position_counts['FLEX'] < required_positions['FLEX']:
                            position_counts['FLEX'] += 1
                        else:
                            position_counts[player.position] += 1

        # Then fill the remaining slots
        all_players = sorted(team.players, key=lambda p: p.value_1qb, reverse=True)
        for player in all_players:
            if len(filled_starters) >= sum(required_positions.values()):
                break
            
            if player.sleeper_id not in filled_starters:
                if player.position in required_positions and position_counts[player.position] < required_positions[player.position]:
                    filled_starters.append(player.sleeper_id)
                    position_counts[player.position] += 1
                elif player.position in flex_eligible and position_counts['FLEX'] < required_positions['FLEX']:
                    filled_starters.append(player.sleeper_id)
                    position_counts['FLEX'] += 1

        # If we still don't have enough starters, fill FLEX positions with best available players
        if len(filled_starters) < sum(required_positions.values()):
            for player in all_players:
                if player.sleeper_id not in filled_starters and player.position in flex_eligible:
                    filled_starters.append(player.sleeper_id)
                    if len(filled_starters) >= sum(required_positions.values()):
                        break

        return filled_starters[:sum(required_positions.values())]

    def calculate_team_score(self, team, week, starters):
        score = 0
        total_receptions = 0
        for player in team.players:
            if player and player.pff_projections:
                player_score, player_receptions = self.calculate_player_score(player, week)
                if player.sleeper_id in starters:
                    score += player_score
                    total_receptions += player_receptions
                if player.position not in ['DEF', 'K']:
                    self.weekly_player_scores[player.sleeper_id][week].append(player_score)
                    # print(f"Week {week}, Player {player.full_name}: Score {player_score}")  # Debug statement
        
        # Add defense and kicker scores
        score += self.add_defense_score()
        score += self.add_kicker_score()
        
        return score, total_receptions
        
    def get_player_by_id(self, player_id, player_name=None):
        player_id = str(player_id).strip()  # Ensure player_id is a string and trimmed
        for team in self.league.rosters:
            for player in team.players:
                if str(player.sleeper_id).strip() == player_id:
                    return player
        # print(f"Player not found by ID: {player_id}")  # Debug statement
        
        # Fallback to name-based lookup if player_name is provided
        if player_name:
            for team in self.league.rosters:
                for player in team.players:
                    if player_name.lower() == (player.first_name + " " + player.last_name).lower():
                        # print(f"Player found by name: {player.first_name} {player.last_name}")
                        return player
            print(f"Player not found by name: {player_name}")

        return None

    def calculate_player_score(self, player, week):
        proj = player.pff_projections
        scoring = self.league.scoring_settings

        if not proj:
            print(f"No projections for {player.full_name}")
            return 0, 0  # Return 0 score and 0 receptions if no projections

        games = float(proj['games'])
        bye_week = int(proj.get('byeWeek', 0))

        if games == 0 or week == bye_week:
            return 0, 0  # Player is not expected to play or it's their bye week

        # Calculate per-game averages
        avg_pass_yds = float(proj['passYds']) / games
        avg_pass_td = float(proj['passTd']) / games
        avg_pass_int = float(proj['passInt']) / games
        avg_rush_yds = float(proj['rushYds']) / games
        avg_rush_td = float(proj['rushTd']) / games
        avg_rec_yds = float(proj['recvYds']) / games
        avg_rec_td = float(proj['recvTd']) / games
        avg_receptions = float(proj.get('recvReceptions', 0)) / games

        # Add randomness to projections
        pass_yds = max(0, random.gauss(avg_pass_yds, avg_pass_yds * 0.25))
        pass_td = max(0, random.gauss(avg_pass_td, avg_pass_td * 0.75))
        pass_int = max(0, random.gauss(avg_pass_int, avg_pass_int * 0.75))
        rush_yds = max(0, random.gauss(avg_rush_yds, avg_rush_yds * 0.25))
        rush_td = max(0, random.gauss(avg_rush_td, avg_rush_td * 0.75))
        
        # calculate receptions
        receptions = max(0, random.gauss(avg_receptions, avg_receptions * 0.8))

        # Calculate receiving yards based on receptions
        avg_yards_per_reception = avg_rec_yds / avg_receptions if avg_receptions > 0 else 0 # Avoid division by zero 

        base_rec_yds = receptions * avg_yards_per_reception # Base receiving yards based on receptions
        rec_yds = max(0, random.gauss(base_rec_yds, base_rec_yds * 0.1))
        rec_td = max(0, random.gauss(avg_rec_td, avg_rec_td * 0.75))
        
        if receptions <= 0:
            receptions = 0
            rec_yds = 0
            rec_td = 0

        # Round stats to realistic values
        pass_yds = round(pass_yds)
        pass_td = round(pass_td)
        pass_int = round(pass_int)
        rush_yds = round(rush_yds)
        rush_td = round(rush_td)
        rec_yds = round(rec_yds)
        rec_td = round(rec_td)
        receptions = round(receptions)

        score = (
            pass_yds * scoring.pass_yd +
            pass_td * scoring.pass_td +
            pass_int * scoring.pass_int +
            rush_yds * scoring.rush_yd +
            rush_td * scoring.rush_td +
            rec_yds * scoring.rec_yd +
            rec_td * scoring.rec_td +
            receptions * (scoring.te_rec if player.position == 'TE' else scoring.rec)
        )

        return score, receptions

    def add_defense_score(self):
        # randomly generate defense scores bell curve around 15 with min max at -5 and 35
        return max(-5, min(35, round(random.gauss(15, 10))))
        
        
    def add_kicker_score(self):
        # randomly generate kicker scores bell curve around 10 with min max at  0 and 20
        return max(0, min(20, round(random.gauss(10, 5))))
    
    
