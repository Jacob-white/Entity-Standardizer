"""Southeast Asia Regional Address Grammar (IDN, MYS, PHL, THA, VNM, KHM, LAO, MMR, BRN, TLS).

Provides specialized parsing and normalization for:
- Indonesia (IDN): Jalan/Gang, Kavling/Blok, RT/RW notation, Kelurahan/Kecamatan sub-localities,
  number-last thoroughfares ("Jalan Gajah Mada No. 19 - 26").
- Malaysia (MYS): Jalan/Lorong, Taman/Seksyen, 5-digit postcode state inference (KUL, SGR, JHR, etc.).
- Philippines (PHL): Block and Lot (B42 L7), Barangay/Brgy., Purok, Sitio, Metro Manila cities.
- Thailand (THA): House/Village numbers (217/27 Moo 9), Soi, Thanon, Tambon/Amphoe.
- Vietnam (VNM): Số, Hẻm/Ngõ, Đường, Phường/Quận, Thành phố.
- Singapore retains its specialized SingaporeGrammar; Brunei, Cambodia, Laos, Myanmar, and Timor-Leste
  are handled via shared regional Southeast Asian conventions.
"""

from __future__ import annotations

import re
from typing import ClassVar, Dict, List, Optional, Tuple

from address_standardizer._patterns import (
    RE_COMMA_DOT,
    RE_WHITESPACE,
)
from address_standardizer.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.tables import COUNTRY_NAME_MAP

# Malaysian postal prefix (first 2 digits) to state abbreviation
MY_POSTAL_STATE_PREFIXES: Dict[str, str] = {
    "01": "PLS", "02": "KDH", "05": "KDH", "06": "KDH", "07": "KDH", "08": "KDH", "09": "KDH",
    "10": "PNG", "11": "PNG", "12": "PNG", "13": "PNG", "14": "PNG",
    "15": "KTN", "16": "KTN", "17": "KTN", "18": "KTN",
    "20": "TRG", "21": "TRG", "22": "TRG", "23": "TRG", "24": "TRG",
    "25": "PHG", "26": "PHG", "27": "PHG", "28": "PHG",
    "30": "PRK", "31": "PRK", "32": "PRK", "33": "PRK", "34": "PRK", "35": "PRK", "36": "PRK", "39": "PRK",
    "40": "SGR", "41": "SGR", "42": "SGR", "43": "SGR", "44": "SGR", "45": "SGR", "46": "SGR", "47": "SGR", "48": "SGR",
    "50": "KUL", "51": "KUL", "52": "KUL", "53": "KUL", "54": "KUL", "55": "KUL", "56": "KUL", "57": "KUL", "58": "KUL", "59": "KUL", "60": "KUL",
    "62": "PJY", "63": "SGR", "64": "SGR", "68": "SGR",
    "70": "NSN", "71": "NSN", "72": "NSN", "73": "NSN",
    "75": "MLK", "76": "MLK", "77": "MLK", "78": "MLK",
    "80": "JHR", "81": "JHR", "82": "JHR", "83": "JHR", "84": "JHR", "85": "JHR", "86": "JHR",
    "87": "LBN",
    "88": "SBH", "89": "SBH", "90": "SBH", "91": "SBH",
    "93": "SWK", "94": "SWK", "95": "SWK", "96": "SWK", "97": "SWK", "98": "SWK",
}

# Number-first street pattern: e.g. "12 Jalan Ampang", "217/27 Moo 9 Beach Rd.", "B42L7 Lucas Road"
RE_SE_NUM_FIRST = re.compile(
    r"^((?:B\d+L\d+|BLK\s*\d+\s*LOT\s*\d+|\d+[A-Za-z0-9\-\/]*(?:\s*-\s*\d+)?))\s+(.*)$",
    re.IGNORECASE,
)

# Number-last street pattern: e.g. "Jalan Gajah Mada No. 19 - 26", "Jl. Sunda 9", "Đường Cách Mạng Tháng Tám 306B"
RE_SE_NUM_LAST = re.compile(
    r"^(.*?)(?:\s+(?:NO\.?|NOMOR|SO|SỐ)?\s*(\d+[A-Za-z0-9\-\/]*(?:\s*-\s*\d+)?))\s*$",
    re.IGNORECASE,
)

# Secondary unit indicators (Indonesian/Malaysian/English)
RE_SE_UNIT = re.compile(
    r"\b(?:UNIT|APT|SUITE|STE|FL|FLOOR|TINGKAT|TKT|LANTAI|LT|BLOK|BLK|RT|RW)\b\.?\s*([A-Za-z0-9\-\/]+)",
    re.IGNORECASE,
)


class SoutheastAsiaGrammar(CountryGrammar):
    """Regional grammar family for Southeast Asian nations."""

    country_iso3: ClassVar[str] = "IDN"
    split_commaless_line: ClassVar[bool] = True
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "IDN", "INDONESIA", "ID",
        "MYS", "MALAYSIA", "MY",
        "PHL", "PHILIPPINES", "PH",
        "THA", "THAILAND", "TH",
        "VNM", "VIETNAM", "VN",
        "KHM", "CAMBODIA", "KH",
        "LAO", "LAOS", "LA",
        "MMR", "MYANMAR", "MM",
        "BRN", "BRUNEI", "BN",
        "TLS", "TIMOR-LESTE", "TL",
    )

    def _resolve_country_iso(self, country_cand: Optional[str]) -> str:
        if not country_cand:
            return "IDN"
        cand_str = country_cand.strip().upper()
        if cand_str in ("IDN", "INDONESIA", "ID"):
            return "IDN"
        from address_standardizer.international.countries import CountryRegistry
        info = CountryRegistry.get(cand_str)
        if info and info.alpha3 in self.supported_countries:
            return info.alpha3
        return "IDN"

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Southeast Asian postal codes."""
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())
        m = re.match(r"^(\d{4,6})$", clean)
        return m.group(1) if m else clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise, street_number, thoroughfare) from Southeast Asian street line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()
        # Number-first: "12 Jalan Ampang", "B42L7 Lucas Road", "217/27 Moo 9 Beach Rd."
        m_first = RE_SE_NUM_FIRST.match(line)
        if m_first:
            return None, m_first.group(1).strip(), line

        # Number-last: "Jalan Gajah Mada No. 19 - 26", "Jl. Sunda 9"
        m_last = RE_SE_NUM_LAST.match(line)
        if m_last:
            st_num = m_last.group(2).strip()
            return None, st_num, line

        return None, None, line

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        country_iso = self._resolve_country_iso(metadata.get("country", self.country_iso3))

        norm_s1 = ""
        norm_s2 = ""
        dep_locality: Optional[str] = None
        building_name: Optional[str] = None

        # 1. Comma-separated parsing when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts = [p.strip() for p in s1_raw.split(",") if p.strip()]
            if len(parts) >= 2:
                cand_iso = self._resolve_country_iso(parts[-1])
                if cand_iso in self.supported_countries and (
                    parts[-1].upper() in self.supported_countries
                    or parts[-1].upper() in COUNTRY_NAME_MAP
                ):
                    country_iso = cand_iso
                    parts = parts[:-1]

            if len(parts) >= 3:
                # Rightmost part is often "{City} {Postal}" or "{State} {Postal}"
                last_p = parts[-1]
                m_pc = re.search(r"\b(\d{4,6})\b", last_p)
                if m_pc and not postal_raw:
                    postal_raw = m_pc.group(1)
                    clean_loc = (last_p[:m_pc.start()] + last_p[m_pc.end():]).strip()
                    parts[-1] = clean_loc

                city_raw = parts[-1]
                # Check if second-to-last part is a sub-district / dependent locality
                if len(parts) >= 4:
                    dep_locality = ", ".join(parts[1:-1]).upper()
                    s1_raw = parts[0]
                else:
                    # e.g. ["Jalan KH Wahid Hasyim No. 189", "Tanah Abang", "Central Jakarta"]
                    dep_locality = parts[1].upper()
                    s1_raw = parts[0]
            elif len(parts) == 2:
                # e.g. ["7431 Yakal Street", "Makati 1203"]
                m_pc = re.search(r"\b(\d{4,6})\b", parts[1])
                if m_pc and not postal_raw:
                    postal_raw = m_pc.group(1)
                    city_raw = (parts[1][:m_pc.start()] + parts[1][m_pc.end():]).strip()
                else:
                    city_raw = parts[1]
                s1_raw = parts[0]
            elif len(parts) == 1:
                s1_raw = parts[0]

        # 2. Extract dependent locality from s1_raw if city_raw is already known
        elif city_raw and s1_raw and "," in s1_raw:
            s1_parts = [p.strip() for p in s1_raw.split(",") if p.strip()]
            if len(s1_parts) >= 2 and any(ch.isdigit() for ch in s1_parts[0]) and not any(
                ch.isdigit() for ch in ",".join(s1_parts[1:])
            ):
                dep_locality = ", ".join(s1_parts[1:]).upper()
                s1_raw = s1_parts[0]

        # 3. Malaysian state inference from 2-digit postal prefix
        if country_iso in ("MYS", "MY", "MALAYSIA") and postal_raw and not state_raw:
            pfx = postal_raw[:2]
            if pfx in MY_POSTAL_STATE_PREFIXES:
                state_raw = MY_POSTAL_STATE_PREFIXES[pfx]

        # 4. Standardize street and secondary unit
        s1_clean = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", s1_raw).strip().upper())
        s2_clean = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", s2_raw).strip().upper())
        norm_s1_base, norm_s2_base = split_intl_secondary_unit(s1_clean, s2_clean)
        norm_s1 = norm_s1_base
        norm_s2 = norm_s2_base

        norm_city = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
        norm_state = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", state_raw).strip().upper())
        norm_postal = self.normalize_postal_code(postal_raw)

        unit_t = None
        unit_n = None
        if norm_s2:
            s2_parts = norm_s2.split(maxsplit=1)
            unit_t = s2_parts[0]
            unit_n = s2_parts[1] if len(s2_parts) > 1 else None

        return ParsedAddressComponents(
            street_name=norm_s1 if norm_s1 else None,
            unit_type=unit_t,
            unit_number=unit_n,
            dependent_locality=dep_locality,
            building_name=building_name,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
