
import os
import json
import requests
from datetime import datetime, timedelta
from sim.SimulationClasses.SimulationMatchup import SimulationMatchup
        
        
class SimulationSeason:
    def __init__(self, league, tracker):
        self.league = league
        self.tracker = tracker
        self.weeks = 18  # Or however many weeks your season has        self.weeks = 18
        self.matchups = {}
        self.matchups_file = f'datarepo/matchups_{league.league_id}.json'
        self.matchups_refresh_interval = timedelta(days=1)

    def simulate_week(self, week):
        for team in self.league.rosters:
            for player in team.players:
                player.update_injury_status(week)
            team.fill_starters(week)
            team.roll_new_injuries(week)
        
        matchups = self.get_matchups(week)
        for matchup in matchups:
            matchup.week = week
            matchup.simulate(self.league.scoring_settings, self.tracker)

    def simulate(self):
        for week in range(1, self.weeks + 1):
            self.simulate_week(week)
        
        # Record games missed at the end of the season
        for team in self.league.rosters:
            for player in team.players:
                if player.games_missed_this_season > 0:
                    self.tracker.record_player_games_missed(player.sleeper_id, player.games_missed_this_season)
                    print(f"Recorded {player.games_missed_this_season} missed games for {player.name} in this season")
                player.reset_injury_status()

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

        
        
    def get_team_by_roster_id(self, roster_id):
        for team in self.league.rosters:
            if team.roster_id == roster_id:
                return team
        return None

    def get_standings(self):
        return sorted(
            [(team.name, team.wins, team.points_for) for team in self.league.rosters],
            key=lambda x: (x[1], x[2]),
            reverse=True
        )