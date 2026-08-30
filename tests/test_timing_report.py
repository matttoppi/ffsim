import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ffsim.draft_intel.live import PreparedDraft
from ffsim.draft_intel.market_model import SLEEPER_ADP_SOURCE
from ffsim.draft_intel.timing_report import (
    _expected_best,
    build_timing_report,
    load_timing_report,
    write_timing_report,
)
from ffsim.historical_sleeper.empirical_survival import EMPIRICAL_SURVIVAL_VERSION
from tests.test_decision import draft_state, evaluator


class TimingReportTest(unittest.TestCase):
    def prepared(self):
        subject = evaluator()
        player_ids = subject.bank.player_ids
        return PreparedDraft(
            summary={
                "market_context": {
                    "target_context": {
                        "scoring": "PPR",
                        "team_count": 4,
                    }
                },
                "world_bank": {
                    "version": subject.bank.version,
                    "worlds": subject.bank.world_count,
                    "players": len(player_ids),
                },
            },
            live_draft_id="nested-offline",
            league_id="league",
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "market",
                "observations": [
                    {"canonical_player_id": player_id, "adp": rank}
                    for rank, player_id in enumerate(player_ids, 1)
                ],
            },
            evaluator=subject,
            player_details={
                player_id: {"name": player_id.upper(), "team": "TST"}
                for player_id in player_ids
            },
        )

    def test_report_combines_projection_and_survival_without_decision_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "empirical-survival.manifest.json"
            manifest.write_text(json.dumps({"model_version": EMPIRICAL_SURVIVAL_VERSION}))
            choose = lambda *_args, **_kwargs: None
            choose.board_player_ids = np.asarray(
                self.prepared().evaluator.bank.player_ids,
                dtype=object,
            )
            with (
                patch(
                    "ffsim.draft_intel.timing_report.load_empirical_survival_artifact",
                    return_value={
                        "sha256": "artifact",
                        "model_version": EMPIRICAL_SURVIVAL_VERSION,
                    },
                ),
                patch(
                    "ffsim.draft_intel.timing_report.load_empirical_survival_lookup",
                    return_value={"lookup": "fixed"},
                ),
                patch(
                    "ffsim.draft_intel.timing_report.lookup_survival",
                    side_effect=lambda _lookup, **values: {
                        "status": "available",
                        "probability": 0.9 - 0.05 * values["market_rank"],
                        "raw_rate": 0.85,
                        "interval_95": [0.8, 0.9],
                        "count": 1_000,
                    },
                ),
                patch(
                    "ffsim.draft_intel.timing_report._live_opponent_choice",
                    return_value=choose,
                ),
            ):
                report = build_timing_report(
                    self.prepared(),
                    draft_state(),
                    manifest,
                    input_hashes={"draft": "hash"},
                    candidate_breadth=4,
                )

            self.assertFalse(report["decision_active"])
            self.assertEqual(report["pick_no"], 1)
            self.assertEqual(report["next_turn_pick_no"], 8)
            self.assertGreaterEqual(len(report["players"]), 4)
            self.assertTrue(report["top_ten_capture_complete"])
            self.assertEqual(len(report["candidate_branches"]), len(report["players"]))
            for branch in report["candidate_branches"].values():
                self.assertEqual(branch["captured_market_players"], 10)
                self.assertTrue(branch["top_ten_capture_complete"])
            for row in report["players"]:
                self.assertIn("current_roster_value", row)
                self.assertIn("take_now_route_value", row)
                self.assertIn("best_wait_route_value", row)
                self.assertIn("wait_delta", row)
                self.assertIn("return_probability", row)
                self.assertNotIn("recommendation", row)
            output = root / "timing.json"
            write_timing_report(report, output)
            self.assertEqual(load_timing_report(output), report)
            with self.assertRaises(FileExistsError):
                write_timing_report(report, output)

    def test_unsupported_fallbacks_do_not_create_zero_value_routes(self):
        self.assertIsNone(_expected_best([
            {
                "player_id": "p1",
                "marginal_value": 50.0,
                "survival_probability": None,
            }
        ]))

    def test_report_requires_roster_on_clock(self):
        prepared = self.prepared()
        prepared = PreparedDraft(
            **{
                **prepared.__dict__,
                "user_roster_id": 2,
            }
        )
        with self.assertRaisesRegex(ValueError, "on the clock"):
            build_timing_report(
                prepared,
                draft_state(),
                "missing",
                input_hashes={},
            )


if __name__ == "__main__":
    unittest.main()
