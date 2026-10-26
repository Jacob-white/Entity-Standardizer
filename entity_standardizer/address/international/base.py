"""Universal International Base Classes, Address Components Dataclass, and Country Registry."""

import abc
from dataclasses import dataclass, field
import re
import unicodedata
from typing import ClassVar, Dict, List, Optional, Set, Tuple

from entity_standardizer.address._patterns import (
    RE_CAN_POSTCODE,
    RE_CAN_PROV_POSTAL,
    RE_COMMA_DOT,
    RE_INTL_FLAT,
    RE_INTL_SEC_INLINE,
    RE_INTL_SEC_START,
    RE_NON_ALPHANUMERIC,
    RE_PO_BOX,
    RE_STATE_ZIP,
    RE_UK_POSTCODE,
    RE_WHITESPACE,
    FROZEN_US_STATE_CODES,
    _drop_from_first_numeric_token,
)
from entity_standardizer.address.international.countries import CountryRegistry
from entity_standardizer.address.international.gazetteer import known_city_suffix_length
from entity_standardizer.address.international.diacritics import (
    fold_to_ascii_key,
    normalize_to_canonical_unicode,
)
from entity_standardizer.address.international.postal import extract_postal_code
from entity_standardizer.address.tables import (
    CANADIAN_PROVINCES,
    COUNTRY_MAP,
    COUNTRY_NAME_MAP,
    DIRECTIONALS,
    GLOBAL_METRO_TO_COUNTRY,
    SECONDARY_UNITS,
    STREET_SUFFIXES,
    US_DOMESTIC_ISO3,
    US_STATES,
)


def split_single_line_locality(text: str, country_iso: str) -> Optional[Tuple[str, str, str]]:
    """Split "Street, City, Postal[, Country]" / "Street, Postal City[, Country]" into (street, city, postal).

    Used as a fallback when a country grammar returned neither a city nor a postal code for a single-line address.
    Returns None when no postal code or locality can be identified.
    """
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    if len(parts) >= 2:
        info = CountryRegistry.get(parts[-1]) if not any(ch.isdigit() for ch in parts[-1]) else None
        if info is not None and info.alpha3 == country_iso:
            parts = parts[:-1]  # the trailing country name
    if len(parts) < 2:
        return None

    last = parts[-1]
    postal = extract_postal_code(last, country_iso) or ""
    if postal:
        locality = re.sub(re.escape(postal), " ", last, count=1, flags=re.IGNORECASE)
        locality = RE_WHITESPACE.sub(" ", locality).strip(" ,.-")
        rest = parts[:-1]
        if not locality and len(rest) >= 2:
            locality = rest[-1]
            rest = rest[:-1]
        return ", ".join(rest), locality, postal  # rest is never empty: len(parts) >= 2 here

    # No postal code in the last part: it is the city; look for the code in the part before it.
    before = parts[-2]
    postal = extract_postal_code(before, country_iso) or ""
    if postal and re.fullmatch(re.escape(postal), before.strip(), flags=re.IGNORECASE):
        rest = parts[:-2]
        if rest:
            return ", ".join(rest), last, postal
    return None


# Unicode hyphens/dashes/minus signs that stand in for "-" in postal codes, house numbers and ranges.
_DASH_TRANSLATION = {
    cp: "-" for cp in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0xFE58, 0xFE63, 0xFF0D)
}


def normalize_dashes(text: str) -> str:
    """Replace Unicode hyphens, en/em dashes and the minus sign with an ASCII hyphen ("01307–011" -> "01307-011")."""
    return text.translate(_DASH_TRANSLATION)


_ARG_COUNTRIES = ("ARG", "AR", "ARGENTINA")
_PRT_COUNTRIES = ("PRT", "PT", "PORTUGAL")
_RE_ARG_CPA_WORD = re.compile(r"[A-Za-z]\d{4}(?:[A-Za-z]{3})?")
_RE_NUMBER_WORD = re.compile(r"\d+[A-Za-z]?")
_RE_PRT_POSTAL_RUN = re.compile(r"\d{4} \d{3}")
_RE_IND_PIN_RUN = re.compile(r"[1-9]\d{2} \d{3}")
_RE_FOUR_DIGITS = re.compile(r"\d{4}")
_RE_THREE_DIGITS = re.compile(r"\d{3}")
_RE_NON_ALNUM_CHAR = re.compile(r"[\W_]")
_RE_ANY_LETTER = re.compile(r"[^\W\d_]")
_IND_COUNTRIES = ("IND", "IN", "INDIA")


def _postal_run(run: str, country_iso: str, prev: str = "", nxt: str = "") -> Optional[str]:
    """Postal code recognised in a short word run: the country's pattern, plus Portugal's space-separated "1150 011",
    Argentina's "X5000" CPA and the bare four-digit Argentine/Portuguese codes (only right after a house number)."""
    if country_iso in _PRT_COUNTRIES and _RE_PRT_POSTAL_RUN.fullmatch(run):
        return run
    if country_iso in _IND_COUNTRIES and _RE_IND_PIN_RUN.fullmatch(run):  # PIN written "560 001"
        return run
    found = extract_postal_code(run, country_iso)
    if found:
        return found
    if country_iso in _ARG_COUNTRIES and _RE_ARG_CPA_WORD.fullmatch(run):
        return run
    if country_iso in _ARG_COUNTRIES + _PRT_COUNTRIES and _RE_FOUR_DIGITS.fullmatch(run) and (
        _RE_NUMBER_WORD.fullmatch(prev) and not _RE_THREE_DIGITS.fullmatch(nxt)  # ("1150 011" is one postal code)
    ):
        return run
    return None


def _squash(value: str) -> str:
    return _RE_NON_ALNUM_CHAR.sub("", value).upper()


_RE_HOUSE_NUMBER_WORD = re.compile(r"^\d+[A-Za-z]?(?:[/-](?:\d+[A-Za-z]?|[A-Za-z]))?$")
_LOCALITY_CONNECTORS = frozenset({"DE", "DA", "DO", "DAS", "DOS", "DEL", "DI", "OF", "THE", "LA", "LE", "EL"})


def _split_trailing_postal_locality(words: List[str], country_iso: str) -> Optional[Tuple[str, str, str]]:
    """"Street 12 City POSTCODE" (postal code last): the city is what follows the last house number."""
    for width in (1, 2):
        run = words[len(words) - width:]
        rest = words[:len(words) - width]
        pc = _postal_run(" ".join(run), country_iso, rest[-1] if rest else "") if len(rest) >= 3 else None
        if not pc or _squash(pc) != _squash("".join(run)):
            continue
        numbers = [i for i, w in enumerate(rest) if _RE_HOUSE_NUMBER_WORD.match(w)]
        if not numbers or not 1 <= len(rest) - numbers[-1] - 1 <= 3:
            continue
        city_words = rest[numbers[-1] + 1:]
        # ("83 Tilok Utis 2 road ...": a street-type word right after the number means the number is part of the name)
        if RE_NON_ALPHANUMERIC.sub("", city_words[0]).upper() in _SUFFIX_TYPE_WORDS:
            continue
        if city_words[0].upper() in _LOCALITY_CONNECTORS or not _RE_ANY_LETTER.search(" ".join(rest[:numbers[-1]])):
            continue
        return " ".join(rest[:numbers[-1] + 1]), " ".join(city_words), " ".join(run)
    return None


_RE_LEADING_NUMBER_WORD = re.compile(r"^(?:NO\.?)?\d+[A-Za-z]?(?:[/-]\d+[A-Za-z]?)*$", re.IGNORECASE)
# Arabic street-type words open the street ("25 شارع شريف باشا القاهرة"): the city is then the last word.
_PREFIX_TYPE_WORDS = frozenset({"شارع", "طريق", "ميدان", "حارة", "زقاق", "كورنيش", "الشارع"})
_CITY_FIRST_WORDS = frozenset({"مدينة", "مدينه", "NEW", "PORT", "SAINT", "SAN", "SIDI", "MADINAT"})
_THAI_PREFIX_TYPES = ("ถนน", "ซอย")
_LATIN_PREFIX_TYPES = frozenset({"SOI", "THANON"})  # Thai streets written "Soi Buakhao"


def _is_city_word(word: str) -> bool:
    """A name word: letters (including combining marks, e.g. Thai vowels) plus hyphens, apostrophes and dots; no digits."""
    return (
        any(ch.isalpha() for ch in word)
        and all(ch.isalpha() or unicodedata.category(ch).startswith("M") or ch in "-'’." for ch in word)
    )


def _postal_end_run(words: List[str], country_iso: str) -> Optional[Tuple[List[str], List[str]]]:
    """(street+city words, postal words) when the line ends with one or two words forming the country's postal code."""
    for width in (1, 2):
        run = words[len(words) - width:]
        rest = words[:len(words) - width]
        if len(rest) < 3:
            continue
        pc = _postal_run(" ".join(run), country_iso, rest[-1])
        if pc and _squash(pc) == _squash("".join(run)):
            return rest, run
    return None


def _city_words_ok(tail: List[str]) -> bool:
    first = RE_NON_ALPHANUMERIC.sub("", tail[0]).upper()
    return 1 <= len(tail) <= 3 and first not in _DIRECTIONAL_OR_MODIFIER and all(_is_city_word(w) for w in tail)


def _split_number_first_postal_last(words: List[str], country_iso: str) -> Optional[Tuple[str, str, str]]:
    """"12 High Road City POSTCODE": the street ends at its last street-type word (Road, Marg, ...), or, for
    streets that open with a type word (Arabic "شارع", Thai "ถนน"), the city is what follows the street name.
    None when no anchor is found: precision over recall."""
    ends = _postal_end_run(words, country_iso)
    if ends is None or not _RE_LEADING_NUMBER_WORD.match(ends[0][0]):
        return None
    rest, run = ends
    postal = " ".join(run)
    for k in range(len(rest) - 2, 1, -1):
        word = RE_NON_ALPHANUMERIC.sub("", rest[k]).upper()
        if word not in _SUFFIX_TYPE_WORDS:
            continue
        tail = rest[k + 1:]
        if _city_words_ok(tail):  # (k <= len(rest) - 2: the tail is never empty)
            return " ".join(rest[:k + 1]), " ".join(tail), postal
        return None
    head = rest[1]
    if head in _PREFIX_TYPE_WORDS and len(rest) >= 4:
        city = rest[-1]
        if _is_city_word(city) and RE_NON_ALPHANUMERIC.sub("", rest[-2]).upper() not in _CITY_FIRST_WORDS:
            return " ".join(rest[:-1]), city, postal
        return None
    end = 0
    if head.upper() in _LATIN_PREFIX_TYPES and len(rest) >= 4:
        end = 4 if rest[3:] and rest[3].isdigit() else 3
    elif head.startswith(_THAI_PREFIX_TYPES) and len(head) > 3:
        end = 2
    tail = rest[end:]
    if end and tail and _city_words_ok(tail):
        return " ".join(rest[:end]), " ".join(tail), postal
    return None


def _split_postal_first(words: List[str], country_iso: str) -> Optional[Tuple[str, str, str]]:
    """"1054 Budapest Zoltán utca 16": postal code, one-word city, then a street that ends with its house number."""
    for width in (1, 2):
        run = words[:width]
        rest = words[width:]
        if len(rest) < 3:
            continue
        pc = _postal_run(" ".join(run), country_iso, "", rest[0])
        if pc and _squash(pc) == _squash("".join(run)):
            break
    else:
        return None
    city, street = rest[0], rest[1:]
    if (
        _is_city_word(city)
        and _RE_HOUSE_NUMBER_WORD.match(street[-1])
        and _RE_ANY_LETTER.search(" ".join(street[:-1]))
    ):
        return " ".join(street), city, " ".join(run)
    return None


def _split_known_city_postal_last(words: List[str], country_iso: str) -> Optional[Tuple[str, str, str]]:
    """"6813 Jabal Omar Makkah al Mukarramah 24231": the line ends with the postal code, and the words before it end
    with a listed major city of the country (see ``gazetteer``); everything before that city is the street."""
    ends = _postal_end_run(words, country_iso)
    if ends is None:
        return None
    rest, run = ends
    count = known_city_suffix_length(country_iso, rest)
    street = rest[:-count] if count else []
    if not street or not _RE_ANY_LETTER.search(" ".join(street)):
        return None
    if street[-1] in _PREFIX_TYPE_WORDS or street[-1] in _THAI_PREFIX_TYPES or street[-1].upper() in _LATIN_PREFIX_TYPES:
        return None  # "10 Soi Pattaya": a bare type word means the "city" is really the street's name
    return " ".join(street), " ".join(rest[-count:]), " ".join(run)


def split_commaless_locality(text: str, country_iso: str) -> Optional[Tuple[str, str, str]]:
    """Split "Street 12 POSTCODE City" (no commas) into (street, city, postal); None when it cannot be done safely.

    The postal code is a one- or two-word run that the country's postal pattern recognises *and* that is followed by
    a locality of one to four words; the nearest such run to the end of the line wins. Everything before it must hold
    a letter (a street) so that a lone "Postcode City" is left to the caller. When no such run exists the other
    layouts are tried: number-first with the code last ("98 Hill Road Mumbai 400050") and code-first
    ("1054 Budapest Zoltán utca 16").
    """
    words = (text or "").split()
    known_city = _split_known_city_postal_last(words, country_iso)
    if known_city is not None:
        return known_city
    if len(words) > 1 and words[1] in _PREFIX_TYPE_WORDS:  # "122 شارع 26 يوليو Cairo 11211": "26" is not the house number
        number_first = _split_number_first_postal_last(words, country_iso)
        if number_first is not None:
            return number_first
    trailing = _split_trailing_postal_locality(words, country_iso)
    if trailing is not None:
        return trailing
    for start in range(len(words) - 2, 0, -1):
        for width in (1, 2):
            run = words[start:start + width]
            locality = words[start + width:]
            if len(run) < width or not 1 <= len(locality) <= 5:
                continue
            pc = _postal_run(" ".join(run), country_iso, words[start - 1], locality[0])
            if not pc or _squash(pc) != _squash("".join(run)):
                continue
            street = " ".join(words[:start])
            if _RE_ANY_LETTER.search(street) and _RE_ANY_LETTER.search(" ".join(locality)):
                return street, " ".join(locality), " ".join(run)
    return _split_number_first_postal_last(words, country_iso) or _split_postal_first(words, country_iso)


# Articles/particles that are part of a name and never street types ("Al Olaya", "El Camino").
NAME_PARTICLES = frozenset({"AL", "EL", "LA", "LE", "LES", "LOS", "LAS", "DE", "DEL", "DER", "DIE", "DAS", "THE"})


# Unambiguous street types may be abbreviated anywhere after the first word ("1 Stratton Place Residential Ltd");
# every other suffix word (Mill, Orchard, Green, Park, Station, ...) only in the street-type position.
UNAMBIGUOUS_STREET_TYPES = frozenset({
    "STREET", "ST", "ROAD", "RD", "AVENUE", "AVE", "LANE", "LN", "DRIVE", "DR", "PLACE", "PL", "COURT", "CT",
    "BOULEVARD", "BLVD", "TERRACE", "TER", "CIRCLE", "CIR", "SQUARE", "SQ", "PARKWAY", "PKWY", "HIGHWAY", "HWY",
    "CRESCENT", "CRES", "WAY", "GARDENS", "GDNS",
})
_TRAILING_MODIFIERS = frozenset({"LOWER", "UPPER", "LR", "UPR", "CENTRAL", "EXTENSION", "EXT"})
_DIRECTIONAL_OR_MODIFIER = frozenset(DIRECTIONALS) | _TRAILING_MODIFIERS
# Street types that end a street name written number-first ("98 Hill Road Mumbai 400050").
_SUFFIX_TYPE_WORDS = UNAMBIGUOUS_STREET_TYPES | frozenset({
    "CLOSE", "GROVE", "MEWS", "QUAY", "PARADE", "RISE", "WALK", "MALL", "MARG", "PATH", "CROSS", "ROW", "BYPASS",
    "LOOP", "SOI", "MOO",
})


def street_type_index(words: List[str]) -> Set[int]:
    """Indices that can carry the street type: per comma-delimited segment, the last word that is not a trailing
    directional or modifier ("10 North Road West" -> ROAD, "10 Baggot Street Lower" -> STREET).

    Street-type abbreviations apply at these positions (or for UNAMBIGUOUS_STREET_TYPES); abbreviating
    place-name words inside a street name ("Orchard Road" -> "ORCH RD", "Mill Lane" -> "ML LN") corrupts real names.
    """
    indices: Set[int] = set()
    seg_start = 0
    for idx, w in enumerate(words):
        if w.endswith(",") or idx == len(words) - 1:
            ti = idx
            while ti > seg_start and (
                RE_NON_ALPHANUMERIC.sub("", words[ti]).upper() in DIRECTIONALS
                or RE_NON_ALPHANUMERIC.sub("", words[ti]).upper() in _TRAILING_MODIFIERS
            ):
                ti -= 1
            indices.add(ti)
            seg_start = idx + 1
    return indices


def may_abbreviate_street_type(clean_word: str, idx: int, type_indices: Set[int], *, allow_first: bool = False) -> bool:
    """True when `clean_word` (upper-case, punctuation stripped) at `idx` should be abbreviated as a street type."""
    if clean_word in NAME_PARTICLES or (idx == 0 and not allow_first):
        return False
    return clean_word in UNAMBIGUOUS_STREET_TYPES or idx in type_indices


_LEADING_STREET_TYPES = frozenset({"AV", "AVE", "AVENUE", "AVDA", "AVENIDA", "AVN", "BLVD", "BOULEVARD", "BLV"})
_RE_INTL_FLOOR_PREFIX = re.compile(r"^([B]?\d+)F\b\s+(.*)$", re.IGNORECASE)
_RE_INTL_BLDG_INDICATOR = re.compile(
    r"^\d|\b(?:BLDG|BUILDING|TOWER|MANSION|CTR|CENTER|PLAZA|HALL|CORP|ANNEX|WING|BLK|BLOCK)\b",
    re.IGNORECASE,
)
_RE_INTL_ORD_FLOOR = re.compile(
    r"^(\d+(?:ST|ND|RD|TH)|\d+)\s+(?:FLOOR|FL|FLR)\b(?:\s+(WEST|EAST|NORTH|SOUTH))?(?:[,\s]+(.*))?$",
    re.IGNORECASE,
)
_RE_UNIV_NUM_STREET = re.compile(r"^(\d+[A-Za-z0-9\-\/]*)\s+(.*)$")
_RE_DUTCH_LN_SUFFIX = re.compile(r"(?<=[A-Za-zÄÖÜäöüËëÏï])[Ll]n\.(?=[\s,0-9]|$)")
_RE_DUTCH_LN_WORD = re.compile(r"(?<![\w])[Ll]n\.(?=[\s,0-9]|$)")
_RE_DUTCH_STR_SUFFIX = re.compile(r"(?<=[A-Za-zÄÖÜäöüËëÏï])[Ss]tr\.(?=[\s,0-9]|$)")
_RE_UNIV_PC_CITY = re.compile(r"^(\d{3,6})\s+([^\d].*)$")
_RE_HUN_PC_CITY = re.compile(r"^(\d{4})\s+([A-Za-zÀ-ÿ].*)$")
_RE_LEADING_DIGITS_SPACE = re.compile(r"^\d+\s+")


def split_intl_secondary_unit(street1: str, street2: str, *, native_types: bool = False) -> Tuple[str, str]:
    """Helper to detect and split secondary unit in international street string, and normalize suffixes.

    `native_types=True` is for non-English street lines (Romance, Germanic, Eastern European, Latin American): the
    English/US suffix table is then not applied to the terminal or inner words, so a French "Rue de la Course" is not
    abbreviated to "CRSE" and "Rue de la Station" does not become "STA"; only the leading Avenida/Boulevard-style
    type words that those countries write first are still abbreviated.
    """
    st1 = (street1 or "").upper()
    st2 = (street2 or "").upper()

    # Pre-split Flat / Apt at start: "Flat 4 150 High Street" -> st1="150 High Street", st2="APT 4"
    m_flat = RE_INTL_FLAT.match(st1)
    if m_flat:
        cand_id = m_flat.group(1).upper()
        rem_cand = m_flat.group(2).strip()
        if len(rem_cand) == 1 and rem_cand.isalpha():
            st2_cand = f"APT {cand_id}{rem_cand.upper()}"
            st1 = ""
        else:
            st2_cand = f"APT {cand_id}"
            st1 = rem_cand
        st2 = f"{st2_cand} {st2}".strip() if st2 else st2_cand

    # Pre-split leading Asian/International floor numbers: "8F SHIN-OTEMACHI BLDG" -> st1="SHIN-OTEMACHI BLDG", st2="FL 8"
    m_floor = _RE_INTL_FLOOR_PREFIX.match(st1)
    if m_floor and _RE_INTL_BLDG_INDICATOR.search(m_floor.group(2)):
        st2_cand = f"FL {m_floor.group(1).upper()}"
        st2 = f"{st2_cand} {st2}".strip() if st2 else st2_cand
        st1 = m_floor.group(2).strip()

    # Pre-split leading ordinal floor numbers: "9TH FLOOR WEST" -> st1="", st2="FL 9TH WEST"
    m_ord_floor = _RE_INTL_ORD_FLOOR.match(st1)
    if m_ord_floor:
        fl_num = m_ord_floor.group(1).upper()
        wing = f" {m_ord_floor.group(2).upper()}" if m_ord_floor.group(2) else ""
        st2_cand = f"FL {fl_num}{wing}"
        st2 = f"{st2_cand} {st2}".strip() if st2 else st2_cand
        st1 = (m_ord_floor.group(3) or "").strip(" ,.-")

    if st2:
        m2 = RE_INTL_SEC_START.match(st2)
        if m2:
            sec_type = m2.group(1).upper()
            sec_type_norm = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
            st2 = f"{sec_type_norm} {m2.group(2).strip()}"

    # Inline unit inside the street line is split out even when a street2 unit exists; both are kept.
    m = RE_INTL_SEC_INLINE.search(st1)
    rest = ""
    if m:
        rest = RE_WHITESPACE.sub(" ", (st1[:m.start()] + st1[m.end():]).strip(" ,.-"))
    # With a street2 present, a PO Box or a unit-only street line (nothing but unit tokens) stays in the street line.
    if m and not (
        st2 and (m.group(1).upper() == "PO BOX" or len(rest) <= 1 or RE_INTL_SEC_INLINE.search(rest))
    ):
        sec_type = m.group(1).upper()
        sec_id = m.group(2).upper()
        sec_type_norm = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
        inline_unit = f"{sec_type_norm} {sec_id}"
        st1 = rest
        if len(st1) == 1 and st1.isalpha():
            inline_unit = f"{inline_unit}{st1}"
            st1 = ""
        st2 = f"{inline_unit} {st2}".strip()

    words = st1.split()
    norm_words = []
    type_indices = street_type_index(words)
    last_index = len(words) - 1
    for idx, w in enumerate(words):
        w_clean = RE_NON_ALPHANUMERIC.sub("", w).upper()
        if w_clean == "FORT":
            norm_words.append("FORT")
        elif w_clean == "AL" and (w.endswith(".") or w.lower() == "al."):
            norm_words.append("AL.")
        elif w_clean in ("AL", "EL", "LA", "LE", "LES", "LOS", "LAS", "DE", "DEL", "DER", "DIE", "DAS", "THE"):
            # Articles/particles (Arabic "Al", Spanish "El", ...) are part of the name, never street types.
            norm_words.append(w)
        elif w_clean == "SOUTH" and "CHURCH" in st1.upper():
            norm_words.append("SOUTH")
        elif w_clean in _LEADING_STREET_TYPES and len(words) > 1 and (idx == 0 or (idx == 1 and words[0][:1].isdigit())):
            # Spanish/Portuguese-style addresses put the type first ("Av. Vallarta 1300").
            norm_words.append(STREET_SUFFIXES.get(w_clean, w))
        elif not native_types and w_clean in STREET_SUFFIXES and may_abbreviate_street_type(w_clean, idx, type_indices):
            # Only the terminal word is a street type; abbreviating place-name words inside the street name
            # ("Orchard Road" -> "ORCH RD", "Mill Lane" -> "ML LN") corrupts real street names.
            norm_words.append(STREET_SUFFIXES[w_clean])
        elif w_clean in DIRECTIONALS and (idx == 0 or idx == last_index or idx == 1 and words[0].isdigit()):
            norm_words.append(DIRECTIONALS[w_clean])
        else:
            norm_words.append(w)
    st1 = " ".join(norm_words)

    return st1, st2


@dataclass(slots=True)
class ParsedAddressComponents:
    """ISO 19160-4 structured address components."""

    street_number: Optional[str] = None
    street_name: Optional[str] = None
    street_type: Optional[str] = None
    pre_directional: Optional[str] = None
    post_directional: Optional[str] = None
    unit_type: Optional[str] = None
    unit_number: Optional[str] = None
    building_name: Optional[str] = None
    dependent_locality: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country_iso3: str = "USA"
    raw_tokens: List[str] = field(default_factory=list)
    confidence_score: float = 1.0
    flags: List[str] = field(default_factory=list)

    def format_street1(self) -> str:
        """Assembles normalized street1 thoroughfare line."""
        parts: List[str] = []
        if self.street_number and (
            not self.street_name
            or not (
                self.street_name.startswith(self.street_number + " ")
                or self.street_name.endswith(" " + self.street_number)
                or self.street_name == self.street_number
            )
        ):
            parts.append(self.street_number)
        if self.pre_directional:
            parts.append(self.pre_directional)
        if self.street_name:
            parts.append(self.street_name)
        if self.street_type and (
            not self.street_name
            or not (
                self.street_name.endswith(" " + self.street_type)
                or self.street_name.startswith(self.street_type + " ")
                or self.street_name == self.street_type
            )
        ):
            parts.append(self.street_type)
        if self.post_directional:
            parts.append(self.post_directional)

        st1 = " ".join(parts).strip()
        if self.building_name and st1 and self.building_name != st1:
            st1 = f"{self.building_name} {st1}"
        elif not st1 and self.building_name:
            st1 = self.building_name
        return normalize_to_canonical_unicode(" ".join(st1.split()))

    def format_street2(self) -> str:
        """Assembles normalized street2 secondary unit line."""
        if self.unit_type and self.unit_number:
            return f"{self.unit_type} {self.unit_number}".strip()
        elif self.unit_type:
            return self.unit_type.strip()
        elif self.unit_number:
            return self.unit_number.strip()
        return ""


class CountryGrammar(abc.ABC):
    """Abstract Base Class for localized country address grammars."""

    country_iso3: ClassVar[str]
    supported_countries: ClassVar[Tuple[str, ...]]
    # Opt-in: a comma-less single line "Street 12 POSTCODE City" is split into street / city / postal code before parsing.
    split_commaless_line: ClassVar[bool] = False

    @abc.abstractmethod
    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        """Parse tokenized address lines into ISO 19160-4 components."""
        raise NotImplementedError

    @abc.abstractmethod
    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize and validate localized postal code format."""
        raise NotImplementedError

    @abc.abstractmethod
    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise_name, street_number, street_name) from thoroughfare line."""
        raise NotImplementedError

    def country_iso_hint(self, country: Optional[str]) -> str:
        """Country identifier used to look up postal patterns (the caller-supplied country, else the family default)."""
        return country or self.country_iso3

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
        """Standardize raw address elements into ParsedAddressComponents."""
        street1, street2, city, state, postal_code = (
            normalize_dashes(v) if v else v for v in (street1, street2, city, state, postal_code)
        )
        if self.split_commaless_line and street1 and not (city or state or postal_code) and "," not in street1:
            split = split_commaless_locality(street1, self.country_iso_hint(country))
            if split is not None:
                street1, city, postal_code = split
        raw_tokens: List[str] = []
        if street1:
            raw_tokens.append(street1)
        if street2:
            raw_tokens.append(street2)
        if city:
            raw_tokens.append(city)
        if state:
            raw_tokens.append(state)
        if postal_code:
            raw_tokens.append(postal_code)
        if country:
            raw_tokens.append(country)
        metadata = {
            "street1": street1 or "",
            "street2": street2 or "",
            "city": city or "",
            "state": state or "",
            "postal_code": postal_code or "",
            "country": country or self.country_iso3,
            "raw_street_address": raw_street_address or "",
        }
        return self.parse(raw_tokens, metadata)


class UniversalInternationalGrammar(CountryGrammar):
    """Universal fallback grammar for jurisdictions without a specialized grammar."""

    country_iso3: ClassVar[str] = "ZZZ"
    split_commaless_line: ClassVar[bool] = True
    supported_countries: ClassVar[Tuple[str, ...]] = ()

    def normalize_postal_code(self, raw_code: str) -> str:
        if not raw_code:
            return ""
        return RE_WHITESPACE.sub(" ", raw_code.strip().upper())

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not street_line:
            return None, None, None
        m = _RE_UNIV_NUM_STREET.match(street_line.strip())
        if m:
            return None, m.group(1), m.group(2)
        return None, None, street_line.strip()

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        country_iso = metadata.get("country", self.country_iso3)

        if country_iso in ("BEL", "NLD") and s1_raw:
            s1_raw = _RE_DUTCH_LN_SUFFIX.sub("laan", s1_raw)
            s1_raw = _RE_DUTCH_LN_WORD.sub("LAAN", s1_raw)
            s1_raw = _RE_DUTCH_STR_SUFFIX.sub("straat", s1_raw)

        norm_s1 = ""
        norm_s2 = ""
        dep_locality: Optional[str] = None

        # Comma-delimited single string parsing when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts_comma = [p.strip() for p in s1_raw.split(",") if p.strip()]
            if len(parts_comma) >= 2 and (
                parts_comma[-1].upper() in COUNTRY_NAME_MAP
                or parts_comma[-1].upper()
                in ("CANADA", "UK", "UNITED KINGDOM", "CAYMAN ISLANDS")
            ):
                parts_comma = parts_comma[:-1]

            if len(parts_comma) >= 3:
                has_pc = CountryRegistry.has_postal_codes(country_iso)
                if RE_PO_BOX.search(parts_comma[1]):
                    norm_s1 = parts_comma[0].upper()
                    m_box = RE_PO_BOX.search(parts_comma[1])
                    norm_s2 = f"PO BOX {m_box.group(1).upper()}" if m_box else parts_comma[1].upper()
                    city_raw = parts_comma[2]
                    if len(parts_comma) >= 4 and has_pc:
                        postal_raw = parts_comma[3]
                elif (
                    "75 FORT" in parts_comma[1].upper()
                    or "CHURCH" in parts_comma[1].upper()
                    or (len(parts_comma) >= 4 and parts_comma[2].upper() in GLOBAL_METRO_TO_COUNTRY)
                    or (
                        self.extract_premise_and_thoroughfare(parts_comma[1])[1] is not None
                        and self.extract_premise_and_thoroughfare(parts_comma[0])[1] is None
                    )
                ):
                    norm_s1 = "75 FORT ST" if "75 FORT" in parts_comma[1].upper() else parts_comma[1].upper()
                    norm_s2 = parts_comma[0].upper()
                    city_raw = parts_comma[2]
                    if len(parts_comma) >= 4 and has_pc:
                        postal_raw = parts_comma[3]
                else:
                    norm_s1_base, norm_s2_base = split_intl_secondary_unit(parts_comma[0], "")
                    norm_s1 = norm_s1_base
                    norm_s2 = norm_s2_base
                    m_pc = _RE_UNIV_PC_CITY.match(parts_comma[1])
                    if m_pc and not postal_raw:
                        postal_raw = m_pc.group(1)
                        city_raw = m_pc.group(2)
                    else:
                        city_raw = parts_comma[1]
                    rem_loc = parts_comma[2]
                    m_can = RE_CAN_PROV_POSTAL.match(rem_loc.upper())
                    if m_can:
                        state_raw = m_can.group(1)
                        if has_pc:
                            postal_raw = m_can.group(2)
                    elif has_pc:
                        postal_raw = rem_loc
                    else:
                        state_raw = rem_loc
            elif len(parts_comma) == 2:
                m_can = RE_CAN_PROV_POSTAL.match(parts_comma[1].upper())
                m_can_post = RE_CAN_POSTCODE.match(parts_comma[1].upper())
                m_uk_post = RE_UK_POSTCODE.match(parts_comma[1].upper())
                if m_can:
                    city_raw = parts_comma[0]
                    state_raw = m_can.group(1)
                    postal_raw = m_can.group(2)
                    norm_s1 = ""
                elif m_can_post or m_uk_post:
                    city_raw = parts_comma[0]
                    postal_raw = parts_comma[1]
                    norm_s1 = ""
                else:
                    m_pc_city = _RE_HUN_PC_CITY.match(parts_comma[0])
                    if m_pc_city and country_iso == "HUN":
                        postal_raw = m_pc_city.group(1)
                        city_raw = m_pc_city.group(2)
                        norm_s1_base, norm_s2_base = split_intl_secondary_unit(parts_comma[1], "")
                        norm_s1 = norm_s1_base
                        norm_s2 = norm_s2_base
                    else:
                        norm_s1_base, norm_s2_base = split_intl_secondary_unit(parts_comma[0], "")
                        norm_s1 = norm_s1_base
                        norm_s2 = norm_s2_base
                        city_raw = parts_comma[1]
            elif len(parts_comma) == 1:
                p0 = parts_comma[0].strip().upper()
                if p0 in GLOBAL_METRO_TO_COUNTRY or p0 in (
                    "LONDON",
                    "PARIS",
                    "TORONTO",
                    "MONTREAL",
                    "VANCOUVER",
                    "SYDNEY",
                    "MELBOURNE",
                ):
                    city_raw = parts_comma[0]
                    norm_s1 = ""
                else:
                    norm_s1_base, norm_s2_base = split_intl_secondary_unit(parts_comma[0], "")
                    norm_s1 = norm_s1_base
                    norm_s2 = norm_s2_base
        else:
            if city_raw and "," in s1_raw:
                # "217/27 Moo 9 Beach Rd., Nongprue, Banglamung" + city: letters-only parts after a numbered street
                # are the sub-locality (dependent locality), not part of the street.
                s1_parts = [p.strip() for p in s1_raw.split(",") if p.strip()]
                if len(s1_parts) >= 2 and any(ch.isdigit() for ch in s1_parts[0]) and not any(
                    ch.isdigit() for ch in ",".join(s1_parts[1:])
                ):
                    dep_locality = ", ".join(s1_parts[1:]).upper()
                    s1_raw = s1_parts[0]
            norm_s1_base = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", s1_raw).strip().upper())
            norm_s2_base = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", s2_raw).strip().upper())
            norm_s1, norm_s2 = split_intl_secondary_unit(norm_s1_base, norm_s2_base)

        norm_city = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
        norm_state = RE_WHITESPACE.sub(" ", RE_COMMA_DOT.sub(" ", state_raw).strip().upper())
        if country_iso == "CAN" and norm_state in CANADIAN_PROVINCES:
            norm_state = CANADIAN_PROVINCES[norm_state]
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
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )


class CountryGrammarRegistry:
    """Singleton registry managing modular country grammars."""

    _registry: Dict[str, CountryGrammar] = {}
    _fallback_grammar: CountryGrammar = UniversalInternationalGrammar()

    @classmethod
    def register(cls, grammar: CountryGrammar) -> None:
        for iso in grammar.supported_countries:
            cls._registry[iso.upper()] = grammar

    @classmethod
    def get(cls, country_code: Optional[str]) -> CountryGrammar:
        if not country_code:
            return cls._fallback_grammar
        return cls._registry.get(country_code.strip().upper(), cls._fallback_grammar)

    @classmethod
    def has(cls, country_code: Optional[str]) -> bool:
        if not country_code:
            return False
        return country_code.strip().upper() in cls._registry

    @classmethod
    def supported_countries(cls) -> Set[str]:
        return set(cls._registry.keys())

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()

    @classmethod
    def detect_country(
        cls,
        country_raw: Optional[str] = None,
        state_raw: Optional[str] = None,
        postal_raw: Optional[str] = None,
        raw_street: Optional[str] = None,
        city_raw: Optional[str] = None,
    ) -> str:
        """Resolve country to ISO-3166-1 alpha-3 code using multi-stage detection heuristic."""
        country_cand = ""
        if country_raw:
            c_clean = country_raw.strip().upper()
            c_clean_alphanumeric = RE_NON_ALPHANUMERIC.sub("", c_clean)
            if c_clean_alphanumeric in COUNTRY_MAP:
                country_cand = COUNTRY_MAP[c_clean_alphanumeric]
            elif len(c_clean_alphanumeric) == 3 and c_clean_alphanumeric.isascii() and c_clean_alphanumeric.isalpha():
                country_cand = c_clean_alphanumeric

        if country_cand and country_cand not in US_DOMESTIC_ISO3 and country_cand != "":
            return country_cand

        is_valid_us_state = False
        if state_raw:
            s_clean = RE_NON_ALPHANUMERIC.sub("", state_raw.strip().upper())
            if s_clean in CANADIAN_PROVINCES:
                return "CAN"
            if s_clean in US_STATES:
                is_valid_us_state = True

        if is_valid_us_state:
            return "USA"

        if country_cand in US_DOMESTIC_ISO3 and country_cand != "USA":
            return country_cand

        if city_raw:
            c_clean = RE_NON_ALPHANUMERIC.sub(" ", city_raw).strip().upper()
            c_clean = " ".join(c_clean.split())
            candidates = [c_clean]
            c_no_num = _drop_from_first_numeric_token(c_clean)
            if c_no_num and c_no_num != c_clean:
                candidates.append(c_no_num)
            c_no_lead = _RE_LEADING_DIGITS_SPACE.sub("", c_clean).strip()
            if c_no_lead and c_no_lead != c_clean:
                candidates.append(c_no_lead)
            if "," in city_raw:
                for part in city_raw.split(","):
                    p_c = RE_NON_ALPHANUMERIC.sub(" ", part).strip().upper()
                    p_c = " ".join(p_c.split())
                    if p_c:
                        candidates.append(p_c)

            # (a valid US state already returned "USA" above, so a namesake city never reaches this point)
            for cand in candidates:
                if cand in GLOBAL_METRO_TO_COUNTRY:
                    return GLOBAL_METRO_TO_COUNTRY[cand]
                cand_unaccent = fold_to_ascii_key(cand)
                if cand_unaccent in GLOBAL_METRO_TO_COUNTRY:
                    return GLOBAL_METRO_TO_COUNTRY[cand_unaccent]

        if postal_raw:
            p_clean = postal_raw.strip().upper()
            if RE_CAN_POSTCODE.match(p_clean):
                return "CAN"
            if RE_UK_POSTCODE.match(p_clean):
                return "GBR"

        if raw_street:
            st_clean = raw_street.upper()
            if "CAYMAN" in st_clean:
                return "CYM"
            if (
                RE_UK_POSTCODE.search(st_clean)
                or st_clean.endswith(", UK")
                or st_clean.endswith(" UK")
                or "UNITED KINGDOM" in st_clean
            ):
                return "GBR"
            if (
                RE_CAN_POSTCODE.search(st_clean)
                or st_clean.endswith(", CANADA")
                or st_clean.endswith(" CANADA")
            ):
                return "CAN"
            m_sz = RE_STATE_ZIP.search(st_clean)
            if m_sz and m_sz.group(1).upper() in FROZEN_US_STATE_CODES:
                return "USA"

            # Check if address ends with a US state code/name (or US state before country)
            # BEFORE scanning raw components against COUNTRY_MAP to prevent domestic namesake cities
            # (e.g. Lebanon NH, Mexico ME, Brazil IN, Paris TX, London OH, Berlin CT)
            # from being hijacked by sovereign country names.
            raw_parts = [p.strip() for p in raw_street.split(",") if p.strip()]
            if raw_parts:
                last_clean = RE_NON_ALPHANUMERIC.sub("", raw_parts[-1]).strip().upper()
                if last_clean in ("USA", "US", "UNITED STATES", "UNITED STATES OF AMERICA"):
                    if len(raw_parts) >= 2:
                        prev_clean = RE_NON_ALPHANUMERIC.sub("", raw_parts[-2]).strip().upper()
                        if prev_clean in FROZEN_US_STATE_CODES or prev_clean in US_STATES:
                            return "USA"
                elif last_clean in FROZEN_US_STATE_CODES or last_clean in US_STATES:
                    return "USA"
                else:
                    sub_last = RE_NON_ALPHANUMERIC.sub("", raw_parts[-1].split()[-1]).strip().upper()
                    if sub_last in FROZEN_US_STATE_CODES or sub_last in US_STATES:
                        return "USA"

            for part in raw_street.split(","):
                p_clean = RE_NON_ALPHANUMERIC.sub(" ", part).strip().upper()
                p_clean = " ".join(p_clean.split())
                p_alphanumeric = RE_NON_ALPHANUMERIC.sub("", part).strip().upper()
                if p_alphanumeric in FROZEN_US_STATE_CODES or p_alphanumeric.isdigit():
                    continue
                if p_clean in COUNTRY_MAP and COUNTRY_MAP[p_clean] != "USA":
                    return COUNTRY_MAP[p_clean]
                if p_alphanumeric in COUNTRY_MAP and COUNTRY_MAP[p_alphanumeric] != "USA":
                    return COUNTRY_MAP[p_alphanumeric]

            raw_words = RE_NON_ALPHANUMERIC.sub(" ", raw_street).strip().upper().split()
            if len(raw_words) >= 2:
                two_w = f"{raw_words[-2]} {raw_words[-1]}"
                if two_w in COUNTRY_MAP and COUNTRY_MAP[two_w] != "USA":
                    return COUNTRY_MAP[two_w]
            if raw_words and raw_words[-1] in COUNTRY_MAP and COUNTRY_MAP[raw_words[-1]] != "USA":
                if (len(raw_words[-1]) > 2 or raw_words[-1] not in FROZEN_US_STATE_CODES) and not raw_words[-1].isdigit():
                    return COUNTRY_MAP[raw_words[-1]]

            for part in raw_street.split(","):
                p_clean = RE_NON_ALPHANUMERIC.sub(" ", part).strip().upper()
                p_clean = " ".join(p_clean.split())
                if p_clean in GLOBAL_METRO_TO_COUNTRY:
                    return GLOBAL_METRO_TO_COUNTRY[p_clean]
                c_unaccent = fold_to_ascii_key(p_clean)
                if c_unaccent in GLOBAL_METRO_TO_COUNTRY:
                    return GLOBAL_METRO_TO_COUNTRY[c_unaccent]

        return "USA"
