import unittest

from ffsim.draft_intel.live import _draft_id, mock_mismatch_reasons


class LiveDraftTest(unittest.TestCase):
    def test_draft_url_and_id_inputs(self):
        self.assertEqual(_draft_id(" 1393634461312106496 ", "Mock"), "1393634461312106496")
        self.assertEqual(
            _draft_id(
                "https://sleeper.app/draft/nfl/1393634461312106496",
                "Mock",
            ),
            "1393634461312106496",
        )
        self.assertIsNone(_draft_id("", "Mock", required=False))
        with self.assertRaisesRegex(ValueError, "Sleeper draft ID or draft URL"):
            _draft_id("https://example.com/draft/nfl/123", "Mock")

    def test_league_mock_must_match_real_geometry_and_market(self):
        real = {
            "type": "snake",
            "settings": {
                "teams": 12,
                "rounds": 15,
                "slots_qb": 1,
                "slots_flex": 1,
                "slots_bn": 6,
            },
            "metadata": {"scoring_type": "ppr"},
        }
        self.assertEqual(mock_mismatch_reasons(real, real), [])

        mock = {
            **real,
            "settings": {**real["settings"], "teams": 10, "slots_flex": 2},
            "metadata": {"scoring_type": "std"},
        }
        codes = {reason["code"] for reason in mock_mismatch_reasons(real, mock)}
        self.assertEqual(codes, {
            "mock_team_count_mismatch",
            "mock_roster_slots_mismatch",
            "mock_market_context_mismatch",
        })


if __name__ == "__main__":
    unittest.main()
