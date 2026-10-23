"""Name folding and tolerant place-name comparison used by the reference layer."""

from __future__ import annotations

import re
from typing import Tuple

from address_standardizer.fuzzy import damerau_levenshtein_distance
from address_standardizer.international.diacritics import fold_to_ascii_key

_TOKEN = re.compile(r"[A-Z0-9~]+")
# Words that do not help identify a locality ("City of Industry", "Springfield Township").
_NOISE = frozenset({"CITY", "TOWN", "VILLAGE", "TOWNSHIP", "TWP", "OF", "THE"})
# Leading abbreviations expanded so "St Louis" == "Saint Louis".
_LEADING = {"ST": "SAINT", "STE": "SAINTE", "MT": "MOUNT", "FT": "FORT"}


def fold_name(name: str) -> str:
    """Accent- and case-insensitive key for a place name (ASCII upper case; non-Latin text becomes ``~hex``)."""
    return fold_to_ascii_key(name or "")


def name_tokens(name: str) -> Tuple[str, ...]:
    """Comparable tokens of a place name: folded, split on punctuation, noise words dropped, ``St`` -> ``SAINT``."""
    tokens = _TOKEN.findall(fold_name(name))
    if tokens and tokens[0] in _LEADING:
        tokens[0] = _LEADING[tokens[0]]
    kept = [t for t in tokens if t not in _NOISE]
    return tuple(kept or tokens)


def names_match(a: str, b: str) -> bool:
    """True if two place names plausibly denote the same locality.

    Matches when the token sequences are equal, when one name's tokens are a subset of the other's
    ("Springfield" vs "East Springfield", at least 3 characters), or when the names differ by a small
    Damerau-Levenshtein distance (1 edit up to 8 characters, 2 beyond; at least 4 characters).
    """
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    sa, sb = set(ta), set(tb)
    shorter = sa if len(sa) <= len(sb) else sb
    longer = sb if shorter is sa else sa
    if shorter <= longer and len("".join(shorter)) >= 3:
        return True
    ja, jb = "".join(ta), "".join(tb)
    longest = max(len(ja), len(jb))
    if min(len(ja), len(jb)) < 4:
        return False
    return damerau_levenshtein_distance(ja, jb) <= (1 if longest <= 8 else 2)
