class PFFProjections:
    def __init__(self, data):
        self.fantasy_points_rank = data.get('fantasyPointsRank')
        self.fantasy_points = data.get('fantasyPoints')
        self.auction_value = data.get('auctionValue')
        self.pass_comp = data.get('passComp')
        self.pass_att = data.get('passAtt')
        self.pass_yds = data.get('passYds')
        self.pass_td = data.get('passTd')
        self.pass_int = data.get('passInt')
        self.rush_att = data.get('rushAtt')
        self.rush_yds = data.get('rushYds')
        self.rush_td = data.get('rushTd')
        self.recv_targets = data.get('recvTargets')
        self.recv_receptions = data.get('recvReceptions')
        self.recv_yds = data.get('recvYds')
        self.recv_td = data.get('recvTd')
        # Add other attributes as needed