import random
from sim.SimulationClasses.InjurySimulation import InjurySimulation

class PlayerSimulator:
    def __init__(self, player):
        self.player = player
        self.simulation_injury = None
        self.returning_from_injury = False
        self.avg_points_per_game = 0 
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        self.current_week_score = 0

    def simulate_player_score(self, week, scoring_settings):
        if not self.player.pff_projections:
            return 0

        proj = self.player.pff_projections
        games = float(proj.games or 0)
        bye_week = int(proj.bye_week or 0)

        if games == 0 or week == bye_week:
            return 0

        # Calculate per-game averages and add randomness
        pass_yds = max(0, random.gauss(float(proj.pass_yds or 0) / games, float(proj.pass_yds or 0) / games * 0.25))
        pass_td = max(0, random.gauss(float(proj.pass_td or 0) / games, float(proj.pass_td or 0) / games * 0.75))
        pass_int = max(0, random.gauss(float(proj.pass_int or 0) / games, float(proj.pass_int or 0) / games * 0.75))
        rush_yds = max(0, random.gauss(float(proj.rush_yds or 0) / games, float(proj.rush_yds or 0) / games * 0.25))
        rush_td = max(0, random.gauss(float(proj.rush_td or 0) / games, float(proj.rush_td or 0) / games * 0.75))
        receptions = max(0, random.gauss(float(proj.recv_receptions or 0) / games, float(proj.recv_receptions or 0) / games * 0.75))
        rec_yds = max(0, random.gauss(float(proj.recv_yds or 0) / games, float(proj.recv_yds or 0) / games * 0.25))
        rec_td = max(0, random.gauss(float(proj.recv_td or 0) / games, float(proj.recv_td or 0) / games * 0.75))
        
        # Round stats to realistic values
        pass_yds, pass_td, pass_int = round(pass_yds), round(pass_td), round(pass_int)
        rush_yds, rush_td = round(rush_yds), round(rush_td)
        receptions, rec_yds, rec_td = round(receptions), round(rec_yds), round(rec_td)

        # Calculate score based on league scoring settings
        score = (
            pass_yds * scoring_settings.pass_yd +
            pass_td * scoring_settings.pass_td +
            pass_int * scoring_settings.pass_int +
            rush_yds * scoring_settings.rush_yd +
            rush_td * scoring_settings.rush_td +
            rec_yds * scoring_settings.rec_yd +
            rec_td * scoring_settings.rec_td +
            receptions * (scoring_settings.te_rec if self.player.position == 'TE' else scoring_settings.rec)
        )

        return score

    def simulate_week(self, week, scoring_settings):
        if self.is_injured(week):
            self.current_week_score = 0
            return 0

        if self.player.position in ['DEF', 'K']:
            self.current_week_score = self.simulate_special_position()
        else:
            self.current_week_score = self.simulate_player_score(week, scoring_settings)

        self.update_avg_points(self.current_week_score)
        return self.current_week_score

    def is_injured(self, week):
        if self.simulation_injury:
            injury_end = self.simulation_injury['start_week'] + self.simulation_injury['duration']
            if week >= injury_end:
                self.simulation_injury = None
                self.returning_from_injury = True
                return False
            return True
        return False

    def check_for_injury(self, week):
        if InjurySimulation.check_for_injuries(self, week):
            return True
        return False

    def simulate_special_position(self):
        if self.player.position == 'DEF':
            return max(-5, min(35, round(random.gauss(15, 10))))
        elif self.player.position == 'K':
            return max(0, min(20, round(random.gauss(10, 5))))



    def update_avg_points(self, score):
        self.total_simulated_games += 1
        self.total_simulated_points += score
        self.avg_points_per_game = self.total_simulated_points / self.total_simulated_games

    def get_current_week_score(self):
        return self.current_week_score