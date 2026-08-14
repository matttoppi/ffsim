from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ffsim.draft_intel.synthetic import (
    _RecommendationTrace,
    _run_one_draft,
    _sample_to_next_user,
    estimated_telemetry_gb,
    run_synthetic_drafts,
)
from ffsim.draft_intel.state import replay_sleeper_draft


class SyntheticDraftTest(unittest.TestCase):
    def state(self, draft_type="snake", teams=3, rounds=3):
        return replay_sleeper_draft(
            {
                "draft_id": "synthetic-test",
                "type": draft_type,
                "status": "drafting",
                "settings": {"teams": teams, "rounds": rounds},
                "draft_order": {str(slot): slot for slot in range(1, teams + 1)},
                "slot_to_roster_id": {
                    str(slot): 100 + slot for slot in range(1, teams + 1)
                },
            },
            (),
            (),
            (f"p{index}" for index in range(1, teams * rounds + 4)),
        )

    def sample(self, state, user_roster_id, root_candidate_id):
        prepared = SimpleNamespace(
            user_roster_id=user_roster_id,
            evaluator=object(),
            player_details={},
        )

        def equal_utilities(roster_id, pick_no, rosters, available):
            return {player_id: 0.0 for player_id in available}

        with (
            patch("ffsim.draft_intel.synthetic._bank_market_snapshot"),
            patch(
                "ffsim.draft_intel.synthetic._live_opponent_choice",
                return_value=equal_utilities,
            ),
            patch(
                "ffsim.draft_intel.synthetic._projection_user_policy",
                return_value=equal_utilities,
            ),
        ):
            return _sample_to_next_user(
                prepared, state, root_candidate_id, (0, 1), 2026
            )

    def test_snake_end_adjacent_pick_gets_a_fresh_recommendation(self):
        state = self.state().with_pick("p1").with_pick("p2")

        result, picks = self.sample(state, 103, "p3")

        self.assertEqual([pick.pick_no for pick in picks], [3])
        self.assertEqual(result.current_pick_no, 4)
        self.assertEqual(result.current_roster_id, 103)

    def test_sampling_keeps_root_and_opponents_until_an_ordinary_user_pick(self):
        state = self.state().with_pick("p1")

        result, picks = self.sample(state, 102, "p2")

        self.assertEqual([pick.pick_no for pick in picks], [2, 3, 4])
        self.assertEqual(result.current_pick_no, 5)
        self.assertEqual(result.current_roster_id, 102)

    def test_sampling_from_an_opponent_stops_before_the_user_pick(self):
        state = self.state()

        result, picks = self.sample(state, 103, None)

        self.assertEqual([pick.pick_no for pick in picks], [1, 2])
        self.assertEqual(result.current_pick_no, 3)
        self.assertEqual(result.current_roster_id, 103)

    def test_linear_sampling_also_stops_before_each_user_pick(self):
        state = self.state(draft_type="linear").with_pick("p1")

        result, picks = self.sample(state, 102, "p2")

        self.assertEqual([pick.pick_no for pick in picks], [2, 3, 4])
        self.assertEqual(result.current_pick_no, 5)
        self.assertEqual(result.current_roster_id, 102)

    def test_short_candidate_pool_is_a_complete_screen(self):
        trace = _RecommendationTrace()
        payload = {"candidates_evaluated": 7, "candidate_pool": 7}

        trace.record(
            "session", "draft", "recommendation", payload,
            stage="calculating", duration_seconds=1.5,
        )

        self.assertEqual(trace.screen, (payload, "calculating", 1.5))

    def test_trace_waits_for_the_full_screen_and_ignores_refinement(self):
        trace = _RecommendationTrace()
        partial = {"candidates_evaluated": 9, "candidate_pool": 12}
        full = {"candidates_evaluated": 12, "candidate_pool": 12}

        trace.record("session", "draft", "recommendation", partial)
        self.assertIsNone(trace.screen)
        trace.record("session", "draft", "recommendation", full)
        self.assertEqual(trace.screen, (full, None, None))
        trace.record(
            "session", "draft", "recommendation",
            {**full, "screened_candidates": []},
        )
        self.assertEqual(trace.screen, (full, None, None))

    def test_estimate_uses_1700_kb_per_draft(self):
        self.assertEqual(estimated_telemetry_gb(250), 0.425)
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
            ["Estimated SQLite addition: 0.425000 GB (1700 KB x 250 drafts)"],
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
