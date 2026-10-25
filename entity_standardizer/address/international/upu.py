"""Universal Postal Union (UPU S42) Address Template Formatter.

Implements international envelope address layout standards per UPU S42 guidelines:
- European postal-first style: <street> <house_number>\\n<postal_code> <city>\\n<COUNTRY>
- Anglo-Saxon postal-last style: <house_number> <street>\\n<city>, <state> <postal_code>\\n<COUNTRY>
- East Asian top-down style: 〒<postal_code>\\n<state/prefecture><city><street>\\n<COUNTRY>
- Non-postal nation layout: gracefully omits postal code without blank line artifacts.
"""

from __future__ import annotations

import unicodedata
from typing import Any, List, Optional, Set

from entity_standardizer.address.international.countries import CountryRegistry

# European countries adhering to postal-code before city layout
EUROPEAN_POSTAL_FIRST_ISO3: Set[str] = {
    "DEU", "AUT", "CHE", "FRA", "NLD", "BEL", "LUX", "ITA", "ESP", "PRT",
    "DNK", "SWE", "NOR", "FIN", "POL", "CZE", "SVK", "HUN", "GRC", "ROU",
    "BGR", "HRV", "SVN", "EST", "LVA", "LTU", "ISL", "MCO", "AND", "SMR",
    "VAT", "LIE", "CYP", "MLT", "ALB", "BIH", "MKD", "MNE", "SRB", "UKR",
    "BLR", "MDA",
}

# European countries where house number precedes street name
EUROPEAN_NUMBER_FIRST_ISO3: Set[str] = {
    "FRA", "BEL", "MCO", "LUX",
}

# East Asian top-down postal systems
EAST_ASIAN_ISO3: Set[str] = {
    "JPN", "CHN", "KOR", "TWN",
}

# Anglo-Saxon postal-last style countries
ANGLO_SAXON_ISO3: Set[str] = {
    "USA", "CAN", "GBR", "AUS", "NZL", "IRL", "ZAF", "JEY", "GGY", "IMN",
}


def _is_cjk(text: str) -> bool:
    """Check if string contains CJK ideographs, Hiragana, Katakana, or Hangul."""
    for ch in text:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF       # CJK Unified Ideographs
            or 0x3400 <= cp <= 0x4DBF   # CJK Extension A
            or 0x3040 <= cp <= 0x309F   # Hiragana
            or 0x30A0 <= cp <= 0x30FF   # Katakana
            or 0xAC00 <= cp <= 0xD7AF   # Hangul Syllables
            or 0x1100 <= cp <= 0x11FF   # Hangul Jamo
        ):
            return True
    return False


def format_upu_address(
    parsed: Any,
    recipient: Optional[str] = None,
    include_country_name: bool = True,
) -> str:
    """Render address in Universal Postal Union (UPU S42) envelope layout.

    Args:
        parsed: ParsedAddressComponents or StandardizedAddress instance.
        recipient: Optional addressee name to appear on top line.
        include_country_name: Whether to include the destination country on the bottom line.

    Returns:
        Formatted multi-line envelope string joined by newlines.
    """
    # 1. Resolve country metadata
    country_code = (
        getattr(parsed, "country_iso3", None)
        or getattr(parsed, "country", None)
        or "USA"
    )
    country_info = CountryRegistry.get(country_code)
    iso3 = country_info.alpha3 if country_info else str(country_code).upper()
    country_display_name = country_info.name.upper() if country_info else iso3
    has_postal = country_info.has_postal_codes if country_info else True

    # 2. Extract address components
    city = (getattr(parsed, "city", None) or "").strip()
    state = (getattr(parsed, "state", None) or "").strip()
    postal = (getattr(parsed, "postal_code", None) or "").strip()
    building = (getattr(parsed, "building_name", None) or "").strip()
    dept_loc = (getattr(parsed, "dependent_locality", None) or "").strip()

    st1 = ""
    st2 = ""
    if hasattr(parsed, "format_street1") and callable(parsed.format_street1):
        st1 = parsed.format_street1().strip()
    else:
        st1 = (getattr(parsed, "street1", None) or "").strip()

    if hasattr(parsed, "format_street2") and callable(parsed.format_street2):
        st2 = parsed.format_street2().strip()
    else:
        st2 = (getattr(parsed, "street2", None) or "").strip()

    # Specialized street number adjustment for European / continental postal-first style
    st_num = (getattr(parsed, "street_number", None) or "").strip()
    st_name = (getattr(parsed, "street_name", None) or "").strip()

    is_postal_first = iso3 in EUROPEAN_POSTAL_FIRST_ISO3 or (
        country_info is not None and country_info.postal_position == "before_city"
    )
    is_number_first = iso3 in EUROPEAN_NUMBER_FIRST_ISO3 or (
        country_info is not None and country_info.house_number_position == "before_street"
    )

    if is_postal_first:
        if is_number_first:
            # France/Belgium: house number before street
            if st_num and st_name and not (st_name.startswith(st_num + " ") or st_name == st_num):
                st1 = f"{st_num} {st_name}".strip()
        else:
            # Germany/Austria/Nordic/Eastern Europe: street before house number
            if st_num and st_name and not (st_name.endswith(" " + st_num) or st_name == st_num):
                st1 = f"{st_name} {st_num}".strip()

    # Assemble lines according to regional template
    lines: List[str] = []

    # Recipient on first line if provided
    if recipient and recipient.strip():
        lines.append(recipient.strip())

    # Template selection
    if not has_postal or not postal or (country_info is not None and country_info.postal_position == "none"):
        # -------------------------------------------------------------------
        # Non-postal nation layout (e.g. UAE, Qatar, Panama, Bahamas, Seychelles)
        # -------------------------------------------------------------------
        if building and building != st1:
            lines.append(building)
        if st1:
            lines.append(st1)
        if st2:
            lines.append(st2)
        if dept_loc and dept_loc != city:
            lines.append(dept_loc)
        if city and state:
            lines.append(f"{city}, {state}".strip())
        elif city:
            lines.append(city)
        elif state:
            lines.append(state)

    elif iso3 in EAST_ASIAN_ISO3 or (country_info is not None and country_info.postal_position == "leading_top"):
        # -------------------------------------------------------------------
        # East Asian top-down style (Japan, China, South Korea, Taiwan)
        # 〒<postal_code>\n<state/prefecture><city><street>\n<COUNTRY>
        # -------------------------------------------------------------------
        postal_str = postal
        if iso3 == "JPN":
            if not postal_str.startswith("〒"):
                postal_str = f"〒{postal_str}"
        lines.append(postal_str)

        all_cjk = any(_is_cjk(s) for s in (state, city, dept_loc, st1))
        if all_cjk:
            # CJK characters concatenated hierarchically without spaces
            lines.append(f"{state}{city}{dept_loc}{st1}".strip())  # non-empty: at least one part is CJK text
        else:
            # Romanized / ASCII representation
            parts = [p for p in (state, city, dept_loc, st1) if p]
            if parts:
                lines.append(", ".join(parts))

        if building and building != st1:
            lines.append(f"{building} {st2}".strip() if st2 else building)
        elif st2:
            lines.append(st2)

    elif is_postal_first:
        # -------------------------------------------------------------------
        # European / continental postal-first style
        # <street> <house_number>\n<postal_code> <city>\n<COUNTRY>
        # -------------------------------------------------------------------
        if building and building != st1:
            lines.append(building)
        if st1:
            lines.append(st1)
        if st2:
            lines.append(st2)
        if dept_loc and dept_loc != city:
            lines.append(dept_loc)

        lines.append(f"{postal} {city}".strip())  # postal is non-empty in this layout

    else:
        # -------------------------------------------------------------------
        # Anglo-Saxon postal-last style (USA, CAN, GBR, AUS, NZL, etc.)
        # <house_number> <street>\n<city>, <state> <postal_code>\n<COUNTRY>
        # -------------------------------------------------------------------
        if building and building != st1:
            lines.append(building)
        if st1:
            lines.append(st1)
        if st2:
            lines.append(st2)
        if dept_loc and dept_loc != city:
            lines.append(dept_loc)

        # postal is non-empty in this layout (postal-less addresses use the non-postal layout above)
        city_state = ", ".join(p for p in (city, state) if p)  # no leading comma when the city is missing
        lines.append(f"{city_state} {postal}")

    # Country line on the bottom in capital letters
    if include_country_name:
        lines.append(country_display_name)

    # Filter out empty or whitespace-only lines and return
    clean_lines = [unicodedata.normalize("NFC", line.strip()) for line in lines if line and line.strip()]
    return "\n".join(clean_lines)
