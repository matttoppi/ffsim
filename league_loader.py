class LeagueLoader:
    def __init__(self, league_id, player_loader):
        self.sleeper_league = SleeperLeague(league_id)
        self.league_id = league_id
        self.player_loader = player_loader  # Instance of PlayerLoader

    def load_league(self):
        league_data = self.sleeper_league.get_league()
        league = League(league_data)

        rosters = self.sleeper_league.get_rosters()
        for roster_data in rosters:
            # Use owner_id as a placeholder for team name if needed, or modify according to your data structure
            fantasy_team = FantasyTeam(str(roster_data['owner_id']))

            # Populate team stats and settings
            fantasy_team.wins = roster_data['settings']['wins']
            fantasy_team.losses = roster_data['settings']['losses']
            fantasy_team.ties = roster_data['settings']['ties']
            fantasy_team.fantasy_pts_total = roster_data['settings']['fpts']
            fantasy_team.points_for = roster_data['settings']['fpts']
            fantasy_team.points_against = roster_data['settings']['fpts_against']

            # Add player details to each fantasy team
            for player_id in roster_data.get('players', []):
                player_details = self.player_loader.get_player(player_id)
                if player_details:
                    player = Player(player_details['first_name'] + " " + player_details['last_name'])
                    # Now, populate the Player object with details from player_details
                    player.nfl_team = player_details.get('team')
                    player.position = player_details.get('position')
                    player.number = player_details.get('number')
                    player.age = player_details.get('age')
                    player.height = player_details.get('height')
                    player.weight = player_details.get('weight')
                    player.college = player_details.get('college')
                    player.years_exp = player_details.get('years_exp')
                    player.draft_year = None  # This information might not be directly available
                    player.depth_chart_position = player_details.get('depth_chart_position')
                    player.status = player_details.get('status')
                    player.sport = player_details.get('sport')
                    player.fantasy_positions = player_details.get('fantasy_positions')
                    player.last_name = player_details.get('last_name')
                    player.fantasy_data_id = player_details.get('fantasy_data_id')
                    player.injury_status = player_details.get('injury_status')
                    player.player_id = player_details.get('player_id')
                    player.birth_country = player_details.get('birth_country')
                    player.search_rank = player_details.get('search_rank')
                    player.first_name = player_details.get('first_name')
                    player.depth_chart_order = player_details.get('depth_chart_order')
                    player.rotowire_id = player_details.get('rotowire_id')
                    player.rotoworld_id = player_details.get('rotoworld_id')

                    # Additional attributes such as 'injury_risk', 'player_potential', etc., would need custom logic
                    # or additional data sources since they are not directly available in the provided player data

                    fantasy_team.players.append(player)

            league.fantasy_teams.append(fantasy_team)


        return league
