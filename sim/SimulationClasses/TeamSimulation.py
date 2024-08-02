from sim.SimulationClasses.PlayerSimulator import PlayerSimulator


class TeamSimulation:
    def __init__(self, fantasy_team):
        self.fantasy_team = fantasy_team
        self.player_sims = {player.sleeper_id: PlayerSimulator(player) for player in fantasy_team.players}
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        self.weekly_scores = []

    def simulate_week(self, week, scoring_settings):
        weekly_score = 0
        for player_sim in self.player_sims.values():
            player_score = player_sim.simulate_week(week, scoring_settings)
            weekly_score += player_score

        self.weekly_scores.append(weekly_score)
        self.points_for += weekly_score
        return weekly_score

    def update_record(self, won, tied, points_against):
        if won:
            self.wins += 1
        elif tied:
            self.ties += 1
        else:
            self.losses += 1
        self.points_against += points_against

    def check_for_injuries(self, week):
        for player_sim in self.player_sims.values():
            player_sim.check_for_injury(week)

    def get_active_players(self, week):
        return [player_sim for player_sim in self.player_sims.values() if not player_sim.is_injured(week)]

    def get_weekly_score(self, week):
        return self.weekly_scores[week - 1] if week <= len(self.weekly_scores) else 0