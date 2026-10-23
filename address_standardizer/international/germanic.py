"""Germanic and Nordic Address Grammar (DEU, AUT, CHE, NLD, DNK, SWE, NOR)."""

import re
from typing import ClassVar, List, Optional, Tuple

from address_standardizer._patterns import RE_COMMA_DOT
from address_standardizer.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.international.diacritics import normalize_to_canonical_unicode

# Dutch 4-digit + 2-letter postal code
RE_NLD_POSTCODE = re.compile(r"^([1-9]\d{3})\s*([A-Z]{2})$", re.IGNORECASE)
DISALLOWED_NLD_COMBOS = {"SA", "SD", "SS"}

# General 4 to 5 digit European postal codes
RE_EURO_POSTCODE = re.compile(r"^(\d{4,5})$")

# Inverted Germanic street number: Thoroughfare followed by number and optional addition
# e.g. "Musterstraße 12", "Am Hauptbahnhof 5a", "Friedrichstraße 43-45", "Keizersgracht 421-B", "Mannerheimintie 12 B"
RE_INVERTED_STREET_NUMBER = re.compile(
    r"^(.*?)\s+(\d+[A-Za-z0-9\-\/]*(?:\s+[A-Za-z]\b)?)(?:[\s,]+(?:Apt|Suite|Unit|Fl|Wohnung|Wg)\.?\s*([A-Za-z0-9\-]+))?$",
    re.IGNORECASE,
)

# Nordic floor and door indicators (e.g. "2. tv.", "st. th.", "1. mf.")
RE_NORDIC_TAIL = re.compile(r"^(?:\d+\.|st\.)\s*(?:tv|th|mf)\.?$", re.IGNORECASE)
RE_NORDIC_FLOOR_DOOR = re.compile(
    r"[, ]+(\d+\.|\bst\.)\s*(tv|th|mf)\.?",
    re.IGNORECASE,
)

# Compound suffix patterns to protect
COMPOUND_SUFFIXES = (
    "straße",
    "strasse",
    "gasse",
    "weg",
    "platz",
    "allee",
    "damm",
    "ring",
    "chaussee",
    "ufer",
    "markt",
    "steig",
    "zeile",
    "tor",
    "brücke",
    "gatan",
    "vägen",
    "gade",
    "vei",
    "katu",
    "tie",
    "kuja",
    "väylä",
    "polku",
    "kaari",
    "ranta",
    "aukio",
)


_GERMAN_COUNTRIES = frozenset({"DEU", "AUT", "CHE", "LIE"})
# "Hauptstr." / "Hauptstr" / "Str." -> STRASSE ; "Marktpl." / "Pl." -> PLATZ (dotted forms only for Platz, which is
# otherwise ambiguous). Already spelled-out "Straße"/"Strasse" is left to the caller's upper-casing.
_RE_DE_STR = re.compile(r"(?<=[A-Za-zÄÖÜäöüß])[Ss]tr\.?(?=[\s,]|$)|(?<![\w])[Ss]tr\.(?=[\s,]|$)")
_RE_DE_PL = re.compile(r"(?<=[A-Za-zÄÖÜäöüß])[Pp]l\.(?=[\s,]|$)|(?<![\w])[Pp]l\.(?=[\s,]|$)")


def expand_german_street_abbreviations(street_line: str) -> str:
    """Expand German `Str.`/`str` to STRASSE and `Pl.` to PLATZ ("Hauptstr. 5" -> "Haupt" + "STRASSE" + " 5")."""
    if not street_line:
        return street_line
    out = _RE_DE_STR.sub("STRASSE", street_line)
    return _RE_DE_PL.sub("PLATZ", out)


_RE_NL_LN = re.compile(r"(?<=[A-Za-zÄÖÜäöüËëÏï])[Ll]n\.(?=[\s,]|$)|(?<![\w])[Ll]n\.(?=[\s,]|$)", re.IGNORECASE)
_RE_NL_STR = re.compile(r"(?<=[A-Za-zÄÖÜäöüËëÏï])[Ss]tr\.(?=[\s,]|$)|(?<![\w])[Ss]tr\.(?=[\s,]|$)", re.IGNORECASE)


def expand_dutch_street_abbreviations(street_line: str) -> str:
    """Expand Dutch `Ln.`/`ln.` to LAAN and `Str.`/`str.` to STRAAT."""
    if not street_line:
        return street_line
    out = _RE_NL_LN.sub("LAAN", street_line)
    return _RE_NL_STR.sub("STRAAT", out)


def is_valid_dutch_postcode(raw_code: str) -> bool:
    """Validate Netherlands postal code (4 digits + 2 letters, excluding SA/SD/SS)."""
    if not raw_code:
        return False
    clean = " ".join(raw_code.strip().upper().split())
    m = RE_NLD_POSTCODE.match(clean)
    if not m:
        return False
    letters = m.group(2).upper()
    return letters not in DISALLOWED_NLD_COMBOS


_RE_DE_POSTFACH_UNIT = re.compile(r"^(?:POSTFACH|POSTBOX|PF)\s+(\d+)(?:\s*[,;]\s*|\s+)([A-Za-zÄÖÜäöü][^\d].*|[A-Za-zÄÖÜäöü]+\s+\d.*)$", re.IGNORECASE)


class GermanicGrammar(CountryGrammar):
    """Germanic and Nordic address grammar with inverted house number ordering."""

    split_commaless_line: ClassVar[bool] = True

    country_iso3: ClassVar[str] = "DEU"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "DEU", "GERMANY", "DEUTSCHLAND",
        "AUT", "AUSTRIA", "OESTERREICH",
        "CHE", "SWITZERLAND", "SCHWEIZ", "SUISSE", "SVIZZERA",
        "NLD", "NETHERLANDS", "HOLLAND",
        "DNK", "DENMARK",
        "SWE", "SWEDEN",
        "NOR", "NORWAY",
        "FIN", "FINLAND", "SUOMI",
        "BEL", "BELGIUM", "BELGIQUE", "BELGIE",
        "LUX", "LUXEMBOURG",
        "LIE", "LIECHTENSTEIN",
        "ISL", "ICELAND", "ISLAND",
        "FRO", "FAROE ISLANDS",
        "GRL", "GREENLAND",
        "ALA", "ALAND ISLANDS", "ÅLAND ISLANDS",
        "SJM", "SVALBARD AND JAN MAYEN",
        "ABW", "ARUBA",
        "CUW", "CURACAO", "CURAÇAO",
        "SXM", "SINT MAARTEN",
        "BES", "BONAIRE",
        "SUR", "SURINAME",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())
        m_nld = RE_NLD_POSTCODE.match(clean)
        if m_nld:
            return f"{m_nld.group(1)} {m_nld.group(2).upper()}"
        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract inverted (premise, street_number, thoroughfare) from Germanic address line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()
        m = RE_INVERTED_STREET_NUMBER.match(line)
        if m:
            thoroughfare = m.group(1).strip()
            st_num = m.group(2).strip()
            return None, st_num, thoroughfare

        return None, None, line

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        country_iso = metadata.get("country", self.country_iso3)

        unit_type: Optional[str] = None
        unit_number: Optional[str] = None
        street_line = s1_raw

        # Handle comma-delimited single string when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts_comma = [p.strip() for p in s1_raw.split(",") if p.strip()]
            # Strip trailing country if present
            if len(parts_comma) >= 2 and parts_comma[-1].upper() in self.supported_countries:
                parts_comma = parts_comma[:-1]

            # A trailing Nordic floor/door ("45, 2. tv.") belongs to the street line, not the city.
            nordic_tail = ""
            if len(parts_comma) >= 2 and RE_NORDIC_TAIL.match(parts_comma[-1]):
                nordic_tail = f", {parts_comma.pop()}"

            if len(parts_comma) >= 2:
                last_part = parts_comma[-1].strip()
                # Check for "10115 Berlin", "1016 EK Amsterdam", or "111 35 Stockholm"
                m_post_city = re.match(
                    r"^(\d{4}[A-Z]{2}|\d{4,5}(?:\s+[A-Z]{2})?|\d{3}\s+\d{2})\s+(.*)$",
                    last_part,
                    re.IGNORECASE,
                )
                if m_post_city:
                    postal_raw = m_post_city.group(1)
                    city_raw = m_post_city.group(2)
                    street_line = ", ".join(parts_comma[:-1])
                else:
                    city_raw = parts_comma[-1]
                    street_line = ", ".join(parts_comma[:-1])
            elif len(parts_comma) == 1:
                street_line = parts_comma[0]
            street_line += nordic_tail

        if country_iso in _GERMAN_COUNTRIES:
            street_line = expand_german_street_abbreviations(street_line)
            # "Postfach 309, Zimmer 100" / "Postfach 309 Zimmer 100": the box is the street line, the rest is the unit.
            m_pf = _RE_DE_POSTFACH_UNIT.match(street_line.strip())
            if m_pf:
                street_line = f"POSTFACH {m_pf.group(1)}"
                s2_raw = f"{m_pf.group(2).strip()} {s2_raw}".strip() if s2_raw else m_pf.group(2).strip()
        elif country_iso in ("NLD", "BEL", "SUR", "ABW", "CUW", "SXM", "BES"):
            street_line = expand_dutch_street_abbreviations(street_line)

        # Check for Nordic floor/door (e.g. "45, 2. tv.")
        m_nordic_fd = RE_NORDIC_FLOOR_DOOR.search(street_line)
        if m_nordic_fd:
            unit_number = f"{m_nordic_fd.group(1)} {m_nordic_fd.group(2).lower()}"
            street_line = street_line[:m_nordic_fd.start()] + street_line[m_nordic_fd.end():]
            street_line = street_line.strip(" ,")

        # Extract secondary unit from s2_raw or street_line
        st1_base, st2_base = split_intl_secondary_unit(street_line, s2_raw, native_types=True)
        if st2_base and not unit_number:
            s2_parts = st2_base.split(maxsplit=1)
            unit_type = s2_parts[0]
            unit_number = s2_parts[1] if len(s2_parts) > 1 else None
        elif st2_base:
            # Nordic floor/door plus a street2 unit: keep both rather than dropping street2.
            unit_number = f"{unit_number} {st2_base}"

        # Check for Dutch/Germanic addition like "421-B" -> number: 421, unit: APT B
        m_dash_unit = re.match(r"^(.*?)\s+(\d+)-([A-Za-z0-9]+)$", st1_base)
        # Check for Finnish/Nordic stairwell and apartment like "12 B 25"
        m_stair_apt = re.match(r"^(.*?)\s+(\d+)\s+([A-Za-z]\s*\d+)$", st1_base)
        # "5-7" is a house-number range, not a unit. Only Dutch "421-B" and descending "421-2" additions are units: an
        # ascending numeric pair ("59-72") is a range in the Netherlands too.
        if (
            m_dash_unit
            and m_dash_unit.group(3).isdigit()
            and (country_iso != "NLD" or int(m_dash_unit.group(3)) > int(m_dash_unit.group(2)))
        ):
            m_dash_unit = None
        if m_dash_unit and not unit_type and not unit_number:
            thoroughfare_stem = m_dash_unit.group(1).strip()
            st_num = m_dash_unit.group(2).strip()
            unit_type = "APT"
            unit_number = m_dash_unit.group(3).strip().upper()
            full_street = f"{thoroughfare_stem} {st_num}"
        elif m_stair_apt and not unit_type and not unit_number:
            thoroughfare_stem = m_stair_apt.group(1).strip()
            st_num = m_stair_apt.group(2).strip()
            unit_number = m_stair_apt.group(3).strip().upper()
            full_street = f"{thoroughfare_stem} {st_num}"
        else:
            _, st_num, thoroughfare_stem = self.extract_premise_and_thoroughfare(st1_base)
            if st_num and thoroughfare_stem:
                full_street = f"{thoroughfare_stem} {st_num}"
            else:
                full_street = st1_base

        norm_postal = self.normalize_postal_code(postal_raw)
        norm_city = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
        norm_state = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", state_raw).strip().upper())

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=normalize_to_canonical_unicode(full_street) if full_street else None,
            unit_type=unit_type,
            unit_number=unit_number,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
