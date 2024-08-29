import pandas as pd
import re

class PFFLoader:
    @staticmethod
    def get_and_clean_data():    
        df = pd.read_csv('datarepo/PFFProjections/24PFFProjections.csv')
        
        desired_columns = [
        "fantasyPointsRank","playerName","teamName","position","byeWeek","games","fantasyPoints","auctionValue",
        "passComp","passAtt","passYds","passTd","passInt","passSacked","rushAtt","rushYds","rushTd","recvTargets",
        "recvReceptions","recvYds","recvTd","fumbles","fumblesLost","twoPt","returnYds","returnTd","fgMade019",
        "fgAtt019","fgMade2029","fgAtt2029","fgMade3039","fgAtt3039","fgMade4049","fgAtt4049","fgMade50plus",
        "fgAtt50plus","patMade","patAtt","dstSacks","dstSafeties","dstInt","dstFumblesForced","dstFumblesRecovered",
        "dstTd","dstReturnYds","dstReturnTd","dstPts0","dstPts16","dstPts713","dstPts1420","dstPts2127","dstPts2834",
        "dstPts35plus","idpTacklesSolo","idpTacklesAssist","idpSacks","idpTacklesForLoss","idpPassDefended","idpInt",
        "idpFumblesForced","idpFumblesRecovered","idpSafeties","idpTd"
    ]
        
        # Check which desired columns are actually present
        available_columns = [col for col in desired_columns if col in df.columns]
        
        if not available_columns:
            raise ValueError("None of the desired columns are present in the dataframe")
        
        # Clean playerName column
        if 'playerName' in df.columns:
            df['playerName'] = df['playerName'].apply(PFFLoader.clean_name)
            
        print(f"PFF data loaded with {len(df)} rows")
        
        return df

    @staticmethod
    def clean_name(name):
        if pd.isna(name):
            return name
        name = str(name).lower()
        name = re.sub(r'\s(jr\.?|sr\.?|ii|iii|iv|v|vi)$', '', name, flags=re.IGNORECASE)
        name = name.replace('.', '').replace("'", '')
        return name.strip().title()