"""Validate a standardized address against a reference provider (postal code / place / state consistency).

What this checks: that the postal code exists, that the locality plausibly belongs to it, and (US/CA) that the state
agrees with it. What it does NOT check: that the street or house number exists, or that mail is deliverable there
(that needs a licensed delivery-point source, see ``AuthoritativeDeliveryProvider``).
"""

from __future__ import annotations

import logging
import math
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from address_standardizer.international.countries import CountryRegistry
from address_standardizer.reference._match import names_match
from address_standardizer.reference.base import ReferencePlace, ReferenceProvider

logger = logging.getLogger(__name__)

__all__ = [
    "ERR_POSTAL_UNKNOWN",
    "ERR_POSTAL_STATE_MISMATCH",
    "WARN_POSTAL_PLACE_MISMATCH",
    "REFERENCE_DB_ENV",
    "ReferenceValidation",
    "validate_against_reference",
    "apply_reference_validation",
    "attach_server_reference_validation",
]

ERR_POSTAL_UNKNOWN = "ERR_POSTAL_UNKNOWN"
ERR_POSTAL_STATE_MISMATCH = "ERR_POSTAL_STATE_MISMATCH"
WARN_POSTAL_PLACE_MISMATCH = "WARN_POSTAL_PLACE_MISMATCH"

REFERENCE_DB_ENV = "ADDRESS_STANDARDIZER_REFERENCE_DB"
_STATE_COUNTRIES = ("US", "CA")
_MAX_CANDIDATES = 10
_EARTH_RADIUS_KM = 6371.0088


@dataclass
class ReferenceValidation:
    """Outcome of checking one address against reference data.

    ``status``: ``confirmed`` (every check that could run passed), ``postal_unknown`` (the reference has data for the
    country but not this postal code), ``place_mismatch`` (the postal code exists but none of its places resembles the
    city), ``state_mismatch`` (US/CA state differs from the postal code's state), ``not_checked`` (no postal code,
    unrecognised country, or the provider has no data for the country: absence of data is not evidence of an error).
    ``checks`` lists the checks that actually ran (``postal``, ``state``, ``place``).
    """

    status: str
    provider: str = ""
    source: str = ""
    license: str = ""
    as_of: str = ""
    country: str = ""
    postal_code: str = ""
    matched_place: Optional[ReferencePlace] = None
    distance_km: Optional[float] = None
    reason_codes: List[str] = field(default_factory=list)
    checks: List[str] = field(default_factory=list)
    candidate_places: List[str] = field(default_factory=list)
    detail: str = ""

    @property
    def is_confirmed(self) -> bool:
        return self.status == "confirmed"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "source": self.source,
            "license": self.license,
            "as_of": self.as_of,
            "country": self.country,
            "postal_code": self.postal_code,
            "matched_place": self.matched_place.as_dict() if self.matched_place is not None else None,
            "distance_km": self.distance_km,
            "reason_codes": list(self.reason_codes),
            "checks": list(self.checks),
            "candidate_places": list(self.candidate_places),
            "detail": self.detail,
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def validate_against_reference(std_address: Any, provider: ReferenceProvider) -> ReferenceValidation:
    """Check a :class:`~address_standardizer.models.StandardizedAddress` against ``provider``. See the module docs."""
    info = CountryRegistry.get(getattr(std_address, "country", None))
    iso2 = info.alpha2 if info is not None else ""
    postal = (getattr(std_address, "postal_code", "") or "").strip()

    def result(status: str, **fields: Any) -> ReferenceValidation:
        return ReferenceValidation(
            status=status, provider=provider.name, source=provider.source, license=provider.license,
            as_of=provider.as_of, country=iso2, postal_code=postal, **fields,
        )

    if not iso2:
        return result("not_checked", detail="country not recognised")
    if not postal:
        return result("not_checked", detail="no postal code to check")
    if not provider.covers_country(iso2):
        return result("not_checked", detail=f"provider has no data for {iso2}")

    places = provider.lookup_postal(iso2, postal)
    if not places:
        return result(
            "postal_unknown", reason_codes=[ERR_POSTAL_UNKNOWN], checks=["postal"],
            detail=f"postal code {postal} is not in the reference data for {iso2}",
        )

    checks = ["postal"]
    codes: List[str] = []
    state = (getattr(std_address, "state", "") or "").strip().upper()
    state_mismatch = False
    if iso2 in _STATE_COUNTRIES and state:
        known = {p.admin1_code.upper() for p in places if p.admin1_code}
        if known:
            checks.append("state")
            if state not in known:
                state_mismatch = True
                codes.append(ERR_POSTAL_STATE_MISMATCH)

    names = [n for n in (getattr(std_address, "city", ""), getattr(std_address, "dependent_locality", "")) if n]
    matched: Optional[ReferencePlace] = None
    place_mismatch = False
    candidates: List[str] = []
    if names:
        checks.append("place")
        # Prefer places in the supplied state so a ZIP that spans two states resolves to the right locality.
        ordered = sorted(places, key=lambda p: p.admin1_code.upper() != state)
        matched = next(
            (p for p in ordered if any(names_match(n, ref) for n in names for ref in (p.place_name, p.admin2) if ref)),
            None,
        )
        if matched is None:
            place_mismatch = True
            codes.append(WARN_POSTAL_PLACE_MISMATCH)
            candidates = list(dict.fromkeys(p.place_name for p in places))[:_MAX_CANDIDATES]
    elif len(places) == 1:
        matched = places[0]

    distance: Optional[float] = None
    ref = matched or places[0]
    lat, lon = getattr(std_address, "latitude", None), getattr(std_address, "longitude", None)
    if lat is not None and lon is not None and ref.latitude is not None and ref.longitude is not None:
        distance = round(_haversine_km(lat, lon, ref.latitude, ref.longitude), 3)

    if state_mismatch:
        status, detail = "state_mismatch", f"state {state} does not match the state(s) for postal code {postal}"
    elif place_mismatch:
        status, detail = "place_mismatch", f"city does not resemble any place for postal code {postal}"
    else:
        status, detail = "confirmed", "postal code known; checks passed: " + ", ".join(checks)
    return result(
        status, matched_place=matched, distance_km=distance, reason_codes=codes, checks=checks,
        candidate_places=candidates, detail=detail,
    )


def apply_reference_validation(std_address: Any, provider: ReferenceProvider) -> Any:
    """Validate, attach the result as ``std_address.reference_validation`` and merge its reason codes."""
    validation = validate_against_reference(std_address, provider)
    std_address.reference_validation = validation
    existing = list(std_address.failure_reason_codes)
    std_address.failure_reason_codes = existing + [c for c in validation.reason_codes if c not in existing]
    conf = getattr(std_address, "confidence_score", None)
    if conf is not None and conf > 0.0:
        if ERR_POSTAL_UNKNOWN in validation.reason_codes or ERR_POSTAL_STATE_MISMATCH in validation.reason_codes:
            std_address.confidence_score = round(max(0.0, std_address.confidence_score - 0.25), 4)
            if std_address.confidence_score < 0.80:
                std_address.routing_tier = "MANUAL_STEWARDSHIP"
            else:
                std_address.routing_tier = "FUZZY_REVIEW"
        elif WARN_POSTAL_PLACE_MISMATCH in validation.reason_codes:
            std_address.confidence_score = round(max(0.0, std_address.confidence_score - 0.12), 4)
            if getattr(std_address, "routing_tier", "") == "AUTO_PASS":
                std_address.routing_tier = "FUZZY_REVIEW"
    return std_address


_server_lock = threading.Lock()
_server_providers: Dict[str, Any] = {}


def close_server_providers() -> None:
    """Close and forget the providers cached for the REST server (used by tests and on shutdown)."""
    with _server_lock:
        for provider in _server_providers.values():
            provider.close()
        _server_providers.clear()


def server_reference_provider() -> Optional[Any]:
    """The provider the REST server validates against, or None when ``ADDRESS_STANDARDIZER_REFERENCE_DB`` is unset or
    the database cannot be opened (``attach_server_reference_validation`` reports that case in its response)."""
    path = os.environ.get(REFERENCE_DB_ENV)
    if not path:
        return None
    from address_standardizer.reference.geonames import GeoNamesPostalProvider

    try:
        with _server_lock:
            provider = _server_providers.get(path)
            if provider is None:
                provider = _server_providers[path] = GeoNamesPostalProvider(path)
    except (OSError, ValueError):
        return None
    return provider


def attach_server_reference_validation(std_address: Any, response: Dict[str, Any]) -> Dict[str, Any]:
    """Add a ``reference_validation`` object to a REST response, only when ``ADDRESS_STANDARDIZER_REFERENCE_DB`` is set.

    With the variable unset the response is returned untouched. If the database cannot be opened the object is still
    added, with status ``not_checked`` and the reason in ``detail``, so a misconfiguration is visible, not silent (the cause is logged, not returned).
    """
    path = os.environ.get(REFERENCE_DB_ENV)
    if not path:
        return response
    from address_standardizer.reference.geonames import GeoNamesPostalProvider

    try:
        with _server_lock:
            provider = _server_providers.get(path)
            if provider is None:
                provider = _server_providers[path] = GeoNamesPostalProvider(path)
    except (OSError, ValueError):
        # The exception text can carry a server filesystem path, so it goes to the log, not the response.
        logger.exception("Reference database %s could not be opened", REFERENCE_DB_ENV)
        response["reference_validation"] = {
            "status": "not_checked", "reason_codes": [],
            "detail": "reference database unavailable (see the server log)",
        }
        return response
    response["reference_validation"] = validate_against_reference(std_address, provider).as_dict()
    return response
