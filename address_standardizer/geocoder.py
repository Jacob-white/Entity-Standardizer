"""
Census Batch Geocoder Client & Fallback Centroid Service.
=========================================================
Wraps the US Census Bureau public Batch Geocoding API with automatic fallback
to regional ZIP3 / State centroids to ensure coordinates are never empty for valid US locations.
"""

import re
import io
import csv
import logging
import urllib.request
import urllib.parse
from typing import Dict, Tuple, Optional, List, Any

from address_standardizer.tables import (
    ZIP3_TO_STATE,
    STATE_CENTROIDS,
    METRO_ZIP3_CENTROIDS,
    US_STATES,
)

from address_standardizer.cascade import (
    VerificationCascade,
    CascadeResult,
    CascadePrecision,
    resolve_verification_cascade,
)

__all__ = [
    "CensusGeocoder",
    "OfflineGeocoder",
    "get_default_offline_geocoder",
    "geocode_offline",
    "get_fallback_centroid",
    "parse_census_geocoder_response",
    "VerificationCascade",
    "CascadeResult",
    "CascadePrecision",
    "resolve_verification_cascade",
]

logger = logging.getLogger(__name__)
CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def get_fallback_centroid(zip5: Optional[str] = None, state: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """Returns fallback (latitude, longitude) based on ZIP3 or State when rooftop geocoding fails."""
    found = get_fallback_centroid_tier(zip5=zip5, state=state)
    return (found[0], found[1]) if found else None


def get_fallback_centroid_tier(
    zip5: Optional[str] = None, state: Optional[str] = None
) -> Optional[Tuple[float, float, str]]:
    """Like get_fallback_centroid, but also reports which tier answered: ``"ZIP3"`` or ``"STATE"``."""
    if zip5:
        z_digits = re.sub(r"[^\d]", "", zip5.strip())
        if len(z_digits) == 4:
            z_digits = f"0{z_digits}"
        if len(z_digits) >= 3:
            z3 = z_digits[:3]
            if z3 in METRO_ZIP3_CENTROIDS:
                lat, lon = METRO_ZIP3_CENTROIDS[z3]
                return lat, lon, "ZIP3"
            st = ZIP3_TO_STATE.get(z3)
            if st and st in STATE_CENTROIDS:
                lat, lon = STATE_CENTROIDS[st]
                return lat, lon, "STATE"
    if state:
        s_clean = re.sub(r"[^\w\s]", "", state.strip().upper())
        st_code = US_STATES.get(s_clean, s_clean[:2] if len(s_clean) == 2 else s_clean)
        if st_code in STATE_CENTROIDS:
            lat, lon = STATE_CENTROIDS[st_code]
            return lat, lon, "STATE"
    return None


def parse_census_geocoder_response(response_text: str) -> Dict[str, Tuple[float, float, str]]:
    """
    Parses CSV output from the US Census Bureau Batch Geocoding API.
    Returns mapping: { id_str: (latitude, longitude, tiger_line_id) }

    Column 7 of the addressbatch format is the TIGER/Line edge id, *not* a census tract (tracts need the
    geographies endpoint), so it is exposed as ``tiger_line_id``.
    """
    results = {}
    reader = csv.reader(io.StringIO(response_text))
    for row in reader:
        if len(row) >= 6:
            rec_id = row[0].strip()
            match_status = row[2].strip() if len(row) > 2 else ""
            coords = row[5].strip() if len(row) > 5 else ""
            tiger_line_id = row[6].strip() if len(row) > 6 else ""

            if match_status.upper() == "MATCH" and coords and "," in coords:
                try:
                    lon_str, lat_str = coords.split(",")
                    results[rec_id] = (float(lat_str.strip()), float(lon_str.strip()), tiger_line_id)
                except Exception:
                    continue
    return results


class CensusGeocoder:
    """Client for US Census Bureau Batch and Single Geocoding API."""

    def __init__(self, timeout_seconds: int = 45):
        self.timeout = timeout_seconds

    def geocode_batch(
        self,
        records: List[Tuple[str, str, str, str, str]],
        fallback_to_centroids: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Geocodes a batch of records: [(id_str, street, city, state, zip_code), ...]
        Returns dict: { id_str: {'latitude': float, 'longitude': float, 'precision': 'rooftop'|'zip_centroid'} }
        """
        if not records:
            return {}

        csv_lines = []
        for rec_id, st1, city, state, zip_c in records:
            clean_st1 = (st1 or "").replace('"', '""')
            clean_city = (city or "").replace('"', '""')
            clean_state = (state or "").replace('"', '""')
            clean_zip = (zip_c or "").replace('"', '""')
            csv_lines.append(f'"{rec_id}","{clean_st1}","{clean_city}","{clean_state}","{clean_zip}"')

        csv_data = "\n".join(csv_lines).encode("utf-8")
        boundary = "---------------------------CensusBatchBoundary987654321"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="benchmark"\r\n\r\nPublic_AR_Current\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="addressFile"; filename="batch.csv"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8") + csv_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "AddressStandardizer/1.0 (Census Geocoder)"
        }

        output: Dict[str, Dict[str, Any]] = {}
        matched_ids = set()

        try:
            req = urllib.request.Request(CENSUS_BATCH_URL, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                resp_text = resp.read().decode("utf-8", errors="replace")
                results = parse_census_geocoder_response(resp_text)
                for rec_id, (lat, lon, tiger_line_id) in results.items():
                    output[rec_id] = {
                        "latitude": lat,
                        "longitude": lon,
                        "census_tract": None,
                        "tiger_line_id": tiger_line_id or None,
                        "precision": "rooftop",
                    }
                    matched_ids.add(rec_id)
        except Exception as ex:
            logger.warning(f"US Census batch geocoding error: {ex}")

        # Fallback to centroid for records not matched by Census
        if fallback_to_centroids:
            for rec_id, st1, city, state, zip_c in records:
                rec_id_str = str(rec_id)
                if rec_id_str not in matched_ids:
                    coords = get_fallback_centroid(zip5=zip_c, state=state)
                    if coords:
                        output[rec_id_str] = {
                            "latitude": coords[0],
                            "longitude": coords[1],
                            "census_tract": None,
                            "precision": "zip_centroid",
                        }

        return output

    def geocode_address(
        self,
        street: str,
        city: str = "",
        state: str = "",
        zip_code: str = "",
        fallback_to_centroids: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Geocodes a single address record."""
        res = self.geocode_batch(
            [("1", street, city, state, zip_code)],
            fallback_to_centroids=fallback_to_centroids,
        )
        return res.get("1")


class OfflineGeocoder:
    """
    Pure Offline Rooftop Geocoding & Interpolation Engine (Zero External APIs).
    Supports:
    1. Exact Rooftop matches (OpenAddresses / OfflineReferenceIndex)
    2. Linear interpolation along street edges (US Census TIGER)
    3. Locality / Postal centroid fallback
    Populates: latitude, longitude, precision (ROOFTOP, RANGE_INTERPOLATED, LOCALITY),
               accuracy_radius_meters, census_tract, and fips_code.
    """

    def __init__(self, index: Optional[Any] = None):
        if index is not None:
            self._index = index
        else:
            from address_standardizer.offline_index import get_default_offline_index
            self._index = get_default_offline_index()

    def geocode(self, address: Any, fallback_to_centroids: bool = True) -> Dict[str, Any]:
        """Geocodes a StandardizedAddress or address string completely offline."""
        if fallback_to_centroids and not getattr(address, "is_us", True):
            fallback_to_centroids = False
        return self._index.geocode(address, fallback_to_centroids=fallback_to_centroids)

    def geocode_address(
        self,
        street: str,
        city: str = "",
        state: str = "",
        zip_code: str = "",
        fallback_to_centroids: bool = True,
    ) -> Dict[str, Any]:
        """Geocodes address fields completely offline."""
        from address_standardizer.standardizer import standardize_address
        std = standardize_address(street1=street, city=city, state=state, postal_code=zip_code, enable_geocoding=False)
        return self.geocode(std, fallback_to_centroids=fallback_to_centroids)

    def geocode_batch(
        self,
        records: List[Tuple[str, str, str, str, str]],
        fallback_to_centroids: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Geocodes a batch of records completely offline:
        [(id_str, street, city, state, zip_code), ...]
        Returns dict: { id_str: {'latitude': float, 'longitude': float, 'precision': str, 'accuracy_radius_meters': float, 'census_tract': Optional[str], 'fips_code': Optional[str]} }
        """
        output: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            rec_id, st1, city, state, zip_c = rec
            output[str(rec_id)] = self.geocode_address(
                st1, city=city, state=state, zip_code=zip_c, fallback_to_centroids=fallback_to_centroids
            )
        return output


_DEFAULT_OFFLINE_GEOCODER: Optional[OfflineGeocoder] = None


def get_default_offline_geocoder() -> OfflineGeocoder:
    global _DEFAULT_OFFLINE_GEOCODER
    if _DEFAULT_OFFLINE_GEOCODER is None:
        _DEFAULT_OFFLINE_GEOCODER = OfflineGeocoder()
    return _DEFAULT_OFFLINE_GEOCODER


def geocode_offline(address: Any, fallback_to_centroids: bool = True) -> Dict[str, Any]:
    """Convenience functional interface for pure offline geocoding."""
    return get_default_offline_geocoder().geocode(address, fallback_to_centroids=fallback_to_centroids)
