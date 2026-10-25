"""
Care-of / attention prefix cleaner (split out of standardizer.py).

Strips ``c/o <company name>`` segments, ``(C/O ...)`` clauses and trailing legal-entity suffixes,
preserving any physical street address before or after them.
"""

import re

# Street / thoroughfare words used to recognize a physical street after a care-of name.
STREET_TYPE_WORDS = (
    "ST", "STREET", "AVE", "AVENUE", "BLVD", "BOULEVARD", "RD", "ROAD", "DR", "DRIVE", "LN", "LANE", "WAY",
    "CT", "COURT", "PL", "PLACE", "CIR", "CIRCLE", "PKWY", "PARKWAY", "HWY", "HIGHWAY", "TER", "TERRACE",
    "TRL", "TRAIL", "LOOP", "WALK", "RUN", "BLUFF", "ROW", "ALLEY", "ALY", "CTR", "CENTER", "PLAZA", "PK",
    "PARK", "PW", "HY", "HW", "BL", "BLV", "WY", "AL", "GADE", "TPKE", "TURNPIKE", "EXPY", "EXPRESSWAY",
    "PIKE", "WALKWAY", "MEWS", "SQ", "SQUARE",
)
# Words that identify a street-like tail even without a house number. Short or ambiguous abbreviations
# (AL, PK, PW, HY, HW, BL, BLV, WY, RUN, GADE) are excluded because they also occur in company names.
_AMBIGUOUS_TYPE_WORDS = frozenset({"AL", "PK", "PW", "HY", "HW", "BL", "BLV", "WY", "RUN", "GADE"})
_STREET_TAIL_WORDS = (frozenset(STREET_TYPE_WORDS) - _AMBIGUOUS_TYPE_WORDS) | {"BOX", "BROADWAY", "BOWERY"}
# Narrow set used when a c/o clause has a single leftover part and no digits.
# Single-word streets that stand alone.
_BARE_STREET_WORDS = frozenset({"BROADWAY", "BOWERY"})
_SINGLE_PART_STREET_WORDS = frozenset({
    "ST", "STREET", "RD", "ROAD", "AVE", "AVENUE", "BLVD", "BOULEVARD", "DR", "DRIVE", "LN", "LANE", "WAY",
    "CT", "COURT", "PL", "PLACE", "BOX", "HWY", "HIGHWAY", "PKWY", "PARKWAY", "CIR", "CIRCLE",
})

LEGAL_SUFFIXES_CLEAN = frozenset({
    "LLC", "LP", "LLP", "LLLPO", "INC", "CORP", "LTD", "CO", "PLLC", "PC",
    "SA", "AG", "NV", "BV", "GMBH", "PLC", "FSB", "ESQ", "CPA", "MD", "PA",
    "NA", "NTSA", "TRUST", "COMPANY", "LIMITED", "INCORPORATED", "CORPORATION",
    "PARTNERSHIP", "SGIIC", "SL", "SRL", "SARL", "SAS", "SP", "SPA", "PTY",
    "BHD", "SDN", "KGAA", "SE", "QC", "SC", "EIRL", "SCOP", "JR", "SR", "II", "III", "IV", "LPA", "APC",
    "GROUP", "DEPARTMENT", "DEPT", "DIVISION", "DIV", "OFFICE", "HOLDINGS", "VENTURES", "CAPITAL",
    "MANAGEMENT", "PARTNERS", "FINANCIAL", "SERVICES", "SOLUTIONS", "ESTATES", "PROPERTY", "PROPERTIES",
})

_STREET_ALT = "|".join(STREET_TYPE_WORDS)

_RE_STREET_BOUNDARY = re.compile(
    rf"""(?:\b|(?<=[\s,]))(?:
        # Number followed by street name and thoroughfare suffix
        (\d+\s+(?:(?:N|S|E|W|NORTH|SOUTH|EAST|WEST|NE|NW|SE|SW)\s+)?[A-Za-z0-9\.\-']+\s+(?:{_STREET_ALT})\b.*) |
        # Word numbers: ONE WORLD TRADE CENTER, etc.
        ((?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\s+(?:WORLD\s+TRADE\s+CENTER|WTC|BROADWAY|BOWERY|PENN\s+PLAZA|[A-Za-z0-9\.\-']+\s+(?:{_STREET_ALT}))\b.*) |
        # Broadway / Bowery / Embarcadero with digits
        (\d+\s+(?:(?:N|S|E|W|NORTH|SOUTH|EAST|WEST|NE|NW|SE|SW)\s+)?(?:BROADWAY|BOWERY|THE\s+EMBARCADERO|EMBARCADERO)\b.*) |
        # PO Box / Postal
        ((?:P\.?\s*O\.?\s*BOX|POB|POST\s+OFFICE\s+BOX|PSC|CMR|HC|RR)\b.*) |
        # Spanish thoroughfares
        ((?:CALLE|AVENIDA|CARR|PASEO|CAMINO|CALZADA)\b.*)
    )$""",
    re.IGNORECASE | re.VERBOSE,
)

# ATTN/ATTENTION must not be followed by a street-type word, or "123 Attention St" would be read as a care-of marker.
_CO_MARKER = rf"(?:C\s*/\s*O|C\s*/\s*-(?=\s|$)|IN\s+CARE\s+OF|(?:ATTN|ATTENTION)(?!\s+(?:{_STREET_ALT})\b))"
_CO_END = r"(?:\b|(?<=-))"  # "C/-" (Australian care-of) ends in a non-word character
RE_CO_PAREN = re.compile(rf"[\(\[]{_CO_MARKER}{_CO_END}[^)\]]*[\)\]]", re.IGNORECASE)
RE_CO_PAREN_START = re.compile(rf"[\(\[]{_CO_MARKER}{_CO_END}", re.IGNORECASE)
RE_CO_MARKER = re.compile(rf"(?:^|[\s,]){_CO_MARKER}{_CO_END}[:\s\-]*", re.IGNORECASE)

# Matches a legal suffix followed by more text; ordered longest-first so the alternation is deterministic.
_RE_LEGAL_SUFFIX_THEN_TEXT = re.compile(
    r"\b(?:" + "|".join(sorted(LEGAL_SUFFIXES_CLEAN, key=lambda w: (-len(w), w))) + r")\b[\s,]+(?=[A-Za-z0-9])",
    re.IGNORECASE,
)
_RE_NUMBERED_TAIL = re.compile(r"\b(\d+\s+[A-Za-z].*)$")


def has_care_of(text: str) -> bool:
    """True if the text contains a care-of / attention marker."""
    return bool(RE_CO_PAREN_START.search(text) or RE_CO_MARKER.search(text))


def _looks_like_street(candidate: str) -> bool:
    """A tail after a legal suffix is a street only if it has a house number or *ends* in a street-type word.

    Requiring the street type to be the last word keeps company-name tails such as "Park Capital Partners",
    "Ocean Park Holdings" or "Way Financial" from becoming a delivery line.
    """
    if re.search(r"\d", candidate):
        return True
    words = [w.upper() for w in re.findall(r"\w+", candidate)]
    if not words:
        return False
    if len(words) == 1:
        return words[0] in _BARE_STREET_WORDS
    return words[-1] in _STREET_TAIL_WORDS


def _street_after_legal_suffix(after_co: str) -> str:
    """Pick the street following the *last* legal suffix whose tail is not just more suffix words."""
    matches = list(_RE_LEGAL_SUFFIX_THEN_TEXT.finditer(after_co))
    for m in reversed(matches):
        candidate = after_co[m.end():].strip(" ,.-")  # never empty: the regex lookahead requires an alphanumeric
        words = [w.upper() for w in re.findall(r"\w+", candidate)]
        if words and all(w in LEGAL_SUFFIXES_CLEAN for w in words):
            continue
        # The tail is only a street if it looks like one; otherwise it is just the rest of the c/o name
        # (e.g. "C/O CORE PROPERTY P/S", "... GROUP AB").
        if not _looks_like_street(candidate):
            continue
        return candidate
    return ""


def strip_care_of(text: str) -> str:
    """Remove care-of / attention clauses, keeping any physical street address."""
    return extract_care_of(text)[0]


def extract_care_of(text: str) -> "tuple[str, str]":
    """Split ``text`` into ``(address_without_care_of, care_of_text)``.

    ``care_of_text`` is what was removed ("ACME HOLDINGS LLC" for "c/o Acme Holdings LLC, 100 Main St"), so the
    information is reported instead of discarded; it is ``""`` when there is no care-of clause.
    """
    if not text:
        return "", ""

    removed: list = []
    prev = None
    curr = text
    while curr != prev:  # pragma: no branch  (every pass either breaks or removes a marker, so the guard never ends the loop)
        prev = curr
        # Strip parenthesized or bracketed care-of / attn clauses: (C/O ...) or [C/O ...]
        for m_paren in RE_CO_PAREN.finditer(curr):
            inner = re.sub(rf"^[\(\[]\s*{_CO_MARKER}{_CO_END}[:\s\-]*", "", m_paren.group(0), flags=re.IGNORECASE)
            inner = inner.rstrip(")] ").strip(" ,.-")
            if inner:
                removed.append(inner)
        curr = RE_CO_PAREN.sub(" ", curr).strip(" ,.-")

        m_co = RE_CO_MARKER.search(curr)
        if not m_co:
            break

        prefix = curr[:m_co.start()].strip(" ,.-")
        after_co = curr[m_co.end():].strip()

        extracted_street = ""
        m_boundary = _RE_STREET_BOUNDARY.search(after_co)
        if m_boundary:
            extracted_street = m_boundary.group(0).strip(" ,.-")
        else:
            extracted_street = _street_after_legal_suffix(after_co)

        if not extracted_street:
            m_fb = _RE_NUMBERED_TAIL.search(after_co)
            if m_fb:
                extracted_street = m_fb.group(1).strip(" ,.-")

        if extracted_street:
            idx = after_co.rfind(extracted_street)
            care_piece = after_co[:idx] if idx >= 0 else after_co.replace(extracted_street, "", 1)
            care_piece = care_piece.strip(" ,.-")
            if care_piece:
                removed.append(care_piece)
        elif prefix:
            removed.append(after_co.strip(" ,.-"))

        if prefix and extracted_street:
            curr = f"{prefix}, {extracted_street}"
        elif extracted_street:
            curr = extracted_street
        elif prefix:
            curr = prefix
        else:
            co_parts = [p.strip() for p in curr.split(",") if p.strip()]
            rem_co = co_parts[1:]
            while rem_co and rem_co[0].upper().replace(".", "").replace("&", "").replace(" ", "").strip() in LEGAL_SUFFIXES_CLEAN:
                rem_co = rem_co[1:]
            if len(rem_co) == 1 and not re.search(r"\d", rem_co[0]):
                words = set(re.findall(r"\w+", rem_co[0].upper()))
                if not (words & _SINGLE_PART_STREET_WORDS):
                    rem_co = []
            kept = ", ".join(rem_co)
            care_piece = after_co.replace(kept, "", 1).strip(" ,.-") if kept else after_co.strip(" ,.-")
            if care_piece:
                removed.append(care_piece)
            curr = kept
        curr = curr.strip(" ,.-")
    return curr, "; ".join(dict.fromkeys(removed))
