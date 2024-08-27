import matplotlib.pyplot as plt
import numpy as np
import os
import shutil
from matplotlib.backends.backend_pdf import PdfPages
from math import ceil

class SimulationVisualizer:
    def __init__(self, league, tracker):
        self.league = league
        self.tracker = tracker

    def plot_scoring_distributions(self, tracker):
        positions = ['QB', 'RB', 'WR', 'TE']
        
        # Clear existing plots
        if os.path.exists('plots'):
            shutil.rmtree('plots')
        os.makedirs('plots', exist_ok=True)
        
        # Plot top players per position
        for position in positions:
            top_players = self._get_top_players(position)
            
            if top_players:
                self._plot_and_save_histograms(top_players, position)
            else:
                print(f"No data for {position}")

        # Create team-specific PDFs
        for team in self.league.rosters:
            self._create_team_pdf(team)

        print("Scoring distribution plots and team PDF files saved.")

    def _get_top_players(self, position):
        players = [player for team in self.league.rosters for player in team.players if player.position == position]
        
        player_stats = []
        for player in players:
            avg_score, total_scores, games_played, min_score, max_score = self.tracker.get_player_average_score(player.sleeper_id)
            best_season_avg = self.tracker.get_player_best_season_average(player.sleeper_id)
            if games_played > 0:
                player_stats.append((player, avg_score, self.tracker.player_scores[player.sleeper_id], best_season_avg))
        
        # Sort players by average score and get top 10
        sorted_players = sorted(player_stats, key=lambda x: x[1], reverse=True)[:10]
        
        return sorted_players

    def _plot_and_save_histograms(self, top_players, position):
        os.makedirs(f'plots/{position}', exist_ok=True)
        
        for player, avg_score, scores_dict, best_season_avg in top_players:
            scores = [score for week_scores in scores_dict.values() for score in week_scores if score > 0]
            
            fig, ax = plt.subplots(figsize=(10, 6))
            
            rank = top_players.index((player, avg_score, scores_dict, best_season_avg)) + 1
            
            self._plot_histogram(ax, scores, player.name, avg_score, rank, position, best_season_avg)
            
            plt.tight_layout()
            plt.savefig(f'plots/{position}/{player.name.replace(" ", "_")}.png')
            plt.close(fig)
            print(f"Saved plot for {player.name} ({position})")

    def _plot_histogram(self, ax, scores, player_name, avg_score, rank, position, best_season_avg):
        ax.hist(scores, bins=50, edgecolor='black')
        
        total_weeks = 18 * self.tracker.num_simulations
        active_weeks = len(scores)
        bye_weeks = self.tracker.num_simulations  # Assuming 1 bye week per season
        missed_weeks = total_weeks - active_weeks - bye_weeks
        
        avg_games_played = active_weeks / self.tracker.num_simulations
        avg_games_missed = missed_weeks / self.tracker.num_simulations
        
        title = (f'{player_name} Scoring Distribution ({position}{rank})\n'
                 f'Best Season Avg: {best_season_avg:.2f}')
        
        ax.set_title(title)
        ax.set_xlabel('Score')
        ax.set_ylabel('Frequency')
        
        if scores:
            mean_score = np.mean(scores)
            median_score = np.median(scores)
            ax.axvline(mean_score, color='r', linestyle='dashed', linewidth=2, label=f'Avg: {mean_score:.2f}')
            ax.axvline(median_score, color='g', linestyle='dashed', linewidth=2, label=f'Median: {median_score:.2f}')
            ax.axvline(best_season_avg, color='b', linestyle='dashed', linewidth=2, label=f'Best Season Avg: {best_season_avg:.2f}')
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No non-zero scores', 
                    horizontalalignment='center', verticalalignment='center')

    def _create_team_pdf(self, team):
        pdf_filename = f'plots/{team.name.replace(" ", "_")}_player_distributions.pdf'
        with PdfPages(pdf_filename) as pdf:
            players = team.players
            players_with_data = [p for p in players if self._get_player_scores(p.sleeper_id)]
            
            if not players_with_data:
                print(f"No data available for any players on {team.name}. Skipping PDF creation.")
                return

            # Sort players based on their average score (highest to lowest)
            players_with_data.sort(key=lambda p: self._get_player_average_score(p.sleeper_id), reverse=True)

            players_per_page = 6
            total_pages = ceil(len(players_with_data) / players_per_page)

            for page in range(total_pages):
                fig = plt.figure(figsize=(11, 8.5))  # US Letter size
                plt.suptitle(f"{team.name} - Player Distributions (Page {page + 1}/{total_pages})", fontsize=16)

                start_idx = page * players_per_page
                end_idx = min((page + 1) * players_per_page, len(players_with_data))
                page_players = players_with_data[start_idx:end_idx]

                for i, player in enumerate(page_players):
                    ax = fig.add_subplot(3, 2, i + 1)
                    self._plot_player_histogram(ax, player)

                # Remove any empty subplots
                for i in range(len(page_players), players_per_page):
                    if i < len(fig.axes):
                        fig.delaxes(fig.axes[i])

                plt.tight_layout(rect=[0, 0.03, 1, 0.95])
                pdf.savefig(fig)
                plt.close(fig)

        print(f"Created PDF for {team.name}: {pdf_filename}")

    def _get_player_average_score(self, player_id):
        scores = self._get_player_scores(player_id)
        return np.mean(scores) if scores else 0

    def _plot_player_histogram(self, ax, player):
        scores = self._get_player_scores(player.sleeper_id)
        
        ax.hist(scores, bins=35, edgecolor='black')
        mean_score = np.mean(scores)
        median_score = np.median(scores)
        ax.axvline(mean_score, color='r', linestyle='dashed', linewidth=1, label=f'Avg: {mean_score:.1f}')
        ax.axvline(median_score, color='g', linestyle='dashed', linewidth=1, label=f'Med: {median_score:.1f}')
        
        if player.position != 'DEF':
            best_season_avg = self.tracker.get_player_best_season_average(player.sleeper_id)
            ax.axvline(best_season_avg, color='b', linestyle='dashed', linewidth=1, label=f'Best: {best_season_avg:.1f}')
            title = f"{player.name} ({player.position})\nAvg: {mean_score:.2f} | Best Season: {best_season_avg:.2f}"
        else:
            title = f"{player.name} ({player.position})\nAvg: {mean_score:.2f}"
        
        ax.set_title(title, fontsize=10)
        ax.set_xlabel('Score', fontsize=8)
        ax.set_ylabel('Frequency', fontsize=8)
        ax.tick_params(axis='both', which='major', labelsize=6)
        ax.legend(fontsize=6)
        ax.set_ylim(bottom=0)  # Ensure y-axis starts at 0

    def _get_player_scores(self, player_id):
        if player_id in self.tracker.player_scores:
            return [score for week_scores in self.tracker.player_scores[player_id].values() for score in week_scores if score > 0]
        return []