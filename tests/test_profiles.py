import sqlite3
import tempfile
import unittest
from pathlib import Path

from ffsim.draft_intel.profiles import load_pick_observations, summarize_manager_profiles
from ffsim.draft_intel.storage import SCHEMA


class PickObservationTest(unittest.TestCase):
    def test_reconstructs_target_rosters_and_observed_available_players(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with sqlite3.connect(database_path) as database:
                database.executescript(SCHEMA)
                database.executemany(
                    "INSERT INTO managers VALUES (?, ?, ?, ?)",
                    (("u1", "One", "now", "now"), ("u2", "Two", "now", "now")),
                )
                database.execute(
                    """
                    INSERT INTO historical_drafts (
                        draft_id, season, status, draft_type, roster_slots_json,
                        context_hash, included, exclusion_reasons_json,
                        raw_snapshot_hash, raw_snapshot_path, observed_at
                    ) VALUES ('draft', 2026, 'complete', 'snake', '[]',
                              'context', 1, '[]', 'raw', 'raw.json', 'now')
                    """
                )
                database.executemany(
                    "INSERT INTO historical_draft_managers VALUES ('draft', ?, ?, ?)",
                    (("u1", 2, None), ("u2", 1, None)),
                )
                database.executemany(
                    "INSERT INTO canonical_players VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        (f"sleeper:{number}", f"Player {number}", f"player{number}",
                         "WR", None, 1, "now")
                        for number in range(1, 6)
                    ),
                )
                database.executemany(
                    """
                    INSERT INTO historical_picks (
                        draft_id, pick_no, round, draft_slot, manager_id,
                        canonical_player_id, source_player_id, position, is_keeper
                    ) VALUES ('draft', ?, ?, ?, ?, ?, ?, 'WR', ?)
                    """,
                    (
                        (1, 1, 1, "room-manager", "sleeper:1", "1", 0),
                        (2, 1, 2, "u1", "sleeper:2", "2", 0),
                        (3, 1, 2, "u1", "sleeper:5", "5", 1),
                        (4, 1, 1, "u2", "sleeper:3", "3", 0),
                        (5, 1, 2, "u1", "sleeper:4", "4", 0),
                    ),
                )

            observations = load_pick_observations(directory)

            self.assertEqual(
                [(observation.manager_id, observation.pick_no) for observation in observations],
                [("u1", 2), ("u2", 4), ("u1", 5)],
            )
            self.assertEqual(observations[0].roster_before_pick, ("sleeper:5",))
            self.assertEqual(
                observations[0].observed_available_player_ids,
                ("sleeper:2", "sleeper:3", "sleeper:4"),
            )
            self.assertEqual(observations[2].roster_before_pick, ("sleeper:5", "sleeper:2"))
            self.assertEqual(
                observations[2].observed_available_player_ids,
                ("sleeper:4",),
            )
            self.assertEqual(summarize_manager_profiles(observations)["u1"], {
                "display_name": "One",
                "draft_count": 1,
                "pick_count": 2,
                "drafts_by_season": {2026: 1},
                "drafts_by_scoring": {"unknown": 1},
                "drafts_by_team_count": {"unknown": 1},
                "position_picks": {"WR": 2},
                "position_picks_by_round": {"1": {"WR": 2}},
                "first_position_rounds": {"WR": [1]},
            })
