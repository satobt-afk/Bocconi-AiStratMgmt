"""A small rate limiter: at most `limit` actions per `window` seconds for each key.

Keys look like "user_id:chat". The AI runs on a single Mac, so a few requests
per minute per user keep it responsive for everyone and stop one browser (or a
script) from monopolising it.

Counters live in memory: they reset when the server restarts, which is fine
for a single small server. Thread-safe, because FastAPI runs requests in threads.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock  # injectable, so tests can move time forward
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        """Record one action for `key` if it stays within the limit; return whether it is allowed."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window:  # forget actions older than the window
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
