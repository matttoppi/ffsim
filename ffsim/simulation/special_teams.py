import csv
import random

class SpecialTeamScorer:
    def __init__(self, kickers_file, dsts_file):
        self.kickers = self.load_kicker_data(kickers_file)
        self.dsts = self.load_dst_data(dsts_file)

    def load_dst_data(self, file_path):
        data = {}
        with open(file_path, 'r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                team_name = row['teamName']
                full_name = row['playerName']
                data[team_name] = {
                    'rank': int(row['fantasyPointsRank']),
                    'full_name': full_name,
                    'fantasy_points': float(row['fantasyPoints'])
                }
        return data
    def load_kicker_data(self, file_path):
        data = {}
        with open(file_path, 'r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                name = row['playerName']
                data[name] = {
                    'rank': int(row['fantasyPointsRank']),
                    'team': row['teamName'],
                    'fantasy_points': float(row['fantasyPoints'])
                }
        return data


    def generate_score_based_on_rank(self, rank, fantasy_points, position):
        if position.lower() == 'k':
            base_mean = 11
            base_std_dev = 1.5
            rank_factor = 0.1
            points_factor = 0.1
        elif position.lower() in ['dst', 'def']:
            base_mean = 6
            base_std_dev = 4
            rank_factor = 0.2
            points_factor = 0.15
        else:
            raise ValueError(f"Invalid position: {position}")

        # Adjust mean based on rank and fantasy points
        rank_adjustment = (32 - rank) * rank_factor
        points_adjustment = (fantasy_points / 50) * points_factor
        adjusted_mean = base_mean + rank_adjustment + points_adjustment

        # Adjust standard deviation based on rank
        rank_ratio = rank / 32
        adjusted_std_dev = base_std_dev * (0.5 + (rank_ratio / 2))

        # Generate score using normal distribution
        score = max(0, random.gauss(adjusted_mean, adjusted_std_dev))
        
        # Add occasional boom/bust performances
        if random.random() < 0.1:
            score *= random.uniform(1.5, 2.0) if random.random() < 0.5 else random.uniform(0.5, 0.75)
        
        if score > 35:
            score = 35 + (score - 35) * 0.5
        
        # Introduce more variability based on rank, especially for defenses
        if position.lower() in ['dst', 'def']:
            rank_variability = (32 - rank) * 0.1  # Increased factor for defenses
            score += random.uniform(-rank_variability, rank_variability)
        
            # Add a rank-based adjustment to ensure higher-ranked defenses tend to score higher
            rank_bonus = (32 - rank) * 0.05
            score += rank_bonus
        
            # Add a small random adjustment to further differentiate scores
            small_adjustment = random.uniform(-0.5, 0.5)
            score += small_adjustment
        else:
            # For kickers, keep the original logic
            rank_variability = (32 - rank) * 0.05
            score += random.uniform(-rank_variability, rank_variability)
        
        return round(score, 2)

    def get_player_score(self, player_name, position, team=None):
        if position.lower() == 'k':
            data = self.kickers
            player_data = data.get(player_name)
        elif position.lower() in ['dst', 'def']:
            data = self.dsts
            player_data = data.get(team)
        else:
            raise ValueError(f"Position must be 'K' or 'DST', got {position}")

        if player_data is None:
            return self.generate_score_based_on_rank(16, 100, position)

        rank = player_data['rank']
        fantasy_points = player_data['fantasy_points']
        return self.generate_score_based_on_rank(rank, fantasy_points, position)
