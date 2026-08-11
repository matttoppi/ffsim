"""Join PFF DST projections to Mike Clay's 2026 defensive unit grades."""

import csv
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PFF = ROOT / "data" / "projections" / "defenses.csv"
OUTPUT = ROOT / "data" / "projections" / "defense_matchups.csv"

TEAM_ALIASES = {"ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "LA": "LAR"}

CLAY = """team,team_name,di_grade,edge_grade,lb_grade,cb_grade,s_grade,defense_grade,defense_rank
LAR,Los Angeles Rams,6,7,5,8,6,3.2,1
BAL,Baltimore Ravens,7,5,5,5,9,3.0,4
PHI,Philadelphia Eagles,7,6,8,7,3,3.0,5
NE,New England Patriots,6,5,6,7,7,2.9,7
DET,Detroit Lions,5,6,8,5,7,2.8,8
BUF,Buffalo Bills,5,6,3,5,5,2.4,26
SEA,Seattle Seahawks,7,5,5,7,7,2.9,6
SF,San Francisco 49ers,4,6,7,5,4,2.5,20
DAL,Dallas Cowboys,6,5,4,5,6,2.6,16
DEN,Denver Broncos,6,5,5,6,6,2.8,9
KC,Kansas City Chiefs,5,5,7,5,6,2.6,13
CIN,Cincinnati Bengals,6,5,4,5,5,2.4,25
GB,Green Bay Packers,5,5,5,5,7,2.6,15
HOU,Houston Texans,5,7,6,8,5,3.1,2
LAC,Los Angeles Chargers,5,6,4,4,7,2.6,17
CHI,Chicago Bears,4,5,7,6,5,2.6,14
TB,Tampa Bay Buccaneers,6,5,5,5,6,2.6,12
PIT,Pittsburgh Steelers,7,8,4,7,5,3.1,3
JAX,Jacksonville Jaguars,4,6,6,5,5,2.5,22
NYJ,New York Jets,6,4,8,5,6,2.7,10
MIN,Minnesota Vikings,6,5,6,5,4,2.5,21
NYG,New York Giants,4,8,5,4,5,2.5,19
WAS,Washington Commanders,5,4,5,5,4,2.3,30
IND,Indianapolis Colts,5,5,3,6,5,2.5,24
NO,New Orleans Saints,5,6,5,5,6,2.5,18
ATL,Atlanta Falcons,5,4,5,5,7,2.4,29
CLE,Cleveland Browns,5,6,7,4,6,2.7,11
LV,Las Vegas Raiders,4,6,5,5,5,2.4,27
CAR,Carolina Panthers,6,4,5,5,5,2.5,23
TEN,Tennessee Titans,5,5,5,5,4,2.4,28
ARI,Arizona Cardinals,5,4,4,4,4,2.1,31
MIA,Miami Dolphins,5,3,7,3,2,1.9,32
"""


def main():
    clay = {row["team"]: row for row in csv.DictReader(StringIO(CLAY))}
    with PFF.open(newline="") as source:
        pff = list(csv.DictReader(source))
    rows = []
    for projection in pff:
        team = TEAM_ALIASES.get(projection["teamName"], projection["teamName"])
        unit = clay.pop(team)
        rows.append({
            "season": 2026,
            **unit,
            "bye_week": projection["byeWeek"],
            "games": projection["games"],
            "pff_dst_rank": projection["fantasyPointsRank"],
            "pff_fantasy_points": projection["fantasyPoints"],
            "pff_sacks": projection["dstSacks"],
            "pff_safeties": projection["dstSafeties"],
            "pff_interceptions": projection["dstInt"],
            "pff_fumbles_forced": projection["dstFumblesForced"],
            "pff_fumbles_recovered": projection["dstFumblesRecovered"],
            "pff_defensive_tds": projection["dstTd"],
            "pff_return_yards": projection["dstReturnYds"],
            "pff_return_tds": projection["dstReturnTd"],
            "pff_points_allowed_0": projection["dstPts0"],
            "pff_points_allowed_1_6": projection["dstPts16"],
            "pff_points_allowed_7_13": projection["dstPts713"],
            "pff_points_allowed_14_20": projection["dstPts1420"],
            "pff_points_allowed_21_27": projection["dstPts2127"],
            "pff_points_allowed_28_34": projection["dstPts2834"],
            "pff_points_allowed_35_plus": projection["dstPts35plus"],
        })
    if clay or len(rows) != 32:
        raise ValueError(f"Expected all 32 teams; unmatched Clay teams: {sorted(clay)}")
    with OUTPUT.open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
