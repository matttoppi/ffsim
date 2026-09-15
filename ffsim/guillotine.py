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
    return {
        "retrieved_at": now.isoformat(), "week": week, "league": league,
        "user": fetch_sleeper(f"user/{quote(username, safe='')}"),
        "rosters": fetch_sleeper(f"league/{league_id}/rosters"),
        "players": json.loads(player_path.read_text()),
        "transactions": transactions, "projections": projections,
        "projection_players": metadata,
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


def projection_map(snapshot, player_ids):
    """Match stable external IDs, including Sleeper's offensive eligibility."""
    response = snapshot["projections"]
    if (int(response["season"]) != int(snapshot["league"]["season"])
            or int(response["week"]) != snapshot["week"]):
        raise ValueError("Projection season/week does not match the league snapshot")
    external = defaultdict(list)
    for sid, player in snapshot["players"].items():
        if player.get("sportradar_id"):
            external[str(player["sportradar_id"])].append(sid)
    provider_ids = {
        str(player["player_id"]): str(player.get("sportsdata_player_id") or "")
        for player in snapshot["projection_players"]["players"]
    }
    result = {}
    for row in response["players"]:
        matches = external.get(provider_ids.get(str(row["fpid"])), ())
        if len(matches) != 1:
            continue
        sid = matches[0]
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


def spending_plan(recommendations, budget, risk, teams, weekly_cap=5, bids=None, spent=0):
    """Allocate bargain ranges; never infer a market price from projected points."""
    bids = dict(bids or {})
    for value in (budget, weekly_cap, spent, *bids.values()):
        _dollars(value)
    if teams < 2 or not 0 <= risk <= 1:
        raise ValueError("Invalid team count or chop risk")
    rows = [dict(row) for row in recommendations]
    unknown = set(bids) - {row["player_id"] for row in rows}
    if unknown:
        raise ValueError(f"Bid IDs are not available chop candidates: {sorted(unknown)}")
    available = min(max(0, int(weekly_cap) - int(spent)), int(budget))
    groups = defaultdict(int)
    for row in rows:
        # Only claims dropping the SAME owned player are mutually exclusive.
        row["claim_group"] = f"drop:{row['drop_id']}" if row["drop_id"] else f"add:{row['player_id']}"
        reduction = row["risk_reduction"]
        clear_gain = reduction > 2 * row["risk_reduction_standard_error"]
        # ponytail: review thresholds, not calibrated probabilities or prices.
        # Use validated guillotine outcomes before treating these as predictions.
        if row["action"] == "pass":
            row["category"] = "Pass"
        elif not clear_gain:
            row["category"] = "Free only"
        elif reduction < 0.01:
            row["category"] = "Marginal depth"
        else:
            row["category"] = "Review survival need" if risk > 1 / teams else "Review upgrade"
        row["chosen_bid"] = bids.get(row["player_id"])
        if row["chosen_bid"] is not None:
            if row["action"] == "pass":
                raise ValueError(f"Cannot bid on a pass candidate: {row['player_id']}")
            group = row["claim_group"]
            groups[group] = max(groups[group], int(row["chosen_bid"]))
    if sum(groups.values()) > available:
        raise ValueError(f"Chosen claims can spend ${sum(groups.values())}; remaining weekly limit is ${available}")
    remaining = available - sum(groups.values())
    for row in rows:
        group = row["claim_group"]
        if row["chosen_bid"] is not None:
            row["bid_range"] = [int(row["chosen_bid"])] * 2
            continue
        if row["category"] in {"Pass", "Free only"}:
            row["bid_range"] = None if row["category"] == "Pass" else [0, 0]
            continue
        ceiling = min(5, groups[group] + remaining)
        extra = max(0, ceiling - groups[group])
        remaining -= extra
        groups[group] += extra
        row["bid_range"] = [0, ceiling]
    return {
        "pricing": "spending_policy_v1", "weekly_cap": int(weekly_cap),
        "weekly_spent": int(spent), "weekly_remaining": available,
        "maximum_plan_spend": sum(groups.values()),
        "recommendations": rows,
    }


def analyze(snapshot, *, simulations=5000, seed=2026, weekly_cap=5, bids=None, drop_player=None):
    if not isinstance(simulations, int) or simulations < 100:
        raise ValueError("Use at least 100 simulations")
    _dollars(weekly_cap)
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
        **plan,
        "completed_waiver_bids": [t["settings"]["waiver_bid"] for t in transactions if t["type"] == "waiver" and t["status"] == "complete" and "waiver_bid" in (t.get("settings") or {})],
        "assumptions": [
            "Bid ranges are spending limits, not estimates of winning prices. It is OK to lose every claim.",
            "Default weekly limit: $5 total. Larger bids require an explicit player bid and a sufficient weekly limit.",
            "Maximum plan spend sums the largest offer per shared drop; claims without a drop count separately.",
            "Completed waiver spending for your roster in this Sleeper week is deducted from the weekly limit.",
            "The remaining limit covers only this report's claims. Include any other pending claims in your spending limit.",
            "Use the listed drop on every claim. Do not drop that player separately. Order equal bids by this table.",
            "Each roster comparison assumes one acquisition. Refresh after a win; gains from multiple wins are not additive.",
            "Current-week outcomes with opponents' current rosters; no future acquisitions or title probabilities.",
            "Drop suggestions use current-week value; injured/bye players require an explicit drop override.",
            "Healthy and questionable players use the projection as given; Out/IR/PUP/Sus/Inactive and no-game players score zero.",
            "Unresolved exact chop ties split elimination probability evenly.",
            "No paid default when risk reduction is within two simulation standard errors of zero; this is only a noise screen.",
            "A reduction of at least 1 percentage point flags an upgrade for review. Above-average baseline risk flags survival review.",
            "Review categories do not raise bids: assess future roster value and other available players before choosing a larger offer.",
            "Remaining teams affect the comparison and urgency flag, not a dollars-per-point formula.",
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
        "Ranges are bargain offers, not predicted winning prices. You may lose every claim.",
        "Review upgrades for lasting value before choosing a larger bid. Raising the weekly limit does not price players.",
        "Choose the claims you want. The ranges share one budget; some $0-only rows have no paid allowance left.", "",
        "| Player | Drop | Points gained | Chop risk after | Risk reduction | Category | Offer |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in report["recommendations"]:
        name = row["player"] + (f" ({row['status']})" if row["status"] != "Active" else "")
        offer = "Pass"
        if row["chosen_bid"] is not None:
            offer = f"${row['chosen_bid']} (your choice)"
        elif row["bid_range"] is not None:
            ceiling = row["bid_range"][1]
            offer = f"$0–${ceiling}" if ceiling else "$0 only"
        lines.append(f"| {name} | {row['drop'] or 'Open roster spot'} | {row['points_gain']:+.2f} | {row['chop_risk']:.1%} | {row['risk_reduction'] * 100:+.2f} pp | {row['category']} | {offer} |")
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
    parser.add_argument("--weekly-cap", type=int, default=5, help="Total limit for this report's claims; default $5")
    parser.add_argument("--bid", action="append", default=[], metavar="SLEEPER_ID=AMOUNT",
                        help="Your chosen bid, not a model price; repeat for multiple players")
    parser.add_argument("--drop-player", help="Sleeper ID to use instead of the automatic drop search")
    parser.add_argument("--output", type=Path, help="JSON report path; also writes a Markdown table")
    args = parser.parse_args()
    try:
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
