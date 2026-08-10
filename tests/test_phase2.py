import unittest

import numpy as np

from ffsim.loaders.pff import PFFLoader, canonical_team
from ffsim.models.player import Player
from ffsim.scoring import ScoringSettings, score_raw_stats
from ffsim.simulation.empirical import EmpiricalLibrary, PLAYER_COLUMNS, validate_2026_schedule


SCORING = ScoringSettings(
    {
        "pass_yd": 0.04,
        "pass_td": 4,
        "pass_int": -2,
        "rush_yd": 0.1,
        "rush_td": 6,
        "rec": 1,
        "rec_yd": 0.1,
        "rec_td": 6,
        "fum_lost": -2,
        "fgm": 3,
        "fgm_50p": 2,
        "fgmiss": -1,
        "xpm": 1,
        "xpmiss": -1,
        "sack": 1,
        "int": 2,
        "fum_rec": 2,
        "safe": 2,
        "def_td": 6,
        "def_st_td": 6,
        "pts_allow_0": 10,
        "pts_allow_1_6": 7,
        "pts_allow_7_13": 4,
        "pts_allow_14_20": 1,
        "pts_allow_28_34": -1,
        "pts_allow_35p": -4,
    }
)


class EmpiricalSamplingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = EmpiricalLibrary()
        cls.projections = PFFLoader.get_and_clean_data()

    def projected_player(self, position, player_id=None, games=None):
        row = self.projections[self.projections.position == position].iloc[0].to_dict()
        if games is not None:
            scale = games / float(row["games"])
            for column, value in list(row.items()):
                if column not in {"fantasyPointsRank", "byeWeek", "games"}:
                    try:
                        row[column] = float(value) * scale
                    except (TypeError, ValueError):
                        pass
            row["games"] = games
        row.update(
            player_id=player_id or f"rookie-{position}",
            full_name=f"Test {position}",
            projection_match_status="matched",
            pff_projections=row.copy(),
        )
        player = Player(row)
        player.initialize_empirical_sampler(self.library)
        return player

    def test_2026_schedule_and_projection_byes_agree(self):
        byes = validate_2026_schedule()
        self.assertEqual(len(byes), 32)
        self.assertTrue(all(week is not None for week in byes.values()))
        projection_byes = {
            canonical_team(team): int(group.byeWeek.iloc[0])
            for team, group in self.projections.groupby("teamName")
        }
        self.assertEqual(byes, projection_byes)

    def test_snap_join_retains_played_but_zero_rows_and_id_coverage(self):
        rows = self.library.player_rows
        missing_stats = rows[rows.weekly_join == "left_only"]
        self.assertGreater(len(missing_stats), 0)
        self.assertTrue((missing_stats[list(PLAYER_COLUMNS)].sum(axis=1) == 0).all())
        self.assertGreater(rows.gsis_id.notna().mean(), 0.99)
        self.assertGreater((rows.sleeper_id != "").mean(), 0.98)

    def test_every_recentered_component_pool_has_mean_one(self):
        for key, pool in self.library.player_pools.items():
            for column in (column for column in pool if column.startswith("z_")):
                if pool[column].notna().any():
                    with self.subTest(pool=key, stat=column):
                        self.assertAlmostEqual(pool[column].mean(), 1, places=12)
        for key, pool in self.library.team_pools.items():
            for column in (column for column in pool if column.startswith("z_")):
                if pool[column].notna().any():
                    with self.subTest(pool=key, stat=column):
                        self.assertAlmostEqual(pool[column].mean(), 1, places=12)

    def test_joint_samples_satisfy_logical_constraints(self):
        rng = np.random.default_rng(20)
        for position in ("QB", "RB", "WR", "TE"):
            subject = self.projected_player(position)
            for _ in range(5_000):
                stats = self.library.sample(subject, rng)
                self.assertLessEqual(stats["receptions"], stats["targets"])
                self.assertLessEqual(stats["completions"], stats["attempts"])
                if stats["receptions"] == 0:
                    self.assertEqual((stats["receiving_yards"], stats["receiving_tds"]), (0, 0))

    def test_empirical_kicker_and_defense_keep_shape_and_center(self):
        rng = np.random.default_rng(21)
        for position in ("K", "DEF"):
            subject = self.projected_player(position)
            scores = np.array([
                score_raw_stats(self.library.sample(subject, rng), position, SCORING)
                for _ in range(100_000)
            ])
            with self.subTest(position=position):
                self.assertAlmostEqual(scores.mean(), subject.expected_weekly_score(SCORING), delta=subject.expected_weekly_score(SCORING) * 0.01)
                self.assertGreater(scores.std(), 0)
                self.assertGreater(np.mean(scores == 0), 0)
        defense = self.projected_player("DEF")
        defense_scores = [score_raw_stats(self.library.sample(defense, rng), "DEF", SCORING) for _ in range(20_000)]
        self.assertLess(min(defense_scores), 0)
        self.assertGreater(max(defense_scores), 20)

    def test_empirical_sampling_and_availability_preserve_reduced_total(self):
        subject = self.projected_player("WR", games=8.5)
        totals = []
        for stream in np.random.SeedSequence(22).spawn(5_000):
            rng = np.random.default_rng(stream)
            subject.prepare_availability(range(1, 19), rng)
            totals.append(sum(subject.calculate_score(SCORING, week, rng) for week in range(1, 19)))
            subject.reset_season_stats()
        target = subject.projected_season_score(SCORING)
        self.assertAlmostEqual(np.mean(totals), target, delta=target * 0.01)

    def test_logical_correction_rates_are_reported(self):
        report = self.library.correction_report()
        self.assertGreater(report["samples"], 0)
        self.assertEqual(sorted(report["corrections"]), list(report["corrections"]))


if __name__ == "__main__":
    unittest.main()
