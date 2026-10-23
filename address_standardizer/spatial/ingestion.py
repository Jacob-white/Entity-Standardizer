"""
Open Reference Data ETL Ingestion Pipelines (Milestone 3.2).
============================================================
Parsers and batch database builders for US Census TIGER/Line street segments,
OpenAddresses global rooftop points, and OpenStreetMap building centroids
with polygon Shoelace calculations and coordinate snapping.
"""

import csv
import math
import json
import logging
from typing import List, Dict, Any, Optional, Iterable, Tuple

from address_standardizer.spatial.engine import SpatialEngine

logger = logging.getLogger(__name__)


def snap_coordinate(val: float, precision: int = 6) -> float:
    """Snaps coordinate float to specified decimal places (default 6: ~0.11m)."""
    return round(float(val), precision)


def calculate_polygon_centroid(coordinates: List[List[float]]) -> Tuple[float, float]:
    """
    Computes polygon centroid (lon, lat) using the Shoelace formula.
    Falls back to vertex averaging for degenerate polygons or linear rings.
    """
    n = len(coordinates)
    if n == 0:
        return 0.0, 0.0

    # A ring that crosses the antimeridian jumps by ~360 degrees between vertices: unwrap negative longitudes into
    # [180, 360) so the planar maths sees a contiguous shape, then wrap the answer back into [-180, 180].
    lons = [pt[0] for pt in coordinates]
    if max(lons) - min(lons) > 180.0:
        shifted = [[pt[0] + 360.0 if pt[0] < 0 else pt[0], pt[1]] for pt in coordinates]
        lon, lat = calculate_polygon_centroid(shifted)
        if lon > 180.0:
            lon = snap_coordinate(lon - 360.0)
        return lon, lat
    if n < 3:
        avg_x = sum(pt[0] for pt in coordinates) / n
        avg_y = sum(pt[1] for pt in coordinates) / n
        return snap_coordinate(avg_x), snap_coordinate(avg_y)

    area = 0.0
    cx = 0.0
    cy = 0.0
    # Work relative to the first vertex: absolute lon/lat products lose precision for small buildings.
    ox, oy = coordinates[0][0], coordinates[0][1]
    for i in range(n):
        j = (i + 1) % n
        xi, yi = coordinates[i][0] - ox, coordinates[i][1] - oy
        xj, yj = coordinates[j][0] - ox, coordinates[j][1] - oy
        factor = xi * yj - xj * yi
        area += factor
        cx += (xi + xj) * factor
        cy += (yi + yj) * factor

    area *= 0.5
    if abs(area) < 1e-9:
        # Fallback to arithmetic vertex mean
        avg_x = sum(pt[0] for pt in coordinates) / n
        avg_y = sum(pt[1] for pt in coordinates) / n
        return snap_coordinate(avg_x), snap_coordinate(avg_y)

    cx = cx / (6.0 * area) + ox
    cy = cy / (6.0 * area) + oy
    return snap_coordinate(cx), snap_coordinate(cy)


def _valid_coordinate(lat: Any, lon: Any) -> bool:
    """Finite and within WGS84 bounds; anything else (NaN, lat=200, empty geometry) is skipped, not stored."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat_f) and math.isfinite(lon_f) and -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


class OpenAddressesIngestor:
    """ETL parser for OpenAddresses cadastral parcel points."""

    def __init__(self, engine: SpatialEngine):
        self.engine = engine

    def ingest_records(self, records: Iterable[Dict[str, Any]], batch_size: int = 5000) -> int:
        count = 0
        for rec in records:
            lat = rec.get("LATITUDE") if "LATITUDE" in rec else rec.get("latitude")
            lon = rec.get("LONGITUDE") if "LONGITUDE" in rec else rec.get("longitude")
            number = rec.get("NUMBER") if "NUMBER" in rec else rec.get("number", "")
            street = rec.get("STREET") if "STREET" in rec else rec.get("street", "")
            unit = rec.get("UNIT") if "UNIT" in rec else rec.get("unit", "")
            city = rec.get("CITY") if "CITY" in rec else rec.get("city", "")
            state = rec.get("REGION") if "REGION" in rec else (rec.get("state") or "")
            postcode = rec.get("POSTCODE") if "POSTCODE" in rec else (rec.get("postal_code") or "")
            country = rec.get("COUNTRY") if "COUNTRY" in rec else (rec.get("country") or "USA")

            if lat is None or lon is None or not str(street).strip():
                continue

            try:
                lat_f = snap_coordinate(float(lat))
                lon_f = snap_coordinate(float(lon))
            except (ValueError, TypeError):
                continue
            if not _valid_coordinate(lat_f, lon_f):
                continue

            num_str = str(number).strip() if number is not None else ""
            street_str = str(street).strip().upper()
            st_line = f"{num_str} {street_str}".strip().upper()
            unit_str = str(unit).strip().upper() if unit is not None else ""
            c_str = str(city).strip().upper() if city is not None else ""
            s_str = str(state).strip().upper() if state is not None else ""
            p_str = str(postcode).strip() if postcode is not None else ""
            co_str = str(country).strip().upper() if country is not None else "USA"

            addr_key = f"{st_line}|{unit_str}|{c_str}|{s_str}|{p_str[:5] if p_str else ''}|{co_str}"
            bld_key = f"{st_line}||{c_str}|{s_str}|{p_str[:5] if p_str else ''}|{co_str}"

            st_num_int = int(num_str) if num_str.isascii() and num_str.isdigit() else None
            parcel_id = rec.get("ID") if "ID" in rec else rec.get("parcel_id")

            if self.engine.has_address_key(addr_key):
                continue  # re-running an ingest must not duplicate points

            self.engine.insert_point(
                address_key=addr_key,
                building_key=bld_key,
                latitude=lat_f,
                longitude=lon_f,
                precision_code="CONFIRMED_ROOFTOP",
                accuracy_radius_m=3.0,
                parcel_id=str(parcel_id) if parcel_id is not None else None,
                source="OPENADDRESSES",
                street_number=st_num_int,
                street_name=street_str,
                city=c_str or None,
                state=s_str or None,
                postal_code=p_str or None,
                country_iso3=co_str,
            )
            count += 1
        return count

    def ingest_csv(self, file_path_or_buffer: Any) -> int:
        """Reads OpenAddresses CSV data from a file path or StringIO/buffer."""
        if isinstance(file_path_or_buffer, str):
            with open(file_path_or_buffer, mode="r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                return self.ingest_records(reader)
        elif hasattr(file_path_or_buffer, "read"):
            reader = csv.DictReader(file_path_or_buffer)
            return self.ingest_records(reader)
        else:
            raise TypeError("Expected file path or file-like buffer for ingest_csv")


class TigerLineIngestor:
    """ETL parser for US Census TIGER/Line street segments."""

    def __init__(self, engine: SpatialEngine):
        self.engine = engine

    def ingest_segments(self, segments: Iterable[Dict[str, Any]]) -> int:
        count = 0
        for seg in segments:
            st_name = seg.get("street_name")
            f_num = seg.get("from_number")
            t_num = seg.get("to_number")
            s_lat = seg.get("start_lat")
            s_lon = seg.get("start_lon")
            e_lat = seg.get("end_lat")
            e_lon = seg.get("end_lon")

            if (
                not st_name
                or f_num is None
                or t_num is None
                or s_lat is None
                or s_lon is None
                or e_lat is None
                or e_lon is None
            ):
                continue

            try:
                from_n = int(f_num)
                to_n = int(t_num)
                s_lat_f = snap_coordinate(float(s_lat))
                s_lon_f = snap_coordinate(float(s_lon))
                e_lat_f = snap_coordinate(float(e_lat))
                e_lon_f = snap_coordinate(float(e_lon))
            except (ValueError, TypeError):
                continue

            self.engine.insert_street_segment(
                street_name=str(st_name).strip().upper(),
                from_number=from_n,
                to_number=to_n,
                start_lat=s_lat_f,
                start_lon=s_lon_f,
                end_lat=e_lat_f,
                end_lon=e_lon_f,
                parity=seg.get("parity", "BOTH"),
                postal_code=seg.get("postal_code"),
                city=seg.get("city"),
                state=seg.get("state"),
                country_iso3=seg.get("country_iso3", "USA"),
                source=seg.get("source", "TIGER"),
            )
            count += 1
        return count

    def ingest_csv(self, file_path_or_buffer: Any) -> int:
        """Reads TIGER street segments from a CSV file path or buffer."""
        if isinstance(file_path_or_buffer, str):
            with open(file_path_or_buffer, mode="r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                return self.ingest_segments(reader)
        elif hasattr(file_path_or_buffer, "read"):
            reader = csv.DictReader(file_path_or_buffer)
            return self.ingest_segments(reader)
        else:
            raise TypeError("Expected file path or file-like buffer for ingest_csv")


class OsmBuildingIngestor:
    """ETL parser for OpenStreetMap building polygons and nodes."""

    def __init__(self, engine: SpatialEngine):
        self.engine = engine

    def ingest_features(self, features: Iterable[Dict[str, Any]]) -> int:
        count = 0
        for feat in features:
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            g_type = geom.get("type")
            coords = geom.get("coordinates", [])

            lat, lon = None, None
            try:
                if g_type == "Point" and len(coords) >= 2:
                    lon, lat = snap_coordinate(coords[0]), snap_coordinate(coords[1])
                elif g_type == "Polygon" and coords and coords[0]:
                    lon, lat = calculate_polygon_centroid(coords[0])
                elif g_type == "MultiPolygon" and coords and coords[0] and coords[0][0]:
                    lon, lat = calculate_polygon_centroid(coords[0][0])
            except (TypeError, ValueError, IndexError):
                continue  # malformed geometry: skip the feature, keep ingesting

            if lat is None or lon is None or not _valid_coordinate(lat, lon):
                continue

            num = props.get("addr:housenumber", "")
            street = props.get("addr:street", "")
            unit = props.get("addr:unit", "")
            city = props.get("addr:city", "")
            state = props.get("addr:state", "")
            postcode = props.get("addr:postcode", "")
            country = props.get("addr:country", "USA")

            if not street:
                continue

            st_line = f"{num} {street}".strip().upper()
            addr_key = f"{st_line}|{unit}|{city}|{state}|{postcode[:5] if postcode else ''}|{country}".upper()
            bld_key = f"{st_line}||{city}|{state}|{postcode[:5] if postcode else ''}|{country}".upper()

            if self.engine.has_address_key(addr_key):
                continue

            self.engine.insert_point(
                address_key=addr_key,
                building_key=bld_key,
                latitude=lat,
                longitude=lon,
                precision_code="CONFIRMED_ROOFTOP",
                accuracy_radius_m=4.0,
                source="OSM",
                street_number=int(num) if str(num).isascii() and str(num).isdigit() else None,
                street_name=str(street).strip().upper(),
                city=str(city).strip().upper() if city else None,
                state=str(state).strip().upper() if state else None,
                postal_code=str(postcode).strip() if postcode else None,
                country_iso3=str(country).strip().upper(),
            )
            count += 1
        return count

    def ingest_geojson(self, file_path_or_buffer: Any) -> int:
        """Reads OSM building features from GeoJSON file or buffer."""
        if isinstance(file_path_or_buffer, str):
            with open(file_path_or_buffer, mode="r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        elif hasattr(file_path_or_buffer, "read"):
            data = json.load(file_path_or_buffer)
        else:
            raise TypeError("Expected file path or file-like buffer for ingest_geojson")

        features = data.get("features", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        return self.ingest_features(features)


def build_spatial_database(
    output_db_path: str,
    openaddresses_data: Optional[Iterable[Dict[str, Any]]] = None,
    tiger_segments: Optional[Iterable[Dict[str, Any]]] = None,
    osm_features: Optional[Iterable[Dict[str, Any]]] = None,
) -> SpatialEngine:
    """Builds and initializes a complete spatial SQLite database from open data sources."""
    engine = SpatialEngine(db_path=output_db_path, seed=True)
    if openaddresses_data:
        oa = OpenAddressesIngestor(engine)
        oa.ingest_records(openaddresses_data)
    if tiger_segments:
        tg = TigerLineIngestor(engine)
        tg.ingest_segments(tiger_segments)
    if osm_features:
        osm = OsmBuildingIngestor(engine)
        osm.ingest_features(osm_features)
    return engine
