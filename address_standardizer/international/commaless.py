"""Shared splitter for comma-less "street city [region] postal" lines (AU, NZ, CA; reusable for other countries).

``split_commaless_region_postal_city`` generalises :func:`uk.split_commaless_postal_city` with an optional
region token (state / province) between the city and the trailing postal code::

    14 Gray Court Adelaide SA 5000          -> ("14 Gray Court", "Adelaide", "SA", "5000")
    683 Abbott Street Vancouver BC V6B 0J4  -> ("683 Abbott Street", "Vancouver", "BC", "V6B 0J4")
    134 Willis Street Wellington 6011       -> ("134 Willis Street", "Wellington", "", "6011")

Precision over recall: the city is returned only when it is a known town or the plain words after the last
street-type word; otherwise it stays empty (left inside the street) and only region / postal are taken off.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable, FrozenSet, Iterable, List, Optional, Set, Tuple

from address_standardizer.international.uk import (
    _COMMALESS_TYPE_WORDS,
    split_commaless_postal_city,
    trailing_postal_width,
)

# Extra street-type words of the Commonwealth / French-Canadian styles (not in the UK list).
COMMONWEALTH_TYPE_WORDS: FrozenSet[str] = _COMMALESS_TYPE_WORDS | {
    "ESPLANADE", "HIGHWAY", "CIRCUIT", "WHARF", "BOULEVARD", "PROMENADE", "TRAIL", "ROW", "LANE", "DRIVE",
    "PARKWAY", "PDE", "ESP", "CCT", "BVD", "BLVD", "AVE", "CLOSE", "LOOP",
}

_NO_COUNTRY_TAIL = re.compile(r"(?!)")  # never matches: the caller already removed any country text

def town_set(names: Iterable[str]) -> Set[str]:
    """Upper-case town names plus their accent-free and hyphen-as-space spellings (``Trois-Rivières`` also matches
    ``Trois Rivieres``), the form :func:`split_commaless_region_postal_city` looks them up in."""
    out: Set[str] = set()
    for name in names:
        plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
        for variant in (name, plain):
            out.add(variant.upper())
            out.add(variant.upper().replace("-", " "))
    return out


# region_suffix(words_before_postal, postal) -> (number_of_trailing_words, region_code) or None
RegionSuffix = Callable[[List[str], str], Optional[Tuple[int, str]]]


def split_commaless_region_postal_city(
    text: str,
    is_postal: Callable[[str], bool],
    region_suffix: Optional[RegionSuffix],
    towns: Set[str],
    country_tail: "re.Pattern[str]",
    type_words: FrozenSet[str] = COMMONWEALTH_TYPE_WORDS,
    suffix_directionals: FrozenSet[str] = frozenset(),
    prefix_types: FrozenSet[str] = frozenset(),
) -> Optional[Tuple[str, str, str, str]]:
    """Split ``text`` into ``(street, city, region_code, postal)``; None when it has no trailing postal code.

    ``region_suffix`` recognises the region words directly before the postal code (and may veto them, e.g. when
    the postcode is not inside that state's range); None means the country has no region token (New Zealand).
    """
    words = country_tail.sub("", text).split()
    width = trailing_postal_width(words, is_postal)
    if width is None:
        return None
    postal = " ".join(words[-width:])
    rest = words[:-width]
    region = ""
    if region_suffix is not None:
        found = region_suffix(rest, postal)
        if found is not None:
            count, region = found
            rest = rest[:-count]
    split = split_commaless_postal_city(
        " ".join(rest + [postal]),
        lambda candidate: candidate == postal,
        towns,
        _NO_COUNTRY_TAIL,
        type_words,
        suffix_directionals,
        prefix_types,
    )
    if split is None:
        return None
    street, city, _ = split
    return street, city, region, postal
