"""Explicit compatibility checks for attached Sleeper leagues and drafts."""

from ffsim.models.team import FLEX_ELIGIBILITY
from ffsim.scoring import unsupported_scoring_keys


SUPPORTED_ROSTER_POSITIONS = {
    "QB", "RB", "WR", "TE", "K", "DEF", *FLEX_ELIGIBILITY, "BN", "IR",
}


def league_compatibility(league, draft, picks=()):
    """Report where an attached source can be used without changing its rules."""
    league_settings = league.get("settings") or {}
    draft_settings = draft.get("settings") or {}
    draft_type = str(draft.get("type") or "unknown").casefold()
    replay_reasons = []
    rollout_reasons = []
    season_reasons = []
    redraft_reasons = []

    league_type = league_settings.get("type")
    scoring_type = str((draft.get("metadata") or {}).get("scoring_type") or "")
    if league_type == 1:
        redraft_reasons.append("keeper_league")
    elif league_type == 2 or "dynasty" in scoring_type.casefold():
        redraft_reasons.append("dynasty")
    elif league_type not in {None, 0}:
        redraft_reasons.append(f"unknown_league_type_{league_type}")
    if any(pick.get("is_keeper") is True for pick in picks):
        redraft_reasons.append("keeper_picks")
        replay_reasons.append({"code": "keeper_picks"})
    redraft_reasons = list(dict.fromkeys(redraft_reasons))
    rollout_reasons.extend({"code": reason} for reason in redraft_reasons)

    if draft_type not in {"snake", "linear", "auction"}:
        reason = {"code": "unsupported_draft_type", "value": draft_type}
        replay_reasons.append(reason)
        rollout_reasons.append(reason)
    elif draft_type == "auction":
        rollout_reasons.append({"code": "auction_future_owners_unknown"})

    league_teams = _positive_int(league.get("total_rosters"))
    draft_teams = _positive_int(draft_settings.get("teams"))
    if league_teams is None or draft_teams is None:
        reason = {"code": "invalid_team_count"}
        replay_reasons.append(reason)
        rollout_reasons.append(reason)
        season_reasons.append(reason)
    elif league_teams != draft_teams:
        reason = {
            "code": "team_count_mismatch",
            "league": league_teams,
            "draft": draft_teams,
        }
        replay_reasons.append(reason)
        rollout_reasons.append(reason)
        season_reasons.append(reason)

    best_ball = league_settings.get("best_ball")
    if best_ball is None:
        season_reasons.append({"code": "unknown_best_ball"})
    elif bool(best_ball):
        season_reasons.append({"code": "best_ball"})

    roster_positions = {str(position) for position in league.get("roster_positions") or ()}
    unsupported_positions = sorted(roster_positions - SUPPORTED_ROSTER_POSITIONS)
    if not roster_positions:
        season_reasons.append({"code": "missing_roster_positions"})
    elif unsupported_positions:
        season_reasons.append({
            "code": "unsupported_roster_positions",
            "values": unsupported_positions,
        })

    try:
        unsupported_scoring = unsupported_scoring_keys(
            league.get("scoring_settings") or {}
        )
    except (TypeError, ValueError):
        season_reasons.append({"code": "invalid_scoring_settings"})
    else:
        if unsupported_scoring:
            season_reasons.append({
                "code": "unsupported_scoring_keys",
                "values": unsupported_scoring,
            })

    playoff_teams = _positive_int(league_settings.get("playoff_teams"))
    if playoff_teams not in {4, 6, 8}:
        season_reasons.append({
            "code": "unsupported_playoff_teams",
            "value": league_settings.get("playoff_teams"),
        })
    elif league_teams is not None and playoff_teams > league_teams:
        season_reasons.append({"code": "playoff_teams_exceed_league_size"})
    if league_settings.get("playoff_round_type") != 0:
        season_reasons.append({
            "code": "unsupported_playoff_round_type",
            "value": league_settings.get("playoff_round_type"),
        })
    if league_settings.get("playoff_seed_type") != 0:
        season_reasons.append({
            "code": "unsupported_playoff_seed_type",
            "value": league_settings.get("playoff_seed_type"),
        })
    divisions = _nonnegative_int(league_settings.get("divisions", 0))
    if divisions is None or (playoff_teams is not None and divisions > playoff_teams):
        season_reasons.append({
            "code": "unsupported_division_count",
            "value": league_settings.get("divisions"),
        })

    capabilities = {
        "attachment": {"status": "supported", "reasons": []},
        "draft_replay": _capability(replay_reasons),
        "draft_rollout": _capability(rollout_reasons),
        "season_evaluation": _capability(season_reasons),
    }
    return {
        "status": (
            "supported"
            if all(value["status"] == "supported" for value in capabilities.values())
            else "attachment_only"
        ),
        "capabilities": capabilities,
        "redraft_eligible": not redraft_reasons,
        "redraft_ineligibility_reasons": redraft_reasons,
    }


def _capability(reasons):
    return {
        "status": "supported" if not reasons else "unsupported",
        "reasons": reasons,
    }


def _positive_int(value):
    try:
        value = int(value)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _nonnegative_int(value):
    try:
        value = int(value)
        return value if value >= 0 else None
    except (TypeError, ValueError):
        return None
