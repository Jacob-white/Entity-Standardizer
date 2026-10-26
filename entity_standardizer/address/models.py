"""Data structures for standardized address representations."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import re

_RE_PO_BOX_POST_INIT = re.compile(r"\b(?:P\.?\s*O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX|APO|FPO|DPO)\b")
_RE_DUAL_PHYSICAL_START = re.compile(r"^(?:\d+|PR-|CARR-|KM\b)")
_RE_HOUSE_NUMBER_PREFIX = re.compile(r"^(\d+[A-Z]?(?:-\d+)?)\b")


@dataclass(slots=True)
class SpatialResolutionResult:
    """Standardized geographic coordinate resolution result conforming to Blueprint Section 3.4."""
    latitude: float
    longitude: float
    precision: str  # CONFIRMED_ROOFTOP, RANGE_INTERPOLATED, POSTAL_CENTROID, MUNICIPAL_CENTROID, UNRESOLVED
    accuracy_radius_meters: float
    stage: int  # 1..4 (0 if UNRESOLVED)
    source: str
    h3_res10: str
    parcel_id: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        # An unresolved lookup has no location: report null instead of the (0, 0) "Null Island" placeholder so
        # consumers that only test `latitude is not None` do not treat it as a real point.
        unresolved = self.precision == "UNRESOLVED"
        return {
            "latitude": None if unresolved else self.latitude,
            "longitude": None if unresolved else self.longitude,
            "precision": self.precision,
            "accuracy_radius_meters": None if unresolved else self.accuracy_radius_meters,
            "stage": self.stage,
            "source": self.source,
            "h3_res10": self.h3_res10,
            "parcel_id": self.parcel_id,
            "execution_time_ms": self.execution_time_ms,
            "metadata": dict(self.metadata),
        }



class AddressStatus:
    STANDARDIZED = "standardized"
    PENDING = "pending"
    PARSE_FAILED = "parse_failed"
    MANUAL_OVERRIDE = "manual_override"
    LOCALITY_ONLY = "locality_only"
    CITY_LEVEL = "city_level"


class LocalityOnlyStatus(str):
    """String status representing locality-only / city-level standardization.

    Public contract: an instance compares equal to *both* ``"locality_only"`` and ``"city_level"`` (case-insensitive),
    which is what callers rely on. Python cannot give one hash to two different strings, so ``hash()`` follows the
    canonical ``"locality_only"`` spelling; do not use ``"city_level" in {status}`` for set/dict lookups. Test with
    ``status in ("locality_only", "city_level")`` (tuple membership uses ``==``), or ``StandardizedAddress.is_locality_only``.
    """

    def __eq__(self, other):
        if isinstance(other, str):
            o = other.lower()
            if o in ("locality_only", "city_level"):
                return True
        return super().__eq__(other)

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __hash__(self):
        return hash("locality_only")


@dataclass
class StandardizedAddress:
    """Standardized representation of a physical or mailing address."""
    street1: str
    street2: str
    city: str
    state: str
    postal_code: str
    country: str
    normalized_address_key: Optional[str]
    address_status: str  # 'standardized', 'pending', 'parse_failed', 'manual_override'
    raw_street_address: str
    is_us: bool
    is_private_residence: bool = False
    building_key: Optional[str] = None
    phonetic_key: Optional[str] = None
    is_registered_agent_hub: bool = False
    dependent_locality: Optional[str] = None
    building_name: Optional[str] = None
    care_of: Optional[str] = None  # text of a removed "c/o <name>" / "attn" clause, kept for reference
    rooftop_address: Optional[str] = None

    def __post_init__(self):
        has_po = bool(_RE_PO_BOX_POST_INIT.search(
            f"{self.street1} {self.street2} {self.raw_street_address}".upper()
        ))
        is_dual_physical = has_po and bool(self.street1 and _RE_DUAL_PHYSICAL_START.match(self.street1))
        if self.is_private_residence or (has_po and not is_dual_physical) or self.address_status in ("locality_only", "city_level", "parse_failed"):
            self.rooftop_address = None
        elif getattr(self, "rooftop_address", None) is None:
            from entity_standardizer.address._patterns import clean_rooftop_address
            self.rooftop_address = clean_rooftop_address(self.street1)
        if not hasattr(self, "_confidence_score"):
            self._confidence_score: Optional[float] = None
        if not hasattr(self, "_routing_tier"):
            self._routing_tier: Optional[str] = None
        if not hasattr(self, "_failure_reason_codes"):
            self._failure_reason_codes: Optional[List[str]] = None
        if not hasattr(self, "_audit_record"):
            self._audit_record: Optional[Any] = None
        if not hasattr(self, "_cascade_result"):
            self._cascade_result: Optional[Any] = None
        if not hasattr(self, "_rdi"):
            self._rdi: str = "Unknown"
        if not hasattr(self, "_cmra"):
            self._cmra: bool = False
        if not hasattr(self, "_vacant"):
            self._vacant: bool = False
        if not hasattr(self, "_dpv_footnotes"):
            self._dpv_footnotes: Optional[List[str]] = None
        if not hasattr(self, "_corporate_risk_score"):
            self._corporate_risk_score: float = 0.0
        if not hasattr(self, "_corporate_risk_flags"):
            self._corporate_risk_flags: Optional[List[str]] = None
        if not hasattr(self, "_spatial_result"):
            self._spatial_result: Optional[SpatialResolutionResult] = None
        if not hasattr(self, "_deliverability"):
            self._deliverability: Optional[str] = None
        if not hasattr(self, "_latitude"):
            self._latitude: Optional[float] = None
        if not hasattr(self, "_longitude"):
            self._longitude: Optional[float] = None
        if not hasattr(self, "_precision"):
            self._precision: Optional[str] = None
        if not hasattr(self, "_accuracy_radius_meters"):
            self._accuracy_radius_meters: Optional[float] = None
        if not hasattr(self, "_census_tract"):
            self._census_tract: Optional[str] = None
        if not hasattr(self, "_fips_code"):
            self._fips_code: Optional[str] = None
        if not hasattr(self, "_country_iso3"):
            self._country_iso3: str = getattr(self, "country", "USA") or "USA"
        if not hasattr(self, "_is_locality_only"):
            self._is_locality_only: bool = self.address_status in ("locality_only", "city_level")

    @property
    def confidence_score(self) -> Optional[float]:
        return getattr(self, "_confidence_score", None)

    @confidence_score.setter
    def confidence_score(self, value: Optional[float]):
        self._confidence_score = value

    @property
    def routing_tier(self) -> Optional[str]:
        return getattr(self, "_routing_tier", None)

    @routing_tier.setter
    def routing_tier(self, value: Optional[str]):
        self._routing_tier = value

    @property
    def failure_reason_codes(self) -> List[str]:
        val = getattr(self, "_failure_reason_codes", None)
        return list(val) if val is not None else []

    @failure_reason_codes.setter
    def failure_reason_codes(self, value: List[str]):
        self._failure_reason_codes = list(value)

    @property
    def audit_record(self) -> Optional[Any]:
        return getattr(self, "_audit_record", None)

    @audit_record.setter
    def audit_record(self, value: Optional[Any]):
        self._audit_record = value

    @property
    def cascade_result(self) -> Optional[Any]:
        return getattr(self, "_cascade_result", None)

    @cascade_result.setter
    def cascade_result(self, value: Optional[Any]):
        self._cascade_result = value

    @property
    def rdi(self) -> str:
        return getattr(self, "_rdi", "Unknown")

    @rdi.setter
    def rdi(self, value: str):
        self._rdi = value

    @property
    def cmra(self) -> bool:
        return getattr(self, "_cmra", False)

    @cmra.setter
    def cmra(self, value: bool):
        self._cmra = bool(value)

    @property
    def is_cmra(self) -> bool:
        return self.cmra

    @is_cmra.setter
    def is_cmra(self, value: bool):
        self.cmra = value

    @property
    def vacant(self) -> bool:
        return getattr(self, "_vacant", False)

    @vacant.setter
    def vacant(self, value: bool):
        self._vacant = bool(value)

    @property
    def is_vacant(self) -> bool:
        return self.vacant

    @is_vacant.setter
    def is_vacant(self, value: bool):
        self.vacant = value

    @property
    def dpv_footnotes(self) -> List[str]:
        val = getattr(self, "_dpv_footnotes", None)
        return list(val) if val is not None else []

    @dpv_footnotes.setter
    def dpv_footnotes(self, value: List[str]):
        self._dpv_footnotes = list(value)

    @property
    def corporate_risk_score(self) -> float:
        return getattr(self, "_corporate_risk_score", 0.0)

    @corporate_risk_score.setter
    def corporate_risk_score(self, value: float):
        self._corporate_risk_score = float(value)

    @property
    def corporate_risk_flags(self) -> List[str]:
        val = getattr(self, "_corporate_risk_flags", None)
        return list(val) if val is not None else []

    @corporate_risk_flags.setter
    def corporate_risk_flags(self, value: List[str]):
        self._corporate_risk_flags = list(value)

    @property
    def spatial_result(self) -> Optional[SpatialResolutionResult]:
        return getattr(self, "_spatial_result", None)

    @spatial_result.setter
    def spatial_result(self, value: Optional[SpatialResolutionResult]):
        self._spatial_result = value

    @property
    def deliverability(self) -> str:
        val = getattr(self, "_deliverability", None)
        if val is not None:
            return val
        footnotes = set(self.dpv_footnotes)
        if "N1" in footnotes:
            return "REQUIRES_SECONDARY"
        if "BB" in footnotes:
            return "DELIVERABLE"
        if self.address_status == "parse_failed" or "M1" in footnotes or "M3" in footnotes:
            return "UNDELIVERABLE"
        return "DELIVERABLE" if self.address_status == "standardized" else "UNDELIVERABLE"

    @deliverability.setter
    def deliverability(self, value: str):
        self._deliverability = value

    @property
    def secondary_prompt_required(self) -> bool:
        return "N1" in self.dpv_footnotes or getattr(self, "_secondary_prompt_required", False)

    @secondary_prompt_required.setter
    def secondary_prompt_required(self, value: bool):
        self._secondary_prompt_required = bool(value)

    @property
    def prompt_message(self) -> Optional[str]:
        val = getattr(self, "_prompt_message", None)
        if val is not None:
            return val
        if self.secondary_prompt_required:
            return "Requires Suite / Apartment Number"
        return None

    @prompt_message.setter
    def prompt_message(self, value: Optional[str]):
        self._prompt_message = value

    @property
    def suggested_secondary_units(self) -> List[str]:
        val = getattr(self, "_suggested_secondary_units", None)
        if val is not None:
            return list(val)
        if self.secondary_prompt_required:
            return ["STE", "FL", "UNIT", "APT"]
        return []

    @suggested_secondary_units.setter
    def suggested_secondary_units(self, value: List[str]):
        self._suggested_secondary_units = list(value)

    @property
    def latitude(self) -> Optional[float]:
        val = getattr(self, "_latitude", None)
        if val is not None:
            return val
        if self.spatial_result is not None and self.spatial_result.precision != "UNRESOLVED":
            return self.spatial_result.latitude
        return None

    @latitude.setter
    def latitude(self, value: Optional[float]):
        self._latitude = value

    @property
    def longitude(self) -> Optional[float]:
        val = getattr(self, "_longitude", None)
        if val is not None:
            return val
        if self.spatial_result is not None and self.spatial_result.precision != "UNRESOLVED":
            return self.spatial_result.longitude
        return None

    @longitude.setter
    def longitude(self, value: Optional[float]):
        self._longitude = value

    @property
    def precision(self) -> Optional[str]:
        val = getattr(self, "_precision", None)
        if val is not None:
            return val
        if self.spatial_result is not None:
            return self.spatial_result.precision
        return None

    @precision.setter
    def precision(self, value: Optional[str]):
        self._precision = value

    @property
    def accuracy_radius_meters(self) -> Optional[float]:
        val = getattr(self, "_accuracy_radius_meters", None)
        if val is not None:
            return val
        if self.spatial_result is not None:
            return self.spatial_result.accuracy_radius_meters
        return None

    @accuracy_radius_meters.setter
    def accuracy_radius_meters(self, value: Optional[float]):
        self._accuracy_radius_meters = value

    @property
    def census_tract(self) -> Optional[str]:
        val = getattr(self, "_census_tract", None)
        if val is not None:
            return val
        if self.spatial_result is not None and hasattr(self.spatial_result, "metadata") and isinstance(self.spatial_result.metadata, dict):
            return self.spatial_result.metadata.get("census_tract")
        return None

    @census_tract.setter
    def census_tract(self, value: Optional[str]):
        self._census_tract = value

    @property
    def fips_code(self) -> Optional[str]:
        val = getattr(self, "_fips_code", None)
        if val is not None:
            return val
        if self.spatial_result is not None and hasattr(self.spatial_result, "metadata") and isinstance(self.spatial_result.metadata, dict):
            return self.spatial_result.metadata.get("fips_code")
        return None

    @fips_code.setter
    def fips_code(self, value: Optional[str]):
        self._fips_code = value

    @property
    def reference_validation(self) -> Optional[Any]:
        """Set only when ``standardize_address(..., reference_provider=...)`` was used."""
        return getattr(self, "_reference_validation", None)

    @reference_validation.setter
    def reference_validation(self, value: Optional[Any]):
        self._reference_validation = value

    @property
    def explanation(self) -> Optional[List[Dict[str, Any]]]:
        """Ordered change records; set only when ``standardize_address(..., explain=True)`` was used."""
        return getattr(self, "_explanation", None)

    @explanation.setter
    def explanation(self, value: Optional[List[Dict[str, Any]]]):
        self._explanation = value

    @property
    def field_confidence(self) -> Optional[Dict[str, float]]:
        """Per-field confidence in [0, 1]; set only with ``explain=True`` (heuristic unless calibrated)."""
        return getattr(self, "_field_confidence", None)

    @field_confidence.setter
    def field_confidence(self, value: Optional[Dict[str, float]]):
        self._field_confidence = value

    @property
    def alternatives(self) -> Optional[List[Dict[str, Any]]]:
        """Next-best interpretations; set only when ``standardize_address(..., alternatives=N)`` was used."""
        return getattr(self, "_alternatives", None)

    @alternatives.setter
    def alternatives(self, value: Optional[List[Dict[str, Any]]]):
        self._alternatives = value

    @property
    def country_iso3(self) -> str:
        return getattr(self, "_country_iso3", getattr(self, "country", "USA") or "USA")

    @country_iso3.setter
    def country_iso3(self, value: str):
        self._country_iso3 = value

    @property
    def is_locality_only(self) -> bool:
        return self.address_status in ("locality_only", "city_level") or getattr(self, "_is_locality_only", False)

    @is_locality_only.setter
    def is_locality_only(self, value: bool):
        self._is_locality_only = bool(value)

    @property
    def is_city_level(self) -> bool:
        return self.is_locality_only

    @is_city_level.setter
    def is_city_level(self, value: bool):
        self._is_locality_only = bool(value)

    @property
    def full_rooftop_address(self) -> Optional[str]:
        """Single-line formatted rooftop address (excludes secondary units like suite, apt, fl)."""
        if not self.rooftop_address:
            return None
        parts = [self.rooftop_address]
        if self.city:
            parts.append(self.city)
        if self.state and self.postal_code:
            parts.append(f"{self.state} {self.postal_code}")
        elif self.state:
            parts.append(self.state)
        elif self.postal_code:
            parts.append(self.postal_code)
        if self.country and self.country not in ("USA", "US"):
            parts.append(self.country)
        return ", ".join(parts)

    def as_dict(
        self, include_metadata: bool = False, include_rooftop: bool = False, include_explanation: bool = False
    ) -> Dict[str, Any]:
        d = {
            "street1": self.street1,
            "street2": self.street2,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "normalized_address_key": self.normalized_address_key,
            "building_key": self.building_key,
            "phonetic_key": self.phonetic_key,
            "address_status": self.address_status,
            "raw_street_address": self.raw_street_address,
            "is_us": self.is_us,
            "is_private_residence": self.is_private_residence,
            "is_registered_agent_hub": self.is_registered_agent_hub,
        }
        if include_rooftop:
            d["rooftop_address"] = self.rooftop_address
            d["full_rooftop_address"] = self.full_rooftop_address
        if include_metadata:
            d["rooftop_address"] = self.rooftop_address
            d["full_rooftop_address"] = self.full_rooftop_address
            d["is_locality_only"] = self.is_locality_only
            d["is_city_level"] = self.is_city_level
            d["dependent_locality"] = self.dependent_locality
            d["building_name"] = self.building_name
            d["care_of"] = self.care_of
            d["confidence_score"] = self.confidence_score
            d["routing_tier"] = self.routing_tier
            d["failure_reason_codes"] = self.failure_reason_codes
            d["rdi"] = self.rdi
            d["cmra"] = self.cmra
            d["is_cmra"] = self.is_cmra
            d["vacant"] = self.vacant
            d["is_vacant"] = self.is_vacant
            d["dpv_footnotes"] = self.dpv_footnotes
            d["corporate_risk_score"] = self.corporate_risk_score
            d["corporate_risk_flags"] = self.corporate_risk_flags
            if self.audit_record is not None:
                d["audit_id"] = getattr(self.audit_record, "audit_id", None)
            if self.cascade_result is not None:
                d["cascade"] = (
                    self.cascade_result.as_dict()
                    if hasattr(self.cascade_result, "as_dict")
                    else self.cascade_result
                )
            d["deliverability"] = self.deliverability
            d["secondary_prompt_required"] = self.secondary_prompt_required
            d["prompt_message"] = self.prompt_message
            d["suggested_secondary_units"] = list(self.suggested_secondary_units)
            unresolved = self.precision == "UNRESOLVED"
            d["latitude"] = None if unresolved else self.latitude
            d["longitude"] = None if unresolved else self.longitude
            d["precision"] = self.precision
            d["accuracy_radius_meters"] = None if unresolved else self.accuracy_radius_meters
            d["census_tract"] = self.census_tract
            d["fips_code"] = self.fips_code
            if self.spatial_result is not None:
                d["spatial_result"] = (
                    self.spatial_result.as_dict()
                    if hasattr(self.spatial_result, "as_dict")
                    else self.spatial_result
                )
            else:
                d["spatial_result"] = None
            d["country_iso3"] = self.country_iso3
            if self.reference_validation is not None:
                d["reference_validation"] = self.reference_validation.as_dict()
        if include_explanation or include_metadata:
            # Present only when explain=True / alternatives=N was requested; the default result never carries them.
            if self.explanation is not None:
                d["explanation"] = [dict(r) for r in self.explanation]
            if self.field_confidence is not None:
                d["field_confidence"] = dict(self.field_confidence)
            if self.alternatives is not None:
                d["alternatives"] = [dict(a) for a in self.alternatives]
        return d

    @property
    def secondary_unit(self) -> str:
        return self.street2

    @property
    def phonetic_address_key(self) -> Optional[str]:
        return self.phonetic_key

    @property
    def house_number(self) -> Optional[str]:
        m = _RE_HOUSE_NUMBER_PREFIX.match((self.street1 or "").strip())
        return m.group(1) if m else None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the standardized address record into a JSON-compatible dictionary."""
        d = self.as_dict(include_explanation=self.explanation is not None)
        if self.spatial_result is not None or self.latitude is not None:
            unresolved = self.precision == "UNRESOLVED"
            d["latitude"] = None if unresolved else self.latitude
            d["longitude"] = None if unresolved else self.longitude
            d["precision"] = self.precision
            d["accuracy_radius_meters"] = None if unresolved else self.accuracy_radius_meters
            d["census_tract"] = self.census_tract
            d["fips_code"] = self.fips_code
            d["spatial_result"] = (
                self.spatial_result.as_dict()
                if hasattr(self.spatial_result, "as_dict")
                else self.spatial_result
            )
        return d

    def as_extended_dict(self) -> Dict[str, Any]:
        """Returns comprehensive enterprise dictionary including all risk, confidence, and audit metadata."""
        return self.as_dict(include_metadata=True)

    def format_upu(
        self,
        recipient: Optional[str] = None,
        include_country_name: bool = True,
    ) -> str:
        """Render address in Universal Postal Union (UPU S42) envelope layout."""
        from entity_standardizer.address.international.upu import format_upu_address

        return format_upu_address(
            self,
            recipient=recipient,
            include_country_name=include_country_name,
        )
