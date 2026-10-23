"""
Secondary-unit (suite/apt/flat) normalization helpers (split out of standardizer.py).
"""

import logging
import re
from typing import Tuple

from address_standardizer.tables import (
    DIRECTIONALS,
    STREET_SUFFIXES,
    SECONDARY_UNITS,
)
from address_standardizer._patterns import (
    RE_WHITESPACE,
    RE_NON_ALPHANUMERIC,
    RE_GLUED_HASH,
    RE_GLUED_UNIT,
    RE_GLUED_HOUSE_NUM,
    clean_repetitive_cycles,
    RE_ATTACHED_SUFFIX_EXPLICIT_UNIT,
    RE_ATTACHED_SUFFIX_BARE_UNIT,
    RE_SAINT_HYPHEN,
    RE_PRIVATE_MAILBOX,
    RE_HYPHENATED_UNIT,
    RE_INTL_FLAT,
    RE_INTL_SEC_INLINE,
    RE_INTL_SEC_START,
)

logger = logging.getLogger(__name__)


def _pre_normalize_address_string(text: str) -> str:
    """Pre-normalizes glued punctuation, symbols, formatting, and repetitive cycles."""
    text = clean_repetitive_cycles(text)
    # Split glued house numbers: '3340PEACHTREE ROAD' -> '3340 PEACHTREE ROAD'
    text = RE_GLUED_HOUSE_NUM.sub(r"\1 \2", text.strip())
    # Split glued hashtags: 'Main St#101' -> 'Main St # 101'
    text = RE_GLUED_HASH.sub(" # ", text)
    # Split glued unit prefixes: 'Apt.4B' -> 'Apt 4B'
    text = RE_GLUED_UNIT.sub(r"\1 ", text)
    # Normalize Saint hyphenation e.g. 'St-Charles' -> 'St Charles', 'Saint-Gaudens' -> 'Saint Gaudens'
    text = RE_SAINT_HYPHEN.sub(r"\1 \2", text)
    # Suffix-attached unit: 'Main St-Ste 200' -> 'Main St STE 200', 'Main St-4B' -> 'Main St APT 4B'
    text = RE_ATTACHED_SUFFIX_EXPLICIT_UNIT.sub(r"\1 \2 \3", text)
    text = RE_ATTACHED_SUFFIX_BARE_UNIT.sub(r"\1 APT \2", text)
    # Normalize Private Mailbox to PMB
    text = RE_PRIVATE_MAILBOX.sub("PMB", text)
    # Normalize STE-400 -> STE 400
    text = RE_HYPHENATED_UNIT.sub(r"\1 \2", text)
    return text


_ONES = {
    "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10,
    "ELEVEN": 11, "TWELVE": 12, "THIRTEEN": 13, "FOURTEEN": 14, "FIFTEEN": 15, "SIXTEEN": 16, "SEVENTEEN": 17,
    "EIGHTEEN": 18, "NINETEEN": 19,
}
_TENS = {"TWENTY": 20, "THIRTY": 30, "FORTY": 40, "FIFTY": 50, "SIXTY": 60, "SEVENTY": 70, "EIGHTY": 80, "NINETY": 90}
_ORDINAL_ONES = {
    "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6, "SEVENTH": 7, "EIGHTH": 8, "NINTH": 9,
    "TENTH": 10, "ELEVENTH": 11, "TWELFTH": 12, "THIRTEENTH": 13, "FOURTEENTH": 14, "FIFTEENTH": 15,
    "SIXTEENTH": 16, "SEVENTEENTH": 17, "EIGHTEENTH": 18, "NINETEENTH": 19,
}
_ORDINAL_TENS = {
    "TWENTIETH": 20, "THIRTIETH": 30, "FORTIETH": 40, "FIFTIETH": 50, "SIXTIETH": 60, "SEVENTIETH": 70,
    "EIGHTIETH": 80, "NINETIETH": 90,
}
_NUMBER_WORDS = set(_ONES) | set(_TENS) | set(_ORDINAL_ONES) | set(_ORDINAL_TENS) | {"HUNDRED"}
_UNIT_DESIGNATORS = {"STE", "SUITE", "SUIT", "APARTMENT", "APPT", "APT", "UNIT", "RM", "ROOM", "BLDG", "DEPT", "FL", "SPC", "LOT", "TRLR", "PH"}


def _words_to_number(words: list) -> int:
    """Value of a number-word run ("FIVE HUNDRED", "TWENTY FIRST", "SECOND"); -1 if it is not a valid number."""
    total, current, seen = 0, 0, False
    for w in words:
        if w in _ONES:
            current += _ONES[w]
        elif w in _ORDINAL_ONES:
            current += _ORDINAL_ONES[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w in _ORDINAL_TENS:
            current += _ORDINAL_TENS[w]
        elif w == "HUNDRED":
            if current == 0:
                return -1
            current *= 100
        else:
            return -1
        seen = True
    total += current
    return total if seen and total > 0 else -1


def _numberize_unit_words(tokens: list) -> list:
    """Replace number words next to a unit designator or FL with digits ("SECOND FL" -> "2 FL", "STE FIVE HUNDRED" -> "STE 500")."""
    # Split "TWENTY-FIRST" style hyphenation into separate words first.
    flat: list = []
    for tok in tokens:
        parts = tok.split("-")
        if len(parts) > 1 and all(p in _NUMBER_WORDS for p in parts):
            flat.extend(parts)
        else:
            flat.append(tok)
    out: list = []
    i = 0
    while i < len(flat):
        if flat[i] in _NUMBER_WORDS:
            j = i
            while j < len(flat) and flat[j] in _NUMBER_WORDS:
                j += 1
            prev_tok = flat[i - 1] if i > 0 else ""
            next_tok = flat[j] if j < len(flat) else ""
            value = _words_to_number(flat[i:j])
            if value > 0 and (prev_tok in _UNIT_DESIGNATORS or next_tok in ("FL", "FLOOR", "FLR")):
                out.append(str(value))
                i = j
                continue
        out.append(flat[i])
        i += 1
    return out


def _standardize_secondary_unit(sec: str) -> str:
    """Standardizes secondary units according to USPS Pub 28, deduplicates repeated tokens, and enforces FL <num>."""
    if not sec:
        return ""
    # Strip any leading STE or SUITE if followed by other unit types (FL, APT, UNIT, DEPT, PH, SUITE, STE) or ordinal floor
    s = re.sub(
        r"^(?:STE|SUITE)\s+(?=(?:\d+(?:ST|ND|RD|TH)\s+)?(?:FL|FLOOR|FLR|APT|APARTMENT|UNIT|DEPT|DEPARTMENT|PH|PENTHOUSE|SUITE|STE)\b)",
        "",
        sec.strip().upper(),
        flags=re.IGNORECASE,
    )
    # Clean separator punctuation between tokens, preserving hyphens in unit identifiers like 4-B or PH-A
    s = re.sub(r"[,;]+", " ", s)
    s = re.sub(r"\s+[\-–—\/]\s+", " ", s)
    raw_tokens = s.split()
    if not raw_tokens:
        return ""

    tokens = []
    for t in raw_tokens:
        if t in ("SUITE", "SUIT"):
            tokens.append("STE")
        elif t in ("FLOOR", "FLR"):
            tokens.append("FL")
        elif t in ("APARTMENT", "APPT"):
            tokens.append("APT")
        else:
            tokens.append(t)

    tokens = _numberize_unit_words(tokens)

    # Token-level repeat deduplication
    for rlen in range(1, len(tokens) // 2 + 1):
        if len(tokens) % rlen == 0:
            chunk = tokens[:rlen]
            if chunk * (len(tokens) // rlen) == tokens:
                tokens = chunk
                break

    # Floor normalization: Pub 28 strict format FL <num>
    if len(tokens) == 2 and tokens[1] in ("FL", "FLOOR", "FLR"):
        m = re.match(r"^(\d+)(?:ST|ND|RD|TH)?$", tokens[0])
        if m:
            tokens = ["FL", m.group(1)]
    elif len(tokens) == 2 and tokens[0] in ("FL", "FLOOR", "FLR"):
        m = re.match(r"^(\d+)(?:ST|ND|RD|TH)?$", tokens[1])
        if m:
            tokens = ["FL", m.group(1)]
    else:
        new_toks = []
        i = 0
        while i < len(tokens):
            if i + 1 < len(tokens) and tokens[i+1] in ("FL", "FLOOR", "FLR"):
                is_preceded_by_unit = (i > 0 and tokens[i-1] in ("STE", "APT", "UNIT", "DEPT", "RM", "ROOM", "BLDG", "PH"))
                is_ordinal = bool(re.search(r"(?:ST|ND|RD|TH)$", tokens[i]))
                m = re.match(r"^(\d+)(?:ST|ND|RD|TH)?$", tokens[i])
                if m and (not is_preceded_by_unit or is_ordinal):
                    new_toks.extend(["FL", m.group(1)])
                    i += 2
                    continue
            if tokens[i] in ("FL", "FLOOR", "FLR") and i + 1 < len(tokens):
                m = re.match(r"^(\d+)(?:ST|ND|RD|TH)?$", tokens[i+1])
                if m:
                    new_toks.extend(["FL", m.group(1)])
                    i += 2
                    continue
            new_toks.append(tokens[i])
            i += 1
        tokens = new_toks

    # Final repeat check after normalization
    for rlen in range(1, len(tokens) // 2 + 1):
        if len(tokens) % rlen == 0:
            chunk = tokens[:rlen]
            if chunk * (len(tokens) // rlen) == tokens:
                tokens = chunk
                break

    res = " ".join(tokens)
    # Strip any STE or SUITE prepended to FL, APT, UNIT, DEPT, PH
    res = re.sub(r"^(?:STE|SUITE)\s+(FL|APT|UNIT|DEPT|PH)\b", r"\1", res)
    # "No. 5" / "Number 5" / "Num 5" is the same thing as "#5": a bare unit identifier (USPS form here: STE <id>).
    res = re.sub(r"^(?:STE\s+)?(?:NO|NUM|NUMBER)\s+(?=[A-Z0-9\-]*\d|[A-Z]$)([A-Z0-9\-]+)$", r"STE \1", res)
    return res


def _split_international_secondary_unit(street1: str, street2: str) -> Tuple[str, str]:
    """Helper to detect and split secondary unit in international street string, and normalize suffixes."""
    st1 = (street1 or "").upper()
    st2 = (street2 or "").upper()

    # Pre-split Flat / Apt at start: "Flat 4 150 High Street" -> st1="150 High Street", st2="APT 4"
    m_flat = RE_INTL_FLAT.match(st1)
    if m_flat:
        st2_cand = f"APT {m_flat.group(1).upper()}"
        st2 = f"{st2_cand} {st2}".strip() if st2 else st2_cand
        st1 = m_flat.group(2).strip()

    if not st2:
        m = RE_INTL_SEC_INLINE.search(st1)
        if m:
            sec_type = m.group(1).upper()
            sec_id = m.group(2).upper()
            sec_type_norm = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
            st2 = f"{sec_type_norm} {sec_id}"
            st1 = st1[:m.start()] + st1[m.end():]
            st1 = RE_WHITESPACE.sub(" ", st1.strip(" ,.-"))
    else:
        m2 = RE_INTL_SEC_START.match(st2)
        if m2:
            sec_type = m2.group(1).upper()
            sec_type_norm = SECONDARY_UNITS.get(sec_type, "APT" if sec_type == "FLAT" else sec_type)
            st2 = f"{sec_type_norm} {m2.group(2).strip()}"

    words = st1.split()
    norm_words = []
    for w in words:
        w_clean = RE_NON_ALPHANUMERIC.sub("", w).upper()
        if w_clean in STREET_SUFFIXES:
            norm_words.append(STREET_SUFFIXES[w_clean])
        elif w_clean in DIRECTIONALS:
            norm_words.append(DIRECTIONALS[w_clean])
        else:
            norm_words.append(w)
    st1 = " ".join(norm_words)

    return st1, st2
