"""
Offline Open-Data Spatial & Rooftop Geocoding Subsystem (Milestone 3.2).
========================================================================
Embedded SQLite R*Tree spatial indexing, 4-stage cascade resolution,
Uber H3 hexagonal clustering, and open-data ETL ingestion pipelines.
"""

from address_standardizer.models import SpatialResolutionResult
from address_standardizer.spatial.engine import (
    SpatialEngine,
    get_default_spatial_engine,
    resolve_spatial_coordinates,
)
from address_standardizer.spatial.h3_indexer import (
    lat_lng_to_h3,
    h3_to_int,
    int_to_h3,
    is_valid_h3,
    k_ring,
    h3_distance,
    h3_to_parent,
)
from address_standardizer.spatial.ingestion import (
    snap_coordinate,
    calculate_polygon_centroid,
    OpenAddressesIngestor,
    TigerLineIngestor,
    OsmBuildingIngestor,
    build_spatial_database,
)

__all__ = [
    "SpatialEngine",
    "SpatialResolutionResult",
    "get_default_spatial_engine",
    "resolve_spatial_coordinates",
    "lat_lng_to_h3",
    "h3_to_int",
    "int_to_h3",
    "is_valid_h3",
    "k_ring",
    "h3_distance",
    "h3_to_parent",
    "snap_coordinate",
    "calculate_polygon_centroid",
    "OpenAddressesIngestor",
    "TigerLineIngestor",
    "OsmBuildingIngestor",
    "build_spatial_database",
]
