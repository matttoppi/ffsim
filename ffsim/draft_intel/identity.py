from dataclasses import dataclass

from ffsim.loaders.pff import canonical_team, normalized_name


@dataclass(frozen=True)
class CanonicalPlayer:
    canonical_player_id: str
    sleeper_id: str
    full_name: str
    normalized_name: str
    position: str
    nfl_team: str | None
    active: bool


def canonical_players_from_cache(rows):
    players = {}
    for row in rows:
        sleeper_id = row.get("sleeper_id") or row.get("player_id")
        if not sleeper_id:
            raise ValueError("Cached player is missing a Sleeper ID")
        sleeper_id = str(sleeper_id)
        full_name = str(row.get("full_name") or row.get("name") or "")
        player = CanonicalPlayer(
            canonical_player_id=f"sleeper:{sleeper_id}",
            sleeper_id=sleeper_id,
            full_name=full_name,
            normalized_name=normalized_name(full_name),
            position=str(row.get("position") or "UNKNOWN").upper().replace("DST", "DEF"),
            nfl_team=canonical_team(row.get("team")) or None,
            active=True,
        )
        if sleeper_id in players and players[sleeper_id] != player:
            raise ValueError(f"Conflicting cached players for Sleeper ID {sleeper_id}")
        players[sleeper_id] = player
    return tuple(players[player_id] for player_id in sorted(players))
