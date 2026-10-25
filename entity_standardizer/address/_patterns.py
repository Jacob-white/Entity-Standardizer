"""
Pre-Compiled Regular Expressions and Fast Lookup Sets.
======================================================
Provides pre-compiled regex automata and immutable frozensets to eliminate
re.compile overhead and accelerate token validation.
"""

import re
import unicodedata
from typing import Optional
from entity_standardizer.address.tables import (
    DIRECTIONALS,
    STREET_SUFFIXES,
    SECONDARY_UNITS,
    US_STATES,
    WORD_ORDINALS,
)

# ---------------------------------------------------------------------------
# Pre-Compiled Regular Expressions
# ---------------------------------------------------------------------------

# Token cleaning & whitespace
RE_CLEAN_TOKEN = re.compile(r"^[,\.#;:\-]+|[,\.#;:\-]+$")
RE_WHITESPACE = re.compile(r"\s+")
RE_NON_ALPHANUMERIC = re.compile(r"[^\w\s]")
RE_PUNCTUATION_SPLIT = re.compile(r"[,\.;:#]+")

# Tier 1 Fast-Path Regexes
# Matches: "100 Main St, New York, NY 10005" or "100 Main St, Suite 200, New York, NY 10005"
RE_CANONICAL_COMMA = re.compile(
    r"^(\d+[A-Z0-9\-\/]*)\s+([^,]+?)(?:,\s*([^,]+?))?,\s*([^,]+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$",
    re.IGNORECASE
)

# State and ZIP matching
RE_STATE_ZIP = re.compile(r"\b([A-Z]{2})(?:,\s*|\s+)(\d{5}(?:-\d{4})?)\b", re.IGNORECASE)
# PO Box
RE_PO_BOX = re.compile(r"\b(?:P\.?O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX)\s+(\d[A-Z0-9\-]*|[A-Z](?![A-Z]))\b", re.IGNORECASE)
# Secondary Units
RE_SEC_UNIT = re.compile(
    r"\b(SUITE|STE|SUIT|UNIT|UNT|APT|APARTMENT|APPT|FLOOR|FL|FLR|ROOM|RM|BLDG|BUILDING|BLD|"
    r"DEPT|DEPARTMENT|LOT|SPC|SPACE|LEVEL|LVL|HNGR|HANGAR|KEY|PIER|SLIP|STP|STOP|TRLR|TRAILER)\b\.?\s*(?:#\s*)?([A-Z0-9\-]+)|"
    r"#\s*([A-Z0-9\-]+)|"
    r"\b(BSMT|BASEMENT|FRNT|FRONT|LBBY|LOBBY|LOWR|LOWER|MEZZ|MEZZANINE|OFC|OFFICE|PH|PENTHOUSE|REAR|SIDE|UPPR|UPPER)\b\.?(?:\s*(?:#\s*)?(\d+[A-Z0-9\-]*|[A-Z]\b))?",
    re.IGNORECASE
)

# PMB / Private Mailbox
RE_PMB = re.compile(r"\b(?:PMB|PRIVATE\s+MAILBOX)\s*#?\s*([A-Z0-9\-]+)\b", re.IGNORECASE)

# Queens borough hyphenation vs street range vs attached secondary unit
RE_QUEENS_BOROUGH = re.compile(r"^(\d+-\d+)\s+([A-Za-z].*)$")
# Suffix-attached secondary unit (e.g. "Main St-4B")
# Puerto Rico Urbanization
RE_URBANIZATION = re.compile(
    r"\b(?:URB|URBANIZACION)\.?\s+([A-Z\s]+?)(?=\s+[A-Z]-?\d|\d|\b(?:CALLE|AVE|AVENIDA|CARR|BO|SECTOR|KM|BLQ|MZ|SOLAR|MANZANA)\b|,|$)",
    re.IGNORECASE,
)

# International Postcodes
RE_UK_POSTCODE = re.compile(r"\b(?:GIR\s*0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.IGNORECASE)
RE_CAN_POSTCODE = re.compile(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", re.IGNORECASE)

# Sovereign Country Terminal Pattern
RE_TERMINAL_COUNTRY = re.compile(
    r"(?:,\s*|\s+)(?:UNITED\s+STATES(?:\s+OF\s+AMERICA)?|U\.S\.A\.|USA|CAYMAN\s+ISLANDS|UNITED\s+KINGDOM|GREAT\s+BRITAIN|CANADA|CAN)\.?\s*$",
    re.IGNORECASE,
)

# Legacy ETL Artifacts (e.g. "10005TH UNITED ESTS", "UNITED ESTS")
RE_LEGACY_CORRUPTIONS = re.compile(
    r"\b\d{4,5}(?:ST|ND|RD|TH)?\s+UNITED\s+ESTS\b|\bUNITED\s+ESTS\b",
    re.IGNORECASE,
)

# Numbered streets
RE_NUMBERED_STREET = re.compile(r"^(\d+)(?:ST|ND|RD|TH)?$", re.IGNORECASE)

# Glued punctuation normalization
RE_GLUED_HASH = re.compile(r"(?<=[A-Za-z0-9])#(?=[A-Za-z0-9])")
RE_GLUED_UNIT = re.compile(r"\b(APT|STE|UNIT|FL)\.?(?=\d)", re.IGNORECASE)
RE_GLUED_HOUSE_NUM = re.compile(r"^(\d+)([A-Za-z]{3,})\b")

# Military Mail (APO, FPO, DPO)
RE_MILITARY_UNIT_BOX = re.compile(
    r"^\s*((?:UNIT|PSC|CMR)\s+\d+)\s*(?:,)?\s*(BOX\s+\d+)\b",
    re.IGNORECASE,
)

# Rural Route & Highway Contract
RE_RURAL_ROUTE = re.compile(r"\b(R\.?\s?R\.?|RURAL\s+ROUTE)\s*#?\s*(\d+)\b(?:[ ,\t]*BOX\s*#?\s*([A-Z0-9\-]+))?", re.IGNORECASE)
RE_HIGHWAY_CONTRACT = re.compile(r"\b(H\.?C\.?|HIGHWAY\s+CONTRACT)\s*#?\s*(\d+)\b(?:[ ,\t]*BOX\s*#?\s*([A-Z0-9\-]+))?", re.IGNORECASE)

# Additional Pre-Compiled Utility Patterns
RE_CLEAN_ALPHA = re.compile(r"[^A-Z]")
RE_SAINT_HYPHEN = re.compile(r"\b(ST|SAINT)-([A-Za-z]{2,})\b", re.IGNORECASE)
RE_ATTACHED_SUFFIX_EXPLICIT_UNIT = re.compile(
    r"\b(ST|STREET|AVE|AVENUE|BLVD|BOULEVARD|RD|ROAD|DR|DRIVE|LN|LANE|WAY|CT|COURT|PL|PLACE|CIR|CIRCLE|PKWY|PARKWAY)-(SUITE|STE|APARTMENT|APT|UNIT|FLOOR|FL|ROOM|RM)\b\s*#?\s*([A-Z0-9\-]+)\b",
    re.IGNORECASE,
)
RE_ATTACHED_SUFFIX_BARE_UNIT = re.compile(
    r"\b(ST|STREET|AVE|AVENUE|BLVD|BOULEVARD|RD|ROAD|DR|DRIVE|LN|LANE|WAY|CT|COURT|PL|PLACE|CIR|CIRCLE|PKWY|PARKWAY)-(\d+[A-Z0-9\-]*|[A-Z])\b",
    re.IGNORECASE,
)
RE_PRIVATE_MAILBOX = re.compile(r"\bPRIVATE\s+MAILBOX\b", re.IGNORECASE)
RE_HYPHENATED_UNIT = re.compile(r"\b(STE|SUITE|APT|UNIT|FL)-(\d+)", re.IGNORECASE)
RE_PRIVATE_RESIDENCE = re.compile(
    r"\b(?:PRIVATE\s+RESIDENCE|PRIVATE\s+ADDRESS|CONFIDENTIAL|RESIDENCE\s+ONLY|RESIDENTIAL\s+ONLY|PERSONAL\s+RESIDENCE|RESIDENTIAL\s+ADDRESS)\b"
    r"|^(?:RESIDENTIAL|RESIDENCE)$"
    r"|\bRESIDENTIAL(?!\s+(?:LTD|LIMITED|LLC|INC|CORP|LP|LLP|CO|COMPANY|PROPERTIES|INVESTMENTS|MGMT|MANAGEMENT|HOLDINGS|GROUP|PLC|SERVICES|SOLUTIONS|CAPITAL|EQUITY|PARTNERS|ASSOC|ASSOCIATION|REALT|DEVELOPMENT))\b",
    re.IGNORECASE,
)
RE_COMMA_DOT = re.compile(r"[,\.]+")
RE_DIGITS = re.compile(r"\d")

# Spanish Prefix Thoroughfares
SPANISH_PREFIX_THOROUGHFARES = frozenset(
    {"CALLE", "AVENIDA", "CARR", "RUTA", "CAMINO", "PASEO", "CALZADA", "CARRETERA"}
)


# Puerto Rico Highway Addresses (e.g. "PR #2 KM 82 HM. 2", "PR-2 KM 82.2", "CARR 167 KM 15")
RE_PR_HIGHWAY = re.compile(
    r"^(?:PR|CARR|CARRETERA)\s*(?:#|NO\.?|-)?\s*(\d+[A-Z]?)\s+(?:KM|KILOMETRO)\.?\s*(\d+(?:\.\d+)?)(?:\s+(?:HM|HECTOMETRO)\.?\s*(\d+))?(.*)$",
    re.IGNORECASE,
)
RE_PHYSICAL_STREET_INDICATOR = re.compile(r"\b\d+\s+[A-Za-z]+\s+(ST|AVE|RD|BLVD|DR|LN|WAY)\b", re.IGNORECASE)
RE_OCCUPANCY_VAL_CLEAN = re.compile(r"[^\w\-]")
RE_IDENTIFIER_TOKEN = re.compile(r"^(\d+[A-Z0-9\-]*|[A-Z]\d+|[A-Z])$")
RE_INTL_FLAT = re.compile(r"^(?:FLAT|APT|UNIT)\s*#?\s*([A-Z0-9\-]+)[,\s]+(.+)$", re.IGNORECASE)
RE_INTL_SEC_INLINE = re.compile(r"\b(SUITE|STE|UNIT|APT|FLOOR|LEVEL|LVL|PO BOX|FLAT|FL)\b\s*#?\s*([A-Z0-9\-]+)\b", re.IGNORECASE)
RE_INTL_SEC_START = re.compile(r"^(SUITE|STE|UNIT|APT|FLOOR|LEVEL|LVL|PO BOX|FLAT|FL)\b\s*#?\s*(.+)$", re.IGNORECASE)
RE_CAN_PROV_POSTAL = re.compile(r"^([A-Z]{2})\s+([A-Z]\d[A-Z]\s?\d[A-Z]\d)$")
RE_NUMBER_HYPHEN_NUMBER = re.compile(r"^\d+-\d+$")
RE_US_ZIP5_OR_9 = re.compile(r"^\d{5}(?:-\d{4})?$")
RE_PO_BOX_KEY = re.compile(r"^(?:P\.?O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX)\s+(\d[A-Z0-9\-]*|[A-Z](?![A-Z]))")
RE_NUMBERED_STREET_KEY = re.compile(r"^(\d+)(?:ST|ND|RD|TH)?$")

# ---------------------------------------------------------------------------
# Frozensets & Fast Lookup Dictionaries
# ---------------------------------------------------------------------------

FROZEN_STREET_SUFFIXES = frozenset(STREET_SUFFIXES.keys())
FROZEN_STREET_SUFFIX_VALUES = frozenset(STREET_SUFFIXES.values())

FROZEN_DIRECTIONALS = frozenset(DIRECTIONALS.keys())
FROZEN_DIRECTIONAL_VALUES = frozenset(DIRECTIONALS.values())

FROZEN_US_STATES = frozenset(US_STATES.keys())
FROZEN_US_STATE_CODES = frozenset(US_STATES.values())

FROZEN_SECONDARY_UNITS = frozenset(SECONDARY_UNITS.keys())
FROZEN_SECONDARY_UNIT_VALUES = frozenset(SECONDARY_UNITS.values())

ROUTE_PREFIXES = frozenset({
    "RTE", "ROUTE", "HWY", "HIGHWAY", "CR", "SR", "RR", "FM", "RM",
    "COUNTY RD", "COUNTY ROAD", "STATE ROUTE", "ROAD", "RD", "CO RD",
    "RANCH ROAD", "FARM ROAD", "INTERSTATE", "I", "IH", "US", "SH", "STATE HWY", "STATE HIGHWAY",
})
# A bare number after a state name is that state's route number ("Texas 71", "California 1"), never an ordinal.
ROUTE_STATE_NAMES = frozenset(name for name in US_STATES if len(name) > 2)


def is_route_number_prefix(prev: str, prev2: str = "") -> bool:
    """True when a bare number following `prev` (and the two-word `prev2`) is a route number, not a street ordinal.

    "Highway 35", "Interstate 35 N", "US 90", "SH 71", "State Route 9", "County Road 12", "Texas 71".
    """
    return prev in ROUTE_PREFIXES or prev2 in ROUTE_PREFIXES or prev in ROUTE_STATE_NAMES

KNOWN_VALID_SINGLE_WORD_STREETS = frozenset({
    "BROADWAY", "BOWERY", "THE EMBARCADERO", "THE MALL", "WALL", "MALL"
})


RE_BARE_UNIT_PHRASE = re.compile(
    r"^(?:FL|FLOOR|APT|APARTMENT|STE|SUITE|UNIT|RM|ROOM|BLDG|BUILDING|LEVEL|LVL)\s*#?\s*[A-Z0-9\-]+$",
    re.IGNORECASE
)
RE_LONE_NUMBER = re.compile(r"^\d+[A-Z0-9\-\/]*$")
RE_LONE_ALPHANUM = re.compile(r"^[A-Z]\d+$|^\d+[A-Z]$")
INVALID_ORPHAN_TOKENS = frozenset({
    "UP", "BO", "GDN", "LB", "DUO", "FSB", "ESQ", "CPA", "MD", "PA", "NA", "NTSA",
    "JR", "SR", "II", "III", "IV", "LPA", "FLT", "LHS", "RHS", "TOR",
    "LLC", "LP", "LLP", "INC", "CORP", "LTD", "PLC", "SA", "AG", "GMBH", "BV", "NV",
    "IST", "IIND", "IIIRD", "IVTH"
})


def is_invalid_thoroughfare(st1: Optional[str]) -> bool:
    """
    Returns True if st1 is NOT a legitimate thoroughfare line.
    Detects bare house/unit numbers, orphan unit designators, and stray legal suffixes.
    """
    if not st1:
        return True
    clean = str(st1).strip().upper()
    if not clean:
        return True
    clean_alnum = re.sub(r"[^\w]", "", clean)
    if len(clean_alnum) <= 1:
        return True
    if clean.startswith("(") and clean.endswith(")"):
        return True
    if " " not in clean and "&" in clean:
        return True
    if " " in clean:
        return bool(RE_BARE_UNIT_PHRASE.match(clean))
    if clean in KNOWN_VALID_SINGLE_WORD_STREETS:
        return False
    if clean in INVALID_ORPHAN_TOKENS or clean_alnum in INVALID_ORPHAN_TOKENS:
        return True
    if clean in ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN"):
        return True
    if clean in STREET_SUFFIXES or clean in STREET_SUFFIXES.values():
        return True
    if RE_LONE_NUMBER.match(clean):
        return True
    if RE_LONE_ALPHANUM.match(clean):
        return True
    return False

MULTI_WORD_CITIES = frozenset({
    "NEW YORK", "SAN FRANCISCO", "LOS ANGELES", "SALT LAKE CITY", "KANSAS CITY",
    "BATON ROUGE", "OKLAHOMA CITY", "COLORADO SPRINGS", "VIRGINIA BEACH",
    "JERSEY CITY", "FORT WORTH", "SAINT PAUL", "SAN ANTONIO", "SAN DIEGO",
    "ELK GROVE VILLAGE", "WHITE PLAINS", "FALLS CHURCH", "KEW GARDENS",
    "FOREST HILLS", "LONG ISLAND CITY", "JACKSON HEIGHTS", "WEST TRENTON",
    "SOUTH BEND", "NORTH VERNON", "PARK CITY", "GROVE CITY", "CEDAR RAPIDS",
    "PALM SPRINGS", "SANTA FE", "SANTA BARBARA", "SAN JOSE", "EL PASO",
    "LAS VEGAS", "CORPUS CHRISTI", "CHULA VISTA", "WINSTON SALEM", "GRAND RAPIDS",
    "SIOUX FALLS", "FORT WAYNE", "DES MOINES", "LITTLE ROCK", "SAN JUAN"
})

# Known Standalone Secondary Units (Pub 28 Section 251)
STANDALONE_SEC_UNITS = frozenset({
    "BSMT", "BASEMENT", "FRNT", "FRONT", "LBBY", "LOBBY", "LOWR", "LOWER",
    "MEZZ", "MEZZANINE", "OFC", "OFFICE", "PH", "PENTHOUSE", "REAR", "SIDE", "UPPR", "UPPER"
})

def is_edit_distance_leq1(s1: str, s2: str) -> bool:
    """
    Determines if edit distance (Damerau-Levenshtein <= 1) between s1 and s2 is <= 1.
    Supports single insertion, deletion, substitution, or adjacent transposition.
    Runs in O(min(len(s1), len(s2))) time and O(1) memory.
    """
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > 1:
        return False

    if s1 == s2:
        return True

    if len1 == len2:
        diffs = 0
        i = 0
        while i < len1:
            if s1[i] != s2[i]:
                diffs += 1
                if diffs > 1:
                    return False
                if i + 1 < len1 and s1[i] == s2[i + 1] and s1[i + 1] == s2[i]:
                    i += 2
                    continue
            i += 1
        return diffs <= 1

    # Length difference is 1: ensure s1 is the shorter string
    if len1 > len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    i = 0
    j = 0
    diffs = 0
    while i < len1 and j < len2:
        if s1[i] != s2[j]:
            diffs += 1
            if diffs > 1:
                return False
            j += 1
        else:
            i += 1
            j += 1
    return True


def get_fuzzy_suffix(token: str) -> Optional[str]:
    """
    O(1) dictionary check with distance <= 1 fallback against closed STREET_SUFFIXES.
    Fuzzy distance check only applies to word tokens of length >= 4 to avoid abbreviation collisions.
    Excludes keywords like STATE and COUNTY to prevent route prefix misidentification.
    """
    if not token or re.search(r"[\d\-]", token):
        return None
    tok_clean = RE_CLEAN_ALPHA.sub("", token.upper())
    if not tok_clean:
        return None
    if tok_clean in ("STATE", "STATES", "COUNTY", "UNITED", "AMERICA", "ISLANDS", "COUNTRY"):
        return None
    if tok_clean in STREET_SUFFIXES:
        return STREET_SUFFIXES[tok_clean]

    from entity_standardizer.address.fuzzy import heal_street_suffix
    return heal_street_suffix(tok_clean, max_distance=2)


def clean_redundant_street_tail(
    s: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
) -> str:
    """
    Strips terminal sovereign country tokens, legacy corruptions, and redundant
    trailing city, state, and postal codes that were already provided in separate fields or concatenated.
    """
    if not s:
        return ""
    curr = s.strip()

    # Pre-clean legacy artifacts
    curr = RE_LEGACY_CORRUPTIONS.sub("", curr).rstrip(" ,.-")

    for _ in range(4):
        prev = curr

        # 1. Strip terminal sovereign country
        curr = RE_TERMINAL_COUNTRY.sub("", curr).rstrip(" ,.-")

        # 2. Strip matching postal code if at end
        if postal_code:
            zip_clean = postal_code.strip()
            zip_nospace = zip_clean.replace(" ", "")
            if zip_clean and curr.upper().endswith(zip_clean.upper()):
                curr = curr[:-len(zip_clean)].rstrip(" ,.-")
            elif zip_nospace and curr.upper().endswith(zip_nospace.upper()):
                curr = curr[:-len(zip_nospace)].rstrip(" ,.-")
            elif len(zip_clean) >= 5 and curr.upper().endswith(zip_clean[:5].upper()):
                curr = curr[:-5].rstrip(" ,.-")
        else:
            m_can_tail = re.search(r"(?:,\s*|\s+)([A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z]\s*\d[A-CEGHJ-NPR-TV-Z]\d)\s*$", curr, re.IGNORECASE)
            if m_can_tail:
                curr = curr[:m_can_tail.start()].rstrip(" ,.-")

        # 3. Strip matching state / province if at end
        if state:
            st_clean = state.strip().upper()
            if st_clean:
                st_variants = [re.escape(st_clean)]
                from entity_standardizer.address.tables import CANADIAN_PROVINCES, US_STATES
                for k, v in CANADIAN_PROVINCES.items():
                    if k == st_clean or v == st_clean:
                        st_variants.append(re.escape(k))
                        st_variants.append(re.escape(v))
                for k, v in US_STATES.items():
                    if k == st_clean or v == st_clean:
                        st_variants.append(re.escape(k))
                        st_variants.append(re.escape(v))
                st_pat = "|".join(set(st_variants))
                m_st = re.search(r"(?:,\s*|\s+)(?:" + st_pat + r")$", curr, re.IGNORECASE)
                if m_st:
                    cand = curr[:m_st.start()].rstrip(" ,.-")
                    tokens_cand = cand.split()
                    has_street_words = any(t.isalpha() and t.upper() not in ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN") for t in tokens_cand)
                    if has_street_words or not tokens_cand:
                        curr = cand

        # 4. Strip matching city if at end or exact match
        if city:
            city_clean = city.strip().upper()
            if city_clean:
                m_city = re.search(r"(?:,\s*|\s+)" + re.escape(city_clean) + r"$", curr, re.IGNORECASE)
                if m_city:
                    cand = curr[:m_city.start()].rstrip(" ,.-")
                    tokens_cand = cand.split()
                    DANGLING_PREPOSITIONS = {"DE", "DEL", "OF", "LA", "EL", "DU", "VON", "VAN"}
                    if tokens_cand and tokens_cand[-1].upper() in DANGLING_PREPOSITIONS:
                        cand_no_prep = " ".join(tokens_cand[:-1]).rstrip(" ,.-")
                        cand_tokens_check = cand_no_prep.split()
                        has_street_words = any(t.isalpha() and t.upper() not in ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN") for t in cand_tokens_check)
                        if has_street_words:
                            cand = cand_no_prep
                    has_street_words = any(t.isalpha() and t.upper() not in ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN") for t in cand.split())
                    if has_street_words or not cand.split():
                        curr = cand
                if curr.upper() == city_clean:
                    curr = ""

        if curr == prev:
            break

    return curr


def get_fuzzy_directional(token: str) -> Optional[str]:
    """
    O(1) dictionary check with distance <= 1 fallback against DIRECTIONALS.
    Fuzzy distance check only applies to word tokens of length >= 3 to avoid 1-letter collisions.
    """
    tok_clean = RE_CLEAN_ALPHA.sub("", token.upper())
    if not tok_clean:
        return None
    if tok_clean in DIRECTIONALS:
        return DIRECTIONALS[tok_clean]

    if len(tok_clean) < 3:
        return None

    t_len = len(tok_clean)
    for canonical, abbr in DIRECTIONALS.items():
        if len(canonical) >= 4 and abs(len(canonical) - t_len) <= 1:
            if is_edit_distance_leq1(tok_clean, canonical):
                return abbr
    return None


def clean_repetitive_cycles(s: str) -> str:
    """
    Detects and collapses looping concatenated substrings, repeated token n-grams,
    and concatenated cycle artifacts before address parsing.
    Examples:
      - 'CALLE 75 8-77 OF.301 CALLE 75 8-77 OF.301' -> 'CALLE 75 8-77 OF.301'
      - 'STE 4075 4075 4075' -> 'STE 4075'
      - '100 MAIN ST, 100 MAIN ST' -> '100 MAIN ST'
    """
    if not s or len(s) < 4:
        return s

    curr = s.strip()

    # 1. Comma / Semicolon chunk repetition: "A, A, A" -> "A"
    for delim in (",", ";"):
        if delim in curr:
            chunks = [c.strip() for c in curr.split(delim) if c.strip()]
            if len(chunks) >= 2:
                if all(c.upper() == chunks[0].upper() for c in chunks):
                    curr = chunks[0]
                    break
                for clen in range(1, len(chunks) // 2 + 1):
                    if len(chunks) % clen == 0:
                        pattern = [c.upper() for c in chunks[:clen]]
                        repeated = True
                        for idx in range(clen, len(chunks), clen):
                            if [c.upper() for c in chunks[idx:idx + clen]] != pattern:
                                repeated = False
                                break
                        if repeated:
                            curr = f" {delim} ".join(chunks[:clen])
                            break

    # 2. Token-level cycle detection on whitespace-separated words
    tokens = curr.split()
    if len(tokens) >= 2:
        # Fast exit: a cycle needs at least one repeated (normalized) token, so all-distinct tokens
        # can never collapse and the loops below would only re-join them unchanged.
        normalized = [t.upper().strip(" ,.-") for t in tokens]
        if len(set(normalized)) == len(normalized):
            return " ".join(tokens)

        def _is_prefix_seq(rem_seq: list, chunk_seq: list) -> bool:
            # (callers only pass a non-empty remainder)
            if len(rem_seq) > len(chunk_seq):
                return False
            for idx_p in range(len(rem_seq) - 1):
                if rem_seq[idx_p] != chunk_seq[idx_p]:
                    return False
            return chunk_seq[len(rem_seq) - 1].startswith(rem_seq[-1])

        # Check whole-token repetition e.g. "CALLE 75 8-77 OF.301 CALLE 75 8-77 OF.301"
        n_toks = len(tokens)
        collapsed = False
        for k in range(1, n_toks // 2 + 1):
            if k == 1 and n_toks == 2 and tokens[0].isalpha() and tokens[0].upper() == tokens[1].upper():
                continue
            chunk = [t.upper().strip(" ,.-") for t in tokens[:k]]
            repeats = 1
            idx = k
            while idx + k <= n_toks:
                if [t.upper().strip(" ,.-") for t in tokens[idx:idx + k]] == chunk:
                    repeats += 1
                    idx += k
                else:
                    break
            rem = [t.upper().strip(" ,.-") for t in tokens[idx:]]
            min_repeats = 3 if k == 1 else 2
            if repeats >= min_repeats and (not rem or _is_prefix_seq(rem, chunk)):
                tokens = tokens[:k]
                curr = " ".join(tokens)
                collapsed = True
                break

        if not collapsed:
            # Check internal repeated runs of length k (e.g., 'STE 4075 4075 4075' -> 'STE 4075')
            new_tokens = []
            i = 0
            while i < len(tokens):
                found_rep = False
                for k in range(1, (len(tokens) - i) // 2 + 1):
                    chunk = [t.upper().strip(" ,.-") for t in tokens[i:i + k]]
                    r = 1
                    j = i + k
                    while j + k <= len(tokens):
                        if [t.upper().strip(" ,.-") for t in tokens[j:j + k]] == chunk:
                            r += 1
                            j += k
                        else:
                            break
                    rem = [t.upper().strip(" ,.-") for t in tokens[j:]]
                    has_partial = bool(rem and _is_prefix_seq(rem, chunk))
                    min_r = 3 if k == 1 else 2
                    if r >= min_r:
                        new_tokens.extend(tokens[i:i + k])
                        i = j + (len(rem) if has_partial else 0)
                        found_rep = True
                        break
                if not found_rep:
                    new_tokens.append(tokens[i])
                    i += 1
            tokens = new_tokens
            curr = " ".join(tokens)

    return curr


collapse_cyclic_patterns = clean_repetitive_cycles
clean_cyclic_repetitions = clean_repetitive_cycles

# ---------------------------------------------------------------------------
# Intersection & Cross-Street Grammar
# ---------------------------------------------------------------------------

PLURAL_STREET_SUFFIXES = {
    "STREETS": "ST", "STS": "ST",
    "AVENUES": "AVE", "AVES": "AVE",
    "ROADS": "RD", "RDS": "RD",
    "BOULEVARDS": "BLVD", "BLVDS": "BLVD",
    "HIGHWAYS": "HWY", "HWYS": "HWY",
    "LANES": "LN", "LNS": "LN",
    "WAYS": "WAY",
    "DRIVES": "DR", "DRS": "DR",
    "COURTS": "CT", "CTS": "CT",
    "PLACES": "PL", "PLS": "PL",
}

RE_CORNER_PREFIX = re.compile(
    r"^(?:CORNER\s+OF|INTERSECTION\s+OF|AT\s+THE\s+CORNER\s+OF|CNR\s+OF|NEAR\s+THE\s+CORNER\s+OF)\s+",
    re.IGNORECASE,
)
RE_ROUTE_PAIR = re.compile(
    r"^(?:ROUTES?|RTES?|HWYS?|STATE\s+ROUTES?|STATE\s+HWYS?)\s+([A-Z0-9\-]+)\s+(?:AND|&|\/)\s+([A-Z0-9\-]+)$",
    re.IGNORECASE,
)

def _normalize_intersection_branch(branch: str) -> str:
    tokens = branch.split()
    res = []
    for tok in tokens:
        clean = tok.upper().strip(".,")
        if clean in WORD_ORDINALS:
            res.append(WORD_ORDINALS[clean])
        elif clean in STREET_SUFFIXES:
            res.append(STREET_SUFFIXES[clean])
        elif clean in DIRECTIONALS:
            res.append(DIRECTIONALS[clean])
        elif clean in ("ROUTE", "ROUTES", "RTE", "RTES"):
            res.append("RT")
        elif clean in ("HIGHWAY", "HIGHWAYS"):
            res.append("HWY")
        else:
            res.append(clean)
    return " ".join(res)


def parse_intersection_address(s: str) -> Optional[str]:
    """
    Parses and canonicalizes cross-street and intersection addresses.
    Examples:
      - 'Cherry And Fourth Streets' -> 'CHERRY ST & 4TH ST'
      - 'Routes 60 And 155' -> 'RT 60 & RT 155'
      - 'Main And Franklin Streets' -> 'MAIN ST & FRANKLIN ST'
      - 'Ranch Road 12 And River Road' -> 'RANCH RD 12 & RIVER RD'
      - 'Corner of 5th Ave and 42nd St' -> '5TH AVE & 42ND ST'
    """
    if not s or len(s.strip()) < 5:
        return None
    raw = s.strip()
    raw = RE_CORNER_PREFIX.sub("", raw).strip()

    # Route pairs: e.g. 'Routes 60 And 155'
    m_rt = RE_ROUTE_PAIR.match(raw)
    if m_rt:
        return f"RT {m_rt.group(1)} & RT {m_rt.group(2)}".upper()

    # Split on intersection delimiter
    m_split = re.search(r"\s+(AND|&|@|\/|AT)\s+", raw, re.IGNORECASE)
    if m_split:
        delim = m_split.group(1).upper()
        p1 = raw[:m_split.start()].strip()
        p2 = raw[m_split.end():].strip()
        # Avoid false positives like secondary units
        if p1.upper().startswith(("SUITE", "STE", "APT", "UNIT", "FLOOR", "FL")):
            return None
        if p2.upper().startswith(("SUITE", "STE", "APT", "UNIT", "FLOOR", "FL")):
            return None

        # Exclude commercial development / campus premises like "The Village at Thornblade"
        if delim in ("AT", "@"):
            COMPLEX_PREMISES = {"VILLAGE", "SHOPS", "COMMONS", "CENTER", "ESTATES", "LANDING", "GALLERIA", "PROMENADE", "MARKETPLACE", "RESIDENCES", "TOWERS"}
            if bool(set(p1.upper().split()) & COMPLEX_PREMISES):
                return None

        # Check for plural suffix on second part: e.g. 'Cherry and Fourth Streets'
        p2_tokens = p2.split()
        if p2_tokens and p2_tokens[-1].upper().rstrip(".,") in PLURAL_STREET_SUFFIXES:
            suf_raw = p2_tokens[-1].upper().rstrip(".,")
            shared_suf = PLURAL_STREET_SUFFIXES[suf_raw]
            p2_base = " ".join(p2_tokens[:-1])
            # Check if p1 also needs the shared suffix
            p1_tokens = p1.split()
            if (
                p1_tokens
                and p1_tokens[-1].upper().rstrip(".,") not in STREET_SUFFIXES
                and p1_tokens[-1].upper().rstrip(".,") not in FROZEN_STREET_SUFFIX_VALUES
            ):
                p1_clean = f"{p1} {shared_suf}"
            else:
                p1_clean = p1
            p2_clean = f"{p2_base} {shared_suf}" if p2_base else p2
            b1 = _normalize_intersection_branch(p1_clean)
            b2 = _normalize_intersection_branch(p2_clean)
            return f"{b1} & {b2}"

        def _has_street_evidence(part_str: str) -> bool:
            toks = [t.upper().strip(".,") for t in part_str.split()]
            return any(
                t in STREET_SUFFIXES
                or t in FROZEN_STREET_SUFFIX_VALUES
                or t in ("ROAD", "RD", "ST", "STREET", "AVE", "AVENUE", "BLVD", "HWY", "ROUTE", "RTE", "WAY", "LN", "LANE", "DR", "DRIVE")
                for t in toks
            )

        if delim in ("AT", "@"):
            # When delimiter is 'at' or '@', both sides must have street evidence
            if _has_street_evidence(p1) and _has_street_evidence(p2):
                b1 = _normalize_intersection_branch(p1)
                b2 = _normalize_intersection_branch(p2)
                return f"{b1} & {b2}"
        else:
            if _has_street_evidence(p1) or _has_street_evidence(p2):
                b1 = _normalize_intersection_branch(p1)
                b2 = _normalize_intersection_branch(p2)
                return f"{b1} & {b2}"

    return None


KNOWN_METRO_ACRONYMS = frozenset({
    "LA", "NYC", "SF", "CHI", "PHX", "MIA", "INDY", "MT", "SD", "DC", "BOS", "ATL", "DFW", "MSP", "PDX"
})


def is_city_noise_in_street1(s1: Optional[str], city: Optional[str], state: Optional[str]) -> bool:
    """
    Identifies non-numeric municipal prefixes, acronyms, or city names mistakenly entered
    into the street1 address field.
    Examples:
      - 'LA' / 'LA JOLLA' -> True
      - 'S BND IN' / 'SOUTH BEND' -> True
      - 'MT' / 'MT VERNON' -> True
      - 'HALF MOON' / 'HALF MOON BAY' -> True
      - 'OLD BRG NJ' / 'OLD BRIDGE' -> True
      - '100 MAIN ST' / 'NEW YORK' -> False
    """
    if not s1:
        return False
    s1_clean = re.sub(r"[\r\n\t]+", " ", unicodedata.normalize('NFKC', str(s1))).strip()
    s1_clean = RE_LEGACY_CORRUPTIONS.sub("", s1_clean).strip(" ,.-")
    if not s1_clean:
        return True

    # If it contains any digits, it has a house number / building number - NOT city noise!
    if any(c.isdigit() for c in s1_clean):
        return False

    s1_upper = s1_clean.upper()
    city_upper = (city or "").strip().upper()
    state_upper = (state or "").strip().upper()

    # Don't false-positive on PO boxes, rural routes, or intersections
    if (
        s1_upper.startswith(("PO BOX", "P.O.", "POB", "RR ", "HC ", "PRIVATE RESIDENCE"))
        or " & " in s1_upper
        or " AND " in s1_upper
    ):
        return False

    # Check if s1 is a bare street suffix only (e.g. "BLVD", "ST", "AVE")
    if s1_upper in ("BLVD", "ST", "AVE", "RD", "DR", "LN", "CT", "WAY", "HWY", "ROUTE"):
        return True

    # 1. Exact match with city or state
    if city_upper and s1_upper == city_upper:
        return True
    if state_upper and s1_upper == state_upper:
        return True

    # 2. Known metro acronyms / abbreviations without street numbers
    if s1_upper in KNOWN_METRO_ACRONYMS:
        return True

    # 3. Prefix of multi-word city (e.g. "HALF MOON" for "HALF MOON BAY", "RANCHO PALOS" for "RANCHO PALOS VERDES")
    if city_upper and city_upper.startswith(s1_upper) and len(s1_upper) >= 2:
        return True

    # 4. Acronym or abbreviation ending with the state code (e.g. "S BND IN", "OLD BRG NJ", "N SMITHFIELD RI", "CHADDS FRD PA")
    tokens = s1_upper.split()
    if len(tokens) >= 2 and state_upper and tokens[-1] == state_upper:
        prefix_words = " ".join(tokens[:-1])
        if prefix_words in city_upper or all(ch in city_upper for ch in prefix_words.replace(" ", "")):
            return True

    # 5. City consonants / abbreviation match (e.g. "CHADDS FRD" for "CHADDS FORD", "S BND" for "SOUTH BEND")
    if city_upper:
        city_no_vowels = re.sub(r"[AEIOU\s]", "", city_upper)
        s1_no_vowels = re.sub(r"[AEIOU\s]", "", s1_upper)
        if s1_no_vowels and s1_no_vowels == city_no_vowels:
            return True

    return False


# ---------------------------------------------------------------------------
# Rooftop Physical Street Line Cleaner (Excludes Suite, Apt, Floor, etc.)
# ---------------------------------------------------------------------------

RE_ROOFTOP_SEC = re.compile(
    r"(?:,?\s+(?:#\s*([A-Z0-9\-]+)|(APT|APARTMENT|STE|SUITE|FL|FLOOR|FLR|UNIT|RM|ROOM|DEPT|DEPARTMENT|BLDG|BUILDING|PH|PENTHOUSE|BSMT|BASEMENT|MEZZ|MEZZANINE|OFC|OFFICE|SPC|SPACE|TRLR|TRAILER|LOT|LEVEL|LVL|LBBY|LOBBY|LOWR|LOWER|UPPR|UPPER|FRNT|FRONT|REAR|SIDE|SLIP|STP|STOP|HNGR|HANGAR|KEY|PIER|FLAT)\b(?:\s*([A-Z0-9\-#]+))?|(\d+(?:ST|ND|RD|TH))\s+(FL|FLOOR|FLR)\b.*))$",
    re.IGNORECASE,
)
RE_PO_BOX_ANYWHERE = re.compile(
    r"\b(?:P\.?\s*O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX|APO|FPO|DPO)\b|^(?:BOX|RR|HC)\b",
    re.IGNORECASE,
)


def clean_rooftop_address(street_line: Optional[str]) -> Optional[str]:
    """
    Derives clean physical rooftop address line by excluding secondary units
    such as Suite, Apt, Floor, Unit, Bldg, Room, Dept, etc.
    Returns None for empty addresses, locality-only, private residences, or PO boxes.
    """
    if not street_line or not str(street_line).strip():
        return None
    val = str(street_line).strip()
    val_upper = val.upper()
    if val_upper in ("PRIVATE RESIDENCE", "CONFIDENTIAL", "RESIDENTIAL", "PERSONAL RESIDENCE"):
        return None
    if RE_PO_BOX_ANYWHERE.search(val_upper):
        return None
    if " " not in val_upper and is_invalid_thoroughfare(val):
        return None

    # Fast-path check: if none of the secondary indicator substrings are present, return immediately
    if not any(
        kw in val_upper
        for kw in (
            "#", "STE", "SUITE", "APT", "FL", "UNIT", "RM", "ROOM",
            "BLDG", "BUILDING", "DEPT", "DEPARTMENT", "OFFICE", "PH", "BSMT", "MEZZ", "OFC", "SPC", "LOT",
            "LEVEL", "FLAT", "FRNT", "REAR", "SIDE", "SLIP", "HNGR", "PIER"
        )
    ):
        if " " in val_upper:
            return val
        return None if is_invalid_thoroughfare(val) else val

    # Iteratively strip trailing secondary units (e.g., 'BLDG 4 STE 200')
    for _ in range(8):
        m = RE_ROOFTOP_SEC.search(val)
        if m:
            cand_id = (m.group(1) or m.group(3) or "").upper()
            sec_type = (m.group(2) or m.group(5) or "").upper()
            # If the candidate identifier is actually a street suffix or directional, it is NOT a unit
            if cand_id and (cand_id in STREET_SUFFIXES or cand_id in DIRECTIONALS):
                break
            # If bare unit word with no identifier, verify it is not part of a street name
            if not cand_id:
                if sec_type in ("BUILDING", "BLDG", "OFFICE", "OFC", "LEVEL", "LOT", "SPACE", "SPC"):
                    pre = val[:m.start()].strip()
                    tokens = pre.split()
                    if not ("," in val[m.start()-2:m.start()+1] or (len(tokens) >= 2 and tokens[-1] in STREET_SUFFIXES)):
                        break
            val = val[:m.start()].strip(" ,.-#;:")
        else:
            break

    val = re.sub(r"[\s,.\-#;:]+$", "", val).strip()
    if not val or is_invalid_thoroughfare(val):
        return None
    return val

