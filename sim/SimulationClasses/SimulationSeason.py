import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

from sim.SimulationClasses.Playoffs import PlayoffSimulation
from sim.SimulationClasses.SimulationMatchup import SimulationMatchup


class SimulationSeason:
    def __init__(self, league, tracker):
        self.league = league
        self.tracker = tracker
        self.weeks = 14
        self.matchups_file = Path(f"datarepo/matchups_{league.league_id}.json")
        self.matchups = self.load_or_fetch_matchups()
        self.playoff_sim = None

    def simulate(self):
        for team in self.league.rosters:
            team.create_season_modifiers()

        for week in range(1, self.weeks + 1):
            self.simulate_week(week)

        self.playoff_sim = PlayoffSimulation(self.league, self.get_standings(), self)
        self.playoff_sim.setup_playoffs()
        self.playoff_sim.champion = self.playoff_sim.simulate_playoffs()

        for team in self.league.rosters:
            for player in team.players:
                games_missed = player.total_games_missed_this_season
                if games_missed:
                    self.tracker.record_player_games_missed(player.sleeper_id, games_missed)
                player.reset_injury_status()

    def simulate_team_week(self, team, week):
        total_score = 0
        for player in team.get_active_starters(week):
            score = player.calculate_score(self.league.scoring_settings, week)
            total_score += score
            self.tracker.record_player_score(player.sleeper_id, week, score)
        return total_score

    def get_matchups(self, week):
        week_matchups = self.matchups.get(str(week), [])
        pairs = {}
        for team in week_matchups:
            pairs.setdefault(team["matchup_id"], []).append(team)

        matchups = []
        for pair in pairs.values():
            if len(pair) != 2:
                continue
            home_team = self.get_team_by_roster_id(pair[0]["roster_id"])
            away_team = self.get_team_by_roster_id(pair[1]["roster_id"])
            if home_team and away_team:
                matchups.append(SimulationMatchup(home_team, away_team, week))
        return matchups

    def load_or_fetch_matchups(self):
        if self.matchups_file.exists():
            age = datetime.now() - datetime.fromtimestamp(self.matchups_file.stat().st_mtime)
            if age <= timedelta(days=1):
                with self.matchups_file.open() as file:
                    return json.load(file)

        matchups = self.fetch_all_matchups()
        with self.matchups_file.open("w") as file:
            json.dump(matchups, file)
        return matchups

    def fetch_all_matchups(self):
        matchups = {}
        for week in range(1, self.weeks + 1):
            url = f"https://api.sleeper.app/v1/league/{self.league.league_id}/matchups/{week}"
            with urlopen(url, timeout=30) as response:
                matchups[str(week)] = json.load(response)
        return matchups

    def get_team_by_roster_id(self, roster_id):
        return next((team for team in self.league.rosters if team.roster_id == roster_id), None)

    def get_standings(self):
        return sorted(self.league.rosters, key=lambda team: (team.wins, team.points_for), reverse=True)

    def simulate_week(self, week):
        for team in self.league.rosters:
            for player in team.players:
                player.update_injury_status(week)
            team.fill_starters(week)

        for matchup in self.get_matchups(week):
            matchup.simulate(self.league.scoring_settings, self.tracker)
