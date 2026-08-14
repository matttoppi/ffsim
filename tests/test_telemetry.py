import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from ffsim.api import LiveDraftMonitor, create_app


def endpoint(app, path, method):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path
        and method in getattr(route, "methods", ())
    )


class TelemetryTest(unittest.TestCase):
    def test_recommendations_survive_the_monitor_and_are_queryable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite3"
            app = create_app(Path(directory) / "config.json", path)
            telemetry = app.state.draft_telemetry
            prepared = SimpleNamespace(
                live_draft_id="draft",
                user_roster_id=1,
                summary={"market_snapshot_id": "market", "world_bank": {"version": "world"}},
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
