import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import quote

from .client import HeavyRateLimitError, SleeperClient
from .ingest import (
    TARGET_SEASONS,
    ingest_bracket,
    ingest_draft,
    ingest_drafts,
    ingest_league,
    ingest_league_users,
    ingest_matchups,
    ingest_picks,
    ingest_players,
    ingest_rosters,
    ingest_traded_picks,
    ingest_user_leagues,
)
from .outcomes import compute_team_seasons


class DatasetCrawler:
    def __init__(
        self,
        store,
        *,
        requests_per_minute=750,
        timeout=30,
        max_retries=5,
        client=None,
        refresh=False,
    ):
        self.store = store
        self.client = client or SleeperClient(
            requests_per_minute=requests_per_minute,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.refresh = refresh
        self.stop_event = threading.Event()

    def seed(self, usernames, seasons=TARGET_SEASONS):
        seeded = []
        for username in usernames:
            normalized = username.strip()
            if not normalized:
                continue
            endpoint = f"user/{quote(normalized, safe='')}"
            payload, raw_hash = self._fetch(endpoint, "seed", normalized)
            if not isinstance(payload, dict) or not payload.get("user_id"):
                raise ValueError(f"Sleeper user not found: {normalized}")
            user_id = self.store.add_seed(payload, raw_hash, seasons=seasons)
            seeded.append({"username": normalized, "user_id": user_id})
        return seeded

    def run_discovery(self, *, max_depth=2, workers=8, limit=None, progress=None):
        self._enqueue_existing_owner_tasks(max_depth, limit)
        self.store.recover_stale()
        return self._run_parallel_queue(
            claim=lambda: self.store.claim_crawl(max_depth),
            process=lambda task: self._process_discovery(task, max_depth),
            finish=lambda task: self.store.finish_crawl(task["id"]),
            fail=lambda task, error: self.store.fail_crawl(task["id"], error),
            workers=workers,
            limit=limit,
            progress=progress,
            label="discovery tasks",
        )

    def _enqueue_existing_owner_tasks(self, max_depth, task_limit):
        task_limit = task_limit or 5_000
        owner_limit = max(
            1,
            (task_limit + len(TARGET_SEASONS) - 1) // len(TARGET_SEASONS),
        )
        self.store.enqueue_existing_owner_tasks(
            max_depth,
            TARGET_SEASONS,
            owner_limit=owner_limit,
        )

    def run_hydration(self, *, workers=4, limit=None, progress=None):
        self.store.recover_stale()
        return self._run_parallel_queue(
            claim=self.store.claim_hydration,
            process=self._process_hydration,
            finish=lambda task: self.store.finish_hydration(task["league_id"], task["season"]),
            fail=lambda task, error: self.store.fail_hydration(task["league_id"], task["season"], error),
            workers=workers,
            limit=limit,
            progress=progress,
            label="league hydrations",
        )

    def refresh_players(self):
        endpoint = "players/nfl"
        payload, raw_hash = self._fetch(endpoint, "players", "nfl")
        ingest_players(self.store, payload, raw_hash)
        return len(payload)

    def _run_parallel_queue(
        self,
        *,
        claim,
        process,
        finish,
        fail,
        workers,
        limit,
        progress,
        label,
    ):
        if workers < 1:
            raise ValueError("workers must be positive")
        started = time.monotonic()
        baseline_status = self.store.status()
        baseline_client = self.client.metrics()
        submitted = completed = failed = 0
        heavy_rate_limit = None
        futures = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while not self.stop_event.is_set():
                while len(futures) < workers and (limit is None or submitted < limit):
                    task = claim()
                    if task is None:
                        break
                    futures[executor.submit(process, task)] = task
                    submitted += 1
                if not futures:
                    break
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    task = futures.pop(future)
                    try:
                        future.result()
                    except HeavyRateLimitError as error:
                        fail(task, error)
                        failed += 1
                        heavy_rate_limit = error
                        self.stop_event.set()
                    except Exception as error:
                        fail(task, error)
                        failed += 1
                    else:
                        finish(task)
                        completed += 1
                    total = completed + failed
                    if progress and (total == 1 or total % 25 == 0):
                        elapsed = time.monotonic() - started
                        current_status = self.store.status()
                        client_metrics = self.client.metrics()
                        progress(
                            label,
                            completed,
                            failed,
                            elapsed,
                            {
                                "requests": client_metrics["requests"] - baseline_client["requests"],
                                "failed_attempts": client_metrics["failed_attempts"] - baseline_client["failed_attempts"],
                                "users": current_status["users"],
                                "new_users": current_status["users"] - baseline_status["users"],
                                "league_seasons": current_status["league_seasons"],
                                "new_leagues": current_status["league_seasons"] - baseline_status["league_seasons"],
                            },
                        )
                if limit is not None and submitted >= limit and not futures:
                    break
            for future, task in list(futures.items()):
                if future.cancel():
                    fail(task, "cancelled after rate-limit circuit breaker")
                    failed += 1
                    continue
                try:
                    future.result()
                except Exception as error:
                    fail(task, error)
                    failed += 1
                else:
                    finish(task)
                    completed += 1
        result = {
            "submitted": submitted,
            "completed": completed,
            "failed": failed,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stopped_for_rate_limit": heavy_rate_limit is not None,
        }
        client_metrics = self.client.metrics()
        result["requests"] = client_metrics["requests"] - baseline_client["requests"]
        result["failed_attempts"] = client_metrics["failed_attempts"] - baseline_client["failed_attempts"]
        if heavy_rate_limit:
            result["stop_reason"] = str(heavy_rate_limit)
        return result

    def _process_discovery(self, task, max_depth):
        task_type = task["task_type"]
        entity_id = task["entity_id"]
        season = task["season"]
        if task_type == "user_leagues":
            endpoint = f"user/{entity_id}/leagues/nfl/{season}"
        elif task_type == "league":
            endpoint = f"league/{entity_id}"
        elif task_type == "league_rosters":
            endpoint = f"league/{entity_id}/rosters"
        elif task_type == "league_users":
            endpoint = f"league/{entity_id}/users"
        elif task_type == "league_drafts":
            endpoint = f"league/{entity_id}/drafts"
        else:
            raise ValueError(f"unknown crawl task type: {task_type}")
        payload, raw_hash = self._fetch(endpoint, "crawl_queue", str(task["id"]))
        if task_type == "user_leagues":
            ingest_user_leagues(self.store, payload, raw_hash, task, max_depth=max_depth)
        elif task_type == "league":
            ingest_league(self.store, payload, raw_hash, task)
        elif task_type == "league_rosters":
            ingest_rosters(self.store, payload, raw_hash, task, max_depth=max_depth)
        elif task_type == "league_users":
            ingest_league_users(self.store, payload, raw_hash)
        else:
            ingest_drafts(self.store, payload, raw_hash, task)

    def _process_hydration(self, task):
        league_id = task["league_id"]
        season = int(task["season"])
        queue_key = f"{league_id}:{season}"
        discovery_context = {
            "entity_id": league_id,
            "season": season,
            "depth": 0,
            "seed_user_id": None,
            "mechanism": "hydration",
        }
        endpoint = f"league/{league_id}"
        league, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
        ingest_league(self.store, league, raw_hash, discovery_context)

        endpoint = f"league/{league_id}/rosters"
        rosters, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
        ingest_rosters(self.store, rosters, raw_hash, discovery_context, max_depth=0)

        endpoint = f"league/{league_id}/users"
        users, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
        ingest_league_users(self.store, users, raw_hash)

        endpoint = f"league/{league_id}/drafts"
        drafts, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
        ingest_drafts(self.store, drafts, raw_hash, discovery_context)
        for draft_summary in drafts:
            draft_id = str(draft_summary["draft_id"])
            endpoint = f"draft/{draft_id}"
            draft, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
            ingest_draft(self.store, draft, raw_hash, fallback_season=season)

            endpoint = f"draft/{draft_id}/picks"
            picks, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
            ingest_picks(self.store, picks, raw_hash, draft_id)

            endpoint = f"draft/{draft_id}/traded_picks"
            traded, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
            ingest_traded_picks(self.store, traded, raw_hash, draft_id)

        for bracket_type in ("winners", "losers"):
            endpoint = f"league/{league_id}/{bracket_type}_bracket"
            bracket, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
            ingest_bracket(self.store, bracket, raw_hash, league_id, season, bracket_type)

        settings = league.get("settings") or {}
        last_scored_leg = int(settings.get("last_scored_leg") or 0)
        for week in range(1, last_scored_leg + 1):
            endpoint = f"league/{league_id}/matchups/{week}"
            matchups, raw_hash = self._fetch(endpoint, "hydration_queue", queue_key)
            ingest_matchups(self.store, matchups, raw_hash, league_id, season, week)
        compute_team_seasons(self.store, league_id, season)

    def _fetch(self, endpoint, queue_name, queue_key):
        if not self.refresh:
            cached = self.store.cached_payload(endpoint)
            if cached is not None:
                return cached

        def record(attempt, status, error):
            self.store.record_failure(queue_name, queue_key, endpoint, attempt, status, error)

        try:
            payload = self.client.get(endpoint, on_failure=record)
        except HeavyRateLimitError as error:
            self.store.record_failure(queue_name, queue_key, endpoint, 0, error.status, str(error))
            raise
        raw_hash = self.store.save_raw(endpoint, payload)
        return payload, raw_hash


def progress_line(label, completed, failed, elapsed, metrics):
    total = completed + failed
    task_rate = total / elapsed * 60 if elapsed else 0.0
    request_intervals = max(0, metrics["requests"] - 1)
    request_rate = request_intervals / elapsed * 60 if elapsed else 0.0
    league_rate = metrics["new_leagues"] / elapsed * 60 if elapsed else 0.0
    print(
        f"{label}: {completed} complete, {failed} failed · "
        f"{task_rate:.1f} tasks/min · "
        f"HTTP {metrics['requests']} total, {request_rate:.1f} RPM, "
        f"{metrics['failed_attempts']} retry failures · "
        f"users {metrics['users']:,} (+{metrics['new_users']:,}) · "
        f"league-seasons {metrics['league_seasons']:,} "
        f"(+{metrics['new_leagues']:,}, {league_rate:.1f} new/min)",
        flush=True,
    )
