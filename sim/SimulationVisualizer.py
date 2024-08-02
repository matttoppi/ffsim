import matplotlib.pyplot as plt
import numpy as np

class SimulationVisualizer:
    def __init__(self, league):
        self.league = league
            
    def plot_scoring_distributions(self, tracker):
        positions = ['QB', 'RB', 'WR', 'TE']
        fig, axs = plt.subplots(2, 2, figsize=(15, 15))
        fig.suptitle('Scoring Distributions by Position (Excluding Non-Playing Weeks)')

        for idx, position in enumerate(positions):
            row = idx // 2
            col = idx % 2
            
            all_scores = self._get_all_scores_for_position(tracker, position)
            
            if all_scores:
                self._plot_histogram(axs[row, col], all_scores, position)
            else:
                axs[row, col].text(0.5, 0.5, f'No data for {position}', 
                                   horizontalalignment='center', verticalalignment='center')

        plt.tight_layout()
        plt.savefig('scoring_distributions.png')
        print("Scoring distribution plot saved as 'scoring_distributions.png'")

    def _get_all_scores_for_position(self, tracker, position):
        all_scores = []
        for team in self.league.rosters:
            for player in team.players:
                if player.position == position:
                    player_stats = tracker.get_player_stats(player.sleeper_id)
                    if player_stats and 'all_scores' in player_stats:
                        all_scores.extend([score for score in player_stats['all_scores'] if score > 0])
        return all_scores

    def _plot_histogram(self, ax, scores, position):
        ax.hist(scores, bins=50, edgecolor='black')
        ax.set_title(f'{position} Scoring Distribution')
        ax.set_xlabel('Score')
        ax.set_ylabel('Frequency')
        
        if scores:
            mean_score = np.mean(scores)
            median_score = np.median(scores)
            ax.axvline(mean_score, color='r', linestyle='dashed', linewidth=2, label=f'Mean: {mean_score:.2f}')
            ax.axvline(median_score, color='g', linestyle='dashed', linewidth=2, label=f'Median: {median_score:.2f}')
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No non-zero scores', 
                    horizontalalignment='center', verticalalignment='center')
            