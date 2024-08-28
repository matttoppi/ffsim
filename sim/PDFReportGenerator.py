from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.widgets.markers import makeMarker

import os

class PDFReportGenerator:
    def __init__(self, league, tracker, visualizer):
        self.league = league
        self.tracker = tracker
        self.visualizer = visualizer
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

    def generate_report(self, filename):
        # Use a relative path for the reports directory
        directory = os.path.join(os.getcwd(), 'reports')
        if not os.path.exists(directory):
            os.makedirs(directory)

        # Create the full path for the PDF file
        full_path = os.path.join(directory, filename)

        doc = SimpleDocTemplate(full_path, pagesize=letter)
        story = []

        story.extend(self.create_league_overview())
        story.extend(self.create_team_analysis())
        story.extend(self.create_player_rankings())
        story.extend(self.create_playoff_results())
        story.extend(self.add_team_performance_charts())
        story.extend(self.create_injury_impact_summary())
        story.extend(self.create_team_season_breakdowns())  # New method

        doc.build(story)
        print(f"PDF report generated: {filename}")

    def create_league_overview(self):
        elements = []
        elements.append(Paragraph("League Overview", self.title_style))
        
        # League settings
        elements.append(Paragraph("League Settings", self.subtitle_style))
        settings_data = [
            ["Setting", "Value"],
            ["League Name", self.league.name],
            ["Total Rosters", self.league.total_rosters],
            ["Roster Positions", ", ".join(self.league.offensive_roster_positions)],
        ]
        settings_table = Table(settings_data)
        settings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(settings_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # League standings
        elements.append(Paragraph("League Standings", self.subtitle_style))
        standings = self.tracker.get_overall_standings()
        standings_data = [["Rank", "Team", "Avg Wins", "Avg Points"]]
        for rank, (team_name, avg_wins, avg_points) in enumerate(standings, 1):
            standings_data.append([rank, team_name, f"{avg_wins:.2f}", f"{avg_points:.2f}"])
        
        standings_table = Table(standings_data)
        standings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(standings_table)
        elements.append(Spacer(1, 0.2*inch))

        return elements
    


    def create_team_analysis(self):
        elements = []
        elements.append(Paragraph("Team Analysis", self.title_style))

        for team in self.league.rosters:
            elements.append(Paragraph(f"{team.name} Analysis", self.subtitle_style))
            
            team_stats = self.tracker.get_team_stats(team.name)
            if team_stats:
                stats_data = [
                    ["Statistic", "Value"],
                    ["Average Wins", f"{team_stats.get('avg_wins', 'N/A'):.2f}"],
                    ["Average Points", f"{team_stats.get('avg_points', 'N/A'):.2f}"],
                ]
                
                if 'best_season' in team_stats:
                    stats_data.extend([
                        ["Best Season Wins", str(team_stats['best_season'].get('wins', 'N/A'))],
                        ["Best Season Points", f"{team_stats['best_season'].get('points_for', 'N/A'):.2f}"],
                    ])
                
                if 'worst_season' in team_stats:
                    stats_data.extend([
                        ["Worst Season Wins", str(team_stats['worst_season'].get('wins', 'N/A'))],
                        ["Worst Season Points", f"{team_stats['worst_season'].get('points_for', 'N/A'):.2f}"],
                    ])
                
                stats_table = Table(stats_data)
                stats_table.setStyle(TableStyle([
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
                elements.append(stats_table)
                elements.append(Spacer(1, 0.2*inch))

            # Add team's top performers
            elements.append(Paragraph("Top Performers", self.styles['Heading3']))
            top_performers = self.tracker.get_top_performers(team.name, 5)
            if top_performers:
                performer_data = [["Player", "Position", "Avg Score"]]
                for player, avg_score in top_performers:
                    performer_data.append([player.name, player.position, f"{avg_score:.2f}"])
                
                performer_table = Table(performer_data)
                performer_table.setStyle(TableStyle([
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
                elements.append(performer_table)
            else:
                elements.append(Paragraph("No top performer data available", self.styles['Normal']))

            elements.append(Spacer(1, 0.3*inch))

        return elements

    def create_player_rankings(self):
        elements = []
        elements.append(Paragraph("Player Rankings", self.title_style))

        positions = ['QB', 'RB', 'WR', 'TE']
        for position in positions:
            elements.append(Paragraph(f"Top {position}s", self.subtitle_style))
            top_players = self.tracker.get_top_players_by_position(position, 10)
            
            if top_players:
                player_data = [["Rank", "Player", "Team", "Avg Score"]]
                for rank, (player, avg_score) in enumerate(top_players, 1):
                    player_data.append([rank, player.name, player.team, f"{avg_score:.2f}"])
                
                player_table = Table(player_data)
                player_table.setStyle(TableStyle([
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
                elements.append(player_table)
            else:
                elements.append(Paragraph(f"No {position} data available", self.styles['Normal']))

            elements.append(Spacer(1, 0.2*inch))

        return elements

    def create_playoff_results(self):
        elements = []
        elements.append(Paragraph("Playoff Results", self.title_style))

        # Championship results
        elements.append(Paragraph("Championship Results", self.subtitle_style))
        championship_data = [["Team", "Championships", "Win Rate"]]
        for team, wins in self.tracker.championships.items():
            win_rate = wins / self.tracker.num_simulations * 100
            championship_data.append([team, str(wins), f"{win_rate:.1f}%"])
        
        championship_table = Table(championship_data)
        championship_table.setStyle(TableStyle([
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
        elements.append(championship_table)
        elements.append(Spacer(1, 0.2*inch))

        # Playoff appearance rates
        elements.append(Paragraph("Playoff Appearance Rates", self.subtitle_style))
        playoff_data = [["Team", "Appearances", "Rate"]]
        for team, appearances in self.tracker.playoff_appearances.items():
            rate = appearances / self.tracker.num_simulations * 100
            playoff_data.append([team, str(appearances), f"{rate:.1f}%"])
        
        playoff_table = Table(playoff_data)
        playoff_table.setStyle(TableStyle([
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
        elements.append(playoff_table)
        elements.append(Spacer(1, 0.2*inch))

        # Add championship pie chart
        elements.append(Paragraph("Championship Distribution", self.subtitle_style))
        pie_chart = self.create_championship_pie_chart()
        elements.append(pie_chart)
        elements.append(Spacer(1, 0.2*inch))

        return elements

    def create_championship_pie_chart(self):
        drawing = Drawing(400, 200)
        pie = Pie()
        pie.x = 100
        pie.y = 15
        pie.width = 200
        pie.height = 170
        pie.data = [self.tracker.championships[team] for team in self.tracker.championships]
        pie.labels = list(self.tracker.championships.keys())
        pie.slices.strokeWidth = 0.5

        # Add a legend
        legend = Legend()
        legend.x = 320
        legend.y = 150
        legend.alignment = 'right'
        legend.columnMaximum = 10
        legend.fontName = 'Helvetica'
        legend.fontSize = 7
        legend.colorNamePairs = [(colors.blue, label) for label in pie.labels]

        drawing.add(pie)
        drawing.add(legend)
        return drawing

    def create_team_performance_chart(self, team_name):
        team_stats = self.tracker.get_team_stats(team_name)
        if not team_stats:
            return None

        drawing = Drawing(400, 200)
        bc = VerticalBarChart()
        bc.x = 50
        bc.y = 50
        bc.height = 125
        bc.width = 300
        bc.data = [
            [team_stats['avg_wins']],
            [team_stats['avg_points'] / 14]  # Assuming 14-week season
        ]
        bc.categoryAxis.categoryNames = ['Avg Wins', 'Avg Points/Week']
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max(14, max(bc.data[0] + bc.data[1]))
        bc.bars[0].fillColor = colors.lightblue
        bc.bars[1].fillColor = colors.lightgreen
        drawing.add(bc)
        return drawing

    def add_team_performance_charts(self):
        elements = []
        elements.append(Paragraph("Team Performance Charts", self.title_style))
        
        for team in self.league.rosters:
            elements.append(Paragraph(f"{team.name} Performance", self.subtitle_style))
            chart = self.create_team_performance_chart(team.name)
            if chart:
                elements.append(chart)
            else:
                elements.append(Paragraph("No data available", self.styles['Normal']))
            elements.append(Spacer(1, 0.2*inch))
        
        return elements

    def create_injury_impact_summary(self):
        elements = []
        elements.append(Paragraph("Injury Impact Summary", self.title_style))
        
        injury_data = [["Team", "Avg Points Lost/Week", "Total Points Lost/Season"]]
        for team in self.league.rosters:
            impact_stats = self.tracker.get_injury_impact_stats(team.name)
            if impact_stats:
                injury_data.append([
                    team.name,
                    f"{impact_stats['avg_points_lost_per_week']:.2f}",
                    f"{impact_stats['total_points_lost_per_season']:.2f}"
                ])
        
        injury_table = Table(injury_data)
        injury_table.setStyle(TableStyle([
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
        elements.append(injury_table)
        
        return elements
    
    
    
    def create_team_season_breakdowns(self):
        elements = []
        for team in self.league.rosters:
            elements.append(Paragraph(f"{team.name} Season Breakdowns", self.title_style))
            
            # Best Season
            elements.append(Paragraph("Best Season", self.subtitle_style))
            best_season = self.tracker.get_best_season_breakdown(team.name)
            if best_season:
                elements.extend(self.create_season_breakdown_table(best_season))
            
            # Worst Season
            elements.append(Paragraph("Worst Season", self.subtitle_style))
            worst_season = self.tracker.get_worst_season_breakdown(team.name)
            if worst_season:
                elements.extend(self.create_season_breakdown_table(worst_season))
            
            elements.append(Spacer(1, 0.2*inch))
        
        return elements

    def create_season_breakdown_table(self, season):
        data = [
            ["Record", season['record']],
            ["Points For", f"{season['points_for']:.2f}"],
            ["Points Against", f"{season['points_against']:.2f}"],
            ["Playoff Result", season['playoff_result']]
        ]
        
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
        
        elements = [table, Spacer(1, 0.1*inch)]
        
        # Add top performers table
        player_data = [["Player", "Position", "Total Points", "Avg Points", "Modifier"]]
        for player in season['player_performances'][:5]:  # Top 5 performers
            player_data.append([
                player['name'],
                player['position'],
                f"{player['total_points']:.2f}",
                f"{player['avg_points']:.2f}",
                f"{player['modifier']:.2f}"
            ])
        
        player_table = Table(player_data)
        player_table.setStyle(TableStyle([
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
        
        elements.append(player_table)
        return elements