import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .historical_projections import (
    HISTORICAL_PROJECTION_VERSION,
    import_historical_projection_snapshot,
    load_historical_projection_snapshot,
    projection_rows_for_draft,
)


class HistoricalProjectionTest(unittest.TestCase):
    def fixture(self, root):
        csv_path = root / "source.csv"
        csv_path.write_text(
            "sleeper_id,projected_points,projected_games,position\n"
            "1,250.5,17,QB\n"
            "2,180,16,RB\n"
        )
        evidence = {
            "schema_version": HISTORICAL_PROJECTION_VERSION,
            "source": "licensed-test-source",
            "season": 2024,
            "observed_at": "2024-08-01T12:00:00Z",
            "regular_season_start": "2024-09-05T20:20:00-04:00",
            "timestamp_evidence": "provider snapshot 2024-08-01T12:00:00Z",
            "authorization": "personal non-commercial research",
            "scoring": "PPR",
            "decision_reference": "TEST-APPROVAL",
            "raw_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            "player_id_namespace": "sleeper",
        }
        evidence_path = root / "evidence.json"
        evidence_path.write_text(json.dumps(evidence))
        return csv_path, evidence_path, evidence

    def test_import_is_immutable_hashed_and_draft_time_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path, evidence_path, _ = self.fixture(root)
            output = root / "output"
            manifest = import_historical_projection_snapshot(
                csv_path, evidence_path, output
            )
            snapshot = load_historical_projection_snapshot(
                output / "projection-snapshot.manifest.json"
            )

            self.assertEqual(manifest["status"], "research_approved_source")
            self.assertEqual([row["sleeper_id"] for row in snapshot["rows"]], ["1", "2"])
            self.assertEqual(
                projection_rows_for_draft(snapshot, "2024-08-15T12:00:00Z"),
                snapshot["rows"],
            )
            with self.assertRaisesRegex(ValueError, "not observable"):
                projection_rows_for_draft(snapshot, "2024-07-15T12:00:00Z")
            with self.assertRaises(FileExistsError):
                import_historical_projection_snapshot(csv_path, evidence_path, output)

    def test_import_rejects_unproved_time_hash_and_identity(self):
        cases = (
            ("observed_at", "2024-10-01T00:00:00Z", "predate"),
            ("raw_sha256", "wrong", "raw hash"),
            ("player_id_namespace", "name", "Sleeper player IDs"),
            ("timestamp_evidence", "", "timestamp_evidence is empty"),
        )
        for key, value, message in cases:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                csv_path, evidence_path, evidence = self.fixture(root)
                evidence[key] = value
                evidence_path.write_text(json.dumps(evidence))
                with self.assertRaisesRegex(ValueError, message):
                    import_historical_projection_snapshot(
                        csv_path, evidence_path, root / "output"
                    )

    def test_import_rejects_duplicate_ids_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path, evidence_path, evidence = self.fixture(root)
            csv_path.write_text(
                "sleeper_id,projected_points,position\n"
                "1,200,QB\n"
                "1,180,RB\n"
            )
            evidence["raw_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            evidence_path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "duplicate Sleeper IDs"):
                import_historical_projection_snapshot(
                    csv_path, evidence_path, root / "output"
                )


if __name__ == "__main__":
    unittest.main()
