"""Core immutable data models and enumerations for Phone Standardizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PhoneLineType:
    """Standardized ITU/NANP telephone line classification."""

    MOBILE = "MOBILE"
    FIXED_LINE = "FIXED_LINE"
    FIXED_LINE_OR_MOBILE = "FIXED_LINE_OR_MOBILE"
    TOLL_FREE = "TOLL_FREE"
    PREMIUM_RATE = "PREMIUM_RATE"
    SHARED_COST = "SHARED_COST"
    VOIP = "VOIP"
    PERSONAL_NUMBER = "PERSONAL_NUMBER"
    PAGER = "PAGER"
    UAN = "UAN"
    VOICEMAIL = "VOICEMAIL"
    SHORT_CODE = "SHORT_CODE"
    EMERGENCY = "EMERGENCY"
    UNKNOWN = "UNKNOWN"


class PhoneRoutingTier:
    """Data stewardship routing tiers based on composite confidence."""

    AUTO_PASS = "AUTO_PASS"
    FUZZY_REVIEW = "FUZZY_REVIEW"
    MANUAL_STEWARDSHIP = "MANUAL_STEWARDSHIP"


class PhoneRiskFlag:
    """Diagnostic risk and fraud flags surfaced during phone evaluation."""

    FICTITIOUS_RANGE = "FICTITIOUS_RANGE"
    REPEATING_DIGITS = "REPEATING_DIGITS"
    SEQUENTIAL_DIGITS = "SEQUENTIAL_DIGITS"
    PREMIUM_RATE_IRSF_RISK = "PREMIUM_RATE_IRSF_RISK"
    INVALID_LENGTH = "INVALID_LENGTH"
    INVALID_AREA_CODE = "INVALID_AREA_CODE"
    INVALID_EXCHANGE = "INVALID_EXCHANGE"
    UNASSIGNED_CALLING_CODE = "UNASSIGNED_CALLING_CODE"
    ADDRESS_COUNTRY_MISMATCH = "ADDRESS_COUNTRY_MISMATCH"


class HealingAction:
    """Auditable record of lexical and telephony healing transformations applied."""

    UNICODE_DIGITS_FOLDED = "UNICODE_DIGITS_FOLDED"
    VANITY_KEYPAD_DECODED = "VANITY_KEYPAD_DECODED"
    EXTENSION_EXTRACTED = "EXTENSION_EXTRACTED"
    IDD_EXIT_PREFIX_STRIPPED = "IDD_EXIT_PREFIX_STRIPPED"
    NATIONAL_TRUNK_STRIPPED = "NATIONAL_TRUNK_STRIPPED"
    REDUNDANT_INTL_TRUNK_STRIPPED = "REDUNDANT_INTL_TRUNK_STRIPPED"
    LEGACY_MEXICO_MOBILE_1_STRIPPED = "LEGACY_MEXICO_MOBILE_1_STRIPPED"
    ARGENTINA_MOBILE_15_HEALED = "ARGENTINA_MOBILE_15_HEALED"
    BRAZIL_MOBILE_9_INSERTED = "BRAZIL_MOBILE_9_INSERTED"
    COUNTRY_INFERRED_FROM_CONTEXT = "COUNTRY_INFERRED_FROM_CONTEXT"
    MULTI_NUMBER_PRIMARY_SELECTED = "MULTI_NUMBER_PRIMARY_SELECTED"


@dataclass(frozen=True)
class CountryDialPlan:
    """ITU-T E.164 and national dialing plan specification for an ISO-3166-1 jurisdiction."""

    iso2: str
    iso3: str
    numeric: str
    name: str
    calling_code: str
    idd_prefix: str = "00"
    national_trunk_prefix: str | None = "0"
    nsn_lengths: tuple[int, ...] = (8, 9, 10)
    mobile_prefixes: tuple[str, ...] = ()
    toll_free_prefixes: tuple[str, ...] = ("800",)
    premium_prefixes: tuple[str, ...] = ("900",)
    voip_prefixes: tuple[str, ...] = ()
    shared_cost_prefixes: tuple[str, ...] = ()
    region: str = "Global"

    def to_dict(self) -> dict[str, Any]:
        """Serialize dial plan metadata to a dictionary."""
        return {
            "iso2": self.iso2,
            "iso3": self.iso3,
            "numeric": self.numeric,
            "name": self.name,
            "calling_code": self.calling_code,
            "idd_prefix": self.idd_prefix,
            "national_trunk_prefix": self.national_trunk_prefix,
            "nsn_lengths": list(self.nsn_lengths),
            "mobile_prefixes": list(self.mobile_prefixes),
            "toll_free_prefixes": list(self.toll_free_prefixes),
            "premium_prefixes": list(self.premium_prefixes),
            "voip_prefixes": list(self.voip_prefixes),
            "shared_cost_prefixes": list(self.shared_cost_prefixes),
            "region": self.region,
        }


@dataclass(frozen=True)
class StandardizedPhone:
    """Immutable golden record produced by Phone Standardizer."""

    raw_input: str
    e164: str | None = None
    national: str | None = None
    international: str | None = None
    rfc3966: str | None = None
    country_calling_code: str | None = None
    country_iso2: str | None = None
    country_iso3: str | None = None
    country_name: str | None = None
    national_significant_number: str | None = None
    area_code: str | None = None
    subscriber_number: str | None = None
    extension: str | None = None
    vanity_alias: str | None = None
    region_code: str | None = None
    line_type: str = PhoneLineType.UNKNOWN
    is_valid: bool = False
    is_possible: bool = False
    phone_key: str | None = None
    phone_ext_key: str | None = None
    confidence: float = 0.0
    routing_tier: str = PhoneRoutingTier.MANUAL_STEWARDSHIP
    risk_flags: tuple[str, ...] = field(default_factory=tuple)
    healing_actions: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary of the standardized phone record."""
        return {
            "raw_input": self.raw_input,
            "e164": self.e164,
            "national": self.national,
            "international": self.international,
            "rfc3966": self.rfc3966,
            "country_calling_code": self.country_calling_code,
            "country_iso2": self.country_iso2,
            "country_iso3": self.country_iso3,
            "country_name": self.country_name,
            "national_significant_number": self.national_significant_number,
            "area_code": self.area_code,
            "subscriber_number": self.subscriber_number,
            "extension": self.extension,
            "vanity_alias": self.vanity_alias,
            "region_code": self.region_code,
            "line_type": self.line_type,
            "is_valid": self.is_valid,
            "is_possible": self.is_possible,
            "phone_key": self.phone_key,
            "phone_ext_key": self.phone_ext_key,
            "confidence": self.confidence,
            "routing_tier": self.routing_tier,
            "risk_flags": list(self.risk_flags),
            "healing_actions": list(self.healing_actions),
        }

    def as_dict(self) -> dict[str, Any]:
        """Alias for to_dict() for parity with Address-Standardizer."""
        return self.to_dict()
