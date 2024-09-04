from custom_dataclasses.loaders.PlayerLoader import PlayerLoader
from custom_dataclasses.loaders.league_loader import LeagueLoader
from sim.MonteCarloSimulation import MonteCarloSimulation
import os
import pprint
import argparse




def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Run Monte Carlo Simulation for Fantasy Football")
    parser.add_argument('-n', '--num_simulations', type=int, default=250,
                        help='Number of simulations to run (default: 250)')
    args = parser.parse_args()

    sleeper_id = "1048288271089983488"  # You can change this to user input if needed
    
    player_loader = PlayerLoader()
    league_loader = LeagueLoader(sleeper_id, player_loader)
    
    # Load the league data
    league = league_loader.load_league()
    
    # Run Monte Carlo Simulation
    input("Press Enter to run Monte Carlo Simulation")
    os.system('cls' if os.name == 'nt' else 'clear')
    monte_carlo = MonteCarloSimulation(league, num_simulations=args.num_simulations)
    monte_carlo.run()


if __name__ == "__main__":
    main()
    # league.print_league()
    

# Add in season breakout players. (season long multipliers for players) based on years of experience and age
# Add in season tracking so we can we each fantasy teams best and worst seasons 
#       and breakdown of the wins and losses for those seasons as well as players averages for those seasons

