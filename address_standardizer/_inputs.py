"""Input coercion and guard helpers shared by the standardization pipeline."""

import math
import os
import re
from typing import Any, Optional, Tuple

from address_standardizer._patterns import RE_PRIVATE_RESIDENCE
from address_standardizer.tables import US_STATES, ZIP3_TO_STATE

# No real address line is anywhere near this long; longer inputs would only feed quadratic regexes and parsers.
MAX_FIELD_LENGTH = 600

_PO_BOX_VARIANT = re.compile(
    r"(?<![A-Za-z0-9])(?:P\.?\s?O\.?\s?B(?:OX)?\.?|POST\s+OFFICE\s+BOX)\s*#?\s*(?=[A-Za-z]?\d+(?!\d|(?:ST|ND|RD|TH)\b))",
    re.IGNORECASE,
)


def coerce_text(value: Any) -> str:
    """Turn a caller-supplied value into text: None/NaN become empty, integral floats lose their '.0'."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        text = str(int(value)) if value.is_integer() else str(value)
    elif isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:  # lone surrogates (e.g. from JSON "\ud800") cannot be stored or logged
        text = text.encode("utf-8", errors="replace").decode("utf-8")
    from address_standardizer.international.scripts import strip_zero_width

    return strip_zero_width(text)


def normalize_po_box_spelling(text: str) -> str:
    """'P.O. Box #5', 'P O Box 5', 'PO Box5', 'P.O.B. 5' and 'Post Office Box 5' all become 'PO BOX 5'."""
    return _PO_BOX_VARIANT.sub("PO BOX ", text)


_STRONG_PRIVACY_PHRASE = re.compile(
    r"\b(?:PRIVATE\s+RESIDENCE|PRIVATE\s+ADDRESS|PERSONAL\s+RESIDENCE|RESIDENTIAL\s+ADDRESS|CONFIDENTIAL\s+(?:ADDRESS|RESIDENCE))\b", re.IGNORECASE
)


def is_privacy_placeholder(*fields: str) -> bool:
    """True when a street field marks a private residence.

    Explicit phrases ("Private Residence", "Personal Residence") count anywhere in the field. Weaker words
    ("Confidential", "Residence Only", "Residential") only count when they *are* the field (optionally followed by
    a comma-separated city), so "Confidential Data Inc" and "100 Residential Dr" are left alone.
    """
    for field in fields:
        if _STRONG_PRIVACY_PHRASE.search(field):
            return True
        first_part = field.split(",")[0].strip(" .-")
        if first_part and RE_PRIVATE_RESIDENCE.fullmatch(first_part):
            return True
    return False


CORRECT_STATE_ENV = "ADDRESS_STANDARDIZER_CORRECT_STATE_FROM_ZIP"
_US_COUNTRY_NAMES = frozenset({"", "US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"})
_RE_ZIP5 = re.compile(r"^\s*(\d{5})(?:[-\s]?\d{4})?\s*$")


def correct_state_from_zip_enabled(explicit: Optional[bool]) -> bool:
    """Per-call setting wins; otherwise the ADDRESS_STANDARDIZER_CORRECT_STATE_FROM_ZIP environment switch."""
    if explicit is not None:
        return bool(explicit)
    return os.environ.get(CORRECT_STATE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def correct_state_from_zip(
    state: Optional[str], postal_code: Optional[str], country: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Replace a US state that contradicts the ZIP code with the state the ZIP belongs to.

    Returns ``(state, original_state)``; ``original_state`` is None when nothing was changed. Only a US address
    with a valid 5-digit ZIP and a *recognizable* US state that differs from the ZIP's state is touched, so
    missing/unknown states and non-US addresses pass through unchanged.
    """
    if not state or not postal_code:
        return state, None
    if (country or "").strip().upper() not in _US_COUNTRY_NAMES:
        return state, None
    m = _RE_ZIP5.match(postal_code)
    if not m:
        return state, None
    expected = ZIP3_TO_STATE.get(m.group(1)[:3])
    if not expected:
        return state, None
    raw = state.strip().upper().replace(".", "")
    current = US_STATES.get(raw, raw)
    if current not in set(US_STATES.values()) or current == expected:
        return state, None
    return expected, state
