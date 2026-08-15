import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError

from ffsim.draft_intel.history import _normalize_draft, load_history, summarize_history
from ffsim.draft_intel.identity import canonical_players_from_cache
from ffsim.draft_intel.storage import (
    _context_hash,
    load_sleeper_identity_map,
    store_history,
)


class DraftHistoryTest(unittest.TestCase):
    def test_shared_drafts_and_picks_are_fetched_and_counted_once(self):
        fixture = Path(__file__).parent / "fixtures" / "sleeper_history.json"
        responses = json.loads(fixture.read_text())
        calls = []

        def fetch(path):
            calls.append(path)
            if path == "league/le":
                raise HTTPError(path, 404, "Not Found", None, None)
            return responses[path]

        history = load_history(
            "target",
            (2026, 2025),
            fetch,
            canonical_player_ids={
                "9509": "sleeper:9509",
                "6803": "sleeper:6803",
            },
        )
        summary = summarize_history(history, 2026)

        self.assertEqual([manager.user_id for manager in history.managers], ["u1", "u2"])
        self.assertEqual(history.draft_discoveries, 6)
        self.assertEqual(len(history.drafts), 5)
        self.assertEqual(len(history.leagues), 4)
        self.assertEqual(len(history.picks), 5)
        self.assertEqual(history.drafts[0].manager_ids, ("u1", "u2"))
        self.assertEqual(calls.count("draft/a"), 1)
        self.assertEqual(calls.count("draft/a/picks"), 1)
        self.assertEqual(calls.count("league/la"), 1)
        self.assertEqual(summary["duplicate_discoveries_removed"], 1)
        self.assertEqual(summary["shared_drafts"], 1)
        self.assertEqual(summary["keeper_picks"], 1)
        self.assertEqual(summary["model_eligible_picks"], 1)
        self.assertEqual(summary["draft_classification"], {
            "included": 1,
            "excluded": 4,
            "exclusion_reasons": {
                "auction": 1,
                "best_ball": 1,
                "dynasty": 2,
                "non_snake": 1,
                "not_complete": 1,
                "unknown_best_ball": 1,
                "unknown_league_context": 1,
            },
        })
        self.assertEqual(summary["league_context"], {
            "unique_leagues": 5,
            "loaded_leagues": 4,
            "leagues_unknown_best_ball": 1,
            "drafts_missing_context": 1,
        })
        self.assertEqual(
            summary["canonical_player_coverage"]["all_picks"]["pick_match_rate"],
            0.4,
        )
        self.assertEqual(
            summary["canonical_player_coverage"]["model_eligible_picks"]["pick_match_rate"],
            1.0,
        )
        self.assertEqual(history.drafts[0].player_type, 0)
        self.assertIn(("super_flex", 1), history.drafts[0].roster_slots)
        self.assertEqual(history.drafts[0].draft_order, (("u1", 1), ("u2", 2)))
        self.assertEqual(history.drafts[0].slot_to_roster_id, ((1, 2), (2, 3)))
        self.assertEqual(history.leagues[0].max_keepers, 1)
        self.assertFalse(history.leagues[0].best_ball)
        self.assertEqual(history.leagues[0].scoring_settings, (
            ("bonus_rec_rb", 0.0),
            ("bonus_rec_te", 0.5),
            ("pass_td", 4.0),
            ("rec", 1.0),
        ))
        self.assertEqual(
            [draft.draft_provenance for draft in history.drafts],
            ["real_league", "mock", "cpu_bot", "mock", "real_league"],
        )
        self.assertEqual(
            _normalize_draft(
                {**responses["draft/e"], "league_id": None},
                (),
            ).draft_provenance,
            "unknown",
        )
        self.assertTrue(history.drafts[0].included)
        self.assertEqual(history.drafts[1].exclusion_reasons, ("auction", "best_ball"))

    def test_context_hash_covers_scoring_team_and_roster_context(self):
        fixture = Path(__file__).parent / "fixtures" / "sleeper_history.json"
        responses = json.loads(fixture.read_text())
        history = load_history("target", (2026, 2025), responses.__getitem__)
        draft = history.drafts[0]
        league = history.leagues[0]
        baseline = _context_hash(draft, league)

        variants = (
            _context_hash(
                draft,
                replace(league, scoring_settings=(("rec", 0.5),)),
            ),
            _context_hash(replace(draft, teams=12), league),
            _context_hash(
                replace(draft, roster_slots=tuple(
                    (position, count + 1 if position == "wr" else count)
                    for position, count in draft.roster_slots
                )),
                league,
            ),
            _context_hash(
                draft,
                replace(league, roster_positions=(*league.roster_positions, "WR")),
            ),
        )
        self.assertTrue(all(value != baseline for value in variants))
        self.assertEqual(len(set(variants)), len(variants))

    def test_persistence_is_idempotent_and_preserves_raw_source_ids(self):
        fixture = Path(__file__).parent / "fixtures" / "sleeper_history.json"
        responses = json.loads(fixture.read_text())
        canonical_players = canonical_players_from_cache([
            {
                "sleeper_id": "9509",
                "full_name": "Player One Jr.",
                "position": "RB",
                "team": "ARZ",
            },
            {
                "sleeper_id": "6803",
                "full_name": "Player Two",
                "position": "WR",
                "team": "PIT",
            },
        ])
        canonical_ids = {
            player.sleeper_id: player.canonical_player_id
            for player in canonical_players
        }
        captured = {}
        history = load_history(
            "target",
            (2026, 2025),
            responses.__getitem__,
            canonical_player_ids=canonical_ids,
            raw_responses=captured,
        )

        with tempfile.TemporaryDirectory() as directory:
            first = store_history(
                history,
                captured,
                canonical_players,
                storage_dir=directory,
                observed_at="2026-08-12T12:00:00+00:00",
            )
            with closing(sqlite3.connect(first["database_path"])) as database, database:
                database.execute(
                    "INSERT INTO managers VALUES (?, ?, ?, ?)",
                    ("other-target", "Other", "earlier", "earlier"),
                )
                database.execute(
                    "INSERT INTO historical_draft_managers VALUES (?, ?, ?, ?)",
                    ("a", "other-target", 3, 4),
                )
            raw_before = Path(first["raw_snapshot_path"]).read_bytes()
            second = store_history(
                history,
                captured,
                canonical_players[:1],
                storage_dir=directory,
                observed_at="2026-08-12T13:00:00+00:00",
            )

            self.assertEqual(first["raw_snapshot_hash"], second["raw_snapshot_hash"])
            self.assertEqual(Path(first["raw_snapshot_path"]).read_bytes(), raw_before)
            raw = json.loads(Path(first["raw_snapshot_path"]).read_text())
            self.assertEqual(
                raw["responses"]["draft/a/picks"][1]["player_id"],
                "retired-player",
            )
            self.assertEqual(
                raw["responses"]["league/la"]["scoring_settings"],
                {
                    "rec": 1,
                    "pass_td": "4",
                    "bonus_rec_te": 0.5,
                    "bonus_rec_rb": 0,
                },
            )
            with closing(sqlite3.connect(first["database_path"])) as database:
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM historical_drafts").fetchone()[0],
                    5,
                )
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM historical_leagues").fetchone()[0],
                    4,
                )
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM historical_picks").fetchone()[0],
                    5,
                )
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM canonical_players").fetchone()[0],
                    2,
                )
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM player_external_ids").fetchone()[0],
                    2,
                )
                self.assertEqual(
                    database.execute(
                        "SELECT COUNT(*) FROM historical_draft_managers WHERE draft_id = 'a'"
                    ).fetchone()[0],
                    3,
                )
                self.assertEqual(
                    database.execute(
                        """
                        SELECT source_player_id, canonical_player_id
                        FROM historical_picks
                        WHERE source_player_id = 'retired-player'
                        """
                    ).fetchone(),
                    ("retired-player", None),
                )
                self.assertEqual(
                    database.execute(
                        """
                        SELECT draft_slot, roster_id
                        FROM historical_draft_managers
                        WHERE draft_id = 'a' AND manager_id = 'u1'
                        """
                    ).fetchone(),
                    (1, 2),
                )
                self.assertEqual(
                    database.execute(
                        """
                        SELECT normalized_name, nfl_team, active
                        FROM canonical_players
                        WHERE canonical_player_id = 'sleeper:9509'
                        """
                    ).fetchone(),
                    ("playerone", "ARI", 0),
                )
                self.assertEqual(
                    database.execute(
                        "SELECT best_ball, max_keepers FROM historical_leagues WHERE league_id = 'la'"
                    ).fetchone(),
                    (0, 1),
                )
                self.assertEqual(
                    database.execute(
                        "SELECT scoring_settings_json FROM historical_leagues WHERE league_id = 'la'"
                    ).fetchone()[0],
                    '{"bonus_rec_rb":0.0,"bonus_rec_te":0.5,"pass_td":4.0,"rec":1.0}',
                )
                self.assertEqual(
                    database.execute(
                        "SELECT draft_provenance FROM historical_drafts ORDER BY draft_id"
                    ).fetchall(),
                    [
                        ("real_league",),
                        ("mock",),
                        ("cpu_bot",),
                        ("mock",),
                        ("real_league",),
                    ],
                )
            self.assertEqual(
                load_sleeper_identity_map(directory),
                {"9509": "sleeper:9509", "6803": "sleeper:6803"},
            )

    def test_legacy_history_schema_migrates_and_reingestion_replaces_defaults(self):
        fixture = Path(__file__).parent / "fixtures" / "sleeper_history.json"
        responses = json.loads(fixture.read_text())
        captured = {}
        history = load_history(
            "target",
            (2026, 2025),
            responses.__getitem__,
            raw_responses=captured,
        )

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "history.sqlite3"
            with closing(sqlite3.connect(database_path)) as database, database:
                database.executescript(
                    """
                    CREATE TABLE historical_leagues (
                        league_id TEXT PRIMARY KEY,
                        season INTEGER,
                        status TEXT NOT NULL,
                        name TEXT NOT NULL,
                        best_ball INTEGER,
                        max_keepers INTEGER,
                        league_type INTEGER,
                        roster_positions_json TEXT NOT NULL,
                        raw_snapshot_hash TEXT NOT NULL,
                        raw_snapshot_path TEXT NOT NULL,
                        observed_at TEXT NOT NULL
                    );
                    CREATE TABLE historical_drafts (
                        draft_id TEXT PRIMARY KEY,
                        league_id TEXT,
                        season INTEGER NOT NULL,
                        season_type TEXT,
                        status TEXT NOT NULL,
                        draft_type TEXT NOT NULL,
                        scoring_type TEXT,
                        team_count INTEGER,
                        rounds INTEGER,
                        player_type INTEGER,
                        roster_slots_json TEXT NOT NULL,
                        created_at INTEGER,
                        start_time INTEGER,
                        last_picked_at INTEGER,
                        context_hash TEXT NOT NULL,
                        included INTEGER NOT NULL,
                        exclusion_reasons_json TEXT NOT NULL,
                        raw_snapshot_hash TEXT NOT NULL,
                        raw_snapshot_path TEXT NOT NULL,
                        observed_at TEXT NOT NULL
                    );
                    INSERT INTO historical_leagues (
                        league_id, status, name, roster_positions_json,
                        raw_snapshot_hash, raw_snapshot_path, observed_at
                    ) VALUES ('la', 'old', 'Old', '[]', 'old', 'old', 'old');
                    INSERT INTO historical_drafts (
                        draft_id, season, status, draft_type, roster_slots_json,
                        context_hash, included, exclusion_reasons_json,
                        raw_snapshot_hash, raw_snapshot_path, observed_at
                    ) VALUES (
                        'a', 2025, 'old', 'snake', '[]', 'legacy', 0, '[]',
                        'old', 'old', 'old'
                    );
                    """
                )

            store_history(
                history,
                captured,
                (),
                storage_dir=directory,
                observed_at="2026-08-12T12:00:00+00:00",
            )

            with closing(sqlite3.connect(database_path)) as database:
                league_columns = {
                    row[1] for row in database.execute("PRAGMA table_info(historical_leagues)")
                }
                draft_columns = {
                    row[1] for row in database.execute("PRAGMA table_info(historical_drafts)")
                }
                self.assertIn("scoring_settings_json", league_columns)
                self.assertIn("draft_provenance", draft_columns)
                self.assertEqual(
                    database.execute(
                        "SELECT scoring_settings_json FROM historical_leagues WHERE league_id = 'la'"
                    ).fetchone()[0],
                    '{"bonus_rec_rb":0.0,"bonus_rec_te":0.5,"pass_td":4.0,"rec":1.0}',
                )
                provenance, context_hash = database.execute(
                    "SELECT draft_provenance, context_hash FROM historical_drafts WHERE draft_id = 'a'"
                ).fetchone()
                self.assertEqual(provenance, "real_league")
                self.assertNotEqual(context_hash, "legacy")

    def test_conflicting_cached_player_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Conflicting cached players"):
            canonical_players_from_cache([
                {"sleeper_id": "1", "full_name": "One", "position": "WR"},
                {"sleeper_id": "1", "full_name": "Other", "position": "WR"},
            ])

    def test_conflicting_duplicate_pick_fails_closed(self):
        draft = {
            "draft_id": "a", "season": "2026", "status": "complete", "type": "snake",
        }
        pick = {"draft_id": "a", "pick_no": 1, "player_id": "1"}
        responses = {
            "league/target/users": [{"user_id": "u1"}],
            "user/u1/drafts/nfl/2026": [draft],
            "draft/a": draft,
            "draft/a/picks": [pick, {**pick, "player_id": "2"}],
        }

        with self.assertRaisesRegex(ValueError, "Conflicting duplicate Sleeper pick a/1"):
            load_history("target", (2026,), responses.__getitem__)


if __name__ == "__main__":
    unittest.main()
