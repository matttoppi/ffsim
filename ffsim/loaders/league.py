import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

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
    scoring_type = str((draft.get("metadata") or {}).get("scoring_type") or "")
    league_type = (league.get("settings") or {}).get("type")
    reasons = []
    if league_type == 1:
        reasons.append("keeper_league")
    elif league_type == 2 or "dynasty" in scoring_type.casefold():
        reasons.append("dynasty")
    elif league_type not in {None, 0}:
        reasons.append(f"unknown_league_type_{league_type}")
    if any(pick.get("is_keeper") is True for pick in picks):
        reasons.append("keeper_picks")
    reasons = list(dict.fromkeys(reasons))
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
        "redraft_eligible": not reasons,
        "redraft_ineligibility_reasons": reasons,
    }


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
                            f"Rostered player has no unique position-consistent PFF projection: "
                            f"{player.name} ({player.position}, {player.team}, Sleeper {player.sleeper_id})"
                        )
                    if player.position in {"QB", "RB", "WR", "TE", "K", "DEF"} and player.projection_match_status == "unmatched":
                        self.unmatched_rostered.append(player)
                    team.add_player(player)

            team.calculate_metadata()
            rosters.append(team)
        return rosters
