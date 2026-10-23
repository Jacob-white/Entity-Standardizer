"""Global Postal Code Validation and Extraction Engine.

Covers all 160+ postal-issuing countries and territories with official regex
patterns, length bounds, illegal character detection, and canonical formatting.
Provides graceful handling for non-postal nations, robust extraction from noisy
unformatted international address lines, and detailed diagnostics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Pattern, Set, Tuple, Union

from address_standardizer.international.countries import CountryInfo, CountryRegistry


@dataclass(frozen=True)
class PostalValidationResult:
    """Structured postal code validation diagnostic result."""

    is_valid: bool
    postal_code: str
    country_code: str  # ISO-3166-1 alpha-3
    reason: str
    formatted_code: Optional[str] = None
    is_non_postal_country: bool = False


@dataclass(frozen=True)
class PostalRule:
    """Validation and formatting rule for a country's postal code system."""

    alpha3: str
    pattern: Pattern[str]
    min_length: int
    max_length: int
    allows_alphanumeric: bool = False
    format_func: Optional[Callable[[str], str]] = None
    allowed_prefixes: Tuple[str, ...] = ()
    description: str = ""
    example: str = ""


# ---------------------------------------------------------------------------
# Country-Specific Formatting Helpers
# ---------------------------------------------------------------------------


def _format_uk(code: str) -> str:
    """Canonical Royal Mail format: outward + inward separated by a single space."""
    clean = re.sub(r"\s+", "", code).upper()
    if clean == "GIR0AA":
        return "GIR 0AA"
    if len(clean) >= 5:
        return f"{clean[:-3]} {clean[-3:]}"
    return clean


def _format_canada(code: str) -> str:
    """Canonical Canada Post format: A1A 1A1."""
    clean = re.sub(r"\s+", "", code).upper()
    if len(clean) == 6:
        return f"{clean[:3]} {clean[3:]}"
    return clean


def _format_netherlands(code: str) -> str:
    """Canonical PostNL format: 1234 AB."""
    clean = re.sub(r"\s+", "", code).upper()
    if len(clean) == 6:
        return f"{clean[:4]} {clean[4:]}"
    return clean


def _format_japan(code: str) -> str:
    """Canonical Japan Post format: 123-4567."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 7:
        return f"{clean[:3]}-{clean[3:]}"
    return clean


def _format_poland(code: str) -> str:
    """Canonical Poczta Polska format: 12-345."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 5:
        return f"{clean[:2]}-{clean[2:]}"
    return clean


def _format_portugal(code: str) -> str:
    """Canonical CTT Portugal format: 1234-567 or 1234."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 7:
        return f"{clean[:4]}-{clean[4:]}"
    return clean


def _format_brazil(code: str) -> str:
    """Canonical Correios Brazil format: 12345-678."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 8:
        return f"{clean[:5]}-{clean[5:]}"
    return clean


def _format_sweden(code: str) -> str:
    """Canonical PostNord Sweden format: 123 45."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 5:
        return f"{clean[:3]} {clean[3:]}"
    return clean


def _format_czech_slovak(code: str) -> str:
    """Canonical Czech/Slovak format: 123 45."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 5:
        return f"{clean[:3]} {clean[3:]}"
    return clean


def _format_greece(code: str) -> str:
    """Canonical ELTA Greece format: 123 45."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 5:
        return f"{clean[:3]} {clean[3:]}"
    return clean


def _format_usa(code: str) -> str:
    """Canonical USPS format: 12345 or 12345-6789."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 9:
        return f"{clean[:5]}-{clean[5:]}"
    return clean


def _format_saudi(code: str) -> str:
    """Canonical Saudi Post format: 12345 or 12345-6789."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 9:
        return f"{clean[:5]}-{clean[5:]}"
    return clean


def _format_korea(code: str) -> str:
    """Canonical Korea Post format: 12345 or legacy 123-456."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) == 6:
        return f"{clean[:3]}-{clean[3:]}"
    return clean


def _format_ireland(code: str) -> str:
    """Canonical Eircode format: D02 X285."""
    clean = re.sub(r"[\s\-]", "", code).upper()
    if len(clean) == 7:
        return f"{clean[:3]} {clean[3:]}"
    return clean


def _format_cayman(code: str) -> str:
    """Canonical Cayman Islands format: KY1-1104."""
    clean = re.sub(r"[^\dA-Za-z]", "", code).upper()
    if clean.startswith("CYM"):
        clean = clean[3:]
    m = re.match(r"^KY([123])(\d{4})$", clean)
    if m:
        return f"KY{m.group(1)}-{m.group(2)}"
    m2 = re.match(r"^KY(\d{4})$", clean)
    if m2:
        return f"KY1-{m2.group(1)}"
    if len(clean) == 4 and clean.isdigit():
        return f"KY1-{clean}"
    if clean.startswith("KY") and len(clean) == 7:
        return f"{clean[:3]}-{clean[3:]}"
    return clean


def _format_vgb(code: str) -> str:
    """Canonical British Virgin Islands format: VG1110."""
    clean = re.sub(r"[^\dA-Za-z]", "", code).upper()
    if clean.startswith("VG"):
        return clean
    if len(clean) == 4 and clean.isdigit():
        return f"VG{clean}"
    return clean


def _format_malta(code: str) -> str:
    """Canonical MaltaPost format: VLT 1115."""
    clean = re.sub(r"\s+", "", code).upper()
    if len(clean) >= 5:
        return f"{clean[:3]} {clean[3:]}"
    return clean


def _format_bermuda(code: str) -> str:
    """Canonical Bermuda format: HM 11."""
    clean = re.sub(r"\s+", "", code).upper()
    if len(clean) == 4:
        return f"{clean[:2]} {clean[2:]}"
    return clean


# ---------------------------------------------------------------------------
# Specific Country Semantic Validation Checks
# ---------------------------------------------------------------------------
_DISALLOWED_NLD_COMBOS: Set[str] = {"SA", "SD", "SS"}
_DISALLOWED_UK_OUTWARD_POS1: Set[str] = {"Q", "V", "X"}
_DISALLOWED_UK_OUTWARD_POS2: Set[str] = {"I", "J", "Z"}
_DISALLOWED_UK_INWARD: Set[str] = {"C", "I", "K", "M", "O", "V"}

_RE_CAN_EXACT = re.compile(
    r"^([A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z])\s*(\d[A-CEGHJ-NPR-TV-Z]\d)$",
    re.IGNORECASE,
)
_RE_UK_EXACT = re.compile(
    r"^(GIR|[A-Z]{1,2}\d[A-Z0-9]?)\s*(\d[A-Z]{2})$",
    re.IGNORECASE,
)
_RE_NLD_EXACT = re.compile(
    r"^([1-9]\d{3})\s*([A-Z]{2})$",  # PostNL: first digit 1-9 (no leading zero)
    re.IGNORECASE,
)


def _validate_uk_semantics(code: str) -> bool:
    """Validate Royal Mail outward and inward character constraints."""
    clean = re.sub(r"\s+", " ", code.strip().upper())
    if clean == "GIR 0AA":
        return True
    m = _RE_UK_EXACT.match(clean)
    if not m:
        return False
    outward = m.group(1).upper()
    inward = m.group(2).upper()
    if len(outward) >= 1 and outward[0] in _DISALLOWED_UK_OUTWARD_POS1:
        return False
    if len(outward) >= 2 and outward[1].isalpha() and outward[1] in _DISALLOWED_UK_OUTWARD_POS2:
        return False
    # The regex guarantees a 3-character inward code (digit + two letters).
    if inward[1] in _DISALLOWED_UK_INWARD or inward[2] in _DISALLOWED_UK_INWARD:
        return False
    return True


def _validate_canadian_semantics(code: str) -> bool:
    """Validate Canada Post FSA/LDU character constraints."""
    clean = re.sub(r"\s+", " ", code.strip().upper())
    m = _RE_CAN_EXACT.match(clean)
    return m is not None


def _validate_dutch_semantics(code: str) -> bool:
    """Validate PostNL 4-digit + 2-letter constraints excluding SA/SD/SS."""
    clean = re.sub(r"\s+", " ", code.strip().upper())
    m = _RE_NLD_EXACT.match(clean)
    if not m:
        return False
    letters = m.group(2).upper()
    return letters not in _DISALLOWED_NLD_COMBOS


# ---------------------------------------------------------------------------
# Global Catalog of 196 Postal-Issuing Countries & Territories
# ---------------------------------------------------------------------------


def _rule(
    alpha3: str,
    pattern_str: str,
    min_len: int,
    max_len: int,
    allows_alnum: bool = False,
    format_fn: Optional[Callable[[str], str]] = None,
    prefixes: Tuple[str, ...] = (),
    desc: str = "",
    example: str = "",
) -> PostalRule:
    return PostalRule(
        alpha3=alpha3,
        pattern=re.compile(pattern_str, re.IGNORECASE),
        min_length=min_len,
        max_length=max_len,
        allows_alphanumeric=allows_alnum,
        format_func=format_fn,
        allowed_prefixes=prefixes,
        description=desc,
        example=example,
    )


POSTAL_RULES: Dict[str, PostalRule] = {
    # North America & Caribbean
    "USA": _rule(
        "USA", r"^\d{5}(?:-?\d{4})?$", 5, 9,
        format_fn=_format_usa, desc="5 digits or ZIP+4", example="10005-1234",
    ),
    "CAN": _rule(
        "CAN", r"^[A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z]\s*\d[A-CEGHJ-NPR-TV-Z]\d$",
        6, 6, allows_alnum=True, format_fn=_format_canada,
        desc="A1A 1A1 alternating", example="M5V 2T6",
    ),
    "MEX": _rule("MEX", r"^\d{5}$", 5, 5, desc="5 digits", example="06000"),
    "PRI": _rule("PRI", r"^00[6-9]\d{2}(?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (00600-00999)", example="00901"),
    "VIR": _rule("VIR", r"^008\d{2}(?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (00801-00851)", example="00802"),
    "GUM": _rule("GUM", r"^969\d{2}(?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (96910-96932)", example="96910"),
    "ASM": _rule("ASM", r"^96799(?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (96799)", example="96799"),
    "MNP": _rule("MNP", r"^9695[0-2](?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (96950-96952)", example="96950"),
    "UMI": _rule("UMI", r"^96898(?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (96898)", example="96898"),
    "ABW": _rule("ABW", r"^\d{4}$", 4, 4, desc="4 digits", example="1234"),
    "AIA": _rule("AIA", r"^AI-?2640$", 4, 7, allows_alnum=True, desc="AI-2640", example="AI-2640"),
    "BES": _rule("BES", r"^\d{4}$", 4, 4, desc="4 digits", example="1234"),
    "BLM": _rule("BLM", r"^97133$", 5, 5, desc="5 digits (97133)", example="97133"),
    "BMU": _rule("BMU", r"^(?:[A-Z]{2}\s?\d{2}|HM\s?[A-Z]X)$", 4, 4, allows_alnum=True, format_fn=_format_bermuda, desc="2 letters + 2 digits (area codes are not whitelisted: published lists disagree), or the Hamilton P.O. Box form HM <letter>X", example="HM 11"),
    "BRB": _rule("BRB", r"^BB\d{5}$", 7, 7, allows_alnum=True, desc="BB + 5 digits", example="BB11000"),
    "CUB": _rule("CUB", r"^(?:CP\s*)?\d{5}$", 5, 5, desc="5 digits", example="10100"),
    "CUW": _rule("CUW", r"^\d{4}$", 4, 4, desc="4 digits", example="1234"),
    "CYM": _rule("CYM", r"^(?:KY[1-3]?[- ]?)?\d{4}$", 4, 7, allows_alnum=True, format_fn=_format_cayman, prefixes=("CYM-", "CYM ", "CYM", "KY-", "KY "), desc="KY1-xxxx or 4 digits", example="KY1-1104"),
    "DOM": _rule("DOM", r"^\d{5}$", 5, 5, desc="5 digits", example="10101"),
    "GLP": _rule("GLP", r"^971\d{2}$", 5, 5, desc="5 digits (971xx)", example="97100"),
    "HTI": _rule("HTI", r"^\d{4}$", 4, 4, desc="4 digits", example="6110"),
    "JAM": _rule("JAM", r"^\d{2}$|^JM[A-Z]{3}\d{2}$", 2, 7, allows_alnum=True, desc="2 digits or JM + 3 letters + 2 digits", example="01"),
    "MAF": _rule("MAF", r"^97150$", 5, 5, desc="5 digits (97150)", example="97150"),
    "MSR": _rule("MSR", r"^MSR\s*\d{4}$", 7, 7, allows_alnum=True, desc="MSR + 4 digits", example="MSR 1110"),
    "MTQ": _rule("MTQ", r"^972\d{2}$", 5, 5, desc="5 digits (972xx)", example="97200"),
    "SPM": _rule("SPM", r"^97500$", 5, 5, desc="5 digits (97500)", example="97500"),
    "SXM": _rule("SXM", r"^\d{4}$", 4, 4, desc="4 digits", example="1234"),
    "TCA": _rule("TCA", r"^TKCA\s*1ZZ$", 7, 7, allows_alnum=True, desc="TKCA 1ZZ", example="TKCA 1ZZ"),
    "TTO": _rule("TTO", r"^\d{6}$", 6, 6, desc="6 digits", example="100110"),
    "VCT": _rule("VCT", r"^VC\d{4}$", 6, 6, allows_alnum=True, desc="VC + 4 digits", example="VC0100"),
    "VGB": _rule(
        "VGB", r"^(?:VG\s*)?\d{4}$", 4, 6,
        allows_alnum=True,
        format_fn=_format_vgb,
        prefixes=("BVI-", "BVI ", "BVI", "VG-", "VG "),
        desc="VG + 4 digits", example="VG1110",
    ),

    # Central & South America
    "ARG": _rule("ARG", r"^(?:\d{4}|[A-Z]\d{4}[A-Z]{3})$", 4, 8, allows_alnum=True, desc="4 digits or CPA 8 chars", example="C1024CWN"),
    "BOL": _rule("BOL", r"^\d{4,5}$", 4, 5, desc="4 or 5 digits", example="1234"),
    "BRA": _rule("BRA", r"^\d{5}(?:-?\d{3})?$", 5, 8, format_fn=_format_brazil, desc="8 digits (5+3)", example="01310-200"),
    "CHL": _rule("CHL", r"^\d{7}$|^\d{3}-?\d{4}$", 7, 7, desc="7 digits (3+4)", example="8320000"),
    "COL": _rule("COL", r"^\d{6}$", 6, 6, desc="6 digits", example="110111"),
    "CRI": _rule("CRI", r"^\d{5}$", 5, 5, desc="5 digits", example="10101"),
    "ECU": _rule("ECU", r"^(?:(?:EC)?\d{6}|\d{2}-\d{2}-\d{2})$", 6, 8, allows_alnum=True, desc="6 digits", example="170504"),
    "FLK": _rule("FLK", r"^FIQQ\s*1ZZ$", 7, 7, allows_alnum=True, desc="FIQQ 1ZZ", example="FIQQ 1ZZ"),
    "GUF": _rule("GUF", r"^973\d{2}$", 5, 5, desc="5 digits (973xx)", example="97300"),
    "GTM": _rule("GTM", r"^\d{5}$", 5, 5, desc="5 digits", example="01001"),
    "HND": _rule("HND", r"^\d{5}$", 5, 5, desc="5 digits", example="11101"),
    "NIC": _rule("NIC", r"^\d{5}$", 5, 5, desc="5 digits", example="11001"),
    "PER": _rule("PER", r"^\d{5}$|^\d{2}$", 2, 5, desc="5 digits or 2 digits", example="15001"),
    "PRY": _rule("PRY", r"^\d{4}$", 4, 4, desc="4 digits", example="1530"),
    "SLV": _rule("SLV", r"^(?:CP\s*)?\d{4}$", 4, 4, desc="4 digits", example="1101"),
    "SGS": _rule("SGS", r"^SIQQ\s*1ZZ$", 7, 7, allows_alnum=True, desc="SIQQ 1ZZ", example="SIQQ 1ZZ"),
    "URY": _rule("URY", r"^\d{5}$", 5, 5, desc="5 digits", example="11000"),
    "VEN": _rule("VEN", r"^\d{4}(?:-[A-Z])?$", 4, 5, allows_alnum=True, desc="4 digits", example="1010"),

    # Europe
    "GBR": _rule(
        "GBR", r"^(?:GIR\s*0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})$",
        5, 7, allows_alnum=True, format_fn=_format_uk,
        desc="Royal Mail alphanumeric format", example="SW1A 1AA",
    ),
    "DEU": _rule("DEU", r"^\d{5}$", 5, 5, prefixes=("D-", "DE-", "DEU-"), desc="5 digits", example="10115"),
    "FRA": _rule("FRA", r"^\d{5}$", 5, 5, prefixes=("F-", "FR-", "FRA-"), desc="5 digits", example="75001"),
    "ITA": _rule("ITA", r"^\d{5}$", 5, 5, prefixes=("I-", "IT-", "ITA-"), desc="5 digits", example="00185"),
    "ESP": _rule("ESP", r"^(?:0[1-9]|[1-4]\d|5[0-2])\d{3}$", 5, 5, prefixes=("E-", "ES-", "ESP-"), desc="5 digits (01000-52999)", example="28001"),
    "NLD": _rule(
        "NLD", r"^[1-9]\d{3}\s*[A-Z]{2}$", 6, 6, allows_alnum=True,
        format_fn=_format_netherlands, prefixes=("NL-", "NLD-"),
        desc="4 digits + 2 letters", example="1012 JS",
    ),
    "BEL": _rule("BEL", r"^[1-9]\d{3}$", 4, 4, prefixes=("B-", "BE-", "BEL-"), desc="4 digits (1000-9999)", example="1000"),
    "CHE": _rule("CHE", r"^[1-9]\d{3}$", 4, 4, prefixes=("CH-", "CHE-"), desc="4 digits (1000-9999)", example="8001"),
    "AUT": _rule("AUT", r"^\d{4}$", 4, 4, prefixes=("A-", "AT-", "AUT-"), desc="4 digits", example="1010"),
    "SWE": _rule("SWE", r"^\d{3}\s?\d{2}$", 5, 5, format_fn=_format_sweden, prefixes=("SE-", "SWE-", "S-"), desc="5 digits (3+2)", example="111 22"),
    "NOR": _rule("NOR", r"^\d{4}$", 4, 4, prefixes=("N-", "NO-", "NOR-"), desc="4 digits", example="0150"),
    "DNK": _rule("DNK", r"^\d{4}$", 4, 4, prefixes=("DK-", "DNK-"), desc="4 digits", example="1050"),
    "FIN": _rule("FIN", r"^\d{5}$", 5, 5, prefixes=("FI-", "FIN-"), desc="5 digits", example="00100"),
    "POL": _rule("POL", r"^\d{2}-?\d{3}$", 5, 5, format_fn=_format_poland, prefixes=("PL-", "POL-"), desc="5 digits (2+3)", example="00-950"),
    "PRT": _rule("PRT", r"^\d{4}(?:-?\d{3})?$", 4, 7, format_fn=_format_portugal, prefixes=("P-", "PT-", "PRT-"), desc="4 or 7 digits (4+3)", example="1000-001"),
    "IRL": _rule("IRL", r"^(?:[AC-FHKNPRTV-Y]\d{2}|D6W)\s?[0-9AC-FHKNPRTV-Y]{4}$", 7, 7, allows_alnum=True, format_fn=_format_ireland, desc="Eircode: routing key (letter from ACDEFHKNPRTVWXY + 2 digits, or D6W) + 4 characters from 0-9ACDEFHKNPRTVWXY", example="D02 X285"),
    "CZE": _rule("CZE", r"^\d{3}\s?\d{2}$", 5, 5, format_fn=_format_czech_slovak, prefixes=("CZ-", "CZE-"), desc="5 digits (3+2)", example="110 00"),
    "SVK": _rule("SVK", r"^\d{3}\s?\d{2}$", 5, 5, format_fn=_format_czech_slovak, prefixes=("SK-", "SVK-"), desc="5 digits (3+2)", example="811 01"),
    "HUN": _rule("HUN", r"^[1-9]\d{3}$", 4, 4, prefixes=("H-", "HU-", "HUN-"), desc="4 digits", example="1011"),
    "ROU": _rule("ROU", r"^\d{6}$", 6, 6, prefixes=("RO-", "ROU-"), desc="6 digits", example="010011"),
    "BGR": _rule("BGR", r"^\d{4}$", 4, 4, prefixes=("BG-", "BGR-"), desc="4 digits", example="1000"),
    "GRC": _rule("GRC", r"^\d{3}\s?\d{2}$", 5, 5, format_fn=_format_greece, prefixes=("GR-", "GRC-"), desc="5 digits (3+2)", example="104 31"),
    "RUS": _rule("RUS", r"^\d{6}$", 6, 6, prefixes=("RU-", "RUS-"), desc="6 digits", example="101000"),
    "UKR": _rule("UKR", r"^\d{5}$", 5, 5, prefixes=("UA-", "UKR-"), desc="5 digits", example="01001"),
    "BLR": _rule("BLR", r"^\d{6}$", 6, 6, prefixes=("BY-", "BLR-"), desc="6 digits", example="220030"),
    "HRV": _rule("HRV", r"^\d{5}$", 5, 5, prefixes=("HR-", "HRV-"), desc="5 digits", example="10000"),
    "SVN": _rule("SVN", r"^(?:SI-?)?\d{4}$", 4, 6, allows_alnum=True, prefixes=("SI-", "SVN-"), desc="4 digits", example="1000"),
    "BIH": _rule("BIH", r"^\d{5}$", 5, 5, prefixes=("BA-", "BIH-"), desc="5 digits", example="71000"),
    "SRB": _rule("SRB", r"^\d{5}$", 5, 5, prefixes=("RS-", "SRB-"), desc="5 digits", example="11000"),
    "MNE": _rule("MNE", r"^\d{5}$", 5, 5, prefixes=("ME-", "MNE-"), desc="5 digits", example="81000"),
    "MKD": _rule("MKD", r"^\d{4}$", 4, 4, prefixes=("MK-", "MKD-"), desc="4 digits", example="1000"),
    "ALB": _rule("ALB", r"^\d{4}$", 4, 4, desc="4 digits", example="1001"),
    "EST": _rule("EST", r"^\d{5}$", 5, 5, prefixes=("EE-", "EST-"), desc="5 digits", example="10111"),
    "LVA": _rule("LVA", r"^(?:LV-?)?\d{4}$", 4, 6, allows_alnum=True, prefixes=("LV-", "LVA-"), desc="4 digits", example="1050"),
    "LTU": _rule("LTU", r"^(?:LT-?)?\d{5}$", 5, 7, allows_alnum=True, prefixes=("LT-", "LTU-"), desc="5 digits", example="01100"),
    "MDA": _rule("MDA", r"^(?:MD-?)?\d{4}$", 4, 6, allows_alnum=True, prefixes=("MD-", "MDA-"), desc="4 digits", example="2012"),
    "LUX": _rule("LUX", r"^(?:L-?)?\d{4}$", 4, 6, allows_alnum=True, prefixes=("L-", "LU-", "LUX-"), desc="4 digits", example="1111"),
    "ISL": _rule("ISL", r"^\d{3}$", 3, 3, prefixes=("IS-", "ISL-"), desc="3 digits", example="101"),
    "MLT": _rule("MLT", r"^[A-Z]{3}\s*\d{2,4}$", 5, 7, allows_alnum=True, format_fn=_format_malta, desc="3 letters + 2-4 digits", example="VLT 1115"),
    "CYP": _rule("CYP", r"^\d{4}$", 4, 4, prefixes=("CY-", "CYP-"), desc="4 digits", example="1010"),
    "MCO": _rule("MCO", r"^(?:MC-?)?980\d{2}$", 5, 7, allows_alnum=True, prefixes=("MC-", "MCO-"), desc="5 digits (980xx)", example="98000"),
    "AND": _rule("AND", r"^AD\d{3}$", 5, 5, allows_alnum=True, desc="AD + 3 digits", example="AD500"),
    "SMR": _rule("SMR", r"^4789\d$", 5, 5, prefixes=("SM-", "SMR-"), desc="5 digits (4789x)", example="47890"),
    "VAT": _rule("VAT", r"^(?:VA-?)?00120$", 5, 7, allows_alnum=True, prefixes=("VA-", "VAT-"), desc="00120", example="00120"),
    "LIE": _rule("LIE", r"^\d{4}$", 4, 4, prefixes=("FL-", "LIE-"), desc="4 digits (948x-949x)", example="9490"),
    "GIB": _rule("GIB", r"^GX11\s*1AA$", 7, 7, allows_alnum=True, desc="GX11 1AA", example="GX11 1AA"),
    "GGY": _rule(
        "GGY", r"^GY\d[A-Z0-9]?\s*\d[A-Z]{2}$", 6, 7,
        allows_alnum=True, format_fn=_format_uk,
        prefixes=("GB-", "GB ", "GB", "UK-", "UK ", "UK", "GGY-", "GGY ", "GGY"),
        desc="GY + UK format", example="GY1 1AA",
    ),
    "JEY": _rule(
        "JEY", r"^JE\d[A-Z0-9]?\s*\d[A-Z]{2}$", 6, 7,
        allows_alnum=True, format_fn=_format_uk,
        prefixes=("GB-", "GB ", "GB", "UK-", "UK ", "UK", "JEY-", "JEY ", "JEY"),
        desc="JE + UK format", example="JE1 1AA",
    ),
    "IMN": _rule(
        "IMN", r"^IM\d[A-Z0-9]?\s*\d[A-Z]{2}$", 6, 7,
        allows_alnum=True, format_fn=_format_uk,
        prefixes=("GB-", "GB ", "GB", "UK-", "UK ", "UK", "IMN-", "IMN ", "IMN"),
        desc="IM + UK format", example="IM1 1AA",
    ),
    "ALA": _rule("ALA", r"^(?:AX-?)?22\d{3}$", 5, 7, allows_alnum=True, desc="5 digits (22xxx)", example="22100"),
    "FRO": _rule("FRO", r"^(?:FO-?)?\d{3}$", 3, 5, allows_alnum=True, prefixes=("FO-", "FRO-"), desc="3 digits", example="100"),
    "GRL": _rule("GRL", r"^39\d{2}$", 4, 4, desc="4 digits (39xx)", example="3900"),
    "SJM": _rule("SJM", r"^917\d$", 4, 4, desc="4 digits (917x)", example="9170"),

    # Asia & Middle East
    "JPN": _rule("JPN", r"^\d{3}-?\d{4}$", 7, 7, format_fn=_format_japan, desc="7 digits (3+4)", example="100-0001"),
    "CHN": _rule("CHN", r"^\d{6}$", 6, 6, desc="6 digits", example="100000"),
    "KOR": _rule("KOR", r"^\d{5}$|^\d{3}-?\d{3}$", 5, 6, format_fn=_format_korea, desc="5 digits or 6 digits", example="03186"),
    "TWN": _rule("TWN", r"^\d{3}(?:-?\d{2,3})?$", 3, 6, desc="3, 5, or 6 digits", example="100-01"),
    "IND": _rule("IND", r"^[1-9]\d{5}$", 6, 6, desc="6 digits", example="110001"),
    "SGP": _rule(
        "SGP", r"^\d{6}$", 6, 6,
        prefixes=("SGP-", "SGP ", "SGP", "SG-", "SG ", "SG", "S-", "S ", "S"),
        desc="6 digits", example="049909",
    ),
    "MYS": _rule("MYS", r"^\d{5}$", 5, 5, desc="5 digits", example="50450"),
    "THA": _rule("THA", r"^\d{5}$", 5, 5, desc="5 digits", example="10100"),
    "IDN": _rule("IDN", r"^\d{5}$", 5, 5, desc="5 digits", example="10110"),
    "PHL": _rule("PHL", r"^\d{4}$", 4, 4, desc="4 digits", example="1000"),
    "VNM": _rule("VNM", r"^\d{5,6}$", 5, 6, desc="5 or 6 digits", example="100000"),
    "PAK": _rule("PAK", r"^\d{5}$", 5, 5, desc="5 digits", example="44000"),
    "BGD": _rule("BGD", r"^\d{4}$", 4, 4, desc="4 digits", example="1205"),
    "LKA": _rule("LKA", r"^\d{5}$", 5, 5, desc="5 digits", example="00100"),
    "NPL": _rule("NPL", r"^\d{5}$", 5, 5, desc="5 digits", example="44600"),
    "SAU": _rule("SAU", r"^\d{5}(?:-\d{4})?$", 5, 9, format_fn=_format_saudi, desc="5 digits or 5+4", example="11564"),
    "ISR": _rule("ISR", r"^\d{5}$|^\d{7}$", 5, 7, desc="7 digits (or legacy 5)", example="9100001"),
    "TUR": _rule("TUR", r"^\d{5}$", 5, 5, prefixes=("TR-", "TUR-"), desc="5 digits", example="34000"),
    "IRN": _rule("IRN", r"^\d{5}(?:-?\d{5})?$", 5, 10, desc="5 or 10 digits", example="11111-11111"),
    "IRQ": _rule("IRQ", r"^\d{5}$", 5, 5, desc="5 digits", example="10001"),
    "JOR": _rule("JOR", r"^\d{5}$", 5, 5, desc="5 digits", example="11118"),
    "KWT": _rule("KWT", r"^\d{5}$", 5, 5, desc="5 digits", example="13001"),
    "LBN": _rule("LBN", r"^\d{4}(?:\s?\d{4})?$", 4, 8, desc="4 or 8 digits", example="1107 2020"),
    "OMN": _rule("OMN", r"^\d{3}$", 3, 3, desc="3 digits", example="100"),
    "BHR": _rule("BHR", r"^\d{3,4}$", 3, 4, desc="3 or 4 digits", example="317"),
    "PSE": _rule("PSE", r"^\d{3}$|^\d{5}$", 3, 5, desc="3 or 5 digits", example="90100"),
    "KAZ": _rule("KAZ", r"^\d{6}$|^[A-Z]\d{2}[A-Z\d]{4}$", 6, 7, allows_alnum=True, desc="6 digits or alphanumeric", example="010000"),
    "UZB": _rule("UZB", r"^\d{6}$", 6, 6, desc="6 digits", example="100000"),
    "KGZ": _rule("KGZ", r"^\d{6}$", 6, 6, desc="6 digits", example="720000"),
    "TJK": _rule("TJK", r"^\d{6}$", 6, 6, desc="6 digits", example="734000"),
    "TKM": _rule("TKM", r"^\d{6}$", 6, 6, desc="6 digits", example="744000"),
    "AFG": _rule("AFG", r"^\d{4}$", 4, 4, desc="4 digits", example="1001"),
    "ARM": _rule("ARM", r"^\d{4}$", 4, 4, desc="4 digits", example="0010"),
    "AZE": _rule("AZE", r"^(?:AZ-?)?\d{4}$", 4, 6, allows_alnum=True, desc="AZ + 4 digits", example="AZ1000"),
    "GEO": _rule("GEO", r"^\d{4}$", 4, 4, desc="4 digits", example="0101"),
    "MNG": _rule("MNG", r"^\d{5,6}$", 5, 6, desc="5 or 6 digits", example="15160"),
    "MMR": _rule("MMR", r"^\d{5}$", 5, 5, desc="5 digits", example="11181"),
    "KHM": _rule("KHM", r"^\d{5,6}$", 5, 6, desc="5 or 6 digits", example="12000"),
    "LAO": _rule("LAO", r"^\d{5}$", 5, 5, desc="5 digits", example="01000"),
    "BRN": _rule("BRN", r"^[A-Z]{2}\d{4}$", 6, 6, allows_alnum=True, desc="2 letters + 4 digits", example="BA1234"),
    "MDV": _rule("MDV", r"^\d{4,5}$", 4, 5, desc="4 or 5 digits", example="20026"),
    "BTN": _rule("BTN", r"^\d{5}$", 5, 5, desc="5 digits", example="11001"),

    # Oceania
    "AUS": _rule(
        "AUS", r"^\d{4}$", 4, 4,
        prefixes=(
            "AUS-", "AUS ", "AUS", "AU-", "AU ", "AU",
            "NSW-", "NSW ", "NSW",
            "VIC-", "VIC ", "VIC",
            "QLD-", "QLD ", "QLD",
            "SA-", "SA ", "SA",
            "WA-", "WA ", "WA",
            "TAS-", "TAS ", "TAS",
            "ACT-", "ACT ", "ACT",
            "NT-", "NT ", "NT",
        ),
        desc="4 digits", example="2000",
    ),
    "NZL": _rule("NZL", r"^\d{4}$", 4, 4, desc="4 digits", example="6011"),
    "PNG": _rule("PNG", r"^\d{3}$", 3, 3, desc="3 digits", example="111"),
    "CCK": _rule("CCK", r"^6799$", 4, 4, desc="4 digits (6799)", example="6799"),
    "CXR": _rule("CXR", r"^6798$", 4, 4, desc="4 digits (6798)", example="6798"),
    "NFK": _rule("NFK", r"^2899$", 4, 4, desc="4 digits (2899)", example="2899"),
    "HMD": _rule("HMD", r"^7151$", 4, 4, desc="4 digits (7151)", example="7151"),
    "FSM": _rule("FSM", r"^9694[1-4](?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (96941-96944)", example="96941"),
    "MHL": _rule("MHL", r"^969[67]0(?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (96960/96970)", example="96960"),
    "PLW": _rule("PLW", r"^96940(?:-\d{4})?$", 5, 9, format_fn=_format_usa, desc="5 digits (96940)", example="96940"),
    "NCL": _rule("NCL", r"^988\d{2}$", 5, 5, desc="5 digits (988xx)", example="98800"),
    "PYF": _rule("PYF", r"^987\d{2}$", 5, 5, desc="5 digits (987xx)", example="98700"),
    "WLF": _rule("WLF", r"^98600$", 5, 5, desc="5 digits (98600)", example="98600"),
    "WSM": _rule("WSM", r"^\d{4}$", 4, 4, desc="4 digits", example="1750"),
    "PCN": _rule("PCN", r"^PCRN\s*1ZZ$", 7, 7, allows_alnum=True, desc="PCRN 1ZZ", example="PCRN 1ZZ"),

    # Africa
    "ZAF": _rule("ZAF", r"^\d{4}$", 4, 4, desc="4 digits", example="2000"),
    "EGY": _rule("EGY", r"^\d{5}$", 5, 5, desc="5 digits", example="11511"),
    "NGA": _rule("NGA", r"^\d{6}$", 6, 6, desc="6 digits", example="100001"),
    "KEN": _rule("KEN", r"^\d{5}$", 5, 5, desc="5 digits", example="00100"),
    "MAR": _rule("MAR", r"^\d{5}$", 5, 5, desc="5 digits", example="10000"),
    "DZA": _rule("DZA", r"^\d{5}$", 5, 5, desc="5 digits", example="16000"),
    "TUN": _rule("TUN", r"^\d{4}$", 4, 4, desc="4 digits", example="1000"),
    "ETH": _rule("ETH", r"^\d{4}$", 4, 4, desc="4 digits", example="1000"),
    "AGO": _rule("AGO", r"^\d{4}$", 4, 4, desc="4 digits", example="1000"),
    "MOZ": _rule("MOZ", r"^\d{4}$", 4, 4, desc="4 digits", example="1100"),
    "MDG": _rule("MDG", r"^\d{3}$", 3, 3, desc="3 digits", example="101"),
    "MUS": _rule("MUS", r"^\d{5}$|^\d{3}[A-Z]{2}\d{3}$", 5, 8, allows_alnum=True, desc="5 digits or alphanumeric", example="11101"),
    "NAM": _rule("NAM", r"^\d{4,5}$", 4, 5, desc="4 or 5 digits", example="9000"),
    "SEN": _rule("SEN", r"^\d{5}$", 5, 5, desc="5 digits", example="12500"),
    "SDN": _rule("SDN", r"^\d{5}$", 5, 5, desc="5 digits", example="11111"),
    "ZMB": _rule("ZMB", r"^\d{5}$", 5, 5, desc="5 digits", example="10101"),
    "MWI": _rule("MWI", r"^\d{4}$|^\d{6}$", 4, 6, desc="4 or 6 digits", example="1234"),
    "TZA": _rule("TZA", r"^\d{5}$", 5, 5, desc="5 digits", example="11101"),
    "UGA": _rule("UGA", r"^\d{4,5}$", 4, 5, desc="4 or 5 digits", example="12345"),
    "CPV": _rule("CPV", r"^\d{4}$", 4, 4, desc="4 digits", example="7600"),
    "LSO": _rule("LSO", r"^\d{3}$", 3, 3, desc="3 digits", example="100"),
    "SWZ": _rule("SWZ", r"^[A-Z]\d{3}$", 4, 4, allows_alnum=True, desc="1 letter + 3 digits", example="H100"),
    "LBR": _rule("LBR", r"^\d{4}$", 4, 4, desc="4 digits", example="1000"),
    "LBY": _rule("LBY", r"^\d{5}$", 5, 5, desc="5 digits", example="10000"),
    "NER": _rule("NER", r"^\d{4}$", 4, 4, desc="4 digits", example="8000"),
    "TGO": _rule("TGO", r"^\d{4,5}$", 4, 5, desc="4 or 5 digits", example="1234"),
    "CIV": _rule("CIV", r"^\d{2}$", 2, 2, desc="2 digits", example="01"),
    "ESH": _rule("ESH", r"^\d{5}$", 5, 5, desc="5 digits", example="70000"),
    "MYT": _rule("MYT", r"^976\d{2}$", 5, 5, desc="5 digits (976xx)", example="97600"),
    "REU": _rule("REU", r"^974\d{2}$", 5, 5, desc="5 digits (974xx)", example="97400"),
    "SHN": _rule("SHN", r"^(?:STHL|ASCN|TDCU)\s*1ZZ$", 7, 7, allows_alnum=True, desc="STHL/ASCN/TDCU 1ZZ", example="STHL 1ZZ"),

    # Remaining Outlying / Polar Territories
    "ATA": _rule("ATA", r"^\d{4,5}$", 4, 5, desc="4 or 5 digits", example="9999"),
    "ATF": _rule("ATF", r"^984\d{2}$", 5, 5, desc="5 digits (984xx)", example="98400"),
    "BVT": _rule("BVT", r"^7447$", 4, 4, desc="4 digits (7447)", example="7447"),
    "IOT": _rule("IOT", r"^BBND\s*1ZZ$", 7, 7, allows_alnum=True, desc="BBND 1ZZ", example="BBND 1ZZ"),
}


DEPRECATED_POSTAL_RULES: Dict[str, PostalRule] = {
    # Hong Kong and Macao do not use domestic postal codes.
    # China Post routing codes 999077/999078 are deprecated in favor of non-postal nation status.
    "HKG": _rule("HKG", r"^999077$", 6, 6, desc="China Post routing code (deprecated)", example="999077"),
    "MAC": _rule("MAC", r"^999078$", 6, 6, desc="China Post routing code (deprecated)", example="999078"),
}


# ---------------------------------------------------------------------------
# Public Functions: validate_postal_code and extract_postal_code
# ---------------------------------------------------------------------------


def validate_postal_code(
    postal_code: Optional[str],
    country_code: Optional[str] = None,
    return_details: bool = False,
    *,
    country: Optional[str] = None,
) -> Union[bool, PostalValidationResult]:
    """Validate a postal code against national postal authority specifications.

    Resolves country via CountryRegistry. Gracefully validates non-postal nations
    (e.g., UAE, Qatar, Panama, Bahamas) where postal codes are not used or required.

    Args:
        postal_code: Postal code string (or None/empty).
        country_code: ISO-3166-1 alpha-2, alpha-3, numeric code, or country name.
        return_details: When True, returns a PostalValidationResult dataclass with
            validation diagnostics; otherwise returns a boolean.
        country: Optional alias for country_code.

    Returns:
        bool or PostalValidationResult depending on return_details.
    """
    effective_country = country_code or country or ""
    raw_pc = str(postal_code).strip() if postal_code is not None else ""
    c_info = CountryRegistry.get(effective_country)

    if c_info is None:
        norm_code = effective_country.strip().upper() if effective_country else ""
        res = PostalValidationResult(
            is_valid=False,
            postal_code=raw_pc,
            country_code=norm_code,
            reason=f"Unknown or unsupported country: '{effective_country}'",
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    # Graceful handling for non-postal countries
    if not c_info.has_postal_codes:
        res = PostalValidationResult(
            is_valid=True,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason="Non-postal nation; postal code not required",
            formatted_code=raw_pc if raw_pc else None,
            is_non_postal_country=True,
        )
        return res if return_details else True

    # Postal country requires a code
    if not raw_pc:
        res = PostalValidationResult(
            is_valid=False,
            postal_code="",
            country_code=c_info.alpha3,
            reason=f"Postal code is required for {c_info.name} ({c_info.alpha3})",
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    rule = POSTAL_RULES.get(c_info.alpha3)
    if rule is None:
        # Fallback for country with postal codes not in explicit catalog
        clean = re.sub(r"\s+", " ", raw_pc).upper()
        res = PostalValidationResult(
            is_valid=True,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason="Valid postal code format (standard length)",
            formatted_code=clean,
            is_non_postal_country=False,
        )
        return res if return_details else True

    # Strip permitted external country / jurisdiction prefix (e.g. "D-10115" -> "10115", "NSW 2000" -> "2000", "S238880" -> "238880")
    check_code = raw_pc
    if rule.allowed_prefixes:
        for pfx in sorted(rule.allowed_prefixes, key=len, reverse=True):
            if check_code.upper().startswith(pfx.upper()):
                check_code = check_code[len(pfx):].strip().lstrip("-").strip()
                break

    # Jurisdictional normalization before regex validation
    if c_info.alpha3 == "VGB":
        # British Virgin Islands: normalize "VG 1110" -> "VG1110"
        check_code = re.sub(r"^VG\s+(\d{4})$", r"VG\1", check_code, flags=re.IGNORECASE)
    elif c_info.alpha3 == "CYM":
        # Cayman Islands: normalize "KY 1104", "KY-1104", "KY1 1104", "1104", "CYM 1104"
        check_code = re.sub(r"^KY\s+(\d{4})$", r"KY1-\1", check_code, flags=re.IGNORECASE)
        check_code = re.sub(r"^KY-(\d{4})$", r"KY1-\1", check_code, flags=re.IGNORECASE)
        check_code = re.sub(r"^KY([1-3])\s+(\d{4})$", r"KY\1-\2", check_code, flags=re.IGNORECASE)
        check_code = re.sub(r"^KY([1-3])(\d{4})$", r"KY\1-\2", check_code, flags=re.IGNORECASE)
        if re.match(r"^\d{4}$", check_code):
            check_code = f"KY1-{check_code}"
    elif c_info.alpha3 == "JEY":
        check_code = re.sub(r"^JE-(\d)", r"JE\1", check_code, flags=re.IGNORECASE)
    elif c_info.alpha3 == "GGY":
        check_code = re.sub(r"^GY-(\d)", r"GY\1", check_code, flags=re.IGNORECASE)
    elif c_info.alpha3 == "IMN":
        check_code = re.sub(r"^IM-(\d)", r"IM\1", check_code, flags=re.IGNORECASE)

    # Character validity checks
    if not rule.allows_alphanumeric:
        if re.search(r"[A-Za-z]", check_code):
            res = PostalValidationResult(
                is_valid=False,
                postal_code=raw_pc,
                country_code=c_info.alpha3,
                reason=f"Postal code contains illegal alphabetic characters for {c_info.name} ({c_info.alpha3})",
                formatted_code=None,
                is_non_postal_country=False,
            )
            return res if return_details else False
        if re.search(r"[^\d\s\-]", check_code):
            res = PostalValidationResult(
                is_valid=False,
                postal_code=raw_pc,
                country_code=c_info.alpha3,
                reason=f"Postal code contains illegal characters for {c_info.name} ({c_info.alpha3})",
                formatted_code=None,
                is_non_postal_country=False,
            )
            return res if return_details else False
    else:
        if re.search(r"[^\w\s\-]", check_code):
            res = PostalValidationResult(
                is_valid=False,
                postal_code=raw_pc,
                country_code=c_info.alpha3,
                reason=f"Postal code contains illegal characters for {c_info.name} ({c_info.alpha3})",
                formatted_code=None,
                is_non_postal_country=False,
            )
            return res if return_details else False

    # Length bounds check (alphanumeric characters only)
    alnum_code = re.sub(r"[^A-Za-z0-9]", "", check_code)
    if len(alnum_code) < rule.min_length:
        res = PostalValidationResult(
            is_valid=False,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason=(
                f"Postal code '{raw_pc}' is too short for {c_info.name} ({c_info.alpha3}): "
                f"expected {rule.min_length} to {rule.max_length} characters"
            ),
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    if len(alnum_code) > rule.max_length:
        res = PostalValidationResult(
            is_valid=False,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason=(
                f"Postal code '{raw_pc}' is too long for {c_info.name} ({c_info.alpha3}): "
                f"expected {rule.min_length} to {rule.max_length} characters"
            ),
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    # Regex pattern check
    norm_check = re.sub(r"\s+", " ", check_code.strip()).upper()
    if not rule.pattern.match(norm_check):
        res = PostalValidationResult(
            is_valid=False,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason=f"Postal code '{raw_pc}' does not match official format for {c_info.name} ({c_info.alpha3})",
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    # Special semantic constraints
    if c_info.alpha3 == "GBR" and not _validate_uk_semantics(norm_check):
        res = PostalValidationResult(
            is_valid=False,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason=f"Postal code '{raw_pc}' violates Royal Mail character constraints for United Kingdom",
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    if c_info.alpha3 == "CAN" and not _validate_canadian_semantics(norm_check):
        res = PostalValidationResult(
            is_valid=False,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason=f"Postal code '{raw_pc}' contains invalid characters for Canada Post",
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    if c_info.alpha3 == "NLD" and not _validate_dutch_semantics(norm_check):
        res = PostalValidationResult(
            is_valid=False,
            postal_code=raw_pc,
            country_code=c_info.alpha3,
            reason=f"Postal code '{raw_pc}' contains disallowed combination for Netherlands",
            formatted_code=None,
            is_non_postal_country=False,
        )
        return res if return_details else False

    # Canonical formatting
    formatted = rule.format_func(norm_check) if rule.format_func else norm_check
    res = PostalValidationResult(
        is_valid=True,
        postal_code=raw_pc,
        country_code=c_info.alpha3,
        reason="Valid postal code format",
        formatted_code=formatted,
        is_non_postal_country=False,
    )
    return res if return_details else True


_UNANCHORED_CACHE: Dict[str, "re.Pattern[str]"] = {}


def _unanchored(pattern: "re.Pattern[str]") -> "re.Pattern[str]":
    """A search version of an anchored validation pattern: ``^code$`` becomes ``(?<![A-Z0-9])code(?![A-Z0-9])``."""
    cached = _UNANCHORED_CACHE.get(pattern.pattern)
    if cached is None:
        body = pattern.pattern.removeprefix("^").removesuffix("$").replace("$|^", "|")
        cached = re.compile(r"(?<![A-Za-z0-9])(?:" + body + r")(?![A-Za-z0-9])", pattern.flags | re.IGNORECASE)
        _UNANCHORED_CACHE[pattern.pattern] = cached
    return cached


def _extract_for_country(text: str, c_info: CountryInfo) -> Optional[str]:
    """Isolate postal code for a known country using specific matching heuristics."""
    alpha3 = c_info.alpha3

    # Canada
    if alpha3 == "CAN":
        m = re.search(
            r"\b([A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z]\s*\d[A-CEGHJ-NPR-TV-Z]\d)\b",
            text,
            re.IGNORECASE,
        )
        if m:
            res = validate_postal_code(m.group(1), "CAN", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # United Kingdom
    if alpha3 in ("GBR", "GGY", "JEY", "IMN"):
        m = re.search(
            r"\b(GIR\s*0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
            text,
            re.IGNORECASE,
        )
        if m:
            res = validate_postal_code(m.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Netherlands
    if alpha3 == "NLD":
        m = re.search(r"\b(\d{4}\s*[A-Z]{2})\b", text, re.IGNORECASE)
        if m:
            res = validate_postal_code(m.group(1), "NLD", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Ireland
    if alpha3 == "IRL":
        m = re.search(r"\b([A-Za-z]\d[0-9A-Za-z]\s*[0-9A-Za-z]{4})\b", text)
        if m:
            res = validate_postal_code(m.group(1), "IRL", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Japan
    if alpha3 == "JPN":
        m = re.search(r"(?:〒\s*)?(?<!\d)(\d{3}-\d{4})\b", text)
        if m:
            res = validate_postal_code(m.group(1), "JPN", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        m7 = re.findall(r"\b(\d{7})\b", text)
        if m7:
            res = validate_postal_code(m7[-1], "JPN", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Brazil
    if alpha3 == "BRA":
        m = re.search(r"(?:CEP\s*)?(\d{5}-?\d{3})\b", text, re.IGNORECASE)
        if m:
            res = validate_postal_code(m.group(1), "BRA", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Poland
    if alpha3 == "POL":
        m = re.search(r"\b(\d{2}-\d{3})\b", text)
        if m:
            res = validate_postal_code(m.group(1), "POL", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Portugal
    if alpha3 == "PRT":
        m = re.search(r"\b(\d{4}-\d{3})\b", text)
        if m:
            res = validate_postal_code(m.group(1), "PRT", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Argentina
    if alpha3 == "ARG":
        m = re.search(r"\b([A-Z]\d{4}[A-Z]{3})\b", text)
        if m:
            res = validate_postal_code(m.group(1), "ARG", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Singapore
    if alpha3 == "SGP":
        m_sg = re.search(r"\b(?:SGP|SG|S)\s*(\d{6})\b", text, re.IGNORECASE)
        if m_sg:
            res = validate_postal_code(m_sg.group(0), "SGP", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        matches_sg = list(re.finditer(r"\b(\d{6})\b", text))
        for m in reversed(matches_sg):
            res = validate_postal_code(m.group(1), "SGP", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Australia
    if alpha3 == "AUS":
        m_au = re.search(r"\b(?:NSW|VIC|QLD|SA|WA|TAS|ACT|NT|AU|AUS)\s*(\d{4})\b", text, re.IGNORECASE)
        if m_au:
            res = validate_postal_code(m_au.group(0), "AUS", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        matches_au = list(re.finditer(r"\b(\d{4})\b", text))
        for m in reversed(matches_au):
            res = validate_postal_code(m.group(1), "AUS", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # British Virgin Islands
    if alpha3 == "VGB":
        m_vg = re.search(r"\b(?:BVI[- ]*)?(?:VG[- ]*|\bBVI[- ]*)(\d{4})\b", text, re.IGNORECASE)
        if m_vg:
            res = validate_postal_code(m_vg.group(0), "VGB", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        matches_vg = list(re.finditer(r"\b(\d{4})\b", text))
        for m in reversed(matches_vg):
            res = validate_postal_code(m.group(1), "VGB", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Cayman Islands
    if alpha3 == "CYM":
        m_ky = re.search(r"\b(?:CYM[- ]*)?(?:KY[1-3]?[- ]*)(\d{4})\b", text, re.IGNORECASE)
        if m_ky:
            res = validate_postal_code(m_ky.group(0), "CYM", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        matches_ky = list(re.finditer(r"\b(\d{4})\b", text))
        for m in reversed(matches_ky):
            res = validate_postal_code(m.group(1), "CYM", return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # United States & Territories
    if alpha3 in ("USA", "PRI", "VIR", "GUM", "ASM", "MNP", "UMI", "FSM", "MHL", "PLW"):
        # Check State + ZIP first
        m_sz = re.search(r"\b[A-Z]{2}\s+(\d{5}(?:-\d{4})?)\b", text)
        if m_sz:
            res = validate_postal_code(m_sz.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        # Check ZIP+4
        m_z4 = re.search(r"\b(\d{5}-\d{4})\b", text)
        if m_z4:
            res = validate_postal_code(m_z4.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        # Check all 5-digit tokens, prioritizing the last (trailing) token
        matches = list(re.finditer(r"\b(\d{5})\b", text))
        for m in reversed(matches):
            res = validate_postal_code(m.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Standard 5-digit European / Global countries
    rule = POSTAL_RULES.get(alpha3)
    if rule and rule.min_length == 5 and rule.max_length == 5 and not rule.allows_alphanumeric:
        m_pfx = re.search(r"\b(?:[A-Z]{1,3}-)(\d{5})\b", text)
        if m_pfx:
            res = validate_postal_code(m_pfx.group(0), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        matches = list(re.finditer(r"\b(\d{5})\b", text))
        for m in reversed(matches):
            res = validate_postal_code(m.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        # Space-separated 3+2 groups as written in CZ, SK, SE, GR ("111 51")
        for m in reversed(list(re.finditer(r"\b(\d{3}\s\d{2})\b", text))):
            res = validate_postal_code(m.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Standard 6-digit countries (China, India, Russia, Singapore, Colombia, etc.)
    if rule and rule.min_length == 6 and rule.max_length == 6 and not rule.allows_alphanumeric:
        matches = list(re.finditer(r"\b(\d{6})\b", text))
        for m in reversed(matches):
            res = validate_postal_code(m.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Standard 4-digit countries (Australia, Austria, Switzerland, Belgium, South Africa, etc.)
    if rule and rule.min_length == 4 and rule.max_length == 4 and not rule.allows_alphanumeric:
        matches = list(re.finditer(r"\b(\d{4})\b", text))
        for m in reversed(matches):
            res = validate_postal_code(m.group(1), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code
        return None

    # Generic search using country's regex
    if rule:
        matches = list(_unanchored(rule.pattern).finditer(text))
        for m in reversed(matches):
            res = validate_postal_code(m.group(0), alpha3, return_details=True)
            if isinstance(res, PostalValidationResult) and res.is_valid:
                return res.formatted_code

    return None


def _extract_candidate_any(text: str) -> Optional[str]:
    """Candidate matchers across prioritized international postal formats."""
    # 1. Canada Post
    m_can = re.search(
        r"\b([A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z]\s*\d[A-CEGHJ-NPR-TV-Z]\d)\b",
        text,
        re.IGNORECASE,
    )
    if m_can:
        res = validate_postal_code(m_can.group(1), "CAN", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 2. Royal Mail UK
    m_uk = re.search(
        r"\b(GIR\s*0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
        text,
        re.IGNORECASE,
    )
    if m_uk:
        res = validate_postal_code(m_uk.group(1), "GBR", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 3. Netherlands PostNL
    m_nld = re.search(r"\b(\d{4}\s*[A-Z]{2})\b", text, re.IGNORECASE)
    if m_nld:
        res = validate_postal_code(m_nld.group(1), "NLD", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 4. Ireland Eircode
    m_irl = re.search(r"\b([A-Za-z]\d[0-9A-Za-z]\s*[0-9A-Za-z]{4})\b", text)
    if m_irl:
        res = validate_postal_code(m_irl.group(1), "IRL", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 5. Japan 3+4
    m_jpn = re.search(r"(?:〒\s*)?(?<!\d)(\d{3}-\d{4})\b", text)
    if m_jpn:
        res = validate_postal_code(m_jpn.group(1), "JPN", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 6. Brazil CEP
    m_bra = re.search(r"(?:CEP\s*)?(\d{5}-\d{3})\b", text, re.IGNORECASE)
    if m_bra:
        res = validate_postal_code(m_bra.group(1), "BRA", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 7. Poland 2+3
    m_pol = re.search(r"\b(\d{2}-\d{3})\b", text)
    if m_pol:
        res = validate_postal_code(m_pol.group(1), "POL", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 8. Portugal 4+3
    m_prt = re.search(r"\b(\d{4}-\d{3})\b", text)
    if m_prt:
        res = validate_postal_code(m_prt.group(1), "PRT", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 9. Argentina CPA
    m_arg = re.search(r"\b([A-Z]\d{4}[A-Z]{3})\b", text)
    if m_arg:
        res = validate_postal_code(m_arg.group(1), "ARG", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 10. US ZIP+4
    m_z4 = re.search(r"\b(\d{5}-\d{4})\b", text)
    if m_z4:
        res = validate_postal_code(m_z4.group(1), "USA", return_details=True)
        if isinstance(res, PostalValidationResult) and res.is_valid:
            return res.formatted_code

    # 11. Explicit postal keyword prefix
    m_kw = re.search(
        r"\b(?:ZIP(?:\s+CODE)?|POSTAL(?:\s+CODE)?|POSTCODE|PLZ|CEP|C\.?P\.?|CAP)\s*[:#]?\s*([A-Z0-9\- ]{3,10})\b",
        text,
        re.IGNORECASE,
    )
    if m_kw:
        cand = m_kw.group(1).strip()
        alnum = re.sub(r"[^A-Za-z0-9]", "", cand)
        if 3 <= len(alnum) <= 10:
            return re.sub(r"\s+", " ", cand).upper()

    # 12. European country prefix (e.g. D-10115, F-75008, CH-8001)
    m_ep = re.search(r"\b(?:[A-Z]{1,3}-)(\d{4,5})\b", text)
    if m_ep:
        return m_ep.group(1)

    # 13. State + 5-digit ZIP
    m_sz = re.search(r"\b[A-Z]{2}\s+(\d{5})\b", text)
    if m_sz:
        return m_sz.group(1)

    # 14. Trailing 5-digit number
    matches_5 = list(re.finditer(r"\b(\d{5})\b", text))
    if matches_5:
        return matches_5[-1].group(1)

    # 15. Trailing 6-digit number
    matches_6 = list(re.finditer(r"\b(\d{6})\b", text))
    if matches_6:
        return matches_6[-1].group(1)

    # 16. Trailing 4-digit number
    matches_4 = list(re.finditer(r"\b(\d{4})\b", text))
    if matches_4:
        return matches_4[-1].group(1)

    return None


def extract_postal_code(
    text: Optional[str],
    country_hint: Optional[str] = None,
    *,
    country: Optional[str] = None,
) -> Optional[str]:
    """Isolate and extract a postal code from an unformatted or noisy address line.

    Uses country-specific patterns if country_hint is provided; otherwise uses
    contextual country detection and prioritized candidate matchers.

    Args:
        text: Address line or text segment containing a postal code.
        country_hint: Optional country name, alpha-2, or alpha-3 code.
        country: Optional alias for country_hint.

    Returns:
        Extracted and formatted postal code string, or None if no postal code found.
    """
    if not text or not str(text).strip():
        return None

    raw_text = str(text).strip()
    effective_hint = country_hint or country

    # Direct country hint check
    if effective_hint:
        c_info = CountryRegistry.get(effective_hint)
        if c_info is not None:
            if not c_info.has_postal_codes:
                return None
            return _extract_for_country(raw_text, c_info)
        return None

    # Detect country contextually from text
    det = CountryRegistry.detect_country(raw_text)
    if det is not None:
        if not det.has_postal_codes:
            return None
        cand = _extract_for_country(raw_text, det)
        if cand:
            return cand

    # Fallback to multi-country candidate matchers
    return _extract_candidate_any(raw_text)
