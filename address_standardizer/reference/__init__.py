"""Pluggable reference-data layer: validate addresses against authoritative data, not just normalise them.

See ``docs/reference_data.md``.
"""

from address_standardizer.reference.base import (
    DPV_MATCH_CODES,
    AuthoritativeDeliveryProvider,
    CompositeProvider,
    DeliveryMatch,
    ReferencePlace,
    ReferenceProvider,
)
from address_standardizer.reference.geonames import (
    ATTRIBUTION,
    GeoNamesPostalProvider,
    build_geonames_index,
    download_geonames,
)
from address_standardizer.reference.us_zip5 import (
    USZip5Provider,
    get_default_us_zip5_provider,
)
from address_standardizer.reference.validation import (
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
