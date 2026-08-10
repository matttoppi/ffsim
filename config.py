import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    league_id: str
    simulations: int = 1000
    seed: int = 2026
    regular_season_weeks: int = 14
    results_file: str = "results.json"

    def __post_init__(self):
        if not self.league_id.strip():
            raise ValueError("league_id is required")
        if self.simulations < 1 or self.regular_season_weeks < 1:
            raise ValueError("simulations and regular_season_weeks must be positive")
        if not self.results_file.strip():
            raise ValueError("results_file is required")

    @classmethod
    def from_file(cls, path):
        try:
            with Path(path).open() as file:
                data = json.load(file)
            league_id = data["league_id"]
            return cls(
                league_id="" if league_id is None else str(league_id).strip(),
                simulations=int(data.get("simulations", 1000)),
                seed=int(data.get("seed", 2026)),
                regular_season_weeks=int(data.get("regular_season_weeks", 14)),
                results_file=str(data.get("results_file", "results.json")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid config file {path}: {error}") from error
