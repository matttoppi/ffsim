class PlayoffMatch:
    def __init__(self, home_team, away_team, week, simulation_season):
        self.home_team = home_team
        self.away_team = away_team
        self.week = week
        self.simulation_season = simulation_season
        self.winner = None

    def simulate(self):
        for team in (self.home_team, self.away_team):
            team.fill_starters(self.week)

        home_score = self.simulation_season.simulate_team_week(self.home_team, self.week)
        away_score = self.simulation_season.simulate_team_week(self.away_team, self.week)
        
        self.winner = self.home_team if home_score > away_score else self.away_team
        return self.winner


class PlayoffBracket:
    def __init__(self, teams, division_winners, simulation_season):
        self.teams = teams
        self.division_winners = division_winners
        self.matches = []
        self.simulation_season = simulation_season
        self.first_week = simulation_season.weeks + 1

    def create_bracket(self):
        first_round = self.teams[2:] if len(self.teams) == 6 else self.teams
        self._pair_outer_seeds(first_round, self.first_week)

    def _pair_outer_seeds(self, teams, week):
        self.matches.extend(
            PlayoffMatch(teams[index], teams[-index - 1], week, self.simulation_season)
            for index in range(len(teams) // 2)
        )

    def simulate_round(self):
        results = [match.simulate() for match in self.matches]
        self.matches = []
        return results

    def create_next_round(self, winners, week):
        if len(self.teams) == 6 and week == self.first_week + 1:
            self.matches.append(
                PlayoffMatch(self.teams[0], winners[1], week, self.simulation_season)
            )
            self.matches.append(
                PlayoffMatch(self.teams[1], winners[0], week, self.simulation_season)
            )
            return
        self._pair_outer_seeds(winners, week)


class PlayoffSimulation:
    def __init__(self, league, season_standings, simulation_season):
        self.league = league
        self.season_standings = season_standings
        self.simulation_season = simulation_season
        self.bracket = None

    def setup_playoffs(self):
        validate_playoff_format(self.league)
        division_winners = get_division_winners(self.league, self.season_standings)
        remaining_teams = [
            team for team in self.season_standings if team not in division_winners
        ]
        wild_card_teams = sorted(
            remaining_teams, key=lambda team: (team.wins, team.points_for), reverse=True
        )[: self.league.playoff_teams - len(division_winners)]
        playoff_teams = division_winners + wild_card_teams
        if len(playoff_teams) != self.league.playoff_teams:
            raise ValueError(
                f"Sleeper setting playoff_teams={self.league.playoff_teams} exceeds "
                f"the league's {len(self.league.rosters)} rosters"
            )

        self.bracket = PlayoffBracket(
            playoff_teams,
            division_winners,
            self.simulation_season,
        )
        self.bracket.create_bracket()

    def simulate_playoffs(self):
        week = self.bracket.first_week
        while True:
            self.simulation_season.prepare_week_factors(week)
            winners = self.bracket.simulate_round()
            if len(winners) == 1:
                return winners[0]
            week += 1
            self.bracket.create_next_round(winners, week)


def validate_playoff_format(league):
    if league.playoff_teams not in {4, 6, 8}:
        raise ValueError(
            f"Unsupported Sleeper setting playoff_teams={league.playoff_teams!r}; "
            "supported values are 4, 6, and 8"
        )
    if league.playoff_round_type != 0:
        raise ValueError(
            f"Unsupported Sleeper setting playoff_round_type={league.playoff_round_type!r}; "
            "only single-week rounds (0) are supported"
        )
    if league.playoff_seed_type != 0:
        raise ValueError(
            f"Unsupported Sleeper setting playoff_seed_type={league.playoff_seed_type!r}; "
            "only record-based seeding (0) is supported"
        )
    assigned_rosters = {
        roster_id for roster_ids in league.divisions.values() for roster_id in roster_ids
    }
    all_rosters = {team.roster_id for team in league.rosters}
    if len(league.divisions) != league.division_count:
        raise ValueError(
            f"Sleeper setting divisions={league.division_count} does not match "
            f"the roster division assignments ({len(league.divisions)})"
        )
    if assigned_rosters and assigned_rosters != all_rosters:
        raise ValueError(
            "Unsupported Sleeper roster setting division: every roster must belong to a division"
        )
    if len(league.divisions) > league.playoff_teams:
        raise ValueError(
            f"Unsupported Sleeper setting divisions={len(league.divisions)}; "
            f"it exceeds playoff_teams={league.playoff_teams}"
        )


def get_division_winners(league, standings):
    winners = [
        max(
            (team for team in standings if team.roster_id in roster_ids),
            key=lambda team: (team.wins, team.points_for),
        )
        for _, roster_ids in sorted(league.divisions.items())
    ]
    return sorted(winners, key=lambda team: (team.wins, team.points_for), reverse=True)
