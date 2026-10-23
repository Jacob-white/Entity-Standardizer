"""
Tier 1 Fast-Path Address Matcher.
=================================
Ultra-fast deterministic parser (< 0.015 ms, > 65,000 rec/s) for:
  - Clean structured address fields (street1, city, state, zip)
  - Canonical comma-delimited single-string addresses
Bypasses CRF execution for standard addresses using O(1) table lookups.
"""

import re
from typing import Optional, Tuple
from address_standardizer.models import StandardizedAddress
from address_standardizer.tables import (
    DIRECTIONALS,
    STREET_SUFFIXES,
    SECONDARY_UNITS,
    US_STATES,
    WORD_ORDINALS,
    COMPOUND_ORDINALS,
)
from address_standardizer._patterns import (
    RE_CANONICAL_COMMA,
    RE_SEC_UNIT,
    RE_PO_BOX,
    RE_QUEENS_BOROUGH,
    clean_rooftop_address,
    RE_NUMBER_HYPHEN_NUMBER,
    RE_NUMBERED_STREET,
    RE_ATTACHED_SUFFIX_EXPLICIT_UNIT,
    RE_ATTACHED_SUFFIX_BARE_UNIT,
    RE_SAINT_HYPHEN,
    RE_GLUED_HOUSE_NUM,
    FROZEN_US_STATE_CODES,
    FROZEN_DIRECTIONAL_VALUES,
    ROUTE_PREFIXES,
    is_route_number_prefix,
    get_fuzzy_suffix,
    get_fuzzy_directional,
    RE_NON_ALPHANUMERIC,
    RE_WHITESPACE,
    RE_TERMINAL_COUNTRY,
    clean_redundant_street_tail,
    clean_repetitive_cycles,
)
from address_standardizer.phonetics import generate_phonetic_address_key

def _normalize_city(text: str) -> str:
    """Same city normalization as the full pipeline (strip punctuation, collapse whitespace, upper-case)."""
    return RE_WHITESPACE.sub(" ", RE_NON_ALPHANUMERIC.sub("", text).strip().upper())


PRIVACY_PLACEHOLDERS: frozenset[str] = frozenset({
    "PRIVATE RESIDENCE", "CONFIDENTIAL", "PERSONAL RESIDENCE",
    "HOME OFFICE", "UNDISCLOSED", "RESIDENCE ONLY", "PRIVATE ADDRESS"
})

RE_PRIVACY_COMMA = re.compile(
    r"^(PRIVATE RESIDENCE|CONFIDENTIAL|PERSONAL RESIDENCE|HOME OFFICE|UNDISCLOSED|RESIDENCE ONLY|PRIVATE ADDRESS)"
    r"(?:,\s*(?:STE|SUITE|APT|UNIT|FL|FLOOR|BLDG|DEPT)?\s*[\w\-]+)?"
    r",\s*([A-Za-z\s]+),\s*([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)$",
    re.IGNORECASE,
)


def _fast_num_to_ordinal(n: int) -> str:
    """Fast inline ordinal conversion."""
    if 11 <= (n % 100) <= 13:
        return f"{n}TH"
    mod = n % 10
    if mod == 1:
        return f"{n}ST"
    elif mod == 2:
        return f"{n}ND"
    elif mod == 3:
        return f"{n}RD"
    return f"{n}TH"


def _normalize_fast_sec_unit(sec_raw: str) -> Optional[str]:
    """Normalizes a clean secondary unit string like 'Suite 400' -> 'STE 400' or multi-tier 'Building 4, Floor 3, Suite 200'."""
    sec_clean = sec_raw.strip().upper()
    if not sec_clean:
        return ""
    from address_standardizer.standardizer import _standardize_secondary_unit
    matches = list(RE_SEC_UNIT.finditer(sec_clean))
    if matches:
        # Text before the first unit ("200 OAK AVE APT 3") is not a unit: extracting only the unit would silently drop it.
        if re.search(r"[A-Z]", sec_clean[:matches[0].start()]):
            return None
        sec_parts = []
        for m in matches:
            if m.group(1):
                stype = SECONDARY_UNITS.get(m.group(1).upper(), m.group(1).upper())
                sval = m.group(2).upper()
                sec_parts.append(f"{stype} {sval}")
            elif m.group(3):
                sec_parts.append(f"STE {m.group(3).upper()}")
            else:  # alternation 3 (descriptive position word): the only one left once groups 1 and 3 are empty
                stype = SECONDARY_UNITS.get(m.group(4).upper(), m.group(4).upper())
                sval = m.group(5).upper() if m.group(5) else ""
                sec_parts.append(f"{stype} {sval}".strip())
        res = " ".join(sec_parts).strip()
        return _standardize_secondary_unit(res)
    if re.match(r"^\d+[A-Z]?\s+[A-Z]{2,}", sec_clean) and not re.search(r"\b(?:FL|FLR|FLOOR)\b", sec_clean):
        return None  # "5 OAK": a street fragment, not a unit; the full parser decides
    res = _standardize_secondary_unit(sec_clean)
    if res and res != sec_clean:
        return res
    return None


def _normalize_fast_street_phrase(phrase: str, enable_fuzzy: bool = True) -> Optional[Tuple[str, str]]:
    """
    Parses clean street phrase e.g. '100 Main St' or '200 Park Ave Suite 1200'.
    Returns (normalized_street1, normalized_street2) or None if complex/ambiguous.
    """
    phrase_upper = re.sub(r"[\r\n\t]+", " ", phrase).strip().upper()
    if not phrase_upper:
        return None
    phrase_upper = RE_TERMINAL_COUNTRY.sub("", phrase_upper).rstrip(" ,.-")
    if not phrase_upper:
        return None

    # Split glued house numbers: '3340PEACHTREE ROAD' -> '3340 PEACHTREE ROAD'
    phrase_upper = RE_GLUED_HOUSE_NUM.sub(r"\1 \2", phrase_upper)
    # Normalize Saint hyphenation e.g. 'St-Charles' -> 'St Charles'
    phrase_upper = RE_SAINT_HYPHEN.sub(r"\1 \2", phrase_upper)
    # Suffix-attached unit: 'Main St-Ste 200' -> 'Main St STE 200', 'Main St-4B' -> 'Main St APT 4B'
    phrase_upper = RE_ATTACHED_SUFFIX_EXPLICIT_UNIT.sub(r"\1 \2 \3", phrase_upper)
    phrase_upper = RE_ATTACHED_SUFFIX_BARE_UNIT.sub(r"\1 APT \2", phrase_upper)

    # Edge-case checks: if PO Box or rural route: fallback
    if RE_PO_BOX.search(phrase_upper):
        return None

    # Check for multi-tier secondary unit inside phrase
    sec_unit = ""
    matches = list(RE_SEC_UNIT.finditer(phrase_upper))
    # Descriptive position words without an identifier (FRONT, UPPER, OFFICE, REAR...) are ambiguous with real
    # street-name words ("100 Front Royal Pike"); the full parser decides those.
    # A trailing one ("100 Main St Basement") is a real unit; one in the middle of the phrase is a street word.
    if any(m.group(4) and phrase_upper[m.end():].strip(" ,.-") for m in matches):
        return None
    if matches:
        sec_parts = []
        for m in matches:
            if m.group(1):
                stype = SECONDARY_UNITS.get(m.group(1).upper(), m.group(1).upper())
                sval = m.group(2).lstrip("#-").upper()
                sec_parts.append(f"{stype} {sval}")
            elif m.group(3):
                sec_parts.append(f"STE {m.group(3).lstrip('#-').upper()}")
            else:  # alternation 3 (descriptive position word): the only one left once groups 1 and 3 are empty
                stype = SECONDARY_UNITS.get(m.group(4).upper(), m.group(4).upper())
                sval = m.group(5).lstrip("#-").upper() if m.group(5) else ""
                sec_parts.append(f"{stype} {sval}".strip())
        sec_cand = " ".join(sec_parts).strip()
        from address_standardizer.standardizer import _standardize_secondary_unit
        sec_unit = _standardize_secondary_unit(sec_cand)
        phrase_upper = RE_SEC_UNIT.sub(" ", phrase_upper).strip(" ,.-")

    tokens = [t.strip(" ,.-") for t in phrase_upper.split() if t.strip(" ,.-")]
    if len(tokens) < 2:
        return None

    house_num = tokens[0]
    rem_tokens = tokens[1:]

    # Queens hyphen, hyphenated number, or fractional number -> delegate to Tier 2
    if (
        RE_NUMBER_HYPHEN_NUMBER.match(house_num)
        or RE_QUEENS_BOROUGH.match(phrase_upper)
        or (len(tokens) > 1 and tokens[1] in ("1/2", "1/4", "3/4"))
    ):
        return None

    if not (house_num.isdigit() or (len(house_num) > 1 and house_num[:-1].isdigit() and house_num[-1].isalpha())):
        return None

    # Route prefixes (e.g. County Road, CR, Route) -> delegate to Tier 2
    route_scan = rem_tokens[1:] if (rem_tokens[0] in DIRECTIONALS or rem_tokens[0] in FROZEN_DIRECTIONAL_VALUES) else rem_tokens
    if rem_tokens[0] in ROUTE_PREFIXES or (len(rem_tokens) > 1 and f"{rem_tokens[0]} {rem_tokens[1]}" in ROUTE_PREFIXES):
        return None
    if route_scan and (route_scan[0] in ROUTE_PREFIXES or (len(route_scan) > 1 and f"{route_scan[0]} {route_scan[1]}" in ROUTE_PREFIXES)):
        return None

    # A bare number after a route word anywhere in the name ("N Interstate Highway 35 Service Rd", "Texas 71 Frontage Rd")
    # is a route number, not an ordinal: Tier 2 handles it.
    for r_idx in range(len(rem_tokens) - 1):
        if rem_tokens[r_idx + 1].isdigit() and is_route_number_prefix(
            rem_tokens[r_idx], f"{rem_tokens[r_idx - 1]} {rem_tokens[r_idx]}" if r_idx else ""
        ):
            return None

    # Directional ambiguity check: if remaining tokens are just e.g. ['SOUTH', 'ST']
    # 'SOUTH' is the street name, not a directional! Handled by Tier 2 positional grammar.
    if len(rem_tokens) == 2 and (rem_tokens[0] in DIRECTIONALS or rem_tokens[0] in FROZEN_DIRECTIONAL_VALUES) and (rem_tokens[1] in STREET_SUFFIXES or rem_tokens[1] in STREET_SUFFIXES.values()):
        return None

    # Compound directional street name check: e.g. ['NORTH', 'EAST', 'STREET']
    # 'NORTH EAST' is the street name, not pre-directional + street name. Handled by Tier 2.
    if len(rem_tokens) >= 2 and (rem_tokens[0] in DIRECTIONALS or rem_tokens[0] in FROZEN_DIRECTIONAL_VALUES) and (rem_tokens[1] in DIRECTIONALS or rem_tokens[1] in FROZEN_DIRECTIONAL_VALUES):
        return None

    # Check for pre-directional
    pre_dir = ""
    if len(rem_tokens) >= 3:
        if rem_tokens[0] in DIRECTIONALS:
            pre_dir = DIRECTIONALS[rem_tokens[0]]
            rem_tokens = rem_tokens[1:]
        elif enable_fuzzy:
            f_pre = get_fuzzy_directional(rem_tokens[0])
            if f_pre:
                pre_dir = f_pre
                rem_tokens = rem_tokens[1:]

    # Check for post-directional
    post_dir = ""
    if len(rem_tokens) >= 3:
        if rem_tokens[-1] in DIRECTIONALS:
            post_dir = DIRECTIONALS[rem_tokens[-1]]
            rem_tokens = rem_tokens[:-1]
        elif enable_fuzzy:
            f_post = get_fuzzy_directional(rem_tokens[-1])
            if f_post:
                post_dir = f_post
                rem_tokens = rem_tokens[:-1]

    # Check for street suffix at end
    suffix = ""
    if rem_tokens[-1] in STREET_SUFFIXES:
        suffix = STREET_SUFFIXES[rem_tokens[-1]]
        name_tokens = rem_tokens[:-1]
    elif enable_fuzzy:
        # Check fuzzy suffix
        f_suf = get_fuzzy_suffix(rem_tokens[-1])
        if f_suf:
            suffix = f_suf
            name_tokens = rem_tokens[:-1]
        else:
            return None
    else:
        return None

    if not name_tokens or len(name_tokens) > 5 or any(len(tok) == 5 and tok.isdigit() for tok in name_tokens):
        return None

    # Normalize street name tokens (ordinals, words)
    norm_name_parts = []
    k = 0
    while k < len(name_tokens):
        t = name_tokens[k]
        if k + 1 < len(name_tokens):
            comp = f"{t} {name_tokens[k+1]}"
            if comp in COMPOUND_ORDINALS:
                norm_name_parts.append(COMPOUND_ORDINALS[comp])
                k += 2
                continue
        if t in COMPOUND_ORDINALS:
            norm_name_parts.append(COMPOUND_ORDINALS[t])
        elif t in WORD_ORDINALS:
            norm_name_parts.append(WORD_ORDINALS[t])
        elif norm_name_parts and norm_name_parts[-1] in ("&", "AND", "/", "-", "TO"):
            norm_name_parts.append(t)
        elif t.isdigit() and 1 <= int(t) <= 999:
            norm_name_parts.append(_fast_num_to_ordinal(int(t)))
        elif t.isdigit():
            norm_name_parts.append(t)
        else:
            # Check if ordinal like 42ND, 5TH
            m_num = RE_NUMBERED_STREET.match(t)
            if m_num and 1 <= int(m_num.group(1)) <= 999:
                norm_name_parts.append(_fast_num_to_ordinal(int(m_num.group(1))))
            elif m_num:
                norm_name_parts.append(t)
            elif enable_fuzzy:
                from address_standardizer.fuzzy import heal_street_name
                h_name = heal_street_name(t)
                norm_name_parts.append(h_name if h_name else t)
            else:
                norm_name_parts.append(t)
        k += 1

    st1_parts = [house_num]
    if pre_dir:
        st1_parts.append(pre_dir)
    st1_parts.extend(norm_name_parts)
    st1_parts.append(suffix)  # always set: a missing suffix returned None above
    if post_dir:
        st1_parts.append(post_dir)

    st1_norm = " ".join(st1_parts).strip()
    st1_norm = re.sub(r"[\s,.\-#;:]+$", "", st1_norm).strip()
    return st1_norm, sec_unit


def fast_path_parse(
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    is_hub_func = None,
    enable_fuzzy: bool = True,
) -> Optional[StandardizedAddress]:
    """
    Tier 1 Fast-Path Matcher.
    Attempts sub-0.015ms deterministic parse for structured or canonical comma inputs.
    Returns StandardizedAddress on high-confidence match, or None to cascade to Tier 2.
    """
    # Country check: only US addresses qualify for US fast-path
    c_raw = (country or "USA").strip().upper()
    if c_raw not in ("USA", "US", "UNITED STATES", "UNITED STATES OF AMERICA"):
        return None

    s1_raw = re.sub(r"[\r\n\t]+", " ", (street1 or "")).strip()
    s2_raw = re.sub(r"[\r\n\t]+", " ", (street2 or "")).strip()
    s1_raw = clean_repetitive_cycles(s1_raw)
    if s2_raw:
        s2_raw = clean_repetitive_cycles(s2_raw)
    city_raw = re.sub(r"[\r\n\t]+", " ", (city or "")).strip()
    state_raw = re.sub(r"[\r\n\t]+", " ", (state or "")).strip()
    zip_raw = re.sub(r"[\r\n\t]+", " ", (postal_code or "")).strip()

    # Path A: Structured Inputs (street1, city, state, postal_code provided)
    if s1_raw and city_raw and state_raw and zip_raw:
        s1_raw = RE_TERMINAL_COUNTRY.sub("", s1_raw).rstrip(" ,.-")
        if s2_raw:
            s2_raw = RE_TERMINAL_COUNTRY.sub("", s2_raw).rstrip(" ,.-")
        # Validate state
        st_clean = state_raw.upper().replace(".", "").strip()
        state_code = US_STATES.get(st_clean, st_clean if st_clean in FROZEN_US_STATE_CODES else None)
        if not state_code:
            return None

        # Clean redundant city/state/zip if present at end of s1_raw or s2_raw
        s1_raw = clean_redundant_street_tail(s1_raw, city=city_raw, state=state_code, postal_code=zip_raw)
        if not s1_raw:
            return None
        if s2_raw:
            s2_raw = clean_redundant_street_tail(s2_raw, city=city_raw, state=state_code, postal_code=zip_raw)

        # Validate ZIP5
        zip_clean = re.sub(r"^(\d{5})\s+(\d{4})$", r"\1-\2", zip_raw.strip())  # "02101 1234" -> "02101-1234"
        if len(zip_clean) >= 5 and zip_clean[:5].isdigit():
            zip5 = zip_clean[:5]
            norm_postal = f"{zip5}-{zip_clean[6:10]}" if len(zip_clean) >= 10 and zip_clean[5] == "-" and zip_clean[6:10].isdigit() else (
                f"{zip5}-{zip_clean[5:9]}" if len(zip_clean) >= 9 and zip_clean[5:9].isdigit() else zip5
            )
            if enable_fuzzy:
                from address_standardizer.fuzzy import heal_postal_code_transposition
                h_zip = heal_postal_code_transposition(zip5, state=state_code)
                if h_zip and h_zip != zip5:
                    if len(norm_postal) > 5 and norm_postal[:5] == zip5:
                        norm_postal = f"{h_zip}{norm_postal[5:]}"
                    else:
                        norm_postal = h_zip
                    zip5 = h_zip
        else:
            return None

        # Check compliance privacy placeholder
        s1_upper = s1_raw.upper().replace(".", "").strip()
        is_priv = s1_upper in PRIVACY_PLACEHOLDERS

        if is_priv:
            norm_s1 = "PRIVATE RESIDENCE"
            norm_s2 = ""
        else:
            # Normalize street1 and secondary unit
            parsed_st = _normalize_fast_street_phrase(s1_raw, enable_fuzzy=enable_fuzzy)
            if not parsed_st:
                return None
            norm_s1, embedded_sec = parsed_st

            # If secondary unit was provided in s2_raw or embedded
            if s2_raw:
                norm_s2 = _normalize_fast_sec_unit(s2_raw)
                if norm_s2 is None:
                    return None
                if embedded_sec:
                    norm_s2 = f"{norm_s2} {embedded_sec}".strip()
            else:
                norm_s2 = embedded_sec

            from address_standardizer.standardizer import _standardize_secondary_unit
            norm_s2 = _standardize_secondary_unit(norm_s2)
            norm_s1 = re.sub(r"[\s,.\-#;:]+$", "", norm_s1).strip()

        norm_city = _normalize_city(city_raw)
        if enable_fuzzy:
            from address_standardizer.fuzzy import heal_city_token
            h_city = heal_city_token(norm_city, state=state_code, zip3=zip5[:3])
            if h_city:
                norm_city = h_city
        raw_components = [v for v in [s1_raw, s2_raw, city_raw, state_raw, zip_raw, "USA"] if v]
        raw_street_address = ", ".join(raw_components)

        key = f"{norm_s1}|{norm_s2}|{norm_city}|{state_code}|{zip5}|USA"
        b_key = f"{norm_s1}||{norm_city}|{state_code}|{zip5}|USA"
        p_key = generate_phonetic_address_key(norm_s1, zip5, norm_city)

        is_hub = False if is_priv else (
            is_hub_func(norm_s1, norm_s2, norm_city, state_code, zip5, "USA", raw_street_address) if is_hub_func else False
        )

        rooftop_addr = None if is_priv else clean_rooftop_address(norm_s1)

        return StandardizedAddress(
            street1=norm_s1,
            street2=norm_s2,
            city=norm_city,
            state=state_code,
            postal_code=norm_postal,
            country="USA",
            normalized_address_key=key,
            address_status="standardized",
            raw_street_address=raw_street_address,
            is_us=True,
            is_private_residence=is_priv,
            building_key=b_key,
            phonetic_key=p_key,
            is_registered_agent_hub=is_hub,
            rooftop_address=rooftop_addr,
        )

    # Path B: Single comma-delimited string passed in street1
    if s1_raw and not (city_raw or state_raw or zip_raw):
        m_priv = RE_PRIVACY_COMMA.match(s1_raw)
        if m_priv:
            city_part = m_priv.group(2).strip()
            state_cand = m_priv.group(3).upper()
            zip_cand = m_priv.group(4).strip()
            if state_cand in FROZEN_US_STATE_CODES:
                norm_city = _normalize_city(city_part)
                zip5 = zip_cand[:5]
                norm_postal = zip_cand
                raw_street_address = s1_raw
                key = f"PRIVATE RESIDENCE||{norm_city}|{state_cand}|{zip5}|USA"
                b_key = f"PRIVATE RESIDENCE||{norm_city}|{state_cand}|{zip5}|USA"
                p_key = generate_phonetic_address_key("PRIVATE RESIDENCE", zip5, norm_city)
                return StandardizedAddress(
                    street1="PRIVATE RESIDENCE",
                    street2="",
                    city=norm_city,
                    state=state_cand,
                    postal_code=norm_postal,
                    country="USA",
                    normalized_address_key=key,
                    address_status="standardized",
                    raw_street_address=raw_street_address,
                    is_us=True,
                    is_private_residence=True,
                    building_key=b_key,
                    phonetic_key=p_key,
                    is_registered_agent_hub=False,
                    rooftop_address=None,
                )
        m = RE_CANONICAL_COMMA.match(s1_raw)
        if m:
            house_num = m.group(1).upper()
            street_part = m.group(2).strip()
            sec_part = m.group(3)
            city_part = m.group(4).strip()
            state_cand = m.group(5).upper()
            zip_cand = m.group(6).strip()

            if state_cand not in FROZEN_US_STATE_CODES:
                return None

            # Check street phrase
            full_st_phrase = f"{house_num} {street_part}"
            parsed_st = _normalize_fast_street_phrase(full_st_phrase, enable_fuzzy=enable_fuzzy)
            if not parsed_st:
                return None
            norm_s1, embedded_sec = parsed_st

            norm_s2 = ""
            if sec_part:
                norm_s2_cand = _normalize_fast_sec_unit(sec_part)
                if norm_s2_cand is None:
                    return None
                norm_s2 = norm_s2_cand
            if embedded_sec:
                norm_s2 = f"{norm_s2} {embedded_sec}".strip() if norm_s2 else embedded_sec

            from address_standardizer.standardizer import _standardize_secondary_unit
            norm_s2 = _standardize_secondary_unit(norm_s2)
            norm_s1 = re.sub(r"[\s,.\-#;:]+$", "", norm_s1).strip()

            zip5 = zip_cand[:5]
            norm_postal = zip_cand
            if enable_fuzzy:
                from address_standardizer.fuzzy import heal_city_token, heal_postal_code_transposition
                h_zip = heal_postal_code_transposition(zip5, state=state_cand)
                if h_zip and h_zip != zip5:
                    if len(norm_postal) > 5 and norm_postal[:5] == zip5:
                        norm_postal = f"{h_zip}{norm_postal[5:]}"
                    else:
                        norm_postal = h_zip
                    zip5 = h_zip
            norm_city = _normalize_city(city_part)
            if enable_fuzzy:
                h_city = heal_city_token(norm_city, state=state_cand, zip3=zip5[:3])
                if h_city:
                    norm_city = h_city

            raw_street_address = s1_raw
            key = f"{norm_s1}|{norm_s2}|{norm_city}|{state_cand}|{zip5}|USA"
            b_key = f"{norm_s1}||{norm_city}|{state_cand}|{zip5}|USA"
            p_key = generate_phonetic_address_key(norm_s1, zip5, norm_city)

            is_hub = is_hub_func(norm_s1, norm_s2, norm_city, state_cand, zip5, "USA", raw_street_address) if is_hub_func else False
            rooftop_addr = clean_rooftop_address(norm_s1)

            return StandardizedAddress(
                street1=norm_s1,
                street2=norm_s2,
                city=norm_city,
                state=state_cand,
                postal_code=norm_postal,
                country="USA",
                normalized_address_key=key,
                address_status="standardized",
                raw_street_address=raw_street_address,
                is_us=True,
                is_private_residence=False,
                building_key=b_key,
                phonetic_key=p_key,
                is_registered_agent_hub=is_hub,
                rooftop_address=rooftop_addr,
            )

    return None
