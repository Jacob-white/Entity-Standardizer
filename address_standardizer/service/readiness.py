"""Readiness checks behind ``GET /ready`` (liveness stays ``GET /health``).

A check is a zero-argument callable that raises if its dependency is unusable. Failures are reported by name only
("unavailable"); details go to the server log, never to the response.
"""

import logging
from typing import Callable, Dict, Tuple

logger = logging.getLogger("address_standardizer.server")


def _check_cache() -> None:
    from address_standardizer.cache import get_cache_stats

    get_cache_stats()


def _check_ledger() -> None:
    from address_standardizer.audit import get_audit_ledger

    ledger = get_audit_ledger()
    with ledger._lock:
        ledger._get_conn().execute("SELECT 1").fetchone()


def _check_reference_db() -> None:
    from address_standardizer.offline_index import get_default_offline_index

    get_default_offline_index().count()


CHECKS: Dict[str, Callable[[], None]] = {
    "cache": _check_cache,
    "audit_ledger": _check_ledger,
    "reference_db": _check_reference_db,
}


def register_check(name: str, check: Callable[[], None]) -> None:
    """Add (or replace) a readiness check, e.g. for a newly installed reference-data store."""
    CHECKS[name] = check


def run_checks() -> Tuple[bool, Dict[str, str]]:
    results: Dict[str, str] = {}
    for name, check in list(CHECKS.items()):
        try:
            check()
            results[name] = "ok"
        except Exception:
            logger.exception("Readiness check %r failed", name)
            results[name] = "unavailable"
    return all(v == "ok" for v in results.values()), results
