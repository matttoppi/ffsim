import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from ffsim.config import AppConfig
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
    manager_display_name: str
    selected_player_id: str | None
    selected_position: str | None
    roster_before_pick: tuple[str, ...]
    roster_positions_before_pick: tuple[str, ...]
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
                   m.display_name, p.canonical_player_id, p.position, p.is_keeper
            FROM historical_picks AS p
            JOIN historical_drafts AS d ON d.draft_id = p.draft_id
            LEFT JOIN managers AS m ON m.sleeper_user_id = p.manager_id
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
            if pick["is_keeper"] == 1 and pick["manager_id"]:
                rosters[pick["manager_id"]].append(
                    (pick["canonical_player_id"], pick["position"])
                )
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
                    manager_display_name=pick["display_name"] or "",
                    selected_player_id=player_id,
                    selected_position=pick["position"],
                    roster_before_pick=tuple(
                        player_id for player_id, _ in rosters[manager_id] if player_id
                    ),
                    roster_positions_before_pick=tuple(
                        position for _, position in rosters[manager_id] if position
                    ),
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
                rosters[manager_id].append((player_id, pick["position"]))
    return tuple(observations)


def load_target_context(config_path, season, league_id=None, cache_dir=None):
    config = AppConfig.from_file(config_path)
    league_id = str(league_id or config.league_id)
    if league_id != config.league_id or config.draft_id is None:
        raise ValueError("Attach an exact Sleeper league and draft before manager-audit")
    path = Path(cache_dir or CACHE_DIR) / f"league_{league_id}.json"
    if not path.exists():
        raise FileNotFoundError("League cache is missing. Run `python -m ffsim refresh` first.")

    snapshot = json.loads(path.read_text())
    draft = snapshot.get("draft") or {}
    if (
        str(draft.get("draft_id")) != config.draft_id
        or str(draft.get("league_id")) != league_id
    ):
        raise ValueError("Attached draft cache does not match config; run refresh")
    scoring_type = str((draft.get("metadata") or {}).get("scoring_type") or "unknown")
    team_count = (draft.get("settings") or {}).get("teams")
    if season <= 0 or not isinstance(team_count, int) or team_count <= 0:
        raise ValueError("Target season and attached draft team count must be positive")
    return {
        "season": season,
        "scoring_type": scoring_type,
        "team_count": team_count,
    }


def summarize_manager_profiles(
    observations,
    *,
    target_season,
    target_scoring_type,
    target_team_count,
):
    if target_season <= 0 or target_team_count <= 0 or not target_scoring_type:
        raise ValueError("Complete positive target context is required")
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
        first_positions_by_draft = {}
        picks_by_draft = defaultdict(list)
        for pick in picks:
            picks_by_draft[pick.draft_id].append(pick)
        for draft_id, draft_picks in picks_by_draft.items():
            draft_picks.sort(key=lambda pick: pick.pick_no)
            first_by_position = {}
            for pick in draft_picks:
                if pick.selected_position and pick.round is not None:
                    first_by_position.setdefault(pick.selected_position, pick.round)
            for position, round_number in first_by_position.items():
                first_rounds[position].append(round_number)
            first_positions_by_draft[draft_id] = first_by_position
        drafts = [draft_picks[0] for draft_picks in picks_by_draft.values()]
        roster_counts = _roster_counts_by_round(picks_by_draft)
        context_weights = {
            draft.draft_id: _context_weight(
                draft,
                target_season,
                target_scoring_type,
                target_team_count,
            )
            for draft in drafts
        }
        four_round_starts = [
            (draft_id, counts[4])
            for draft_id, counts in roster_counts.items()
            if 4 in counts
        ]
        weighted_rb_shapes = Counter()
        weighted_wr_heavy = 0.0
        for draft_id, counts in four_round_starts:
            weight = context_weights[draft_id]["weight"]
            weighted_rb_shapes[_rb_shape(counts)] += weight
            if counts["WR"] >= 3:
                weighted_wr_heavy += weight

        profiles[manager_id] = {
            "display_name": picks[0].manager_display_name,
            "draft_count": len(picks_by_draft),
            "pick_count": len(picks),
            "drafts_by_season": dict(sorted(Counter(
                pick.season for pick in drafts
            ).items())),
            "drafts_by_scoring": dict(sorted(Counter(
                pick.scoring_type or "unknown"
                for pick in drafts
            ).items())),
            "drafts_by_team_count": dict(sorted(Counter(
                str(pick.team_count) if pick.team_count is not None else "unknown"
                for pick in drafts
            ).items())),
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
            "qb_te_timing": _position_timing(
                first_positions_by_draft,
                context_weights,
                ("QB", "TE"),
            ),
            "average_roster_after_round": _average_roster_counts(
                roster_counts,
                context_weights,
            ),
            "four_round_starts": {
                "sample_size": len(four_round_starts),
                "rb_shape": dict(sorted(Counter(
                    _rb_shape(counts) for _, counts in four_round_starts
                ).items())),
                "wr_heavy": sum(counts["WR"] >= 3 for _, counts in four_round_starts),
                "sample_weight": round(sum(
                    context_weights[draft_id]["weight"]
                    for draft_id, _ in four_round_starts
                ), 4),
                "weighted_rb_shape": {
                    shape: round(weight, 4)
                    for shape, weight in sorted(weighted_rb_shapes.items())
                },
                "weighted_wr_heavy": round(weighted_wr_heavy, 4),
            },
            "context": {
                "weighted_draft_count": round(sum(
                    context["weight"] for context in context_weights.values()
                ), 4),
                "draft_weights": dict(sorted(context_weights.items())),
            },
        }
    return profiles


def _roster_counts_by_round(picks_by_draft):
    by_draft = {}
    for draft_id, picks in picks_by_draft.items():
        picks = sorted(picks, key=lambda pick: pick.pick_no)
        counts = Counter(picks[0].roster_positions_before_pick)
        picks_by_round = defaultdict(list)
        for pick in picks:
            if pick.round is not None and pick.selected_position:
                picks_by_round[pick.round].append(pick.selected_position)
        snapshots = {}
        for round_number in range(1, max(picks_by_round, default=0) + 1):
            counts.update(picks_by_round[round_number])
            snapshots[round_number] = counts.copy()
        by_draft[draft_id] = snapshots
    return by_draft


def _average_roster_counts(roster_counts, context_weights):
    rounds = sorted({round_number for counts in roster_counts.values() for round_number in counts})
    positions = sorted({
        position
        for counts in roster_counts.values()
        for snapshot in counts.values()
        for position in snapshot
    })
    return {
        str(round_number): _weighted_round_summary(samples, positions, context_weights)
        for round_number in rounds
        if (samples := [
            (draft_id, counts[round_number])
            for draft_id, counts in roster_counts.items()
            if round_number in counts
        ])
    }


def _weighted_round_summary(samples, positions, context_weights):
    total_weight = sum(context_weights[draft_id]["weight"] for draft_id, _ in samples)
    return {
        "draft_count": len(samples),
        "draft_weight": round(total_weight, 4),
        "positions": {
            position: (
                round(sum(
                    counts[position] * context_weights[draft_id]["weight"]
                    for draft_id, counts in samples
                ) / total_weight, 3)
                if total_weight else None
            )
            for position in positions
        },
    }


def _position_timing(first_positions_by_draft, context_weights, positions):
    sample_weight = sum(context["weight"] for context in context_weights.values())
    result = {}
    for position in positions:
        selected = {
            draft_id: first_rounds[position]
            for draft_id, first_rounds in first_positions_by_draft.items()
            if position in first_rounds
        }
        weighted_rounds = Counter()
        for draft_id, round_number in selected.items():
            weighted_rounds[round_number] += context_weights[draft_id]["weight"]
        result[position] = {
            "selected_drafts": len(selected),
            "not_selected_drafts": len(first_positions_by_draft) - len(selected),
            "first_round_counts": dict(sorted(Counter(selected.values()).items())),
            "sample_weight": round(sample_weight, 4),
            "selected_weight": round(sum(
                context_weights[draft_id]["weight"] for draft_id in selected
            ), 4),
            "weighted_first_rounds": {
                str(round_number): round(weight, 4)
                for round_number, weight in sorted(weighted_rounds.items())
            },
        }
    return result


def _rb_shape(counts):
    if counts["RB"] == 0:
        return "zero_rb"
    if counts["RB"] == 1:
        return "hero_rb"
    return "heavy_rb"


def _context_weight(draft, target_season, target_scoring_type, target_team_count):
    if draft.scoring_type is None or draft.team_count is None:
        raise ValueError(f"Draft {draft.draft_id} lacks context required for weighting")
    season_delta = target_season - draft.season
    if season_delta < 0:
        raise ValueError(f"Draft {draft.draft_id} is newer than the target season")

    # ponytail: transparent V1 heuristic; tune only after draft-level backtests exist.
    season_weight = {0: 1.0, 1: 0.35, 2: 0.15}.get(season_delta, 0.0)
    scoring_weight = 1.0 if draft.scoring_type == target_scoring_type else 0.5
    team_count_weight = min(draft.team_count, target_team_count) / max(
        draft.team_count, target_team_count
    )
    return {
        "season": draft.season,
        "scoring_type": draft.scoring_type,
        "team_count": draft.team_count,
        "season_weight": season_weight,
        "scoring_weight": scoring_weight,
        "team_count_weight": round(team_count_weight, 4),
        "weight": round(season_weight * scoring_weight * team_count_weight, 4),
    }


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
