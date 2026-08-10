import json
from types import SimpleNamespace
from urllib.request import urlopen

import numpy as np

from ffsim.paths import CACHE_DIR
from ffsim.simulation.matchup import SimulationMatchup
from ffsim.simulation.playoffs import PlayoffSimulation


def refresh_matchups(league_id, weeks):
    matchups = {}
    for week in range(1, weeks + 1):
        with urlopen(f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}", timeout=30) as response:
            matchups[str(week)] = json.load(response)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"matchups_{league_id}.json").write_text(json.dumps(matchups, indent=2) + "\n")


class SimulationSeason:
    def __init__(self, league, tracker, weeks=14, rng=None):
        self.league = league
        self.tracker = tracker
        self.weeks = weeks
        self.rng = rng or np.random.default_rng()
        path = CACHE_DIR / f"matchups_{league.league_id}.json"
        if not path.exists():
            raise FileNotFoundError("Matchup cache is missing. Run `python -m ffsim refresh` first.")
        self.matchups = json.loads(path.read_text())
        self.playoff_sim = None

    def simulate(self):
        cutoff = min(self.league.last_scored_week, self.weeks)
        future_weeks = list(range(cutoff + 1, self.weeks + 4))
        for team in self.league.rosters:
            for player in team.players:
                player.prepare_availability(future_weeks, self.rng)

        self._apply_completed_regular_season(cutoff)
        for week in range(cutoff + 1, self.weeks + 1):
            self.simulate_week(week)

        if self.league.last_scored_week > self.weeks:
            if self.league.status != "complete":
                raise ValueError("Partially completed fantasy playoffs are not yet supported")
            self.playoff_sim = self._completed_playoffs()
        else:
            self.playoff_sim = PlayoffSimulation(self.league, self.get_standings(), self)
            self.playoff_sim.setup_playoffs()
            self.playoff_sim.champion = self.playoff_sim.simulate_playoffs()

        for team in self.league.rosters:
            for player in team.players:
                if player.total_games_missed_this_season:
                    self.tracker.record_player_games_missed(
                        player.sleeper_id, player.total_games_missed_this_season
                    )

    def _apply_completed_regular_season(self, cutoff):
        for week in range(1, cutoff + 1):
            entries = self.matchups.get(str(week))
            if entries is None:
                raise ValueError(f"Completed Sleeper matchup week {week} is missing from the snapshot")
            pairs = {}
            completed_matchups = []
            for entry in entries:
                pairs.setdefault(entry.get("matchup_id"), []).append(entry)
                starters = tuple(entry.get("starters", ()))
                self.league.completed_starters[(week, entry["roster_id"])] = starters
                for player_id, score in (entry.get("players_points") or {}).items():
                    if player_id in starters:
                        self.tracker.record_player_score(player_id, week, float(score), played=True)
            for pair in pairs.values():
                if len(pair) != 2:
                    raise ValueError(f"Completed Sleeper matchup week {week} has an incomplete pairing")
                home, away = pair
                home_score = _completed_score(home)
                away_score = _completed_score(away)
                matchup = SimulationMatchup(
                    self.get_team_by_roster_id(home["roster_id"]),
                    self.get_team_by_roster_id(away["roster_id"]),
                    week,
                )
                matchup.home_score, matchup.away_score = home_score, away_score
                matchup.update_records()
                completed_matchups.append(matchup)
            self._apply_median_game(completed_matchups)

    def _completed_playoffs(self):
        bracket = self.league.winners_bracket
        final = max(bracket, key=lambda matchup: matchup.get("r", 0), default=None)
        if not final or not final.get("w"):
            raise ValueError("Completed league snapshot is missing the final playoff winner")
        roster_ids = sorted({
            int(roster_id)
            for matchup in bracket
            for roster_id in (matchup.get("t1"), matchup.get("t2"), matchup.get("w"), matchup.get("l"))
            if isinstance(roster_id, (int, str)) and str(roster_id).isdigit()
        })
        teams = [self.get_team_by_roster_id(roster_id) for roster_id in roster_ids]
        teams = [team for team in teams if team]
        division_winners = [
            max(
                (team for team in self.league.rosters if team.roster_id in roster_ids_in_division),
                key=lambda team: (team.wins, team.points_for),
            )
            for roster_ids_in_division in self.league.divisions.values()
        ]
        bracket_state = SimpleNamespace(
            teams=teams,
            division1_winner=division_winners[0],
            division2_winner=division_winners[1],
        )
        return SimpleNamespace(
            bracket=bracket_state,
            champion=self.get_team_by_roster_id(int(final["w"])),
        )

    def simulate_team_week(self, team, week):
        total_score = 0.0
        for player in team.get_active_starters(week):
            score = player.calculate_score(self.league.scoring_settings, week, self.rng)
            total_score += score
            self.tracker.record_player_score(player.sleeper_id, week, score, played=True)
        return total_score

    def get_matchups(self, week):
        pairs = {}
        for team in self.matchups.get(str(week), []):
            pairs.setdefault(team["matchup_id"], []).append(team)
        matchups = []
        for pair in pairs.values():
            if len(pair) == 2:
                home = self.get_team_by_roster_id(pair[0]["roster_id"])
                away = self.get_team_by_roster_id(pair[1]["roster_id"])
                if home and away:
                    matchups.append(SimulationMatchup(home, away, week, self.rng))
        return matchups

    def get_team_by_roster_id(self, roster_id):
        return next((team for team in self.league.rosters if team.roster_id == roster_id), None)

    def get_standings(self):
        return sorted(self.league.rosters, key=lambda team: (team.wins, team.points_for), reverse=True)

    def simulate_week(self, week):
        for team in self.league.rosters:
            team.fill_starters(week)
        matchups = self.get_matchups(week)
        for matchup in matchups:
            matchup.simulate(self.league.scoring_settings, self.tracker)
        self._apply_median_game(matchups)

    def _apply_median_game(self, matchups):
        if not self.league.league_average_match or not matchups:
            return
        teams_and_scores = [
            pair
            for matchup in matchups
            for pair in ((matchup.home_team, matchup.home_score), (matchup.away_team, matchup.away_score))
        ]
        median = float(np.median([score for _, score in teams_and_scores]))
        for team, score in teams_and_scores:
            if score > median:
                team.wins += 1
            elif score < median:
                team.losses += 1
            else:
                team.ties += 1


def _completed_score(entry):
    value = entry.get("custom_points") if entry.get("custom_points") is not None else entry.get("points")
    if value is None:
        raise ValueError(f"Completed Sleeper matchup has no points for roster {entry.get('roster_id')}")
    return float(value)
