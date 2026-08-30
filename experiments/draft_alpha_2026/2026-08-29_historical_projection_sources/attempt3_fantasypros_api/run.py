#!/usr/bin/env python3
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ffsim.loaders.fantasypros import fantasypros_api_key

SEASONS = (2024, 2025)


def main():
    key = fantasypros_api_key()
    seasons = {}
    for season in SEASONS:
        url = f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections"
        url = f"{url}?{urlencode({'positions': 'QB:RB:WR:TE', 'week': 0})}"
        request = Request(
            url,
            headers={
                "x-api-key": key,
                "Cache-Control": "no-cache",
                "User-Agent": "ffsim/1.0",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                status = response.status
            payload = json.loads(raw)
            players = payload.get("players")
            timestamp_fields = {
                name: value
                for name, value in payload.items()
                if any(token in name.lower() for token in ("date", "time", "updated", "observed"))
            }
            seasons[str(season)] = {
                "http_status": status,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "season": payload.get("season"),
                "week": payload.get("week"),
                "positions": payload.get("positions"),
                "rows": len(players) if isinstance(players, list) else None,
                "timestamp_fields": timestamp_fields,
                "response_keys": sorted(payload),
            }
        except HTTPError as error:
            seasons[str(season)] = {
                "http_status": error.code,
                "error": str(error.reason),
            }
        time.sleep(1)
    has_rows = all((result.get("rows") or 0) > 0 for result in seasons.values())
    has_timestamps = all(result.get("timestamp_fields") for result in seasons.values())
    historical_access_authorized = False
    accepted = has_rows and has_timestamps and historical_access_authorized
    result = {
        "source": "FantasyPros personal API",
        "official_access_note": (
            "Personal keys cover current rankings and projections; the official "
            "API page assigns historical data and bulk access to Commercial."
        ),
        "seasons": seasons,
        "historical_access_authorized": historical_access_authorized,
        "accepted_for_training": accepted,
        "status": "accepted" if accepted else "rejected_for_point_in_time",
        "reason": (
            "Historical rows require an authoritative preseason observation "
            "timestamp and authorized historical access. A season parameter "
            "alone does not establish point-in-time provenance."
        ),
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
