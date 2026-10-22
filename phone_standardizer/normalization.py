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

# Extension patterns at the end of a phone string (RFC 3966 ;ext=/;isub=, parenthesized, separators, DTMF)
_EXTENSION_RE = re.compile(
    r"(?:"
    r";(?:ext|isub)=([0-9]{1,10})"
    r"|\(\s*(?:ext\.?|extension|xt\.?|int\.?|interno|ramal|poste|dw|durchwahl|доб\.?|内線|x\.?|#)\s*[:\-#]?\s*([0-9]{1,10})\s*\)"
    r"|(?:[|,;\s]+)(?:"
    r"(?:ext\.?|extension|xt\.?|int\.?|interno|ramal|poste|dw|durchwahl|доб\.?|内線)\s*[:\-#]?\s*"
    r"|x\.?\s*[:\-#]?\s*"
    r"|#\s*"
    r")([0-9]{1,10})"
    r"|(?<=\d)\s*(?:(?:ext\.?|xt\.?|x\.?|#)\s*[:\-#]?\s*([0-9]{1,10})|(?:[,;#]+|[pw]+)\s*([0-9]{1,10}))"
    r")\s*$",
    re.IGNORECASE,
)

# Leading label or RFC 3966 URI prefix (supports arbitrary "Label: " prefixes and common unpunctuated prefixes)
_LEADING_LABEL_RE = re.compile(
    r"^\s*(?:tel:|(?:[A-Za-z][A-Za-z0-9\s./&_'\-]{0,25}:\s*|"
    r"(?:primary|main|work|cell|mobile|mob|office|phone|call|contact|whatsapp|direct|home|tel|ph|fax)\.?(?:\s*[:\-]\s*|\s+))+)",
    re.IGNORECASE,
)

# Trailing conversational parenthetical notes (e.g. "(ask for Sarah)", "(UK)") - preserves "(0)" and digit groups
_TRAILING_NOTE_RE = re.compile(r"\s*\([A-Za-z\s.,'\-]{2,}\)\s*$")

# Vanity token pattern: digits/prefix followed by separator and 3-11 alphanumeric vanity letters/digits
_VANITY_CANDIDATE_RE = re.compile(
    r"(\+?[0-9()\s.,\-]{3,16}[-\s.,]?)(?=[A-Za-z])([A-Za-z0-9]*[A-Za-z]{3,8}[A-Za-z0-9]*(?:[-\s][A-Za-z0-9]{2,6})?)"
)

_TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", re.IGNORECASE)
_MULTI_PHONE_SEMI_SLASH_RE = re.compile(
    r"\s*(?:;|/|\||&)\s*(?!(?:ext|isub)=)",
    re.IGNORECASE,
)


def _fold_unicode_digits_py(text: str) -> tuple[str, bool]:
    """Pure-Python implementation of multi-script Unicode numeral folding."""
    folded = text.translate(_UNICODE_TRANSLATION_MAP)
    return folded, (folded != text)


def _fold_vanity_digits_py(text: str) -> str:
    """Pure-Python implementation of ITU-T E.161 keypad character folding."""
    return "".join(ITU_E161_KEYPAD_MAP.get(ch.upper(), ch) for ch in text)


def fold_unicode_digits(text: str) -> tuple[str, bool]:
    """Fold non-ASCII Unicode numerals and full-width punctuation to ASCII equivalents."""
    from phone_standardizer._native_dispatch import fold_unicode_digits_dispatch

    return fold_unicode_digits_dispatch(text)


def strip_leading_label(text: str) -> str:
    """Strip leading URI schemes ('tel:') and arbitrary conversational labels ('Contact: ', 'WhatsApp: ')."""
    return _LEADING_LABEL_RE.sub("", text).strip()


def split_primary_phone(text: str) -> tuple[str, bool]:
    """If text contains multiple complete phone numbers separated by ';', '/', '|', '&', or ',', return (primary_phone, was_split)."""
    parts = _MULTI_PHONE_SEMI_SLASH_RE.split(text)
    if (
        len(parts) >= 2
        and sum(c.isdigit() for c in parts[0]) >= 7
        and (
            sum(c.isdigit() for c in parts[1]) >= 7
            or (sum(c.isdigit() for c in parts[0]) >= 10 and len(parts[1].strip()) == 4 and parts[1].strip().isdigit())
        )
    ):
        p0, _ = split_primary_phone(parts[0])
        return p0.strip(), True

    if "," in text:
        cparts = text.split(",")
        for i in range(1, len(cparts)):
            p0 = ",".join(cparts[:i]).strip()
            p1 = cparts[i].strip()
            d0 = sum(c.isdigit() for c in p0)
            d1 = sum(c.isdigit() for c in p1)
            if d0 >= 7 and d1 >= 7:
                p0_sub, _ = split_primary_phone(p0)
                return p0_sub.strip(), True

    return text, False


def extract_extension(text: str) -> tuple[str, str | None]:
    """Extract a trailing numeric extension and return (base_text, extension)."""
    primary, _ = split_primary_phone(text)
    # Strip trailing non-digit comments first if they follow an extension or base number
    cleaned = _TRAILING_NOTE_RE.sub("", primary).strip()
    cleaned = re.sub(r"[!?|,;\s]+$", "", cleaned)
    match = _EXTENSION_RE.search(cleaned)
    if match:
        ext = next(g for g in match.groups() if g is not None)
        base = cleaned[:match.start()].strip()
        full_match = match.group(0).rstrip()
        delim = full_match[:-len(ext)].strip()
        if "," in delim and not any(ch.isalpha() for ch in delim):
            base_digits = sum(c.isdigit() for c in base)
            if base_digits < 10 or "," in base:
                return cleaned, None
        base = re.sub(r"[!?|,;\s]+$", "", base)
        return base, ext
    return cleaned, None


def decode_vanity_phone(text: str) -> tuple[str, str | None]:
    """Detect and decode ITU-T E.161 alphanumeric vanity phone numbers (e.g., 1-800-FLOWERS)."""
    from phone_standardizer._native_dispatch import fold_vanity_digits_dispatch

    if _TIME_RANGE_RE.search(text):
        return text.strip(), None

    stripped = strip_leading_label(text)
    match = _VANITY_CANDIDATE_RE.search(stripped)
    if not match:
        return stripped, None

    # Guard against trailing conversational words after an already-complete 10+ digit phone number
    digits_before_alpha = sum(ch.isdigit() for ch in stripped[:match.start(2)])
    if digits_before_alpha >= 10:
        return stripped[:match.start(2)].strip(), None

    prefix_part = match.group(1)
    alpha_part = match.group(2)
    # Reconstruct clean vanity alias
    raw_alias = (prefix_part + alpha_part).strip().upper()
    raw_alias = re.sub(r"[\s,]+", "-", raw_alias)

    decoded_tail = fold_vanity_digits_dispatch(alpha_part.upper())
    replaced = stripped[:match.start()] + prefix_part + decoded_tail + stripped[match.end():]
    return replaced, raw_alias


