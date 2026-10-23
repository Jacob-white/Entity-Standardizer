"""Observability helpers: request IDs, latency histogram, bounded counters, access log lines, optional tracing.

Access-log lines carry no address content, no query strings and never credentials.
"""

import bisect
import json
import logging
import re
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, ContextManager, Dict, List, Optional, Tuple

DEFAULT_BUCKETS: Tuple[float, ...] = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

access_logger = logging.getLogger("address_standardizer.access")


def route_label(request: Any) -> str:
    """Matched route template (e.g. "/v1/batch"), or "unmatched" for 404s: never the raw client path."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


def new_request_id() -> str:
    return uuid.uuid4().hex


def sanitize_request_id(value: Optional[str]) -> Optional[str]:
    """A client-supplied request ID if it is short and log-safe, else None (the caller generates one)."""
    if value and _REQUEST_ID_RE.match(value):
        return value
    return None


class LatencyHistogram:
    """Cumulative Prometheus-style histogram. Not thread-safe on its own; the owner serializes access."""

    def __init__(self, buckets: Tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        self.buckets = buckets
        self._counts: List[int] = [0] * (len(buckets) + 1)  # last slot is +Inf
        self.sum = 0.0
        self.count = 0

    def observe(self, seconds: float) -> None:
        self._counts[bisect.bisect_left(self.buckets, seconds)] += 1
        self.sum += seconds
        self.count += 1

    def cumulative(self) -> List[Tuple[str, int]]:
        """``[(le_label, cumulative_count), ...]`` ending with ``("+Inf", total)``."""
        out: List[Tuple[str, int]] = []
        running = 0
        for index, bound in enumerate(self.buckets):
            running += self._counts[index]
            out.append((repr(bound), running))
        out.append(("+Inf", running + self._counts[-1]))
        return out


def bounded_increment(counts: Dict[str, int], label: str, cap: int, overflow: str = "other") -> None:
    """Increment ``counts[label]``; once ``cap`` distinct labels exist new ones are folded into ``overflow``."""
    if label not in counts and len(counts) >= cap:
        label = overflow
    counts[label] = counts.get(label, 0) + 1


def log_access(fields: Dict[str, Any]) -> None:
    """Emit one structured JSON access-log line on the ``address_standardizer.access`` logger."""
    if not access_logger.isEnabledFor(logging.INFO):
        return
    access_logger.info(json.dumps(fields, separators=(",", ":"), sort_keys=True))


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def load_tracer() -> Any:
    """An OpenTelemetry tracer if the optional ``opentelemetry`` API is importable, else None."""
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    return trace.get_tracer("address_standardizer")


def start_span(tracer: Any, name: str) -> ContextManager[Any]:
    """Context manager yielding a span (or None when tracing is off)."""
    if tracer is None:
        return nullcontext(None)
    return tracer.start_as_current_span(name)
