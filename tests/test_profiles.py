import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from ffsim.draft_intel.profiles import (
    MANAGER_PROFILE_MODEL_STATUS,
    load_pick_observations,
    load_target_context,
    summarize_manager_profiles,
)
from ffsim.draft_intel.storage import SCHEMA


class PickObservationTest(unittest.TestCase):
    def test_manager_profiles_are_explicitly_not_decision_eligible(self):
        self.assertEqual(MANAGER_PROFILE_MODEL_STATUS["use"], "descriptive_only")
        self.assertFalse(MANAGER_PROFILE_MODEL_STATUS["decision_eligible"])
        self.assertEqual(MANAGER_PROFILE_MODEL_STATUS["calibration"], "not_run")

    def test_reconstructs_target_rosters_and_observed_available_players(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with closing(sqlite3.connect(database_path)) as database, database:
                database.executescript(SCHEMA)
                database.executemany(
                    "INSERT INTO managers VALUES (?, ?, ?, ?)",
                    (("u1", "One", "now", "now"), ("u2", "Two", "now", "now")),
                )
                database.execute(
                    """
                    INSERT INTO historical_drafts (
                        draft_id, season, status, draft_type, scoring_type, team_count,
                        roster_slots_json,
                        context_hash, included, exclusion_reasons_json,
                        raw_snapshot_hash, raw_snapshot_path, observed_at
                    ) VALUES ('draft', 2026, 'complete', 'snake', 'ppr', 10, '[]',
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
                        (4, 2, 1, "u2", "sleeper:3", "3", 0),
                        (5, 4, 2, "u1", "sleeper:4", "4", 0),
                    ),
                )

            observations = load_pick_observations(directory)

            self.assertEqual(
                [(observation.manager_id, observation.pick_no) for observation in observations],
                [("u1", 2), ("u2", 4), ("u1", 5)],
            )
            self.assertEqual(observations[0].roster_before_pick, ("sleeper:5",))
            self.assertEqual(observations[0].roster_positions_before_pick, ("WR",))
            self.assertEqual(
                observations[0].observed_available_player_ids,
                ("sleeper:2", "sleeper:3", "sleeper:4"),
            )
            self.assertEqual(observations[2].roster_before_pick, ("sleeper:5", "sleeper:2"))
            self.assertEqual(
                observations[2].observed_available_player_ids,
                ("sleeper:4",),
            )
            self.assertEqual(summarize_manager_profiles(
                observations,
                target_season=2026,
                target_scoring_type="ppr",
                target_team_count=10,
            )["u1"], {
                "display_name": "One",
                "draft_count": 1,
                "pick_count": 2,
                "drafts_by_season": {2026: 1},
                "drafts_by_scoring": {"ppr": 1},
                "drafts_by_team_count": {"10": 1},
                "position_picks": {"WR": 2},
                "position_picks_by_round": {"1": {"WR": 1}, "4": {"WR": 1}},
                "first_position_rounds": {"WR": [1]},
                "qb_te_timing": {
                    "QB": {
                        "selected_drafts": 0,
                        "not_selected_drafts": 1,
                        "first_round_counts": {},
                        "sample_weight": 1.0,
                        "selected_weight": 0,
                        "weighted_first_rounds": {},
                    },
                    "TE": {
                        "selected_drafts": 0,
                        "not_selected_drafts": 1,
                        "first_round_counts": {},
                        "sample_weight": 1.0,
                        "selected_weight": 0,
                        "weighted_first_rounds": {},
                    },
                },
                "average_roster_after_round": {
                    "1": {"draft_count": 1, "draft_weight": 1.0, "positions": {"WR": 2.0}},
                    "2": {"draft_count": 1, "draft_weight": 1.0, "positions": {"WR": 2.0}},
                    "3": {"draft_count": 1, "draft_weight": 1.0, "positions": {"WR": 2.0}},
                    "4": {"draft_count": 1, "draft_weight": 1.0, "positions": {"WR": 3.0}},
                },
                "four_round_starts": {
                    "sample_size": 1,
                    "rb_shape": {"zero_rb": 1},
                    "wr_heavy": 1,
                    "sample_weight": 1.0,
                    "weighted_rb_shape": {"zero_rb": 1.0},
                    "weighted_wr_heavy": 1.0,
                },
                "context": {
                    "weighted_draft_count": 1.0,
                    "draft_weights": {
                        "draft": {
                            "season": 2026,
                            "scoring_type": "ppr",
                            "team_count": 10,
                            "season_weight": 1.0,
                            "scoring_weight": 1.0,
                            "team_count_weight": 1.0,
                            "weight": 1.0,
                        },
                    },
                },
            })

            prior = replace(
                observations[0],
                draft_id="prior",
                season=2025,
                scoring_type="2qb",
                team_count=12,
            )
            context = summarize_manager_profiles(
                (prior,),
                target_season=2026,
                target_scoring_type="ppr",
                target_team_count=10,
            )["u1"]["context"]
            self.assertEqual(context["weighted_draft_count"], 0.1458)
            self.assertEqual(context["draft_weights"]["prior"], {
                "season": 2025,
                "scoring_type": "2qb",
                "team_count": 12,
                "season_weight": 0.35,
                "scoring_weight": 0.5,
                "team_count_weight": 0.8333,
                "weight": 0.1458,
            })

    def test_loads_target_context_from_cached_league(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text('{"league_id": "league", "draft_id": "draft"}')
            (Path(directory) / "league_league.json").write_text(
                '{"draft": {'
                '"draft_id": "draft", "league_id": "league", '
                '"metadata": {"scoring_type": "custom_redraft"}, '
                '"settings": {"teams": 3}'
                '}}'
            )

            self.assertEqual(load_target_context(
                config_path,
                2026,
                cache_dir=directory,
            ), {
                "season": 2026,
                "scoring_type": "custom_redraft",
                "team_count": 3,
            })
