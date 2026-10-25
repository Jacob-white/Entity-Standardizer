"""
Core Address Standardizer & Entity Resolution Engine.
=====================================================
Standardizes US and International addresses to USPS Publication 28 and ISO standards:
  - Tier 1: Sub-0.015ms Fast-path regex and structured trie parser.
  - Tier 2: Deterministic rule matrix with right-to-left reverse anchor scanning,
            positional directional grammar, rural route mapping, Queens hyphenation,
            and Levenshtein <= 1 closed-vocabulary typo recovery.
  - Tier 3: Statistical CRF fallback (usaddress) with tag post-processing.
  - Two-tier matching keys: suite-level (normalized_address_key) and building-level (building_key).
  - Hybrid collision-free phonetic blocking keys.
  - Commercial formation / registered agent hub detection.
"""

import copy
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from entity_standardizer.address.models import StandardizedAddress, LocalityOnlyStatus
from entity_standardizer.address.confidence import (
    RoutingTier,
    compute_confidence_score,
)
from entity_standardizer.address.audit import get_audit_ledger
from entity_standardizer.address.cache import (
    get_default_cache,
    make_cache_key,
)
from entity_standardizer.address._patterns import (
    RE_SEC_UNIT,
    RE_WHITESPACE,
    RE_NON_ALPHANUMERIC,
    RE_GLUED_HOUSE_NUM,
    RE_TERMINAL_COUNTRY,
    RE_LEGACY_CORRUPTIONS,
    clean_redundant_street_tail,
    clean_repetitive_cycles,
    parse_intersection_address,
    is_city_noise_in_street1,
    clean_rooftop_address,
    is_invalid_thoroughfare,
    RE_COMMA_DOT,
    RE_PHYSICAL_STREET_INDICATOR,
    FROZEN_US_STATE_CODES,
)
from entity_standardizer.address.phonetics import (
    generate_phonetic_address_key,
)
from entity_standardizer.address.fast_path import fast_path_parse
from entity_standardizer.address.explain import _RECORDER as _explain_recorder
from entity_standardizer.address.tables import US_DOMESTIC_ISO3
from entity_standardizer.address.international import (
    CountryGrammarRegistry,
    fold_to_ascii_key,
)

logger = logging.getLogger(__name__)

from entity_standardizer.address.us_street_parser import (  # noqa: E402
    _rule_based_us_street_parse,  # noqa: F401
    USStreetParseResult,  # noqa: F401
    _parse_us_street_tokens,  # noqa: F401
    _parse_us_address_components,
    _parse_us_street_lines,  # noqa: F401
)

from entity_standardizer.address.normalization import (  # noqa: E402
    num_to_ordinal,  # noqa: F401
    swap_region_city_state,
    swap_us_city_state,
    get_state_from_zip3,  # noqa: F401
    _clean_token,  # noqa: F401
    normalize_country_code,  # noqa: F401
    normalize_country,  # noqa: F401
    normalize_us_state,  # noqa: F401
    normalize_us_postal_code,  # noqa: F401
    is_registered_agent_hub_address,  # noqa: F401
)
from entity_standardizer.address._inputs import (  # noqa: E402
    MAX_FIELD_LENGTH,
    coerce_text,
    correct_state_from_zip as correct_state_from_zip_helper,
    correct_state_from_zip_enabled,
    is_privacy_placeholder,
    normalize_po_box_spelling,
)
from entity_standardizer.address.care_of import extract_care_of, has_care_of, strip_care_of  # noqa: E402,F401
from entity_standardizer.address.secondary_units import (  # noqa: E402
    _pre_normalize_address_string,  # noqa: F401
    _standardize_secondary_unit,  # noqa: F401
    _split_international_secondary_unit,  # noqa: F401
    _numberize_unit_words,
)


def generate_building_key(
    street1: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    allow_locality: bool = False,
    **kwargs: Any,
) -> Optional[str]:
    """
    Derives deterministic building-level matching key (omits secondary units):
      Format: {STREET1}||{CITY}|{STATE}|{ZIP5_OR_POSTAL}|{COUNTRY_ALPHA3}
    Returns None if address is empty or fails parsing.
    """
    std = standardize_address(
        street1=street1,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        allow_locality=allow_locality,
        **kwargs,
    )
    return std.building_key


def generate_normalized_address_key(
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    allow_locality: bool = False,
    **kwargs: Any,
) -> Optional[str]:
    """
    Derives deterministic matching key:
      Format: {STREET1}|{STREET2}|{CITY}|{STATE}|{ZIP5_OR_POSTAL}|{COUNTRY_ALPHA3}
    Returns None if address is empty or fails parsing.
    """
    std = standardize_address(
        street1=street1,
        street2=street2,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        allow_locality=allow_locality,
        **kwargs,
    )
    return std.normalized_address_key


def _finalize_standardized_address(
    std: StandardizedAddress,
    raw_input: Optional[Dict[str, Any]] = None,
    cache_key: Optional[str] = None,
    enable_geocoding: bool = False,
) -> StandardizedAddress:
    from entity_standardizer.address.delivery import evaluate_delivery_intelligence
    from entity_standardizer.address.registry import evaluate_corporate_risk

    if raw_input and raw_input.get("care_of"):
        std.care_of = raw_input["care_of"]

    # 1. Delivery Intelligence & DPV Footnotes
    vac_override = raw_input.get("is_vacant") if raw_input and raw_input.get("is_vacant") is not None else None
    deliv = evaluate_delivery_intelligence(std, raw_input=raw_input, is_vacant_override=vac_override)
    std.rdi = deliv.rdi
    std.cmra = deliv.cmra
    std.is_cmra = deliv.is_cmra
    std.vacant = deliv.vacant
    std.is_vacant = deliv.is_vacant
    std.dpv_footnotes = deliv.dpv_footnotes
    std.deliverability = deliv.deliverability
    std.secondary_prompt_required = deliv.secondary_prompt_required
    std.prompt_message = deliv.prompt_message
    std.suggested_secondary_units = deliv.suggested_secondary_units

    # 2. Corporate Risk & BOI Transparency Flags
    corp_score, corp_flags = evaluate_corporate_risk(std, raw_input=raw_input)
    std.corporate_risk_score = corp_score
    std.corporate_risk_flags = corp_flags

    # 3. Composite Confidence Scoring
    conf = compute_confidence_score(std, raw_input=raw_input)
    std.confidence_score = conf.composite_score
    std.routing_tier = conf.routing_tier
    std.failure_reason_codes = conf.failure_reason_codes
    if (
        conf.routing_tier == RoutingTier.MANUAL_STEWARDSHIP
        or std.is_registered_agent_hub
        or std.address_status == "parse_failed"
    ):
        import os
        from entity_standardizer.address import audit as _addr_audit

        if (
            _addr_audit._DEFAULT_AUDIT_LEDGER is not None
            or os.environ.get("ENTITY_STANDARDIZER_AUDIT_ENABLED", "").strip().lower()
            in ("1", "true", "yes", "on")
        ):
            audit_rec = get_audit_ledger().record_standardized_address(
                std, conf, raw_input=raw_input
            )
            std.audit_record = audit_rec

    # 4. Pure Offline Spatial & Rooftop Coordinate Resolution (Zero External APIs)
    if enable_geocoding:
        from entity_standardizer.address.spatial import resolve_spatial_coordinates
        sp = resolve_spatial_coordinates(std)
        std.spatial_result = sp
        if sp is not None and sp.precision != "UNRESOLVED":
            std.latitude = sp.latitude
            std.longitude = sp.longitude
            std.precision = sp.precision
            std.accuracy_radius_meters = sp.accuracy_radius_meters
            if hasattr(sp, "metadata") and isinstance(sp.metadata, dict):
                std.census_tract = sp.metadata.get("census_tract")
                std.fips_code = sp.metadata.get("fips_code")

        # Enrich with census tract / FIPS metadata and handle fallback from offline reference index
        from entity_standardizer.address.geocoder import geocode_offline
        geo_dict = geocode_offline(std, fallback_to_centroids=True)
        if geo_dict:
            if not std.census_tract and geo_dict.get("census_tract"):
                std.census_tract = geo_dict["census_tract"]
                if sp is not None and hasattr(sp, "metadata") and isinstance(sp.metadata, dict):
                    sp.metadata["census_tract"] = geo_dict["census_tract"]
            if not std.fips_code and geo_dict.get("fips_code"):
                std.fips_code = geo_dict["fips_code"]
                if sp is not None and hasattr(sp, "metadata") and isinstance(sp.metadata, dict):
                    sp.metadata["fips_code"] = geo_dict["fips_code"]
            if (std.latitude is None or (sp and sp.precision == "UNRESOLVED")) and geo_dict.get("latitude") is not None:
                std.latitude = geo_dict["latitude"]
                std.longitude = geo_dict["longitude"]
                std.precision = geo_dict["precision"]
                std.accuracy_radius_meters = geo_dict["accuracy_radius_meters"]

    if cache_key is not None:
        cache = get_default_cache()
        if cache.is_enabled():
            cache.set(cache_key, copy.deepcopy(std))
    return std


_GARBAGE_TOKENS = frozenset({"N/A", "NONE", "NULL", "UNKNOWN", "-", ".", "NO ADDRESS"})


def _is_unit_phrase(text: str) -> bool:
    """True if `text` is made only of secondary-unit designators and short identifiers (e.g. 'STE 400 A')."""
    if not RE_SEC_UNIT.match(text):
        return False
    rest = RE_SEC_UNIT.sub(" ", text)
    return all(len(tok) <= 2 for tok in re.findall(r"\w+", rest))


_RE_TRAILING_STATE_ZIP = re.compile(r"(?<![A-Za-z])(?P<state>[A-Za-z]{2})[ ,]+(?P<zip>\d{5}(?:-\d{4})?)\s*$")


def standardize_address(
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    is_vacant: Optional[bool] = None,
    enable_fuzzy: bool = True,
    enable_geocoding: bool = False,
    use_cache: bool = True,
    allow_locality: bool = False,
    finalize: bool = True,
    correct_state_from_zip: Optional[bool] = None,
    reference_provider: Optional[Any] = None,
    enable_reference_validation: bool = False,
    explain: bool = False,
    alternatives: int = 0,
    calibrator: Optional[Any] = None,
    **kwargs: Any,
) -> StandardizedAddress:
    """
    Standardize an address to USPS Pub 28 (for US) or International ISO standard.
    Generates deterministic normalized_address_key, building_key, phonetic_key,
    and flags registered agent hubs and private residences.

    With ``finalize=False`` the confidence score, delivery intelligence, corporate risk and spatial
    resolution steps (and the result cache) are skipped, which is the fast batch-normalization mode used by
    ``_pure_python_core``.

    A ZIP that belongs to a different state never changes how the address is standardized: the supplied state is
    kept, ``ERR_ZIP_STATE_MISMATCH`` is reported and deliverability is UNDELIVERABLE (DPV footnote A1). Set
    ``correct_state_from_zip=True`` (or ``ADDRESS_STANDARDIZER_CORRECT_STATE_FROM_ZIP=1``) to replace the state with
    the ZIP's state instead; the change is reported as ``WARN_STATE_CORRECTED_FROM_ZIP``. Off by default.

    ``reference_provider`` (an ``entity_standardizer.address.reference.ReferenceProvider``) additionally validates the result
    against reference data: it is attached as ``std.reference_validation`` and its reason codes are appended to
    ``failure_reason_codes``. The default ``None`` changes nothing and costs nothing.

    ``explain=True`` attaches ``std.explanation`` (ordered change records) and ``std.field_confidence`` (per-field
    confidence, heuristic unless a fitted ``calibrator`` is passed); ``alternatives=N`` (at most 5) attaches
    ``std.alternatives`` (next-best readings of an ambiguous input). Both bypass the result cache and are off by default.
    """
    if reference_provider is None and enable_reference_validation:
        from entity_standardizer.address.reference.us_zip5 import get_default_us_zip5_provider

        reference_provider = get_default_us_zip5_provider()

    if explain or alternatives:
        from entity_standardizer.address.explain import standardize_explained

        return standardize_explained(explain, alternatives, calibrator, dict(
            street1=street1, street2=street2, city=city, state=state, postal_code=postal_code, country=country,
            is_vacant=is_vacant, enable_fuzzy=enable_fuzzy, enable_geocoding=enable_geocoding,
            allow_locality=allow_locality, finalize=finalize, correct_state_from_zip=correct_state_from_zip,
            reference_provider=reference_provider, enable_reference_validation=enable_reference_validation, **kwargs,
        ))
    if reference_provider is not None:
        from entity_standardizer.address.reference.validation import apply_reference_validation

        base = standardize_address(
            street1=street1, street2=street2, city=city, state=state, postal_code=postal_code, country=country,
            is_vacant=is_vacant, enable_fuzzy=enable_fuzzy, enable_geocoding=enable_geocoding, use_cache=use_cache,
            allow_locality=allow_locality, finalize=finalize, correct_state_from_zip=correct_state_from_zip, **kwargs,
        )
        return apply_reference_validation(base, reference_provider)
    import os

    _xr = _explain_recorder.get()  # None on every default call; set only inside an explain=True call

    # Callers (pandas, CSV readers) pass NaN, floats and bytes; normalize to text once, up front.
    street1 = coerce_text(street1) if street1 is not None else None
    street2 = coerce_text(street2) if street2 is not None else None
    city = coerce_text(city) if city is not None else None
    state = coerce_text(state) if state is not None else None
    postal_code = coerce_text(postal_code) if postal_code is not None else None
    country = coerce_text(country) if country is not None else None
    original_state_arg = state
    state_corrected_from: Optional[str] = None
    if correct_state_from_zip_enabled(correct_state_from_zip):
        state, state_corrected_from = correct_state_from_zip_helper(state, postal_code, country)
        if state_corrected_from is None and street1 and not (state or "").strip() and not (postal_code or "").strip():
            # Single-line input ("100 Main St, Los Angeles, NY 90012"): the state/ZIP live inside the street text.
            tail = _RE_TRAILING_STATE_ZIP.search(street1)
            if tail:
                new_state, was = correct_state_from_zip_helper(tail.group("state"), tail.group("zip"), country)
                if was is not None and new_state:
                    street1 = street1[: tail.start("state")] + new_state + street1[tail.end("state"):]
                    state_corrected_from = was
    if _xr is not None and state_corrected_from is not None:
        _xr.add("state", state or "", "state_corrected_from_zip", {"from": state_corrected_from, "postal_code": postal_code})
    allow_locality = allow_locality or bool(
        kwargs.get("allow_locality_only")
        or kwargs.get("allow_city_level")
        or kwargs.get("allow_locality")
        or os.environ.get("ENTITY_STANDARDIZER_ALLOW_LOCALITY") == "1"
        or os.environ.get("ADDRESS_STANDARDIZER_ALLOW_LOCALITY") == "1"
    )
    raw_dict = {
        "street1": str(street1) if street1 is not None else "",
        "street2": str(street2) if street2 is not None else "",
        "city": str(city) if city is not None else "",
        "state": str(state) if state is not None else "",
        "postal_code": str(postal_code) if postal_code is not None else "",
        "country": str(country) if country is not None else "",
        "is_vacant": is_vacant if is_vacant is not None else kwargs.get("vacant"),
        "enable_fuzzy": enable_fuzzy,
        "enable_geocoding": enable_geocoding,
        "allow_locality": allow_locality,
        "state_corrected_from": state_corrected_from,
    }

    cache = get_default_cache()
    cache_key = None
    if finalize and use_cache and cache.is_enabled():
        cache_key = make_cache_key(
            street1 if street1 is not None else kwargs.get("street"),
            street2,
            city,
            original_state_arg,
            postal_code,
            country,
            enable_fuzzy=enable_fuzzy,
            enable_geocoding=enable_geocoding,
            allow_locality=allow_locality,
            is_vacant=is_vacant if is_vacant is not None else kwargs.get("vacant"),
            correct_state_from_zip=state_corrected_from is not None or correct_state_from_zip_enabled(correct_state_from_zip),
        )
        cached = cache.get(cache_key)
        if cached is not None:
            hit = copy.deepcopy(cached)
            if hit.audit_record is not None:
                get_audit_ledger().ensure_recorded(hit.audit_record)
            return hit

    def _finish(std: StandardizedAddress) -> StandardizedAddress:
        if not finalize:
            return std
        return _finalize_standardized_address(std, raw_dict, cache_key, enable_geocoding=enable_geocoding)

    _street_alias = kwargs.get("street")
    if any(
        len(v) > MAX_FIELD_LENGTH
        for v in (
            street1 or (_street_alias if isinstance(_street_alias, str) else ""),
            street2 or "", city or "", state or "", postal_code or "", country or "",
        )
    ):
        # Keep the caller's country (cheap to resolve, and the field itself is short) so downstream grouping works.
        too_long_iso = "USA"
        if country and len(country) <= MAX_FIELD_LENGTH:
            too_long_iso = normalize_country_code(country, "", "", raw_street="", city_raw="") or "USA"
        too_long = StandardizedAddress(
            street1="", street2="", city="", state="", postal_code="", country=too_long_iso,
            normalized_address_key=None, address_status="parse_failed", raw_street_address="",
            is_us=too_long_iso in US_DOMESTIC_ISO3, building_key=None, phonetic_key=None,
            is_registered_agent_hub=False, rooftop_address=None,
        )
        too_long.country_iso3 = too_long_iso
        return _finish(too_long)

    # Tier 0: Pre-Flight Sanity, Multiline Bleed Recovery, & Unicode NFKC Normalization
    s1_cand = street1 if street1 is not None else kwargs.get("street")
    s1_in = str(s1_cand).strip() if s1_cand is not None else ""
    s2_in = str(street2).strip() if street2 is not None else ""
    if s2_in:
        # "Suite Five Hundred" / "Second Floor": number words next to a unit designator become digits up front.
        _s2_tokens = s2_in.upper().split()
        _s2_numeric = _numberize_unit_words(_s2_tokens)
        if _s2_numeric != _s2_tokens:
            s2_in = " ".join(_s2_numeric)
    city_in = str(city).strip() if city is not None else ""
    state_in = str(state).strip() if state is not None else ""
    postal_in = str(postal_code).strip() if postal_code is not None else ""
    country_in = str(country).strip() if country is not None else ""

    # Embedded Newline / Multiline Field Bleed Cleaner
    s1_lines_u = [line.strip().upper() for line in re.split(r"[\r\n]+", s1_in) if line.strip()]
    if "\n" in city_in or "\r" in city_in:
        c_lines = [line.strip() for line in re.split(r"[\r\n]+", city_in) if line.strip()]
        if len(c_lines) > 1:  # pragma: no branch  (city_in is stripped, so an embedded newline always separates 2+ lines)
            cleaned_city_parts = []
            for cline in c_lines:
                cline_u = cline.upper()
                if (
                    re.match(r"^(?:(?:TH|ST|ND|RD|\d+(?:TH|ST|ND|RD)?)\s+(?:FLOOR|FL)|SUITE|STE|APT|UNIT|ROOM|RM|BLDG|BUILDING)\b", cline_u)
                    or cline_u.endswith((" FLOOR", " FL", " STE", " SUITE"))
                    or re.match(r"^(?:FLOOR|FLR|FL)\s+[A-Z0-9]+$", cline_u)
                ):
                    if not s2_in:
                        s2_in = cline
                    elif cline_u not in s2_in.upper():
                        s2_in = f"{s2_in} {cline}".strip()
                elif cline_u in ("OFFICE", "MAIN OFFICE", "BRANCH OFFICE", "HOME OFFICE"):
                    pass
                elif cline_u in s1_lines_u:
                    pass
                else:
                    cleaned_city_parts.append(cline)
            if cleaned_city_parts:
                city_in = " ".join(cleaned_city_parts)

    _city_words = city_in.split()
    if len(_city_words) > 1:
        _tail = [w.upper() for w in _city_words[-3:]]
        if _tail[-1] == "OFFICE":
            _drop = 2 if len(_tail) >= 2 and _tail[-2] in ("BRANCH", "MAIN") and len(_city_words) > 2 else 1
            city_in = " ".join(_city_words[:-_drop])
    city_in = city_in.strip()

    if "\n" in s1_in or "\r" in s1_in:
        s1_lines = [line.strip() for line in re.split(r"[\r\n]+", s1_in) if line.strip()]
        if len(s1_lines) > 1:  # pragma: no branch  (s1_in is stripped, so an embedded newline always separates 2+ lines)
            cleaned_s1_parts = []
            for sline in s1_lines:
                sline_u = sline.upper()
                if re.match(r"^(?:(?:TH|ST|ND|RD|\d+(?:TH|ST|ND|RD)?)\s+(?:FLOOR|FL)|SUITE|STE|APT|UNIT|ROOM|RM)\b", sline_u):
                    if not s2_in:
                        s2_in = sline
                    elif sline_u not in s2_in.upper():
                        s2_in = f"{s2_in} {sline}".strip()
                elif re.fullmatch(r"(?:(?:MAIN|BRANCH|HOME|HEAD|CORPORATE|REGIONAL)\s+)?OFFICE", sline_u) or (
                    city_in and re.fullmatch(re.escape(city_in.upper()) + r"\s+(?:(?:MAIN|BRANCH)\s+)?OFFICE", sline_u)
                ):
                    pass  # a bare office label line, not a street line that merely contains the word
                else:
                    cleaned_s1_parts.append(sline)
            if cleaned_s1_parts:
                s1_in = " ".join(cleaned_s1_parts)
            else:
                s1_in = ""

    # Municipal Prefix / City Acronym Noise Filter in street1
    if is_city_noise_in_street1(s1_in, city_in, state_in):
        if _xr is not None:
            _xr.add("street1", "", "city_noise_removed", {"city": city_in})
        s1_in = ""

    # Care-Of / Attention Prefix Cleaner: strips "c/o <company>" segments, keeping any physical street
    had_co = has_care_of(s1_in)
    s1_in, care_of_1 = extract_care_of(s1_in)
    care_of_2 = ""
    if s2_in:
        s2_in, care_of_2 = extract_care_of(s2_in)
    raw_dict["care_of"] = "; ".join(dict.fromkeys(c for c in (care_of_1, care_of_2) if c)) or None
    if _xr is not None:
        if care_of_1:
            _xr.add("street1", s1_in, "care_of_removed", {"care_of": care_of_1})
        if care_of_2:
            _xr.add("street2", s2_in, "care_of_removed", {"care_of": care_of_2})
    if had_co and not s1_in and s2_in:
        s1_in = s2_in
        s2_in = ""

    s1_raw = re.sub(r"[\r\n\t]+", " ", unicodedata.normalize('NFKC', s1_in)).strip()
    s2_raw = re.sub(r"[\r\n\t]+", " ", unicodedata.normalize('NFKC', s2_in)).strip()
    s1_raw = normalize_po_box_spelling(s1_raw)
    s2_raw = normalize_po_box_spelling(s2_raw)
    if s2_raw.upper() in _GARBAGE_TOKENS and s1_raw:
        s2_raw = ""  # a placeholder in street2 next to a real street must not leak into the key
    s1_raw = clean_repetitive_cycles(s1_raw)
    s1_raw = RE_GLUED_HOUSE_NUM.sub(r"\1 \2", s1_raw)
    if s2_raw:
        s2_raw = clean_repetitive_cycles(s2_raw)
    city_raw = re.sub(r"[\r\n\t]+", " ", unicodedata.normalize('NFKC', city_in)).strip()
    state_raw = re.sub(r"[\r\n\t]+", " ", unicodedata.normalize('NFKC', state_in)).strip()
    postal_raw = re.sub(r"[\r\n\t]+", " ", unicodedata.normalize('NFKC', postal_in)).strip()
    country_raw = re.sub(r"[\r\n\t]+", " ", unicodedata.normalize('NFKC', country_in)).strip()

    raw_components = [v for v in [s1_raw, s2_raw, city_raw, state_raw, postal_raw, country_raw] if v]
    raw_street_address = ", ".join(raw_components)

    # Empty / garbage check
    if not raw_components:
        empty_std = StandardizedAddress(
            street1="",
            street2="",
            city="",
            state="",
            postal_code="",
            country="USA",
            normalized_address_key=None,
            address_status="parse_failed",
            raw_street_address="",
            is_us=True,
            building_key=None,
            phonetic_key=None,
            is_registered_agent_hub=False,
            rooftop_address=None,
        )
        empty_std.country_iso3 = "USA"
        return _finish(empty_std)

    if len(raw_components) == 1 and s1_raw.upper() in ("N/A", "NONE", "NULL", "UNKNOWN", "-", ".", "NO ADDRESS"):
        garbage_std = StandardizedAddress(
            street1="",
            street2="",
            city="",
            state="",
            postal_code="",
            country="USA",
            normalized_address_key=None,
            address_status="parse_failed",
            raw_street_address=raw_street_address,
            is_us=True,
            building_key=None,
            phonetic_key=None,
            is_registered_agent_hub=False,
            rooftop_address=None,
        )
        garbage_std.country_iso3 = "USA"
        return _finish(garbage_std)

    # Pre-clean legacy baked-in ETL artifacts (e.g. "10005TH UNITED ESTS", "UNITED ESTS")
    s1_raw = RE_LEGACY_CORRUPTIONS.sub("", s1_raw).strip(" ,.-")
    if s2_raw:
        s2_raw = RE_LEGACY_CORRUPTIONS.sub("", s2_raw).strip(" ,.-")

    # Detect country code
    country_iso = normalize_country_code(
        country_raw,
        state_raw,
        postal_raw,
        raw_street=raw_street_address,
        city_raw=city_raw,
    )
    if not country_raw:
        from entity_standardizer.address.international.scripts import (
            country_matches_script,
            detect_script_country,
            split_script_single_line,
        )

        _script_iso = detect_script_country(raw_street_address)
        if _script_iso:
            if not country_matches_script(country_iso, _script_iso):
                country_iso = _script_iso
            if not (city_raw or state_raw or postal_raw):
                _script_split = split_script_single_line(s1_raw, country_iso)
                if _script_split:
                    if _xr is not None:
                        _xr.add("street1", _script_split[0], "script_single_line_split",
                                {"city": _script_split[1], "state": _script_split[2], "postal_code": _script_split[3]})
                    s1_raw, city_raw, state_raw, postal_raw = _script_split
        if _xr is not None:
            _xr.country(country_raw, country_iso, state_raw, postal_raw, _script_iso)
    is_us = country_iso in US_DOMESTIC_ISO3
    if is_us:
        city_raw, state_raw = swap_us_city_state(city_raw, state_raw)
    elif country_iso in ("CAN", "AUS", "BRA", "IND", "MEX"):
        from entity_standardizer.address.international.australia import AU_STATES
        from entity_standardizer.address.international.india import IN_STATES
        from entity_standardizer.address.international.latin_america import BR_STATES, MX_STATES
        from entity_standardizer.address.tables import CANADIAN_PROVINCES

        if country_iso == "CAN":
            regs = CANADIAN_PROVINCES
        elif country_iso == "AUS":
            regs = AU_STATES
        elif country_iso == "BRA":
            regs = BR_STATES
        elif country_iso == "IND":
            regs = IN_STATES
        else:
            regs = MX_STATES

        city_raw, state_raw = swap_region_city_state(city_raw, state_raw, regs)

    # Strip terminal sovereign country before US or international parsing if structured components present
    if city_raw or state_raw or postal_raw:
        s1_raw = RE_TERMINAL_COUNTRY.sub("", s1_raw).rstrip(" ,.-")
        if s2_raw:
            s2_raw = RE_TERMINAL_COUNTRY.sub("", s2_raw).rstrip(" ,.-")

    # Tier 1: Ultra-Fast Deterministic Fast-Path Parser (< 0.015 ms)
    if is_us:
        fast_res = fast_path_parse(
            street1=s1_raw,
            street2=s2_raw,
            city=city_raw,
            state=state_raw,
            postal_code=postal_raw,
            country=country_raw or "USA",
            is_hub_func=is_registered_agent_hub_address,
            enable_fuzzy=enable_fuzzy,
        )
        if fast_res is not None:
            if _xr is not None:
                _xr.parse_path = "fast_path"
            fast_res.country_iso3 = country_iso
            return _finish(fast_res)

    # Tier 2 & Tier 3: Deterministic Rule Matrix and Statistical CRF Fallback
    if is_us:
        # US Pipeline (USPS Pub 28)
        if _xr is not None:
            _xr.parse_path = "us_parser"
        s1_clean = clean_redundant_street_tail(s1_raw, city=city_raw, state=state_raw, postal_code=postal_raw)
        s2_clean = clean_redundant_street_tail(s2_raw, city=city_raw, state=state_raw, postal_code=postal_raw) if s2_raw else s2_raw
        bldg_name = None
        if not s1_clean:
            norm_s1 = ""
            norm_s2 = _standardize_secondary_unit(s2_clean) if s2_clean else ""
            success = True
            p_city = p_state = p_zip = None
        else:
            intersection_line = parse_intersection_address(s1_clean)
            if intersection_line:
                norm_s1 = intersection_line
                norm_s2 = s2_clean or ""
                success = True
                p_city = p_state = p_zip = None
            else:
                parsed_res = _parse_us_address_components(
                    s1_clean, s2_clean, enable_fuzzy=enable_fuzzy, city_raw=city_raw
                )
                norm_s1, norm_s2, success, p_city, p_state, p_zip = parsed_res
                bldg_name = getattr(parsed_res, "building_name", None)
        if is_invalid_thoroughfare(norm_s1):
            if norm_s1:
                norm_s2 = f"{norm_s1} {norm_s2}".strip() if norm_s2 else norm_s1
                norm_s1 = ""
        if not city_raw and p_city:
            city_raw = p_city
        if not state_raw and p_state:
            state_raw = p_state
        if not postal_raw and p_zip:
            postal_raw = p_zip

        norm_city = RE_WHITESPACE.sub(" ", RE_NON_ALPHANUMERIC.sub("", city_raw).strip().upper())
        norm_postal, zip5 = normalize_us_postal_code(postal_raw)
        norm_state = normalize_us_state(state_raw, zip5)

        if enable_fuzzy:
            from entity_standardizer.address.fuzzy import heal_city_token, heal_postal_code_transposition
            if norm_city:
                healed_city = heal_city_token(norm_city, state=norm_state, zip3=zip5[:3] if zip5 else None)
                if healed_city:
                    norm_city = healed_city

            # Guarded postal code healing: only when norm_s1 is valid and non-empty, and city/state are valid
            if norm_s1 and norm_s1 != "PRIVATE RESIDENCE" and norm_city and norm_state in FROZEN_US_STATE_CODES:
                if zip5:
                    healed_zip = heal_postal_code_transposition(zip5, state=norm_state)
                    if healed_zip and healed_zip != zip5:
                        if len(norm_postal) > 5 and norm_postal[:5] == zip5:
                            norm_postal = f"{healed_zip}{norm_postal[5:]}"
                        else:
                            norm_postal = healed_zip
                        zip5 = healed_zip

        # Detect private residence indicators
        is_priv = is_privacy_placeholder(s1_raw, s2_raw)
        if is_priv:
            norm_s1 = "PRIVATE RESIDENCE"
            norm_s2 = ""

        if norm_s1 and norm_city and norm_s1.upper() == norm_city.upper():
            norm_s1 = ""

        # Minimum viable check: requires valid non-empty street line or locality-only record
        has_locality = bool(norm_city or norm_state or zip5)
        if not norm_s1:
            if allow_locality and has_locality:
                status = LocalityOnlyStatus("locality_only")
                k_city = fold_to_ascii_key(norm_city)
                k_state = fold_to_ascii_key(norm_state)
                k_post = fold_to_ascii_key(zip5)
                k_country = fold_to_ascii_key(country_iso) or "USA"
                key = f"||{k_city}|{k_state}|{k_post}|{k_country}"
                b_key = f"||{k_city}|{k_state}|{k_post}|{k_country}"
                p_key = None
            else:
                status = "parse_failed"
                key = None
                b_key = None
                p_key = None
        else:
            status = "standardized"
            k_s1 = fold_to_ascii_key(norm_s1)
            k_s2 = fold_to_ascii_key(norm_s2)
            k_city = fold_to_ascii_key(norm_city)
            k_state = fold_to_ascii_key(norm_state)
            k_post = fold_to_ascii_key(zip5)
            k_country = fold_to_ascii_key(country_iso) or "USA"
            key = f"{k_s1}|{k_s2}|{k_city}|{k_state}|{k_post}|{k_country}"
            b_key = f"{k_s1}||{k_city}|{k_state}|{k_post}|{k_country}"
            p_key = generate_phonetic_address_key(k_s1, k_post, k_city)

        if is_priv:
            is_hub = False
        else:
            is_hub = is_registered_agent_hub_address(
                street1=norm_s1,
                street2=norm_s2,
                city=norm_city,
                state=norm_state,
                postal_code=zip5,
                country=country_iso,
                raw_street=raw_street_address,
            )

        has_po = bool(re.search(r"\b(?:P\.?\s*O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX|APO|FPO|DPO)\b", f"{norm_s1} {norm_s2} {raw_street_address}".upper()))
        is_dual_physical = has_po and bool(norm_s1 and re.match(r"^(?:\d+|PR-|CARR-|KM\b)", norm_s1))
        rooftop_addr = None if (is_priv or (has_po and not is_dual_physical) or not norm_s1 or status != "standardized") else clean_rooftop_address(norm_s1)

        std_us = StandardizedAddress(
            street1=norm_s1,
            street2=norm_s2,
            city=norm_city,
            state=norm_state,
            postal_code=norm_postal,
            country=country_iso,
            normalized_address_key=key,
            address_status=status,
            raw_street_address=raw_street_address,
            is_us=True,
            is_private_residence=is_priv,
            building_key=b_key,
            phonetic_key=p_key,
            is_registered_agent_hub=is_hub,
            rooftop_address=rooftop_addr,
            building_name=bldg_name,
        )
        std_us.country_iso3 = country_iso
        return _finish(std_us)
    else:
        # International Pipeline
        if state_raw in ("US", "USA"):
            state_raw = ""
        if postal_raw == "00000":
            postal_raw = ""
        norm_s1 = ""
        norm_s2 = ""
        dep_loc = None
        bldg_name = None
        is_priv = is_privacy_placeholder(s1_raw, s2_raw)
        if is_priv:
            norm_s1 = "PRIVATE RESIDENCE"
            norm_s2 = ""
            norm_city = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
            norm_state = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", state_raw).strip().upper())
            norm_postal = RE_WHITESPACE.sub(" ", postal_raw.strip().upper())
        else:
            grammar = CountryGrammarRegistry.get(country_iso)
            if _xr is not None:
                _xr.parse_path = (
                    "universal_grammar" if type(grammar).__name__ == "UniversalInternationalGrammar" else "country_grammar"
                )
            parsed = grammar.standardize(
                street1=s1_raw,
                street2=s2_raw,
                city=city_raw,
                state=state_raw,
                postal_code=postal_raw,
                country=country_iso,
                raw_street_address=raw_street_address,
            )
            # "Street, City, Postal, Country" written on one line: when the grammar did not isolate a valid postal
            # code, split the locality off generically and parse the street and locality separately.
            if not city_raw and not postal_raw and not state_raw and "," in s1_raw:
                from entity_standardizer.address.international.base import split_single_line_locality
                from entity_standardizer.address.international.postal import validate_postal_code

                has_valid_postal = bool(parsed.postal_code) and bool(validate_postal_code(parsed.postal_code, country_iso))
                split = None if has_valid_postal else split_single_line_locality(s1_raw, country_iso)
                if split is not None:
                    reparsed = grammar.standardize(
                        street1=split[0],
                        street2=s2_raw,
                        city=split[1],
                        state="",
                        postal_code=split[2],
                        country=country_iso,
                        raw_street_address=raw_street_address,
                    )
                    # Adopt the locality split when it yields a postal code, unless it pushed a unit into street1
                    # that the original parse had kept apart.
                    unit_leaked = bool(RE_SEC_UNIT.search(reparsed.format_street1())) and not RE_SEC_UNIT.search(
                        parsed.format_street1()
                    )
                    if reparsed.postal_code and not unit_leaked:
                        parsed = reparsed
            norm_s1 = parsed.format_street1()
            norm_s2 = parsed.format_street2()
            norm_city = parsed.city or ""
            norm_state = parsed.state or ""
            norm_postal = parsed.postal_code or ""
            dep_loc = parsed.dependent_locality
            bldg_name = parsed.building_name

        if norm_s1 and norm_city and norm_s1.upper() == norm_city.upper():
            norm_s1 = ""

        if norm_s1 and norm_s2.startswith("PO BOX ") and _is_unit_phrase(norm_s1):
            # A unit phrase plus a PO box ("PO Box 450, Suite 400"): the box is the delivery line and the
            # unit stays secondary, matching the US pipeline.
            norm_s1, norm_s2 = norm_s2, _standardize_secondary_unit(norm_s1)
        elif is_invalid_thoroughfare(norm_s1):
            # Lone numbers/letters and other non-street street1 values are merged into the secondary line.
            if norm_s1:
                norm_s2 = f"{norm_s1} {norm_s2}".strip() if norm_s2 else norm_s1
                norm_s1 = ""

        # If thoroughfare (street1) is empty but secondary delivery line / PO Box exists, promote it
        if not norm_s1 and norm_s2:
            if norm_s2.startswith("PO BOX ") or (RE_PHYSICAL_STREET_INDICATOR.search(norm_s2) and not is_invalid_thoroughfare(norm_s2)):
                norm_s1 = norm_s2
                norm_s2 = ""

        # Minimum viable check: requires valid non-empty street line or locality-only record
        if (
            not norm_s1
            and allow_locality
            and not (norm_city or norm_state or norm_postal)
            and norm_s2
            and not any(c.isdigit() for c in norm_s2)
            and len(norm_s2) >= 3
            and not _is_unit_phrase(norm_s2)
        ):
            norm_city = norm_s2
            norm_s2 = ""
        has_locality = bool(norm_city or norm_state or norm_postal)
        if not norm_s1:
            if allow_locality and has_locality:
                status = LocalityOnlyStatus("locality_only")
                k_city = fold_to_ascii_key(norm_city)
                k_state = fold_to_ascii_key(norm_state)
                k_post = fold_to_ascii_key(norm_postal)
                k_country = fold_to_ascii_key(country_iso)
                key = f"||{k_city}|{k_state}|{k_post}|{k_country}"
                b_key = f"||{k_city}|{k_state}|{k_post}|{k_country}"
                p_key = None
            else:
                status = "parse_failed"
                key = None
                b_key = None
                p_key = None
        else:
            status = "standardized"
            k_s1 = fold_to_ascii_key(norm_s1)
            k_s2 = fold_to_ascii_key(norm_s2)
            k_city = fold_to_ascii_key(norm_city)
            k_state = fold_to_ascii_key(norm_state)
            k_post = fold_to_ascii_key(norm_postal)
            k_country = fold_to_ascii_key(country_iso)
            key = f"{k_s1}|{k_s2}|{k_city}|{k_state}|{k_post}|{k_country}"
            b_key = f"{k_s1}||{k_city}|{k_state}|{k_post}|{k_country}"
            p_key = generate_phonetic_address_key(k_s1, k_post, k_city)

        if is_priv:
            is_hub = False
        else:
            is_hub = is_registered_agent_hub_address(
                street1=norm_s1,
                street2=norm_s2,
                city=norm_city,
                state=norm_state,
                postal_code=norm_postal,
                country=country_iso,
                raw_street=raw_street_address,
            )

        has_po = bool(re.search(r"\b(?:P\.?\s*O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX|APO|FPO|DPO)\b", f"{norm_s1} {norm_s2} {raw_street_address}".upper()))
        is_dual_physical = has_po and bool(norm_s1 and re.match(r"^(?:\d+|PR-|CARR-|KM\b)", norm_s1))
        rooftop_addr = None if (is_priv or (has_po and not is_dual_physical) or not norm_s1 or status != "standardized") else clean_rooftop_address(norm_s1)

        std_intl = StandardizedAddress(
            street1=norm_s1,
            street2=norm_s2,
            city=norm_city,
            state=norm_state,
            postal_code=norm_postal,
            country=country_iso,
            normalized_address_key=key,
            address_status=status,
            raw_street_address=raw_street_address,
            is_us=False,
            is_private_residence=is_priv,
            building_key=b_key,
            phonetic_key=p_key,
            is_registered_agent_hub=is_hub,
            dependent_locality=dep_loc,
            building_name=bldg_name,
            rooftop_address=rooftop_addr,
        )
        std_intl.country_iso3 = country_iso
        return _finish(std_intl)


@dataclass
class AddressValidationResult:
    """Outcome of validating an address."""

    is_valid: bool
    deliverability: str
    rejection_reason: Optional[str] = None
    failure_reason_codes: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    routing_tier: str = "MANUAL_STEWARDSHIP"
    standardized_address: Optional[StandardizedAddress] = None

    @property
    def is_deliverable(self) -> bool:
        return self.is_valid and self.deliverability == "DELIVERABLE"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "deliverability": self.deliverability,
            "rejection_reason": self.rejection_reason,
            "failure_reason_codes": list(self.failure_reason_codes),
            "confidence_score": self.confidence_score,
            "routing_tier": self.routing_tier,
            "standardized_address": self.standardized_address.as_dict() if self.standardized_address else None,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the address validation result into a JSON-compatible dictionary."""
        return self.as_dict()


def validate_address(
    address: Union[str, Dict[str, Any], None] = None,
    country: Optional[str] = None,
    strict: bool = False,
    enable_reference_validation: bool = False,
    **kwargs: Any,
) -> AddressValidationResult:
    """Lightweight address validation returning deliverability, validity, and error messages."""
    if isinstance(address, dict):
        addr_dict = dict(address)
        if country and "country" not in addr_dict:
            addr_dict["country"] = country
        std = standardize_address(**addr_dict, enable_reference_validation=enable_reference_validation, **kwargs)
    elif isinstance(address, str):
        std = standardize_address(street1=address, country=country, enable_reference_validation=enable_reference_validation, **kwargs)
    else:
        std = standardize_address(country=country, enable_reference_validation=enable_reference_validation, **kwargs)

    routing_str = str(std.routing_tier.value if hasattr(std.routing_tier, "value") else std.routing_tier)
    deliv_str = str(std.deliverability.value if hasattr(std.deliverability, "value") else std.deliverability)
    reasons = list(getattr(std, "failure_reason_codes", []) or [])

    fatal_errors = [r for r in reasons if r.startswith("ERR_")]

    if strict:
        is_valid = (routing_str == "AUTO_PASS") and (deliv_str != "UNDELIVERABLE") and (len(fatal_errors) == 0)
    else:
        is_valid = (routing_str in ("AUTO_PASS", "FUZZY_REVIEW")) and (deliv_str != "UNDELIVERABLE") and (len(fatal_errors) == 0)

    rejection = None
    if not is_valid:
        if fatal_errors:
            rejection = f"Validation failed: {', '.join(fatal_errors)}"
        elif deliv_str == "UNDELIVERABLE":
            rejection = "Address is undeliverable"
        elif routing_str == "MANUAL_STEWARDSHIP":
            rejection = "Low confidence score requires manual stewardship"
        else:
            rejection = "Address validation failed strict requirements"

    return AddressValidationResult(
        is_valid=is_valid,
        deliverability=deliv_str,
        rejection_reason=rejection,
        failure_reason_codes=reasons,
        confidence_score=round(float(std.confidence_score), 4),
        routing_tier=routing_str,
        standardized_address=std,
    )

