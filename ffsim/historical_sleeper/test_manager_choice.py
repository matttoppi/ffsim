import unittest

import numpy as np

from .manager_choice import (
    MANAGER_CHOICE_VERSION,
    personalize_choice_probabilities,
)


class ManagerChoiceTest(unittest.TestCase):
    def model(self):
        return {
            "population_position_factors": np.ones(7),
            "manager_factors": {
                "manager": {
                    "training_picks": 80,
                    "position_factors": np.asarray([1.0, 2.0, 0.5, 1.0, 1.0, 1.0, 1.0]),
                }
            },
        }

    def test_supported_manager_reweights_and_normalizes_position_mass(self):
        result = personalize_choice_probabilities(
            self.model(),
            "manager",
            ["QB", "RB", "WR"],
            [0.2, 0.4, 0.4],
        )

        self.assertEqual(result["status"], "personalized")
        self.assertEqual(result["training_picks"], 80)
        self.assertEqual(result["model_version"], MANAGER_CHOICE_VERSION)
        self.assertAlmostEqual(result["probabilities"].sum(), 1.0)
        self.assertGreater(result["probabilities"][1], 0.4)
        self.assertLess(result["probabilities"][2], 0.4)

    def test_unknown_manager_uses_population_without_guessing_identity(self):
        result = personalize_choice_probabilities(
            self.model(),
            "unknown",
            ["QB", "RB"],
            [0.25, 0.75],
        )

        self.assertEqual(result["status"], "population")
        np.testing.assert_allclose(result["probabilities"], [0.25, 0.75])

    def test_rejects_unaligned_or_unnormalized_probabilities(self):
        with self.assertRaisesRegex(ValueError, "must align"):
            personalize_choice_probabilities(
                self.model(), "manager", ["QB"], [0.5, 0.5]
            )
        with self.assertRaisesRegex(ValueError, "normalized"):
            personalize_choice_probabilities(
                self.model(), "manager", ["QB", "RB"], [0.2, 0.2]
            )


if __name__ == "__main__":
    unittest.main()
