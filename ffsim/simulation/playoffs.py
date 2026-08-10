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
    def __init__(self, teams, division1_winner, division2_winner, simulation_season):
        self.teams = teams
        self.division1_winner = division1_winner
        self.division2_winner = division2_winner
        self.matches = []
        self.simulation_season = simulation_season
        self.first_week = simulation_season.weeks + 1

    def create_bracket(self):
        bye_teams = [self.division1_winner, self.division2_winner]
        non_bye_teams = [team for team in self.teams if team not in bye_teams]
        if len(non_bye_teams) != 4:
            raise ValueError("The playoff bracket requires six teams.")
        self.matches.append(
            PlayoffMatch(
                non_bye_teams[0],
                non_bye_teams[-1],
                self.first_week,
                self.simulation_season,
            )
        )
        self.matches.append(
            PlayoffMatch(
                non_bye_teams[1],
                non_bye_teams[-2],
                self.first_week,
                self.simulation_season,
            )
        )

    def simulate_round(self):
        results = [match.simulate() for match in self.matches]
        self.matches = []
        return results

    def create_semifinal(self, first_round_winners, week):
        if len(first_round_winners) != 2:
            raise ValueError("The semifinals require two first-round winners.")
        self.matches.append(
            PlayoffMatch(
                self.division1_winner,
                first_round_winners[1],
                week,
                self.simulation_season,
            )
        )
        self.matches.append(
            PlayoffMatch(
                self.division2_winner,
                first_round_winners[0],
                week,
                self.simulation_season,
            )
        )

    def create_final(self, semifinal_winners, week):
        if len(semifinal_winners) != 2:
            raise ValueError("The final requires two semifinal winners.")
        self.matches.append(
            PlayoffMatch(
                semifinal_winners[0],
                semifinal_winners[1],
                week,
                self.simulation_season,
            )
        )


class PlayoffSimulation:
    def __init__(self, league, season_standings, simulation_season):
        self.league = league
        self.season_standings = season_standings
        self.simulation_season = simulation_season
        self.bracket = None

    def setup_playoffs(self):
        divisions = sorted(self.league.divisions.values())
        if len(divisions) != 2 or self.league.playoff_teams != 6:
            raise ValueError("The simulator currently requires six playoff teams across two divisions.")

        division1_teams = [
            team for team in self.season_standings if team.roster_id in divisions[0]
        ]
        division2_teams = [
            team for team in self.season_standings if team.roster_id in divisions[1]
        ]
        if not division1_teams or not division2_teams:
            raise ValueError("Each division must contain at least one roster.")

        division1_winner = max(division1_teams, key=lambda team: (team.wins, team.points_for))
        division2_winner = max(division2_teams, key=lambda team: (team.wins, team.points_for))

        if (division1_winner.wins, division1_winner.points_for) < (
            division2_winner.wins,
            division2_winner.points_for,
        ):
            division1_winner, division2_winner = division2_winner, division1_winner

        remaining_teams = [
            team
            for team in self.season_standings
            if team not in (division1_winner, division2_winner)
        ]
        wild_card_teams = sorted(
            remaining_teams, key=lambda team: (team.wins, team.points_for), reverse=True
        )[: self.league.playoff_teams - 2]
        playoff_teams = [division1_winner, division2_winner] + wild_card_teams
        playoff_teams.sort(key=lambda team: (team.wins, team.points_for), reverse=True)

        self.bracket = PlayoffBracket(
            playoff_teams,
            division1_winner,
            division2_winner,
            self.simulation_season,
        )
        self.bracket.create_bracket()

    def simulate_playoffs(self):
        first_week = self.bracket.first_week
        first_round_winners = self.bracket.simulate_round()
        self.bracket.create_semifinal(first_round_winners, first_week + 1)

        semifinal_winners = self.bracket.simulate_round()
        self.bracket.create_final(semifinal_winners, first_week + 2)
        return self.bracket.simulate_round()[0]
