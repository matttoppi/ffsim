"""Import an authorized saved DraftSharks Injury Predictor HTML page."""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffsim.loaders.pff import canonical_team, normalized_name
from ffsim.paths import CACHE_DIR, DATA_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Saved Injury Predictor HTML or copied table text")
    parser.add_argument("--output", default=DATA_DIR / "injuries" / "risk.csv")
    args = parser.parse_args()

    source = Path(args.source).read_text()
    marker = '"playerData":'
    if marker in source:
        rows, _ = json.JSONDecoder().raw_decode(source[source.index(marker) + len(marker):])
    else:
        values = [value.strip() for value in source.splitlines() if value.strip()][13:]
        if len(values) % 11:
            raise ValueError("Copied table does not contain complete 11-field player rows")
        rows = []
        for index in range(0, len(values), 11):
            (
                name, team, rank, _, _, injuries_per_season, season_risk,
                per_game_risk, durability, _, missed
            ) = values[index:index + 11]
            first, _, last = name.replace("\xa0", " ").partition(" ")
            rows.append({
                "first_name": first,
                "last_name": last,
                "fantasy_position": re.sub(r"\d+$", "", rank).upper(),
                "team": {"abbr": team},
                "sipPlayerProfile": {
                    "injury_prob": str(float(season_risk.rstrip("%")) / 100),
                    "injuries_per_season": injuries_per_season.removesuffix("/yr"),
                    "injury_prob_per_game": str(float(per_game_risk.rstrip("%")) / 100),
                    "proj_games_missed": missed,
                    "durability": durability,
                    "update_time": "2026 copied table",
                },
            })
    cached = json.loads((CACHE_DIR / "players.json").read_text())
    sleeper_ids = {
        (normalized_name(player.get("full_name")), str(player.get("position", "")).upper()):
        str(player["sleeper_id"])
        for player in cached
    }
    fallback_ids = {
        (
            normalized_name(str(player.get("last_name", ""))),
            str(player.get("position", "")).upper(),
            canonical_team(player.get("team")),
        ): str(player["sleeper_id"])
        for player in cached
    }

    output = []
    for player in rows:
        profile = player.get("sipPlayerProfile") or {}
        key = (
            normalized_name(f"{player.get('first_name', '')} {player.get('last_name', '')}"),
            str(player.get("fantasy_position", "")).upper(),
        )
        if key[1] not in {"QB", "RB", "WR", "TE"}:
            continue
        sleeper_id = sleeper_ids.get(key) or fallback_ids.get((
            normalized_name(player.get("last_name")),
            key[1],
            canonical_team((player.get("team") or {}).get("abbr")),
        ))
        if not sleeper_id or not profile:
            continue
        output.append({
            "season": 2026,
            "sleeper_id": sleeper_id,
            "player": f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
            "position": key[1],
            "team": (player.get("team") or {}).get("abbr", ""),
            "injury_probability": profile["injury_prob"],
            "injuries_per_season": profile.get("injuries_per_season", ""),
            "injury_probability_per_game": profile.get("injury_prob_per_game", ""),
            "projected_games_missed": profile["proj_games_missed"],
            "durability": profile.get("durability", ""),
            "updated_at": profile.get("update_time", ""),
        })

    if not output:
        raise ValueError("No DraftSharks players matched the Sleeper player cache")

    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=output[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(output)
    print(f"Imported {len(output)} current injury profiles to {path}")


if __name__ == "__main__":
    main()
