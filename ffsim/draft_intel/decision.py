"""Joint draft-continuation and season-world candidate evaluation."""

from dataclasses import dataclass
from hashlib import sha256
import math

from ffsim.draft_intel.rollout import complete_drafts, normalize_rollout_id


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

    @property
    def sample_count(self):
        return len(self.championship_outcomes)


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
    rollout_ids: tuple[int, ...]
    world_indices: tuple[int, ...]
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
        mean, standard_error = _mean_and_error(differences)
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


def evaluate_candidates(
    state,
    candidate_ids,
    user_roster_id,
    rollout_ids,
    opponent_choice,
    user_policy,
    league_evaluator,
    *,
    seed=2026,
    temperature=1.0,
    use_cache=True,
):
    """Evaluate root candidates on paired draft continuations and season worlds."""
    candidate_ids = _canonical_ids(candidate_ids, "candidate_ids")
    if not candidate_ids:
        raise ValueError("candidate_ids must not be empty")
    rollout_ids = tuple(normalize_rollout_id(value) for value in rollout_ids)
    if len(rollout_ids) < 2 or len(set(rollout_ids)) != len(rollout_ids):
        raise ValueError("Root candidates require at least two unique rollout IDs")
    user_roster_id = int(user_roster_id)
    state_roster_ids = {roster_id for roster_id, _ in state.rosters}
    if set(league_evaluator.roster_ids) != state_roster_ids:
        raise ValueError("Draft state and league evaluator roster IDs do not match")
    if user_roster_id not in state_roster_ids:
        raise ValueError(f"Unknown user roster {user_roster_id}")

    world_indices = tuple(
        coupled_world_index(seed, rollout_id, league_evaluator.bank.world_count)
        for rollout_id in rollout_ids
    )
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
        for completion, world_index in zip(completions, world_indices):
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
                world_indices=(world_index,),
                use_cache=use_cache,
            )
            championships.append(bool(result.champion_indices[0] == user_index))
            playoffs.append(bool(result.playoffs[0, user_index]))
            wins.append(int(result.wins[0, user_index]))
            points.append(float(result.points[0, user_index]))
            log_probabilities.append(completion.opponent_log_probability)

        championship_probability, championship_error = _mean_and_error(championships)
        evaluations.append(CandidateEvaluation(
            candidate_id=candidate_id,
            championship_probability=championship_probability,
            championship_standard_error=championship_error,
            championship_interval=_wilson_interval(championships),
            playoff_probability=sum(playoffs) / len(playoffs),
            expected_wins=sum(wins) / len(wins),
            expected_points=sum(points) / len(points),
            championship_outcomes=tuple(championships),
            playoff_outcomes=tuple(playoffs),
            wins=tuple(wins),
            points=tuple(points),
            continuation_log_probabilities=tuple(log_probabilities),
        ))

    return DecisionEvaluation(
        draft_id=state.draft_id,
        state_pick_no=state.current_pick_no,
        user_roster_id=user_roster_id,
        rollout_ids=rollout_ids,
        world_indices=world_indices,
        world_bank_version=league_evaluator.bank.version,
        league_evaluator_version=league_evaluator.version,
        candidates=tuple(evaluations),
    )


def coupled_world_index(seed, rollout_id, world_count):
    """Map one rollout to the same season world across candidate branches."""
    if world_count < 1:
        raise ValueError("world_count must be positive")
    payload = f"{int(seed)}\0{normalize_rollout_id(rollout_id)}".encode()
    return int.from_bytes(sha256(payload).digest()[:8], "big") % world_count


def _mean_and_error(values):
    values = tuple(float(value) for value in values)
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(variance / len(values))


def _wilson_interval(values):
    values = tuple(bool(value) for value in values)
    count = len(values)
    probability = sum(values) / count
    z = 1.96
    denominator = 1 + z**2 / count
    center = (probability + z**2 / (2 * count)) / denominator
    margin = z * math.sqrt(
        probability * (1 - probability) / count + z**2 / (4 * count**2)
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _canonical_ids(values, field):
    values = tuple(str(value) for value in values)
    if any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{field} must contain unique non-empty IDs")
    return tuple(sorted(values))
