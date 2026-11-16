"""Externalized JSON Entity Registries & Runtime Override API."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from pathlib import Path
from typing import Any

_DEFAULT_REGISTRY_PATH: Path = Path(__file__).resolve().parent / "data" / "entity_registries.json"


def _load_default_payload() -> dict[str, Any]:
    return json.loads(_DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))


BRAND_LINEAGE_PREFIXES: list[tuple[str, str]] = []
CREDENTIALS: dict[str, str] = {}
SURNAME_PARTICLES: set[str] = set()
NICKNAME_TO_ROOT: dict[str, str] = {}
MULTI_ROOT_DIMINUTIVES: dict[str, tuple[str, ...]] = {}


def reset_custom_registries() -> None:
    """Restore all packaged JSON entity registries to their default shipped contents."""
    payload = _load_default_payload()

    BRAND_LINEAGE_PREFIXES.clear()
    BRAND_LINEAGE_PREFIXES.extend(
        (str(prefix).strip().upper(), str(family).strip().upper())
        for prefix, family in payload["brand_lineage_prefixes"]
    )

    CREDENTIALS.clear()
    CREDENTIALS.update(
        {str(k).strip().upper(): str(v).strip().upper() for k, v in payload["credentials"].items()}
    )

    SURNAME_PARTICLES.clear()
    SURNAME_PARTICLES.update(str(p).strip().upper() for p in payload["surname_particles"])

    NICKNAME_TO_ROOT.clear()
    NICKNAME_TO_ROOT.update(
        {str(k).strip().upper(): str(v).strip().upper() for k, v in payload["nickname_to_root"].items()}
    )

    MULTI_ROOT_DIMINUTIVES.clear()
    MULTI_ROOT_DIMINUTIVES.update(
        {
            str(k).strip().upper(): tuple(str(r).strip().upper() for r in roots)
            for k, roots in payload["multi_root_diminutives"].items()
        }
    )


def register_brand_lineage_overrides(overrides: Mapping[str, str] | Iterable[tuple[str, str]]) -> None:
    """Prepend or update custom corporate brand-lineage prefix -> family mappings at runtime."""
    pairs = overrides.items() if isinstance(overrides, Mapping) else overrides
    normalized: list[tuple[str, str]] = []
    override_keys: set[str] = set()
    for prefix, family in pairs:
        p = str(prefix).strip().upper()
        f = str(family).strip().upper()
        if p and f:
            normalized.append((p, f))
            override_keys.add(p)
    if not normalized:
        return
    remaining = [(p, f) for p, f in BRAND_LINEAGE_PREFIXES if p not in override_keys]
    BRAND_LINEAGE_PREFIXES.clear()
    BRAND_LINEAGE_PREFIXES.extend(normalized + remaining)


def register_nickname_overrides(overrides: Mapping[str, str]) -> None:
    """Add or update custom given-name nickname -> canonical root mappings at runtime."""
    for alias, root in overrides.items():
        a = str(alias).strip().upper()
        r = str(root).strip().upper()
        if a and r:
            NICKNAME_TO_ROOT[a] = r


def register_multi_root_diminutive_overrides(overrides: Mapping[str, Iterable[str]]) -> None:
    """Add or update custom ambiguous diminutive -> canonical root tuples at runtime."""
    for alias, roots in overrides.items():
        a = str(alias).strip().upper()
        norm_roots = tuple(str(r).strip().upper() for r in roots if str(r).strip())
        if a and norm_roots:
            MULTI_ROOT_DIMINUTIVES[a] = norm_roots


def register_credential_overrides(overrides: Mapping[str, str]) -> None:
    """Add or update custom post-nominal credential token -> normalized credential mappings."""
    for raw_cred, canonical in overrides.items():
        k = str(raw_cred).strip().upper()
        v = str(canonical).strip().upper()
        if k and v:
            CREDENTIALS[k] = v


def register_surname_particles(particles: Iterable[str]) -> None:
    """Register additional surname particles at runtime."""
    for token in particles:
        t = str(token).strip().upper()
        if t:
            SURNAME_PARTICLES.add(t)


def load_registry_overrides(source: str | Path | Mapping[str, Any]) -> None:
    """Load an external JSON registry file or mapping and overlay its non-empty sections."""
    if isinstance(source, Mapping):
        data: Mapping[str, Any] = source
    else:
        data = json.loads(Path(source).read_text(encoding="utf-8"))

    if "brand_lineage_prefixes" in data:
        raw_brands = data["brand_lineage_prefixes"]
        pairs = raw_brands.items() if isinstance(raw_brands, Mapping) else [(p, f) for p, f in raw_brands]
        register_brand_lineage_overrides(pairs)
    if "nickname_to_root" in data:
        register_nickname_overrides(data["nickname_to_root"])
    if "multi_root_diminutives" in data:
        register_multi_root_diminutive_overrides(data["multi_root_diminutives"])
    if "credentials" in data:
        register_credential_overrides(data["credentials"])
    if "surname_particles" in data:
        register_surname_particles(data["surname_particles"])


def get_registry_snapshot() -> dict[str, Any]:
    """Return a defensive copy of the currently active entity registries."""
    return {
        "brand_lineage_prefixes": list(BRAND_LINEAGE_PREFIXES),
        "credentials": dict(CREDENTIALS),
        "surname_particles": sorted(SURNAME_PARTICLES),
        "nickname_to_root": dict(NICKNAME_TO_ROOT),
        "multi_root_diminutives": {k: list(v) for k, v in MULTI_ROOT_DIMINUTIVES.items()},
    }


reset_custom_registries()
