"""Organization and Company Name Standardization (ISO 20275 ELF & Entity Resolution)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import re
from typing import Any

from entity_standardizer._native_dispatch import normalize_company_tokens_dispatch
from entity_standardizer.normalization import fold_latin_diacritics

# Multi-token and single-token legal entity forms (ISO 20275 ELF)
# Mapped to (canonical_suffix, unambiguous_country_iso2)
_MULTI_TOKEN_LEGAL_SUFFIXES: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("SOCIEDAD", "ANONIMA", "DE", "CAPITAL", "VARIABLE"), "SA DE CV", "MX"),
    (("SPOLKA", "Z", "OGRANICZONA", "ODPOWIEDZIALNOSCIA"), "SP Z OO", "PL"),
    (("SOCIETE", "A", "RESPONSABILITE", "LIMITEE"), "SARL", "FR"),
    (("LIMITED", "LIABILITY", "LIMITED", "PARTNERSHIP"), "LLLP", None),
    (("SA", "DE", "CV"), "SA DE CV", "MX"),
    (("S", "A", "DE", "C", "V"), "SA DE CV", "MX"),
    (("PROFESSIONAL", "LIMITED", "LIABILITY", "COMPANY"), "PLLC", None),
    (("KOMMANDITGESELLSCHAFT", "AUF", "AKTIEN"), "KGAA", "DE"),
    (("REAL", "ESTATE", "INVESTMENT", "TRUST"), "REIT", None),
    (("LIMITED", "LIABILITY", "COMPANY"), "LLC", None),
    (("LIMITED", "LIABILITY", "PARTNERSHIP"), "LLP", None),
    (("SPECIAL", "LIMITED", "PARTNERSHIP"), "SCSP", "LU"),
    (("SEGREGATED", "PORTFOLIO", "COMPANY"), "SPC", "KY"),
    (("DELAWARE", "STATUTORY", "TRUST"), "DST", "US"),
    (("UNLIMITED", "LIABILITY", "COMPANY"), "ULC", "CA"),
    (("PUBLIC", "LIMITED", "COMPANY"), "PLC", "GB"),
    (("FEDERAL", "SAVINGS", "BANK"), "FSB", "US"),
    (("SP", "Z", "O", "O"), "SP Z OO", "PL"),
    (("SP", "Z", "OO"), "SP Z OO", "PL"),
    (("PROPRIETARY", "LIMITED"), "PTY LTD", "AU"),
    (("PROPRIETARY", "LTD"), "PTY LTD", "AU"),
    (("PTY", "LIMITED"), "PTY LTD", "AU"),
    (("PTY", "LTD"), "PTY LTD", "AU"),
    (("PRIVATE", "LIMITED"), "PTE LTD", "SG"),
    (("PRIVATE", "LTD"), "PTE LTD", "SG"),
    (("PTE", "LIMITED"), "PTE LTD", "SG"),
    (("PTE", "LTD"), "PTE LTD", "SG"),
    (("PVT", "LIMITED"), "PVT LTD", "IN"),
    (("PVT", "LTD"), "PVT LTD", "IN"),
    (("SENDIRIAN", "BERHAD"), "SDN BHD", "MY"),
    (("SDN", "BHD"), "SDN BHD", "MY"),
    (("SOCIETAS", "EUROPAEA"), "SE", None),
    (("GMBH", "AND", "CO", "KG"), "GMBH", "DE"),
    (("KABUSHIKI", "KAISHA"), "KK", "JP"),
    (("KABUSHIKI", "GAISHA"), "KK", "JP"),
    (("LIMITED", "PARTNERSHIP"), "LP", None),
    (("PROFESSIONAL", "CORPORATION"), "PC", None),
    (("NATIONAL", "ASSOCIATION"), "NA", "US"),
    (("STATUTORY", "TRUST"), "TRUST", None),
    (("BUSINESS", "TRUST"), "TRUST", None),
    (("SOCIEDAD", "ANONIMA"), "SA", None),
    (("SOCIETE", "ANONYME"), "SA", None),
    (("SA", "RL"), "SARL", "LU"),
    (("SC", "SP"), "SCSP", "LU"),
)

_SINGLE_TOKEN_LEGAL_SUFFIXES: dict[str, tuple[str, str | None]] = {
    "LLC": ("LLC", None),
    "INC": ("INC", None),
    "INCORPORATED": ("INC", None),
    "CORP": ("CORP", None),
    "CORPORATION": ("CORP", None),
    "LTD": ("LTD", None),
    "LIMITED": ("LTD", None),
    "PLC": ("PLC", "GB"),
    "LLP": ("LLP", None),
    "LLLP": ("LLLP", None),
    "LP": ("LP", None),
    "PC": ("PC", None),
    "PLLC": ("PLLC", None),
    "ULC": ("ULC", "CA"),
    "NA": ("NA", "US"),
    "FSB": ("FSB", "US"),
    "CO": ("CO", None),
    "COMPANY": ("CO", None),
    "GMBH": ("GMBH", "DE"),
    "AG": ("AG", None),
    "AKTIENGESELLSCHAFT": ("AG", None),
    "SA": ("SA", None),
    "SARL": ("SARL", "FR"),
    "SCSP": ("SCSP", "LU"),
    "SCA": ("SCA", "LU"),
    "SPC": ("SPC", "KY"),
    "DST": ("DST", "US"),
    "REIT": ("REIT", None),
    "TRUST": ("TRUST", None),
    "SAS": ("SAS", "FR"),
    "SRL": ("SRL", "IT"),
    "SPA": ("SPA", "IT"),
    "BV": ("BV", "NL"),
    "NV": ("NV", "NL"),
    "KK": ("KK", "JP"),
    "LTDA": ("LTDA", "BR"),
    "LIMITADA": ("LTDA", "BR"),
    "OY": ("OY", "FI"),
    "OYJ": ("OY", "FI"),
    "AB": ("AB", "SE"),
    "AS": ("AS", None),
    "ASA": ("AS", "NO"),
    "APS": ("APS", "DK"),
    "SE": ("SE", None),
    "KGAA": ("KGAA", "DE"),
    "KFT": ("KFT", "HU"),
    "SRO": ("SRO", "CZ"),
    "DOO": ("DOO", None),
    "OU": ("OU", "EE"),
    "BHD": ("BHD", "MY"),
    "BERHAD": ("BHD", "MY"),
}

_GENERIC_BRAND_TAIL_WORDS: frozenset[str] = frozenset(
    {
        "HOLDINGS",
        "HOLDING",
        "GROUP",
        "ENTERPRISES",
        "ENTERPRISE",
        "INTERNATIONAL",
        "INTL",
        "GLOBAL",
        "WORLDWIDE",
        "INDUSTRIES",
        "SOLUTIONS",
        "TECHNOLOGIES",
        "TECHNOLOGY",
        "SYSTEMS",
        "PARTNERS",
        "VENTURES",
        "CAPITAL",
        "MANAGEMENT",
        "ADVISORS",
        "ADVISERS",
        "INVESTMENTS",
        "INVESTORS",
        "SECURITIES",
        "ASSOCIATES",
        "SERVICES",
        "CORPORATION",
        "CORP",
        "COMPANY",
        "CO",
    }
)

_BRANCH_KEYWORDS_RE = re.compile(
    r"\b(?:DIVISION|DIV|BRANCH|UNIT|DEPARTMENT|DEPT|OFFICE|REGION|STORE|PLANT|FACILITY|HEADQUARTERS|HQ|OPERATIONS|PROGRAM\s+MANAGER|PLAN\s+SPONSOR|GENERAL\s+PARTNER|MANAGING\s+MEMBER|SERIES|PORTFOLIO|TRANCHE|SUB[\-\s]?FUND)\b",
    re.IGNORECASE,
)

_TRAILING_HYPHEN_BRANCH_RE = re.compile(
    r"\s+[-–—]\s+([A-Za-z0-9#.\s]{2,60})$"
)

_PAREN_BRANCH_RE = re.compile(
    r"\s*\(([^()]{2,60})\)\s*$"
)

_PAREN_ACRONYM_RE = re.compile(
    r"\s*\(\s*([A-Z]{2,8})\s*\)\s*$"
)

_SEC_STATE_SUFFIX_RE = re.compile(
    r"\s+/\s*(AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|PR|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|FI|BD|TA|ADV)\s*/?\s*$",
    re.IGNORECASE,
)

_TRUST_AGREEMENT_GUARD_RE = re.compile(
    r"\b(?:U\s*/\s*A(?:\s*/\s*D)?|U\s*/\s*D\s*/\s*T|F\s*/\s*B\s*/\s*O|REVOCABLE\s+TRUST|IRREVOCABLE\s+TRUST|LIVING\s+TRUST|FAMILY\s+TRUST|TRUST\s+DATED|DATED\s+\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.IGNORECASE,
)

_PAREN_DBA_RE = re.compile(
    r"\(\s*(?:D\s*/\s*B\s*/\s*A|D\.B\.A\.?|DBA|DOING\s+BUSINESS\s+AS|TRADING\s+AS|T\s*/\s*A|A\s*/\s*K\s*/\s*A|AKA)\b[:\s\-]*([^()]+)\)",
    re.IGNORECASE,
)

_PAREN_FKA_RE = re.compile(
    r"\(\s*(?:F\s*/\s*K\s*/\s*A|F\.K\.A\.?|FKA|FORMERLY\s+KNOWN\s+AS|FORMERLY|N\s*/\s*K\s*/\s*A|NKA)\b[:\s\-]*([^()]+)\)",
    re.IGNORECASE,
)

_DBA_SPLIT_RE = re.compile(
    r"\b(?:D\s*/\s*B\s*/\s*A|D\.B\.A\.?|DBA|DOING\s+BUSINESS\s+AS|TRADING\s+AS|T\s*/\s*A|A\s*/\s*K\s*/\s*A|A\.K\.A\.?|AKA)\b[:\s\-]*",
    re.IGNORECASE,
)

_FKA_SPLIT_RE = re.compile(
    r"\b(?:F\s*/\s*K\s*/\s*A|F\.K\.A\.?|FKA|FORMERLY\s+KNOWN\s+AS|FORMERLY|N\s*/\s*K\s*/\s*A|N\.K\.A\.?|NKA)\b[:\s\-]*",
    re.IGNORECASE,
)

# Dotted initialisms like "I. B. M.", "I.B.M.", "I.B.M", "S.A.R.L.", "S.r.l.", "B.V.", "B.V", "L.L.C"
_DOTTED_INITIALISM_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:[A-Za-z]\.\s*){2,}(?:[A-Za-z](?![A-Za-z0-9.]))?|[A-Za-z]\.[A-Za-z](?![A-Za-z0-9.]))"
)
# Danish/Norwegian A/S legal form
_AS_SLASH_RE = re.compile(r"\bA\s*/\s*S\b", re.IGNORECASE)

# Unicode alphanumeric extras where Rust char::is_alphanumeric() is True but Python \w is False
# (892 BMP codepoints across Hebrew, Arabic, Devanagari, Bengali, Thai, Lao, etc.)
_COMPANY_NON_WORD_RE = re.compile(
    r"[^\w\s"
    r"\u05b0-\u05bd\u05bf\u05c1-\u05c2\u05c4-\u05c5\u05c7"
    r"\u0610-\u061a\u064b-\u0657\u0659-\u065f\u0670\u06d6-\u06dc\u06e1-\u06e4\u06e7-\u06e8\u06ed"
    r"\u0711\u0730-\u073f\u07a6-\u07b0\u0816-\u0817\u081b-\u0823\u0825-\u0827\u0829-\u082c\u0897-\u089f"
    r"\u08ca-\u08e1\u08e3-\u0903\u093a-\u093c\u093e-\u094c\u094e-\u094f\u0951-\u0957\u0962-\u0963"
    r"\u0981-\u0983\u09bc\u09be-\u09c4\u09c7-\u09c8\u09cb-\u09cc\u09d7\u09e2-\u09e3\u0a01-\u0a03\u0a3c"
    r"\u0a3e-\u0a42\u0a47-\u0a48\u0a4b-\u0a4c\u0a51\u0a70-\u0a71\u0a75\u0a81-\u0a83\u0abc\u0abe-\u0ac5"
    r"\u0ac7-\u0ac9\u0acb-\u0acc\u0ae2-\u0ae3\u0afa-\u0afc\u0b01-\u0b03\u0b3c\u0b3e-\u0b44\u0b47-\u0b48\u0b4b-\u0b4c"
    r"\u0b56-\u0b57\u0b62-\u0b63\u0b82\u0bbe-\u0bc2\u0bc6-\u0bc8\u0bca-\u0bcc\u0bd7\u0c00-\u0c04"
    r"\u0c3e-\u0c44\u0c46-\u0c48\u0c4a-\u0c4c\u0c55-\u0c56\u0c62-\u0c63\u0c81-\u0c83\u0cbc\u0cbe-\u0cc4"
    r"\u0cc6-\u0cc8\u0cca-\u0ccc\u0cd5-\u0cd6\u0ce2-\u0ce3\u0cf3\u0d00-\u0d03\u0d3b-\u0d3c\u0d3e-\u0d44"
    r"\u0d46-\u0d48\u0d4a-\u0d4c\u0d57\u0d62-\u0d63\u0d81-\u0d83\u0dca\u0dcf-\u0dd4\u0dd6\u0dd8-\u0ddf"
    r"\u0df2-\u0df3\u0e31\u0e34-\u0e3a\u0e47-\u0e4e\u0eb1\u0eb4-\u0ebc\u0ec8-\u0ecd\u0f18-\u0f19\u0f35"
    r"\u0f37\u0f39\u0f3e-\u0f3f\u0f71-\u0f84\u0f86-\u0f87\u0f8d-\u0f97\u0f99-\u0fbc\u0fc6\u102b-\u103e"
    r"\u1056-\u1059\u105e-\u1060\u1062-\u1064\u1067-\u106d\u1071-\u1074\u1082-\u108d\u108f\u109a-\u109d"
    r"\u135d-\u135f\u16ee\u1712-\u1714\u1732-\u1734\u1752-\u1753\u1772-\u1773\u17b4-\u17d3\u17dd"
    r"\u180b-\u180d\u1885-\u1886\u18a9\u1920-\u192b\u1930-\u193b\u1a17-\u1a1b\u1a55-\u1a5e\u1a60-\u1a7c"
    r"\u1a7f\u1ab0-\u1ace\u1b00-\u1b04\u1b34-\u1b44\u1b6b-\u1b73\u1b80-\u1b82\u1ba1-\u1baa\u1bac-\u1bad\u1be6-\u1bf3"
    r"\u1c24-\u1c37\u1c89-\u1c8a\u1cd0-\u1cd2\u1cd4-\u1ce8\u1ced\u1cf2-\u1cf4\u1cf7-\u1cf9\u1dc0-\u1dff\u2071\u207f"
    r"\u2090-\u209c\u2102\u2107\u210a-\u2113\u2115\u2118-\u211d\u2124\u2128\u212c-\u212d\u212f-\u2139"
    r"\u213c-\u213f\u2145-\u2149\u214e\u2160-\u2188\u2460-\u249b\u24b6-\u24e9\u24ea-\u24ff\u2cf2-\u2cf3\u2d7f"
    r"\u2de0-\u2dff\u3005-\u3007\u3021-\u3029\u3031-\u3035\u3038-\u303c\u3099-\u309a\u3192-\u3195"
    r"\u31d0-\u31e3\u3220-\u3229\u3248-\u324f\u3251-\u325f\u3280-\u3289\u32b1-\u32bf\ua66f\ua674-\ua67d"
    r"\ua69e-\ua69f\ua6f0-\ua6f1\ua7cb-\ua7cd\ua7da-\ua7dc\ua802\ua806\ua80b\ua823-\ua827\ua82c\ua880-\ua881\ua8b4-\ua8c5"
    r"\ua8e0-\ua8f1\ua8ff\ua926-\ua92d\ua947-\ua953\ua980-\ua983\ua9b3-\ua9c0\ua9e5\uaa29-\uaa36\uaa43"
    r"\uaa4c-\uaa4d\uaa7b-\uaa7d\uaab0\uaab2-\uaab4\uaab7-\uaab8\uaabe-\uaabf\uaac1\uaaf5-\uaaf6"
    r"\uaaeb-\uaaef\uab5b\uabe3-\uabea\uabec-\uabed\ufb1e\ufe00-\ufe0f\ufe20-\ufe2f"
    r"]"
)


@dataclass(slots=True)
class StandardizedCompany:
    """Canonical representation of a standardized organization or company name."""

    raw_input: str
    legal_name: str | None = None
    base_name: str | None = None
    brand_stem: str | None = None
    legal_suffix: str | None = None
    dba_name: str | None = None
    fka_name: str | None = None
    branch_unit: str | None = None
    inferred_country_iso2: str | None = None
    company_key: str | None = None
    brand_key: str | None = None
    phonetic_key: str | None = None
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized company record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "legal_name": self.legal_name,
            "base_name": self.base_name,
            "brand_stem": self.brand_stem,
            "legal_suffix": self.legal_suffix,
            "dba_name": self.dba_name,
            "fka_name": self.fka_name,
            "branch_unit": self.branch_unit,
            "inferred_country_iso2": self.inferred_country_iso2,
            "company_key": self.company_key,
            "brand_key": self.brand_key,
            "phonetic_key": self.phonetic_key,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


StandardizedOrganization = StandardizedCompany


_fold_latin_diacritics = fold_latin_diacritics


def _pure_normalize_tokens(text: str, actions: list[str] | None = None) -> list[str]:
    """Pure-Python normalization of punctuation, ampersands, and spaced/dotted initialisms into uppercase tokens."""
    working = _AS_SLASH_RE.sub(" AS ", fold_latin_diacritics(text))

    if "&" in working or "+" in working:
        working = re.sub(r"\s*[&+]\s*", " AND ", working)
        if actions is not None:
            actions.append("AMPERSAND_NORMALIZED")

    def _collapse_dotted(match: re.Match[str]) -> str:
        raw_seq = match.group(0)
        letters = re.sub(r"[^A-Za-z]", "", raw_seq).upper()
        if actions is not None:
            actions.append("INITIALISM_COLLAPSED")
        return f" {letters} "

    working = _DOTTED_INITIALISM_RE.sub(_collapse_dotted, working)
    working = _COMPANY_NON_WORD_RE.sub(" ", working)
    raw_tokens = [t.upper() for t in working.split() if t]

    # Collapse consecutive single-letter tokens (e.g. "I B M" -> "IBM"), preserving "SA DE CV"
    collapsed: list[str] = []
    i = 0
    n = len(raw_tokens)
    while i < n:
        if (
            len(raw_tokens[i]) == 1
            and raw_tokens[i].isascii()
            and raw_tokens[i].isalpha()
            and i + 1 < n
            and len(raw_tokens[i + 1]) == 1
            and raw_tokens[i + 1].isascii()
            and raw_tokens[i + 1].isalpha()
        ):
            run = [raw_tokens[i]]
            j = i + 1
            while (
                j < n
                and len(raw_tokens[j]) == 1
                and raw_tokens[j].isascii()
                and raw_tokens[j].isalpha()
            ):
                run.append(raw_tokens[j])
                j += 1
            collapsed.append("".join(run))
            if actions is not None:
                actions.append("INITIALISM_COLLAPSED")
            i = j
        else:
            collapsed.append(raw_tokens[i])
            i += 1

    return collapsed


def _normalize_tokens(
    text: str,
    actions: list[str] | None = None,
    precomputed: tuple[list[str], bool, bool] | None = None,
) -> list[str]:
    """Normalize punctuation, ampersands, and spaced/dotted initialisms into uppercase tokens."""
    native_res = precomputed if precomputed is not None else normalize_company_tokens_dispatch(text)
    if native_res is not None:
        tokens, amp_norm, init_col = native_res
        if actions is not None:
            if amp_norm:
                actions.append("AMPERSAND_NORMALIZED")
            if init_col:
                actions.append("INITIALISM_COLLAPSED")
        return tokens
    return _pure_normalize_tokens(text, actions)


def _strip_trailing_co_and(base: list[str], canonical: str) -> list[str]:
    """Strip trailing 'CO'/'COMPANY' and 'AND' preceding a primary corporate suffix like LTD or INC."""
    if canonical != "CO" and len(base) > 1 and base[-1] in ("CO", "COMPANY"):
        base = base[:-1]
    if len(base) > 1 and base[-1] == "AND":
        base = base[:-1]
    return base


def _extract_legal_suffix(
    tokens: list[str],
) -> tuple[list[str], str | None, str | None]:
    """Split token list into (base_tokens, canonical_legal_suffix, inferred_country_iso2)."""
    if len(tokens) < 2:
        return tokens, None, None

    # 1. Check multi-token legal suffixes (longest first)
    for pattern, canonical, country_iso2 in _MULTI_TOKEN_LEGAL_SUFFIXES:
        pat_len = len(pattern)
        if len(tokens) > pat_len and tuple(tokens[-pat_len:]) == pattern:
            base = _strip_trailing_co_and(tokens[:-pat_len], canonical)
            return base, canonical, country_iso2

    # 2. Check single-token legal suffixes
    last_tok = tokens[-1]
    if last_tok in _SINGLE_TOKEN_LEGAL_SUFFIXES:
        canonical, country_iso2 = _SINGLE_TOKEN_LEGAL_SUFFIXES[last_tok]
        base = _strip_trailing_co_and(tokens[:-1], canonical)
        return base, canonical, country_iso2

    # 3. Check prefix K.K. (e.g. "K.K. Sony" -> "KK SONY")
    if tokens[0] == "KK" and len(tokens) >= 2:
        return tokens[1:], "KK", "JP"

    return tokens, None, None


def _pop_trailing_branch(
    text: str, actions: list[str]
) -> tuple[str, str | None]:
    """Extract a parenthesized or hyphenated trailing branch/division clause if present."""
    m_p = _PAREN_BRANCH_RE.search(text)
    if m_p and _BRANCH_KEYWORDS_RE.search(m_p.group(1)):
        actions.append("BRANCH_UNIT_EXTRACTED")
        return text[: m_p.start()].strip(), m_p.group(1).strip()

    m_h = _TRAILING_HYPHEN_BRANCH_RE.search(text)
    if m_h and _BRANCH_KEYWORDS_RE.search(m_h.group(1)):
        actions.append("BRANCH_UNIT_EXTRACTED")
        return text[: m_h.start()].strip(), m_h.group(1).strip()

    return text, None


def standardize_company(
    raw_input: str | None,
    *,
    country: str | None = None,
    _precomputed_tokens: dict[str, tuple[list[str], bool, bool]] | None = None,
) -> StandardizedCompany:
    """Standardize an organization or company name into canonical components and keys."""
    if raw_input is None:
        return StandardizedCompany(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw:
        return StandardizedCompany(raw_input=str(raw_input))

    actions: list[str] = []
    working = re.sub(r"\s+", " ", cleaned_raw)

    # 0. Strip trailing SEC /XX or /XX/ state-of-incorporation or filing suffixes
    sec_country: str | None = None
    m_sec = _SEC_STATE_SUFFIX_RE.search(working)
    if m_sec and working[: m_sec.start()].strip():
        sec_code = m_sec.group(1).upper()
        working = working[: m_sec.start()].strip(" ,;-")
        actions.append("SEC_STATE_SUFFIX_STRIPPED")
        if sec_code not in ("FI", "BD", "TA", "ADV"):
            sec_country = "US"

    # 1. Extract parenthesized DBA / FKA clauses
    dba_raw: str | None = None
    fka_raw: str | None = None
    branch_raw: str | None = None

    m_p_dba = _PAREN_DBA_RE.search(working)
    if m_p_dba:
        dba_raw = m_p_dba.group(1).strip()
        working = (working[: m_p_dba.start()] + " " + working[m_p_dba.end() :]).strip()
        actions.append("DBA_EXTRACTED")

    m_p_fka = _PAREN_FKA_RE.search(working)
    if m_p_fka:
        fka_raw = m_p_fka.group(1).strip()
        working = (working[: m_p_fka.start()] + " " + working[m_p_fka.end() :]).strip()
        actions.append("FKA_EXTRACTED")

    # 2. Split inline FKA and DBA clauses (guarded against trust agreement U/A/D or T/A date clauses)
    is_trust_clause = bool(_TRUST_AGREEMENT_GUARD_RE.search(working))
    m_fka = _FKA_SPLIT_RE.search(working)
    if m_fka:
        before_fka = working[: m_fka.start()].strip(" ,;-")
        after_fka = working[m_fka.end() :].strip(" ,;-")
        m_dba_in_after = None if is_trust_clause else _DBA_SPLIT_RE.search(after_fka)
        if m_dba_in_after:
            fka_raw = after_fka[: m_dba_in_after.start()].strip(" ,;-")
            dba_raw = after_fka[m_dba_in_after.end() :].strip(" ,;-")
            actions.append("DBA_EXTRACTED")
        else:
            fka_raw = after_fka
        working = before_fka
        actions.append("FKA_EXTRACTED")

    m_dba = None if is_trust_clause else _DBA_SPLIT_RE.search(working)
    if m_dba:
        before_dba = working[: m_dba.start()].strip(" ,;-")
        after_dba = working[m_dba.end() :].strip(" ,;-")
        dba_raw = after_dba
        working = before_dba
        actions.append("DBA_EXTRACTED")

    # 3. Extract trailing hyphen or parenthesized branch/division unit from DBA, FKA, or legal name
    if dba_raw is not None:
        dba_raw, branch_raw = _pop_trailing_branch(dba_raw, actions)
    if branch_raw is None and fka_raw is not None:
        fka_raw, branch_raw = _pop_trailing_branch(fka_raw, actions)
    if branch_raw is None:
        working, branch_raw = _pop_trailing_branch(working, actions)

    # 3b. Extract trailing parenthesized uppercase acronym alias (e.g., "Pacific Investment Management Company (PIMCO)")
    if dba_raw is None:
        m_acr = _PAREN_ACRONYM_RE.search(working)
        if m_acr:
            cand_acr = m_acr.group(1).strip()
            prefix_str = working[: m_acr.start()].strip()
            if (
                cand_acr not in _SINGLE_TOKEN_LEGAL_SUFFIXES
                and not _BRANCH_KEYWORDS_RE.search(cand_acr)
                and len(prefix_str.split()) >= 2
            ):
                dba_raw = cand_acr
                working = prefix_str
                actions.append("DBA_EXTRACTED")

    # 4. Normalize tokens and extract legal suffix
    pre_tok = _precomputed_tokens.get(working) if _precomputed_tokens else None
    tokens = _normalize_tokens(working, actions, pre_tok)
    if not tokens:
        return StandardizedCompany(raw_input=str(raw_input))

    base_tokens, legal_suffix, suffix_country = _extract_legal_suffix(tokens)
    if legal_suffix is not None:
        actions.append("LEGAL_SUFFIX_NORMALIZED")

    # Strip leading article "THE" when followed by at least one token
    if len(base_tokens) > 1 and base_tokens[0] == "THE":
        base_tokens = base_tokens[1:]
        actions.append("LEADING_ARTICLE_STRIPPED")

    base_name = " ".join(base_tokens)
    legal_name = f"{base_name} {legal_suffix}".strip() if legal_suffix else base_name

    # 5. Compute core brand_stem by stripping trailing generic corporate descriptors
    stem_tokens = list(base_tokens)
    while len(stem_tokens) > 1 and (
        stem_tokens[-1] in _GENERIC_BRAND_TAIL_WORDS or stem_tokens[-1] == "AND"
    ):
        stem_tokens.pop()
    brand_stem = " ".join(stem_tokens)

    # 6. Normalize DBA, FKA, and Branch if present
    dba_tokens = _normalize_tokens(dba_raw) if dba_raw else []
    if dba_tokens:
        dba_base, _, _ = _extract_legal_suffix(dba_tokens)
        if len(dba_base) > 1 and dba_base[0] == "THE":
            dba_base = dba_base[1:]
        dba_name: str | None = " ".join(dba_base)
    else:
        dba_name = None

    fka_tokens = _normalize_tokens(fka_raw) if fka_raw else []
    if fka_tokens:
        fka_base, fka_sfx, _ = _extract_legal_suffix(fka_tokens)
        if len(fka_base) > 1 and fka_base[0] == "THE":
            fka_base = fka_base[1:]
        fka_name: str | None = (
            f"{' '.join(fka_base)} {fka_sfx}".strip() if fka_sfx else " ".join(fka_base)
        )
    else:
        fka_name = None

    branch_tokens = _normalize_tokens(branch_raw) if branch_raw else []
    branch_unit = " ".join(branch_tokens) if branch_tokens else None

    from entity_standardizer._native_dispatch import compute_soundex_dispatch
    from entity_standardizer.registry import normalize_country_iso2

    explicit_country = normalize_country_iso2(country) if country else None
    inferred_country_iso2 = explicit_country or suffix_country or sec_country

    company_key = f"{base_name}|{legal_suffix}" if legal_suffix else base_name
    brand_key = brand_stem
    phonetic_parts = [compute_soundex_dispatch(t) for t in base_tokens]
    phonetic_parts = [p for p in phonetic_parts if p]
    phonetic_key = "|".join(phonetic_parts) if phonetic_parts else None

    confidence = 0.98 if legal_suffix else 0.92

    return StandardizedCompany(
        raw_input=str(raw_input),
        legal_name=legal_name,
        base_name=base_name,
        brand_stem=brand_stem,
        legal_suffix=legal_suffix,
        dba_name=dba_name,
        fka_name=fka_name,
        branch_unit=branch_unit,
        inferred_country_iso2=inferred_country_iso2,
        company_key=company_key,
        brand_key=brand_key,
        phonetic_key=phonetic_key,
        is_valid=True,
        confidence=confidence,
        healing_actions=list(dict.fromkeys(actions)),
    )


standardize_organization = standardize_company


@dataclass(slots=True)
class CompanyComparisonResult:
    """Result of comparing two organization/company records for entity resolution."""

    is_match: bool
    score: float
    match_type: str
    company_a: StandardizedCompany
    company_b: StandardizedCompany

    def to_dict(self) -> dict[str, Any]:
        """Serialize the company comparison result into a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "company_a": self.company_a.to_dict(),
            "company_b": self.company_b.to_dict(),
        }


def compare_companies(
    company_a: str | StandardizedCompany | None,
    company_b: str | StandardizedCompany | None,
) -> CompanyComparisonResult:
    """Compare two company names or StandardizedCompany objects across canonical, alias, brand, and phonetic keys."""
    from entity_standardizer._native_dispatch import damerau_levenshtein_distance_dispatch

    ca = company_a if isinstance(company_a, StandardizedCompany) else standardize_company(company_a)
    cb = company_b if isinstance(company_b, StandardizedCompany) else standardize_company(company_b)

    if not ca.is_valid or not cb.is_valid or not ca.base_name or not cb.base_name:
        return CompanyComparisonResult(
            is_match=False,
            score=0.0,
            match_type="INVALID_INPUT",
            company_a=ca,
            company_b=cb,
        )

    if ca.company_key == cb.company_key:
        return CompanyComparisonResult(
            is_match=True,
            score=1.0,
            match_type="EXACT_COMPANY_KEY",
            company_a=ca,
            company_b=cb,
        )

    if ca.base_name == cb.base_name:
        return CompanyComparisonResult(
            is_match=True,
            score=0.96,
            match_type="BASE_NAME_MATCH",
            company_a=ca,
            company_b=cb,
        )

    aliases_a = {x for x in (ca.dba_name, ca.fka_name) if x}
    aliases_b = {x for x in (cb.dba_name, cb.fka_name) if x}
    names_a = {x for x in (ca.base_name, ca.legal_name, ca.brand_stem) if x} | aliases_a
    names_b = {x for x in (cb.base_name, cb.legal_name, cb.brand_stem) if x} | aliases_b
    if (aliases_a & names_b) or (aliases_b & names_a):
        return CompanyComparisonResult(
            is_match=True,
            score=0.94,
            match_type="ALIAS_MATCH",
            company_a=ca,
            company_b=cb,
        )

    if ca.brand_stem and ca.brand_stem == cb.brand_stem and len(ca.brand_stem) >= 3:
        return CompanyComparisonResult(
            is_match=True,
            score=0.9,
            match_type="BRAND_STEM_MATCH",
            company_a=ca,
            company_b=cb,
        )

    max_len = max(len(ca.base_name), len(cb.base_name))
    dist = damerau_levenshtein_distance_dispatch(ca.base_name, cb.base_name)
    sim = round(max(0.0, 1.0 - (dist / max_len)), 4)

    if ca.phonetic_key and ca.phonetic_key == cb.phonetic_key and sim >= 0.8:
        return CompanyComparisonResult(
            is_match=True,
            score=sim,
            match_type="PHONETIC_FUZZY_MATCH",
            company_a=ca,
            company_b=cb,
        )

    return CompanyComparisonResult(
        is_match=False,
        score=sim,
        match_type="NO_MATCH",
        company_a=ca,
        company_b=cb,
    )


compare_organizations = compare_companies


def batch_standardize_companies(
    inputs: Sequence[str | None],
    *,
    country: str | None = None,
) -> list[StandardizedCompany]:
    """Batch-standardize a sequence of organization or company names."""
    from entity_standardizer._native_dispatch import normalize_batch_company_tokens_dispatch

    clean_texts = list(
        dict.fromkeys(
            re.sub(r"\s+", " ", str(x).strip())
            for x in inputs
            if x is not None and str(x).strip()
        )
    )
    batch_tokens = normalize_batch_company_tokens_dispatch(clean_texts) if clean_texts else None
    precomputed = dict(zip(clean_texts, batch_tokens)) if batch_tokens is not None else None
    return [
        standardize_company(item, country=country, _precomputed_tokens=precomputed)
        for item in inputs
    ]


batch_standardize_organizations = batch_standardize_companies


@dataclass(frozen=True, slots=True)
class CompanyCluster:
    """A deduplicated cluster of company records resolved to a single Golden Company Record."""

    cluster_id: str
    golden_company: StandardizedCompany
    members: tuple[StandardizedCompany, ...]
    raw_inputs: tuple[str, ...]
    match_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the company cluster to a JSON-compatible dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "golden_company": self.golden_company.to_dict(),
            "members": [m.to_dict() for m in self.members],
            "raw_inputs": list(self.raw_inputs),
            "match_types": list(self.match_types),
        }


def _company_survivorship_rank(comp: StandardizedCompany) -> tuple[int, float, int, int, int]:
    return (
        1 if comp.is_valid else 0,
        comp.confidence,
        1 if comp.legal_suffix else 0,
        1 if (comp.dba_name or comp.fka_name) else 0,
        len(comp.legal_name or ""),
    )


def deduplicate_companies(
    companies: Sequence[str | StandardizedCompany | None],
    *,
    country: str | None = None,
    min_score: float = 0.90,
    fuzzy_threshold: float | None = None,
) -> list[CompanyCluster]:
    """Cluster and deduplicate a collection of company names into Golden Company Records."""
    if not companies:
        return []
    threshold = fuzzy_threshold if fuzzy_threshold is not None else min_score

    parsed: list[StandardizedCompany] = [
        c if isinstance(c, StandardizedCompany) else standardize_company(c, country=country)
        for c in companies
    ]
    from entity_standardizer.dedup import DisjointSet

    n = len(parsed)
    dsu = DisjointSet(range(n))

    buckets: dict[str, list[int]] = {}
    for idx, c in enumerate(parsed):
        if not c.is_valid:
            continue
        keys: set[str] = {
            f"CK:{c.company_key}",
            f"BN:{c.base_name}",
            f"PK:{c.phonetic_key or ''}",
            f"BS:{c.brand_stem if c.brand_stem and len(c.brand_stem) >= 3 else ''}",
        }
        for nm in (c.base_name, c.legal_name, c.brand_stem, c.dba_name, c.fka_name):
            if nm:
                keys.add(f"NM:{nm}")
        keys.discard("PK:")
        keys.discard("BS:")
        for k in keys:
            buckets.setdefault(k, []).append(idx)

    candidate_pairs: set[tuple[int, int]] = set()
    for indices in buckets.values():
        for i_pos in range(len(indices)):
            for j_pos in range(i_pos + 1, len(indices)):
                candidate_pairs.add((indices[i_pos], indices[j_pos]))

    for i, j in sorted(candidate_pairs):
        cmp = compare_companies(parsed[i], parsed[j])
        if cmp.is_match and cmp.score >= threshold:
            dsu.union(i, j, cmp.match_type)

    clusters: list[CompanyCluster] = []
    for cluster_num, (root_idx, member_indices) in enumerate(dsu.groups().items(), start=1):
        members = tuple(parsed[i] for i in member_indices)
        golden = max(members, key=_company_survivorship_rank)
        match_types = tuple(sorted(dsu.reasons[root_idx] or {"SINGLETON"}))
        clusters.append(
            CompanyCluster(
                cluster_id=f"COMPANY-CLUSTER-{cluster_num:04d}",
                golden_company=golden,
                members=members,
                raw_inputs=tuple(m.raw_input for m in members),
                match_types=match_types,
            )
        )
    return clusters


deduplicate_organizations = deduplicate_companies


