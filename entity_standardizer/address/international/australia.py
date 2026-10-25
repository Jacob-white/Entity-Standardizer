"""Australia Address Grammar (AUS).

Provides specialized parsing and normalization for Australian addresses:
- Level / Unit conventions: LEVEL 15, LVL 12, SUITE 402, UNIT 5
- Australian Unit/Number slash notation: 5/100 GEORGE ST -> Unit 5, 100 George St
- 8 States and Territories: NSW, VIC, QLD, WA, SA, TAS, ACT, NT
- 4-digit postcode validation and state range concordance
"""

from __future__ import annotations

import re
from typing import Callable, ClassVar, Dict, List, Optional, Tuple

from entity_standardizer.address.international.base import (
    may_abbreviate_street_type,
    street_type_index,
    CountryGrammar,
    ParsedAddressComponents,
    UniversalInternationalGrammar,
    split_intl_secondary_unit,
)
from entity_standardizer.address.international.commaless import split_commaless_region_postal_city, town_set
from entity_standardizer.address.tables import DIRECTIONALS, STREET_SUFFIXES


# Australian States and Territories
AU_STATES: Dict[str, str] = {
    "NSW": "NSW", "NEW SOUTH WALES": "NSW",
    "VIC": "VIC", "VICTORIA": "VIC",
    "QLD": "QLD", "QUEENSLAND": "QLD",
    "WA": "WA", "WESTERN AUSTRALIA": "WA",
    "SA": "SA", "SOUTH AUSTRALIA": "SA",
    "TAS": "TAS", "TASMANIA": "TAS",
    "ACT": "ACT", "AUSTRALIAN CAPITAL TERRITORY": "ACT",
    "NT": "NT", "NORTHERN TERRITORY": "NT",
}

# Postcode ranges per state
AU_POSTCODE_RANGES: List[Tuple[int, int, str]] = [
    (1000, 2599, "NSW"), (2619, 2899, "NSW"), (2921, 2999, "NSW"),
    (200, 299, "ACT"), (2600, 2618, "ACT"), (2900, 2920, "ACT"),
    (3000, 3999, "VIC"), (8000, 8999, "VIC"),
    (4000, 4999, "QLD"), (9000, 9999, "QLD"),
    (5000, 5799, "SA"), (5800, 5999, "SA"),
    (6000, 6797, "WA"), (6800, 6999, "WA"),
    (7000, 7799, "TAS"), (7800, 7999, "TAS"),
    (800, 899, "NT"), (900, 999, "NT"),
]

_RE_AU_TRAILING_COUNTRY = re.compile(r"\s+(?:AUSTRALIA|COMMONWEALTH\s+OF\s+AUSTRALIA|AUS|AU)\s*$", re.IGNORECASE)
_RE_NZ_TRAILING_COUNTRY = re.compile(r"\s+(?:NEW\s+ZEALAND|AOTEAROA|NZL|NZ)\s*$", re.IGNORECASE)
_RE_FOUR_DIGITS = re.compile(r"\d{4}")

# Well-known cities and suburbs, used only to find where the city starts in a comma-less line (the street-type
# word is the primary anchor; this list covers multi-word names and names that start with a direction).
AU_TOWNS = town_set((
    "LANE COVE", "SYDNEY", "MELBOURNE", "BRISBANE", "PERTH", "ADELAIDE", "HOBART", "DARWIN", "CANBERRA", "GOLD COAST", "NEWCASTLE",
    "WOLLONGONG", "GEELONG", "CAIRNS", "TOWNSVILLE", "TOOWOOMBA", "BALLARAT", "BENDIGO", "LAUNCESTON", "ALBURY",
    "WAGGA WAGGA", "MACKAY", "ROCKHAMPTON", "BUNDABERG", "HERVEY BAY", "SUNSHINE COAST", "ALICE SPRINGS", "PARRAMATTA",
    "NORTH PARRAMATTA", "SOUTH YARRA", "SOUTH BRISBANE", "WEST END", "FORTITUDE VALLEY", "NEW FARM", "HIGHGATE HILL",
    "SURRY HILLS", "BONDI JUNCTION", "BONDI BEACH", "ST KILDA", "ST LEONARDS", "ST ALBANS", "ST PETERS", "ST IVES",
    "PORT MELBOURNE", "PORT ADELAIDE", "NORTH SYDNEY", "NORTH MELBOURNE", "WEST MELBOURNE", "SOUTH MELBOURNE",
    "EAST MELBOURNE", "SOUTHBANK", "DOCKLANDS", "CARLTON", "FITZROY", "RICHMOND", "HAWTHORN", "KEW", "CAMBERWELL",
    "BOX HILL", "CHATSWOOD", "MANLY", "BLACKTOWN", "PENRITH", "LIVERPOOL", "CAMPBELLTOWN", "HORNSBY", "BURWOOD",
    "STRATHFIELD", "BANKSTOWN", "HURSTVILLE", "SUTHERLAND", "MOUNT GRAVATT", "MOUNT LAWLEY", "SOUTH PERTH",
    "EAST PERTH", "WEST PERTH", "NORTH PERTH", "NORTH ADELAIDE", "GLENELG", "PRAHRAN", "SOUTH BANK", "KANGAROO POINT",
    "SPRING HILL", "PADDINGTON", "WOOLLOOMOOLOO", "DARLINGHURST", "REDFERN", "NEWTOWN", "BALMAIN", "LEICHHARDT",
    "ULTIMO", "PYRMONT", "HAYMARKET", "THE ROCKS", "MILSONS POINT", "WOOLLOONGABBA", "TOOWONG", "INDOOROOPILLY",
    "CHERMSIDE", "SOUTHPORT", "SURFERS PARADISE", "BROADBEACH", "FREMANTLE", "SUBIACO", "NORTHBRIDGE", "GLEBE",
))
NZ_TOWNS = town_set((
    "AUCKLAND", "WELLINGTON", "CHRISTCHURCH", "HAMILTON", "TAURANGA", "DUNEDIN", "PALMERSTON NORTH", "NAPIER",
    "HASTINGS", "NELSON", "ROTORUA", "NEW PLYMOUTH", "WHANGAREI", "INVERCARGILL", "WHANGANUI", "GISBORNE",
    "QUEENSTOWN", "TIMARU", "BLENHEIM", "TAUPO", "PORIRUA", "LOWER HUTT", "UPPER HUTT", "HUTT", "PONSONBY",
    "GREY LYNN", "NEWMARKET", "PARNELL", "TE ARO", "KARORI", "KELBURN", "THORNDON", "MOUNT VICTORIA", "MOUNT EDEN",
    "MOUNT MAUNGANUI", "ST HELIERS", "ST HELENS",
    "EAST TAMAKI", "MANUKAU", "ONEHUNGA", "PAPAKURA", "TAKAPUNA", "DEVONPORT", "HENDERSON", "NEW LYNN", "AVONDALE",
    "RICCARTON", "ADDINGTON", "SYDENHAM", "SUMNER", "PAPANUI", "LYTTELTON", "ASHBURTON", "RANGIORA", "KAIAPOI",
    "OAMARU", "GREYMOUTH", "WESTPORT", "MASTERTON", "PETONE", "ISLAND BAY", "MIRAMAR",
))


def _postcode_in_state(postcode: str, state: str) -> bool:
    """True when the 4-digit postcode lies in one of the ranges of the (already normalised) state code."""
    if not postcode or not state or not postcode.isdigit():
        return False
    p_int = int(postcode)
    return any(p_min <= p_int <= p_max and s_exp == state for p_min, p_max, s_exp in AU_POSTCODE_RANGES)


_PLACE_NAME_PREFIXES = frozenset({"MOUNT", "MT", "PORT", "LAKE", "NORTH", "SOUTH", "EAST", "WEST", "NEW", "ST", "SAINT", "CAPE", "POINT"})


def _au_region_suffix(rest: List[str], postal: str) -> Optional[Tuple[int, str]]:
    """State words (code or full name) directly before the postcode, accepted only when the postcode is in range."""
    for n in (3, 2, 1):
        if len(rest) > n:
            key = " ".join(rest[-n:]).upper().replace(".", "")
            code = AU_STATES.get(key)
            # "Mount Victoria 3000": a full state name that is the tail of a place name is the suburb, not the state
            if key != code and rest[-n - 1].upper() in _PLACE_NAME_PREFIXES:
                continue
            if code and _postcode_in_state(postal, code):
                return n, code
    return None


def _four_digits(candidate: str) -> bool:
    return _RE_FOUR_DIGITS.fullmatch(candidate) is not None


def _split_commaless_au_nz(
    street1: Optional[str],
    city: Optional[str],
    state: Optional[str],
    postal_code: Optional[str],
    country_tail: "re.Pattern[str]",
    towns: set,
    region_suffix: Optional[Callable[[List[str], str], Optional[Tuple[int, str]]]],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Comma-less split of an unstructured single-line AU / NZ input; returns the possibly updated fields."""
    if street1 and not (city or state or postal_code) and "," not in street1:
        split = split_commaless_region_postal_city(street1, _four_digits, region_suffix, towns, country_tail)
        if split is not None:
            return split
    return street1, city, state, postal_code


# Slash unit pattern: e.g. "5/100 GEORGE ST", "U5/100 GEORGE ST", "LEVEL 15/225 GEORGE ST"
RE_AU_SLASH_UNIT = re.compile(
    r"^(?:(?P<pfx>UNIT|U|APT|SUITE|STE|LEVEL|LVL|L)\s*)?(?P<unit>[0-9A-Za-z]+)\s*\/\s*(?P<num>\d+[A-Za-z0-9\-]*)\s+(?P<st>.+)$",
    re.IGNORECASE,
)

# Level pattern: LEVEL 15, LVL 12, L15
RE_AU_LEVEL = re.compile(
    r"\b(?:LEVEL|LVL|L)\.?\s*([0-9]+)\b",
    re.IGNORECASE,
)

# 4-digit postcode
RE_AU_POSTCODE = re.compile(
    r"\b([0-9]{4})\b",
)


class AustraliaGrammar(CountryGrammar):
    """Australia localized address grammar."""

    country_iso3: ClassVar[str] = "AUS"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "AUS",
        "AU",
        "AUSTRALIA",
        "COMMONWEALTH OF AUSTRALIA",
        "CCK", "COCOS ISLANDS", "COCOS (KEELING) ISLANDS",
        "CXR", "CHRISTMAS ISLAND",
        "NFK", "NORFOLK ISLAND",
        "HMD", "HEARD ISLAND AND MCDONALD ISLANDS",
        "ATA", "ANTARCTICA",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Australian 4-digit postcode."""
        if not raw_code:
            return ""
        digits = re.sub(r"[^\d]", "", raw_code.strip())
        if len(digits) == 3:
            digits = f"0{digits}"
        if len(digits) == 4:
            return digits
        m = RE_AU_POSTCODE.search(raw_code.strip())
        if m:
            return m.group(1)
        return ""

    def standardize(
        self,
        street1: Optional[str] = None,
        street2: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
        raw_street_address: Optional[str] = None,
    ) -> ParsedAddressComponents:
        """Standardize; a comma-less "14 Gray Court Adelaide SA 5000" is split at its state and postcode first."""
        street1, city, state, postal_code = _split_commaless_au_nz(
            street1, city, state, postal_code, _RE_AU_TRAILING_COUNTRY, AU_TOWNS, _au_region_suffix
        )
        return super().standardize(street1, street2, city, state, postal_code, country, raw_street_address)

    def validate_postcode_state(self, postcode: str, state: str) -> bool:
        """Check if 4-digit postcode falls into the designated state range."""
        st_norm = (state or "").upper()
        return _postcode_in_state(postcode, AU_STATES.get(st_norm, st_norm))

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise_name, street_number, street_name) from Australian address line."""
        if not street_line:
            return None, None, None

        s_clean = " ".join(street_line.strip().split())

        # "Tower, 12 George St": a leading premise name followed by a number-led street line
        if "," in s_clean:
            head, tail = (p.strip() for p in s_clean.rsplit(",", 1))
            if head and tail[:1].isdigit():
                _, tail_num, tail_name = self.extract_premise_and_thoroughfare(tail)
                return head.upper(), tail_num, tail_name

        # Check slash unit: "5/100 GEORGE ST"
        m_slash = RE_AU_SLASH_UNIT.match(s_clean)
        if m_slash:
            return None, m_slash.group(2), m_slash.group(3)

        # Standard street number and name
        m_st = re.match(r"^(\d+[A-Za-z0-9\-]*)\s+(.+)$", s_clean)
        if m_st:
            return None, m_st.group(1), m_st.group(2)

        return None, None, s_clean

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        """Parse tokenized lines into structured Australian components."""
        s1 = metadata.get("street1") or ""
        s2 = metadata.get("street2") or ""
        city_raw = metadata.get("city") or ""
        state_raw = metadata.get("state") or ""
        post_raw = metadata.get("postal_code") or ""
        raw_full = metadata.get("raw_street_address") or ""
        country_raw = metadata.get("country", self.country_iso3)
        from entity_standardizer.address.international.countries import CountryRegistry
        info = CountryRegistry.get(country_raw)
        country_iso = info.alpha3 if (info and info.alpha3 in self.supported_countries) else self.country_iso3

        combined = s1.strip() if s1 else raw_full.strip()
        if not combined and s2:
            combined = s2.strip()
            s2 = ""

        # Normalize State
        norm_state = ""
        if state_raw:
            s_up = state_raw.strip().upper()
            norm_state = AU_STATES.get(s_up, s_up if len(s_up) in (2, 3) else "")

        norm_post = self.normalize_postal_code(post_raw)

        # Comma decomposition for unstructured single-line addresses
        if not city_raw and "," in combined:
            parts = [p.strip() for p in combined.split(",") if p.strip()]
            if parts and parts[-1].upper() in ("AUSTRALIA", "AUS", "AU", "COMMONWEALTH OF AUSTRALIA"):
                parts.pop()

            if parts:
                last_p = parts[-1]
                m_post_c = RE_AU_POSTCODE.search(last_p)
                if m_post_c:
                    if not norm_post:
                        norm_post = m_post_c.group(1)
                    last_p = (last_p[:m_post_c.start()] + last_p[m_post_c.end():]).strip()

                for s_name, s_code in sorted(AU_STATES.items(), key=lambda x: len(x[0]), reverse=True):
                    m_s_c = re.search(rf"\b{re.escape(s_name)}\b", last_p, re.IGNORECASE)
                    if m_s_c:
                        if not norm_state:
                            norm_state = s_code
                        last_p = (last_p[:m_s_c.start()] + last_p[m_s_c.end():]).strip()
                        break

                if last_p and not last_p[0].isdigit():
                    city_raw = last_p
                    parts.pop()
                elif last_p:
                    # A number-led remainder is the street ("12 George St, AUSTRALIA"), never a suburb.
                    parts[-1] = last_p
                else:
                    parts.pop()

            combined = ", ".join(parts)

        # Extract 4-digit Postcode if not already found
        norm_post = self.normalize_postal_code(post_raw or norm_post)
        if not norm_post:
            m_post = RE_AU_POSTCODE.search(combined)
            if m_post:
                norm_post = m_post.group(1)
                combined = combined[:m_post.start()] + " " + combined[m_post.end():]

        # Infer state from postcode if missing
        if not norm_state and norm_post and norm_post.isdigit():
            p_val = int(norm_post)
            for p_min, p_max, s_code in AU_POSTCODE_RANGES:
                if p_min <= p_val <= p_max:
                    norm_state = s_code
                    break

        # Check secondary unit
        sec_unit_str = ""
        st1_rem, st2_norm = split_intl_secondary_unit(combined, s2)
        if st2_norm:
            sec_unit_str = st2_norm
            combined = st1_rem
        else:
            m_slash = RE_AU_SLASH_UNIT.match(combined.strip())
            if m_slash:
                pfx = (m_slash.group("pfx") or "").upper()
                u_val = m_slash.group("unit").upper()
                st_num = m_slash.group("num")
                st_name = m_slash.group("st")
                if pfx in ("LEVEL", "LVL", "L") or u_val.startswith("LEVEL") or u_val.startswith("LVL"):
                    sec_unit_str = f"LEVEL {u_val}" if not u_val.startswith("LEVEL") else u_val
                elif pfx in ("SUITE", "STE"):
                    sec_unit_str = f"STE {u_val}"
                elif pfx in ("APT",):
                    sec_unit_str = f"APT {u_val}"
                else:
                    sec_unit_str = f"UNIT {u_val}"
                combined = f"{st_num} {st_name}"
            else:
                m_lvl = RE_AU_LEVEL.search(combined)
                if m_lvl:
                    sec_unit_str = f"LEVEL {m_lvl.group(1)}"
                    combined = combined[:m_lvl.start()] + " " + combined[m_lvl.end():]

        combined = " ".join(combined.strip(" ,.-/").split())
        combined = re.sub(r"(?:,\s*|\s+)\b(?:AUSTRALIA|AUS|AU)\b$", "", combined, flags=re.IGNORECASE).strip(" ,.-")

        # Strip state from thoroughfare if embedded at end
        for st_name, st_code in sorted(AU_STATES.items(), key=lambda x: len(x[0]), reverse=True):
            m_st_end = re.search(rf"(?:,\s*|\s+)\b{re.escape(st_name)}\b$", combined, re.IGNORECASE)
            if m_st_end:
                if not norm_state:
                    norm_state = st_code
                combined = combined[:m_st_end.start()].strip(" ,.-")
                break

        # Extract suburb/city if comma separated
        if not city_raw and "," in combined and not combined.rsplit(",", 1)[1].strip()[:1].isdigit():
            st_part, city_part = combined.rsplit(",", 1)
            city_raw = city_part.strip().upper()
            combined = st_part.strip()

        # Extract premise, number, thoroughfare
        b_name, st_num_extracted, st_name_extracted = self.extract_premise_and_thoroughfare(combined)

        # Normalize thoroughfare suffixes (STREET -> ST, ROAD -> RD, etc.)
        if st_name_extracted:
            words = st_name_extracted.split()
            norm_words = []
            type_idx = street_type_index(words)
            for idx, w in enumerate(words):
                w_up = w.upper()
                if w_up in STREET_SUFFIXES and may_abbreviate_street_type(w_up, idx, type_idx):
                    norm_words.append(STREET_SUFFIXES[w_up])
                elif w_up in DIRECTIONALS:
                    norm_words.append(DIRECTIONALS[w_up])
                else:
                    norm_words.append(w_up)
            st_name_extracted = " ".join(norm_words)

        u_parts = sec_unit_str.split(None, 1) if sec_unit_str else []
        u_type = u_parts[0] if len(u_parts) > 1 else None
        u_num = u_parts[1] if len(u_parts) > 1 else (sec_unit_str or None)

        return ParsedAddressComponents(
            street_number=st_num_extracted,
            street_name=st_name_extracted,
            street_type=None,
            unit_type=u_type,
            unit_number=u_num,
            building_name=b_name,
            dependent_locality=None,
            city=city_raw.strip().upper() if city_raw else "",
            state=norm_state,
            postal_code=norm_post or "",
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
            confidence_score=0.95,
        )


class NewZealandGrammar(UniversalInternationalGrammar):
    """New Zealand: the universal grammar plus a comma-less "134 Willis Street Wellington 6011" split."""

    country_iso3: ClassVar[str] = "NZL"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "NZL", "NZ", "NEW ZEALAND", "AOTEAROA",
        "COK", "COOK ISLANDS",
        "NIU", "NIUE",
        "TKL", "TOKELAU",
    )

    def standardize(
        self,
        street1: Optional[str] = None,
        street2: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
        raw_street_address: Optional[str] = None,
    ) -> ParsedAddressComponents:
        """Standardize; New Zealand has no state, so only city and the 4-digit postcode are split off."""
        street1, city, state, postal_code = _split_commaless_au_nz(
            street1, city, state, postal_code, _RE_NZ_TRAILING_COUNTRY, NZ_TOWNS, None
        )
        return super().standardize(street1, street2, city, state, postal_code, country, raw_street_address)
