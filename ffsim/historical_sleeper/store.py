import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .schema import SCHEMA, SCHEMA_VERSION


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_text(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.database_path = self.data_dir / "historical_sleeper.sqlite3"
        self.raw_dir = self.data_dir / "raw"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "UPDATE league_seasons SET previous_league_id = NULL "
                "WHERE previous_league_id = '0'"
            )
            connection.execute(
                """
                UPDATE crawl_queue
                SET status = 'done', completed_at = COALESCE(completed_at, ?),
                    claimed_at = NULL, last_error = 'ignored Sleeper zero ID sentinel'
                WHERE task_type = 'league' AND entity_id = '0'
                """,
                (utc_now(),),
            )

    @contextmanager
    def connect(self, *, immediate=False):
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        if immediate:
            connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def set_collection_targets(
        self,
        training_ready_target,
        candidate_buffer,
        min_training_ready_per_year,
    ):
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (
                    ("collection_training_ready_target", str(int(training_ready_target))),
                    ("collection_candidate_buffer", str(int(candidate_buffer))),
                    (
                        "collection_min_training_ready_per_year",
                        str(int(min_training_ready_per_year)),
                    ),
                ),
            )

    def save_raw(self, endpoint, payload, *, http_status=200):
        data = (json_text(payload) + "\n").encode()
        content_hash = hashlib.sha256(data).hexdigest()
        relative_path = Path("raw") / content_hash[:2] / f"{content_hash}.json.gz"
        destination = self.data_dir / relative_path
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            compressed = gzip.compress(data, compresslevel=6, mtime=0)
            descriptor, temporary = tempfile.mkstemp(dir=destination.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(compressed)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
        fetched_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO raw_objects (
                    content_hash, endpoint, relative_path, fetched_at, byte_count, http_status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (content_hash, endpoint, str(relative_path), fetched_at, len(data), http_status),
            )
            connection.execute(
                """
                INSERT INTO endpoint_cache(endpoint, content_hash, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    fetched_at = excluded.fetched_at
                """,
                (endpoint, content_hash, fetched_at),
            )
        return content_hash

    def cached_payload(self, endpoint):
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT raw_objects.relative_path, raw_objects.content_hash
                FROM endpoint_cache
                JOIN raw_objects USING (content_hash)
                WHERE endpoint_cache.endpoint = ?
                """,
                (endpoint,),
            ).fetchone()
        if row is None:
            return None
        with gzip.open(self.data_dir / row["relative_path"], "rt", encoding="utf-8") as stream:
            return json.load(stream), row["content_hash"]

    def cached_endpoints(self):
        with self.connect() as connection:
            return connection.execute(
                "SELECT endpoint, content_hash FROM endpoint_cache ORDER BY endpoint"
            ).fetchall()

    def add_user(self, user, raw_hash=None):
        user_id = str(user.get("user_id") or "")
        if not user_id:
            raise ValueError("Sleeper user is missing user_id")
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    user_id, username, display_name, avatar, is_bot, raw_hash,
                    first_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, users.username),
                    display_name = COALESCE(excluded.display_name, users.display_name),
                    avatar = COALESCE(excluded.avatar, users.avatar),
                    is_bot = COALESCE(excluded.is_bot, users.is_bot),
                    raw_hash = COALESCE(excluded.raw_hash, users.raw_hash),
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    _text(user.get("username")),
                    _text(user.get("display_name")),
                    _text(user.get("avatar")),
                    _bool_int(user.get("is_bot")),
                    raw_hash,
                    now,
                    now,
                ),
            )
        return user_id

    def add_seed(self, user, raw_hash, *, source="cli", seasons=()):
        user_id = self.add_user(user, raw_hash)
        username = str(user.get("username") or user.get("display_name") or user_id)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO seeds(user_id, username, source, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    source = excluded.source
                """,
                (user_id, username, source, now),
            )
        for season in seasons:
            self.enqueue_crawl(
                "user_leagues", user_id, int(season), depth=0,
                seed_user_id=user_id, mechanism="seed",
            )
        return user_id

    def enqueue_crawl(
        self,
        task_type,
        entity_id,
        season,
        *,
        depth,
        seed_user_id,
        mechanism,
    ):
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_queue (
                    task_type, entity_id, season, depth, seed_user_id,
                    mechanism, status, available_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(task_type, entity_id, season) DO UPDATE SET
                    depth = MIN(crawl_queue.depth, excluded.depth)
                """,
                (
                    task_type,
                    str(entity_id),
                    season,
                    int(depth),
                    seed_user_id,
                    mechanism,
                    now,
                ),
            )

    def enqueue_user_seasons(
        self,
        user_ids,
        seasons,
        *,
        depth,
        seed_user_id,
        mechanism,
    ):
        now = utc_now()
        rows = [
            (
                "user_leagues",
                str(user_id),
                int(season),
                int(depth),
                seed_user_id,
                mechanism,
                now,
            )
            for user_id in dict.fromkeys(user_ids)
            for season in seasons
        ]
        if not rows:
            return 0
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO crawl_queue (
                    task_type, entity_id, season, depth, seed_user_id,
                    mechanism, status, available_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(task_type, entity_id, season) DO UPDATE SET
                    depth = MIN(crawl_queue.depth, excluded.depth)
                """,
                rows,
            )
            return connection.total_changes - before

    def enqueue_existing_owner_tasks(self, max_depth, seasons, owner_limit=1_000):
        if max_depth < 1:
            return 0
        seasons = tuple(dict.fromkeys(int(season) for season in seasons))
        if not seasons:
            return 0
        if owner_limit < 1:
            raise ValueError("owner enqueue limit must be positive")
        values = ", ".join("(?)" for _ in seasons)
        sql = f"""
            WITH seasons(season) AS (VALUES {values}),
            owner_depths AS (
                SELECT rosters.owner_id,
                       MIN(league_provenance.discovery_depth) + 1 AS depth,
                       MIN(league_provenance.seed_user_id) AS seed_user_id
                FROM rosters
                JOIN league_provenance USING (league_id, season)
                WHERE rosters.owner_id IS NOT NULL
                  AND league_provenance.discovery_depth < ?
                GROUP BY rosters.owner_id
            ),
            owners AS (
                SELECT owner_depths.*
                FROM owner_depths
                WHERE EXISTS (
                    SELECT 1
                    FROM seasons
                    LEFT JOIN crawl_queue
                      ON crawl_queue.task_type = 'user_leagues'
                     AND crawl_queue.entity_id = owner_depths.owner_id
                     AND crawl_queue.season = seasons.season
                    WHERE crawl_queue.id IS NULL
                       OR crawl_queue.depth > owner_depths.depth
                )
                ORDER BY owner_depths.owner_id
                LIMIT ?
            )
            INSERT INTO crawl_queue (
                task_type, entity_id, season, depth, seed_user_id,
                mechanism, status, available_at
            )
            SELECT 'user_leagues', owners.owner_id, seasons.season,
                   owners.depth, owners.seed_user_id, 'roster_owner',
                   'pending', ?
            FROM owners
            CROSS JOIN seasons
            LEFT JOIN crawl_queue
              ON crawl_queue.task_type = 'user_leagues'
             AND crawl_queue.entity_id = owners.owner_id
             AND crawl_queue.season = seasons.season
            WHERE crawl_queue.id IS NULL OR crawl_queue.depth > owners.depth
            ON CONFLICT(task_type, entity_id, season) DO UPDATE SET
                depth = MIN(crawl_queue.depth, excluded.depth)
        """
        with self.connect() as connection:
            before = connection.total_changes
            connection.execute(
                sql,
                (*seasons, int(max_depth), int(owner_limit), utc_now()),
            )
            return connection.total_changes - before

    def claim_crawl(self, max_depth):
        now = utc_now()
        with self.connect(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM crawl_queue
                WHERE status = 'pending' AND available_at <= ? AND depth <= ?
                ORDER BY depth, id
                LIMIT 1
                """,
                (now, max_depth),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE crawl_queue
                SET status = 'in_progress', claimed_at = ?, attempts = attempts + 1,
                    last_error = NULL
                WHERE id = ?
                """,
                (now, row["id"]),
            )
        return dict(row)

    def finish_crawl(self, task_id):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE crawl_queue
                SET status = 'done', completed_at = ?, claimed_at = NULL
                WHERE id = ?
                """,
                (utc_now(), task_id),
            )

    def fail_crawl(self, task_id, error):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE crawl_queue
                SET status = 'failed', last_error = ?, claimed_at = NULL
                WHERE id = ?
                """,
                (str(error), task_id),
            )

    def recover_stale(self, minutes=30):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        with self.connect() as connection:
            crawl = connection.execute(
                """
                UPDATE crawl_queue
                SET status = 'pending', claimed_at = NULL,
                    last_error = 'recovered stale claim'
                WHERE status = 'in_progress' AND claimed_at < ?
                """,
                (cutoff,),
            ).rowcount
            hydration = connection.execute(
                """
                UPDATE hydration_queue
                SET status = 'pending', claimed_at = NULL,
                    last_error = 'recovered stale claim'
                WHERE status = 'in_progress' AND claimed_at < ?
                """,
                (cutoff,),
            ).rowcount
        return crawl + hydration

    def enqueue_hydration_candidates(self, limit=None, preferred_seasons=()):
        preferred_seasons = tuple(
            dict.fromkeys(int(season) for season in preferred_seasons)
        )
        order = "league_seasons.season DESC"
        parameters = [utc_now()]
        if preferred_seasons:
            cases = " ".join(
                f"WHEN ? THEN {index}"
                for index, _ in enumerate(preferred_seasons)
            )
            order = (
                f"CASE league_seasons.season {cases} "
                f"ELSE {len(preferred_seasons)} END, league_seasons.league_id"
            )
            parameters.extend(preferred_seasons)
        sql = f"""
            INSERT OR IGNORE INTO hydration_queue (
                league_id, season, status, available_at
            )
            SELECT league_seasons.league_id, league_seasons.season,
                   'pending', ?
            FROM league_seasons
            LEFT JOIN hydration_queue USING (league_id, season)
            WHERE league_seasons.is_candidate = 1
              AND hydration_queue.league_id IS NULL
            ORDER BY {order}
        """
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(int(limit))
        with self.connect() as connection:
            before = connection.total_changes
            connection.execute(sql, parameters)
            return connection.total_changes - before

    def claim_hydration(self):
        now = utc_now()
        with self.connect(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM hydration_queue
                WHERE status = 'pending' AND available_at <= ?
                ORDER BY season ASC, league_id
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE hydration_queue
                SET status = 'in_progress', claimed_at = ?, attempts = attempts + 1,
                    last_error = NULL
                WHERE league_id = ? AND season = ?
                """,
                (now, row["league_id"], row["season"]),
            )
        return dict(row)

    def finish_hydration(self, league_id, season):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE hydration_queue
                SET status = 'done', completed_at = ?, claimed_at = NULL
                WHERE league_id = ? AND season = ?
                """,
                (utc_now(), league_id, season),
            )

    def fail_hydration(self, league_id, season, error):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE hydration_queue
                SET status = 'failed', last_error = ?, claimed_at = NULL
                WHERE league_id = ? AND season = ?
                """,
                (str(error), league_id, season),
            )

    def record_failure(self, queue_name, queue_key, endpoint, attempt, status, error):
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO request_failures (
                    queue_name, queue_key, endpoint, attempt, http_status, error, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (queue_name, queue_key, endpoint, attempt, status, error, utc_now()),
            )

    def retry_failures(self):
        with self.connect() as connection:
            crawl = connection.execute(
                """
                UPDATE crawl_queue
                SET status = 'pending', available_at = ?, last_error = NULL
                WHERE status = 'failed'
                """,
                (utc_now(),),
            ).rowcount
            hydration = connection.execute(
                """
                UPDATE hydration_queue
                SET status = 'pending', available_at = ?, last_error = NULL
                WHERE status = 'failed'
                """,
                (utc_now(),),
            ).rowcount
        return {"crawl": crawl, "hydration": hydration}

    def status(self):
        with self.connect() as connection:
            counts = {
                "users": _scalar(connection, "SELECT COUNT(*) FROM users"),
                "seeds": _scalar(connection, "SELECT COUNT(*) FROM seeds"),
                "league_seasons": _scalar(connection, "SELECT COUNT(*) FROM league_seasons"),
                "candidate_leagues": _scalar(connection, "SELECT COUNT(*) FROM league_seasons WHERE is_candidate = 1"),
                "rosters": _scalar(connection, "SELECT COUNT(*) FROM rosters"),
                "drafts": _scalar(connection, "SELECT COUNT(*) FROM drafts"),
                "draft_picks": _scalar(connection, "SELECT COUNT(*) FROM draft_picks"),
                "team_seasons": _scalar(connection, "SELECT COUNT(*) FROM team_seasons"),
                "raw_objects": _scalar(connection, "SELECT COUNT(*) FROM raw_objects"),
                "request_failures": _scalar(connection, "SELECT COUNT(*) FROM request_failures"),
                "rate_limit_responses": _scalar(
                    connection,
                    "SELECT COUNT(*) FROM request_failures WHERE http_status = 429",
                ),
            }
            counts["leagues_by_year"] = {
                str(row["season"]): row["count"]
                for row in connection.execute(
                    "SELECT season, COUNT(*) AS count FROM league_seasons GROUP BY season ORDER BY season"
                )
            }
            counts["crawl_queue"] = _status_counts(connection, "crawl_queue")
            counts["hydration_queue"] = _status_counts(connection, "hydration_queue")
            counts["quality_flags"] = {
                row["code"]: row["count"]
                for row in connection.execute(
                    "SELECT code, COUNT(*) AS count FROM quality_flags GROUP BY code ORDER BY code"
                )
            }
        return counts


def _status_counts(connection, table):
    return {
        row["status"]: row["count"]
        for row in connection.execute(
            f"SELECT status, COUNT(*) AS count FROM {table} GROUP BY status"
        )
    }


def _scalar(connection, sql):
    return connection.execute(sql).fetchone()[0]


def _text(value):
    return None if value in {None, ""} else str(value)


def _bool_int(value):
    if value is None:
        return None
    return int(bool(value))
