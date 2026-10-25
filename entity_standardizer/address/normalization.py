"""
Country, US state and postal-code normalization helpers (split out of standardizer.py).
"""

import unicodedata
import logging
import re
from typing import Optional, Tuple

from entity_standardizer.address.tables import (
    STREET_SUFFIXES,
    US_DOMESTIC_ISO3,
    US_STATES,
    COUNTRY_MAP,
    COUNTRY_NAME_MAP,
    CANADIAN_PROVINCES,
    CANADIAN_PROVINCE_NAMES_COMPACT,
    ZIP3_TO_STATE,
    GLOBAL_METRO_TO_COUNTRY,
)
from entity_standardizer.address._patterns import (
    RE_CLEAN_TOKEN,
    RE_NON_ALPHANUMERIC,
    RE_STATE_ZIP,
    RE_UK_POSTCODE,
    RE_CAN_POSTCODE,
    FROZEN_US_STATE_CODES,
)

logger = logging.getLogger(__name__)


def num_to_ordinal(n: int) -> str:
    """Converts integer into ordinal representation (1 -> 1ST, 2 -> 2ND, 3 -> 3RD, 4 -> 4TH)."""
    if 11 <= (n % 100) <= 13:
        suffix = 'TH'
    else:
        suffix = {1: 'ST', 2: 'ND', 3: 'RD'}.get(n % 10, 'TH')
    return f"{n}{suffix}"


def get_state_from_zip3(zip5: Optional[str]) -> Optional[str]:
    """Resolves US state code from first 3 digits of a 5-digit ZIP code."""
    if not zip5 or len(zip5) < 3 or not zip5[:3].isdigit():
        return None
    return ZIP3_TO_STATE.get(zip5[:3])


def _clean_token(t: str) -> str:
    """Strip leading/trailing punctuation and whitespace."""
    return RE_CLEAN_TOKEN.sub("", t.strip())


_US_STATE_NAMES = sorted((k for k in US_STATES if len(k) > 2 and k.replace(" ", "").isalpha()), key=len, reverse=True)
_RE_STATE_NAME_ZIP = re.compile(
    r"(?:^|[,\s])(?:" + "|".join(re.escape(n) for n in _US_STATE_NAMES) + r")\s+\d{5}(?:-\d{4})?\s*$"
)
# Australian "<STATE> <4-digit postcode>" tail ("Sydney NSW 2000"); WA is also a US state but a US ZIP has 5 digits.
_RE_AU_STATE_POSTCODE = re.compile(r"(?:^|[,\s])(?:NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\s*$")


_RE_TRAILING_CAN_PROVINCE = re.compile(r",\s*(?:ON|QC|BC|AB|MB|SK|NS|NB|NL|PE|NT|YT|NU)\s*$")
# Names scanned out of free text (street lines, city parts). The numeric ISO codes in COUNTRY_MAP ("500" = Montserrat,
# "250" = France, ...) are only meaningful in the dedicated country field: in free text they are house numbers.
_COUNTRY_NAME_MAP = COUNTRY_NAME_MAP

UNKNOWN_COUNTRY = "ZZZ"  # ISO 3166 user-assigned code, used when a supplied country name cannot be resolved
_COUNTRY_PLACEHOLDERS = frozenset(
    {"N/A", "N.A.", "N.A", "NONE", "NULL", "NIL", "UNKNOWN", "UNK", "NOT AVAILABLE", "NOT APPLICABLE", "-", "--", "?", "TBD"}
)
# A bare "NA" is Namibia's ISO code and is deliberately not a placeholder.


def _drop_from_first_numeric_token(text: str) -> str:
    """"LEEDS 4 EXTRA" -> "LEEDS": everything from the first digit-initial word (after the first word) onwards is dropped.

    Linear-time replacement for the regex ``\\s+\\d+.*$``, which backtracks quadratically on long whitespace runs.
    """
    words = text.split()
    for i, word in enumerate(words):
        if i > 0 and word[:1].isdigit():
            return " ".join(words[:i])
    return text.strip()


_RE_CROWN_POSTCODE = re.compile(r"\b(JE|GY|IM)\d[A-Z0-9]?\s*\d[A-Z]{2}\b")
_CROWN_PREFIX_ISO = {"JE": "JEY", "GY": "GGY", "IM": "IMN"}
_CROWN_NAME_ISO = {"JERSEY": "JEY", "GUERNSEY": "GGY", "ISLE OF MAN": "IMN"}


def _crown_dependency_code(text: str) -> Optional[str]:
    """JE/GY/IM postcode or a trailing Jersey/Guernsey/Isle of Man country name -> JEY/GGY/IMN."""
    up = text.upper()
    m = _RE_CROWN_POSTCODE.search(up)
    if m:
        return _CROWN_PREFIX_ISO[m.group(1)]
    last = up.split(",")[-1].strip()
    return _CROWN_NAME_ISO.get(last)


def normalize_country_code(
    country_raw: Optional[str],
    state_raw: Optional[str] = None,
    postal_raw: Optional[str] = None,
    raw_street: Optional[str] = None,
    city_raw: Optional[str] = None,
) -> str:
    """Resolve country to ISO-3166-1 alpha-3 code, defaulting to USA if state is a US state or CAN if Canadian province."""
    country_cand = ""
    if country_raw and country_raw.strip().upper() in _COUNTRY_PLACEHOLDERS:
        country_raw = None  # "N/A", "none", "unknown": a missing country, not a country called N/A (Namibia)
    country_supplied = bool(country_raw and country_raw.strip())
    if country_raw:
        c_clean = country_raw.strip().upper()
        c_clean_alphanumeric = RE_NON_ALPHANUMERIC.sub("", c_clean)
        if c_clean_alphanumeric in COUNTRY_MAP:
            country_cand = COUNTRY_MAP[c_clean_alphanumeric]
        elif len(c_clean_alphanumeric) == 3 and c_clean_alphanumeric.isascii() and c_clean_alphanumeric.isalpha():
            country_cand = c_clean_alphanumeric
        else:
            from entity_standardizer.address.international.countries import CountryRegistry

            info = CountryRegistry.get(country_raw)
            if info:
                country_cand = info.alpha3

    # If country is explicitly non-US, return it immediately
    if country_cand and country_cand not in US_DOMESTIC_ISO3 and country_cand != "":
        return country_cand

    # Check state indicator
    is_valid_us_state = False
    if state_raw:
        s_clean = RE_NON_ALPHANUMERIC.sub("", state_raw.strip().upper())
        s_ascii = "".join(c for c in unicodedata.normalize("NFKD", s_clean) if not unicodedata.combining(c))
        if s_clean in CANADIAN_PROVINCES or s_ascii in CANADIAN_PROVINCE_NAMES_COMPACT:
            return "CAN"
        if s_clean in US_STATES:
            is_valid_us_state = True

    # If state is explicitly a US state, then country is USA
    if is_valid_us_state:
        return "USA"

    if country_cand in US_DOMESTIC_ISO3 and country_cand != "USA":
        return country_cand

    # Cross-Border Foreign Operating Bank Branches / Metadata check:
    # The state is absent or not a US state here (a US state returned above), so check the city against global metros.
    # International metro check: When state is absent or not a US state,
    # check city against global metros to prevent erroneous USA defaulting
    if city_raw:
        c_clean = RE_NON_ALPHANUMERIC.sub(" ", city_raw).strip().upper()
        c_clean = " ".join(c_clean.split())
        candidates = [c_clean]
        c_no_num = _drop_from_first_numeric_token(c_clean)
        if c_no_num and c_no_num != c_clean:
            candidates.append(c_no_num)
        c_no_lead = re.sub(r"^\d+\s+", "", c_clean).strip()
        if c_no_lead and c_no_lead != c_clean:
            candidates.append(c_no_lead)
        if "," in city_raw:
            for part in city_raw.split(","):
                p_c = RE_NON_ALPHANUMERIC.sub(" ", part).strip().upper()
                p_c = " ".join(p_c.split())
                if p_c:
                    candidates.append(p_c)

        for cand in candidates:
            # (a valid US state already returned "USA" above, so a global-metro city name always wins here)
            if cand in GLOBAL_METRO_TO_COUNTRY:
                return GLOBAL_METRO_TO_COUNTRY[cand]
            cand_unaccent = unicodedata.normalize("NFKD", cand).encode("ASCII", "ignore").decode("utf-8")
            if cand_unaccent in GLOBAL_METRO_TO_COUNTRY:
                return GLOBAL_METRO_TO_COUNTRY[cand_unaccent]

    if postal_raw:
        p_clean = postal_raw.strip().upper()
        if RE_CAN_POSTCODE.match(p_clean):
            return "CAN"
        if RE_UK_POSTCODE.match(p_clean):
            return _crown_dependency_code(p_clean) or "GBR"

    # Scan raw single string for international indicators
    if raw_street:
        st_clean = raw_street.upper()
        if "CAYMAN" in st_clean:
            return "CYM"
        crown = _crown_dependency_code(st_clean)
        if crown:
            return crown
        if RE_UK_POSTCODE.search(st_clean) or st_clean.endswith(", UK") or st_clean.endswith(" UK") or "UNITED KINGDOM" in st_clean:
            return "GBR"
        if RE_CAN_POSTCODE.search(st_clean) or st_clean.endswith(", CANADA") or st_clean.endswith(" CANADA"):
            return "CAN"
        # "..., Toronto, ON": a trailing comma-separated Canadian province code (none of these is a US state code).
        if _RE_TRAILING_CAN_PROVINCE.search(st_clean):
            return "CAN"
        m_sz = RE_STATE_ZIP.search(st_clean)
        if m_sz and m_sz.group(1).upper() in FROZEN_US_STATE_CODES:
            return "USA"
        # "..., Poland, Ohio 44514": a full US state name followed by a 5-digit ZIP is a US address even when the
        # city (Poland, Denmark, Holland, Peru) or the state (Georgia) is also a country name.
        if _RE_STATE_NAME_ZIP.search(st_clean):
            return "USA"
        if _RE_AU_STATE_POSTCODE.search(st_clean):
            return "AUS"

        # Check if address ends with a US state code/name (or US state before country)
        # BEFORE scanning raw components against COUNTRY_MAP to prevent domestic namesake cities
        # (e.g. Lebanon NH, Mexico ME, Brazil IN, Paris TX, London OH, Berlin CT)
        # from being hijacked by sovereign country names.
        raw_parts = [p.strip() for p in raw_street.split(",") if p.strip()]
        if raw_parts:
            last_clean = RE_NON_ALPHANUMERIC.sub("", raw_parts[-1]).strip().upper()
            if last_clean in ("USA", "US", "UNITED STATES", "UNITED STATES OF AMERICA"):
                if len(raw_parts) >= 2:
                    prev_clean = RE_NON_ALPHANUMERIC.sub("", raw_parts[-2]).strip().upper()
                    if prev_clean in FROZEN_US_STATE_CODES or prev_clean in US_STATES:
                        return "USA"
            elif last_clean in FROZEN_US_STATE_CODES or last_clean in US_STATES:
                return "USA"
            else:
                subwords = raw_parts[-1].split()  # non-empty: the parts were filtered to non-blank strings
                sub_last = RE_NON_ALPHANUMERIC.sub("", subwords[-1]).strip().upper()
                if sub_last in FROZEN_US_STATE_CODES or sub_last in US_STATES:
                    return "USA"

        # A trailing comma part that is a country's name in any supported language/accent ("Italia", "Belgique",
        # "Sverige", "México") resolves through the same registry the structured `country` field uses.
        if len(raw_parts) >= 2:
            trailing = raw_parts[-1].strip()
            if 3 <= len(trailing) <= 40 and not any(ch.isdigit() for ch in trailing):
                from entity_standardizer.address.international.countries import CountryRegistry

                info = CountryRegistry.get(trailing)
                if info is not None and info.alpha3 != "USA":
                    return info.alpha3

        # Check country map in raw street components (ignoring US state abbreviations and numbers)
        for part in raw_street.split(","):
            p_clean = RE_NON_ALPHANUMERIC.sub(" ", part).strip().upper()
            p_clean = " ".join(p_clean.split())
            p_alphanumeric = RE_NON_ALPHANUMERIC.sub("", part).strip().upper()
            if p_alphanumeric in FROZEN_US_STATE_CODES or p_alphanumeric.isdigit():
                continue
            if p_alphanumeric in STREET_SUFFIXES or p_alphanumeric in STREET_SUFFIXES.values():
                continue
            if p_clean in _COUNTRY_NAME_MAP and _COUNTRY_NAME_MAP[p_clean] != "USA":
                return _COUNTRY_NAME_MAP[p_clean]
            if p_alphanumeric in _COUNTRY_NAME_MAP and _COUNTRY_NAME_MAP[p_alphanumeric] != "USA":
                return _COUNTRY_NAME_MAP[p_alphanumeric]

        raw_words = RE_NON_ALPHANUMERIC.sub(" ", raw_street).strip().upper().split()
        if len(raw_words) >= 2:
            two_w = f"{raw_words[-2]} {raw_words[-1]}"
            if two_w in _COUNTRY_NAME_MAP and _COUNTRY_NAME_MAP[two_w] != "USA":
                return _COUNTRY_NAME_MAP[two_w]
        if raw_words and raw_words[-1] in _COUNTRY_NAME_MAP and _COUNTRY_NAME_MAP[raw_words[-1]] != "USA":
            if (
                (len(raw_words[-1]) > 2 or raw_words[-1] not in FROZEN_US_STATE_CODES)
                and not raw_words[-1].isdigit()
                and raw_words[-1] not in STREET_SUFFIXES
                and raw_words[-1] not in STREET_SUFFIXES.values()
            ):
                return _COUNTRY_NAME_MAP[raw_words[-1]]
        elif len(raw_words) >= 2 and raw_words[-1].isdigit():
            prev_w = raw_words[-2]
            if (
                prev_w in _COUNTRY_NAME_MAP
                and _COUNTRY_NAME_MAP[prev_w] != "USA"
                and (len(prev_w) > 2 or prev_w not in FROZEN_US_STATE_CODES)
                and prev_w not in STREET_SUFFIXES
                and prev_w not in STREET_SUFFIXES.values()
            ):
                return _COUNTRY_NAME_MAP[prev_w]

        # Check global metros in raw street SECOND
        for part in raw_street.split(","):
            p_clean = RE_NON_ALPHANUMERIC.sub(" ", part).strip().upper()
            p_clean = " ".join(p_clean.split())
            if p_clean in GLOBAL_METRO_TO_COUNTRY:
                return GLOBAL_METRO_TO_COUNTRY[p_clean]
            c_unaccent = unicodedata.normalize("NFKD", p_clean).encode("ASCII", "ignore").decode("utf-8")
            if c_unaccent in GLOBAL_METRO_TO_COUNTRY:
                return GLOBAL_METRO_TO_COUNTRY[c_unaccent]
            # Drop everything from the first whitespace-separated token that starts with a digit (linear scan).
            _tokens = p_clean.split()
            _cut = next((i for i, tok in enumerate(_tokens) if i > 0 and tok[:1].isdigit()), None)
            p_no_num = " ".join(_tokens[:_cut]) if _cut is not None else p_clean.strip()
            if p_no_num and p_no_num != p_clean:
                if p_no_num in GLOBAL_METRO_TO_COUNTRY:
                    return GLOBAL_METRO_TO_COUNTRY[p_no_num]
                if p_no_num in _COUNTRY_NAME_MAP and _COUNTRY_NAME_MAP[p_no_num] != "USA":
                    return _COUNTRY_NAME_MAP[p_no_num]
            p_no_lead = re.sub(r"^\d+\s+", "", p_clean).strip()
            if p_no_lead and p_no_lead != p_clean:
                if p_no_lead in GLOBAL_METRO_TO_COUNTRY:
                    return GLOBAL_METRO_TO_COUNTRY[p_no_lead]
                p_lead_unaccent = unicodedata.normalize("NFKD", p_no_lead).encode("ASCII", "ignore").decode("utf-8")
                if p_lead_unaccent in GLOBAL_METRO_TO_COUNTRY:
                    return GLOBAL_METRO_TO_COUNTRY[p_lead_unaccent]
                if p_no_lead in _COUNTRY_NAME_MAP and _COUNTRY_NAME_MAP[p_no_lead] != "USA":
                    return _COUNTRY_NAME_MAP[p_no_lead]

    if country_supplied and not country_cand:
        # A country was given but nothing recognises it and nothing else points to the US: do not silently call it USA.
        return UNKNOWN_COUNTRY
    return "USA"


normalize_country = normalize_country_code


def normalize_us_state(state_raw: Optional[str], zip5: Optional[str] = None) -> str:
    """Normalize US state string or full name to standard 2-letter postal code, with ZIP3 auto-healing."""
    res = ""
    if state_raw:
        s_raw = state_raw.strip()
        if s_raw.upper().startswith("USA-"):
            s_raw = s_raw[4:].strip()
        elif s_raw.upper().startswith("US-"):
            s_raw = s_raw[3:].strip()
        s_clean = RE_NON_ALPHANUMERIC.sub("", s_raw.upper())
        res = US_STATES.get(s_clean, s_clean[:2] if len(s_clean) == 2 else s_clean)
    if (not res or res not in FROZEN_US_STATE_CODES) and zip5:
        zip3_st = get_state_from_zip3(zip5)
        if zip3_st:
            res = zip3_st
    return res


def swap_us_city_state(city: Optional[str], state: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Repair a city/state pair entered the wrong way round ("city: IL, state: Chicago").

    Only when the city field is a US state (code or name) and the state field is NOT one; "Indiana" + "PA" (a town) and
    any pair whose state field is a real state stay as given.
    """
    if city and state and city.strip(" .").upper() in US_STATES and state.strip(" .").upper() not in US_STATES:
        return state, city
    return city, state


def swap_region_city_state(city: Optional[str], state: Optional[str], regions) -> Tuple[Optional[str], Optional[str]]:
    """Generic form of :func:`swap_us_city_state`: swap only when ``city`` is one of the country's regions (code or
    name, upper-case keys in ``regions``) and ``state`` is not."""
    if city and state:
        c_clean = city.strip(" .").upper()
        s_clean = state.strip(" .").upper()
        c_folded = unicodedata.normalize("NFKD", c_clean).encode("ascii", "ignore").decode("ascii")
        s_folded = unicodedata.normalize("NFKD", s_clean).encode("ascii", "ignore").decode("ascii")
        is_city_reg = c_clean in regions or c_folded in regions
        is_state_reg = s_clean in regions or s_folded in regions
        if is_city_reg and not is_state_reg:
            return state, city
    return city, state


def normalize_us_postal_code(postal_raw: Optional[str]) -> Tuple[str, str]:
    """Returns (formatted_postal_code, zip5).

    Accepts ZIP (``12345``), ZIP+4 (``12345-6789`` / ``123456789``) and a 4-digit ZIP whose leading zero was lost
    (``1234`` -> ``01234``). Anything else (3, 6-8 or 10+ digits, letters, a ``1234-5678`` split) is not a US ZIP: it
    is returned cleaned but unchanged with an empty ``zip5``, never truncated or padded into a plausible-looking ZIP.
    """
    if not postal_raw:
        return "", ""
    clean = postal_raw.strip().upper()
    if not clean:
        return "", ""
    only = clean.replace("-", "").replace(" ", "")
    if only.isascii() and only.isdigit():
        if len(only) == 4 and "-" not in clean and " " not in clean:
            only = f"0{only}"
        if len(only) == 5 and ("-" not in clean or clean.endswith("-")):
            return only, only
        if len(only) == 9 and (clean.count("-") == 0 or RE_ZIP_PLUS4_SPLIT.match(clean)):
            return f"{only[:5]}-{only[5:]}", only[:5]
    return clean, ""


RE_ZIP_PLUS4_SPLIT = re.compile(r"^\d{5}[-\s]\d{4}$")


def is_registered_agent_hub_address(
    street1: str,
    street2: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    country: str = "USA",
    raw_street: str = ""
) -> bool:
    """Detects whether an address corresponds to a known corporate service or formation hub."""
    from entity_standardizer.address.registry import is_registered_agent_hub_address as _reg_is_hub
    return _reg_is_hub(
        street1=street1,
        street2=street2,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country,
        raw_street=raw_street,
    )
