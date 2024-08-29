import matplotlib.pyplot as plt
import numpy as np
import os
import shutil
from matplotlib.backends.backend_pdf import PdfPages
from math import ceil
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
from PyPDF2 import PdfMerger

from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend



import io
from reportlab.platypus import Image, Table, TableStyle


class SimulationVisualizer:
    def __init__(self, league, tracker):
        self.league = league
        self.tracker = tracker
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'Title',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=12
        )
        self.subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=6
        )

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
            self.create_team_pdf(team)

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
        ax.hist(scores, bins=50, edgecolor='black', color='skyblue')

        total_weeks = len(scores)
        active_weeks = len([score for score in scores if score > 0])

        title = (f'{player_name} Scoring Distribution ({position} Rank: {rank})\n'
                f'Best Season Avg: {best_season_avg:.2f}')
        ax.set_title(title, fontsize=14, fontweight='bold')

        ax.set_xlabel('Score', fontsize=12)
        ax.set_ylabel('Frequency', fontsize=12)

        ax.grid(True, linestyle='--', alpha=0.7)

        if scores:
            mean_score = np.mean(scores)
            median_score = np.median(scores)
            ax.axvline(mean_score, color='red', linestyle='dashed', linewidth=2, label=f'Avg: {mean_score:.2f}')
            ax.axvline(median_score, color='green', linestyle='dashed', linewidth=2, label=f'Median: {median_score:.2f}')
            ax.axvline(best_season_avg, color='blue', linestyle='dashed', linewidth=2, label=f'Best Season Avg: {best_season_avg:.2f}')
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No non-zero scores', 
                    horizontalalignment='center', verticalalignment='center', fontsize=12, fontstyle='italic')



    def create_player_table(self, player_performances):
        data = [
            ["Player", "Position", "Total Points", "Avg Points", "Modifier", "Games Played"]
        ]
        for player in player_performances:
            data.append([
                player['name'],
                player['position'],
                f"{player['total_points']:.2f}",
                f"{player['avg_points']:.2f}",
                f"{player['modifier']:.2f}",
                str(player['games_played'])
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        return table    
    
    
    
    def create_team_pdf(self, team):
        base_filename = f'plots/{team.name.replace(" ", "_")}'
        main_pdf = f'{base_filename}_main.pdf'
        plots_pdf = f'{base_filename}_plots.pdf'
        final_pdf = f'{base_filename}_team_report.pdf'

        # Create main content PDF
        doc = SimpleDocTemplate(main_pdf, pagesize=letter)
        elements = []

        # Add best season breakdown
        elements.extend(self.create_season_breakdown(team, 'best'))
        elements.append(PageBreak())

        # Add worst season breakdown
        elements.extend(self.create_season_breakdown(team, 'worst'))

        doc.build(elements)

        # Create player distribution plots PDF
        self._create_player_distributions(team, plots_pdf)

        # Merge PDFs
        merger = PdfMerger()
        merger.append(main_pdf)
        merger.append(plots_pdf)
        merger.write(final_pdf)
        merger.close()

        # Clean up temporary files
        os.remove(main_pdf)
        os.remove(plots_pdf)

        print(f"Created combined PDF report for {team.name}: {final_pdf}")

    def _create_player_distributions(self, team, filename):
        players = team.players
        players_with_data = [p for p in players if self._get_player_scores(p.sleeper_id)]

        if not players_with_data:
            print(f"No data available for any players on {team.name}. Skipping player distributions.")
            return

        players_with_data.sort(key=lambda p: self._get_player_average_score(p.sleeper_id), reverse=True)

        players_per_page = 6
        total_pages = ceil(len(players_with_data) / players_per_page)

        with PdfPages(filename) as pdf:
            for page in range(total_pages):
                start_idx = page * players_per_page
                end_idx = min((page + 1) * players_per_page, len(players_with_data))
                page_players = players_with_data[start_idx:end_idx]

                fig, axs = plt.subplots(3, 2, figsize=(11, 8.5))  # Letter size, landscape
                fig.suptitle(f"{team.name} - Overall Player Distributions (Page {page + 1}/{total_pages})", fontsize=16)

                for i, player in enumerate(page_players):
                    ax = axs[i // 2, i % 2]
                    self._plot_player_histogram(ax, player)

                # Remove any empty subplots
                for i in range(len(page_players), 6):
                    axs[i // 2, i % 2].axis('off')

                plt.tight_layout(rect=[0, 0.03, 1, 0.95])
                pdf.savefig(fig)
                plt.close(fig)

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
            title = f"{player.name} ({player.position})\nAvg: {mean_score:.2f} | Best: {best_season_avg:.2f}"
        else:
            title = f"{player.name} ({player.position})\nAvg: {mean_score:.2f}"

        ax.set_title(title, fontsize=10)
        ax.set_xlabel('Score', fontsize=8)
        ax.set_ylabel('Frequency', fontsize=8)
        ax.tick_params(axis='both', which='major', labelsize=6)
        ax.legend(fontsize=6)
        ax.set_ylim(bottom=0)

    def _get_player_scores(self, player_id):
        if player_id in self.tracker.player_scores:
            return [score for week_scores in self.tracker.player_scores[player_id].values() for score in week_scores if score > 0]
        return []

    def _get_player_average_score(self, player_id):
        scores = self._get_player_scores(player_id)
        return np.mean(scores) if scores else 0

    

    def create_season_performance_chart(self, breakdown):
        drawing = Drawing(400, 200)
        bc = VerticalBarChart()
        bc.x = 50
        bc.y = 50
        bc.height = 125
        bc.width = 300
        bc.data = [
            [breakdown['points_for']],
            [breakdown['points_against']]
        ]
        bc.categoryAxis.categoryNames = ['Points']
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max(breakdown['points_for'], breakdown['points_against']) * 1.1
        bc.bars[0].fillColor = colors.lightblue
        bc.bars[1].fillColor = colors.lightcoral
        bc.barLabels.nudge = 10
        bc.barLabelFormat = '%.2f'
        bc.barLabels.dy = 0
        bc.barLabels.fontSize = 8
        drawing.add(bc)

        legend = Legend()
        legend.alignment = 'right'
        legend.x = 360
        legend.y = 150
        legend.columnMaximum = 1
        legend.colorNamePairs = [(colors.lightblue, 'Points For'),
                                 (colors.lightcoral, 'Points Against')]
        drawing.add(legend)

        return drawing

    def create_win_loss_pie_chart(self, breakdown):
        drawing = Drawing(400, 200)
        pc = Pie()
        pc.x = 150
        pc.y = 75
        pc.width = 150
        pc.height = 150
        record = breakdown['record'].split('-')
        wins, losses, ties = int(record[0]), int(record[1]), int(record[2])
        pc.data = [wins, losses, ties]
        pc.labels = ['Wins', 'Losses', 'Ties']
        pc.slices.strokeWidth = 0.5
        pc.slices[0].fillColor = colors.green
        pc.slices[1].fillColor = colors.red
        pc.slices[2].fillColor = colors.yellow
        drawing.add(pc)

        legend = Legend()
        legend.alignment = 'right'
        legend.x = 310
        legend.y = 150
        legend.columnMaximum = 1
        legend.colorNamePairs = [(colors.green, f'Wins ({wins})'),
                                 (colors.red, f'Losses ({losses})'),
                                 (colors.yellow, f'Ties ({ties})')]
        drawing.add(legend)

        return drawing

    
    def create_season_breakdown(self, team, season_type):
        if season_type == 'best':
            breakdown = self.tracker.get_best_season_breakdown(team.name)
            title = f"{team.name} - Best Season Breakdown"
        else:
            breakdown = self.tracker.get_worst_season_breakdown(team.name)
            title = f"{team.name} - Worst Season Breakdown"

        elements = []

        # Add title
        elements.append(Paragraph(title, self.title_style))

        # Add season summary
        summary_style = ParagraphStyle('Summary', fontSize=12, spaceAfter=12, alignment=1)
        summary = f"""
        <b>Record:</b> {breakdown['record']}  |  
        <b>Points For:</b> {breakdown['points_for']:.2f}  |  
        <b>Points Against:</b> {breakdown['points_against']:.2f}
        <br/>
        <b>Points per Week:</b> {breakdown['points_for'] / 17:.2f}
        <br/><br/>
        <b>Playoff Result:</b> {breakdown['playoff_result']}
        """
        elements.append(Paragraph(summary, summary_style))

        # Create and add charts
        points_chart = self.create_points_chart(breakdown)
        win_loss_chart = self.create_win_loss_chart(breakdown)

        # Create a table to hold both charts side by side
        chart_table = Table([[points_chart, win_loss_chart]], colWidths=[3*inch, 3*inch])
        chart_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        elements.append(chart_table)
        elements.append(Spacer(1, 0.2 * inch))

        # Create player performance table
        elements.append(Paragraph("Player Performances", self.subtitle_style))
        player_table = self.create_player_table(breakdown['player_performances'])
        elements.append(player_table)

        # Add a note about the season modifier
        elements.append(Spacer(1, 0.2 * inch))
        note = "Note: Season modifier represents player's performance relative to expectations (1.0 is average)"
        elements.append(Paragraph(note, self.styles['Italic']))

        return elements

    def create_points_chart(self, breakdown):
        fig, ax = plt.subplots(figsize=(4, 3))
        categories = ['Points For', 'Points Against']
        values = [breakdown['points_for'], breakdown['points_against']]
        colors = ['lightblue', 'lightcoral']

        ax.bar(categories, values, color=colors)
        ax.set_ylabel('Points')
        ax.set_title('Points Comparison')

        # Add buffer to y-axis
        y_max = max(values) * 1.1  # 10% buffer
        ax.set_ylim(0, y_max)

        # Add value labels with adjusted position
        for i, v in enumerate(values):
            ax.text(i, v, f'{v:.2f}', ha='center', va='bottom', fontweight='bold', fontsize=9)

        # Remove top and right spines
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Add subtle grid lines
        ax.yaxis.grid(True, linestyle='--', alpha=0.7)

        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close(fig)

        return Image(img_buffer, width=3*inch, height=2.25*inch)

    def create_win_loss_chart(self, breakdown):
        fig, ax = plt.subplots(figsize=(4, 3))
        record = breakdown['record'].split('-')
        wins, losses, ties = int(record[0]), int(record[1]), int(record[2])
        
        sizes = [wins, losses]
        labels = ['Wins', 'Losses']
        colors = ['green', 'red']

        ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        ax.set_title('Win/Loss Distribution')

        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        plt.close(fig)

        return Image(img_buffer, width=3*inch, height=2.25*inch)