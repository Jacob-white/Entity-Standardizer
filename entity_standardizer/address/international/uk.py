from dataclasses import dataclass
import re
from typing import Callable, ClassVar, List, Optional, Set, Tuple

from entity_standardizer.address._patterns import (
    RE_COMMA_DOT,
    RE_INTL_FLAT,
    RE_INTL_SEC_INLINE,
    RE_INTL_SEC_START,
    RE_NON_ALPHANUMERIC,
    RE_WHITESPACE,
    is_invalid_thoroughfare,
)
from entity_standardizer.address.international.base import (
    UNAMBIGUOUS_STREET_TYPES,
    may_abbreviate_street_type,
    street_type_index,
    CountryGrammar,
    ParsedAddressComponents,
)
from entity_standardizer.address.tables import DIRECTIONALS, SECONDARY_UNITS, STREET_SUFFIXES


@dataclass(slots=True)
class UKParsedAddressComponents(ParsedAddressComponents):
    """Royal Mail PAF / BS 7666 structured component formatter."""

    def format_street1(self) -> str:
        """Formats street1 as numbered thoroughfare delivery line."""
        if self.street_number and self.street_name:
            parts = [self.street_number]
            if self.pre_directional:
                parts.append(self.pre_directional)
            parts.append(self.street_name)
            if self.street_type and not (
                self.street_name.endswith(" " + self.street_type)
                or self.street_name.startswith(self.street_type + " ")
                or self.street_name == self.street_type
            ):
                parts.append(self.street_type)
            if self.post_directional:
                parts.append(self.post_directional)
            return " ".join(parts).strip()
        # When thoroughfare name is absent (e.g. only building number and unit: "UNIT A 10", "SUITE 302 4")
        if self.street_name and self.street_name.isdigit() and (self.unit_type or self.unit_number):
            u_str = f"{self.unit_type or 'UNIT'} {self.unit_number or ''}".strip()
            return f"{self.street_name} {u_str}".strip()
        if self.street_number and not self.street_name and (self.unit_type or self.unit_number):
            u_str = f"{self.unit_type or 'UNIT'} {self.unit_number or ''}".strip()
            return f"{self.street_number} {u_str}".strip()
        return ParsedAddressComponents.format_street1(self)

    def format_street2(self) -> str:
        """Formats street2 combining secondary unit and premise name."""
        # If street1 incorporated the secondary unit because no street name was present, do not repeat it in street2
        if (self.street_name and self.street_name.isdigit() and (self.unit_type or self.unit_number)) or (
            self.street_number and not self.street_name and (self.unit_type or self.unit_number)
        ):
            if self.building_name:
                return self.building_name.strip()
            return ""
        sec = ParsedAddressComponents.format_street2(self)
        if self.building_name and self.street_number:
            if sec:
                return f"{sec} {self.building_name}".strip()
            return self.building_name.strip()
        return sec

RE_UK_POSTCODE_EXACT = re.compile(
    r"^(GIR|[A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})$", re.IGNORECASE
)
RE_UK_POSTCODE_SEARCH = re.compile(
    r"\b(GIR\s*0AA|[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2})\b", re.IGNORECASE
)

# Royal Mail Post Towns
UK_POST_TOWNS: Set[str] = {
    "ABERDEEN",
    "ARMAGH",
    "BATH",
    "BELFAST",
    "BIRMINGHAM",
    "BRADFORD",
    "BRIGHTON",
    "BRISTOL",
    "CAMBRIDGE",
    "CANTERBURY",
    "CARDIFF",
    "CARLISLE",
    "CHELMSFORD",
    "CHESTER",
    "CHICHESTER",
    "COLCHESTER",
    "COVENTRY",
    "DERBY",
    "DERRY",
    "DONCASTER",
    "DUNDEE",
    "DURHAM",
    "EDINBURGH",
    "ELY",
    "EXETER",
    "GLASGOW",
    "GLOUCESTER",
    "HEREFORD",
    "INVERNESS",
    "IPSWICH",
    "KINGSTON UPON HULL",
    "HULL",
    "LANCASTER",
    "LEEDS",
    "LEICESTER",
    "LICHFIELD",
    "LINCOLN",
    "LIVERPOOL",
    "LONDON",
    "LUTON",
    "MANCHESTER",
    "MILTON KEYNES",
    "NEWCASTLE UPON TYNE",
    "NEWCASTLE",
    "NEWPORT",
    "NORWICH",
    "NOTTINGHAM",
    "OXFORD",
    "PERTH",
    "PETERBOROUGH",
    "PLYMOUTH",
    "PORTSMOUTH",
    "PRESTON",
    "READING",
    "RIPON",
    "SALFORD",
    "SALISBURY",
    "SHEFFIELD",
    "SOUTHAMPTON",
    "SOUTHEND-ON-SEA",
    "ST ALBANS",
    "ST ASAPH",
    "ST DAVIDS",
    "STIRLING",
    "STOKE-ON-TRENT",
    "SUNDERLAND",
    "SWANSEA",
    "TRURO",
    "WAKEFIELD",
    "WELLS",
    "WESTMINSTER",
    "WINCHESTER",
    "WOLVERHAMPTON",
    "WORCESTER",
    "WREXHAM",
    "YORK",
    "BOURNEMOUTH",
    "BOLTON",
    "BLACKPOOL",
    "BLACKBURN",
    "HUDDERSFIELD",
    "STOCKPORT",
    "ROTHERHAM",
    "SWINDON",
    "NORTHAMPTON",
    "SLOUGH",
    "ST HELIER",
    "ST PETER PORT",
    "DOUGLAS",
}

UK_BUILDING_INDICATORS: Set[str] = {
    "COURT",
    "HOUSE",
    "MANSIONS",
    "MANSION",
    "TOWER",
    "TOWERS",
    "CHAMBERS",
    "HALL",
    "LODGE",
    "COTTAGE",
    "VILLA",
    "VILLAS",
    "BUILDING",
    "BUILDINGS",
    "CENTRE",
    "CENTER",
    "WHARF",
    "MEWS",
    "PRIORY",
    "MANOR",
    "GRANGE",
    "CASTLE",
    "PALACE",
}


RE_PO_BOX_WITH_UNIT = re.compile(
    r"^(?:P\.?O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX)\s+([A-Z0-9\-]+)[,\s]+"
    r"((?:SUITE|STE|FLAT|APT|APARTMENT|UNIT|FLOOR|FL|ROOM|RM)\s*#?\s*[A-Z0-9\-]+)$",
    re.IGNORECASE,
)


def split_po_box_unit(line: str) -> Optional[Tuple[str, str]]:
    """"PO Box 309 Suite 100" -> ("PO BOX 309", "Suite 100"); None when the line is not a PO box plus a unit."""
    m = RE_PO_BOX_WITH_UNIT.match((line or "").strip())
    if not m:
        return None
    return f"PO BOX {m.group(1).upper()}", m.group(2).strip()


def is_uk_building_name(text: str) -> bool:
    """Returns True if text matches UK building / premise naming conventions."""
    if not text:
        return False
    clean = text.strip().upper()
    if clean.startswith("THE "):
        return True
    tokens = set(re.findall(r"[A-Z]+", clean))
    return bool(tokens & UK_BUILDING_INDICATORS)


def _is_name_directional(words: List[str], idx: int) -> bool:
    """A leading North/South/East/West followed by a further name word ("North Western Arcade", "West Register
    Street") belongs to the street name; Royal Mail does not abbreviate it ("North Street" -> "N ST" is kept)."""
    return idx == 0 and len(words) >= 3 and RE_NON_ALPHANUMERIC.sub("", words[1]).upper() not in STREET_SUFFIXES


# Royal Mail has no abbreviation for these; "Prospect Hill" must not become "PROSPECT HL".
_UK_KEEP_FULL = frozenset({"HILL", "HILLS", "ARCADE"})

DISALLOWED_OUTWARD_POS1 = {"Q", "V", "X"}
DISALLOWED_OUTWARD_POS2 = {"I", "J", "Z"}
DISALLOWED_INWARD_LETTERS = {"C", "I", "K", "M", "O", "V"}


def is_valid_uk_postcode(raw_code: str) -> bool:
    """Validate Royal Mail alphanumeric postcode format and character constraints."""
    if not raw_code:
        return False
    clean = " ".join(raw_code.strip().upper().split())
    if clean == "GIR 0AA":
        return True

    m = RE_UK_POSTCODE_EXACT.match(clean)
    if not m:
        return False

    outward = m.group(1).upper()
    inward = m.group(2).upper()

    if len(outward) >= 1 and outward[0] in DISALLOWED_OUTWARD_POS1:
        return False
    if len(outward) >= 2 and outward[1].isalpha() and outward[1] in DISALLOWED_OUTWARD_POS2:
        return False

    # The regex guarantees a 3-character inward code (digit + two letters).
    if inward[1] in DISALLOWED_INWARD_LETTERS or inward[2] in DISALLOWED_INWARD_LETTERS:
        return False

    return True


# Further well-known towns/cities, used only to find where the city starts in a comma-less line.
_UK_SPLIT_EXTRA_TOWNS: Set[str] = {
    "BARNSLEY", "BASINGSTOKE", "BEDFORD", "BRACKNELL", "BURNLEY", "CHELTENHAM", "CRAWLEY", "DARLINGTON", "DUDLEY",
    "EASTBOURNE", "GATESHEAD", "GUILDFORD", "HARROGATE", "HASTINGS", "HIGH WYCOMBE", "HUDDERSFIELD", "KEIGHLEY",
    "MAIDSTONE", "MIDDLESBROUGH", "NEWRY", "OLDHAM", "POOLE", "ROCHDALE", "SCUNTHORPE", "SOLIHULL", "STAFFORD",
    "TELFORD", "TORQUAY", "WALSALL", "WARRINGTON", "WATFORD", "WEST BROMWICH", "WIGAN", "WINDSOR", "WORTHING",
    "LISBURN", "LONDONDERRY", "BANGOR", "NEWTOWNABBEY", "EAST KILBRIDE", "PAISLEY", "FALKIRK", "KIRKCALDY",
}

# Words that end a street name in a comma-less "10 High Street Leeds LS1 4AB" (never "ST": "St Ives" is a town).
_COMMALESS_TYPE_WORDS = (UNAMBIGUOUS_STREET_TYPES - {"ST"}) | {
    "CLOSE", "GROVE", "MEWS", "QUAY", "ARCADE", "PARADE", "RISE", "WALK", "MALL", "CRESCENT", "TERRACE", "SQUARE",
}
_RE_CITY_WORD = re.compile(r"[^\W\d_][\w'.\-]*")
_RE_HAS_LETTER = re.compile(r"[^\W\d_]")


_RE_UK_TRAILING_COUNTRY = re.compile(
    r"\s+(?:UNITED\s+KINGDOM|GREAT\s+BRITAIN|NORTHERN\s+IRELAND|ENGLAND|SCOTLAND|WALES|UK|GBR|GB)\s*$", re.IGNORECASE
)


def trailing_postal_width(words: "List[str]", is_postal: "Callable[[str], bool]") -> Optional[int]:
    """Number of trailing words (2 or 1) that form a postal code, with at least one word left over; else None."""
    for width in (2, 1):
        if len(words) > width + 1 and is_postal(" ".join(words[-width:])):
            return width
    return None


def split_commaless_postal_city(
    text: str,
    is_postal: "Callable[[str], bool]",
    towns: "Set[str]",
    country_tail: "re.Pattern[str]" = _RE_UK_TRAILING_COUNTRY,
    type_words: "Set[str] | frozenset[str]" = _COMMALESS_TYPE_WORDS,
    suffix_directionals: "Set[str] | frozenset[str]" = frozenset(),
    prefix_types: "Set[str] | frozenset[str]" = frozenset(),
) -> Optional[Tuple[str, str, str]]:
    """Split a comma-less "10 High Street Leeds LS1 4AB" into (street, city, postal code); None when there is no
    trailing postal code. Precision over recall: the city is only returned when it is a known town (longest suffix)
    or the one-to-three plain words after the last street-type word; otherwise the city stays empty (inside street).

    ``type_words`` are the words that end a street name; ``suffix_directionals`` (Canada: WEST, OUEST...) are
    directions that belong to the street when they directly follow the type word and are followed by the city;
    ``prefix_types`` (Canada: RUE, AVENUE...) are type words that, standing right after the house number, begin the
    street name rather than end it and therefore are no boundary.
    """
    words = country_tail.sub("", text).split()
    width = trailing_postal_width(words, is_postal)
    if width is None:
        return None
    postal = " ".join(words[-width:])
    rest = words[:-width]
    if not _RE_HAS_LETTER.search(" ".join(rest)):
        return None
    for n in (4, 3, 2, 1):
        if len(rest) > n and " ".join(rest[-n:]).upper() in towns and _RE_HAS_LETTER.search(" ".join(rest[:-n])):
            return " ".join(rest[:-n]), " ".join(rest[-n:]), postal
    anchors = [
        i for i, w in enumerate(rest)
        if RE_NON_ALPHANUMERIC.sub("", w).upper() in type_words
        and not (RE_NON_ALPHANUMERIC.sub("", w).upper() in prefix_types and not _RE_HAS_LETTER.search(" ".join(rest[:i])))
    ]
    if anchors:
        end = anchors[-1] + 1
        tail = rest[end:]
        first = RE_NON_ALPHANUMERIC.sub("", tail[0]).upper() if tail else ""
        if first in suffix_directionals and len(tail) >= 2:
            end += 1
            tail = tail[1:]
            first = RE_NON_ALPHANUMERIC.sub("", tail[0]).upper()
        if (
            1 <= len(tail) <= 3
            and first not in DIRECTIONALS
            and first not in ("LOWER", "UPPER")
            and all(_RE_CITY_WORD.fullmatch(w) for w in tail)
        ):
            return " ".join(rest[:end]), " ".join(tail), postal
    return " ".join(rest), "", postal


class UKGrammar(CountryGrammar):
    """Royal Mail PAF / BS 7666 compliant United Kingdom grammar."""

    country_iso3: ClassVar[str] = "GBR"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "GBR", "UK", "UNITED KINGDOM",
        "JEY", "JERSEY",
        "GGY", "GUERNSEY",
        "IMN", "ISLE OF MAN",
        "GIB", "GIBRALTAR",
        "FLK", "FALKLAND ISLANDS",
        "SHN", "SAINT HELENA",
        "PCN", "PITCAIRN",
        "IOT", "BRITISH INDIAN OCEAN TERRITORY",
        "SGS", "SOUTH GEORGIA",
        "MLT", "MALTA",
        "CYP", "CYPRUS",
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
    ) -> UKParsedAddressComponents:
        """Standardize; a comma-less "10 High Street Leeds LS1 4AB" is split at its trailing postcode first."""
        if street1 and not (city or state or postal_code) and "," not in street1:
            split = split_commaless_postal_city(street1, is_valid_uk_postcode, UK_POST_TOWNS | _UK_SPLIT_EXTRA_TOWNS)
            if split is not None:
                street1, city, postal_code = split
        return super().standardize(street1, street2, city, state, postal_code, country, raw_street_address)

    def normalize_postal_code(self, raw_code: str) -> str:
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())
        # Strip permitted country / jurisdiction prefixes (e.g. "GB-JE2 3RP", "UK-GY1 1AA")
        clean = re.sub(r"^(?:GB|UK|JEY|GGY|IMN)[-\s]+", "", clean, flags=re.IGNORECASE)
        # Normalize hyphenated area codes (e.g. "JE-2 3RP" -> "JE2 3RP")
        clean = re.sub(r"^(JE|GY|IM)-(\d)", r"\1\2", clean, flags=re.IGNORECASE)
        m = RE_UK_POSTCODE_EXACT.match(clean)
        if m:
            outward = m.group(1).upper()
            inward = m.group(2).upper()
            return f"{outward} {inward}"
        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise_name, street_number, street_name) from UK thoroughfare line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()
        premise: Optional[str] = None
        st_num: Optional[str] = None
        st_name: Optional[str] = None

        if "," in line:
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) >= 2:
                # Part 0 is potential premise name
                m_num0 = re.match(r"^(\d+[A-Za-z0-9\-\/]*)\s+(.*)$", parts[0])
                if not m_num0:
                    premise = parts[0].upper()
                    rest = ", ".join(parts[1:])
                else:
                    rest = line
            else:
                rest = line
        else:
            rest = line

        # Split remaining into street number and street name
        m_num = re.match(r"^(\d+[A-Za-z0-9\-\/]*)\s+(.*)$", rest.strip())
        if m_num:
            st_num = m_num.group(1).upper()
            st_name = self._normalize_street_tokens(m_num.group(2))
        else:
            cand = self._normalize_street_tokens(rest)
            # If cand is purely numeric, orphan token, or invalid thoroughfare, do not treat as street name
            if re.match(r"^\d+[A-Za-z]?$", cand) or cand in ("UP", "DUO", "BO", "GDN", "LB", "FLT", "LHS", "RHS", "TOR") or is_invalid_thoroughfare(cand):
                st_name = None
                premise = cand if not premise else premise
            else:
                st_name = cand

        return premise, st_num, st_name

    def _normalize_street_tokens(self, text: str) -> str:
        """Normalizes thoroughfare tokens while preserving double-barrelled hyphens."""
        if not text:
            return ""
        words = text.strip().split()
        norm_words: List[str] = []
        type_idx = street_type_index(words)
        for idx, w in enumerate(words):
            if "-" in w and any(c.isalpha() for c in w):
                subparts = w.split("-")
                norm_sub = []
                for sub_idx, sp in enumerate(subparts):
                    sp_clean = RE_NON_ALPHANUMERIC.sub("", sp).upper()
                    if sub_idx == len(subparts) - 1 and sp_clean in STREET_SUFFIXES and sp_clean not in _UK_KEEP_FULL and may_abbreviate_street_type(sp_clean, idx, type_idx, allow_first=True):
                        norm_sub.append(STREET_SUFFIXES[sp_clean])
                    elif sp_clean in DIRECTIONALS:
                        norm_sub.append(DIRECTIONALS[sp_clean])
                    else:
                        norm_sub.append(sp.upper())
                norm_words.append("-".join(norm_sub))
            else:
                w_clean = RE_NON_ALPHANUMERIC.sub("", w).upper()
                if w_clean in STREET_SUFFIXES and w_clean not in _UK_KEEP_FULL and may_abbreviate_street_type(w_clean, idx, type_idx):
                    norm_words.append(STREET_SUFFIXES[w_clean])
                elif w_clean in DIRECTIONALS and not _is_name_directional(words, idx):
                    norm_words.append(DIRECTIONALS[w_clean])
                else:
                    norm_words.append(w.upper())
        return " ".join(norm_words)

    def parse(self, raw_tokens: List[str], metadata: dict) -> UKParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        country_iso = metadata.get("country", self.country_iso3)

        unit_type: Optional[str] = None
        unit_number: Optional[str] = None
        building_name: Optional[str] = None
        dep_locality: Optional[str] = None
        if s1_raw and not s2_raw:
            po_split = split_po_box_unit(s1_raw)
            if po_split:
                s1_raw, s2_raw = po_split
        street_line = s1_raw

        # Handle single-line comma-separated address when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts_comma = [p.strip() for p in s1_raw.split(",") if p.strip()]
            if len(parts_comma) >= 2:
                last_up = parts_comma[-1].upper()
                if last_up in (
                    "UK", "GBR", "UNITED KINGDOM", "ENGLAND", "SCOTLAND", "WALES",
                    "JERSEY", "GUERNSEY", "ISLE OF MAN", "JEY", "GGY", "IMN"
                ):
                    parts_comma = parts_comma[:-1]

            # Check if last token is UK postcode
            if parts_comma and (
                RE_UK_POSTCODE_EXACT.match(parts_comma[-1])
                or RE_UK_POSTCODE_SEARCH.search(parts_comma[-1])
            ):
                m_post = RE_UK_POSTCODE_SEARCH.search(parts_comma[-1])
                if m_post:
                    postal_raw = m_post.group(1)
                    rem = parts_comma[-1][:m_post.start()].strip()
                    if rem:
                        parts_comma[-1] = rem
                    else:
                        parts_comma = parts_comma[:-1]

            # Pre-check if any part is secondary unit (e.g. "Flat 3" or post-street "Flat 2")
            new_parts: List[str] = []
            for part in parts_comma:
                m_f = re.match(
                    r"^(?:FLAT|APT|UNIT|SUITE|STE)\s*#?\s*([A-Za-z0-9\-]+)$",
                    part.strip(),
                    re.IGNORECASE,
                )
                if m_f and not unit_number:
                    p_type = part.strip().split()[0].upper()
                    unit_type = SECONDARY_UNITS.get(p_type, "APT" if p_type == "FLAT" else p_type)
                    unit_number = m_f.group(1).upper()
                else:
                    new_parts.append(part)
            parts_comma = new_parts

            if not parts_comma:
                # Everything was a postcode / unit; do not re-parse the raw line as a thoroughfare.
                street_line = ""
            elif len(parts_comma) == 1:
                p0 = parts_comma[0].strip().upper()
                if p0 in UK_POST_TOWNS:
                    city_raw = parts_comma[0]
                    street_line = ""
                else:
                    street_line = parts_comma[0]
            elif len(parts_comma) == 2:
                p0 = parts_comma[0].strip()
                p1 = parts_comma[1].strip()
                p1_upper = p1.upper()
                p1_tokens = p1_upper.split()
                if re.match(r"^\d+[A-Z]?$", p0) and (
                    p1_upper in STREET_SUFFIXES
                    or (p1_tokens and p1_tokens[-1] in STREET_SUFFIXES)
                    or p1_upper not in UK_POST_TOWNS
                ):
                    street_line = f"{p0} {p1}"
                    city_raw = ""
                else:
                    street_line = p0
                    city_raw = p1
            else:  # three or more parts
                last_token = parts_comma[-1].strip().upper()
                if last_token in UK_POST_TOWNS:
                    city_raw = parts_comma[-1]
                    # Check if first part is street number and second is thoroughfare (e.g. "93, QUEEN STREET, LEEDS")
                    if len(parts_comma) == 3 and re.match(r"^\d+[A-Z]?$", parts_comma[0].strip()):
                        street_line = f"{parts_comma[0].strip()} {parts_comma[1].strip()}"
                    else:
                        m_num_prev = re.match(r"^\d+", parts_comma[-2].strip())
                        if m_num_prev:
                            # parts_comma[-2] is thoroughfare, parts_comma[0] is building
                            building_name = parts_comma[0].upper()
                            street_line = ", ".join(parts_comma[1:-1])
                        else:
                            dep_locality = parts_comma[-2].strip().upper()
                            street_line = ", ".join(parts_comma[:-2])
                else:
                    city_raw = parts_comma[-1]
                    street_line = ", ".join(parts_comma[:-1])

        # Handle s2_raw: classify non-unit as building_name or dependent_locality, or extract unit
        if s2_raw:
            m_s2 = RE_INTL_SEC_START.match(s2_raw.strip())
            if m_s2:
                sec_type = m_s2.group(1).upper()
                unit_type = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
                sec_rest = m_s2.group(2).strip()
                m_id = re.match(r"^([A-Za-z0-9\-]+)[,\s]+(.*)$", sec_rest, re.IGNORECASE)
                if m_id:
                    unit_number = m_id.group(1).upper()
                    rest = m_id.group(2).strip()
                    if is_uk_building_name(rest) and not building_name:
                        building_name = rest.upper()
                    elif not dep_locality:
                        dep_locality = rest.upper()
                else:
                    unit_number = sec_rest.upper()
            else:
                if is_uk_building_name(s2_raw) and not building_name:
                    building_name = s2_raw.strip().upper()
                elif not dep_locality:
                    dep_locality = s2_raw.strip().upper()

        # Pre-split leading or inline secondary unit from street_line if not already found
        if not unit_number and street_line:
            m_multi = re.match(
                r"^(?:FLAT|FLATS|APT|APTS|UNIT|UNITS|SUITE|STE)\s*#?\s*([A-Z0-9]+(?:[\/\-&]|(?:\s+(?:&|AND|-)\s+))[A-Z0-9]+)(?:[,\s]+(.*))?$",
                street_line,
                re.IGNORECASE,
            )
            m_floor_unit = re.match(
                r"^(?:TOP|GROUND|BASEMENT|LOWER\s+GROUND|FIRST|SECOND|THIRD|FOURTH|GARDEN|GDN)\s+(?:FLOOR|FLR)?\s*(?:FLAT|APT|UNIT)\s*(?:NO\.?|#)?\s*([A-Za-z0-9\-\/]+)?(?:[,\s]+(.*))?$",
                street_line,
                re.IGNORECASE,
            )
            m_flat = RE_INTL_FLAT.match(street_line)
            m_sec = RE_INTL_SEC_START.match(street_line)
            m_ord = re.match(r"^(\d+(?:ST|ND|RD|TH)|\d+)\s+(?:FLOOR|FL|FLR)\b(?:\s+(WEST|EAST|NORTH|SOUTH))?(?:[,\s]+(.*))?$", street_line, re.IGNORECASE)
            if m_multi:
                unit_type = "APT" if m_multi.group(0).upper().startswith("FLAT") else "UNIT"
                unit_number = m_multi.group(1).upper()
                street_line = (m_multi.group(2) or "").strip(" ,.-")
            elif m_floor_unit:
                unit_type = "APT"
                u_val = m_floor_unit.group(1)
                unit_number = u_val.upper() if u_val else street_line.split()[0].upper()
                street_line = (m_floor_unit.group(2) or "").strip(" ,.-")
            elif m_flat:
                unit_type = "APT"
                cand_id = m_flat.group(1).upper()
                cand_rest = m_flat.group(2).strip()
                m_sub = re.match(r"^\(?([A-Za-z0-9\-]+)\)?$", cand_rest)
                if m_sub and len(m_sub.group(1)) <= 2:
                    unit_number = f"{cand_id}{m_sub.group(1).upper()}"
                    street_line = ""
                else:
                    unit_number = cand_id
                    street_line = cand_rest
            elif m_ord:
                unit_type = "FL"
                fl_num = m_ord.group(1).upper()
                wing = f" {m_ord.group(2).upper()}" if m_ord.group(2) else ""
                unit_number = f"{fl_num}{wing}"
                rem_street = (m_ord.group(3) or "").strip(" ,.-")
                if rem_street.upper() in ("FLAT", "FLATS", "APT", "APTS", "UNIT", "UNITS", "LHS", "RHS"):
                    unit_type = "APT" if "FLAT" in rem_street.upper() or "APT" in rem_street.upper() else "FL"
                    unit_number = f"{fl_num} {rem_street.upper()}"
                    street_line = ""
                else:
                    street_line = rem_street
                if not street_line and dep_locality:
                    street_line = dep_locality
                    dep_locality = None
            elif m_sec:
                sec_type = m_sec.group(1).upper()
                sec_rest = m_sec.group(2).strip()
                if sec_type == "PO BOX":
                    unit_type = "PO BOX"
                    if "," in sec_rest:
                        p_pob, p_thoro = [p.strip() for p in sec_rest.split(",", 1)]
                        unit_number = p_pob.upper()
                        street_line = p_thoro
                    else:
                        unit_number = sec_rest.upper()
                        street_line = ""
                else:
                    m_id = re.match(r"^([A-Z0-9\-]+)[,\s]+(.*)$", sec_rest, re.IGNORECASE)
                    if m_id:
                        sec_type_norm = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
                        unit_type = sec_type_norm
                        cand_id = m_id.group(1).upper()
                        cand_rest = m_id.group(2).strip()
                        if len(cand_rest) == 1 and cand_rest.isalpha():
                            unit_number = f"{cand_id}{cand_rest.upper()}"
                            street_line = ""
                        else:
                            unit_number = cand_id
                            street_line = cand_rest
                    else:
                        sec_type_norm = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
                        unit_type = sec_type_norm
                        unit_number = sec_rest.upper()
                        street_line = ""
            elif RE_INTL_SEC_INLINE.search(street_line):
                    m_inline = RE_INTL_SEC_INLINE.search(street_line)
                    sec_type = m_inline.group(1).upper()
                    sec_type_norm = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
                    unit_type = sec_type_norm
                    unit_number = m_inline.group(2).upper()
                    street_line = street_line[:m_inline.start()] + street_line[m_inline.end():]
                    street_line = RE_WHITESPACE.sub(" ", street_line.strip(" ,.-"))

        # "14 High Street, Headingley" with a separate city: the trailing part is a dependent locality (or premise).
        if city_raw and street_line and "," in street_line:
            seg = [p.strip() for p in street_line.split(",") if p.strip()]
            if len(seg) == 2 and re.match(r"^\d+[A-Za-z]?\s+\S", seg[0]) and not re.search(r"\d", seg[1]):
                if is_uk_building_name(seg[1]):
                    pass  # premise-like tails keep their existing handling
                elif not dep_locality and seg[1].upper() != RE_WHITESPACE.sub(" ", city_raw.strip().upper()):
                    dep_locality = seg[1].upper()
                    street_line = seg[0]

        premise, st_num, st_name = self.extract_premise_and_thoroughfare(street_line)
        if not building_name and premise:
            building_name = premise

        norm_postal = self.normalize_postal_code(postal_raw)
        norm_city = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
        norm_state = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", state_raw).strip().upper())

        return UKParsedAddressComponents(
            street_number=st_num,
            street_name=st_name,
            unit_type=unit_type,
            unit_number=unit_number,
            building_name=building_name,
            dependent_locality=dep_locality,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
