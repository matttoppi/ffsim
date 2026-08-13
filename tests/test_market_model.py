import json
import math
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ffsim.draft_intel.market_model import (
    backtest_sleeper_adp,
    load_league_market_snapshot,
    mixture_choice_probabilities,
    position_caps,
    resolve_league_market_context,
    resolve_market_context,
    sleeper_adp_choice,
    sleeper_adp_model_version,
)
from ffsim.draft_intel.storage import SCHEMA


class MarketModelTest(unittest.TestCase):
    def test_context_resolution_is_exact_or_explicitly_proxy(self):
        exact = resolve_league_market_context({
            "roster_positions": ["QB", "RB", "WR", "FLEX"],
            "scoring_settings": {"rec": 1},
        })
        superflex_proxy = resolve_league_market_context({
            "roster_positions": ["QB", "SUPER_FLEX", "RB", "WR"],
            "scoring_settings": {"rec": 1},
        })
        custom_proxy = resolve_league_market_context({
            "roster_positions": ["QB", "RB", "WR"],
            "scoring_settings": {"rec": 0.25},
        })

        self.assertEqual(
            (exact["status"], exact["league_format"], exact["scoring"]),
            ("exact", "1qb", "PPR"),
        )
        self.assertEqual(
            (superflex_proxy["status"], superflex_proxy["scoring"]),
            ("proxy", "HALF"),
        )
        self.assertEqual(custom_proxy["status"], "proxy")
        self.assertEqual(custom_proxy["scoring"], "STD")
        self.assertEqual(
            resolve_market_context(roster_positions=(), scoring_type="ppr")["status"],
            "unsupported",
        )

    def test_reach_mixture_thickens_the_tail_of_the_sharp_board_follower(self):
        utilities = {f"p{number}": -math.log(number) for number in range(1, 21)}
        sharp = dict(mixture_choice_probabilities(utilities, 0.11, 0.0))
        mixed = dict(mixture_choice_probabilities(utilities, 0.11, 0.15))

        self.assertAlmostEqual(sum(mixed.values()), 1.0)
        # A pure fitted board-follower assigns near-zero probability to deep
        # reaches; the mixture restores a real snipe hazard down the board.
        self.assertGreater(mixed["p20"], 10 * sharp["p20"])
        self.assertLess(mixed["p1"], sharp["p1"])
        with self.assertRaisesRegex(ValueError, "reach_rate"):
            mixture_choice_probabilities(utilities, 0.11, 1.0)

    def test_positional_caps_block_impossible_rosters_with_a_fallback(self):
        caps = position_caps({
            "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1,
        })
        self.assertEqual(caps, {"K": 1, "DEF": 1, "QB": 2, "TE": 3})
        self.assertEqual(position_caps({"QB": 1, "SUPER_FLEX": 1})["QB"], 3)

        snapshot = {
            "source": "fantasypros:sleeper",
            "observations": [
                {"canonical_player_id": player_id, "adp": adp}
                for player_id, adp in (("k1", 1.0), ("k2", 2.0), ("wr1", 3.0))
            ],
        }
        choice = sleeper_adp_choice(
            snapshot,
            temperature=0.11,
            reach_rate=0.15,
            positions={"k1": "K", "k2": "K", "wr1": "WR"},
            slot_counts={"WR": 1, "K": 1},
        )
        rosters = ((1, ("k1",)), (2, ()))

        capped = choice(1, 5, rosters, frozenset({"k2", "wr1"}))
        self.assertEqual(set(capped), {"wr1"})
        # A roster left with only capped players falls back to the board.
        self.assertEqual(set(choice(1, 5, rosters, frozenset({"k2"}))), {"k2"})
        uncapped = choice(2, 5, rosters, frozenset({"k2", "wr1"}))
        self.assertEqual(set(uncapped), {"k2", "wr1"})
        self.assertAlmostEqual(
            sum(math.exp(value) for value in uncapped.values()), 1.0
        )

    def test_choice_callback_and_backtest_use_only_pre_draft_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with closing(sqlite3.connect(database_path)) as database, database:
                database.executescript(SCHEMA)
                for number in range(1, 4):
                    database.execute(
                        "INSERT INTO canonical_players VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (f"sleeper:{number}", f"Player {number}", f"player{number}",
                         "WR", None, 1, "now"),
                    )
                database.execute(
                    """
                    INSERT INTO market_snapshots VALUES (
                        'snapshot', 'fantasypros:sleeper', 'fantasypros_api', 2026,
                        'PPR', '1qb', NULL, '2026-08-13T12:00:00+00:00',
                        '2026-08-13T13:00:00+00:00', 'raw', 'raw.json', 3
                    )
                    """
                )
                database.executemany(
                    "INSERT INTO market_observations VALUES ('snapshot', ?, ?, ?, NULL, NULL, NULL)",
                    ((f"sleeper:{number}", str(number), float(number)) for number in range(1, 4)),
                )
                roster_slots = json.dumps([["qb", 1], ["rb", 2], ["wr", 2]])
                for draft_id, started_at in (
                    ("before-retrieval", "2026-08-13T12:30:00+00:00"),
                    ("after-retrieval", "2026-08-13T14:00:00+00:00"),
                ):
                    start_ms = int(datetime.fromisoformat(started_at).timestamp() * 1000)
                    database.execute(
                        """
                        INSERT INTO historical_drafts (
                            draft_id, season, status, draft_type, scoring_type,
                            team_count, roster_slots_json, start_time, context_hash,
                            included, exclusion_reasons_json, raw_snapshot_hash,
                            raw_snapshot_path, observed_at
                        ) VALUES (?, 2026, 'complete', 'snake', 'ppr', 2, ?, ?,
                                  'context', 1, '[]', 'history', 'history.json', 'now')
                        """,
                        (draft_id, roster_slots, start_ms),
                    )
                    database.executemany(
                        """
                        INSERT INTO historical_picks (
                            draft_id, pick_no, canonical_player_id, source_player_id,
                            position, is_keeper
                        ) VALUES (?, ?, ?, ?, 'WR', 0)
                        """,
                        (
                            (draft_id, 1, "sleeper:2", "2"),
                            (draft_id, 2, "sleeper:1", "1"),
                        ),
                    )

            snapshot = {
                "source": "fantasypros:sleeper",
                "observations": [
                    {"canonical_player_id": f"sleeper:{number}", "adp": number}
                    for number in range(1, 4)
                ],
            }
            choice = sleeper_adp_choice(snapshot)
            utilities = choice(1, 1, (), frozenset({"sleeper:1", "sleeper:3"}))
            selected = load_league_market_snapshot(
                {
                    "roster_positions": ["QB", "RB", "WR"],
                    "scoring_settings": {"rec": 1},
                },
                season=2026,
                at=datetime(2026, 8, 13, 14, tzinfo=timezone.utc),
                storage_dir=directory,
            )
            result = backtest_sleeper_adp(storage_dir=directory)

            self.assertGreater(utilities["sleeper:1"], utilities["sleeper:3"])
            self.assertEqual(selected["snapshot"]["snapshot_id"], "snapshot")
            self.assertEqual(
                sleeper_adp_model_version(selected["snapshot"]),
                "sleeper-adp-inverse-rank-v1:snapshot",
            )
            self.assertEqual(result["historical_drafts_considered"], 2)
            self.assertEqual(result["drafts_with_time_local_snapshot"], 1)
            self.assertEqual(result["scored_picks"], 2)
            self.assertEqual(result["top_1_accuracy"], 0.5)
            self.assertEqual(result["top_3_accuracy"], 1.0)
            self.assertEqual(result["contexts"], {"exact/1qb/PPR": 1})
            self.assertEqual(result["skipped_drafts"], {"no_time_local_snapshot": 1})
            self.assertFalse(result["model"]["decision_eligible"])


if __name__ == "__main__":
    unittest.main()
