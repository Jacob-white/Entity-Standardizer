"""Embedded reference data package."""

from entity_standardizer.address.data.embedded_reference import (
    DEFAULT_CACHE_DIR,
    ensure_embedded_reference_cache,
    get_embedded_reference_provider,
    get_reference_cache_dir,
)

__all__ = [
    "DEFAULT_CACHE_DIR",
    "ensure_embedded_reference_cache",
    "get_embedded_reference_provider",
    "get_reference_cache_dir",
]
