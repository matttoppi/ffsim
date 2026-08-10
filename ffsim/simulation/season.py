import json
from urllib.request import urlopen

from ffsim.paths import CACHE_DIR
from ffsim.simulation.matchup import SimulationMatchup
from ffsim.simulation.playoffs import PlayoffSimulation


def refresh_matchups(league_id, weeks):
    matchups = {}
    for week in range(1, weeks + 1):
        url = f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}"
        with urlopen(url, timeout=30) as response:
            matchups[str(week)] = json.load(response)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"matchups_{league_id}.json"
    path.write_text(json.dumps(matchups, indent=2) + "\n")


class SimulationSeason:
    def __init__(self, league, tracker, weeks=14):
        self.league = league
        self.tracker = tracker
        self.weeks = weeks
        self.matchups_file = CACHE_DIR / f"matchups_{league.league_id}.json"
        if not self.matchups_file.exists():
            raise FileNotFoundError("Matchup cache is missing. Run `python -m ffsim refresh` first.")
        with self.matchups_file.open() as file:
            self.matchups = json.load(file)
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
