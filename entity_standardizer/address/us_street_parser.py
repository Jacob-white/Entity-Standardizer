"""
US street-line parsing: rule-based parser, usaddress CRF fallback and component extraction
(split out of standardizer.py).
"""

import logging
import re
from typing import Optional, Tuple, List

try:
    import usaddress
except ImportError:
    usaddress = None

from entity_standardizer.address.tables import (
    DIRECTIONALS,
    STREET_SUFFIXES,
    SECONDARY_UNITS,
    US_STATES,
    CANADIAN_PROVINCES,
    WORD_ORDINALS,
    COMPOUND_ORDINALS,
    LANDMARK_CAMPUS_KEYWORDS,
    CATALOGED_COMMERCIAL_HUBS,
)
from entity_standardizer.address._patterns import (
    RE_WHITESPACE,
    RE_NON_ALPHANUMERIC,
    RE_STATE_ZIP,
    RE_PO_BOX,
    RE_SEC_UNIT,
    RE_PMB,
    RE_QUEENS_BOROUGH,
    RE_URBANIZATION,
    RE_NUMBERED_STREET,
    RE_MILITARY_UNIT_BOX,
    RE_RURAL_ROUTE,
    clean_redundant_street_tail,
    is_invalid_thoroughfare,
    RE_HIGHWAY_CONTRACT,
    RE_COMMA_DOT,
    RE_DIGITS,
    RE_PHYSICAL_STREET_INDICATOR,
    RE_OCCUPANCY_VAL_CLEAN,
    RE_IDENTIFIER_TOKEN,
    RE_NUMBER_HYPHEN_NUMBER,
    SPANISH_PREFIX_THOROUGHFARES,
    RE_PR_HIGHWAY,
    FROZEN_DIRECTIONAL_VALUES,
    FROZEN_US_STATE_CODES,
    is_route_number_prefix,
    MULTI_WORD_CITIES,
    STANDALONE_SEC_UNITS,
    get_fuzzy_suffix,
    get_fuzzy_directional,
)

logger = logging.getLogger(__name__)

from entity_standardizer.address.normalization import (  # noqa: E402
    _clean_token,
    get_state_from_zip3,
    num_to_ordinal,
)
from entity_standardizer.address.secondary_units import (  # noqa: E402
    _pre_normalize_address_string,
    _standardize_secondary_unit,
    _words_to_number,
)
from entity_standardizer.address.fuzzy import heal_street_name  # noqa: E402

_RE_TRAILING_PUNCT = re.compile(r"[\s,.\-#;:]+$")


def _rule_based_us_street_parse(address_str: str, enable_fuzzy: bool = True) -> Tuple[str, str, bool]:
    """
    Tier 2 Deterministic Rule Matrix:
    Standardizes US streets according to USPS Pub 28 using positional grammar,
    Rural Route handling, Queens hyphenation, and typo recovery.
    """
    clean_addr = _pre_normalize_address_string(address_str)

    # Check for Rural Route / Highway Contract
    m_rr = RE_RURAL_ROUTE.search(clean_addr)
    if m_rr:
        prefix_before = clean_addr[:m_rr.start()].strip()
        if not any(c.isdigit() for c in prefix_before):
            rr_num = m_rr.group(2)
            box_id = m_rr.group(3)
            st1_rr = f"RR {rr_num} BOX {box_id}".strip() if box_id else f"RR {rr_num}"
            return st1_rr, "", True

    m_hc = RE_HIGHWAY_CONTRACT.search(clean_addr)
    if m_hc:
        prefix_before = clean_addr[:m_hc.start()].strip()
        if not any(c.isdigit() for c in prefix_before):
            hc_num = m_hc.group(2)
            box_id = m_hc.group(3)
            st1_hc = f"HC {hc_num} BOX {box_id}".strip() if box_id else f"HC {hc_num}"
            return st1_hc, "", True

    # Check for Military Unit Box
    m_mil = RE_MILITARY_UNIT_BOX.search(clean_addr)
    if m_mil and not RE_PHYSICAL_STREET_INDICATOR.search(clean_addr):
        # (the pattern is anchored at the start of the string, so nothing can precede the unit/box)
        st1_mil = f"{' '.join(m_mil.group(1).upper().split())} {' '.join(m_mil.group(2).upper().split())}"
        return st1_mil, "", True

    # Check for PO Box
    m_po = RE_PO_BOX.search(clean_addr)
    if m_po:
        pob_num = m_po.group(1).upper()
        rem = clean_addr[:m_po.start()] + clean_addr[m_po.end():]
        rem = rem.strip(" ,.-")
        if rem:
            st1_sub, sec_sub, _ = _rule_based_us_street_parse(rem)
            sec_out = f"{sec_sub} PO BOX {pob_num}".strip() if sec_sub else f"PO BOX {pob_num}"
            return (st1_sub or f"PO BOX {pob_num}"), (sec_out if st1_sub else sec_sub), True
        return f"PO BOX {pob_num}", "", True

    # PMB / Private Mailbox extraction
    sec_unit = ""
    m_pmb = RE_PMB.search(clean_addr)
    if m_pmb:
        sec_unit = f"PMB {m_pmb.group(1).upper()}"
        clean_addr = clean_addr[:m_pmb.start()] + clean_addr[m_pmb.end():]

    # Secondary unit extraction (multi-tier support)
    sec_parts = []
    matches = list(RE_SEC_UNIT.finditer(clean_addr))
    if matches:
        for m_sec in matches:
            if m_sec.group(1):
                sec_type = SECONDARY_UNITS.get(m_sec.group(1).upper(), m_sec.group(1).upper())
                sec_val = m_sec.group(2).lstrip("#-").upper()
                sec_parts.append(f"{sec_type} {sec_val}")
            elif m_sec.group(3):
                sec_parts.append(f"STE {m_sec.group(3).lstrip('#-').upper()}")
            else:  # alternation 3 (descriptive position word): the only one left once groups 1 and 3 are empty
                sec_type = SECONDARY_UNITS.get(m_sec.group(4).upper(), m_sec.group(4).upper())
                sec_val = m_sec.group(5).lstrip("#-").upper() if m_sec.group(5) else ""
                sec_parts.append(f"{sec_type} {sec_val}".strip())
        clean_addr = RE_SEC_UNIT.sub(" ", clean_addr).strip()
    if sec_parts:
        extracted_sec = " ".join(sec_parts).strip()
        sec_unit = f"{sec_unit} {extracted_sec}".strip() if sec_unit else extracted_sec
    if sec_unit:
        sec_unit = _standardize_secondary_unit(sec_unit)

    clean_addr = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", clean_addr)).strip().upper()
    if not clean_addr:
        return "", sec_unit, bool(sec_unit)

    tokens = clean_addr.split()

    # Determine House Number vs Words
    house_num_tokens = []
    i = 0
    # Check for fractional house number: "100 1/2 Main St"
    if len(tokens) > 1 and tokens[0].isdigit() and tokens[1] in ("1/2", "1/4", "3/4"):
        house_num_tokens = [tokens[0], tokens[1]]
        i = 2
    # Queens hyphenated or address range: "123-45 82nd Ave" or "100-102 Main St"
    elif RE_QUEENS_BOROUGH.match(tokens[0]) or RE_NUMBER_HYPHEN_NUMBER.match(tokens[0]):
        house_num_tokens = [tokens[0]]
        i = 1
    elif any(c.isdigit() for c in tokens[0]):
        house_num_tokens = [tokens[0]]
        i = 1

    rem_tokens = tokens[i:]
    norm_tokens = list(house_num_tokens)

    # Positional Directional Grammar:
    # If remaining tokens (excluding house number) is [DIRECTIONAL, SUFFIX] e.g. ['SOUTH', 'ST']
    # 'SOUTH' is the street name itself, NOT a pre-directional!
    is_named_directional = False
    if len(rem_tokens) == 2:
        tok0 = rem_tokens[0]
        tok1 = rem_tokens[1]
        f_suf = get_fuzzy_suffix(tok1) if enable_fuzzy else None
        if (tok0 in DIRECTIONALS or tok0 in FROZEN_DIRECTIONAL_VALUES) and (tok1 in STREET_SUFFIXES or f_suf):
            is_named_directional = True

    # Compound directional street name e.g. ['NORTH', 'EAST', 'ST']
    is_compound_directional = False
    if len(rem_tokens) == 3:
        comp_dir = f"{rem_tokens[0]} {rem_tokens[1]}"
        tok2 = rem_tokens[2]
        f_suf = get_fuzzy_suffix(tok2) if enable_fuzzy else None
        if comp_dir in ("NORTH EAST", "NORTH WEST", "SOUTH EAST", "SOUTH WEST") and (tok2 in STREET_SUFFIXES or f_suf):
            is_compound_directional = True

    j = 0
    while j < len(rem_tokens):
        t = rem_tokens[j]

        # Named directional bypass: preserve full word
        if is_named_directional and j == 0:
            norm_tokens.append(t)
            j += 1
            continue

        if is_compound_directional and j == 0:
            norm_tokens.append(t)
            norm_tokens.append(rem_tokens[1])
            j += 2
            continue

        # Check for 2-token compound ordinals
        if j + 1 < len(rem_tokens):
            compound_candidate = f"{t} {rem_tokens[j+1]}"
            if compound_candidate in COMPOUND_ORDINALS:
                norm_tokens.append(COMPOUND_ORDINALS[compound_candidate])
                j += 2
                continue

        if t in COMPOUND_ORDINALS:
            norm_tokens.append(COMPOUND_ORDINALS[t])
        elif t in WORD_ORDINALS:
            norm_tokens.append(WORD_ORDINALS[t])
        elif t in DIRECTIONALS:
            norm_tokens.append(DIRECTIONALS[t])
        elif t in STREET_SUFFIXES:
            norm_tokens.append(STREET_SUFFIXES[t])
        elif norm_tokens and norm_tokens[-1] in ("&", "AND", "/", "-", "TO"):
            norm_tokens.append(t)
        elif t.isdigit() and 1 <= int(t) <= 999:
            # Check route prefix exclusion
            prev = norm_tokens[-1] if norm_tokens else ""
            prev2 = f"{norm_tokens[-2]} {prev}" if len(norm_tokens) >= 2 else ""
            if not is_route_number_prefix(prev, prev2) and j + 1 < len(rem_tokens) and (rem_tokens[j+1] in STREET_SUFFIXES or (enable_fuzzy and get_fuzzy_suffix(rem_tokens[j+1]))):
                norm_tokens.append(num_to_ordinal(int(t)))
            else:
                norm_tokens.append(t)
        else:
            m_ord = RE_NUMBERED_STREET.match(t)
            is_suffix_pos = (len(rem_tokens) > 1 and j == len(rem_tokens) - 1) or (
                len(rem_tokens) > 2 and j == len(rem_tokens) - 2 and (rem_tokens[-1] in DIRECTIONALS or rem_tokens[-1] in FROZEN_DIRECTIONAL_VALUES)
            )
            is_dir_pos = (j == 0 and len(rem_tokens) > 2) or (j == len(rem_tokens) - 1)

            f_suf = (get_fuzzy_suffix(t) if is_suffix_pos else None) if enable_fuzzy else None
            f_dir = (get_fuzzy_directional(t) if is_dir_pos else None) if enable_fuzzy else None

            if m_ord:
                norm_tokens.append(num_to_ordinal(int(m_ord.group(1))))
            elif f_suf:
                norm_tokens.append(f_suf)
            elif f_dir:
                norm_tokens.append(f_dir)
            elif enable_fuzzy:
                h_name = heal_street_name(t)
                norm_tokens.append(h_name if h_name else t)
            else:
                norm_tokens.append(t)
        j += 1

    st1 = " ".join(norm_tokens).strip()
    st1 = _RE_TRAILING_PUNCT.sub("", st1).strip()
    sec_unit = _standardize_secondary_unit(sec_unit)
    return st1, sec_unit, bool(st1)


class USStreetParseResult(tuple):
    """Subclass of tuple for US street parse results, preserving 6-element unpacking while exposing building_name."""
    def __new__(cls, st1: str, st2: str, ok: bool, p_city: str, p_state: str, p_zip: str, building_name: Optional[str] = None):
        inst = super().__new__(cls, (st1, st2, ok, p_city, p_state, p_zip))
        inst.building_name = building_name
        return inst


_RE_ORDINAL_FLOOR = re.compile(
    r"(?<![A-Za-z0-9])(?P<ord>[A-Za-z]+)\s+(?:FL|FLR|FLOOR)\b\.?(?!\s*[#\d])", re.IGNORECASE
)


def _ordinal_floor_to_unit(match: "re.Match[str]") -> str:
    nxt = match.string[match.end():].split(None, 1)
    if nxt and nxt[0].strip(".,").upper() in STREET_SUFFIXES:
        return match.group(0)  # "100 Fifth Floor Rd": Floor is part of the street name
    word = match.group("ord").upper()  # letters only (the pattern excludes digits), so never "3RD"
    value = _words_to_number([word])
    return f"FL {value}" if value > 0 else match.group(0)


_RE_NUMBERED_STREET = re.compile(r"^\d+[A-Za-z]?\s+[A-Za-z]")
# "..., IL, Chicago 60614": state and city written the wrong way round before the ZIP.
_RE_SWAPPED_STATE_CITY = re.compile(
    r",\s*([A-Za-z][A-Za-z .]*?)\s*,\s*([A-Za-z][A-Za-z .'\-]*?)\s+(\d{5}(?:-\d{4})?)\s*$"
)


def _unswap_state_city(text: str) -> str:
    """Rewrite "..., IL, Chicago 60614" as "..., Chicago, IL 60614"; anything else (a city that already ends in a
    state code, a first part that is not a US state) is returned untouched."""
    m = _RE_SWAPPED_STATE_CITY.search(text)
    if not m or m.group(1).strip(" .").upper() not in US_STATES:
        return text
    city = m.group(2)
    if city.split()[-1].upper() in FROZEN_US_STATE_CODES:
        return text
    return f"{text[:m.start()]}, {city}, {m.group(1).strip(' .')} {m.group(3)}"


def _parse_us_street_tokens(address_str: str, enable_fuzzy: bool = True, city_raw: str = "") -> Tuple[str, str, bool, str, str, str]:
    """Parse address string using usaddress with rule-based fallback and USPS Pub 28 mapping."""
    clean_input = _pre_normalize_address_string(address_str)
    # "Third Fl" / "3rd Floor" is a unit, not a place name + the state FL: rewrite to "FL 3" before the CRF sees it.
    clean_input = _RE_ORDINAL_FLOOR.sub(_ordinal_floor_to_unit, clean_input)
    clean_input = _unswap_state_city(clean_input)

    # Check for Puerto Rico Urbanization prefix
    urb_prefix = ""
    m_urb = RE_URBANIZATION.search(clean_input)
    if m_urb:
        urb_prefix = f"URB {m_urb.group(1).strip().upper()}"
        clean_input = clean_input[:m_urb.start()] + clean_input[m_urb.end():]

    # Check for Rural Route in single string before usaddress
    m_rr = RE_RURAL_ROUTE.search(clean_input)
    if m_rr and not RE_PHYSICAL_STREET_INDICATOR.search(clean_input):
        prefix_before = clean_input[:m_rr.start()].strip()
        if not any(c.isdigit() for c in prefix_before):
            rr_num = m_rr.group(2)
            box_id = m_rr.group(3)
            st1_rr = f"RR {rr_num} BOX {box_id}".strip() if box_id else f"RR {rr_num}"
            # Extract city state zip
            m_sz = RE_STATE_ZIP.search(clean_input.upper())
            p_st = m_sz.group(1) if m_sz else ""
            p_zp = m_sz.group(2) if m_sz else ""
            p_city = ""
            if m_sz:
                before_sz = clean_input[:m_sz.start()].rstrip(" ,")
                after_rr = before_sz[m_rr.end():].strip(" ,")
                p_city = after_rr
            return USStreetParseResult(st1_rr, "", True, p_city, p_st, p_zp)

    m_hc = RE_HIGHWAY_CONTRACT.search(clean_input)
    if m_hc and not RE_PHYSICAL_STREET_INDICATOR.search(clean_input):
        prefix_before = clean_input[:m_hc.start()].strip()
        if not any(c.isdigit() for c in prefix_before):
            hc_num = m_hc.group(2)
            box_id = m_hc.group(3)
            st1_hc = f"HC {hc_num} BOX {box_id}".strip() if box_id else f"HC {hc_num}"
            m_sz = RE_STATE_ZIP.search(clean_input.upper())
            p_st = m_sz.group(1) if m_sz else ""
            p_zp = m_sz.group(2) if m_sz else ""
            p_city = ""
            if m_sz:
                before_sz = clean_input[:m_sz.start()].rstrip(" ,")
                after_hc = before_sz[m_hc.end():].strip(" ,")
                p_city = after_hc
            return USStreetParseResult(st1_hc, "", True, p_city, p_st, p_zp)

    # Check for Military Unit Box
    m_mil = RE_MILITARY_UNIT_BOX.search(clean_input)
    if m_mil and not RE_PHYSICAL_STREET_INDICATOR.search(clean_input):
        # (the pattern is anchored at the start of the string, so nothing can precede the unit/box)
        st1_mil = f"{' '.join(m_mil.group(1).upper().split())} {' '.join(m_mil.group(2).upper().split())}"
        m_sz = RE_STATE_ZIP.search(clean_input.upper())
        p_st = m_sz.group(1) if m_sz else ""
        p_zp = m_sz.group(2) if m_sz else ""
        p_city = ""
        if m_sz:
            before_sz = clean_input[:m_sz.start()].rstrip(" ,")
            after_mil = before_sz[m_mil.end():].strip(" ,")
            p_city = after_mil
        return USStreetParseResult(st1_mil, "", True, p_city, p_st, p_zp)

    p_city = ""
    p_st = ""
    p_zp = ""
    m_sz = RE_STATE_ZIP.search(clean_input.upper())
    if m_sz:
        p_st = m_sz.group(1)
        p_zp = m_sz.group(2)
        before_sz = clean_input[:m_sz.start()].rstrip(" ,")
        DANGLING_PREPOSITIONS = {"DE", "DEL", "OF", "LA", "EL", "DU", "VON", "VAN"}
        if "," in before_sz:
            st_part, city_cand = before_sz.rsplit(",", 1)
            p_city = city_cand.strip()
            st_clean = st_part.strip()
            st_tokens = st_clean.split()
            if st_tokens and st_tokens[-1].upper() in DANGLING_PREPOSITIONS:
                st_clean = " ".join(st_tokens[:-1]).rstrip(" ,.-")
            clean_input = st_clean
        else:
            tokens_raw = before_sz.split()
            tokens_upper = before_sz.upper().split()
            for num_words in (4, 3, 2):
                if len(tokens_upper) > num_words:
                    cand_city = " ".join(tokens_upper[-num_words:])
                    if cand_city in MULTI_WORD_CITIES:
                        cand_street_tokens = tokens_raw[:-num_words]
                        if cand_street_tokens and cand_street_tokens[-1].upper() in DANGLING_PREPOSITIONS:
                            cand_street_tokens = cand_street_tokens[:-1]
                        p_city = " ".join(tokens_raw[-num_words:])
                        clean_input = " ".join(cand_street_tokens)
                        break
    else:
        m_z = re.search(r"(?:^|[,\s])(\d{5}(?:-\d{4})?)\s*$", clean_input)
        if m_z and get_state_from_zip3(m_z.group(1)[:3]):
            cand_zip = m_z.group(1).strip()
            before_z = clean_input[:m_z.start()].rstrip(" ,")
            DANGLING_PREPOSITIONS = {"DE", "DEL", "OF", "LA", "EL", "DU", "VON", "VAN"}
            from entity_standardizer.address.reference._match import name_tokens
            from entity_standardizer.address.reference.us_zip5 import get_default_us_zip5_provider

            place_tokens = {
                name_tokens(p.place_name)
                for p in get_default_us_zip5_provider().lookup_postal("US", cand_zip[:5])
            }
            if "," in before_z:
                st_part, city_cand = before_z.rsplit(",", 1)
                cand_city = city_cand.strip()
                city_toks = {RE_NON_ALPHANUMERIC.sub("", t).upper() for t in cand_city.split()}
                if (
                    st_part.strip()
                    and cand_city
                    and re.fullmatch(r"[A-Za-z][A-Za-z\s.\-]*", cand_city)
                    and not (city_toks & set(SECONDARY_UNITS.keys()))
                    and not (city_toks & set(SECONDARY_UNITS.values()))
                    and "BOX" not in city_toks
                ):
                    p_city = cand_city
                    p_zp = cand_zip
                    st_clean = st_part.strip()
                    st_tokens = st_clean.split()
                    if st_tokens and st_tokens[-1].upper() in DANGLING_PREPOSITIONS:
                        st_clean = " ".join(st_tokens[:-1]).rstrip(" ,.-")
                    clean_input = st_clean
            elif not RE_DIGITS.search(before_z):
                cand_city = before_z.strip()
                city_tok_list = [RE_NON_ALPHANUMERIC.sub("", t).upper() for t in cand_city.split()]
                if (
                    cand_city
                    and re.fullmatch(r"[A-Za-z][A-Za-z\s.\-]*", cand_city)
                    and not (set(city_tok_list) & (set(SECONDARY_UNITS.keys()) | set(SECONDARY_UNITS.values()) | {"BOX"}))
                    and city_tok_list[-1] not in STREET_SUFFIXES
                    and city_tok_list[-1] not in STREET_SUFFIXES.values()
                    and (name_tokens(cand_city) in place_tokens or usaddress is None)
                ):
                    p_city = cand_city
                    p_zp = cand_zip
                    clean_input = ""
            else:
                tokens_raw = before_z.split()
                for num_words in (4, 3, 2, 1):
                    if len(tokens_raw) >= num_words + 2:
                        cand_city = " ".join(tokens_raw[-num_words:])
                        if (
                            re.fullmatch(r"[A-Za-z][A-Za-z\s.\-]*", cand_city)
                            and name_tokens(cand_city) in place_tokens
                        ):
                            cand_street_tokens = tokens_raw[:-num_words]
                            if cand_street_tokens and cand_street_tokens[-1].upper() in DANGLING_PREPOSITIONS:
                                cand_street_tokens = cand_street_tokens[:-1]
                            p_city = cand_city
                            p_zp = cand_zip
                            clean_input = " ".join(cand_street_tokens)
                            break

    # Execute CRF parser
    if usaddress is not None:
        try:
            parsed = usaddress.parse(clean_input)
        except Exception:
            parsed = None
    else:
        parsed = None

    if parsed is None:
        st_input = clean_input
        m_tail = m_sz
        if not m_tail and not p_city and not p_zp:
            m_z_fb = re.search(r"(?:^|[,\s])(\d{5}(?:-\d{4})?)\s*$", clean_input)
            if m_z_fb and get_state_from_zip3(m_z_fb.group(1)[:3]):
                m_tail = m_z_fb
        if not p_city and m_tail:
            before_sz = clean_input[:m_tail.start()].rstrip(" ,")
            if not RE_DIGITS.search(before_sz):
                st_input = ""
                p_city = before_sz.strip()
                if not m_sz:
                    p_zp = m_tail.group(1).strip()
            else:
                # Right-to-Left Reverse Anchor Parsing
                split_found = False
                m_po = RE_PO_BOX.search(before_sz)
                if m_po:
                    end_idx = m_po.end()
                    st_cand = before_sz[:end_idx].strip()
                    rem_cand = before_sz[end_idx:].strip()
                    if rem_cand:
                        st_input = st_cand
                        p_city = rem_cand
                        split_found = True

                if not split_found:
                    tokens = before_sz.split()
                    for k in range(1, len(tokens)):
                        t_clean = RE_NON_ALPHANUMERIC.sub("", tokens[k]).upper()
                        if t_clean in STREET_SUFFIXES:
                            curr = k
                            if curr + 1 < len(tokens):
                                next_clean = RE_NON_ALPHANUMERIC.sub("", tokens[curr + 1]).upper()
                                if next_clean in DIRECTIONALS:
                                    curr += 1
                            if curr + 1 < len(tokens):
                                sec_cand = RE_NON_ALPHANUMERIC.sub("", tokens[curr + 1]).upper()
                                if sec_cand in SECONDARY_UNITS:
                                    curr += 1
                                    if curr + 1 < len(tokens):
                                        val_cand = RE_OCCUPANCY_VAL_CLEAN.sub("", tokens[curr + 1]).upper()
                                        if val_cand:
                                            curr += 1
                            if curr + 1 < len(tokens):
                                st_input = " ".join(tokens[:curr+1])
                                p_city = " ".join(tokens[curr+1:])
                                split_found = True
                            break

                if split_found and not m_sz:
                    p_zp = m_tail.group(1).strip()
                elif not split_found and m_sz:
                    st_input = before_sz.strip()

        rb_st1, rb_st2, ok = _rule_based_us_street_parse(st_input, enable_fuzzy=enable_fuzzy)
        if urb_prefix:
            rb_st1 = f"{urb_prefix} {rb_st1}".strip()
        rb_st1 = re.sub(r"[\s,.\-#;:]+$", "", rb_st1).strip()
        rb_st2 = _standardize_secondary_unit(rb_st2)
        return USStreetParseResult(rb_st1, rb_st2, ok, p_city, p_st, p_zp)

    # Process CRF tags
    street_parts: List[str] = []
    sec_parts: List[str] = []
    building_parts: List[str] = []
    city_parts: List[str] = []
    state_parts: List[str] = []
    zip_parts: List[str] = []
    rr_parts: List[str] = []

    # Check if parsed contains any StreetName tag
    has_street_name = any(lbl == "StreetName" for _, lbl in parsed)

    i = 0
    while i < len(parsed):
        token, label = parsed[i]
        clean = _clean_token(token).upper()
        if not clean:
            i += 1
            continue

        if label in ("AddressNumber", "AddressNumberPrefix", "AddressNumberSuffix"):
            street_parts.append(clean)
        elif label in ("StreetNamePreDirectional", "StreetNamePostDirectional"):
            # Positional grammar: if no StreetName exists, this directional IS the street name!
            if not has_street_name and len(street_parts) >= 1:
                street_parts.append(clean)
            else:
                street_parts.append(DIRECTIONALS.get(clean, clean))
        elif label in ("StreetNamePostType", "StreetNamePreType"):
            if clean == "ROUTE" and street_parts and street_parts[-1] == "STATE":
                norm_suf = "ROUTE"
            else:
                norm_suf = STREET_SUFFIXES.get(clean, (get_fuzzy_suffix(clean) if enable_fuzzy else None) or clean)
            street_parts.append(norm_suf)
        elif label == "StreetName":
            # Compound directional check: NORTH EAST, NORTH WEST, SOUTH EAST, SOUTH WEST
            if clean in ("NORTH", "SOUTH", "EAST", "WEST") and street_parts and street_parts[-1] in ("N", "S", "E", "W"):
                if i + 1 < len(parsed) and parsed[i+1][1] in ("StreetNamePostType", "StreetNamePreType"):
                    dir_unabbrev = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}
                    street_parts[-1] = dir_unabbrev.get(street_parts[-1], street_parts[-1])
                    street_parts.append(clean)
                    i += 1
                    continue

            # Check for 2-token compound ordinal (e.g. Twenty First -> 21ST)
            if i + 1 < len(parsed):
                next_tok, next_lbl = parsed[i + 1]
                next_clean = _clean_token(next_tok).upper()
                if next_lbl == "StreetName" and f"{clean} {next_clean}" in COMPOUND_ORDINALS:
                    street_parts.append(COMPOUND_ORDINALS[f"{clean} {next_clean}"])
                    i += 2
                    continue
            if clean in COMPOUND_ORDINALS:
                street_parts.append(COMPOUND_ORDINALS[clean])
            elif clean in WORD_ORDINALS:
                street_parts.append(WORD_ORDINALS[clean])
            elif street_parts and street_parts[-1] in ("&", "AND", "/", "-", "TO"):
                street_parts.append(clean)
            elif clean.isdigit() and 1 <= int(clean) <= 999:
                prev = street_parts[-1] if street_parts else ""
                prev2 = f"{street_parts[-2]} {prev}" if len(street_parts) >= 2 else ""
                if not is_route_number_prefix(prev, prev2):
                    street_parts.append(num_to_ordinal(int(clean)))
                else:
                    street_parts.append(clean)
            else:
                # Check for typo in directional or suffix
                f_dir = get_fuzzy_directional(clean) if enable_fuzzy else None
                f_suf = get_fuzzy_suffix(clean) if enable_fuzzy else None
                m_ord = RE_NUMBERED_STREET.match(clean)
                if m_ord and 1 <= int(m_ord.group(1)) <= 999:
                    street_parts.append(num_to_ordinal(int(m_ord.group(1))))
                elif m_ord:
                    street_parts.append(clean)
                elif f_dir and len(street_parts) == 1 and i + 1 < len(parsed) and parsed[i+1][1] == "StreetName":
                    street_parts.append(f_dir)
                elif f_suf and len(street_parts) >= 2 and (i == len(parsed) - 1 or (i == len(parsed) - 2 and parsed[i+1][1] in ("StateName", "ZipCode"))):
                    street_parts.append(f_suf)
                elif enable_fuzzy:
                    from entity_standardizer.address.fuzzy import heal_street_name
                    h_name = heal_street_name(clean)
                    street_parts.append(h_name if h_name else clean)
                else:
                    street_parts.append(clean)
        elif label in ("OccupancyType", "SubaddressType"):
            has_existing_suf = any(
                p in STREET_SUFFIXES or p in STREET_SUFFIXES.values()
                for p in street_parts[1:]
            ) if len(street_parts) >= 2 else False

            if clean.upper() in SPANISH_PREFIX_THOROUGHFARES and not street_parts:
                street_parts.append(clean.upper())
            elif clean.upper() == "SLIP" and not has_existing_suf and street_parts:
                street_parts.append("SLIP")
            elif clean.upper() in SECONDARY_UNITS or clean.upper() in SECONDARY_UNITS.values():
                sec_parts.append(SECONDARY_UNITS.get(clean.upper(), clean.upper()))
            elif street_parts and any(p.upper() in SPANISH_PREFIX_THOROUGHFARES for p in street_parts):
                street_parts.append(clean)
            else:
                sec_parts.append(SECONDARY_UNITS.get(clean, clean))
        elif label in ("OccupancyIdentifier", "SubaddressIdentifier"):
            clean_id = clean.lstrip("#-").strip()
            if clean_id:  # pragma: no branch  (clean already has leading "#"/"-" stripped and is non-empty)
                if street_parts and (
                    street_parts[-1].upper() in SPANISH_PREFIX_THOROUGHFARES
                    or (
                        not sec_parts
                        and any(p.upper() in SPANISH_PREFIX_THOROUGHFARES for p in street_parts)
                        and not any(p.isdigit() or re.match(r"^[A-Z]?\d|\d+[A-Z]?$", p) for p in street_parts)
                    )
                ):
                    street_parts.append(clean_id)
                elif clean_id in SECONDARY_UNITS:
                    sec_parts.append(SECONDARY_UNITS[clean_id])
                else:
                    starts_with_unit_prefix = any(
                        clean_id == u or clean_id.startswith(f"{u} ") or clean_id.startswith(f"{u}-")
                        for u in ("FL", "APT", "UNIT", "DEPT", "PH", "SUITE", "STE")
                    )
                    if not sec_parts and not starts_with_unit_prefix:
                        sec_parts.append("STE")
                    sec_parts.append(clean_id)
        elif label == "BuildingName":
            building_parts.append(clean)
        elif label in ("USPSBoxGroupType", "USPSBoxGroupID"):
            rr_parts.append(clean)
        elif label in ("USPSBoxType", "USPSBoxID"):
            if rr_parts:
                rr_parts.append(clean)
            elif (
                clean.upper() in SPANISH_PREFIX_THOROUGHFARES
                or (street_parts and any(p.upper() in SPANISH_PREFIX_THOROUGHFARES for p in street_parts))
            ):
                street_parts.append(clean)
            else:
                sec_parts.append(clean)
        elif label == "PlaceName":
            if clean.upper() in SPANISH_PREFIX_THOROUGHFARES or (
                street_parts
                and any(p.upper() in SPANISH_PREFIX_THOROUGHFARES for p in street_parts)
                and not any(p.isdigit() or re.match(r"^[A-Z]?\d|\d+[A-Z]?$", p) for p in street_parts)
            ):
                street_parts.append(clean)
            elif re.match(r"^PH-[A-Z0-9]+$", clean):
                sec_parts.append(clean)
            elif clean in STANDALONE_SEC_UNITS:
                sec_type = SECONDARY_UNITS.get(clean, clean)
                if i + 1 < len(parsed):
                    next_tok, next_lbl = parsed[i + 1]
                    next_clean = _clean_token(next_tok).upper()
                    if next_lbl in ("OccupancyIdentifier", "SubaddressIdentifier") or RE_IDENTIFIER_TOKEN.match(next_clean):
                        sec_parts.append(f"{sec_type} {next_clean}")
                        i += 2
                        continue
                sec_parts.append(sec_type)
            elif clean in ("ST", "SAINT") and i + 1 < len(parsed):
                next_tok, next_lbl = parsed[i + 1]
                next_clean = _clean_token(next_tok).upper()
                norm_c_raw = RE_NON_ALPHANUMERIC.sub("", city_raw).upper() if city_raw else ""
                if (
                    (city_raw and not norm_c_raw.startswith("ST") and not norm_c_raw.startswith("SAINT"))
                    or (not has_street_name and len(street_parts) <= 2)
                ):
                    street_parts.append(clean)
                    street_parts.append(next_clean)
                    i += 2
                    continue
                else:
                    city_parts.append(clean)
            else:
                city_parts.append(clean)
        elif label == "StateName":
            state_parts.append(clean)
        elif label == "ZipCode":
            zip_parts.append(clean)
        elif label == "Recipient":
            if clean.upper() in SPANISH_PREFIX_THOROUGHFARES or (street_parts and street_parts[-1].upper() in SPANISH_PREFIX_THOROUGHFARES):
                street_parts.append(clean)
                while i + 1 < len(parsed) and parsed[i + 1][1] == "Recipient":
                    i += 1
                    nxt = _clean_token(parsed[i][0]).upper()
                    if nxt:
                        street_parts.append(nxt)
            i += 1
            continue
        elif label in ("CountryName", "NotAddress"):
            i += 1
            continue
        elif label == "LandmarkName":
            # If preceding PlaceName/StateName or no street number present, it is a city prefix like 'LA' in 'LA JOLLA'
            if i + 1 < len(parsed) and parsed[i + 1][1] in ("PlaceName", "StateName", "LandmarkName"):
                city_parts.append(clean)
            elif not any(lbl == "AddressNumber" for _, lbl in parsed):
                city_parts.append(clean)
            else:
                building_parts.append(clean)
        else:
            street_parts.append(clean)
        i += 1

    # Route Rural Routes to street_parts if no other physical street
    if rr_parts and not street_parts:
        street_parts = rr_parts
    elif rr_parts and street_parts:
        sec_parts = rr_parts + sec_parts

    clean_st = " ".join(state_parts)
    if clean_st:
        is_valid_state = (clean_st in US_STATES or clean_st in US_STATES.values() or clean_st in CANADIAN_PROVINCES)
        if not is_valid_state:
            # Invalid state tag from CRF (e.g. "FLOOR", "SUITE", or stray words)
            cand_sec = f"{clean_st} {' '.join(zip_parts)}".strip()
            std_sec = _standardize_secondary_unit(cand_sec)
            if any(std_sec.startswith(u) for u in ("FL ", "STE ", "APT ", "UNIT ", "DEPT ", "RM ", "BLDG ")):
                sec_parts.append(std_sec)
                zip_parts = []
                state_parts = []
            elif len(state_parts) == 1 and state_parts[0] in STREET_SUFFIXES and state_parts[0] not in FROZEN_US_STATE_CODES:
                street_parts.append(STREET_SUFFIXES[state_parts[0]])
                state_parts = []
            elif len(state_parts) > 1 and state_parts[-1] in FROZEN_US_STATE_CODES:
                city_parts = state_parts[:-1] + city_parts
                state_parts = [state_parts[-1]]
            elif clean_st.upper().replace(".", "") in (
                "LP", "LLC", "INC", "CORP", "LTD", "CO", "PLLC", "PC", "SA", "AG",
                "NV", "BV", "GMBH", "SGIIC", "SL", "PLC", "BO", "BARRIO", "SEC", "SECTOR"
            ):
                state_parts = []
            elif all(p in STREET_SUFFIXES or p in STREET_SUFFIXES.values() for p in street_parts) and not any(p.isdigit() or re.match(r"^\d+", p) for p in street_parts):
                street_parts = city_parts + state_parts + street_parts
                city_parts = []
                state_parts = []
            elif city_parts and all(c in DIRECTIONALS for c in city_parts) and state_parts and zip_parts:
                for c in city_parts:
                    street_parts.append(DIRECTIONALS[c])
                city_parts = list(state_parts)
                state_parts = []
            elif city_parts and state_parts and zip_parts:
                city_parts.extend(state_parts)
                state_parts = []
            else:
                street_parts.extend(state_parts)
                state_parts = []

    # Rescue non-numeric street suffixes from zip_parts when no leading house number exists
    has_leading_house_num = bool(
        street_parts and (street_parts[0].isdigit() or re.match(r"^\d+", street_parts[0]))
    )
    if not has_leading_house_num and zip_parts:
        rescued_suffixes = [z for z in zip_parts if not z.isdigit() and z.upper() in STREET_SUFFIXES]
        if rescued_suffixes:
            for z in rescued_suffixes:
                zip_parts.remove(z)
                norm_suf = STREET_SUFFIXES.get(z.upper(), z.upper())
                if city_parts:
                    street_parts = city_parts + street_parts + [norm_suf]
                    city_parts = []
                else:
                    street_parts.append(norm_suf)
        elif any(p.upper() in SPANISH_PREFIX_THOROUGHFARES for p in street_parts):
            # Rescue numeric or alphanumeric street number mistakenly tagged as ZipCode
            rescued_nums = [z for z in zip_parts if (len(z) < 5 or not p_zp)]
            if rescued_nums and not any(p.isdigit() or re.match(r"^[A-Z]?\d|\d+[A-Z]?$", p) for p in street_parts):
                for z in rescued_nums:
                    zip_parts.remove(z)
                    street_parts.append(z)

    # If city_raw was explicitly provided, and street_parts has no thoroughfare/street name
    # (e.g. empty or only Roman numerals / bare single identifiers like "LIGHTON PLAZA II" where
    # "LIGHTON PLAZA" was tagged as PlaceName and "II" as street/state), reassociate city_parts
    if city_raw and city_parts:
        city_raw_clean = re.sub(r"[^\w]", "", city_raw.upper())
        cand_city = re.sub(r"[^\w]", "", " ".join(city_parts).upper())
        if city_raw_clean and cand_city and cand_city != city_raw_clean:
            has_addr_num = any(p.isdigit() or re.match(r"^\d+", p) for p in street_parts)
            has_thoroughfare = any(p in STREET_SUFFIXES or p in STREET_SUFFIXES.values() for p in street_parts)
            if has_addr_num and has_thoroughfare:
                is_continuation_only = False
            else:
                is_continuation_only = (not street_parts) or all(
                    p in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
                    or p in STREET_SUFFIXES
                    or p in STREET_SUFFIXES.values()
                    or p.isdigit()
                    or len(p) == 1
                    for p in street_parts
                )
            has_premise_indicator = any(
                p.upper() in LANDMARK_CAMPUS_KEYWORDS
                or p.upper() in STREET_SUFFIXES
                or p.upper() in ("CITY", "PARK", "PLACE", "TERRACE", "ROW", "MEWS", "SQUARE",
                                 "CALLE", "AVENIDA", "AVE", "CAMINO", "PASEO", "CARRETERA", "CARR", "RUTA")
                for p in city_parts
            )
            if is_continuation_only and has_premise_indicator:
                street_parts = city_parts + street_parts
                city_parts = []

    st1 = " ".join(street_parts).strip()
    st1 = _RE_TRAILING_PUNCT.sub("", st1).strip()
    if is_invalid_thoroughfare(st1):
        if st1:
            sec_parts.append(st1)
            st1 = ""
    st2 = _standardize_secondary_unit(" ".join(sec_parts).strip())
    if not p_city or not p_city.strip():
        p_city = " ".join(city_parts).strip()
    if not p_st or not p_st.strip():
        p_state = " ".join(state_parts).strip()
    else:
        p_state = p_st
    if not p_zp or not p_zp.strip():
        p_zip = " ".join(zip_parts).strip()
    else:
        p_zip = p_zp

    # Prepend Puerto Rico urbanization if present
    if urb_prefix:
        st1 = f"{urb_prefix} {st1}".strip() if st1 else urb_prefix

    # If street_parts was empty but building_parts exists (e.g. "One Financial Plaza")
    bldg_name = None
    if not st1 and building_parts:
        st1 = " ".join(building_parts).strip()
    elif st1 and building_parts:
        bldg_name = " ".join(building_parts).strip()
        st2 = f"{bldg_name} {st2}".strip() if st2 else bldg_name

    # Bare commercial premise followed by secondary units or cataloged commercial hubs
    if not st1 and st2 and city_parts:
        st1 = " ".join(city_parts).strip()
        city_parts = []
        if not city_raw and not (p_st or p_zp):
            p_city = ""
    elif not st1 and city_parts and " ".join(city_parts).upper() in CATALOGED_COMMERCIAL_HUBS:
        st1 = " ".join(city_parts).strip()
        city_parts = []
        if not city_raw and not (p_st or p_zp):
            p_city = ""
    elif city_parts:
        cand_city = re.sub(r"[^\w]", "", " ".join(city_parts).upper())
        prov_city = re.sub(r"[^\w]", "", (city_raw or p_city or "").upper())
        SPANISH_THOROUGHFARES = {"CALLE", "AVENIDA", "CARR", "PASEO", "CAMINO", "CALZADA", "CARRETERA", "RUTA", "AVE"}
        st1_words = [
            w for w in st1.split()
            if w.upper() not in STREET_SUFFIXES
            and w.upper() not in STREET_SUFFIXES.values()
            and w.upper() not in SPANISH_THOROUGHFARES
            and not w.isdigit()
        ]
        if (not st1 or not st1_words) and (not prov_city or (cand_city and cand_city != prov_city)):
            if st1:
                st1 = f"{st1} {' '.join(city_parts)}".strip()
            else:
                st1 = " ".join(city_parts).strip()
            city_parts = []
            # (no p_city reset needed: an input-derived p_city only exists together with a state and ZIP)

    st1 = _RE_TRAILING_PUNCT.sub("", st1).strip()
    st2 = _standardize_secondary_unit(st2)

    # Fallback to rule-based parser if st1 is empty
    # Handles commercial campuses, business parks, landmark premises, or Recipient-tagged tokens
    # e.g., "Blue Bell Executive Campus, Suite 200", "Devonshire, Floor 10", "Two Lincoln Centre"
    if not st1:
        if not (p_city or p_state or p_zip):
            # No municipality/state/zip in address_str; address_str is purely a street/premise candidate
            rb_st1, rb_st2, ok = _rule_based_us_street_parse(clean_input, enable_fuzzy=enable_fuzzy)
            if rb_st1:
                st1 = rb_st1
                if not st2 and rb_st2:
                    st2 = rb_st2
        elif clean_input:
            # address_str contained city/state/zip, but clean_input remains
            # Check if clean_input contains landmark campus keywords or commercial hubs and is not just the city name
            clean_words = set(re.findall(r"\b[A-Z0-9]+\b", clean_input.upper()))
            norm_pc = re.sub(r"[^A-Z0-9]", "", p_city.upper()) if p_city else ""
            norm_ci = re.sub(r"[^A-Z0-9]", "", clean_input.upper())
            is_hub = (
                bool(clean_words & LANDMARK_CAMPUS_KEYWORDS)
                or clean_input.upper().strip() in CATALOGED_COMMERCIAL_HUBS
                or any(hub in clean_input.upper() for hub in CATALOGED_COMMERCIAL_HUBS)
            )
            if is_hub and norm_ci != norm_pc:
                rb_st1, rb_st2, ok = _rule_based_us_street_parse(clean_input, enable_fuzzy=enable_fuzzy)
                if rb_st1:
                    st1 = rb_st1
                    if not st2 and rb_st2:
                        st2 = rb_st2

    if st1 and st2 and re.sub(r"[^\w]", "", st1.upper()) == re.sub(r"[^\w]", "", st2.upper()):
        st2 = ""
    if st1 and st2 and st2.upper().startswith(st1.upper() + " "):
        # The premise name ended up in both lines ("ACME" / "ACME STE 500"): the unit is what follows it.
        st2 = _standardize_secondary_unit(st2[len(st1):].strip())

    # Ultimate fallback to rule-based parser if empty
    if not st1 and not st2 and not (p_city or p_state or p_zip):
        rb_st1, rb_st2, ok = _rule_based_us_street_parse(address_str, enable_fuzzy=enable_fuzzy)
        return USStreetParseResult(rb_st1, rb_st2, ok, p_city, p_state, p_zip)

    return USStreetParseResult(st1, st2, True, p_city, p_state, p_zip, building_name=bldg_name)


# Words that make a trailing number part of the road's NAME ("County Road 12", "State Route 9", "Forest Road 5",
# "Farm to Market Road 1960"), not a house number written after the street.
_ROUTE_NAME_WORDS = frozenset({
    "COUNTY", "CO", "STATE", "ST", "ROUTE", "RTE", "RT", "HIGHWAY", "HWY", "INTERSTATE", "US", "FM", "RM", "CR", "SR",
    "FARM", "MARKET", "RANCH", "FOREST", "FOREST SERVICE", "FS", "NATIONAL", "TOWNSHIP", "TWP", "BYPASS",
})
_RE_FARM_TO_MARKET = re.compile(r"\bFARM[\s-]+TO[\s-]+MARKET\s+(?:(?:ROAD|RD)\s+)?(\d+)\b", re.IGNORECASE)
_RE_TRAILING_HOUSE_NUMBER = re.compile(r"^(?P<street>[A-Za-z][A-Za-z.'\- ]*?)\s+(?P<num>\d{1,6}[A-Za-z]?)$")
_RE_SPANISH_PREFIX_HOUSE_NUM = re.compile(
    r"^(?P<prefix>CALLE|AVENIDA|AVE\.?|PASEO|CAMINO|CALZADA|BULEVAR)\s+"
    r"(?P<name>[A-Za-z][A-Za-z.'\- ]*?)\s+"
    r"(?:#\s*|NO\.?\s*|NUM\.?\s*)(?P<num>\d{1,6}[A-Za-z]?)"
    r"(?P<rest>(?:\s*[, ]\s*.*)?)$",
    re.IGNORECASE,
)


def _move_trailing_house_number(street: str) -> str:
    """"St. Louis Ave 100" -> "100 St. Louis Ave" (house number written after the street, as in much of Europe).

    Only when the text is letters, then a street-type word, then a bare number, and no route-style word precedes the
    type ("County Road 12", "Highway 66" and "Route 9" are names, not house numbers).
    Also rewrites Spanish/Puerto Rico prefix-thoroughfare addresses with explicit '#' / 'No.' house numbers
    (e.g. "AVENIDA ESMERALDA #5, SECOND FLOOR" -> "5 AVENIDA ESMERALDA, SECOND FLOOR").
    """
    m_sp = _RE_SPANISH_PREFIX_HOUSE_NUM.match(street.strip())
    if m_sp:
        return f"{m_sp.group('num')} {m_sp.group('prefix')} {m_sp.group('name').strip()}{m_sp.group('rest') or ''}"
    m = _RE_TRAILING_HOUSE_NUMBER.match(street.strip())
    if not m:
        return street
    words = m.group("street").replace(".", " ").upper().split()
    if len(words) < 2 or words[-1] not in STREET_SUFFIXES and words[-1] not in STREET_SUFFIXES.values():
        return street
    name_words = words[:-1]
    # "St"/"Saint" at the very start is part of a name (St. Louis); anywhere else ST is a street type.
    check = name_words[1:] if name_words and name_words[0] in ("ST", "SAINT") else name_words
    if not check and name_words and name_words[0] in ("ST", "SAINT"):
        return street
    if any(w in _ROUTE_NAME_WORDS for w in check) or (check and check[0] in DIRECTIONALS and len(check) == 1):
        return street
    return f"{m.group('num')} {m.group('street').strip()}"


def _parse_us_address_components(street1_raw: str, street2_raw: str = "", enable_fuzzy: bool = True, city_raw: str = "") -> Tuple[str, str, bool, str, str, str]:
    """Parses US address lines and returns (st1, st2, ok, p_city, p_state, p_zip)."""
    s1_clean = (street1_raw or "").strip()
    s2_clean = (street2_raw or "").strip()
    s1_clean = _RE_FARM_TO_MARKET.sub(r"FM \1", s1_clean)
    s1_clean = _move_trailing_house_number(s1_clean)
    if city_raw:
        s1_clean = clean_redundant_street_tail(s1_clean, city=city_raw)
        if s2_clean:
            s2_clean = clean_redundant_street_tail(s2_clean, city=city_raw)

    # Check if street1 contains purely an urbanization name and street2 contains a physical thoroughfare
    m_s1_urb = RE_URBANIZATION.search(s1_clean)
    if m_s1_urb:
        rem_s1 = s1_clean[:m_s1_urb.start()] + s1_clean[m_s1_urb.end():]
        if not rem_s1.strip(" ,.-#"):
            s2_words = {w.upper().strip(" ,.-#") for w in s2_clean.split()}
            has_thoroughfare = bool(
                (s2_words & SPANISH_PREFIX_THOROUGHFARES)
                or (s2_words & set(STREET_SUFFIXES.keys()))
                or (s2_words & set(STREET_SUFFIXES.values()))
                or RE_PHYSICAL_STREET_INDICATOR.search(s2_clean)
                or RE_PR_HIGHWAY.match(s2_clean)
                or re.match(r"^\d+[A-Z]?\s+[A-Za-z]", s2_clean)
            )
            if s2_clean and not has_thoroughfare and not RE_PO_BOX.match(s2_clean):
                # "Urb Las Flores" + "Apt 5": the urbanization name is street1 and street2 is just the unit.
                return USStreetParseResult(
                    f"URB {m_s1_urb.group(1).strip().upper()}", _standardize_secondary_unit(s2_clean), True, "", "", ""
                )
            if has_thoroughfare and not RE_PO_BOX.match(s2_clean):
                urb_prefix = f"URB {m_s1_urb.group(1).strip().upper()}"
                parse_res = _parse_us_street_tokens(s2_clean, enable_fuzzy=enable_fuzzy, city_raw=city_raw)
                st1, st2, ok, p_city, p_state, p_zip = parse_res
                st1 = f"{urb_prefix} {st1}".strip() if st1 else urb_prefix
                st1 = _RE_TRAILING_PUNCT.sub("", st1).strip()
                st2 = _standardize_secondary_unit(st2)
                return USStreetParseResult(st1, st2, True, p_city, p_state, p_zip, building_name=getattr(parse_res, "building_name", None))


    # Check if street1 has physical street and street2 has PO Box (Dual-Address line)
    m_s1_po = RE_PO_BOX.search(s1_clean)
    m_s2_po = RE_PO_BOX.search(s2_clean)

    if m_s2_po and not m_s1_po:
        # Street1 has physical street, Street2 has PO Box
        parse_res = _parse_us_street_tokens(s1_clean, enable_fuzzy=enable_fuzzy, city_raw=city_raw)
        st1, st2, ok, p_city, p_state, p_zip = parse_res
        po_box_str = f"PO BOX {m_s2_po.group(1).upper()}"
        combined_st2 = f"{st2} {po_box_str}".strip() if st2 else po_box_str
        combined_st2 = _standardize_secondary_unit(combined_st2)
        st1 = _RE_TRAILING_PUNCT.sub("", st1).strip()
        return USStreetParseResult(st1, combined_st2, True, p_city, p_state, p_zip, building_name=getattr(parse_res, "building_name", None))

    # Two physical street lines ("100 Main St" / "200 Oak Ave"): parse each on its own. Merging them into one string
    # produced garbage such as "100 MAIN ST 200TH OAK AVE". Street1 stays the primary address; the second street
    # address is kept (normalised) in street2 rather than guessed at or dropped.
    if s1_clean and s2_clean and _RE_NUMBERED_STREET.match(s1_clean) and _RE_NUMBERED_STREET.match(s2_clean):
        first_word = s2_clean.split()[1].strip(".,#").upper() if len(s2_clean.split()) > 1 else ""
        if first_word not in SECONDARY_UNITS and first_word not in SECONDARY_UNITS.values():
            p1 = _parse_us_street_tokens(s1_clean, enable_fuzzy=enable_fuzzy, city_raw=city_raw)
            p2 = _parse_us_street_tokens(s2_clean, enable_fuzzy=enable_fuzzy, city_raw=city_raw)
            p2_words = set(p2[0].upper().split()[1:])
            has_suffix = bool(p2_words & set(STREET_SUFFIXES.values()))  # a real street ("OAK AVE"), not "3 FL"/"5 OAK"
            has_suffix = has_suffix or bool(p2[1] and p2_words - set(p2[1].upper().split()))  # "200 Oak Ste 5"
            if p1[0] and p2[0] and has_suffix:
                second = f"{p2[0]} {p2[1]}".strip() if p2[1] else p2[0]
                st2_dual = f"{p1[1]} {second}".strip() if p1[1] else second
                return USStreetParseResult(
                    _RE_TRAILING_PUNCT.sub("", p1[0]).strip(), st2_dual, True, p1[3], p1[4], p1[5],
                    building_name=getattr(p1, "building_name", None),
                )

    # Puerto Rico Highway Mile/Kilometer Markers (e.g. "PR #2 KM 82 HM. 2", "PR-2 KM 82.2", "CARR 167 KM 15")
    m_pr_hwy = RE_PR_HIGHWAY.match(s1_clean)
    if m_pr_hwy:
        hwy = m_pr_hwy.group(1).upper()
        km = m_pr_hwy.group(2).upper()
        hm = m_pr_hwy.group(3) or ""
        rest = (m_pr_hwy.group(4) or "").strip()
        km_str = f"{km}.{hm}" if (hm and "." not in km) else km
        hwy_prefix = "PR" if s1_clean.upper().startswith("PR") else "CARR"
        st1_res = f"{hwy_prefix}-{hwy} KM {km_str}"
        st2_res = _standardize_secondary_unit(rest) if rest else ""
        return USStreetParseResult(st1_res, st2_res, True, "", "", "")

    combined = " ".join(filter(None, [s1_clean, s2_clean]))
    if not combined:
        return USStreetParseResult("", "", False, "", "", "")

    # Check for PO Box in combined string
    po_box_match = RE_PO_BOX.search(combined)
    if po_box_match:
        po_box_num = po_box_match.group(1).upper()
        remaining = combined[:po_box_match.start()] + combined[po_box_match.end():]
        remaining = remaining.strip(" ,.-")
        if remaining:
            parse_res = _parse_us_street_tokens(remaining, enable_fuzzy=enable_fuzzy, city_raw=city_raw)
            st1, st2, _, p_city, p_state, p_zip = parse_res
            if st1:
                combined_st2 = f"{st2} PO BOX {po_box_num}".strip() if st2 else f"PO BOX {po_box_num}"
                combined_st2 = _standardize_secondary_unit(combined_st2)
                st1 = _RE_TRAILING_PUNCT.sub("", st1).strip()
                return USStreetParseResult(st1, combined_st2, True, p_city, p_state, p_zip, building_name=getattr(parse_res, "building_name", None))
            else:
                combined_st2 = _standardize_secondary_unit(st2)
                return USStreetParseResult(f"PO BOX {po_box_num}", combined_st2, True, p_city, p_state, p_zip)
        return USStreetParseResult(f"PO BOX {po_box_num}", "", True, "", "", "")

    parse_res = _parse_us_street_tokens(combined, enable_fuzzy=enable_fuzzy, city_raw=city_raw)
    st1, st2, ok, p_city, p_state, p_zip = parse_res
    if st1 and city_raw and st1.upper() == city_raw.strip().upper():
        st1 = ""
    st1 = _RE_TRAILING_PUNCT.sub("", st1).strip()
    st2 = _standardize_secondary_unit(st2)
    return USStreetParseResult(st1, st2, ok, p_city, p_state, p_zip, building_name=getattr(parse_res, "building_name", None))


def _parse_us_street_lines(street1_raw: str, street2_raw: str = "", enable_fuzzy: bool = True, city_raw: str = "") -> Tuple[str, str, bool]:
    """Parses and standardizes US street1 and street2 into USPS Pub 28 format."""
    st1, st2, ok, _, _, _ = _parse_us_address_components(street1_raw, street2_raw, enable_fuzzy=enable_fuzzy, city_raw=city_raw)
    return st1, st2, ok
