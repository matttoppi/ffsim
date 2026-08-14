"""Lightweight roster-index evaluation against a fixed season world bank."""

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from operator import index

import numpy as np

from ffsim.models.team import FLEX_ELIGIBILITY


EVALUATOR_VERSION = 1
# Deterministic projected roster-value scorer revision. Kept separate from
# EVALUATOR_VERSION because that constant also seeds streamer randomness.
ROSTER_VALUE_VERSION = 1


@dataclass(frozen=True)
class LeagueEvaluation:
    world_indices: tuple[int, ...]
    roster_ids: tuple
    weekly_scores: np.ndarray
    wins: np.ndarray
    points: np.ndarray
    seeds: np.ndarray
    playoffs: np.ndarray
    division_wins: np.ndarray
    champion_indices: np.ndarray


class LeagueEvaluator:
    def __init__(
        self,
        league,
        world_bank,
        roster_ids,
        regular_season_weeks,
        *,
        schedule=None,
        seed=2026,
    ):
        self.bank = world_bank
        player_count = len(world_bank.player_ids)
        if (
            len(world_bank.player_positions) != player_count
            or len(world_bank.expected_scores) != player_count
            or world_bank.scores.shape[1:] != (player_count, len(world_bank.weeks))
            or world_bank.available.shape != world_bank.scores.shape
        ):
            raise ValueError("SeasonWorldBank axes are inconsistent")
        self.roster_ids = tuple(sorted(roster_ids, key=str))
        if not self.roster_ids or len(set(self.roster_ids)) != len(self.roster_ids):
            raise ValueError("roster_ids must be unique")
        self.roster_index = {
            roster_id: index for index, roster_id in enumerate(self.roster_ids)
        }
        self.slots = tuple((slot, int(count)) for slot, count in league.roster_slots.items())
        self.slot_counts = dict(self.slots)
        if not self.slots or any(count < 1 for _, count in self.slots):
            raise ValueError("League must have positive starting roster slots")
        unsupported_slots = sorted({
            slot for slot, _ in self.slots
            if slot not in FLEX_ELIGIBILITY
            and slot not in {"QB", "RB", "WR", "TE", "K", "DEF"}
        })
        if unsupported_slots:
            raise ValueError("Unsupported roster slots: " + ", ".join(unsupported_slots))

        self.playoff_teams = league.playoff_teams
        if self.playoff_teams not in {4, 6, 8}:
            raise ValueError(f"Unsupported playoff_teams={self.playoff_teams!r}")
        if league.playoff_round_type != 0 or league.playoff_seed_type not in {0, 1}:
            raise ValueError("Only single-week fixed or reseeded playoffs are supported")
        self.playoff_reseeding = league.playoff_seed_type == 1
        if self.playoff_teams > len(self.roster_ids):
            raise ValueError("playoff_teams exceeds the roster count")
        self.league_average_match = league.league_average_match

        self.regular_season_weeks = int(regular_season_weeks)
        playoff_rounds = 2 if self.playoff_teams == 4 else 3
        self.total_weeks = self.regular_season_weeks + playoff_rounds
        if (
            self.regular_season_weeks < 1
            or tuple(world_bank.weeks[:self.total_weeks])
            != tuple(range(1, self.total_weeks + 1))
        ):
            raise ValueError("SeasonWorldBank does not cover the required fantasy weeks")

        self.divisions = tuple(
            tuple(self.roster_index[roster_id] for roster_id in roster_ids)
            for _, roster_ids in sorted(league.divisions.items())
        )
        assigned = [team for division in self.divisions for team in division]
        if (
            len(self.divisions) != league.division_count
            or (assigned and sorted(assigned) != list(range(len(self.roster_ids))))
            or len(self.divisions) > self.playoff_teams
        ):
            raise ValueError("Invalid division assignments")

        self.seed = int(seed)
        self.schedules = (
            _fixed_schedules(schedule, self.roster_index, self.regular_season_weeks, world_bank.world_count)
            if schedule is not None
            else _generated_schedules(
                len(self.roster_ids),
                self.regular_season_weeks,
                world_bank.world_count,
                self.seed,
            )
        )
        self.slot_offsets = {}
        slot_count = 0
        for slot, count in self.slots:
            self.slot_offsets[slot] = slot_count
            slot_count += count
        self._position_array = np.asarray(world_bank.player_positions, dtype=object)
        sigma = math.sqrt(math.log(1 + 0.5**2))
        streams = np.random.SeedSequence((self.seed, EVALUATOR_VERSION)).spawn(
            world_bank.world_count
        )
        self.streamer_factors = np.asarray([
            np.random.default_rng(stream).lognormal(
                -0.5 * sigma**2,
                sigma,
                (len(self.roster_ids), self.total_weeks, slot_count),
            )
            for stream in streams
        ], dtype=np.float32)
        self._mean_scores = None
        self._mean_available = None
        self._unit_cum = None
        self.version = _version(self)
        self._cache = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def evaluate(self, roster_assignment, *, world_indices=None, use_cache=True):
        assignment = self._canonical_assignment(roster_assignment)
        world_indices = self._world_indices(world_indices)
        key = (assignment, world_indices)
        if use_cache and key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        self.cache_misses += 1
        result = self._evaluate(assignment, world_indices)
        if use_cache:
            self._cache[key] = result
        return result

    def _world_indices(self, world_indices):
        if world_indices is None:
            return tuple(range(self.bank.world_count))
        try:
            values = tuple(index(value) for value in world_indices)
        except TypeError:
            raise ValueError("world_indices must contain integers") from None
        if (
            not values
            or any(isinstance(value, bool) or value < 0 or value >= self.bank.world_count for value in values)
        ):
            raise ValueError("world_indices must select valid SeasonWorldBank worlds")
        return values

    def _canonical_assignment(self, roster_assignment):
        if set(roster_assignment) != set(self.roster_ids):
            raise ValueError("Roster assignment must contain every configured roster ID")
        assignment = tuple(
            tuple(sorted(int(player) for player in roster_assignment[roster_id]))
            for roster_id in self.roster_ids
        )
        players = [player for roster in assignment for player in roster]
        if (
            len(players) != len(set(players))
            or any(player < 0 or player >= len(self.bank.player_ids) for player in players)
        ):
            raise ValueError("Roster assignment contains duplicate or invalid player indices")
        return assignment

    def _evaluate(self, assignment, world_indices):
        replacement = self._replacement_scores(assignment)
        worlds = len(world_indices)
        teams = len(self.roster_ids)
        world_list = list(world_indices)
        weekly_scores = np.zeros((worlds, teams, self.total_weeks), dtype=float)
        # Greedy lineup selection vectorized over (world, roster player, week):
        # within one team the roster order by (-expected, player_id) is fixed,
        # so "best count available players matching a slot" is a masked
        # cumulative count over that order — identical picks to the previous
        # per-week loop, computed for every world and week at once.
        factors = self.streamer_factors[world_list, :, : self.total_weeks]
        factors_cum = np.concatenate(
            [
                np.zeros((*factors.shape[:3], 1), dtype=factors.dtype),
                np.cumsum(factors, axis=3),
            ],
            axis=3,
        )
        for team, roster in enumerate(assignment):
            order = self._lineup_order(roster)
            available = self.bank.available[
                np.ix_(world_list, order)
            ][:, :, : self.total_weeks]
            scores = self.bank.scores[
                np.ix_(world_list, order)
            ][:, :, : self.total_weeks]
            weekly_scores[:, team, :] = self._lineup_totals(
                order, available, scores, replacement, factors_cum[:, team]
            )

        wins = np.zeros((worlds, teams), dtype=int)
        points = np.zeros((worlds, teams), dtype=float)
        seeds = np.zeros((worlds, teams), dtype=np.int16)
        playoffs = np.zeros((worlds, teams), dtype=bool)
        division_wins = np.zeros((worlds, teams), dtype=bool)
        champions = np.zeros(worlds, dtype=np.int16)
        for output_world, bank_world in enumerate(world_indices):
            schedule = self.schedules[bank_world]
            for week, pairs in enumerate(schedule):
                points[output_world] += weekly_scores[output_world, :, week]
                for home, away in pairs:
                    home_score = weekly_scores[output_world, home, week]
                    away_score = weekly_scores[output_world, away, week]
                    if home_score > away_score:
                        wins[output_world, home] += 1
                    elif away_score > home_score:
                        wins[output_world, away] += 1
                if self.league_average_match:
                    scores = weekly_scores[output_world, :, week]
                    wins[output_world] += scores > float(np.median(scores))

            standings = sorted(
                range(teams),
                key=lambda team: (
                    -wins[output_world, team],
                    -points[output_world, team],
                    str(self.roster_ids[team]),
                ),
            )
            for seed, team in enumerate(standings, 1):
                seeds[output_world, team] = seed
            division_winners = [
                next(team for team in standings if team in division)
                for division in self.divisions
            ]
            division_winners.sort(key=standings.index)
            division_wins[output_world, division_winners] = True
            playoff_order = division_winners + [
                team for team in standings if team not in division_winners
            ][: self.playoff_teams - len(division_winners)]
            playoffs[output_world, playoff_order] = True
            champions[output_world] = self._champion(
                output_world, playoff_order, weekly_scores
            )

        for array in (
            weekly_scores, wins, points, seeds, playoffs, division_wins, champions
        ):
            array.flags.writeable = False
        return LeagueEvaluation(
            world_indices,
            self.roster_ids,
            weekly_scores,
            wins,
            points,
            seeds,
            playoffs,
            division_wins,
            champions,
        )

    def _lineup_order(self, roster):
        expected = self.bank.expected_scores
        player_ids = self.bank.player_ids
        return sorted(
            roster,
            key=lambda player: (-expected[player], str(player_ids[player])),
        )

    def _lineup_totals(self, order, available, scores, replacement, team_cum):
        """Greedy legal lineup totals for one team over (world, week) cells.

        ``available``/``scores`` are (worlds, len(order), weeks) in lineup
        order; ``team_cum`` is the per-slot cumulative streamer factor.
        """
        team_positions = self._position_array[order]
        chosen = np.zeros(available.shape, dtype=bool)
        filled = {}
        for slot, count in self.slots:
            if slot in FLEX_ELIGIBILITY:
                continue
            slot_mask = team_positions == slot
            candidates = available & slot_mask[None, :, None] & ~chosen
            take = candidates & (np.cumsum(candidates, axis=1) <= count)
            chosen |= take
            filled[slot] = take.sum(axis=1)
        for slot, eligible in FLEX_ELIGIBILITY.items():
            count = self.slot_counts.get(slot, 0)
            if not count:
                continue
            member = np.fromiter(
                (position in eligible for position in team_positions),
                bool,
                len(team_positions),
            )
            candidates = available & member[None, :, None] & ~chosen
            take = candidates & (np.cumsum(candidates, axis=1) <= count)
            chosen |= take
            filled[slot] = take.sum(axis=1)
        totals = (scores * chosen).sum(axis=1, dtype=float)
        for slot, count in self.slots:
            replacement_value = max(
                (
                    replacement.get(position, 0.0)
                    for position in FLEX_ELIGIBILITY.get(slot, {slot})
                ),
                default=0.0,
            )
            offset = self.slot_offsets[slot]
            lower = np.take_along_axis(
                team_cum, (offset + filled[slot])[..., None], axis=2
            )[..., 0]
            totals += replacement_value * (team_cum[:, :, offset + count] - lower)
        return totals

    def projected_roster_value(self, roster_assignment, roster_id):
        """Deterministic projected lineup points over full-streamer replacement.

        Scores one roster's best legal weekly lineup on the bank's expected
        (across-world mean) player-week points, with byes/never-available
        weeks masked out and unfilled slots credited at the same replacement
        semantics as ``_evaluate`` (the streamer factor's mean is exactly 1).
        The all-streamer baseline is subtracted, so an empty roster scores 0.
        """
        assignment = self._canonical_assignment(roster_assignment)
        team = self.roster_index[roster_id]
        replacement = self._replacement_scores(assignment)
        if self._mean_scores is None:
            weeks = self.total_weeks
            self._mean_scores = self.bank.scores[:, :, :weeks].mean(
                axis=0, dtype=float
            )
            self._mean_available = self.bank.available[:, :, :weeks].any(axis=0)
            slot_count = sum(count for _, count in self.slots)
            self._unit_cum = np.tile(
                np.arange(slot_count + 1, dtype=float), (1, weeks, 1)
            )
        order = self._lineup_order(assignment[team])
        totals = self._lineup_totals(
            order,
            self._mean_available[order][None, :, :],
            self._mean_scores[order][None, :, :],
            replacement,
            self._unit_cum,
        )
        baseline = self.total_weeks * sum(
            count * max(
                (
                    replacement.get(position, 0.0)
                    for position in FLEX_ELIGIBILITY.get(slot, {slot})
                ),
                default=0.0,
            )
            for slot, count in self.slots
        )
        return float(totals.sum()) - baseline

    def _replacement_scores(self, assignment):
        rostered = {player for roster in assignment for player in roster}
        result = {}
        for position in {"QB", "RB", "WR", "TE", "K", "DEF"}:
            scores = sorted(
                (
                    self.bank.expected_scores[player]
                    for player, player_position in enumerate(self.bank.player_positions)
                    if player not in rostered and player_position == position
                ),
                reverse=True,
            )[:len(self.roster_ids)]
            if scores:
                result[position] = float(np.median(scores))
        return result

    def _champion(self, world, playoff_order, weekly_scores):
        week = self.regular_season_weeks
        teams = playoff_order[2:] if len(playoff_order) == 6 else playoff_order
        winners = _round_winners(teams, weekly_scores[world, :, week])
        while len(winners) > 1:
            week += 1
            if len(playoff_order) == 6 and week == self.regular_season_weeks + 1:
                if not self.playoff_reseeding:
                    winners = _pair_winners(
                        ((playoff_order[0], winners[1]), (playoff_order[1], winners[0])),
                        weekly_scores[world, :, week],
                    )
                    continue
                winners = [*playoff_order[:2], *winners]
            if self.playoff_reseeding:
                winners.sort(key=playoff_order.index)
            winners = _round_winners(winners, weekly_scores[world, :, week])
        return winners[0]


def _fixed_schedules(schedule, roster_index, weeks, worlds):
    normalized = []
    for week in range(1, weeks + 1):
        pairs = tuple(
            (roster_index[home], roster_index[away])
            for home, away in schedule.get(week, schedule.get(str(week), ()))
        )
        playing = [team for pair in pairs for team in pair]
        if (
            any(home == away for home, away in pairs)
            or len(playing) != len(set(playing))
            or len(playing) != len(roster_index) - len(roster_index) % 2
        ):
            raise ValueError(f"Invalid fantasy schedule week {week}")
        normalized.append(pairs)
    return (tuple(normalized),) * worlds


def _generated_schedules(team_count, weeks, worlds, seed):
    result = []
    for stream in np.random.SeedSequence((seed, 0)).spawn(worlds):
        rng = np.random.default_rng(stream)
        schedule = []
        while len(schedule) < weeks:
            schedule.extend(_round_robin(tuple(map(int, rng.permutation(team_count)))))
        result.append(tuple(schedule[:weeks]))
    return tuple(result)


def _round_robin(teams):
    teams = list(teams)
    if len(teams) % 2:
        teams.append(None)
    rounds = []
    for _ in range(len(teams) - 1):
        rounds.append(tuple(
            (teams[index], teams[-index - 1])
            for index in range(len(teams) // 2)
            if teams[index] is not None and teams[-index - 1] is not None
        ))
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return rounds


def _round_winners(teams, scores):
    return _pair_winners(
        tuple((teams[index], teams[-index - 1]) for index in range(len(teams) // 2)),
        scores,
    )


def _pair_winners(pairs, scores):
    return [home if scores[home] > scores[away] else away for home, away in pairs]


def _version(evaluator):
    return sha256(json.dumps({
        "evaluator": EVALUATOR_VERSION,
        "roster_value": ROSTER_VALUE_VERSION,
        "world_bank": evaluator.bank.version,
        "rosters": evaluator.roster_ids,
        "slots": evaluator.slots,
        "playoff_teams": evaluator.playoff_teams,
        "playoff_reseeding": evaluator.playoff_reseeding,
        "divisions": evaluator.divisions,
        "regular_season_weeks": evaluator.regular_season_weeks,
        "schedules": evaluator.schedules,
        "seed": evaluator.seed,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
