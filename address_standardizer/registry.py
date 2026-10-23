"""
Corporate Transparency (BOI) Registry & Formation Hub Intelligence.
===================================================================
Comprehensive curated registry of commercial registered agents, mail drops,
virtual office providers, and offshore secrecy jurisdictions.

Enforces FinCEN Corporate Transparency Act (CTA), Beneficial Ownership Information (BOI),
and KYC/AML entity co-location isolation invariants.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Dict, List, Optional, Tuple, Any

from address_standardizer.registry_data import (  # noqa: F401
    CURATED_CORPORATE_REGISTRY,
    CorporateRegistryEntry,
    CorporateRiskFlag,
    RegistryCategory,
)
from address_standardizer.tables import US_STATES


@lru_cache(maxsize=8192)
def _fold_ascii(s: str) -> str:
    if not s:
        return ""
    return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8").upper()


COUNTRY_SYNONYMS: Dict[str, List[str]] = {
    "GBR": ["UNITED KINGDOM", "UK", "ENGLAND", "LONDON", "GREAT BRITAIN"],
    "CYM": ["CAYMAN", "CAYMAN ISLANDS", "GEORGE TOWN", "UGLAND"],
    "VGB": ["VIRGIN ISLANDS", "BVI", "BRITISH VIRGIN ISLANDS", "TORTOLA", "ROAD TOWN"],
    "BMU": ["BERMUDA", "HAMILTON", "CLARENDON"],
    "PAN": ["PANAMA", "PANAMA CITY"],
    "NLD": ["NETHERLANDS", "AMSTERDAM", "HOLLAND", "NEDERLAND"],
    "LUX": ["LUXEMBOURG", "LUXEMBURG"],
    "CHE": ["SWITZERLAND", "ZUG", "SCHWEIZ", "SUISSE", "SVIZZERA"],
    "IRL": ["IRELAND", "DUBLIN", "IFSC", "EIRE"],
    "SGP": ["SINGAPORE", "RAFFLES"],
}


@lru_cache(maxsize=2048)
def _token_run_regex(pattern: str) -> "re.Pattern[str]":
    """Compiled, cached matcher for `pattern` delimited by non-alphanumerics."""
    return re.compile(r"(?<![A-Z0-9])" + re.escape(pattern) + r"(?![A-Z0-9])")


def _contains_token_run(pattern: str, text: str) -> bool:
    """True if `pattern` occurs in `text` delimited by non-alphanumerics (so '1209 N ORANGE' never matches '11209 N ORANGE')."""
    if not pattern or pattern not in text:  # plain substring test rejects almost every registry entry cheaply
        return False
    return _token_run_regex(pattern).search(text) is not None


_LOOKUP_MEMO_MAX = 4096
_LOOKUP_MEMO: Dict[Tuple[Any, ...], Optional[CorporateRegistryEntry]] = {}
# (registry list, its length) the memo was filled against; swapping or resizing the registry invalidates it.
_LOOKUP_MEMO_OWNER: List[Any] = [None, -1]


def lookup_corporate_registry(
    street1: str,
    street2: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    country: str = "USA",
    raw_street: str = "",
) -> Optional[CorporateRegistryEntry]:
    """
    Looks up an address against the comprehensive curated corporate registry.
    Returns the matching CorporateRegistryEntry if found, else None.
    Supports US domestic, UK, European, Swiss, and offshore secrecy hubs.

    The lookup is a pure function of its arguments and the registry list, and one standardization asks the same
    question several times (hub flag, risk score, delivery intelligence), so results are memoized in a bounded dict
    that is dropped whenever the registry list object is replaced or changes length.
    """
    registry = CURATED_CORPORATE_REGISTRY
    if _LOOKUP_MEMO_OWNER[0] is not registry or _LOOKUP_MEMO_OWNER[1] != len(registry):
        _LOOKUP_MEMO.clear()
        _LOOKUP_MEMO_OWNER[0] = registry
        _LOOKUP_MEMO_OWNER[1] = len(registry)
    key = (street1, street2, city, state, postal_code, country, raw_street)
    try:
        return _LOOKUP_MEMO[key]
    except KeyError:
        pass
    entry = _lookup_corporate_registry_uncached(street1, street2, city, state, postal_code, country, raw_street)
    if len(_LOOKUP_MEMO) >= _LOOKUP_MEMO_MAX:
        _LOOKUP_MEMO.clear()
    _LOOKUP_MEMO[key] = entry
    return entry


def _lookup_corporate_registry_uncached(
    street1: str,
    street2: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    country: str = "USA",
    raw_street: str = "",
) -> Optional[CorporateRegistryEntry]:
    combined_raw = f"{street1} {street2} {city} {state} {postal_code} {raw_street}"
    combined = _fold_ascii(combined_raw)
    norm_st = _fold_ascii(street1)
    norm_c = _fold_ascii(country)

    st_clean = (state or "").strip().upper()
    st_norm = US_STATES.get(st_clean, st_clean)
    city_clean = _fold_ascii(city)
    post_clean = _fold_ascii(postal_code)
    zip_digits = re.sub(r"[^\d]", "", postal_code)

    # Detect if address exhibits explicit domestic US state indicators
    is_explicit_us_state = bool(st_norm and st_norm in US_STATES)

    for entry in CURATED_CORPORATE_REGISTRY:
        entry_country = entry.country.upper()

        # 1. Jurisdiction compatibility filter
        if entry_country == "USA":
            # If user explicitly supplied a non-US country code, skip US entries
            if norm_c and norm_c not in ("USA", "US", "UNITED STATES") and not is_explicit_us_state:
                continue
            # If state was explicitly provided and differs from entry state, skip
            if st_norm and entry.state and st_norm != entry.state:
                continue
        else:
            # International entry: Skip if address has an explicit domestic US state
            # unless address combined text explicitly mentions entry's country or provider name
            if is_explicit_us_state:
                country_in_text = (
                    entry_country in combined
                    or _fold_ascii(entry.provider_name) in combined
                )
                if not country_in_text:
                    continue

        # 2. Street pattern match
        matched_street = any(
            _contains_token_run(_fold_ascii(pat), combined) or _contains_token_run(_fold_ascii(pat), norm_st)
            for pat in entry.street_patterns
        )
        if not matched_street:
            continue

        # 3. Secondary unit match (if required by tower hub)
        if entry.requires_secondary_match:
            sec_candidates = f" {street2} {street1} {raw_street} ".upper()
            sec_candidates_clean = re.sub(r"[,\.#;:]+", " ", sec_candidates)
            matched_sec = False
            for pat in entry.mandatory_unit_patterns:
                pat_upper = pat.upper()
                esc_pat = re.escape(pat_upper)
                pattern_re = (
                    r"(?:\b|#)" + esc_pat.lstrip("#") + r"\b"
                    if pat_upper.startswith("#")
                    else r"\b" + esc_pat + r"\b"
                )
                if re.search(pattern_re, sec_candidates) or re.search(pattern_re, sec_candidates_clean):
                    matched_sec = True
                    break
            if not matched_sec:
                continue

        # 4. Jurisdiction confirmation
        if entry_country == "USA":
            # An explicit city or ZIP that contradicts the hub rules the entry out; a matching state alone
            # (e.g. any Delaware address) must not be enough to label a different building as the hub.
            if entry.city and city_clean:
                entry_city_fold = _fold_ascii(entry.city)
                if entry_city_fold not in city_clean and city_clean not in entry_city_fold:
                    continue
            if entry.postal_code and zip_digits and not zip_digits.startswith(entry.postal_code[:3]):
                continue

            state_match = False
            if entry.state:
                if st_norm == entry.state:
                    state_match = True
                else:  # a differing explicit state was already ruled out above, so none was supplied
                    state_match = bool(re.search(r"\b" + re.escape(entry.state) + r"\b", combined))

            city_match = False
            if entry.city:
                entry_city_norm = _fold_ascii(entry.city)
                if city_clean and city_clean == entry_city_norm:
                    city_match = True
                elif not city_clean:
                    city_match = bool(re.search(r"\b" + re.escape(entry_city_norm) + r"\b", combined))

            zip_match = False
            if entry.postal_code:
                if zip_digits and zip_digits.startswith(entry.postal_code[:3]):
                    zip_match = True
                else:  # a non-matching ZIP was already ruled out above, so none was supplied
                    zip_match = entry.postal_code in combined

            if state_match or city_match or zip_match:
                return entry

        else:
            # An explicit country that is a different country vetoes the entry (Hamilton, Ontario is not Bermuda).
            if norm_c and norm_c not in ("USA", "US", "UNITED STATES"):
                from address_standardizer.normalization import normalize_country_code

                supplied_iso = normalize_country_code(country, state, postal_code, raw_street=raw_street, city_raw=city)
                if supplied_iso and supplied_iso != entry_country:
                    continue
            # International Jurisdiction Confirmation
            # A. Country matching
            country_matched = False
            if norm_c and norm_c in (entry_country, _fold_ascii(entry.country)):
                country_matched = True
            elif re.search(r"\b" + re.escape(entry_country) + r"\b", combined):
                country_matched = True
            elif any(k in combined for k in COUNTRY_SYNONYMS.get(entry_country, [])):
                country_matched = True

            # B. City matching
            city_matched = False
            if entry.city:
                entry_city_norm = _fold_ascii(entry.city)
                if city_clean and city_clean == entry_city_norm:
                    city_matched = True
                elif re.search(r"\b" + re.escape(entry_city_norm) + r"\b", combined):
                    city_matched = True

            # C. Postal code matching
            postal_matched = False
            if entry.postal_code:
                entry_post_norm = _fold_ascii(entry.postal_code)
                entry_post_clean = re.sub(r"[\s\-]", "", entry_post_norm)
                post_input_clean = re.sub(r"[\s\-]", "", post_clean)
                if post_input_clean and (
                    post_input_clean == entry_post_clean
                    or post_input_clean.startswith(entry_post_clean[:3])
                    or (len(post_input_clean) >= 3 and entry_post_clean.startswith(post_input_clean[:3]))
                ):
                    postal_matched = True
                elif entry_post_norm in combined or entry_post_clean in combined.replace(" ", "").replace("-", ""):
                    postal_matched = True

            # D. Landmark / single-island premise matching
            is_distinct_premise_hub = any(
                p in norm_st or p in combined
                for p in ["UGLAND HOUSE", "CLIFTON HOUSE", "CRAIGMUIR CHAMBERS", "WICKHAMS CAY", "CLARENDON HOUSE"]
            )

            if country_matched or city_matched or postal_matched or is_distinct_premise_hub:
                return entry

    return None


_HUB_CATEGORIES = (
    RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
    RegistryCategory.FORMATION_AGENT,
    RegistryCategory.OFFSHORE_SECRECY,
    RegistryCategory.TRUST_FIDUCIARY_COMPANY,
)


def is_registered_agent_hub_address(
    street1: str,
    street2: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    country: str = "USA",
    raw_street: str = "",
) -> bool:
    """
    Detects whether an address corresponds to a known corporate service or formation hub.
    Only COMMERCIAL_REGISTERED_AGENT, FORMATION_AGENT, OFFSHORE_SECRECY, and TRUST_FIDUCIARY_COMPANY
    set is_registered_agent_hub=True.
    Virtual offices and CMRA mail drops populate corporate_risk_score and flags, but do not set is_registered_agent_hub=True.
    """
    entry = lookup_corporate_registry(
        street1=street1,
        street2=street2,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        raw_street=raw_street,
    )
    if entry is None:
        return False
    return entry.category in (
        RegistryCategory.COMMERCIAL_REGISTERED_AGENT,
        RegistryCategory.FORMATION_AGENT,
        RegistryCategory.OFFSHORE_SECRECY,
        RegistryCategory.TRUST_FIDUCIARY_COMPANY,
    )


def can_safely_merge_corporate_entities(addr1: Any, addr2: Any) -> Tuple[bool, str]:
    """
    Enforces the critical Enterprise Entity Resolution Invariants:
    1. Multi-Tenant Skyscraper Suite Isolation (Blueprint 5.4.1)
    2. Private Residence Protection & Data Privacy (Blueprint 5.4.2)
    3. Formation Hub Co-Location Isolation (Blueprint 5.4.3)
    """
    def _val(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    # 0. Empty street isolation check
    s1_1 = _val(addr1, "street1", None)
    s1_2 = _val(addr2, "street1", None)
    if not s1_1 or not str(s1_1).strip() or not s1_2 or not str(s1_2).strip():
        return False, "EMPTY_STREET_ISOLATION: Cannot safely merge entities when an address lacks a valid street line."

    # 1. Private residence isolation check (Invariant 2)
    is_priv1 = _val(addr1, "is_private_residence", False)
    is_priv2 = _val(addr2, "is_private_residence", False)
    b1 = (_val(addr1, "building_key", "") or "")
    b2 = (_val(addr2, "building_key", "") or "")
    k1 = (_val(addr1, "normalized_address_key", "") or "")
    k2 = (_val(addr2, "normalized_address_key", "") or "")

    if (
        is_priv1
        or is_priv2
        or b1.startswith("PRIVATE RESIDENCE||")
        or b2.startswith("PRIVATE RESIDENCE||")
        or k1.startswith("PRIVATE RESIDENCE||")
        or k2.startswith("PRIVATE RESIDENCE||")
        or str(s1_1).strip().upper() == "PRIVATE RESIDENCE"
        or str(s1_2).strip().upper() == "PRIVATE RESIDENCE"
    ):
        return (
            False,
            "PRIVATE_RESIDENCE_ISOLATION: Entity resolution prohibited at private residential locations.",
        )

    if not b1 or not b2 or b1 != b2:
        return False, "DISTINCT_BUILDINGS: Addresses do not share an identical building_key."

    # 2. Formation Hub Co-Location Isolation (Invariant 3)
    is_hub1 = _val(addr1, "is_registered_agent_hub", False)
    is_hub2 = _val(addr2, "is_registered_agent_hub", False)
    flags1 = _val(addr1, "corporate_risk_flags", []) or []
    flags2 = _val(addr2, "corporate_risk_flags", []) or []

    if (
        is_hub1
        or is_hub2
        or CorporateRiskFlag.RISK_CRA_CO_LOCATION in flags1
        or CorporateRiskFlag.RISK_CRA_CO_LOCATION in flags2
        or CorporateRiskFlag.RISK_OFFSHORE_SECRECY_HUB in flags1
        or CorporateRiskFlag.RISK_OFFSHORE_SECRECY_HUB in flags2
        or CorporateRiskFlag.RISK_TRUST_FIDUCIARY in flags1
        or CorporateRiskFlag.RISK_TRUST_FIDUCIARY in flags2
    ):
        return (
            False,
            "CO_LOCATION_ISOLATION_INVARIANT: Both entities share a registered agent / formation hub "
            "building_key. Corporate profile consolidation is strictly prohibited.",
        )

    # Defense in depth: do not trust caller-populated flags alone. An address that was never run through
    # evaluate_corporate_risk (hand-built or legacy rows) must still be refused at a known hub or mail drop.
    for addr in (addr1, addr2):
        known = lookup_corporate_registry(
            street1=str(_val(addr, "street1", "") or ""),
            street2=str(_val(addr, "street2", "") or ""),
            city=str(_val(addr, "city", "") or ""),
            state=str(_val(addr, "state", "") or ""),
            postal_code=str(_val(addr, "postal_code", "") or ""),
            country=str(_val(addr, "country", "") or "USA"),
        )
        if known is not None:
            if known.category in _HUB_CATEGORIES:
                return (
                    False,
                    "CO_LOCATION_ISOLATION_INVARIANT: Address matches a known registered agent / formation hub "
                    f"({known.provider_name}). Corporate profile consolidation is strictly prohibited.",
                )
            return (
                False,
                "CO_LOCATION_ISOLATION_INVARIANT: Shared virtual office or CMRA mail drop location. "
                "Corporate profile consolidation is prohibited without independent EIN or SOS verification.",
            )

    # Check for Virtual Office / Mail Drop
    is_cmra1 = _val(addr1, "is_cmra", False) or _val(addr1, "cmra", False)
    is_cmra2 = _val(addr2, "is_cmra", False) or _val(addr2, "cmra", False)
    if (
        is_cmra1
        or is_cmra2
        or CorporateRiskFlag.RISK_VIRTUAL_OFFICE in flags1
        or CorporateRiskFlag.RISK_VIRTUAL_OFFICE in flags2
        or CorporateRiskFlag.RISK_CMRA_MAIL_DROP in flags1
        or CorporateRiskFlag.RISK_CMRA_MAIL_DROP in flags2
    ):
        return (
            False,
            "CO_LOCATION_ISOLATION_INVARIANT: Shared virtual office or CMRA mail drop location. "
            "Corporate profile consolidation is prohibited without independent EIN or SOS verification.",
        )

    # 3. Multi-Tenant Skyscraper Suite Isolation (Invariant 1)
    s2_1 = (str(_val(addr1, "street2", "") or "")).strip().upper()
    s2_2 = (str(_val(addr2, "street2", "") or "")).strip().upper()

    if s2_1 and s2_2:
        if s2_1 == s2_2:
            if k1 and k2 and k1 != k2:
                return False, "KEY_MISMATCH: Normalized address keys differ."
            return True, "MATCHING_SECONDARY_UNIT: Co-located entities share building and exact secondary unit."
        return False, "SECONDARY_UNIT_MISMATCH: Distinct suites/units within the same parcel."

    if not s2_1 and not s2_2:
        if k1 and k2 and k1 != k2:
            return False, "KEY_MISMATCH: Normalized address keys differ."
        return True, "SINGLE_TENANT_BUILDING: Both entities occupy the same parcel without secondary units."

    return False, "SECONDARY_UNIT_ASYMMETRY: One entity supplied a suite/unit while the other omitted it."


def evaluate_corporate_risk(
    std_address: Any,
    raw_input: Optional[Dict[str, Any]] = None,
) -> Tuple[float, List[str]]:
    """
    Computes a normalized corporate risk score in [0.0, 1.0] and returns KYC/AML
    corporate transparency risk flags based on FinCEN CTA/BOI criteria.
    Enforces Invariant 2: Private residence protection and data privacy guardrail.
    """
    def _get(field_name: str, default: Any = "") -> Any:
        if isinstance(std_address, dict):
            return std_address.get(field_name, default)
        return getattr(std_address, field_name, default)

    # Invariant 2: Private Residence Protection & Data Privacy Invariant
    # When is_private_residence == True, all formation hub risk scores/flags are suppressed
    if _get("is_private_residence", False):
        if isinstance(std_address, dict):
            std_address["is_registered_agent_hub"] = False
        elif hasattr(std_address, "is_registered_agent_hub"):
            setattr(std_address, "is_registered_agent_hub", False)
        return 0.40, [CorporateRiskFlag.RISK_RESIDENTIAL_COMMERCIAL]

    raw = raw_input or {}
    raw_combined = f"{raw.get('street1', '')} {raw.get('street2', '')} {_get('raw_street_address', '')}".upper()

    flags: List[str] = []

    def _add_flag(flag: str):
        if flag not in flags:
            flags.append(flag)

    base_score = 0.0

    # 1. Lookup in curated registry
    entry = lookup_corporate_registry(
        street1=_get("street1", ""),
        street2=_get("street2", ""),
        city=_get("city", ""),
        state=_get("state", ""),
        postal_code=_get("postal_code", ""),
        country=_get("country", "USA"),
        raw_street=_get("raw_street_address", ""),
    )

    if entry is not None:
        base_score = max(base_score, entry.base_risk_score)
        if entry.category in (RegistryCategory.COMMERCIAL_REGISTERED_AGENT, RegistryCategory.FORMATION_AGENT):
            _add_flag(CorporateRiskFlag.RISK_CRA_CO_LOCATION)
        elif entry.category == RegistryCategory.VIRTUAL_OFFICE:
            _add_flag(CorporateRiskFlag.RISK_VIRTUAL_OFFICE)
        elif entry.category == RegistryCategory.OFFSHORE_SECRECY:
            _add_flag(CorporateRiskFlag.RISK_OFFSHORE_SECRECY_HUB)
        elif entry.category == RegistryCategory.TRUST_FIDUCIARY_COMPANY:
            _add_flag(CorporateRiskFlag.RISK_TRUST_FIDUCIARY)
        elif entry.category == RegistryCategory.MAIL_DROP_CMRA:
            _add_flag(CorporateRiskFlag.RISK_CMRA_MAIL_DROP)
    elif _get("is_registered_agent_hub", False):
        base_score = max(base_score, 0.85)
        _add_flag(CorporateRiskFlag.RISK_CRA_CO_LOCATION)

    # 2. Check for missing secondary unit at commercial hub
    has_sec = bool(str(_get("street2", "") or "").strip())
    if (
        CorporateRiskFlag.RISK_CRA_CO_LOCATION in flags
        or CorporateRiskFlag.RISK_VIRTUAL_OFFICE in flags
        or CorporateRiskFlag.RISK_OFFSHORE_SECRECY_HUB in flags
        or CorporateRiskFlag.RISK_TRUST_FIDUCIARY in flags
    ) and not has_sec:
        _add_flag(CorporateRiskFlag.RISK_MISSING_SECONDARY_AT_HUB)
        base_score = min(1.0, base_score + 0.05)

    # 3. Check for disguised PMB (e.g., 'PMB' in raw, but formatted as 'Suite' in standardized)
    raw_has_pmb = "PMB" in raw_combined or "PRIVATE MAILBOX" in raw_combined
    std_sec = (str(_get("street2", "") or "")).upper()
    std_has_ste = any(t in std_sec for t in ["STE", "SUITE", "APT", "UNIT", "FL"])
    std_has_pmb = "PMB" in std_sec

    if (raw_has_pmb and std_has_ste) or (not raw_has_pmb and std_has_pmb):
        _add_flag(CorporateRiskFlag.RISK_DISGUISED_PMB)
        _add_flag(CorporateRiskFlag.RISK_CMRA_MAIL_DROP)
        base_score = max(base_score, 0.65)
    elif raw_has_pmb or std_has_pmb:
        _add_flag(CorporateRiskFlag.RISK_CMRA_MAIL_DROP)
        base_score = max(base_score, 0.60)

    final_score = round(max(0.0, min(1.0, base_score)), 4)
    return final_score, flags
