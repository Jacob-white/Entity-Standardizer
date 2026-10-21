"""Phone Standardizer: Universal Multi-National Phone Standardization & Entity Resolution."""

from __future__ import annotations

from phone_standardizer._native_dispatch import (
    fold_vanity_digits_dispatch,
    get_engine_info,
    is_native_available,
)
from phone_standardizer.batch import (
    batch_standardize_phones,
    stream_standardize_csv,
    stream_standardize_jsonl,
)
from phone_standardizer.confidence import (
    evaluate_confidence_and_risk,
    has_repeating_subscriber_digits,
    has_sequential_subscriber_digits,
    is_fictitious_number,
)
from phone_standardizer.models import (
    CountryDialPlan,
    HealingAction,
    PhoneLineType,
    PhoneRiskFlag,
    PhoneRoutingTier,
    StandardizedPhone,
)
from phone_standardizer.nanp import resolve_nanp_npa
from phone_standardizer.normalization import (
    decode_vanity_phone,
    extract_extension,
    fold_unicode_digits,
)
from phone_standardizer.registry import (
    CountryDialRegistry,
    get_dial_plan,
    normalize_country_iso2,
)
from phone_standardizer.standardizer import (
    format_e164,
    format_international,
    format_national,
    format_rfc3966,
    mask_phone,
    standardize_phone,
    validate_phone,
)

__version__ = "1.0.0"

__all__ = [
    "CountryDialPlan",
    "CountryDialRegistry",
    "HealingAction",
    "PhoneLineType",
    "PhoneRiskFlag",
    "PhoneRoutingTier",
    "StandardizedPhone",
    "__version__",
    "batch_standardize_phones",
    "decode_vanity_phone",
    "evaluate_confidence_and_risk",
    "extract_extension",
    "fold_unicode_digits",
    "fold_vanity_digits_dispatch",
    "format_e164",
    "format_international",
    "format_national",
    "format_rfc3966",
    "get_dial_plan",
    "get_engine_info",
    "has_repeating_subscriber_digits",
    "has_sequential_subscriber_digits",
    "is_fictitious_number",
    "is_native_available",
    "mask_phone",
    "normalize_country_iso2",
    "resolve_nanp_npa",
    "standardize_phone",
    "stream_standardize_csv",
    "stream_standardize_jsonl",
    "validate_phone",
]
