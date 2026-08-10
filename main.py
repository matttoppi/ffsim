from custom_dataclasses.loaders.PlayerLoader import PlayerLoader
from custom_dataclasses.loaders.league_loader import LeagueLoader
from sim.MonteCarloSimulation import MonteCarloSimulation
import os



def main():
    sleeper_id = "1048288271089983488"  # You can change this to user input if needed
    
    player_loader = PlayerLoader()
    league_loader = LeagueLoader(sleeper_id, player_loader)
    
    league = league_loader.load_league()
    league.print_rosters()

    input("Press Enter to run Monte Carlo Simulation")
    os.system('cls' if os.name == 'nt' else 'clear')
    monte_carlo = MonteCarloSimulation(league, num_simulations=150)
    monte_carlo.run()


if __name__ == "__main__":
    main()
