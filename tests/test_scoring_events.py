import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tools.extract_scoring_events import COLUMNS, extract


class ScoringEventExtractionTest(unittest.TestCase):
    def test_play_by_play_events_are_credited_to_players_and_teams(self):
        defaults = {column: 0 for column in COLUMNS}
        defaults.update(season=2025, season_type="REG", week=1, game_id="game")
        plays = [
            {**defaults, "pass_touchdown": 1, "touchdown": 1, "yards_gained": 55, "td_player_id": "receiver"},
            {**defaults, "interception": 1, "return_touchdown": 1, "passer_player_id": "quarterback"},
            {
                **defaults,
                "special_teams_play": 1,
                "fumble": 1,
                "posteam": "BUF",
                "defteam": "MIA",
                "fumbled_1_team": "MIA",
                "forced_fumble_player_1_team": "BUF",
                "forced_fumble_player_1_player_id": "forcer",
                "fumble_recovery_1_team": "BUF",
                "fumble_recovery_1_player_id": "recoverer",
            },
            {**defaults, "posteam": "BUF", "defteam": "MIA", "punt_blocked": 1},
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "pbp.csv")
            pd.DataFrame(plays, columns=COLUMNS).to_csv(source, index=False)
            players, teams = extract(source, 2025)

        receiver = players[players.player_id == "receiver"].iloc[0]
        quarterback = players[players.player_id == "quarterback"].iloc[0]
        self.assertEqual((receiver.receiving_tds_40_plus, receiver.receiving_tds_50_plus), (1, 1))
        self.assertEqual(quarterback.pick_sixes_thrown, 1)
        self.assertEqual(players[players.player_id == "forcer"].iloc[0].special_teams_fumbles_forced, 1)
        self.assertEqual(players[players.player_id == "recoverer"].iloc[0].special_teams_fumbles_recovered, 1)
        self.assertEqual(teams[teams.team == "MIA"].iloc[0].blocked_kicks, 1)
        self.assertEqual(teams[teams.team == "BUF"].iloc[0].defense_special_teams_fumbles_recovered, 1)


if __name__ == "__main__":
    unittest.main()
