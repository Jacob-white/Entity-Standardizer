"""Middle East and Africa Address Grammar (ARE, SAU, EGY, ZAF, NGA, KEN).

Provides specialized parsing and normalization for:
- UAE (ARE): Non-postal nation graceful handling, PO Box delivery (P.O. Box 12345 / ص.ب 12345),
  emirate routing (Dubai, Abu Dhabi, Sharjah, etc.).
- Saudi Arabia (SAU): National Address system with 4-digit building numbers and
  additional numbers, District (Hayy / Al-Malaz), postal codes (11564).
- Egypt (EGY): Street number + street name, District (Maadi, Zamalek, Dokki),
  Governorates (Cairo, Giza, Alexandria), 5-digit postal codes.
- South Africa (ZAF): Street number + street, Suburb (Sandton, Rosebank),
  City (Johannesburg, Cape Town), 4-digit postal codes.
- Nigeria (NGA): Plot / Street number + street, Area/District (Victoria Island, Ikeja),
  City (Lagos, Abuja), 6-digit postal codes.
- Kenya (KEN): PO Box delivery (P.O. Box 30197-00100), Street (Waiyaki Way),
  Suburb (Westlands), City (Nairobi), 5-digit postal codes.
- Full Arabic script preservation in native fields (street1, city, state, dependent_locality).
"""

from __future__ import annotations

import re
from typing import ClassVar, List, Optional, Tuple

from address_standardizer._patterns import RE_COMMA_DOT
from address_standardizer.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.international.diacritics import (
    normalize_to_canonical_unicode,
)
from address_standardizer.tables import COUNTRY_NAME_MAP, GLOBAL_METRO_TO_COUNTRY

# PO Box patterns (English and Arabic)
RE_PO_BOX = re.compile(
    r"\b(?:P\.?\s*O\.?\s*BOX|POB|POST\s*OFFICE\s*BOX|ص\.?\s*ب\.?|صندوق\s*بريد)\s*([A-Za-z0-9\-]+)?\b",
    re.IGNORECASE,
)

# Secondary unit designator that makes up a whole comma part: "Office 5", "Suite 12", "Floor 3"
RE_UNIT_PART = re.compile(
    r"^(?:OFFICE|OFC|SUITE|STE|UNIT|FLOOR|FL|APT|APARTMENT|FLAT|ROOM|SHOP|LEVEL)\b\.?\s*[A-Za-z0-9\-]+$",
    re.IGNORECASE,
)

# Plot pattern (Nigeria / Africa)
RE_PLOT = re.compile(
    r"^\b(?:PLOT|PLT)\.?\s*([A-Za-z0-9\-\/]+)\b",
    re.IGNORECASE,
)

# UAE Emirates (English and Arabic)
UAE_EMIRATES = {
    "DUBAI": "DUBAI",
    "ABU DHABI": "ABU DHABI",
    "SHARJAH": "SHARJAH",
    "AJMAN": "AJMAN",
    "UMM AL QUWAIN": "UMM AL QUWAIN",
    "RAS AL KHAIMAH": "RAS AL KHAIMAH",
    "FUJAIRAH": "FUJAIRAH",
    "دبي": "دبي",
    "أبوظبي": "أبوظبي",
    "الشارقة": "الشارقة",
    "عجمان": "عجمان",
    "أم القيوين": "أم القيوين",
    "رأس الخيمة": "رأس الخيمة",
    "الفجيرة": "الفجيرة",
}

# Number-first street pattern: e.g. "7543 King Fahd Road", "100 Sandton Drive", "15 Tahrir Street"
RE_NUM_FIRST = re.compile(
    r"^(\d+[A-Za-z0-9\-\/]*(?:\s*-\s*\d+)?)\s+(.*)$"
)


# Arabic Country Names
ARABIC_COUNTRY_MAP = {
    "الإمارات العربية المتحدة": "ARE",
    "الإمارات": "ARE",
    "المملكة العربية السعودية": "SAU",
    "السعودية": "SAU",
    "مصر": "EGY",
    "جمهورية مصر العربية": "EGY",
    "جنوب أفريقيا": "ZAF",
    "نيجيريا": "NGA",
    "كينيا": "KEN",
}


def normalize_po_box_str(raw: str) -> str:
    """Normalize PO Box string to standard form."""
    m = RE_PO_BOX.search(raw)
    if not m:
        return raw.strip()
    box_num = (m.group(1) or "").strip()
    match_str = m.group(0)
    if "ص" in match_str or "بريد" in match_str:
        return f"ص.ب {box_num}".strip() if box_num else "ص.ب"
    return f"PO BOX {box_num}".strip() if box_num else "PO BOX"


class MenaAfricaGrammar(CountryGrammar):
    """Regional grammar family for Middle East & Africa jurisdictions."""

    country_iso3: ClassVar[str] = "ARE"
    split_commaless_line: ClassVar[bool] = True
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "ARE", "UNITED ARAB EMIRATES", "UAE",
        "SAU", "SAUDI ARABIA", "KSA",
        "EGY", "EGYPT", "MISR",
        "ZAF", "SOUTH AFRICA", "RSA",
        "NGA", "NIGERIA",
        "KEN", "KENYA",
        "MAR", "MOROCCO",
        "DZA", "ALGERIA",
        "TUN", "TUNISIA",
        "ISR", "ISRAEL",
        "JOR", "JORDAN",
        "LBN", "LEBANON",
        "QAT", "QATAR",
        "KWT", "KUWAIT",
        "OMN", "OMAN",
        "BHR", "BAHRAIN",
        "GHA", "GHANA",
        "ETH", "ETHIOPIA",
        "TZA", "TANZANIA",
        "UGA", "UGANDA",
        "AGO", "ANGOLA",
        "BDI", "BURUNDI",
        "BEN", "BENIN",
        "BFA", "BURKINA FASO",
        "BWA", "BOTSWANA",
        "CAF", "CENTRAL AFRICAN REPUBLIC",
        "CIV", "COTE D'IVOIRE", "CÔTE D'IVOIRE", "IVORY COAST",
        "CMR", "CAMEROON",
        "COD", "DEMOCRATIC REPUBLIC OF THE CONGO", "DR CONGO",
        "COG", "REPUBLIC OF THE CONGO", "CONGO",
        "COM", "COMOROS",
        "CPV", "CAPE VERDE", "CABO VERDE",
        "DJI", "DJIBOUTI",
        "ERI", "ERITREA",
        "GAB", "GABON",
        "GIN", "GUINEA",
        "GMB", "GAMBIA",
        "GNB", "GUINEA-BISSAU",
        "GNQ", "EQUATORIAL GUINEA",
        "IRQ", "IRAQ",
        "IRN", "IRAN",
        "LBR", "LIBERIA",
        "LBY", "LIBYA",
        "LSO", "LESOTHO",
        "MDG", "MADAGASCAR",
        "MLI", "MALI",
        "MOZ", "MOZAMBIQUE",
        "MRT", "MAURITANIA",
        "MUS", "MAURITIUS",
        "MWI", "MALAWI",
        "NAM", "NAMIBIA",
        "NER", "NIGER",
        "PSE", "PALESTINE", "STATE OF PALESTINE",
        "RWA", "RWANDA",
        "SDN", "SUDAN",
        "SEN", "SENEGAL",
        "SLE", "SIERRA LEONE",
        "SOM", "SOMALIA",
        "SSD", "SOUTH SUDAN",
        "STP", "SAO TOME AND PRINCIPE", "SÃO TOMÉ AND PRÍNCIPE",
        "SWZ", "ESWATINI", "SWAZILAND",
        "SYC", "SEYCHELLES",
        "SYR", "SYRIA",
        "TCD", "CHAD",
        "TGO", "TOGO",
        "YEM", "YEMEN",
        "ZMB", "ZAMBIA",
        "ZWE", "ZIMBABWE",
        "ESH", "WESTERN SAHARA",
        "BVT", "BOUVET ISLAND",
        "FJI", "FIJI",
        "PNG", "PAPUA NEW GUINEA",
        "WSM", "SAMOA",
        "TON", "TONGA",
        "VUT", "VANUATU",
        "SLB", "SOLOMON ISLANDS",
        "KIR", "KIRIBATI",
        "TUV", "TUVALU",
        "NRU", "NAURU",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Middle East / Africa postal code."""
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())

        # Saudi Arabia: 5 digits or 5+4 (XXXXX-XXXX)
        m_sau = re.match(r"^(\d{5})(?:-?(\d{4}))?$", clean)
        if m_sau and m_sau.group(2):
            return f"{m_sau.group(1)}-{m_sau.group(2)}"
        elif m_sau:
            return m_sau.group(1)

        # South Africa: 4 digits
        m_zaf = re.match(r"^(\d{4})$", clean)
        if m_zaf:
            return m_zaf.group(1)

        # Nigeria: 6 digits
        m_nga = re.match(r"^(\d{6})$", clean)
        if m_nga:
            return m_nga.group(1)

        # Egypt & Kenya 5-digit codes are already returned by the Saudi 5-digit branch above.
        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise, street_number, thoroughfare) from address line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()

        # Check PO Box
        m_box = RE_PO_BOX.search(line)
        if m_box:
            box_num = m_box.group(1) or ""
            return None, box_num, line.upper() if line.isascii() else line

        # Check Plot
        m_plt = RE_PLOT.match(line)
        if m_plt:
            plt_num = m_plt.group(1).strip()
            return None, plt_num, line.upper() if line.isascii() else line

        # Number-first: "7543 King Fahd Road", "100 Sandton Drive"
        # Collapse whitespace first: single spaces cannot trigger the regex's quadratic backtracking on long runs.
        m_num = RE_NUM_FIRST.match(" ".join(line.split()))
        if m_num:
            st_num = m_num.group(1).strip()
            thoroughfare = m_num.group(2).strip()
            full_line = f"{st_num} {thoroughfare}"
            return None, st_num, full_line.upper() if full_line.isascii() else full_line

        return None, None, line

    def _resolve_country_iso(self, country_cand: Optional[str]) -> str:
        if not country_cand:
            return "ARE"
        cand_str = country_cand.strip()
        if cand_str in ARABIC_COUNTRY_MAP:
            return ARABIC_COUNTRY_MAP[cand_str]
        c = cand_str.upper()
        if c in ("ARE", "UNITED ARAB EMIRATES", "UAE"):
            return "ARE"
        if c in ("SAU", "SAUDI ARABIA", "KSA"):
            return "SAU"
        if c in ("EGY", "EGYPT", "MISR"):
            return "EGY"
        if c in ("ZAF", "SOUTH AFRICA", "RSA"):
            return "ZAF"
        if c in ("NGA", "NIGERIA"):
            return "NGA"
        if c in ("KEN", "KENYA"):
            return "KEN"
        from address_standardizer.international.countries import CountryRegistry
        info = CountryRegistry.get(cand_str)
        if info and info.alpha3 in self.supported_countries:
            return info.alpha3
        return "ARE"

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        country_raw = metadata.get("country", self.country_iso3)
        country_iso = self._resolve_country_iso(country_raw)

        unit_type: Optional[str] = None
        unit_number: Optional[str] = None
        dep_locality: Optional[str] = None
        building_name: Optional[str] = None
        street_line = s1_raw

        # Handle comma-delimited single string when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts = [p.strip() for p in s1_raw.split(",") if p.strip()]
            # Strip trailing country if present (excluding UAE emirates/cities like Dubai)
            if (
                len(parts) >= 2
                and parts[-1].upper() not in UAE_EMIRATES
                and parts[-1].strip() not in UAE_EMIRATES
                and (
                    parts[-1].upper() in self.supported_countries
                    or parts[-1].upper() in COUNTRY_NAME_MAP
                    or parts[-1].strip() in ARABIC_COUNTRY_MAP
                )
            ):
                country_iso = self._resolve_country_iso(parts[-1])
                parts = parts[:-1]

            sec_parts: List[str] = []
            rem_parts: List[str] = []
            inline_box_seen = False
            for part in parts:
                m_box = RE_PO_BOX.search(part)
                if m_box:
                    sec_parts.append(normalize_po_box_str(part.strip()))
                    # "Sheikh Zayed Road PO Box 5": the thoroughfare before the box is kept, not discarded.
                    before_box = part[:m_box.start()].strip(" ,.-")
                    if before_box:
                        rem_parts.append(before_box)
                        inline_box_seen = True
                    continue

                # A unit designator following a street+box part ("..., Office 5") is secondary, not a city.
                if inline_box_seen and RE_UNIT_PART.match(part.strip()):
                    sec_parts.append(part.strip())
                    continue

                # Check if entire part is a standalone postal code
                if re.match(r"^\d{4,6}(?:-\d{4})?$", part.strip()):
                    postal_raw = part.strip()
                    continue

                rem_parts.append(part)

            if sec_parts:
                unit_number = ", ".join(sec_parts)

            if len(rem_parts) >= 3:
                # e.g. ["100 Sandton Drive", "Sandton", "Johannesburg 2196", "Gauteng"]
                # OR ["Sheikh Zayed Road", "Trade Centre 1", "Dubai"]
                # OR ["7543 King Fahd Road", "Al-Malaz", "Riyadh 11564-2341"]
                m_pc_last = re.match(r"^(.*?)\s+(\d{4,6}(?:-\d{4})?)$", rem_parts[-1])
                m_pc_prev = re.match(r"^(.*?)\s+(\d{4,6}(?:-\d{4})?)$", rem_parts[-2])
                if m_pc_last:
                    city_raw = m_pc_last.group(1).strip()
                    postal_raw = m_pc_last.group(2).strip()
                    dep_locality = rem_parts[-2].strip()
                    street_line = ", ".join(rem_parts[:-2])
                elif m_pc_prev:
                    state_raw = rem_parts[-1].strip()
                    city_raw = m_pc_prev.group(1).strip()
                    postal_raw = m_pc_prev.group(2).strip()
                    if len(rem_parts) >= 4:
                        dep_locality = rem_parts[-3].strip()
                        street_line = ", ".join(rem_parts[:-3])
                    else:
                        street_line = rem_parts[0]
                else:
                    city_raw = rem_parts[-1]
                    dep_locality = rem_parts[-2]
                    street_line = ", ".join(rem_parts[:-2])
            elif len(rem_parts) == 2:
                # e.g. ["Sheikh Zayed Road", "Dubai"] OR ["Waiyaki Way", "Nairobi 00100"]
                m_pc = re.match(r"^(.*?)\s+(\d{4,6}(?:-\d{4})?)$", rem_parts[1])
                if m_pc:
                    city_raw = m_pc.group(1).strip()
                    postal_raw = m_pc.group(2).strip()
                else:
                    city_raw = rem_parts[1]
                street_line = rem_parts[0]
            elif len(rem_parts) == 1:
                p0 = rem_parts[0].strip().upper()
                p0_raw = rem_parts[0].strip()
                if not city_raw and (p0 in GLOBAL_METRO_TO_COUNTRY or p0 in UAE_EMIRATES or p0_raw in UAE_EMIRATES):
                    city_raw = rem_parts[0]
                    street_line = ""
                else:
                    street_line = rem_parts[0]
            else:
                # Every part was consumed as a PO box / postal code: nothing is left for the street line.
                street_line = ""

            # In postal routing where an address consists of a PO Box without a thoroughfare street,
            # promote the PO Box to street_line rather than leaving street_line empty.
            if not street_line and sec_parts:
                street_line = sec_parts.pop(0)
                unit_number = ", ".join(sec_parts) if sec_parts else None

        # Handle secondary units in s2_raw or embedded in street_line
        if s2_raw and not unit_number:
            if RE_PO_BOX.search(s2_raw):
                unit_number = normalize_po_box_str(s2_raw)
            else:
                unit_number = s2_raw.strip()

        # Check inline PO Box in street_line
        m_box_inline = RE_PO_BOX.search(street_line)
        if m_box_inline:
            box_str = normalize_po_box_str(m_box_inline.group(0))
            rem_st = street_line[:m_box_inline.start()] + street_line[m_box_inline.end():]
            rem_st = rem_st.strip(" ,.-")
            if rem_st:
                # Keep the box alongside any caller-supplied unit rather than dropping it.
                if not unit_number:
                    unit_number = box_str
                elif box_str.upper() not in unit_number.upper():
                    unit_number = f"{box_str}, {unit_number}"
                street_line = rem_st
            else:
                street_line = box_str

        # If street_line is still empty and unit_number is a PO Box, promote to primary delivery line
        if not street_line and unit_number and (RE_PO_BOX.search(unit_number) or "PO BOX" in unit_number.upper()):
            street_line = unit_number
            unit_number = None

        # Check secondary unit in Latin street line (unless street_line is solely a PO Box)
        is_sole_po_box = bool(RE_PO_BOX.search(street_line)) and (
            street_line.upper().startswith("PO BOX")
            or street_line.upper().startswith("P.O. BOX")
            or street_line.startswith("ص.ب")
            or street_line.startswith("صندوق بريد")
        )
        if not is_sole_po_box:
            st1_base, st2_base = split_intl_secondary_unit(street_line, "")
            if st2_base and not unit_number:
                s2_p = st2_base.split(maxsplit=1)
                unit_type = s2_p[0]
                unit_number = s2_p[1] if len(s2_p) > 1 else None
                street_line = st1_base
            else:
                street_line = st1_base

        _, st_num, thoroughfare = self.extract_premise_and_thoroughfare(street_line)

        # For UAE, if no postal code, leave empty
        norm_postal = self.normalize_postal_code(postal_raw) if country_iso != "ARE" or postal_raw else ""
        norm_city = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", city_raw).strip())
        norm_state = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", state_raw).strip())
        norm_street = normalize_to_canonical_unicode(thoroughfare.strip()) if thoroughfare else None
        norm_dep_loc = normalize_to_canonical_unicode(dep_locality.strip()) if dep_locality else None

        # Uppercase Latin scripts while preserving authentic Arabic Unicode
        if norm_city and norm_city.isascii():
            norm_city = norm_city.upper()
        if norm_state and norm_state.isascii():
            norm_state = norm_state.upper()
        if norm_street and norm_street.isascii():
            norm_street = norm_street.upper()
        if norm_dep_loc and norm_dep_loc.isascii():
            norm_dep_loc = norm_dep_loc.upper()
        if unit_number and unit_number.isascii():
            unit_number = unit_number.upper()

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=norm_street,
            unit_type=unit_type,
            unit_number=unit_number,
            building_name=building_name,
            dependent_locality=norm_dep_loc,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
