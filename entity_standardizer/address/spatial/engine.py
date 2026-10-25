"""
SQLite R*Tree Spatial Engine & 4-Stage Cascade Resolver.
========================================================
Embedded spatial engine supporting bounding box and radius queries,
linear street range interpolation, postal/municipal centroid matching,
and zero-downtime atomic hot-swapping under a strict < 120MB heap ceiling.
"""

import json
import math
import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Any

from entity_standardizer.address.models import SpatialResolutionResult
from entity_standardizer.address.spatial.h3_indexer import lat_lng_to_h3
from entity_standardizer.address.tables import (
    METRO_ZIP3_CENTROIDS,
    STATE_CENTROIDS,
    US_STATES,
)


SEED_SPATIAL_POINTS = [
    {
        "address_key": "100 WALL ST|STE 400|NEW YORK|NY|10005|USA",
        "building_key": "100 WALL ST||NEW YORK|NY|10005|USA",
        "latitude": 40.7061,
        "longitude": -74.0060,
        "precision_code": "CONFIRMED_ROOFTOP",
        "accuracy_radius_m": 3.0,
        "parcel_id": "NY-MAN-00100",
        "source": "OPENADDRESSES",
        "street_number": 100,
        "street_name": "WALL ST",
        "city": "NEW YORK",
        "state": "NY",
        "postal_code": "10005",
        "country_iso3": "USA",
    },
    {
        "address_key": "200 PARK AVE|STE 1200|NEW YORK|NY|10166|USA",
        "building_key": "200 PARK AVE||NEW YORK|NY|10166|USA",
        "latitude": 40.7535,
        "longitude": -73.9768,
        "precision_code": "CONFIRMED_ROOFTOP",
        "accuracy_radius_m": 4.0,
        "parcel_id": "NY-MAN-00200",
        "source": "OPENADDRESSES",
        "street_number": 200,
        "street_name": "PARK AVE",
        "city": "NEW YORK",
        "state": "NY",
        "postal_code": "10166",
        "country_iso3": "USA",
    },
    {
        "address_key": "1209 N ORANGE ST|STE 400|WILMINGTON|DE|19801|USA",
        "building_key": "1209 N ORANGE ST||WILMINGTON|DE|19801|USA",
        "latitude": 39.7478,
        "longitude": -75.5492,
        "precision_code": "CONFIRMED_ROOFTOP",
        "accuracy_radius_m": 2.0,
        "parcel_id": "DE-NCC-26027",
        "source": "OPENADDRESSES",
        "street_number": 1209,
        "street_name": "N ORANGE ST",
        "city": "WILMINGTON",
        "state": "DE",
        "postal_code": "19801",
        "country_iso3": "USA",
    },
    {
        "address_key": "30 N GOULD ST|STE R|SHERIDAN|WY|82801|USA",
        "building_key": "30 N GOULD ST||SHERIDAN|WY|82801|USA",
        "latitude": 44.7972,
        "longitude": -106.9562,
        "precision_code": "CONFIRMED_ROOFTOP",
        "accuracy_radius_m": 2.5,
        "parcel_id": "WY-SHR-08280",
        "source": "OPENADDRESSES",
        "street_number": 30,
        "street_name": "N GOULD ST",
        "city": "SHERIDAN",
        "state": "WY",
        "postal_code": "82801",
        "country_iso3": "USA",
    },
    {
        "address_key": "500 N MICHIGAN AVE|STE 1400|CHICAGO|IL|60611|USA",
        "building_key": "500 N MICHIGAN AVE||CHICAGO|IL|60611|USA",
        "latitude": 41.8919,
        "longitude": -87.6243,
        "precision_code": "CONFIRMED_ROOFTOP",
        "accuracy_radius_m": 3.0,
        "parcel_id": "IL-COOK-17101",
        "source": "OPENADDRESSES",
        "street_number": 500,
        "street_name": "N MICHIGAN AVE",
        "city": "CHICAGO",
        "state": "IL",
        "postal_code": "60611",
        "country_iso3": "USA",
    },
]

SEED_STREET_SEGMENTS = [
    {
        "street_name": "MARKET ST",
        "postal_code": "94103",
        "city": "SAN FRANCISCO",
        "state": "CA",
        "from_number": 1000,
        "to_number": 1100,
        "start_lat": 37.7785,
        "start_lon": -122.4130,
        "end_lat": 37.7770,
        "end_lon": -122.4150,
        "parity": "BOTH",
        "source": "TIGER",
    },
    {
        "street_name": "BROADWAY",
        "postal_code": "10007",
        "city": "NEW YORK",
        "state": "NY",
        "from_number": 200,
        "to_number": 300,
        "start_lat": 40.7130,
        "start_lon": -74.0075,
        "end_lat": 40.7145,
        "end_lon": -74.0065,
        "parity": "EVEN",
        "source": "TIGER",
    },
]


class SpatialEngine:
    """
    Embedded SQLite R*Tree Spatial Engine with 4-stage cascade resolution.
    Strictly adheres to < 120MB heap and < 500MB RAM budgets.
    """

    def __init__(self, db_path: Optional[str] = None, seed: bool = True):
        self._db_path = db_path or ":memory:"
        self._seed = seed
        self._pid = os.getpid()
        self._lock = threading.RLock()
        self._real_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._real_conn.row_factory = sqlite3.Row
        self._init_schema(self._real_conn)

        if seed and self.count() == 0:
            self._seed_defaults()

    @property
    def _conn(self) -> sqlite3.Connection:
        current_pid = os.getpid()
        if current_pid != self._pid:
            with self._lock:
                if current_pid != self._pid:
                    self._pid = current_pid
                    self._real_conn = sqlite3.connect(self._db_path, check_same_thread=False)
                    self._real_conn.row_factory = sqlite3.Row
                    self._init_schema(self._real_conn)
                    if self._seed and self.count() == 0:
                        self._seed_defaults()
        return self._real_conn

    @_conn.setter
    def _conn(self, val: Optional[sqlite3.Connection]):
        self._real_conn = val

    def _init_schema(self, conn: Optional[sqlite3.Connection] = None):
        target_conn = conn or self._real_conn
        with self._lock, target_conn:
            # Memory and WAL pragmas
            if self._db_path != ":memory:":
                try:
                    target_conn.execute("PRAGMA journal_mode = WAL;")
                    target_conn.execute("PRAGMA synchronous = NORMAL;")
                    target_conn.execute("PRAGMA mmap_size = 268435456;")
                except sqlite3.Error:
                    pass
            target_conn.execute("PRAGMA cache_size = -64000;")
            target_conn.execute("PRAGMA temp_store = MEMORY;")

            # 1. R*Tree Virtual Table for Spatial Points
            target_conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS spatial_rtree USING rtree(
                    id INTEGER PRIMARY KEY,
                    minX REAL, maxX REAL,
                    minY REAL, maxY REAL
                );
            """)

            # 2. Master Spatial Points Table
            target_conn.execute("""
                CREATE TABLE IF NOT EXISTS spatial_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address_key TEXT NOT NULL,
                    building_key TEXT NOT NULL,
                    h3_res10 TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    precision_code TEXT NOT NULL,
                    accuracy_radius_m REAL NOT NULL,
                    parcel_id TEXT,
                    source TEXT NOT NULL,
                    street_number INTEGER,
                    street_name TEXT,
                    city TEXT,
                    state TEXT,
                    postal_code TEXT,
                    country_iso3 TEXT DEFAULT 'USA',
                    metadata_json TEXT
                );
            """)
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_spatial_addr ON spatial_points(address_key);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_spatial_bld ON spatial_points(building_key);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_spatial_h3 ON spatial_points(h3_res10);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_spatial_parcel ON spatial_points(parcel_id);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_spatial_post_st ON spatial_points(postal_code, street_name);")

            # 3. R*Tree Virtual Table for Street Segments
            target_conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS street_segments_rtree USING rtree(
                    id INTEGER PRIMARY KEY,
                    minX REAL, maxX REAL,
                    minY REAL, maxY REAL
                );
            """)

            # 4. Master Street Segments Table
            target_conn.execute("""
                CREATE TABLE IF NOT EXISTS street_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    street_name TEXT NOT NULL,
                    postal_code TEXT,
                    city TEXT,
                    state TEXT,
                    country_iso3 TEXT DEFAULT 'USA',
                    from_number INTEGER NOT NULL,
                    to_number INTEGER NOT NULL,
                    start_lat REAL NOT NULL,
                    start_lon REAL NOT NULL,
                    end_lat REAL NOT NULL,
                    end_lon REAL NOT NULL,
                    parity TEXT DEFAULT 'BOTH',
                    source TEXT DEFAULT 'TIGER'
                );
            """)
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_street_seg_name ON street_segments(street_name);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_street_seg_post ON street_segments(postal_code, street_name);")

            # 5. Postal Centroids Table
            target_conn.execute("""
                CREATE TABLE IF NOT EXISTS postal_centroids (
                    postal_code TEXT PRIMARY KEY,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    h3_res10 TEXT NOT NULL,
                    accuracy_radius_m REAL NOT NULL,
                    city TEXT,
                    state TEXT,
                    country_iso3 TEXT DEFAULT 'USA'
                );
            """)

            # 6. Municipal Centroids Table
            target_conn.execute("""
                CREATE TABLE IF NOT EXISTS municipal_centroids (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    state TEXT,
                    country_iso3 TEXT DEFAULT 'USA',
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    h3_res10 TEXT NOT NULL,
                    accuracy_radius_m REAL NOT NULL
                );
            """)
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_muni_lookup ON municipal_centroids(country_iso3, state, name);")

    def _seed_defaults(self):
        for pt in SEED_SPATIAL_POINTS:
            self.insert_point(**pt)
        for seg in SEED_STREET_SEGMENTS:
            self.insert_street_segment(**seg)
        for z3, coords in METRO_ZIP3_CENTROIDS.items():
            self.insert_postal_centroid(postal_code=z3, latitude=coords[0], longitude=coords[1], accuracy_radius_m=8000.0)
        for st_code, coords in STATE_CENTROIDS.items():
            self.insert_municipal_centroid(name=st_code, state=st_code, latitude=coords[0], longitude=coords[1], accuracy_radius_m=50000.0)

    def has_address_key(self, address_key: str) -> bool:
        """True if a point with this (case-insensitive) address key is already stored."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM spatial_points WHERE address_key = ? LIMIT 1", (address_key.strip().upper(),)
            ).fetchone()
            return row is not None

    def insert_point(
        self,
        address_key: str,
        building_key: str,
        latitude: float,
        longitude: float,
        precision_code: str = "CONFIRMED_ROOFTOP",
        accuracy_radius_m: float = 3.0,
        parcel_id: Optional[str] = None,
        source: str = "OPENADDRESSES",
        street_number: Optional[int] = None,
        street_name: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country_iso3: str = "USA",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Inserts a single spatial point into spatial_points and spatial_rtree."""
        if not (math.isfinite(latitude) and math.isfinite(longitude)) or not (
            -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0
        ):
            raise ValueError(f"invalid coordinates: lat={latitude}, lon={longitude}")
        h3_idx = lat_lng_to_h3(latitude, longitude, resolution=10)
        meta_json = json.dumps(metadata or {})
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO spatial_points (
                    address_key, building_key, h3_res10, latitude, longitude,
                    precision_code, accuracy_radius_m, parcel_id, source,
                    street_number, street_name, city, state, postal_code,
                    country_iso3, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    address_key.strip().upper(),
                    building_key.strip().upper(),
                    h3_idx,
                    round(latitude, 6),
                    round(longitude, 6),
                    precision_code,
                    accuracy_radius_m,
                    parcel_id,
                    source,
                    street_number,
                    street_name.strip().upper() if street_name else None,
                    city.strip().upper() if city else None,
                    state.strip().upper() if state else None,
                    postal_code.strip() if postal_code else None,
                    country_iso3.strip().upper(),
                    meta_json,
                ),
            )
            row_id = cur.lastrowid
            self._conn.execute(
                "INSERT INTO spatial_rtree (id, minX, maxX, minY, maxY) VALUES (?, ?, ?, ?, ?)",
                (row_id, longitude, longitude, latitude, latitude),
            )
            return row_id

    def insert_street_segment(
        self,
        street_name: str,
        from_number: int,
        to_number: int,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        parity: str = "BOTH",
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country_iso3: str = "USA",
        source: str = "TIGER",
    ) -> int:
        """Inserts a street segment into street_segments and street_segments_rtree."""
        min_x = min(start_lon, end_lon)
        max_x = max(start_lon, end_lon)
        min_y = min(start_lat, end_lat)
        max_y = max(start_lat, end_lat)
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO street_segments (
                    street_name, postal_code, city, state, country_iso3,
                    from_number, to_number, start_lat, start_lon, end_lat,
                    end_lon, parity, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    street_name.strip().upper(),
                    postal_code.strip() if postal_code else None,
                    city.strip().upper() if city else None,
                    state.strip().upper() if state else None,
                    country_iso3.strip().upper(),
                    from_number,
                    to_number,
                    start_lat,
                    start_lon,
                    end_lat,
                    end_lon,
                    parity.upper(),
                    source,
                ),
            )
            seg_id = cur.lastrowid
            self._conn.execute(
                "INSERT INTO street_segments_rtree (id, minX, maxX, minY, maxY) VALUES (?, ?, ?, ?, ?)",
                (seg_id, min_x, max_x, min_y, max_y),
            )
            return seg_id

    def insert_postal_centroid(
        self,
        postal_code: str,
        latitude: float,
        longitude: float,
        accuracy_radius_m: float = 5000.0,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country_iso3: str = "USA",
    ):
        """Inserts a postal code centroid into postal_centroids."""
        h3_idx = lat_lng_to_h3(latitude, longitude, resolution=10)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO postal_centroids (
                    postal_code, latitude, longitude, h3_res10, accuracy_radius_m, city, state, country_iso3
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    postal_code.strip().upper(),
                    round(latitude, 6),
                    round(longitude, 6),
                    h3_idx,
                    accuracy_radius_m,
                    city.strip().upper() if city else None,
                    state.strip().upper() if state else None,
                    country_iso3.strip().upper(),
                ),
            )

    def insert_municipal_centroid(
        self,
        name: str,
        latitude: float,
        longitude: float,
        accuracy_radius_m: float = 25000.0,
        state: Optional[str] = None,
        country_iso3: str = "USA",
    ):
        """Inserts a municipal or administrative centroid into municipal_centroids."""
        h3_idx = lat_lng_to_h3(latitude, longitude, resolution=10)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO municipal_centroids (
                    name, state, country_iso3, latitude, longitude, h3_res10, accuracy_radius_m
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip().upper(),
                    state.strip().upper() if state else None,
                    country_iso3.strip().upper(),
                    round(latitude, 6),
                    round(longitude, 6),
                    h3_idx,
                    accuracy_radius_m,
                ),
            )

    def query_bounding_box(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        limit: int = 100,
    ) -> List[SpatialResolutionResult]:
        """Queries points within a longitude/latitude bounding box using SQLite R*Tree.

        A box that crosses the antimeridian is given with ``min_lon > max_lon`` (e.g. 179.9 .. -179.9) and is
        answered as the two boxes [min_lon, 180] and [-180, max_lon].
        """
        min_lat, max_lat = max(-90.0, min(min_lat, max_lat)), min(90.0, max(min_lat, max_lat))
        if min_lon > max_lon:
            east = self._query_box(min_lon, min_lat, 180.0, max_lat, limit)
            west = self._query_box(-180.0, min_lat, max_lon, max_lat, max(0, limit - len(east)))
            return east + west
        return self._query_box(min_lon, min_lat, max_lon, max_lat, limit)

    def _query_box(
        self, min_lon: float, min_lat: float, max_lon: float, max_lat: float, limit: int
    ) -> List[SpatialResolutionResult]:
        """Single R*Tree box query (no wrapping)."""
        if limit <= 0:
            return []
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT p.* FROM spatial_points p
                JOIN spatial_rtree r ON p.id = r.id
                WHERE r.minX <= ? AND r.maxX >= ?
                  AND r.minY <= ? AND r.maxY >= ?
                LIMIT ?
                """,
                (max_lon, min_lon, max_lat, min_lat, limit),
            )
            results = []
            for row in cur.fetchall():
                meta = {}
                if row["metadata_json"]:
                    try:
                        meta = json.loads(row["metadata_json"])
                    except Exception:
                        pass
                results.append(
                    SpatialResolutionResult(
                        latitude=row["latitude"],
                        longitude=row["longitude"],
                        precision=row["precision_code"],
                        accuracy_radius_meters=row["accuracy_radius_m"],
                        stage=1,
                        source=row["source"],
                        h3_res10=row["h3_res10"],
                        parcel_id=row["parcel_id"],
                        metadata=meta,
                    )
                )
            return results

    def query_radius(
        self,
        lon: float,
        lat: float,
        radius_meters: float = 1000.0,
        limit: int = 50,
    ) -> List[SpatialResolutionResult]:
        """Queries points within a metric radius around (lon, lat)."""
        if not (math.isfinite(lat) and math.isfinite(lon)) or not -90.0 <= lat <= 90.0:
            raise ValueError("lat must be within [-90, 90] and lon finite")
        lon = ((lon + 180.0) % 360.0) - 180.0
        deg_lat = radius_meters / 111320.0
        min_lat, max_lat = lat - deg_lat, lat + deg_lat
        if max_lat >= 90.0 or min_lat <= -90.0:
            # The circle contains a pole: every longitude is in range.
            min_lon, max_lon = -180.0, 180.0
        else:
            # (deg_lon < 180 always holds here: a circle wide enough to span 360 degrees of longitude would
            # already have reached a pole, which the branch above handles.)
            deg_lon = radius_meters / (111320.0 * max(1e-6, math.cos(math.radians(lat))))
            min_lon, max_lon = lon - deg_lon, lon + deg_lon
            # Wrap across the antimeridian; query_bounding_box answers min_lon > max_lon as two boxes.
            if min_lon < -180.0:
                min_lon += 360.0
            if max_lon > 180.0:
                max_lon -= 360.0

        # Fetch a generous candidate set, then order by true distance so `limit` returns the nearest points
        # (R*Tree order is arbitrary).
        candidates = self.query_bounding_box(min_lon, min_lat, max_lon, max_lat, limit=max(limit * 20, 1000))
        filtered = []
        for c in candidates:
            # Haversine distance check
            d_lat = math.radians(c.latitude - lat)
            d_lon = math.radians(c.longitude - lon)
            a = (
                math.sin(d_lat / 2.0) ** 2
                + math.cos(math.radians(lat)) * math.cos(math.radians(c.latitude)) * math.sin(d_lon / 2.0) ** 2
            )
            dist = 2.0 * 6371000.0 * math.asin(math.sqrt(max(0.0, min(1.0, a))))
            if dist <= radius_meters:
                filtered.append((dist, c))
        filtered.sort(key=lambda pair: pair[0])
        return [c for _, c in filtered[:limit]]

    def query_street_segments(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Queries street segments within a bounding box using street_segments_rtree."""
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT s.* FROM street_segments s
                JOIN street_segments_rtree r ON s.id = r.id
                WHERE r.minX <= ? AND r.maxX >= ?
                  AND r.minY <= ? AND r.maxY >= ?
                LIMIT ?
                """,
                (max_lon, min_lon, max_lat, min_lat, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def resolve(self, address: Any) -> SpatialResolutionResult:
        """
        Executes the 4-stage cascade resolution:
          Stage 1: Rooftop / Parcel Match (< 5m radius)
          Stage 2: Street Centerline Range Interpolation (25-100m radius)
          Stage 3: Postal Centroid Match (1-8km radius)
          Stage 4: Administrative / Municipal Centroid Match (10-50km radius)
          Fallback: UNRESOLVED
        """
        t0 = time.perf_counter()
        with self._lock:
            # Extract query components
            norm_key = getattr(address, "normalized_address_key", None)
            bld_key = getattr(address, "building_key", None)
            parcel_id = getattr(address, "parcel_id", None) or getattr(address, "parcel", None)
            st1 = getattr(address, "street1", None)
            city = getattr(address, "city", None)
            state = getattr(address, "state", None)
            post = getattr(address, "postal_code", None)
            is_us = getattr(address, "is_us", None)
            country = getattr(address, "country", None)

            if isinstance(address, str):
                if "|" in address:
                    norm_key = address
                    parts = address.split("|")
                    if len(parts) >= 6 and parts[5].strip():
                        country = parts[5].strip()
                else:
                    from entity_standardizer.address.standardizer import standardize_address
                    std = standardize_address(address)
                    return self.resolve(std)

            if isinstance(address, dict):
                norm_key = address.get("normalized_address_key")
                bld_key = address.get("building_key")
                parcel_id = address.get("parcel_id") or address.get("parcel")
                st1 = address.get("street1")
                city = address.get("city")
                state = address.get("state")
                post = address.get("postal_code")
                if "is_us" in address and address["is_us"] is not None:
                    is_us = bool(address["is_us"])
                country = address.get("country") or address.get("country_code") or country
                if not country and norm_key and "|" in norm_key:
                    parts = norm_key.split("|")
                    if len(parts) >= 6 and parts[5].strip():
                        country = parts[5].strip()

            if is_us is None:
                if country:
                    c_clean = str(country).strip().upper()
                    is_us = c_clean in ("USA", "US", "UNITED STATES", "UNITED STATES OF AMERICA", "PRI", "VIR", "GUM", "MNP", "ASM")
                else:
                    is_us = True

            # Stage 1: Rooftop / Parcel Match
            if norm_key:
                cur = self._conn.execute(
                    "SELECT * FROM spatial_points WHERE address_key = ? LIMIT 1",
                    (norm_key.strip().upper(),),
                )
                row = cur.fetchone()
                if row:
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=row["latitude"],
                        longitude=row["longitude"],
                        precision=row["precision_code"],
                        accuracy_radius_meters=row["accuracy_radius_m"],
                        stage=1,
                        source=row["source"],
                        h3_res10=row["h3_res10"],
                        parcel_id=row["parcel_id"],
                        execution_time_ms=round(ms, 4),
                        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
                    )

            if bld_key:
                cur = self._conn.execute(
                    "SELECT * FROM spatial_points WHERE building_key = ? LIMIT 1",
                    (bld_key.strip().upper(),),
                )
                row = cur.fetchone()
                if row:
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=row["latitude"],
                        longitude=row["longitude"],
                        precision=row["precision_code"],
                        accuracy_radius_meters=row["accuracy_radius_m"],
                        stage=1,
                        source=row["source"],
                        h3_res10=row["h3_res10"],
                        parcel_id=row["parcel_id"],
                        execution_time_ms=round(ms, 4),
                        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
                    )

            if parcel_id:
                cur = self._conn.execute(
                    "SELECT * FROM spatial_points WHERE parcel_id = ? LIMIT 1",
                    (str(parcel_id).strip(),),
                )
                row = cur.fetchone()
                if row:
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=row["latitude"],
                        longitude=row["longitude"],
                        precision=row["precision_code"],
                        accuracy_radius_meters=row["accuracy_radius_m"],
                        stage=1,
                        source=row["source"],
                        h3_res10=row["h3_res10"],
                        parcel_id=row["parcel_id"],
                        execution_time_ms=round(ms, 4),
                        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
                    )

            # Stage 2: Street Centerline Range Interpolation (US only)
            if is_us and st1:
                st1_clean = st1.strip().upper()
                tokens = st1_clean.split()
                if tokens and tokens[0].isascii() and tokens[0].isdigit():
                    num = int(tokens[0])
                    street_name = " ".join(tokens[1:])
                    sql = "SELECT * FROM street_segments WHERE street_name = ?"
                    params: List[Any] = [street_name]
                    if post:
                        sql += " AND (postal_code = ? OR postal_code IS NULL)"
                        params.append(post.strip())
                    cur = self._conn.execute(sql, tuple(params))
                    rows = cur.fetchall()
                    for r in rows:
                        f_num, t_num = r["from_number"], r["to_number"]
                        low, high = min(f_num, t_num), max(f_num, t_num)
                        if low <= num <= high:
                            parity = r["parity"]
                            if parity != "BOTH":
                                if parity == "ODD" and num % 2 == 0:
                                    continue
                                if parity == "EVEN" and num % 2 != 0:
                                    continue

                            # Linear interpolation
                            span = t_num - f_num
                            mu = (num - f_num) / span if span != 0 else 0.5
                            mu = max(0.0, min(1.0, mu))
                            lat_interp = r["start_lat"] + mu * (r["end_lat"] - r["start_lat"])
                            lon_interp = r["start_lon"] + mu * (r["end_lon"] - r["start_lon"])

                            # Parity curb-side offset
                            dx = r["end_lon"] - r["start_lon"]
                            dy = r["end_lat"] - r["start_lat"]
                            length = math.hypot(dx, dy)
                            if length > 0:
                                side = 1.0 if num % 2 != 0 else -1.0
                                offset = 0.00009  # ~10 meters
                                lon_interp += (-dy / length) * side * offset
                                lat_interp += (dx / length) * side * offset

                            h3_idx = lat_lng_to_h3(lat_interp, lon_interp, resolution=10)
                            ms = (time.perf_counter() - t0) * 1000.0
                            return SpatialResolutionResult(
                                latitude=round(lat_interp, 6),
                                longitude=round(lon_interp, 6),
                                precision="RANGE_INTERPOLATED",
                                accuracy_radius_meters=35.0,
                                stage=2,
                                source=f"{r['source']}_INTERPOLATION",
                                h3_res10=h3_idx,
                                execution_time_ms=round(ms, 4),
                            )

            # Stage 3: Postal Centroid Match (US only)
            if is_us and post:
                clean_p = post.strip().upper()
                cur = self._conn.execute(
                    "SELECT * FROM postal_centroids WHERE postal_code = ? LIMIT 1",
                    (clean_p,),
                )
                row = cur.fetchone()
                if not row and len(clean_p) >= 3:
                    cur = self._conn.execute(
                        "SELECT * FROM postal_centroids WHERE postal_code = ? LIMIT 1",
                        (clean_p[:3],),
                    )
                    row = cur.fetchone()

                if row:
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=row["latitude"],
                        longitude=row["longitude"],
                        precision="POSTAL_CENTROID",
                        accuracy_radius_meters=row["accuracy_radius_m"],
                        stage=3,
                        source="POSTAL_CENTROID",
                        h3_res10=row["h3_res10"],
                        execution_time_ms=round(ms, 4),
                    )

                # In-memory METRO_ZIP3_CENTROIDS fallback
                z3 = clean_p[:3]
                if z3 in METRO_ZIP3_CENTROIDS:
                    coords = METRO_ZIP3_CENTROIDS[z3]
                    h3_idx = lat_lng_to_h3(coords[0], coords[1], resolution=10)
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=coords[0],
                        longitude=coords[1],
                        precision="POSTAL_CENTROID",
                        accuracy_radius_meters=8000.0,
                        stage=3,
                        source="METRO_ZIP3_CENTROID",
                        h3_res10=h3_idx,
                        execution_time_ms=round(ms, 4),
                    )

            # Stage 4: Administrative / Municipal Centroid Match (US only)
            if is_us and city and state:
                cur = self._conn.execute(
                    "SELECT * FROM municipal_centroids WHERE state = ? AND name = ? LIMIT 1",
                    (state.strip().upper(), city.strip().upper()),
                )
                row = cur.fetchone()
                if row:
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=row["latitude"],
                        longitude=row["longitude"],
                        precision="MUNICIPAL_CENTROID",
                        accuracy_radius_meters=row["accuracy_radius_m"],
                        stage=4,
                        source="MUNICIPAL_CENTROID",
                        h3_res10=row["h3_res10"],
                        execution_time_ms=round(ms, 4),
                    )

            if is_us and state:
                st_clean = state.strip().upper()
                st_code = US_STATES.get(st_clean, st_clean[:2] if len(st_clean) == 2 else st_clean)
                cur = self._conn.execute(
                    "SELECT * FROM municipal_centroids WHERE name = ? LIMIT 1",
                    (st_code,),
                )
                row = cur.fetchone()
                if row:
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=row["latitude"],
                        longitude=row["longitude"],
                        precision="MUNICIPAL_CENTROID",
                        accuracy_radius_meters=row["accuracy_radius_m"],
                        stage=4,
                        source="STATE_CENTROID",
                        h3_res10=row["h3_res10"],
                        execution_time_ms=round(ms, 4),
                    )

                if st_code in STATE_CENTROIDS:
                    coords = STATE_CENTROIDS[st_code]
                    h3_idx = lat_lng_to_h3(coords[0], coords[1], resolution=10)
                    ms = (time.perf_counter() - t0) * 1000.0
                    return SpatialResolutionResult(
                        latitude=coords[0],
                        longitude=coords[1],
                        precision="MUNICIPAL_CENTROID",
                        accuracy_radius_meters=50000.0,
                        stage=4,
                        source="STATE_CENTROID",
                        h3_res10=h3_idx,
                        execution_time_ms=round(ms, 4),
                    )

            # Fallback: UNRESOLVED
            ms = (time.perf_counter() - t0) * 1000.0
            return SpatialResolutionResult(
                latitude=0.0,
                longitude=0.0,
                precision="UNRESOLVED",
                accuracy_radius_meters=0.0,
                stage=0,
                source="NONE",
                h3_res10="",
                execution_time_ms=round(ms, 4),
            )

    def hot_swap(self, new_db_path: str):
        """Thread-safe zero-downtime hot swap to a new spatial SQLite database."""
        if not os.path.exists(new_db_path):
            raise FileNotFoundError(f"Hot swap database path does not exist: {new_db_path}")

        test_conn = sqlite3.connect(new_db_path, check_same_thread=False)
        test_conn.row_factory = sqlite3.Row
        try:
            cur = test_conn.execute("SELECT count(*) FROM spatial_points")
            cur.fetchone()
            cur = test_conn.execute("SELECT count(*) FROM spatial_rtree")
            cur.fetchone()
        except sqlite3.Error as e:
            test_conn.close()
            raise ValueError(f"Invalid spatial database schema in {new_db_path}: {e}")

        with self._lock:
            old_conn = self._conn
            self._conn = test_conn
            self._db_path = new_db_path
            old_conn.close()

    def count(self) -> int:
        """Returns the total number of points in spatial_points."""
        with self._lock:
            cur = self._conn.execute("SELECT count(*) FROM spatial_points")
            row = cur.fetchone()
            return row[0] if row else 0

    def close(self):
        """Closes the underlying SQLite connection."""
        with self._lock:
            if self._conn:
                self._conn.close()


_DEFAULT_SPATIAL_ENGINE: Optional[SpatialEngine] = None
_SPATIAL_ENGINE_LOCK = threading.Lock()


def get_default_spatial_engine() -> SpatialEngine:
    """Returns singleton instance of the offline spatial geocoding engine."""
    global _DEFAULT_SPATIAL_ENGINE
    if _DEFAULT_SPATIAL_ENGINE is None:
        with _SPATIAL_ENGINE_LOCK:
            if _DEFAULT_SPATIAL_ENGINE is None:
                env_path = os.environ.get("SPATIAL_DB_PATH")
                db_path = None
                if env_path and os.path.isfile(env_path):
                    db_path = env_path
                else:
                    candidates = [
                        "data/spatial_index.db",
                        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "spatial_index.db"),
                    ]
                    for cand in candidates:
                        if os.path.isfile(cand):
                            db_path = cand
                            break

                if db_path:
                    _DEFAULT_SPATIAL_ENGINE = SpatialEngine(db_path=db_path, seed=False)
                else:
                    _DEFAULT_SPATIAL_ENGINE = SpatialEngine(seed=True)
    return _DEFAULT_SPATIAL_ENGINE


def resolve_spatial_coordinates(address: Any) -> SpatialResolutionResult:
    """Convenience helper to resolve coordinates through the default spatial engine."""
    return get_default_spatial_engine().resolve(address)
