"""Lexical normalization, Unicode numeral folding, extension extraction, and ITU-T E.161 vanity decoding."""

from __future__ import annotations

import re

# Multi-script Unicode numeral & telephony punctuation translation table
_UNICODE_TRANSLATION_MAP: dict[int, str] = {
    # Full-width ASCII digits and telephony punctuation
    ord("０"): "0", ord("１"): "1", ord("２"): "2", ord("３"): "3", ord("４"): "4",
    ord("５"): "5", ord("６"): "6", ord("７"): "7", ord("８"): "8", ord("９"): "9",
    ord("＋"): "+", ord("－"): "-", ord("（"): "(", ord("）"): ")",
    ord("–"): "-", ord("—"): "-", ord("−"): "-", ord("‑"): "-",
    # Arabic-Indic digits (U+0660..U+0669)
    0x0660: "0", 0x0661: "1", 0x0662: "2", 0x0663: "3", 0x0664: "4",
    0x0665: "5", 0x0666: "6", 0x0667: "7", 0x0668: "8", 0x0669: "9",
    # Eastern Arabic-Indic / Persian digits (U+06F0..U+06F9)
    0x06F0: "0", 0x06F1: "1", 0x06F2: "2", 0x06F3: "3", 0x06F4: "4",
    0x06F5: "5", 0x06F6: "6", 0x06F7: "7", 0x06F8: "8", 0x06F9: "9",
    # Devanagari digits (U+0966..U+096F)
    0x0966: "0", 0x0967: "1", 0x0968: "2", 0x0969: "3", 0x096A: "4",
    0x096B: "5", 0x096C: "6", 0x096D: "7", 0x096E: "8", 0x096F: "9",
}

# ITU-T E.161 standard telephone keypad mapping
ITU_E161_KEYPAD_MAP: dict[str, str] = {
    "A": "2", "B": "2", "C": "2",
    "D": "3", "E": "3", "F": "3",
    "G": "4", "H": "4", "I": "4",
    "J": "5", "K": "5", "L": "5",
    "M": "6", "N": "6", "O": "6",
    "P": "7", "Q": "7", "R": "7", "S": "7",
    "T": "8", "U": "8", "V": "8",
    "W": "9", "X": "9", "Y": "9", "Z": "9",
}

# Extension patterns at the end of a phone string (RFC 3966, English, LatAm, EU, RU, JP)
_EXTENSION_RE = re.compile(
    r"(?:;ext=|(?:,|\s)+(?:"
    r"ext\.?|extension|int\.?|interno|ramal|poste|dw|durchwahl|доб\.?|内線|x|#"
    r")\s*|[;#]\s*)"
    r"([0-9]{1,7})\s*$",
    re.IGNORECASE,
)

# Leading label or RFC 3966 URI prefix
_LEADING_LABEL_RE = re.compile(
    r"^\s*(?:tel:|(?:primary\s+|main\s+|work\s+|cell\s+|mobile\s+|office\s+|phone\s+|call\s+|tel\.?\s*|ph\.?\s*|fax\.?\s*)+[:\-]?\s*)+",
    re.IGNORECASE,
)

# Trailing conversational parenthetical notes (e.g. "(ask for Sarah)", "(UK)") - preserves "(0)" and digit groups
_TRAILING_NOTE_RE = re.compile(r"\s*\([A-Za-z\s.,'\-]{2,}\)\s*$")

# Vanity token pattern: digits/prefix followed by separator and 3-8 uppercase/lowercase letters
_VANITY_CANDIDATE_RE = re.compile(
    r"(\+?[0-9()\s.\-]{3,12}[-\s.])([A-Za-z]{3,8}(?:[-\s][A-Za-z0-9]{2,6})?)"
)


def fold_unicode_digits(text: str) -> tuple[str, bool]:
    """Fold non-ASCII Unicode numerals and full-width punctuation to ASCII equivalents."""
    folded = text.translate(_UNICODE_TRANSLATION_MAP)
    return folded, (folded != text)


def extract_extension(text: str) -> tuple[str, str | None]:
    """Extract a trailing numeric extension and return (base_text, extension)."""
    # Strip trailing non-digit comments first if they follow an extension or base number
    cleaned = _TRAILING_NOTE_RE.sub("", text).strip()
    cleaned = re.sub(r"[!?\s]+$", "", cleaned)
    match = _EXTENSION_RE.search(cleaned)
    if match:
        ext = match.group(1)
        base = cleaned[:match.start()].strip()
        return base, ext
    return cleaned, None


def decode_vanity_phone(text: str) -> tuple[str, str | None]:
    """Detect and decode ITU-T E.161 alphanumeric vanity phone numbers (e.g., 1-800-FLOWERS)."""
    stripped = _LEADING_LABEL_RE.sub("", text).strip()
    match = _VANITY_CANDIDATE_RE.search(stripped)
    if not match:
        return stripped, None

    prefix_part = match.group(1)
    alpha_part = match.group(2)
    # Reconstruct clean vanity alias
    raw_alias = (prefix_part + alpha_part).strip().upper()
    raw_alias = re.sub(r"\s+", "-", raw_alias)

    decoded_chars: list[str] = []
    for ch in alpha_part.upper():
        if ch in ITU_E161_KEYPAD_MAP:
            decoded_chars.append(ITU_E161_KEYPAD_MAP[ch])
        else:
            decoded_chars.append(ch)
    decoded_tail = "".join(decoded_chars)
    replaced = stripped[:match.start()] + prefix_part + decoded_tail + stripped[match.end():]
    return replaced, raw_alias
