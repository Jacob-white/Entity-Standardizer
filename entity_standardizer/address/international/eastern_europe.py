"""Eastern European and Cyrillic Address Grammar (POL, CZE, ROU, GRC, BGR, SRB, UKR).

Provides specialized parsing and normalization for:
- Poland (POL): Prefix road types (ul., al., pl.), house numbers with slashes (10/12),
  mieszkanie/lokal (m. 14, lok. 2), postal codes (00-950).
- Czechia (CZE): Prefix road types (ul., nám., tř.), descriptive/orientation numbers,
  postal codes (110 00).
- Romania (ROU): Strada, Bulevardul, Calea, secondary units (Bl., Sc., Ap.), postal codes (010011).
- Greece (GRC): Odos, Leoforos, Plateia, Greek alphabet and Romanized, postal codes (105 63).
- Bulgaria (BGR): Cyrillic and Romanized (ул., бул., пл.), postal codes (1000).
- Serbia (SRB): Cyrillic and Latin (ul., bul., trg, Knez Mihailova), postal codes (11000).
- Ukraine (UKR): Cyrillic and Romanized (вул., просп., кв., оф.), postal codes (01001).
"""

from __future__ import annotations

import re
from typing import ClassVar, List, Optional, Tuple

from entity_standardizer.address._patterns import RE_COMMA_DOT
from entity_standardizer.address.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from entity_standardizer.address.international.diacritics import (
    normalize_to_canonical_unicode,
)
from entity_standardizer.address.tables import COUNTRY_NAME_MAP, GLOBAL_METRO_TO_COUNTRY

# Secondary unit indicators (Polish, Czech, Romanian, Greek, Cyrillic, Baltic, Balkan)
RE_EE_SECONDARY = re.compile(
    r"\b(?:(?:m\.|m)\s*(?=\d)|lok\.|mieszkanie|lokal|ap\.|apt|apartament|byt|bl\.|bloc|sc\.|scara|et\.|etaj|кв\.|кв|квартира|ап\.|оф\.|офис|офіс|вх\.|вход|ет\.|етаж|krt\.|dz\.|stan|butas|διαμ\.|diam\.|orofos)\s*#?\s*([A-Za-z0-9\-]+)",
    re.IGNORECASE,
)

# House number addition at end of thoroughfare: e.g. "10/12", "5A", "1", "123/4", "45-47"
RE_EE_HOUSE_NUM = re.compile(
    r"^(.*?)\s+(\d+[A-Za-z0-9\-\/]*(?:\s+[A-Za-z]\b)?)$"
)

# Countries whose single-line addresses are written "[postcode] City, Street type-name, number" (city first, no marker).
_CITY_FIRST_COUNTRIES = frozenset({"RUS", "UKR", "BGR", "SRB", "HUN", "BLR", "MDA"})

# Cyrillic street-type words (lower case, trailing dot removed): full words and common abbreviations.
_CYR_STREET_TYPES = frozenset({
    "улица", "ул", "проспект", "просп", "пр-т", "пр-кт", "переулок", "пер", "бульвар", "бул", "б-р",
    "набережная", "наб", "шоссе", "ш", "площадь", "пл", "проезд", "пр-д", "тупик", "аллея", "линия", "тракт",
    "вулиця", "вул", "провулок", "пров", "площа", "набережна", "узвіз", "шосе", "майдан", "алея", "дорога",
})
# First words of two-word city names ("Нижний Новгород", "Кривий Ріг").
_CYR_CITY_FIRST_WORDS = frozenset({
    "нижний", "великий", "старый", "новый", "набережные", "верхняя", "нижняя", "кривий", "нова", "нове",
    "верхній", "нижній", "біла", "великі", "белая",
})
# A comma part that is only a house number with its additions: "9", "2а", "42/44", "1-А", "15 с2", "16-18 с1", "3/5 кГ".
_RE_STANDALONE_HOUSE = re.compile(
    r"^\d+(?:[/\-]\d+)*(?:[\s\-]?[^\W\d_]{1,2}\.?\d*)?(?:\s+[^\W\d_]{1,6}\.?\s?\d+)*$"
)
_RE_LEADING_POSTAL = re.compile(r"^(\d{5,6})[\s,]+(.+)$")
# A comma part that opens with a postal code and a (letter) city name: "15000 Praha 5", "4029 Debrecen", "110 00 Praha 1".
# Such a part is never a bare house number even though "Praha 5" resembles "15 с2".
_RE_POSTAL_THEN_NAME = re.compile(r"^(?:\d{2}-\d{3}|\d{3}\s?\d{2}|\d{4,6})\s+[^\W\d_]{3,}")
# Hungary writes "<postcode> City, Street type-name number[.]": a four-digit postcode opens the first part.
_RE_HU_POSTAL_FIRST = re.compile(r"^(\d{4})\s+([^\W\d_].*)$")

_HUN_STREET_TYPES = frozenset({
    "utca", "út", "ut", "tér", "ter", "körút", "korut", "fasor", "sor", "köz", "koz",
    "sétány", "setany", "rakpart", "dűlő", "dulo", "u", "krt",
})


def _type_word_index(words: List[str]) -> int:
    """Index of the first Cyrillic street-type word in ``words`` (case/dot-insensitive), else -1."""
    for idx, w in enumerate(words):
        if w.strip(".,;").lower() in _CYR_STREET_TYPES:
            return idx
    return -1


_RE_TRAILING_HOUSE = re.compile(r"(?:^|\s)\d{1,4}(?:\s?[^\W\d_])?(?:[/\-][A-Za-z0-9]+)?$")


def _is_street_like(part: str) -> bool:
    """True when a comma-delimited part has a street type word or a trailing house number (so it is no bare city)."""
    words = part.split()
    if _type_word_index(words) >= 0:
        return True
    if any(w.strip(".,;").lower() in _HUN_STREET_TYPES for w in words):
        return True
    return bool(_RE_TRAILING_HOUSE.search(part))


def split_cyrillic_locality(line: str) -> Tuple[str, str, str]:
    """Split ``"[postcode] City Street-with-type[, number]"`` into (postcode, city, street line).

    The city has no marker: it is the word(s) before the street. A street starts at a leading type word
    ("улица Ленина 5") or, for type-after streets ("Пречистенская набережная, 9"), one name word before the
    type. Returns ("", "", line) when no unambiguous split exists (a bare street such as
    "Пречистенская набережная, 9" keeps everything as the street).
    """
    work = line.strip()
    postal = ""
    m_pc = _RE_LEADING_POSTAL.match(work)
    if m_pc:
        postal, work = m_pc.group(1), m_pc.group(2).strip()
    words = work.split()
    t_idx = _type_word_index(words)
    if t_idx < 0:
        return postal, "", work
    # type word followed by the name ("улица Ленина 5") -> everything before it is the city;
    # type word closing the name ("Тверская улица, 5") -> the single name word before it stays with the street.
    remainder = " ".join(words[t_idx + 1:]).strip(" ,")
    name_follows = bool(remainder) and not _RE_STANDALONE_HOUSE.match(remainder)
    city_len = t_idx if name_follows else t_idx - 1
    if city_len < 1:
        return postal, "", work
    if words[0].strip(",").lower() in _CYR_CITY_FIRST_WORDS and city_len >= 2:
        city_len = min(city_len, 2)
    else:
        city_len = 1
    city = " ".join(words[:city_len]).strip(" ,")
    street = " ".join(words[city_len:]).strip()
    return postal, city, street


class EasternEuropeGrammar(CountryGrammar):
    """Regional grammar family for Eastern Europe & Cyrillic jurisdictions."""

    country_iso3: ClassVar[str] = "POL"
    split_commaless_line: ClassVar[bool] = True
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "POL", "POLAND", "POLSKA", "PL",
        "HUN", "HUNGARY", "MAGYARORSZAG", "MAGYARORSZÁG", "HU",
        "CZE", "CZECH REPUBLIC", "CZECHIA", "CESKA REPUBLIKA", "ČESKÁ REPUBLIKA", "CZ",
        "ROU", "ROMANIA", "ROMÂNIA", "RO",
        "GRC", "GREECE", "HELLAS", "ELLADA", "ΕΛΛΑΔΑ", "ΕΛΛΆΔΑ", "ΕΛΛΑΣ", "ΕΛΛΆΣ", "GR",
        "BGR", "BULGARIA", "BALGARIYA", "БЪЛГАРИЯ", "BG",
        "SRB", "SERBIA", "SRBIJA", "СРБИЈА", "RS",
        "UKR", "UKRAINE", "UKRAYINA", "УКРАЇНА", "УКРАИНА", "UA",
        "RUS", "RUSSIA", "RUSSIAN FEDERATION", "ROSSIYA", "РОССИЯ", "РОССИЙСКАЯ ФЕДЕРАЦИЯ", "RU",
        "SVK", "SLOVAKIA", "SLOVENSKO",
        "SVN", "SLOVENIA", "SLOVENIJA",
        "HRV", "CROATIA", "HRVATSKA",
        "BIH", "BOSNIA AND HERZEGOVINA", "BOSNIA",
        "MNE", "MONTENEGRO", "CRNA GORA",
        "MKD", "NORTH MACEDONIA", "MACEDONIA",
        "ALB", "ALBANIA", "SHQIPERIA",
        "EST", "ESTONIA", "EESTI",
        "LVA", "LATVIA", "LATVIJA",
        "LTU", "LITHUANIA", "LIETUVA",
        "BLR", "BELARUS", "BELARUS'",
        "MDA", "MOLDOVA",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Eastern European postal code."""
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())
        # Strip European ISO prefix if present (e.g. "PL-00-950", "CZ-110 00", "GR-105 63")
        m_pfx = re.match(r"^(?:PL|CZ|RO|GR|BG|RS|UA|RU)-?(.*)$", clean)
        if m_pfx:
            clean = m_pfx.group(1).strip()

        # Poland with explicit hyphen: XX-XXX
        m_pl = re.match(r"^(\d{2})-(\d{3})$", clean)
        if m_pl:
            return f"{m_pl.group(1)}-{m_pl.group(2)}"

        # Czechia & Greece: XXX XX (with space)
        m_sp = re.match(r"^(\d{3})\s+(\d{2})$", clean)
        if m_sp:
            return f"{m_sp.group(1)} {m_sp.group(2)}"

        # Romania: XXXXXX (6 digits)
        m_ro = re.match(r"^(\d{6})$", clean)
        if m_ro:
            return m_ro.group(1)

        # Bulgaria: XXXX (4 digits)
        m_bg = re.match(r"^(\d{4})$", clean)
        if m_bg:
            return m_bg.group(1)

        # Serbia & Ukraine / unhyphenated 5 digits: XXXXX
        m_5d = re.match(r"^(\d{5})$", clean)
        if m_5d:
            return m_5d.group(1)

        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise, street_number, thoroughfare) from Eastern European street line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()
        m = RE_EE_HOUSE_NUM.match(line)
        if m:
            st_num = m.group(2).strip()
            return None, st_num, line

        # Check leading house number: e.g. "91, M. Alexandrou Str." or "91 M. Alexandrou"
        m_lead = re.match(r"^(\d+[A-Za-z0-9\-\/]*)[,\s]+([A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF].*)$", line)
        if m_lead:
            st_num = m_lead.group(1).strip()
            thoroughfare = m_lead.group(2).strip()
            return None, st_num, thoroughfare

        if re.match(r"^\d+[A-Za-z]?$", line):
            return None, None, None

        return None, None, line

    def _resolve_country_iso(self, country_cand: Optional[str]) -> str:
        if not country_cand:
            return "POL"
        c = country_cand.strip().upper()
        if c in ("POL", "POLAND", "POLSKA", "PL"):
            return "POL"
        if c in ("HUN", "HUNGARY", "MAGYARORSZAG", "MAGYARORSZÁG", "HU"):
            return "HUN"
        if c in ("CZE", "CZECH REPUBLIC", "CZECHIA", "CESKA REPUBLIKA", "ČESKÁ REPUBLIKA", "CZ"):
            return "CZE"
        if c in ("ROU", "ROMANIA", "ROMÂNIA", "RO"):
            return "ROU"
        if c in ("GRC", "GREECE", "HELLAS", "ELLADA", "ΕΛΛΑΔΑ", "ΕΛΛΆΔΑ", "ΕΛΛΑΣ", "ΕΛΛΆΣ", "GR"):
            return "GRC"
        if c in ("BGR", "BULGARIA", "BALGARIYA", "БЪЛГАРИЯ", "BG"):
            return "BGR"
        if c in ("SRB", "SERBIA", "SRBIJA", "СРБИЈА", "RS"):
            return "SRB"
        if c in ("UKR", "UKRAINE", "UKRAYINA", "УКРАЇНА", "УКРАИНА", "UA"):
            return "UKR"
        if c in ("RUS", "RUSSIA", "RUSSIAN FEDERATION", "ROSSIYA", "РОССИЯ", "РОССИЙСКАЯ ФЕДЕРАЦИЯ", "RU"):
            return "RUS"
        from entity_standardizer.address.international.countries import CountryRegistry
        info = CountryRegistry.get(c)
        if info and info.alpha3 in self.supported_countries:
            return info.alpha3
        return "POL"

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
        street_line = s1_raw

        # Handle comma-delimited single string when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts = [p.strip() for p in s1_raw.split(",") if p.strip()]
            # Strip trailing country if present
            if len(parts) >= 2 and (
                parts[-1].upper() in self.supported_countries
                or parts[-1].upper() in COUNTRY_NAME_MAP
            ):
                country_iso = self._resolve_country_iso(parts[-1])
                parts = parts[:-1]

            sec_units: List[str] = []
            rem_parts: List[str] = []
            for part in parts:
                m_sec = RE_EE_SECONDARY.search(part)
                if m_sec:
                    if m_sec.start() > 0:
                        street_p = part[:m_sec.start()].strip(" ,.-")
                        sec_p = part[m_sec.start():].strip(" ,.-")  # never empty: it starts at the keyword match
                        if street_p:
                            rem_parts.append(street_p)
                        sec_units.append(sec_p)
                    else:
                        sec_units.append(part.strip())
                    continue

                # Check if entire part is a standalone postal code
                if re.match(r"^(?:[A-Z]{2}-)?(?:\d{2}-\d{3}|\d{3}\s+\d{2}|\d{4,6})$", part.strip(), re.IGNORECASE):
                    postal_raw = part.strip()
                    continue

                rem_parts.append(part)

            if sec_units:
                unit_number = " ".join(sec_units)

            # A trailing bare house number belongs to the street part before it ("Street, 12" is not a city).
            if (
                len(rem_parts) >= 2
                and _RE_STANDALONE_HOUSE.match(rem_parts[-1])
                and not _RE_POSTAL_THEN_NAME.match(rem_parts[-1])
            ):
                house_part = rem_parts.pop()
                rem_parts[-1] = f"{rem_parts[-1]}, {house_part}"

            m_hu = _RE_HU_POSTAL_FIRST.match(rem_parts[0]) if country_iso == "HUN" and len(rem_parts) >= 2 else None
            if m_hu:
                # "1054 Budapest, Zoltán utca 16": postcode, city, then the street (type word after the name).
                postal_raw = m_hu.group(1)
                city_raw = m_hu.group(2)
                street_line = ", ".join(rem_parts[1:]).rstrip(".")
            elif (
                len(rem_parts) >= 2
                and country_iso in _CITY_FIRST_COUNTRIES
                and not _is_street_like(rem_parts[0])
                and any(_is_street_like(p) for p in rem_parts[1:])
            ):
                # "Москва, Пречистенская набережная, 9": the unmarked first part is the city.
                city_raw = rem_parts[0]
                street_line = ", ".join(rem_parts[1:])
            elif len(rem_parts) >= 2:
                # Check for "<Postal Code> <City>" OR "<City> <Postal Code>" in last part
                # e.g. "00-026 Warszawa", "110 00 Praha", "010011 București", "105 63 Αθήνα", "1000 София", "01001 Київ"
                # OR "София 1000", "Αθήνα 105 63", "Београд 11000"
                m_pc_city = re.match(
                    r"^(?:[A-Z]{2}-)?(\d{2}-\d{3}|\d{3}\s+\d{2}|\d{4,6})\s+(.*)$",
                    rem_parts[-1],
                    re.IGNORECASE,
                )
                m_city_pc = re.match(
                    r"^(.*?)\s+((?:[A-Z]{2}-)?(?:\d{2}-\d{3}|\d{3}\s+\d{2}|\d{4,6}))$",
                    rem_parts[-1],
                    re.IGNORECASE,
                )
                if m_pc_city:
                    postal_raw = m_pc_city.group(1)
                    city_raw = m_pc_city.group(2)
                    street_line = ", ".join(rem_parts[:-1])
                elif m_city_pc:
                    city_raw = m_city_pc.group(1)
                    postal_raw = m_city_pc.group(2)
                    street_line = ", ".join(rem_parts[:-1])
                else:
                    city_raw = rem_parts[-1]
                    street_line = ", ".join(rem_parts[:-1])
            elif len(rem_parts) == 1:
                p0 = rem_parts[0].strip().upper()
                if not city_raw and p0 in GLOBAL_METRO_TO_COUNTRY:
                    city_raw = rem_parts[0]
                    street_line = ""
                else:
                    street_line = rem_parts[0]

        # "[postcode] City Street type-name[, number]" without commas around the city (Russia, Ukraine, ...).
        if not city_raw and country_iso in _CITY_FIRST_COUNTRIES and street_line:
            loc_postal, loc_city, loc_street = split_cyrillic_locality(street_line)
            if loc_postal or loc_city:
                if loc_postal and not postal_raw:
                    postal_raw = loc_postal
                city_raw = loc_city
                street_line = loc_street

        # Handle secondary units in s2_raw or embedded in street_line
        if s2_raw and not unit_number:
            unit_number = s2_raw.strip()

        # Check inline secondary unit in street_line
        m_sec_inline = RE_EE_SECONDARY.search(street_line)
        if m_sec_inline:
            inline_unit = street_line[m_sec_inline.start():].strip(" ,.-")
            street_line = street_line[:m_sec_inline.start()].strip(" ,.-")
            if not unit_number:
                unit_number = inline_unit
            elif inline_unit.upper() not in unit_number.upper():  # (comma parsing may already have taken it)
                unit_number = f"{inline_unit} {unit_number}"

        # Extract secondary unit via split_intl_secondary_unit (kept alongside any street2 unit)
        st1_base, st2_base = split_intl_secondary_unit(street_line, "", native_types=True)
        if st2_base and not unit_number:
            s2_p = st2_base.split(maxsplit=1)
            unit_type = s2_p[0]
            unit_number = s2_p[1] if len(s2_p) > 1 else None
        elif st2_base:
            unit_number = f"{st2_base} {unit_number}"
        street_line = st1_base

        # Ensure Polish postal code \b\d{2}-\d{3}\b is isolated and extracted
        if not postal_raw or country_iso == "POL":
            if not postal_raw:
                m_pl_post = re.search(r"\b(\d{2}-\d{3})\b", s1_raw)
                if m_pl_post:
                    postal_raw = m_pl_post.group(1)
            if city_raw:
                m_c_post = re.search(r"\b(\d{2}-\d{3})\b", city_raw)
                if m_c_post:
                    if not postal_raw:
                        postal_raw = m_c_post.group(1)
                    city_raw = re.sub(r"\b\d{2}-\d{3}\b", "", city_raw).strip(" ,.-")
            if street_line:
                m_s_post = re.search(r"\b(\d{2}-\d{3})\b", street_line)
                if m_s_post:  # (postal_raw is already set from s1_raw above, which this line was derived from)
                    street_line = re.sub(r"\b\d{2}-\d{3}\b", "", street_line).strip(" ,.-")

        _, st_num, thoroughfare = self.extract_premise_and_thoroughfare(street_line)

        norm_postal = self.normalize_postal_code(postal_raw)
        if country_iso == "POL" and re.match(r"^\d{5}$", norm_postal):
            norm_postal = f"{norm_postal[:2]}-{norm_postal[2:]}"
        elif country_iso in ("CZE", "GRC") and re.match(r"^\d{5}$", norm_postal):
            norm_postal = f"{norm_postal[:3]} {norm_postal[3:]}"
        norm_city = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", city_raw).strip())
        norm_state = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", state_raw).strip())
        norm_street = normalize_to_canonical_unicode(thoroughfare.strip()) if thoroughfare else None

        # Uppercase Latin scripts while preserving authentic Cyrillic and Greek Unicode casing
        if norm_city:
            norm_city = norm_city.upper()
        if norm_state:
            norm_state = norm_state.upper()
        if norm_street:
            norm_street = norm_street.upper()
        if unit_number:
            unit_number = unit_number.upper()

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=norm_street,
            unit_type=unit_type,
            unit_number=unit_number,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
