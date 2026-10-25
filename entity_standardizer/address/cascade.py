"""
Graceful Cascading Fallback & Verification Topology.
===================================================
Implements the 4-stage graceful degradation cascade (Blueprint Section 3.5.2 & 4.4):
  Stage 1: Primary Rooftop DPV / Local Reference (< 5m, CONFIRMED_ROOFTOP)
  Stage 2: US Census TIGER Centerline Range (25 - 100m, FALLBACK_TIGER)
  Stage 3: Sectional Center ZIP3 Centroid (3 - 8 miles, FALLBACK_ZIP3)
  Stage 4: State Geographic Centroid (State-wide, FALLBACK_STATE)

Guarantees zero unhandled exceptions and zero-null coordinate output for valid locations.
"""

import re
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List

from entity_standardizer.address.tables import (
    ZIP3_TO_STATE,
    STATE_CENTROIDS,
    METRO_ZIP3_CENTROIDS,
    US_STATES,
)


class CascadePrecision:
    CONFIRMED_ROOFTOP = "CONFIRMED_ROOFTOP"
    FALLBACK_TIGER = "FALLBACK_TIGER"
    FALLBACK_ZIP3 = "FALLBACK_ZIP3"
    FALLBACK_STATE = "FALLBACK_STATE"


ACCURACY_RADII_METERS: Dict[str, float] = {
    CascadePrecision.CONFIRMED_ROOFTOP: 5.0,
    CascadePrecision.FALLBACK_TIGER: 100.0,
    CascadePrecision.FALLBACK_ZIP3: 8000.0,
    CascadePrecision.FALLBACK_STATE: 100000.0,
}


@dataclass
class CascadeResult:
    """Geographic resolution output from the verification cascade."""
    latitude: float
    longitude: float
    precision: str
    accuracy_radius_meters: float
    source: str
    stage: int
    census_tract: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "precision": self.precision,
            "accuracy_radius_meters": self.accuracy_radius_meters,
            "source": self.source,
            "stage": self.stage,
            "census_tract": self.census_tract,
        }


class VerificationCascade:
    """
    Orchestrates the 4-stage verification and geocoding fallback cascade.
    """

    def __init__(self, offline_index: Optional[Any] = None):
        self._local_rooftop_registry: Dict[str, Tuple[float, float]] = {}
        self._offline_index = offline_index

    def register_rooftop(self, address_key: str, lat: float, lon: float):
        """Registers a known rooftop/DPV delivery point in the local Stage 1 reference table."""
        clean_key = address_key.strip().upper()
        self._local_rooftop_registry[clean_key] = (lat, lon)

    def resolve(
        self,
        street1: Optional[str] = None,
        street2: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
        normalized_address_key: Optional[str] = None,
        census_geocoder: Optional[Any] = None,
        offline_index: Optional[Any] = None,
    ) -> Optional[CascadeResult]:
        """
        Cascades through Stages 1 -> 4 to resolve coordinates.
        Never throws exceptions on invalid or partial inputs.
        """
        # Stage 1: Local Rooftop Reference / DPV Lookup
        keys_to_check: List[str] = []
        if normalized_address_key:
            norm_key_clean = normalized_address_key.strip().upper()
            keys_to_check.append(norm_key_clean)
            parts = norm_key_clean.split("|")
            if len(parts) == 6 and parts[1]:
                keys_to_check.append(f"{parts[0]}||{'|'.join(parts[2:])}")
        elif street1:
            from entity_standardizer.address.standardizer import (
                generate_normalized_address_key,
                generate_building_key,
            )
            calc_key = generate_normalized_address_key(
                street1=street1,
                street2=street2,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country or "USA",
            )
            if calc_key:
                keys_to_check.append(calc_key.strip().upper())
            calc_bld = generate_building_key(
                street1=street1,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country or "USA",
            )
            if calc_bld:
                keys_to_check.append(calc_bld.strip().upper())

        if street1 and city and state and postal_code:
            zip5 = re.sub(r"[^\d]", "", postal_code)[:5]
            keys_to_check.append(f"{street1.strip().upper()}|{city.strip().upper()}|{state.strip().upper()}|{zip5}")

        for k in keys_to_check:
            if k in self._local_rooftop_registry:
                lat, lon = self._local_rooftop_registry[k]
                return CascadeResult(
                    latitude=lat,
                    longitude=lon,
                    precision=CascadePrecision.CONFIRMED_ROOFTOP,
                    accuracy_radius_meters=ACCURACY_RADII_METERS[CascadePrecision.CONFIRMED_ROOFTOP],
                    source="LOCAL_ROOFTOP_REGISTRY",
                    stage=1,
                )

        # Stage 1b: Offline Rooftop Reference Index
        active_offline = offline_index if offline_index is not None else self._offline_index
        if active_offline is not None:
            for k in keys_to_check:
                off_rec = active_offline.resolve_coordinates(k)
                if off_rec is not None:
                    return CascadeResult(
                        latitude=off_rec.latitude,
                        longitude=off_rec.longitude,
                        precision=CascadePrecision.CONFIRMED_ROOFTOP,
                        accuracy_radius_meters=off_rec.accuracy_radius_meters,
                        source="OFFLINE_ROOFTOP_INDEX",
                        stage=1,
                        census_tract=off_rec.census_tract,
                    )

        # Stage 2: Census TIGER Centerline / Batch Geocoder
        if census_geocoder and street1:
            try:
                geo_res = census_geocoder.geocode_batch(
                    [("1", street1, city or "", state or "", postal_code or "")],
                    fallback_to_centroids=False,
                )
                if "1" in geo_res and geo_res["1"].get("latitude") is not None:
                    match_data = geo_res["1"]
                    return CascadeResult(
                        latitude=float(match_data["latitude"]),
                        longitude=float(match_data["longitude"]),
                        precision=CascadePrecision.FALLBACK_TIGER,
                        accuracy_radius_meters=ACCURACY_RADII_METERS[CascadePrecision.FALLBACK_TIGER],
                        source="CENSUS_TIGER",
                        stage=2,
                        census_tract=match_data.get("census_tract"),
                    )
            except Exception:
                pass

        # Stage 3: Sectional Center Metro ZIP3 Centroid
        if postal_code:
            z_digits = re.sub(r"[^\d]", "", postal_code.strip())
            if len(z_digits) == 4:
                z_digits = f"0{z_digits}"
            if len(z_digits) >= 3:
                z3 = z_digits[:3]
                if z3 in METRO_ZIP3_CENTROIDS:
                    lat, lon = METRO_ZIP3_CENTROIDS[z3]
                    return CascadeResult(
                        latitude=lat,
                        longitude=lon,
                        precision=CascadePrecision.FALLBACK_ZIP3,
                        accuracy_radius_meters=ACCURACY_RADII_METERS[CascadePrecision.FALLBACK_ZIP3],
                        source="METRO_ZIP3_CENTROID",
                        stage=3,
                    )
                # If z3 not in METRO_ZIP3, check if it maps to a State Centroid
                st_from_z3 = ZIP3_TO_STATE.get(z3)
                if st_from_z3 and st_from_z3 in STATE_CENTROIDS:
                    lat, lon = STATE_CENTROIDS[st_from_z3]
                    return CascadeResult(
                        latitude=lat,
                        longitude=lon,
                        precision=CascadePrecision.FALLBACK_STATE,
                        accuracy_radius_meters=ACCURACY_RADII_METERS[CascadePrecision.FALLBACK_STATE],
                        source="STATE_CENTROID_FROM_ZIP3",
                        stage=4,
                    )

        # Stage 4: State Geographic Centroid
        if state:
            s_clean = re.sub(r"[^\w\s]", "", state.strip().upper())
            st_code = US_STATES.get(s_clean, s_clean[:2] if len(s_clean) == 2 else s_clean)
            if st_code in STATE_CENTROIDS:
                lat, lon = STATE_CENTROIDS[st_code]
                return CascadeResult(
                    latitude=lat,
                    longitude=lon,
                    precision=CascadePrecision.FALLBACK_STATE,
                    accuracy_radius_meters=ACCURACY_RADII_METERS[CascadePrecision.FALLBACK_STATE],
                    source="STATE_CENTROID",
                    stage=4,
                )

        return None


_DEFAULT_CASCADE = VerificationCascade()


def resolve_verification_cascade(
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    normalized_address_key: Optional[str] = None,
    census_geocoder: Optional[Any] = None,
    offline_index: Optional[Any] = None,
) -> Optional[CascadeResult]:
    """Convenience helper to resolve coordinates through the 4-stage cascade."""
    return _DEFAULT_CASCADE.resolve(
        street1=street1,
        street2=street2,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        normalized_address_key=normalized_address_key,
        census_geocoder=census_geocoder,
        offline_index=offline_index,
    )
