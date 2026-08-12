from collections import Counter, defaultdict
from dataclasses import dataclass

from ffsim.loaders.league import _fetch_json


@dataclass(frozen=True)
class Manager:
    user_id: str
    display_name: str


@dataclass(frozen=True)
class HistoricalDraft:
    draft_id: str
    league_id: str | None
    season: int
    status: str
    draft_type: str
    scoring_type: str | None
    teams: int | None
    rounds: int | None
    start_time: int | None
    manager_ids: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalPick:
    draft_id: str
    pick_no: int
    round: int | None
    draft_slot: int | None
    roster_id: int | None
    manager_id: str | None
    player_id: str
    position: str | None
    is_keeper: bool | None


@dataclass(frozen=True)
class DraftHistory:
    managers: tuple[Manager, ...]
    drafts: tuple[HistoricalDraft, ...]
    picks: tuple[HistoricalPick, ...]
    draft_discoveries: int


def load_history(league_id, seasons, fetch_json=None):
    fetch_json = fetch_json or _fetch_json
    seasons = tuple(dict.fromkeys(int(season) for season in seasons))
    if not seasons:
        raise ValueError("At least one history season is required")

    managers = tuple(
        sorted(
            (
                Manager(_required_text(user, "user_id"), str(user.get("display_name") or ""))
                for user in fetch_json(f"league/{league_id}/users")
            ),
            key=lambda manager: manager.user_id,
        )
    )
    manager_ids_by_draft = defaultdict(set)
    draft_ids = set()
    discoveries = 0
    for manager in managers:
        for season in seasons:
            for draft in fetch_json(f"user/{manager.user_id}/drafts/nfl/{season}"):
                draft_id = _required_text(draft, "draft_id")
                draft_ids.add(draft_id)
                manager_ids_by_draft[draft_id].add(manager.user_id)
                discoveries += 1

    drafts = []
    picks_by_key = {}
    for draft_id in sorted(draft_ids):
        raw_draft = fetch_json(f"draft/{draft_id}")
        if _required_text(raw_draft, "draft_id") != draft_id:
            raise ValueError(f"Sleeper returned the wrong draft for {draft_id}")
        drafts.append(_normalize_draft(raw_draft, manager_ids_by_draft[draft_id]))
        for raw_pick in fetch_json(f"draft/{draft_id}/picks"):
            pick = _normalize_pick(raw_pick)
            if pick.draft_id != draft_id:
                raise ValueError(f"Sleeper pick {pick.pick_no} belongs to draft {pick.draft_id}, not {draft_id}")
            key = (pick.draft_id, pick.pick_no)
            if key in picks_by_key and picks_by_key[key] != pick:
                raise ValueError(f"Conflicting duplicate Sleeper pick {draft_id}/{pick.pick_no}")
            picks_by_key[key] = pick

    return DraftHistory(
        managers=managers,
        drafts=tuple(drafts),
        picks=tuple(picks_by_key[key] for key in sorted(picks_by_key)),
        draft_discoveries=discoveries,
    )


def summarize_history(history, current_season):
    formats = Counter(
        (draft.season, draft.status, draft.draft_type, draft.scoring_type, draft.teams)
        for draft in history.drafts
    )
    manager_counts = []
    for manager in history.managers:
        manager_drafts = [draft for draft in history.drafts if manager.user_id in draft.manager_ids]
        manager_counts.append({
            "user_id": manager.user_id,
            "display_name": manager.display_name,
            "same_season": sum(draft.season == current_season for draft in manager_drafts),
            "prior_seasons": sum(draft.season != current_season for draft in manager_drafts),
        })
    keeper_picks = sum(pick.is_keeper is True for pick in history.picks)
    return {
        "managers": manager_counts,
        "draft_discoveries": history.draft_discoveries,
        "unique_drafts": len(history.drafts),
        "duplicate_discoveries_removed": history.draft_discoveries - len(history.drafts),
        "shared_drafts": sum(len(draft.manager_ids) > 1 for draft in history.drafts),
        "unique_picks": len(history.picks),
        "keeper_picks": keeper_picks,
        "format_breakdown": [
            {
                "season": season,
                "status": status,
                "type": draft_type,
                "scoring": scoring,
                "teams": teams,
                "drafts": count,
            }
            for (season, status, draft_type, scoring, teams), count in sorted(
                formats.items(), key=lambda item: tuple(str(value) for value in item[0])
            )
        ],
    }


def _normalize_draft(draft, manager_ids):
    settings = draft.get("settings") or {}
    metadata = draft.get("metadata") or {}
    return HistoricalDraft(
        draft_id=_required_text(draft, "draft_id"),
        league_id=_text(draft.get("league_id")),
        season=_required_int(draft, "season"),
        status=str(draft.get("status") or "unknown"),
        draft_type=str(draft.get("type") or "unknown"),
        scoring_type=_text(metadata.get("scoring_type")),
        teams=_int(settings.get("teams")),
        rounds=_int(settings.get("rounds")),
        start_time=_int(draft.get("start_time")),
        manager_ids=tuple(sorted(manager_ids)),
    )


def _normalize_pick(pick):
    metadata = pick.get("metadata") or {}
    return HistoricalPick(
        draft_id=_required_text(pick, "draft_id"),
        pick_no=_required_int(pick, "pick_no"),
        round=_int(pick.get("round")),
        draft_slot=_int(pick.get("draft_slot")),
        roster_id=_int(pick.get("roster_id")),
        manager_id=_text(pick.get("picked_by")),
        player_id=_required_text(pick, "player_id"),
        position=_text(metadata.get("position")),
        is_keeper=pick.get("is_keeper") if isinstance(pick.get("is_keeper"), bool) else None,
    )


def _required_text(data, key):
    value = _text(data.get(key))
    if value is None:
        raise ValueError(f"Sleeper payload is missing {key}")
    return value


def _required_int(data, key):
    value = _int(data.get(key))
    if value is None:
        raise ValueError(f"Sleeper payload is missing integer {key}")
    return value


def _text(value):
    return None if value is None or str(value) == "" else str(value)


def _int(value):
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None
