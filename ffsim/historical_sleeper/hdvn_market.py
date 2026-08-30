import hashlib
import math
import json
import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path

from .hdvn_contract import MARKET_VERSION
from .hdvn_snapshot import canonical_json


@dataclass(frozen=True)
class MarketContext:
    season: int
    scoring_format: str
    team_count: int
    draft_range: str


@dataclass
class _Moments:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value):
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    def remove(self, value):
        if self.count < 1:
            raise ValueError("cannot remove from empty moments")
        if self.count == 1:
            self.count = 0
            self.mean = 0.0
            self.m2 = 0.0
            return
        old_mean = self.mean
        new_count = self.count - 1
        new_mean = (self.count * old_mean - value) / new_count
        self.m2 -= (value - old_mean) * (value - new_mean)
        self.count = new_count
        self.mean = new_mean

    @property
    def dispersion(self):
        return math.sqrt(self.m2 / (self.count - 1)) if self.count > 1 else None


def milliseconds(value):
    if value is None:
        return None
    value = int(value)
    return value * 1000 if value < 100_000_000_000 else value


def draft_range(start_ms):
    moment = datetime.fromtimestamp(milliseconds(start_ms) / 1000, timezone.utc)
    if (moment.month, moment.day) < (8, 1):
        return "early"
    if (moment.month, moment.day) < (9, 8):
        return "main"
    return "late"


def _range_bounds(season, name):
    start_year = int(season)
    if name == "early":
        return 0, int(datetime(start_year, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
    if name == "main":
        return (
            int(datetime(start_year, 8, 1, tzinfo=timezone.utc).timestamp() * 1000),
            int(datetime(start_year, 9, 8, tzinfo=timezone.utc).timestamp() * 1000),
        )
    return int(datetime(start_year, 9, 8, tzinfo=timezone.utc).timestamp() * 1000), 9_999_999_999_999


def build_market_board(connection, target_draft_id, *, min_support_drafts=1):
    """Build an exact-context board using only drafts completed before the target."""
    if min_support_drafts < 1:
        raise ValueError("minimum support must be positive")
    target = connection.execute(
        """
        SELECT d.draft_id, d.season, d.team_count, d.start_time, d.draft_type,
               l.scoring_format
        FROM drafts AS d
        JOIN league_seasons AS l
          ON l.league_id = d.league_id AND l.season = d.season
        WHERE d.draft_id = ?
        """,
        (target_draft_id,),
    ).fetchone()
    if target is None:
        raise ValueError(f"unknown target draft {target_draft_id}")
    cutoff_ms = milliseconds(target["start_time"])
    if cutoff_ms is None:
        raise ValueError(f"target draft start time missing: {target_draft_id}")
    context = MarketContext(
        int(target["season"]),
        target["scoring_format"],
        int(target["team_count"]),
        draft_range(cutoff_ms),
    )
    lower_ms, upper_ms = _range_bounds(context.season, context.draft_range)
    source_rows = connection.execute(
        """
        SELECT d.draft_id,
               COALESCE(d.last_picked_ms, (
                   SELECT MAX(p.picked_at_ms) FROM draft_picks AS p
                   WHERE p.draft_id = d.draft_id
               )) AS completed_at_ms
        FROM drafts AS d
        JOIN league_seasons AS l
          ON l.league_id = d.league_id AND l.season = d.season
        WHERE d.draft_id <> ?
          AND d.season = ?
          AND d.team_count = ?
          AND d.draft_type = ?
          AND d.status = 'complete'
          AND l.scoring_format = ?
          AND CASE WHEN d.start_time < 100000000000
                   THEN d.start_time * 1000 ELSE d.start_time END >= ?
          AND CASE WHEN d.start_time < 100000000000
                   THEN d.start_time * 1000 ELSE d.start_time END < ?
        ORDER BY d.draft_id
        """,
        (
            target_draft_id,
            context.season,
            context.team_count,
            target["draft_type"],
            context.scoring_format,
            lower_ms,
            upper_ms,
        ),
    )
    source_drafts = []
    max_completed_ms = None
    for row in source_rows:
        completed_ms = milliseconds(row["completed_at_ms"])
        if completed_ms is None or completed_ms >= cutoff_ms:
            continue
        source_drafts.append(row["draft_id"])
        max_completed_ms = max(max_completed_ms or completed_ms, completed_ms)

    source_drafts.sort()
    provenance = {
        "market_version": MARKET_VERSION,
        "target_draft_id": target_draft_id,
        "cutoff_ms": cutoff_ms,
        "max_source_completed_ms": max_completed_ms,
        "context": context.__dict__,
        "source_draft_count": len(source_drafts),
        "source_draft_ids_sha256": hashlib.sha256(
            canonical_json(source_drafts).encode()
        ).hexdigest(),
        "sparse_context": len(source_drafts) < min_support_drafts,
        "sparse_behavior": "unavailable_without_fallback",
    }
    if len(source_drafts) < min_support_drafts:
        return {"provenance": provenance, "players": []}

    moments = {}
    positions = {}
    support_drafts = Counter()
    for source_draft_id in source_drafts:
        seen_players = set()
        for pick in connection.execute(
            """
            SELECT player_id, pick_no, position
            FROM draft_picks
            WHERE draft_id = ? AND player_id IS NOT NULL AND COALESCE(is_keeper, 0) = 0
            ORDER BY pick_no
            """,
            (source_draft_id,),
        ):
            player_id = pick["player_id"]
            moments.setdefault(player_id, _Moments()).add(float(pick["pick_no"]))
            if player_id not in seen_players:
                support_drafts[player_id] += 1
                seen_players.add(player_id)
            if pick["position"]:
                positions.setdefault(player_id, pick["position"])

    ordered = sorted(moments, key=lambda player_id: (moments[player_id].mean, player_id))
    players = [
        {
            "player_id": player_id,
            "position": positions.get(player_id),
            "rank": rank,
            "support_draft_count": support_drafts[player_id],
            "adp": round(moments[player_id].mean, 6),
            "dispersion": (
                round(moments[player_id].dispersion, 6)
                if moments[player_id].dispersion is not None else None
            ),
            "observation_count": moments[player_id].count,
        }
        for rank, player_id in enumerate(ordered, 1)
    ]
    board = {"provenance": provenance, "players": players}
    assert_board_temporal_integrity(board)
    return board


def assert_board_temporal_integrity(board):
    provenance = board["provenance"]
    completed = provenance["max_source_completed_ms"]
    if completed is not None and completed >= provenance["cutoff_ms"]:
        raise ValueError("market board contains a target or later draft")
    if provenance["target_draft_id"] is None:
        raise ValueError("market board target missing")
    return True


def market_only_pick(board, available_player_ids):
    available = set(available_player_ids)
    for player in board["players"]:
        if player["player_id"] in available:
            return player
    return None


@dataclass
class _RollingContext:
    moments: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)
    support_drafts: Counter = field(default_factory=Counter)
    source_draft_ids: list = field(default_factory=list)
    source_completed_ms: dict = field(default_factory=dict)
    target_picks: dict = field(default_factory=dict)

    def add(self, draft_id, completed_ms, picks, *, retain_target=False):
        self.source_draft_ids.append(draft_id)
        self.source_completed_ms[draft_id] = completed_ms
        if retain_target:
            self.target_picks[draft_id] = picks
        self._add_picks(picks)

    def board(self, target, min_support_drafts):
        target_id = target["draft_id"]
        excluded = self.target_picks.get(target_id)
        if target_id in self.source_completed_ms and excluded is None:
            raise ValueError("target draft contribution is unavailable for exclusion")
        if excluded is not None:
            self._remove_picks(excluded)
        try:
            source_ids = [
                draft_id for draft_id in self.source_draft_ids if draft_id != target_id
            ]
            support = len(source_ids)
            max_completed_ms = max(
                (self.source_completed_ms[draft_id] for draft_id in source_ids),
                default=None,
            )
            provenance = {
                "market_version": MARKET_VERSION,
                "target_draft_id": target_id,
                "cutoff_ms": target["start_ms"],
                "max_source_completed_ms": max_completed_ms,
                "context": {
                    "season": target["season"],
                    "scoring_format": target["scoring_format"],
                    "team_count": target["team_count"],
                    "draft_type": target["draft_type"],
                    "draft_range": target["draft_range"],
                },
                "source_draft_count": support,
                "source_draft_ids_sha256": hashlib.sha256(
                    canonical_json(source_ids).encode()
                ).hexdigest(),
                "sparse_context": support < min_support_drafts,
                "sparse_behavior": "unavailable_without_fallback",
            }
            if support < min_support_drafts:
                return {"provenance": provenance, "players": []}
            ordered = sorted(
                (
                    player_id
                    for player_id, moments in self.moments.items()
                    if moments.count
                ),
                key=lambda player_id: (self.moments[player_id].mean, player_id),
            )
            return {
                "provenance": provenance,
                "players": [
                    {
                        "player_id": player_id,
                        "position": self.positions.get(player_id),
                        "rank": rank,
                        "adp": round(self.moments[player_id].mean, 6),
                        "dispersion": (
                            round(self.moments[player_id].dispersion, 6)
                            if self.moments[player_id].dispersion is not None
                            else None
                        ),
                        "observation_count": self.moments[player_id].count,
                        "support_draft_count": self.support_drafts[player_id],
                    }
                    for rank, player_id in enumerate(ordered, 1)
                ],
            }
        finally:
            if excluded is not None:
                self._add_picks(excluded)

    def _add_picks(self, picks):
        seen_players = set()
        for pick in picks:
            player_id = pick["player_id"]
            if player_id is None:
                continue
            self.moments.setdefault(player_id, _Moments()).add(float(pick["pick_no"]))
            if player_id not in seen_players:
                self.support_drafts[player_id] += 1
                seen_players.add(player_id)
            if pick["position"]:
                self.positions.setdefault(player_id, pick["position"])

    def _remove_picks(self, picks):
        seen_players = set()
        for pick in picks:
            player_id = pick["player_id"]
            if player_id is None:
                continue
            self.moments[player_id].remove(float(pick["pick_no"]))
            if player_id not in seen_players:
                self.support_drafts[player_id] -= 1
                seen_players.add(player_id)


def materialize_rolling_markets(
    snapshot_database,
    output_directory,
    *,
    source_snapshot_hash,
    feature_manifest_hash,
    command,
    min_support_drafts=25,
):
    """Build every target board in one chronological pass over source drafts."""
    if min_support_drafts < 1:
        raise ValueError("minimum support must be positive")
    snapshot_database = Path(snapshot_database).resolve()
    output_directory = Path(output_directory).resolve()
    database_path = output_directory / "market-v1.sqlite3"
    report_path = output_directory / "market-v1.report.json"
    manifest_path = output_directory / "market-v1.manifest.json"
    paths = (database_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable market output already exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    temporary = database_path.with_suffix(".sqlite3.tmp")
    if temporary.exists():
        raise FileExistsError(f"stale market temporary file exists: {temporary}")

    source = sqlite3.connect(
        f"file:{snapshot_database.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    source.row_factory = sqlite3.Row
    destination = sqlite3.connect(temporary)
    destination.row_factory = sqlite3.Row
    try:
        _create_market_schema(destination)
        contexts = defaultdict(_RollingContext)
        targets = list(_iter_target_drafts(source))
        target_starts = {target["draft_id"]: target["start_ms"] for target in targets}
        source_drafts = iter(_iter_source_drafts(source))
        next_source = next(source_drafts, None)
        coverage = Counter()
        context_rows = defaultdict(Counter)
        support_values = []
        staleness_values = []
        stability_values = []
        previous_ranks = {}
        temporal_violations = 0
        target_count = 0
        player_count = 0
        pick_count = 0

        for target in targets:
            target_count += 1
            while next_source is not None and next_source[0]["completed_ms"] < target["start_ms"]:
                metadata, picks = next_source
                contexts[_context_key(metadata)].add(
                    metadata["draft_id"],
                    metadata["completed_ms"],
                    picks,
                    retain_target=(
                        metadata["draft_id"] in target_starts
                        and metadata["completed_ms"]
                        < target_starts[metadata["draft_id"]]
                    ),
                )
                next_source = next(source_drafts, None)
            board = contexts[_context_key(target)].board(target, min_support_drafts)
            assert_board_temporal_integrity(board)
            provenance = board["provenance"]
            if provenance["max_source_completed_ms"] is not None:
                staleness_values.append(
                    provenance["cutoff_ms"] - provenance["max_source_completed_ms"]
                )
            if provenance["max_source_completed_ms"] is not None and (
                provenance["max_source_completed_ms"] >= provenance["cutoff_ms"]
            ):
                temporal_violations += 1
            support_values.append(provenance["source_draft_count"])
            context_label = canonical_json(provenance["context"])
            context_rows[context_label]["targets"] += 1
            if board["players"]:
                coverage["available"] += 1
                context_rows[context_label]["available"] += 1
            else:
                coverage["sparse"] += 1
                context_rows[context_label]["sparse"] += 1

            ranks = {row["player_id"]: row["rank"] for row in board["players"]}
            prior = previous_ranks.get(context_label)
            if prior is not None and ranks:
                shared = set(prior) & ranks.keys()
                if shared:
                    stability_values.append(
                        sum(abs(prior[player] - ranks[player]) for player in shared)
                        / len(shared)
                    )
            if ranks:
                previous_ranks[context_label] = ranks

            destination.execute(
                """
                INSERT INTO boards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target["draft_id"],
                    target["season"],
                    target["scoring_format"],
                    target["team_count"],
                    target["draft_type"],
                    target["draft_range"],
                    target["start_ms"],
                    provenance["max_source_completed_ms"],
                    provenance["source_draft_count"],
                    provenance["source_draft_ids_sha256"],
                    int(provenance["sparse_context"]),
                    len(board["players"]),
                ),
            )
            destination.executemany(
                "INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        target["draft_id"],
                        player["player_id"],
                        player["position"],
                        player["rank"],
                        player["adp"],
                        player["dispersion"],
                        player["observation_count"],
                        player["support_draft_count"],
                    )
                    for player in board["players"]
                ),
            )
            player_count += len(board["players"])
            board_by_player = {row["player_id"]: row for row in board["players"]}
            picks = source.execute(
                """
                SELECT pick_no, effective_roster_id, player_id
                FROM draft_picks WHERE draft_id = ? ORDER BY pick_no
                """,
                (target["draft_id"],),
            )
            market_pick_rows = []
            for pick in picks:
                market = board_by_player.get(pick["player_id"])
                market_pick_rows.append((
                    target["draft_id"],
                    pick["pick_no"],
                    pick["effective_roster_id"],
                    pick["player_id"],
                    market["rank"] if market else None,
                    market["adp"] if market else None,
                    round(market["adp"] - pick["pick_no"], 6) if market else None,
                    provenance["source_draft_count"],
                    provenance["source_draft_ids_sha256"],
                ))
            destination.executemany(
                "INSERT INTO market_picks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                market_pick_rows,
            )
            pick_count += len(market_pick_rows)
            if target_count % 100 == 0:
                destination.commit()
        destination.commit()
        if temporal_violations:
            raise ValueError("rolling market contains target or future drafts")

        report = {
            "market_version": MARKET_VERSION,
            "min_support_drafts": min_support_drafts,
            "coverage_by_year": _coverage_by_year(destination),
            "coverage_by_context": [
                {"context": json.loads(context), **dict(sorted(counts.items()))}
                for context, counts in sorted(context_rows.items())
            ],
            "sparse_and_missing_contexts": [
                {"context": json.loads(context), **dict(sorted(counts.items()))}
                for context, counts in sorted(context_rows.items())
                if counts["sparse"]
            ],
            "support_distribution": _distribution(support_values),
            "staleness_ms": _distribution(staleness_values),
            "rank_stability_mean_absolute_change": _distribution(stability_values),
            "source_draft_counts": {
                "targets": target_count,
                "available": coverage["available"],
                "sparse": coverage["sparse"],
            },
            "target_future_exclusion": {
                "violations": temporal_violations,
                "rule": "source completion must be strictly before target start; target draft excluded",
            },
            "bounded_generation": {
                "source_passes": 1,
                "target_history_queries": 0,
                "target_pick_queries": target_count,
                "context_accumulators": len(contexts),
            },
        }
        report_path.write_text(canonical_json(report) + "\n")
        destination.close()
        source.close()
        os.replace(temporary, database_path)
        table_hashes = {
            table: _table_hash(database_path, table, order)
            for table, order in (
                ("boards", "target_draft_id"),
                ("players", "target_draft_id, rank, player_id"),
                ("market_picks", "target_draft_id, pick_no"),
            )
        }
        manifest = {
            "manifest_version": 1,
            "market_version": MARKET_VERSION,
            "source_snapshot_sha256": source_snapshot_hash,
            "feature_manifest_hash": feature_manifest_hash,
            "min_support_drafts": min_support_drafts,
            "command": command,
            "rows": {
                "boards": target_count,
                "players": player_count,
                "market_picks": pick_count,
            },
            "files": {
                database_path.name: {
                    "bytes": database_path.stat().st_size,
                    "sha256": _sha256_file(database_path),
                },
                report_path.name: {
                    "bytes": report_path.stat().st_size,
                    "sha256": _sha256_file(report_path),
                },
            },
            "table_row_sha256": table_hashes,
        }
        manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
        manifest_path.write_text(canonical_json(manifest) + "\n")
        for path in paths:
            path.chmod(0o444)
        return manifest
    except BaseException:
        destination.close()
        source.close()
        database_path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise


def _context_key(row):
    return (
        int(row["season"]),
        row["scoring_format"],
        int(row["team_count"]),
        row["draft_type"],
        row["draft_range"],
    )


def _iter_source_drafts(connection):
    cursor = connection.execute(
        """
        WITH eligible AS (
            SELECT d.draft_id, d.season, d.team_count, d.draft_type, d.start_time,
                   l.scoring_format,
                   CASE
                     WHEN d.last_picked_ms IS NOT NULL AND d.last_picked_ms < 100000000000
                     THEN d.last_picked_ms * 1000
                     WHEN d.last_picked_ms IS NOT NULL THEN d.last_picked_ms
                     ELSE (SELECT MAX(CASE WHEN p.picked_at_ms < 100000000000
                                          THEN p.picked_at_ms * 1000 ELSE p.picked_at_ms END)
                           FROM draft_picks AS p WHERE p.draft_id = d.draft_id)
                   END AS completed_ms
            FROM drafts AS d
            JOIN league_seasons AS l
              ON l.league_id = d.league_id AND l.season = d.season
            WHERE d.status = 'complete' AND d.draft_type = 'snake'
              AND d.start_time IS NOT NULL
              AND l.is_candidate = 1
              AND d.team_count = l.total_rosters AND d.rounds > 0
              AND (SELECT COUNT(*) FROM draft_picks AS p WHERE p.draft_id = d.draft_id)
                  = d.team_count * d.rounds
              AND NOT EXISTS (
                  SELECT 1 FROM draft_picks AS p
                  WHERE p.draft_id = d.draft_id AND COALESCE(p.is_keeper, 0) = 1
              )
        )
        SELECT e.*, p.pick_no, p.player_id, p.position
        FROM eligible AS e
        JOIN draft_picks AS p USING (draft_id)
        WHERE e.completed_ms IS NOT NULL
        ORDER BY e.completed_ms, e.draft_id, p.pick_no
        """
    )
    for _, rows in groupby(cursor, key=lambda row: row["draft_id"]):
        rows = iter(rows)
        first = next(rows)
        start_ms = milliseconds(first["start_time"])
        metadata = {
            "draft_id": first["draft_id"],
            "season": int(first["season"]),
            "team_count": int(first["team_count"]),
            "draft_type": first["draft_type"],
            "scoring_format": first["scoring_format"],
            "draft_range": draft_range(start_ms),
            "completed_ms": int(first["completed_ms"]),
        }
        picks = [
            {
                "pick_no": first["pick_no"],
                "player_id": first["player_id"],
                "position": first["position"],
            },
            *(
                {
                    "pick_no": row["pick_no"],
                    "player_id": row["player_id"],
                    "position": row["position"],
                }
                for row in rows
            ),
        ]
        yield metadata, picks


def _iter_target_drafts(connection):
    from .hdvn_snapshot import TRAINING_READY_CTE

    cursor = connection.execute(
        TRAINING_READY_CTE
        + """
        , chosen AS (
            SELECT d.*, ROW_NUMBER() OVER (
                PARTITION BY d.league_id, d.season
                ORDER BY CASE WHEN d.draft_id = l.draft_id THEN 0 ELSE 1 END,
                         d.start_time, d.draft_id
            ) AS choice
            FROM drafts AS d
            JOIN ready USING (league_id, season)
            JOIN league_seasons AS l USING (league_id, season)
            WHERE d.status = 'complete' AND d.draft_type = 'snake'
              AND d.team_count = l.total_rosters
              AND (SELECT COUNT(*) FROM draft_picks AS p WHERE p.draft_id = d.draft_id)
                  = d.team_count * d.rounds
              AND NOT EXISTS (
                  SELECT 1 FROM draft_picks AS p
                  WHERE p.draft_id = d.draft_id AND COALESCE(p.is_keeper, 0) = 1
              )
        )
        SELECT c.draft_id, c.season, c.team_count, c.draft_type, c.start_time,
               l.scoring_format
        FROM chosen AS c
        JOIN league_seasons AS l USING (league_id, season)
        WHERE c.choice = 1 AND c.start_time IS NOT NULL
        ORDER BY CASE WHEN c.start_time < 100000000000
                      THEN c.start_time * 1000 ELSE c.start_time END,
                 c.draft_id
        """
    )
    for row in cursor:
        start_ms = milliseconds(row["start_time"])
        yield {
            "draft_id": row["draft_id"],
            "season": int(row["season"]),
            "team_count": int(row["team_count"]),
            "draft_type": row["draft_type"],
            "scoring_format": row["scoring_format"],
            "draft_range": draft_range(start_ms),
            "start_ms": start_ms,
        }


def _create_market_schema(connection):
    connection.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = FULL;
        CREATE TABLE boards (
            target_draft_id TEXT PRIMARY KEY,
            season INTEGER NOT NULL,
            scoring_format TEXT NOT NULL,
            team_count INTEGER NOT NULL,
            draft_type TEXT NOT NULL,
            draft_range TEXT NOT NULL,
            cutoff_ms INTEGER NOT NULL,
            max_source_completed_ms INTEGER,
            source_draft_count INTEGER NOT NULL,
            source_draft_identity_hash TEXT NOT NULL,
            sparse_context INTEGER NOT NULL,
            player_count INTEGER NOT NULL
        );
        CREATE TABLE players (
            target_draft_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            position TEXT,
            rank INTEGER NOT NULL,
            adp REAL NOT NULL,
            dispersion REAL,
            observation_count INTEGER NOT NULL,
            support_draft_count INTEGER NOT NULL,
            PRIMARY KEY (target_draft_id, player_id)
        ) WITHOUT ROWID;
        CREATE INDEX players_rank ON players(target_draft_id, rank);
        CREATE TABLE market_picks (
            target_draft_id TEXT NOT NULL,
            pick_no INTEGER NOT NULL,
            roster_id INTEGER,
            player_id TEXT,
            market_rank INTEGER,
            market_adp REAL,
            market_value REAL,
            market_support_drafts INTEGER NOT NULL,
            market_provenance_hash TEXT NOT NULL,
            PRIMARY KEY (target_draft_id, pick_no)
        ) WITHOUT ROWID;
        """
    )


def _coverage_by_year(connection):
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT season, COUNT(*) AS targets,
                   SUM(CASE WHEN sparse_context = 0 THEN 1 ELSE 0 END) AS available,
                   SUM(sparse_context) AS sparse
            FROM boards GROUP BY season ORDER BY season
            """
        )
    ]


def _distribution(values):
    values = sorted(float(value) for value in values)
    if not values:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}
    return {
        "count": len(values),
        "min": values[0],
        "p25": _percentile(values, 0.25),
        "median": _percentile(values, 0.5),
        "p75": _percentile(values, 0.75),
        "max": values[-1],
    }


def _percentile(values, probability):
    index = (len(values) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def _table_hash(database_path, table, order):
    digest = hashlib.sha256()
    connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            digest.update(canonical_json(dict(row)).encode())
            digest.update(b"\n")
    finally:
        connection.close()
    return digest.hexdigest()


def _sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
