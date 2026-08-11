import matplotlib.pyplot as plt
import numpy as np
import shutil

from ffsim.paths import OUTPUT_DIR


PLOTS_DIR = OUTPUT_DIR / "plots"

class SimulationVisualizer:
    def __init__(self, league, tracker):
        self.league = league
        self.tracker = tracker
            
    def plot_scoring_distributions(self):
        if not self.tracker.keep_samples:
            raise ValueError("Scoring distribution plots require keep_samples=True")
        positions = ['QB', 'RB', 'WR', 'TE']
        
        if PLOTS_DIR.exists():
            shutil.rmtree(PLOTS_DIR)
        
        for position in positions:
            top_players = self._get_top_players(position)
            
            if top_players:
                self._plot_and_save_histograms(top_players, position)
            else:
                print(f"No data for {position}")

        print("Scoring distribution plots saved.")

    def _get_top_players(self, position):
        players = [player for team in self.league.rosters for player in team.players if player.position == position]
        
        player_stats = []
        for player in players:
            avg_score, total_scores, games_played, min_score, max_score = self.tracker.get_player_average_score(player.sleeper_id)
            if games_played > 0:
                player_stats.append((player, avg_score, self.tracker.player_scores[player.sleeper_id]))
        
        return sorted(player_stats, key=lambda x: x[1], reverse=True)[:15]

    def _plot_and_save_histograms(self, top_players, position):
        position_dir = PLOTS_DIR / position
        position_dir.mkdir(parents=True, exist_ok=True)
        
        for rank, (player, _, scores_dict) in enumerate(top_players, 1):
            scores = [score for week_scores in scores_dict.values() for score in week_scores]
            fig, ax = plt.subplots(figsize=(10, 6))
            self._plot_histogram(ax, scores, player.name, rank, position)
            plt.tight_layout()
            plt.savefig(position_dir / f'{player.name.replace(" ", "_")}.png')
            plt.close(fig)
            print(f"Saved plot for {player.name} ({position})")

    def _plot_histogram(self, ax, scores, player_name, rank, position):
        ax.hist(scores, bins=50, edgecolor='black')
        
        title = (f'{player_name} Scoring Distribution ({position}{rank})')
        
        ax.set_title(title)
        ax.set_xlabel('Score')
        ax.set_ylabel('Frequency')
        
        if scores:
            mean_score = np.mean(scores)
            median_score = np.median(scores)
            ax.axvline(mean_score, color='r', linestyle='dashed', linewidth=2, label=f'Avg: {mean_score:.2f}')
            ax.axvline(median_score, color='g', linestyle='dashed', linewidth=2, label=f'Median: {median_score:.2f}')
            ax.legend()
        else:
                ax.text(0.5, 0.5, 'No scores',
                    horizontalalignment='center', verticalalignment='center')
