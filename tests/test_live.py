import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import call, patch

from ffsim.draft_intel.live import (
    PreparedDraft,
    _draft_id,
    _manager_slot,
    _projection_user_policy,
    _refresh_history,
    create_live_executor,
    evaluate_live_candidates,
    evaluate_live_league_equity,
    live_candidate_pool,
    live_league_equity_payload,
    live_state_summary,
    mock_mismatch_reasons,
)
from ffsim.draft_intel.market_model import SLEEPER_ADP_SOURCE
from ffsim.draft_intel.state import DraftPick
from tests.test_decision import draft_state, evaluator


class LiveDraftTest(unittest.TestCase):
    def test_live_league_equity_payload_names_and_ranks_every_roster(self):
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={},
            roster_details={
                roster_id: {
                    "name": f"Team {roster_id}",
                    "draft_slot": roster_id,
                    "is_user": roster_id == 1,
                }
                for roster_id in range(1, 5)
            },
        )

        payload = live_league_equity_payload(
            prepared,
            evaluate_live_league_equity(prepared, draft_state(), 4),
        )

        self.assertEqual(len(payload["rosters"]), 4)
        self.assertEqual({row["name"] for row in payload["rosters"]}, {
            "Team 1", "Team 2", "Team 3", "Team 4",
        })
        self.assertTrue(next(row for row in payload["rosters"] if row["roster_id"] == 1)["is_user"])
        self.assertAlmostEqual(
            sum(row["championship_probability"] for row in payload["rosters"]),
            1.0,
        )

    def test_parallel_candidate_evaluation_matches_the_sequential_batch(self):
        state = draft_state()
        prepared = PreparedDraft(
            summary={},
            live_draft_id="draft",
            league_id=None,
            standalone=True,
            user_roster_id=1,
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": f"p{index}", "adp": float(index)}
                    for index in range(1, 13)
                ],
            },
            evaluator=evaluator(),
            player_details={},
        )
        candidates = ("p1", "p2", "p3")
        sequential = evaluate_live_candidates(prepared, state, 4, candidates)
        with create_live_executor(prepared, workers=2) as executor:
            parallel = evaluate_live_candidates(
                prepared, state, 4, candidates, executor=executor
            )
        self.assertEqual(sequential.rollout_ids, parallel.rollout_ids)
        self.assertEqual(sequential.world_indices, parallel.world_indices)
        self.assertEqual(sequential.draft_model_version, parallel.draft_model_version)
        self.assertTrue(sequential.draft_model_version.endswith(":t0.11:vor2"))
        self.assertEqual(
            {candidate.candidate_id: candidate for candidate in sequential.candidates},
            {candidate.candidate_id: candidate for candidate in parallel.candidates},
        )

    def test_future_user_policy_prefers_value_over_replacement_in_open_slots(self):
        bank = SimpleNamespace(
            player_ids=(
                "qb1", "qb2", "qb3", "rb1", "rb2", "rb3", "wr1", "wr2", "te1",
                "k1", "k2", "k3", "def1", "def2", "def3",
            ),
            player_positions=(
                "QB", "QB", "QB", "RB", "RB", "RB", "WR", "WR", "TE",
                "K", "K", "K", "DEF", "DEF", "DEF",
            ),
            expected_scores=(
                25.0, 24.0, 20.0, 18.0, 15.0, 8.0, 17.0, 9.0, 12.0,
                10.0, 9.0, 8.0, 9.0, 8.0, 7.0,
            ),
            weeks=(1, 2, 3),
        )
        league_evaluator = SimpleNamespace(
            bank=bank,
            roster_ids=(1, 2),
            slot_counts={"QB": 1, "RB": 1, "FLEX": 1, "K": 1, "DEF": 1},
        )
        policy = _projection_user_policy(league_evaluator)

        # Replacement-aware: rb1's value over replacement beats the raw-points
        # leader qb1, so the future self does not stack quarterbacks early.
        empty = ((1, ()), (2, ()))
        utilities = policy(1, 2, empty, frozenset(bank.player_ids))
        self.assertGreater(utilities["rb1"], utilities["qb1"])
        self.assertGreater(utilities["rb1"], utilities["rb2"])

        # Once the only QB slot is filled (QB is not FLEX eligible here), any
        # further QB ranks below even a replacement-level open-slot player.
        after_qb = ((1, ("qb1",)), (2, ()))
        utilities = policy(1, 3, after_qb, frozenset(bank.player_ids) - {"qb1"})
        self.assertNotIn("qb2", utilities)

        # Once the core lineup is full, bench value competes with K/DEF
        # instead of those slots being filled mechanically.
        core_filled = ((1, ("qb1", "rb1", "wr1")), (2, ()))
        available = frozenset(bank.player_ids) - set(core_filled[0][1])
        utilities = policy(1, 4, core_filled, available)
        self.assertGreater(utilities["rb2"], utilities["k1"])

        # There is no reason for the user's rollout policy to draft a backup
        # kicker or defense while replacement streaming exists.
        after_kicker = ((1, (*core_filled[0][1], "k1")), (2, ()))
        utilities = policy(1, 5, after_kicker, available - {"k1"})
        self.assertNotIn("k2", utilities)

    def test_candidate_pool_expands_outward_from_the_current_pick(self):
        adps = {
            "p02": ("RB", 2.0),   # fallen stud
            "p09": ("WR", 9.0),
            "p10": ("WR", 10.0),  # at the anchor
            "p11": ("QB", 11.0),
            "p14": ("QB", 14.0),
            "p30": ("TE", 30.0),
            "p90": ("K", 90.0),   # never forced into the early window
        }
        prepared = SimpleNamespace(
            market_snapshot={
                "source": SLEEPER_ADP_SOURCE,
                "snapshot_id": "snap",
                "observations": [
                    {"canonical_player_id": player_id, "adp": adp}
                    for player_id, (_, adp) in adps.items()
                ],
            },
            evaluator=SimpleNamespace(
                bank=SimpleNamespace(player_ids=tuple(adps)),
            ),
            player_details={
                player_id: {"position": position}
                for player_id, (position, _) in adps.items()
            },
        )
        state = SimpleNamespace(
            available_player_ids=frozenset(adps),
            current_pick_no=10,
        )
        # Pure best-player-available by ADP: fallers first, then the window
        # deepens down the board; the kicker enters only at its ADP depth.
        self.assertEqual(
            live_candidate_pool(prepared, state, 10),
            ["p02", "p09", "p10", "p11", "p14", "p30", "p90"],
        )
        self.assertEqual(live_candidate_pool(prepared, state, 5),
                         ["p02", "p09", "p10", "p11", "p14"])
        self.assertNotIn("p90", live_candidate_pool(prepared, state, 6))
        with self.assertRaisesRegex(ValueError, "No available market players"):
            live_candidate_pool(
                SimpleNamespace(
                    market_snapshot=prepared.market_snapshot,
                    evaluator=prepared.evaluator,
                    player_details={},
                ),
                SimpleNamespace(available_player_ids=frozenset(), current_pick_no=1),
                5,
            )

    def test_live_state_summary_includes_the_full_pick_feed(self):
        prepared = SimpleNamespace(
            user_roster_id=None,
            player_details={
                "p1": {"name": "Alpha One", "position": "WR", "team": "BUF"},
            },
        )
        picks = tuple(
            DraftPick(
                pick_no=pick_no,
                round=1,
                draft_slot=pick_no,
                roster_id=pick_no,
                picked_by=None,
                player_id=f"p{pick_no}",
                position="RB" if pick_no == 2 else None,
                price=None,
            )
            for pick_no in (1, 2)
        )
        state = SimpleNamespace(
            draft_id="draft",
            status="drafting",
            completed_picks=picks,
            current_pick_no=3,
            current_roster_id=3,
        )
        summary = live_state_summary(prepared, state)
        self.assertEqual(summary["completed_picks"], 2)
        self.assertEqual(summary["recent_picks"], [
            {
                "pick_no": 1,
                "round": 1,
                "draft_slot": 1,
                "roster_id": 1,
                "player_id": "p1",
                "name": "Alpha One",
                "position": "WR",
                "team": "BUF",
            },
            {
                "pick_no": 2,
                "round": 1,
                "draft_slot": 2,
                "roster_id": 2,
                "player_id": "p2",
                "name": "p2",
                "position": "RB",
                "team": None,
            },
        ])

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
