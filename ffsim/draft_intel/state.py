from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class DraftPick:
    pick_no: int
    round: int
    draft_slot: int
    roster_id: int
    picked_by: str | None
    player_id: str
    position: str | None
    price: int | None


@dataclass(frozen=True)
class DraftTurn:
    current_pick_no: int | None
    current_roster_id: int | None
    user_current_pick_no: int | None
    user_next_pick_no: int | None
    future_user_pick_nos: tuple[int, ...]
    opponent_roster_ids_until_next: tuple[int, ...]

    @property
    def opponent_pick_counts(self):
        return tuple(sorted(Counter(self.opponent_roster_ids_until_next).items()))

    @property
    def back_to_back_roster_ids(self):
        return tuple(dict.fromkeys(
            left
            for left, right in pairwise(self.opponent_roster_ids_until_next)
            if left == right
        ))


@dataclass(frozen=True)
class DraftState:
    draft_id: str
    draft_type: str
    status: str
    teams: int
    rounds: int
    reversal_round: int
    completed_picks: tuple[DraftPick, ...]
    pick_slots: tuple[int | None, ...]
    pick_owners: tuple[int | None, ...]
    manager_roster_ids: tuple[tuple[str, int], ...]
    rosters: tuple[tuple[int, tuple[str, ...]], ...]
    selected_player_ids: frozenset[str]
    available_player_ids: frozenset[str]
    remaining_budgets: tuple[tuple[int, int], ...]

    @property
    def current_pick_no(self):
        next_pick = len(self.completed_picks) + 1
        return next_pick if next_pick <= len(self.pick_owners) else None

    @property
    def current_roster_id(self):
        return (
            self.pick_owners[self.current_pick_no - 1]
            if self.current_pick_no is not None
            else None
        )

    def roster_player_ids(self, roster_id):
        try:
            return dict(self.rosters)[int(roster_id)]
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Unknown roster {roster_id}") from None

    def roster_id_for_manager(self, manager_id):
        try:
            return dict(self.manager_roster_ids)[str(manager_id)]
        except KeyError:
            raise ValueError(f"Unknown draft manager {manager_id}") from None

    def turn_for(self, roster_id, future_pick_count=3):
        roster_id = int(roster_id)
        if roster_id not in dict(self.rosters):
            raise ValueError(f"Unknown roster {roster_id}")
        if self.draft_type == "auction":
            raise ValueError("Auction future roster ownership is not predetermined")
        if future_pick_count < 1:
            raise ValueError("future_pick_count must be positive")

        current = self.current_pick_no
        if current is None:
            return DraftTurn(None, None, None, None, (), ())
        future = tuple(
            pick_no
            for pick_no in range(current, len(self.pick_owners) + 1)
            if self.pick_owners[pick_no - 1] == roster_id
        )
        on_clock = self.current_roster_id == roster_id
        next_index = 1 if on_clock else 0
        next_pick = future[next_index] if len(future) > next_index else None
        opponent_start = current + 1 if on_clock else current
        opponents = (
            tuple(
                owner
                for owner in self.pick_owners[opponent_start - 1:next_pick - 1]
                if owner is not None and owner != roster_id
            )
            if next_pick is not None
            else ()
        )
        future_after_current = future[1:] if on_clock else future
        return DraftTurn(
            current_pick_no=current,
            current_roster_id=self.current_roster_id,
            user_current_pick_no=current if on_clock else None,
            user_next_pick_no=next_pick,
            future_user_pick_nos=future_after_current[:future_pick_count],
            opponent_roster_ids_until_next=opponents,
        )

    def future_turn_pick_nos(self, roster_id, count=3):
        """First pick of each future turn, grouping adjacent snake picks."""
        if count < 1:
            raise ValueError("count must be positive")
        turn = self.turn_for(roster_id, future_pick_count=len(self.pick_owners))
        previous = self.current_pick_no if turn.user_current_pick_no is not None else None
        result = []
        for pick_no in turn.future_user_pick_nos:
            if previous is None or pick_no != previous + 1:
                result.append(pick_no)
                if len(result) == count:
                    break
            previous = pick_no
        return tuple(result)


def replay_sleeper_draft(draft, picks, traded_picks, player_ids):
    draft_id = _required_text(draft, "draft_id")
    draft_type = _required_text(draft, "type")
    if draft_type not in {"snake", "linear", "auction"}:
        raise ValueError(f"Unsupported draft type: {draft_type}")

    settings = draft.get("settings") or {}
    teams = _positive_int(settings.get("teams"), "draft teams")
    rounds = _positive_int(settings.get("rounds"), "draft rounds")
    reversal_round = _nonnegative_int(
        settings.get("reversal_round"),
        "draft reversal round",
    )
    roster_by_slot = _roster_by_slot(draft, teams)
    manager_roster_ids = []
    for manager_id, raw_slot in (draft.get("draft_order") or {}).items():
        slot = _positive_int(raw_slot, "draft order slot")
        if slot not in roster_by_slot:
            raise ValueError(f"Draft manager {manager_id} has unknown slot {slot}")
        manager_roster_ids.append((str(manager_id), roster_by_slot[slot]))
    manager_roster_ids = tuple(sorted(manager_roster_ids))

    pick_slots = _pick_slots(draft_type, teams, rounds, reversal_round)
    pick_owners = _pick_owners(
        draft_id,
        draft_type,
        teams,
        rounds,
        roster_by_slot,
        traded_picks,
        pick_slots,
    )
    normalized_picks = _normalize_picks(
        draft_id,
        draft_type,
        teams,
        pick_slots,
        pick_owners,
        roster_by_slot,
        picks,
    )
    if (
        str(draft.get("status") or "unknown") == "complete"
        and len(normalized_picks) != teams * rounds
    ):
        raise ValueError(f"Completed draft {draft_id} does not contain every pick")

    pool = frozenset(str(player_id) for player_id in player_ids)
    selected = frozenset(pick.player_id for pick in normalized_picks)
    missing = selected - pool
    if missing:
        raise ValueError(f"Selected player {sorted(missing)[0]} is missing from the player pool")

    rosters = defaultdict(list)
    for roster_id in roster_by_slot.values():
        rosters[roster_id]
    for pick in normalized_picks:
        rosters[pick.roster_id].append(pick.player_id)

    if draft_type == "auction":
        budget = _positive_int(settings.get("budget"), "auction budget")
        spent = Counter()
        for pick in normalized_picks:
            spent[pick.roster_id] += pick.price
        if any(amount > budget for amount in spent.values()):
            raise ValueError(f"Auction spend exceeds the {budget} budget")
        remaining_budgets = tuple(
            (roster_id, budget - spent[roster_id]) for roster_id in sorted(rosters)
        )
        mutable_owners = list(pick_owners)
        mutable_slots = list(pick_slots)
        for pick in normalized_picks:
            mutable_owners[pick.pick_no - 1] = pick.roster_id
            mutable_slots[pick.pick_no - 1] = pick.draft_slot
        pick_owners = tuple(mutable_owners)
        pick_slots = tuple(mutable_slots)
    else:
        remaining_budgets = ()

    return DraftState(
        draft_id=draft_id,
        draft_type=draft_type,
        status=str(draft.get("status") or "unknown"),
        teams=teams,
        rounds=rounds,
        reversal_round=reversal_round,
        completed_picks=normalized_picks,
        pick_slots=pick_slots,
        pick_owners=pick_owners,
        manager_roster_ids=manager_roster_ids,
        rosters=tuple(
            (roster_id, tuple(players))
            for roster_id, players in sorted(rosters.items())
        ),
        selected_player_ids=selected,
        available_player_ids=pool - selected,
        remaining_budgets=remaining_budgets,
    )


def reconcile_sleeper_draft(previous, draft, picks, traded_picks, player_ids):
    current = replay_sleeper_draft(draft, picks, traded_picks, player_ids)
    if (
        current.draft_id != previous.draft_id
        or current.draft_type != previous.draft_type
        or current.teams != previous.teams
        or current.rounds != previous.rounds
        or current.reversal_round != previous.reversal_round
    ):
        raise ValueError("Draft identity or geometry changed during reconciliation")
    previous_count = len(previous.completed_picks)
    if current.completed_picks[:previous_count] != previous.completed_picks:
        raise ValueError("Sleeper rewrote or removed an already observed pick")
    return current


def _roster_by_slot(draft, teams):
    roster_by_slot = {
        _positive_int(slot, "draft slot"): _positive_int(roster_id, "roster ID")
        for slot, roster_id in (draft.get("slot_to_roster_id") or {}).items()
    }
    if set(roster_by_slot) != set(range(1, teams + 1)):
        raise ValueError("slot_to_roster_id must contain every draft slot")
    if len(set(roster_by_slot.values())) != teams:
        raise ValueError("slot_to_roster_id must contain unique rosters")
    return roster_by_slot


def _pick_slots(draft_type, teams, rounds, reversal_round):
    if draft_type == "auction":
        return (None,) * (teams * rounds)

    slots = []
    for round_number in range(1, rounds + 1):
        descending = draft_type == "snake" and round_number % 2 == 0
        if draft_type == "snake" and reversal_round and round_number >= reversal_round:
            descending = not descending
        slots.extend(
            range(teams, 0, -1) if descending else range(1, teams + 1)
        )
    return tuple(slots)


def _pick_owners(
    draft_id,
    draft_type,
    teams,
    rounds,
    roster_by_slot,
    traded_picks,
    pick_slots,
):
    if draft_type == "auction":
        if tuple(traded_picks):
            raise ValueError("Auction drafts cannot have fixed traded-pick ownership")
        return (None,) * (teams * rounds)

    traded = {}
    roster_ids = set(roster_by_slot.values())
    for trade in traded_picks:
        if trade.get("draft_id") is not None and str(trade["draft_id"]) != draft_id:
            raise ValueError(f"Traded pick belongs to draft {trade['draft_id']}, not {draft_id}")
        round_number = _positive_int(trade.get("round"), "traded pick round")
        original_roster = _positive_int(trade.get("roster_id"), "traded pick roster")
        owner = _positive_int(trade.get("owner_id"), "traded pick owner")
        if round_number > rounds or original_roster not in roster_ids or owner not in roster_ids:
            raise ValueError("Traded pick references an unknown round or roster")
        key = (round_number, original_roster)
        if key in traded and traded[key] != owner:
            raise ValueError(f"Conflicting traded-pick owner for round {round_number}")
        traded[key] = owner

    return tuple(
        traded.get(
            (pick_index // teams + 1, roster_by_slot[slot]),
            roster_by_slot[slot],
        )
        for pick_index, slot in enumerate(pick_slots)
    )


def _normalize_picks(
    draft_id,
    draft_type,
    teams,
    pick_slots,
    pick_owners,
    roster_by_slot,
    picks,
):
    by_number = {}
    selected = set()
    for raw_pick in picks:
        if str(raw_pick.get("draft_id")) != draft_id:
            raise ValueError(f"Pick belongs to draft {raw_pick.get('draft_id')}, not {draft_id}")
        if raw_pick.get("is_keeper") is True:
            raise ValueError("Keeper picks are outside the redraft draft-state scope")
        pick_no = _positive_int(raw_pick.get("pick_no"), "pick number")
        if pick_no > len(pick_owners):
            raise ValueError(f"Pick {pick_no} exceeds the configured draft length")
        round_number = _positive_int(raw_pick.get("round"), "pick round")
        expected_round = (pick_no - 1) // teams + 1
        if round_number != expected_round:
            raise ValueError(f"Pick {pick_no} has round {round_number}, expected {expected_round}")
        draft_slot = _positive_int(raw_pick.get("draft_slot"), "pick draft slot")
        if draft_slot not in roster_by_slot:
            raise ValueError(f"Pick {pick_no} has unknown draft slot {draft_slot}")
        if draft_type != "auction" and draft_slot != pick_slots[pick_no - 1]:
            raise ValueError(
                f"Pick {pick_no} has slot {draft_slot}, expected {pick_slots[pick_no - 1]}"
            )
        roster_id = _positive_int(raw_pick.get("roster_id"), "pick roster")
        expected_roster = (
            roster_by_slot[draft_slot]
            if draft_type == "auction"
            else pick_owners[pick_no - 1]
        )
        if roster_id != expected_roster:
            raise ValueError(
                f"Pick {pick_no} belongs to roster {roster_id}, expected {expected_roster}"
            )
        player_id = _required_text(raw_pick, "player_id")
        metadata = raw_pick.get("metadata") or {}
        price = (
            _positive_int(metadata.get("amount"), "auction price")
            if draft_type == "auction"
            else None
        )
        pick = DraftPick(
            pick_no=pick_no,
            round=round_number,
            draft_slot=draft_slot,
            roster_id=roster_id,
            picked_by=(str(raw_pick["picked_by"]) if raw_pick.get("picked_by") else None),
            player_id=player_id,
            position=(str(metadata["position"]) if metadata.get("position") else None),
            price=price,
        )
        if pick_no in by_number and by_number[pick_no] != pick:
            raise ValueError(f"Conflicting duplicate pick {draft_id}/{pick_no}")
        if player_id in selected and by_number.get(pick_no) != pick:
            raise ValueError(f"Player {player_id} was selected more than once")
        by_number[pick_no] = pick
        selected.add(player_id)

    if set(by_number) != set(range(1, len(by_number) + 1)):
        raise ValueError("Draft picks must be contiguous from pick one")
    return tuple(by_number[pick_no] for pick_no in sorted(by_number))


def _required_text(data, key):
    value = data.get(key)
    if value is None or str(value) == "":
        raise ValueError(f"Sleeper payload is missing {key}")
    return str(value)


def _positive_int(value, field):
    if isinstance(value, bool):
        raise ValueError(f"Sleeper payload has invalid {field}")
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Sleeper payload has invalid {field}") from None
    if value < 1:
        raise ValueError(f"Sleeper payload has invalid {field}")
    return value


def _nonnegative_int(value, field):
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError(f"Sleeper payload has invalid {field}")
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Sleeper payload has invalid {field}") from None
    if value < 0:
        raise ValueError(f"Sleeper payload has invalid {field}")
    return value
