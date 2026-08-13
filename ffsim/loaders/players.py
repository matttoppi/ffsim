import json
from copy import deepcopy
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from ffsim.loaders.data_merger import DataMerger
from ffsim.loaders.fantasy_calc import FantasyCalcLoader
from ffsim.loaders.fantasypros import (
    FANTASYPROS_REFRESH_INTERVAL,
    FantasyProsLoader,
    combine_with_pff,
)
from ffsim.loaders.injuries import InjuryDataLoader
from ffsim.loaders.pff import PFFLoader
from ffsim.loaders.sleeper import SleeperLoader
from ffsim.models.player import Player
from ffsim.paths import CACHE_DIR
from ffsim.simulation.empirical import EmpiricalLibrary


class PlayerLoader:
    def __init__(self):
        self.players_file = CACHE_DIR / "players.json"
        self.sleeper_players_file = CACHE_DIR / "sleeper_players.json"
        self.projection_report_file = CACHE_DIR / "projection_matches.json"
        self.enriched_players = []
        self.players_by_id = {}

    def refresh(self, season=2026, retrieved_at=None):
        sleeper_players = self.refresh_sleeper_players()

        sleeper_projections = self.fetch_sleeper_projections(season)
        injuries = InjuryDataLoader.get_and_clean_data()
        injuries = {
            row.sleeper_id: row._asdict()
            for row in injuries.itertuples(index=False)
        }
        fantasy_calc = FantasyCalcLoader.get_and_clean_data()
        sleeper = SleeperLoader.get_and_clean_data(sleeper_players.values())
        pff = PFFLoader.get_and_clean_data()
        pff_matches = DataMerger.merge_data(fantasy_calc, sleeper, pff)
        pff_report = deepcopy(DataMerger.last_projection_report)
        pff_by_sleeper_id = {
            str(row["player_id"]): pff.loc[int(row["_projection_index"])].to_dict()
            for _, row in pff_matches.iterrows()
            if row["projection_match_status"] == "matched"
        }
        fantasypros = FantasyProsLoader.get_and_clean_data(sleeper, season)
        fantasypros_mapping_report = fantasypros.attrs["mapping_report"]
        projections = combine_with_pff(fantasypros, pff_by_sleeper_id)
        merged = DataMerger.merge_data(fantasy_calc, sleeper, projections)
        projection_report = deepcopy(DataMerger.last_projection_report)
        self.enriched_players = []
        for _, row in merged.iterrows():
            player_data = row.to_dict()
            player_data["projections"] = (
                player_data.copy() if player_data["projection_match_status"] == "matched" else None
            )
            player_data["pff_projections"] = pff_by_sleeper_id.get(str(player_data["player_id"]))
            player_data["sleeper_projections"] = sleeper_projections.get(
                str(player_data["player_id"]), {}
            )
            player_data.update(injuries.get(str(player_data["player_id"]), {}))
            player = Player(player_data)
            self.enriched_players.append(player)

        self._index_players()
        self.save_players()
        retrieved_at = _datetime(retrieved_at or datetime.now(timezone.utc))
        self.projection_report_file.write_text(json.dumps({
            "fantasypros_projection": {
                "season": season,
                "retrieved_at": retrieved_at.isoformat(),
                "next_refresh_at": (retrieved_at + FANTASYPROS_REFRESH_INTERVAL).isoformat(),
            },
            "fantasypros_identity": fantasypros_mapping_report,
            "primary": projection_report,
            "supplemental_pff": pff_report,
        }, indent=2) + "\n")
        print(f"Refreshed {len(self.enriched_players)} players.")
        print(f"Projection match report: {self.projection_report_file}")
        return self.projection_status(season=season, now=retrieved_at)

    def refresh_if_stale(self, season=2026, now=None):
        status = self.projection_status(season=season, now=now)
        if status["fresh"]:
            return {**status, "refreshed": False}
        return {**self.refresh(season=season, retrieved_at=now), "refreshed": True}

    def projection_status(self, season=2026, now=None):
        now = _datetime(now or datetime.now(timezone.utc))
        retrieved_at = None
        if self.players_file.exists() and self.sleeper_players_file.exists():
            try:
                report = json.loads(self.projection_report_file.read_text())
                metadata = report["fantasypros_projection"]
                if int(metadata["season"]) == season:
                    retrieved_at = _datetime(metadata["retrieved_at"])
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
                pass
        next_refresh = retrieved_at + FANTASYPROS_REFRESH_INTERVAL if retrieved_at else None
        return {
            "season": season,
            "refresh_interval_hours": 12,
            "fresh": next_refresh is not None and now < next_refresh,
            "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
            "next_refresh_at": next_refresh.isoformat() if next_refresh else None,
        }

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
        self.enriched_players = [Player(data) for data in player_data]
        empirical_library = EmpiricalLibrary()
        for player in self.enriched_players:
            player.initialize_empirical_sampler(empirical_library)
        self._index_players()

    def save_players(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = []
        for player in self.enriched_players:
            row = player.to_dict()
            row["projections"] = player.projections.data if player.projections else None
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


def _datetime(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if value.tzinfo is None:
        raise ValueError("Projection refresh timestamps must include a timezone")
    return value.astimezone(timezone.utc)
