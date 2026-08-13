import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    league_id: str
    draft_id: str | None = None
    simulations: int = 300
    seed: int = 2026
    regular_season_weeks: int = 14
    results_file: str = "output/results.json"
    scenario_file: str | None = None

    def __post_init__(self):
        if not self.league_id.strip():
            raise ValueError("league_id is required")
        if self.draft_id is not None and not self.draft_id.strip():
            raise ValueError("draft_id cannot be empty")
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
                draft_id=(
                    str(data["draft_id"]).strip()
                    if data.get("draft_id") is not None
                    else None
                ),
                simulations=int(data.get("simulations", 300)),
                seed=int(data.get("seed", 2026)),
                regular_season_weeks=int(data.get("regular_season_weeks", 14)),
                results_file=str(data.get("results_file", "output/results.json")),
                scenario_file=data.get("scenario_file"),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid config file {path}: {error}") from error


def save_league_attachment(path, league_id, draft_id):
    path = Path(path)
    config = replace(
        AppConfig.from_file(path),
        league_id="" if league_id is None else str(league_id).strip(),
        draft_id="" if draft_id is None else str(draft_id).strip(),
    )
    data = json.loads(path.read_text())
    data["league_id"] = config.league_id
    data["draft_id"] = config.draft_id
    descriptor, temporary_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump(data, file, indent=2)
            file.write("\n")
        os.replace(temporary_path, path)
    finally:
        Path(temporary_path).unlink(missing_ok=True)
    return config
