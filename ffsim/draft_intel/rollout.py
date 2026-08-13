"""Coupled, sequential rest-of-draft simulation from an immutable draft state."""

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import math
from operator import index


@dataclass(frozen=True)
class RolloutPick:
    pick_no: int
    roster_id: int
    player_id: str
    probability: float
    user_pick: bool


@dataclass(frozen=True)
class DraftCompletion:
    rollout_id: int
    root_candidate_id: str
    next_user_pick_no: int | None
    initial_available_player_ids: frozenset[str]
    picks: tuple[RolloutPick, ...]
    rosters: tuple[tuple[int, tuple[str, ...]], ...]
    remaining_player_ids: frozenset[str]
    opponent_log_probability: float


@dataclass(frozen=True)
class PlayerSurvival:
    player_id: str
    survives_to_next_pick: float
    pick_hazard: tuple[tuple[int, float], ...]
    threat_share: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class TierSurvival:
    tier_id: str
    survives_to_next_pick: float
    expected_remaining: float
    exhaustion_probability: float
    remaining_count_probabilities: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class SurvivalReport:
    rollout_count: int
    players: tuple[PlayerSurvival, ...]
    tiers: tuple[TierSurvival, ...]


def choice_probabilities(utilities, temperature=1.0):
    """Return a stable softmax over canonical player IDs."""
    return tuple(
        (player_id, math.exp(log_probability))
        for player_id, log_probability in _log_probabilities(utilities, temperature)
    )


def complete_drafts(
    state,
    root_candidate_id,
    user_roster_id,
    rollout_ids,
    opponent_choice,
    user_policy,
    *,
    seed=2026,
    temperature=1.0,
):
    """Sample multiple target-distribution draft completions for one root pick."""
    if state.draft_type not in {"snake", "linear"}:
        raise ValueError("Future draft rollouts require predetermined pick ownership")
    user_roster_id = int(user_roster_id)
    if state.current_roster_id != user_roster_id:
        raise ValueError("The configured user roster is not on the clock")
    root_candidate_id = str(root_candidate_id)
    if root_candidate_id not in state.available_player_ids:
        raise ValueError(f"Root candidate {root_candidate_id} is not available")
    rollout_ids = tuple(normalize_rollout_id(value) for value in rollout_ids)
    if len(rollout_ids) < 2 or len(set(rollout_ids)) != len(rollout_ids):
        raise ValueError("Root candidates require at least two unique rollout IDs")
    if not callable(opponent_choice) or not callable(user_policy):
        raise TypeError("opponent_choice and user_policy must be callable")
    seed = normalize_seed(seed)
    temperature = _temperature(temperature)

    return tuple(
        _complete_draft(
            state,
            root_candidate_id,
            user_roster_id,
            rollout_id,
            opponent_choice,
            user_policy,
            seed,
            temperature,
        )
        for rollout_id in rollout_ids
    )


def summarize_survival(completions, player_ids=(), tiers=None):
    """Summarize exact-player and tier availability at the next user pick."""
    completions = tuple(completions)
    if len(completions) < 2:
        raise ValueError("Survival estimates require at least two draft completions")
    first = completions[0]
    if first.next_user_pick_no is None:
        raise ValueError("The user has no later pick in this draft")
    if any(
        completion.root_candidate_id != first.root_candidate_id
        or completion.next_user_pick_no != first.next_user_pick_no
        or completion.initial_available_player_ids != first.initial_available_player_ids
        for completion in completions[1:]
    ):
        raise ValueError("Draft completions do not share one root state and candidate")
    if len({completion.rollout_id for completion in completions}) != len(completions):
        raise ValueError("Draft completions require unique rollout IDs")

    player_ids = _canonical_ids(player_ids, "player_ids")
    unknown = set(player_ids) - first.initial_available_player_ids
    if unknown:
        raise ValueError(f"Tracked player {sorted(unknown)[0]} was not initially available")
    horizon = first.next_user_pick_no
    count = len(completions)
    tracked = set(player_ids)
    hazards = {player_id: Counter() for player_id in player_ids}
    threats = {player_id: Counter() for player_id in player_ids}
    eliminated = Counter()
    selected_before = []
    for completion in completions:
        before = set()
        for pick in completion.picks:
            if pick.pick_no < horizon:
                before.add(pick.player_id)
            if pick.player_id not in tracked:
                continue
            hazards[pick.player_id][pick.pick_no] += 1
            if pick.pick_no < horizon:
                eliminated[pick.player_id] += 1
                if not pick.user_pick:
                    threats[pick.player_id][pick.roster_id] += 1
        selected_before.append(before)
    players = []
    for player_id in player_ids:
        threat_total = sum(threats[player_id].values())
        players.append(PlayerSurvival(
            player_id=player_id,
            survives_to_next_pick=1 - eliminated[player_id] / count,
            pick_hazard=tuple(
                (pick_no, occurrences / count)
                for pick_no, occurrences in sorted(hazards[player_id].items())
            ),
            threat_share=tuple(
                (roster_id, occurrences / threat_total)
                for roster_id, occurrences in sorted(threats[player_id].items())
            ),
        ))

    tier_results = []
    for tier_id, raw_player_ids in sorted((tiers or {}).items(), key=lambda item: str(item[0])):
        tier_player_ids = _canonical_ids(raw_player_ids, f"tier {tier_id}")
        if not tier_player_ids:
            raise ValueError(f"tier {tier_id} must not be empty")
        unknown = set(tier_player_ids) - first.initial_available_player_ids
        if unknown:
            raise ValueError(f"Tier player {sorted(unknown)[0]} was not initially available")
        remaining_counts = Counter(
            sum(player_id not in selected for player_id in tier_player_ids)
            for selected in selected_before
        )
        probabilities = tuple(
            (remaining, occurrences / count)
            for remaining, occurrences in sorted(remaining_counts.items())
        )
        exhausted = remaining_counts[0] / count
        tier_results.append(TierSurvival(
            tier_id=str(tier_id),
            survives_to_next_pick=1 - exhausted,
            expected_remaining=sum(remaining * probability for remaining, probability in probabilities),
            exhaustion_probability=exhausted,
            remaining_count_probabilities=probabilities,
        ))

    return SurvivalReport(count, tuple(players), tuple(tier_results))


def stable_gumbel(seed, rollout_id, pick_no, roster_id, player_id):
    """Return one deterministic Gumbel(0, 1) shock from stable identifiers."""
    seed = normalize_seed(seed)
    payload = "\0".join(map(str, (seed, rollout_id, pick_no, roster_id, player_id)))
    integer = int.from_bytes(sha256(payload.encode()).digest()[:8], "big") >> 11
    uniform = (integer + 1) / (2**53 + 2)
    return -math.log(-math.log(uniform))


def _complete_draft(
    state,
    root_candidate_id,
    user_roster_id,
    rollout_id,
    opponent_choice,
    user_policy,
    seed,
    temperature,
):
    initial_available = state.available_player_ids
    all_players = initial_available | state.selected_player_ids
    available = set(initial_available)
    rosters = {roster_id: list(players) for roster_id, players in state.rosters}
    current_pick_no = state.current_pick_no
    next_user_pick_no = next(
        (
            pick_no
            for pick_no in range(current_pick_no + 1, len(state.pick_owners) + 1)
            if state.pick_owners[pick_no - 1] == user_roster_id
        ),
        None,
    )
    picks = [RolloutPick(current_pick_no, user_roster_id, root_candidate_id, 1.0, True)]
    rosters[user_roster_id].append(root_candidate_id)
    available.remove(root_candidate_id)
    log_probability = 0.0

    for pick_no in range(current_pick_no + 1, len(state.pick_owners) + 1):
        roster_id = state.pick_owners[pick_no - 1]
        if roster_id is None:
            raise ValueError(f"Pick {pick_no} has no predetermined owner")
        roster_view = tuple(
            (owner, tuple(players)) for owner, players in sorted(rosters.items())
        )
        available_view = frozenset(available)
        raw_utilities = (
            user_policy(roster_id, pick_no, roster_view, available_view)
            if roster_id == user_roster_id
            else opponent_choice(roster_id, pick_no, roster_view, available_view)
        )
        utilities = _available_utilities(raw_utilities, available, all_players)
        if roster_id == user_roster_id:
            player_id = min(
                utilities,
                key=lambda candidate: (-utilities[candidate], candidate),
            )
            probability = 1.0
        else:
            log_probabilities = dict(_log_probabilities(utilities, temperature))
            player_id = _gumbel_choice(
                log_probabilities,
                seed,
                rollout_id,
                pick_no,
                roster_id,
            )
            log_probability += log_probabilities[player_id]
            probability = math.exp(log_probabilities[player_id])
        picks.append(RolloutPick(
            pick_no,
            roster_id,
            player_id,
            probability,
            roster_id == user_roster_id,
        ))
        rosters[roster_id].append(player_id)
        available.remove(player_id)

    return DraftCompletion(
        rollout_id=rollout_id,
        root_candidate_id=root_candidate_id,
        next_user_pick_no=next_user_pick_no,
        initial_available_player_ids=initial_available,
        picks=tuple(picks),
        rosters=tuple(
            (roster_id, tuple(players))
            for roster_id, players in sorted(rosters.items())
        ),
        remaining_player_ids=frozenset(available),
        opponent_log_probability=log_probability,
    )


def _gumbel_choice(log_probabilities, seed, rollout_id, pick_no, roster_id):
    prefix = sha256(
        ("\0".join(map(str, (seed, rollout_id, pick_no, roster_id))) + "\0").encode()
    )

    def score(player_id):
        digest = prefix.copy()
        digest.update(player_id.encode())
        integer = int.from_bytes(digest.digest()[:8], "big") >> 11
        uniform = (integer + 1) / (2**53 + 2)
        return log_probabilities[player_id] - math.log(-math.log(uniform))

    return max(sorted(log_probabilities), key=score)


def _available_utilities(utilities, available, all_players):
    normalized = _normalized_utilities(utilities)
    unknown = set(normalized) - all_players
    if unknown:
        raise ValueError(f"Choice model returned unknown player {sorted(unknown)[0]}")
    result = {player_id: utility for player_id, utility in normalized.items() if player_id in available}
    if not result:
        raise ValueError("Choice model returned no available players")
    return result


def _log_probabilities(utilities, temperature):
    temperature = _temperature(temperature)
    normalized = _normalized_utilities(utilities)
    if not normalized:
        raise ValueError("utilities must not be empty")
    scaled = {player_id: utility / temperature for player_id, utility in normalized.items()}
    maximum = max(scaled.values())
    denominator = sum(math.exp(utility - maximum) for utility in scaled.values())
    normalizer = maximum + math.log(denominator)
    return tuple(
        (player_id, scaled[player_id] - normalizer)
        for player_id in sorted(scaled)
    )


def _normalized_utilities(utilities):
    try:
        items = tuple(utilities.items())
    except AttributeError:
        raise TypeError("utilities must be a mapping") from None
    normalized = {str(player_id): float(utility) for player_id, utility in items}
    if len(normalized) != len(items):
        raise ValueError("utilities contain duplicate canonical player IDs")
    if any(not player_id or not math.isfinite(utility) for player_id, utility in normalized.items()):
        raise ValueError("utilities require non-empty player IDs and finite values")
    return normalized


def _canonical_ids(player_ids, field):
    values = tuple(str(player_id) for player_id in player_ids)
    if any(not player_id for player_id in values) or len(set(values)) != len(values):
        raise ValueError(f"{field} must contain unique non-empty player IDs")
    return tuple(sorted(values))


def normalize_rollout_id(value):
    return _nonnegative_integer(value, "rollout IDs")


def normalize_seed(value):
    return _nonnegative_integer(value, "seed")


def _nonnegative_integer(value, field):
    try:
        value = index(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a non-negative integer") from None
    if isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _temperature(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError("temperature must be finite and positive") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError("temperature must be finite and positive")
    return value
