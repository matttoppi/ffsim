from custom_dataclasses.loaders.PlayerLoader import PlayerLoader
from custom_dataclasses.loaders.league_loader import LeagueLoader
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
        # pprint.pprint(player.pff_projections.to_dict())
    
    # Print league info
    league.print_rosters()
    
    # Run Monte Carlo Simulation
    input("Press Enter to run Monte Carlo Simulation")
    os.system('cls' if os.name == 'nt' else 'clear')
    monte_carlo = MonteCarloSimulation(league, num_simulations=75)
    monte_carlo.run()


if __name__ == "__main__":
    main()
    # league.print_league()
    



# FIX OUTPUT ISSUE: players at very last full team print have higher averages than they do in the top 30 players print



