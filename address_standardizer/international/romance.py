"""Romance European Address Grammar (FRA, ESP, ITA, PRT); Latin America lives in latin_america.py."""

import re
from typing import ClassVar, Dict, List, Optional, Tuple

from address_standardizer._patterns import RE_COMMA_DOT
from address_standardizer.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.international.diacritics import normalize_to_canonical_unicode
from address_standardizer.tables import GLOBAL_METRO_TO_COUNTRY

# Road type abbreviations for Romance languages
ROMANCE_ROAD_TYPES: Dict[str, str] = {
    "AVENIDA": "AVENIDA",
    "AV": "AV",
    "AVE": "AV",
    "BOULEVARD": "BD",
    "BLVD": "BD",
    "BD": "BD",
    "CALLE": "CALLE",
    "C": "CALLE",
    "CLLE": "CALLE",
    "CARRERA": "CRA",
    "CRA": "CRA",
    "CR": "CRA",
    "RUE": "RUE",
    "RUA": "RUA",
    "VIA": "VIA",
    "ALLEE": "ALLEE",
    "ALLÉE": "ALLEE",
    "PLACE": "PL",
    "PLAZA": "PZ",
    "PIAZZA": "PZ",
    "PRAÇA": "PRACA",
    "PRACA": "PRACA",
    "PASEO": "PASEO",
    "CALZADA": "CALZ",
    "CALZ": "CALZ",
    "CAMINO": "CAMINO",
    "CARRETERA": "CTRA",
    "CTRA": "CTRA",
    "DIAGONAL": "DIAG",
    "DIAG": "DIAG",
    "TRANSVERSAL": "TRANSV",
}

# French road type mappings
FRENCH_ROAD_TYPES: Dict[str, str] = {
    "BOULEVARD": "BD",
    "BD": "BD",
    "BLVD": "BD",
    "AVENUE": "AV",
    "AV": "AV",
    "AVE": "AV",
    "RUE": "RUE",
    "ALLEE": "ALLEE",
    "ALLÉE": "ALLEE",
    "PLACE": "PL",
    "IMPASSE": "IMP",
    "IMP": "IMP",
}

# Brazilian CEP: 12345-678 or 12345678
RE_BRA_CEP = re.compile(r"^\b(\d{5})-?(\d{3})\b$")

# Colonia / Barrio prefix
RE_COLONIA = re.compile(
    r"^\b(?:COL|COLONIA|BARRIO|BO|FRACC|FRACCIONAMIENTO)\.?\s+(.+)$", re.IGNORECASE
)

# Secondary unit indicators (Int, Piso, Esc, Apt, Depto)
# A unit keyword must be a whole word: "INT" never matches inside "Internacional", "PISO" never inside "Pisos".
_SEC_END = r"(?![^\W\d_])\.?\s*"
_ROMANCE_SEC_TYPES = (
    r"INTERIOR|INT|DEPARTAMENTO|DEPTO|DPTO|PISO|ESCALIER|ESC|BATIMENT|BÂTIMENT|BÂT|BAT|ETAGE|ÉTAGE|PIANO"
    r"|APARTMENT|APTO|APT|SUITE|STE|UNIT"
)
RE_ROMANCE_SEC = re.compile(rf"(?<!\w)({_ROMANCE_SEC_TYPES}){_SEC_END}([A-Za-z0-9\-]+)?", re.IGNORECASE)

# A unit identifier that is unmistakably a unit number/letter ("4", "12B", "B", "B2", "IZQ"). Used when the keyword is
# found inside a street line, where "Piso Alto" or "Escuela Nueva" must stay part of the street name.
_STRICT_UNIT_ID = r"\d+[A-Za-z]{0,2}(?:-\d+)?|[A-Za-z]\d*|IZQ|DCHA|DER|PB|BIS"
# Floor/door like 2º B, 2o B, 2ª B, 2° B
# The ordinal marker is º/ª/° (optionally spaced) or a lowercase "o" glued to the number ("2o B"); a letter "o"
# after a space is a word ("12 Oeste", "5 Oriente"). The door/letter is at most 3 characters ("B", "IZQ").
RE_FLOOR_DOOR = re.compile(r"\b(\d+)(?:\s*[ºª°]\s*|o\s+)([A-Za-z0-9\-]{1,3})\b", re.IGNORECASE)
# French "3ème étage", "1er étage", "2e étage"
RE_FR_FLOOR = re.compile(r"(\d+)\s*(?:ER|ÈRE|ERE|RE|ÈME|EME|E|ND|D)?\s*(?:ÉTAGE|ETAGE|ETG)\.?", re.IGNORECASE)


def make_strict_sec_regex(types: str) -> "re.Pattern[str]":
    """Keyword plus an unmistakable identifier, as a whole-word match (see `_STRICT_UNIT_ID`)."""
    return re.compile(rf"(?<!\w)({types}){_SEC_END}({_STRICT_UNIT_ID})(?!\w)", re.IGNORECASE)


RE_ROMANCE_SEC_STRICT = make_strict_sec_regex(_ROMANCE_SEC_TYPES)


# "1578 - Bela Vista": street number followed by a barrio after a spaced dash
RE_NUM_BARRIO = re.compile(r"^(\d+[A-Za-z0-9\/]*)\s+-\s+(.+)$")


def merge_num_barrio(rem_parts: List[str]) -> Optional[str]:
    """Fold a "number - barrio" comma part into the street part before it (in place); return the barrio.

    "Av Paulista, 1578 - Bela Vista, Sao Paulo" -> parts ["Av Paulista 1578", "Sao Paulo"], barrio "Bela Vista".
    """
    for idx, part in enumerate(rem_parts):
        m_nb = RE_NUM_BARRIO.match(part)
        if idx and m_nb:
            rem_parts[idx - 1] = f"{rem_parts[idx - 1]} {m_nb.group(1)}"
            del rem_parts[idx]
            return m_nb.group(2).strip()
    return None


# A comma part that is nothing but a house number: "123", "12A", "12/14", "7-9", "Nº 45", "s/n".
RE_STANDALONE_NUMBER = re.compile(
    r"^(?:N[º°o]?\.?\s*)?(\d+[A-Za-z]?(?:\s?[/-]\s?\d+[A-Za-z]?)?(?:\s+[A-Za-z]{1,2}\d+)?|S/N)$", re.IGNORECASE
)
# A house number glued in front of a locality: "108 São Paulo" (but not "20 de Noviembre", "5 do Sul").
RE_LEADING_NUMBER_LOCALITY = re.compile(r"^(\d+[A-Za-z]?(?:\s+[A-Za-z]{1,2}\d+)?|S/N)\s+(?!(?:de|del|da|do|das|dos|di)\b)([^\W\d_].*)$", re.IGNORECASE)
# "7 - 9": the dash joins a house-number range, it does not introduce a barrio.
RE_NUMBER_RANGE_DASH = re.compile(r"(\d[A-Za-z]?)\s+[-–]\s+(\d+[A-Za-z]?)\s*$")


def merge_standalone_number(rem_parts: List[str]) -> None:
    """Fold a comma part that is only a house number into the street part before it (in place).

    "Rua X, 123, Bairro, Cidade" -> ["Rua X 123", "Bairro", "Cidade"]; without it the number would be read as a
    locality. The street part before must itself not be a bare number.
    """
    for idx in range(1, len(rem_parts)):
        num = RE_STANDALONE_NUMBER.match(rem_parts[idx].strip())
        if num and not RE_STANDALONE_NUMBER.match(rem_parts[idx - 1].strip()):
            rem_parts[idx - 1] = f"{rem_parts[idx - 1]} {num.group(1)}"
            del rem_parts[idx]
            return


def collapse_number_range(street_line: str) -> str:
    """"Travessa da Queimada 7 - 9" -> "Travessa da Queimada 7-9" (a numeric range, not "number - barrio")."""
    return RE_NUMBER_RANGE_DASH.sub(r"\1-\2", street_line)


def split_number_from_locality(street_line: str, locality: str) -> Tuple[str, str]:
    """Move a house number that leaked in front of the locality back onto the street line.

    ("Rua Dona Antonia", "108 Sao Paulo") -> ("Rua Dona Antonia 108", "Sao Paulo"); a street line that already ends
    in a number is left alone.
    """
    m = RE_LEADING_NUMBER_LOCALITY.match(locality.strip())
    if not m or not street_line or re.search(r"\d[A-Za-z]?$", street_line.strip()):
        return street_line, locality
    return f"{street_line} {m.group(1)}", m.group(2)


def unit_text(text: str) -> str:
    """Upper-cased unit text with punctuation stripped ("Esc. 2" -> "ESC 2")."""
    return " ".join(re.sub(r"[.,;]", " ", text).upper().split())


def extract_units_from_part(
    part: str,
    sec_re: "re.Pattern[str]",
    strict_re: "re.Pattern[str]",
    allow_whole: bool = True,
) -> Tuple[str, List[str]]:
    """Split one comma-delimited part into (remaining street/locality text, unit texts).

    A part that *starts* with a unit keyword is entirely a unit. A unit keyword at the *end* of a part that already
    has a house number ("Rua Augusta 1500 Apto 32") is split off and the street kept. A floor/door marker ("2º B")
    is removed from the part wherever it sits. Anything else is returned untouched.
    """
    s = part.strip()
    if not s:
        return "", []
    if allow_whole and sec_re.match(s):
        return "", [unit_text(s)]
    tail = s.rstrip(" .")
    for m in strict_re.finditer(s):
        prefix = s[: m.start()].strip(" ,.-")
        if m.end() == len(tail) and prefix and re.search(r"\d", prefix):
            return prefix, [unit_text(m.group(0))]
    m_fd = RE_FLOOR_DOOR.search(s)
    if m_fd:
        rest = (s[: m_fd.start()] + " " + s[m_fd.end():]).strip(" ,.-")
        return rest, [f"{m_fd.group(1)} {m_fd.group(2).upper()}"]
    return s, []


def merge_units(
    found: List[str], s2_type: Optional[str], s2_number: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Combine units found in the street line with the street2 unit; nothing is dropped."""
    if not found:
        return s2_type, s2_number
    s2_full = " ".join(p for p in (s2_type, s2_number) if p)
    return None, " ".join(found + ([s2_full] if s2_full else []))


def parse_street2_unit(
    s2: str, sec_re: "re.Pattern[str]"
) -> Tuple[Optional[str], Optional[str]]:
    """Normalise a street2 value into (unit_type, unit_number) without dropping any part of it.

    A single "TYPE ID" stays split ("APTO", "32"); everything else (several comma-delimited parts such as
    "Bât. B, Esc. 2, 3ème étage", trailing words, unknown text) is kept in full, upper-cased, as the unit number.
    """
    s = " ".join(s2.split())
    if not s:
        return None, None
    if "," in s or ";" in s:
        items: List[str] = []
        for p in re.split(r"[,;]", s):
            p = p.strip()
            if not p:
                continue
            m_fr = RE_FR_FLOOR.fullmatch(p)
            m_fd = RE_FLOOR_DOOR.fullmatch(p)
            if m_fr:
                items.append(f"ETAGE {m_fr.group(1)}")
            elif m_fd:
                items.append(f"{m_fd.group(1)} {m_fd.group(2).upper()}")
            else:
                items.append(unit_text(p))
        return None, " ".join(items) or None
    m_fr = RE_FR_FLOOR.fullmatch(s)
    if m_fr:
        return None, f"ETAGE {m_fr.group(1)}"
    ms = list(sec_re.finditer(s))
    if len(ms) == 1 and ms[0].start() == 0 and ms[0].end() == len(s.rstrip(" .")):
        return ms[0].group(1).upper(), (ms[0].group(2).upper() if ms[0].group(2) else None)
    m_fd = RE_FLOOR_DOOR.fullmatch(s)
    if m_fd:
        return None, f"{m_fd.group(1)} {m_fd.group(2).upper()}"
    return None, unit_text(s)


_RE_POSTAL_CITY = re.compile(r"^(\d{5}(?:-\d{3})?|\d{4}[- ]\d{3})\s+(.*)$")
# Portugal also writes the bare four-digit postal area before the city: "4000 Porto".
_RE_POSTAL_CITY_PRT = re.compile(r"^(\d{5}(?:-\d{3})?|\d{4}[- ]\d{3}|\d{4})\s+([^\W\d_].*)$")


def _postal_city_re(country_iso: str) -> "re.Pattern[str]":
    """Pattern for a "<postcode> <city>" comma part in the given country."""
    return _RE_POSTAL_CITY_PRT if country_iso in ("PRT", "PT", "PORTUGAL") else _RE_POSTAL_CITY


# Dotted Italian street-type abbreviations at the start of a street ("V. Dante", "C.so Sardegna"): the dot is required,
# a bare "V" is too ambiguous.
_IT_COUNTRIES = frozenset({"ITA", "IT", "ITALY", "ITALIA"})
_RE_IT_ABBREV = re.compile(r"^(V\.le|V\.lo|C\.so|P\.zza|P\.za|L\.go|V\.)(?=\s|\.|[A-Za-z])\.?\s*", re.IGNORECASE)
_IT_ABBREV = {"V.": "Via", "C.SO": "Corso", "P.ZA": "Piazza", "P.ZZA": "Piazza", "V.LE": "Viale", "L.GO": "Largo",
              "V.LO": "Vicolo"}


def expand_italian_street_abbreviation(line: str) -> str:
    """"V. Dante 53" -> "Via Dante 53"; only a dotted abbreviation at the very start is expanded."""
    m = _RE_IT_ABBREV.match(line)
    if not m:
        return line
    return f"{_IT_ABBREV[m.group(1).upper()]} {line[m.end():]}"


class RomanceGrammar(CountryGrammar):
    """Romance and Latin American address grammar with prefix road types and colonias."""

    split_commaless_line: ClassVar[bool] = True

    country_iso3: ClassVar[str] = "FRA"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "FRA", "FRANCE",
        "ESP", "SPAIN", "ESPANA",
        "ITA", "ITALY", "ITALIA",
        "PRT", "PORTUGAL",
        "MCO", "MONACO",
        "AND", "ANDORRA",
        "SMR", "SAN MARINO",
        "VAT", "VATICAN CITY", "HOLY SEE",
        "GLP", "GUADELOUPE",
        "MTQ", "MARTINIQUE",
        "GUF", "FRENCH GUIANA",
        "REU", "REUNION", "RÉUNION",
        "MYT", "MAYOTTE",
        "SPM", "SAINT PIERRE AND MIQUELON",
        "BLM", "SAINT BARTHELEMY", "SAINT BARTHÉLEMY",
        "MAF", "SAINT MARTIN",
        "NCL", "NEW CALEDONIA",
        "PYF", "FRENCH POLYNESIA",
        "WLF", "WALLIS AND FUTUNA",
        "ATF", "FRENCH SOUTHERN TERRITORIES",
    )
    # MEX/COL/ARG/BRA are owned by LatinAmericaGrammar (colonias, CEP/CPA, Manzana/Lote); each country code is
    # registered by exactly one grammar. tests/test_intl_latam_europe_review.py enforces this.

    def normalize_postal_code(self, raw_code: str) -> str:
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())
        m_bra = RE_BRA_CEP.match(clean)
        if m_bra:
            return f"{m_bra.group(1)}-{m_bra.group(2)}"
        m_prt = re.match(r"^(\d{4})[- ](\d{3})$", clean)  # Portugal "1150-011", sometimes written "1150 011"
        if m_prt:
            return f"{m_prt.group(1)}-{m_prt.group(2)}"
        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not street_line:
            return None, None, None

        line = street_line.strip()

        # Check French number-first format: "142 Boulevard Saint-Germain"
        m_fr = re.match(r"^(\d+[A-Za-z0-9\-\/]*)\s+([A-Za-zÀ-ÿ]+)\s+(.*)$", line)
        if m_fr:
            st_num = m_fr.group(1).upper()
            road_type_cand = m_fr.group(2).upper()
            rest = m_fr.group(3).strip()
            if road_type_cand in FRENCH_ROAD_TYPES:
                norm_type = FRENCH_ROAD_TYPES[road_type_cand]
                st_name = f"{norm_type} {rest.strip(' ,.').upper()}"
                return None, st_num, st_name

        # Check Latin American numbered street: "Calle 72 No. 10-07" or "Calle 72 # 10-07"
        if re.search(r"\b(?:NO\.?|#)\s*\d", line, re.IGNORECASE):
            return None, None, line.upper()

        # Latin American / Spanish prefix format: "Av. Insurgentes Sur 1602" or "Calle Mayor 45"
        # Road type + Name + Number
        m_es = re.match(r"^([A-Za-zÀ-ÿ\.]+)\s+(.*?)\s+(\d+[A-Za-z0-9\-\/]*)$", line)
        if m_es:
            prefix_cand = m_es.group(1).strip(".").upper()
            rest_name = m_es.group(2).strip(" ,.")
            st_num = m_es.group(3).strip().upper()
            if prefix_cand in ROMANCE_ROAD_TYPES:
                norm_prefix = ROMANCE_ROAD_TYPES[prefix_cand]
                st_name = f"{norm_prefix} {rest_name.upper()} {st_num}"
                return None, st_num, st_name

        return None, None, line

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        country_iso = metadata.get("country", self.country_iso3)
        if str(country_iso).upper() in _IT_COUNTRIES:
            s1_raw = expand_italian_street_abbreviation(s1_raw)

        unit_type: Optional[str] = None
        unit_number: Optional[str] = None
        sec_units: List[str] = []
        dep_locality: Optional[str] = None
        street_line = s1_raw

        # Handle comma-delimited single string when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts_comma = [p.strip() for p in s1_raw.split(",") if p.strip()]
            if len(parts_comma) >= 2:
                from address_standardizer.international.countries import CountryRegistry
                info = CountryRegistry.get(parts_comma[-1])
                if info and info.alpha3 in self.supported_countries:
                    country_iso = info.alpha3
                    parts_comma = parts_comma[:-1]

            # Scan from right for State / Postal / City
            rem_parts: List[str] = []
            for part in parts_comma:
                # Check for Colonia
                m_col = RE_COLONIA.match(part)
                if m_col:
                    dep_locality = m_col.group(1).strip()
                    continue

                # Check for secondary units: "Int. 401", "Esc. B", "Apt 12", "Rua X 15 Apto 3"
                part, found_units = extract_units_from_part(part, RE_ROMANCE_SEC, RE_ROMANCE_SEC_STRICT)
                sec_units.extend(found_units)
                if not part:
                    continue

                # Check if entire part is a postal code
                if RE_BRA_CEP.match(part.strip()) or re.match(r"^(?:\d{5}(?:-\d{3})?|\d{4}[- ]\d{3})$", part.strip()):
                    postal_raw = part.strip()
                    continue

                rem_parts.append(part)

            if len(rem_parts) >= 2:
                last_p = rem_parts[-1]
                m_city_st = re.match(r"^(.*?)\s*-\s*([A-Za-z]{2})$", last_p)
                if m_city_st and not state_raw:
                    city_raw = m_city_st.group(1).strip()
                    state_raw = m_city_st.group(2).strip()
                    rem_parts = rem_parts[:-1]

            # "Calle Mayor, 12, Madrid": a bare number part belongs to the street, not to a locality.
            merge_standalone_number(rem_parts)
            if not city_raw and not dep_locality:
                dep_locality = merge_num_barrio(rem_parts)

            if city_raw:
                street_line = ", ".join(rem_parts)
            elif len(rem_parts) >= 3:
                # e.g. "Av. Insurgentes Sur 1602", "03940 Ciudad de México", "CDMX"
                # OR "142 Boulevard Saint-Germain", "Quartier Latin", "75006 Paris"
                m_pc_last = _postal_city_re(country_iso).match(rem_parts[-1])
                if m_pc_last:
                    postal_raw = m_pc_last.group(1)
                    city_raw = m_pc_last.group(2)
                    street_line = ", ".join(rem_parts[:-1])
                else:
                    state_raw = rem_parts[-1]
                    m_pc = _postal_city_re(country_iso).match(rem_parts[-2])
                    if m_pc:
                        postal_raw = m_pc.group(1)
                        city_raw = m_pc.group(2)
                    else:
                        city_raw = rem_parts[-2]
                    street_line = ", ".join(rem_parts[:-2])
            elif len(rem_parts) == 2:
                # e.g. "Calle Mayor 45", "28013 Madrid"
                m_pc = _postal_city_re(country_iso).match(rem_parts[1])
                if m_pc:
                    postal_raw = m_pc.group(1)
                    city_raw = m_pc.group(2)
                else:
                    city_raw = rem_parts[1]
                street_line = rem_parts[0]
            elif len(rem_parts) == 1:
                p0 = rem_parts[0].strip().upper()
                if not city_raw and (p0 in GLOBAL_METRO_TO_COUNTRY or p0 in (
                    "PARIS",
                    "MADRID",
                    "ROME",
                    "ROMA",
                    "BOGOTA",
                    "BOGOTÁ",
                    "BUENOS AIRES",
                    "SAO PAULO",
                    "SÃO PAULO",
                    "RIO DE JANEIRO",
                )):
                    city_raw = rem_parts[0]
                    street_line = ""
                else:
                    street_line = rem_parts[0]
            else:
                # Every part was consumed as colonia / unit / postal code: no street line remains.
                street_line = ""

            if city_raw:
                street_line, city_raw = split_number_from_locality(street_line, city_raw)

        # Handle secondary units in s2_raw or embedded in street_line
        s2_type: Optional[str] = None
        s2_number: Optional[str] = None
        if s2_raw:
            s2_type, s2_number = parse_street2_unit(s2_raw, RE_ROMANCE_SEC)

        street_line = collapse_number_range(street_line)
        # Check for Brazil " - " separator before split_intl_secondary_unit
        if " - " in street_line:
            p_dash = street_line.split(" - ", 1)
            street_line = p_dash[0].strip()
            if not dep_locality:
                dep_locality = p_dash[1].strip()

        # A unit written at the end of the street line ("Avenida Estela 100 Int 4") or a floor/door ("Calle Mayor 45 2º B")
        street_line, inline_units = extract_units_from_part(
            street_line, RE_ROMANCE_SEC_STRICT, RE_ROMANCE_SEC_STRICT, allow_whole=False
        )
        sec_units.extend(inline_units)
        st1_base, st2_base = split_intl_secondary_unit(street_line, "", native_types=True)
        if st2_base and not (sec_units or s2_type or s2_number):
            st2_parts = st2_base.split(maxsplit=1)
            unit_type = st2_parts[0]
            unit_number = st2_parts[1] if len(st2_parts) > 1 else None
        else:
            if st2_base:
                sec_units.append(st2_base)
            unit_type, unit_number = merge_units(sec_units, s2_type, s2_number)

        # Normalize thoroughfare
        _, st_num, thoroughfare = self.extract_premise_and_thoroughfare(st1_base)

        norm_postal = self.normalize_postal_code(postal_raw)
        norm_city = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
        norm_state = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", state_raw).strip().upper())
        norm_dep_loc = normalize_to_canonical_unicode(dep_locality.upper()) if dep_locality else None

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=normalize_to_canonical_unicode(thoroughfare) if thoroughfare else None,
            unit_type=unit_type,
            unit_number=unit_number,
            dependent_locality=norm_dep_loc,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
