from custom_dataclasses.player_loader import PlayerLoader
from league_loader import LeagueLoader

def main():
    
    
    player_loader = PlayerLoader()
    # sleeper_id = input("Enter a Sleeper ID: ")
    # continue_prompt = input("Enter a Sleeper ID: ")
    sleeper_id = "1048288271089983488"
    
    print("Using Sleeper ID: ", sleeper_id)
    
    
    league_loader = LeagueLoader(sleeper_id, player_loader)
    
    # Load the league data
    league = league_loader.load_league()
    
    # print the league data in order from highest to lowest value
    # league.print_league_value_rankings()
    league.print_rosters()
    
    print(league.rosters[0].players[0].pff_projections)
    
    
    
    # league.print_league()
    


if __name__ == "__main__":
    main()
