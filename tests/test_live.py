import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import call, patch

from ffsim.draft_intel.live import (
    _draft_id,
    _manager_slot,
    _refresh_history,
    mock_mismatch_reasons,
)


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

        self.assertEqual(_manager_slot({"draft_order": {"user": 3}}, "user"), 3)
        self.assertIsNone(_manager_slot({"draft_order": {"creator": 1}}, "user"))

    def test_league_mock_must_match_real_geometry_and_market(self):
        real = {
            "league_id": "league",
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
        league_mock = {
            **real,
            "league_id": None,
            "metadata": {
                "scoring_type": "ppr",
                "type": "league_mock",
                "league_id": "league",
            },
        }
        self.assertEqual(mock_mismatch_reasons(real, league_mock), [])

        mock = {
            **league_mock,
            "settings": {**real["settings"], "teams": 10, "slots_flex": 2},
            "metadata": {"scoring_type": "std", "type": "mock"},
        }
        codes = {reason["code"] for reason in mock_mismatch_reasons(real, mock)}
        self.assertEqual(codes, {
            "mock_league_link_mismatch",
            "mock_team_count_mismatch",
            "mock_roster_slots_mismatch",
            "mock_market_context_mismatch",
        })

    def test_history_refresh_can_initialize_an_empty_store(self):
        canonical_player = SimpleNamespace(sleeper_id="s", canonical_player_id="c")
        history = object()
        with (
            TemporaryDirectory() as directory,
            patch("ffsim.draft_intel.live.CACHE_DIR", Path(directory)),
            patch("ffsim.draft_intel.live.canonical_players_from_cache", return_value=(canonical_player,)),
            patch("ffsim.draft_intel.live.load_sleeper_identity_map", return_value={}),
            patch("ffsim.draft_intel.live.load_history", return_value=history) as load,
            patch("ffsim.draft_intel.live.summarize_history", return_value={}) as summarize,
            patch("ffsim.draft_intel.live.store_history", return_value={"database_path": "db"}) as store,
        ):
            (Path(directory) / "players.json").write_text("{}")
            result = _refresh_history("league", 2026)

        load.assert_has_calls([call(
            "league",
            range(2026, 2023, -1),
            canonical_player_ids={"s": "c"},
            raw_responses={},
        )])
        summarize.assert_called_once_with(history, 2026)
        store.assert_called_once()
        self.assertEqual(result["storage"], {"database_path": "db"})


if __name__ == "__main__":
    unittest.main()
