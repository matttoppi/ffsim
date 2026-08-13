"""Standalone Sleeper mock attachment and append-only refresh."""

from datetime import datetime, timezone
import json
from pathlib import Path

from ffsim.draft_intel.market_model import resolve_draft_market_context
from ffsim.draft_intel.state import reconcile_sleeper_draft, replay_sleeper_draft
from ffsim.draft_intel.storage import _atomic_write
from ffsim.loaders.league import _fetch_json
from ffsim.paths import CACHE_DIR


def attach_mock_draft(draft_id, *, fetch_json=None, cache_dir=None, player_ids=None):
    draft_id = str(draft_id).strip()
    if not draft_id:
        raise ValueError("Sleeper mock draft ID is required")
    fetch = fetch_json or _fetch_json
    draft = fetch(f"draft/{draft_id}")
    picks = fetch(f"draft/{draft_id}/picks")
    traded_picks = fetch(f"draft/{draft_id}/traded_picks")
    _validate_mock_payload(draft_id, draft, picks, traded_picks)

    cache_dir = Path(cache_dir or CACHE_DIR)
    path = cache_dir / f"mock_draft_{draft_id}.json"
    player_ids = tuple(
        _cached_player_ids(cache_dir) if player_ids is None else player_ids
    )
    if path.exists():
        previous_payload = json.loads(path.read_text())
        previous = replay_sleeper_draft(
            previous_payload["draft"],
            previous_payload["picks"],
            previous_payload["traded_picks"],
            player_ids,
        )
        state = reconcile_sleeper_draft(previous, draft, picks, traded_picks, player_ids)
    else:
        state = replay_sleeper_draft(draft, picks, traded_picks, player_ids)

    context = resolve_draft_market_context(draft)
    creator_ids = tuple(str(value) for value in draft.get("creators") or ())
    user_roster_id = _user_roster_id(state, creator_ids)
    payload = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "draft": draft,
        "picks": picks,
        "traded_picks": traded_picks,
    }
    _atomic_write(path, (json.dumps(payload, indent=2) + "\n").encode())
    attachment_path = cache_dir / "draft_intel" / "mock_attachment.json"
    _atomic_write(
        attachment_path,
        (json.dumps({"draft_id": draft_id}, indent=2) + "\n").encode(),
    )
    return {
        "draft_id": draft_id,
        "status": state.status,
        "draft_type": state.draft_type,
        "teams": state.teams,
        "rounds": state.rounds,
        "completed_picks": len(state.completed_picks),
        "current_pick_no": state.current_pick_no,
        "creator_ids": list(creator_ids),
        "user_roster_id": user_roster_id,
        "market_context": context,
        "cache_path": str(path),
    }


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


def _validate_mock_payload(draft_id, draft, picks, traded_picks):
    if not isinstance(draft, dict) or str(draft.get("draft_id")) != draft_id:
        raise ValueError(f"Sleeper returned the wrong draft for {draft_id}")
    if draft.get("league_id") is not None:
        raise ValueError("Use normal league attachment for a league-backed draft")
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
