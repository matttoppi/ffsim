
import os
import json
import requests
from datetime import datetime, timedelta
from sim.SimulationClasses.SimulationMatchup import SimulationMatchup
from sim.SimulationClasses.Playoffs import PlayoffSimulation
        
        
        
        
class SimulationSeason:
    def __init__(self, league, tracker):
        self.league = league
        self.tracker = tracker
        self.weeks = 14  # Regular season weeks
        self.playoff_weeks = 3  # Playoff weeks
        self.matchups = {}
        self.matchups_file = f'datarepo/matchups_{league.league_id}.json'
        self.matchups_refresh_interval = timedelta(days=1)
        self.playoff_sim = None

    
                
    

    def get_matchups(self, week):
        all_matchups = self.load_or_fetch_matchups()
        
        if str(week) not in all_matchups:
            print(f"No matchup data available for week {week}")
            return []

        week_matchups = all_matchups[str(week)]
        matchup_pairs = {}

        for team in week_matchups:
            matchup_id = team['matchup_id']
            if matchup_id not in matchup_pairs:
                matchup_pairs[matchup_id] = []
            matchup_pairs[matchup_id].append(team)

        matchups = []
        for pair in matchup_pairs.values():
            if len(pair) == 2:
                home_team = self.get_team_by_roster_id(pair[0]['roster_id'])
                away_team = self.get_team_by_roster_id(pair[1]['roster_id'])
                if home_team and away_team:
                    matchups.append(SimulationMatchup(home_team, away_team, week))

        return matchups


    def load_or_fetch_matchups(self):
        if os.path.exists(self.matchups_file):
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.matchups_file))
            if file_age <= self.matchups_refresh_interval:
                with open(self.matchups_file, 'r') as f:
                    return json.load(f)

        print("Fetching matchups from Sleeper API...")
        all_matchups = self.fetch_all_matchups()
        
        os.makedirs(os.path.dirname(self.matchups_file), exist_ok=True)
        with open(self.matchups_file, 'w') as f:
            json.dump(all_matchups, f)
        
        return all_matchups

    def fetch_all_matchups(self):
        all_matchups = {}
        for week in range(1, self.weeks + 1):
            url = f"https://api.sleeper.app/v1/league/{self.league.league_id}/matchups/{week}"
            response = requests.get(url)
            if response.status_code == 200:
                all_matchups[str(week)] = response.json()
            else:
                print(f"Failed to fetch matchups for week {week}: HTTP {response.status_code}")
        return all_matchups
    def get_team_by_roster_id(self, roster_id):
        for team in self.league.rosters:
            if team.roster_id == roster_id:
                return team
        return None

    def update_records(self, home_team, away_team, home_score, away_score, week):
        home_team.update_record(home_score > away_score, home_score == away_score, away_score, week)
        away_team.update_record(away_score > home_score, home_score == away_score, home_score, week)


    def get_standings(self):
        return sorted(self.league.rosters, key=lambda t: (t.wins, t.points_for), reverse=True)

        
    def record_playoff_results(self, champion):
        # Implement logic to record playoff results in the tracker
        self.tracker.record_champion(champion.name)
    
                    
    def simulate_week(self, week):
        for team in self.league.rosters:
            for player in team.players:
                player.update_injury_status(week)
            team.fill_starters(week)

        matchups = self.get_matchups(week)
        for matchup in matchups:
            matchup.simulate(self.league.scoring_settings, self.tracker)

        print(f"DEBUG: Week {week} completed")

    def simulate_team_week(self, team, week):
        total_score = 0
        for player in team.get_active_starters(week):
            score = player.calculate_score(self.league.scoring_settings, week)
            total_score += score
        return total_score
    
    
    
    def simulate(self):
        # Reset all team stats at the start of the simulation
        for team in self.league.rosters:
            team.reset_stats()

        # create season long modifiers for each player on each team
        for team in self.league.rosters:
            team.create_season_modifiers()

        for week in range(1, self.weeks + 1):
            self.simulate_week(week)

        # Simulate playoffs
        standings = self.get_standings()
        self.playoff_sim = PlayoffSimulation(self.league, standings, self)
        self.playoff_sim.setup_playoffs()
        champion = self.playoff_sim.simulate_playoffs()

        self.record_season_results()

        # Update injury status for all players after the entire season (including playoffs)
        for team in self.league.rosters:
            for player in team.players:
                games_missed = player.get_games_missed_for_tracking()
                if games_missed > 0:
                    self.tracker.record_player_games_missed(player.sleeper_id, games_missed)
                self.tracker.record_total_games_missed(player.sleeper_id, player.total_games_missed_this_season)
                player.reset_injury_status()

    def record_season_results(self):
        for team in self.league.rosters:
            self.tracker.record_team_season(
                team.name,
                team.wins,
                team.losses,
                team.ties,
                team.points_for,
                team.points_against,
                team.playoff_result
            )
            for player in team.players:
                self.tracker.record_player_season(team.name, player.sleeper_id, player.weekly_scores, player.season_modifier)