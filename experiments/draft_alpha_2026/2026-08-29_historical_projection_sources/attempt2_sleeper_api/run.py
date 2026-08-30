#!/usr/bin/env python3
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SEASONS = (2024, 2025)


def iso(milliseconds):
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()


def main():
    seasons = {}
    for season in SEASONS:
        url = f"https://api.sleeper.com/projections/nfl/{season}?season_type=regular"
        request = Request(url, headers={"User-Agent": "ffsim/1.0"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
        rows = json.loads(raw)
        modified = [int(row["last_modified"]) for row in rows if row.get("last_modified")]
        kickoff = datetime(season, 9, 1, tzinfo=timezone.utc).timestamp() * 1000
        seasons[str(season)] = {
            "url": url,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "rows": len(rows),
            "category_values": sorted({str(row.get("category")) for row in rows}),
            "minimum_last_modified": iso(min(modified)),
            "maximum_last_modified": iso(max(modified)),
            "rows_modified_before_september": sum(value < kickoff for value in modified),
            "rows_modified_after_september": sum(value >= kickoff for value in modified),
            "sample_stat_fields": sorted({
                key for row in rows[:100] for key in (row.get("stats") or {})
            }),
        }
    accepted = all(
        result["rows_modified_after_september"] == 0 for result in seasons.values()
    )
    result = {
        "source": "Sleeper projections API",
        "access": "public read-only non-commercial",
        "seasons": seasons,
        "accepted_for_training": accepted,
        "status": "accepted" if accepted else "rejected_for_point_in_time",
        "reason": (
            "Every row must retain a pre-season modification timestamp. "
            "Post-season updates cannot reconstruct what was known at draft time."
        ),
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
