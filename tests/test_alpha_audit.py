import tempfile
import unittest
from pathlib import Path

from ffsim.draft_intel.alpha_audit import (
    build_alpha_shadow_audit,
    write_alpha_shadow_audit,
)
from ffsim.draft_intel.telemetry import DraftTelemetry
from ffsim.historical_sleeper.hdvn_snapshot import sha256_file


class AlphaShadowAuditTest(unittest.TestCase):
    def payload(self, pick_no):
        return {
            "status": "ready",
            "decision_active": False,
            "draft_id": "draft",
            "pick_no": pick_no,
            "round": (pick_no - 1) // 2 + 1,
            "opponent_picks_until_next": pick_no,
            "state_signature": f"state-{pick_no}",
            "terminal_recommendation_id": "p1",
            "survival_manifest_hash": "survival",
            "manager_manifest_hash": "manager",
            "manager_probability_blend": 0.1,
            "top_ten_capture_complete": True,
            "candidates": [
                {
                    "player_id": "p1",
                    "return_probability": 0.5,
                    "return_interval_95": [0.4, 0.6],
                    "direct_support": 200,
                    "timing_label": "uncertain",
                },
                {
                    "player_id": "p2",
                    "return_probability": None,
                    "return_interval_95": None,
                    "direct_support": 0,
                    "timing_label": "outside_model",
                },
            ],
            "manager_shadow": {
                "status": "ready",
                "terminal_leader_candidate_id": "p1",
                "shadow_leader_candidate_id": "p1",
                "shadow_leader_in_terminal_practical_tier": True,
                "callback_calls": {
                    "personalized": 100,
                    "population": 20,
                },
            },
            "manager_support": {
                "supported_rosters": 7,
                "population_fallback_rosters": 2,
                "total_opponent_rosters": 9,
            },
        }

    def test_six_state_development_gate_and_immutable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telemetry = DraftTelemetry(root / "telemetry.sqlite3")
            telemetry.start_session("session", "draft", {"test": True})
            for pick_no in range(1, 7):
                telemetry.record(
                    "session",
                    "draft",
                    "alpha_shadow",
                    self.payload(pick_no),
                    pick_no=pick_no,
                    stage="shadow",
                    duration_seconds=float(pick_no),
                )
            telemetry.record(
                "session",
                "draft",
                "alpha_shadow",
                self.payload(1),
                pick_no=1,
                stage="shadow",
                duration_seconds=1.5,
            )
            telemetry.record(
                "session",
                "draft",
                "alpha_shadow_discarded",
                self.payload(7),
                pick_no=7,
                stage="shadow",
                duration_seconds=2.0,
            )
            telemetry.finish_session("session", "stopped")
            telemetry_hash = sha256_file(telemetry.path)

            report = build_alpha_shadow_audit(telemetry.path)
            self.assertEqual(sha256_file(telemetry.path), telemetry_hash)
            self.assertTrue(report["development_gate"]["passes"])
            self.assertFalse(report["live_evidence_gate"]["passes"])
            self.assertEqual(report["metrics"]["ready_states"], 6)
            self.assertEqual(report["metrics"]["raw_ready_events"], 7)
            self.assertEqual(report["metrics"]["duplicate_ready_events"], 1)
            self.assertEqual(report["metrics"]["discarded_events"], 1)
            self.assertEqual(report["metrics"]["top_ten_capture_rate"], 1.0)
            self.assertEqual(
                report["metrics"]["manager_practical_retention_rate"], 1.0
            )
            self.assertEqual(
                report["metrics"]["manager_callback_calls"],
                {"personalized": 600, "population": 120},
            )
            output = root / "audit.json"
            written = write_alpha_shadow_audit(report, output)
            self.assertTrue(written["sha256"])
            with self.assertRaises(FileExistsError):
                write_alpha_shadow_audit(report, output)

    def test_failure_event_fails_development_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telemetry = DraftTelemetry(root / "telemetry.sqlite3")
            telemetry.start_session("session", "draft", {})
            telemetry.record(
                "session",
                "draft",
                "alpha_shadow_error",
                {"error": "boom"},
                pick_no=1,
                stage="shadow",
                duration_seconds=1.0,
            )

            report = build_alpha_shadow_audit(telemetry.path)
            self.assertFalse(report["development_gate"]["passes"])
            self.assertEqual(report["metrics"]["failure_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
