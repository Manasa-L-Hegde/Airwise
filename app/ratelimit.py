"""In-memory sliding-window rate limiter (per client key)."""

from __future__ import annotations

import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float = 60.0, max_keys: int = 10_000) -> None:
        self._limit = limit
        self._window = window_s
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        if len(self._hits) > self._max_keys:
            self._prune(cutoff)
        return True

    def _prune(self, cutoff: float) -> None:
        stale = [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
