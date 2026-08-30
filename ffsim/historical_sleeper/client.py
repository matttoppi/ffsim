import json
import random
import threading
import time
from collections import deque
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://api.sleeper.app/v1"


class SleeperRequestError(RuntimeError):
    def __init__(self, path, message, *, status=None):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.status = status


class HeavyRateLimitError(SleeperRequestError):
    pass


class RateLimiter:
    """Thread-safe, evenly spaced global request limiter."""

    def __init__(self, requests_per_minute=750, *, clock=time.monotonic, sleep=time.sleep):
        if not 1 <= requests_per_minute < 1000:
            raise ValueError("requests_per_minute must be between 1 and 999")
        self.interval = 60.0 / requests_per_minute
        self.clock = clock
        self.sleep = sleep
        self._next_request = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = self.clock()
            delay = max(0.0, self._next_request - now)
            self._next_request = max(now, self._next_request) + self.interval
        if delay:
            self.sleep(delay)


class SleeperClient:
    def __init__(
        self,
        requests_per_minute=750,
        *,
        timeout=30,
        max_retries=5,
        backoff_base=1.0,
        rate_limit_stop_count=3,
        opener=urlopen,
        sleep=time.sleep,
        clock=time.monotonic,
        rng=None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.rate_limit_stop_count = rate_limit_stop_count
        self.opener = opener
        self.sleep = sleep
        self.clock = clock
        self.rng = rng or random.Random()
        self.limiter = RateLimiter(requests_per_minute, clock=clock, sleep=sleep)
        self._rate_limits = deque()
        self._rate_limit_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self.request_count = 0
        self.failure_count = 0

    def get(self, path, *, on_failure=None):
        path = path.lstrip("/")
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            with self._metrics_lock:
                self.request_count += 1
            try:
                request = Request(
                    f"{BASE_URL}/{path}",
                    headers={"User-Agent": "ffsim-historical-sleeper/1"},
                )
                with self.opener(request, timeout=self.timeout) as response:
                    payload = response.read()
                return json.loads(payload)
            except HTTPError as error:
                status = error.code
                retry_after = _retry_after_seconds(error.headers, time.time())
                error.read()
                error.close()
                if status == 429:
                    self._record_rate_limit(path)
                retryable = status == 429 or 500 <= status < 600
                message = f"HTTP {status}"
            except (TimeoutError, URLError, OSError) as error:
                status = None
                retry_after = None
                retryable = True
                message = f"{type(error).__name__}: {error}"
            except json.JSONDecodeError as error:
                status = None
                retry_after = None
                retryable = True
                message = f"invalid JSON: {error}"

            with self._metrics_lock:
                self.failure_count += 1
            if on_failure is not None:
                on_failure(attempt + 1, status, message)
            if not retryable or attempt == self.max_retries:
                raise SleeperRequestError(path, message, status=status)
            ceiling = min(60.0, self.backoff_base * (2**attempt))
            delay = ceiling * (0.5 + self.rng.random() * 0.5)
            self.sleep(max(delay, retry_after or 0.0))

        raise AssertionError("unreachable")

    def metrics(self):
        with self._metrics_lock:
            return {
                "requests": self.request_count,
                "failed_attempts": self.failure_count,
            }

    def _record_rate_limit(self, path):
        now = self.clock()
        with self._rate_limit_lock:
            self._rate_limits.append(now)
            while self._rate_limits and self._rate_limits[0] < now - 60:
                self._rate_limits.popleft()
            if len(self._rate_limits) >= self.rate_limit_stop_count:
                raise HeavyRateLimitError(
                    path,
                    f"stopping after {len(self._rate_limits)} HTTP 429 responses in 60 seconds",
                    status=429,
                )


def _retry_after_seconds(headers, now):
    if not headers:
        return None
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - now)
        except (TypeError, ValueError, OverflowError):
            return None
