"""One-click draft preparation and live recommendation calculations."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field, replace
import json
from math import exp
import os
from pathlib import Path
from urllib.parse import quote, urlparse

from ffsim.config import AppConfig, save_league_attachment
from ffsim.draft_intel.decision import (
    evaluate_candidates,
    evaluate_league_equity,
    merge_evaluations,
    merge_rollout_ranges,
    rank_candidates,
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
    roster_details: dict = field(default_factory=dict)


def prepare_draft(
    config_path,
    draft_id,
    username,
    *,
    mock_draft_id=None,
    season=2026,
    world_count=300,
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

    live_user_roster_id = (
        mock_user_roster_id if mock_draft is not None else user_roster_id
    )

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

    live_draft = mock_draft or draft
    live_roster_by_slot = {
        int(slot): int(roster_id)
        for slot, roster_id in (live_draft.get("slot_to_roster_id") or {}).items()
    }
    real_roster_by_slot = {
        int(slot): int(roster_id)
        for slot, roster_id in (draft.get("slot_to_roster_id") or {}).items()
    }
    roster_details = _roster_details(
        live_roster_by_slot,
        real_roster_by_slot,
        snapshot.get("rosters") or (),
        league_users,
        live_user_roster_id,
    )
    evaluator = None
    bank = None
    if not blockers:
        progress("Building coupled season worlds")
        player_loader.load_players()
        league_model = League(league)
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
        roster_details=roster_details,
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
    """Order candidates best-player-available by market ADP.

    The head is simply the best remaining players (fallers first), and the
    expanding window walks deeper down the board; the UI filters positions.
    """
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("Prepared draft is missing market or season inputs")
    board = sleeper_adp_utilities(prepared.market_snapshot)
    bank_players = set(prepared.evaluator.bank.player_ids)
    pool = state.available_player_ids & board.keys() & bank_players
    if not pool:
        raise ValueError("No available market players can be evaluated")
    return sorted(
        pool, key=lambda player_id: (-board[player_id], player_id)
    )[:breadth]


# Softmax temperature fitted by maximum likelihood on 286 observed non-user
# picks from this league's Sleeper mocks (2026-08-13); see the ledger. It is
# provisional evidence, refit as real human drafts accumulate.
LIVE_TEMPERATURE = 0.11
# Share of opponent picks drawn from the broad reach component instead of the
# sharp board-follower (ADR-019). The mock rooms that fit the temperature are
# bot-heavy and cannot show human reach/need picks, so the pure sharp model
# assigns near-zero probability to the snipes that actually cost drafts.
# ponytail: 0.15 is a prior, not a fit; refit with the temperature once real
# human draft picks accumulate in the history store.
LIVE_REACH_RATE = 0.15
# Season worlds per continuation: outcome resolution is cheap relative to
# continuation sampling, so take three coupled worlds per draft path.
LIVE_SEASON_WORLDS_PER_ROLLOUT = 3
# Benchmarked on the M5 Max (12 P-cores): 4 workers left half the achievable
# throughput unused, 12 was 2.3x faster end-to-end, and 16 gained nothing.
LIVE_EVALUATION_WORKERS = min(12, max(1, (os.cpu_count() or 4) - 2))

_WORKER = {}


def _bank_market_snapshot(prepared):
    bank_players = set(prepared.evaluator.bank.player_ids)
    return {
        **prepared.market_snapshot,
        "observations": [
            observation
            for observation in prepared.market_snapshot.get("observations") or ()
            if str(observation.get("canonical_player_id")) in bank_players
        ],
    }


def _live_model_version(snapshot, temperature):
    # vor2: core starters are filled before bench depth, while K/DEF compete
    # on value once the core lineup is complete and are never duplicated.
    # reach/caps: opponents mix the sharp board-follower with occasional
    # reaches and respect positional sanity caps (ADR-019).
    return (
        f"{sleeper_adp_model_version(snapshot)}"
        f":t{temperature}:reach{LIVE_REACH_RATE}:caps:vor2"
    )


def _live_opponent_choice(snapshot, evaluator, temperature):
    """Calibrated ADP opponents with reach mixture and positional caps."""
    bank = evaluator.bank
    return sleeper_adp_choice(
        snapshot,
        temperature=temperature,
        reach_rate=LIVE_REACH_RATE,
        positions=dict(zip(bank.player_ids, bank.player_positions)),
        slot_counts=evaluator.slot_counts,
    )


def _value_over_replacement(evaluator):
    """Season projections, positions, and league-wide replacement levels."""
    from ffsim.models.team import FLEX_ELIGIBILITY

    bank = evaluator.bank
    weeks = len(bank.weeks)
    projection = {
        player_id: float(score) * weeks
        for player_id, score in zip(bank.player_ids, bank.expected_scores)
    }
    position_of = dict(zip(bank.player_ids, bank.player_positions))
    teams = len(evaluator.roster_ids)
    slots = dict(evaluator.slot_counts)
    dedicated = {
        position: count for position, count in slots.items()
        if position not in FLEX_ELIGIBILITY
    }
    by_position = {}
    for player_id, points in projection.items():
        by_position.setdefault(position_of[player_id], []).append(points)
    for points in by_position.values():
        points.sort(reverse=True)

    # League-wide starter fill: dedicated slots first, then each flex seat to
    # the best remaining eligible player; what is left defines replacement.
    taken = {position: teams * count for position, count in dedicated.items()}

    def next_projection(position):
        points = by_position.get(position, [])
        index = taken.get(position, 0)
        return points[index] if index < len(points) else float("-inf")

    for slot, count in slots.items():
        eligible = FLEX_ELIGIBILITY.get(slot)
        if not eligible:
            continue
        for _ in range(teams * count):
            best = max(sorted(eligible), key=next_projection)
            taken[best] = taken.get(best, 0) + 1
    replacement = {
        position: max(next_projection(position), 0.0)
        for position in by_position
    }
    return projection, position_of, replacement


def _projection_user_policy(evaluator):
    """Future user picks by projection over positional replacement.

    Opponents follow the calibrated market model, but the user's own later
    picks should follow this tool's valuation: value over replacement from
    the season projections, preferring players who still fill an open
    starting slot. Root candidates are forced, so this only shapes the
    simulated follow-up picks.
    """
    from ffsim.models.team import FLEX_ELIGIBILITY

    projection, position_of, replacement = _value_over_replacement(evaluator)
    slots = dict(evaluator.slot_counts)
    dedicated = {
        position: count for position, count in slots.items()
        if position not in FLEX_ELIGIBILITY
    }

    def policy(roster_id, pick_no, rosters, available):
        del pick_no
        mine = dict(rosters)[roster_id]
        counts = {}
        for player_id in mine:
            position = position_of.get(player_id)
            if position is not None:
                counts[position] = counts.get(position, 0) + 1
        open_positions = {
            position for position, count in dedicated.items()
            if position not in {"K", "DEF"} and counts.get(position, 0) < count
        }
        for slot, count in slots.items():
            eligible = FLEX_ELIGIBILITY.get(slot)
            if not eligible:
                continue
            surplus = sum(
                max(0, counts.get(position, 0) - dedicated.get(position, 0))
                for position in eligible
            )
            if surplus < count:
                open_positions.update(eligible)
        return {
            player_id: projection[player_id] - replacement.get(position_of[player_id], 0.0)
            for player_id in projection
            if player_id in available
            and (not open_positions or position_of[player_id] in open_positions)
            and not (
                position_of[player_id] in {"K", "DEF"}
                and counts.get(position_of[player_id], 0)
            )
        }

    return policy


def _evaluate_candidate_batch(
    snapshot,
    evaluator,
    user_roster_id,
    state,
    candidate_ids,
    survival_ids,
    rollout_ids,
    temperature,
):
    choose = _live_opponent_choice(snapshot, evaluator, temperature)
    return evaluate_candidates(
        state,
        candidate_ids,
        user_roster_id,
        _rollout_ids(rollout_ids),
        choose,
        _projection_user_policy(evaluator),
        evaluator,
        draft_model_version=_live_model_version(snapshot, temperature),
        survival_player_ids=survival_ids,
        # The opponent callback returns final log-probabilities with the
        # fitted temperature and reach mixture folded in, so rollouts run
        # at temperature 1.0.
        temperature=1.0,
        season_worlds_per_rollout=LIVE_SEASON_WORLDS_PER_ROLLOUT,
    )


def _init_candidate_worker(snapshot, evaluator, user_roster_id):
    _WORKER["snapshot"] = snapshot
    _WORKER["evaluator"] = evaluator
    _WORKER["user_roster_id"] = user_roster_id


def _rollout_ids(rollout_ids):
    return range(rollout_ids) if isinstance(rollout_ids, int) else rollout_ids


def _rollout_chunks(rollout_ids, size):
    """Split contiguous rollout IDs so every worker stays busy.

    Each chunk keeps the minimum two rollouts required for paired estimates.
    """
    chunks = [rollout_ids[start:start + size] for start in range(0, len(rollout_ids), size)]
    if len(chunks) > 1 and len(chunks[-1]) < 2:
        merged = len(chunks.pop()) + len(chunks[-1])
        chunks[-1] = rollout_ids[len(rollout_ids) - merged:]
    return chunks


def _evaluate_candidate_task(state, candidate_id, survival_ids, rollout_ids, temperature):
    return _evaluate_candidate_batch(
        _WORKER["snapshot"],
        _WORKER["evaluator"],
        _WORKER["user_roster_id"],
        state,
        (candidate_id,),
        survival_ids,
        rollout_ids,
        temperature,
    )


def create_live_executor(prepared, workers=LIVE_EVALUATION_WORKERS):
    """Worker processes holding the market snapshot and season evaluator."""
    return ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_candidate_worker,
        initargs=(
            _bank_market_snapshot(prepared),
            prepared.evaluator,
            prepared.user_roster_id,
        ),
    )


# Rollout-range chunk submitted per worker task: large refinement ranges are
# split so a handful of finalists still saturates every worker process.
LIVE_ROLLOUT_CHUNK = 250


def evaluate_live_candidates(
    prepared,
    state,
    rollout_count,
    candidate_ids,
    temperature=None,
    executor=None,
    survival_ids=None,
):
    if state.current_roster_id != prepared.user_roster_id:
        raise ValueError("Live recommendations require the user on the clock")
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("Prepared draft is missing market or season inputs")
    temperature = LIVE_TEMPERATURE if temperature is None else float(temperature)
    candidate_ids = tuple(candidate_ids)
    survival_ids = tuple(candidate_ids if survival_ids is None else survival_ids)
    rollout_ids = _rollout_ids(rollout_count)
    if executor is None:
        return _evaluate_candidate_batch(
            _bank_market_snapshot(prepared),
            prepared.evaluator,
            prepared.user_roster_id,
            state,
            candidate_ids,
            survival_ids,
            rollout_ids,
            temperature,
        )
    # Candidate evaluations are independent under coupled randomness, and so
    # are disjoint rollout ranges, so a chunked fan-out merged afterwards is
    # exactly one batch evaluation.
    chunks = _rollout_chunks(rollout_ids, LIVE_ROLLOUT_CHUNK)
    futures = [
        [
            executor.submit(
                _evaluate_candidate_task,
                state,
                candidate_id,
                survival_ids,
                chunk,
                temperature,
            )
            for chunk in chunks
        ]
        for candidate_id in candidate_ids
    ]
    return merge_evaluations([
        merge_rollout_ranges([future.result() for future in candidate_futures])
        for candidate_futures in futures
    ])


def merge_screen_refinement(screen_evaluations, extension):
    """Extend finalists' screen observations with the refinement range.

    The screen already evaluated rollout IDs 0..screen-1 for every finalist,
    so refinement evaluates only the remaining IDs and merges (spec 18.5).
    The merge is exactly equal to one full-range evaluation.
    """
    finalist_ids = tuple(
        candidate.candidate_id for candidate in extension.candidates
    )
    finalist_set = set(finalist_ids)
    screened = merge_evaluations(screen_evaluations)
    by_id = {
        candidate.candidate_id: candidate for candidate in screened.candidates
    }
    if not finalist_set <= by_id.keys():
        raise ValueError("Screen evaluations do not cover every finalist")
    candidates = tuple(
        replace(
            by_id[finalist_id],
            survival=(
                replace(
                    by_id[finalist_id].survival,
                    players=tuple(
                        player for player in by_id[finalist_id].survival.players
                        if player.player_id in finalist_set
                    ),
                )
                if by_id[finalist_id].survival is not None
                else None
            ),
        )
        for finalist_id in finalist_ids
    )
    return merge_rollout_ranges([
        replace(screened, candidates=candidates),
        extension,
    ])


def refinement_survivors(evaluation):
    """Racing gate: the leader plus every statistically tied candidate.

    Returns the surviving candidate IDs and the largest paired upper-bound
    advantage any survivor still holds over the leader. A small bound means
    no further sampling can change the decision materially.
    """
    ranked = rank_candidates(evaluation)
    leader = ranked[0]
    survivors = [leader.candidate_id]
    max_advantage = 0.0
    for candidate in ranked[1:]:
        delta = evaluation.paired_delta(candidate.candidate_id, leader.candidate_id)
        if delta.interval[1] >= 0:
            survivors.append(candidate.candidate_id)
            max_advantage = max(max_advantage, delta.interval[1])
    return tuple(survivors), max_advantage


def predicted_next_state(prepared, state, temperature=None):
    """Most likely next draft state under the calibrated opponent model.

    Used for speculative computation while an opponent deliberates. Reuse is
    gated on the realized state's exact signature, so a wrong guess costs
    only otherwise-idle compute.
    """
    if prepared.market_snapshot is None or prepared.evaluator is None:
        return None
    roster_id = state.current_roster_id
    if roster_id is None or roster_id == prepared.user_roster_id:
        return None
    temperature = LIVE_TEMPERATURE if temperature is None else float(temperature)
    snapshot = _bank_market_snapshot(prepared)
    choose = _live_opponent_choice(snapshot, prepared.evaluator, temperature)
    utilities = choose(
        roster_id,
        state.current_pick_no,
        state.rosters,
        state.available_player_ids,
    )
    player_id = max(sorted(utilities), key=lambda candidate: utilities[candidate])
    picked_by = next(
        (
            manager_id
            for manager_id, manager_roster_id in state.manager_roster_ids
            if manager_roster_id == roster_id
        ),
        None,
    )
    return state.with_pick(
        player_id,
        picked_by=picked_by,
        position=prepared.player_details.get(player_id, {}).get("position"),
    )


def select_finalists(prepared, state, screened_rows, count):
    """Screen co-leaders plus guaranteed chalk/value and minimum breadth.

    A noisy screen must not discard a candidate whose paired interval still
    overlaps the leader. Market chalk and top value also always advance.
    """
    del state
    rows = [str(row["player_id"]) for row in screened_rows]
    forced = []
    priced = [row for row in screened_rows if row.get("adp") is not None]
    if priced:
        forced.append(str(min(priced, key=lambda row: row["adp"])["player_id"]))
    projection, position_of, replacement = _value_over_replacement(
        prepared.evaluator
    )
    valued = [player_id for player_id in rows if player_id in projection]
    if valued:
        forced.append(max(
            valued,
            key=lambda player_id: projection[player_id]
            - replacement.get(position_of[player_id], 0.0),
        ))
    keep = dict.fromkeys((
        *forced,
        *(
            str(row["player_id"])
            for row in screened_rows
            if row.get("is_top_tier")
        ),
    ))
    for player_id in rows:
        if len(keep) >= count:
            break
        keep.setdefault(player_id)
    return tuple(sorted(keep, key=rows.index))


def evaluate_live_league_equity(prepared, state, rollout_count, temperature=None):
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("Prepared draft is missing market or season inputs")
    temperature = LIVE_TEMPERATURE if temperature is None else float(temperature)
    snapshot = _bank_market_snapshot(prepared)
    return evaluate_league_equity(
        state,
        prepared.user_roster_id,
        range(rollout_count),
        _live_opponent_choice(snapshot, prepared.evaluator, temperature),
        _projection_user_policy(prepared.evaluator),
        prepared.evaluator,
        draft_model_version=_live_model_version(snapshot, temperature),
        temperature=1.0,
        season_worlds_per_rollout=LIVE_SEASON_WORLDS_PER_ROLLOUT,
    )


def live_league_equity_payload(prepared, evaluation):
    rows = []
    for equity in sorted(
        evaluation.rosters,
        key=lambda row: (
            -row.championship_probability,
            -row.playoff_probability,
            -row.expected_wins,
            row.roster_id,
        ),
    ):
        details = prepared.roster_details.get(equity.roster_id, {})
        rows.append({
            **asdict(equity),
            "name": details.get("name", f"Roster {equity.roster_id}"),
            "draft_slot": details.get("draft_slot"),
            "is_user": details.get("is_user", equity.roster_id == prepared.user_roster_id),
        })
    return {
        "model_status": "uncalibrated_sleeper_adp_baseline",
        "pick_no": evaluation.state_pick_no,
        "completed_picks": evaluation.completed_picks,
        "rollout_count": evaluation.rollout_count,
        "joint_outcome_count": evaluation.joint_outcome_count,
        "rosters": rows,
    }


def position_timing_outlook(prepared, state, positions=("QB", "TE")):
    """Projected positional value at the user's next three non-adjacent turns."""
    if prepared.market_snapshot is None or prepared.evaluator is None:
        return []
    pick_nos = state.future_turn_pick_nos(prepared.user_roster_id)
    if state.current_pick_no is None or not pick_nos:
        return []

    bank = prepared.evaluator.bank
    weeks = len(bank.weeks)
    projection = {
        player_id: float(score) * weeks
        for player_id, score in zip(bank.player_ids, bank.expected_scores)
    }
    position_of = dict(zip(bank.player_ids, bank.player_positions))
    adp = {
        player_id: exp(-utility)
        for player_id, utility in sleeper_adp_utilities(
            prepared.market_snapshot
        ).items()
    }
    roster_counts = {}
    for player_id in state.roster_player_ids(prepared.user_roster_id):
        position = position_of.get(player_id)
        roster_counts[position] = roster_counts.get(position, 0) + 1

    # ponytail: three turns keeps the live advice legible; extend the horizon
    # only if real drafts show QB/TE cliffs routinely falling beyond it.
    outlook = []
    for position in positions:
        if (
            roster_counts.get(position, 0)
            >= prepared.evaluator.slot_counts.get(position, 0)
        ):
            continue
        players = [
            player_id
            for player_id in state.available_player_ids
            if position_of.get(player_id) == position
            and player_id in projection
            and player_id in adp
        ]
        if not players:
            continue

        def best(player_ids):
            return max(
                player_ids,
                key=lambda player_id: (
                    projection[player_id],
                    -adp[player_id],
                    player_id,
                ),
            )

        best_now = best(players)
        turns = []
        for pick_no in pick_nos:
            # Reaches snipe targets ahead of market (ADR-019): a share of the
            # intervening picks deviate from the board, so a player counts as
            # available at a future turn only with ADP beyond the pick plus
            # that expected displacement.
            cushion = LIVE_REACH_RATE * (pick_no - state.current_pick_no)
            expected_available = [
                player_id
                for player_id in players
                if adp[player_id] >= pick_no + cushion
            ]
            player_id = best(expected_available) if expected_available else None
            points = projection[player_id] if player_id else 0.0
            turns.append({
                "pick_no": pick_no,
                "player_id": player_id,
                "name": (
                    prepared.player_details.get(player_id, {}).get("name", player_id)
                    if player_id else None
                ),
                "projected_points": points,
                "adp": adp[player_id] if player_id else None,
                "drop_from_now": projection[best_now] - points,
            })

        points = [projection[best_now], *(turn["projected_points"] for turn in turns)]
        drops = [left - right for left, right in zip(points, points[1:])]
        cliff = drops.index(max(drops)) if max(drops) > 0 else None
        target_pick_no = (
            turns[-1]["pick_no"]
            if cliff is None
            else state.current_pick_no
            if cliff == 0
            else turns[cliff - 1]["pick_no"]
        )
        outlook.append({
            "position": position,
            "best_now_player_id": best_now,
            "best_now_name": prepared.player_details.get(best_now, {}).get(
                "name", best_now
            ),
            "best_now_points": projection[best_now],
            "best_now_adp": adp[best_now],
            "advantage_now_vs_next_turn": drops[0],
            "target_pick_no": target_pick_no,
            "recommendation": (
                "WAIT_THROUGH_PICK"
                if cliff is None
                else "TAKE_NOW"
                if cliff == 0
                else "TARGET_BY_PICK"
            ),
            "turns": turns,
        })
    return outlook


def live_recommendation_payload(prepared, state, evaluations, candidate_pool_count):
    evaluation = merge_evaluations(evaluations)
    recommendation = asdict(recommendation_summary(evaluation))
    top_tier = set(recommendation["co_leader_candidate_ids"])
    ranked = rank_candidates(evaluation)
    adp = {
        player_id: exp(-utility)
        for player_id, utility in sleeper_adp_utilities(
            prepared.market_snapshot
        ).items()
    }
    candidates = []
    for candidate in ranked:
        best_wait = next(
            (alternative for alternative in ranked if alternative is not candidate),
            None,
        )
        survival = (
            next(
                (
                    player for player in best_wait.survival.players
                    if player.player_id == candidate.candidate_id
                ),
                None,
            )
            if best_wait and best_wait.survival
            else None
        )
        candidates.append({
            "player_id": candidate.candidate_id,
            "name": prepared.player_details.get(candidate.candidate_id, {}).get(
                "name", candidate.candidate_id
            ),
            "position": prepared.player_details.get(candidate.candidate_id, {}).get(
                "position"
            ),
            "championship_probability": candidate.championship_probability,
            "is_top_tier": candidate.candidate_id in top_tier,
            "playoff_probability": candidate.playoff_probability,
            "expected_wins": candidate.expected_wins,
            "adp": adp.get(candidate.candidate_id),
            "survives_to_next_pick": (
                survival.survives_to_next_pick if survival else None
            ),
            "best_wait_candidate_id": (
                best_wait.candidate_id if best_wait else None
            ),
        })
    # The scarcity tie-break can promote a non-argmax co-leader, so the
    # board leads with the actual recommendation.
    candidates.sort(
        key=lambda row: row["player_id"]
        != recommendation["recommended_candidate_id"]
    )
    recommendation["candidates"] = candidates
    recommendation["position_timing"] = position_timing_outlook(prepared, state)
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


def _roster_details(live_by_slot, real_by_slot, rosters, users, user_roster_id):
    users_by_id = {str(user.get("user_id")): user for user in users}
    rosters_by_id = {int(roster["roster_id"]): roster for roster in rosters}
    details = {}
    for slot, live_roster_id in live_by_slot.items():
        roster = rosters_by_id.get(real_by_slot.get(slot), {})
        owner_id = roster.get("owner_id") or next(iter(roster.get("co_owners") or ()), None)
        user = users_by_id.get(str(owner_id), {})
        name = (
            (user.get("metadata") or {}).get("team_name")
            or user.get("display_name")
            or f"Roster {slot}"
        )
        details[live_roster_id] = {
            "name": str(name),
            "draft_slot": slot,
            "is_user": live_roster_id == user_roster_id,
        }
    return details


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
