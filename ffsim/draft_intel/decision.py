"""Joint draft-continuation and season-world candidate evaluation."""

from dataclasses import dataclass, replace
from hashlib import sha256
import math
from operator import index

from ffsim.draft_intel.rollout import (
    SurvivalReport,
    complete_drafts,
    merge_survival_reports,
    normalize_rollout_id,
    normalize_seed,
    summarize_survival,
)


DECISION_ENGINE_VERSION = 5


@dataclass(frozen=True)
class DraftOpportunityCost:
    current_marginal_value: float
    next_user_pick_no: int | None
    expected_best_later_value: float | None
    expected_same_position_later_value: float | None
    value_over_next_alternative: float | None
    positional_value_drop: float | None
    later_alternative_distribution: tuple[tuple[str, float], ...]
    sample_count: int
    model_version: str


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
    projected_roster_value: float
    projected_roster_value_standard_error: float
    projected_roster_value_interval: tuple[float, float]
    continuation_roster_values: tuple[float, ...]
    championship_probability: float
    championship_standard_error: float
    championship_interval: tuple[float, float]
    playoff_probability: float
    expected_wins: float
    expected_points: float
    championship_outcomes: tuple[bool, ...]
    playoff_outcomes: tuple[bool, ...]
    wins: tuple[int, ...]
    points: tuple[float, ...]
    continuation_log_probabilities: tuple[float, ...]
    continuation_championship_probabilities: tuple[float, ...]
    survival: SurvivalReport | None
    opportunity_cost: DraftOpportunityCost | None = None

    @property
    def sample_count(self):
        return len(self.championship_outcomes)

    @property
    def rollout_count(self):
        return len(self.continuation_championship_probabilities)


@dataclass(frozen=True)
class RosterEquity:
    roster_id: int
    championship_probability: float
    championship_standard_error: float
    championship_interval: tuple[float, float]
    playoff_probability: float
    expected_wins: float
    expected_points: float


@dataclass(frozen=True)
class LeagueEquityEvaluation:
    draft_id: str
    state_pick_no: int | None
    completed_picks: int
    rollout_count: int
    season_worlds_per_rollout: int
    joint_outcome_count: int
    draft_model_version: str
    world_bank_version: str
    league_evaluator_version: str
    rosters: tuple[RosterEquity, ...]


@dataclass(frozen=True)
class PairedDelta:
    candidate_id: str
    baseline_candidate_id: str
    championship_probability_delta: float
    standard_error: float
    interval: tuple[float, float]
    better_outcome_probability: float
    worse_outcome_probability: float


@dataclass(frozen=True)
class PairedValueDelta:
    """Paired projected-roster-value difference across coupled continuations."""

    candidate_id: str
    baseline_candidate_id: str
    projected_value_delta: float
    standard_error: float
    interval: tuple[float, float]
    better_continuation_probability: float
    worse_continuation_probability: float


@dataclass(frozen=True)
class DecisionEvaluation:
    draft_id: str
    state_pick_no: int
    state_signature: str
    user_roster_id: int
    next_user_pick_no: int | None
    rollout_ids: tuple[int, ...]
    world_indices: tuple[tuple[int, ...], ...]
    season_worlds_per_rollout: int
    seed: int
    decision_engine_version: int
    draft_model_version: str
    world_bank_version: str
    league_evaluator_version: str
    candidates: tuple[CandidateEvaluation, ...]

    def candidate(self, candidate_id):
        candidate_id = str(candidate_id)
        try:
            return next(
                candidate for candidate in self.candidates
                if candidate.candidate_id == candidate_id
            )
        except StopIteration:
            raise ValueError(f"Unknown evaluated candidate {candidate_id}") from None

    def paired_delta(self, candidate_id, baseline_candidate_id):
        candidate = self.candidate(candidate_id)
        baseline = self.candidate(baseline_candidate_id)
        differences = tuple(
            int(left) - int(right)
            for left, right in zip(
                candidate.championship_outcomes,
                baseline.championship_outcomes,
            )
        )
        continuation_differences = tuple(
            sum(differences[start:start + self.season_worlds_per_rollout])
            / self.season_worlds_per_rollout
            for start in range(0, len(differences), self.season_worlds_per_rollout)
        )
        mean, standard_error = _mean_and_error(continuation_differences)
        return PairedDelta(
            candidate_id=candidate.candidate_id,
            baseline_candidate_id=baseline.candidate_id,
            championship_probability_delta=mean,
            standard_error=standard_error,
            interval=(
                max(-1.0, mean - 1.96 * standard_error),
                min(1.0, mean + 1.96 * standard_error),
            ),
            better_outcome_probability=sum(value > 0 for value in differences) / len(differences),
            worse_outcome_probability=sum(value < 0 for value in differences) / len(differences),
        )

    def paired_value_delta(self, candidate_id, baseline_candidate_id):
        """Paired projected-roster-value delta; one deterministic value per continuation."""
        candidate = self.candidate(candidate_id)
        baseline = self.candidate(baseline_candidate_id)
        differences = tuple(
            left - right
            for left, right in zip(
                candidate.continuation_roster_values,
                baseline.continuation_roster_values,
                strict=True,
            )
        )
        mean, standard_error = _mean_and_error(differences)
        return PairedValueDelta(
            candidate_id=candidate.candidate_id,
            baseline_candidate_id=baseline.candidate_id,
            projected_value_delta=mean,
            standard_error=standard_error,
            interval=(mean - 1.96 * standard_error, mean + 1.96 * standard_error),
            better_continuation_probability=(
                sum(value > 0 for value in differences) / len(differences)
            ),
            worse_continuation_probability=(
                sum(value < 0 for value in differences) / len(differences)
            ),
        )


@dataclass(frozen=True)
class RecommendationSummary:
    draft_id: str
    state_pick_no: int
    state_signature: str
    run_signature: str
    user_roster_id: int
    next_user_pick_no: int | None
    recommended_candidate_id: str
    runner_up_candidate_id: str | None
    decision_status: str
    co_leader_candidate_ids: tuple[str, ...]
    projected_roster_value: float
    projected_roster_value_interval: tuple[float, float]
    paired_value_delta_vs_runner_up: PairedValueDelta | None
    championship_probability: float
    championship_interval: tuple[float, float]
    playoff_probability: float
    expected_wins: float
    expected_points: float
    continuation_equity_percentiles: tuple[float, float, float]
    paired_delta_vs_runner_up: PairedDelta | None
    availability: SurvivalReport | None
    rollout_count: int
    season_worlds_per_rollout: int
    joint_outcome_count: int
    seed: int
    decision_engine_version: int
    draft_model_version: str
    world_bank_version: str
    league_evaluator_version: str
    reason_codes: tuple[str, ...]


def evaluate_candidates(
    state,
    candidate_ids,
    user_roster_id,
    rollout_ids,
    opponent_choice,
    user_policy,
    league_evaluator,
    *,
    draft_model_version,
    seed=2026,
    temperature=1.0,
    season_worlds_per_rollout=1,
    survival_player_ids=(),
    tiers=None,
    use_cache=True,
):
    """Evaluate root candidates on paired draft continuations and season worlds."""
    candidate_ids = _canonical_ids(candidate_ids, "candidate_ids")
    if not candidate_ids:
        raise ValueError("candidate_ids must not be empty")
    rollout_ids = tuple(normalize_rollout_id(value) for value in rollout_ids)
    if len(rollout_ids) < 2 or len(set(rollout_ids)) != len(rollout_ids):
        raise ValueError("Root candidates require at least two unique rollout IDs")
    if draft_model_version is None or not str(draft_model_version).strip():
        raise ValueError("draft_model_version is required")
    draft_model_version = str(draft_model_version).strip()
    seed = normalize_seed(seed)
    survival_player_ids = tuple(survival_player_ids)
    raw_tiers = tuple(
        (str(tier_id), tuple(player_ids))
        for tier_id, player_ids in (tiers or {}).items()
    )
    if len({tier_id for tier_id, _ in raw_tiers}) != len(raw_tiers):
        raise ValueError("tiers contain duplicate canonical IDs")
    tiers = dict(raw_tiers)
    user_roster_id = int(user_roster_id)
    state_roster_ids = {roster_id for roster_id, _ in state.rosters}
    if set(league_evaluator.roster_ids) != state_roster_ids:
        raise ValueError("Draft state and league evaluator roster IDs do not match")
    if user_roster_id not in state_roster_ids:
        raise ValueError(f"Unknown user roster {user_roster_id}")

    world_indices = tuple(
        coupled_world_indices(
            seed,
            rollout_id,
            league_evaluator.bank.world_count,
            season_worlds_per_rollout,
        )
        for rollout_id in rollout_ids
    )
    season_worlds_per_rollout = len(world_indices[0])
    player_indices = {
        player_id: player_index
        for player_index, player_id in enumerate(league_evaluator.bank.player_ids)
    }
    user_index = league_evaluator.roster_index[user_roster_id]
    future_turns = state.future_turn_pick_nos(user_roster_id, count=1)
    next_user_pick_no = future_turns[0] if future_turns else None
    evaluations = []
    for candidate_id in candidate_ids:
        completions = complete_drafts(
            state,
            candidate_id,
            user_roster_id,
            rollout_ids,
            opponent_choice,
            user_policy,
            seed=seed,
            temperature=temperature,
        )
        championships = []
        playoffs = []
        wins = []
        points = []
        log_probabilities = []
        continuation_probabilities = []
        roster_values = []
        for completion, completion_worlds in zip(completions, world_indices):
            try:
                assignment = {
                    roster_id: tuple(player_indices[player_id] for player_id in player_ids)
                    for roster_id, player_ids in completion.rosters
                }
            except KeyError as error:
                raise ValueError(
                    f"Completed draft player {error.args[0]} is missing from SeasonWorldBank"
                ) from None
            roster_values.append(
                league_evaluator.projected_roster_value(assignment, user_roster_id)
            )
            result = league_evaluator.evaluate(
                assignment,
                world_indices=completion_worlds,
                use_cache=use_cache,
            )
            completion_championships = tuple(
                bool(champion == user_index) for champion in result.champion_indices
            )
            championships.extend(completion_championships)
            playoffs.extend(bool(value) for value in result.playoffs[:, user_index])
            wins.extend(int(value) for value in result.wins[:, user_index])
            points.extend(float(value) for value in result.points[:, user_index])
            log_probabilities.append(completion.opponent_log_probability)
            continuation_probabilities.append(
                sum(completion_championships) / len(completion_championships)
            )

        championship_probability, championship_error = _mean_and_error(
            continuation_probabilities
        )
        roster_value, roster_value_error = _mean_and_error(roster_values)
        evaluations.append(CandidateEvaluation(
            candidate_id=candidate_id,
            projected_roster_value=roster_value,
            projected_roster_value_standard_error=roster_value_error,
            projected_roster_value_interval=(
                roster_value - 1.96 * roster_value_error,
                roster_value + 1.96 * roster_value_error,
            ),
            continuation_roster_values=tuple(roster_values),
            championship_probability=championship_probability,
            championship_standard_error=championship_error,
            championship_interval=_probability_interval(
                championship_probability, championship_error
            ),
            playoff_probability=sum(playoffs) / len(playoffs),
            expected_wins=sum(wins) / len(wins),
            expected_points=sum(points) / len(points),
            championship_outcomes=tuple(championships),
            playoff_outcomes=tuple(playoffs),
            wins=tuple(wins),
            points=tuple(points),
            continuation_log_probabilities=tuple(log_probabilities),
            continuation_championship_probabilities=tuple(continuation_probabilities),
            survival=(
                summarize_survival(completions, survival_player_ids, tiers)
                if (survival_player_ids or tiers) and next_user_pick_no is not None
                else None
            ),
            opportunity_cost=(
                user_policy.opportunity_evidence(state, candidate_id, completions)
                if hasattr(user_policy, "opportunity_evidence")
                else None
            ),
        ))

    return DecisionEvaluation(
        draft_id=state.draft_id,
        state_pick_no=state.current_pick_no,
        state_signature=_state_signature(state),
        user_roster_id=user_roster_id,
        next_user_pick_no=next_user_pick_no,
        rollout_ids=rollout_ids,
        world_indices=world_indices,
        season_worlds_per_rollout=season_worlds_per_rollout,
        seed=seed,
        decision_engine_version=DECISION_ENGINE_VERSION,
        draft_model_version=draft_model_version,
        world_bank_version=league_evaluator.bank.version,
        league_evaluator_version=league_evaluator.version,
        candidates=tuple(evaluations),
    )


def evaluate_league_equity(
    state,
    user_roster_id,
    rollout_ids,
    opponent_choice,
    user_policy,
    league_evaluator,
    *,
    draft_model_version,
    seed=2026,
    temperature=1.0,
    season_worlds_per_rollout=1,
    use_cache=True,
):
    """Estimate every roster's equity from the current unforced draft state."""
    rollout_ids = tuple(normalize_rollout_id(value) for value in rollout_ids)
    if len(rollout_ids) < 2 or len(set(rollout_ids)) != len(rollout_ids):
        raise ValueError("League equity requires at least two unique rollout IDs")
    if draft_model_version is None or not str(draft_model_version).strip():
        raise ValueError("draft_model_version is required")
    user_roster_id = int(user_roster_id)
    if set(league_evaluator.roster_ids) != {roster_id for roster_id, _ in state.rosters}:
        raise ValueError("Draft state and league evaluator roster IDs do not match")
    if user_roster_id not in league_evaluator.roster_ids:
        raise ValueError(f"Unknown user roster {user_roster_id}")

    world_indices = tuple(
        coupled_world_indices(
            seed,
            rollout_id,
            league_evaluator.bank.world_count,
            season_worlds_per_rollout,
        )
        for rollout_id in rollout_ids
    )
    completions = complete_drafts(
        state,
        None,
        user_roster_id,
        rollout_ids,
        opponent_choice,
        user_policy,
        seed=seed,
        temperature=temperature,
    )
    player_indices = {
        player_id: player_index
        for player_index, player_id in enumerate(league_evaluator.bank.player_ids)
    }
    championships = {roster_id: [] for roster_id in league_evaluator.roster_ids}
    continuation_probabilities = {
        roster_id: [] for roster_id in league_evaluator.roster_ids
    }
    playoffs = {roster_id: [] for roster_id in league_evaluator.roster_ids}
    wins = {roster_id: [] for roster_id in league_evaluator.roster_ids}
    points = {roster_id: [] for roster_id in league_evaluator.roster_ids}
    for completion, completion_worlds in zip(completions, world_indices):
        try:
            assignment = {
                roster_id: tuple(player_indices[player_id] for player_id in player_ids)
                for roster_id, player_ids in completion.rosters
            }
        except KeyError as error:
            raise ValueError(
                f"Completed draft player {error.args[0]} is missing from SeasonWorldBank"
            ) from None
        result = league_evaluator.evaluate(
            assignment,
            world_indices=completion_worlds,
            use_cache=use_cache,
        )
        for roster_id in league_evaluator.roster_ids:
            roster_index = league_evaluator.roster_index[roster_id]
            outcomes = tuple(
                bool(champion == roster_index) for champion in result.champion_indices
            )
            championships[roster_id].extend(outcomes)
            continuation_probabilities[roster_id].append(sum(outcomes) / len(outcomes))
            playoffs[roster_id].extend(bool(value) for value in result.playoffs[:, roster_index])
            wins[roster_id].extend(int(value) for value in result.wins[:, roster_index])
            points[roster_id].extend(float(value) for value in result.points[:, roster_index])

    roster_equities = []
    for roster_id in league_evaluator.roster_ids:
        probability, error = _mean_and_error(continuation_probabilities[roster_id])
        roster_equities.append(RosterEquity(
            roster_id=roster_id,
            championship_probability=probability,
            championship_standard_error=error,
            championship_interval=_probability_interval(probability, error),
            playoff_probability=sum(playoffs[roster_id]) / len(playoffs[roster_id]),
            expected_wins=sum(wins[roster_id]) / len(wins[roster_id]),
            expected_points=sum(points[roster_id]) / len(points[roster_id]),
        ))
    return LeagueEquityEvaluation(
        draft_id=state.draft_id,
        state_pick_no=state.current_pick_no,
        completed_picks=len(state.completed_picks),
        rollout_count=len(rollout_ids),
        season_worlds_per_rollout=len(world_indices[0]),
        joint_outcome_count=len(rollout_ids) * len(world_indices[0]),
        draft_model_version=str(draft_model_version).strip(),
        world_bank_version=league_evaluator.bank.version,
        league_evaluator_version=league_evaluator.version,
        rosters=tuple(roster_equities),
    )


def evaluate_completed_league(state, league_evaluator, *, use_cache=True):
    """Evaluate the observed final rosters across every prepared season world."""
    if state.current_pick_no is not None:
        raise ValueError("The draft is not complete")
    if set(league_evaluator.roster_ids) != {roster_id for roster_id, _ in state.rosters}:
        raise ValueError("Draft state and league evaluator roster IDs do not match")

    player_indices = {
        player_id: player_index
        for player_index, player_id in enumerate(league_evaluator.bank.player_ids)
    }
    try:
        assignment = {
            roster_id: tuple(player_indices[player_id] for player_id in player_ids)
            for roster_id, player_ids in state.rosters
        }
    except KeyError as error:
        raise ValueError(
            f"Completed draft player {error.args[0]} is missing from SeasonWorldBank"
        ) from None

    result = league_evaluator.evaluate(assignment, use_cache=use_cache)
    roster_equities = []
    for roster_id in league_evaluator.roster_ids:
        roster_index = league_evaluator.roster_index[roster_id]
        championships = tuple(
            champion == roster_index for champion in result.champion_indices
        )
        probability, error = _mean_and_error(championships)
        roster_equities.append(RosterEquity(
            roster_id=roster_id,
            championship_probability=probability,
            championship_standard_error=error,
            championship_interval=_probability_interval(probability, error),
            playoff_probability=float(result.playoffs[:, roster_index].mean()),
            expected_wins=float(result.wins[:, roster_index].mean()),
            expected_points=float(result.points[:, roster_index].mean()),
        ))

    return LeagueEquityEvaluation(
        draft_id=state.draft_id,
        state_pick_no=None,
        completed_picks=len(state.completed_picks),
        rollout_count=1,
        season_worlds_per_rollout=league_evaluator.bank.world_count,
        joint_outcome_count=league_evaluator.bank.world_count,
        draft_model_version="observed-final-rosters-v1",
        world_bank_version=league_evaluator.bank.version,
        league_evaluator_version=league_evaluator.version,
        rosters=tuple(roster_equities),
    )


def merge_evaluations(evaluations):
    """Combine candidate batches evaluated on identical coupled inputs.

    Candidate results are independent of which batch evaluated them, so a
    merged evaluation is exactly equal to one large evaluation of the union.
    """
    evaluations = tuple(evaluations)
    if not evaluations:
        raise ValueError("evaluations must not be empty")

    def identity(evaluation):
        return (
            evaluation.draft_id,
            evaluation.state_pick_no,
            evaluation.state_signature,
            evaluation.user_roster_id,
            evaluation.next_user_pick_no,
            evaluation.rollout_ids,
            evaluation.world_indices,
            evaluation.season_worlds_per_rollout,
            evaluation.seed,
            evaluation.decision_engine_version,
            evaluation.draft_model_version,
            evaluation.world_bank_version,
            evaluation.league_evaluator_version,
        )

    base = evaluations[0]
    if any(identity(other) != identity(base) for other in evaluations[1:]):
        raise ValueError("Cannot merge evaluations from different states or model inputs")
    candidates = tuple(
        candidate for evaluation in evaluations for candidate in evaluation.candidates
    )
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("Merged evaluations contain duplicate candidates")
    return replace(base, candidates=candidates)


def merge_rollout_ranges(evaluations):
    """Concatenate evaluations of disjoint rollout ranges for one candidate set.

    Rollout outcomes are independent per deterministic rollout ID, so
    evaluating IDs 0-99 and 100-999 separately and merging in ascending order
    is exactly one 0-999 evaluation: identical statistics, intervals,
    survival, and run identity.
    """
    evaluations = tuple(evaluations)
    if not evaluations:
        raise ValueError("evaluations must not be empty")

    def identity(evaluation):
        return (
            evaluation.draft_id,
            evaluation.state_pick_no,
            evaluation.state_signature,
            evaluation.user_roster_id,
            evaluation.next_user_pick_no,
            evaluation.season_worlds_per_rollout,
            evaluation.seed,
            evaluation.decision_engine_version,
            evaluation.draft_model_version,
            evaluation.world_bank_version,
            evaluation.league_evaluator_version,
            tuple(candidate.candidate_id for candidate in evaluation.candidates),
        )

    base = evaluations[0]
    if any(identity(other) != identity(base) for other in evaluations[1:]):
        raise ValueError("Cannot merge rollout ranges from different states or candidates")
    rollout_ids = tuple(
        rollout_id for evaluation in evaluations for rollout_id in evaluation.rollout_ids
    )
    if len(set(rollout_ids)) != len(rollout_ids):
        raise ValueError("Cannot merge overlapping rollout ranges")
    candidates = []
    for candidate_index, candidate in enumerate(base.candidates):
        parts = tuple(
            evaluation.candidates[candidate_index] for evaluation in evaluations
        )
        continuation_probabilities = tuple(
            probability
            for part in parts
            for probability in part.continuation_championship_probabilities
        )
        playoffs = tuple(o for part in parts for o in part.playoff_outcomes)
        wins = tuple(w for part in parts for w in part.wins)
        points = tuple(p for part in parts for p in part.points)
        probability, error = _mean_and_error(continuation_probabilities)
        roster_values = tuple(
            value for part in parts for value in part.continuation_roster_values
        )
        roster_value, roster_value_error = _mean_and_error(roster_values)
        survivals = tuple(part.survival for part in parts)
        if any((survival is None) != (survivals[0] is None) for survival in survivals):
            raise ValueError("Cannot merge partially tracked survival reports")
        candidates.append(CandidateEvaluation(
            candidate_id=candidate.candidate_id,
            projected_roster_value=roster_value,
            projected_roster_value_standard_error=roster_value_error,
            projected_roster_value_interval=(
                roster_value - 1.96 * roster_value_error,
                roster_value + 1.96 * roster_value_error,
            ),
            continuation_roster_values=roster_values,
            championship_probability=probability,
            championship_standard_error=error,
            championship_interval=_probability_interval(probability, error),
            playoff_probability=sum(playoffs) / len(playoffs),
            expected_wins=sum(wins) / len(wins),
            expected_points=sum(points) / len(points),
            championship_outcomes=tuple(
                o for part in parts for o in part.championship_outcomes
            ),
            playoff_outcomes=playoffs,
            wins=wins,
            points=points,
            continuation_log_probabilities=tuple(
                value
                for part in parts
                for value in part.continuation_log_probabilities
            ),
            continuation_championship_probabilities=continuation_probabilities,
            survival=(
                merge_survival_reports(survivals)
                if survivals[0] is not None
                else None
            ),
            opportunity_cost=_merge_opportunity_costs(
                tuple(part.opportunity_cost for part in parts)
            ),
        ))
    return replace(
        base,
        rollout_ids=rollout_ids,
        world_indices=tuple(
            worlds for evaluation in evaluations for worlds in evaluation.world_indices
        ),
        candidates=tuple(candidates),
    )


def _merge_opportunity_costs(costs):
    if all(cost is None for cost in costs):
        return None
    if any(cost is None for cost in costs):
        raise ValueError("Cannot merge partially tracked opportunity costs")
    first = costs[0]
    identity = (
        first.current_marginal_value,
        first.next_user_pick_no,
        first.model_version,
    )
    if any(
        (cost.current_marginal_value, cost.next_user_pick_no, cost.model_version)
        != identity
        for cost in costs[1:]
    ):
        raise ValueError("Cannot merge incompatible opportunity costs")
    total = sum(cost.sample_count for cost in costs)

    def weighted(field):
        values = [
            (getattr(cost, field), cost.sample_count)
            for cost in costs
            if getattr(cost, field) is not None
        ]
        return (
            sum(value * count for value, count in values) / sum(count for _, count in values)
            if values
            else None
        )

    alternatives = {}
    for cost in costs:
        for player_id, probability in cost.later_alternative_distribution:
            alternatives[player_id] = alternatives.get(player_id, 0.0) + (
                probability * cost.sample_count
            )
    return DraftOpportunityCost(
        current_marginal_value=first.current_marginal_value,
        next_user_pick_no=first.next_user_pick_no,
        expected_best_later_value=weighted("expected_best_later_value"),
        expected_same_position_later_value=weighted(
            "expected_same_position_later_value"
        ),
        value_over_next_alternative=weighted("value_over_next_alternative"),
        positional_value_drop=weighted("positional_value_drop"),
        later_alternative_distribution=tuple(
            (player_id, count / total)
            for player_id, count in sorted(
                alternatives.items(), key=lambda item: (-item[1], item[0])
            )
        ),
        sample_count=total,
        model_version=first.model_version,
    )


def rank_candidates(evaluation):
    """Order by expected completed-roster projected value; equity breaks ties."""
    return tuple(
        sorted(
            evaluation.candidates,
            key=lambda candidate: (
                -candidate.projected_roster_value,
                -candidate.championship_probability,
                -candidate.playoff_probability,
                -candidate.expected_wins,
                -candidate.expected_points,
                candidate.candidate_id,
            ),
        )
    )


def candidate_vona(candidate):
    """Value over the expected best next-turn alternative; None-safe."""
    cost = candidate.opportunity_cost
    if cost is None or cost.value_over_next_alternative is None:
        return None
    return cost.value_over_next_alternative


def candidate_urgency(candidate):
    """Whole-point take-now urgency: positive VONA only.

    Negative VONA means waiting loses nothing, so it carries no ordering
    information — late-round VONA magnitudes are artifacts of how far below
    replacement the feasible pool sits, not real differences. Quantized to
    whole points because sub-point differences sit below the sampling
    precision of the expected-best-later estimate.
    """
    vona = candidate_vona(candidate)
    return 0 if vona is None else max(0, round(vona))


def tier_order(candidates, ranked, key=None):
    """Order statistically tied candidates by urgency, then ``key``.

    ``key`` refines ordering among equally urgent candidates; the live layer
    passes market ADP (and zeroes streamable K/DEF urgency): among
    interchangeable picks, prefer the asset the market values most — the one
    worth the most in a trade package.
    """
    ranked_index = {candidate.candidate_id: i for i, candidate in enumerate(ranked)}

    def sort_key(candidate):
        return (
            *(key(candidate) if key is not None else (-candidate_urgency(candidate),)),
            ranked_index[candidate.candidate_id],
        )

    return sorted(candidates, key=sort_key)


def recommendation_summary(evaluation, tier_key=None):
    """Rank candidates without inventing market-dependent reach/wait labels."""
    ranked = rank_candidates(evaluation)
    leader = ranked[0]
    co_leaders = tuple(
        candidate for candidate in ranked
        if candidate is leader
        or evaluation.paired_value_delta(
            leader.candidate_id, candidate.candidate_id
        ).interval[0] <= 0
    )
    decision_status = "clear_leader" if len(co_leaders) == 1 else "toss_up"
    # Projected value cannot separate a statistical tie, but urgency can:
    # headline the tied candidate least replaceable at the next turn (highest
    # value over the expected best next-turn alternative).
    best = tier_order(co_leaders, ranked, tier_key)[0]
    reasons = (
        ["PROJECTED_VALUE_LEADER"]
        if best is leader
        else ["PROJECTED_VALUE_TIE", "VONA_TIEBREAK"]
    )
    runner_up = next(
        (candidate for candidate in ranked if candidate is not best), None
    )
    delta = (
        evaluation.paired_delta(best.candidate_id, runner_up.candidate_id)
        if runner_up
        else None
    )
    value_delta = (
        evaluation.paired_value_delta(best.candidate_id, runner_up.candidate_id)
        if runner_up
        else None
    )
    if decision_status == "toss_up":
        reasons.append("LOW_CONFIDENCE_TOSS_UP")
    elif value_delta:
        reasons.append("PAIRED_VALUE_EDGE")
    availability = None
    if runner_up and runner_up.survival:
        players = tuple(
            player for player in runner_up.survival.players
            if player.player_id == best.candidate_id
        )
        if players:
            availability = replace(runner_up.survival, players=players)
    run_signature = sha256(
        repr((
            evaluation.state_signature,
            evaluation.rollout_ids,
            evaluation.world_indices,
            evaluation.seed,
            evaluation.decision_engine_version,
            evaluation.draft_model_version,
            evaluation.world_bank_version,
            evaluation.league_evaluator_version,
            tuple(candidate.candidate_id for candidate in ranked),
        )).encode()
    ).hexdigest()
    return RecommendationSummary(
        draft_id=evaluation.draft_id,
        state_pick_no=evaluation.state_pick_no,
        state_signature=evaluation.state_signature,
        run_signature=run_signature,
        user_roster_id=evaluation.user_roster_id,
        next_user_pick_no=evaluation.next_user_pick_no,
        recommended_candidate_id=best.candidate_id,
        runner_up_candidate_id=runner_up.candidate_id if runner_up else None,
        decision_status=decision_status,
        co_leader_candidate_ids=tuple(
            candidate.candidate_id for candidate in co_leaders
        ),
        projected_roster_value=best.projected_roster_value,
        projected_roster_value_interval=best.projected_roster_value_interval,
        paired_value_delta_vs_runner_up=value_delta,
        championship_probability=best.championship_probability,
        championship_interval=best.championship_interval,
        playoff_probability=best.playoff_probability,
        expected_wins=best.expected_wins,
        expected_points=best.expected_points,
        continuation_equity_percentiles=tuple(
            _percentile(best.continuation_championship_probabilities, percentile)
            for percentile in (0.1, 0.5, 0.9)
        ),
        paired_delta_vs_runner_up=delta,
        availability=availability,
        rollout_count=best.rollout_count,
        season_worlds_per_rollout=evaluation.season_worlds_per_rollout,
        joint_outcome_count=best.sample_count,
        seed=evaluation.seed,
        decision_engine_version=evaluation.decision_engine_version,
        draft_model_version=evaluation.draft_model_version,
        world_bank_version=evaluation.world_bank_version,
        league_evaluator_version=evaluation.league_evaluator_version,
        reason_codes=tuple(reasons),
    )


def _state_signature(state):
    return sha256(
        repr((
            state.draft_id,
            state.status,
            state.current_pick_no,
            state.current_roster_id,
            state.rosters,
            state.completed_picks,
            state.pick_owners,
            tuple(sorted(state.available_player_ids)),
        )).encode()
    ).hexdigest()


def coupled_world_indices(seed, rollout_id, world_count, count):
    """Select balanced deterministic worlds shared across candidate branches."""
    world_count = _positive_count(world_count, "world_count")
    count = _positive_count(count, "season_worlds_per_rollout")
    if count > world_count:
        raise ValueError("season_worlds_per_rollout exceeds the SeasonWorldBank size")
    seed = normalize_seed(seed)
    rollout_id = normalize_rollout_id(rollout_id)
    start = _hash_int(seed, 0, "world-start") % world_count
    if world_count == 1:
        return (0,)
    stride = _hash_int(seed, 0, "world-stride") % world_count
    while math.gcd(stride, world_count) != 1:
        stride = (stride + 1) % world_count
    offset = rollout_id * count
    return tuple(
        (start + (offset + sample) * stride) % world_count
        for sample in range(count)
    )


def _mean_and_error(values):
    values = tuple(float(value) for value in values)
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(variance / len(values))


def _probability_interval(probability, standard_error):
    """Normal interval from the across-rollout standard error.

    The same clustered estimator backs the paired deltas, so the marginal
    interval and the co-leader gate cannot disagree about precision.
    """
    margin = 1.96 * standard_error
    return max(0.0, probability - margin), min(1.0, probability + margin)


def _percentile(values, percentile):
    values = sorted(values)
    position = percentile * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _hash_int(seed, rollout_id, label):
    payload = f"{seed}\0{rollout_id}\0{label}".encode()
    return int.from_bytes(sha256(payload).digest()[:8], "big")


def _positive_count(value, field):
    try:
        value = index(value)
    except TypeError:
        raise ValueError(f"{field} must be a positive integer") from None
    if isinstance(value, bool) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _canonical_ids(values, field):
    values = tuple(str(value) for value in values)
    if any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{field} must contain unique non-empty IDs")
    return tuple(sorted(values))
