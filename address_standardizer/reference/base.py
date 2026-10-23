"""Provider interfaces for authoritative reference data.

Two interfaces live here:

* :class:`ReferenceProvider` - open reference data (postal code -> places). Implemented by
  :class:`~address_standardizer.reference.geonames.GeoNamesPostalProvider`.
* :class:`AuthoritativeDeliveryProvider` - the plug-in point for a *licensed* delivery-point source (USPS AIS /
  CASS-certified software, or a commercial vendor). This package ships **no implementation** of it and no data:
  USPS Delivery Point Validation (DPV) results can only come from the licensed USPS product files, and this library
  does not simulate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

__all__ = [
    "ReferencePlace",
    "ReferenceProvider",
    "CompositeProvider",
    "DeliveryMatch",
    "DPV_MATCH_CODES",
    "AuthoritativeDeliveryProvider",
]


@dataclass(frozen=True)
class ReferencePlace:
    """One place (locality) that a reference source associates with a postal code."""

    country: str  # ISO 3166-1 alpha-2
    postal_code: str
    place_name: str
    admin1: str = ""  # state / province name
    admin1_code: str = ""  # state / province code (e.g. "NY", "ON")
    admin2: str = ""  # county / district name
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    provider: str = ""  # name of the provider that returned the row

    def as_dict(self) -> Dict[str, Any]:
        return {
            "country": self.country,
            "postal_code": self.postal_code,
            "place_name": self.place_name,
            "admin1": self.admin1,
            "admin1_code": self.admin1_code,
            "admin2": self.admin2,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "provider": self.provider,
        }


@runtime_checkable
class ReferenceProvider(Protocol):
    """Read-only source of postal-code reference data.

    ``name``, ``source`` (where the data came from), ``license`` and ``as_of`` (data vintage) are plain strings so
    results can always be traced back to their origin.
    """

    name: str
    source: str
    license: str
    as_of: str

    def covers_country(self, country: str) -> bool:
        """True if the provider holds data for the ISO alpha-2 ``country`` (absence is then meaningful)."""

    def lookup_postal(self, country: str, postal_code: str) -> List[ReferencePlace]:
        """Places for a postal code, or an empty list when the code is unknown."""

    def lookup_place(self, country: str, place_name: str, admin1_code: Optional[str] = None) -> List[str]:
        """Postal codes serving a place name (accent/case-insensitive exact name), optionally within a state."""


class CompositeProvider:
    """Queries several providers in priority order; the first that has an answer wins.

    ``covers_country`` is true if any member covers the country. ``lookup_postal`` / ``lookup_place`` return the
    first non-empty answer, so put the most authoritative provider first.
    """

    def __init__(self, providers: Sequence[ReferenceProvider]) -> None:
        if not providers:
            raise ValueError("CompositeProvider needs at least one provider")
        self.providers: List[ReferenceProvider] = list(providers)
        self.name = "composite(" + ",".join(p.name for p in self.providers) + ")"
        self.source = "; ".join(p.source for p in self.providers)
        self.license = "; ".join(p.license for p in self.providers)
        self.as_of = "; ".join(p.as_of for p in self.providers)

    def covers_country(self, country: str) -> bool:
        return any(p.covers_country(country) for p in self.providers)

    def lookup_postal(self, country: str, postal_code: str) -> List[ReferencePlace]:
        for provider in self.providers:
            places = provider.lookup_postal(country, postal_code)
            if places:
                return places
        return []

    def lookup_place(self, country: str, place_name: str, admin1_code: Optional[str] = None) -> List[str]:
        for provider in self.providers:
            codes = provider.lookup_place(country, place_name, admin1_code)
            if codes:
                return codes
        return []


# USPS DPV confirmation indicators (the public meaning of the codes; this library never produces them itself).
DPV_MATCH_CODES: Dict[str, str] = {
    "Y": "Confirmed: primary and secondary (if any) numbers matched a delivery point",
    "S": "Confirmed by dropping secondary information (secondary present but not matched)",
    "D": "Confirmed but missing secondary information (a secondary number is required)",
    "N": "Not confirmed: the address did not match a delivery point",
}


@dataclass
class DeliveryMatch:
    """Result of an authoritative delivery-point check (DPV-style)."""

    match_code: str  # one of DPV_MATCH_CODES, or a vendor-specific code documented by the adapter
    footnotes: List[str] = field(default_factory=list)  # DPV footnotes, e.g. "AA", "BB", "N1" (see delivery.DPVFootnote)
    provider: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"match_code": self.match_code, "footnotes": list(self.footnotes), "provider": self.provider}


@runtime_checkable
class AuthoritativeDeliveryProvider(Protocol):
    """Adapter interface for a licensed delivery-point validation source. NO IMPLEMENTATION IS PROVIDED.

    To get real USPS DPV you need a licensed product (USPS Address Information System data via a CASS-certified
    engine, or a commercial address-verification service). Write a small class that calls it and satisfies this
    protocol, then use it wherever you need authoritative deliverability; nothing in this package fabricates DPV
    results. ``verify`` receives a :class:`~address_standardizer.models.StandardizedAddress` and returns a
    :class:`DeliveryMatch`.
    """

    name: str
    source: str
    license: str
    as_of: str

    def verify(self, address: Any) -> DeliveryMatch:
        """Check one standardized address against the authoritative source."""
