"""Personal season-point offsets layered over the base projections (ADR-046).

One offset per player, denominated in projected season points: positive
means the owner values the player above the base projection (like),
negative below it (dislike). Offsets shift the user-side valuation only —
simulated future user picks, the preference-adjusted candidate utility,
and the guaranteed value entrants of the candidate window. Opponent
modeling, survival simulation, replacement levels, and the shared
``SeasonWorldBank`` never see them.
"""

import json
from hashlib import sha256
from pathlib import Path

from ffsim.draft_intel.storage import _atomic_write
from ffsim.paths import CACHE_DIR


ALLOWED_OFFSETS = (
    -50, -40, -30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30, 40, 50,
)


def ranks_path(path=None):
    return Path(path) if path is not None else (
        CACHE_DIR / "draft_intel" / "personal_ranks.json"
    )


def load_offsets(path=None):
    """Stored nonzero offsets keyed by Sleeper player ID."""
    file = ranks_path(path)
    if not file.exists():
        return {}
    raw = json.loads(file.read_text()).get("offsets") or {}
    offsets = {}
    for player_id, offset in raw.items():
        offset = int(offset)
        if offset in ALLOWED_OFFSETS and offset != 0:
            offsets[str(player_id)] = offset
    return offsets


def save_offset(player_id, offset, path=None):
    """Persist one offset atomically; ``0`` clears the player's entry."""
    player_id = str(player_id).strip()
    if not player_id:
        raise ValueError("player_id is required")
    offset = int(offset)
    if offset not in ALLOWED_OFFSETS:
        raise ValueError(f"offset must be one of {ALLOWED_OFFSETS}")
    offsets = load_offsets(path)
    if offset == 0:
        offsets.pop(player_id, None)
    else:
        offsets[player_id] = offset
    _atomic_write(
        ranks_path(path),
        (json.dumps({"offsets": offsets}, sort_keys=True, indent=1) + "\n").encode(),
    )
    return offsets


def adjusted_projection(projection, offsets):
    """Season projections under the owner's offsets: ``base + offset``.

    The single ADR-046 rule for season-point maps — every consumer that
    shows or ranks by the owner's numbers (the future-user policy's
    projection map, the board's points/VORP/WORP tables) goes through
    here. Replacement levels stay raw: offsets are player opinions, not a
    new league-wide cutline.
    """
    if not offsets:
        return projection
    return {
        player_id: points + offsets.get(player_id, 0.0)
        for player_id, points in projection.items()
    }


def offsets_hash(offsets):
    """Stable identity of a personal board; ``None`` when empty."""
    if not offsets:
        return None
    return sha256(
        json.dumps(
            {player_id: offsets[player_id] for player_id in sorted(offsets)},
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
