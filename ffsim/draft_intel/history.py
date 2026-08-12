from collections import Counter, defaultdict
from dataclasses import dataclass, replace

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
    season_type: str | None
    status: str
    draft_type: str
    scoring_type: str | None
    teams: int | None
    rounds: int | None
    player_type: int | None
    roster_slots: tuple[tuple[str, int], ...]
    created_at: int | None
    start_time: int | None
    last_picked_at: int | None
    draft_order: tuple[tuple[str, int], ...]
    slot_to_roster_id: tuple[tuple[int, int], ...]
    manager_ids: tuple[str, ...]
    exclusion_reasons: tuple[str, ...] = ()

    @property
    def included(self):
        return not self.exclusion_reasons


@dataclass(frozen=True)
class HistoricalPick:
    draft_id: str
    pick_no: int
    round: int | None
    draft_slot: int | None
    roster_id: int | None
    manager_id: str | None
    player_id: str
    canonical_player_id: str | None
    position: str | None
    is_keeper: bool | None


@dataclass(frozen=True)
class DraftHistory:
    managers: tuple[Manager, ...]
    drafts: tuple[HistoricalDraft, ...]
    picks: tuple[HistoricalPick, ...]
    draft_discoveries: int


def load_history(
    league_id,
    seasons,
    fetch_json=None,
    canonical_player_ids=(),
    raw_responses=None,
):
    source_fetch = fetch_json or _fetch_json

    def fetch_json(path):
        payload = source_fetch(path)
        if raw_responses is not None:
            raw_responses[path] = payload
        return payload

    canonical_player_ids = {
        str(source_id): str(canonical_id)
        for source_id, canonical_id in dict(canonical_player_ids).items()
    }
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
        draft = _normalize_draft(raw_draft, manager_ids_by_draft[draft_id])
        draft_picks = []
        for raw_pick in fetch_json(f"draft/{draft_id}/picks"):
            pick = _normalize_pick(raw_pick, canonical_player_ids)
            if pick.draft_id != draft_id:
                raise ValueError(f"Sleeper pick {pick.pick_no} belongs to draft {pick.draft_id}, not {draft_id}")
            key = (pick.draft_id, pick.pick_no)
            if key in picks_by_key and picks_by_key[key] != pick:
                raise ValueError(f"Conflicting duplicate Sleeper pick {draft_id}/{pick.pick_no}")
            if key not in picks_by_key:
                draft_picks.append(pick)
            picks_by_key[key] = pick
        drafts.append(replace(draft, exclusion_reasons=_draft_exclusion_reasons(draft, draft_picks)))

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
        included_drafts = [draft for draft in manager_drafts if draft.included]
        manager_counts.append({
            "user_id": manager.user_id,
            "display_name": manager.display_name,
            "same_season": sum(draft.season == current_season for draft in manager_drafts),
            "prior_seasons": sum(draft.season != current_season for draft in manager_drafts),
            "included_same_season": sum(
                draft.season == current_season for draft in included_drafts
            ),
            "included_prior_seasons": sum(
                draft.season != current_season for draft in included_drafts
            ),
        })
    keeper_picks = sum(pick.is_keeper is True for pick in history.picks)
    included_draft_ids = {draft.draft_id for draft in history.drafts if draft.included}
    model_picks = tuple(
        pick for pick in history.picks
        if pick.draft_id in included_draft_ids and pick.is_keeper is not True
    )
    exclusion_reasons = Counter(
        reason for draft in history.drafts for reason in draft.exclusion_reasons
    )
    return {
        "managers": manager_counts,
        "draft_discoveries": history.draft_discoveries,
        "unique_drafts": len(history.drafts),
        "duplicate_discoveries_removed": history.draft_discoveries - len(history.drafts),
        "shared_drafts": sum(len(draft.manager_ids) > 1 for draft in history.drafts),
        "unique_picks": len(history.picks),
        "keeper_picks": keeper_picks,
        "model_eligible_picks": len(model_picks),
        "draft_classification": {
            "included": len(included_draft_ids),
            "excluded": len(history.drafts) - len(included_draft_ids),
            "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        },
        "canonical_player_coverage": {
            "method": "known_sleeper_external_id",
            "all_picks": _canonical_coverage(history.picks),
            "model_eligible_picks": _canonical_coverage(model_picks),
        },
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
        season_type=_text(draft.get("season_type")),
        status=str(draft.get("status") or "unknown"),
        draft_type=str(draft.get("type") or "unknown"),
        scoring_type=_text(metadata.get("scoring_type")),
        teams=_int(settings.get("teams")),
        rounds=_int(settings.get("rounds")),
        player_type=_int(settings.get("player_type")),
        roster_slots=tuple(sorted(
            (key.removeprefix("slots_"), int(value))
            for key, value in settings.items()
            if key.startswith("slots_") and _int(value) is not None
        )),
        created_at=_int(draft.get("created")),
        start_time=_int(draft.get("start_time")),
        last_picked_at=_int(draft.get("last_picked")),
        draft_order=tuple(sorted(
            (manager_id, slot)
            for raw_manager_id, raw_slot in (draft.get("draft_order") or {}).items()
            if (manager_id := _text(raw_manager_id)) is not None
            and (slot := _int(raw_slot)) is not None
        )),
        slot_to_roster_id=tuple(sorted(
            (slot, roster_id)
            for raw_slot, raw_roster_id in (draft.get("slot_to_roster_id") or {}).items()
            if (slot := _int(raw_slot)) is not None
            and (roster_id := _int(raw_roster_id)) is not None
        )),
        manager_ids=tuple(sorted(manager_ids)),
    )


def _normalize_pick(pick, canonical_player_ids):
    metadata = pick.get("metadata") or {}
    player_id = _required_text(pick, "player_id")
    return HistoricalPick(
        draft_id=_required_text(pick, "draft_id"),
        pick_no=_required_int(pick, "pick_no"),
        round=_int(pick.get("round")),
        draft_slot=_int(pick.get("draft_slot")),
        roster_id=_int(pick.get("roster_id")),
        manager_id=_text(pick.get("picked_by")),
        player_id=player_id,
        canonical_player_id=canonical_player_ids.get(player_id),
        position=_text(metadata.get("position")),
        is_keeper=pick.get("is_keeper") if isinstance(pick.get("is_keeper"), bool) else None,
    )


def _draft_exclusion_reasons(draft, picks):
    reasons = []
    if draft.status != "complete":
        reasons.append("not_complete")
    if draft.draft_type == "auction":
        reasons.append("auction")
    elif draft.draft_type != "snake":
        reasons.append("non_snake")

    scoring_type = (draft.scoring_type or "").casefold()
    if not scoring_type:
        reasons.append("unknown_scoring")
    if "dynasty" in scoring_type:
        reasons.append("dynasty")
    if "idp" in scoring_type:
        reasons.append("idp")
    if draft.status == "complete" and not picks:
        reasons.append("no_picks")
    return tuple(reasons)


def _canonical_coverage(picks):
    matched = [pick for pick in picks if pick.canonical_player_id is not None]
    source_player_ids = {pick.player_id for pick in picks}
    matched_source_ids = {pick.player_id for pick in matched}
    return {
        "matched_picks": len(matched),
        "total_picks": len(picks),
        "pick_match_rate": round(len(matched) / len(picks), 4) if picks else None,
        "matched_players": len(matched_source_ids),
        "total_players": len(source_player_ids),
        "player_match_rate": (
            round(len(matched_source_ids) / len(source_player_ids), 4)
            if source_player_ids else None
        ),
    }


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
