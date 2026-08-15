from contextlib import closing
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from ffsim.api import LiveDraftMonitor, create_app
from ffsim.draft_intel.telemetry import DraftTelemetry


def endpoint(app, path, method):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path
        and method in getattr(route, "methods", ())
    )


class TelemetryTest(unittest.TestCase):
    def test_initialization_uses_wal_busy_timeout_and_foreign_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            telemetry = DraftTelemetry(Path(directory) / "telemetry.sqlite3")

            with closing(telemetry._connect()) as database:
                self.assertEqual(
                    database.execute("PRAGMA journal_mode").fetchone()[0],
                    "wal",
                )
                self.assertEqual(
                    database.execute("PRAGMA busy_timeout").fetchone()[0],
                    5_000,
                )
                self.assertEqual(
                    database.execute("PRAGMA foreign_keys").fetchone()[0],
                    1,
                )

    def test_initialization_migrates_an_existing_database_to_wal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite3"
            with closing(sqlite3.connect(path)) as database, database:
                self.assertEqual(
                    database.execute("PRAGMA journal_mode = DELETE").fetchone()[0],
                    "delete",
                )
                database.execute("CREATE TABLE legacy (value TEXT)")
                database.execute("INSERT INTO legacy VALUES ('preserved')")

            telemetry = DraftTelemetry(path)

            with closing(telemetry._connect()) as database:
                self.assertEqual(
                    database.execute("PRAGMA journal_mode").fetchone()[0],
                    "wal",
                )
                self.assertEqual(
                    database.execute("SELECT value FROM legacy").fetchone()[0],
                    "preserved",
                )

    def test_external_reader_does_not_block_event_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite3"
            telemetry = DraftTelemetry(path)
            telemetry.start_session("session", "draft", {})

            with closing(sqlite3.connect(path)) as reader:
                reader.execute("BEGIN")
                reader.execute("SELECT count(*) FROM live_draft_events").fetchone()

                telemetry.record("session", "draft", "pick", {"player_id": "1"})
                result = telemetry.query(session_id="session")

                self.assertEqual(len(result["events"]), 1)
                self.assertEqual(result["events"][0]["payload"], {"player_id": "1"})

    def test_writer_timeout_remains_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite3"
            telemetry = DraftTelemetry(path)
            telemetry.start_session("session", "draft", {})

            with closing(sqlite3.connect(path)) as writer:
                writer.execute("BEGIN IMMEDIATE")
                with patch(
                    "ffsim.draft_intel.telemetry.TELEMETRY_BUSY_TIMEOUT_SECONDS",
                    0.05,
                ):
                    started_at = time.monotonic()
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        telemetry.record("session", "draft", "pick", {})
                    elapsed = time.monotonic() - started_at

                self.assertLess(elapsed, 1.0)
            self.assertEqual(telemetry.query(session_id="session")["events"], [])

    def test_recommendations_survive_the_monitor_and_are_queryable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite3"
            app = create_app(Path(directory) / "config.json", path)
            telemetry = app.state.draft_telemetry
            prepared = SimpleNamespace(
                live_draft_id="draft",
                user_roster_id=1,
                summary={
                    "market_snapshot_id": "market",
                    "market_context": {
                        "status": "proxy",
                        "target_context": {
                            "team_count": 10,
                            "reception_points": 1.0,
                            "tight_end_reception_bonus": 0.5,
                        },
                        "base_board_context": {
                            "snapshot_id": "market",
                            "team_count": None,
                        },
                        "proxy_reason_codes": [
                            "te_reception_premium_not_represented_by_board",
                            "team_count_unavailable_uses_generic_board",
                        ],
                        "calibration_artifact": None,
                        "model_status": "uncalibrated_sleeper_adp_baseline",
                        "model_version": "sleeper-adp-inverse-rank-v2",
                    },
                    "world_bank": {"version": "world"},
                },
            )
            monitor = LiveDraftMonitor(
                prepared,
                1,
                300,
                9,
                telemetry=telemetry,
                session_id="session",
            )
            fingerprint = ("drafting", 8, 1, (1, 2))
            monitor.state_fingerprint = fingerprint
            telemetry.start_session(
                monitor.session_id,
                prepared.live_draft_id,
                {"prepared": prepared.summary},
            )
            recommendation = {
                "pick_no": 9,
                "recommended_candidate_id": "player-1",
                "candidates": [{"player_id": "player-1", "championship_probability": 0.2}],
                "run_signature": "run",
                "draft_model_version": "model",
                "world_bank_version": "world",
                "seed": 2026,
                "reason_codes": ["TITLE_EQUITY_LEADER"],
            }

            self.assertTrue(monitor._publish_recommendation(
                fingerprint,
                9,
                recommendation,
                "ready",
                time.monotonic(),
                final=True,
            ))
            telemetry.finish_session(monitor.session_id, "completed")

            query = endpoint(app, "/api/draft-intel/telemetry", "GET")
            result = query(draft_id="draft", event_type="recommendation", pick_no=9)
            self.assertEqual(result["sessions"][0]["status"], "completed")
            self.assertEqual(
                result["sessions"][0]["config"]["prepared"]["market_context"],
                prepared.summary["market_context"],
            )
            self.assertEqual(result["events"][0]["payload"], recommendation)
            self.assertEqual(result["events"][0]["stage"], "ready")
            self.assertNotIn("payload_json", result["events"][0])
            with self.assertRaises(HTTPException):
                query(limit=0)

    def test_monitor_persists_state_changes_and_observed_picks(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                Path(directory) / "config.json",
                Path(directory) / "telemetry.sqlite3",
            )
            prepared = SimpleNamespace(
                live_draft_id="draft",
                user_roster_id=1,
                summary={},
                evaluator=None,
            )
            monitor = LiveDraftMonitor(
                prepared,
                0,
                2,
                2,
                telemetry=app.state.draft_telemetry,
                session_id="session",
            )
            pick = {
                "pick_no": 1,
                "round": 1,
                "draft_slot": 2,
                "roster_id": 2,
                "player_id": "player-1",
                "name": "Player One",
                "position": "RB",
                "team": "NFL",
            }
            states = [
                SimpleNamespace(
                    status="drafting",
                    completed_picks=(),
                    current_pick_no=1,
                    current_roster_id=2,
                    pick_owners=(2,),
                ),
                SimpleNamespace(
                    status="drafting",
                    completed_picks=(object(),),
                    current_pick_no=None,
                    current_roster_id=None,
                    pick_owners=(2,),
                ),
            ]

            def summary(_prepared, state):
                return {
                    "completed_picks": len(state.completed_picks),
                    "recent_picks": [pick][:len(state.completed_picks)],
                    "current_pick_no": state.current_pick_no,
                }

            with (
                patch(
                    "ffsim.draft_intel.live.sync_prepared_draft",
                    side_effect=[
                        SimpleNamespace(state=states[0]),
                        SimpleNamespace(state=states[1]),
                    ],
                ),
                patch("ffsim.draft_intel.live.live_state_summary", side_effect=summary),
            ):
                monitor.run()

            result = app.state.draft_telemetry.query(session_id="session")
            self.assertEqual(result["sessions"][0]["status"], "completed")
            self.assertEqual(
                [event["event_type"] for event in result["events"]],
                ["draft_state", "pick", "draft_state"],
            )
            self.assertEqual(result["events"][1]["payload"], pick)


if __name__ == "__main__":
    unittest.main()
