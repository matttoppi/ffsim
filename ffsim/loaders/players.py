import json
from urllib.request import Request, urlopen

from ffsim.loaders.data_merger import DataMerger
from ffsim.loaders.fantasy_calc import FantasyCalcLoader
from ffsim.loaders.injuries import InjuryDataLoader
from ffsim.loaders.pff import PFFLoader
from ffsim.loaders.sleeper import SleeperLoader
from ffsim.models.player import PFFProjections, Player
from ffsim.paths import CACHE_DIR
from ffsim.simulation.empirical import EmpiricalLibrary


class PlayerLoader:
    def __init__(self):
        self.players_file = CACHE_DIR / "players.json"
        self.sleeper_players_file = CACHE_DIR / "sleeper_players.json"
        self.enriched_players = []
        self.players_by_id = {}

    def refresh(self):
        sleeper_players = self.refresh_sleeper_players()

        sleeper_projections = self.fetch_sleeper_projections()
        injuries = InjuryDataLoader.get_and_clean_data()
        injuries = {
            row.sleeper_id: row._asdict()
            for row in injuries.itertuples(index=False)
        }
        fantasy_calc = FantasyCalcLoader.get_and_clean_data()
        sleeper = SleeperLoader.get_and_clean_data(sleeper_players.values())
        projections = PFFLoader.get_and_clean_data()
        merged = DataMerger.merge_data(fantasy_calc, sleeper, projections)
        self.enriched_players = []
        for _, row in merged.iterrows():
            player_data = row.to_dict()
            player_data["pff_projections"] = (
                player_data.copy() if player_data["projection_match_status"] == "matched" else None
            )
            player_data["sleeper_projections"] = sleeper_projections.get(
                str(player_data["player_id"]), {}
            )
            player_data.update(injuries.get(str(player_data["player_id"]), {}))
            player = Player(player_data)
            self.enriched_players.append(player)

        self._index_players()
        self.save_players()
        report_file = CACHE_DIR / "projection_matches.json"
        report_file.write_text(json.dumps(DataMerger.last_projection_report, indent=2) + "\n")
        print(f"Refreshed {len(self.enriched_players)} players.")
        print(f"Projection match report: {report_file}")

    def refresh_sleeper_players(self):
        sleeper_players = self.fetch_sleeper_players()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.sleeper_players_file.write_text(json.dumps(sleeper_players) + "\n")
        return sleeper_players

    @staticmethod
    def fetch_sleeper_players():
        with urlopen("https://api.sleeper.app/v1/players/nfl", timeout=30) as response:
            players = json.load(response)
        for player_id, player in players.items():
            player["player_id"] = player.get("player_id") or player_id
        return players

    @staticmethod
    def fetch_sleeper_projections(season=2026):
        url = f"https://api.sleeper.com/projections/nfl/{season}?season_type=regular"
        request = Request(url, headers={"User-Agent": "ffsim/1.0"})
        with urlopen(request, timeout=30) as response:
            rows = json.load(response)
        return {
            str(row["player_id"]): row.get("stats", {})
            for row in rows
            if row.get("player_id")
        }

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
            self.enriched_players.append(player)
        empirical_library = EmpiricalLibrary()
        for player in self.enriched_players:
            player.initialize_empirical_sampler(empirical_library)
        self._index_players()

    def save_players(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = []
        for player in self.enriched_players:
            row = player.to_dict()
            row["pff_projections"] = player.pff_projections.data if player.pff_projections else None
            row["missed_weeks"] = []
            data.append(self.to_serializable(row))
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
