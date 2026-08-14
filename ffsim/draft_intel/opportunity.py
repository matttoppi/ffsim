"""Draft value and next-turn opportunity cost for the future-user policy."""

from collections import Counter

import numpy as np

from ffsim.draft_intel.decision import DraftOpportunityCost
from ffsim.draft_intel.market_model import position_caps, starting_lineup_needs
from ffsim.models.team import FLEX_ELIGIBILITY


VONA_MODEL_VERSION = "next-turn-vona-v1:conditional-hazard"


def season_value_over_replacement(evaluator):
    """Season projections and league-wide starter-cutline value."""
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


def next_turn_user_policy(evaluator, state, opponent_choice):
    """Choose future user picks by current plus expected next-turn value."""
    projection, position_of, replacement = season_value_over_replacement(evaluator)
    marginal_values = {
        player_id: points - replacement.get(position_of[player_id], 0.0)
        for player_id, points in projection.items()
    }
    slots = dict(evaluator.slot_counts)
    caps = position_caps(slots)
    roster_sizes = Counter(
        roster_id for roster_id in state.pick_owners if roster_id is not None
    )
    board_ids = opponent_choice.board_player_ids
    board_index = {player_id: index for index, player_id in enumerate(board_ids)}

    def policy(roster_id, pick_no, rosters, available):
        current_values = _roster_feasible_values(
            roster_id, rosters, available, marginal_values, position_of, slots,
            caps, roster_sizes,
        )
        next_turn = next_user_turn_pick_no(state.pick_owners, pick_no, roster_id)
        if next_turn is None:
            return current_values

        candidates = {}
        for player_id, value in current_values.items():
            position = position_of[player_id]
            incumbent = candidates.get(position)
            if incumbent is None or (-value, player_id) < (
                -current_values[incumbent], incumbent
            ):
                candidates[position] = player_id

        base_rosters = dict(rosters)
        base_mask = np.fromiter(
            (player_id in available for player_id in board_ids),
            bool,
            len(board_ids),
        )
        plans = []
        for candidate_id in candidates.values():
            future_rosters = {
                owner: list(players) for owner, players in base_rosters.items()
            }
            future_available = set(available)
            future_mask = base_mask.copy()
            future_rosters[roster_id].append(candidate_id)
            future_available.remove(candidate_id)
            if candidate_id in board_index:
                future_mask[board_index[candidate_id]] = False
            total = current_values[candidate_id]

            future_pick_no = pick_no + 1
            while (
                future_pick_no < next_turn
                and state.pick_owners[future_pick_no - 1] == roster_id
            ):
                adjacent = _roster_feasible_values(
                    roster_id, future_rosters, future_available, marginal_values,
                    position_of, slots, caps, roster_sizes,
                )
                selected = min(
                    adjacent,
                    key=lambda player_id: (-adjacent[player_id], player_id),
                )
                total += adjacent[selected]
                future_rosters[roster_id].append(selected)
                future_available.remove(selected)
                if selected in board_index:
                    future_mask[board_index[selected]] = False
                future_pick_no += 1

            later = _roster_feasible_values(
                roster_id, future_rosters, future_available, marginal_values,
                position_of, slots, caps, roster_sizes,
            )
            opponent_picks = next_turn - future_pick_no
            guaranteed = sorted(later.values(), reverse=True)[
                min(opponent_picks, len(later) - 1)
            ]
            plans.append((
                candidate_id, total, guaranteed, later, future_rosters,
                future_available, future_mask, future_pick_no,
            ))

        utilities = {}
        best_lower_bound = max(total + guaranteed for _, total, guaranteed, *_ in plans)
        for (
            candidate_id, total, guaranteed, later, future_rosters,
            future_available, future_mask, future_pick_no,
        ) in plans:
            optimistic = total + max(later.values())
            if optimistic < best_lower_bound:
                utilities[candidate_id] = optimistic
                continue
            survival = np.ones(len(board_ids))
            for opponent_pick_no in range(future_pick_no, next_turn):
                owner = state.pick_owners[opponent_pick_no - 1]
                ids, log_probabilities, _ = opponent_choice(
                    owner, opponent_pick_no, future_rosters, future_available,
                    mask=future_mask,
                )
                indices = np.fromiter(
                    map(board_index.__getitem__, ids),
                    int,
                    len(ids),
                )
                survival[indices] *= 1 - np.exp(log_probabilities)
                selected = ids[int(log_probabilities.argmax())]
                future_rosters[owner].append(selected)
                future_available.remove(selected)
                future_mask[board_index[selected]] = False

            # ponytail: marginal survival independence avoids nested rollouts;
            # replace with batched exact lookahead if telemetry shows regret.
            expected_best = 0.0
            better_gone = 1.0
            for player_id in sorted(
                later, key=lambda player_id: (-later[player_id], player_id)
            ):
                survives = (
                    float(survival[board_index[player_id]])
                    if player_id in board_index else 1.0
                )
                expected_best += later[player_id] * survives * better_gone
                better_gone *= 1 - survives
            utilities[candidate_id] = total + max(expected_best, guaranteed)
        return utilities

    def opportunity_evidence(root_state, candidate_id, completions):
        current = marginal_values[candidate_id]
        turns = root_state.future_turn_pick_nos(state.current_roster_id, count=1)
        next_turn = turns[0] if turns else None
        if next_turn is None:
            return DraftOpportunityCost(
                current, None, None, None, None, None, (), 0, VONA_MODEL_VERSION
            )

        best_values = []
        same_position_values = []
        best_players = Counter()
        candidate_position = position_of[candidate_id]
        for completion in completions:
            rosters = {
                owner: list(players) for owner, players in root_state.rosters
            }
            available = set(root_state.available_player_ids)
            for pick in completion.picks:
                if pick.pick_no >= next_turn:
                    break
                rosters[pick.roster_id].append(pick.player_id)
                available.remove(pick.player_id)
            later = _roster_feasible_values(
                state.current_roster_id, rosters, available, marginal_values,
                position_of, slots, caps, roster_sizes,
            )
            best = min(later, key=lambda player_id: (-later[player_id], player_id))
            best_players[best] += 1
            best_values.append(later[best])
            same_position_values.append(max(
                (
                    value for player_id, value in later.items()
                    if position_of[player_id] == candidate_position
                ),
                default=0.0,
            ))

        expected_best = sum(best_values) / len(best_values)
        expected_same_position = sum(same_position_values) / len(same_position_values)
        return DraftOpportunityCost(
            current_marginal_value=current,
            next_user_pick_no=next_turn,
            expected_best_later_value=expected_best,
            expected_same_position_later_value=expected_same_position,
            value_over_next_alternative=current - expected_best,
            positional_value_drop=current - expected_same_position,
            later_alternative_distribution=tuple(
                (player_id, count / len(completions))
                for player_id, count in sorted(
                    best_players.items(), key=lambda item: (-item[1], item[0])
                )
            ),
            sample_count=len(completions),
            model_version=VONA_MODEL_VERSION,
        )

    policy.opportunity_evidence = opportunity_evidence
    return policy


def _roster_feasible_values(
    roster_id, rosters, available, marginal_values, position_of, slots, caps,
    roster_sizes,
):
    mine = rosters[roster_id] if isinstance(rosters, dict) else dict(rosters)[roster_id]
    counts = Counter(position_of.get(player_id) for player_id in mine)
    needs = starting_lineup_needs(mine, position_of, slots)
    needed_positions = {position for need in needs for position in need}
    core_positions = needed_positions - {"K", "DEF"}
    remaining = roster_sizes[roster_id] - len(mine)
    allowed_positions = (
        needed_positions if needs and remaining <= len(needs) else core_positions
    )
    return {
        player_id: marginal_values[player_id]
        for player_id in marginal_values
        if player_id in available
        and (not allowed_positions or position_of[player_id] in allowed_positions)
        and (
            position_of[player_id] not in caps
            or counts[position_of[player_id]] < caps[position_of[player_id]]
        )
    }


def next_user_turn_pick_no(pick_owners, pick_no, roster_id):
    saw_opponent = False
    for future_pick_no in range(pick_no + 1, len(pick_owners) + 1):
        owner = pick_owners[future_pick_no - 1]
        if owner == roster_id:
            if saw_opponent:
                return future_pick_no
        else:
            saw_opponent = True
    return None
