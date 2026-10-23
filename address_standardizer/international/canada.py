"""Canada Post Bilingual English/French Address Grammar."""

import re
import unicodedata
from typing import ClassVar, Dict, List, Optional, Tuple

from address_standardizer._patterns import (
    RE_CAN_POSTCODE,
    RE_COMMA_DOT,
    RE_NON_ALPHANUMERIC,
    RE_PO_BOX,
    RE_WHITESPACE,
    clean_redundant_street_tail,
)
from address_standardizer.international.base import (
    may_abbreviate_street_type,
    street_type_index,
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.international.commaless import (
    COMMONWEALTH_TYPE_WORDS,
    split_commaless_region_postal_city,
    town_set,
)
from address_standardizer.tables import (
    CANADIAN_PROVINCE_ABBREVIATIONS,
    CANADIAN_PROVINCES,
    DIRECTIONALS,
    STREET_SUFFIXES,
)

RE_CAN_POSTCODE_EXACT = re.compile(
    r"^([A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z])\s*(\d[A-CEGHJ-NPR-TV-Z]\d)$",
    re.IGNORECASE,
)

# "Ontario M4X 1W4" / "ON M4X1W4" / "Québec, H3B 4W8": a province (any form) followed by the postal code.
RE_CAN_PROV_THEN_POSTAL = re.compile(
    r"^(.+?)[\s,]+([A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z]\s?\d[A-CEGHJ-NPR-TV-Z]\d)$", re.IGNORECASE
)

# French / bilingual secondary-unit designators: "app. 4", "appt 12", "bureau 200", "unité 3", "local 101".
_FR_UNIT_TYPES: Dict[str, str] = {
    "APP": "APT", "APPT": "APT", "BUREAU": "STE", "BUR": "STE", "UNITE": "UNIT", "LOCAL": "UNIT",
}
_FR_UNIT_ALT = "|".join(sorted(list(_FR_UNIT_TYPES) + ["UNITÉ"], key=len, reverse=True))
RE_CAN_FR_UNIT_WHOLE = re.compile(rf"^({_FR_UNIT_ALT})\.?\s*#?\s*([A-Z0-9][A-Z0-9\-]*)$", re.IGNORECASE)
RE_CAN_FR_UNIT_TAIL = re.compile(
    rf"^(.*?\S)(?:\s*,\s*|\s+)({_FR_UNIT_ALT})\.?\s*#?\s*([A-Z0-9][A-Z0-9\-]*)$", re.IGNORECASE
)

# "PO Box 123 Stn A" / "CP 123 Succ A" / "PO Box 123 RPO Main": the station belongs to the PO box line.
RE_CAN_PO_STATION = re.compile(
    r"^(P\.?O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX|C\.?P\.?|CASE\s+POSTALE)\s+(\d[A-Z0-9\-]*)[,\s]+"
    r"(STN|STATION|RPO|SUCC|SUCCURSALE)\.?\s+([^,]+?)(?:\s*,\s*(.+))?$",
    re.IGNORECASE,
)
RE_CAN_STATION_ONLY = re.compile(r"^(?:STN|STATION|RPO|SUCC|SUCCURSALE)\.?\s+\S.*$", re.IGNORECASE)

FRENCH_STREET_TYPES: Dict[str, str] = {
    "RUE": "RUE",
    "BOULEVARD": "BD",
    "BD": "BD",
    "BLVD": "BD",
    "BOUL": "BD",
    "AVENUE": "AV",
    "AV": "AV",
    "AVE": "AV",
    "CHEMIN": "CH",
    "CH": "CH",
    "CROISSANT": "CROIS",
    "CROIS": "CROIS",
    "ROUTE": "RTE",
    "RTE": "RTE",
    "MONTEE": "MTE",
    "MONTÉE": "MTE",
    "MTE": "MTE",
    "ALLEE": "ALLEE",
    "ALLÉE": "ALLEE",
    "PLACE": "PL",
    "PL": "PL",
    "COTE": "COTE",
    "CÔTE": "COTE",
    "IMPASSE": "IMP",
    "IMP": "IMP",
    "PROMENADE": "PROM",
    "PROM": "PROM",
    "TERRASSE": "TERR",
    "TERR": "TERR",
    "RANG": "RG",
    "RG": "RG",
    "CARREFOUR": "CARREF",
    "SQUARE": "SQ",
}

FRENCH_DIRECTIONS: Dict[str, str] = {
    "OUEST": "O",
    "EST": "E",
    "NORD": "N",
    "SUD": "S",
    "NORD-EST": "NE",
    "NORDEST": "NE",
    "NORD-OUEST": "NO",
    "NORDOUEST": "NO",
    "SUD-EST": "SE",
    "SUDEST": "SE",
    "SUD-OUEST": "SO",
    "SUDOUEST": "SO",
}

RURAL_DELIVERY_MODES: Dict[str, str] = {
    "RR": "RR",
    "RURAL ROUTE": "RR",
    "SS": "SS",
    "SUBURBAN SERVICE": "SS",
    "MR": "MR",
    "MOBILE ROUTE": "MR",
    "STN MAIN": "STN MAIN",
    "STATION MAIN": "STN MAIN",
    "COMP": "COMP",
    "COMPARTMENT": "COMP",
    "CP": "PO BOX",
    "CASE POSTALE": "PO BOX",
}


_RE_CAN_TRAILING_COUNTRY = re.compile(r"\s+(?:CANADA|CAN)\s*$", re.IGNORECASE)

# First letters of the postal codes of each province (Canada Post forward sortation areas).
_PROVINCE_FSA_LETTERS: Dict[str, str] = {
    "NL": "A", "NS": "B", "PE": "C", "NB": "E", "QC": "GHJ", "ON": "KLMNP", "MB": "R", "SK": "S", "AB": "T",
    "BC": "V", "NU": "X", "NT": "X", "YT": "Y",
}

# Words that end a French street name (the direction) or, for the comma-less splitter, are no street start.
_CAN_TYPE_WORDS = COMMONWEALTH_TYPE_WORDS | frozenset(
    RE_NON_ALPHANUMERIC.sub("", d) for d in ("OUEST", "EST", "NORD", "SUD", "NORD-EST", "NORD-OUEST", "SUD-EST", "SUD-OUEST")
)
_CAN_PREFIX_TYPES = frozenset(RE_NON_ALPHANUMERIC.sub("", t).upper() for t in FRENCH_STREET_TYPES)
_CAN_SUFFIX_DIRECTIONALS = frozenset({
    "NORTH", "SOUTH", "EAST", "WEST", "NORTHEAST", "NORTHWEST", "SOUTHEAST", "SOUTHWEST", "N", "S", "E", "W", "NE",
    "NW", "SE", "SW",
})

# Well-known cities (English and French spellings), used only to find where the city starts in a comma-less line.
CA_TOWNS = town_set((
    "TORONTO", "MONTRÉAL", "MONTREAL", "VANCOUVER", "CALGARY", "EDMONTON", "OTTAWA", "WINNIPEG", "QUÉBEC", "QUEBEC",
    "HAMILTON", "KITCHENER", "LONDON", "VICTORIA", "HALIFAX", "OSHAWA", "WINDSOR", "SASKATOON", "REGINA",
    "SHERBROOKE", "ST. JOHN'S", "ST JOHNS", "BARRIE", "KELOWNA", "ABBOTSFORD", "KINGSTON", "SUDBURY", "SAGUENAY",
    "TROIS-RIVIÈRES", "GUELPH", "MONCTON", "BRANTFORD", "THUNDER BAY", "SAINT JOHN", "PETERBOROUGH", "LAVAL",
    "GATINEAU", "LONGUEUIL", "MISSISSAUGA", "BRAMPTON", "MARKHAM", "VAUGHAN", "RICHMOND HILL", "OAKVILLE", "BURLINGTON",
    "NORTH YORK", "SCARBOROUGH", "ETOBICOKE", "EAST YORK", "NORTH VANCOUVER", "WEST VANCOUVER", "SURREY",
    "BURNABY", "RICHMOND", "COQUITLAM", "NEW WESTMINSTER", "LANGLEY", "NANAIMO", "KAMLOOPS", "SAINT-LAURENT",
    "SAINT-LÉONARD", "SAINT-JEAN-SUR-RICHELIEU", "SAINT-HYACINTHE", "SAINT-JÉRÔME", "SAINT-BRUNO", "LÉVIS",
    "DRUMMONDVILLE", "GRANBY", "SHAWINIGAN", "RIMOUSKI", "CHICOUTIMI", "JONQUIÈRE", "VERDUN", "LASALLE", "OUTREMONT",
    "WESTMOUNT", "ANJOU", "LACHINE", "PIERREFONDS", "MONTRÉAL-NORD", "MONTRÉAL-OUEST", "CÔTE-SAINT-LUC", "LÉVIS",
    "CHARLOTTETOWN", "FREDERICTON", "WHITEHORSE", "YELLOWKNIFE", "IQALUIT", "ST. CATHARINES", "ST CATHARINES",
    "NIAGARA FALLS", "WATERLOO", "CAMBRIDGE", "SARNIA", "BELLEVILLE", "CORNWALL", "NORTH BAY", "SAULT STE. MARIE",
    "RED DEER", "LETHBRIDGE", "MEDICINE HAT", "GRANDE PRAIRIE", "FORT MCMURRAY", "ST. ALBERT", "ST ALBERT",
    "PRINCE GEORGE", "PRINCE ALBERT", "MOOSE JAW", "BRANDON", "SAINT-LAMBERT", "BROSSARD", "TERREBONNE", "REPENTIGNY",
    "BLAINVILLE", "BOUCHERVILLE", "DORVAL", "KIRKLAND", "POINTE-CLAIRE", "BEACONSFIELD", "MONT-ROYAL", "MONTREAL WEST",
))


def _can_region_suffix(rest: List[str], postal: str) -> Optional[Tuple[int, str]]:
    """Province words (code or name, English or French) directly before the postal code, accepted only when the
    postal code's first letter belongs to that province ("Rue Ontario H2L 1R9" keeps "Ontario" in the street)."""
    for n in (4, 3, 2, 1):
        if len(rest) > n:
            code = province_code(" ".join(rest[-n:]))
            if code and postal.upper()[:1] in _PROVINCE_FSA_LETTERS[code]:
                return n, code
    return None


def province_code(raw: str) -> Optional[str]:
    """Two-letter province code for a province name or abbreviation in English or French, else None.

    Accents, dots, hyphens and case are ignored: ``Québec``, ``QUEBEC``, ``P.E.I.``, ``Nouveau-Brunswick``, ``ONT``.
    """
    folded = "".join(c for c in unicodedata.normalize("NFKD", raw or "") if not unicodedata.combining(c))
    key = " ".join(re.sub(r"[^A-Z0-9]+", " ", folded.upper()).split())
    return CANADIAN_PROVINCES.get(key) or CANADIAN_PROVINCE_ABBREVIATIONS.get(key)


def french_unit(text: str) -> Optional[str]:
    """``"app. 4"`` -> ``"APT 4"``; None when the whole text is not a French-style unit designator."""
    m = RE_CAN_FR_UNIT_WHOLE.match((text or "").strip())
    return f"{_FR_UNIT_TYPES[_ascii_upper(m.group(1))]} {m.group(2).upper()}" if m else None


def _ascii_upper(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).upper()


def is_valid_canadian_postal_code(raw_code: str) -> bool:
    """Validate Canadian postal code against Canada Post FSA/LDU specification."""
    if not raw_code:
        return False
    clean = " ".join(raw_code.strip().upper().split())
    m = RE_CAN_POSTCODE_EXACT.match(clean)
    if not m:
        return False
    # Characters D, F, I, O, Q, U and initial W, Z are prohibited by regex [A-CEGHJ-NPR-TVXY]
    return True


class CanadaGrammar(CountryGrammar):
    """Canada Post compliant bilingual English/French address grammar."""

    country_iso3: ClassVar[str] = "CAN"
    supported_countries: ClassVar[Tuple[str, ...]] = ("CAN", "CANADA")

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
        """Standardize; a comma-less "683 Abbott Street Vancouver BC V6B 0J4" is split at its province and postal
        code first."""
        if street1 and not (city or state or postal_code) and "," not in street1:
            split = split_commaless_region_postal_city(
                street1,
                is_valid_canadian_postal_code,
                _can_region_suffix,
                CA_TOWNS,
                _RE_CAN_TRAILING_COUNTRY,
                _CAN_TYPE_WORDS,
                _CAN_SUFFIX_DIRECTIONALS,
                _CAN_PREFIX_TYPES,
            )
            if split is not None:
                street1, city, state, postal_code = split
        return super().standardize(street1, street2, city, state, postal_code, country, raw_street_address)

    def normalize_postal_code(self, raw_code: str) -> str:
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())
        m = RE_CAN_POSTCODE_EXACT.match(clean)
        if m:
            return f"{m.group(1).upper()} {m.group(2).upper()}"
        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not street_line:
            return None, None, None

        line = street_line.strip()

        # Check Rural Route / Delivery modes
        m_rr = re.match(
            r"^(RR|RURAL\s+ROUTE|SS|MR|STN\s+MAIN|COMP|CP|CASE\s+POSTALE)\b\s*#?\s*([A-Za-z0-9\-]+)?(.*)$",
            line,
            re.IGNORECASE,
        )
        if m_rr:
            mode_raw = m_rr.group(1).upper()
            mode_norm = RURAL_DELIVERY_MODES.get(mode_raw, mode_raw)
            mode_num = m_rr.group(2) or ""
            trailing = (m_rr.group(3) or "").strip(" ,")  # "Site 3 Box 4" etc. must survive
            return None, None, f"{mode_norm} {mode_num} {trailing}".strip()

        # Standard civic address
        m_num = re.match(r"^(\d+[A-Za-z0-9\-\/]*)\s+(.*)$", line)
        if m_num:
            st_num = m_num.group(1).upper()
            rest = m_num.group(2).strip()
            st_name = self._normalize_bilingual_street(rest)
            return None, st_num, st_name

        return None, None, self._normalize_bilingual_street(line)

    def _normalize_bilingual_street(self, text: str) -> str:
        if not text:
            return ""
        words = text.strip().split()
        if not words:
            return ""

        # Check French prefix type: "rue Saint-Denis", "boulevard René-Lévesque Ouest"
        first_clean = RE_NON_ALPHANUMERIC.sub("", words[0]).upper()
        if first_clean in FRENCH_STREET_TYPES:
            prefix_norm = FRENCH_STREET_TYPES[first_clean]
            rest_words = words[1:]
            norm_rest: List[str] = []
            for w in rest_words:
                w_clean = RE_NON_ALPHANUMERIC.sub("", w).upper()
                if w_clean in FRENCH_DIRECTIONS:
                    norm_rest.append(FRENCH_DIRECTIONS[w_clean])
                elif w_clean in DIRECTIONALS:
                    norm_rest.append(DIRECTIONALS[w_clean])
                else:
                    norm_rest.append(w.upper())
            return f"{prefix_norm} {' '.join(norm_rest)}"

        # English suffix type: "King Street West"
        norm_words: List[str] = []
        type_idx = street_type_index(words)
        for idx, w in enumerate(words):
            w_clean = RE_NON_ALPHANUMERIC.sub("", w).upper()
            if w_clean in STREET_SUFFIXES and may_abbreviate_street_type(w_clean, idx, type_idx):
                norm_words.append(STREET_SUFFIXES[w_clean])
            elif w_clean in DIRECTIONALS:
                norm_words.append(DIRECTIONALS[w_clean])
            elif w_clean in FRENCH_DIRECTIONS:
                norm_words.append(FRENCH_DIRECTIONS[w_clean])
            else:
                norm_words.append(w.upper())
        return " ".join(norm_words)

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
            if len(parts_comma) >= 2 and parts_comma[-1].upper() in ("CANADA", "CAN"):
                parts_comma = parts_comma[:-1]

            if len(parts_comma) >= 2:
                last_part = parts_comma[-1].upper()
                m_prov_post = RE_CAN_PROV_THEN_POSTAL.match(last_part)
                if m_prov_post and not province_code(m_prov_post.group(1)):
                    m_prov_post = None
                m_post = RE_CAN_POSTCODE.match(last_part)
                if m_prov_post:
                    state_raw = m_prov_post.group(1)
                    postal_raw = m_prov_post.group(2)
                    city_raw = parts_comma[-2]
                    street_line = ", ".join(parts_comma[:-2])
                elif m_post:
                    postal_raw = parts_comma[-1]
                    rest_parts = parts_comma[:-1]
                    # "Street, City, Province, Postal": the part before the postal code is the province
                    if len(rest_parts) >= 3 and province_code(rest_parts[-1]):
                        state_raw = rest_parts[-1]
                        rest_parts = rest_parts[:-1]
                    city_raw = rest_parts[-1]
                    street_line = ", ".join(rest_parts[:-1])
                elif len(parts_comma) >= 3 and province_code(last_part):
                    state_raw = parts_comma[-1]
                    city_raw = parts_comma[-2]
                    street_line = ", ".join(parts_comma[:-2])
                elif (
                    len(parts_comma) >= 3
                    and province_code(parts_comma[-2])
                    and RE_CAN_PROV_THEN_POSTAL.match(last_part)
                ):
                    # "Street, Nova Scotia, Halifax B3H 4A8": province before the "City Postal" part (the regex's first
                    # group is the city here, not a province)
                    m_city_post = RE_CAN_PROV_THEN_POSTAL.match(parts_comma[-1])
                    state_raw = parts_comma[-2]
                    city_raw, postal_raw = m_city_post.group(1), m_city_post.group(2)
                    street_line = ", ".join(parts_comma[:-2])
                else:
                    city_raw = parts_comma[-1]
                    street_line = ", ".join(parts_comma[:-1])
            elif len(parts_comma) == 1:
                street_line = parts_comma[0]

        # Extract trailing postal code and province from street_line if not provided
        if not postal_raw and street_line:
            m_tail_pc = re.search(r"(?:,\s*|\s+)([A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z]\s*\d[A-CEGHJ-NPR-TV-Z]\d)\s*$", street_line, re.IGNORECASE)
            if m_tail_pc:
                postal_raw = m_tail_pc.group(1)

        if not state_raw and street_line:
            m_tail_prov = re.search(r"(?:,\s*|\s+)([A-Z]{2})\s*(?:[A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z]\s*\d[A-CEGHJ-NPR-TV-Z]\d)?\s*$", street_line, re.IGNORECASE)
            if m_tail_prov and m_tail_prov.group(1).upper() in CANADIAN_PROVINCES:
                state_raw = m_tail_prov.group(1).upper()

        # Clean redundant city, province, country, and postal code from street_line and s2_raw
        street_line = clean_redundant_street_tail(street_line, city=city_raw, state=state_raw, postal_code=postal_raw)
        if s2_raw:
            s2_raw = clean_redundant_street_tail(s2_raw, city=city_raw, state=state_raw, postal_code=postal_raw)

        # Canada Post puts the delivery station on the PO box line: "PO BOX 123 STN A" (also RPO / Succ forms).
        po_station_line: Optional[str] = None
        if s2_raw and RE_CAN_STATION_ONLY.match(s2_raw.strip()) and RE_PO_BOX.search(street_line):
            street_line = f"{street_line.strip()} {s2_raw.strip()}"
            s2_raw = ""
        m_pos = RE_CAN_PO_STATION.match(street_line.strip())
        if m_pos:
            po_station_line = f"PO BOX {m_pos.group(2).upper()} STN {m_pos.group(4).strip().upper()}"
            street_line = (m_pos.group(5) or "").strip()

        # French-style units ("app. 4", "bureau 200") that the generic splitter does not know.
        fr_unit_s2 = french_unit(s2_raw)
        if fr_unit_s2:
            s2_raw = fr_unit_s2
        m_fr_tail = RE_CAN_FR_UNIT_TAIL.match(street_line.strip())
        if m_fr_tail:
            street_line = m_fr_tail.group(1)
            fr_unit = f"{_FR_UNIT_TYPES[_ascii_upper(m_fr_tail.group(2))]} {m_fr_tail.group(3).upper()}"
            s2_raw = f"{fr_unit} {s2_raw}".strip()

        st1_base, st2_base = split_intl_secondary_unit(street_line, s2_raw)
        if st2_base:
            s2_parts = st2_base.split(maxsplit=1)
            unit_type = s2_parts[0]
            unit_number = s2_parts[1] if len(s2_parts) > 1 else None

        # Check for PO Box in st1_base
        m_box = RE_PO_BOX.search(st1_base)
        if m_box and not unit_type:
            unit_type = "PO BOX"
            unit_number = m_box.group(1).upper()
            st1_base = st1_base[:m_box.start()] + st1_base[m_box.end():]
            st1_base = st1_base.strip(" ,.-")

        _, st_num, st_name = self.extract_premise_and_thoroughfare(st1_base)
        if po_station_line:
            st_num, st_name = None, po_station_line

        # Normalize Province
        norm_state = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", state_raw).strip().upper())
        norm_state = province_code(norm_state) or norm_state

        norm_city = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
        norm_postal = self.normalize_postal_code(postal_raw)

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=st_name,
            unit_type=unit_type,
            unit_number=unit_number,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
