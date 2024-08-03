
import random
from sim.SimulationClasses.InjurySimulation import InjurySimulation

class PlayerSimulator:
    def __init__(self, player):
        self.player = player
        self.simulation_injury = None
        self.returning_from_injury = False
        self.total_simulated_points = 0
        self.total_simulated_games = 0
        self.current_week_score = 0
        self.weekly_scores = {}  # Add this line to store weekly scores

    def simulate_week(self, week, scoring_settings):
        if self.player.is_injured(week):
            self.current_week_score = 0
        else:
            self.current_week_score = self.calculate_score(scoring_settings)
            self.check_for_injury(week)
            
        print(f"{self.player.name} scored {self.current_week_score} in week {week}")
        return self.current_week_score

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
    def simulate_special_position(self):
        if self.player.position == 'DEF':
            return max(-5, min(35, round(random.gauss(15, 10))))
        elif self.player.position == 'K':
            return max(0, min(20, round(random.gauss(10, 5))))

    def update_stats(self, score):
        self.total_simulated_games += 1
        self.total_simulated_points += score

    def check_for_injury(self, week):
        if random.random() < self.player.injury_probability_game:
            injury_duration = self.generate_injury_duration()
            self.player.simulation_injury = {
                'start_week': week,
                'duration': injury_duration,
                'return_week': week + math.ceil(injury_duration)
            }
            return True
        return False

    def generate_injury_duration(self):
        return max(0.5, random.gauss(self.player.projected_games_missed, 1))
    
    def get_current_week_score(self):
        return self.current_week_score