import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from ffsim.loaders.fantasypros import (
    combine_with_pff,
    normalize_fantasypros_projections,
)
from ffsim.models.player import Player
from ffsim.loaders.players import PlayerLoader


class FantasyProsProjectionTest(unittest.TestCase):
    def test_fantasypros_counting_stats_win_and_pff_only_supplements(self):
        sleeper = pd.DataFrame([{
            "player_id": "s1",
            "sportradar_id": "sportsdata-1",
        }])
        response = {
            "season": "2026",
            "week": "0",
            "positions": "QB,RB,WR,TE",
            "players": [{
                "fpid": 10,
                "name": "Primary Receiver",
                "position_id": "WR",
                "team_id": "JAC",
                "stats": {
                    "points": 200,
                    "rec_rec": 80,
                    "rec_yds": 1000,
                    "rec_tds": 8,
                },
            }],
        }
        metadata = {"players": [{
            "player_id": 10,
            "sportsdata_player_id": "sportsdata-1",
        }]}

        primary = normalize_fantasypros_projections(
            response,
            metadata,
            sleeper,
            season=2026,
            bye_weeks={"JAX": 8},
        )
        combined = combine_with_pff(primary, {
            "s1": {
                "playerName": "Primary Receiver",
                "teamName": "JAX",
                "position": "WR",
                "recvTargets": 120,
                "recvYds": 900,
            },
            "offense-without-primary": {"position": "RB", "rushYds": 700},
            "kicker": {"position": "K", "games": 17, "byeWeek": 9},
        })
        receiver = combined[combined.sleeperId == "s1"].iloc[0]

        self.assertEqual(primary.attrs["mapping_report"]["mapped"], 1)
        self.assertEqual(receiver.recvYds, 1000)
        self.assertEqual(receiver.recvTargets, 120)
        self.assertEqual(receiver.byeWeek, 8)
        self.assertEqual(set(combined.sleeperId), {"s1", "kicker"})

        player = Player({
            "player_id": "s1",
            "position": "WR",
            "projections": receiver.to_dict(),
            "pff_projections": {"games": 17, "recvYds": 900},
        })
        self.assertEqual(player.season_raw_stats()["receiving_yards"], 1000)

        missing = combine_with_pff(
            pd.DataFrame([{"sleeperId": "s2", "recvYds": float("nan")}]),
            {"s2": {"position": "WR", "recvYds": 700}},
        ).iloc[0]
        self.assertEqual(missing.recvYds, 700)

    def test_setup_refreshes_projection_cache_only_after_twelve_hours(self):
        now = datetime(2026, 8, 13, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            loader = PlayerLoader()
            loader.players_file = Path(directory) / "players.json"
            loader.sleeper_players_file = Path(directory) / "sleeper_players.json"
            loader.projection_report_file = Path(directory) / "projection_matches.json"
            loader.players_file.write_text("[]")
            loader.sleeper_players_file.write_text("{}")
            loader.projection_report_file.write_text(
                '{"fantasypros_projection":{"season":2026,"retrieved_at":"2026-08-13T00:00:00+00:00"}}'
            )

            with patch.object(loader, "refresh", return_value={"fresh": True}) as refresh:
                fresh = loader.refresh_if_stale(now=now + timedelta(hours=11))
                stale = loader.refresh_if_stale(now=now + timedelta(hours=12))

            self.assertFalse(fresh["refreshed"])
            self.assertTrue(stale["refreshed"])
            refresh.assert_called_once_with(
                season=2026,
                retrieved_at=now + timedelta(hours=12),
            )


if __name__ == "__main__":
    unittest.main()
