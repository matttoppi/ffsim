import hashlib
import json
import math
from pathlib import Path

from ffsim.config import AppConfig
from ffsim.draft_intel.live import (
    PreparedDraft,
    LIVE_TEMPERATURE,
    _bank_market_snapshot,
    _live_market_snapshot,
    _live_opponent_choice,
    _player_details,
    _roster_details,
    live_candidate_pool,
)
from ffsim.draft_intel.market_model import load_league_market_snapshot, sleeper_adp_utilities
from ffsim.draft_intel.mock import _standalone_state_picks
from ffsim.draft_intel.opportunity import (
    next_turn_user_policy,
    season_value_over_replacement,
)
from ffsim.draft_intel.state import replay_sleeper_draft
from ffsim.historical_sleeper.hdvn_snapshot import canonical_json, sha256_file
from ffsim.historical_sleeper.empirical_survival import (
    EMPIRICAL_SURVIVAL_VERSION,
    load_empirical_survival_artifact,
    load_empirical_survival_lookup,
    lookup_survival,
)
from ffsim.historical_sleeper.hierarchical_survival import (
    HIERARCHICAL_SURVIVAL_VERSION,
    load_hierarchical_survival_artifact,
    load_hierarchical_survival_model,
    predict_hierarchical_survival,
)
from ffsim.historical_sleeper.rank20_survival import (
    RANK20_SURVIVAL_VERSION,
    load_rank20_survival_artifact,
    load_rank20_survival_model,
    predict_rank20_survival,
)
from ffsim.loaders.players import PlayerLoader
from ffsim.models.league import League
from ffsim.paths import CACHE_DIR
from ffsim.simulation.evaluator import LeagueEvaluator
from ffsim.simulation.world_bank import build_season_world_bank, draftable_players


TIMING_REPORT_VERSION = "offline-2026-player-timing-v3"
DEFAULT_WORLD_COUNT = 50
DEFAULT_CANDIDATE_BREADTH = 20
FALLBACK_BREADTH = 10


def build_cached_timing_context(
    config_path,
    league_cache,
    *,
    roster_id,
    draft_cache=None,
    world_count=DEFAULT_WORLD_COUNT,
):
    """Build projection and draft state only from explicit local cache files."""
    config = AppConfig.from_file(config_path)
    league_cache = Path(league_cache).resolve()
    snapshot = json.loads(league_cache.read_text())
    league = snapshot.get("league") or {}
    if str(league.get("league_id")) != config.league_id:
        raise ValueError("league cache does not match the configured league")
    if draft_cache is None:
        draft_payload = {
            "draft": snapshot.get("draft") or {},
            "picks": snapshot.get("draft_picks") or (),
            "traded_picks": snapshot.get("traded_picks") or (),
        }
        draft_cache_path = league_cache
    else:
        draft_cache_path = Path(draft_cache).resolve()
        draft_payload = json.loads(draft_cache_path.read_text())
    draft = draft_payload.get("draft") or {}
    if config.draft_id and draft_cache is None and str(draft.get("draft_id")) != config.draft_id:
        raise ValueError("league cache does not match the configured draft")
    if world_count < 1:
        raise ValueError("world count must be positive")

    player_loader = PlayerLoader()
    player_loader.load_players()
    sleeper_players = json.loads(player_loader.sleeper_players_file.read_text())
    state_picks = (
        _standalone_state_picks(
            draft,
            draft_payload.get("picks") or (),
            draft_payload.get("traded_picks") or (),
        )
        if draft_cache is not None and draft.get("league_id") is None
        else draft_payload.get("picks") or ()
    )
    state = replay_sleeper_draft(
        draft,
        state_picks,
        draft_payload.get("traded_picks") or (),
        tuple(sleeper_players),
    )
    roster_id = int(roster_id)
    if roster_id not in dict(state.rosters):
        raise ValueError(f"Roster {roster_id} is not in cached draft {state.draft_id}")
    if state.current_roster_id != roster_id:
        raise ValueError(
            f"Roster {roster_id} is not on the clock at pick {state.current_pick_no}"
        )

    season = int(league.get("season") or draft.get("season") or 2026)
    market = load_league_market_snapshot(league, season=season, max_age=None)
    market_snapshot = _live_market_snapshot(market["snapshot"])
    if market_snapshot is None or not market_snapshot.get("observations"):
        raise ValueError("cached league has no usable current market snapshot")

    league_model = League(league)
    roster_by_slot = {
        int(slot): int(owner)
        for slot, owner in (draft.get("slot_to_roster_id") or {}).items()
    }
    if set(roster_by_slot.values()) != set(dict(state.rosters)):
        raise ValueError("cached draft roster mapping is inconsistent")
    real_roster_by_slot = {
        int(slot): int(owner)
        for slot, owner in (
            (snapshot.get("draft") or {}).get("slot_to_roster_id") or {}
        ).items()
    }
    real_slot_by_roster = {
        owner: slot for slot, owner in real_roster_by_slot.items()
    }
    for roster in snapshot.get("rosters") or ():
        division = (roster.get("settings") or {}).get("division")
        real_roster_id = int(roster["roster_id"])
        slot = real_slot_by_roster.get(real_roster_id)
        if division is not None and slot in roster_by_slot:
            league_model.divisions.setdefault(int(division), []).append(
                roster_by_slot[slot]
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
        roster_by_slot.values(),
        config.regular_season_weeks,
        seed=config.seed,
    )
    prepared = PreparedDraft(
        summary={
            "status": "offline_research",
            "league_id": str(league.get("league_id")),
            "draft_id": state.draft_id,
            "market_context": market["context"],
            "market_snapshot_id": market_snapshot.get("snapshot_id"),
            "world_bank": {
                "version": bank.version,
                "worlds": bank.world_count,
                "players": len(bank.player_ids),
            },
        },
        live_draft_id=state.draft_id,
        league_id=str(league.get("league_id")),
        standalone=draft_cache is not None,
        user_roster_id=roster_id,
        market_snapshot=market_snapshot,
        evaluator=evaluator,
        player_details=_player_details(player_loader.sleeper_players_file),
        roster_details=_roster_details(
            roster_by_slot,
            real_roster_by_slot,
            snapshot.get("rosters") or (),
            snapshot.get("users") or (),
            roster_id,
        ),
    )
    return {
        "prepared": prepared,
        "state": state,
        "input_hashes": {
            "config": sha256_file(Path(config_path).resolve()),
            "league_cache": sha256_file(league_cache),
            "draft_cache": sha256_file(draft_cache_path),
            "players": sha256_file(player_loader.sleeper_players_file),
        },
    }


def _load_survival_predictor(manifest_path):
    try:
        metadata = json.loads(Path(manifest_path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("survival manifest is malformed") from error
    model_version = metadata.get("model_version")
    if model_version == EMPIRICAL_SURVIVAL_VERSION:
        artifact = load_empirical_survival_artifact(
            manifest_path, expected={"status": "research"}
        )
        lookup = load_empirical_survival_lookup(manifest_path)

        def predict(**context):
            return lookup_survival(lookup, **context)

        return artifact, predict
    if model_version == HIERARCHICAL_SURVIVAL_VERSION:
        artifact = load_hierarchical_survival_artifact(
            manifest_path, expected={"status": "research"}
        )
        model = load_hierarchical_survival_model(manifest_path)

        def predict(**context):
            result = predict_hierarchical_survival(
                model,
                market_rank=context["market_rank"],
                gap=context["gap"],
                round_=context["round_"],
                position=context["position"],
            )
            return {**result, "status": "available"}

        return artifact, predict
    if model_version == RANK20_SURVIVAL_VERSION:
        artifact = load_rank20_survival_artifact(
            manifest_path, expected={"status": "research"}
        )
        model = load_rank20_survival_model(manifest_path)

        def predict(**context):
            return predict_rank20_survival(
                model,
                market_rank=context["market_rank"],
                gap=context["gap"],
                round_=context["round_"],
                position=context["position"],
            )

        return artifact, predict
    raise ValueError(f"unsupported survival model version: {model_version}")


def _value_loss(target_later, fallback):
    """Positive value lost if the target is gone at the later turn; None-safe.

    ``marginal_value`` is ``later_values.get(player_id)`` and is None when
    the target is roster-infeasible at the later turn (late K/QB2-heavy
    pools), so the subtraction must not run (live crash at picks 120/121).
    """
    if target_later is None or fallback is None:
        return None
    marginal = target_later["marginal_value"]
    if marginal is None:
        return None
    return max(0.0, marginal - fallback)


def build_timing_report(
    prepared,
    state,
    survival_manifest,
    *,
    input_hashes,
    candidate_breadth=DEFAULT_CANDIDATE_BREADTH,
):
    if state.current_roster_id != prepared.user_roster_id:
        raise ValueError("offline timing report requires the requested roster on the clock")
    if prepared.market_snapshot is None or prepared.evaluator is None:
        raise ValueError("offline timing report requires cached market and projection inputs")
    if candidate_breadth < 2:
        raise ValueError("candidate breadth must be at least two")

    survival_manifest = Path(survival_manifest).resolve()
    artifact, predict_survival = _load_survival_predictor(survival_manifest)
    survival_breadth = int(
        artifact.get("target_count") or FALLBACK_BREADTH
    )
    target_context = (
        (prepared.summary.get("market_context") or {}).get("target_context")
        or {}
    )
    scoring_format = _empirical_scoring(target_context.get("scoring"))
    team_count = int(target_context.get("team_count") or state.teams)

    next_turns = state.future_turn_pick_nos(prepared.user_roster_id, count=1)
    if not next_turns:
        raise ValueError("the requested roster has no later non-adjacent turn")
    next_turn = next_turns[0]
    gap = next_turn - state.current_pick_no - 1
    round_number = math.ceil(state.current_pick_no / state.teams)

    snapshot = _bank_market_snapshot(prepared)
    choice = _live_opponent_choice(
        snapshot, prepared.evaluator, state, LIVE_TEMPERATURE
    )
    policy = next_turn_user_policy(prepared.evaluator, state, choice)
    current_values = policy.current_values(
        prepared.user_roster_id,
        state.rosters,
        state.available_player_ids,
    )
    candidates = tuple(
        live_candidate_pool(prepared, state, candidate_breadth)
    )
    projection, position_of, replacement = season_value_over_replacement(
        prepared.evaluator
    )
    market_adp = {
        player_id: math.exp(-utility)
        for player_id, utility in sleeper_adp_utilities(
            prepared.market_snapshot
        ).items()
    }
    branches = {
        candidate_id: _branch_timing(
            prepared,
            state,
            policy,
            predict_survival,
            candidate_id,
            current_values[candidate_id],
            market_adp,
            position_of,
            round_number,
            gap,
            scoring_format,
            team_count,
            survival_breadth,
        )
        for candidate_id in candidates
    }
    rows = []
    for player_id in candidates:
        take_branch = branches[player_id]
        wait_candidates = [
            branch for candidate, branch in branches.items()
            if candidate != player_id and branch["route_value"] is not None
        ]
        best_wait = (
            min(
                wait_candidates,
                key=lambda branch: (
                    -branch["route_value"],
                    branch["current_player_id"],
                ),
            )
            if wait_candidates
            else None
        )
        target_later = (
            next(
                (
                    row for row in best_wait["later_players"]
                    if row["player_id"] == player_id
                ),
                None,
            )
            if best_wait
            else None
        )
        fallback = (
            _expected_best(best_wait["later_players"], exclude=player_id)
            if best_wait
            else None
        )
        details = prepared.player_details.get(player_id, {})
        rows.append({
            "player_id": player_id,
            "name": details.get("name", player_id),
            "position": position_of[player_id],
            "team": details.get("team"),
            "projected_points": projection[player_id],
            "replacement_points": replacement.get(position_of[player_id], 0.0),
            "current_roster_value": current_values[player_id],
            "market_adp": market_adp.get(player_id),
            "market_rank": _available_market_rank(
                player_id,
                state.available_player_ids,
                market_adp,
            ),
            "take_now_route_value": take_branch["route_value"],
            "take_now_expected_next_turn_value": take_branch[
                "expected_next_turn_value"
            ],
            "take_now_route_support": take_branch["route_support_status"],
            "best_wait_current_player_id": (
                best_wait["current_player_id"] if best_wait else None
            ),
            "best_wait_current_value": (
                best_wait["current_value"] if best_wait else None
            ),
            "best_wait_route_value": (
                best_wait["route_value"] if best_wait else None
            ),
            "best_wait_route_support": (
                best_wait["route_support_status"] if best_wait else "unavailable"
            ),
            "wait_delta": (
                best_wait["route_value"] - take_branch["route_value"]
                if best_wait and take_branch["route_value"] is not None
                else None
            ),
            "return_probability": (
                target_later["probability"] if target_later else None
            ),
            "survival_raw_rate": (
                target_later["raw_rate"] if target_later else None
            ),
            "survival_interval_95": (
                target_later["interval_95"] if target_later else None
            ),
            "survival_direct_support": (
                target_later["support"] if target_later else 0
            ),
            "survival_pooled_support": (
                target_later["pooled_support"] if target_later else None
            ),
            "target_next_turn_value": (
                target_later["marginal_value"] if target_later else None
            ),
            "expected_fallback_value": fallback,
            "value_loss_if_target_gone": _value_loss(target_later, fallback),
            "support_status": (
                target_later["lookup_status"] if target_later else "outside_top_ten"
            ),
        })
    rows.sort(
        key=lambda row: (
            row["market_rank"] if row["market_rank"] is not None else 10**9,
            row["player_id"],
        )
    )
    body = {
        "report_version": TIMING_REPORT_VERSION,
        "status": "offline_research",
        "decision_active": False,
        "league_id": prepared.league_id,
        "draft_id": state.draft_id,
        "roster_id": prepared.user_roster_id,
        "pick_no": state.current_pick_no,
        "round": round_number,
        "next_turn_pick_no": next_turn,
        "opponent_picks_until_next": gap,
        "candidate_breadth": candidate_breadth,
        "fallback_breadth": survival_breadth,
        "survival_model_version": artifact["model_version"],
        "survival_manifest_hash": artifact["sha256"],
        "market_snapshot_id": prepared.market_snapshot.get("snapshot_id"),
        "world_bank": prepared.summary["world_bank"],
        "input_hashes": dict(sorted(input_hashes.items())),
        "code_sha256": sha256_file(Path(__file__)),
        "top_ten_capture_complete": all(
            branch["top_ten_capture_complete"] for branch in branches.values()
        ),
        "market_window_capture_complete": all(
            branch["market_window_capture_complete"]
            for branch in branches.values()
        ),
        "candidate_branches": {
            player_id: branches[player_id] for player_id in sorted(branches)
        },
        "players": rows,
        "limitations": [
            "offline shadow only; no API, UI, VONA, ranking, or rollout change",
            "one-turn route value is not the completed-roster terminal objective",
            "expected next-turn value uses independent marginal survival probabilities",
            "ineligible market-window players are captured but excluded from route value",
            "the survival artifact did not load the 2025 locked test",
        ],
    }
    return {
        **body,
        "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest(),
    }


def write_timing_report(report, output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"timing report is immutable: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n")
    output.chmod(0o444)
    return output


def load_timing_report(path):
    try:
        report = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("timing report is malformed") from error
    stored = report.get("sha256")
    body = {key: value for key, value in report.items() if key != "sha256"}
    if stored != hashlib.sha256(canonical_json(body).encode()).hexdigest():
        raise ValueError("timing report hash mismatch")
    if report.get("report_version") != TIMING_REPORT_VERSION:
        raise ValueError("timing report version mismatch")
    if report.get("decision_active") is not False:
        raise ValueError("timing report cannot be decision-active")
    return report


def _branch_timing(
    prepared,
    state,
    policy,
    predict_survival,
    candidate_id,
    current_value,
    market_adp,
    position_of,
    round_number,
    gap,
    scoring_format,
    team_count,
    fallback_breadth,
):
    branch = state.with_pick(
        candidate_id,
        position=position_of.get(candidate_id),
    )
    later_values = policy.current_values(
        prepared.user_roster_id,
        branch.rosters,
        branch.available_player_ids,
    )
    ranked_market = sorted(
        branch.available_player_ids & market_adp.keys(),
        key=lambda player_id: (market_adp[player_id], player_id),
    )[:fallback_breadth]
    later_players = []
    for rank, player_id in enumerate(ranked_market, 1):
        position = position_of.get(player_id)
        survival = (
            predict_survival(
                market_rank=rank,
                gap=gap,
                round_=round_number,
                position=position,
                scoring_format=scoring_format,
                team_count=team_count,
            )
            if position is not None
            else {"status": "unavailable"}
        )
        later_players.append({
            "player_id": player_id,
            "market_rank": rank,
            "position": position,
            "eligible_next_turn": player_id in later_values and position is not None,
            "marginal_value": later_values.get(player_id),
            "survival_probability": (
                survival["probability"]
                if survival["status"] == "available"
                else None
            ),
            "probability": survival.get("probability"),
            "raw_rate": survival.get("raw_rate"),
            "interval_95": survival.get("interval_95"),
            "support": survival.get("count", survival.get("direct_support", 0)),
            "pooled_support": survival.get("pooled_support"),
            "lookup_status": survival["status"],
        })
    eligible_players = [
        player for player in later_players if player["eligible_next_turn"]
    ]
    supported_count = sum(
        player["survival_probability"] is not None for player in eligible_players
    )
    expected_next = _expected_best(later_players)
    route_support_status = (
        "unavailable"
        if not supported_count
        else "complete"
        if supported_count == len(eligible_players)
        else "partial"
    )
    return {
        "current_player_id": candidate_id,
        "current_value": current_value,
        "expected_next_turn_value": expected_next,
        "route_value": (
            current_value + expected_next if expected_next is not None else None
        ),
        "route_support_status": route_support_status,
        "supported_later_players": supported_count,
        "eligible_later_players": len(eligible_players),
        "captured_market_players": len(later_players),
        "top_ten_capture_complete": len(later_players) >= min(10, fallback_breadth),
        "market_window_capture_complete": len(later_players) == fallback_breadth,
        "later_players": later_players,
    }


def _expected_best(players, exclude=None):
    supported = [
        row for row in players
        if row["player_id"] != exclude
        and row["survival_probability"] is not None
        and row["marginal_value"] is not None
    ]
    if not supported:
        return None
    expected = 0.0
    better_gone = 1.0
    for player in sorted(
        supported,
        key=lambda row: (-row["marginal_value"], row["player_id"]),
    ):
        survives = player["survival_probability"]
        expected += player["marginal_value"] * survives * better_gone
        better_gone *= 1 - survives
    return expected



def _empirical_scoring(value):
    normalized = str(value or "").upper()
    aliases = {
        "STD": "STD",
        "HALF": "HALF_PPR",
        "HALF_PPR": "HALF_PPR",
        "PPR": "PPR",
    }
    try:
        return aliases[normalized]
    except KeyError:
        raise ValueError(f"unsupported empirical scoring format: {value}") from None

def _available_market_rank(player_id, available, market_adp):
    ranked = sorted(
        available & market_adp.keys(),
        key=lambda candidate: (market_adp[candidate], candidate),
    )
    try:
        return ranked.index(player_id) + 1
    except ValueError:
        return None
