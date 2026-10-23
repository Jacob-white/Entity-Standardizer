"""Organization and Company Name Standardization (ISO 20275 ELF & Entity Resolution)."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

# Multi-token and single-token legal entity forms (ISO 20275 ELF)
# Mapped to (canonical_suffix, unambiguous_country_iso2)
_MULTI_TOKEN_LEGAL_SUFFIXES: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("SOCIEDAD", "ANONIMA", "DE", "CAPITAL", "VARIABLE"), "SA DE CV", "MX"),
    (("SA", "DE", "CV"), "SA DE CV", "MX"),
    (("S", "A", "DE", "C", "V"), "SA DE CV", "MX"),
    (("PROFESSIONAL", "LIMITED", "LIABILITY", "COMPANY"), "PLLC", None),
    (("LIMITED", "LIABILITY", "COMPANY"), "LLC", None),
    (("LIMITED", "LIABILITY", "PARTNERSHIP"), "LLP", None),
    (("PUBLIC", "LIMITED", "COMPANY"), "PLC", "GB"),
    (("PROPRIETARY", "LIMITED"), "PTY LTD", "AU"),
    (("PROPRIETARY", "LTD"), "PTY LTD", "AU"),
    (("PTY", "LIMITED"), "PTY LTD", "AU"),
    (("PTY", "LTD"), "PTY LTD", "AU"),
    (("GMBH", "AND", "CO", "KG"), "GMBH", "DE"),
    (("KABUSHIKI", "KAISHA"), "KK", "JP"),
    (("KABUSHIKI", "GAISHA"), "KK", "JP"),
    (("LIMITED", "PARTNERSHIP"), "LP", None),
    (("PROFESSIONAL", "CORPORATION"), "PC", None),
    (("SOCIEDAD", "ANONIMA"), "SA", None),
    (("SOCIETE", "ANONYME"), "SA", None),
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
    "LP": ("LP", None),
    "PC": ("PC", None),
    "PLLC": ("PLLC", None),
    "CO": ("CO", None),
    "COMPANY": ("CO", None),
    "GMBH": ("GMBH", "DE"),
    "AG": ("AG", None),
    "AKTIENGESELLSCHAFT": ("AG", None),
    "SA": ("SA", None),
    "SARL": ("SARL", "FR"),
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
        "SERVICES",
        "CORPORATION",
        "CORP",
        "COMPANY",
        "CO",
    }
)

_BRANCH_KEYWORDS_RE = re.compile(
    r"\b(?:DIVISION|DIV|BRANCH|UNIT|DEPARTMENT|DEPT|OFFICE|REGION|STORE|PLANT|FACILITY|HEADQUARTERS|HQ|OPERATIONS)\b",
    re.IGNORECASE,
)

_TRAILING_HYPHEN_BRANCH_RE = re.compile(
    r"\s+[-–—]\s+([A-Za-z0-9#.\s]{2,60})$"
)

_PAREN_BRANCH_RE = re.compile(
    r"\s*\(([^()]{2,60})\)\s*$"
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


def _normalize_tokens(text: str, actions: list[str] | None = None) -> list[str]:
    """Normalize punctuation, ampersands, and spaced/dotted initialisms into uppercase tokens."""
    working = _AS_SLASH_RE.sub(" AS ", text)

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
    working = re.sub(r"[^\w\s]", " ", working)
    raw_tokens = [t.upper() for t in working.split() if t]

    # Collapse consecutive single-letter tokens (e.g. "I B M" -> "IBM"), preserving "SA DE CV"
    collapsed: list[str] = []
    i = 0
    n = len(raw_tokens)
    while i < n:
        if (
            len(raw_tokens[i]) == 1
            and raw_tokens[i].isalpha()
            and i + 1 < n
            and len(raw_tokens[i + 1]) == 1
            and raw_tokens[i + 1].isalpha()
        ):
            run = [raw_tokens[i]]
            j = i + 1
            while j < n and len(raw_tokens[j]) == 1 and raw_tokens[j].isalpha():
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
) -> StandardizedCompany:
    """Standardize an organization or company name into canonical components and keys."""
    if raw_input is None:
        return StandardizedCompany(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw:
        return StandardizedCompany(raw_input=str(raw_input))

    actions: list[str] = []
    working = re.sub(r"\s+", " ", cleaned_raw)

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

    # 2. Split inline FKA and DBA clauses
    m_fka = _FKA_SPLIT_RE.search(working)
    if m_fka:
        before_fka = working[: m_fka.start()].strip(" ,;-")
        after_fka = working[m_fka.end() :].strip(" ,;-")
        m_dba_in_after = _DBA_SPLIT_RE.search(after_fka)
        if m_dba_in_after:
            fka_raw = after_fka[: m_dba_in_after.start()].strip(" ,;-")
            dba_raw = after_fka[m_dba_in_after.end() :].strip(" ,;-")
            actions.append("DBA_EXTRACTED")
        else:
            fka_raw = after_fka
        working = before_fka
        actions.append("FKA_EXTRACTED")

    m_dba = _DBA_SPLIT_RE.search(working)
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

    # 4. Normalize tokens and extract legal suffix
    tokens = _normalize_tokens(working, actions)
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

    from address_standardizer.phonetics import compute_soundex
    from phone_standardizer.registry import normalize_country_iso2

    explicit_country = normalize_country_iso2(country) if country else None
    inferred_country_iso2 = explicit_country or suffix_country

    company_key = f"{base_name}|{legal_suffix}" if legal_suffix else base_name
    brand_key = brand_stem
    phonetic_parts = [compute_soundex(t) for t in base_tokens]
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
