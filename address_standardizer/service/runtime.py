"""Assembled service state: configuration plus the key store, limiters, tenancy and tracer built from it."""

import os
import time
from typing import Any, Callable, Mapping, Optional

from address_standardizer.service.auth import KeyStore
from address_standardizer.service.config import ServiceConfig
from address_standardizer.service.ratelimit import DailyQuota, TokenBucketLimiter
from address_standardizer.service.telemetry import load_tracer
from address_standardizer.service.tenancy import Tenancy


class Deadline:
    """Cooperative per-request time budget; ``expired()`` is polled between batch items."""

    def __init__(self, seconds: Optional[float], clock: Callable[[], float]) -> None:
        self._clock = clock
        self._expiry = None if seconds is None else clock() + seconds

    def expired(self) -> bool:
        return self._expiry is not None and self._clock() > self._expiry


class ServiceRuntime:
    def __init__(
        self,
        config: ServiceConfig,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.clock = clock
        self.keystore = KeyStore.from_config(config.api_keys, config.api_keys_file)
        self.limiter: Optional[TokenBucketLimiter] = None
        if config.rate_limit is not None:
            count, period = config.rate_limit
            self.limiter = TokenBucketLimiter(
                count / period, config.rate_burst or count, clock=clock, max_buckets=config.rate_max_buckets
            )
        self.quota: Optional[DailyQuota] = None
        if config.daily_quota is not None:
            self.quota = DailyQuota(config.daily_quota, clock=wall_clock, max_identities=config.rate_max_buckets)
        self.tenancy = Tenancy(config.tenant_isolation, config.tenant_audit_dir)
        self.tracer: Any = load_tracer() if config.otel else None

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> "ServiceRuntime":
        return cls(ServiceConfig.from_env(os.environ if env is None else env), clock=clock, wall_clock=wall_clock)

    def new_deadline(self) -> Deadline:
        return Deadline(self.config.request_timeout_seconds, self.clock)
