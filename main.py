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
    
    # Print league info
    league.print_rosters()
    
    # Run Monte Carlo Simulation
    input("Press Enter to run Monte Carlo Simulation")
    os.system('cls' if os.name == 'nt' else 'clear')
    monte_carlo = MonteCarloSimulation(league, num_simulations=150)
    monte_carlo.run()


if __name__ == "__main__":
    main()
    # league.print_league()
    


# Add in season breakout players. (season long multipliers for players) based on years of experience and age
# Add in season tracking so we can we each fantasy teams best and worst seasons 
#       and breakdown of the wins and losses for those seasons as well as players averages for those seasons


# seems like a season is being tracked 2 times now

