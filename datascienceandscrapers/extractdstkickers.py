import csv
import os

def extract_and_rank_kickers_and_dsts(input_file, kickers_output, dsts_output):
    kickers = []
    dsts = []

    with open(input_file, 'r', newline='') as infile:
        reader = csv.DictReader(infile)
        
        for row in reader:
            if row['position'].lower() == 'k':
                kickers.append(row)
            elif row['position'].lower() == 'dst':
                dsts.append(row)

    # Sort and rank kickers
    kickers.sort(key=lambda x: float(x['fantasyPoints']), reverse=True)
    for rank, kicker in enumerate(kickers, 1):
        kicker['fantasyPointsRank'] = str(rank)

    # Sort and rank DSTs
    dsts.sort(key=lambda x: float(x['fantasyPoints']), reverse=True)
    for rank, dst in enumerate(dsts, 1):
        dst['fantasyPointsRank'] = str(rank)

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
    dst_fields = [
        "fantasyPointsRank", "playerName", "teamName", "position", "byeWeek", 
        "games", "fantasyPoints", "auctionValue",
        "dstSacks", "dstSafeties", "dstInt", "dstFumblesForced", 
        "dstFumblesRecovered", "dstTd", "dstReturnYds", "dstReturnTd", 
        "dstPts0", "dstPts16", "dstPts713", "dstPts1420", "dstPts2127", 
        "dstPts2834", "dstPts35plus"
    ]
    
    write_to_csv(dsts_output, dst_fields, dsts)

def write_to_csv(filename, fields, data):
    with open(filename, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fields)
        writer.writeheader()
        for row in data:
            writer.writerow({field: row.get(field, '') for field in fields})

# Usage

input_file = 'datarepo/PFFProjections/24PFFProjections.csv'


kickers_output = 'datarepo/PFFProjections/kickers.csv'
dsts_output = 'datarepo/PFFProjections/dsts.csv'

extract_and_rank_kickers_and_dsts(input_file, kickers_output, dsts_output)
print(f"Extraction complete. Kickers saved to {kickers_output}, DSTs saved to {dsts_output}")