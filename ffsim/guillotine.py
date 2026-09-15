"""Read-only Sleeper best ball comparisons with an explicit spending limit."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import time
from urllib.parse import quote

import numpy as np
import pandas as pd

from ffsim.loaders.fantasypros import (
    FANTASYPROS_PLAYERS_URL, FANTASYPROS_PROJECTIONS_URL,
    FANTASYPROS_STAT_FIELDS, _fetch_json as fetch_fantasypros,
    fantasypros_api_key,
)
from ffsim.loaders.league import _fetch_json as fetch_sleeper
from ffsim.loaders.pff import canonical_team
from ffsim.models.player import Player
from ffsim.models.team import FLEX_ELIGIBILITY
from ffsim.paths import CACHE_DIR, DATA_DIR, OUTPUT_DIR
from ffsim.scoring import ScoringSettings
from ffsim.simulation.empirical import EmpiricalLibrary


POSITIONS = {"QB", "RB", "WR", "TE", "K"}
OUT_STATUSES = {"Out", "IR", "PUP", "Sus", "Inactive"}
KICK_BUCKETS = ("019", "2029", "3039", "4049", "50plus")
RAW_KICK_BUCKETS = ("0_19", "20_29", "30_39", "40_49", "50_plus")
REST_OF_SEASON_RANKINGS_URL = "https://api.fantasypros.com/public/v2/json/nfl/{season}/consensus-rankings"
ELITE_POSITION_LIMITS = {"QB": 3, "RB": 8, "WR": 8, "TE": 3, "K": 0}
CORE_POSITION_LIMITS = {"QB": 8, "RB": 24, "WR": 30, "TE": 8, "K": 0}


def fetch_snapshot(league_id, username):
    """Refresh league/projections; download Sleeper's player directory daily."""
    if not str(league_id).isdigit():
        raise ValueError("--league-id must be a numeric Sleeper league ID")
    league = fetch_sleeper(f"league/{league_id}")
    if str(league["league_id"]) != str(league_id):
        raise ValueError("Sleeper returned a different league")
    state = fetch_sleeper("state/nfl")
    week = int(league["settings"]["last_scored_leg"]) + 1
    season = int(league["season"])
    if season != int(state["season"]) or week != int(state["leg"]):
        raise ValueError("League must be ready for the current NFL week")
    now = datetime.now(timezone.utc)
    directory = CACHE_DIR / "guillotine"
    directory.mkdir(parents=True, exist_ok=True)
    player_path = directory / "sleeper_players.json"
    if not player_path.exists() or now.timestamp() - player_path.stat().st_mtime >= 86400:
        player_path.write_text(json.dumps(fetch_sleeper("players/nfl")))
    transactions = [
        transaction
        for leg in range(1, week + 1)
        for transaction in fetch_sleeper(f"league/{league_id}/transactions/{leg}")
    ]
    key = fantasypros_api_key()
    projections = fetch_fantasypros(
        FANTASYPROS_PROJECTIONS_URL.format(season=season), key,
        {"positions": ":".join(sorted(POSITIONS)), "week": week},
    )
    time.sleep(1)  # Existing FantasyPros personal access: one request per second.
    metadata = fetch_fantasypros(FANTASYPROS_PLAYERS_URL, key)
    scoring = {0: "STD", 0.5: "HALF", 1: "PPR"}.get(league["scoring_settings"].get("rec", 0))
    if scoring is None:
        raise ValueError("Rest-of-season tiers require standard, half-PPR, or PPR reception scoring")
    time.sleep(1)
    rankings = fetch_fantasypros(REST_OF_SEASON_RANKINGS_URL.format(season=season), key,
                               {"position": "ALL", "type": "ROS", "scoring": scoring})
    return {
        "retrieved_at": now.isoformat(), "week": week, "league": league,
        "user": fetch_sleeper(f"user/{quote(username, safe='')}"),
        "rosters": fetch_sleeper(f"league/{league_id}/rosters"),
        "players": json.loads(player_path.read_text()),
        "transactions": transactions, "projections": projections,
        "projection_players": metadata, "rest_of_season_rankings": rankings,
    }


def _number(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Expected a finite nonnegative number, got {value!r}")
    return number


def _dollars(value):
    if isinstance(value, bool) or not _number(value).is_integer():
        raise ValueError("Spending limits and bids must be nonnegative whole dollars")
    return int(value)


def provider_player_ids(snapshot):
    """Map FantasyPros IDs through unique stable external identities."""
    external = defaultdict(list)
    for sid, player in snapshot["players"].items():
        if player.get("sportradar_id"):
            external[str(player["sportradar_id"])].append(sid)
    provider_ids = {
        str(player["player_id"]): str(player.get("sportsdata_player_id") or "")
        for player in snapshot["projection_players"]["players"]
    }
    return {fpid: external[external_id][0] for fpid, external_id in provider_ids.items()
            if len(external.get(external_id, ())) == 1}


def projection_map(snapshot, player_ids):
    """Match stable external IDs, including Sleeper's offensive eligibility."""
    response = snapshot["projections"]
    if (int(response["season"]) != int(snapshot["league"]["season"])
            or int(response["week"]) != snapshot["week"]):
        raise ValueError("Projection season/week does not match the league snapshot")
    identities = provider_player_ids(snapshot)
    result = {}
    for row in response["players"]:
        sid = identities.get(str(row["fpid"]))
        if sid not in player_ids:
            continue
        player = snapshot["players"][sid]
        eligible = set(player.get("fantasy_positions") or [player["position"]])
        if row["position_id"] not in eligible:
            raise ValueError(f"Projection position disagrees with Sleeper for {sid}")
        if sid in result:
            raise ValueError(f"Duplicate projection for Sleeper player {sid}")
        result[sid] = row
    return result


def rest_of_season_ranks(snapshot):
    response = snapshot.get("rest_of_season_rankings")
    if not response:
        raise ValueError("Snapshot lacks rest-of-season rankings; refresh league inputs")
    scoring = {0: "STD", 0.5: "HALF", 1: "PPR"}.get(snapshot["league"]["scoring_settings"].get("rec", 0))
    if (int(response["year"]) != int(snapshot["league"]["season"])
            or response["ranking_type_name"] != "ros" or response["scoring"] != scoring
            or response["position_id"] != "ALL" or not response["players"]):
        raise ValueError("Invalid rest-of-season rankings for this league")
    identities = provider_player_ids(snapshot)
    result = {}
    for row in response["players"]:
        sid = identities.get(str(row["player_id"]))
        position = row["player_position_id"]
        if sid is None or position not in POSITIONS:
            continue
        label = row["pos_rank"]
        if not label.startswith(position) or not label[len(position):].isdigit():
            raise ValueError(f"Invalid rest-of-season position rank: {label}")
        rank = int(label[len(position):])
        eligible = snapshot["players"][sid].get("fantasy_positions") or [snapshot["players"][sid]["position"]]
        if rank < 1 or sid in result or position not in eligible:
            raise ValueError(f"Invalid or duplicate rest-of-season rank for {sid}")
        result[sid] = rank
    return result


def weekly_player(sid, metadata, row, library):
    """Use weekly means with FFSIM's existing empirical stat sampler."""
    stats = {key: _number(value) for key, value in row["stats"].items()}
    position = row["position_id"]
    projection = {"games": 1, "byeWeek": 0}
    projection.update({
        target: stats[source] for source, target in FANTASYPROS_STAT_FIELDS.items()
        if source in stats
    })
    if position == "K":
        for required in ("fg", "fga", "xpt"):
            if required not in stats:
                raise ValueError(f"Missing weekly kicker statistic {required}: {sid}")
        if stats["fg"] > stats["fga"]:
            raise ValueError(f"Projected field goals exceed attempts: {sid}")
        history = library.team_rows[library.team_rows.position == "K"]
        # ponytail: historical distance/miss shares; use weekly buckets when published.
        for outcome, total in (("made", stats["fg"]), ("missed", stats["fga"] - stats["fg"])):
            counts = [float(history[f"field_goals_{outcome}_{b}"].sum()) for b in RAW_KICK_BUCKETS]
            for bucket, count in zip(KICK_BUCKETS, counts):
                amount = total * count / sum(counts)
                if outcome == "made":
                    projection[f"fgMade{bucket}"] = amount
                    projection[f"fgAtt{bucket}"] = amount
                else:
                    projection[f"fgAtt{bucket}"] += amount
        projection["patMade"] = stats["xpt"]
        projection["patAtt"] = stats["xpt"] * float(
            1 + history.extra_points_missed.sum() / history.extra_points_made.sum()
        )
    else:
        history = library.player_rows[library.player_rows.position == position]
        # FantasyPros omits targets and a separate fumbles-lost field.
        # ponytail: position-wide historical ratios; replace when source publishes them.
        projection["recvTargets"] = projection.get("recvReceptions", 0) * float(
            history.targets.sum() / history.receptions.sum()
        )
        projection["fumblesLost"] = projection.get("fumbles", 0) * float(
            history.fumbles_lost.sum() / history.fumbles.sum()
        )
    player = Player({**metadata, "player_id": sid, "position": position, "projections": projection})
    player.initialize_empirical_sampler(library)
    return player


def best_ball_totals(scores, positions, slots):
    """Exact maximum for single-position players and nested/disjoint FLEX sets."""
    if scores.ndim != 2 or scores.shape[1] != len(positions) or not np.isfinite(scores).all():
        raise ValueError("Invalid player score matrix")
    eligible_sets = [frozenset(FLEX_ELIGIBILITY.get(slot, {slot})) for slot in slots]
    if any(not eligible <= POSITIONS for eligible in eligible_sets):
        raise ValueError("Guillotine supports QB/RB/WR/TE/K and offensive FLEX slots")
    if any(a & b and not (a <= b or b <= a) for a in eligible_sets for b in eligible_sets):
        raise ValueError("Overlapping, non-nested FLEX slots need an assignment solver")
    chosen = np.zeros(scores.shape, dtype=bool)
    totals = np.zeros(scores.shape[0])
    rows = np.arange(len(totals))
    for eligible in sorted(eligible_sets, key=lambda values: (len(values), sorted(values))):
        mask = np.array([position in eligible for position in positions])
        if not mask.any():
            continue  # Empty positions score zero; no hypothetical waiver replacement.
        candidates = np.where(mask[None, :] & ~chosen, scores, -np.inf)
        indices = candidates.argmax(axis=1)
        values = candidates[rows, indices]
        filled = np.isfinite(values)
        totals[filled] += values[filled]
        chosen[rows[filled], indices[filled]] = True
    return np.round(totals, 2)


def chop_shares(totals, rosters, week):
    """Apply Sleeper's score/season-points tiebreak, splitting unresolved ties."""
    tied = totals == totals.min(axis=1, keepdims=True)
    if week == 1:
        tie_values = [r["settings"]["draft_position"] for r in rosters]
    else:
        tie_values = [r["settings"]["fpts"] + r["settings"].get("fpts_decimal", 0) / 100 for r in rosters]
    values = np.where(tied, np.asarray(tie_values)[None, :], np.inf)
    tied &= values == values.min(axis=1, keepdims=True)
    return tied / tied.sum(axis=1, keepdims=True)


def player_bid_range(row, budget, risk, teams):
    """A declared value heuristic: lasting role first, roster fit second."""
    reduction = row["risk_reduction"]
    clear_gain = reduction > 2 * row["risk_reduction_standard_error"]
    if row["action"] == "pass":
        return "Pass", None
    if teams == 2:
        return ("Final-week upgrade", [budget // 2, budget]) if clear_gain else ("Free only", [0, 0])
    rank = row["rest_of_season_position_rank"]
    position = row["position"]
    lasting_fit = rank is not None and row["points_gain"] >= 3
    # ponytail: explicit tier cutoffs and budget shares, not fitted auction prices.
    # Calibrate against league bid results before claiming market accuracy.
    if lasting_fit and rank <= ELITE_POSITION_LIMITS[position]:
        category, shares = "Elite starter", (0.05, 0.15)
    elif lasting_fit and rank <= CORE_POSITION_LIMITS[position]:
        category, shares = "Core starter", (0.02, 0.07)
    elif clear_gain and reduction >= 0.01:
        category, shares = "Short-term upgrade", (0.005, 0.02)
    elif clear_gain:
        return "Marginal depth", [0, min(5, budget)]
    else:
        return "Free only", [0, 0]
    fit = min(1, max(0.5, row["points_gain"] / 10)) if category in {"Elite starter", "Core starter"} else 1
    urgency = min(2, max(1, risk * teams)) if clear_gain else 1
    stage = min(3, max(1, 6 / teams))
    amounts = [budget * share * fit * urgency * stage for share in shares]
    increment = 5 if amounts[1] >= 10 else 1
    upper = min(budget, increment * math.ceil(amounts[1] / increment))
    lower = min(upper, increment * math.floor(amounts[0] / increment))
    return category, [lower, upper]


def spending_plan(recommendations, budget, risk, teams, weekly_cap=None, bids=None, spent=0):
    """Recommend exact bids and bound the cost of claims that can win together."""
    bids = dict(bids or {})
    budget, spent = _dollars(budget), _dollars(spent)
    for value in bids.values():
        _dollars(value)
    if weekly_cap is not None:
        _dollars(weekly_cap)
    if teams < 2 or not 0 <= risk <= 1:
        raise ValueError("Invalid team count or chop risk")
    rows = [dict(row) for row in recommendations]
    unknown = set(bids) - {row["player_id"] for row in rows}
    if unknown:
        raise ValueError(f"Bid IDs are not available chop candidates: {sorted(unknown)}")
    largest = 0
    groups = defaultdict(int)
    for row in rows:
        row["category"], row["recommended_bid_range"] = player_bid_range(row, budget + spent, risk, teams)
        value_range = row["recommended_bid_range"]
        model_bid = None
        if value_range is not None:
            lower, upper = value_range
            model_bid = upper if teams == 2 else (lower + upper + 1) // 2
            largest = max(largest, model_bid)
            model_bid = min(budget, model_bid)
            row["recommended_bid_range"] = [min(budget, amount) for amount in value_range]
        # Only claims dropping the SAME owned player are mutually exclusive.
        row["claim_group"] = f"drop:{row['drop_id']}" if row["drop_id"] else f"add:{row['player_id']}"
        row["chosen_bid"] = _dollars(bids[row["player_id"]]) if row["player_id"] in bids else None
        row["model_bid"] = model_bid
        row["recommended_bid"] = row["chosen_bid"] if row["chosen_bid"] is not None else model_bid
        row["bid_source"] = "user" if row["chosen_bid"] is not None else "heuristic"
        row["selected"] = row["player_id"] in bids if bids else row["action"] != "pass"
        row["planned_bid"] = None
        if row["chosen_bid"] is not None:
            if row["action"] == "pass":
                raise ValueError(f"Cannot bid on a pass candidate: {row['player_id']}")
            group = row["claim_group"]
            groups[group] = max(groups[group], int(row["chosen_bid"]))
    cap_source = "user"
    if weekly_cap is None:
        if bids:
            weekly_cap, cap_source = spent + sum(groups.values()), "chosen_claims"
        else:
            weekly_cap = min(budget + spent, largest + 10) if largest else spent
            cap_source = "automatic"
    available = min(max(0, int(weekly_cap) - int(spent)), int(budget))
    if sum(groups.values()) > available:
        raise ValueError(f"Chosen claims can spend ${sum(groups.values())}; remaining weekly limit is ${available}")
    remaining = available - sum(groups.values())
    rows.sort(key=lambda row: (not row["selected"], -(row["recommended_bid"] or 0), -row["risk_reduction"]))
    for row in rows:
        group = row["claim_group"]
        if not row["selected"]:
            row["plan_status"] = "Pass" if row["action"] == "pass" else "Not selected"
            continue
        if row["chosen_bid"] is not None:
            row["planned_bid"] = row["chosen_bid"]
            row["plan_status"] = "Bid"
            continue
        amount = row["recommended_bid"]
        extra = max(0, amount - groups[group])
        if extra > remaining:
            row["plan_status"] = "Hold"
            continue
        remaining -= extra
        groups[group] += extra
        row["planned_bid"] = amount
        row["plan_status"] = "Bid"
    return {
        "pricing": "exact_bid_policy_v3", "weekly_cap": int(weekly_cap),
        "weekly_cap_source": cap_source, "user_bids": bids,
        "weekly_spent": int(spent), "weekly_remaining": available,
        "maximum_plan_spend": sum(groups.values()),
        "recommendations": rows,
    }


def analyze(snapshot, *, simulations=5000, seed=2026, weekly_cap=None, bids=None, drop_player=None):
    if not isinstance(simulations, int) or simulations < 100:
        raise ValueError("Use at least 100 simulations")
    if weekly_cap is not None:
        _dollars(weekly_cap)
    season_ranks = rest_of_season_ranks(snapshot)
    league = snapshot["league"]
    settings = league["settings"]
    if settings.get("type") != 3 or settings.get("best_ball") != 1:
        raise ValueError("This command requires a Sleeper Chopped best ball league")
    if settings.get("disable_elimination") or settings.get("waiver_type") != 2:
        raise ValueError("Automatic weekly chops and FAAB waivers must be enabled")
    if settings.get("waiver_bid_min", 0) != 0:
        raise ValueError("This calculator currently requires $0 minimum bids")
    week = snapshot["week"]
    if week != int(settings["last_scored_leg"]) + 1:
        raise ValueError("Snapshot does not target the next unscored week")
    rosters = sorted((r for r in snapshot["rosters"] if not r["settings"].get("eliminated")), key=lambda r: r["roster_id"])
    if len(rosters) < 2:
        raise ValueError("The league has finished")
    matches = [i for i, r in enumerate(rosters) if r.get("owner_id") == snapshot["user"]["user_id"]]
    if len(matches) != 1:
        raise ValueError("The selected user must own exactly one surviving team")
    mine = matches[0]
    reserve = {sid for r in rosters for sid in r.get("reserve") or []}
    assignments = [list(r.get("players") or []) for r in rosters]
    owned = [sid for roster in assignments for sid in roster]
    if len(owned) != len(set(owned)):
        raise ValueError("A player appears on more than one surviving roster")
    transactions = snapshot["transactions"]
    if any(t.get("waiver_budget") for t in transactions):
        raise ValueError("FAAB trades need balance reconciliation before bidding")
    chops = [t for t in transactions if t["type"] == "chopped" and t["status"] == "complete"]
    latest = max((t["leg"] for t in chops), default=None)
    if latest is None:
        raise ValueError("No completed chop is available")
    candidates = sorted({sid for t in chops if t["leg"] == latest for sid in t.get("drops") or {}} - set(owned) - reserve)
    if not candidates:
        raise ValueError("All players from the latest chop have been claimed")
    slots = [s for s in league["roster_positions"] if s not in {"BN", "IR", "TAXI"}]
    players = snapshot["players"]
    pool = sorted(set(owned) | set(candidates))
    projections = projection_map(snapshot, set(pool))
    games = pd.read_csv(DATA_DIR / "historical/nflverse/reference/games.csv")
    games = games[(games.season == int(league["season"])) & (games.game_type == "REG") & (games.week == week)]
    if games.empty:
        raise ValueError("The local NFL schedule does not cover this season/week")
    playing_teams = {canonical_team(team) for team in set(games.home_team) | set(games.away_team)}
    inactive, position_by_id = {}, {}
    for sid in pool:
        player = players[sid]
        eligible = set(player.get("fantasy_positions") or [player["position"]]) & POSITIONS
        if len(eligible) != 1:
            raise ValueError(f"Unsupported offensive position eligibility: {sid}")
        position_by_id[sid] = next(iter(eligible))
        reason = player.get("injury_status")
        if reason in OUT_STATUSES or canonical_team(player.get("team")) not in playing_teams:
            inactive[sid] = reason if reason in OUT_STATUSES else "No game"
        elif sid not in projections:
            raise ValueError(f"Missing weekly projection for active player {player.get('full_name', sid)}")
    budgets = [int(settings["waiver_budget"]) - int(r["settings"]["waiver_budget_used"]) for r in rosters]
    if any(b < 0 for b in budgets):
        raise ValueError("Invalid remaining FAAB balance")
    scoring = ScoringSettings(league["scoring_settings"])
    library = EmpiricalLibrary()
    samples = np.zeros((simulations, len(pool)))
    index = {sid: i for i, sid in enumerate(pool)}
    # Separate streams per ID keep every before/after comparison paired.
    # ponytail: existing independent empirical player draws; no new game-correlation model.
    for sid in pool:
        if sid in inactive or sid in reserve:
            continue
        player = weekly_player(sid, players[sid], projections[sid], library)
        rng = np.random.default_rng(np.random.SeedSequence([seed, int(sid)]))
        samples[:, index[sid]] = [player.calculate_score(scoring, week, rng) for _ in range(simulations)]

    def score(roster):
        roster = [sid for sid in roster if sid not in reserve]
        return best_ball_totals(samples[:, [index[sid] for sid in roster]], [position_by_id[sid] for sid in roster], slots)

    totals = np.column_stack([score(roster) for roster in assignments])
    before = chop_shares(totals, rosters, week)[:, mine]
    my_roster = assignments[mine]
    capacity = sum(s not in {"IR", "TAXI"} for s in league["roster_positions"])
    if drop_player is not None and drop_player not in my_roster:
        raise ValueError("--drop-player must be a Sleeper ID on your roster")
    if drop_player:
        drops = [drop_player]
    elif len(set(my_roster) - reserve) < capacity:
        drops = [None]
    else:
        drops = [sid for sid in my_roster if sid not in inactive and sid not in reserve]
    if not drops:
        raise ValueError("No healthy drop candidates; choose --drop-player explicitly")
    recommendations = []
    for candidate in candidates:
        options = []
        for drop in drops:
            after_roster = [sid for sid in my_roster if sid != drop] + [candidate]
            after_points = score(after_roster)
            comparison = totals.copy()
            comparison[:, mine] = after_points
            after = chop_shares(comparison, rosters, week)[:, mine]
            gain = float((after_points - totals[:, mine]).mean())
            drop_mean = float(samples[:, index[drop]].mean()) if drop else 0.0
            options.append((float(after.mean()), -gain, drop_mean, str(drop), drop, after))
        risk, negative_gain, _, _, drop, after = min(options, key=lambda option: option[:4])
        gain = -negative_gain
        delta = before - after
        recommendations.append({
            "player_id": candidate, "player": players[candidate]["full_name"],
            "position": position_by_id[candidate], "status": inactive.get(candidate) or players[candidate].get("injury_status") or "Active",
            "rest_of_season_position_rank": season_ranks.get(candidate),
            "drop_id": drop, "drop": players[drop]["full_name"] if drop else None,
            "points_gain": round(gain, 2), "chop_risk": round(risk, 5),
            "risk_reduction": round(float(delta.mean()), 5),
            "risk_reduction_standard_error": round(float(delta.std(ddof=1) / math.sqrt(simulations)), 5),
            "action": "consider" if candidate not in inactive and (gain > 0 or delta.mean() > 0) else "pass",
        })
    recommendations.sort(key=lambda row: (-row["risk_reduction"], -row["points_gain"], row["player"]))
    spent = sum(_dollars(t["settings"]["waiver_bid"]) for t in transactions
                if t["type"] == "waiver" and t["status"] == "complete"
                and t["leg"] == week and rosters[mine]["roster_id"] in t["roster_ids"])
    plan = spending_plan(recommendations, budgets[mine], float(before.mean()), len(rosters), weekly_cap, bids, spent)
    return {
        "league_id": league["league_id"], "league": league["name"],
        "username": snapshot["user"]["display_name"], "week": week,
        "retrieved_at": snapshot["retrieved_at"], "simulations": simulations, "seed": seed,
        "teams_remaining": len(rosters), "bidding_rounds_remaining": len(rosters) - 1,
        "faab_remaining": budgets[mine], "baseline_chop_risk": round(float(before.mean()), 5),
        "baseline_expected_points": round(float(totals[:, mine].mean()), 2),
        "rest_of_season_source": {key: snapshot["rest_of_season_rankings"][key]
                                  for key in ("scoring", "last_updated", "total_experts")},
        **plan,
        "completed_waiver_bids": [t["settings"]["waiver_bid"] for t in transactions if t["type"] == "waiver" and t["status"] == "complete" and "waiver_bid" in (t.get("settings") or {})],
        "assumptions": [
            "Default bids are value-based rules of thumb, not forecasts of winning bids. User bids are explicit choices for this report.",
            "Elite position ranks: QB3/RB8/WR8/TE3 or better; core ranks: QB8/RB24/WR30/TE8 or better. Kickers receive no lasting-starter premium.",
            "A lasting starter must also add at least 3 expected best ball points next week. Elite base range: 5–15% of budget; core: 2–7%.",
            "Starter ranges scale by roster fit: points gained / 10, bounded to 0.5–1. Short-term upgrades use 0.5–2% without this factor.",
            "Short-term upgrades need at least 1 percentage point of risk reduction above two simulation standard errors; other clear gains receive $0–$5 depth bids.",
            "Urgency scales paid upgrade ranges by risk × teams, bounded to 1–2, only when the risk reduction clears the noise screen.",
            "Stage scales upgrade ranges by 6 / teams, bounded to 1–3. With two teams left, clear upgrades use 50–100% of remaining budget.",
            "Ranges use budget at the start of this Sleeper week, rounded outward to $5 when the upper amount reaches $10, then capped at available funds.",
            "The default bid is the value range midpoint, rounded up to a whole dollar; with two teams left it uses the upper end. Bids cannot exceed remaining funds.",
            "Without chosen bids, the automatic weekly allowance funds the largest default bid plus $10 for depth. Highest bids receive allowance first. --weekly-cap overrides it.",
            "Repeat --bid for an exact selected claim list. Unlisted players are excluded; the automatic allowance covers only the chosen claims' maximum cost.",
            "Bid shows the exact offer. Hold means the weekly allowance cannot fund it; the algorithm does not reduce its valuation to fit the allowance.",
            "Maximum plan spend sums the largest offer per shared drop; claims without a drop count separately.",
            "Completed waiver spending for your roster in this Sleeper week is deducted from the weekly limit.",
            "The remaining limit covers only this report's claims. Include any other pending claims in your spending limit.",
            "Use the listed drop on every claim. Do not drop that player separately. Order equal bids by this table.",
            "Each roster comparison assumes one acquisition. Refresh after a win; gains from multiple wins are not additive.",
            "Risk estimates cover next week with opponents' current rosters. Rest-of-season ranks are a lasting-value proxy, not a championship simulation.",
            "Rest-of-season ranks use standard reception scoring; weekly simulations include your league's tight-end premium and best ball lineup.",
            "An unranked player gets no lasting-starter premium. Check upcoming byes, injury outlook, and other available players before submitting bids.",
            "Drop suggestions use current-week value; injured/bye players require an explicit drop override.",
            "Healthy and questionable players use the projection as given; Out/IR/PUP/Sus/Inactive and no-game players score zero.",
            "Unresolved exact chop ties split elimination probability evenly.",
            "Players without a lasting-starter role or a clear current-week risk improvement receive $0-only bids. The noise screen does not prove calibration.",
            "Historical position ratios supply targets and fumble-loss share; historical kicker ratios supply distance and extra-point misses.",
            "FFSIM's independent empirical weekly draws are model estimates, not calibrated guillotine probabilities.",
        ],
    }


def format_report(report):
    lines = [
        f"# {report['league']} — Week {report['week']}", "",
        f"{report['username']} · {report['teams_remaining']} teams · ${report['faab_remaining']} FAAB · "
        f"modeled chop risk {report['baseline_chop_risk']:.1%}", "",
        f"**Weekly limit: ${report['weekly_cap']} total. Already spent: ${report['weekly_spent']}. "
        f"Available: ${report['weekly_remaining']}. Maximum spend for these claims: ${report['maximum_plan_spend']}.**", "",
        "Each row gives one exact bid. Your choices override the default calculation for this report.",
        "Keep the listed drops: claims sharing a drop are alternatives; claims with different drops can win together.",
        "Hold means the weekly allowance cannot fund that bid. This report does not submit claims.", "",
        "| Player | Drop | Points gained | Bid | Source | Plan |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in report["recommendations"]:
        if report["user_bids"] and not row["selected"]:
            continue
        name = row["player"] + (f" ({row['status']})" if row["status"] != "Active" else "")
        offer = f"${row['recommended_bid']}" if row["recommended_bid"] is not None else "—"
        source = "Your choice" if row["bid_source"] == "user" else "Default calculation"
        lines.append(f"| {name} | {row['drop'] or 'Open roster spot'} | {row['points_gain']:+.2f} | {offer} | {source} | {row['plan_status']} |")
    source = report["rest_of_season_source"]
    lines.extend(["", f"Rest-of-season ranks: FantasyPros {source['scoring']}, updated {source['last_updated']}; {source['total_experts']} experts. "
                  f"Weekly allowance: {report['weekly_cap_source']}."])
    lines.extend(["", f"Source snapshot: {report['retrieved_at']}. Simulations: {report['simulations']}; seed: {report['seed']}.", ""])
    lines.extend(f"- {assumption}" for assumption in report["assumptions"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league-id")
    parser.add_argument("--username")
    parser.add_argument("--snapshot", type=Path, help="Replay a saved input snapshot without network calls")
    parser.add_argument("--simulations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--weekly-cap", type=int, help="Override the automatic total weekly spending allowance")
    parser.add_argument("--bid", action="append", default=[], metavar="SLEEPER_ID=AMOUNT",
                        help="Select an exact bid; repeat for multiple players. Unlisted players are not selected")
    parser.add_argument("--drop-player", help="Sleeper ID to use instead of the automatic drop search")
    parser.add_argument("--output", type=Path, help="JSON report path; also writes a Markdown table")
    args = parser.parse_args()
    try:
        if args.weekly_cap is not None:
            _dollars(args.weekly_cap)
        bids = {}
        for value in args.bid:
            sid, separator, amount = value.partition("=")
            if not separator or not sid.isdigit() or not amount.isdigit() or sid in bids:
                raise ValueError("Use --bid SLEEPER_ID=WHOLE_DOLLARS once per player")
            bids[sid] = int(amount)
        if args.snapshot:
            if args.league_id or args.username:
                parser.error("Use --snapshot alone, or --league-id with --username")
            path = args.snapshot
            snapshot = json.loads(path.read_text())
        else:
            if not args.league_id or not args.username:
                parser.error("Provide --league-id and --username")
            snapshot = fetch_snapshot(args.league_id, args.username)
            payload = json.dumps(snapshot, sort_keys=True) + "\n"
            digest = sha256(payload.encode()).hexdigest()[:16]
            path = CACHE_DIR / "guillotine" / f"{args.league_id}-week{snapshot['week']}-{digest}.json"
            path.write_text(payload)
        report = analyze(snapshot, simulations=args.simulations, seed=args.seed,
                         weekly_cap=args.weekly_cap, bids=bids, drop_player=args.drop_player)
        report["input_snapshot"] = str(path.resolve())
        output = args.output or OUTPUT_DIR / "guillotine" / f"{report['league_id']}-week{report['week']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        rendered = format_report(report)
        output.with_suffix(".md").write_text(rendered)
        print(rendered)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
