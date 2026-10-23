"""
Phonetic Matching & Fuzzy Blocking Keys.
=========================================
Implements American Soundex, collision-free hybrid numbered street blocking,
and compound key generation to enable typo-tolerant entity resolution
without third-party C dependencies.
"""

from typing import Optional
from address_standardizer.tables import STREET_SUFFIXES, DIRECTIONALS
from address_standardizer._patterns import (
    RE_CLEAN_ALPHA,
    RE_PO_BOX_KEY,
    RE_US_ZIP5_OR_9,
    RE_PUNCTUATION_SPLIT,
    RE_WHITESPACE,
    RE_DIGITS,
    RE_NUMBERED_STREET_KEY,
    FROZEN_DIRECTIONAL_VALUES,
    FROZEN_STREET_SUFFIX_VALUES,
)


def _pure_compute_soundex(token: str) -> str:
    """Computes standard American Soundex code for a word token in pure Python."""
    clean = RE_CLEAN_ALPHA.sub("", token.upper())
    if not clean:
        return ""
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
    }
    first_letter = clean[0]
    encoded = [first_letter]
    prev_code = mapping.get(first_letter, '0')
    for char in clean[1:]:
        code = mapping.get(char, '0')
        if code != '0':
            if code != prev_code:
                encoded.append(code)
            prev_code = code
        elif char in ('A', 'E', 'I', 'O', 'U', 'Y'):
            prev_code = '0'
        # H and W do not reset prev_code in American Soundex
    soundex_code = "".join(encoded)
    return (soundex_code + "0000")[:4]


def compute_soundex(token: str) -> str:
    """Computes standard American Soundex code for a word token with native Rust acceleration."""
    from address_standardizer._native_dispatch import try_native
    ok, result = try_native("compute_soundex", token)
    return result if ok else _pure_compute_soundex(token)


def _pure_generate_phonetic_address_key(street1: Optional[str], postal_or_zip: str = "", city: str = "") -> Optional[str]:
    """Pure Python implementation of fuzzy blocking key generation."""
    if not street1:
        return None
    st_raw = street1.strip().upper()
    if not st_raw:
        return None

    # PO Box handling
    m_pob = RE_PO_BOX_KEY.match(st_raw)
    if m_pob:
        loc = (
            postal_or_zip.strip()[:5]
            if postal_or_zip and len(postal_or_zip.strip()) >= 5
            else (postal_or_zip.strip() if postal_or_zip else city.strip())
        )
        return f"POB {m_pob.group(1)}|{loc}".strip("|")

    p_clean = postal_or_zip.strip()
    if RE_US_ZIP5_OR_9.match(p_clean):
        loc = p_clean[:5]
    elif any(c.isalpha() for c in p_clean):
        loc = p_clean
    else:
        loc = (
            p_clean[:5]
            if (p_clean and len(p_clean) >= 5)
            else (city.strip() if city else (p_clean if p_clean else ""))
        )

    st_clean = RE_PUNCTUATION_SPLIT.sub(" ", st_raw).strip()
    st_clean = RE_WHITESPACE.sub(" ", st_clean)
    parts = st_clean.split()
    if not parts:
        return None

    # Rural Route & Highway Contract handling (e.g. RR 2 BOX 152)
    if len(parts) >= 2 and parts[0] in ("RR", "HC") and parts[1].isdigit():
        rr_prefix = f"{parts[0]} {parts[1]}"
        rem = parts[2:]
        if rem and rem[0] == "BOX":
            snd = _pure_compute_soundex("BOX")
        elif rem:
            snd = _pure_compute_soundex(rem[0])
        else:
            snd = _pure_compute_soundex(parts[0])
        return f"{rr_prefix}|{snd}|{loc}".strip("|")

    # Military Unit Box handling (e.g. UNIT 1234 BOX 5678)
    if len(parts) >= 4 and parts[0] == "UNIT" and parts[1].isdigit():
        unit_num = parts[1]
        snd = _pure_compute_soundex(parts[2]) if parts[2] else "B200"
        return f"{unit_num}|{snd}|{loc}".strip("|")

    # Puerto Rico Urbanization handling (e.g. URB LAS GLADIOLAS 123 CALLE FLAMBOYAN)
    if parts[0] in ("URB", "URBANIZACION"):
        # Find first token with digits as house number
        h_idx = -1
        for idx, p in enumerate(parts[1:], 1):
            if RE_DIGITS.search(p):
                h_idx = idx
                break
        if h_idx != -1:
            house_num = parts[h_idx]
            rem_words = parts[h_idx + 1:]
            street_word = rem_words[0] if rem_words else parts[1]
            snd = _pure_compute_soundex(street_word)
            return f"{house_num}|{snd}|{loc}".strip("|")

    # Extract house number (including fractional like '100 1/2' and Queens like '123-45')
    if RE_DIGITS.search(parts[0]):
        if len(parts) > 1 and parts[1] in ("1/2", "1/4", "3/4"):
            house_num = f"{parts[0]} {parts[1]}"
            words = parts[2:]
        else:
            house_num = parts[0]
            words = parts[1:]
    else:
        house_num = ""
        words = parts[:]

    # Strip pre-directional (only if multiple words remain)
    if len(words) > 1 and (words[0] in DIRECTIONALS or words[0] in FROZEN_DIRECTIONAL_VALUES):
        # If words is just ['SOUTH', 'ST'], SOUTH is the street name, do NOT strip!
        if len(words) == 2 and (words[1] in STREET_SUFFIXES or words[1] in FROZEN_STREET_SUFFIX_VALUES):
            pass
        elif len(words) == 3 and f"{words[0]} {words[1]}" in ("NORTH EAST", "NORTH WEST", "SOUTH EAST", "SOUTH WEST", "N E", "N W", "S E", "S W") and (words[2] in STREET_SUFFIXES or words[2] in FROZEN_STREET_SUFFIX_VALUES):
            pass
        else:
            words = words[1:]

    # Strip post-directional
    if len(words) > 1 and (words[-1] in DIRECTIONALS or words[-1] in FROZEN_DIRECTIONAL_VALUES):
        words = words[:-1]

    # Strip street suffix at end
    if len(words) > 1 and (words[-1] in STREET_SUFFIXES or words[-1] in FROZEN_STREET_SUFFIX_VALUES):
        words = words[:-1]

    street_word = words[0] if words else (parts[1] if len(parts) > 1 else parts[0])

    # Hybrid numbered street resolution: prevent Soundex collisions (42nd vs 2nd, etc.)
    m_num = RE_NUMBERED_STREET_KEY.match(street_word)
    if m_num:
        snd = f"#{m_num.group(1)}"
    else:
        snd = _pure_compute_soundex(street_word)

    res = f"{house_num}|{snd}|{loc}".strip("|")
    return res or None


def generate_phonetic_address_key(
    street1: Optional[str],
    postal_or_zip: str = "",
    city: str = "",
) -> Optional[str]:
    """Generates a fuzzy blocking key with native Rust acceleration."""
    from address_standardizer._native_dispatch import try_native
    ok, result = try_native("generate_phonetic_address_key", street1, postal_or_zip=postal_or_zip, city=city)
    return result if ok else _pure_generate_phonetic_address_key(street1, postal_or_zip=postal_or_zip, city=city)
