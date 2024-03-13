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
            fantasy_team = FantasyTeam(str(roster_data['owner_id']))

            fantasy_team.wins = roster_data['settings']['wins']
            fantasy_team.losses = roster_data['settings']['losses']
            fantasy_team.ties = roster_data['settings']['ties']
            fantasy_team.fantasy_pts_total = roster_data['settings']['fpts']
            fantasy_team.points_for = roster_data['settings']['fpts']
            fantasy_team.points_against = roster_data['settings']['fpts_against']

            for player_id in roster_data.get('players', []):
                player_details = self.player_loader.get_player(player_id)
                if player_details:
                    player = Player(player_details['first_name'] + " " + player_details['last_name'])
                    # Map Sleeper API and CSV data to Player attributes
                    for attr in ['nfl_team', 'position', 'age', 'draft_year', 'ecr_1qb', 'ecr_2qb', 'ecr_pos',
                                'value_1qb', 'value_2qb', 'scrape_date', 'fp_id', 'mfl_id', 'sportradar_id',
                                'fantasypros_id', 'gsis_id', 'pff_id', 'sleeper_id', 'nfl_id', 'espn_id',
                                'yahoo_id', 'fleaflicker_id', 'cbs_id', 'pfr_id', 'cfbref_id', 'rotowire_id',
                                'rotoworld_id', 'ktc_id', 'stats_id', 'stats_global_id', 'fantasy_data_id',
                                'swish_id', 'merge_name', 'team', 'birthdate', 'draft_round', 'draft_pick',
                                'draft_ovr', 'twitter_username', 'height', 'weight', 'college', 'db_season',
                                'number', 'depth_chart_position', 'status', 'sport', 'fantasy_positions',
                                'search_last_name', 'injury_start_date', 'practice_participation', 'last_name',
                                'search_full_name', 'birth_country', 'search_rank', 'first_name', 'depth_chart_order',
                                'search_first_name']:
                        setattr(player, attr, player_details.get(attr))

                    fantasy_team.players.append(player)

            league.fantasy_teams.append(fantasy_team)

        return league
