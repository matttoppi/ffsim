import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from .hdvn_contract import LABEL_VERSION
from .hdvn_snapshot import canonical_json, sha256_file


SPLIT_VERSION = "hdvn-split-v1"
PARTITION_BY_YEAR = {
    2021: "train",
    2022: "train",
    2023: "train",
    2024: "validation",
    2025: "locked_test",
}

LABEL_CONTRACT = {
    "label_version": LABEL_VERSION,
    "labels": {
        "points_for_percentile": {
            "source": "team_seasons.matchup_points_for",
            "rule": "within-league midrank percentile on commissioner-adjusted regular-season matchup points",
            "null": "source cannot support safe regular-season points",
        },
        "regular_season_win_percentage": {
            "source": "team_seasons.h2h_wins, h2h_losses, h2h_ties, regular_season_games",
            "rule": "(wins + 0.5 * ties) / games",
            "null": "source cannot support safe head-to-head games",
        },
        "made_playoffs": {
            "source": "team_seasons.made_playoffs",
            "rule": "roster appears in the winners bracket",
            "null": "source bracket cannot support a safe result",
        },
        "champion": {
            "source": "team_seasons.champion",
            "rule": "exactly one placement-1 winners-bracket champion per included league-season",
            "null": "source bracket cannot support exactly one champion",
        },
    },
    "raw_source_facts_separate": True,
}


def label_manifest():
    body = dict(LABEL_CONTRACT)
    return {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}


def training_exclusion_reasons(connection, league_id, season, draft_id):
    league = connection.execute(
        """
        SELECT is_candidate, candidate_reasons_json, total_rosters, best_ball
        FROM league_seasons WHERE league_id = ? AND season = ?
        """,
        (league_id, season),
    ).fetchone()
    draft = connection.execute(
        "SELECT status, draft_type, team_count, rounds FROM drafts WHERE draft_id = ?",
        (draft_id,),
    ).fetchone()
    reasons = []
    if league is None or draft is None:
        return ["missing_league_or_draft"]
    if not league["is_candidate"]:
        reasons.append("unsupported_format")
        reasons.extend(json.loads(league["candidate_reasons_json"] or "[]"))
    if league["best_ball"]:
        reasons.append("best_ball")
    if draft["status"] != "complete":
        reasons.append("incomplete_draft")
    if draft["draft_type"] != "snake":
        reasons.append("unsupported_draft_type")
    expected = (draft["team_count"] or 0) * (draft["rounds"] or 0)
    actual = connection.execute(
        "SELECT COUNT(*) FROM draft_picks WHERE draft_id = ?", (draft_id,)
    ).fetchone()[0]
    if not expected or actual != expected:
        reasons.append("incomplete_draft")
    if connection.execute(
        "SELECT EXISTS(SELECT 1 FROM draft_picks WHERE draft_id = ? AND is_keeper = 1)",
        (draft_id,),
    ).fetchone()[0]:
        reasons.append("keeper_draft")
    hydration = connection.execute(
        "SELECT status FROM hydration_queue WHERE league_id = ? AND season = ?",
        (league_id, season),
    ).fetchone()
    if hydration is None or hydration[0] != "done":
        reasons.append("not_hydrated")
    if connection.execute(
        """
        SELECT EXISTS(
            SELECT 1 FROM quality_flags
            WHERE severity = 'error'
              AND ((scope = 'league_season' AND entity_key = ? || ':' || ?)
                   OR (scope = 'draft' AND entity_key = ?))
        )
        """,
        (league_id, season, draft_id),
    ).fetchone()[0]:
        reasons.append("error_quality_flag")
    roster_count = connection.execute(
        "SELECT COUNT(*) FROM rosters WHERE league_id = ? AND season = ?",
        (league_id, season),
    ).fetchone()[0]
    if roster_count != league["total_rosters"]:
        reasons.append("roster_count_mismatch")
    return sorted(set(reasons))


def labels_for_league(connection, league_id, season):
    rows = list(
        connection.execute(
            """
            SELECT roster_id, matchup_points_for, h2h_wins, h2h_losses, h2h_ties,
                   regular_season_games, made_playoffs, champion
            FROM team_seasons
            WHERE league_id = ? AND season = ?
            ORDER BY roster_id
            """,
            (league_id, season),
        )
    )
    points = [row["matchup_points_for"] for row in rows if row["matchup_points_for"] is not None]
    percentiles = _midrank_percentiles(points)
    champion_count = sum(row["champion"] == 1 for row in rows)
    labels = {}
    for row in rows:
        games = row["regular_season_games"]
        win_percentage = (
            (row["h2h_wins"] + 0.5 * row["h2h_ties"]) / games if games else None
        )
        labels[row["roster_id"]] = {
            "label_version": LABEL_VERSION,
            "points_for_percentile": percentiles.get(row["matchup_points_for"]),
            "regular_season_win_percentage": win_percentage,
            "made_playoffs": row["made_playoffs"],
            "champion": row["champion"] if champion_count == 1 else None,
            "champion_count": champion_count,
        }
    return labels


def _midrank_percentiles(values):
    if not values:
        return {}
    ordered = sorted(values)
    if len(ordered) == 1:
        return {ordered[0]: 50.0}
    result = {}
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[index]:
            end += 1
        result[ordered[index]] = 100 * ((index + end) / 2) / (len(ordered) - 1)
        index = end + 1
    return result


def build_split_manifest(team_rows):
    leagues = {}
    context_counts = Counter()
    champion_events = Counter()
    draft_slots = Counter()
    team_counts = Counter()
    for row in team_rows:
        if not row["training_eligible"]:
            continue
        season = int(row["season"])
        partition = PARTITION_BY_YEAR.get(season)
        if partition is None:
            raise ValueError(f"unsupported split year {season}")
        key = f"{season}:{row['league_id']}"
        prior = leagues.setdefault(key, partition)
        if prior != partition:
            raise ValueError(f"league-season crosses partitions: {key}")
        context_counts[(partition, season, row["scoring_format"], row["team_count"])] += 1
        draft_slots[(partition, row["draft_slot"])] += 1
        team_counts[partition] += 1
        champion_events[partition] += int(row.get("champion") == 1)

    partitions = {
        name: sorted(key for key, partition in leagues.items() if partition == name)
        for name in ("train", "validation", "locked_test")
    }
    all_ids = set().union(*(set(values) for values in partitions.values()))
    if all_ids != set(leagues):
        raise ValueError("split manifest lost a league-season")
    names = tuple(partitions)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            if set(partitions[left]) & set(partitions[right]):
                raise ValueError("league-season appears in multiple partitions")
    body = {
        "split_version": SPLIT_VERSION,
        "years": {"train": [2021, 2022, 2023], "validation": [2024], "locked_test": [2025]},
        "partitions": partitions,
        "counts": {
            "league_seasons": {name: len(values) for name, values in partitions.items()},
            "teams": dict(sorted(team_counts.items())),
            "champion_events": dict(sorted(champion_events.items())),
            "by_context": [
                {
                    "partition": key[0],
                    "season": key[1],
                    "scoring_format": key[2],
                    "team_count": key[3],
                    "teams": count,
                }
                for key, count in sorted(context_counts.items())
            ],
            "by_draft_slot": [
                {"partition": key[0], "draft_slot": key[1], "teams": count}
                for key, count in sorted(draft_slots.items())
            ],
        },
        "locked_test_policy": "2025 IDs are immutable and excluded from fitting and model selection",
    }
    return {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}


def write_split_manifest(manifest, path):
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"split manifest is immutable: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(manifest) + "\n")
    path.chmod(0o444)
    return path


def assert_split_isolation(rows, manifest):
    membership = {}
    for partition, league_ids in manifest["partitions"].items():
        for league_season_id in league_ids:
            prior = membership.setdefault(league_season_id, partition)
            if prior != partition:
                raise ValueError(f"league-season crosses partitions: {league_season_id}")
    for row in rows:
        if not row.get("training_eligible", True):
            continue
        key = row.get("league_season_id") or f"{row['season']}:{row['league_id']}"
        expected = PARTITION_BY_YEAR.get(int(row["season"]))
        if membership.get(key) != expected:
            raise ValueError(f"row is outside its league-season partition: {key}")
        if row.get("partition") not in {None, expected}:
            raise ValueError(f"row crosses its league-season partition: {key}")
    return True


def materialize_labels_and_split(
    team_table,
    prefix_table,
    output_directory,
    *,
    source_snapshot_hash,
    feature_manifest_hash,
    tables_manifest_hash,
    command,
    batch_size=10_000,
):
    team_table = Path(team_table).resolve()
    prefix_table = Path(prefix_table).resolve()
    output_directory = Path(output_directory).resolve()
    labels_path = output_directory / "labels-v1.parquet"
    partition_paths = {
        "train": output_directory / "team-train-v1.parquet",
        "validation": output_directory / "team-validation-v1.parquet",
        "locked_test": output_directory / "team-locked-test-v1.parquet",
    }
    split_path = output_directory / "split-v1.json"
    locked_path = output_directory / "locked-test-2025-v1.json"
    manifest_path = output_directory / "labels-split-v1.manifest.json"
    paths = (
        labels_path,
        *partition_paths.values(),
        split_path,
        locked_path,
        manifest_path,
    )
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable label/split output already exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    try:
        _write_label_and_partition_tables(
            team_table,
            labels_path,
            partition_paths,
            batch_size,
        )
        split = build_split_manifest(_iter_parquet_rows(team_table, batch_size))
        contract = label_manifest()
        body = {
            **{key: value for key, value in split.items() if key != "sha256"},
            "source_snapshot_sha256": source_snapshot_hash,
            "feature_manifest_hash": feature_manifest_hash,
            "label_manifest_hash": contract["sha256"],
            "tables_manifest_hash": tables_manifest_hash,
            "partition_files": {
                partition: {
                    "path": path.name,
                    "sha256": sha256_file(path),
                }
                for partition, path in partition_paths.items()
            },
        }
        split = {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}
        assert_split_isolation(_iter_parquet_rows(team_table, batch_size), split)
        assert_split_isolation(_iter_parquet_rows(prefix_table, batch_size), split)
        write_split_manifest(split, split_path)

        locked_body = {
            "manifest_version": 1,
            "split_version": SPLIT_VERSION,
            "partition": "locked_test",
            "season": 2025,
            "league_season_ids": split["partitions"]["locked_test"],
            "team_file": partition_paths["locked_test"].name,
            "team_file_sha256": sha256_file(partition_paths["locked_test"]),
            "source_snapshot_sha256": source_snapshot_hash,
            "feature_manifest_hash": feature_manifest_hash,
            "label_manifest_hash": contract["sha256"],
            "split_manifest_hash": split["sha256"],
            "policy": "locked benchmark only; ordinary training access is prohibited",
        }
        locked = {
            **locked_body,
            "sha256": hashlib.sha256(canonical_json(locked_body).encode()).hexdigest(),
        }
        locked_path.write_text(canonical_json(locked) + "\n")
        locked_path.chmod(0o444)

        label_acceptance = _validate_label_table(labels_path, batch_size)
        manifest = {
            "manifest_version": 1,
            "label_contract": contract,
            "source_snapshot_sha256": source_snapshot_hash,
            "feature_manifest_hash": feature_manifest_hash,
            "tables_manifest_hash": tables_manifest_hash,
            "split_manifest_hash": split["sha256"],
            "locked_test_manifest_hash": locked["sha256"],
            "command": command,
            "label_acceptance": label_acceptance,
            "files": {
                path.name: {
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in (
                    labels_path,
                    *partition_paths.values(),
                    split_path,
                    locked_path,
                )
            },
        }
        manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
        manifest_path.write_text(canonical_json(manifest) + "\n")
        for path in paths:
            path.chmod(0o444)
        return manifest
    except BaseException:
        for path in paths:
            path.unlink(missing_ok=True)
        raise


def load_team_partition(manifest_path, partition, *, locked_benchmark=False):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    stored_hash = manifest.get("sha256")
    body = {key: value for key, value in manifest.items() if key != "sha256"}
    if stored_hash != hashlib.sha256(canonical_json(body).encode()).hexdigest():
        raise ValueError("split manifest hash mismatch")
    if partition not in {"train", "validation", "locked_test"}:
        raise ValueError(f"unknown split partition: {partition}")
    if partition == "locked_test" and not locked_benchmark:
        raise PermissionError("locked 2025 test access requires the locked-benchmark command")
    record = manifest["partition_files"][partition]
    path = manifest_path.parent / record["path"]
    if sha256_file(path) != record["sha256"]:
        raise ValueError(f"partition file hash mismatch: {partition}")
    return _iter_parquet_rows(path, 10_000)


def _write_label_and_partition_tables(team_table, labels_path, partition_paths, batch_size):
    try:
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("label materialization requires pyarrow") from error
    parquet = pq.ParquetFile(team_table)
    label_columns = (
        "league_id",
        "season",
        "draft_id",
        "roster_id",
        "owner_id",
        "points_for_percentile",
        "regular_season_win_percentage",
        "made_playoffs",
        "champion",
        "label_version",
        "source_manifest_hash",
    )
    temporary = {
        "labels": labels_path.with_suffix(labels_path.suffix + ".tmp"),
        **{
            partition: path.with_suffix(path.suffix + ".tmp")
            for partition, path in partition_paths.items()
        },
    }
    writers = {}
    try:
        for batch in parquet.iter_batches(batch_size=batch_size):
            table = pa.Table.from_batches([batch])
            labels = table.select(label_columns)
            if "labels" not in writers:
                writers["labels"] = pq.ParquetWriter(
                    temporary["labels"],
                    labels.schema,
                    compression="zstd",
                )
            writers["labels"].write_table(labels)
            eligible = pc.equal(table["training_eligible"], True)
            for partition, years in (
                ("train", (2021, 2022, 2023)),
                ("validation", (2024,)),
                ("locked_test", (2025,)),
            ):
                in_years = pc.is_in(table["season"], value_set=pa.array(years))
                selected = table.filter(pc.and_(eligible, in_years))
                if selected.num_rows == 0:
                    continue
                if partition not in writers:
                    writers[partition] = pq.ParquetWriter(
                        temporary[partition],
                        table.schema,
                        compression="zstd",
                    )
                writers[partition].write_table(selected)
    finally:
        for writer in writers.values():
            writer.close()
    if set(writers) != {"labels", "train", "validation", "locked_test"}:
        for path in temporary.values():
            path.unlink(missing_ok=True)
        raise ValueError("one or more split partitions are empty")
    os.replace(temporary["labels"], labels_path)
    for partition, path in partition_paths.items():
        os.replace(temporary[partition], path)


def _iter_parquet_rows(path, batch_size):
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("label materialization requires pyarrow") from error
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=batch_size):
        yield from batch.to_pylist()


def _validate_label_table(path, batch_size):
    rows = 0
    nulls = Counter()
    champions = Counter()
    for row in _iter_parquet_rows(path, batch_size):
        rows += 1
        league = f"{row['season']}:{row['league_id']}"
        champions[league] += int(row["champion"] or 0)
        for field in (
            "points_for_percentile",
            "regular_season_win_percentage",
            "made_playoffs",
            "champion",
        ):
            if row[field] is None:
                nulls[field] += 1
        points = row["points_for_percentile"]
        wins = row["regular_season_win_percentage"]
        if points is not None and not 0 <= points <= 100:
            raise ValueError("points percentile is outside 0..100")
        if wins is not None and not 0 <= wins <= 1:
            raise ValueError("win percentage is outside 0..1")
    invalid_champions = sum(count != 1 for count in champions.values())
    if invalid_champions:
        raise ValueError("included label cohort does not have exactly one champion per league")
    return {
        "rows": rows,
        "league_seasons": len(champions),
        "champion_events": sum(champions.values()),
        "null_counts": dict(sorted(nulls.items())),
        "invalid_champion_leagues": invalid_champions,
    }
