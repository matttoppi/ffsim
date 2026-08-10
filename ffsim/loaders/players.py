import json
from urllib.request import urlopen

from ffsim.loaders.data_merger import DataMerger
from ffsim.loaders.fantasy_calc import FantasyCalcLoader
from ffsim.loaders.injuries import InjuryDataLoader
from ffsim.loaders.pff import PFFLoader
from ffsim.loaders.sleeper import SleeperLoader
from ffsim.models.player import PFFProjections, Player
from ffsim.paths import CACHE_DIR, DATA_DIR
from ffsim.simulation.special_teams import SpecialTeamScorer


class PlayerLoader:
    def __init__(self):
        self.players_file = CACHE_DIR / "players.json"
        self.enriched_players = []
        self.players_by_id = {}
        self.special_team_scorer = SpecialTeamScorer(
            DATA_DIR / "projections" / "kickers.csv",
            DATA_DIR / "projections" / "defenses.csv",
        )

    def refresh(self):
        sleeper_players = self.fetch_sleeper_players()
        fantasy_calc = FantasyCalcLoader.get_and_clean_data()
        sleeper = SleeperLoader.get_and_clean_data(sleeper_players.values())
        projections = PFFLoader.get_and_clean_data()
        injuries = InjuryDataLoader.get_and_clean_data()

        for dataframe in (fantasy_calc, sleeper, projections, injuries):
            for column in ("full_name", "first_name", "last_name"):
                if column in dataframe.columns:
                    dataframe[column] = dataframe[column].apply(Player.clean_name)

        merged = DataMerger.merge_data(fantasy_calc, sleeper, projections, injuries)
        self.enriched_players = []
        for _, row in merged.iterrows():
            player_data = row.to_dict()
            player_data["pff_projections"] = player_data.copy()
            player = Player(player_data)
            player.normalize_injury_probability()
            player.initialize_st_scorer(self.special_team_scorer)
            self.enriched_players.append(player)

        self._index_players()
        self.save_players()
        print(f"Refreshed {len(self.enriched_players)} players.")

    @staticmethod
    def fetch_sleeper_players():
        with urlopen("https://api.sleeper.app/v1/players/nfl", timeout=30) as response:
            players = json.load(response)
        for player_id, player in players.items():
            player["player_id"] = player.get("player_id") or player_id
        return players

    def load_players(self):
        if not self.players_file.exists():
            raise FileNotFoundError("Player cache is missing. Run `python -m ffsim refresh` first.")

        with self.players_file.open() as file:
            player_data = json.load(file)
        self.enriched_players = []
        for data in player_data:
            pff_data = data.get("pff_projections")
            data["pff_projections"] = PFFProjections(pff_data) if pff_data else None
            player = Player(data)
            player.initialize_st_scorer(self.special_team_scorer)
            self.enriched_players.append(player)
        self._index_players()

    def save_players(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = [self.to_serializable(player.to_dict()) for player in self.enriched_players]
        self.players_file.write_text(json.dumps(data, indent=2) + "\n")

    def _index_players(self):
        self.players_by_id = {str(player.sleeper_id): player for player in self.enriched_players}

    def ensure_players_loaded(self):
        if not self.enriched_players:
            self.load_players()

    def load_player(self, sleeper_id):
        self.ensure_players_loaded()
        return self.players_by_id.get(str(sleeper_id))

    def to_serializable(self, obj):
        if isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        if isinstance(obj, dict):
            return {key: self.to_serializable(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self.to_serializable(item) for item in obj]
        if hasattr(obj, "__dict__"):
            return self.to_serializable(obj.__dict__)
        return str(obj)
