"""Multi-Tier Caching Engine (L1 In-Memory LRU + L2 Persistent SQLite WAL Cache)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from entity_standardizer.models import StandardizedPhone


def make_cache_key(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
    addr_iso2: str | None = None,
    addr_state: str | None = None,
) -> str:
    """Create a deterministic cache key for a phone standardization request."""
    p = "" if raw_phone is None else str(raw_phone).strip()
    c = "" if country is None else str(country).strip().upper()
    d = str(default_country).strip().upper()
    ai = "" if addr_iso2 is None else str(addr_iso2).strip().upper()
    ast = "" if addr_state is None else str(addr_state).strip().upper()
    if ai or ast:
        return f"{d}|{c}|{ai}|{ast}|{p}"
    return f"{d}|{c}|{p}"


class LRUCache:
    """Thread-safe L1 in-memory Least-Recently-Used cache for StandardizedPhone records."""

    def __init__(self, max_size: int = 4096) -> None:
        self.max_size = max(1, max_size)
        self._store: OrderedDict[str, StandardizedPhone] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> StandardizedPhone | None:
        with self._lock:
            if key not in self._store:
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return self._store[key]

    def set(self, key: str, value: StandardizedPhone) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = value
                return
            if len(self._store) >= self.max_size:
                self._store.popitem(last=False)
                self.evictions += 1
            self._store[key] = value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
            self.evictions = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._store),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
            }


class SQLiteCache:
    """Persistent L2 SQLite cache for StandardizedPhone records."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._closed = True
        self.hits = 0
        self.misses = 0
        self._conn = self._open_conn()
        self._closed = False

    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS phone_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        current_pid = os.getpid()
        if current_pid != self._pid:
            self._conn.close()
            self._pid = current_pid
            self._conn = self._open_conn()
            self._closed = False
        return self._conn

    def get(self, key: str) -> StandardizedPhone | None:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT payload_json FROM phone_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                self.misses += 1
                return None
            self.hits += 1
            data = json.loads(row[0])
            data["risk_flags"] = tuple(data.get("risk_flags", ()))
            data["healing_actions"] = tuple(data.get("healing_actions", ()))
            return StandardizedPhone(**data)

    def set(self, key: str, value: StandardizedPhone) -> None:
        payload = json.dumps(value.to_dict())
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO phone_cache (cache_key, payload_json) VALUES (?, ?)",
                (key, payload),
            )
            conn.commit()

    def clear(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM phone_cache")
            conn.commit()
            self.hits = 0
            self.misses = 0

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

    def __enter__(self) -> SQLiteCache:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


class MultiTierCache:
    """Two-tier (L1 in-memory LRU + optional L2 SQLite) cache manager."""

    def __init__(self, l1_max_size: int = 4096, sqlite_path: str | Path | None = None) -> None:
        self.l1 = LRUCache(max_size=l1_max_size)
        self.l2 = SQLiteCache(sqlite_path) if sqlite_path is not None else None

    def get(self, key: str) -> StandardizedPhone | None:
        res = self.l1.get(key)
        if res is not None:
            return res
        if self.l2 is not None:
            res2 = self.l2.get(key)
            if res2 is not None:
                self.l1.set(key, res2)
                return res2
        return None

    def set(self, key: str, value: StandardizedPhone) -> None:
        self.l1.set(key, value)
        if self.l2 is not None:
            self.l2.set(key, value)

    def clear(self) -> None:
        self.l1.clear()
        if self.l2 is not None:
            self.l2.clear()

    def close(self) -> None:
        """Close the L2 SQLite cache if enabled."""
        if self.l2 is not None:
            self.l2.close()

    def __enter__(self) -> MultiTierCache:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def stats(self) -> dict[str, Any]:
        return {
            "l1": self.l1.stats(),
            "l2_enabled": self.l2 is not None,
            "l2_hits": self.l2.hits if self.l2 is not None else 0,
            "l2_misses": self.l2.misses if self.l2 is not None else 0,
        }


_DEFAULT_CACHE = MultiTierCache()


def get_default_cache() -> MultiTierCache:
    """Return the active global MultiTierCache instance."""
    return _DEFAULT_CACHE


def configure_cache(l1_max_size: int = 4096, sqlite_path: str | Path | None = None) -> MultiTierCache:
    """Reconfigure and replace the global MultiTierCache instance."""
    global _DEFAULT_CACHE
    _DEFAULT_CACHE.close()
    _DEFAULT_CACHE = MultiTierCache(l1_max_size=l1_max_size, sqlite_path=sqlite_path)
    return _DEFAULT_CACHE


def clear_cache() -> None:
    """Clear all entries from the active global phone and address caches."""
    _DEFAULT_CACHE.clear()
    from entity_standardizer.address import cache as _addr_cache

    if _addr_cache._DEFAULT_CACHE is not None:
        _addr_cache._DEFAULT_CACHE.clear()


def get_cache_stats() -> dict[str, Any]:
    """Return hit/miss/size metrics from active global caches across phone and address."""
    phone_stats = _DEFAULT_CACHE.stats()
    stats: dict[str, Any] = {
        "l1": phone_stats["l1"],
        "l2_enabled": phone_stats["l2_enabled"],
        "l2_hits": phone_stats["l2_hits"],
        "l2_misses": phone_stats["l2_misses"],
        "phone": phone_stats,
    }
    from entity_standardizer.address import cache as _addr_cache

    if _addr_cache._DEFAULT_CACHE is not None:
        stats["address"] = _addr_cache._DEFAULT_CACHE.get_stats()
    else:
        stats["address"] = {
            "enabled": True,
            "l1": {"size": 0, "hits": 0, "misses": 0, "evictions": 0, "hit_rate": 0.0},
            "l2": {"size": 0, "hits": 0, "misses": 0, "evictions": 0, "hit_rate": 0.0},
            "total_lookups": 0,
            "total_hits": 0,
            "overall_hit_rate": 0.0,
        }
    return stats


