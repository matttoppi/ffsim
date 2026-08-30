#!/usr/bin/env python3
import csv
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parents[4]
SOURCE = ROOT / "archive/data/legacy/pff_projections_2024.csv"


def main():
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames
    history = subprocess.run(
        [
            "git",
            "log",
            "--follow",
            "--diff-filter=A",
            "--format=%H %aI",
            "--",
            str(SOURCE.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().splitlines()
    if len(history) != 1:
        raise RuntimeError(f"expected one file-addition commit, found {history}")
    commit, committed_at = history[0].split(" ", 1)
    before_kickoff = datetime.fromisoformat(committed_at) < datetime.fromisoformat(
        "2024-09-05T20:20:00-04:00"
    )
    projection_fields = {
        "fantasyPoints",
        "passYds",
        "passTd",
        "rushYds",
        "rushTd",
        "recvTargets",
        "recvReceptions",
        "recvYds",
        "recvTd",
    }
    result = {
        "source": "manual PFF 2024 export",
        "path": str(SOURCE.relative_to(ROOT)),
        "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "rows": len(rows),
        "columns": columns,
        "projection_fields_present": sorted(projection_fields & set(columns)),
        "repository_addition_commit": commit,
        "repository_addition_time": committed_at,
        "repository_addition_before_kickoff": before_kickoff,
        "provider_publication_timestamp_verified": False,
        "provider_player_id_present": False,
        "accepted_for_training": False,
        "status": "rejected_for_point_in_time",
        "reason": (
            "Git history proves only repository custody. It does not establish "
            "the provider publication or download timestamp required for a "
            "leakage-safe target-draft cutoff."
        ),
    }
    Path(__file__).with_name("result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
