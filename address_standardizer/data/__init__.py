"""Embedded reference data package."""

from address_standardizer.data.embedded_reference import (
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
