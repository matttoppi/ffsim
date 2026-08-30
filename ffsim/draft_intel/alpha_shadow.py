from collections import Counter
import json
import os
import time
from pathlib import Path

import numpy as np

from ffsim.draft_intel.decision import (
    _state_signature,
    evaluate_candidates,
    rank_candidates,
)
from ffsim.draft_intel.live import (
    LIVE_SEASON_WORLDS_PER_ROLLOUT,
    LIVE_TEMPERATURE,
    _bank_market_snapshot,
    _live_opponent_choice,
)
from ffsim.draft_intel.opportunity import next_turn_user_policy
from ffsim.draft_intel.timing_report import build_timing_report
from ffsim.historical_sleeper.hierarchical_survival import (
    load_hierarchical_survival_artifact,
)
from ffsim.historical_sleeper.rank20_survival import (
    RANK20_SURVIVAL_VERSION,
    load_rank20_survival_artifact,
)
from ffsim.historical_sleeper.roster_manager_choice import (
    load_roster_manager_choice_artifact,
    load_roster_manager_choice_model,
    POSITIONS,
    manager_position_factors,
)

MANAGER_SHADOW_BLEND = 0.10
MANAGER_SHADOW_ROLLOUTS = 20
MANAGER_SHADOW_CANDIDATE_LIMIT = 5
DEFAULT_HIERARCHICAL_MANIFEST = (
    Path.home()
    / ".cache/ffsim/historical_sleeper/hdvn/"
    "hierarchical-survival-final-20260829/hierarchical-survival.manifest.json"
)
DEFAULT_ROSTER_MANAGER_MANIFEST = (
    Path.home()
    / ".cache/ffsim/historical_sleeper/hdvn/"
    "roster-manager-choice-final-20260829/roster-manager-choice.manifest.json"
)


class AlphaShadowCollector:
    def __init__(self, hierarchical_manifest, roster_manager_manifest=None):
        self.hierarchical_manifest = Path(hierarchical_manifest).resolve()
        metadata = json.loads(self.hierarchical_manifest.read_text())
        if metadata.get("model_version") == RANK20_SURVIVAL_VERSION:
            self.hierarchical_artifact = load_rank20_survival_artifact(
                self.hierarchical_manifest, expected={"status": "research"}
            )
        else:
            self.hierarchical_artifact = load_hierarchical_survival_artifact(
                self.hierarchical_manifest, expected={"status": "research"}
            )
        self.roster_manager_manifest = (
            Path(roster_manager_manifest).resolve()
            if roster_manager_manifest is not None
            else None
        )
        self.roster_manager_artifact = None
        self.roster_manager_model = None
        if self.roster_manager_manifest is not None:
            self.roster_manager_artifact = load_roster_manager_choice_artifact(
                self.roster_manager_manifest, expected={"status": "research"}
            )
            self.roster_manager_model = load_roster_manager_choice_model(
                self.roster_manager_manifest
            )

    def collect(self, prepared, state, recommendation):
        timing_started = time.monotonic()
        timing = build_timing_report(
            prepared,
            state,
            self.hierarchical_manifest,
            input_hashes={
                "market_snapshot": str(
                    (prepared.market_snapshot or {}).get("snapshot_id") or ""
                ),
                "world_bank": str(
                    (prepared.summary.get("world_bank") or {}).get("version") or ""
                ),
            },
            candidate_breadth=max(
                20, len(recommendation.get("candidates") or ())
            ),
        )
        timing_duration = time.monotonic() - timing_started
        recommended_id = str(
            recommendation.get("recommended_candidate_id") or ""
        )
        recommended_branch = timing["candidate_branches"].get(recommended_id)
        engine_ranks = {
            str(candidate.get("player_id")): index
            for index, candidate in enumerate(
                recommendation.get("candidates") or (), 1
            )
        }
        candidates = [
            _candidate_evidence(row, engine_ranks[row["player_id"]])
            for row in timing["players"]
            if row["player_id"] in engine_ranks
        ]
        candidates.sort(key=lambda row: (row["engine_rank"], row["player_id"]))
        manager_support = self._manager_support(prepared)
        manager_started = time.monotonic()
        manager_shadow = self._manager_shadow(
            prepared, state, recommendation
        )
        manager_duration = time.monotonic() - manager_started
        state_signature = _state_signature(state)
        return {
            "status": "ready",
            "decision_active": False,
            "draft_id": state.draft_id,
            "pick_no": state.current_pick_no,
            "component_duration_seconds": {
                "hierarchical_timing": timing_duration,
                "manager_shadow": manager_duration,
            },
            "round": timing["round"],
            "next_turn_pick_no": timing["next_turn_pick_no"],
            "opponent_picks_until_next": timing[
                "opponent_picks_until_next"
            ],
            "state_signature": state_signature,
            "terminal_recommendation_id": recommended_id or None,
            "terminal_q_leader_id": recommendation.get(
                "q_leader_candidate_id"
            ),
            "terminal_co_leader_candidate_ids": list(
                recommendation.get("co_leader_candidate_ids") or ()
            ),
            "survival_model_version": timing["survival_model_version"],
            "survival_manifest_hash": timing["survival_manifest_hash"],
            "manager_model_version": (
                self.roster_manager_artifact["model_version"]
                if self.roster_manager_artifact is not None
                else None
            ),
            "manager_manifest_hash": (
                self.roster_manager_artifact["sha256"]
                if self.roster_manager_artifact is not None
                else None
            ),
            "manager_probability_blend": (
                MANAGER_SHADOW_BLEND
                if self.roster_manager_artifact is not None
                else None
            ),
            "top_ten_capture_complete": timing[
                "top_ten_capture_complete"
            ],
            "candidates": candidates,
            "recommended_branch_next_turn": (
                [
                    _later_player(row)
                    for row in recommended_branch["later_players"]
                ]
                if recommended_branch is not None
                else []
            ),
            "manager_support": manager_support,
            "manager_shadow": manager_shadow,
            "manager_replay_input": {
                "candidate_ids": [
                    str(candidate.get("player_id"))
                    for candidate in recommendation.get("candidates") or ()
                ],
                "terminal_recommendation_id": recommended_id or None,
                "terminal_co_leader_candidate_ids": list(
                    recommendation.get("co_leader_candidate_ids") or ()
                ),
                "state_signature": state_signature,
                "completed_pick_count": len(state.completed_picks),
                "manager_probability_blend": (
                    MANAGER_SHADOW_BLEND
                    if self.roster_manager_artifact is not None
                    else None
                ),
                "manager_shadow_rollouts": manager_shadow.get("rollouts"),
                "supported_rosters": manager_support["supported_rosters"],
                "population_fallback_rosters": manager_support[
                    "population_fallback_rosters"
                ],
            },
            "limitations": [
                "shadow evidence cannot alter the terminal recommendation",
                "one-turn route value is diagnostic only",
                "manager rollout comparison uses a low-cost shadow budget",
            ],
        }

    def _manager_shadow(self, prepared, state, recommendation):
        if self.roster_manager_model is None:
            return {
                "status": "unavailable",
                "reason": "manager artifact missing",
            }
        candidate_ids = tuple(
            str(candidate.get("player_id"))
            for candidate in (
                recommendation.get("candidates") or ()
            )[:MANAGER_SHADOW_CANDIDATE_LIMIT]
        )
        if len(candidate_ids) < 2:
            return {
                "status": "unavailable",
                "reason": "fewer than two terminal candidates",
            }
        population_choice = _live_opponent_choice(
            _bank_market_snapshot(prepared),
            prepared.evaluator,
            state,
            LIVE_TEMPERATURE,
        )
        position_by_id = dict(zip(
            prepared.evaluator.bank.player_ids,
            prepared.evaluator.bank.player_positions,
        ))
        callback_calls = Counter()

        def choose(roster_id, pick_no, rosters, available, mask=None):
            ids, population_logs, keys = population_choice(
                roster_id, pick_no, rosters, available, mask=mask
            )
            roster = tuple(dict(rosters)[roster_id])
            factors = manager_position_factors(
                self.roster_manager_model,
                (
                    prepared.roster_details.get(roster_id) or {}
                ).get("manager_id"),
                [
                    position_by_id.get(player_id, "UNKNOWN")
                    for player_id in roster
                ],
            )
            factor_by_position = dict(zip(POSITIONS, factors["factors"]))
            player_factors = np.asarray([
                factor_by_position.get(
                    position_by_id.get(player_id, "UNKNOWN"),
                    factor_by_position["UNKNOWN"],
                )
                for player_id in ids
            ])
            population_probabilities = np.exp(population_logs)
            manager_probabilities = (
                population_probabilities * player_factors
            )
            manager_probabilities /= manager_probabilities.sum()
            probabilities = (
                (1 - MANAGER_SHADOW_BLEND) * population_probabilities
                + MANAGER_SHADOW_BLEND * manager_probabilities
            )
            probabilities /= probabilities.sum()
            callback_calls[factors["status"]] += 1
            return ids, np.log(probabilities), keys

        choose.returns_final_log_probabilities = True
        choose.returns_log_probability_arrays = True
        choose.board_player_ids = population_choice.board_player_ids
        evaluation = evaluate_candidates(
            state,
            candidate_ids,
            prepared.user_roster_id,
            range(MANAGER_SHADOW_ROLLOUTS),
            choose,
            next_turn_user_policy(prepared.evaluator, state, choose),
            prepared.evaluator,
            draft_model_version=(
                f"shadow:{self.roster_manager_artifact['sha256']}:"
                f"blend{MANAGER_SHADOW_BLEND:.2f}"
            ),
            survival_player_ids=candidate_ids,
            seed=2026,
            temperature=1.0,
            season_worlds_per_rollout=min(
                LIVE_SEASON_WORLDS_PER_ROLLOUT,
                prepared.evaluator.bank.world_count,
            ),
        )
        ranked = rank_candidates(evaluation)
        shadow_leader = ranked[0].candidate_id
        terminal_leader = str(
            recommendation.get("recommended_candidate_id")
            or recommendation.get("q_leader_candidate_id")
            or ""
        )
        terminal_tier = {
            str(candidate_id)
            for candidate_id in (
                recommendation.get("co_leader_candidate_ids") or ()
            )
        }
        return {
            "status": "ready",
            "rollouts": MANAGER_SHADOW_ROLLOUTS,
            "probability_blend": MANAGER_SHADOW_BLEND,
            "terminal_leader_candidate_id": terminal_leader or None,
            "shadow_leader_candidate_id": shadow_leader,
            "shadow_leader_in_terminal_practical_tier": (
                shadow_leader in terminal_tier
            ),
            "ranking": [
                candidate.candidate_id for candidate in ranked
            ],
            "callback_calls": dict(callback_calls),
        }

    def _manager_support(self, prepared):
        manager_factors = (
            self.roster_manager_model["manager_factors"]
            if self.roster_manager_model is not None
            else {}
        )
        supported = fallback = 0
        for details in prepared.roster_details.values():
            if details.get("is_user"):
                continue
            manager_id = str(details.get("manager_id") or "")
            if manager_id and manager_id in manager_factors:
                supported += 1
            else:
                fallback += 1
        return {
            "supported_rosters": supported,
            "population_fallback_rosters": fallback,
            "total_opponent_rosters": supported + fallback,
        }


def load_default_alpha_shadow_collector():
    hierarchical = Path(
        os.environ.get(
            "FFSIM_HIERARCHICAL_SURVIVAL_MANIFEST",
            DEFAULT_HIERARCHICAL_MANIFEST,
        )
    )
    roster_manager = Path(
        os.environ.get(
            "FFSIM_ROSTER_MANAGER_MANIFEST",
            DEFAULT_ROSTER_MANAGER_MANIFEST,
        )
    )
    if not hierarchical.exists():
        return None, f"hierarchical survival artifact not found: {hierarchical}"
    try:
        collector = AlphaShadowCollector(
            hierarchical,
            roster_manager if roster_manager.exists() else None,
        )
    except (OSError, ValueError) as error:
        return None, str(error)
    return collector, None


def _candidate_evidence(row, engine_rank):
    probability = row["return_probability"]
    return {
        "player_id": row["player_id"],
        "name": row["name"],
        "position": row["position"],
        "team": row["team"],
        "engine_rank": engine_rank,
        "market_rank": row["market_rank"],
        "return_probability": probability,
        "return_interval_95": row["survival_interval_95"],
        "direct_support": row["survival_direct_support"],
        "pooled_support": row["survival_pooled_support"],
        "support_status": row["support_status"],
        "timing_label": _timing_label(probability),
        "current_roster_value": row["current_roster_value"],
        "wait_delta": row["wait_delta"],
    }


def _later_player(row):
    return {
        "player_id": row["player_id"],
        "market_rank": row["market_rank"],
        "position": row["position"],
        "eligible_next_turn": row["eligible_next_turn"],
        "return_probability": row["probability"],
        "return_interval_95": row["interval_95"],
        "direct_support": row["support"],
        "pooled_support": row["pooled_support"],
        "timing_label": _timing_label(row["probability"]),
    }


def _timing_label(probability):
    if probability is None:
        return "outside_model"
    if probability >= 0.70:
        return "safe_to_wait"
    if probability <= 0.30:
        return "urgent"
    return "uncertain"
