"""Reusable correlated player-week season worlds."""

from dataclasses import dataclass
from hashlib import sha256
import json

import numpy as np

from ffsim.simulation.season import PlayerWorldGenerator


WORLD_GENERATOR_VERSION = 1
SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


@dataclass(frozen=True)
class SeasonWorldBank:
    version: str
    seed: int
    player_ids: tuple[str, ...]
    weeks: tuple[int, ...]
    source_versions: tuple[tuple[str, str], ...]
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
    source_versions,
):
    """Generate immutable score and availability tensors for a draftable pool."""
    if world_count < 1 or weeks < 1:
        raise ValueError("world_count and weeks must be positive")
    versions = tuple(sorted((str(key), str(value)) for key, value in source_versions.items()))
    if not versions or any(not key or not value for key, value in versions):
        raise ValueError("source_versions must contain non-empty version identifiers")

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
        versions,
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
        versions,
        scores,
        available,
    )


def _version(scoring, scenario, source_versions, player_ids, weeks, seed, world_count):
    payload = {
        "generator": WORLD_GENERATOR_VERSION,
        "scoring": scoring,
        "scenario": scenario,
        "sources": source_versions,
        "players": player_ids,
        "weeks": weeks,
        "seed": seed,
        "world_count": world_count,
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
