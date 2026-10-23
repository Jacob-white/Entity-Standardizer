"""Hong Kong Address Grammar (HKG).

Provides specialized parsing and normalization for Hong Kong addresses:
- Floor and flat conventions: FLAT A, 15/F, ROOM 1205, SUITE 801
- Tower / commercial premise names: TWO INTERNATIONAL FINANCE CENTRE, CHATER HOUSE, JARDINE HOUSE, etc.
- District hierarchy: Central, Admiralty, Wan Chai, Tsim Sha Tsui, Kowloon, New Territories
- Postal code handling: Hong Kong does not use domestic postal codes
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import ClassVar, List, Optional, Tuple

from address_standardizer.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)


@dataclass(slots=True)
class HongKongParsedAddressComponents(ParsedAddressComponents):
    """Structured parsed address components for Hong Kong."""

    def format_street1(self) -> str:
        if self.street_number and self.street_name:
            return f"{self.street_number} {self.street_name.upper()}".strip()
        return ParsedAddressComponents.format_street1(self)

    def format_street2(self) -> str:
        sec = ParsedAddressComponents.format_street2(self)
        if self.building_name and self.street_number and self.street_name:
            if sec:
                return f"{sec}, {self.building_name}".strip(" ,")
            return self.building_name.strip()
        return sec


# Hong Kong Districts and Localities
HK_ISLAND_DISTRICTS = {
    "CENTRAL", "ADMIRALTY", "WAN CHAI", "WANCHAI", "CAUSEWAY BAY", "SHEUNG WAN",
    "NORTH POINT", "QUARRY BAY", "TAIKOO", "TAIKOO SHING", "ABERDEEN", "POK FU LAM",
    "POKFULAM", "WESTERN DISTRICT", "WESTERN", "MID-LEVELS", "MID LEVELS", "HAPPY VALLEY",
    "KENNEDY TOWN", "CHAI WAN", "SHAU KEI WAN", "SAI YING PUN", "CENTRAL AND WESTERN",
    "EASTERN DISTRICT", "SOUTHERN DISTRICT", "WAN CHAI DISTRICT",
}

HK_KOWLOON_DISTRICTS = {
    "TSIM SHA TSUI", "TSIMSHATSUI", "TST", "MONG KOK", "MONGKOK", "YAU MA TEI",
    "YAUMATEI", "KWUN TONG", "KOWLOON BAY", "HUNG HOM", "HUNGHOM", "CHEUNG SHA WAN",
    "LAI CHI KOK", "SHAM SHUI PO", "JORDAN", "SAN PO KONG", "KOWLOON TONG",
    "TO KWA WAN", "WONG TAI SIN", "KOWLOON CITY", "KOWLOON",
}

HK_NT_DISTRICTS = {
    "SHA TIN", "SHATIN", "TSUEN WAN", "KWAI CHUNG", "TUEN MUN", "TAI PO",
    "YUEN LONG", "SAI KUNG", "TSEUNG KWAN O", "TKO", "FANLING", "SHEUNG SHUI",
    "MA ON SHAN", "TIN SHUI WAI", "TSING YI", "TUNG CHUNG", "LANTAU", "LANTAU ISLAND",
    "NEW TERRITORIES", "NT",
}

_HK_ROAD_TYPE_WORDS = frozenset({
    "ROAD", "RD", "STREET", "ST", "AVENUE", "AVE", "LANE", "LN", "PATH", "DRIVE", "DR", "TERRACE", "BOULEVARD",
    "BLVD", "WAY", "CIRCUIT", "CRESCENT", "STREETS",
})

ALL_HK_DISTRICTS = HK_ISLAND_DISTRICTS | HK_KOWLOON_DISTRICTS | HK_NT_DISTRICTS

# Prominent Commercial Towers and Buildings
HK_NOTABLE_BUILDINGS = {
    "TWO INTERNATIONAL FINANCE CENTRE", "ONE INTERNATIONAL FINANCE CENTRE",
    "INTERNATIONAL FINANCE CENTRE", "2 IFC", "1 IFC", "IFC",
    "INTERNATIONAL COMMERCE CENTRE", "ICC",
    "EXCHANGE SQUARE", "EXCHANGE SQUARE TOWER 1", "EXCHANGE SQUARE TOWER 2",
    "EXCHANGE SQUARE TOWER 3", "ONE EXCHANGE SQUARE", "TWO EXCHANGE SQUARE",
    "THREE EXCHANGE SQUARE", "CHATER HOUSE", "JARDINE HOUSE", "CHEUNG KONG CENTER",
    "BANK OF CHINA TOWER", "HSBC MAIN BUILDING", "THE CENTER", "PACIFIC PLACE",
    "ONE PACIFIC PLACE", "TWO PACIFIC PLACE", "THREE PACIFIC PLACE",
    "AIA CENTRAL", "PRINCE'S BUILDING", "ALEXANDRA HOUSE", "GLOUCESTER TOWER",
    "EDINBURGH TOWER", "YORK HOUSE", "LANDMARK ATRIUM", "CITIC TOWER",
    "MAN YEE BUILDING", "SWIRE HOUSE", "HONG KONG CLUB BUILDING",
    "STANDARD CHARTERED BANK BUILDING", "LI PPO CENTRE", "LIPPO CENTRE",
    "CHAMPION TOWER", "THREE GARDEN ROAD",
}

# Flat and Floor extraction regexes
RE_HK_FLAT_AND_FLOOR = re.compile(
    r"\b((?:FLAT|UNIT|RM|ROOM|SUITE|STE|OFC|OFFICE)\s+[A-Za-z0-9\-]+)[,\s]+([BGL]?\d*\/?[Ff]|(?:[0-9]+(?:ST|ND|RD|TH)?\s+FLOOR))\b",
    re.IGNORECASE,
)
RE_HK_FLOOR_AND_FLAT = re.compile(
    r"\b([BGL]?\d*\/?[Ff]|(?:[0-9]+(?:ST|ND|RD|TH)?\s+FLOOR))[,\s]+((?:FLAT|UNIT|RM|ROOM|SUITE|STE|OFC|OFFICE)\s+[A-Za-z0-9\-]+)\b",
    re.IGNORECASE,
)
RE_HK_FLOOR_SLASH = re.compile(r"\b([BGL]?\d+)\s*\/\s*F\b", re.IGNORECASE)
RE_HK_LEVEL = re.compile(r"\b(?:LEVEL|LVL)\s*(\d+)\b", re.IGNORECASE)
RE_HK_FLAT_ONLY = re.compile(r"\b(FLAT|UNIT|RM|ROOM|SUITE|STE|OFC|OFFICE)\s*([A-Za-z0-9\-]+)\b", re.IGNORECASE)
RE_HK_FLOOR_ONLY = re.compile(r"\b(\d+)\s*(?:TH|ST|ND|RD)?\s*(?:FLOOR|FL|FLR)\b", re.IGNORECASE)


# Roads whose official name ends in a district word ("Queen's Road Central", "Des Voeux Road West"): there the district
# word is part of the street name. For any other road ("8 Finance Street Central") it is the locality.
_HK_DISTRICT_NAMED_ROADS = frozenset({"QUEENSROAD", "DESVOEUXROAD", "CONNAUGHTROAD"})


def _is_district_named_road(words_before_district: list) -> bool:
    name = "".join(re.sub(r"[^A-Z]", "", w.upper()) for w in words_before_district[-3:])
    return any(name.endswith(road) for road in _HK_DISTRICT_NAMED_ROADS)


class HongKongGrammar(CountryGrammar):
    """Hong Kong localized address grammar."""

    country_iso3: ClassVar[str] = "HKG"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "HKG",
        "HK",
        "HONG KONG",
        "HONG KONG SAR",
        "HONG KONG S.A.R.",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        """Hong Kong does not utilize domestic postal codes."""
        if not raw_code:
            return ""
        clean = raw_code.strip().upper()
        if clean in ("999077", "000000", "00000", "HK", "HKG"):
            return ""
        return ""

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise_name, street_number, street_name) from Hong Kong address line."""
        if not street_line:
            return None, None, None

        s_clean = " ".join(street_line.strip().split())
        s_upper = s_clean.upper()

        # Check known notable buildings
        for bldg in sorted(HK_NOTABLE_BUILDINGS, key=len, reverse=True):
            if s_upper.startswith(bldg):
                rem = s_clean[len(bldg):].strip(" ,.-")
                if rem:
                    # check for street number and street name in remainder
                    m_num_st = re.match(r"^(\d+[A-Za-z0-9\-]*)\s+(.+)$", rem)
                    if m_num_st:
                        return bldg, m_num_st.group(1), m_num_st.group(2)
                    return bldg, None, rem
                return bldg, None, None

        # Check for standard building keyword: Tower, House, Building, Chambers, Centre
        m_bldg = re.match(
            r"^(.*?\b(?:TOWER\s*\d*|HOUSE|BUILDING|CHAMBERS|CENTRE|CENTER|MANSION|PLAZA|COURT|COMMERCIAL\s+BUILDING)\b)(?:[,\s]+(.*))?$",
            s_clean,
            re.IGNORECASE,
        )
        if m_bldg:
            b_name = m_bldg.group(1).strip(" ,.-")
            rest = (m_bldg.group(2) or "").strip(" ,.-")
            if rest:
                m_num = re.match(r"^(\d+[A-Za-z0-9\-]*)\s+(.+)$", rest)
                if m_num:
                    return b_name, m_num.group(1), m_num.group(2)
                return b_name, None, rest
            return b_name, None, None

        # Check standard street number + street name: e.g. "8 FINANCE STREET"
        m_st = re.match(r"^(\d+[A-Za-z0-9\-]*)\s+(.+)$", s_clean)
        if m_st:
            return None, m_st.group(1), m_st.group(2)

        return None, None, s_clean

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        """Parse tokenized lines into structured Hong Kong components."""
        s1 = metadata.get("street1") or ""
        s2 = metadata.get("street2") or ""
        city_raw = metadata.get("city") or ""
        state_raw = metadata.get("state") or ""
        raw_full = metadata.get("raw_street_address") or ""

        combined = f"{s1} {s2}".strip()
        if raw_full and not combined:
            combined = raw_full

        # Extract secondary unit: Floor / Flat
        sec_unit_str = ""

        m_ff = RE_HK_FLAT_AND_FLOOR.search(combined)
        if m_ff:
            flat_part = m_ff.group(1).strip().upper()
            fl_part = m_ff.group(2).strip().upper()
            if "/" not in fl_part and fl_part.endswith("F"):
                fl_part = f"{fl_part[:-1]}/F"
            elif "FLOOR" in fl_part:
                num = re.sub(r"[^\d]", "", fl_part)
                fl_part = f"{num}/F" if num else fl_part
            sec_unit_str = f"{flat_part}, {fl_part}"
            combined = combined[:m_ff.start()] + " " + combined[m_ff.end():]
        else:
            m_rev = RE_HK_FLOOR_AND_FLAT.search(combined)
            if m_rev:
                fl_part = m_rev.group(1).strip().upper()
                flat_part = m_rev.group(2).strip().upper()
                if "/" not in fl_part and fl_part.endswith("F"):
                    fl_part = f"{fl_part[:-1]}/F"
                elif "FLOOR" in fl_part:
                    num = re.sub(r"[^\d]", "", fl_part)
                    fl_part = f"{num}/F" if num else fl_part
                sec_unit_str = f"{flat_part}, {fl_part}"
                combined = combined[:m_rev.start()] + " " + combined[m_rev.end():]

        if not sec_unit_str:
            m_slash = RE_HK_FLOOR_SLASH.search(combined)
            if m_slash:
                fl_num = m_slash.group(1).upper()
                sec_unit_str = f"{fl_num}/F"
                combined = combined[:m_slash.start()] + " " + combined[m_slash.end():]
            else:
                m_lvl = RE_HK_LEVEL.search(combined)
                if m_lvl:
                    sec_unit_str = f"{m_lvl.group(1)}/F"
                    combined = combined[:m_lvl.start()] + " " + combined[m_lvl.end():]
                else:
                    m_fl = RE_HK_FLOOR_ONLY.search(combined)
                    if m_fl:
                        sec_unit_str = f"{m_fl.group(1)}/F"
                        combined = combined[:m_fl.start()] + " " + combined[m_fl.end():]

        if not sec_unit_str and s2:
            # A non-empty street2 always comes back as a non-empty secondary unit.
            st1_rem, sec_unit_str = split_intl_secondary_unit(s1, s2)
            combined = st1_rem

        if not sec_unit_str:
            m_flat = RE_HK_FLAT_ONLY.search(combined)
            if m_flat:
                sec_unit_str = f"{m_flat.group(1).upper()} {m_flat.group(2).upper()}"
                combined = combined[:m_flat.start()] + " " + combined[m_flat.end():]

        combined = " ".join(combined.strip(" ,.-").split())
        combined = re.sub(r"(?:,\s*|\s+)\b(?:HONG\s+KONG|HKG|HK)\b$", "", combined, flags=re.IGNORECASE).strip(" ,.-")
        combined = re.sub(r"\b(?:999077|000000|00000)\b", "", combined).strip(" ,.-")

        # District and Region extraction
        dep_loc = None
        region_city = "HONG KONG"

        # Check districts in order of length descending. A district is only peeled off when it is clearly a separate
        # locality: comma-separated, or not directly after a road type ("Queen's Road Central", "Des Voeux Road West"
        # carry the district word in the street name itself).
        for dist in sorted(ALL_HK_DISTRICTS, key=len, reverse=True):
            chosen = None
            for m_d in re.finditer(rf"(,\s*|\s+|^)\b{re.escape(dist)}\b", combined, flags=re.IGNORECASE):
                lead = m_d.group(1)
                prev_words = combined[: m_d.start()].split()
                prev_word = re.sub(r"[^A-Z]", "", prev_words[-1].upper()) if prev_words else ""
                if "," not in lead and prev_word in _HK_ROAD_TYPE_WORDS and _is_district_named_road(prev_words):
                    continue
                chosen = m_d
            if chosen is None:
                continue
            dep_loc = dist
            if dist in HK_KOWLOON_DISTRICTS and dist != "KOWLOON":
                region_city = "KOWLOON"
            elif dist in HK_NT_DISTRICTS and dist not in ("NEW TERRITORIES", "NT"):
                region_city = "NEW TERRITORIES"
            combined = (combined[: chosen.start()] + combined[chosen.end():]).strip(" ,.-")
            break

        if not dep_loc and city_raw:
            c_up = city_raw.strip().upper()
            if c_up in ALL_HK_DISTRICTS:
                dep_loc = c_up
                if c_up in HK_KOWLOON_DISTRICTS:
                    region_city = "KOWLOON"
                elif c_up in HK_NT_DISTRICTS:
                    region_city = "NEW TERRITORIES"
            elif c_up in ("HONG KONG", "KOWLOON", "NEW TERRITORIES"):
                region_city = c_up

        if not dep_loc and state_raw:
            st_up = state_raw.strip().upper()
            if st_up in ALL_HK_DISTRICTS:
                dep_loc = st_up

        # Extract premise name, street number, street name
        b_name, st_num, st_name = self.extract_premise_and_thoroughfare(combined)

        unit_parts = sec_unit_str.split(None, 1) if sec_unit_str else []
        u_type = unit_parts[0] if len(unit_parts) > 1 else None
        u_num = unit_parts[1] if len(unit_parts) > 1 else (sec_unit_str or None)
        if u_type and u_type.upper() == "SUITE":
            u_type = "STE"

        final_city = dep_loc or region_city

        return HongKongParsedAddressComponents(
            street_number=st_num,
            street_name=st_name,
            street_type=None,
            unit_type=u_type,
            unit_number=u_num,
            building_name=b_name,
            dependent_locality=None,
            city=final_city,
            state="",
            postal_code="",
            country_iso3=self.country_iso3,
            raw_tokens=raw_tokens,
            confidence_score=0.95,
        )
