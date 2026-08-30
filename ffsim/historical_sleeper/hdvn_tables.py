import hashlib
import json
import os
import sqlite3
from collections import Counter
from itertools import groupby
from pathlib import Path

from .hdvn_contract import (
    FEATURE_VERSION,
    LABEL_VERSION,
    MATERIALIZED_COLUMN_FEATURES,
    PREFIX_VERSION,
    validate_materialized_columns,
)
from .hdvn_labels import labels_for_league, training_exclusion_reasons
from .hdvn_snapshot import TRAINING_READY_CTE, canonical_json, sha256_file


TEAM_TABLE_VERSION = "hdvn-team-table-v1"
FLEX_ELIGIBILITY = {
    "FLEX": ("RB", "WR", "TE"),
    "REC_FLEX": ("WR", "TE"),
    "WRRB_FLEX": ("WR", "RB"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
}
BENCH_SLOTS = {"BN", "BENCH", "IR", "RESERVE", "TAXI"}


def iter_team_rows(
    connection,
    market_connection,
    source_manifest_hash,
    feature_manifest_hash,
    *,
    batch_size=100,
):
    """Yield one deterministic row per eligible team-season."""
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    cursor = connection.execute(
        TRAINING_READY_CTE
        + """
        , eligible_drafts AS (
            SELECT d.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY d.league_id, d.season
                       ORDER BY CASE WHEN d.draft_id = l.draft_id THEN 0 ELSE 1 END,
                                d.start_time, d.draft_id
                   ) AS choice
            FROM drafts AS d
            JOIN ready USING (league_id, season)
            JOIN league_seasons AS l USING (league_id, season)
            WHERE d.status = 'complete' AND d.draft_type = 'snake'
              AND d.team_count = l.total_rosters AND d.rounds > 0
              AND (SELECT COUNT(*) FROM draft_picks AS p WHERE p.draft_id = d.draft_id)
                  = d.team_count * d.rounds
              AND NOT EXISTS (
                  SELECT 1 FROM draft_picks AS p
                  WHERE p.draft_id = d.draft_id AND COALESCE(p.is_keeper, 0) = 1
              )
        )
        SELECT d.draft_id, d.league_id, d.season, d.team_count, d.rounds,
               d.draft_type, d.settings_json, d.start_time,
               l.scoring_format, l.scoring_settings_json, l.roster_positions_json
        FROM eligible_drafts AS d
        JOIN league_seasons AS l
          ON l.league_id = d.league_id AND l.season = d.season
        WHERE d.choice = 1
        ORDER BY d.season, d.league_id, d.draft_id
        """
    )
    while targets := cursor.fetchmany(batch_size):
        for target in targets:
            picks = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT pick_no, round, draft_slot, effective_roster_id, player_id,
                           position, picked_at_ms
                    FROM draft_picks WHERE draft_id = ? ORDER BY pick_no
                    """,
                    (target["draft_id"],),
                )
            ]
            roster_rows = list(
                connection.execute(
                    """
                    SELECT roster_id, owner_id FROM rosters
                    WHERE league_id = ? AND season = ? ORDER BY roster_id
                    """,
                    (target["league_id"], target["season"]),
                )
            )
            labels = labels_for_league(connection, target["league_id"], target["season"])
            base_reasons = []
            roster_ids = {row["roster_id"] for row in roster_rows}
            drafted_rosters = {
                pick["effective_roster_id"]
                for pick in picks
                if pick["effective_roster_id"] is not None
            }
            if roster_ids - drafted_rosters:
                base_reasons.append("missing_team_picks")
            board = _load_market_board(market_connection, target["draft_id"])
            board_by_player = {row["player_id"]: row for row in board["players"]}
            roster_positions = json.loads(target["roster_positions_json"])
            settings = json.loads(target["settings_json"])
            geometry = "third_round_reversal" if settings.get("reversal_round") else target["draft_type"]
            for roster in roster_rows:
                team_picks = [
                    pick for pick in picks if pick["effective_roster_id"] == roster["roster_id"]
                ]
                positions = [pick["position"] or "UNKNOWN" for pick in team_picks]
                rounds = [int(pick["round"]) for pick in team_picks]
                coverage = starter_coverage(positions, roster_positions)
                market_rows = [board_by_player.get(pick["player_id"]) for pick in team_picks]
                market_values = [
                    round(market["adp"] - pick["pick_no"], 6) if market else None
                    for pick, market in zip(team_picks, market_rows)
                ]
                label = labels.get(roster["roster_id"], {})
                reasons = list(base_reasons)
                if not label:
                    reasons.append("missing_labels")
                elif label["champion_count"] != 1:
                    reasons.append("incomplete_championship_label")
                yield {
                    "team_table_version": TEAM_TABLE_VERSION,
                    "league_id": target["league_id"],
                    "season": target["season"],
                    "draft_id": target["draft_id"],
                    "roster_id": roster["roster_id"],
                    "owner_id": roster["owner_id"],
                    "draft_slot": min((pick["draft_slot"] for pick in team_picks), default=None),
                    "draft_geometry": geometry,
                    "draft_type": target["draft_type"],
                    "round_count": target["rounds"],
                    "team_count": target["team_count"],
                    "scoring_format": target["scoring_format"],
                    "scoring_settings_hash": hashlib.sha256(
                        target["scoring_settings_json"].encode()
                    ).hexdigest(),
                    "roster_positions_json": canonical_json(roster_positions),
                    "position_sequence_json": canonical_json(positions),
                    "pick_player_ids_json": canonical_json([pick["player_id"] for pick in team_picks]),
                    "pick_numbers_json": canonical_json([pick["pick_no"] for pick in team_picks]),
                    "pick_rounds_json": canonical_json(rounds),
                    "first_qb_round": _first_round(positions, rounds, "QB"),
                    "first_rb_round": _first_round(positions, rounds, "RB"),
                    "first_wr_round": _first_round(positions, rounds, "WR"),
                    "first_te_round": _first_round(positions, rounds, "TE"),
                    "position_counts_r3_json": canonical_json(_counts_through(positions, rounds, 3)),
                    "position_counts_r5_json": canonical_json(_counts_through(positions, rounds, 5)),
                    "position_counts_r8_json": canonical_json(_counts_through(positions, rounds, 8)),
                    "position_counts_json": canonical_json(dict(sorted(Counter(positions).items()))),
                    "starter_slots": coverage["starter_slots"],
                    "starter_covered": coverage["starter_covered"],
                    "flex_slots": coverage["flex_slots"],
                    "flex_covered": coverage["flex_covered"],
                    "bench_structure_json": canonical_json(coverage["bench_structure"]),
                    "market_rank_by_pick_json": canonical_json([
                        market["rank"] if market else None for market in market_rows
                    ]),
                    "market_adp_by_pick_json": canonical_json([
                        market["adp"] if market else None for market in market_rows
                    ]),
                    "market_value_by_pick_json": canonical_json(market_values),
                    "cumulative_market_value": round(sum(value for value in market_values if value is not None), 6),
                    "market_support_drafts": board["provenance"]["source_draft_count"],
                    "market_cutoff_ms": board["provenance"]["cutoff_ms"],
                    "market_provenance_hash": hashlib.sha256(
                        canonical_json(board["provenance"]).encode()
                    ).hexdigest(),
                    "source_manifest_hash": source_manifest_hash,
                    "feature_manifest_hash": feature_manifest_hash,
                    "feature_version": FEATURE_VERSION,
                    "label_version": LABEL_VERSION,
                    "points_for_percentile": label.get("points_for_percentile"),
                    "regular_season_win_percentage": label.get("regular_season_win_percentage"),
                    "made_playoffs": label.get("made_playoffs"),
                    "champion": label.get("champion"),
                    "training_eligible": not reasons,
                    "exclusion_reasons_json": canonical_json(sorted(set(reasons))),
                }


def iter_prefix_rows(connection, market_connection, team_rows):
    for draft_id, draft_teams in groupby(team_rows, key=lambda row: row["draft_id"]):
        teams = list(draft_teams)
        board = _load_market_board(market_connection, draft_id)
        all_picks = _draft_picks(connection, draft_id)
        for team in teams:
            own_picks = [
                pick
                for pick in all_picks
                if pick["effective_roster_id"] == team["roster_id"]
            ]
            for own_index in range(len(own_picks)):
                yield _prefix_row(team, board, all_picks, own_picks, own_index)


def iter_sampled_team_prefixes(
    connection,
    market_connection,
    team_rows,
    *,
    seed,
    epoch,
):
    team_index = 0
    for draft_id, draft_teams in groupby(team_rows, key=lambda row: row["draft_id"]):
        teams = list(draft_teams)
        board = _load_market_board(market_connection, draft_id)
        all_picks = _draft_picks(connection, draft_id)
        for team in teams:
            if not team["training_eligible"]:
                continue
            own_picks = [
                pick
                for pick in all_picks
                if pick["effective_roster_id"] == team["roster_id"]
            ]
            if not own_picks:
                raise ValueError(f"team has no prefixes: {team['league_id']}:{team['roster_id']}")
            team_key = f"{team['season']}:{team['league_id']}:{team['roster_id']}"
            digest = hashlib.sha256(f"{seed}:{epoch}:{team_key}".encode()).digest()
            desired = _desired_bucket(team_index, seed, epoch)
            candidates = [
                index
                for index, pick in enumerate(own_picks)
                if prefix_bucket(pick["round"], team["round_count"]) == desired
            ] or list(range(len(own_picks)))
            choice = candidates[int.from_bytes(digest[1:9], "big") % len(candidates)]
            team_index += 1
            yield {
                **_prefix_row(team, board, all_picks, own_picks, choice),
                "sampled_bucket": desired,
            }


def _draft_picks(connection, draft_id):
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT pick_no, round, effective_roster_id, player_id, position
            FROM draft_picks WHERE draft_id = ? ORDER BY pick_no
            """,
            (draft_id,),
        )
    ]


def _prefix_row(team, board, all_picks, own_picks, own_index):
    prefix_pick = own_picks[own_index]
    observed = [
        pick for pick in all_picks if pick["pick_no"] <= prefix_pick["pick_no"]
    ]
    observed_ids = {pick["player_id"] for pick in observed}
    available = [
        player
        for player in board["players"]
        if player["player_id"] not in observed_ids
    ]
    available_by_position = Counter(
        player["position"] or "UNKNOWN" for player in available
    )
    available_by_tier = Counter(
        str((player["rank"] - 1) // team["team_count"] + 1)
        for player in available
    )
    best_rank = {}
    for player in available:
        position = player["position"] or "UNKNOWN"
        best_rank.setdefault(position, player["rank"])
    recent = observed[-team["team_count"]:]
    next_pick = (
        own_picks[own_index + 1]["pick_no"]
        if own_index + 1 < len(own_picks)
        else None
    )
    current_positions = [
        pick["position"] or "UNKNOWN" for pick in own_picks[:own_index + 1]
    ]
    return {
        "prefix_version": PREFIX_VERSION,
        "league_season_id": f"{team['season']}:{team['league_id']}",
        "league_id": team["league_id"],
        "season": team["season"],
        "draft_id": team["draft_id"],
        "roster_id": team["roster_id"],
        "owner_id": team["owner_id"],
        "team_count": team["team_count"],
        "scoring_format": team["scoring_format"],
        "draft_slot": team["draft_slot"],
        "prefix_round": prefix_pick["round"],
        "prefix_pick_no": prefix_pick["pick_no"],
        "prefix_bucket": prefix_bucket(prefix_pick["round"], team["round_count"]),
        "observed_picks_json": canonical_json(observed),
        "current_roster_json": canonical_json(current_positions),
        "position_counts_json": canonical_json(
            dict(sorted(Counter(current_positions).items()))
        ),
        "remaining_picks": len(own_picks) - own_index - 1,
        "next_user_pick": next_pick,
        "available_by_position_json": canonical_json(
            dict(sorted(available_by_position.items()))
        ),
        "available_by_tier_json": canonical_json(
            dict(sorted(available_by_tier.items()))
        ),
        "best_rank_by_position_json": canonical_json(dict(sorted(best_rank.items()))),
        "tier_boundary_distance_json": canonical_json(
            _tier_boundaries(available, team["team_count"])
        ),
        "recent_position_runs_json": canonical_json(
            dict(sorted(Counter(
                pick["position"] or "UNKNOWN" for pick in recent
            ).items()))
        ),
        "market_support_drafts": board["provenance"]["source_draft_count"],
        "market_cutoff_ms": board["provenance"]["cutoff_ms"],
        "points_for_percentile": team["points_for_percentile"],
        "regular_season_win_percentage": team["regular_season_win_percentage"],
        "made_playoffs": team["made_playoffs"],
        "champion": team["champion"],
        "prefix_weight": 1.0,
        "prefix_sampling_method": "one_per_team_per_epoch_balanced_thirds",
        "feature_version": team["feature_version"],
        "source_manifest_hash": team["source_manifest_hash"],
        "label_version": team["label_version"],
        "training_eligible": team["training_eligible"],
    }


def prefix_bucket(round_number, total_rounds):
    position = (int(round_number) - 1) / max(int(total_rounds), 1)
    return ("early", "middle", "late")[min(int(position * 3), 2)]


def sample_prefix_for_team(prefixes, *, seed, epoch, desired_bucket=None):
    prefixes = list(prefixes)
    if not prefixes:
        raise ValueError("team has no prefixes")
    team_key = (
        prefixes[0]["league_season_id"],
        prefixes[0]["roster_id"],
    )
    if any((row["league_season_id"], row["roster_id"]) != team_key for row in prefixes):
        raise ValueError("prefix sample contains multiple teams")
    digest = hashlib.sha256(f"{seed}:{epoch}:{team_key[0]}:{team_key[1]}".encode()).digest()
    desired = desired_bucket or ("early", "middle", "late")[digest[0] % 3]
    candidates = [row for row in prefixes if row["prefix_bucket"] == desired] or prefixes
    choice = int.from_bytes(digest[1:9], "big") % len(candidates)
    return {**candidates[choice], "prefix_weight": 1.0, "sampled_bucket": desired}


def iter_sampled_prefixes(prefix_rows, *, seed, epoch):
    key = lambda row: (row["league_season_id"], row["roster_id"])
    for index, (_, rows) in enumerate(groupby(prefix_rows, key=key)):
        yield sample_prefix_for_team(
            rows,
            seed=seed,
            epoch=epoch,
            desired_bucket=_desired_bucket(index, seed, epoch),
        )


def _desired_bucket(index, seed, epoch):
    offset = hashlib.sha256(f"{seed}:{epoch}".encode()).digest()[0] % 3
    return ("early", "middle", "late")[(index + offset) % 3]


def starter_coverage(positions, roster_slots):
    remaining = Counter(positions)
    starter_slots = [slot for slot in roster_slots if slot not in BENCH_SLOTS]
    matched = []
    for slot in starter_slots:
        if slot in FLEX_ELIGIBILITY:
            continue
        normalized = "DEF" if slot in {"DST", "D/ST"} else slot
        if remaining[normalized] > 0:
            remaining[normalized] -= 1
            matched.append(slot)
    for slot in ("REC_FLEX", "WRRB_FLEX", "FLEX", "SUPER_FLEX"):
        for _ in range(starter_slots.count(slot)):
            eligible = FLEX_ELIGIBILITY[slot]
            choice = max(eligible, key=lambda position: (remaining[position], position))
            if remaining[choice] > 0:
                remaining[choice] -= 1
                matched.append(slot)
    flex_slots = sum(slot in FLEX_ELIGIBILITY for slot in starter_slots)
    return {
        "starter_slots": len(starter_slots),
        "starter_covered": len(matched),
        "flex_slots": flex_slots,
        "flex_covered": sum(slot in FLEX_ELIGIBILITY for slot in matched),
        "bench_structure": dict(sorted((key, value) for key, value in remaining.items() if value)),
    }


def _first_round(positions, rounds, position):
    return next((round_ for value, round_ in zip(positions, rounds) if value == position), None)


def _counts_through(positions, rounds, cutoff):
    return dict(sorted(Counter(
        position for position, round_ in zip(positions, rounds) if round_ <= cutoff
    ).items()))


def _tier_boundaries(available, team_count):
    result = {}
    for player in available:
        position = player["position"] or "UNKNOWN"
        result.setdefault(position, team_count - ((player["rank"] - 1) % team_count))
    return dict(sorted(result.items()))


def _load_market_board(connection, target_draft_id):
    board = connection.execute(
        "SELECT * FROM boards WHERE target_draft_id = ?",
        (target_draft_id,),
    ).fetchone()
    if board is None:
        raise ValueError(f"market board missing for target draft {target_draft_id}")
    players = [
        dict(row)
        for row in connection.execute(
            """
            SELECT player_id, position, rank, adp, dispersion,
                   observation_count, support_draft_count
            FROM players WHERE target_draft_id = ? ORDER BY rank, player_id
            """,
            (target_draft_id,),
        )
    ]
    return {
        "provenance": {
            "market_version": "hdvn-rolling-market-v1",
            "target_draft_id": target_draft_id,
            "cutoff_ms": board["cutoff_ms"],
            "max_source_completed_ms": board["max_source_completed_ms"],
            "context": {
                "season": board["season"],
                "scoring_format": board["scoring_format"],
                "team_count": board["team_count"],
                "draft_type": board["draft_type"],
                "draft_range": board["draft_range"],
            },
            "source_draft_count": board["source_draft_count"],
            "source_draft_ids_sha256": board["source_draft_identity_hash"],
            "sparse_context": bool(board["sparse_context"]),
            "sparse_behavior": "unavailable_without_fallback",
        },
        "players": players,
    }


def write_parquet_rows(rows, path, *, batch_size=10_000, table_name=None):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Parquet output requires pyarrow") from error
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    iterator = iter(rows)
    first = []
    for _ in range(batch_size):
        try:
            first.append(next(iterator))
        except StopIteration:
            break
    if not first:
        raise ValueError("cannot write an empty Parquet table")
    if table_name is not None:
        validate_materialized_columns(
            table_name,
            first[0],
            feature_manifest_eligible_columns(table_name),
        )
    table = pa.Table.from_pylist(first)
    writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
    try:
        writer.write_table(table)
        while True:
            batch = []
            for _ in range(batch_size):
                try:
                    batch.append(next(iterator))
                except StopIteration:
                    break
            if not batch:
                break
            if table_name is not None and any(row.keys() != first[0].keys() for row in batch):
                raise ValueError(f"inconsistent {table_name} materialized columns")
            writer.write_table(pa.Table.from_pylist(batch, schema=table.schema))
    except BaseException:
        writer.close()
        temporary.unlink(missing_ok=True)
        raise
    writer.close()
    os.replace(temporary, path)
    return path


def feature_manifest_eligible_columns(table_name):
    contract = MATERIALIZED_COLUMN_FEATURES[table_name]
    from .hdvn_contract import FEATURE_BY_NAME

    return [
        column
        for column, feature_name in contract.items()
        if FEATURE_BY_NAME[feature_name]["model_eligible"]
    ]


def materialize_training_tables(
    snapshot_database,
    market_database,
    output_directory,
    *,
    source_snapshot_hash,
    source_manifest_hash,
    feature_manifest_hash,
    market_manifest_hash,
    command,
    seed=20260828,
    epoch=0,
    batch_size=10_000,
):
    snapshot_database = Path(snapshot_database).resolve()
    market_database = Path(market_database).resolve()
    output_directory = Path(output_directory).resolve()
    team_path = output_directory / "team-v1.parquet"
    prefix_path = output_directory / "prefix-v1.parquet"
    manifest_path = output_directory / "tables-v1.manifest.json"
    paths = (team_path, prefix_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable table output already exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(
        f"file:{snapshot_database.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    source.row_factory = sqlite3.Row
    market = sqlite3.connect(
        f"file:{market_database.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    market.row_factory = sqlite3.Row
    try:
        write_parquet_rows(
            iter_team_rows(
                source,
                market,
                source_manifest_hash,
                feature_manifest_hash,
            ),
            team_path,
            batch_size=batch_size,
            table_name="team",
        )
        write_parquet_rows(
            iter_sampled_team_prefixes(
                source,
                market,
                _iter_parquet_rows(team_path, batch_size),
                seed=seed,
                epoch=epoch,
            ),
            prefix_path,
            batch_size=batch_size,
            table_name="prefix",
        )
        exclusions = _hydration_exclusion_counts(source)
    except BaseException:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        market.close()
        source.close()

    try:
        team_summary = _parquet_summary(team_path, "team", batch_size)
        prefix_summary = _parquet_summary(prefix_path, "prefix", batch_size)
        if team_summary["training_eligible_rows"] != prefix_summary["rows"]:
            raise ValueError("sampled prefix count does not equal eligible team count")
        if prefix_summary["total_weight"] != float(team_summary["training_eligible_rows"]):
            raise ValueError("sampled prefix team weight is not constant")
        buckets = prefix_summary["prefix_buckets"]
        if set(buckets) != {"early", "middle", "late"}:
            raise ValueError("sampled prefixes do not cover all buckets")
        if max(buckets.values()) - min(buckets.values()) > max(1, team_summary["rows"] * 0.02):
            raise ValueError("sampled prefix buckets are not balanced")
        manifest = {
            "manifest_version": 1,
            "team_table_version": TEAM_TABLE_VERSION,
            "prefix_table_version": PREFIX_VERSION,
            "source_snapshot_sha256": source_snapshot_hash,
            "source_manifest_sha256": source_manifest_hash,
            "feature_manifest_hash": feature_manifest_hash,
            "label_version": LABEL_VERSION,
            "market_manifest_hash": market_manifest_hash,
            "command": command,
            "sampling": {
                "method": "one_per_team_per_epoch_balanced_thirds",
                "seed": seed,
                "epoch": epoch,
                "total_team_weight": prefix_summary["total_weight"],
                "prefix_buckets": buckets,
                "inverse_prefix_weighting": "named_benchmark_only_not_materialized",
            },
            "files": {
                team_path.name: {
                    "bytes": team_path.stat().st_size,
                    "sha256": sha256_file(team_path),
                    **team_summary,
                },
                prefix_path.name: {
                    "bytes": prefix_path.stat().st_size,
                    "sha256": sha256_file(prefix_path),
                    **prefix_summary,
                },
            },
            "hydration_cohort_exclusions": exclusions,
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


def _iter_parquet_rows(path, batch_size):
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Parquet output requires pyarrow") from error
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=batch_size):
        yield from batch.to_pylist()


def _parquet_summary(path, table_name, batch_size):
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Parquet output requires pyarrow") from error
    parquet = pq.ParquetFile(path)
    digest = hashlib.sha256()
    contexts = Counter()
    exclusions = Counter()
    buckets = Counter()
    total_weight = 0.0
    champion_events = 0
    market_supported = 0
    training_eligible_rows = 0
    last_key = None
    rows = 0
    for row in _iter_parquet_rows(path, batch_size):
        rows += 1
        digest.update(canonical_json(row).encode())
        digest.update(b"\n")
        key = (int(row["season"]), row["league_id"], int(row["roster_id"]))
        if last_key is not None and key <= last_key:
            raise ValueError(f"{table_name} rows are duplicated or unsorted")
        last_key = key
        contexts[
            (
                int(row["season"]),
                row["scoring_format"],
                int(row["team_count"]),
                int(row["draft_slot"]) if row["draft_slot"] is not None else 0,
            )
        ] += 1
        champion_events += int(row["champion"] or 0)
        training_eligible_rows += int(row["training_eligible"])
        if table_name == "team":
            for reason in json.loads(row["exclusion_reasons_json"]):
                exclusions[reason] += 1
            if any(
                value is not None
                for value in json.loads(row["market_rank_by_pick_json"])
            ):
                market_supported += 1
        else:
            buckets[row["prefix_bucket"]] += 1
            total_weight += float(row["prefix_weight"])
            if row["market_support_drafts"] >= 25:
                market_supported += 1
    return {
        "rows": rows,
        "training_eligible_rows": training_eligible_rows,
        "schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in parquet.schema_arrow
        ],
        "row_equivalence_sha256": digest.hexdigest(),
        "context_counts": [
            {
                "season": key[0],
                "scoring_format": key[1],
                "team_count": key[2],
                "draft_slot": key[3],
                "rows": count,
            }
            for key, count in sorted(contexts.items())
        ],
        "exclusion_counts": dict(sorted(exclusions.items())),
        "champion_events": champion_events,
        "market_supported_rows": market_supported,
        "prefix_buckets": dict(sorted(buckets.items())),
        "total_weight": total_weight,
    }


def _hydration_exclusion_counts(connection):
    counts = Counter()
    ready = {
        (row["league_id"], int(row["season"]))
        for row in connection.execute(
            TRAINING_READY_CTE + "SELECT league_id, season FROM ready"
        )
    }
    rows = connection.execute(
        """
        SELECT h.league_id, h.season,
               (SELECT d.draft_id FROM drafts AS d
                WHERE d.league_id = h.league_id AND d.season = h.season
                ORDER BY CASE WHEN d.draft_id = l.draft_id THEN 0 ELSE 1 END,
                         d.start_time, d.draft_id
                LIMIT 1) AS draft_id
        FROM hydration_queue AS h
        LEFT JOIN league_seasons AS l USING (league_id, season)
        ORDER BY h.season, h.league_id
        """
    )
    league_seasons = 0
    included = 0
    for row in rows:
        league_seasons += 1
        reasons = training_exclusion_reasons(
            connection,
            row["league_id"],
            row["season"],
            row["draft_id"],
        )
        if not reasons and (row["league_id"], int(row["season"])) not in ready:
            reasons = ["not_strict_ready"]
        if reasons:
            for reason in reasons:
                counts[reason] += 1
        else:
            included += 1
    return {
        "scope": "hydration_queue_league_seasons",
        "league_seasons": league_seasons,
        "included": included,
        "by_reason": dict(sorted(counts.items())),
    }


def derive_strategy_labels(team_row, *, version="hdvn-strategy-v1"):
    """Return optional, versioned strategy labels outside the canonical table."""
    counts_r5 = json.loads(team_row["position_counts_r5_json"])
    return {
        "strategy_version": version,
        "zero_rb_through_round_5": counts_r5.get("RB", 0) == 0,
        "early_qb": team_row["first_qb_round"] is not None and team_row["first_qb_round"] <= 3,
    }
