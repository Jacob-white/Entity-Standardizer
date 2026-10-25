"""
Pluggable cache backends.
=========================
``CacheBackend`` is the small protocol the result cache's second tier speaks: ``get`` / ``set`` / ``delete`` /
``clear`` / ``stats``. Values are ``StandardizedAddress`` objects (or any JSON-serialisable value) and travel as the
JSON payload produced by :func:`serialize_value`, so a backend never has to know the model.

Implementations:

* ``LRUCache`` (process-local, L1) and ``SQLiteCache`` (embedded file or in-memory, L2) in ``entity_standardizer.address.cache``
  already satisfy the protocol; they remain the default and behave exactly as before.
* :class:`RedisCacheBackend` (optional, ``pip install "entity-standardizer[redis]"``) shares results between
  processes and nodes. It is *never* allowed to break standardization: every Redis failure is logged once, counted,
  and treated as a cache miss (reads) or a no-op (writes), and the backend pauses for ``retry_after`` seconds before
  trying the server again.

Select a backend with ``configure_cache(backend=...)`` or the ``ENTITY_STANDARDIZER_CACHE_URL`` environment
variable (with fallback to ``ADDRESS_STANDARDIZER_CACHE_URL``; ``redis://``, ``rediss://`` or ``unix://`` URL). See
``docs/performance.md`` for what is shared between processes and what stays per process.
"""

import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "CacheBackend",
    "RedisCacheBackend",
    "backend_from_url",
    "serialize_value",
    "deserialize_value",
    "REDIS_URL_SCHEMES",
]

REDIS_URL_SCHEMES = ("redis://", "rediss://", "unix://")


@runtime_checkable
class CacheBackend(Protocol):
    """Second-tier result cache. ``get`` returns None for a miss; no method may raise for a backend outage."""

    def get(self, key: str) -> Optional[Any]: ...

    def set(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> bool: ...

    def clear(self) -> None: ...

    def stats(self) -> Dict[str, Any]: ...


_OPTIONAL_METADATA_FIELDS = (
    "deliverability",
    "secondary_prompt_required",
    "prompt_message",
    "suggested_secondary_units",
    "latitude",
    "longitude",
    "precision",
    "accuracy_radius_meters",
    "census_tract",
    "fips_code",
    "is_locality_only",
    "is_city_level",
)


def deserialize_value(payload: str) -> Any:
    """Rebuilds a cached value from its JSON payload (raises on a payload that cannot be rebuilt)."""
    data = json.loads(payload)
    if isinstance(data, dict) and data.get("__class__") == "StandardizedAddress":
        from entity_standardizer.address.models import StandardizedAddress, LocalityOnlyStatus
        status = data["address_status"]
        if status in ("locality_only", "city_level"):
            status = LocalityOnlyStatus("locality_only")
        std = StandardizedAddress(
            street1=data["street1"],
            street2=data["street2"],
            city=data["city"],
            state=data["state"],
            postal_code=data["postal_code"],
            country=data["country"],
            normalized_address_key=data.get("normalized_address_key"),
            address_status=status,
            raw_street_address=data["raw_street_address"],
            is_us=data["is_us"],
            is_private_residence=data.get("is_private_residence", False),
            building_key=data.get("building_key"),
            phonetic_key=data.get("phonetic_key"),
            is_registered_agent_hub=data.get("is_registered_agent_hub", False),
            dependent_locality=data.get("dependent_locality"),
            building_name=data.get("building_name"),
            care_of=data.get("care_of"),
            rooftop_address=data.get("rooftop_address"),
        )
        std.confidence_score = data.get("confidence_score")
        std.routing_tier = data.get("routing_tier")
        std.failure_reason_codes = data.get("failure_reason_codes") or []
        std.rdi = data.get("rdi", "Unknown")
        std.cmra = data.get("cmra", False)
        std.is_cmra = data.get("is_cmra", False)
        std.vacant = data.get("vacant", False)
        std.is_vacant = data.get("is_vacant", False)
        std.dpv_footnotes = data.get("dpv_footnotes") or []
        std.corporate_risk_score = data.get("corporate_risk_score", 0.0)
        std.corporate_risk_flags = data.get("corporate_risk_flags") or []

        for field in _OPTIONAL_METADATA_FIELDS:
            if data.get(field) is not None:
                setattr(std, field, data[field])

        if data.get("audit_record_payload"):
            from entity_standardizer.address.audit import StewardshipAuditRecord
            std.audit_record = StewardshipAuditRecord.from_dict(data["audit_record_payload"])
        elif data.get("audit_id"):
            from entity_standardizer.address.audit import get_audit_ledger
            std.audit_record = get_audit_ledger().get_record(data["audit_id"])

        if data.get("cascade_result_payload"):
            from entity_standardizer.address.cascade import CascadeResult
            c_dict = data["cascade_result_payload"]
            std.cascade_result = CascadeResult(
                latitude=c_dict["latitude"],
                longitude=c_dict["longitude"],
                precision=c_dict["precision"],
                accuracy_radius_meters=c_dict["accuracy_radius_meters"],
                source=c_dict["source"],
                stage=c_dict["stage"],
                census_tract=c_dict.get("census_tract"),
            )
        elif data.get("cascade") and isinstance(data["cascade"], dict):
            from entity_standardizer.address.cascade import CascadeResult
            c_dict = data["cascade"]
            std.cascade_result = CascadeResult(
                latitude=c_dict["latitude"],
                longitude=c_dict["longitude"],
                precision=c_dict["precision"],
                accuracy_radius_meters=c_dict["accuracy_radius_meters"],
                source=c_dict["source"],
                stage=c_dict["stage"],
                census_tract=c_dict.get("census_tract"),
            )

        if data.get("spatial_result_payload"):
            from entity_standardizer.address.models import SpatialResolutionResult
            s_dict = data["spatial_result_payload"]
            std.spatial_result = SpatialResolutionResult(
                latitude=s_dict["latitude"],
                longitude=s_dict["longitude"],
                precision=s_dict["precision"],
                accuracy_radius_meters=s_dict["accuracy_radius_meters"],
                stage=s_dict["stage"],
                source=s_dict["source"],
                h3_res10=s_dict["h3_res10"],
                parcel_id=s_dict.get("parcel_id"),
                execution_time_ms=s_dict.get("execution_time_ms", 0.0),
                metadata=s_dict.get("metadata", {}),
            )
        elif data.get("spatial_result") and isinstance(data["spatial_result"], dict):
            from entity_standardizer.address.models import SpatialResolutionResult
            s_dict = data["spatial_result"]
            std.spatial_result = SpatialResolutionResult(
                latitude=s_dict["latitude"],
                longitude=s_dict["longitude"],
                precision=s_dict["precision"],
                accuracy_radius_meters=s_dict["accuracy_radius_meters"],
                stage=s_dict["stage"],
                source=s_dict["source"],
                h3_res10=s_dict["h3_res10"],
                parcel_id=s_dict.get("parcel_id"),
                execution_time_ms=s_dict.get("execution_time_ms", 0.0),
                metadata=s_dict.get("metadata", {}),
            )

        if data.get("country_iso3"):
            std.country_iso3 = data["country_iso3"]

        return std
    if isinstance(data, dict) and "__cache_value__" in data:
        return data["__cache_value__"]
    return data


def serialize_value(value: Any) -> str:
    """JSON payload for a cache value: StandardizedAddress objects are tagged and expanded; other values are wrapped so
    None / str / int round-trip with their type intact."""
    from entity_standardizer.address.models import StandardizedAddress
    if isinstance(value, StandardizedAddress):
        d = value.as_dict(include_metadata=True)
        d["__class__"] = "StandardizedAddress"
        if value.audit_record is not None and hasattr(value.audit_record, "as_dict"):
            d["audit_record_payload"] = value.audit_record.as_dict()
        if value.cascade_result is not None and hasattr(value.cascade_result, "as_dict"):
            d["cascade_result_payload"] = value.cascade_result.as_dict()
        if value.spatial_result is not None and hasattr(value.spatial_result, "as_dict"):
            d["spatial_result_payload"] = value.spatial_result.as_dict()
        payload_str = json.dumps(d)
    else:
        # Tag generic values so None / str / int round-trip with their type intact.
        try:
            payload_str = json.dumps({"__cache_value__": value})
        except (TypeError, ValueError):
            payload_str = json.dumps({"__cache_value__": str(value)})
    return payload_str


class RedisCacheBackend:
    """Redis-backed :class:`CacheBackend` with TTL, key namespace and graceful degradation.

    ``client`` may be any object with the redis-py ``get`` / ``set(name, value, ex=)`` / ``delete`` / ``scan_iter``
    surface (tests pass a fake); otherwise one is built lazily from ``url`` with ``redis.Redis.from_url``, which does
    not connect until the first command, so constructing the backend never fails because the server is down.

    * ``prefix``: every key is stored as ``prefix + key``; ``clear()`` removes only keys under the prefix (it never
      issues FLUSHDB/FLUSHALL), so one Redis can be shared with other applications and other deployments.
    * ``ttl_seconds``: expiry applied to every ``set`` (``None`` or 0 stores without expiry).
    * ``retry_after``: after a failure the backend answers "miss" without touching Redis for this many seconds.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        client: Optional[Any] = None,
        prefix: str = "address_standardizer:v1:",
        ttl_seconds: Optional[int] = 86400,
        retry_after: float = 30.0,
        socket_timeout: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.prefix = prefix
        self.ttl_seconds = int(ttl_seconds) if ttl_seconds else None
        self.retry_after = float(retry_after)
        self._clock = clock
        self._down_until = 0.0
        self._warned = False
        self._hits = 0
        self._misses = 0
        self._errors = 0
        self._skipped = 0
        self._url = url
        self._socket_timeout = socket_timeout
        self._client = client
        if client is None and url is None:
            raise ValueError("RedisCacheBackend needs a redis URL or a client")

    # -- connection / failure handling -------------------------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import redis  # type: ignore[import-not-found]
            except ImportError as exc:
                raise ImportError(
                    'RedisCacheBackend needs the redis package: pip install "entity-standardizer[redis]"'
                ) from exc
            self._client = redis.Redis.from_url(
                self._url,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_timeout,
            )
        return self._client

    def _usable(self) -> bool:
        """False while the backend is paused after a failure."""
        if self._clock() < self._down_until:
            self._skipped += 1
            return False
        return True

    def _fail(self, action: str, exc: BaseException) -> None:
        self._errors += 1
        self._down_until = self._clock() + self.retry_after
        if not self._warned:
            self._warned = True
            logger.warning(
                "Redis cache %s failed (%s: %s); continuing without it and retrying in %.0fs. "
                "Further Redis failures are counted in stats() but not logged.",
                action, type(exc).__name__, exc, self.retry_after,
            )

    # -- CacheBackend ------------------------------------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        if not self._usable():
            self._misses += 1
            return None
        try:
            raw = self._get_client().get(self.prefix + key)
        except Exception as exc:  # noqa: BLE001 - an outage (or a missing redis package) must degrade to a miss
            self._fail("get", exc)
            self._misses += 1
            return None
        if raw is None:
            self._misses += 1
            return None
        try:
            value = deserialize_value(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        except Exception:  # noqa: BLE001 - corrupt or older-schema payload: drop it and recompute
            self._misses += 1
            self.delete(key)
            return None
        if value is None:
            # A cached ``None`` is indistinguishable from a miss for the caller, which treats None as "not cached".
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        if not self._usable():
            return
        try:
            payload = serialize_value(value)
            self._get_client().set(self.prefix + key, payload, ex=self.ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            self._fail("set", exc)

    def delete(self, key: str) -> bool:
        if not self._usable():
            return False
        try:
            return bool(self._get_client().delete(self.prefix + key))
        except Exception as exc:  # noqa: BLE001
            self._fail("delete", exc)
            return False

    def clear(self) -> None:
        """Remove every key under this backend's prefix (never the whole database) and reset the counters."""
        self._hits = self._misses = self._errors = self._skipped = 0
        if not self._usable():
            return
        try:
            client = self._get_client()
            batch = []
            for name in client.scan_iter(match=self.prefix + "*", count=500):
                batch.append(name)
                if len(batch) >= 500:
                    client.delete(*batch)
                    batch = []
            if batch:
                client.delete(*batch)
        except Exception as exc:  # noqa: BLE001
            self._fail("clear", exc)

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "backend": "redis",
            "prefix": self.prefix,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "skipped_while_down": self._skipped,
            "degraded": self._clock() < self._down_until,
            "evictions": 0,
            "size": None,  # the shared keyspace is not counted per prefix (it would need a full SCAN)
            "hit_rate": round(self._hits / total, 4) if total else 0.0,
        }


def backend_from_url(url: str, **options: Any) -> CacheBackend:
    """Builds a backend from a URL. Only Redis URLs are supported; anything else raises ``ValueError``."""
    if not url.lower().startswith(REDIS_URL_SCHEMES):
        raise ValueError(f"unsupported cache URL {url!r}; expected one starting with {', '.join(REDIS_URL_SCHEMES)}")
    return RedisCacheBackend(url, **options)
