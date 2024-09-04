from functools import lru_cache
import math
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
import multiprocessing as mp

import matplotlib.pyplot as plt
import io
from reportlab.lib.utils import ImageReader
from tqdm import tqdm

from reportlab.pdfbase.pdfmetrics import stringWidth

import logging




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
            fontSize=15,
            spaceAfter=5
        )
        self.subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=self.styles['Heading2'],
            fontSize=13,
            spaceAfter=4
        )
        
        self.subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=self.styles['Heading3'],
        fontSize=8,  # Reduced from 10
        spaceAfter=1  # Reduced from 2
    )
        self.pdf_base_dir = 'pdf_reports'
        self.positions_dir = os.path.join(self.pdf_base_dir, 'positions')
        self.teams_dir = os.path.join(self.pdf_base_dir, 'teams')
        self.cache = {}
        
        
        os.makedirs(self.positions_dir, exist_ok=True)
        os.makedirs(self.teams_dir, exist_ok=True)

        # Delete existing files in the directories
        for directory in [self.positions_dir, self.teams_dir]:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")

        
    def plot_scoring_distributions(self, tracker):
        positions = ['QB', 'RB', 'WR', 'TE']

        # Plot top players per position
        for position in positions:
            top_players = self._get_top_players(position)

            if top_players:
                self._plot_and_save_histograms(top_players, position)
            else:
                print(f"No data for {position}")

        # Create team-specific PDFs with tqdm progress bar
        for team in tqdm(self.league.rosters, desc="Creating team PDFs"):
            self.create_team_pdf(team)




    from tqdm import tqdm

    def _plot_and_save_histograms(self, top_players, position):
        pdf_filename = os.path.join(self.positions_dir, f'{position}_histograms.pdf')

        # Limit to top 30 players
        top_30_players = top_players[:30]

        with PdfPages(pdf_filename) as pdf:
            for i in tqdm(range(0, len(top_30_players), 6), desc=f"Creating {position} histograms"):
                fig, axs = plt.subplots(3, 2, figsize=(11, 8.5))  # Letter size
                fig.suptitle(f'Top 30 {position} Scoring Distributions (Page {i//6 + 1})', fontsize=16)
                
                for j, player_data in enumerate(top_30_players[i:i+6]):
                    ax = axs[j//2, j%2]
                    player, avg_score, scores_dict, best_season_avg = player_data
                    scores = [score for week_scores in scores_dict.values() for score in week_scores if score > 0]
                    rank = top_30_players.index(player_data) + 1
                    best_season_avg = self.tracker.get_player_best_season_average(player.sleeper_id)
                    self._plot_histogram(ax, scores, player.name, avg_score, rank, position, best_season_avg)
                
                # Remove any empty subplots
                for j in range(len(top_30_players[i:i+6]), 6):
                    axs[j//2, j%2].axis('off')
                
                plt.tight_layout(rect=[0, 0.03, 1, 0.95])
                pdf.savefig(fig)
                plt.close(fig)

        # print(f"Created {position} histogram PDF for top 30 players: {pdf_filename}")

    def _plot_histogram(self, ax, scores, player_name, avg_score, rank, position, best_season_avg):
        ax.hist(scores, bins=30, edgecolor='black', color='skyblue')
        ax.set_title(f'{player_name}\n({position} Rank: {rank})', fontsize=10, fontweight='bold')
        ax.set_xlabel('Score', fontsize=8)
        ax.set_ylabel('Frequency', fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.7)
        
        if len(scores) > 0:
            mean_score = np.mean(scores)
            median_score = np.median(scores)
            ax.axvline(mean_score, color='red', linestyle='dashed', linewidth=1, label=f'Avg: {mean_score:.2f}')
            ax.axvline(median_score, color='green', linestyle='dashed', linewidth=1, label=f'Med: {median_score:.2f}')
            ax.axvline(best_season_avg, color='blue', linestyle='dashed', linewidth=1, label=f'Best: {best_season_avg:.2f}')
            ax.legend(fontsize=6)
        
        ax.tick_params(axis='both', which='major', labelsize=6)


    def _create_player_distributions(self, team, filename):
        players = team.players
        players_with_data = [p for p in players if self._get_player_scores(p.sleeper_id)]

        if not players_with_data:
            print(f"No data available for any players on {team.name}. Skipping player distributions.")
            return

        players_with_data.sort(key=lambda p: self.tracker.get_player_average_score(p.sleeper_id), reverse=True)
        
        # remove players with position UNKNOWN
        players_with_data = [p for p in players_with_data if p.position != "UNKNOWN"]

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
            ax.axvline(best_season_avg, color='b', linestyle='dashed', linewidth=1, label=f'Best Season: {best_season_avg:.1f}')
            title = f"{player.name} ({player.position})\nAvg: {mean_score:.2f} | Best Season: {best_season_avg:.2f}"
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

        if breakdown is None:
            elements.append(Paragraph(f"No {season_type} season data available for {team.name}", self.styles['Normal']))
            return elements

        # Add season summary
        summary_style = ParagraphStyle('Summary', fontSize=12, spaceAfter=12, alignment=1)
        summary = f"""
        <b>Record:</b> {breakdown['record']}  |  
        <b>Points For:</b> {breakdown['points_for']:.2f}  |  
        <b>Points Against:</b> {breakdown['points_against']:.2f}
        <br/>
        <b>Points per Week:</b> {breakdown['points_for'] / 14:.2f}
        <br/><br/>
        <b>Playoff Result:</b> {breakdown['playoff_result']}
        <br/><br/>
        <i>Note: All scores and statistics are for the regular season only (Weeks 1-14)</i>
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

        # Filter out players with position "UNKNOWN"
        filtered_performances = [player for player in breakdown['player_performances'] if player['position'] != "UNKNOWN"]

        # Remove players with position DEF or K
        filtered_performances = [player for player in filtered_performances if player['position'] not in ['DEF', 'K']]

        # Create player performance table
        elements.append(Paragraph("Player Performances (Regular Season Only)", self.subtitle_style))
        player_table = self.create_player_table(filtered_performances)
        elements.append(player_table)

        # Add a note about the season modifier
        elements.append(Spacer(1, 0.2 * inch))
        note = "Note: Season modifier represents player's performance relative to expectations (1.0 is average). All statistics are for the regular season only (Weeks 1-14)."
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
    
    
    def create_top_players_tables(self):
        positions = ['QB', 'RB', 'WR', 'TE']
        pages = []
        
        for position in positions:
            if position in ['WR']:
                pages.append(PageBreak())  # Add a page break before WR
            
            top_players = self.tracker.get_top_players_by_position(position, 30)
            
            def create_table(players, start_rank):
                data = [["Rank", "Player", "Avg"]]
                for i, (player, avg_score) in enumerate(players, start=start_rank):
                    _, _, _, min_score, _ = self.tracker.get_player_average_score(player.sleeper_id)
                    data.append([
                        str(i),
                        player.name,
                        f"{avg_score:.2f}"
                    ])
                
                # Increase column widths by 10%
                table = Table(data, colWidths=[0.5*inch, 1.95*inch, 0.5*inch])
                table.setStyle(self.get_alternating_lavender_style(3, len(data)))
                return table
            
            title = Paragraph(f"Top 30 {position}s", self.subtitle_style)
            table1 = create_table(top_players[:15], 1)
            table2 = create_table(top_players[15:], 16)
            
            # Create a table to hold both tables side by side with a gap
            # Increase the total width by 10%
            combined_table = Table([[table1, None, table2]], colWidths=[3.0*inch, 0.5*inch, 3.0*inch])
            combined_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            
            pages.append((title, combined_table))
        
        return pages
    
    
    def create_player_table(self, player_performances):
        data = [
            ["Player", "Pos", "Total", "Avg", "Modifier", "Games", "Status"]
        ]
        for player in player_performances:
            modifier = player['modifier']
            modifier_str = 'NA' if player['position'] in ['K', 'DEF'] else (f"{modifier:.2f}" if isinstance(modifier, float) else str(modifier))
            games_played = 'NA' if player['position'] in ['K', 'DEF'] else player['games_played']
            status = "Out for Season" if player.get('out_for_season', False) else "Active"
            data.append([
                player['name'],
                player['position'],
                f"{player['total_points']:.2f}",
                f"{player['avg_points']:.2f}",
                modifier_str,
                games_played,
                status
            ])
        colWidths=[1.5*inch, 0.4*inch, 0.85*inch, 0.85*inch, 0.85*inch, 0.75*inch, 1.1*inch]
        
        table = Table(data, colWidths=colWidths)
        
        
        style = self.get_alternating_lavender_style(num_columns=7, num_rows=len(data))
        table.setStyle(style)
        return table
        
    
    
    def create_player_average_scores_table(self, team):
        player_scores = []
        for player in team.players:
            avg_score, total_scores, games_played, min_score, max_score = self.tracker.get_player_average_score(player.sleeper_id)
            worst_season_avg = self.tracker.get_player_worst_season_average(player.sleeper_id)
            best_season_avg = self.tracker.get_player_best_season_average(player.sleeper_id)
            
            player_scores.append((
                player,
                avg_score,
                worst_season_avg,
                best_season_avg
            ))

        sorted_players = sorted(player_scores, key=lambda x: x[1], reverse=True)
        sorted_players = [player for player in sorted_players if player[0].position != "UNKNOWN"]
        
        mid_point = len(sorted_players) // 2

        def create_half_table(players):
            data = [["Player", "Pos", "Avg", "Worst", "Best"]]
            for player, avg_score, worst_season, best_season in players:
                data.append([
                    player.name,
                    player.position,
                    f"{avg_score:.2f}",
                    f"{worst_season:.2f}",
                    f"{best_season:.2f}"
                ])
            return data

        left_data = create_half_table(sorted_players[:mid_point])
        right_data = create_half_table(sorted_players[mid_point:])

        left_table = Table(left_data, colWidths=[1.5*inch, 0.4*inch, 0.65*inch, 0.65*inch, 0.65*inch])
        right_table = Table(right_data, colWidths=[1.5*inch, 0.4*inch, 0.65*inch, 0.65*inch, 0.65*inch])

        # Apply the alternating lavenderf style to both tables
        left_table.setStyle(self.get_alternating_lavender_style(num_columns=5, num_rows=len(left_data)))
        right_table.setStyle(self.get_alternating_lavender_style(num_columns=5, num_rows=len(right_data)))

        # Create a table to hold both tables side by side with less space
        combined_table = Table([[left_table, None, right_table]], colWidths=[4*inch, 0.2*inch, 4*inch])
        combined_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        return combined_table

    def create_team_pdf(self, team):
        base_filename = os.path.join(self.teams_dir, team.name.replace(" ", "_"))
        main_pdf = f'{base_filename}_main.pdf'
        plots_pdf = f'{base_filename}_plots.pdf'
        final_pdf = f'{base_filename}_team_report.pdf'


        doc = SimpleDocTemplate(main_pdf, pagesize=letter,
                        leftMargin=0.25*inch, rightMargin=0.25*inch,
                        topMargin=0.25*inch, bottomMargin=0.25*inch)

        elements = []

        # Add summary page
        elements.extend(self.create_summary_page(team))
        

        # In create_team_pdf method
        elements.append(PageBreak())
        elements.append(Paragraph("Top 30 Players by Position", self.title_style))
        elements.append(Spacer(1, 0.2*inch))
        top_players_tables = self.create_top_players_tables()
        for item in top_players_tables:
            if isinstance(item, PageBreak):
                elements.append(item)
            else:
                title, combined_table = item
                elements.append(title)
                elements.append(Spacer(1, 0.1*inch))
                elements.append(combined_table)
                elements.append(Spacer(1, 0.3*inch))
        elements.append(PageBreak())
        
        
    
        # Add team overview
        elements.append(Paragraph(f"{team.name} - Team Overview", self.title_style))
        elements.extend(self.create_team_overview(team))
        
    
        
        # Add player average scores tables
        avg_scores_tables = self.create_player_average_scores_table(team)
        elements.append(avg_scores_tables)
        
        # Add top 15 performers chart
        top_15_chart = self.create_top_performers_chart(team)
        
        img_data = io.BytesIO()
        top_15_chart.savefig(img_data, format='png', dpi=300, bbox_inches='tight')
        img_data.seek(0)
        top_15_img = Image(img_data, width=6*inch, height=4.25*inch)
        elements.append(top_15_img)
        elements.append(PageBreak())
        
        # Add percentile breakdown section
        elements.append(Paragraph(f"{team.name} - Season Percentile Breakdowns", self.title_style))
        elements.append(Spacer(1, 0.2 * inch))
        elements.extend(self.create_percentile_breakdown(team))
        elements.append(PageBreak())
        
            
        # Add best season breakdown
        elements.extend(self.create_season_breakdown(team, 'best'))
        elements.append(PageBreak())
        
        
        
        # Add worst season breakdown
        elements.extend(self.create_season_breakdown(team, 'worst'))
        elements.append(PageBreak())
        
        
        


        # Build the PDF
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

    

    def create_top_performers_chart(self, team):
        top_performers = self.tracker.get_top_performers(team.name, n = "all")
        
        top_performers = [player for player in top_performers if player[0].position != "UNKNOWN"]
                
        # Create the plot
        fig, ax = plt.subplots(figsize=(6, 4.25))  # Wide but not tall
        
        players = [player[0].name for player in top_performers]
        scores = [player[1] for player in top_performers]
        
        # Create horizontal bar chart
        bars = ax.barh(players, scores, color='lightgreen')
        
        # Customize the plot
        ax.set_title("Top Performers")
        ax.set_xlabel("Average Score")
        ax.tick_params(axis='y', labelsize=6)  # Adjust font size as needed
        
        # Add value labels to the end of each bar
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2, f'{scores[i]:.2f}', 
                    ha='left', va='center', fontsize=6)
        
        plt.tight_layout()
        return fig

    
    def create_summary_page(self, team):
        elements = []
        
        # Add title with slightly more space after
        elements.append(Paragraph(f"Triton Dynasty - Season Summary - (Simulations:{self.tracker.num_simulations})", self.title_style))
        elements.append(Spacer(1, 0.1 * inch))  # Increased space after title

        # Reduce row heights for summary tables
        row_height = 0.22 * inch  # Further reduced from previous 0.25 inch
        header_height = 0.28 * inch  # Slightly reduced from previous 0.3 inch
        
        overall_data = [["Rank", "Team", "Avg Wins", "Avg Losses", "Points/Week", "2025 Pick Proj"]]
        for i, (team_name, avg_wins, avg_points) in enumerate(self.tracker.get_overall_standings(), 1):
            avg_points = avg_points / 14 if avg_points > 0 else 0
            avg_losses = 14 - avg_wins
            overall_data.append([str(i), team_name, f"{avg_wins:.2f}", f"{avg_losses:.2f}", f"{avg_points:.2f}", f"{11 - i}"])

        division1_data = [["Rank", "Team", "Avg Wins", "Avg Losses", "Points/Week"]]
        division2_data = [["Rank", "Team", "Avg Wins", "Avg Losses", "Points/Week"]]

        for i, (team_name, avg_wins, avg_points) in enumerate(self.tracker.get_division_standings(1), 1):
            avg_points = avg_points / 14 if avg_points > 0 else 0
            avg_losses = 14 - avg_wins
            division1_data.append([str(i), team_name, f"{avg_wins:.2f}", f"{avg_losses:.2f}", f"{avg_points:.2f}"])

        for i, (team_name, avg_wins, avg_points) in enumerate(self.tracker.get_division_standings(2), 1):
            avg_points = avg_points / 14 if avg_points > 0 else 0
            avg_losses = 14 - avg_wins
            division2_data.append([str(i), team_name, f"{avg_wins:.2f}", f"{avg_losses:.2f}", f"{avg_points:.2f}"])

        # Create playoff statistics table
        playoff_data = [["Team", "Playoff App.", "Division Wins (Bye Weeks)", "Championships"]]
        team_playoff_stats = []
        for team in self.league.rosters:
            appearances = self.tracker.playoff_appearances[team.name]
            div_wins = self.tracker.division_wins[team.name]
            champs = self.tracker.championships[team.name]
            appearance_rate = appearances / self.tracker.num_simulations * 100
            div_win_rate = div_wins / self.tracker.num_simulations * 100
            champ_rate = champs / self.tracker.num_simulations * 100
            team_playoff_stats.append({
                'name': team.name,
                'appearances': appearances,
                'appearance_rate': appearance_rate,
                'div_wins': div_wins,
                'div_win_rate': div_win_rate,
                'champs': champs,
                'champ_rate': champ_rate
            })

        # Sort team_playoff_stats by championships (descending)
        team_playoff_stats.sort(key=lambda x: x['champs'], reverse=True)

        # Create the sorted playoff_data
        for stats in team_playoff_stats:
            playoff_data.append([
                stats['name'],
                f"{stats['appearances']} ({stats['appearance_rate']:.1f}%)",
                f"{stats['div_wins']} ({stats['div_win_rate']:.1f}%)",
                f"{stats['champs']} ({stats['champ_rate']:.1f}%)"
            ])

        overall_table = Table(overall_data, colWidths=[0.4968*inch, 2.0*inch, 1.1178*inch, 1.1178*inch, 1.1178*inch, 1.1178*inch], 
                              rowHeights=[header_height] + [row_height] * (len(overall_data) - 1))
        division1_table = Table(division1_data, colWidths=[0.4968*inch, 2.0*inch, 1.1178*inch, 1.1178*inch, 1.1178*inch], 
                                rowHeights=[header_height] + [row_height] * (len(division1_data) - 1))
        division2_table = Table(division2_data, colWidths=[0.4968*inch, 2.0*inch, 1.1178*inch, 1.1178*inch, 1.1178*inch], 
                                rowHeights=[header_height] + [row_height] * (len(division2_data) - 1))
        playoff_table = Table(playoff_data, colWidths=[1.85*inch, 1.75*inch, 1.7388*inch, 1.4904*inch], 
                              rowHeights=[header_height] + [row_height] * (len(playoff_data) - 1))
            
        overall_table.setStyle(self.get_summary_table_style(6, len(overall_data)))
        division1_table.setStyle(self.get_summary_table_style(5, len(division1_data)))
        division2_table.setStyle(self.get_summary_table_style(5, len(division2_data)))
        playoff_table.setStyle(self.get_summary_table_style(4, len(playoff_data)))

        # Add tables to elements with slightly increased spacing
        elements.append(Paragraph("Overall Standings", self.subtitle_style))
        elements.append(overall_table)
        elements.append(Spacer(1, 0.08 * inch))  # Slightly increased spacing
        elements.append(Paragraph("Division 1 Standings", self.subtitle_style))
        elements.append(division1_table)
        elements.append(Spacer(1, 0.08 * inch))  # Slightly increased spacing
        elements.append(Paragraph("Division 2 Standings", self.subtitle_style))
        elements.append(division2_table)
        elements.append(Spacer(1, 0.08 * inch))  # Slightly increased spacing
        elements.append(Paragraph("Playoff Statistics", self.subtitle_style))
        elements.append(playoff_table)

        return elements
    
    
    def get_summary_table_style(self, num_columns, num_rows):
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),  # Slightly reduced from 10
            ('BOTTOMPADDING', (0, 0), (-1, 0), 1),  # Slight padding
            ('TOPPADDING', (0, 0), (-1, 0), 1),  # Slight padding
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),  # Reduced from 8
            ('TOPPADDING', (0, 1), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]
        
        # Add alternating row colors
        for i in range(1, num_rows):
            if i % 2:
                style.append(('BACKGROUND', (0, i), (num_columns - 1, i), colors.lavender))
            else:
                style.append(('BACKGROUND', (0, i), (num_columns - 1, i), colors.white))
        
        return TableStyle(style)


    def create_team_overview(self, team):
        elements = []
        
        # Add team stats
        team_stats = self.tracker.get_team_stats(team.name)
        if team_stats:
            # Use the same calculation as in the summary page
            avg_points = team_stats['avg_points'] / 14 if team_stats['avg_points'] > 0 else 0

            stats_data = [
                ["Statistic", "Value"],
                ["Average Wins", f"{team_stats['avg_wins']:.2f}"],
                ["Average Points per Week", f"{avg_points:.2f}"]
            ]

            # Define column widths
            col_widths = [2*inch, 1*inch]  # Adjusted to match the actual number of columns

            stats_table = Table(stats_data, colWidths=col_widths)
            stats_table.setStyle(self.get_alternating_lavender_style(2, 3))  # 2 columns, 3 rows
            elements.append(stats_table)
            elements.append(Spacer(1, 0.2 * inch))

        return elements

    def get_alternating_lavender_style(self, num_columns, num_rows):
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Vertical alignment for all cells
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 13),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Increased bottom padding for header
            ('TOPPADDING', (0, 0), (-1, 0), 3.25),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('TOPPADDING', (0, 1), (-1, -1), 2.25),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2.25),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]
        
        # Add alternating row colors
        for i in range(1, num_rows):  # Start from 1 to skip header row
            if i % 2:
                style.append(('BACKGROUND', (0, i), (num_columns - 1, i), colors.lavender))
            else:
                style.append(('BACKGROUND', (0, i), (num_columns - 1, i), colors.white))
        
        return TableStyle(style)
    
    def create_percentile_charts(self, team):
        breakdowns = self.tracker.get_percentile_breakdowns(team.name)
        if not breakdowns:
            return None, None

        # Create win percentile chart
        win_fig, win_ax = plt.subplots(figsize=(6, 3))
        percentiles = ['10%', '25%', '75%', '90%']
        win_values = [breakdowns['wins'][p] for p in percentiles]
        win_ax.bar(percentiles, win_values, color='skyblue')
        win_ax.set_title('Win Percentiles')
        win_ax.set_ylabel('Wins')
        for i, v in enumerate(win_values):
            win_ax.text(i, v, f'{v:.2f}', ha='center', va='bottom')

        # Create points percentile chart
        points_fig, points_ax = plt.subplots(figsize=(6, 3))
        point_values = [breakdowns['points_for'][p] for p in percentiles]
        points_ax.bar(percentiles, point_values, color='lightgreen')
        points_ax.set_title('Points For Percentiles')
        points_ax.set_ylabel('Points')
        for i, v in enumerate(point_values):
            points_ax.text(i, v, f'{v:.2f}', ha='center', va='bottom')

        # Convert figures to ReportLab Images
        win_img_data = io.BytesIO()
        win_fig.savefig(win_img_data, format='png', dpi=300, bbox_inches='tight')
        win_img_data.seek(0)
        win_img = Image(win_img_data, width=6*inch, height=3*inch)

        points_img_data = io.BytesIO()
        points_fig.savefig(points_img_data, format='png', dpi=300, bbox_inches='tight')
        points_img_data.seek(0)
        points_img = Image(points_img_data, width=6*inch, height=3*inch)

        plt.close(win_fig)
        plt.close(points_fig)

        return win_img, points_img


    def create_percentile_breakdown(self, team):
        elements = []
        breakdowns = self.tracker.get_percentile_breakdowns(team.name)

        if not breakdowns:
            elements.append(Paragraph("No percentile data available", self.styles['Normal']))
            return elements

        # Add explanation of percentiles
        elements.append(Paragraph("<b>Understanding Percentiles:</b>", self.styles['Heading3']))
        elements.append(Paragraph("Percentiles mean x% of simulations total wins value fall below the win value assosiated with the percentile.", self.styles['Normal']))
        elements.append(Paragraph("(Ex: 25% at 10 wins means 25% of simulations had 10 or less wins)", self.styles['Normal']))
        
        elements.append(Spacer(1, 0.2 * inch))

        win_img, points_img = self.create_percentile_charts(team)

        if win_img and points_img:
            elements.append(win_img)
            elements.append(Spacer(1, 0.2 * inch))
            elements.append(points_img)
            elements.append(Spacer(1, 0.2 * inch))


        return elements
    
    

    def create_violin_plot(self, team):
        wins = self.tracker.get_all_wins(team.name)
        points = self.tracker.get_all_points(team.name)

        if not wins or not points:
            return None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))

        # Wins violin plot
        ax1.violinplot(wins, showmeans=False, showmedians=True)
        ax1.set_title('Wins Distribution')
        ax1.set_ylabel('Wins')
        ax1.set_xticks([])

        # Points violin plot
        ax2.violinplot(points, showmeans=False, showmedians=True)
        ax2.set_title('Points Distribution')
        ax2.set_ylabel('Points')
        ax2.set_xticks([])

        plt.tight_layout()

        img_data = io.BytesIO()
        fig.savefig(img_data, format='png', dpi=300, bbox_inches='tight')
        img_data.seek(0)
        img = Image(img_data, width=7*inch, height=3.5*inch)

        plt.close(fig)

        return img

    @lru_cache(maxsize=128)
    def _get_top_players(self, position):
        players = [player for team in self.league.rosters for player in team.players if player.position == position]
        player_stats = []
        for player in players:
            avg_score, _, games_played, _, _ = self.tracker.get_player_average_score(player.sleeper_id)
            best_season_avg = self.tracker.get_player_best_season_average(player.sleeper_id)
            if games_played > 0:
                player_stats.append((player, avg_score, self.tracker.player_scores[player.sleeper_id], best_season_avg))
        return sorted(player_stats, key=lambda x: x[1], reverse=True)[:30]


    def _create_player_plot(self, player_data, rank):
        player, avg_score, scores_dict, best_season_avg = player_data
        scores = np.array([score for week_scores in scores_dict.values() for score in week_scores if score > 0])
        
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.hist(scores, bins=30, edgecolor='black', color='skyblue')
        ax.set_title(f'{player.name}\n({player.position} Rank: {rank+1})', fontsize=10, fontweight='bold')
        ax.set_xlabel('Score', fontsize=8)
        ax.set_ylabel('Frequency', fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.7)
        
        if len(scores) > 0:
            mean_score = np.mean(scores)
            median_score = np.median(scores)
            ax.axvline(mean_score, color='red', linestyle='dashed', linewidth=1, label=f'Avg: {mean_score:.2f}')
            ax.axvline(median_score, color='green', linestyle='dashed', linewidth=1, label=f'Med: {median_score:.2f}')
            ax.axvline(best_season_avg, color='blue', linestyle='dashed', linewidth=1, label=f'Best: {best_season_avg:.2f}')
            ax.legend(fontsize=6)
        
        ax.tick_params(axis='both', which='major', labelsize=6)
        
        img = io.BytesIO()
        fig.savefig(img, format='png')
        img.seek(0)
        plt.close(fig)
        return img