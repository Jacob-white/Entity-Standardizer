"""Embedded reference data manager and provider loader.

Manages zero-configuration offline reference datasets (US ZIP5 centroids,
state concordances) cached under ~/.cache/address_standardizer/.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from entity_standardizer.address.reference.us_zip5 import (
    DATA_PATH as BUNDLED_ZIP5_PATH,
    USZip5Provider,
    get_default_us_zip5_provider,
)

DEFAULT_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "address_standardizer"


def get_reference_cache_dir() -> Path:
    """Return the filesystem directory used for caching reference datasets."""
    cache_dir = DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def ensure_embedded_reference_cache(cache_dir: Optional[Path] = None) -> Path:
    """Ensure bundled reference datasets are cached in the user cache directory."""
    target_dir = cache_dir or get_reference_cache_dir()
    target_path = target_dir / "us_zip5.tsv.gz"
    if not target_path.exists() and BUNDLED_ZIP5_PATH.exists():
        shutil.copy2(BUNDLED_ZIP5_PATH, target_path)
    return target_path if target_path.exists() else BUNDLED_ZIP5_PATH


def get_embedded_reference_provider(use_cache_dir: bool = False) -> USZip5Provider:
    """Return the zero-config embedded reference provider."""
    if use_cache_dir:
        path = ensure_embedded_reference_cache()
        return USZip5Provider(data_path=path)
    return get_default_us_zip5_provider()
