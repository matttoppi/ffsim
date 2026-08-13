"""Reusable correlated player-week season worlds."""

from dataclasses import dataclass
from hashlib import file_digest, sha256
import json

import numpy as np

from ffsim.paths import CACHE_DIR, DATA_DIR
from ffsim.simulation.season import PlayerWorldGenerator


WORLD_GENERATOR_VERSION = 1
SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
WORLD_INPUT_FILES = (
    CACHE_DIR / "players.json",
    DATA_DIR / "projections" / "defense_matchups.csv",
    DATA_DIR / "historical" / "nflverse" / "reference" / "games.csv",
    DATA_DIR / "historical" / "nflverse" / "reference" / "db_playerids.csv",
    *(
        DATA_DIR / "historical" / "nflverse" / directory / f"{prefix}_{season}.csv"
        for directory, prefix in (
            ("snap_counts", "snap_counts"),
            ("weekly_stats", "stats_player_week"),
            ("weekly_team_stats", "stats_team_week"),
            ("play_by_play", "scoring_player_week"),
            ("play_by_play", "scoring_team_week"),
        )
        for season in (2024, 2025)
    ),
)


@dataclass(frozen=True)
class SeasonWorldBank:
    version: str
    seed: int
    player_ids: tuple[str, ...]
    weeks: tuple[int, ...]
    input_hash: str
    scores: np.ndarray
    available: np.ndarray

    @property
    def world_count(self):
        return self.scores.shape[0]


def build_season_world_bank(
    league,
    players,
    world_count,
    *,
    weeks=17,
    seed=2026,
    scenario=None,
):
    """Generate immutable score and availability tensors for a draftable pool."""
    if world_count < 1 or weeks < 1:
        raise ValueError("world_count and weeks must be positive")
    players = tuple(sorted(players, key=lambda player: str(player.sleeper_id)))
    player_ids = tuple(str(player.sleeper_id) for player in players)
    if not players or len(set(player_ids)) != len(player_ids) or "None" in player_ids:
        raise ValueError("players must have unique Sleeper IDs")
    invalid = [
        player_id
        for player_id, player in zip(player_ids, players)
        if player.position not in SUPPORTED_POSITIONS
        or not player.pff_projections
        or player.projected_games <= 0
    ]
    if invalid:
        raise ValueError("Players are not world-bank eligible: " + ", ".join(invalid))

    week_ids = tuple(range(1, weeks + 1))
    scenario = scenario or {}
    input_hash = world_bank_input_hash()
    scores = np.zeros((world_count, len(players), weeks), dtype=np.float32)
    available = np.zeros_like(scores, dtype=bool)
    streams = np.random.SeedSequence(seed).spawn(world_count)
    generator = PlayerWorldGenerator(
        league,
        players,
        weeks,
        np.random.default_rng(streams[0]),
        scenario,
    )
    try:
        for world_index, stream in enumerate(streams):
            generator.rng = np.random.default_rng(stream)
            for player in players:
                player.prepare_availability(week_ids, generator.rng)
            for week_index, week in enumerate(week_ids):
                generator.prepare_week_factors(week)
                for player_index, player in enumerate(players):
                    is_available = player.is_available(week)
                    available[world_index, player_index, week_index] = is_available
                    if is_available:
                        scores[world_index, player_index, week_index] = player.calculate_score(
                            league.scoring_settings, week, generator.rng
                        )
    finally:
        for player in players:
            player.reset_season_stats()
            player.season_factor = 1.0
            player.week_factor = 1.0

    scores.flags.writeable = False
    available.flags.writeable = False
    version = _version(
        league.scoring_settings.values,
        scenario,
        input_hash,
        player_ids,
        week_ids,
        seed,
        world_count,
    )
    return SeasonWorldBank(
        version,
        seed,
        player_ids,
        week_ids,
        input_hash,
        scores,
        available,
    )


def draftable_players(players):
    """Return every projected player the current season model can score."""
    return tuple(sorted(
        (
            player for player in players
            if player.position in SUPPORTED_POSITIONS
            and player.pff_projections
            and player.projected_games > 0
        ),
        key=lambda player: str(player.sleeper_id),
    ))


def world_bank_input_hash():
    digest = sha256()
    for path in WORLD_INPUT_FILES:
        if not path.is_file():
            raise FileNotFoundError(f"Season world input is missing: {path}")
        digest.update(str(path.relative_to(DATA_DIR)).encode())
        with path.open("rb") as file:
            digest.update(file_digest(file, "sha256").digest())
    return digest.hexdigest()


def _version(scoring, scenario, input_hash, player_ids, weeks, seed, world_count):
    payload = {
        "generator": WORLD_GENERATOR_VERSION,
        "scoring": scoring,
        "scenario": scenario,
        "inputs": input_hash,
        "players": player_ids,
        "weeks": weeks,
        "seed": seed,
        "world_count": world_count,
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
