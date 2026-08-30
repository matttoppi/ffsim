import unittest

import numpy as np

from .roster_manager_choice import (
    ROSTER_MANAGER_CHOICE_VERSION,
    manager_position_factors,
)


class RosterManagerChoiceTest(unittest.TestCase):
    def model(self):
        population = np.ones((7, 3))
        manager = np.ones((7, 3))
        manager[1] = [2.0, 1.0, 0.5]
        return {
            "population_factors": population,
            "manager_factors": {
                "manager": {
                    "training_picks": 90,
                    "position_count_factors": manager,
                }
            },
        }

    def test_manager_factor_uses_current_position_count_bucket(self):
        empty = manager_position_factors(self.model(), "manager", [])
        one_rb = manager_position_factors(self.model(), "manager", ["RB"])
        three_rb = manager_position_factors(
            self.model(), "manager", ["RB", "RB", "RB"]
        )

        self.assertEqual(empty["model_version"], ROSTER_MANAGER_CHOICE_VERSION)
        self.assertEqual(empty["status"], "personalized")
        self.assertEqual(empty["training_picks"], 90)
        self.assertEqual(empty["factors"][1], 2.0)
        self.assertEqual(one_rb["factors"][1], 1.0)
        self.assertEqual(three_rb["factors"][1], 0.5)

    def test_unknown_manager_uses_explicit_population_fallback(self):
        result = manager_position_factors(
            self.model(), "unknown", ["QB", "WR"]
        )

        self.assertEqual(result["status"], "population")
        self.assertEqual(result["training_picks"], 0)
        np.testing.assert_allclose(result["factors"], np.ones(7))


if __name__ == "__main__":
    unittest.main()
