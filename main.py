from custom_dataclasses.loaders.PlayerLoader import PlayerLoader
from league_loader import LeagueLoader
from sim.MonteCarloSimulation import MonteCarloSimulation
import os
def main():
    
    
    player_loader = PlayerLoader()
    # sleeper_id = input("Enter a Sleeper ID: ")
    # continue_prompt = input("Enter a Sleeper ID: ")
    sleeper_id = "1048288271089983488"
    
    # print("Using Sleeper ID: ", sleeper_id)
    
    
    league_loader = LeagueLoader(sleeper_id, player_loader)
    
    # Load the league data
    league = league_loader.load_league()
    
    # print the league data in order from highest to lowest value
    # league.print_league_value_rankings()
    league.print_rosters()
    # league.scoring_settings.print_scoring_settings()
 
    
    input("Press Enter to run Monte Carlo Simulation")
    # clear the console
    os.system('cls' if os.name == 'nt' else 'clear')   
    monte_carlo = MonteCarloSimulation(league, num_simulations=25, debugging=False)
    monte_carlo.run()
    
    monte_carlo.print_results()
    # monte_carlo.print_average_starter_scores()
    monte_carlo.print_top_players_by_position()
    monte_carlo.print_projected_standings()
    
    
    

if __name__ == "__main__":
    main()
    # league.print_league()
    





#  TODO: Fix defenses not being found in monte carlo
# TODO: Fix kickers not being found in monte carlo
# TODO: Fix no scores for players that werent in the pff projections. Give them random scoring 
# TODO: Implement injuries
