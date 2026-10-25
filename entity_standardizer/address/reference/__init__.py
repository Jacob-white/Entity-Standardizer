"""Pluggable reference-data layer: validate addresses against authoritative data, not just normalise them.

See ``docs/reference_data.md``.
"""

from entity_standardizer.address.reference.base import (
    DPV_MATCH_CODES,
    AuthoritativeDeliveryProvider,
    CompositeProvider,
    DeliveryMatch,
    ReferencePlace,
    ReferenceProvider,
)
from entity_standardizer.address.reference.geonames import (
    ATTRIBUTION,
    GeoNamesPostalProvider,
    build_geonames_index,
    download_geonames,
)
from entity_standardizer.address.reference.us_zip5 import (
    USZip5Provider,
    get_default_us_zip5_provider,
)
from entity_standardizer.address.reference.validation import (
    ERR_POSTAL_STATE_MISMATCH,
    ERR_POSTAL_UNKNOWN,
    WARN_POSTAL_PLACE_MISMATCH,
    ReferenceValidation,
    validate_against_reference,
)

__all__ = [
    "ATTRIBUTION",
    "DPV_MATCH_CODES",
    "AuthoritativeDeliveryProvider",
    "CompositeProvider",
    "DeliveryMatch",
    "ERR_POSTAL_STATE_MISMATCH",
    "ERR_POSTAL_UNKNOWN",
    "GeoNamesPostalProvider",
    "ReferencePlace",
    "ReferenceProvider",
    "ReferenceValidation",
    "USZip5Provider",
    "WARN_POSTAL_PLACE_MISMATCH",
    "build_geonames_index",
    "download_geonames",
    "get_default_us_zip5_provider",
    "validate_against_reference",
]
