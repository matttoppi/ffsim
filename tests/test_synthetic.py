from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ffsim.draft_intel.synthetic import (
    _run_one_draft,
    estimated_telemetry_gb,
    run_synthetic_drafts,
)


class SyntheticDraftTest(unittest.TestCase):
    def test_estimate_uses_450_kb_per_draft(self):
        self.assertEqual(estimated_telemetry_gb(250), 0.1125)
        with self.assertRaisesRegex(ValueError, "positive"):
            estimated_telemetry_gb(0)

    def test_estimate_prints_before_preparation(self):
        output = []
        with (
            patch(
                "ffsim.draft_intel.synthetic._load_templates",
                side_effect=RuntimeError("stop after estimate"),
            ),
            self.assertRaisesRegex(RuntimeError, "stop after estimate"),
        ):
            run_synthetic_drafts("config.json", 250, print_fn=output.append)
        self.assertEqual(
            output,
            ["Estimated SQLite addition: 0.112500 GB (450 KB x 250 drafts)"],
        )

    def test_failed_draft_records_the_exception(self):
        prepared = SimpleNamespace(
            summary={},
            user_roster_id=1,
            evaluator=SimpleNamespace(_cache={}),
        )
        state = SimpleNamespace(
            draft_id="synthetic:test:0001",
            current_pick_no=1,
            current_roster_id=2,
        )
        monitor = SimpleNamespace(calculate=lambda *args: None, stop=lambda: None)
        executor = SimpleNamespace(shutdown=lambda **kwargs: None)
        telemetry = MagicMock()
        with (
            patch(
                "ffsim.draft_intel.synthetic.LiveDraftMonitor",
                return_value=monitor,
            ),
            patch(
                "ffsim.draft_intel.synthetic.create_live_executor",
                return_value=executor,
            ),
            patch(
                "ffsim.draft_intel.synthetic._sample_to_next_user",
                side_effect=ValueError("boom"),
            ),
            self.assertRaisesRegex(ValueError, "boom"),
        ):
            _run_one_draft(prepared, state, telemetry, {}, "test", 2026, 0)

        event = telemetry.record.call_args.args
        self.assertEqual(event[2], "synthetic_error")
        self.assertEqual(event[3]["error_type"], "ValueError")
        self.assertIn("ValueError: boom", event[3]["traceback"])
        telemetry.finish_session.assert_called_once_with(event[0], "failed")


if __name__ == "__main__":
    unittest.main()
