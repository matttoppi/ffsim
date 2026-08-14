"""Draft value and next-turn opportunity cost for the future-user policy."""

from collections import Counter

import numpy as np

from ffsim.draft_intel.decision import DraftOpportunityCost
from ffsim.draft_intel.market_model import position_caps, starting_lineup_needs
from ffsim.models.team import FLEX_ELIGIBILITY
from ffsim.simulation.evaluator import BENCH_ASSET_FACTOR


VONA_MODEL_VERSION = "next-turn-vona-v2:terminal-marginal"

# Orders terminal-equivalent (mostly zero-marginal late) picks by raw
# projection instead of lexicographic player ID. Small enough that it can
# never reorder players the terminal scorer actually separates.
_PROJECTION_TIEBREAK = 1e-9


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
    """Choose future user picks by current plus expected next-turn value.

    Player values mirror the terminal roster scorer
    (``LeagueEvaluator.projected_roster_value``, ADR-027/029): the value
    basis is the scorer's own availability-discounted, cutline-floored flat
    scores (``flat_season_scores``), full credit goes only to a greedy-lineup
    seat (flex-aware, seating decided by raw projection exactly like
    ``_lineup_order``), and bench assets earn ``BENCH_ASSET_FACTOR`` of value
    over the cutline. Keeping the two consistent stops the wait branch from
    leaking value the root-forced branch captures, which produced phantom
    paired edges for high-survival candidates (ADR-031).
    """
    projection, position_of, replacement = season_value_over_replacement(evaluator)
    weeks = len(evaluator.bank.weeks)
    weekly_cut = {
        position: value / weeks for position, value in replacement.items()
    }
    flat = getattr(evaluator, "flat_season_scores", None)
    if flat is None:
        # Bare test evaluators without score tensors: full availability at
        # the projection mean, which makes starter points equal projection.
        starter_points = dict(projection)
        available_weeks = {player_id: weeks for player_id in projection}
    else:
        scores, available = flat()
        player_index = {
            player_id: index
            for index, player_id in enumerate(evaluator.bank.player_ids)
        }
        starter_points = {
            player_id: float(scores[player_index[player_id]].sum())
            for player_id in projection
        }
        available_weeks = {
            player_id: int(available[player_index[player_id]].sum())
            for player_id in projection
        }
    floored_values = {
        player_id: max(
            0.0,
            points
            - available_weeks[player_id]
            * weekly_cut.get(position_of[player_id], 0.0),
        )
        for player_id, points in starter_points.items()
    }
    value_model = (
        floored_values, projection, position_of, weekly_cut, available_weeks,
    )
    slots = dict(evaluator.slot_counts)
    caps = position_caps(slots)
    roster_sizes = Counter(
        roster_id for roster_id in state.pick_owners if roster_id is not None
    )
    board_ids = opponent_choice.board_player_ids
    board_index = {player_id: index for index, player_id in enumerate(board_ids)}

    def policy(roster_id, pick_no, rosters, available):
        current_values = _roster_feasible_values(
            roster_id, rosters, available, value_model, slots, caps,
            roster_sizes,
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
                    roster_id, future_rosters, future_available, value_model,
                    slots, caps, roster_sizes,
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
                roster_id, future_rosters, future_available, value_model,
                slots, caps, roster_sizes,
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
        # Terminal marginal value against the root roster: same scale as the
        # later-alternative values, so VONA differences are roster-value
        # differences. Never feasibility-filtered (a legal root candidate is
        # priced, not excluded).
        root_roster = dict(root_state.rosters)[state.current_roster_id]
        root_summary = _seat_summary(
            root_roster, projection, floored_values, position_of, slots,
            weekly_cut, available_weeks,
        )
        current = _terminal_marginal(candidate_id, root_summary, value_model)
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
                state.current_roster_id, rosters, available, value_model,
                slots, caps, roster_sizes,
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


def _seat_summary(mine, projection, values, position_of, slots, weekly_cut, available_weeks):
    """Greedy seat assignment of a roster under the terminal scorer's rules.

    Mirrors ``projected_roster_value``: players are seated in raw-projection
    order (``_lineup_order``), dedicated slots first, then flex slots in
    ``FLEX_ELIGIBILITY`` order. Gains are priced in the scorer's floored
    flat-score units: a seat's opportunity cost is its weekly streamer level
    (the position cutline for dedicated seats, the best eligible cutline for
    flex seats) over the occupant's available weeks.

    Returns per position ``(dedicated_open, open_flex_weekly_cutline,
    displaced_player_id, displaced_seat_weekly_cutline)``.
    """
    ranked = sorted(
        mine, key=lambda player_id: (-projection.get(player_id, 0.0), player_id)
    )
    used = set()
    occupants_by_slot = {}
    open_seats = {}
    seat_cutlines = {}
    for slot, count in slots.items():
        if slot in FLEX_ELIGIBILITY:
            continue
        occupants = [
            player_id for player_id in ranked
            if player_id not in used and position_of.get(player_id) == slot
        ][:count]
        used.update(occupants)
        occupants_by_slot[slot] = occupants
        open_seats[slot] = count - len(occupants)
        seat_cutlines[slot] = weekly_cut.get(slot, 0.0)
    for slot, eligible in FLEX_ELIGIBILITY.items():
        count = slots.get(slot, 0)
        if not count:
            continue
        occupants = [
            player_id for player_id in ranked
            if player_id not in used and position_of.get(player_id) in eligible
        ][:count]
        used.update(occupants)
        occupants_by_slot[slot] = occupants
        open_seats[slot] = count - len(occupants)
        seat_cutlines[slot] = max(
            weekly_cut.get(position, 0.0) for position in eligible
        )

    summary = {}
    for position in ("QB", "RB", "WR", "TE", "K", "DEF"):
        dedicated_open = bool(open_seats.get(position, 0))
        open_flex_cut = None
        displaced = None
        displaced_seat_cut = 0.0
        for slot, occupants in occupants_by_slot.items():
            eligible = FLEX_ELIGIBILITY.get(slot)
            if eligible is None:
                if slot != position:
                    continue
            elif position not in eligible:
                continue
            else:
                if open_seats[slot] > 0 and (
                    open_flex_cut is None or seat_cutlines[slot] < open_flex_cut
                ):
                    open_flex_cut = seat_cutlines[slot]
            for player_id in occupants:
                if displaced is None or (
                    projection.get(player_id, 0.0)
                    < projection.get(displaced, 0.0)
                ):
                    displaced = player_id
                    displaced_seat_cut = seat_cutlines[slot]
        summary[position] = (
            dedicated_open, open_flex_cut, displaced, displaced_seat_cut
        )
    return summary


def _terminal_marginal(player_id, summary, value_model):
    """Marginal terminal roster value of adding one player (season units).

    Exactly the scorer's cases: an open dedicated seat pays value over the
    position cutline; an open flex seat pays the availability-adjusted value
    over the flex streamer; a player who outranks a current starter in raw
    projection is seated by the greedy lineup (decision by raw projection,
    ``_lineup_order`` semantics) and pays the seat-adjusted value difference
    while the displaced starter keeps ``BENCH_ASSET_FACTOR`` of his value —
    honestly negative when the greedy seats a raw-better but floored-worse
    player; otherwise the player is a discounted bench asset.
    """
    values, projection, position_of, weekly_cut, available_weeks = value_model

    def seat_adjusted(candidate, seat_cut):
        # Starter points over the seat's streamer level for the candidate's
        # available weeks: value over his own cutline minus the cutline gap.
        position = position_of[candidate]
        return values[candidate] - available_weeks[candidate] * (
            seat_cut - weekly_cut.get(position, 0.0)
        )

    position = position_of[player_id]
    value = values[player_id]
    dedicated_open, flex_cut, displaced, displaced_seat_cut = summary.get(
        position, (False, None, None, 0.0)
    )
    if dedicated_open:
        return value
    if flex_cut is not None:
        return seat_adjusted(player_id, flex_cut)
    if displaced is not None and (
        projection.get(player_id, 0.0) > projection.get(displaced, 0.0)
    ):
        return (
            seat_adjusted(player_id, displaced_seat_cut)
            - seat_adjusted(displaced, displaced_seat_cut)
            + BENCH_ASSET_FACTOR * values.get(displaced, 0.0)
        )
    return BENCH_ASSET_FACTOR * value


def _roster_feasible_values(
    roster_id, rosters, available, value_model, slots, caps, roster_sizes,
):
    values, projection, position_of, weekly_cut, available_weeks = value_model
    mine = rosters[roster_id] if isinstance(rosters, dict) else dict(rosters)[roster_id]
    counts = Counter(position_of.get(player_id) for player_id in mine)
    needs = starting_lineup_needs(mine, position_of, slots)
    needed_positions = {position for need in needs for position in need}
    remaining = roster_sizes[roster_id] - len(mine)
    # Only the end-of-draft feasibility guard restricts positions: every
    # remaining pick must fill an open starter seat. Before that boundary the
    # terminal marginal prices the choice itself — an open seat pays full
    # value over the cutline while bench depth pays the discounted asset
    # fraction — so a hard "core starters first" gate would re-create the
    # ADR-030 phantom edges by refusing flex/bench players the terminal
    # scorer values (measured: the policy skipped a 99%-survival TE in
    # 148/148 wait rollouts because open QB/RB seats gated TE out entirely).
    allowed_positions = (
        needed_positions if needs and remaining <= len(needs) else set()
    )
    summary = _seat_summary(
        mine, projection, values, position_of, slots, weekly_cut,
        available_weeks,
    )
    # Per-position piecewise parameters make the per-player marginal a couple
    # of arithmetic ops: profiling showed the per-player _terminal_marginal
    # call dominating the policy (1.3M calls per 50 continuations).
    params = {}
    for position, (dedicated_open, flex_cut, displaced, seat_cut) in summary.items():
        own_cut = weekly_cut.get(position, 0.0)
        if dedicated_open:
            params[position] = (0, 0.0, 0.0, 0.0)
        elif flex_cut is not None:
            params[position] = (1, flex_cut - own_cut, 0.0, 0.0)
        elif displaced is not None:
            displaced_value = values.get(displaced, 0.0)
            displaced_adjusted = displaced_value - available_weeks[displaced] * (
                seat_cut - weekly_cut.get(position_of.get(displaced), 0.0)
            )
            params[position] = (
                2,
                seat_cut - own_cut,
                projection.get(displaced, 0.0),
                BENCH_ASSET_FACTOR * displaced_value - displaced_adjusted,
            )
        else:
            params[position] = (3, 0.0, 0.0, 0.0)
    result = {}
    tiebreak = _PROJECTION_TIEBREAK
    bench = BENCH_ASSET_FACTOR
    for player_id, value in values.items():
        if player_id not in available:
            continue
        position = position_of[player_id]
        if allowed_positions and position not in allowed_positions:
            continue
        if position in caps and counts[position] >= caps[position]:
            continue
        raw = projection[player_id]
        mode, gap, displaced_projection, base = params.get(
            position, (3, 0.0, 0.0, 0.0)
        )
        if mode == 0:
            marginal = value
        elif mode == 1:
            marginal = value - available_weeks[player_id] * gap
        elif mode == 2 and raw > displaced_projection:
            marginal = value - available_weeks[player_id] * gap + base
        else:
            marginal = bench * value
        result[player_id] = marginal + tiebreak * raw
    return result


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
