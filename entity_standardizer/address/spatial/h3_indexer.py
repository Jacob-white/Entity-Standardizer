"""
Uber H3 cell identifiers (thin, validated wrapper around the ``h3`` package).
============================================================================
Computes Resolution 10 (~65m edge length) hexagonal cell identifiers, k-ring neighbourhood disks, parent cells and
grid distances. Every value comes from the real H3 library, so identifiers are interoperable with any other H3 tool.

``h3`` is a required dependency of this package: there is deliberately no approximate stand-in, because an identifier
that merely *looks* like H3 would silently disagree with every other H3 system.
"""

import math
import re
from typing import List

import h3 as _h3

H3_HEX_PATTERN = re.compile(r"^[0-9a-f]{15}$")


def _validate_lat_lng(lat: float, lng: float, resolution: int) -> None:
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise ValueError(f"Coordinates must be finite: lat={lat}, lng={lng}")
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Latitude out of range [-90, 90]: {lat}")
    if not -180.0 <= lng <= 180.0:
        raise ValueError(f"Longitude out of range [-180, 180]: {lng}")
    if not isinstance(resolution, int) or isinstance(resolution, bool) or not 0 <= resolution <= 15:
        raise ValueError(f"Resolution must be an integer in [0, 15]: {resolution!r}")


def lat_lng_to_h3(lat: float, lng: float, resolution: int = 10) -> str:
    """
    Encodes (latitude, longitude) into a lowercase H3 cell index (default Resolution 10, ~65m hexagon edge length).
    Raises ``ValueError`` for non-finite or out-of-range input (nothing is clamped or wrapped).
    """
    _validate_lat_lng(lat, lng, resolution)
    return str(_h3.latlng_to_cell(lat, lng, resolution)).lower()


def is_valid_h3(h3_index: str) -> bool:
    """True if the string is a valid H3 cell index."""
    if not isinstance(h3_index, str):
        return False
    clean = h3_index.strip().lower()
    return bool(H3_HEX_PATTERN.match(clean)) and bool(_h3.is_valid_cell(clean))


def h3_to_int(h3_index: str) -> int:
    """Converts a hex H3 index into a 64-bit integer."""
    if not is_valid_h3(h3_index):
        raise ValueError(f"Invalid H3 index: {h3_index}")
    return int(h3_index.strip(), 16)


def int_to_h3(h3_int: int) -> str:
    """Converts a 64-bit integer back to a hex H3 index string."""
    h3_str = f"{h3_int:015x}"
    if not is_valid_h3(h3_str):
        raise ValueError(f"Invalid integer representation for H3 index: {h3_int}")
    return h3_str


def k_ring(h3_index: str, ring_size: int = 1) -> List[str]:
    """All cells within ``ring_size`` grid steps of the cell (including the cell itself)."""
    clean = h3_index.strip().lower()
    if not is_valid_h3(clean):
        raise ValueError(f"Invalid H3 index: {h3_index}")
    if ring_size <= 0:
        return [clean]
    return sorted(str(c).lower() for c in _h3.grid_disk(clean, ring_size))


def h3_distance(origin: str, destination: str) -> int:
    """Grid distance (number of cell steps) between two cells.

    Raises ``ValueError`` for invalid cells, or when H3 cannot compute a distance (cells too far apart or across a
    pentagon distortion).
    """
    orig = origin.strip().lower()
    dest = destination.strip().lower()
    if not is_valid_h3(orig) or not is_valid_h3(dest):
        raise ValueError(f"Invalid H3 cell: {origin} or {destination}")
    if orig == dest:
        return 0
    try:
        return int(_h3.grid_distance(orig, dest))
    except Exception as exc:  # h3 raises its own error types
        raise ValueError(f"H3 grid distance undefined for {origin} -> {destination}: {exc}") from exc


def h3_to_parent(h3_index: str, parent_res: int) -> str:
    """Parent cell at a coarser resolution."""
    clean = h3_index.strip().lower()
    if not is_valid_h3(clean):
        raise ValueError(f"Invalid H3 index: {h3_index}")
    if parent_res < 0:
        raise ValueError(f"Parent resolution {parent_res} cannot be negative")
    current = _h3.get_resolution(clean)
    if parent_res > current:
        raise ValueError(f"Parent resolution {parent_res} cannot be finer than current {current}")
    return str(_h3.cell_to_parent(clean, parent_res)).lower()
