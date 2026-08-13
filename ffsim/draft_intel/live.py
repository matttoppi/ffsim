"""One-click draft preparation and live recommendation calculations."""

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from urllib.parse import quote, urlparse

from ffsim.config import AppConfig, save_league_attachment
from ffsim.draft_intel.decision import (
    evaluate_candidates,
    merge_evaluations,
    recommendation_summary,
)
from ffsim.draft_intel.history import load_history, summarize_history
from ffsim.draft_intel.identity import canonical_players_from_cache
from ffsim.draft_intel.market import refresh_fantasypros_adp
from ffsim.draft_intel.market_model import (
    load_league_market_snapshot,
    resolve_draft_market_context,
    sleeper_adp_choice,
    sleeper_adp_model_version,
    sleeper_adp_utilities,
)
from ffsim.draft_intel.mock import sync_sleeper_draft
from ffsim.draft_intel.storage import load_sleeper_identity_map, store_history
from ffsim.loaders.league import _fetch_json, league_and_drafts, refresh_league
from ffsim.loaders.players import PlayerLoader
from ffsim.models.league import League
from ffsim.paths import CACHE_DIR
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.simulation.season import refresh_matchups
from ffsim.simulation.world_bank import build_season_world_bank, draftable_players


@dataclass(frozen=True)
class PreparedDraft:
    summary: dict
    live_draft_id: str
    league_id: str | None
    standalone: bool
    user_roster_id: int | None
    market_snapshot: dict | None
    evaluator: LeagueEvaluator | None
    player_details: dict


def prepare_draft(
    config_path,
    draft_id,
    username,
    *,
    mock_draft_id=None,
    season=2026,
    world_count=50,
    progress=None,
):
    """Refresh every input needed by one live draft session."""
    progress = progress or (lambda stage: None)
    draft_id = _draft_id(draft_id, "Real draft")
    mock_draft_id = _draft_id(mock_draft_id, "Mock draft", required=False)
    username = _required_id(username, "Sleeper username")

    progress("Resolving Sleeper draft and user")
    draft = _fetch_json(f"draft/{draft_id}")
    if not isinstance(draft, dict) or str(draft.get("draft_id")) != draft_id:
        raise ValueError(f"Sleeper returned the wrong draft for {draft_id}")
    league_id = _optional_id(draft.get("league_id"))
    if league_id is None:
        raise ValueError("The real draft ID must belong to a Sleeper league")
    league, drafts = league_and_drafts(league_id)
    if not any(str(candidate.get("draft_id")) == draft_id for candidate in drafts):
        raise ValueError(f"Draft {draft_id} does not belong to league {league_id}")
    user = _fetch_json(f"user/{quote(username, safe='')}")
    if not isinstance(user, dict) or not user.get("user_id"):
        raise ValueError(f"Sleeper user not found: {username}")
    user_id = str(user["user_id"])
    league_users = _fetch_json(f"league/{league_id}/users")
    if not isinstance(league_users, list) or user_id not in {
        str(member.get("user_id")) for member in league_users
    }:
        raise ValueError(f"Sleeper user {username} is not a member of league {league_id}")
    config = save_league_attachment(config_path, league_id, draft_id)

    progress("Refreshing league, draft, stale players, and schedule")
    refresh_league(league_id, draft_id)
    player_loader = PlayerLoader()
    projection_refresh = player_loader.refresh_if_stale(season=season)
    refresh_matchups(league_id, config.regular_season_weeks + 3)

    progress("Crawling and deduplicating league-mate history")
    history_summary = _refresh_history(league_id, season)

    progress("Refreshing stale ADP boards")
    market_refresh = refresh_fantasypros_adp(
        season=season,
        sleeper_players_path=player_loader.sleeper_players_file,
    )

    progress("Validating live draft source")
    snapshot = json.loads((CACHE_DIR / f"league_{league_id}.json").read_text())
    league = snapshot["league"]
    draft = snapshot["draft"]
    user_roster_id = next(
        (
            int(roster["roster_id"])
            for roster in snapshot.get("rosters") or ()
            if str(roster.get("owner_id")) == user_id
            or user_id in map(str, roster.get("co_owners") or ())
        ),
        None,
    )
    user_slot = next(
        (
            int(slot)
            for slot, roster_id in (draft.get("slot_to_roster_id") or {}).items()
            if user_roster_id is not None and int(roster_id) == user_roster_id
        ),
        None,
    )

    mock_draft = None
    mock_user_roster_id = None
    mismatch = []
    if mock_draft_id:
        mock_draft = sync_sleeper_draft(
            mock_draft_id,
            standalone=True,
        ).draft
        mismatch = mock_mismatch_reasons(draft, mock_draft)
        mock_user_slot = _manager_slot(mock_draft, user_id)
        mock_user_roster_id = (
            (mock_draft.get("slot_to_roster_id") or {}).get(str(mock_user_slot))
            if mock_user_slot is not None
            else None
        )
        mock_user_roster_id = (
            int(mock_user_roster_id) if mock_user_roster_id is not None else None
        )
        if mock_user_slot != user_slot:
            mismatch.append({
                "code": "mock_user_slot_mismatch",
                "label": "user slot",
                "expected": user_slot,
                "actual": mock_user_slot,
            })

    market = load_league_market_snapshot(league, season=season)
    live_market_snapshot = _live_market_snapshot(market["snapshot"])
    compatibility = snapshot["draft_summary"]["compatibility"]
    blockers = [
        reason["code"]
        for capability in ("draft_replay", "draft_rollout", "season_evaluation")
        for reason in compatibility["capabilities"][capability]["reasons"]
    ]
    if market["snapshot"] is None:
        blockers.append("compatible_market_snapshot_missing")
    elif not (live_market_snapshot.get("observations") or ()):
        blockers.append("market_player_identity_missing")
    if user_roster_id is None:
        blockers.append("user_roster_missing")
    blockers.extend(reason["code"] for reason in mismatch)

    evaluator = None
    bank = None
    if not blockers:
        progress("Building coupled season worlds")
        player_loader.load_players()
        league_model = League(league)
        live_draft = mock_draft or draft
        live_roster_by_slot = {
            int(slot): int(roster_id)
            for slot, roster_id in (live_draft.get("slot_to_roster_id") or {}).items()
        }
        real_slot_by_roster = {
            int(roster_id): int(slot)
            for slot, roster_id in (draft.get("slot_to_roster_id") or {}).items()
        }
        for roster in snapshot.get("rosters") or ():
            division = (roster.get("settings") or {}).get("division")
            if division is not None:
                league_model.divisions.setdefault(int(division), []).append(
                    live_roster_by_slot[real_slot_by_roster[int(roster["roster_id"])]]
                )
        bank = build_season_world_bank(
            league_model,
            draftable_players(player_loader.enriched_players),
            world_count,
            weeks=config.regular_season_weeks + 3,
            seed=config.seed,
        )
        evaluator = LeagueEvaluator(
            league_model,
            bank,
            live_roster_by_slot.values(),
            config.regular_season_weeks,
            seed=config.seed,
        )

    live_user_roster_id = (
        mock_user_roster_id if mock_draft is not None else user_roster_id
    )
    if live_user_roster_id is None:
        blockers.append("live_user_slot_missing")
    if evaluator is None:
        blockers.append("season_worlds_unavailable")
    blockers = list(dict.fromkeys(blockers))
    player_details = _player_details(player_loader.sleeper_players_file)
    relevant_managers = [
        manager
        for manager in history_summary["managers"]
        if manager["included_same_season"] or manager["included_prior_seasons"]
    ]
    summary = {
        "status": "ready",
        "league_id": league_id,
        "draft_id": draft_id,
        "mock_draft_id": mock_draft_id,
        "live_draft_id": mock_draft_id or draft_id,
        "league_name": league.get("name"),
        "draft_status": draft.get("status"),
        "draft_type": draft.get("type"),
        "teams": (draft.get("settings") or {}).get("teams"),
        "rounds": (draft.get("settings") or {}).get("rounds"),
        "user_id": user_id,
        "user_slot": user_slot,
        "user_roster_id": user_roster_id,
        "live_user_roster_id": live_user_roster_id,
        "market_context": market["context"],
        "market_snapshot_id": (
            market["snapshot"].get("snapshot_id") if market["snapshot"] else None
        ),
        "market_players": (
            len(market["snapshot"].get("observations") or ())
            if market["snapshot"]
            else 0
        ),
        "adp_fetched_contexts": market_refresh["fetched_contexts"],
        "projection_refresh": projection_refresh,
        "history": {
            "managers": len(history_summary["managers"]),
            "managers_with_eligible_history": len(relevant_managers),
            "draft_discoveries": history_summary["draft_discoveries"],
            "unique_drafts": history_summary["unique_drafts"],
            "duplicate_discoveries_removed": history_summary[
                "duplicate_discoveries_removed"
            ],
            "model_eligible_picks": history_summary["model_eligible_picks"],
        },
        "mock_compatibility": {
            "status": "not_used" if mock_draft is None else ("exact" if not mismatch else "mismatch"),
            "reasons": mismatch,
        },
        "world_bank": {
            "version": bank.version if bank else None,
            "worlds": bank.world_count if bank else 0,
            "players": len(bank.player_ids) if bank else 0,
        },
        "monitor_ready": not blockers,
        "blockers": blockers,
    }
    progress("Ready")
    return PreparedDraft(
        summary=summary,
        live_draft_id=mock_draft_id or draft_id,
        league_id=None if mock_draft_id else league_id,
        standalone=mock_draft_id is not None,
        user_roster_id=live_user_roster_id,
        market_snapshot=live_market_snapshot,
        evaluator=evaluator,
        player_details=player_details,
    )


def sync_prepared_draft(prepared, *, refresh_metadata=True):
    return sync_sleeper_draft(
        prepared.live_draft_id,
        league_id=prepared.league_id,
        standalone=prepared.standalone,
        refresh_metadata=refresh_metadata,
    )


def live_state_summary(prepared, state):
    user_roster_id = prepared.user_roster_id
    turn = state.turn_for(user_roster_id) if user_roster_id is not None else None
    details = prepared.player_details
    return {
        "draft_id": state.draft_id,
        "draft_status": state.status,
        "completed_picks": len(state.completed_picks),
        "recent_picks": [
            {
                "pick_no": pick.pick_no,
                "round": pick.round,
                "draft_slot": pick.draft_slot,
                "roster_id": pick.roster_id,
                "player_id": pick.player_id,
                "name": details.get(pick.player_id, {}).get("name", pick.player_id),
                "position": pick.position
                or details.get(pick.player_id, {}).get("position"),
                "team": details.get(pick.player_id, {}).get("team"),
            }
            for pick in state.completed_picks
        ],
        "current_pick_no": state.current_pick_no,
        "current_roster_id": state.current_roster_id,
        "user_roster_id": user_roster_id,
        "user_on_clock": state.current_roster_id == user_roster_id,
        "user_next_pick_no": turn.user_next_pick_no if turn else None,
        "opponent_picks_until_next": (
            len(turn.opponent_roster_ids_until_next) if turn else None
        ),
    }


def live_candidate_pool(prepared, state, breadth):
    """Order candidates as an ADP window expanding around the current pick.

    The head covers the best market player per position (so no single
    position can monopolize the board), then candidates step outward from
    the current pick number in both ADP directions.
    """
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("Prepared draft is missing market or season inputs")
    board = sleeper_adp_utilities(prepared.market_snapshot)
    bank_players = set(prepared.evaluator.bank.player_ids)
    pool = state.available_player_ids & board.keys() & bank_players
    if not pool:
        raise ValueError("No available market players can be evaluated")
    anchor = state.current_pick_no or 1
    adp = {player_id: math.exp(-board[player_id]) for player_id in pool}
    by_distance = sorted(
        pool,
        key=lambda player_id: (abs(adp[player_id] - anchor), adp[player_id], player_id),
    )
    positions = set()
    diverse = []
    for player_id in sorted(pool, key=lambda player_id: (-board[player_id], player_id)):
        position = prepared.player_details.get(player_id, {}).get("position")
        if position not in positions:
            positions.add(position)
            diverse.append(player_id)
    return list(dict.fromkeys(diverse + by_distance))[:breadth]


def evaluate_live_candidates(prepared, state, rollout_count, candidate_ids):
    if state.current_roster_id != prepared.user_roster_id:
        raise ValueError("Live recommendations require the user on the clock")
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("Prepared draft is missing market or season inputs")
    bank_players = set(prepared.evaluator.bank.player_ids)
    snapshot = {
        **prepared.market_snapshot,
        "observations": [
            observation
            for observation in prepared.market_snapshot.get("observations") or ()
            if str(observation.get("canonical_player_id")) in bank_players
        ],
    }
    choose = sleeper_adp_choice(snapshot)
    return evaluate_candidates(
        state,
        candidate_ids,
        prepared.user_roster_id,
        range(rollout_count),
        choose,
        choose,
        prepared.evaluator,
        draft_model_version=sleeper_adp_model_version(snapshot),
        survival_player_ids=candidate_ids,
    )


def live_recommendation_payload(prepared, evaluations, candidate_pool_count):
    evaluation = merge_evaluations(evaluations)
    recommendation = asdict(recommendation_summary(evaluation))
    ranked = sorted(
        evaluation.candidates,
        key=lambda candidate: (
            -candidate.championship_probability,
            -candidate.playoff_probability,
            -candidate.expected_wins,
            candidate.candidate_id,
        ),
    )
    recommendation["candidates"] = [
        {
            "player_id": candidate.candidate_id,
            "name": prepared.player_details.get(candidate.candidate_id, {}).get(
                "name", candidate.candidate_id
            ),
            "position": prepared.player_details.get(candidate.candidate_id, {}).get(
                "position"
            ),
            "championship_probability": candidate.championship_probability,
            "playoff_probability": candidate.playoff_probability,
            "expected_wins": candidate.expected_wins,
        }
        for candidate in ranked
    ]
    recommendation["model_status"] = "uncalibrated_sleeper_adp_baseline"
    recommendation["pick_no"] = evaluation.state_pick_no
    recommendation["candidates_evaluated"] = len(evaluation.candidates)
    recommendation["candidate_pool"] = candidate_pool_count
    return recommendation


def mock_mismatch_reasons(real_draft, mock_draft):
    real_settings = real_draft.get("settings") or {}
    mock_settings = mock_draft.get("settings") or {}
    reasons = []
    real_league_id = _optional_id(real_draft.get("league_id"))
    mock_metadata = mock_draft.get("metadata") or {}
    mock_link = {
        "type": mock_metadata.get("type"),
        "league_id": _optional_id(mock_metadata.get("league_id")),
    }
    expected_link = {"type": "league_mock", "league_id": real_league_id}
    if mock_link != expected_link:
        reasons.append({
            "code": "mock_league_link_mismatch",
            "label": "league-created mock",
            "expected": expected_link,
            "actual": mock_link,
        })
    for code, label, expected, actual in (
        ("mock_draft_type_mismatch", "draft type", real_draft.get("type"), mock_draft.get("type")),
        ("mock_team_count_mismatch", "team count", real_settings.get("teams"), mock_settings.get("teams")),
        ("mock_round_count_mismatch", "round count", real_settings.get("rounds"), mock_settings.get("rounds")),
        (
            "mock_reversal_round_mismatch",
            "reversal round",
            int(real_settings.get("reversal_round") or 0),
            int(mock_settings.get("reversal_round") or 0),
        ),
    ):
        if expected != actual:
            reasons.append({"code": code, "label": label, "expected": expected, "actual": actual})
    real_slots = _draft_slots(real_settings)
    mock_slots = _draft_slots(mock_settings)
    if real_slots != mock_slots:
        reasons.append({
            "code": "mock_roster_slots_mismatch",
            "label": "roster slots",
            "expected": real_slots,
            "actual": mock_slots,
        })
    real_market = resolve_draft_market_context(real_draft)
    mock_market = resolve_draft_market_context(mock_draft)
    expected_market = (real_market.get("league_format"), real_market.get("scoring"))
    actual_market = (mock_market.get("league_format"), mock_market.get("scoring"))
    if expected_market != actual_market:
        reasons.append({
            "code": "mock_market_context_mismatch",
            "label": "market context",
            "expected": "/".join(value or "unsupported" for value in expected_market),
            "actual": "/".join(value or "unsupported" for value in actual_market),
        })
    return reasons


def _refresh_history(league_id, season):
    players_path = CACHE_DIR / "players.json"
    canonical_players = canonical_players_from_cache(json.loads(players_path.read_text()))
    player_ids = load_sleeper_identity_map()
    player_ids.update({
        player.sleeper_id: player.canonical_player_id
        for player in canonical_players
    })
    raw_responses = {}
    history = load_history(
        league_id,
        range(season, season - 3, -1),
        canonical_player_ids=player_ids,
        raw_responses=raw_responses,
    )
    summary = summarize_history(history, season)
    summary["storage"] = store_history(history, raw_responses, canonical_players)
    return summary


def _player_details(path):
    players = json.loads(Path(path).read_text())
    return {
        str(player_id): {
            "name": player.get("full_name") or player.get("first_name") or str(player_id),
            "position": player.get("position"),
            "team": player.get("team"),
        }
        for player_id, player in players.items()
    }


def _live_market_snapshot(snapshot):
    if snapshot is None:
        return None
    raw_by_canonical = {
        canonical_id: sleeper_id
        for sleeper_id, canonical_id in load_sleeper_identity_map().items()
    }
    observations = [
        {**observation, "canonical_player_id": raw_by_canonical[canonical_id]}
        for observation in snapshot.get("observations") or ()
        if (canonical_id := str(observation.get("canonical_player_id") or ""))
        in raw_by_canonical
    ]
    return {**snapshot, "observations": observations}


def _draft_slots(settings):
    return {
        key.removeprefix("slots_"): int(value)
        for key, value in settings.items()
        if key.startswith("slots_") and int(value) > 0
    }


def _manager_slot(draft, manager_id):
    raw_slot = (draft.get("draft_order") or {}).get(str(manager_id))
    if raw_slot is None:
        return None
    try:
        return int(raw_slot)
    except (TypeError, ValueError):
        raise ValueError(f"Sleeper returned an invalid draft slot for user {manager_id}") from None


def _required_id(value, label):
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"{label} is required")
    return value


def _optional_id(value):
    value = str(value or "").strip()
    return value or None


def _draft_id(value, label, *, required=True):
    value = str(value or "").strip()
    if not value:
        if required:
            raise ValueError(f"{label} ID or URL is required")
        return None
    if value.isdigit():
        return value
    parsed = urlparse(value)
    parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.casefold() in {"sleeper.app", "www.sleeper.app"}
        and len(parts) == 3
        and parts[:2] == ["draft", "nfl"]
        and parts[2].isdigit()
    ):
        return parts[2]
    raise ValueError(f"{label} must be a Sleeper draft ID or draft URL")
