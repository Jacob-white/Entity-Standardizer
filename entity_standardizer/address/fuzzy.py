"""
Advanced Typo Recovery & Localized Fuzzy Correction Engine.
===========================================================
Implements Damerau-Levenshtein distance 1-2 candidate generation constrained
by state and ZIP3 for misspelled street suffixes, names, and city tokens,
along with digit transposition recovery for postal codes and street numbers.
"""

import functools
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from entity_standardizer.address.tables import (
    STREET_SUFFIXES,
    DIRECTIONALS,
    US_STATES,
    ZIP3_TO_STATE,
)
from entity_standardizer.address._patterns import MULTI_WORD_CITIES


@functools.lru_cache(maxsize=16384)
def _pure_damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Computes true Damerau-Levenshtein edit distance between s1 and s2 in pure Python.
    Supports insertion, deletion, substitution, and transposition of adjacent characters.
    """
    from entity_standardizer._native_dispatch import _damerau_levenshtein_distance_py

    return _damerau_levenshtein_distance_py(s1, s2)


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """Computes true Damerau-Levenshtein edit distance between s1 and s2.

    Accelerated by native Rust extension if loaded, with pure Python fallback.
    """
    from entity_standardizer.address._native_dispatch import try_native

    ok, result = try_native("damerau_levenshtein_distance", s1, s2)
    return result if ok else _pure_damerau_levenshtein_distance(s1, s2)



# ---------------------------------------------------------------------------
# Canonical City Reference by State
# ---------------------------------------------------------------------------

PROMINENT_STATE_CITIES: Dict[str, List[str]] = {
    "NY": ["NEW YORK", "BUFFALO", "ROCHESTER", "YONKERS", "SYRACUSE", "ALBANY", "WHITE PLAINS", "NEW ROCHELLE", "SCHENECTADY", "UTICA"],
    "CA": ["LOS ANGELES", "SAN DIEGO", "SAN JOSE", "SAN FRANCISCO", "FRESNO", "SACRAMENTO", "LONG BEACH", "OAKLAND", "BAKERSFIELD", "ANAHEIM", "SANTA BARBARA", "PALM SPRINGS"],
    "IL": ["CHICAGO", "AURORA", "NAPERVILLE", "JOLIET", "ROCKFORD", "SPRINGFIELD", "ELGIN", "PEORIA", "CHAMPAIGN"],
    "TX": ["HOUSTON", "SAN ANTONIO", "DALLAS", "AUSTIN", "FORT WORTH", "EL PASO", "ARLINGTON", "CORPUS CHRISTI", "PLANO", "LUBBOCK"],
    "FL": ["MIAMI", "ORLANDO", "TAMPA", "JACKSONVILLE", "ST PETERSBURG", "HIALEAH", "TALLAHASSEE", "FORT LAUDERDALE", "PORT ST LUCIE", "CAPE CORAL"],
    "PA": ["PHILADELPHIA", "PITTSBURGH", "ALLENTOWN", "READING", "ERIE", "SCRANTON", "BETHLEHEM", "LANCASTER", "HARRISBURG"],
    "GA": ["ATLANTA", "AUGUSTA", "COLUMBUS", "MACON", "SAVANNAH", "ATHENS", "SANDY SPRINGS", "ROSWELL"],
    "MA": ["BOSTON", "WORCESTER", "SPRINGFIELD", "CAMBRIDGE", "LOWELL", "BROCKTON", "QUINCY", "LYNN", "NEW BEDFORD"],
    "WA": ["SEATTLE", "SPOKANE", "TACOMA", "VANCOUVER", "BELLEVUE", "KENT", "EVERETT", "RENTON"],
    "CO": ["DENVER", "COLORADO SPRINGS", "AURORA", "FORT COLLINS", "LAKEWOOD", "THORNTON", "ARVADA", "WESTMINSTER", "BOULDER"],
    "AZ": ["PHOENIX", "TUCSON", "MESA", "CHANDLER", "SCOTTSDALE", "GLENDALE", "GILBERT", "TEMPE", "PEORIA", "SURPRISE"],
    "DE": ["WILMINGTON", "DOVER", "NEWARK", "MIDDLETOWN", "SMYRNA", "MILFORD", "SEAFORD", "GEORGETOWN", "LEWES"],
    "WY": ["CHEYENNE", "CASPER", "LARAMIE", "GILLETTE", "SHERIDAN", "ROCK SPRINGS", "JACKSON", "BUFFALO", "CODY"],
    "NV": ["LAS VEGAS", "HENDERSON", "RENO", "NORTH LAS VEGAS", "SPARKS", "CARSON CITY"],
    "NJ": ["NEWARK", "JERSEY CITY", "PATERSON", "ELIZABETH", "TRENTON", "CLIFTON", "CAMDEN", "PASSAIC"],
}

# Neighbourhood / borough / district names that USPS accepts as the "city" of a mailing address inside a larger
# city's ZIP codes.  They are valid as supplied and are never rewritten into a different (prominent) city.
VALID_LOCALITY_NAMES = frozenset({
    # Boston
    "DORCHESTER", "ROXBURY", "JAMAICA PLAIN", "ROSLINDALE", "HYDE PARK", "MATTAPAN", "BRIGHTON", "ALLSTON",
    "CHARLESTOWN", "SOUTH BOSTON", "EAST BOSTON", "WEST ROXBURY", "NORTH END", "BACK BAY", "FENWAY",
    # New York City
    "BROOKLYN", "BRONX", "QUEENS", "STATEN ISLAND", "MANHATTAN", "ASTORIA", "FLUSHING", "JAMAICA", "BAYSIDE",
    "RIDGEWOOD", "WOODSIDE", "SUNNYSIDE", "ELMHURST", "CORONA", "FOREST HILLS", "KEW GARDENS", "LONG ISLAND CITY",
    "JACKSON HEIGHTS", "RICHMOND HILL", "OZONE PARK", "FAR ROCKAWAY", "WHITESTONE", "COLLEGE POINT",
    # Los Angeles
    "HOLLYWOOD", "VAN NUYS", "SHERMAN OAKS", "NORTH HOLLYWOOD", "WOODLAND HILLS", "ENCINO", "TARZANA", "RESEDA",
    "CANOGA PARK", "SAN PEDRO", "WILMINGTON", "SUN VALLEY", "SYLMAR", "PACOIMA", "STUDIO CITY", "VENICE",
})

# Common US Street Names susceptible to typos
COMMON_STREET_NAMES = frozenset({
    "MAIN", "BROADWAY", "WASHINGTON", "LINCOLN", "JEFFERSON", "MADISON", "JACKSON",
    "LEXINGTON", "HIGHLAND", "SUNSET", "PARK", "OAK", "PINE", "MAPLE", "CEDAR",
    "ELM", "CHESTNUT", "WALNUT", "PEACHTREE", "MARKET", "CENTER", "SPRING", "FRONT",
    "RIVER", "CHURCH", "SECOND", "THIRD", "FOURTH", "FIFTH", "COLLEGE", "FRANKLIN",
    "ADAMS", "MONROE", "HICKORY", "WALNUT", "SPRUCE", "WILLOW", "CYPRESS", "LAUREL",
})

# Protected Proper Names, Spanish Indicators, and Standard Terms never to be fuzzy corrupted
PROTECTED_STREET_WORDS: frozenset[str] = frozenset({
    # Common proper names / historic names often found in street names
    "MARTIN", "LUTHER", "KING", "JR", "PRESIDENT", "SAINT", "SAN", "SANTA",
    "KENNEDY", "ROOSEVELT", "JEFFERSON", "LINCOLN", "WASHINGTON", "MADISON",
    "JACKSON", "ADAMS", "ADAM", "MONROE", "FRANKLIN", "HAMILTON", "GRANT", "LEE",
    "CLARK", "LEWIS", "BOONE", "CROCKETT", "HOUSTON", "AUSTIN", "TRAVIS",
    "PAINE", "RIVERA", "RIVERO", "CENTRE", "MAINE", "BRUCE", "PRICE", "PIERCE",
    "STONE", "WAYNE", "PAYNE", "CLINTON", "WILSON", "TAYLOR", "HARDING", "HOOVER",
    "TRUMAN", "CARTER", "BUSH", "OBAMA", "EISENHOWER", "MACARTHUR",
    # Spanish street types and indicators (especially Puerto Rico and Southwest)
    "CALLE", "AVENIDA", "PASEO", "CAMINO", "CARRETERA", "CALLEJON", "URB",
    "URBANIZACION", "SOL", "LUNA", "MAR", "FLAMBOYAN", "JARDINES", "PINOS",
    "DOS", "LAS", "DEL", "DE", "LOS", "PLAYA", "ISLA", "VALLE", "MONTE",
    "RIO", "VISTA", "BO", "BARRIO", "SECTOR", "PARC", "PARCELA", "CARR",
    "COND", "CONDOMINIO", "EDIF", "EDIFICIO", "RES", "RESIDENCIAL",
    # Prominent boroughs, geographic markers, and common street words
    "QUEENS", "BROOKLYN", "BRONX", "MANHATTAN", "STATEN", "ISLAND", "YORK",
    "FALLS", "LITTLE", "ORANGE", "GREENTREE", "GOULD", "UGLAND", "HOUSE",
    "FORT", "KISSENA", "CORONA", "JAMAICA", "WALL", "BAY", "BANK", "HIGH",
    "TREE", "PEACH", "ASH", "BIRCH", "FLOWER", "GRAND", "BROADWAY", "MARKET",
    "BELL", "BALL", "HALL", "CALL", "TALL", "BILL", "BULL", "DOLL", "POLL", "ROLL", "TOLL",
    "MICHIGAN", "PENNSYLVANIA", "CALIFORNIA",
    # Common Spanish place/street names and surnames (Puerto Rico, Southwest) that resemble street suffixes
    "FLORES", "TORRES", "MAYOR", "REAL", "NORTE", "SUR", "ESTE", "OESTE", "PRINCIPAL", "CENTRAL", "GRANDE",
    "NUEVA", "NUEVO", "VIEJA", "VIEJO", "PALMAS", "ROBLES", "LOPEZ", "GARCIA", "MARTINEZ", "RODRIGUEZ",
    "GONZALEZ", "PEREZ", "SANCHEZ", "RAMIREZ", "CRUZ", "REYES", "MORALES", "ORTIZ", "DIAZ", "VAZQUEZ",
    "MARKS", "MARK", "PARKER", "MILLER", "BAKER", "FISHER", "TURNER", "WALKER", "HUNTER", "COOPER",
    # Sovereign country / territorial words
    "STATES", "UNITED", "AMERICA", "ISLANDS",
})


@functools.lru_cache(maxsize=4096)
def heal_street_suffix(token: str, max_distance: int = 2) -> Optional[str]:
    """
    Recovers misspelled street suffixes using Damerau-Levenshtein distance <= max_distance.
    Only checks words of length >= 3 to avoid 2-letter abbreviation collisions.
    Rejects tokens containing digits or hyphens, protected words, and short substitutions.
    """
    if not token or re.search(r"[\d\-]", token):
        return None

    tok_clean = re.sub(r"[^A-Z]", "", token.upper())
    if not tok_clean or tok_clean in ("STATE", "STATES", "COUNTY", "UNITED", "AMERICA", "ISLANDS", "COUNTRY", "NORTH", "SOUTH", "EAST", "WEST"):
        return None

    if tok_clean in STREET_SUFFIXES:
        return STREET_SUFFIXES[tok_clean]

    if len(tok_clean) < 3 or tok_clean in PROTECTED_STREET_WORDS:
        return None

    t_len = len(tok_clean)
    # Distance 2 only for long tokens: shorter words within 2 edits of a suffix are usually names (PARKER, MILLER).
    allowed_distance = 1 if t_len <= 8 else min(max_distance, 2)
    best_match: Optional[str] = None
    min_dist = allowed_distance + 1

    for canonical, abbr in STREET_SUFFIXES.items():
        if len(canonical) >= 4 and abs(len(canonical) - t_len) <= allowed_distance:
            # For short tokens (<= 4 chars), reject substitutions (require anagram or omission/insertion)
            if t_len <= 4:
                if sorted(tok_clean) != sorted(canonical) and not (
                    set(tok_clean).issubset(set(canonical)) or set(canonical).issubset(set(tok_clean))
                ):
                    continue
            d = damerau_levenshtein_distance(tok_clean, canonical)
            # A same-length single edit that is not a transposition is a different word, not a typo.
            if d == 1 and len(canonical) == t_len and sorted(tok_clean) != sorted(canonical):
                continue
            if d <= allowed_distance and d < min_dist:
                min_dist = d
                best_match = abbr
                if d == 1:
                    break

    return best_match


@functools.lru_cache(maxsize=4096)
def heal_city_token(
    city_raw: str,
    state: Optional[str] = None,
    zip3: Optional[str] = None,
    max_distance: int = 2,
) -> Optional[str]:
    """
    Recovers misspelled city names constrained by state and/or ZIP3 sectional centers.
    """
    if not city_raw:
        return None

    city_unaccented = unicodedata.normalize("NFKD", city_raw).encode("ASCII", "ignore").decode("utf-8")
    clean_city = re.sub(r"[^\w\s]", "", city_unaccented).strip().upper()
    clean_city = re.sub(r"\s+", " ", clean_city)

    # 1. Direct match check
    if clean_city in MULTI_WORD_CITIES:
        return clean_city

    # Determine state from state arg or zip3
    target_state = (state or "").strip().upper()
    target_state = US_STATES.get(target_state, target_state)
    if not target_state and zip3 and zip3 in ZIP3_TO_STATE:
        target_state = ZIP3_TO_STATE[zip3]

    # A city that is itself a known city (in any state) is never rewritten into a different one.
    all_known = {c for cities in PROMINENT_STATE_CITIES.values() for c in cities}
    if clean_city in all_known or clean_city in VALID_LOCALITY_NAMES:
        return clean_city

    candidate_cities: List[str] = []
    if target_state in PROMINENT_STATE_CITIES:
        candidate_cities.extend(PROMINENT_STATE_CITIES[target_state])
    elif not target_state:
        # Without any state context only a single, unambiguous edit is trusted.
        max_distance = 1
        for cities in PROMINENT_STATE_CITIES.values():
            candidate_cities.extend(cities)
    # Add multi-word cities
    candidate_cities.extend(sorted(MULTI_WORD_CITIES))

    # Collect every candidate at the best distance; only a unique winner is a trustworthy correction
    # (e.g. DEVER is equally close to DENVER and DOVER, so it is left alone).
    scored: List[Tuple[int, str]] = []
    c_len = len(clean_city)
    for cand in dict.fromkeys(candidate_cities):
        if abs(len(cand) - c_len) <= max_distance:
            d = damerau_levenshtein_distance(clean_city, cand)
            # A two-edit "typo" that also replaces the first letter is a different word (DORCHESTER/WORCESTER).
            if d <= max_distance and (d < 2 or cand[0] == clean_city[0]):
                scored.append((d, cand))
    best_d = min((d for d, _ in scored), default=0)
    best = [c for d, c in scored if d == best_d]

    return best[0] if len(best) == 1 else None


@functools.lru_cache(maxsize=4096)
def heal_street_name(name_raw: str, max_distance: int = 1) -> Optional[str]:
    """
    Recovers prominent misspelled street names using edit distance <= max_distance.
    Guarded against corrupting valid English proper names, Spanish street indicators,
    and dictionary words.
    """
    if any(c.isdigit() for c in name_raw):
        return None
    name_unaccented = unicodedata.normalize("NFKD", name_raw).encode("ASCII", "ignore").decode("utf-8")
    clean_name = re.sub(r"[^A-Z]", "", name_unaccented.upper())
    if not clean_name or len(clean_name) < 3:
        return None

    if clean_name in COMMON_STREET_NAMES:
        return clean_name

    if clean_name in PROTECTED_STREET_WORDS:
        return None

    from entity_standardizer.address.tables import (
        WORD_ORDINALS,
        COMPOUND_ORDINALS,
        SECONDARY_UNITS,
        US_STATES,
    )
    from entity_standardizer.address._patterns import ROUTE_PREFIXES

    if (
        clean_name in DIRECTIONALS
        or clean_name in DIRECTIONALS.values()
        or clean_name in STREET_SUFFIXES
        or clean_name in STREET_SUFFIXES.values()
        or clean_name in ROUTE_PREFIXES
        or clean_name in WORD_ORDINALS
        or clean_name in COMPOUND_ORDINALS
        or clean_name in SECONDARY_UNITS
        or clean_name in SECONDARY_UNITS.values()
        or clean_name in US_STATES
        or clean_name in US_STATES.values()
    ):
        return None

    n_len = len(clean_name)
    best_match: Optional[str] = None
    allowed_distance = min(max_distance, 1)
    min_dist = allowed_distance + 1

    for cand in sorted(COMMON_STREET_NAMES):
        if abs(len(cand) - n_len) <= allowed_distance:
            # Never mutate plural or singular variants of street names
            if (
                cand + "S" == clean_name
                or cand + "ES" == clean_name
                or clean_name + "S" == cand
                or clean_name + "ES" == cand
            ):
                continue
            if n_len < 5 and sorted(clean_name) != sorted(cand):
                continue
            # Same-length single edits that are not transpositions are different words (FROST/FRONT, MARKER/MARKET).
            if n_len == len(cand) and sorted(clean_name) != sorted(cand):
                continue
            d = damerau_levenshtein_distance(clean_name, cand)
            if d <= allowed_distance and d < min_dist:
                # cand is a COMMON_STREET_NAME and clean_name is not (checked above), so d >= 1 == allowed_distance
                min_dist = d
                best_match = cand
                break

    return best_match



def heal_postal_code_transposition(postal_code: str, state: Optional[str] = None) -> Optional[str]:
    """
    Detects and corrects adjacent digit transpositions in 5-digit US postal codes
    when cross-referenced against valid ZIP3-to-state mappings.
    """
    if not postal_code or not state:
        return None

    digits = re.sub(r"[^\d]", "", postal_code)
    if len(digits) < 5:
        return None

    zip5 = digits[:5]
    norm_st = state.strip().upper()
    expected_st = US_STATES.get(norm_st, norm_st)

    # Check if current zip already matches expected state
    curr_z3 = zip5[:3]
    if curr_z3 in ZIP3_TO_STATE and ZIP3_TO_STATE[curr_z3] == expected_st:
        return zip5

    # Test adjacent digit transpositions: (0,1), (1,2), (2,3), (3,4)
    char_list = list(zip5)
    candidates: List[str] = []

    for i in range(len(char_list) - 1):
        if char_list[i] != char_list[i + 1]:
            swapped = list(char_list)
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            cand_zip = "".join(swapped)
            cand_z3 = cand_zip[:3]
            if cand_z3 in ZIP3_TO_STATE and ZIP3_TO_STATE[cand_z3] == expected_st:
                candidates.append(cand_zip)

    if len(candidates) == 1:
        return candidates[0]

    return None


def heal_street_number_transposition(
    number_str: str,
    valid_ranges: Optional[List[Tuple[int, int]]] = None,
) -> Optional[str]:
    """
    Detects and corrects adjacent digit transpositions in street house numbers
    when cross-referenced against valid building number ranges.
    """
    if not number_str or not valid_ranges:
        return None

    digits = re.sub(r"[^\d]", "", number_str)
    if len(digits) < 2:
        return None

    val = int(digits)
    # If already within a valid range, no healing needed
    for low, high in valid_ranges:
        if low <= val <= high:
            return number_str

    # Test adjacent transpositions
    char_list = list(digits)
    candidates: List[str] = []
    for i in range(len(char_list) - 1):
        if char_list[i] != char_list[i + 1]:
            swapped = list(char_list)
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            cand_str = "".join(swapped)
            cand_val = int(cand_str)
            for low, high in valid_ranges:
                if low <= cand_val <= high:
                    # Distinct adjacent swaps always yield distinct strings, so no de-duplication is needed.
                    candidates.append(cand_str)
                    break

    if len(candidates) == 1:
        m = re.match(r"^(\d+)(.*)$", number_str.strip())
        if m and m.group(2):
            return f"{candidates[0]}{m.group(2)}"
        return candidates[0]

    return None
