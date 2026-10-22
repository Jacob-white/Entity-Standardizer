"""Phone Standardizer: Universal Multi-National Phone Standardization & Entity Resolution."""

from __future__ import annotations

from phone_standardizer._native_dispatch import (
    damerau_levenshtein_distance_dispatch,
    extract_digits_dispatch,
    fold_unicode_digits_dispatch,
    fold_vanity_digits_dispatch,
    get_engine_info,
    is_native_available,
    standardize_batch_e164_dispatch,
)
from phone_standardizer.arrow import (
    register_duckdb_udfs,
    standardize_arrow,
    standardize_polars,
)
from phone_standardizer.audit import (
    PhoneStewardshipLedger,
    explain_phone,
)
from phone_standardizer.batch import (
    batch_standardize_phones,
    stream_standardize_csv,
    stream_standardize_jsonl,
)
from phone_standardizer.cache import (
    LRUCache,
    MultiTierCache,
    SQLiteCache,
    clear_cache,
    configure_cache,
    get_cache_stats,
    get_default_cache,
    make_cache_key,
)
from phone_standardizer.confidence import (
    evaluate_confidence_and_risk,
    has_repeating_subscriber_digits,
    has_sequential_subscriber_digits,
    is_fictitious_number,
)
from phone_standardizer.dedup import (
    ContactCluster,
    PhoneCluster,
    PhoneComparisonResult,
    are_keypad_adjacent,
    cluster_contact_records,
    compare_phones,
    damerau_levenshtein_distance,
    deduplicate_phones,
    generate_phone_blocking_keys,
    infer_country_from_postal_code,
)
from phone_standardizer.intelligence import (
    CallingWindowResult,
    evaluate_calling_window,
    resolve_carrier_hint,
    resolve_locality,
    resolve_timezones,
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
    strip_leading_label,
)
from phone_standardizer.registry import (
    CountryDialRegistry,
    get_dial_plan,
    normalize_country_iso2,
)
from phone_standardizer.standardizer import (
    extract_phones_from_text,
    format_e164,
    format_international,
    format_national,
    format_rfc3966,
    mask_phone,
    standardize_phone,
    validate_phone,
)

__version__ = "1.3.0"

__all__ = [
    "CallingWindowResult",
    "ContactCluster",
    "CountryDialPlan",
    "CountryDialRegistry",
    "HealingAction",
    "LRUCache",
    "MultiTierCache",
    "PhoneCluster",
    "PhoneComparisonResult",
    "PhoneLineType",
    "PhoneRiskFlag",
    "PhoneRoutingTier",
    "PhoneStewardshipLedger",
    "SQLiteCache",
    "StandardizedPhone",
    "__version__",
    "are_keypad_adjacent",
    "batch_standardize_phones",
    "clear_cache",
    "cluster_contact_records",
    "compare_phones",
    "configure_cache",
    "damerau_levenshtein_distance",
    "damerau_levenshtein_distance_dispatch",
    "decode_vanity_phone",
    "deduplicate_phones",
    "evaluate_calling_window",
    "evaluate_confidence_and_risk",
    "explain_phone",
    "extract_digits_dispatch",
    "extract_extension",
    "extract_phones_from_text",
    "fold_unicode_digits",
    "fold_unicode_digits_dispatch",
    "fold_vanity_digits_dispatch",
    "format_e164",
    "format_international",
    "format_national",
    "format_rfc3966",
    "generate_phone_blocking_keys",
    "get_cache_stats",
    "get_default_cache",
    "get_dial_plan",
    "get_engine_info",
    "has_repeating_subscriber_digits",
    "has_sequential_subscriber_digits",
    "infer_country_from_postal_code",
    "is_fictitious_number",
    "is_native_available",
    "make_cache_key",
    "mask_phone",
    "normalize_country_iso2",
    "register_duckdb_udfs",
    "resolve_carrier_hint",
    "resolve_locality",
    "resolve_nanp_npa",
    "resolve_timezones",
    "standardize_arrow",
    "standardize_batch_e164_dispatch",
    "standardize_phone",
    "standardize_polars",
    "stream_standardize_csv",
    "stream_standardize_jsonl",
    "strip_leading_label",
    "validate_phone",
]
