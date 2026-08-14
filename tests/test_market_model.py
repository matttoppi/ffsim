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
    starting_lineup_needs,
)
from ffsim.draft_intel.rollout import (
    _gumbel_choice,
    _pick_header,
    gumbel_score_array,
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
        self.assertEqual(caps, {"K": 1, "DEF": 1, "QB": 2, "TE": 2})
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

        def as_dict(result):
            ids, log_probabilities, _ = result
            return dict(zip(ids.tolist(), log_probabilities.tolist()))

        capped = as_dict(choice(1, 5, rosters, frozenset({"k2", "wr1"})))
        self.assertEqual(set(capped), {"wr1"})
        # A roster left with only capped players falls back to the board.
        self.assertEqual(
            set(as_dict(choice(1, 5, rosters, frozenset({"k2"})))), {"k2"}
        )
        uncapped = as_dict(choice(2, 5, rosters, frozenset({"k2", "wr1"})))
        self.assertEqual(set(uncapped), {"k2", "wr1"})
        self.assertAlmostEqual(
            sum(math.exp(value) for value in uncapped.values()), 1.0
        )

    def test_last_roster_picks_fill_remaining_starter_seats(self):
        slots = {
            "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1,
        }
        positions = {
            "qb": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR",
            "wr2": "WR", "wr3": "WR", "te": "TE", "k": "K",
            "def": "DEF", "wr4": "WR",
        }
        roster = ("qb", "rb1", "rb2", "wr1", "wr2", "wr3", "te")
        self.assertEqual(
            starting_lineup_needs(roster, positions, slots),
            (("K",), ("DEF",)),
        )
        choice = sleeper_adp_choice(
            {
                "source": "fantasypros:sleeper",
                "observations": [
                    {"canonical_player_id": player_id, "adp": adp}
                    for player_id, adp in (("wr4", 1), ("k", 50), ("def", 60))
                ],
            },
            temperature=0.11,
            reach_rate=0.15,
            positions=positions,
            slot_counts=slots,
            roster_sizes={1: 9},
        )

        ids, _, _ = choice(1, 8, ((1, roster),), frozenset({"wr4", "k", "def"}))
        self.assertEqual(set(ids), {"k", "def"})
        ids, _, _ = choice(
            1,
            9,
            ((1, (*roster, "k")),),
            frozenset({"wr4", "def"}),
        )
        self.assertEqual(ids.tolist(), ["def"])

    def test_vectorized_choice_matches_the_dict_reference_and_gumbel_picks(self):
        positions = {}
        observations = []
        for number in range(1, 41):
            player_id = f"p{number}"
            observations.append({"canonical_player_id": player_id, "adp": float(number)})
            positions[player_id] = ("QB", "RB", "WR", "TE", "K", "DEF")[number % 6]
        snapshot = {"source": "fantasypros:sleeper", "observations": observations}
        slot_counts = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1}
        caps = position_caps(slot_counts)

        def reference(roster_id, pick_no, rosters, available):
            board = {
                f"p{number}": -math.log(number)
                for number in range(1, 41)
                if f"p{number}" in available
            }
            counts = {}
            for player_id in dict(rosters)[roster_id]:
                counts[positions[player_id]] = counts.get(positions[player_id], 0) + 1
            eligible = {
                player_id: utility
                for player_id, utility in board.items()
                if (cap := caps.get(positions[player_id])) is None
                or counts.get(positions[player_id], 0) < cap
            }
            return {
                player_id: math.log(probability)
                for player_id, probability in mixture_choice_probabilities(
                    eligible or board, 0.11, 0.15
                )
            }

        choice = sleeper_adp_choice(
            snapshot,
            temperature=0.11,
            reach_rate=0.15,
            positions=positions,
            slot_counts=slot_counts,
        )
        rosters = ((1, ("p1", "p7", "p13")), (2, ()))
        available = frozenset(f"p{number}" for number in range(3, 41))
        for roster_id in (1, 2):
            expected = reference(roster_id, 5, rosters, available)
            ids, log_probabilities, keys = choice(roster_id, 5, rosters, available)
            actual = dict(zip(ids.tolist(), log_probabilities.tolist()))
            self.assertEqual(set(expected), set(actual))
            worst = max(abs(expected[key] - actual[key]) for key in expected)
            self.assertLess(worst, 1e-12)
            # The scalar and vectorized coupled Gumbel argmax must agree for
            # every rollout, on both the reference and the callback outputs.
            for rollout_id in range(200):
                scores = log_probabilities + gumbel_score_array(
                    _pick_header(2026, rollout_id, 5, roster_id), keys
                )
                vectorized_pick = ids[int(scores.argmax())]
                self.assertEqual(
                    vectorized_pick,
                    _gumbel_choice(expected, 2026, rollout_id, 5, roster_id),
                )
                self.assertEqual(
                    vectorized_pick,
                    _gumbel_choice(actual, 2026, rollout_id, 5, roster_id),
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
            ids, log_probabilities, _ = choice(
                1, 1, (), frozenset({"sleeper:1", "sleeper:3"})
            )
            utilities = dict(zip(ids.tolist(), log_probabilities.tolist()))
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
