import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ffsim.draft_intel.personal_ranks import (
    ALLOWED_OFFSETS,
    load_offsets,
    offsets_hash,
    save_offset,
)


class PersonalRankStorageTests(unittest.TestCase):
    def test_round_trip_and_zero_clears(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "personal_ranks.json"
            self.assertEqual(load_offsets(path), {})
            save_offset("4046", -25, path)
            save_offset("6786", 10, path)
            self.assertEqual(load_offsets(path), {"4046": -25, "6786": 10})
            save_offset("6786", 0, path)
            self.assertEqual(load_offsets(path), {"4046": -25})

    def test_rejects_offsets_outside_the_button_set(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "personal_ranks.json"
            with self.assertRaisesRegex(ValueError, "offset"):
                save_offset("4046", -12, path)
            with self.assertRaisesRegex(ValueError, "player_id"):
                save_offset("  ", -5, path)
            self.assertEqual(load_offsets(path), {})

    def test_hash_is_stable_and_none_when_empty(self):
        self.assertIsNone(offsets_hash({}))
        first = offsets_hash({"a": -5, "b": 10})
        second = offsets_hash({"b": 10, "a": -5})
        self.assertEqual(first, second)
        self.assertNotEqual(first, offsets_hash({"a": -5}))

    def test_zero_is_the_only_neutral_button(self):
        self.assertIn(0, ALLOWED_OFFSETS)
        self.assertEqual(len(set(ALLOWED_OFFSETS)), len(ALLOWED_OFFSETS))


if __name__ == "__main__":
    unittest.main()
