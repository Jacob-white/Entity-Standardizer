"""Token-efficient tool implementations for the Model Context Protocol (MCP) server.

Exposes core Address-Standardizer capabilities for AI agents and LLM tool calling:
- standardize_address
- batch_standardize
- validate_postal
- autocomplete_address
- explain_parse
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from address_standardizer.autocomplete import autocomplete_address
from address_standardizer.international.countries import CountryRegistry
from address_standardizer.international.postal import (
    POSTAL_RULES,
    PostalValidationResult,
    validate_postal_code,
)
from address_standardizer.standardizer import standardize_address


def standardize_address_tool(
    address: Optional[str] = None,
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    enable_geocoding: bool = False,
    include_metadata: bool = False,
    explain: bool = False,
    correct_state_from_zip: bool = False,
) -> Dict[str, Any]:
    """Standardize, validate, and optionally geocode a single postal address across 249 ISO countries."""
    primary_street = street1 if street1 is not None else address
    std = standardize_address(
        street1=primary_street,
        street2=street2,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        enable_geocoding=enable_geocoding,
        explain=explain,
        correct_state_from_zip=correct_state_from_zip,
    )

    resp: Dict[str, Any] = {
        "street1": std.street1,
        "street2": std.street2,
        "city": std.city,
        "state": std.state,
        "postal_code": std.postal_code,
        "country": std.country,
        "normalized_address_key": std.normalized_address_key,
        "building_key": std.building_key,
        "address_status": str(std.address_status.value if hasattr(std.address_status, "value") else std.address_status),
        "routing_tier": str(std.routing_tier.value if hasattr(std.routing_tier, "value") else std.routing_tier),
        "confidence_score": round(float(std.confidence_score), 4),
        "deliverability": str(std.deliverability.value if hasattr(std.deliverability, "value") else std.deliverability),
    }

    if enable_geocoding:
        resp["latitude"] = std.latitude
        resp["longitude"] = std.longitude
        resp["precision"] = getattr(std, "precision", None)
        resp["accuracy_radius_m"] = getattr(std, "accuracy_radius_m", None)
        resp["h3_index_res10"] = getattr(std, "h3_index_res10", None)

    if include_metadata:
        resp["dpv_footnotes"] = list(getattr(std, "dpv_footnotes", []) or [])
        resp["delivery_point_type"] = getattr(std, "delivery_point_type", None)
        resp["is_vacant"] = getattr(std, "is_vacant", False)
        resp["is_registered_agent_hub"] = getattr(std, "is_registered_agent_hub", False)
        resp["is_private_residence"] = getattr(std, "is_private_residence", False)
        resp["failure_reason_codes"] = list(getattr(std, "failure_reason_codes", []) or [])
        resp["suggested_secondary_units"] = list(getattr(std, "suggested_secondary_units", []) or [])
        resp["secondary_prompt_required"] = getattr(std, "secondary_prompt_required", False)

    if explain:
        resp["explanation"] = list(getattr(std, "explanation", []) or [])
        resp["alternatives"] = list(getattr(std, "alternatives", []) or [])

    return resp


def batch_standardize_tool(
    addresses: List[Union[str, Dict[str, Any]]],
    enable_geocoding: bool = False,
    correct_state_from_zip: bool = False,
) -> Dict[str, Any]:
    """High-throughput batch standardization of multiple postal addresses (up to 500 records)."""
    if not addresses:
        raise ValueError("'addresses' list must contain at least 1 address.")
    if len(addresses) > 500:
        raise ValueError("'addresses' list exceeds maximum allowed batch size of 500 records.")

    results: List[Dict[str, Any]] = []
    for item in addresses:
        if isinstance(item, str):
            res = standardize_address_tool(
                address=item,
                enable_geocoding=enable_geocoding,
                correct_state_from_zip=correct_state_from_zip,
            )
        elif isinstance(item, dict):
            res = standardize_address_tool(
                street1=item.get("street1") or item.get("address"),
                street2=item.get("street2"),
                city=item.get("city"),
                state=item.get("state"),
                postal_code=item.get("postal_code") or item.get("zip") or item.get("postal"),
                country=item.get("country"),
                enable_geocoding=enable_geocoding,
                correct_state_from_zip=correct_state_from_zip,
            )
        else:
            raise TypeError(f"Invalid address item type: {type(item).__name__}. Expected str or dict.")
        results.append(res)
    return {"results": results, "count": len(results)}


def validate_postal_tool(
    postal_code: str,
    country: str = "US",
) -> Dict[str, Any]:
    """Validate a postal code format against official national standards across 249 ISO countries."""
    c_info = CountryRegistry.get(country)
    res = validate_postal_code(postal_code, country_code=country, return_details=True)
    rule = POSTAL_RULES.get(c_info.alpha3) if c_info else None
    pattern_str = None
    if rule:
        pattern_str = getattr(getattr(rule, "pattern", None), "pattern", getattr(rule, "regex", None))

    is_valid = res.is_valid if isinstance(res, PostalValidationResult) else bool(res)
    raw_pc = res.postal_code if isinstance(res, PostalValidationResult) else str(postal_code)
    diagnostics = res.reason if isinstance(res, PostalValidationResult) else ("Valid" if res else "Invalid format")

    return {
        "is_valid": is_valid,
        "postal_code": raw_pc,
        "country_iso2": c_info.alpha2 if c_info else (country[:2].upper() if country else "US"),
        "country_iso3": c_info.alpha3 if c_info else (country[:3].upper() if country else "USA"),
        "country_name": c_info.name if c_info else (country or "Unknown"),
        "has_postal_system": c_info.has_postal_codes if c_info else True,
        "format_pattern": pattern_str,
        "diagnostics": diagnostics,
    }


def autocomplete_address_tool(
    query: str,
    limit: int = 5,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    country: str = "USA",
) -> List[Dict[str, Any]]:
    """Real-time address autocomplete and typeahead suggestion engine."""
    suggestions = autocomplete_address(
        query=query,
        max_results=limit,
        latitude=latitude,
        longitude=longitude,
    )
    return [s.as_dict() for s in suggestions]


def explain_parse_tool(
    address: str,
    country: Optional[str] = None,
    alternatives: int = 3,
) -> Dict[str, Any]:
    """Detailed explanation and audit trace of how an address was parsed and standardized."""
    std = standardize_address(
        street1=address,
        country=country,
        explain=True,
        alternatives=alternatives,
    )
    return {
        "standardized_address": {
            "street1": std.street1,
            "street2": std.street2,
            "city": std.city,
            "state": std.state,
            "postal_code": std.postal_code,
            "country": std.country,
            "normalized_address_key": std.normalized_address_key,
            "confidence_score": round(float(std.confidence_score), 4),
            "routing_tier": str(std.routing_tier.value if hasattr(std.routing_tier, "value") else std.routing_tier),
        },
        "explanation": list(getattr(std, "explanation", []) or []),
        "alternatives": list(getattr(std, "alternatives", []) or []),
    }
