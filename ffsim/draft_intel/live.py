"""One-click draft preparation and live recommendation calculations."""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field, replace
import json
from math import exp, isfinite
import os
from pathlib import Path
from urllib.parse import quote, urlparse

import numpy as np

from ffsim.config import AppConfig, save_league_attachment
from ffsim.draft_intel.decision import (
    PRACTICAL_TIE_POINTS,
    candidate_urgency,
    evaluate_candidates,
    evaluate_completed_league,
    evaluate_league_equity,
    is_practical_co_leader,
    merge_evaluations,
    merge_rollout_ranges,
    rank_candidates,
    recommendation_summary,
    tier_order,
)
from ffsim.draft_intel.history import load_history, summarize_history
from ffsim.draft_intel.identity import canonical_players_from_cache
from ffsim.draft_intel.market import refresh_fantasypros_adp
from ffsim.draft_intel.market_model import (
    REACH_TEMPERATURE,
    load_league_market_snapshot,
    position_caps,
    resolve_draft_market_context,
    sleeper_adp_choice,
    sleeper_adp_model_version,
    sleeper_adp_utilities,
    starting_lineup_needs,
)
from ffsim.draft_intel.mock import sync_sleeper_draft
from ffsim.draft_intel.opportunity import (
    next_turn_user_policy as _projection_user_policy,
    next_user_turn_pick_no as _next_user_turn_pick_no,
    season_value_over_replacement as _value_over_replacement,
)
from ffsim.draft_intel.personal_ranks import (
    adjusted_projection,
    load_offsets as load_personal_offsets,
    offsets_hash as personal_offsets_hash,
)
from ffsim.draft_intel.worp import load_worp_curve, projected_worp
from ffsim.draft_intel.storage import load_sleeper_identity_map, store_history
from ffsim.loaders.league import _fetch_json, league_and_drafts, refresh_league
from ffsim.loaders.players import PlayerLoader
from ffsim.models.league import League
from ffsim.models.team import FLEX_ELIGIBILITY
from ffsim.paths import CACHE_DIR
from ffsim.simulation.evaluator import BENCH_ASSET_FACTOR, LeagueEvaluator
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
    personal_ranks: dict = field(default_factory=dict)


def prepare_draft(
    config_path,
    draft_id,
    username,
    *,
    mock_draft_id=None,
    season=2026,
    world_count=300,
    progress=None,
    force_refresh=False,
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

    progress(
        "Refreshing league, draft, players, and schedule"
        + (" (forced FantasyPros refresh)" if force_refresh else "")
    )
    refresh_league(league_id, draft_id)
    player_loader = PlayerLoader()
    projection_refresh = player_loader.refresh_if_stale(
        season=season, force=force_refresh
    )
    refresh_matchups(league_id, config.regular_season_weeks + 3)

    progress("Crawling and deduplicating league-mate history")
    history_summary = _refresh_history(league_id, season)

    progress("Refreshing stale ADP boards")
    market_refresh = refresh_fantasypros_adp(
        season=season,
        sleeper_players_path=player_loader.sleeper_players_file,
        force=force_refresh,
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
    # F8: name each row's projection source so a cross-source artifact
    # (e.g. a PFF starter-level fallback beside consensus-sourced rivals)
    # is visible on the board instead of silently inflating one player.
    for player in player_loader.enriched_players:
        detail = player_details.get(str(player.sleeper_id))
        if detail is not None:
            detail["projection_source"] = player.projection_source
    personal_offsets = load_personal_offsets()
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
        "personal_ranks": {
            "players": len(personal_offsets),
            "hash": personal_offsets_hash(personal_offsets),
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
        personal_ranks=personal_offsets,
    )


def _personal_board(prepared):
    """Stored season-point offsets; tolerates bare test doubles without the field."""
    return getattr(prepared, "personal_ranks", None) or {}


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


def live_candidate_pool(prepared, state, breadth, sticky=()):
    """Order candidates best-player-available by market ADP.

    The head is the best remaining players (fallers first), and the expanding
    window walks deeper down the board. Personal season-point offsets never
    move this market head; they enter through the value entrants below.
    Position caps always apply; only the must-fill draft tail narrows
    further to open starter positions.

    ``sticky`` players (the previous pick's finalists) lead the window when
    still eligible, and the top value-over-replacement players always enter
    it: the value model diverges from ADP late, so a pure ADP cutoff can
    exclude the model's favorite at one pick and admit it at the next,
    flipping recommendations between adjacent turns.
    """
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("Prepared draft is missing market or season inputs")
    board = sleeper_adp_utilities(prepared.market_snapshot)
    bank = prepared.evaluator.bank
    bank_players = set(bank.player_ids)
    pool = state.available_player_ids & board.keys() & bank_players
    if not pool:
        raise ValueError("No available market players can be evaluated")
    user_roster_id = prepared.user_roster_id
    roster = state.roster_player_ids(user_roster_id)
    position_of = dict(zip(bank.player_ids, bank.player_positions))
    counts = Counter(position_of.get(player_id) for player_id in roster)
    caps = position_caps(prepared.evaluator.slot_counts)
    pool = {
        player_id for player_id in pool
        if position_of.get(player_id) not in caps
        or counts[position_of[player_id]] < caps[position_of[player_id]]
    }
    if not pool:
        raise ValueError("No available market player passes roster position limits")
    needs = starting_lineup_needs(
        roster,
        position_of,
        prepared.evaluator.slot_counts,
    )
    remaining = sum(
        roster_id == user_roster_id
        for roster_id in state.pick_owners[state.current_pick_no - 1:]
    )
    if needs and remaining <= len(needs):
        needed_positions = {position for need in needs for position in need}
        pool = {
            player_id for player_id in pool
            if position_of.get(player_id) in needed_positions
        }
        if not pool:
            raise ValueError("No available market player can fill a required starter seat")
    head = sorted(
        pool, key=lambda player_id: (-board[player_id], player_id)
    )[:breadth]
    projection, _, replacement = _value_over_replacement(prepared.evaluator)
    personal = _personal_board(prepared)
    valued = sorted(
        (
            player_id for player_id in pool
            if player_id in projection
            # Streamable positions never force the window open early; the
            # must-fill draft tail already admits them when required.
            and position_of[player_id] not in ("K", "DEF")
        ),
        key=lambda player_id: (
            replacement.get(position_of[player_id], 0.0)
            - projection[player_id]
            # Owner season-point offsets (ADR-046) shift subjective value,
            # so liked players enter the evaluated window sooner.
            - personal.get(player_id, 0.0),
            player_id,
        ),
    )[:VALUE_POOL_COUNT]
    return list(dict.fromkeys((
        *(player_id for player_id in sticky if player_id in pool),
        *head,
        *valued,
    )))


# Guaranteed value-over-replacement entrants in the candidate window,
# regardless of ADP rank.
VALUE_POOL_COUNT = 10
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
# Season worlds per candidate continuation. Paired-delta variance measured on
# cached picks 24/48/120 is 97-100% season noise (sigma_d^2 <= 0.002 vs
# sigma_s^2 0.06-0.28) while a continuation costs ~7-22 ms and a season world
# ~2.3 ms, so the nested-MC optimum spends the budget on worlds: 300
# continuations x 14 worlds beats the validated 1,000 x 3 paired precision on
# every measured candidate pair at 0.56-0.60x the compute and matches its
# cross-seed leader stability (2026-08-13 ledger entry;
# /tmp/ffsim_var_decomp2.py pattern).
LIVE_SEASON_WORLDS_PER_ROLLOUT = 14
# League-wide equity keeps the cheap allocation: it displays every roster's
# marginal odds rather than gating paired candidate decisions, and it runs
# single-process on every pick, so precision beyond 3 worlds is wasted there.
LIVE_EQUITY_WORLDS_PER_ROLLOUT = 3
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


def _live_model_version(snapshot, temperature, personal_values=None):
    # VONA compares feasible current value plus a coupled distribution of
    # next-turn alternatives. Roster caps and must-fill starter needs remain.
    # vona5: policy values mirror the terminal roster scorer (floored at the
    # cutline, flex-aware seats, discounted bench assets) per ADR-031.
    version = (
        f"{sleeper_adp_model_version(snapshot)}"
        f":t{temperature}:reach{LIVE_REACH_RATE}:needs:vona5:hazard1"
    )
    if personal_values:
        # Owner offsets change simulated user choices and the preference
        # utility, so they are part of evaluation identity (ADR-046).
        version += f":ranks{personal_offsets_hash(personal_values)[:8]}"
    return version


def _live_opponent_choice(snapshot, evaluator, state, temperature):
    """Calibrated ADP opponents with reaches and roster construction limits."""
    bank = evaluator.bank
    return sleeper_adp_choice(
        snapshot,
        temperature=temperature,
        reach_rate=LIVE_REACH_RATE,
        positions=dict(zip(bank.player_ids, bank.player_positions)),
        slot_counts=evaluator.slot_counts,
        roster_sizes=Counter(
            roster_id for roster_id in state.pick_owners if roster_id is not None
        ),
    )


def _evaluate_candidate_batch(
    snapshot,
    evaluator,
    user_roster_id,
    state,
    candidate_ids,
    survival_ids,
    rollout_ids,
    temperature,
    seed=2026,
    personal_values=None,
):
    choose = _live_opponent_choice(snapshot, evaluator, state, temperature)
    user_policy = _projection_user_policy(evaluator, state, choose, personal_values)
    return evaluate_candidates(
        state,
        candidate_ids,
        user_roster_id,
        _rollout_ids(rollout_ids),
        choose,
        user_policy,
        evaluator,
        draft_model_version=_live_model_version(
            snapshot, temperature, personal_values
        ),
        survival_player_ids=survival_ids,
        seed=seed,
        # The opponent callback returns final log-probabilities with the
        # fitted temperature and reach mixture folded in, so rollouts run
        # at temperature 1.0.
        temperature=1.0,
        season_worlds_per_rollout=min(
            LIVE_SEASON_WORLDS_PER_ROLLOUT, evaluator.bank.world_count
        ),
        personal_values=personal_values,
    )


def _init_candidate_worker(snapshot, evaluator, user_roster_id, personal_values):
    _WORKER["snapshot"] = snapshot
    _WORKER["evaluator"] = evaluator
    _WORKER["user_roster_id"] = user_roster_id
    _WORKER["personal_values"] = personal_values


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


def _evaluate_candidate_task(
    state, candidate_id, survival_ids, rollout_ids, temperature, seed=2026
):
    return _evaluate_candidate_batch(
        _WORKER["snapshot"],
        _WORKER["evaluator"],
        _WORKER["user_roster_id"],
        state,
        (candidate_id,),
        survival_ids,
        rollout_ids,
        temperature,
        seed,
        personal_values=_WORKER["personal_values"],
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
            _personal_board(prepared),
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
    seed=2026,
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
            seed,
            personal_values=_personal_board(prepared),
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
                seed,
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
    """Return the legacy diagnostic practical tier for an evaluation.

    Production uses fixed-budget refinement and never eliminates a finalist
    from an intermediate interval. This helper remains exported for audit
    compatibility and reports whether any retained comparison straddles the
    practical boundary.
    """
    ranked = rank_candidates(evaluation)
    leader = ranked[0]
    survivors = [leader.candidate_id]
    needs_refinement = False
    for candidate in ranked[1:]:
        delta = evaluation.paired_value_delta(
            leader.candidate_id, candidate.candidate_id
        )
        if is_practical_co_leader(delta):
            survivors.append(candidate.candidate_id)
            needs_refinement |= delta.interval[1] > PRACTICAL_TIE_POINTS
    return tuple(survivors), needs_refinement


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
    choose = _live_opponent_choice(snapshot, prepared.evaluator, state, temperature)
    ids, log_probabilities, _ = choose(
        roster_id,
        state.current_pick_no,
        state.rosters,
        state.available_player_ids,
    )
    # IDs are ascending-sorted, so the first argmax is the lowest-ID co-leader.
    player_id = ids[int(log_probabilities.argmax())]
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
    choose = _live_opponent_choice(snapshot, prepared.evaluator, state, temperature)
    return evaluate_league_equity(
        state,
        prepared.user_roster_id,
        range(rollout_count),
        choose,
        _projection_user_policy(prepared.evaluator, state, choose),
        prepared.evaluator,
        draft_model_version=_live_model_version(snapshot, temperature),
        temperature=1.0,
        season_worlds_per_rollout=min(
            LIVE_EQUITY_WORLDS_PER_ROLLOUT, prepared.evaluator.bank.world_count
        ),
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
        "season_worlds_per_rollout": evaluation.season_worlds_per_rollout,
        "joint_outcome_count": evaluation.joint_outcome_count,
        "draft_model_version": evaluation.draft_model_version,
        "world_bank_version": evaluation.world_bank_version,
        "league_evaluator_version": evaluation.league_evaluator_version,
        "rosters": rows,
    }


def completed_league_simulation(prepared, state):
    if prepared.evaluator is None:
        raise ValueError("Prepared draft is missing season inputs")
    payload = live_league_equity_payload(
        prepared,
        evaluate_completed_league(state, prepared.evaluator),
    )
    return {
        **payload,
        "model_status": "observed_final_rosters",
        "simulation_type": "completed_draft",
    }


PROJECTION_BOARD_VERSION = 3
PROJECTION_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


def _future_turn_survival(
    utilities, available_ids, current_pick_no, future_turns, temperature,
):
    """Mean-field market survival for each available player at future turns.

    Full-distribution propagation without replacement: at every intervening
    pick the ADR-019 market mixture (sharp softmax at ``temperature`` plus a
    ``LIVE_REACH_RATE`` reach component at ``REACH_TEMPERATURE``) removes one
    player in expectation. The per-pick removal probability is the
    UNCONDITIONAL pick mass ``pi_i ~ s_i x w_i / sum_j s_j w_j`` per mixture
    component — never a conditional probability multiplied into ``s`` (that
    double-discounts) — clamped at each player's remaining availability and
    rescaled so exactly one expected pick leaves the board per pick. No
    sampled path, no argmax conditioning; positions and rosters are ignored
    on purpose because the falloff is a market diagnostic. Verified against
    exact without-replacement enumeration in the tests (max survival error
    0.12 on adversarially sharp boards, expected-best within ~4% and
    conservative).

    Returns ``{turn_pick_no: {player_id: survival}}``; players without a
    market observation are never drafted by the model and survive at 1.0.
    """
    if not future_turns:
        return {}
    ids = sorted(
        player_id for player_id in available_ids if player_id in utilities
    )
    if not ids:
        return {turn: {} for turn in future_turns}
    utility = np.asarray([utilities[player_id] for player_id in ids])
    sharp = np.exp((utility - utility.max()) / temperature)
    reach = np.exp((utility - utility.max()) / REACH_TEMPERATURE)
    survival = np.ones(len(ids))
    snapshots = {}
    turn_set = set(future_turns)
    for pick_no in range(current_pick_no + 1, max(future_turns) + 1):
        if pick_no in turn_set:
            snapshots[pick_no] = dict(zip(ids, survival.tolist()))
        raw = np.zeros(len(ids))
        for rate, weights in (
            (1.0 - LIVE_REACH_RATE, sharp), (LIVE_REACH_RATE, reach),
        ):
            mass = survival * weights
            total = mass.sum()
            if total > 0.0:
                raw += rate * mass / total
        picked = np.minimum(raw, survival)
        # Conservation: redistribute the clamped deficit proportionally to
        # the raw mass of players with availability left.
        for _ in range(25):
            deficit = 1.0 - picked.sum()
            if deficit <= 1e-9:
                break
            room = (picked < survival - 1e-12) & (raw > 0.0)
            if not room.any():
                break
            share = raw * room
            picked = np.minimum(picked + share / share.sum() * deficit, survival)
        survival = np.maximum(survival - picked, 0.0)
    return snapshots


def projection_value_board(prepared, state, temperature=None):
    """Fast league-scored rankings with expected-best future-turn lookahead.

    The remaining-pool tables update after every synchronized pick. The
    current-turn plan and route values anchor on the user's own pick, so they
    are published only while the user is on the clock.
    """
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("Prepared draft is missing market or season inputs")
    if state.current_pick_no is None:
        return None
    user_on_clock = state.current_roster_id == prepared.user_roster_id

    temperature = LIVE_TEMPERATURE if temperature is None else float(temperature)
    snapshot = _bank_market_snapshot(prepared)
    choose = _live_opponent_choice(snapshot, prepared.evaluator, state, temperature)
    my_board = _personal_board(prepared)
    # Personal policy prices players at base projection + offset (ADR-046):
    # it drives the board's current/route values. The falloff diagnostic
    # below uses a separate raw-projection policy so cost-of-waiting stays
    # a market/scarcity signal.
    policy = _projection_user_policy(
        prepared.evaluator, state, choose, my_board
    )
    raw_policy = (
        _projection_user_policy(prepared.evaluator, state, choose)
        if my_board
        else policy
    )
    current_values = policy.current_values(
        prepared.user_roster_id,
        state.rosters,
        state.available_player_ids,
    )
    raw_current_values = (
        raw_policy.current_values(
            prepared.user_roster_id,
            state.rosters,
            state.available_player_ids,
        )
        if my_board
        else current_values
    )
    route_values = (
        policy(
            prepared.user_roster_id,
            state.current_pick_no,
            state.rosters,
            state.available_player_ids,
        )
        if user_on_clock
        else {}
    )

    projection, position_of, replacement = _value_over_replacement(
        prepared.evaluator
    )
    # Displayed points are the owner's projections: base + offset.
    # Replacement stays raw — offsets are player opinions, not a new
    # league-wide cutline — so VORP/WORP become personal surpluses.
    projection = adjusted_projection(projection, my_board)
    vorp = {
        player_id: points - replacement.get(position_of[player_id], 0.0)
        for player_id, points in projection.items()
    }
    adp = {
        player_id: exp(-utility)
        for player_id, utility in sleeper_adp_utilities(
            prepared.market_snapshot
        ).items()
    }
    market_context = getattr(prepared, "summary", {}).get("market_context") or {}
    target_context = market_context.get("target_context") or {}
    team_count = target_context.get("team_count") or len(prepared.evaluator.roster_ids)
    scoring_format = target_context.get("scoring")
    if scoring_format:
        worp_curve, worp_status = load_worp_curve(team_count, scoring_format)
    else:
        worp_curve = None
        worp_status = {
            "status": "context_unknown",
            "team_count": team_count,
            "scoring_format": None,
        }
    projection_weeks = len(prepared.evaluator.bank.weeks)
    regular_season_weeks = getattr(
        prepared.evaluator, "regular_season_weeks", projection_weeks
    )
    worp = {
        player_id: (
            projected_worp(
                value,
                projection_weeks,
                regular_season_weeks,
                worp_curve,
            )
            if worp_curve
            else None
        )
        for player_id, value in vorp.items()
    }
    position_order = {
        position: rank for rank, position in enumerate(PROJECTION_POSITIONS)
    }
    eligible = current_values.keys() & projection.keys()
    ranked = sorted(
        eligible,
        key=lambda player_id: (
            position_order.get(position_of.get(player_id), len(position_order)),
            -projection[player_id],
            adp.get(player_id, float("inf")),
            player_id,
        ),
    )
    position_ranks = Counter()
    players = []
    for player_id in ranked:
        position = position_of[player_id]
        position_ranks[position] += 1
        details = prepared.player_details.get(player_id, {})
        players.append({
            "player_id": player_id,
            "name": details.get("name", player_id),
            "position": position,
            "team": details.get("team"),
            "position_rank": position_ranks[position],
            "projected_points": projection[player_id],
            "replacement_points": replacement.get(position, 0.0),
            "value_over_replacement": vorp[player_id],
            "wins_over_replacement": worp[player_id],
            "current_roster_value": current_values[player_id],
            "adp": adp.get(player_id),
            "personal_offset": my_board.get(player_id, 0),
            "projection_source": details.get("projection_source"),
            # F8: consensus (FantasyPros) is the primary offense source;
            # a lone PFF row among consensus rivals is a cross-source
            # artifact worth a fade check, not extra signal.
            "projection_source_outlier": (
                position not in ("K", "DEF")
                and details.get("projection_source") == "pff"
            ),
        })

    points_position_ranks = Counter()
    points_players = []
    remaining_ranked = sorted(
        state.available_player_ids & projection.keys() & position_of.keys(),
        key=lambda player_id: (
            position_order.get(
                position_of.get(player_id), len(position_order)
            ),
            -projection[player_id],
            adp.get(player_id, float("inf")),
            player_id,
        ),
    )
    for player_id in remaining_ranked:
        position = position_of[player_id]
        if position not in position_order:
            continue
        if points_position_ranks[position] >= 10:
            continue
        points_position_ranks[position] += 1
        details = prepared.player_details.get(player_id, {})
        points_players.append({
            "player_id": player_id,
            "name": details.get("name", player_id),
            "position": position,
            "team": details.get("team"),
            "position_rank": points_position_ranks[position],
            "projected_points": projection[player_id],
            "personal_offset": my_board.get(player_id, 0),
            "projection_source": details.get("projection_source"),
            "projection_source_outlier": (
                position not in ("K", "DEF")
                and details.get("projection_source") == "pff"
            ),
        })

    best_route_by_position = {}
    for player_id, value in route_values.items():
        position = position_of[player_id]
        incumbent = best_route_by_position.get(position)
        if incumbent is None or (-value, player_id) < (
            -route_values[incumbent], incumbent
        ):
            best_route_by_position[position] = player_id
    plans = sorted(
        (
            {
                "position": position,
                "player_id": player_id,
                "name": prepared.player_details.get(player_id, {}).get(
                    "name", player_id
                ),
                "projected_points": projection[player_id],
                "value_over_replacement": vorp[player_id],
                "wins_over_replacement": worp[player_id],
                "current_roster_value": current_values[player_id],
                "later_value": max(
                    0.0, route_values[player_id] - current_values[player_id]
                ),
                "route_value": route_values[player_id],
                "adp": adp.get(player_id),
            }
            for position, player_id in best_route_by_position.items()
        ),
        key=lambda row: (
            -row["route_value"],
            -row["current_roster_value"],
            row["player_id"],
        ),
    )
    # The helper treats the anchor pick as the user's own turn. Off the
    # clock the current opponent pick is itself the intervening opponent,
    # so anchor one pick earlier to report the user's actual next turn.
    turn_anchor = (
        state.current_pick_no if user_on_clock else state.current_pick_no - 1
    )
    next_turn = _next_user_turn_pick_no(
        state.pick_owners,
        turn_anchor,
        prepared.user_roster_id,
    )

    # Positional falloff: for every position, the marginal roster value of
    # the best player now versus the survival-weighted EXPECTED best
    # remaining player at each of the user's future turns, under the
    # mean-field market pick model (`_future_turn_survival`) and the current
    # roster. The headline edge is the cost of optimal deferral: best now
    # minus the best expected future turn. No simulation and no encoded
    # strategy; the terminal simulation ranking stays authoritative.
    future_turns = []
    anchor = turn_anchor
    while True:
        turn_pick_no = _next_user_turn_pick_no(
            state.pick_owners, anchor, prepared.user_roster_id
        )
        if turn_pick_no is None:
            break
        future_turns.append(turn_pick_no)
        anchor = turn_pick_no
    turn_survival = _future_turn_survival(
        sleeper_adp_utilities(prepared.market_snapshot),
        state.available_player_ids,
        state.current_pick_no,
        future_turns,
        temperature,
    )
    user_roster_players = next(
        (
            roster_players
            for roster_id, roster_players in state.rosters
            if roster_id == prepared.user_roster_id
        ),
        (),
    )
    user_position_counts = Counter(
        position_of[player_id]
        for player_id in user_roster_players
        if player_id in position_of
    )
    # Flex-aware open seats: dedicated seats first, then surplus starters
    # consume flex seats in ascending-eligibility order. Open flex seats are
    # SHARED across every eligible position, so per-position totals overlap
    # and must not be summed across positions.
    dedicated_open = {}
    position_surplus = {}
    for position in position_order:
        seats = prepared.evaluator.slot_counts.get(position, 0)
        have = user_position_counts.get(position, 0)
        dedicated_open[position] = max(0, seats - have)
        position_surplus[position] = max(0, have - seats)
    open_flex_by_position = dict.fromkeys(position_order, 0)
    flex_slots = sorted(
        (
            (slot, count)
            for slot, count in prepared.evaluator.slot_counts.items()
            if slot in FLEX_ELIGIBILITY
        ),
        key=lambda item: (len(FLEX_ELIGIBILITY[item[0]]), item[0]),
    )
    for slot, seat_count in flex_slots:
        eligible = sorted(FLEX_ELIGIBILITY[slot])
        for position in eligible:
            while seat_count and position_surplus.get(position, 0):
                position_surplus[position] -= 1
                seat_count -= 1
        for position in eligible:
            if position in open_flex_by_position:
                open_flex_by_position[position] += seat_count
    by_position = {}
    for row in players:
        if row["position"] in position_order:
            by_position.setdefault(row["position"], []).append(row)
    outlook_rows = []
    for position, rows in by_position.items():
        # Falloff selects and prices by RAW marginal value AND raw points:
        # cost of waiting is a market/scarcity diagnostic, so a personal
        # boost cannot make a deep dart throw the positional target and a
        # fade cannot hide the market's best (ADR-046). Each row still
        # carries personal_offset so the UI can flag boosted/faded names.
        raw_value = lambda row: raw_current_values.get(row["player_id"], 0.0)
        raw_points = lambda row: row["projected_points"] - row["personal_offset"]
        rows = sorted(
            rows,
            key=lambda row: (
                -raw_value(row),
                row["adp"] if row["adp"] is not None else float("inf"),
                row["player_id"],
            ),
        )
        best_now = rows[0]
        turns = []
        for turn_pick_no in future_turns:
            survival = turn_survival.get(turn_pick_no) or {}
            # Expected best under independent survivals: walk players in
            # value order; each contributes value x P(available) x P(every
            # better player is gone). The displayed player is the most
            # likely best (largest such mass).
            expected_best = 0.0
            better_gone = 1.0
            likely = None
            likely_mass = 0.0
            for row in rows:
                chance = survival.get(row["player_id"], 1.0)
                if chance <= 0.0:
                    continue
                mass = chance * better_gone
                expected_best += raw_value(row) * mass
                if mass > likely_mass:
                    likely, likely_mass = row, mass
                better_gone *= 1.0 - chance
                if better_gone < 1e-9:
                    break
            turns.append({
                "pick_no": turn_pick_no,
                "player_id": likely["player_id"] if likely else None,
                "name": likely["name"] if likely else None,
                "marginal_value": expected_best,
                "projected_points": raw_points(likely) if likely else None,
                "personal_offset": likely["personal_offset"] if likely else 0,
                "adp": likely["adp"] if likely else None,
                "survival_probability": (
                    survival.get(likely["player_id"], 1.0) if likely else 0.0
                ),
                "probability_best": likely_mass,
                "drop_from_now": raw_value(best_now) - expected_best,
            })
        best_wait_value = max(
            (turn["marginal_value"] for turn in turns), default=0.0
        )
        outlook_rows.append({
            "position": position,
            "open_dedicated_slots": dedicated_open.get(position, 0),
            "eligible_open_flex_slots": open_flex_by_position.get(position, 0),
            "remaining_starting_opportunities": dedicated_open.get(position, 0)
            + open_flex_by_position.get(position, 0),
            "best_now_player_id": best_now["player_id"],
            "best_now_name": best_now["name"],
            "best_now_marginal_value": raw_value(best_now),
            "best_now_points": raw_points(best_now),
            "best_now_personal_offset": best_now["personal_offset"],
            "best_now_adp": best_now["adp"],
            "take_now_edge": raw_value(best_now) - best_wait_value,
            "turns": turns,
            "top_players": [
                {
                    "player_id": row["player_id"],
                    "name": row["name"],
                    "position_rank": row["position_rank"],
                    "marginal_value": raw_value(row),
                    "projected_points": raw_points(row),
                    "personal_offset": row["personal_offset"],
                    "adp": row["adp"],
                    "edge_vs_waiting": raw_value(row) - best_wait_value,
                }
                for row in rows[:5]
            ],
        })
    outlook_rows.sort(key=lambda row: -row["take_now_edge"])
    return {
        "model_status": "deterministic_projection_lookahead",
        "model_version": PROJECTION_BOARD_VERSION,
        "route_model_status": "approximate_adp_opponent_choice_lookahead",
        "worp_calibration": worp_status,
        "pick_no": state.current_pick_no,
        "next_user_pick_no": next_turn,
        "recommended_player_id": plans[0]["player_id"] if plans else None,
        "recommended_position": plans[0]["position"] if plans else None,
        "plans": plans,
        "points_source": "fantasypros_primary_offense",
        "special_teams_points_source": "pff",
        "points_players": points_players,
        "players": players,
        "position_outlook": {
            "availability_model": "market_mixture_mean_field_survival",
            # Survival is propagated analytically (`_future_turn_survival`):
            # no sampled path, exactly one expected pick per intervening
            # pick, ADR-019 sharp+reach mixture weights.
            "survival_model": "mean_field_without_replacement",
            "roster_assumption": "current_roster_marginal_value",
            # Raw projections on purpose: personal offsets never move the
            # falloff targets, only the simulation recommendation and the
            # personal board values.
            "value_basis": "raw_projection",
            # Every edge and turn value scores only the FIRST marginal seat
            # at that position under the flex- and bench-aware roster scorer;
            # nothing is multiplied by slot counts.
            "edge_basis": "first_marginal_seat",
            "reach_rate": LIVE_REACH_RATE,
            "future_turn_pick_nos": future_turns,
            "positions": outlook_rows,
        },
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


def order_symmetric_co_leader_ids(evaluation, co_leaders, headline_id):
    """Co-leaders that tie the headline exactly in every continuation (F2).

    At back-to-back turns "A then B" and "B then A" can produce bitwise-
    identical completions. Such a co-leader is a later pick shown early —
    label it "same final roster, order does not matter" instead of letting
    a streamable position read as round-6 advice.
    """
    paired_preference = getattr(evaluation, "paired_preference_delta", None)
    if paired_preference is None:
        paired_preference = evaluation.paired_value_delta
    return [
        candidate.candidate_id
        for candidate in co_leaders
        if candidate.candidate_id != headline_id
        and paired_preference(
            headline_id, candidate.candidate_id
        ).tied_continuation_probability == 1.0
    ]


def live_recommendation_payload(prepared, state, evaluations, candidate_pool_count):
    evaluation = merge_evaluations(evaluations)
    adp = {
        player_id: exp(-utility)
        for player_id, utility in sleeper_adp_utilities(
            prepared.market_snapshot
        ).items()
    }
    my_board = _personal_board(prepared)

    def effective_tie_break_urgency(candidate):
        # Streamable K/DEF are never urgent — their positive VONA is an
        # artifact of the below-replacement feasible pool.
        position = prepared.player_details.get(candidate.candidate_id, {}).get(
            "position"
        )
        return 0 if position in ("K", "DEF") else candidate_urgency(candidate)

    def market_tier_key(candidate):
        return (
            -effective_tie_break_urgency(candidate),
            adp.get(candidate.candidate_id, float("inf")),
        )

    recommendation = asdict(
        recommendation_summary(evaluation, tier_key=market_tier_key)
    )
    recommendation["personal_ranks"] = {
        "players": len(my_board),
        "hash": personal_offsets_hash(my_board),
    }
    top_tier = set(recommendation["co_leader_candidate_ids"])
    ranked = rank_candidates(evaluation)
    co_leaders = tuple(
        candidate for candidate in ranked if candidate.candidate_id in top_tier
    )
    recommendation["order_symmetric_candidate_ids"] = (
        order_symmetric_co_leader_ids(
            evaluation, co_leaders, recommendation["recommended_candidate_id"]
        )
    )
    tie_break_basis = None
    if recommendation["decision_status"] == "toss_up":
        max_urgency = max(map(effective_tie_break_urgency, co_leaders))
        max_urgency_candidates = tuple(
            candidate for candidate in co_leaders
            if effective_tie_break_urgency(candidate) == max_urgency
        )
        if len(max_urgency_candidates) == 1:
            tie_break_basis = "urgency"
        else:
            finite_adps = tuple(
                adp[candidate.candidate_id]
                for candidate in max_urgency_candidates
                if isfinite(adp.get(candidate.candidate_id, float("inf")))
            )
            board_basis = "market_adp"
            tie_break_basis = (
                board_basis
                if finite_adps and finite_adps.count(min(finite_adps)) == 1
                else "engine_rank"
            )
    recommendation["headline_tie_break_basis"] = tie_break_basis
    recommendation["practical_tie_points"] = PRACTICAL_TIE_POINTS
    recommendation["bench_asset_factor"] = BENCH_ASSET_FACTOR
    reason_codes = tuple(
        code for code in recommendation["reason_codes"]
        if code != "VONA_TIEBREAK"
    )
    if tie_break_basis:
        reason_codes += (f"{tie_break_basis.upper()}_TIEBREAK",)
    recommendation["reason_codes"] = reason_codes
    q_leader = ranked[0]
    recommendation["q_leader_candidate_id"] = q_leader.candidate_id
    recommendation["paired_value_bounds_vs_q_leader"] = [
        {
            "candidate_id": candidate.candidate_id,
            "projected_value_delta": delta.projected_value_delta,
            "lower_bound": delta.interval[0],
            "upper_bound": delta.interval[1],
        }
        for candidate in ranked
        for delta in (
            evaluation.paired_value_delta(
                candidate.candidate_id,
                q_leader.candidate_id,
            ),
        )
    ]
    # Projected value cannot order a statistical tie, so the tier leads with
    # the least-replaceable picks (highest value over the next alternative),
    # market-best first among genuine ties.
    display_order = [
        *tier_order(
            (candidate for candidate in ranked if candidate.candidate_id in top_tier),
            ranked,
            market_tier_key,
        ),
        *(candidate for candidate in ranked if candidate.candidate_id not in top_tier),
    ]
    candidates = []
    for candidate in display_order:
        opportunity = candidate.opportunity_cost
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
            "projected_roster_value": candidate.projected_roster_value,
            "projected_roster_value_standard_error": (
                candidate.projected_roster_value_standard_error
            ),
            "championship_probability": candidate.championship_probability,
            "is_top_tier": candidate.candidate_id in top_tier,
            "playoff_probability": candidate.playoff_probability,
            "expected_wins": candidate.expected_wins,
            "adp": adp.get(candidate.candidate_id),
            "personal_offset": my_board.get(candidate.candidate_id, 0),
            "preference_adjusted_value": candidate.preference_adjusted_value,
            "preference_adjusted_value_standard_error": (
                candidate.preference_adjusted_value_standard_error
            ),
            "survives_to_next_pick": (
                survival.survives_to_next_pick if survival else None
            ),
            "best_wait_candidate_id": (
                best_wait.candidate_id if best_wait else None
            ),
            "survival_branch_root_candidate_id": (
                best_wait.candidate_id if survival else None
            ),
            "opportunity_evidence_branch_root_candidate_id": (
                candidate.candidate_id if opportunity else None
            ),
            "target_available_count": (
                survival.available_count if survival else None
            ),
            "target_selected_when_available_count": (
                survival.selected_when_available_count if survival else None
            ),
            "target_rollout_count": (
                best_wait.survival.rollout_count
                if best_wait and best_wait.survival
                else None
            ),
            "rollout_count": candidate.rollout_count,
            "effective_tie_break_urgency": (
                effective_tie_break_urgency(candidate)
            ),
            "current_marginal_value": (
                opportunity.current_marginal_value if opportunity else None
            ),
            "expected_best_later_value": (
                opportunity.expected_best_later_value if opportunity else None
            ),
            "expected_same_position_later_value": (
                opportunity.expected_same_position_later_value if opportunity else None
            ),
            "value_over_next_alternative": (
                opportunity.value_over_next_alternative if opportunity else None
            ),
            "positional_value_drop": (
                opportunity.positional_value_drop if opportunity else None
            ),
            "next_turn_pick_no": (
                opportunity.next_user_pick_no if opportunity else None
            ),
            "later_alternatives": (
                [
                    {
                        "player_id": player_id,
                        "name": prepared.player_details.get(player_id, {}).get(
                            "name", player_id
                        ),
                        "position": prepared.player_details.get(player_id, {}).get(
                            "position"
                        ),
                        "probability": probability,
                    }
                    for player_id, probability in (
                        opportunity.later_alternative_distribution[:3]
                    )
                ]
                if opportunity
                else []
            ),
            "later_alternative_other_probability": (
                max(
                    0.0,
                    1.0 - sum(
                        probability
                        for _, probability in (
                            opportunity.later_alternative_distribution[:3]
                        )
                    ),
                )
                if opportunity and opportunity.sample_count
                else 0.0
            ),
            "opportunity_sample_count": (
                opportunity.sample_count if opportunity else 0
            ),
            "opportunity_model_version": (
                opportunity.model_version if opportunity else None
            ),
        })
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
            "manager_id": str(owner_id) if owner_id is not None else None,
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
