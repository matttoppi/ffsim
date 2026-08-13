"""Transparent target-platform ADP baseline and time-local evaluation."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import groupby
import json
import math
from pathlib import Path
import sqlite3

from ffsim.draft_intel.market import FANTASYPROS_CONTEXTS, load_market_snapshot_at
from ffsim.draft_intel.rollout import choice_probabilities
from ffsim.paths import CACHE_DIR


MODEL_VERSION = "sleeper-adp-inverse-rank-v1"
SLEEPER_ADP_SOURCE = "fantasypros:sleeper"
DEFAULT_BACKTEST_MAX_AGE = timedelta(hours=24)
SCORING_POINTS = {"STD": 0.0, "HALF": 0.5, "PPR": 1.0}
SCORING_TYPES = {"std": 0.0, "half_ppr": 0.5, "ppr": 1.0}
SUPPORTED_CONTEXTS = frozenset(FANTASYPROS_CONTEXTS)


def resolve_league_market_context(league):
    """Resolve raw Sleeper league settings without claiming custom-board support."""
    return resolve_market_context(
        reception_points=(league.get("scoring_settings") or {}).get("rec"),
        roster_positions=league.get("roster_positions") or (),
    )


def resolve_draft_market_context(draft):
    settings = draft.get("settings") or {}
    positions = tuple(
        key.removeprefix("slots_")
        for key, raw_count in settings.items()
        if key.startswith("slots_")
        for _ in range(_slot_count(raw_count))
    )
    return resolve_market_context(
        scoring_type=(draft.get("metadata") or {}).get("scoring_type"),
        roster_positions=positions,
    )


def load_league_market_snapshot(
    league,
    *,
    season,
    at=None,
    max_age=DEFAULT_BACKTEST_MAX_AGE,
    storage_dir=None,
):
    context = resolve_league_market_context(league)
    if context["status"] == "unsupported":
        return {"context": context, "snapshot": None}
    snapshot = load_market_snapshot_at(
        source=SLEEPER_ADP_SOURCE,
        season=season,
        scoring=context["scoring"],
        league_format=context["league_format"],
        team_count=None,
        at=at or datetime.now(timezone.utc),
        max_age=max_age,
        storage_dir=storage_dir,
    )
    return {"context": context, "snapshot": snapshot}


def resolve_market_context(*, roster_positions, scoring_type=None, reception_points=None):
    positions = tuple(str(position).upper() for position in roster_positions)
    if not positions:
        return _unsupported("missing_roster_positions")

    scoring_key = str(scoring_type or "").casefold()
    reasons = []
    if reception_points is None:
        if scoring_key == "2qb":
            reception_points = 0.5
            reasons.append("unknown_reception_scoring_uses_half_ppr")
        elif scoring_key in SCORING_TYPES:
            reception_points = SCORING_TYPES[scoring_key]
        else:
            return _unsupported("unsupported_scoring_type")
    try:
        reception_points = float(reception_points)
    except (TypeError, ValueError):
        return _unsupported("invalid_reception_scoring")
    if not math.isfinite(reception_points) or reception_points < 0:
        return _unsupported("invalid_reception_scoring")

    qb_count = positions.count("QB")
    has_superflex = "SUPER_FLEX" in positions
    league_format = "superflex" if has_superflex or qb_count > 1 or scoring_key == "2qb" else "1qb"
    if qb_count == 0:
        reasons.append("no_qb_slot_uses_nearest_board")
    elif qb_count > 1 and not has_superflex:
        reasons.append("two_qb_uses_superflex_board")

    if league_format == "superflex":
        scoring = "HALF"
        if reception_points != 0.5:
            reasons.append("superflex_scoring_uses_half_ppr_board")
        position = "OP"
    else:
        scoring = min(SCORING_POINTS, key=lambda name: abs(
            SCORING_POINTS[name] - reception_points
        ))
        if reception_points != SCORING_POINTS[scoring]:
            reasons.append("custom_reception_scoring_uses_nearest_board")
        position = "ALL"

    context = (league_format, scoring, position)
    if context not in SUPPORTED_CONTEXTS:
        return _unsupported("market_context_unavailable")
    return {
        "status": "proxy" if reasons else "exact",
        "league_format": league_format,
        "scoring": scoring,
        "position": position,
        "requested_reception_points": reception_points,
        "reasons": reasons,
    }


def sleeper_adp_utilities(snapshot):
    """Return parameter-free log utilities whose softmax weights are 1 / ADP."""
    if snapshot.get("source") != SLEEPER_ADP_SOURCE:
        raise ValueError(f"Expected {SLEEPER_ADP_SOURCE} snapshot")
    utilities = {}
    for observation in snapshot.get("observations") or ():
        player_id = str(observation.get("canonical_player_id") or "")
        try:
            adp = float(observation.get("adp"))
        except (TypeError, ValueError):
            continue
        if not player_id or not math.isfinite(adp) or adp <= 0:
            continue
        if player_id in utilities:
            raise ValueError(f"Duplicate Sleeper ADP player {player_id}")
        utilities[player_id] = -math.log(adp)
    if not utilities:
        raise ValueError("Sleeper ADP snapshot contains no usable observations")
    return utilities


def sleeper_adp_choice(snapshot):
    """Build the rollout callback accepted by ``complete_drafts``."""
    board = sleeper_adp_utilities(snapshot)

    def choose(roster_id, pick_no, rosters, available):
        del roster_id, pick_no, rosters
        utilities = {player_id: board[player_id] for player_id in available if player_id in board}
        if not utilities:
            raise ValueError("Sleeper ADP board has no remaining available players")
        return utilities

    return choose


def sleeper_adp_model_version(snapshot):
    snapshot_id = str(snapshot.get("snapshot_id") or "")
    if not snapshot_id:
        raise ValueError("Sleeper ADP snapshot is missing snapshot_id")
    return f"{MODEL_VERSION}:{snapshot_id}"


def backtest_sleeper_adp(
    *,
    storage_dir=None,
    temperature=1.0,
    max_age=DEFAULT_BACKTEST_MAX_AGE,
):
    """Evaluate only drafts with a snapshot retrieved before the draft began."""
    storage_dir = Path(storage_dir or CACHE_DIR / "draft_intel")
    database_path = storage_dir / "history.sqlite3"
    if not database_path.exists():
        raise FileNotFoundError("Draft intelligence store is missing; run draft-audit --persist first")
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        raise ValueError("temperature must be finite and positive") from None
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be finite and positive")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT d.draft_id, d.season, d.scoring_type, d.roster_slots_json,
                   d.start_time, p.pick_no, p.canonical_player_id, p.is_keeper
            FROM historical_drafts AS d
            JOIN historical_picks AS p USING (draft_id)
            WHERE d.included = 1
            ORDER BY d.draft_id, p.pick_no
            """
        ).fetchall()
    finally:
        connection.close()

    skipped_drafts = Counter()
    skipped_picks = Counter()
    context_counts = Counter()
    snapshot_ids = set()
    considered_drafts = draft_count = scored_picks = total_picks = 0
    log_loss = reciprocal_rank = 0.0
    top_1 = top_3 = top_6 = 0
    for _, draft_rows_iterator in groupby(rows, key=lambda row: row["draft_id"]):
        considered_drafts += 1
        draft_rows = tuple(draft_rows_iterator)
        first = draft_rows[0]
        try:
            roster_slots = json.loads(first["roster_slots_json"])
            roster_positions = tuple(
                position
                for position, count in roster_slots
                for _ in range(int(count))
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError(f"Draft {first['draft_id']} has invalid roster slots") from None
        context = resolve_market_context(
            scoring_type=first["scoring_type"],
            roster_positions=roster_positions,
        )
        if context["status"] == "unsupported":
            skipped_drafts[context["reasons"][0]] += 1
            continue
        started_at = _draft_started_at(first["start_time"])
        if started_at is None:
            skipped_drafts["missing_start_time"] += 1
            continue
        snapshot = load_market_snapshot_at(
            source=SLEEPER_ADP_SOURCE,
            season=first["season"],
            scoring=context["scoring"],
            league_format=context["league_format"],
            team_count=None,
            at=started_at,
            max_age=max_age,
            storage_dir=storage_dir,
        )
        if snapshot is None:
            skipped_drafts["no_time_local_snapshot"] += 1
            continue

        draft_count += 1
        context_counts[(context["status"], context["league_format"], context["scoring"])] += 1
        snapshot_ids.add(snapshot["snapshot_id"])
        board = sleeper_adp_utilities(snapshot)
        keepers = {
            row["canonical_player_id"]
            for row in draft_rows
            if row["is_keeper"] == 1 and row["canonical_player_id"]
        }
        available = set(board) - keepers
        for row in draft_rows:
            if row["is_keeper"] == 1:
                continue
            total_picks += 1
            player_id = row["canonical_player_id"]
            if not player_id:
                skipped_picks["missing_canonical_player"] += 1
                continue
            if player_id not in board:
                skipped_picks["selected_player_missing_from_board"] += 1
                continue
            if player_id not in available:
                raise ValueError(
                    f"Player {player_id} was unavailable at {first['draft_id']}/{row['pick_no']}"
                )
            ranked = sorted(available, key=lambda candidate: (-board[candidate], candidate))
            rank = ranked.index(player_id) + 1
            probabilities = dict(choice_probabilities(
                {candidate: board[candidate] for candidate in available},
                temperature,
            ))
            probability = probabilities[player_id]
            log_loss -= math.log(probability)
            reciprocal_rank += 1 / rank
            top_1 += rank <= 1
            top_3 += rank <= 3
            top_6 += rank <= 6
            scored_picks += 1
            available.remove(player_id)

    return {
        "model": {
            "version": MODEL_VERSION,
            "source": SLEEPER_ADP_SOURCE,
            "temperature": temperature,
            "calibration": "not_run",
            "decision_eligible": False,
        },
        "historical_drafts_considered": considered_drafts,
        "drafts_with_time_local_snapshot": draft_count,
        "total_picks": total_picks,
        "scored_picks": scored_picks,
        "mean_log_loss": log_loss / scored_picks if scored_picks else None,
        "mean_reciprocal_rank": reciprocal_rank / scored_picks if scored_picks else None,
        "top_1_accuracy": top_1 / scored_picks if scored_picks else None,
        "top_3_accuracy": top_3 / scored_picks if scored_picks else None,
        "top_6_accuracy": top_6 / scored_picks if scored_picks else None,
        "contexts": {
            "/".join(context): count
            for context, count in sorted(context_counts.items())
        },
        "snapshot_ids": sorted(snapshot_ids),
        "skipped_drafts": dict(sorted(skipped_drafts.items())),
        "skipped_picks": dict(sorted(skipped_picks.items())),
    }


def _draft_started_at(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return None


def _unsupported(reason):
    return {
        "status": "unsupported",
        "league_format": None,
        "scoring": None,
        "position": None,
        "requested_reception_points": None,
        "reasons": [reason],
    }


def _slot_count(value):
    if isinstance(value, bool):
        raise ValueError("Draft roster slot counts must be non-negative integers")
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("Draft roster slot counts must be non-negative integers") from None
    if value < 0:
        raise ValueError("Draft roster slot counts must be non-negative integers")
    return value
