import json
import tempfile
import tracemalloc
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

from .client import HeavyRateLimitError, RateLimiter, SleeperClient
from .crawl import DatasetCrawler, progress_line
from .__main__ import _parser, _poll_status, _run_collection
from .dashboard import crawler_runtime, render_dashboard, sqlite_storage
from .ingest import (
    ingest_bracket,
    ingest_drafts,
    ingest_league_users,
    ingest_matchups,
    ingest_picks,
    ingest_rosters,
    ingest_traded_picks,
    ingest_user_leagues,
)
from .outcomes import compute_team_seasons
from .rebuild import rebuild_from_raw
from .report import quality_report, validate_dataset
from .store import Store


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "complete_league.json"


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class MappingClient:
    def __init__(self, fixture):
        self.fixture = fixture
        self.calls = []

    def get(self, endpoint, *, on_failure=None):
        self.calls.append(endpoint)
        if endpoint == "user/alpha":
            return {"user_id": "u1", "username": "alpha", "display_name": "Alpha"}
        if endpoint == "user/beta":
            return {"user_id": "u2", "username": "beta", "display_name": "Beta"}
        if endpoint.startswith("user/") and "/leagues/nfl/" in endpoint:
            user_id, season = endpoint.split("/")[1], int(endpoint.rsplit("/", 1)[1])
            return [self.fixture["league"]] if user_id == "u1" and season == 2025 else []
        if endpoint == "league/league-2025":
            return self.fixture["league"]
        if endpoint == "league/league-2025/rosters":
            return self.fixture["rosters"]
        if endpoint == "league/league-2025/users":
            return self.fixture["users"]
        if endpoint == "league/league-2025/drafts":
            return [self.fixture["draft"]]
        if endpoint == "draft/draft-2025":
            return self.fixture["draft"]
        if endpoint == "draft/draft-2025/picks":
            return self.fixture["picks"]
        if endpoint == "draft/draft-2025/traded_picks":
            return self.fixture["traded_picks"]
        if endpoint == "league/league-2025/winners_bracket":
            return self.fixture["winners_bracket"]
        if endpoint == "league/league-2025/losers_bracket":
            return self.fixture["losers_bracket"]
        if endpoint.startswith("league/league-2025/matchups/"):
            week = int(endpoint.rsplit("/", 1)[1])
            return self.fixture[f"week_{week}"]
        if endpoint == "league/league-2024":
            previous = deepcopy(self.fixture["league"])
            previous.update({"league_id": "league-2024", "season": "2024", "previous_league_id": None, "draft_id": None})
            return previous
        if endpoint.startswith("league/league-2024/"):
            return []
        raise AssertionError(f"unexpected endpoint {endpoint}")

    def metrics(self):
        return {"requests": len(self.calls), "failed_attempts": 0}


class ClientTests(unittest.TestCase):
    def test_global_rate_limiter_spaces_requests(self):
        clock = FakeClock()
        limiter = RateLimiter(clock=clock, sleep=clock.sleep)
        limiter.wait()
        limiter.wait()
        self.assertAlmostEqual(clock.sleeps, [0.08])

    def test_progress_labels_http_rpm_separately(self):
        stream = StringIO()
        with redirect_stdout(stream):
            progress_line(
                "discovery tasks",
                4,
                0,
                0.24,
                {
                    "requests": 4,
                    "failed_attempts": 0,
                    "users": 10,
                    "new_users": 2,
                    "league_seasons": 20,
                    "new_leagues": 8,
                },
            )
        output = stream.getvalue()
        self.assertIn("HTTP 4 total, 750.0 RPM", output)
        self.assertIn("8, 2000.0 new/min", output)

    def test_transient_http_error_retries(self):
        clock = FakeClock()
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise HTTPError(request.full_url, 503, "busy", {}, BytesIO(b"{}"))
            return FakeResponse({"ok": True})

        client = SleeperClient(
            requests_per_minute=500,
            max_retries=2,
            opener=opener,
            sleep=clock.sleep,
            clock=clock,
        )
        self.assertEqual(client.get("state/nfl"), {"ok": True})
        self.assertEqual(calls, 2)
        self.assertGreaterEqual(sum(clock.sleeps), 0.5)

    def test_repeated_rate_limits_open_circuit(self):
        clock = FakeClock()

        def opener(request, timeout):
            raise HTTPError(request.full_url, 429, "limited", {}, BytesIO(b"{}"))

        client = SleeperClient(
            max_retries=5,
            rate_limit_stop_count=2,
            opener=opener,
            sleep=clock.sleep,
            clock=clock,
        )
        with self.assertRaises(HeavyRateLimitError):
            client.get("state/nfl")


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Store(self.temporary.name)
        self.fixture = json.loads(FIXTURE_PATH.read_text())
        self.task = {
            "entity_id": "u1",
            "season": 2025,
            "depth": 0,
            "seed_user_id": "u1",
            "mechanism": "seed",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def insert_owner_rows(self, count):
        raw_hash = self.store.save_raw(
            "user/u1/leagues/nfl/2025",
            [self.fixture["league"]],
        )
        ingest_user_leagues(
            self.store,
            [self.fixture["league"]],
            raw_hash,
            self.task,
            max_depth=0,
        )
        with self.store.connect() as connection:
            connection.executemany(
                """
                INSERT INTO rosters (
                    league_id, season, roster_id, owner_id, co_owners_json,
                    players_json, starters_json, reserve_json, settings_json,
                    raw_hash, updated_at
                ) VALUES ('league-2025', 2025, ?, ?, '[]', '[]', '[]', '[]',
                          '{}', NULL, '2026-08-27T00:00:00+00:00')
                """,
                [
                    (index + 1, f"owner-{index:05d}")
                    for index in range(count)
                ],
            )

    def ingest_complete_fixture(self):
        league_hash = self.store.save_raw("user/u1/leagues/nfl/2025", [self.fixture["league"]])
        ingest_user_leagues(self.store, [self.fixture["league"]], league_hash, self.task, max_depth=1)
        roster_task = {**self.task, "entity_id": "league-2025"}
        roster_hash = self.store.save_raw("league/league-2025/rosters", self.fixture["rosters"])
        ingest_rosters(self.store, self.fixture["rosters"], roster_hash, roster_task, max_depth=1)
        users_hash = self.store.save_raw("league/league-2025/users", self.fixture["users"])
        ingest_league_users(self.store, self.fixture["users"], users_hash)
        draft_hash = self.store.save_raw("league/league-2025/drafts", [self.fixture["draft"]])
        ingest_drafts(self.store, [self.fixture["draft"]], draft_hash, roster_task)
        picks_hash = self.store.save_raw("draft/draft-2025/picks", self.fixture["picks"])
        ingest_picks(self.store, self.fixture["picks"], picks_hash, "draft-2025")
        traded_hash = self.store.save_raw("draft/draft-2025/traded_picks", self.fixture["traded_picks"])
        ingest_traded_picks(self.store, self.fixture["traded_picks"], traded_hash, "draft-2025")
        for week in (1, 2):
            matchups = self.fixture[f"week_{week}"]
            matchup_hash = self.store.save_raw(f"league/league-2025/matchups/{week}", matchups)
            ingest_matchups(self.store, matchups, matchup_hash, "league-2025", 2025, week)
        for bracket_type in ("winners", "losers"):
            bracket = self.fixture[f"{bracket_type}_bracket"]
            bracket_hash = self.store.save_raw(f"league/league-2025/{bracket_type}_bracket", bracket)
            ingest_bracket(self.store, bracket, bracket_hash, "league-2025", 2025, bracket_type)
        compute_team_seasons(self.store, "league-2025", 2025)

    def test_queue_deduplicates_and_preserves_seasons(self):
        user = {"user_id": "u1", "username": "alpha"}
        raw_hash = self.store.save_raw("user/alpha", user)
        self.store.add_seed(user, raw_hash, seasons=(2024, 2025))
        self.store.add_seed(user, raw_hash, seasons=(2024, 2025))
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT season FROM crawl_queue ORDER BY season"
            ).fetchall()
        self.assertEqual([row["season"] for row in rows], [2024, 2025])
        first = self.store.claim_crawl(2)
        self.store.finish_crawl(first["id"])
        second = self.store.claim_crawl(2)
        self.assertNotEqual(first["season"], second["season"])

    def test_zero_previous_league_id_is_not_queued(self):
        league = deepcopy(self.fixture["league"])
        league["previous_league_id"] = "0"
        raw_hash = self.store.save_raw("user/u1/leagues/nfl/2025", [league])
        ingest_user_leagues(self.store, [league], raw_hash, self.task, max_depth=0)
        with self.store.connect() as connection:
            previous = connection.execute(
                "SELECT previous_league_id FROM league_seasons WHERE league_id = ?",
                (league["league_id"],),
            ).fetchone()[0]
            zero_tasks = connection.execute(
                "SELECT COUNT(*) FROM crawl_queue WHERE entity_id = '0'"
            ).fetchone()[0]
        self.assertIsNone(previous)
        self.assertEqual(zero_tasks, 0)

    def test_increased_depth_queues_retained_roster_owners(self):
        task = {**self.task, "depth": 1}
        raw_hash = self.store.save_raw("user/u1/leagues/nfl/2025", [self.fixture["league"]])
        ingest_user_leagues(self.store, [self.fixture["league"]], raw_hash, task, max_depth=1)
        roster_hash = self.store.save_raw("league/league-2025/rosters", self.fixture["rosters"])
        ingest_rosters(
            self.store,
            self.fixture["rosters"],
            roster_hash,
            {**task, "entity_id": "league-2025"},
            max_depth=1,
        )
        DatasetCrawler(self.store, client=MappingClient(self.fixture)).run_discovery(
            max_depth=2,
            workers=1,
            limit=0,
        )
        with self.store.connect() as connection:
            depth_two = connection.execute(
                "SELECT COUNT(*) FROM crawl_queue WHERE task_type = 'user_leagues' AND depth = 2"
            ).fetchone()[0]
        self.assertEqual(depth_two, 50)

    def test_owner_queue_batches_advance_without_starvation(self):
        self.insert_owner_rows(10)
        added = [
            self.store.enqueue_existing_owner_tasks(
                1,
                (2025,),
                owner_limit=3,
            )
            for _ in range(5)
        ]
        self.assertEqual(added, [3, 3, 3, 1, 0])
        with self.store.connect() as connection:
            connection.execute(
                """
                UPDATE crawl_queue
                SET depth = 3
                WHERE task_type = 'user_leagues'
                  AND entity_id = 'owner-00000'
                  AND season = 2025
                """
            )
        self.assertEqual(
            self.store.enqueue_existing_owner_tasks(1, (2025,), owner_limit=3),
            1,
        )
        with self.store.connect() as connection:
            depth = connection.execute(
                """
                SELECT depth FROM crawl_queue
                WHERE task_type = 'user_leagues'
                  AND entity_id = 'owner-00000'
                  AND season = 2025
                """
            ).fetchone()[0]
        self.assertEqual(depth, 1)

    def test_owner_queue_batch_has_bounded_python_memory(self):
        self.insert_owner_rows(5_000)
        tracemalloc.start()
        added = self.store.enqueue_existing_owner_tasks(
            1,
            (2021, 2022, 2023, 2024, 2025),
            owner_limit=200,
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertEqual(added, 1_000)
        self.assertLess(peak, 5_000_000)

    def test_complete_fixture_maps_draft_and_outcomes(self):
        self.ingest_complete_fixture()
        with self.store.connect() as connection:
            picks = connection.execute(
                "SELECT pick_no, effective_roster_id FROM draft_picks ORDER BY pick_no"
            ).fetchall()
            champion = connection.execute(
                "SELECT * FROM team_seasons WHERE champion = 1"
            ).fetchone()
            runner_up = connection.execute(
                "SELECT * FROM team_seasons WHERE runner_up = 1"
            ).fetchone()
            candidate = connection.execute(
                "SELECT is_candidate FROM league_seasons WHERE league_id = 'league-2025'"
            ).fetchone()[0]
        self.assertEqual(len(picks), 20)
        self.assertEqual((picks[0]["effective_roster_id"], picks[-1]["effective_roster_id"]), (1, 1))
        self.assertEqual(champion["roster_id"], 1)
        self.assertEqual(runner_up["roster_id"], 2)
        self.assertEqual(champion["reported_points_for"], 110.5)
        self.assertEqual(candidate, 1)

    def test_keeper_pick_remains_stored_and_excludes_candidate(self):
        self.fixture["picks"][0]["is_keeper"] = True
        self.ingest_complete_fixture()
        with self.store.connect() as connection:
            pick = connection.execute(
                "SELECT is_keeper FROM draft_picks WHERE draft_id = 'draft-2025' AND pick_no = 1"
            ).fetchone()[0]
            league = connection.execute(
                "SELECT is_candidate, candidate_reasons_json FROM league_seasons WHERE league_id = 'league-2025'"
            ).fetchone()
        self.assertEqual(pick, 1)
        self.assertEqual(league["is_candidate"], 0)
        self.assertIn("keeper_picks", json.loads(league["candidate_reasons_json"]))

    def test_raw_objects_are_content_deduplicated(self):
        first = self.store.save_raw("one", {"value": 1})
        second = self.store.save_raw("two", {"value": 1})
        self.assertEqual(first, second)
        self.assertEqual(self.store.status()["raw_objects"], 1)

    def test_validation_reports_structural_integrity(self):
        self.ingest_complete_fixture()
        report = validate_dataset(self.store)
        self.assertTrue(report["structurally_valid"])
        self.assertEqual(report["draft_picks_collected"], 20)
        self.assertEqual(report["team_seasons_collected"], 10)

    def test_normalized_tables_rebuild_without_network(self):
        self.ingest_complete_fixture()
        rebuilt_dir = Path(self.temporary.name) / "rebuilt"
        result = rebuild_from_raw(self.store, rebuilt_dir)
        self.assertEqual(result["draft_picks"], 20)
        self.assertEqual(result["team_seasons"], 10)

    def test_hydration_candidate_batches_advance_past_existing_queue_rows(self):
        self.ingest_complete_fixture()
        self.assertEqual(self.store.enqueue_hydration_candidates(1), 1)
        league = deepcopy(self.fixture["league"])
        league.update({
            "league_id": "z-league-2021",
            "season": "2021",
            "draft_id": "z-draft-2021",
        })
        draft = deepcopy(self.fixture["draft"])
        draft.update({
            "league_id": "z-league-2021",
            "season": "2021",
            "draft_id": "z-draft-2021",
        })
        task = {**self.task, "entity_id": "z-league-2021", "season": 2021}
        raw_hash = self.store.save_raw("user/u1/leagues/nfl/2021-z", [league])
        ingest_user_leagues(self.store, [league], raw_hash, task, max_depth=0)
        draft_hash = self.store.save_raw("league/z-league-2021/drafts", [draft])
        ingest_drafts(self.store, [draft], draft_hash, task)
        self.assertEqual(
            self.store.enqueue_hydration_candidates(
                1,
                preferred_seasons=(2021,),
            ),
            1,
        )
        with self.store.connect() as connection:
            queued = connection.execute("SELECT COUNT(*) FROM hydration_queue").fetchone()[0]
        self.assertEqual(queued, 2)
        claimed = self.store.claim_hydration()
        self.assertEqual(claimed["season"], 2021)

    def test_collect_runs_seed_discovery_and_hydration(self):
        crawler = DatasetCrawler(self.store, client=MappingClient(self.fixture))
        result = _run_collection(
            crawler,
            self.store,
            SimpleNamespace(
                usernames=["alpha"],
                seasons=(2025,),
                max_depth=0,
                discovery_workers=2,
                hydration_workers=2,
                discovery_batch=100,
                hydration_batch=10,
                target_training_ready=100,
                candidate_buffer=100,
                min_training_ready_per_year=0,
            ),
            progress=None,
        )
        self.assertEqual(result["hydration_completed"], 1)
        self.assertEqual(result["status"]["team_seasons"], 10)
        self.assertEqual(result["status"]["draft_picks"], 20)

    def test_collect_drains_backlog_then_stops_at_training_target(self):
        self.ingest_complete_fixture()
        store = self.store

        class BacklogCrawler:
            stop_event = SimpleNamespace(is_set=lambda: False)

            @staticmethod
            def seed(_usernames, _seasons):
                return []

            @staticmethod
            def run_discovery(**_kwargs):
                raise AssertionError("discovery must pause while backlog is full")

            @staticmethod
            def run_hydration(**_kwargs):
                task = store.claim_hydration()
                store.finish_hydration(task["league_id"], task["season"])
                return {
                    "submitted": 1,
                    "completed": 1,
                    "failed": 0,
                    "elapsed_seconds": 0.0,
                    "stopped_for_rate_limit": False,
                    "requests": 0,
                    "failed_attempts": 0,
                }

        result = _run_collection(
            BacklogCrawler(),
            self.store,
            SimpleNamespace(
                usernames=[],
                seasons=(2025,),
                max_depth=2,
                discovery_workers=1,
                hydration_workers=1,
                discovery_batch=500,
                hydration_batch=50,
                min_training_ready_per_year=1,
                target_training_ready=1,
                candidate_buffer=1,
            ),
            progress=None,
        )
        self.assertEqual(result["discovery_paused_cycles"], 1)
        self.assertEqual(result["hydration_completed"], 1)
        self.assertEqual(result["stop_reason"], "training_ready_target_reached")

    def test_collect_does_not_stop_when_a_requested_year_misses_floor(self):
        self.ingest_complete_fixture()
        self.store.enqueue_hydration_candidates(1)
        task = self.store.claim_hydration()
        self.store.finish_hydration(task["league_id"], task["season"])

        class EmptyCrawler:
            stop_event = SimpleNamespace(is_set=lambda: False)

            @staticmethod
            def seed(_usernames, _seasons):
                return []

            @staticmethod
            def run_discovery(**_kwargs):
                return {
                    "submitted": 0,
                    "completed": 0,
                    "failed": 0,
                    "elapsed_seconds": 0.0,
                    "stopped_for_rate_limit": False,
                    "requests": 0,
                    "failed_attempts": 0,
                }

            run_hydration = run_discovery

        result = _run_collection(
            EmptyCrawler(),
            self.store,
            SimpleNamespace(
                usernames=[],
                seasons=(2021, 2025),
                max_depth=2,
                discovery_workers=1,
                hydration_workers=1,
                discovery_batch=500,
                hydration_batch=50,
                min_training_ready_per_year=1,
                target_training_ready=1,
                candidate_buffer=500,
            ),
            progress=None,
        )
        self.assertEqual(result["stop_reason"], "queues_exhausted")

    def test_status_dashboard_renders_current_counts(self):
        self.ingest_complete_fixture()
        snapshot = {
            "status": self.store.status(),
            "quality": validate_dataset(self.store),
            "runtime": {
                "process_count": 1,
                "rss_bytes": 50 * 1024 * 1024,
                "pids": [123],
            },
            "storage": {
                "main_bytes": 10 * 1024 * 1024,
                "wal_bytes": 2 * 1024 * 1024,
                "shm_bytes": 32 * 1024,
                "total_bytes": 12 * 1024 * 1024 + 32 * 1024,
            },
            "updated_at": "2026-08-27 12:00:00 EDT",
        }
        rendered = render_dashboard(snapshot, 5, width=100)
        self.assertIn("FFSIM / CHAMPIONSHIP DATASET", rendered)
        self.assertIn("0 / 10,000 ready", rendered)
        self.assertIn("10,000 championship events needed", rendered)
        self.assertIn("READY/YR    floor 500", rendered)
        self.assertIn("waiting 1", rendered)
        self.assertIn("RSS 50.0 MiB", rendered)
        self.assertIn("DB 0.013 GB", rendered)
        self.assertIn("refresh 5s", rendered)
        self.assertNotIn("DRAFT DATA", rendered)
        detailed = render_dashboard(snapshot, 5, width=100, verbose=True)
        self.assertIn("DETAILS", detailed)
        self.assertIn("20 picks", detailed)
        self.assertIn("10 team-seasons", detailed)

    def test_collect_defaults_to_balanced_hydration_batch(self):
        args = _parser().parse_args(["collect"])
        self.assertEqual(args.discovery_batch, 500)
        self.assertEqual(args.hydration_batch, 50)
        self.assertEqual(args.rate, 750)
        self.assertEqual(args.target_training_ready, 10_000)
        self.assertEqual(args.candidate_buffer, 500)
        self.assertEqual(args.min_training_ready_per_year, 500)

    def test_training_ready_requires_complete_valid_league(self):
        self.ingest_complete_fixture()
        self.store.enqueue_hydration_candidates(1)
        task = self.store.claim_hydration()
        self.store.finish_hydration(task["league_id"], task["season"])
        self.assertEqual(quality_report(self.store)["training_ready_leagues"], 1)
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO quality_flags (
                    scope, entity_key, code, severity, details_json, detected_at
                ) VALUES (
                    'draft', 'draft-2025', 'test_error', 'error', '{}',
                    '2026-08-27T00:00:00+00:00'
                )
                """
            )
        self.assertEqual(quality_report(self.store)["training_ready_leagues"], 0)

    def test_status_reads_crawler_memory_and_sqlite_files(self):
        runtime = crawler_runtime(
            """
            123 51200 python3 -m ffsim.historical_sleeper collect
            124 10240 python3 -m ffsim.historical_sleeper status
            """
        )
        self.assertEqual(runtime["process_count"], 1)
        self.assertEqual(runtime["rss_bytes"], 50 * 1024 * 1024)
        self.assertEqual(runtime["pids"], [123])
        Path(str(self.store.database_path) + "-wal").write_bytes(b"x" * 1024)
        storage = sqlite_storage(self.store.database_path)
        self.assertGreater(storage["main_bytes"], 0)
        self.assertEqual(storage["wal_bytes"], 1024)
        self.assertEqual(
            storage["total_bytes"],
            storage["main_bytes"] + storage["wal_bytes"] + storage["shm_bytes"],
        )

    def test_status_poller_refreshes_every_five_seconds(self):
        stream = StringIO()
        sleeps = []
        _poll_status(
            self.store,
            interval=5,
            stream=stream,
            sleep=sleeps.append,
            max_updates=2,
            runtime_fn=lambda: {
                "process_count": 0,
                "rss_bytes": 0,
                "pids": [],
            },
            storage_fn=lambda _path: {
                "main_bytes": 1,
                "wal_bytes": 0,
                "shm_bytes": 0,
                "total_bytes": 1,
            },
        )
        self.assertEqual(sleeps, [5])
        self.assertEqual(stream.getvalue().count("FFSIM / CHAMPIONSHIP DATASET"), 2)

    def test_discovery_resumes_and_expands_roster_owners(self):
        client = MappingClient(self.fixture)
        crawler = DatasetCrawler(self.store, client=client)
        crawler.seed(["alpha", "beta"], seasons=(2025,))
        first = crawler.run_discovery(max_depth=1, workers=2, limit=1)
        self.assertEqual(first["completed"], 1)
        second = crawler.run_discovery(max_depth=1, workers=2, limit=100)
        self.assertGreater(second["completed"], 1)
        with self.store.connect() as connection:
            seasons = connection.execute(
                "SELECT COUNT(*) FROM crawl_queue WHERE task_type = 'user_leagues' AND depth = 1"
            ).fetchone()[0]
            leagues = connection.execute("SELECT COUNT(*) FROM league_seasons").fetchone()[0]
        self.assertEqual(seasons, 48)
        self.assertEqual(leagues, 2)


if __name__ == "__main__":
    unittest.main()
