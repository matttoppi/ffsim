import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

def extract_special_teams(input_file, kickers_output, defenses_output):
    kickers = []
    defenses = []

    with open(input_file, 'r', newline='') as infile:
        reader = csv.DictReader(infile)
        
        for row in reader:
            if row['position'].lower() == 'k':
                kickers.append(row)
            elif row['position'].lower() == 'dst':
                defenses.append(row)

    # Sort and rank kickers
    kickers.sort(key=lambda x: float(x['fantasyPoints']), reverse=True)
    for rank, kicker in enumerate(kickers, 1):
        kicker['fantasyPointsRank'] = str(rank)

    # Sort and rank DSTs
    defenses.sort(key=lambda x: float(x['fantasyPoints']), reverse=True)
    for rank, defense in enumerate(defenses, 1):
        defense['fantasyPointsRank'] = str(rank)

    # Write kickers to file
    kicker_fields = [
        "fantasyPointsRank", "playerName", "teamName", "position", "byeWeek", 
        "games", "fantasyPoints", "auctionValue",
        "fgMade019", "fgAtt019", "fgMade2029", "fgAtt2029", "fgMade3039", 
        "fgAtt3039", "fgMade4049", "fgAtt4049", "fgMade50plus", "fgAtt50plus", 
        "patMade", "patAtt"
    ]
    
    write_to_csv(kickers_output, kicker_fields, kickers)

    # Write DSTs to file
    defense_fields = [
        "fantasyPointsRank", "playerName", "teamName", "position", "byeWeek", 
        "games", "fantasyPoints", "auctionValue",
        "dstSacks", "dstSafeties", "dstInt", "dstFumblesForced", 
        "dstFumblesRecovered", "dstTd", "dstReturnYds", "dstReturnTd", 
        "dstPts0", "dstPts16", "dstPts713", "dstPts1420", "dstPts2127", 
        "dstPts2834", "dstPts35plus"
    ]
    
    write_to_csv(defenses_output, defense_fields, defenses)

def write_to_csv(filename, fields, data):
    with open(filename, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fields)
        writer.writeheader()
        for row in data:
            writer.writerow({field: row.get(field, '') for field in fields})

def main():
    projections_dir = PROJECT_ROOT / "data" / "projections"
    input_file = projections_dir / "players.csv"
    kickers_output = projections_dir / "kickers.csv"
    defenses_output = projections_dir / "defenses.csv"

    extract_special_teams(input_file, kickers_output, defenses_output)
    print(
        f"Extraction complete. Kickers saved to {kickers_output}, "
        f"defenses saved to {defenses_output}"
    )


if __name__ == "__main__":
    main()
