from contextlib import closing, redirect_stdout
import json
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ffsim.__main__ import main
from ffsim.draft_intel.worp import (
    WORP_MODEL_VERSION,
    approve_worp_context,
    fit_worp_calibration,
    load_worp_curve,
    projected_worp,
)


class WORPCalibrationTest(unittest.TestCase):
    def test_fit_requires_explicit_approval_before_live_use(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "history.sqlite"
            artifact_path = Path(directory) / "worp.json"
            _historical_database(database)

            artifact = fit_worp_calibration(
                database,
                output_path=artifact_path,
                min_training_games=1,
                min_validation_games=1,
            )
            unavailable, candidate = load_worp_curve(12, "PPR", artifact_path)
            approve_worp_context(artifact_path, 12, "PPR", "ADR-test")
            curve, status = load_worp_curve(12, "PPR", artifact_path)

            self.assertEqual(artifact["status"], "candidate")
            self.assertIsNone(unavailable)
            self.assertEqual(candidate["status"], "candidate")
            self.assertEqual(status["status"], "validated")
            self.assertEqual(status["decision_reference"], "ADR-test")
            self.assertEqual(status["model_version"], WORP_MODEL_VERSION)
            self.assertGreater(curve.wins_added(5), 0)
            self.assertAlmostEqual(curve.wins_added(-5), -curve.wins_added(5))
            self.assertAlmostEqual(
                projected_worp(85, 17, 14, curve),
                curve.wins_added(5) * 14,
            )
            self.assertEqual(
                json.loads(artifact_path.read_text())["source"]["games"],
                2_000,
            )

    def test_loader_fails_closed_for_insufficient_or_wrong_context(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "history.sqlite"
            artifact_path = Path(directory) / "worp.json"
            _historical_database(database)
            fit_worp_calibration(
                database,
                output_path=artifact_path,
                min_training_games=10_000,
                min_validation_games=10_000,
            )

            curve, status = load_worp_curve(12, "PPR", artifact_path)
            missing, missing_status = load_worp_curve(10, "HALF", artifact_path)

            self.assertIsNone(curve)
            self.assertEqual(status["status"], "insufficient_data")
            self.assertIsNone(missing)
            self.assertEqual(missing_status["status"], "context_missing")
            with self.assertRaisesRegex(ValueError, "candidate gates"):
                approve_worp_context(artifact_path, 12, "PPR", "ADR-test")

    def test_cli_fits_and_approves_an_exact_context(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "history.sqlite"
            artifact_path = Path(directory) / "worp.json"
            _historical_database(database)

            output = StringIO()
            with (
                patch(
                    "sys.argv",
                    [
                        "ffsim",
                        "worp-calibrate",
                        "--database",
                        str(database),
                        "--output",
                        str(artifact_path),
                    ],
                ),
                redirect_stdout(output),
            ):
                main()
            self.assertEqual(json.loads(output.getvalue())["status"], "candidate")

            output = StringIO()
            with (
                patch(
                    "sys.argv",
                    [
                        "ffsim",
                        "worp-approve",
                        "--output",
                        str(artifact_path),
                        "--worp-team-count",
                        "12",
                        "--worp-scoring",
                        "PPR",
                        "--decision-reference",
                        "ADR-test",
                    ],
                ),
                redirect_stdout(output),
            ):
                main()
            self.assertEqual(json.loads(output.getvalue())["status"], "validated")

    def test_fit_rejects_a_non_collector_database(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "empty.sqlite"
            sqlite3.connect(database).close()

            with self.assertRaisesRegex(ValueError, "missing tables"):
                fit_worp_calibration(
                    database,
                    output_path=Path(directory) / "out.json",
                )


def _historical_database(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE league_seasons (
                league_id TEXT NOT NULL,
                season INTEGER NOT NULL,
                total_rosters INTEGER,
                playoff_week_start INTEGER,
                last_scored_leg INTEGER,
                scoring_format TEXT NOT NULL,
                is_candidate INTEGER NOT NULL
            );
            CREATE TABLE weekly_matchups (
                league_id TEXT NOT NULL,
                season INTEGER NOT NULL,
                week INTEGER NOT NULL,
                roster_id INTEGER NOT NULL,
                matchup_id INTEGER,
                points REAL,
                custom_points REAL
            );
            CREATE TABLE quality_flags (
                scope TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                severity TEXT NOT NULL
            );
            """
        )
        margins = (-10, -5, 0, 5, 10)
        for league_index in range(20):
            league_id = f"league-{league_index}"
            connection.execute(
                "INSERT INTO league_seasons VALUES (?, 2025, 12, 15, 17, 'PPR', 1)",
                (league_id,),
            )
            for repeat in range(20):
                for matchup_index, margin in enumerate(margins, 1):
                    matchup_id = repeat * len(margins) + matchup_index
                    left = 100 + margin / 2
                    right = 100 - margin / 2
                    connection.executemany(
                        "INSERT INTO weekly_matchups VALUES (?, 2025, 1, ?, ?, ?, NULL)",
                        (
                            (league_id, matchup_id * 2 - 1, matchup_id, left),
                            (league_id, matchup_id * 2, matchup_id, right),
                        ),
                    )
        connection.commit()


if __name__ == "__main__":
    unittest.main()
