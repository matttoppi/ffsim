"""Standalone Sleeper mock attachment and append-only refresh."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from ffsim.draft_intel.market_model import resolve_draft_market_context
from ffsim.draft_intel.state import reconcile_sleeper_draft, replay_sleeper_draft
from ffsim.draft_intel.storage import _atomic_write
from ffsim.loaders.league import _fetch_json
from ffsim.paths import CACHE_DIR


@dataclass(frozen=True)
class DraftSync:
    state: object
    draft: dict
    cache_path: Path


def attach_mock_draft(draft_id, *, fetch_json=None, cache_dir=None, player_ids=None):
    cache_dir = Path(cache_dir or CACHE_DIR)
    sync = sync_sleeper_draft(
        draft_id,
        standalone=True,
        fetch_json=fetch_json,
        cache_dir=cache_dir,
        player_ids=player_ids,
    )
    draft_id = sync.state.draft_id
    context = resolve_draft_market_context(sync.draft)
    creator_ids = tuple(str(value) for value in sync.draft.get("creators") or ())
    user_roster_id = _user_roster_id(sync.state, creator_ids)
    attachment_path = cache_dir / "draft_intel" / "mock_attachment.json"
    _atomic_write(
        attachment_path,
        (json.dumps({"draft_id": draft_id}, indent=2) + "\n").encode(),
    )
    return {
        "draft_id": draft_id,
        "status": sync.state.status,
        "draft_type": sync.state.draft_type,
        "teams": sync.state.teams,
        "rounds": sync.state.rounds,
        "completed_picks": len(sync.state.completed_picks),
        "current_pick_no": sync.state.current_pick_no,
        "creator_ids": list(creator_ids),
        "user_roster_id": user_roster_id,
        "market_context": context,
        "cache_path": str(sync.cache_path),
    }


def sync_sleeper_draft(
    draft_id,
    *,
    league_id=None,
    standalone=False,
    fetch_json=None,
    cache_dir=None,
    player_ids=None,
    refresh_metadata=True,
):
    draft_id = str(draft_id).strip()
    if not draft_id:
        raise ValueError("Sleeper draft ID is required")
    fetch = fetch_json or _fetch_json
    cache_dir = Path(cache_dir or CACHE_DIR)
    prefix = "mock_draft" if standalone else "live_draft"
    path = cache_dir / f"{prefix}_{draft_id}.json"
    previous_payload = json.loads(path.read_text()) if path.exists() else None
    refresh_metadata = refresh_metadata or previous_payload is None
    draft = (
        fetch(f"draft/{draft_id}")
        if refresh_metadata
        else previous_payload["draft"]
    )
    picks = fetch(f"draft/{draft_id}/picks")
    traded_picks = (
        fetch(f"draft/{draft_id}/traded_picks")
        if refresh_metadata
        else previous_payload["traded_picks"]
    )
    _validate_draft_payload(draft_id, draft, picks, traded_picks, league_id, standalone)

    player_ids = tuple(
        _cached_player_ids(cache_dir) if player_ids is None else player_ids
    )
    state_picks = _standalone_state_picks(draft, picks, traded_picks) if standalone else picks
    if previous_payload is not None:
        previous_picks = (
            _standalone_state_picks(
                previous_payload["draft"],
                previous_payload["picks"],
                previous_payload["traded_picks"],
            )
            if standalone
            else previous_payload["picks"]
        )
        previous = replay_sleeper_draft(
            previous_payload["draft"],
            previous_picks,
            previous_payload["traded_picks"],
            player_ids,
        )
        state = reconcile_sleeper_draft(
            previous,
            draft,
            state_picks,
            traded_picks,
            player_ids,
        )
    else:
        state = replay_sleeper_draft(draft, state_picks, traded_picks, player_ids)

    payload = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "draft": draft,
        "picks": picks,
        "traded_picks": traded_picks,
    }
    _atomic_write(path, (json.dumps(payload, indent=2) + "\n").encode())
    return DraftSync(state, draft, path)


def _standalone_state_picks(draft, picks, traded_picks):
    """Supply ownership Sleeper omits from snake/linear league mocks."""
    if draft.get("type") not in {"snake", "linear"}:
        return picks
    roster_by_slot = {
        int(slot): int(roster_id)
        for slot, roster_id in (draft.get("slot_to_roster_id") or {}).items()
    }
    traded = {
        (int(pick["round"]), int(pick["roster_id"])): int(pick["owner_id"])
        for pick in traded_picks
    }
    return [
        {
            **pick,
            "roster_id": traded.get(
                (int(pick["round"]), roster_by_slot[int(pick["draft_slot"])]),
                roster_by_slot[int(pick["draft_slot"])],
            ),
        }
        if pick.get("roster_id") is None
        else pick
        for pick in picks
    ]


def refresh_attached_mock(*, fetch_json=None, cache_dir=None, player_ids=None):
    cache_dir = Path(cache_dir or CACHE_DIR)
    path = cache_dir / "draft_intel" / "mock_attachment.json"
    if not path.exists():
        raise FileNotFoundError("No standalone Sleeper mock is attached")
    try:
        draft_id = json.loads(path.read_text())["draft_id"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise ValueError("Standalone mock attachment is invalid") from None
    return attach_mock_draft(
        draft_id,
        fetch_json=fetch_json,
        cache_dir=cache_dir,
        player_ids=player_ids,
    )


def _cached_player_ids(cache_dir):
    path = cache_dir / "sleeper_players.json"
    if not path.exists():
        raise FileNotFoundError("Sleeper player cache is missing; run market-refresh first")
    try:
        players = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        raise ValueError("Sleeper player cache is invalid") from None
    if not isinstance(players, dict):
        raise ValueError("Sleeper player cache must contain an object")
    return players


def _validate_draft_payload(draft_id, draft, picks, traded_picks, league_id, standalone):
    if not isinstance(draft, dict) or str(draft.get("draft_id")) != draft_id:
        raise ValueError(f"Sleeper returned the wrong draft for {draft_id}")
    if standalone and draft.get("league_id") is not None:
        raise ValueError("Use normal league attachment for a league-backed draft")
    if not standalone and str(draft.get("league_id")) != str(league_id):
        raise ValueError(f"Draft {draft_id} does not belong to league {league_id}")
    if draft.get("sport") != "nfl":
        raise ValueError("Standalone mock must be an NFL draft")
    if not isinstance(picks, list) or not isinstance(traded_picks, list):
        raise ValueError("Sleeper returned invalid standalone mock pick data")
    if any(str(pick.get("draft_id")) != draft_id for pick in picks):
        raise ValueError("Sleeper returned picks from another draft")


def _user_roster_id(state, creator_ids):
    manager_rosters = dict(state.manager_roster_ids)
    rosters = {manager_rosters[value] for value in creator_ids if value in manager_rosters}
    rosters.update(
        pick.roster_id
        for pick in state.completed_picks
        if pick.picked_by in creator_ids
    )
    if len(rosters) > 1:
        raise ValueError("Standalone mock creator maps to multiple rosters")
    return next(iter(rosters), None)
