from player_loader import PlayerLoader
from league_loader import LeagueLoader

def main():
    player_loader = PlayerLoader()
    # sleeper_id = input("Enter a Sleeper ID: ")
    # continue_prompt = input("Enter a Sleeper ID: ")
    sleeper_id = "1048288271089983488"
    
    
    league_loader = LeagueLoader(sleeper_id, player_loader)
    
    # Load the league data
    league = league_loader.load_league()
    
    # league.print_league()
    
    

if __name__ == "__main__":
    main()
