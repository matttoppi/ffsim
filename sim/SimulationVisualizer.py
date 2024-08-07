import matplotlib.pyplot as plt
import numpy as np
import os
import shutil

class SimulationVisualizer:
    def __init__(self, league):
        self.league = league
            
    def plot_scoring_distributions(self, tracker):
        positions = ['QB', 'RB', 'WR', 'TE']
        
        # Clear existing plots
        if os.path.exists('plots'):
            shutil.rmtree('plots')
        
        for position in positions:
            top_players = self._get_top_players(tracker, position)
            
            if top_players:
                self._plot_and_save_histograms(top_players, position, tracker)
            else:
                print(f"No data for {position}")

        print("Scoring distribution plots saved.")

    def _get_top_players(self, tracker, position):
        players = [player for team in self.league.rosters for player in team.players if player.position == position]
        
        player_stats = []
        for player in players:
            avg_score, total_scores, games_played, min_score, max_score = tracker.get_player_average_score(player.sleeper_id)
            if games_played > 0:
                player_stats.append((player, avg_score, tracker.player_scores[player.sleeper_id]))
        
        # Sort players by average score and get top 10
        sorted_players = sorted(player_stats, key=lambda x: x[1], reverse=True)[:10]
        
        return sorted_players

    def _plot_and_save_histograms(self, top_players, position, tracker):
        os.makedirs(f'plots/{position}', exist_ok=True)
        
        for player, avg_score, scores_dict in top_players:
            scores = [score for week_scores in scores_dict.values() for score in week_scores if score > 0]
            
            fig, ax = plt.subplots(figsize=(10, 6))
            self._plot_histogram(ax, scores, player.name, avg_score)
            
            plt.tight_layout()
            plt.savefig(f'plots/{position}/{player.name.replace(" ", "_")}.png')
            plt.close(fig)
            print(f"Saved plot for {player.name} ({position})")

    def _plot_histogram(self, ax, scores, player_name, avg_score):
        ax.hist(scores, bins=50, edgecolor='black')
        ax.set_title(f'{player_name} Scoring Distribution')
        ax.set_xlabel('Score')
        ax.set_ylabel('Frequency')
        
        if scores:
            median_score = np.median(scores)
            ax.axvline(avg_score, color='r', linestyle='dashed', linewidth=2, label=f'Avg: {avg_score:.2f}')
            ax.axvline(median_score, color='g', linestyle='dashed', linewidth=2, label=f'Median: {median_score:.2f}')
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No non-zero scores', 
                    horizontalalignment='center', verticalalignment='center')