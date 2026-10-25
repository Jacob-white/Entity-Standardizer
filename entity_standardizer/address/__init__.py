"""
Address Standardizer Subpackage (entity_standardizer.address)
=============================================================
High-performance, universal multi-national address standardization, offline spatial rooftop geocoding,
and cross-border corporate entity resolution platform.
Adheres to USPS Publication 28, Universal Postal Union (UPU) S42, and ISO 19160-4 standards.
"""

from typing import Any

__version__ = "2.1.0"

from entity_standardizer._native_dispatch import is_native_available
from entity_standardizer.address._native_dispatch import (
    get_engine_info,
    is_using_native,
    standardize_batch_dispatch,
)
from entity_standardizer.address._patterns import clean_rooftop_address
from entity_standardizer.address.audit import (
    AUDIT_LEDGER_DDL,
    ActionType,
    ReviewStatus,
    StewardshipAuditLedger,
    StewardshipAuditRecord,
    get_audit_ledger,
)
from entity_standardizer.address.autocomplete import (
    AutocompleteEngine,
    AutocompleteSuggestion,
    autocomplete_address,
)
from entity_standardizer.address.batch import (
    batch_standardize,
    buffered_chunk_generator,
    chunk_generator,
    process_chunk,
    stream_standardize_csv,
    stream_standardize_json,
    stream_standardize_jsonl,
)
from entity_standardizer.address.cache import (
    LRUCache,
    MultiTierCache,
    SQLiteCache,
    clear_cache,
    configure_cache,
    get_cache_stats,
    get_default_cache,
    make_cache_key,
)
from entity_standardizer.address.confidence import (
    ConfidenceResult,
    ConfidenceScorer,
    RoutingTier,
    compute_confidence_score,
)
from entity_standardizer.address.delivery import (
    RDI,
    DeliveryIntelligenceResult,
    DPVFootnote,
    evaluate_delivery_intelligence,
)
from entity_standardizer.address.fuzzy import (
    PROTECTED_STREET_WORDS,
    damerau_levenshtein_distance,
    heal_city_token,
    heal_postal_code_transposition,
    heal_street_name,
    heal_street_number_transposition,
    heal_street_suffix,
)
from entity_standardizer.address.geocoder import (
    CascadePrecision,
    CascadeResult,
    CensusGeocoder,
    VerificationCascade,
    get_fallback_centroid,
    resolve_verification_cascade,
)
from entity_standardizer.address.international import (
    CountryInfo,
    CountryRegistry,
    PostalValidationResult,
    extract_postal_code,
    format_upu_address,
    validate_postal_code,
)
from entity_standardizer.address.models import SpatialResolutionResult, StandardizedAddress
from entity_standardizer.address.offline_index import (
    OfflineReferenceIndex,
    ParcelValidationResult,
    RooftopRecord,
    get_default_offline_index,
    resolve_offline_coordinates,
    validate_parcel_offline,
)
from entity_standardizer.address.phonetics import (
    compute_soundex,
    generate_phonetic_address_key,
)
from entity_standardizer.address.reference import (
    ReferencePlace,
    ReferenceProvider,
    ReferenceValidation,
    USZip5Provider,
    get_default_us_zip5_provider,
    validate_against_reference,
)
from entity_standardizer.address.registry import (
    CURATED_CORPORATE_REGISTRY,
    CorporateRegistryEntry,
    CorporateRiskFlag,
    RegistryCategory,
    can_safely_merge_corporate_entities,
    evaluate_corporate_risk,
    lookup_corporate_registry,
)
from entity_standardizer.address.standardizer import (
    AddressValidationResult,
    _split_international_secondary_unit,
    generate_building_key,
    generate_normalized_address_key,
    get_state_from_zip3,
    is_registered_agent_hub_address,
    normalize_country,
    normalize_country_code,
    normalize_us_postal_code,
    normalize_us_state,
    num_to_ordinal,
    standardize_address,
    validate_address,
)

__all__ = [
    "AUDIT_LEDGER_DDL",
    "CURATED_CORPORATE_REGISTRY",
    "PROTECTED_STREET_WORDS",
    "RDI",
    "ActionType",
    "AddressValidationResult",
    "AutocompleteEngine",
    "AutocompleteSuggestion",
    "CascadePrecision",
    "CascadeResult",
    "CensusGeocoder",
    "ConfidenceResult",
    "ConfidenceScorer",
    "CorporateRegistryEntry",
    "CorporateRiskFlag",
    "CountryInfo",
    "CountryRegistry",
    "DPVFootnote",
    "DeliveryIntelligenceResult",
    "LRUCache",
    "MultiTierCache",
    "OfflineReferenceIndex",
    "ParcelValidationResult",
    "PostalValidationResult",
    "ReferencePlace",
    "ReferenceProvider",
    "ReferenceValidation",
    "RegistryCategory",
    "ReviewStatus",
    "RooftopRecord",
    "RoutingTier",
    "SQLiteCache",
    "SpatialEngine",
    "SpatialResolutionResult",
    "StandardizedAddress",
    "StewardshipAuditLedger",
    "StewardshipAuditRecord",
    "USZip5Provider",
    "VerificationCascade",
    "__version__",
    "_split_international_secondary_unit",
    "autocomplete_address",
    "batch_standardize",
    "buffered_chunk_generator",
    "can_safely_merge_corporate_entities",
    "chunk_generator",
    "clean_rooftop_address",
    "clear_cache",
    "compute_confidence_score",
    "compute_soundex",
    "configure_cache",
    "damerau_levenshtein_distance",
    "evaluate_corporate_risk",
    "evaluate_delivery_intelligence",
    "extract_postal_code",
    "format_upu_address",
    "generate_building_key",
    "generate_normalized_address_key",
    "generate_phonetic_address_key",
    "get_audit_ledger",
    "get_cache_stats",
    "get_default_cache",
    "get_default_offline_index",
    "get_default_spatial_engine",
    "get_default_us_zip5_provider",
    "get_engine_info",
    "get_fallback_centroid",
    "get_state_from_zip3",
    "heal_city_token",
    "heal_postal_code_transposition",
    "heal_street_name",
    "heal_street_number_transposition",
    "heal_street_suffix",
    "is_native_available",
    "is_registered_agent_hub_address",
    "is_using_native",
    "lat_lng_to_h3",
    "lookup_corporate_registry",
    "make_cache_key",
    "normalize_country",
    "normalize_country_code",
    "normalize_us_postal_code",
    "normalize_us_state",
    "num_to_ordinal",
    "process_chunk",
    "resolve_offline_coordinates",
    "resolve_spatial_coordinates",
    "resolve_verification_cascade",
    "standardize_address",
    "standardize_batch_dispatch",
    "stream_standardize_csv",
    "stream_standardize_json",
    "stream_standardize_jsonl",
    "validate_address",
    "validate_against_reference",
    "validate_parcel_offline",
    "validate_postal_code",
]

_LAZY_SPATIAL_EXPORTS = {
    "SpatialEngine",
    "get_default_spatial_engine",
    "lat_lng_to_h3",
    "resolve_spatial_coordinates",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_SPATIAL_EXPORTS:
        from entity_standardizer.address import spatial as _spatial

        val = getattr(_spatial, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LAZY_SPATIAL_EXPORTS))
