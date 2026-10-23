"""
Optional transliteration of non-Latin address text to a Latin rendering.
=======================================================================
``transliterate(text)`` returns a Latin-script rendering of ``text``:

* When the optional ``anyascii`` package is installed (``pip install "address-standardizer[translit]"``, ISC
  license) it is used and covers every script it supports (Han, Kana, Hangul, Arabic, Hebrew, Thai, Indic, ...).
* Otherwise a built-in, deterministic fallback handles **Cyrillic and Greek** only, using the same letter tables
  that build the ASCII matching keys (``international/diacritics.py``). Text in any other script is never guessed
  at: ``errors="strict"`` raises :class:`TransliterationUnavailable` (a ``NotImplementedError``) and
  ``errors="passthrough"`` leaves exactly those characters unchanged. No ``?`` placeholders are ever produced.

The fallback is a plain, lossy romanization intended for display, search and matching. It is not an official
scheme (BGN/PCGN, ISO 9, ELOT 743): hard and soft signs are dropped and Greek accents are removed.

Original text is never modified in place; ``std_to_latin`` returns a new dictionary.
"""

import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from address_standardizer.international.diacritics import CYRILLIC_GREEK_MAP

__all__ = ["TransliterationUnavailable", "transliterate", "std_to_latin", "LATIN_FIELDS", "SUPPORTED_SCRIPTS"]

# Fields of ``StandardizedAddress.as_dict()`` that carry free text worth rendering in Latin script.
LATIN_FIELDS: Tuple[str, ...] = ("street1", "street2", "city", "state")

# Script names accepted for the ``script`` hint (lower case). The built-in fallback can render only the first two.
_BUILTIN_SCRIPTS = frozenset({"cyrillic", "greek"})
SUPPORTED_SCRIPTS = _BUILTIN_SCRIPTS | frozenset(
    {"latin", "han", "hiragana", "katakana", "hangul", "arabic", "hebrew", "thai", "devanagari", "bengali",
     "tamil", "georgian", "armenian"}
)

# First word of a character's Unicode name -> normalized script name. Anything else maps to its own lower-cased word
# (e.g. "TELUGU" -> "telugu"), which is reported as unsupported by the fallback.
_NAME_TO_SCRIPT = {"CJK": "han", "HANGUL": "hangul", "HIRAGANA": "hiragana", "KATAKANA": "katakana"}


class TransliterationUnavailable(NotImplementedError):
    """Raised when text contains a script that cannot be transliterated without the optional ``anyascii`` package."""


def _load_anyascii() -> Optional[Any]:
    """The ``anyascii`` callable, or None when the optional dependency is not installed."""
    try:
        from anyascii import anyascii  # type: ignore[import-not-found]
    except ImportError:
        return None
    return anyascii


def _script_of(ch: str) -> Optional[str]:
    """Script name of a non-Latin letter, or None for characters that need no transliteration (ASCII and accented
    Latin letters, digits, punctuation, combining marks)."""
    if ch.isascii() or unicodedata.category(ch)[0] != "L":
        return None
    word = unicodedata.name(ch, "UNKNOWN").split(" ", 1)[0]
    if word == "LATIN":
        return None
    return _NAME_TO_SCRIPT.get(word, word.lower())


def _builtin_char(ch: str, prev_upper: bool, next_upper: bool) -> Optional[str]:
    """Latin rendering of one Cyrillic/Greek letter, or None if the table has no entry for it."""
    mapped = CYRILLIC_GREEK_MAP.get(ch)
    if mapped is None:
        return None
    if not ch.isupper():
        return mapped.lower()
    if len(mapped) > 1 and not (prev_upper or next_upper):
        return mapped.capitalize()  # "Щ" -> "Shch", but "ЩЕ" stays upper case
    return mapped


def _builtin(text: str, errors: str) -> str:
    """Cyrillic/Greek fallback: case preserving, passes everything else through, never invents a rendering."""
    # Greek accents (tonos, dialytika) are dropped so that accented and plain spellings romanize identically.
    text = unicodedata.normalize("NFC", text)
    if any(_script_of(ch) == "greek" for ch in text):
        text = unicodedata.normalize(
            "NFC",
            "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"),
        )
    out: List[str] = []
    unsupported: List[str] = []
    for i, ch in enumerate(text):
        script = _script_of(ch)
        if script is None:
            out.append(ch)
            continue
        prev_upper = i > 0 and text[i - 1].isupper()
        next_upper = i + 1 < len(text) and text[i + 1].isupper()
        rendered = _builtin_char(ch, prev_upper, next_upper) if script in _BUILTIN_SCRIPTS else None
        if rendered is None:
            if script not in unsupported:
                unsupported.append(script)
            out.append(ch)
        else:
            out.append(rendered)
    if unsupported and errors == "strict":
        raise TransliterationUnavailable(
            "no built-in transliteration for script(s): " + ", ".join(unsupported)
            + '; install the optional dependency with: pip install "address-standardizer[translit]"'
        )
    return "".join(out)


def transliterate(text: Optional[str], script: Optional[str] = None, errors: str = "strict") -> str:
    """Latin rendering of ``text``.

    ``script`` is an optional hint naming the script the caller expects (one of ``SUPPORTED_SCRIPTS``, case
    insensitive); an unknown name raises ``ValueError``. With ``script="latin"`` the text is returned unchanged.
    For any other value the hint only validates the input: conversion always covers every script present.

    ``errors`` is ``"strict"`` (raise :class:`TransliterationUnavailable` for characters the built-in fallback cannot
    render) or ``"passthrough"`` (leave those characters unchanged). It has no effect when ``anyascii`` is installed.
    """
    if errors not in ("strict", "passthrough"):
        raise ValueError(f"errors must be 'strict' or 'passthrough', not {errors!r}")
    if script is not None:
        script = script.strip().lower()
        if script not in SUPPORTED_SCRIPTS:
            raise ValueError(f"unknown script {script!r}; expected one of {sorted(SUPPORTED_SCRIPTS)}")
    if not text:
        return ""
    if script == "latin" or text.isascii():
        return text
    anyascii = _load_anyascii()
    if anyascii is not None:
        return anyascii(text)
    return _builtin(text, errors)


def std_to_latin(std: Any, errors: str = "passthrough") -> Dict[str, Any]:
    """``std.as_dict()`` with ``street1``/``street2``/``city``/``state`` rendered in Latin script.

    Same keys as ``as_dict``; every other value is unchanged. ``errors`` defaults to ``"passthrough"`` here so that a
    script the fallback cannot render leaves that field's characters as they were rather than failing the whole
    record (pass ``"strict"`` to raise instead). Matching keys (``normalized_address_key`` etc.) are already ASCII
    and are not modified.
    """
    data = std.as_dict()
    for name in LATIN_FIELDS:
        value = data.get(name)
        if value:
            data[name] = transliterate(value, errors=errors)
    return data
