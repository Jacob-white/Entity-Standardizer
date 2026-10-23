"""In-process rate limiting: per-identity token bucket plus an optional per-identity daily quota.

Both classes take an injectable clock so tests never depend on wall time. State is **per process**: with N workers
each worker enforces its own limit (see docs/operations.md; use the gateway for a global limit).
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Optional

SECONDS_PER_DAY = 86400


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: float  # seconds until a retry can succeed (0 when allowed)


class TokenBucketLimiter:
    """Token bucket per identity: ``burst`` capacity, refilled at ``rate_per_second``, one token per request.

    Memory is bounded two ways: buckets idle long enough to be full again are dropped (lossless), and the table is
    capped at ``max_buckets`` (the least recently used bucket is dropped; that identity gets a fresh full bucket).
    """

    def __init__(
        self,
        rate_per_second: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        max_buckets: int = 10000,
    ) -> None:
        self.rate = rate_per_second
        self.burst = max(1, burst)
        self._clock = clock
        self._max = max(1, max_buckets)
        self._idle_ttl = self.burst / self.rate
        self._buckets: "OrderedDict[str, tuple]" = OrderedDict()  # identity -> (tokens, last_seen)
        self._lock = threading.Lock()
        self._last_sweep = clock()

    def acquire(self, identity: str) -> Decision:
        with self._lock:
            now = self._clock()
            self._sweep(now)
            entry = self._buckets.get(identity)
            if entry is None:
                if len(self._buckets) >= self._max:
                    self._buckets.popitem(last=False)
                tokens = float(self.burst)
            else:
                tokens = min(float(self.burst), entry[0] + max(0.0, now - entry[1]) * self.rate)
            allowed = tokens >= 1.0
            retry_after = 0.0
            if allowed:
                tokens -= 1.0
            else:
                retry_after = (1.0 - tokens) / self.rate
            self._buckets[identity] = (tokens, now)
            self._buckets.move_to_end(identity)
            return Decision(allowed, self.burst, int(tokens), retry_after)

    def _sweep(self, now: float) -> None:
        """Drop buckets untouched for a full refill period (oldest first; the table is ordered by last use)."""
        if now - self._last_sweep < self._idle_ttl:
            return
        self._last_sweep = now
        while self._buckets:
            identity, (_, last_seen) = next(iter(self._buckets.items()))
            if now - last_seen < self._idle_ttl:
                break
            del self._buckets[identity]

    def __len__(self) -> int:
        return len(self._buckets)


class DailyQuota:
    """Requests per identity per UTC day. The counter table resets at midnight UTC and is bounded in size."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.time, max_identities: int = 10000) -> None:
        self.limit = limit
        self._clock = clock
        self._max = max(1, max_identities)
        self._day = int(clock() // SECONDS_PER_DAY)
        self._counts: "OrderedDict[str, int]" = OrderedDict()
        self._lock = threading.Lock()

    def consume(self, identity: str) -> Decision:
        with self._lock:
            now = self._clock()
            day = int(now // SECONDS_PER_DAY)
            if day != self._day:
                self._day = day
                self._counts.clear()
            used = self._counts.get(identity, 0)
            if used >= self.limit:
                return Decision(False, self.limit, 0, (day + 1) * SECONDS_PER_DAY - now)
            if identity not in self._counts and len(self._counts) >= self._max:
                self._counts.popitem(last=False)
            self._counts[identity] = used + 1
            return Decision(True, self.limit, self.limit - used - 1, 0.0)


def client_ip(peer: Optional[str], forwarded_for: str, trust_forwarded_for: bool) -> str:
    """Client identity for unauthenticated limiting.

    With ``trust_forwarded_for`` the **last** X-Forwarded-For entry is used: it is the one appended by the nearest
    trusted proxy, whereas earlier entries are client-controlled. Without it the socket peer is used.
    """
    if trust_forwarded_for:
        last = forwarded_for.split(",")[-1].strip()
        if last:
            return last
    return peer or "unknown"
