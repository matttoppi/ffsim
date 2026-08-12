import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from ffsim.paths import CACHE_DIR


@dataclass(frozen=True)
class PickObservation:
    draft_id: str
    season: int
    scoring_type: str | None
    team_count: int | None
    draft_started_at: int | None
    pick_no: int
    round: int | None
    draft_slot: int | None
    manager_id: str
    selected_player_id: str | None
    selected_position: str | None
    roster_before_pick: tuple[str, ...]
    observed_available_player_ids: tuple[str, ...]


def load_pick_observations(storage_dir=None):
    database_path = Path(storage_dir or CACHE_DIR / "draft_intel") / "history.sqlite3"
    if not database_path.exists():
        raise FileNotFoundError("Draft intelligence store is missing; run draft-audit --persist first")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        target_managers = {
            (row[0], row[1])
            for row in connection.execute(
                "SELECT draft_id, manager_id FROM historical_draft_managers"
            )
        }
        picks = connection.execute(
            """
            SELECT p.draft_id, d.season, d.scoring_type, d.team_count,
                   d.start_time, p.pick_no, p.round, p.draft_slot, p.manager_id,
                   p.canonical_player_id, p.position, p.is_keeper
            FROM historical_picks AS p
            JOIN historical_drafts AS d ON d.draft_id = p.draft_id
            WHERE d.included = 1
            ORDER BY p.draft_id, p.pick_no
            """
        ).fetchall()
    finally:
        connection.close()

    observations = []
    for draft_picks in _by_draft(picks):
        draft_id = draft_picks[0]["draft_id"]
        available = {
            pick["canonical_player_id"]
            for pick in draft_picks
            if pick["canonical_player_id"] and pick["is_keeper"] != 1
        }
        rosters = defaultdict(list)
        keeper_ids = [
            pick["canonical_player_id"]
            for pick in draft_picks
            if pick["canonical_player_id"] and pick["is_keeper"] == 1
        ]
        keepers = set(keeper_ids)
        if len(keepers) != len(keeper_ids):
            raise ValueError(f"A keeper was listed more than once in draft {draft_id}")
        if keepers & available:
            player_id = sorted(keepers & available)[0]
            raise ValueError(f"Keeper {player_id} was also selected in draft {draft_id}")
        for pick in draft_picks:
            if pick["canonical_player_id"] and pick["is_keeper"] == 1 and pick["manager_id"]:
                rosters[pick["manager_id"]].append(pick["canonical_player_id"])
        for pick in draft_picks:
            player_id = pick["canonical_player_id"]
            manager_id = pick["manager_id"]
            if pick["is_keeper"] != 1 and (draft_id, manager_id) in target_managers:
                observations.append(PickObservation(
                    draft_id=pick["draft_id"],
                    season=pick["season"],
                    scoring_type=pick["scoring_type"],
                    team_count=pick["team_count"],
                    draft_started_at=pick["start_time"],
                    pick_no=pick["pick_no"],
                    round=pick["round"],
                    draft_slot=pick["draft_slot"],
                    manager_id=manager_id,
                    selected_player_id=player_id,
                    selected_position=pick["position"],
                    roster_before_pick=tuple(rosters[manager_id]),
                    observed_available_player_ids=tuple(sorted(available)),
                ))
            if player_id:
                if pick["is_keeper"] != 1:
                    if player_id not in available:
                        raise ValueError(
                            f"Player {player_id} was selected more than once in draft {pick['draft_id']}"
                        )
                    available.remove(player_id)
                if manager_id and pick["is_keeper"] != 1:
                    rosters[manager_id].append(player_id)
    return tuple(observations)


def summarize_manager_profiles(observations):
    by_manager = defaultdict(list)
    for observation in observations:
        by_manager[observation.manager_id].append(observation)

    profiles = {}
    for manager_id, picks in sorted(by_manager.items()):
        position_counts = Counter(pick.selected_position for pick in picks if pick.selected_position)
        round_counts = Counter(
            (pick.round, pick.selected_position)
            for pick in picks
            if pick.round is not None and pick.selected_position
        )
        first_rounds = defaultdict(list)
        picks_by_draft = defaultdict(list)
        for pick in picks:
            picks_by_draft[pick.draft_id].append(pick)
        for draft_picks in picks_by_draft.values():
            first_by_position = {}
            for pick in draft_picks:
                if pick.selected_position and pick.round is not None:
                    first_by_position.setdefault(pick.selected_position, pick.round)
            for position, round_number in first_by_position.items():
                first_rounds[position].append(round_number)

        profiles[manager_id] = {
            "draft_count": len(picks_by_draft),
            "pick_count": len(picks),
            "position_picks": dict(sorted(position_counts.items())),
            "position_picks_by_round": {
                str(round_number): dict(sorted(
                    (position, count)
                    for (round_value, position), count in round_counts.items()
                    if round_value == round_number
                ))
                for round_number in sorted({round_value for round_value, _ in round_counts})
            },
            "first_position_rounds": {
                position: sorted(rounds)
                for position, rounds in sorted(first_rounds.items())
            },
        }
    return profiles


def _by_draft(picks):
    draft = []
    draft_id = None
    for pick in picks:
        if draft and pick["draft_id"] != draft_id:
            yield draft
            draft = []
        draft.append(pick)
        draft_id = pick["draft_id"]
    if draft:
        yield draft
