"""Durable telemetry for live draft sessions."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock

from ffsim.paths import CACHE_DIR


SCHEMA = """
CREATE TABLE IF NOT EXISTS live_draft_sessions (
    session_id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS live_draft_sessions_draft
ON live_draft_sessions(draft_id, started_at);

CREATE TABLE IF NOT EXISTS live_draft_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES live_draft_sessions(session_id),
    draft_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    pick_no INTEGER,
    stage TEXT,
    occurred_at TEXT NOT NULL,
    duration_seconds REAL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS live_draft_events_query
ON live_draft_events(draft_id, session_id, event_type, pick_no, id);
"""


class DraftTelemetry:
    def __init__(self, path=None):
        self.path = Path(path or CACHE_DIR / "draft_intel" / "telemetry.sqlite3")
        self.lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as database, database:
            database.executescript(SCHEMA)

    def _connect(self):
        database = sqlite3.connect(self.path)
        database.execute("PRAGMA foreign_keys = ON")
        return database

    def start_session(self, session_id, draft_id, config):
        with self.lock, closing(self._connect()) as database, database:
            database.execute(
                """INSERT INTO live_draft_sessions
                   (session_id, draft_id, started_at, status, config_json)
                   VALUES (?, ?, ?, 'running', ?)""",
                (session_id, draft_id, _now(), _json(config)),
            )

    def finish_session(self, session_id, status):
        with self.lock, closing(self._connect()) as database, database:
            database.execute(
                """UPDATE live_draft_sessions
                   SET finished_at = ?, status = ?
                   WHERE session_id = ?""",
                (_now(), status, session_id),
            )

    def record(
        self,
        session_id,
        draft_id,
        event_type,
        payload,
        *,
        pick_no=None,
        stage=None,
        duration_seconds=None,
    ):
        with self.lock, closing(self._connect()) as database, database:
            database.execute(
                """INSERT INTO live_draft_events
                   (session_id, draft_id, event_type, pick_no, stage,
                    occurred_at, duration_seconds, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    draft_id,
                    event_type,
                    pick_no,
                    stage,
                    _now(),
                    duration_seconds,
                    _json(payload),
                ),
            )

    def query(
        self,
        *,
        draft_id=None,
        session_id=None,
        event_type=None,
        pick_no=None,
        limit=1_000,
    ):
        if not 1 <= limit <= 5_000:
            raise ValueError("limit must be between 1 and 5000")
        filters = []
        values = []
        for column, value in (
            ("draft_id", draft_id),
            ("session_id", session_id),
            ("event_type", event_type),
            ("pick_no", pick_no),
        ):
            if value is not None:
                filters.append(f"{column} = ?")
                values.append(value)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        with self.lock, closing(self._connect()) as database:
            database.row_factory = sqlite3.Row
            sessions = database.execute(
                """SELECT session_id, draft_id, started_at, finished_at, status,
                          config_json
                   FROM live_draft_sessions
                   WHERE (? IS NULL OR draft_id = ?)
                     AND (? IS NULL OR session_id = ?)
                   ORDER BY started_at, session_id""",
                (draft_id, draft_id, session_id, session_id),
            ).fetchall()
            events = database.execute(
                f"""SELECT id, session_id, draft_id, event_type, pick_no, stage,
                           occurred_at, duration_seconds, payload_json
                    FROM live_draft_events{where}
                    ORDER BY id LIMIT ?""",
                (*values, limit),
            ).fetchall()
        return {
            "sessions": [
                {
                    **{key: row[key] for key in row.keys() if key != "config_json"},
                    "config": json.loads(row["config_json"]),
                }
                for row in sessions
            ],
            "events": [
                {
                    **{key: row[key] for key in row.keys() if key != "payload_json"},
                    "payload": json.loads(row["payload_json"]),
                }
                for row in events
            ],
        }


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
