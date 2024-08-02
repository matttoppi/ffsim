from custom_dataclasses.loaders.PlayerLoader import PlayerLoader
from league_loader import LeagueLoader
from sim.MonteCarloSimulation import MonteCarloSimulation
import os
import pprint



def main():
    sleeper_id = "1048288271089983488"  # You can change this to user input if needed
    
    player_loader = PlayerLoader()
    league_loader = LeagueLoader(sleeper_id, player_loader)
    
    # Load the league data
    league = league_loader.load_league()
    
    print("\nPlayer data for the first 5 players in the first team:")
    for player in league.rosters[0].players[:3]:
    #    pretty print the dict
        # print(player.to_dict())
        pprint.pprint(player.to_dict())
    
    # Print league info
    league.print_rosters()
    
    # Run Monte Carlo Simulation
    input("Press Enter to run Monte Carlo Simulation")
    os.system('cls' if os.name == 'nt' else 'clear')
    monte_carlo = MonteCarloSimulation(league, num_simulations=250, debugging=False)
    monte_carlo.run()
    
    monte_carlo.print_results()
    monte_carlo.print_top_players_by_position()
    monte_carlo.print_projected_standings()

if __name__ == "__main__":
    main()
    # league.print_league()
    



#GLARING ISSUE: INJURIES ARE LOPSIDED. SOME HAVE 500pts lost in a week

#  TODO: Fix defenses not being found in monte carlo
# TODO: Fix kickers not being found in monte carlo
# TODO: Fix no scores for players that werent in the pff projections. Give them random scoring 
# TODO: Implement injuries
