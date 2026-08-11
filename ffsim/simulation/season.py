import json
from functools import lru_cache
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pandas as pd

from ffsim.paths import CACHE_DIR, DATA_DIR
from ffsim.models.player import mean_preserving_lognormal
from ffsim.simulation.matchup import SimulationMatchup
from ffsim.simulation.playoffs import PlayoffSimulation


MATCHUP_WEIGHTS = {
    "QB": {"di_grade": 0.20, "edge_grade": 0.30, "lb_grade": 0.10, "cb_grade": 0.25, "s_grade": 0.15},
    "RB": {"di_grade": 0.45, "edge_grade": 0.25, "lb_grade": 0.30},
    "WR": {"edge_grade": 0.15, "cb_grade": 0.55, "s_grade": 0.30},
    "TE": {"edge_grade": 0.10, "lb_grade": 0.55, "s_grade": 0.35},
}


def refresh_matchups(league_id, weeks):
    path = CACHE_DIR / f"matchups_{league_id}.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    matchups = {}
    for week in range(1, weeks + 1):
        try:
            with urlopen(f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}", timeout=30) as response:
                matchups[str(week)] = json.load(response)
        except HTTPError as error:
            if error.code != 404 or str(week) not in previous:
                raise
            matchups[str(week)] = previous[str(week)]
            print(f"Sleeper returned 404 for matchup week {week}; preserved the existing snapshot.")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(matchups, indent=2) + "\n")


class SimulationSeason:
    def __init__(self, league, tracker, weeks=14, rng=None, scenario=None):
        self.league = league
        self.tracker = tracker
        self.weeks = weeks
        self.rng = rng or np.random.default_rng()
        self.scenario = scenario or {}
        self.nfl_games, self.nfl_opponents = self._load_nfl_schedule()
        self.defense_matchups, self.average_defense = self._load_defense_matchups()
        path = CACHE_DIR / f"matchups_{league.league_id}.json"
        if not path.exists():
            raise FileNotFoundError("Matchup cache is missing. Run `python -m ffsim refresh` first.")
        self.matchups = json.loads(path.read_text())
        self.players = tuple(player for team in league.rosters for player in team.players)
        self.teams_by_roster_id = {team.roster_id: team for team in league.rosters}
        self.factor_groups = tuple(
            (
                tuple(group),
                tuple(player.expected_weekly_score(league.scoring_settings) for player in group),
            )
            for group in _groups(self.players, lambda player: (player.team, player.position))
        )
        self.week_contexts = {
            week: tuple(self._player_week_context(player, week) for player in self.players)
            for week in range(1, weeks + 4)
        }
        self.matchup_roster_pairs = {
            week: tuple(
                (pair[0]["roster_id"], pair[1]["roster_id"])
                for pair in _groups(entries, lambda entry: entry["matchup_id"])
                if len(pair) == 2
            )
            for week, entries in self.matchups.items()
        }
        self.playoff_sim = None

    def simulate(self):
        cutoff = min(self.league.last_scored_week, self.weeks)
        future_weeks = list(range(cutoff + 1, self.weeks + 4))
        for player in self.players:
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

        for player in self.players:
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
        total_score = team.streamer_score(self.rng)
        for player in team.get_active_starters(week):
            score = player.calculate_score(self.league.scoring_settings, week, self.rng)
            total_score += score
            self.tracker.record_player_score(player.sleeper_id, week, score, played=True)
        return total_score

    def get_matchups(self, week):
        matchups = []
        for home_id, away_id in self.matchup_roster_pairs.get(str(week), ()):
            home = self.get_team_by_roster_id(home_id)
            away = self.get_team_by_roster_id(away_id)
            if home and away:
                matchups.append(SimulationMatchup(home, away, week, self.rng))
        return matchups

    def get_team_by_roster_id(self, roster_id):
        return self.teams_by_roster_id.get(roster_id)

    def get_standings(self):
        return sorted(self.league.rosters, key=lambda team: (team.wins, team.points_for), reverse=True)

    def simulate_week(self, week):
        self.prepare_week_factors(week)
        for team in self.league.rosters:
            team.fill_starters(week)
        matchups = self.get_matchups(week)
        for matchup in matchups:
            matchup.simulate(self.league.scoring_settings, self.tracker)
        self._apply_median_game(matchups)

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_nfl_schedule():
        path = DATA_DIR / "historical" / "nflverse" / "reference" / "games.csv"
        games = pd.read_csv(path, usecols=["season", "game_type", "week", "away_team", "home_team"])
        games = games[(games.season == 2026) & (games.game_type == "REG")]
        game_ids = {
            (int(row.week), team): f"{int(row.week)}:{row.away_team}:{row.home_team}"
            for row in games.itertuples()
            for team in (row.away_team, row.home_team)
        }
        opponents = {
            (int(row.week), team): opponent
            for row in games.itertuples()
            for team, opponent in ((row.away_team, row.home_team), (row.home_team, row.away_team))
        }
        return game_ids, opponents

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_defense_matchups():
        data = pd.read_csv(DATA_DIR / "projections" / "defense_matchups.csv")
        if len(data) != 32 or data.team.nunique() != 32:
            raise ValueError("Defense matchup data must contain exactly 32 unique teams")
        grades = {
            row.team: {
                position: sum(getattr(row, field) * weight for field, weight in weights.items())
                for position, weights in MATCHUP_WEIGHTS.items()
            }
            for row in data.itertuples()
        }
        averages = {
            position: float(np.mean([team[position] for team in grades.values()]))
            for position in MATCHUP_WEIGHTS
        }
        return grades, averages

    def prepare_week_factors(self, week):
        game_cv = self.scenario.get("game_environment_cv", 0.0)
        team_cv = self.scenario.get("team_environment_cv", 0.0)
        competition_cv = self.scenario.get("competition_cv", 0.0)
        contexts = getattr(self, "week_contexts", {}).get(week)
        if contexts is None:
            players = tuple(player for team in self.league.rosters for player in team.players)
            contexts = tuple(self._player_week_context(player, week) for player in players)
        else:
            players = self.players
        for player, base_factor, _ in contexts:
            player.week_factor = base_factor
        if not any((game_cv, team_cv, competition_cv)):
            return
        game_factors, team_factors = {}, {}
        for player, _, game in contexts:
            if game_cv and game not in game_factors:
                game_factors[game] = mean_preserving_lognormal(1, game_cv, self.rng)
            if team_cv and player.team not in team_factors:
                team_factors[player.team] = mean_preserving_lognormal(1, team_cv, self.rng)
            player.week_factor *= game_factors.get(game, 1.0) * team_factors.get(player.team, 1.0)
        if not competition_cv:
            return
        groups = getattr(self, "factor_groups", None)
        if groups is None:
            groups = tuple(
                (
                    tuple(group),
                    tuple(
                        player.expected_weekly_score(self.league.scoring_settings)
                        for player in group
                    ),
                )
                for group in _groups(players, lambda player: (player.team, player.position))
            )
        for group, weights in groups:
            shocks = [mean_preserving_lognormal(1, competition_cv, self.rng) for _ in group]
            normalizer = np.average(shocks, weights=weights) if sum(weights) else 1.0
            for player, shock in zip(group, shocks):
                player.week_factor *= shock / normalizer

    def _player_week_context(self, player, week):
        opponent = self.nfl_opponents.get((week, player.team))
        grade = self.defense_matchups.get(opponent, {}).get(player.position)
        base_factor = (
            min(1.08, max(0.92, 1 - 0.02 * (grade - self.average_defense[player.position])))
            if grade is not None else 1.0
        )
        game = self.nfl_games.get((week, player.team), f"{week}:{player.team}")
        return player, base_factor, game

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


def _groups(values, key):
    groups = {}
    for value in values:
        groups.setdefault(key(value), []).append(value)
    return groups.values()
