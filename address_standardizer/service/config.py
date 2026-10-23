"""Environment-driven configuration for the HTTP service.

Security-relevant settings fail loudly: a malformed rate limit or key list raises ``ValueError`` at startup instead of
silently running without the protection the operator asked for.
"""

import re
from dataclasses import dataclass
from typing import FrozenSet, Mapping, Optional, Tuple

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")

_PERIODS = {
    "s": 1, "sec": 1, "second": 1,
    "m": 60, "min": 60, "minute": 60,
    "h": 3600, "hour": 3600,
    "d": 86400, "day": 86400,
}
_RATE_RE = re.compile(r"^\s*(\d+)\s*/\s*([a-z]+)\s*$", re.IGNORECASE)


def parse_rate(text: str) -> Tuple[int, int]:
    """Parse ``"100/minute"`` into ``(count, period_seconds)``. Raises ValueError on anything else."""
    match = _RATE_RE.match(text)
    if match is None or match.group(2).lower() not in _PERIODS or int(match.group(1)) < 1:
        raise ValueError(f"invalid rate limit {text!r}: expected N/second|minute|hour|day with N >= 1")
    return int(match.group(1)), _PERIODS[match.group(2).lower()]


def env_flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    """Boolean env var: 1/true/yes/on or 0/false/no/off (case-insensitive); anything else keeps the default."""
    value = env.get(name, "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def env_int(env: Mapping[str, str], name: str, default: Optional[int], minimum: int = 1) -> Optional[int]:
    """Integer env var; unset/blank gives the default, garbage or a value below the minimum raises ValueError."""
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def env_float(env: Mapping[str, str], name: str) -> Optional[float]:
    """Positive float env var; unset/blank/0 means "no limit" (None); garbage or negatives raise ValueError."""
    raw = env.get(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number of seconds") from None
    if not value >= 0:  # also rejects NaN
        raise ValueError(f"{name} must be >= 0")
    return value or None


@dataclass(frozen=True)
class ServiceConfig:
    """Parsed service configuration. All fields default to "feature off" so the default server is unchanged."""

    api_keys: str = ""
    api_keys_file: str = ""
    open_paths: FrozenSet[str] = frozenset({"/health", "/ready"})
    rate_limit: Optional[Tuple[int, int]] = None  # (count, period_seconds)
    rate_burst: Optional[int] = None
    rate_max_buckets: int = 10000
    daily_quota: Optional[int] = None
    trust_forwarded_for: bool = False
    access_log: bool = True
    otel: bool = True
    tenant_isolation: bool = False
    tenant_audit_dir: str = ""
    security_headers: bool = True
    request_timeout_seconds: Optional[float] = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "ServiceConfig":
        prefix = "ADDRESS_STANDARDIZER_"
        rate_text = env.get(prefix + "RATE_LIMIT", "").strip()
        open_text = env.get(prefix + "AUTH_OPEN_PATHS")
        if open_text is None:
            open_paths = cls.open_paths
        else:
            open_paths = frozenset(p.strip() for p in open_text.split(",") if p.strip())
        return cls(
            api_keys=env.get(prefix + "API_KEYS", ""),
            api_keys_file=env.get(prefix + "API_KEYS_FILE", "").strip(),
            open_paths=open_paths,
            rate_limit=parse_rate(rate_text) if rate_text else None,
            rate_burst=env_int(env, prefix + "RATE_LIMIT_BURST", None),
            rate_max_buckets=env_int(env, prefix + "RATE_LIMIT_MAX_BUCKETS", 10000) or 10000,
            daily_quota=env_int(env, prefix + "DAILY_QUOTA", None),
            trust_forwarded_for=env_flag(env, prefix + "TRUST_FORWARDED_FOR", False),
            access_log=env_flag(env, prefix + "ACCESS_LOG", True),
            otel=env_flag(env, prefix + "OTEL", True),
            tenant_isolation=env_flag(env, prefix + "TENANT_ISOLATION", False),
            tenant_audit_dir=env.get(prefix + "TENANT_AUDIT_DIR", "").strip(),
            security_headers=env_flag(env, prefix + "SECURITY_HEADERS", True),
            request_timeout_seconds=env_float(env, prefix + "REQUEST_TIMEOUT_SECONDS"),
        )
