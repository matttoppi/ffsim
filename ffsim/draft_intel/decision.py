"""Joint draft-continuation and season-world candidate evaluation."""

from dataclasses import dataclass
from hashlib import sha256
import math
from operator import index

from ffsim.draft_intel.rollout import (
    SurvivalReport,
    complete_drafts,
    normalize_rollout_id,
    normalize_seed,
    summarize_survival,
)


DECISION_ENGINE_VERSION = 1


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
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

    @property
    def sample_count(self):
        return len(self.championship_outcomes)

    @property
    def rollout_count(self):
        return len(self.continuation_championship_probabilities)


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
class DecisionEvaluation:
    draft_id: str
    state_pick_no: int
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


@dataclass(frozen=True)
class RecommendationSummary:
    draft_id: str
    state_pick_no: int
    user_roster_id: int
    next_user_pick_no: int | None
    recommended_candidate_id: str
    runner_up_candidate_id: str | None
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
        evaluations.append(CandidateEvaluation(
            candidate_id=candidate_id,
            championship_probability=championship_probability,
            championship_standard_error=championship_error,
            championship_interval=_wilson_interval(
                championship_probability,
                len(continuation_probabilities),
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
                if survival_player_ids or tiers
                else None
            ),
        ))

    return DecisionEvaluation(
        draft_id=state.draft_id,
        state_pick_no=state.current_pick_no,
        user_roster_id=user_roster_id,
        next_user_pick_no=state.turn_for(user_roster_id).user_next_pick_no,
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


def recommendation_summary(evaluation):
    """Rank candidates without inventing market-dependent reach/wait labels."""
    ranked = sorted(
        evaluation.candidates,
        key=lambda candidate: (
            -candidate.championship_probability,
            -candidate.playoff_probability,
            -candidate.expected_wins,
            -candidate.expected_points,
            candidate.candidate_id,
        ),
    )
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    delta = (
        evaluation.paired_delta(best.candidate_id, runner_up.candidate_id)
        if runner_up
        else None
    )
    reasons = ["TITLE_EQUITY_LEADER"]
    if delta and delta.interval[0] > 0:
        reasons.append("PAIRED_CHAMPIONSHIP_EDGE")
    return RecommendationSummary(
        draft_id=evaluation.draft_id,
        state_pick_no=evaluation.state_pick_no,
        user_roster_id=evaluation.user_roster_id,
        next_user_pick_no=evaluation.next_user_pick_no,
        recommended_candidate_id=best.candidate_id,
        runner_up_candidate_id=runner_up.candidate_id if runner_up else None,
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
        availability=best.survival,
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


def coupled_world_indices(seed, rollout_id, world_count, count):
    """Select distinct deterministic worlds shared across candidate branches."""
    world_count = _positive_count(world_count, "world_count")
    count = _positive_count(count, "season_worlds_per_rollout")
    if count > world_count:
        raise ValueError("season_worlds_per_rollout exceeds the SeasonWorldBank size")
    seed = normalize_seed(seed)
    rollout_id = normalize_rollout_id(rollout_id)
    start = _hash_int(seed, rollout_id, "start") % world_count
    if world_count == 1:
        return (0,)
    stride = _hash_int(seed, rollout_id, "stride") % world_count
    while math.gcd(stride, world_count) != 1:
        stride = (stride + 1) % world_count
    return tuple((start + sample * stride) % world_count for sample in range(count))


def _mean_and_error(values):
    values = tuple(float(value) for value in values)
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(variance / len(values))


def _wilson_interval(probability, count):
    z = 1.96
    denominator = 1 + z**2 / count
    center = (probability + z**2 / (2 * count)) / denominator
    margin = z * math.sqrt(
        probability * (1 - probability) / count + z**2 / (4 * count**2)
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


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
