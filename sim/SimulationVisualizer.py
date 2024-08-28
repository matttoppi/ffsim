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

        total_weeks = len(scores)
        active_weeks = len([score for score in scores if score > 0])

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

    # def _create_team_pdf(self, team):
    #     pdf_filename = f'plots/{team.name.replace(" ", "_")}_player_distributions.pdf'
    #     with PdfPages(pdf_filename) as pdf:
    #         players = team.players
    #         players_with_data = [p for p in players if self._get_player_scores(p.sleeper_id)]
            
    #         if not players_with_data:
    #             print(f"No data available for any players on {team.name}. Skipping PDF creation.")
    #             return

    #         # Sort players based on their average score (highest to lowest)
    #         players_with_data.sort(key=lambda p: self._get_player_average_score(p.sleeper_id), reverse=True)

    #         players_per_page = 6
    #         total_pages = ceil(len(players_with_data) / players_per_page)

    #         for page in range(total_pages):
    #             fig = plt.figure(figsize=(11, 8.5))  # US Letter size
    #             plt.suptitle(f"{team.name} - Player Distributions (Page {page + 1}/{total_pages})", fontsize=16)

    #             start_idx = page * players_per_page
    #             end_idx = min((page + 1) * players_per_page, len(players_with_data))
    #             page_players = players_with_data[start_idx:end_idx]

    #             for i, player in enumerate(page_players):
    #                 ax = fig.add_subplot(3, 2, i + 1)
    #                 self._plot_player_histogram(ax, player)

    #             # Remove any empty subplots
    #             for i in range(len(page_players), players_per_page):
    #                 if i < len(fig.axes):
    #                     fig.delaxes(fig.axes[i])

    #             plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    #             pdf.savefig(fig)
    #             plt.close(fig)

    #     print(f"Created PDF for {team.name}: {pdf_filename}")
    

        
        
    def _add_team_overview_pages(self, pdf, team):
        # Page 1: Team Summary
        fig, ax = plt.subplots(figsize=(11, 8.5))
        self._create_team_summary(ax, team)
        pdf.savefig(fig)
        plt.close(fig)

        # Page 2: Best Season Breakdown
        fig, ax = plt.subplots(figsize=(11, 8.5))
        self._create_season_breakdown(ax, team, 'best')
        pdf.savefig(fig)
        plt.close(fig)

        # Page 3: Worst Season Breakdown
        fig, ax = plt.subplots(figsize=(11, 8.5))
        self._create_season_breakdown(ax, team, 'worst')
        pdf.savefig(fig)
        plt.close(fig)
        
        
 
        
        
    

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
    
    
    def _add_player_distribution_plots(self, pdf, team):
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
            
            
            
            
            
    def _create_team_summary(self, fig, team):
        fig.suptitle(f"{team.name} - Team Summary", fontsize=16, fontweight='bold')

        team_stats = self.tracker.get_team_stats(team.name)
        if team_stats:
            summary_text = (
                f"Average Wins: {team_stats['avg_wins']:.2f}\n"
                f"Average Points: {team_stats['avg_points']:.2f}\n"
                f"Playoff Appearances: {self.tracker.playoff_appearances[team.name]}\n"
                f"Championships: {self.tracker.championships[team.name]}"
            )
            fig.text(0.1, 0.7, summary_text, fontsize=12)

        # Win distribution chart
        ax = fig.add_subplot(111)
        wins = [season['wins'] for season in self.tracker.team_season_results[team.name]]
        ax.hist(wins, bins=range(min(wins), max(wins) + 2, 1), alpha=0.7, rwidth=0.8, color='skyblue', edgecolor='black')
        ax.set_xlabel('Wins')
        ax.set_ylabel('Frequency')
        ax.set_title('Win Distribution')
        ax.grid(axis='y', linestyle='--', alpha=0.7)

        # Adjust layout to prevent overlapping
        fig.tight_layout(rect=[0, 0, 1, 0.9])

    def _create_season_breakdown(self, fig, team, season_type):
        if season_type == 'best':
            breakdown = self.tracker.get_best_season_breakdown(team.name)
            title = f"{team.name} - Best Season Breakdown"
        else:
            breakdown = self.tracker.get_worst_season_breakdown(team.name)
            title = f"{team.name} - Worst Season Breakdown"

        fig.suptitle(title, fontsize=16, fontweight='bold')

        if breakdown:
            season_text = (
                f"Record: {breakdown['record']}\n"
                f"Points For: {breakdown['points_for']:.2f}\n"
                f"Points Against: {breakdown['points_against']:.2f}\n"
                f"Playoff Result: {breakdown['playoff_result']}"
            )
            fig.text(0.1, 0.8, season_text, fontsize=12)

            # Player performances table
            ax = fig.add_subplot(111)
            ax.axis('off')
            table_data = [['Player', 'Position', 'Total Points', 'Avg Points', 'Modifier']]
            for player in breakdown['player_performances'][:10]:  # Top 10 performers
                table_data.append([
                    player['name'],
                    player['position'],
                    f"{player['total_points']:.2f}",
                    f"{player['avg_points']:.2f}",
                    f"{player['modifier']:.2f}"
                ])

            table = ax.table(cellText=table_data, loc='center', cellLoc='center', colWidths=[0.3, 0.1, 0.2, 0.2, 0.2])
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 1.5)
            
            # Add a footnote about the season modifier
            fig.text(0.1, 0.05, "Note: Season modifier represents player's performance relative to expectations (1.0 is average)", 
                     fontsize=8, fontstyle='italic')

        fig.tight_layout(rect=[0, 0, 1, 0.95])

    def _create_team_pdf(self, team):
        pdf_filename = f'plots/{team.name.replace(" ", "_")}_team_report.pdf'
        with PdfPages(pdf_filename) as pdf:
            # Team Summary
            fig = plt.figure(figsize=(11, 8.5))
            self._create_team_summary(fig, team)
            pdf.savefig(fig)
            plt.close(fig)

            # Best Season Breakdown
            fig = plt.figure(figsize=(11, 8.5))
            self._create_season_breakdown(fig, team, 'best')
            pdf.savefig(fig)
            plt.close(fig)

            # Worst Season Breakdown
            fig = plt.figure(figsize=(11, 8.5))
            self._create_season_breakdown(fig, team, 'worst')
            pdf.savefig(fig)
            plt.close(fig)

            # Add player distribution plots (existing functionality)
            self._add_player_distribution_plots(pdf, team)

        print(f"Created PDF for {team.name}: {pdf_filename}")
