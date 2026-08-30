import unittest

import numpy as np

from .opponent_model import _iter_survival_samples
from .rank20_survival import predict_rank20_survival


class RankTwentySurvivalTest(unittest.TestCase):
    def draft(self):
        player_ids = tuple(f"p{index:02d}" for index in range(1, 26))
        return {
            "draft_id": "draft",
            "team_count": 4,
            "scoring_format": "PPR",
            "player_ids": player_ids,
            "positions": ("WR",) * len(player_ids),
            "adp": np.arange(1, len(player_ids) + 1, dtype=float),
            "index": {
                player_id: index for index, player_id in enumerate(player_ids)
            },
            "picks": (
                {"pick_no": 1, "roster_id": 1, "player_id": "p01"},
                {"pick_no": 2, "roster_id": 2, "player_id": "p02"},
                {"pick_no": 3, "roster_id": 3, "player_id": "p03"},
                {"pick_no": 4, "roster_id": 4, "player_id": "p04"},
                {"pick_no": 5, "roster_id": 1, "player_id": "p05"},
            ),
        }

    def test_default_and_explicit_rank_ten_samples_are_identical(self):
        default = list(_iter_survival_samples(self.draft()))
        explicit = list(_iter_survival_samples(self.draft(), 10))

        self.assertEqual(default, explicit)

    def test_rank_twenty_extends_without_changing_first_ten(self):
        rank10 = list(_iter_survival_samples(self.draft(), 10))[0]
        rank20 = list(_iter_survival_samples(self.draft(), 20))[0]

        self.assertEqual(len(rank10["players"]), 10)
        self.assertEqual(len(rank20["players"]), 20)
        self.assertEqual(rank20["players"][:10], rank10["players"])
        self.assertEqual(
            [player["rank"] for player in rank20["players"]],
            list(range(1, 21)),
        )

    def test_rank_twenty_predictor_is_bounded_and_rejects_rank_twenty_one(self):
        model = {
            "global": (800, 1_000),
            "pooled": {(20, 4, 3): (70, 100)},
            "position": {(20, 4, 3, "WR"): (60, 90)},
        }
        prediction = predict_rank20_survival(
            model,
            market_rank=20,
            gap=4,
            round_=3,
            position="WR",
        )
        unavailable = predict_rank20_survival(
            model,
            market_rank=21,
            gap=4,
            round_=3,
            position="WR",
        )

        self.assertEqual(prediction["status"], "available")
        self.assertGreater(prediction["probability"], 0)
        self.assertLess(prediction["probability"], 1)
        self.assertLess(prediction["interval_95"][0], prediction["probability"])
        self.assertGreater(prediction["interval_95"][1], prediction["probability"])
        self.assertEqual(unavailable["status"], "unavailable")

    def test_target_count_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "must be positive"):
            list(_iter_survival_samples(self.draft(), 0))


if __name__ == "__main__":
    unittest.main()
