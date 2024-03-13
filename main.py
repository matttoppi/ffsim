from player_loader import PlayerLoader
from league_loader import LeagueLoader

def main():
    player_loader = PlayerLoader()
    # sleeper_id = input("Enter a Sleeper ID: ")
    continue_prompt = input("Players loaded. Continue?")
    sleeper_id = "1048288271089983488"
    league_loader = LeagueLoader(sleeper_id, player_loader)
    
    # Load the league data
    league = league_loader.load_league()
    
    # Example usage of the loaded league data:
    print(f"League Name: {league.name}")
    print(f"Season: {league.season}")
    print("Rosters:")
    
    league.print_rosters(league)

if __name__ == "__main__":
    main()
