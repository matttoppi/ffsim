import random

class InjurySimulation:
    @staticmethod
    def check_for_injuries(player_sim, week):
        if player_sim.player.position in ['DEF', 'K']:
            return False
        
        injury_roll = random.random()
        if injury_roll < player_sim.player.injury_probability_game:
            injury_duration = InjurySimulation.generate_injury_duration(player_sim.player)
            injury_time = random.uniform(0, 1)
            player_sim.simulation_injury = {
                'start_week': week,
                'duration': injury_duration,
                'injury_time': injury_time,
                'return_week': week + injury_duration
            }
            return True
        return False

    @staticmethod
    def generate_injury_duration(player):
        base_duration = random.uniform(0.5, player.projected_games_missed * 2)
        return max(0.5, base_duration)

    @staticmethod
    def is_player_injured(player_sim, week):
        if player_sim.simulation_injury:
            injury_end = player_sim.simulation_injury['start_week'] + player_sim.simulation_injury['duration']
            return week < injury_end
        return False