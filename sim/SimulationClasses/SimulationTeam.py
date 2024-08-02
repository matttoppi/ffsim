from sim.SimulationClasses.PlayerSimulator import PlayerSimulator


class SimulationTeam:
    def __init__(self, fantasy_team):
        self.fantasy_team = fantasy_team
        self.roster_id = fantasy_team.roster_id
        self.player_sims = {player.sleeper_id: PlayerSimulator(player) for player in fantasy_team.players}
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        self.weekly_scores = {}
        self.best_week = {'week': 0, 'score': 0}
        self.worst_week = {'week': 0, 'score': float('inf')}

    def simulate_week(self, week, scoring_settings):
        weekly_score = sum(player_sim.simulate_week(week, scoring_settings) for player_sim in self.player_sims.values())
        self.weekly_scores[week] = weekly_score
        self.points_for += weekly_score
        self.update_best_worst_week(week, weekly_score)
        return weekly_score

    def update_record(self, won, tied, points_against, week):
        if won:
            self.wins += 1
        elif tied:
            self.ties += 1
        else:
            self.losses += 1
        self.points_against += points_against

    def get_weekly_score(self, week):
        return self.weekly_scores.get(week, 0)

    def update_best_worst_week(self, week, score):
        if score > self.best_week['score']:
            self.best_week = {'week': week, 'score': score}
        if score < self.worst_week['score']:
            self.worst_week = {'week': week, 'score': score}

    def check_for_injuries(self, week):
        for player_sim in self.player_sims.values():
            player_sim.check_for_injury(week)

    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        self.weekly_scores = {}
        self.best_week = {'week': 0, 'score': 0}
        self.worst_week = {'week': 0, 'score': float('inf')}