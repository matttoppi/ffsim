import random
import math

class FantasyTeam:

    def __init__(self, name, league, user_data=None):
        attributes = [
            'user_id', 'settings', 'metadata', 'league_id', 'is_owner', 'is_bot', 'display_name', 'avatar', 'archived', 'allow_sms', 'allow_pn'
        ]
        
        self.name = name
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.fantasy_pts_total = 0
        self.fantasy_pts_per_game = 0
        self.points_for = 0
        self.points_against = 0
        self.streak = 0
        self.total_value_1qb = 0
        self.total_value_2qb = 0
        self.average_value_1qb = 0
        self.average_value_2qb = 0
        self.average_age = 0
        self.total_age = 0
        self.league = league
        self.roster_id = None
        self.simulation = None  # We'll initialize this after adding players
        self.players = set()  # Use a set instead of a list for faster lookups
        self.player_sleeper_ids = set()
        
        self.starters = {
            'QB': [], 'RB': [], 'WR': [], 'TE': [], 'FLEX': [], 'K': [], 'DEF': []
        }
        self.bench = []
        
        self.sim_injured_players = []
        self.weekly_scores = {}
        self.available_players = [p for p in self.players if not p.is_injured(week) or p.is_partially_injured(week)]
        
        self.playoff_result = None  # Add this line
        
        self.owner_username = user_data.get("display_name")
        if self.name == "Unknown":
            self.name = self.owner_username
            
        self.weekly_team_scores = {}
        
        for key, value in user_data.items():
            if key in attributes:
                setattr(self, key, value)    
                
        self.calculate_metadata()

    def add_player(self, player):
        self.players.add(player)
        self.player_sleeper_ids.add(player.sleeper_id)
        
        
    def create_season_modifiers(self):
        for player in self.players:
            player.create_players_season_modifiers()
            

    def print_fantasy_team(self):     
        print("\n")   
        print(f"Name: {self.name}")
        print(f"Owner: {self.owner_username}")
        print(f"Total Value 1QB: {self.total_value_1qb}")
        
    def print_fantasy_team_short(self):
        print(f"|{self.owner_username:<16} | Value 1QB: {self.total_value_1qb:<8.2f} |")
        


    def calculate_metadata(self):
        if len(self.players) <= 0:
            return
        self.total_value_1qb = round(sum(player.value_1qb for player in self.players if player.value_1qb is not None), 2)
        # self.total_value_2qb = round(sum(player.value_2qb for player in self.players if player.value_2qb is not None), 2)
        self.average_value_1qb = round(self.total_value_1qb / len(self.players), 2)
        # self.average_value_2qb = round(self.total_value_2qb / len(self.players), 2)
        self.total_age = sum(player.age for player in self.players if player.age is not None)
        self.average_age = round(self.total_age / len(self.players), 2) if self.total_age else 0
        

    def update_record(self, won, tied, points_against, points_for, week):
        if won:
            self.wins += 1
        elif tied:
            self.ties += 1
        else:
            self.losses += 1
        self.points_against += points_against
        self.points_for += points_for
        self.weekly_scores[week] = points_for


    def get_weekly_score(self, week):
        return self.weekly_scores.get(week, 0)

    def set_weekly_score(self, week, score):
        self.weekly_scores[week] = score
        self.points_for += score

    def update_injury_status(self, week):
        recovered_players = [p for p in self.sim_injured_players if not p.is_injured(week)]
        for player in recovered_players:
            print(f"{player.name} has recovered from injury and is available to play.")
            self.sim_injured_players.remove(player)

    def simulate_player_week(self, player, week, scoring_settings):
        print(f"Simulating week {week} for {player.name}")
        base_score = player.calculate_score(scoring_settings)
        
        # Check for new injury
        if random.random() < player.injury_probability_game:
            injury_duration = max(0.5, random.gauss(player.projected_games_missed, 1))
            player.simulation_injury = {
                'start_week': week,
                'duration': injury_duration,
                'return_week': week + math.ceil(injury_duration)
            }
            # print(f"New injury for {player.name} on {self.name} for {injury_duration:.2f} weeks")
            self.sim_injured_players.append(player)
            print(f"New injury for {player.name} on {self.name} for {injury_duration:.2f} weeks")
                
                
            # Adjust score based on when injury occurred during the game
            injury_time = random.random()
            adjusted_score = base_score * injury_time
            return adjusted_score
        
        print(f"{player.name} scored {base_score} in week {week}")
        
        return base_score

    def manage_injuries(self, week):
        recovered_players = []
        for player in self.players:
            if player.update_injury_status(week):
                recovered_players.append(player)
        
        for player in recovered_players:
            if player in self.sim_injured_players:
                self.sim_injured_players.remove(player)
                


    
    def print_roster(self):
        
        print("Starters:")
        for pos, players in self.starters.items():
            for player in players:
                print(f"{pos}: {player.name} (Redraft Value: {player.redraft_value})")
        print("\nBench:")
        for player in self.bench:
            print(f"{player.name} (Redraft Value: {player.redraft_value})")
        print("\nInjured:")
        for player in self.sim_injured_players:
            print(f"{player.name} (Redraft Value: {player.redraft_value}) - Injured for {player.simulation_injury['duration']:.2f} more weeks. Return week: {player.simulation_injury['return_week']}")
        print("\n")
        
    def fill_starters(self, week):
        self.manage_injuries(week)

        slots = {
            'QB': 1, 'RB': 3, 'WR': 3, 'TE': 1, 'FLEX': 3, 'K': 1, 'DEF': 1
        }
        flex_eligible = ['RB', 'WR', 'TE']

        self.starters = {pos: [] for pos in slots.keys()}

        def is_player_available(player):
            is_not_injured = not player.is_injured(week)
            is_not_on_bye = not hasattr(player, 'pff_projections') or \
                            player.pff_projections is None or \
                            not hasattr(player.pff_projections, 'bye_week') or \
                            player.pff_projections.bye_week is None or \
                            int(player.pff_projections.bye_week) != week
            return is_not_injured and is_not_on_bye

        # Get all available players
        available_players = [p for p in self.players if is_player_available(p)]

        # Sort players once before filling positions
        if week > 3:
            sorted_players = sorted(available_players, key=lambda p: sum(p.weekly_scores.values()), reverse=True)
        else:
            sorted_players = sorted(available_players, key=lambda p: p.redraft_value if hasattr(p, 'redraft_value') else 0, reverse=True)

        for pos in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            position_players = [p for p in sorted_players if p.position == pos]
            self.starters[pos] = position_players[:slots[pos]]
            sorted_players = [p for p in sorted_players if p not in self.starters[pos]]

        # Fill FLEX positions
        flex_players = [p for p in sorted_players if p.position in flex_eligible]
        self.starters['FLEX'] = flex_players[:slots['FLEX']]

        # Set bench players
        self.bench = [p for p in self.players if p not in [player for pos_list in self.starters.values() for player in pos_list]]

        # Update injured players list
        self.sim_injured_players = [p for p in self.players if p.is_injured(week)]

        # Uncomment the following line if you want to print team status after filling starters
        # self.print_team_status(week)

        # Print team status
        # self.print_team_status(week)

    def print_team_status(self, week):
        # Print starting lineup with redraft values or total points
        print(f"\nStarting lineup for week {week}:")
        for pos, players in self.starters.items():
            if week > 3:
                print(f"{pos}: {', '.join([f'{p.name} (Total Pts: {sum(p.weekly_scores.values()):.2f})' if p else 'Empty' for p in players])}")
            else:
                print(f"{pos}: {', '.join([f'{p.name} (RV: {p.redraft_value:.2f})' if p else 'Empty' for p in players])}")

        # Print bench with redraft values or total points and check for higher values
        print("\nBench:")
        for player in self.bench:
            if week > 3:
                print(f"{player.name} ({player.position}) - Total Pts: {sum(player.weekly_scores.values()):.2f}")
            else:
                print(f"{player.name} ({player.position}) - RV: {player.redraft_value:.2f}")
            if not self.is_player_available(player, week):
                continue
            # Check if bench player has higher value than starters in their position
            self.check_bench_player_value(player, week)

        # Print injured players
        print("\nInjured players:")
        for player in self.sim_injured_players:
            if week > 3:
                print(f"{player.name} ({player.position}) - Total Pts: {sum(player.weekly_scores.values()):.2f} - Injured for {player.simulation_injury['duration']:.2f} more weeks. Return week: {player.simulation_injury['return_week']}")
            else:
                print(f"{player.name} ({player.position}) - RV: {player.redraft_value:.2f} - Injured for {player.simulation_injury['duration']:.2f} more weeks. Return week: {player.simulation_injury['return_week']}")

        # Print players on bye
        print("\nPlayers on bye:")
        for player in self.players:
            if hasattr(player, 'pff_projections') and player.pff_projections is not None and \
            hasattr(player.pff_projections, 'bye_week') and player.pff_projections.bye_week is not None and \
            int(player.pff_projections.bye_week) == week:
                if week > 3:
                    print(f"{player.name} ({player.position}) - Total Pts: {sum(player.weekly_scores.values()):.2f}")
                else:
                    print(f"{player.name} ({player.position}) - RV: {player.redraft_value:.2f}")

        print("\n")

    def is_player_available(self, player, week):
        is_not_injured = not player.is_injured(week)
        is_not_on_bye = not hasattr(player, 'pff_projections') or \
                        player.pff_projections is None or \
                        not hasattr(player.pff_projections, 'bye_week') or \
                        player.pff_projections.bye_week is None or \
                        int(player.pff_projections.bye_week) != week
        return is_not_injured and is_not_on_bye

    def check_bench_player_value(self, player, week):
        if player.position in self.starters:
            for starter in self.starters[player.position]:
                if week > 3:
                    if sum(player.weekly_scores.values()) > sum(starter.weekly_scores.values()):
                        print(f"WARNING: Bench player {player.name} has higher total points than starter {starter.name} at {player.position}")
                else:
                    if player.redraft_value > starter.redraft_value:
                        print(f"WARNING: Bench player {player.name} has higher redraft value than starter {starter.name} at {player.position}")
        elif player.position in ['RB', 'WR', 'TE']:
            for flex_starter in self.starters['FLEX']:
                if week > 3:
                    if sum(player.weekly_scores.values()) > sum(flex_starter.weekly_scores.values()):
                        print(f"WARNING: Bench player {player.name} has higher total points than FLEX starter {flex_starter.name}")
                else:
                    if player.redraft_value > flex_starter.redraft_value:
                        print(f"WARNING: Bench player {player.name} has higher redraft value than FLEX starter {flex_starter.name}")
        
    def calculate_player_score(self, player, week, scoring_settings):
        if player.is_injured(week):
            return 0
        elif player.is_partially_injured(week):
            base_score = player.calculate_score(scoring_settings, week)
            return base_score * player.simulation_injury['partial_week_factor']
        else:
            return player.calculate_score(scoring_settings, week)

    def get_active_starters(self, week):
        return [player for position, players in self.starters.items() 
                for player in players 
                if player is not None and (not player.is_injured(week) or player.is_partially_injured(week))]
    
    
    def reset_season_stats(self):
        """Reset season statistics for the team and all its players."""
        self.weekly_team_scores = {}
        for player in self.players:
            player.reset_season_stats()    
    
    def reset_stats(self):
        """Reset all stats for the team and its players."""
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.points_for = 0
        self.points_against = 0
        self.weekly_scores = {}
        for player in self.players:
            player.reset_season_stats()

    def record_weekly_score(self, week, score):
        """Record the team's weekly score."""
        self.weekly_scores[week] = score
        self.points_for += score

    def get_average_weekly_score(self):
        """Get the team's average weekly score for the season."""
        if len(self.weekly_scores) > 0:
            return sum(self.weekly_scores.values()) / len(self.weekly_scores)
        return 0

    def get_player_average_scores(self):
        """Get a dictionary of average weekly scores for all players."""
        return {player.name: player.get_average_weekly_score() for player in self.players}

    def get_top_performers(self, n=5):
        """Get the top n performing players based on average weekly score."""
        sorted_players = sorted(self.players, key=lambda p: p.get_average_weekly_score(), reverse=True)
        return sorted_players[:n]

    def print_team_stats(self):
        """Print team and player statistics."""
        print(f"\n{self.name} Team Stats:")
        print(f"Record: {self.wins}-{self.losses}-{self.ties}")
        print(f"Points For: {self.points_for:.2f}")
        print(f"Points Against: {self.points_against:.2f}")
        print(f"Average Weekly Score: {self.get_average_weekly_score():.2f}")
        print("\nTop Performers:")
        for player in self.get_top_performers():
            print(f"{player.name}: {player.get_average_weekly_score():.2f}")

    def simulate_week(self, week, scoring_settings):
        """Simulate a week for the team."""
        total_score = 0
        for player in self.get_active_starters(week):
            score = player.calculate_score(scoring_settings, week)
            total_score += score
        self.record_weekly_score(week, total_score)
        return total_score