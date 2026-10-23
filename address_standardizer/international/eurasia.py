"""Eurasian Regional Address Grammar (TUR, GEO, ARM, AZE, KAZ, UZB, KGZ, TJK, TKM).

Provides specialized parsing and normalization for:
- Türkiye (TUR): Mahallesi (Mah.), Cadde (Cad.), Sokak (Sok./Sk.), Bulvarı (Blv.),
  No: / Daire: (D:) / Kat:, District/Province slash separation ("34710 Kadıköy/İstanbul").
- South Caucasus:
  - Georgia (GEO): ქუჩა (kucha), გამზირი (gamziri), 4-digit postal codes.
  - Armenia (ARM): փողոց (poghots), պողոտա (poghota), 4-digit postal codes.
  - Azerbaijan (AZE): küçəsi, prospekti, mənzil, 4-digit postal codes.
- Central Asia:
  - Kazakhstan (KAZ): көшесі, мкр. / шағын ауданы, alphanumeric postal codes (A05A1B2) and legacy 6-digit codes.
  - Uzbekistan (UZB), Kyrgyzstan (KGZ), Tajikistan (TJK), Turkmenistan (TKM):
    ko'chasi / көчөсү / кӯчаи, microdistricts, 6-digit postal codes.
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

# Turkish thoroughfare suffixes
TR_STREET_SUFFIXES: Dict[str, str] = {
    "MAHALLESI": "MAH.",
    "MAHALLE": "MAH.",
    "MAH": "MAH.",
    "MH": "MAH.",
    "CADDESI": "CAD.",
    "CADDE": "CAD.",
    "CAD": "CAD.",
    "CD": "CAD.",
    "SOKAGI": "SOK.",
    "SOKAĞI": "SOK.",
    "SOKAK": "SOK.",
    "SOK": "SOK.",
    "SK": "SOK.",
    "BULVARI": "BLV.",
    "BULVAR": "BLV.",
    "BLV": "BLV.",
}

# Turkish door / apartment / floor designator
RE_TR_UNIT = re.compile(
    r"\b(?:D(?:AIRE)?|K(?:AT)?|NO|NUMARA|KAPI|IC\s*KAPI|İÇ\s*KAPI)\s*[:.]?\s*([A-Za-z0-9\-\/]+)\b",
    re.IGNORECASE,
)

# Number-first pattern: e.g. "1368 Sokak 1 D: 605", "15 Rustaveli Avenue"
RE_EUR_NUM_FIRST = re.compile(
    r"^(\d+[A-Za-z0-9\-\/]*)\s+(.*)$",
)

# Turkish district/province slash syntax: e.g. "Kadıköy/İstanbul", "Çankaya / Ankara"
RE_TR_SLASH_LOC = re.compile(
    r"^(.*?)\s*\/\s*(.*)$",
)


class EurasiaGrammar(CountryGrammar):
    """Regional grammar family for Türkiye, South Caucasus, and Central Asian nations."""

    country_iso3: ClassVar[str] = "TUR"
    split_commaless_line: ClassVar[bool] = True
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "TUR", "TURKEY", "TURKIYE", "TÜRKIYE", "TÜRKİYE", "TR",
        "GEO", "GEORGIA", "GE",
        "ARM", "ARMENIA", "AM",
        "AZE", "AZERBAIJAN", "AZ",
        "KAZ", "KAZAKHSTAN", "KZ",
        "UZB", "UZBEKISTAN", "UZ",
        "KGZ", "KYRGYZSTAN", "KG",
        "TJK", "TAJIKISTAN", "TJ",
        "TKM", "TURKMENISTAN", "TM",
    )

    def _resolve_country_iso(self, country_cand: Optional[str]) -> str:
        if not country_cand:
            return "TUR"
        cand_str = country_cand.strip().upper()
        if cand_str in ("TUR", "TURKEY", "TURKIYE", "TÜRKIYE", "TÜRKİYE", "TR"):
            return "TUR"
        from address_standardizer.international.countries import CountryRegistry
        info = CountryRegistry.get(cand_str)
        if info and info.alpha3 in self.supported_countries:
            return info.alpha3
        return "TUR"

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Eurasian postal codes."""
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())
        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise, street_number, thoroughfare) from Eurasian street line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()
        m_num = re.search(r"\b(?:No\.?|No:|№)\s*(\d+[A-Za-z0-9\-\/]*)\b", line, re.IGNORECASE)
        if m_num:
            return None, m_num.group(1).strip(), line

        m_lead = RE_EUR_NUM_FIRST.match(line)
        if m_lead:
            return None, m_lead.group(1).strip(), line

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
                    parts[-1].upper() in self.supported_countries or parts[-1].upper() in COUNTRY_NAME_MAP
                ):
                    country_iso = cand_iso
                    parts = parts[:-1]

            if len(parts) >= 3:
                # Rightmost part is often "{City} {Postal}" or "{Postal} {City}"
                last_p = parts[-1]
                m_pc_end = re.search(r"\b(\d{4,6}|[A-Z]\d{2}[A-Z\d]{4})\b", last_p)
                if m_pc_end and not postal_raw:
                    postal_raw = m_pc_end.group(1)
                    clean_loc = (last_p[:m_pc_end.start()] + last_p[m_pc_end.end():]).strip()
                    parts[-1] = clean_loc

                city_raw = parts[-1]
                dep_locality = parts[-2]
                s1_raw = ", ".join(parts[:-2])
            elif len(parts) == 2:
                # Check for postal code in part 1
                m_pc = re.search(r"\b(\d{4,6}|[A-Z]\d{2}[A-Z\d]{4})\b", parts[1])
                if m_pc and not postal_raw:
                    postal_raw = m_pc.group(1)
                    city_raw = (parts[1][:m_pc.start()] + parts[1][m_pc.end():]).strip()
                else:
                    city_raw = parts[1]
                s1_raw = parts[0]
            elif len(parts) == 1:
                s1_raw = parts[0]

        # 2. Turkish District/Province slash splitting: "Kadıköy/İstanbul" -> dep_locality="Kadıköy", city="İstanbul"
        if city_raw and "/" in city_raw:
            slash_parts = [p.strip() for p in city_raw.split("/", 1)]
            if len(slash_parts) == 2 and slash_parts[0] and slash_parts[1]:
                dep_locality = slash_parts[0].upper()
                city_raw = slash_parts[1]

        # 3. Turkish door / apartment unit extraction from street1: "Bağdat Caddesi No: 154 Daire: 8"
        m_unit = re.search(r"\b((?:Daire|D|Kat|K|İç\s*Kapı|Ic\s*Kapi)\s*[:.]?\s*[A-Za-z0-9\-]+)\b", s1_raw, re.IGNORECASE)
        if m_unit:
            unit_str = m_unit.group(1).strip()
            s1_raw = (s1_raw[:m_unit.start()] + s1_raw[m_unit.end():]).strip()
            s2_raw = f"{unit_str} {s2_raw}".strip() if s2_raw else unit_str

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
            dependent_locality=dep_locality.upper() if dep_locality else None,
            building_name=building_name,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
