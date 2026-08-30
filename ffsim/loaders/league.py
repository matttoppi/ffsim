import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from ffsim.draft_intel.compatibility import league_compatibility
from ffsim.models.league import League
from ffsim.models.team import FantasyTeam
from ffsim.paths import CACHE_DIR


def _fetch_json(path):
    with urlopen(f"https://api.sleeper.app/v1/{path}", timeout=30) as response:
        return json.load(response)


def leagues_for_username(username, season=2026):
    username = username.strip()
    if not username:
        raise ValueError("Sleeper username cannot be empty")

    user = _fetch_json(f"user/{quote(username, safe='')}")
    if not user or not user.get("user_id"):
        raise ValueError(f"Sleeper user not found: {username}")

    leagues = _fetch_json(f"user/{user['user_id']}/leagues/nfl/{season}")
    return sorted(
        leagues,
        key=lambda league: (
            league.get("name", "").casefold(),
            str(league.get("league_id", "")),
        ),
    )


def league_id_for_username(username, season=2026):
    leagues = leagues_for_username(username, season)
    if not leagues:
        raise ValueError(f"No {season} NFL leagues found for Sleeper user {username}")
    if len(leagues) > 1:
        choices = ", ".join(
            f"{league.get('name', 'Unnamed')} ({league['league_id']})"
            for league in leagues
        )
        raise ValueError(
            f"Multiple {season} NFL leagues found for {username}; "
            f"use --league-id: {choices}"
        )
    return str(leagues[0]["league_id"])


def league_and_drafts(league_id, fetch_json=None):
    fetch = fetch_json or _fetch_json
    league_id = str(league_id)
    league = fetch(f"league/{league_id}")
    if not isinstance(league, dict) or str(league.get("league_id")) != league_id:
        raise ValueError(f"Sleeper returned the wrong league for {league_id}")
    drafts = fetch(f"league/{league_id}/drafts")
    if not isinstance(drafts, list):
        raise ValueError(f"Sleeper returned invalid drafts for league {league_id}")
    for draft in drafts:
        if not isinstance(draft, dict) or not draft.get("draft_id"):
            raise ValueError(f"Sleeper returned an invalid draft for league {league_id}")
        if str(draft.get("league_id")) != league_id:
            raise ValueError(
                f"Sleeper draft {draft['draft_id']} belongs to league {draft.get('league_id')}"
            )
    return league, drafts


def league_summary(league):
    return {
        "league_id": str(league["league_id"]),
        "name": league.get("name") or "Unnamed",
        "status": league.get("status", "unknown"),
        "season": league.get("season"),
        "season_type": league.get("season_type"),
        "total_rosters": league.get("total_rosters"),
        "roster_positions": league.get("roster_positions") or [],
        "settings": league.get("settings") or {},
        "scoring_settings": league.get("scoring_settings") or {},
    }


def draft_summary(league, draft, picks=()):
    compatibility = league_compatibility(league, draft, picks)
    settings = draft.get("settings") or {}
    metadata = draft.get("metadata") or {}
    return {
        "draft_id": str(draft["draft_id"]),
        "league_id": str(draft["league_id"]),
        "name": metadata.get("name") or league.get("name") or "Unnamed",
        "status": draft.get("status", "unknown"),
        "draft_type": draft.get("type", "unknown"),
        "season": draft.get("season"),
        "season_type": draft.get("season_type"),
        "teams": settings.get("teams"),
        "rounds": settings.get("rounds"),
        "pick_timer": settings.get("pick_timer"),
        "scoring_type": metadata.get("scoring_type"),
        "settings": settings,
        "metadata": metadata,
        "redraft_eligible": compatibility["redraft_eligible"],
        "redraft_ineligibility_reasons": compatibility[
            "redraft_ineligibility_reasons"
        ],
        "compatibility": compatibility,
    }


def _recent_trades(league, fetch, limit=30):
    state = fetch("state/nfl")
    if not isinstance(state, dict):
        raise ValueError("Sleeper returned invalid NFL state")
    league_season = int(league["season"])
    current_season = int(state.get("league_season") or state["season"])
    latest_week = (
        max(1, int(state.get("leg") or 1))
        if league_season == current_season
        else (18 if league_season < current_season else 1)
    )
    trades = []
    for week in range(latest_week, 0, -1):
        transactions = fetch(f"league/{league['league_id']}/transactions/{week}")
        if not isinstance(transactions, list) or not all(
            isinstance(transaction, dict) for transaction in transactions
        ):
            raise ValueError(f"Sleeper returned invalid transactions for week {week}")
        trades.extend(
            transaction
            for transaction in transactions
            if transaction.get("type") == "trade"
            and transaction.get("status") == "complete"
        )
        if len(trades) >= limit:
            break
    return sorted(
        trades,
        key=lambda transaction: (
            transaction.get("status_updated") or transaction.get("created") or 0
        ),
        reverse=True,
    )[:limit]


def recent_trade_summaries(snapshot, players):
    users = {str(user["user_id"]): user for user in snapshot.get("users", ())}
    roster_names = {}
    for roster in snapshot.get("rosters", ()):
        user = users.get(str(roster.get("owner_id")), {})
        metadata = user.get("metadata") or {}
        roster_names[str(roster["roster_id"])] = (
            metadata.get("team_name")
            or user.get("display_name")
            or user.get("username")
            or f"Roster {roster['roster_id']}"
        )

    summaries = []
    for trade in snapshot.get("recent_trades", ()):
        sides = {}

        def side(roster_id):
            key = str(roster_id)
            return sides.setdefault(
                key,
                {
                    "roster_id": roster_id,
                    "name": roster_names.get(key, f"Roster {roster_id}"),
                    "players": [],
                    "draft_picks": [],
                    "faab": 0,
                },
            )

        for roster_id in trade.get("roster_ids") or ():
            side(roster_id)

        for player_id, roster_id in (trade.get("adds") or {}).items():
            player = players.get(str(player_id), {})
            side(roster_id)["players"].append({
                "player_id": str(player_id),
                "name": player.get("full_name") or str(player_id),
                "position": player.get("position"),
                "team": player.get("team"),
            })
        for pick in trade.get("draft_picks") or ():
            side(pick["owner_id"])["draft_picks"].append({
                "season": str(pick["season"]),
                "round": int(pick["round"]),
            })
        for transfer in trade.get("waiver_budget") or ():
            side(transfer["receiver"])["faab"] += int(transfer["amount"])

        summaries.append({
            "transaction_id": str(trade["transaction_id"]),
            "completed_at": trade.get("status_updated") or trade.get("created"),
            "sides": list(sides.values()),
        })
    return summaries


def refresh_league(league_id, draft_id=None, fetch_json=None, cache_dir=None):
    fetch = fetch_json or _fetch_json
    league, drafts = league_and_drafts(league_id, fetch)
    selected_draft = None
    draft_picks = []
    traded_picks = []
    if draft_id is not None:
        draft_id = str(draft_id)
        if not any(str(draft["draft_id"]) == draft_id for draft in drafts):
            raise ValueError(f"Draft {draft_id} does not belong to league {league_id}")
        selected_draft = fetch(f"draft/{draft_id}")
        if (
            not isinstance(selected_draft, dict)
            or str(selected_draft.get("draft_id")) != draft_id
            or str(selected_draft.get("league_id")) != str(league_id)
        ):
            raise ValueError(f"Sleeper returned the wrong draft for {draft_id}")
        draft_picks = fetch(f"draft/{draft_id}/picks")
        traded_picks = fetch(f"draft/{draft_id}/traded_picks")
        if not isinstance(draft_picks, list) or not isinstance(traded_picks, list):
            raise ValueError(f"Sleeper returned invalid pick data for draft {draft_id}")
        if any(str(pick.get("draft_id")) != draft_id for pick in draft_picks):
            raise ValueError(f"Sleeper returned picks from another draft for {draft_id}")

    snapshot = {
        "league": league,
        "drafts": drafts,
        "draft": selected_draft,
        "draft_picks": draft_picks,
        "traded_picks": traded_picks,
        "draft_summary": (
            draft_summary(league, selected_draft, draft_picks)
            if selected_draft is not None
            else None
        ),
        "rosters": fetch(f"league/{league_id}/rosters"),
        "users": fetch(f"league/{league_id}/users"),
        "winners_bracket": fetch(f"league/{league_id}/winners_bracket"),
        "recent_trades": _recent_trades(league, fetch),
    }
    cache_dir = Path(cache_dir or CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"league_{league_id}.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n")


class LeagueLoader:
    def __init__(self, league_id, player_loader):
        path = CACHE_DIR / f"league_{league_id}.json"
        if not path.exists():
            raise FileNotFoundError("League cache is missing. Run `python -m ffsim refresh` first.")
        self.snapshot = json.loads(path.read_text())
        if self.snapshot.get("draft"):
            compatibility = league_compatibility(
                self.snapshot["league"],
                self.snapshot["draft"],
                self.snapshot.get("draft_picks", ()),
            )["capabilities"]["season_evaluation"]
            if compatibility["status"] != "supported":
                raise ValueError(
                    "Attached Sleeper league is not supported for season evaluation: "
                    + json.dumps(compatibility["reasons"], separators=(",", ":"))
                )
        self.player_loader = player_loader
        self.player_loader.ensure_players_loaded()
        self.unmatched_rostered = []

    def load_league(self):
        league = League(self.snapshot["league"])
        league.rosters = self.load_rosters(league)
        league.winners_bracket = self.snapshot.get("winners_bracket", [])
        print(f"League {league.name} loaded with {len(league.rosters)} teams.")
        if self.unmatched_rostered:
            print("Rostered players without 2026 projections are unavailable:")
            for player in sorted(self.unmatched_rostered, key=lambda player: (player.name, str(player.sleeper_id))):
                print(f"  {player.name} ({player.position}, {player.team}, Sleeper {player.sleeper_id})")
        return league

    def load_rosters(self, league):
        users = {user["user_id"]: user for user in self.snapshot["users"]}
        rosters = []
        for roster_data in self.snapshot["rosters"]:
            user_data = users.get(roster_data.get("owner_id"), {})
            team_name = user_data.get("metadata", {}).get("team_name", "Unknown")
            team = FantasyTeam(team_name, league, user_data)
            team.roster_id = roster_data.get("roster_id")
            division = roster_data.get("settings", {}).get("division")
            if division is not None:
                league.divisions.setdefault(int(division), []).append(team.roster_id)

            for player_id in roster_data.get("players", []):
                player = self.player_loader.load_player(player_id)
                if player:
                    if player.position in {"QB", "RB", "WR", "TE", "K", "DEF"} and player.projection_match_status in {"ambiguous", "position_mismatch"}:
                        raise ValueError(
                            f"Rostered player has no unique position-consistent projection: "
                            f"{player.name} ({player.position}, {player.team}, Sleeper {player.sleeper_id})"
                        )
                    if player.position in {"QB", "RB", "WR", "TE", "K", "DEF"} and player.projection_match_status == "unmatched":
                        self.unmatched_rostered.append(player)
                    team.add_player(player)

            team.calculate_metadata()
            rosters.append(team)
        return rosters
