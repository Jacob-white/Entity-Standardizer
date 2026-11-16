"""Person Name and Job Title Standardization & Root Name Resolution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import json
import re
from typing import Any

from entity_standardizer._native_dispatch import (
    compute_soundex_dispatch,
    damerau_levenshtein_distance_dispatch,
)
from entity_standardizer.company import _DOTTED_INITIALISM_RE
from entity_standardizer.dedup import DisjointSet
from entity_standardizer.normalization import fold_latin_diacritics, unescape_html_entities
from entity_standardizer.registries import (
    CREDENTIALS as _CREDENTIALS,
    MULTI_ROOT_DIMINUTIVES as _MULTI_ROOT_DIMINUTIVES,
    NICKNAME_TO_ROOT as _NICKNAME_TO_ROOT,
    SURNAME_PARTICLES as _SURNAME_PARTICLES,
)

_SALUTATIONS: dict[str, str] = {
    "DR": "DR",
    "DOCTOR": "DR",
    "DRS": "DRS",
    "MR": "MR",
    "MISTER": "MR",
    "MESSRS": "MESSRS",
    "MRS": "MRS",
    "MISSUS": "MRS",
    "MMES": "MMES",
    "MS": "MS",
    "MISS": "MISS",
    "MX": "MX",
    "PROF": "PROF",
    "PROFESSOR": "PROF",
    "REV": "REV",
    "REVEREND": "REV",
    "HON": "HON",
    "HONORABLE": "HON",
    "SIR": "SIR",
    "DAME": "DAME",
    "LORD": "LORD",
    "LADY": "LADY",
    "CAPT": "CAPT",
    "CAPTAIN": "CAPT",
    "CPT": "CAPT",
    "CDR": "CDR",
    "COMMANDER": "CDR",
    "ADM": "ADM",
    "ADMIRAL": "ADM",
    "COL": "COL",
    "COLONEL": "COL",
    "LTC": "LTC",
    "GEN": "GEN",
    "GENERAL": "GEN",
    "MAJ": "MAJ",
    "MAJOR": "MAJ",
    "LT": "LT",
    "1LT": "LT",
    "2LT": "LT",
    "LIEUTENANT": "LT",
    "SGT": "SGT",
    "SERGEANT": "SGT",
    "FR": "FR",
    "FATHER": "FR",
    "MSGR": "MSGR",
    "MONSIGNOR": "MSGR",
    "SISTER": "SR",
    "BROTHER": "BR",
    "BR": "BR",
    "PASTOR": "PASTOR",
    "DEACON": "DEACON",
    "RABBI": "RABBI",
    "JUDGE": "JUDGE",
    "JUSTICE": "JUSTICE",
    "SEN": "SEN",
    "SENATOR": "SEN",
    "GOV": "GOV",
    "GOVERNOR": "GOV",
    "AMB": "AMB",
    "AMBASSADOR": "AMB",
    "ATTY": "ATTY",
    "ATTORNEY": "ATTY",
}

_GENERATIONAL_SUFFIXES: dict[str, str] = {
    "JR": "JR",
    "JNR": "JR",
    "JUNIOR": "JR",
    "SR": "SR",
    "SNR": "SR",
    "SENIOR": "SR",
    "1ST": "I",
    "II": "II",
    "2ND": "II",
    "2D": "II",
    "III": "III",
    "3RD": "III",
    "3D": "III",
    "IV": "IV",
    "4TH": "IV",
    "4D": "IV",
    "V": "V",
    "5TH": "V",
    "VI": "VI",
    "6TH": "VI",
    "VII": "VII",
    "7TH": "VII",
    "VIII": "VIII",
    "8TH": "VIII",
}

_AMBIGUOUS_MIXED_CASE_CREDS: frozenset[str] = frozenset(
    {"CFS", "CES", "CIM", "PRM", "CMA", "FMA", "ABV", "CIS", "RMA", "CWS", "HRM", "MST", "RET"}
)

_TWO_LETTER_INITIALISMS: frozenset[str] = frozenset(
    {
        "TJ", "AJ", "CJ", "DJ", "RJ", "PJ", "BJ", "JJ", "MJ",
        "JC", "JD", "JP", "KC", "JR", "JW", "JB", "JM", "JT",
        "JL", "JS", "KP", "KT", "DW", "CW", "TC", "TK",
    }
)

_GENDER_PAIR_SUFFIXES: tuple[str, ...] = ("A", "E", "IA", "IE", "INA", "INE", "LA", "LE")


def resolve_given_name_roots(first_name: str | None) -> tuple[str, ...]:
    """Return all canonical root first names associated with a given name or ambiguous diminutive."""
    if not first_name:
        return ()
    tok = _clean_token(first_name)
    if not tok:
        return ()
    if tok in _MULTI_ROOT_DIMINUTIVES:
        return _MULTI_ROOT_DIMINUTIVES[tok]
    primary = _NICKNAME_TO_ROOT.get(tok, tok)
    return (primary,) if primary == tok else (primary, tok)


def _is_gender_distinct_given_pair(fa: str, fb: str) -> bool:
    """Return True if two given names differ purely by a feminine/masculine inflection suffix ('MARIO'/'MARIA', 'PAUL'/'PAULA')."""
    shorter, longer = (fa, fb) if len(fa) <= len(fb) else (fb, fa)
    if len(longer) > len(shorter) and any(longer == shorter + sfx for sfx in _GENDER_PAIR_SUFFIXES):
        return True
    return {fa[-1], fb[-1]} == {"O", "A"} and fa[:-1] == fb[:-1]


def _is_safe_given_name_edit1(fa: str, fb: str) -> bool:
    """Return True if two >=4-char given names share initial and differ by 1 non-gender-suffix edit."""
    if len(fa) < 4 or len(fb) < 4 or fa[0] != fb[0] or abs(len(fa) - len(fb)) > 1:
        return False
    if _is_gender_distinct_given_pair(fa, fb):
        return False
    return damerau_levenshtein_distance_dispatch(fa, fb) == 1


def _is_safe_prefix_shortening(tok_a: str, tok_b: str) -> bool:
    """Return True when one >=4-char name token is an exact prefix of another non-gender-paired token."""
    if len(tok_a) < 4 or len(tok_b) < 4 or tok_a == tok_b:
        return False
    shorter, longer = (tok_a, tok_b) if len(tok_a) < len(tok_b) else (tok_b, tok_a)
    return longer.startswith(shorter) and not _is_gender_distinct_given_pair(tok_a, tok_b)

_PAREN_OR_QUOTE_NICK_RE = re.compile(
    r'\(\s*([A-Za-z][A-Za-z.\s\-]{0,24})\s*\)|"([A-Za-z][A-Za-z.\s\-]{0,24})"|(?<=[\s,])\'([A-Za-z][A-Za-z.\s\-]{0,24})\'(?=[\s,]|$)'
)

# Job Title expansion & classification tables
_TITLE_MULTI_EXPANSIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ASST", "VP"), "ASSISTANT VICE PRESIDENT"),
    (("ASSISTANT", "VP"), "ASSISTANT VICE PRESIDENT"),
    (("ASSOC", "VP"), "ASSOCIATE VICE PRESIDENT"),
    (("ASSOCIATE", "VP"), "ASSOCIATE VICE PRESIDENT"),
    (("SR", "VP"), "SENIOR VICE PRESIDENT"),
    (("SENIOR", "VP"), "SENIOR VICE PRESIDENT"),
    (("EXEC", "VP"), "EXECUTIVE VICE PRESIDENT"),
    (("EXECUTIVE", "VP"), "EXECUTIVE VICE PRESIDENT"),
    (("CO", "FOUNDER"), "CO-FOUNDER"),
    (("VICE", "PRES"), "VICE PRESIDENT"),
    (("GEN", "MGR"), "GENERAL MANAGER"),
    (("MANAGING", "DIR"), "MANAGING DIRECTOR"),
    (("BIZ", "DEV"), "BUSINESS DEVELOPMENT"),
    (("BUSINESS", "DEV"), "BUSINESS DEVELOPMENT"),
)

_TITLE_TOKEN_EXPANSIONS: dict[str, str] = {
    "CEO": "CHIEF EXECUTIVE OFFICER",
    "CFO": "CHIEF FINANCIAL OFFICER",
    "CTO": "CHIEF TECHNOLOGY OFFICER",
    "COO": "CHIEF OPERATING OFFICER",
    "CMO": "CHIEF MARKETING OFFICER",
    "CIO": "CHIEF INFORMATION OFFICER",
    "CISO": "CHIEF INFORMATION SECURITY OFFICER",
    "CRO": "CHIEF REVENUE OFFICER",
    "CPO": "CHIEF PRODUCT OFFICER",
    "CHRO": "CHIEF HUMAN RESOURCES OFFICER",
    "CLO": "CHIEF LEGAL OFFICER",
    "CCO": "CHIEF COMPLIANCE OFFICER",
    "CAO": "CHIEF ACCOUNTING OFFICER",
    "CSO": "CHIEF STRATEGY OFFICER",
    "VP": "VICE PRESIDENT",
    "SVP": "SENIOR VICE PRESIDENT",
    "EVP": "EXECUTIVE VICE PRESIDENT",
    "AVP": "ASSISTANT VICE PRESIDENT",
    "MD": "MANAGING DIRECTOR",
    "GM": "GENERAL MANAGER",
    "DIR": "DIRECTOR",
    "MGR": "MANAGER",
    "SR": "SENIOR",
    "JR": "JUNIOR",
    "ENG": "ENGINEER",
    "ENGR": "ENGINEER",
    "DEV": "DEVELOPER",
    "ASSOC": "ASSOCIATE",
    "ASST": "ASSISTANT",
    "ADMIN": "ADMINISTRATOR",
    "REP": "REPRESENTATIVE",
    "EXEC": "EXECUTIVE",
    "OPS": "OPERATIONS",
    "MKT": "MARKETING",
    "MKTG": "MARKETING",
    "FIN": "FINANCE",
    "ACCT": "ACCOUNTANT",
    "SWE": "SOFTWARE ENGINEER",
    "GC": "GENERAL COUNSEL",
    "PRES": "PRESIDENT",
    "FINOP": "FINANCIAL AND OPERATIONS PRINCIPAL",
    "IAR": "INVESTMENT ADVISER REPRESENTATIVE",
    "OSJ": "OFFICE OF SUPERVISORY JURISDICTION",
}

_UNAMBIGUOUS_ORG_TOKENS: frozenset[str] = frozenset(
    {
        "LLC",
        "INC",
        "INCORPORATED",
        "CORP",
        "CORPORATION",
        "LTD",
        "LIMITED",
        "LLP",
        "LLLP",
        "PLLC",
        "PLC",
        "GMBH",
        "SARL",
        "SCSP",
        "SPC",
        "PTY",
        "ULC",
        "FSB",
        "HOLDINGS",
        "HOLDING",
        "PARTNERS",
        "PARTNERSHIP",
        "VENTURES",
        "CAPITAL",
        "MANAGEMENT",
        "ADVISORS",
        "ADVISERS",
        "SECURITIES",
        "INVESTMENTS",
        "INVESTORS",
        "FUND",
        "FUNDS",
        "TRUST",
        "TRUSTEES",
        "FOUNDATION",
        "ASSOCIATION",
        "BANCORP",
        "COMPANY",
        "COMPANIES",
        "GROUP",
        "ENTERPRISES",
        "SOLUTIONS",
        "SERVICES",
        "UNIVERSITY",
    }
)

_ORG_SUFFIX_PATTERN_RE = re.compile(
    r"(?:,\s*|\s+)L\.?\s*P\.?\s*$"
    r"|\bS\.\s*[aàAÀ]\.?\s*r\.\s*l\.?(?:\s|$)"
    r"|\bL\.\s*L\.\s*C\.?(?:\s|$)"
    r"|\bS\.\s*C\.\s*Sp\.?(?:\s|$)",
    re.IGNORECASE,
)

_PERSON_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "NA",
        "N/A",
        "NONE",
        "NULL",
        "UNKNOWN",
        "TBD",
        "UNAVAILABLE",
        "NOT APPLICABLE",
        "REDACTED",
    }
)

_LEADING_PLACEHOLDER_RE = re.compile(
    r"^\s*(?:[-–—]+|\[?\s*(?:N\s*/\s*A|NA|NONE|NULL|UNKNOWN|TBD)\s*\]?)\s+(?=[A-Za-z])",
    re.IGNORECASE,
)
_ALNUM_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
_TOKEN_CLEAN_RE = re.compile(r"[^A-Za-z0-9'\-]")
_LEADING_NUMBER_RE = re.compile(r"^\d+\s+")
_CHIEF_OFFICER_RE = re.compile(r"\bCHIEF\s+[A-Z\s]+OFFICER\b")
_NON_ALPHA_ASCII_RE = re.compile(r"[^A-Za-z]")
_TITLE_NON_WORD_RE = re.compile(r"[^\w\s\-]")
_CURLY_APOS_RE = re.compile(r"[\u2018\u2019`]")


def is_organization_name(raw_input: str | None) -> bool:
    """Return True if raw_input represents a corporate entity, fund, or trust rather than a natural person."""
    if not raw_input:
        return False
    unesc, _ = unescape_html_entities(str(raw_input))
    s = unesc.strip()
    if not s:
        return False
    if _ORG_SUFFIX_PATTERN_RE.search(s):
        return True
    words = {w.upper() for w in _ALNUM_WORD_RE.findall(s)}
    return bool(words & _UNAMBIGUOUS_ORG_TOKENS)


@dataclass(slots=True)
class StandardizedPerson:
    """Canonical representation of a standardized person name."""

    raw_input: str
    salutation: str | None = None
    first_name: str | None = None
    root_first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    nickname: str | None = None
    generational_suffix: str | None = None
    credentials: list[str] = field(default_factory=list)
    full_name: str | None = None
    person_key: str | None = None
    person_root_key: str | None = None
    person_alt_keys: list[str] = field(default_factory=list)
    phonetic_key: str | None = None
    is_organization: bool = False
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized person record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "salutation": self.salutation,
            "first_name": self.first_name,
            "root_first_name": self.root_first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "nickname": self.nickname,
            "generational_suffix": self.generational_suffix,
            "credentials": list(self.credentials),
            "full_name": self.full_name,
            "person_key": self.person_key,
            "person_root_key": self.person_root_key,
            "person_alt_keys": list(self.person_alt_keys),
            "phonetic_key": self.phonetic_key,
            "is_organization": self.is_organization,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


@dataclass(slots=True)
class StandardizedJobTitle:
    """Canonical representation of a standardized job title, seniority level, and department."""

    raw_input: str
    normalized_title: str | None = None
    seniority_level: str | None = None
    department: str | None = None
    is_executive: bool = False
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized job title record into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "normalized_title": self.normalized_title,
            "seniority_level": self.seniority_level,
            "department": self.department,
            "is_executive": self.is_executive,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


_SPACED_DOTTED_CRED_RE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]{1,2}\.\s*){2,}")
_JOINT_SALUTATION_RE = re.compile(
    r"^(?P<lead>MR|DR)\.?\s*(?:&|AND)\s*MRS\.?\s+(?=[A-Za-z])",
    re.IGNORECASE,
)
_SPOUSAL_GIVEN_RE = re.compile(
    r"^(?P<f1>[A-Za-z]{2,})\s+(?:&|AND)\s+(?P<f2>[A-Za-z]{2,})\s+(?P<rest>[A-Za-z'\-]+(?:\s+[A-Za-z.'\-/]+)*)$",
    re.IGNORECASE,
)


def _collapse_dotted_cred(match: re.Match[str]) -> str:
    collapsed = _NON_ALNUM_RE.sub("", match.group(0)).upper()
    if collapsed in _CREDENTIALS:
        return f" {collapsed} "
    return match.group(0)


def _clean_token(tok: str) -> str:
    """Strip punctuation periods from a single word token and uppercase it."""
    cleaned = _TOKEN_CLEAN_RE.sub("", tok).upper().strip("'-")
    if (
        cleaned
        and cleaned not in _GENERATIONAL_SUFFIXES
        and cleaned not in _SALUTATIONS
        and any(c.isdigit() for c in cleaned)
    ):
        return ""
    return cleaned


def _tokenize_segment_pairs(segment: str) -> list[tuple[str, str]]:
    """Tokenize a segment into (cleaned_upper_token, raw_subtoken) pairs, expanding slash-joined credentials."""
    norm_seg = _SPACED_DOTTED_CRED_RE.sub(_collapse_dotted_cred, segment)
    out: list[tuple[str, str]] = []
    for raw_tok in norm_seg.split():
        if "/" in raw_tok:
            slash_pairs = [(c, p) for p in raw_tok.split("/") if (c := _clean_token(p))]
            if len(slash_pairs) >= 2 and all(c in _CREDENTIALS for c, _ in slash_pairs):
                out.extend(slash_pairs)
                continue
        cleaned = _clean_token(raw_tok)
        if cleaned:
            out.append((cleaned, raw_tok))
    return out


def canonicalize_surname_variants(last_name: str | None) -> tuple[str, ...]:
    """Return canonical & space/particle/Gaelic-folded surname equivalents ('VAN DER BEEK' <-> 'VANDERBEEK', 'MCDONALD' <-> 'MACDONALD')."""
    if not last_name:
        return ()
    ln = " ".join(last_name.upper().split()).strip("'- ")
    if not ln:
        return ()
    variants: list[str] = [ln]

    if "'" in ln:
        variants.append(ln.replace("'", ""))

    parts = ln.split()
    if len(parts) == 2 and parts[0] == "O" and len(parts[1]) >= 3:
        variants.append(f"O'{parts[1]}")
        variants.append(f"O{parts[1]}")

    if len(parts) >= 2 and any(p in _SURNAME_PARTICLES for p in parts[:-1]):
        collapsed = "".join(parts).replace("-", "")
        variants.append(collapsed)
        if parts[0] == "SAINT":
            rest = " ".join(parts[1:])
            variants.append(f"ST {rest}")
            variants.append(f"ST{''.join(parts[1:])}")
        elif parts[0] == "ST":
            rest = " ".join(parts[1:])
            variants.append(f"SAINT {rest}")
            variants.append(f"ST{''.join(parts[1:])}")
        elif parts[0] == "MC" and len(parts) == 2 and len(parts[1]) >= 3:
            variants.append(f"MAC{parts[1]}")
        elif parts[0] == "MAC" and len(parts) == 2 and len(parts[1]) >= 3:
            variants.append(f"MC{parts[1]}")

    base_single = ln.replace(" ", "")
    if base_single.startswith("MC") and len(base_single) >= 5:
        stem = base_single[2:]
        variants.append(f"MC {stem}")
        variants.append(f"MAC{stem}")
    elif (
        base_single.startswith("MAC")
        and len(base_single) >= 6
        and base_single[3] in "BCDFGKLMNPQRSTVWZ"
        and not base_single.startswith("MACH")
    ):
        stem = base_single[3:]
        variants.append(f"MC{stem}")
        variants.append(f"MC {stem}")
    elif base_single.startswith("ST") and len(base_single) >= 6 and base_single[2] in "BCDFGJKLMNPQSTVWZ":
        stem = base_single[2:]
        variants.append(f"ST {stem}")
        variants.append(f"SAINT {stem}")

    return tuple(dict.fromkeys(variants))


def _is_two_letter_initialism(tok: str | None) -> bool:
    return bool(tok and tok in _TWO_LETTER_INITIALISMS)


def _build_person_alt_keys(
    first_name: str | None,
    root_first_name: str | None,
    middle_name: str | None,
    last_name: str | None,
    person_root_key: str,
) -> list[str]:
    """Generate deterministic alternate blocking/matching keys for middle-name, initialisms, apostrophe, and compound surnames."""
    if not first_name or not last_name:
        return []
    raw_alts: list[str] = []
    rf = root_first_name or first_name

    if first_name in _MULTI_ROOT_DIMINUTIVES:
        for alt_root in _MULTI_ROOT_DIMINUTIVES[first_name]:
            raw_alts.append(f"{last_name}|{alt_root}")

    if _is_two_letter_initialism(first_name):
        raw_alts.append(f"{last_name}|{first_name[0]}|{first_name[1]}")
        raw_alts.append(f"{last_name}|{first_name[0]}")

    if middle_name:
        mid_tok = middle_name.split()[0]
        if len(mid_tok) >= 2:
            root_mid = _NICKNAME_TO_ROOT.get(mid_tok, mid_tok)
            raw_alts.append(f"{last_name}|{first_name[0]}|{root_mid}")
            raw_alts.append(f"{last_name}|{root_mid}")
        elif len(first_name) == 1 and len(mid_tok) == 1:
            raw_alts.append(f"{last_name}|{first_name}{mid_tok}")

    if "'" in last_name:
        folded_ln = last_name.replace("'", "")
        raw_alts.append(f"{folded_ln}|{rf}")

    if "-" in last_name:
        parts = [p for p in last_name.split("-") if len(p) >= 2 and p not in _SURNAME_PARTICLES]
        if len(parts) >= 2:
            raw_alts.append(f"{last_name.replace('-', ' ')}|{rf}")
            for part in parts:
                raw_alts.append(f"{part}|{rf}")
    elif " " in last_name:
        parts = last_name.split()
        if all(p not in _SURNAME_PARTICLES and len(p) >= 2 for p in parts):
            raw_alts.append(f"{'-'.join(parts)}|{rf}")
            for part in parts:
                raw_alts.append(f"{part}|{rf}")

    return [k for k in dict.fromkeys(raw_alts) if k != person_root_key]


def standardize_person(raw_input: str | None) -> StandardizedPerson:
    """Parse and standardize a person's full name into structured fields and entity keys."""
    if raw_input is None:
        return StandardizedPerson(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw or _LEADING_NUMBER_RE.match(cleaned_raw):
        return StandardizedPerson(raw_input=str(raw_input))

    # Reject pure placeholders like "N/A", "NONE", "[none]"
    stripped_brackets = cleaned_raw.strip("[](){}-–— ").upper()
    if not stripped_brackets or stripped_brackets in _PERSON_PLACEHOLDERS:
        return StandardizedPerson(raw_input=str(raw_input))

    actions: list[str] = []
    working = _CURLY_APOS_RE.sub("'", " ".join(cleaned_raw.split()))
    unescaped, did_unescape = unescape_html_entities(working)
    if did_unescape:
        working = " ".join(unescaped.split())
        actions.append("HTML_ENTITIES_DECODED")

    # Strip leading placeholder tokens (e.g. "- Enis Hulli" or "N/A Enis Hulli")
    m_lead_ph = _LEADING_PLACEHOLDER_RE.match(working)
    if m_lead_ph:
        working = working[m_lead_ph.end() :].strip()
        actions.append("PLACEHOLDER_STRIPPED")

    # Detect corporate / entity names misplaced in person name fields
    if is_organization_name(working):
        return StandardizedPerson(
            raw_input=str(raw_input),
            is_organization=True,
            is_valid=False,
            healing_actions=["ORGANIZATION_DETECTED_IN_PERSON_FIELD"],
        )

    folded_working = fold_latin_diacritics(working)
    if folded_working != working:
        working = folded_working
        actions.append("DIACRITICS_FOLDED")

    salutation: str | None = None
    nickname: str | None = None
    generational_suffix: str | None = None
    credentials: list[str] = []
    secondary_given: str | None = None

    # Extract joint salutation prefix (e.g. "Mr. & Mrs. John Smith")
    m_joint_sal = _JOINT_SALUTATION_RE.match(working)
    if m_joint_sal:
        salutation = f"{m_joint_sal.group('lead').upper()}_AND_MRS"
        working = working[m_joint_sal.end() :].strip()
        actions.append("SALUTATION_EXTRACTED")

    # 1. Extract parenthetical or quoted nickname (or parenthetical credential/suffix)
    def _replace_nick(match: re.Match[str]) -> str:
        nonlocal nickname, generational_suffix
        inner = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        tok = _clean_token(inner)
        if tok in _CREDENTIALS:
            credentials.append(_CREDENTIALS[tok])
            actions.append("CREDENTIALS_EXTRACTED")
            return " "
        if tok in _GENERATIONAL_SUFFIXES:
            generational_suffix = _GENERATIONAL_SUFFIXES[tok]
            actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
            return " "
        if nickname is None:
            nickname = tok
            actions.append("NICKNAME_EXTRACTED")
        return " "

    working = _PAREN_OR_QUOTE_NICK_RE.sub(_replace_nick, working)

    # Extract dual/spousal given names ("John & Jane Smith") or slash-paired given names ("Tyler/James Miller")
    if "," not in working:
        pre_toks = working.split()
        while len(pre_toks) > 1 and _clean_token(pre_toks[0]) in _SALUTATIONS:
            salutation = _SALUTATIONS[_clean_token(pre_toks.pop(0))]
            actions.append("SALUTATION_EXTRACTED")
        rejoined = " ".join(pre_toks)
        m_spouse = _SPOUSAL_GIVEN_RE.match(rejoined)
        if m_spouse:
            f1_c = _clean_token(m_spouse.group("f1"))
            f2_c = _clean_token(m_spouse.group("f2"))
            rest_str = m_spouse.group("rest")
            rest_first = _clean_token(rest_str.split()[0])
            if (
                f1_c not in _CREDENTIALS
                and f2_c not in _CREDENTIALS
                and rest_first not in _CREDENTIALS
                and rest_first not in _GENERATIONAL_SUFFIXES
            ):
                secondary_given = f2_c
                working = f"{m_spouse.group('f1')} {rest_str}"
                actions.append("SECONDARY_PERSON_EXTRACTED")
        elif len(pre_toks) >= 2 and "/" in pre_toks[0]:
            slash_g = [_clean_token(p) for p in pre_toks[0].split("/") if _clean_token(p)]
            if len(slash_g) == 2 and all(len(p) >= 2 and p not in _CREDENTIALS for p in slash_g):
                secondary_given = slash_g[1]
                pre_toks[0] = slash_g[0]
                working = " ".join(pre_toks)
                actions.append("SECONDARY_PERSON_EXTRACTED")

    # 2. Split by comma and inspect segments for suffixes, credentials, and Last, First inversion
    raw_segments = [s.strip() for s in working.split(",") if s.strip()]
    if not raw_segments:
        return StandardizedPerson(raw_input=str(raw_input))

    core_segments: list[list[str]] = []
    core_segment_pairs: list[list[tuple[str, str]]] = []
    extra_raw_And_toks: list[tuple[str, list[str]]] = []
    for idx, seg in enumerate(raw_segments):
        pairs = _tokenize_segment_pairs(seg)
        if not pairs:
            continue
        toks = [c for c, _ in pairs]
        if idx > 0 and all(
            t in _GENERATIONAL_SUFFIXES or t in _CREDENTIALS or t == "I" for t in toks
        ):
            for t in toks:
                if t == "I":
                    generational_suffix = "I"
                    actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
                elif t in _GENERATIONAL_SUFFIXES:
                    generational_suffix = _GENERATIONAL_SUFFIXES[t]
                    actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
                else:
                    credentials.append(_CREDENTIALS[t])
                    actions.append("CREDENTIALS_EXTRACTED")
        else:
            core_segments.append(toks)
            core_segment_pairs.append(pairs)
            if idx > 0:
                extra_raw_And_toks.append((seg, toks))

    if not core_segments:
        return StandardizedPerson(raw_input=str(raw_input))

    # Guard against false Last, First inversion when segment 0 is already 'First [Middle] Last [CFA]' followed by unknown uppercase credentials
    if len(core_segments) >= 2:
        seg0 = core_segments[0]
        non_sal_sfx = [t for t in seg0 if t not in _SALUTATIONS and t not in _GENERATIONAL_SUFFIXES]
        all_post_upper_codes = bool(extra_raw_And_toks) and all(
            _NON_ALPHA_ASCII_RE.sub("", rseg).isupper() and all(2 <= len(t) <= 6 for t in stoks)
            for rseg, stoks in extra_raw_And_toks
        )
        if (seg0[-1] in _CREDENTIALS and len(non_sal_sfx) >= 3) or (len(non_sal_sfx) >= 2 and all_post_upper_codes):
            for _rseg, stoks in extra_raw_And_toks:
                credentials.extend(stoks)
            actions.append("CREDENTIALS_EXTRACTED")
            core_segments = [seg0]
            core_segment_pairs = [core_segment_pairs[0]]

    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None

    if len(core_segments) >= 2:
        # "Last, First [Middle]" (or "Smith, Jr., Robert J." or "Smith Jr., Robert J.") inversion
        last_toks = list(core_segments[0])
        given_toks: list[str] = []
        for seg_toks in core_segments[1:]:
            given_toks.extend(seg_toks)

        if last_toks[0] in _SALUTATIONS and len(last_toks) > 1:
            salutation = _SALUTATIONS[last_toks.pop(0)]
            actions.append("SALUTATION_EXTRACTED")

        while len(last_toks) > 1 and last_toks[-1] in _GENERATIONAL_SUFFIXES:
            generational_suffix = _GENERATIONAL_SUFFIXES[last_toks.pop()]
            actions.append("GENERATIONAL_SUFFIX_EXTRACTED")

        while given_toks[0] in _SALUTATIONS and len(given_toks) > 1:
            salutation = _SALUTATIONS[given_toks.pop(0)]
            actions.append("SALUTATION_EXTRACTED")

        given_trailing_creds: list[str] = []
        while len(given_toks) > 1 and (
            given_toks[-1] in _CREDENTIALS or given_toks[-1] in _GENERATIONAL_SUFFIXES
        ):
            tail = given_toks.pop()
            if tail in _CREDENTIALS:
                given_trailing_creds.insert(0, _CREDENTIALS[tail])
            else:
                generational_suffix = _GENERATIONAL_SUFFIXES[tail]
                actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
        if given_trailing_creds:
            credentials.extend(given_trailing_creds)
            actions.append("CREDENTIALS_EXTRACTED")

        last_name = " ".join(last_toks)
        first_name = given_toks[0]
        if len(given_toks) > 1:
            middle_name = " ".join(given_toks[1:])
        actions.append("LAST_FIRST_UNINVERTED")
    else:
        seg0_pairs = core_segment_pairs[0]
        toks = [c for c, _ in seg0_pairs]
        raw_seg0_words = [r for _, r in seg0_pairs]
        while len(toks) > 1 and (toks[0] in _SALUTATIONS or (toks[0] == "SR" and len(toks) >= 3)):
            lead_tok = toks.pop(0)
            raw_seg0_words.pop(0)
            salutation = "SR" if lead_tok == "SR" else _SALUTATIONS[lead_tok]
            actions.append("SALUTATION_EXTRACTED")

        # Extract leading uppercase credentials/designations (e.g., "CFM Bill Strohmeier", "CPA Gregory K Ramirez")
        while (
            len(toks) >= 3
            and toks[0] in _CREDENTIALS
            and len(toks[0]) >= 3
            and _NON_ALPHA_ASCII_RE.sub("", raw_seg0_words[0]).isupper()
        ):
            lead_cred = toks.pop(0)
            raw_seg0_words.pop(0)
            credentials.append(_CREDENTIALS[lead_cred])
            actions.append("CREDENTIALS_EXTRACTED")

        # Extract trailing credentials and generational suffixes (when >= 2 tokens precede)
        trailing_creds: list[str] = []
        while len(toks) > 2:
            cand_tail = toks[-1]
            raw_tail = raw_seg0_words[-1]
            if cand_tail in _GENERATIONAL_SUFFIXES:
                toks.pop()
                raw_seg0_words.pop()
                generational_suffix = _GENERATIONAL_SUFFIXES[cand_tail]
                actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
            elif cand_tail == "I" and len(toks) >= 4 and raw_tail == "I":
                toks.pop()
                raw_seg0_words.pop()
                generational_suffix = "I"
                actions.append("GENERATIONAL_SUFFIX_EXTRACTED")
            elif cand_tail in _CREDENTIALS:
                raw_tail_alpha = _NON_ALPHA_ASCII_RE.sub("", raw_tail)
                if cand_tail in _AMBIGUOUS_MIXED_CASE_CREDS and not trailing_creds and not raw_tail_alpha.isupper():
                    break
                toks.pop()
                raw_seg0_words.pop()
                trailing_creds.insert(0, _CREDENTIALS[cand_tail])
            else:
                break
        if trailing_creds:
            credentials.extend(trailing_creds)
            actions.append("CREDENTIALS_EXTRACTED")

        if len(toks) == 1:
            first_name = toks[0]
        elif len(toks) == 2:
            first_name, last_name = toks[0], toks[1]
        else:
            first_name = toks[0]
            # Check for compound surname particles preceding the last token (e.g. "VAN DER BEEK")
            surname_start = len(toks) - 1
            while surname_start > 1 and toks[surname_start - 1] in _SURNAME_PARTICLES:
                surname_start -= 1
            last_name = " ".join(toks[surname_start:])
            mid_slice = toks[1:surname_start]
            middle_name = " ".join(mid_slice) if mid_slice else None

    # 3. Resolve root_first_name from diminutive/nickname table
    root_first_name: str | None = first_name
    if first_name and first_name in _NICKNAME_TO_ROOT:
        root_first_name = _NICKNAME_TO_ROOT[first_name]
        actions.append("NICKNAME_RESOLVED_TO_ROOT")
    elif (
        nickname
        and nickname in _NICKNAME_TO_ROOT
        and first_name
        and len(first_name) == 1
        and _NICKNAME_TO_ROOT[nickname].startswith(first_name)
    ):
        root_first_name = _NICKNAME_TO_ROOT[nickname]
        actions.append("NICKNAME_RESOLVED_TO_ROOT")

    full_parts = [
        p for p in (first_name, middle_name, last_name, generational_suffix) if p
    ]
    full_name = " ".join(full_parts)

    person_key = (
        f"{last_name or ''}|{first_name or ''}|{middle_name or ''}|{generational_suffix or ''}"
    )
    person_root_key = f"{last_name or ''}|{root_first_name or ''}"
    person_alt_keys = _build_person_alt_keys(
        first_name, root_first_name, middle_name, last_name, person_root_key
    )
    if secondary_given and last_name:
        sec_root = _NICKNAME_TO_ROOT.get(secondary_given, secondary_given)
        sec_key = f"{last_name}|{sec_root}"
        if sec_key != person_root_key and sec_key not in person_alt_keys:
            person_alt_keys.append(sec_key)

    last_snd = compute_soundex_dispatch(last_name.split()[-1]) if last_name else ""
    first_snd = compute_soundex_dispatch(root_first_name or first_name or "")
    phonetic_key = f"{last_snd}|{first_snd}".strip("|") or None

    confidence = 0.98 if (first_name and last_name) else 0.78

    return StandardizedPerson(
        raw_input=str(raw_input),
        salutation=salutation,
        first_name=first_name,
        root_first_name=root_first_name,
        middle_name=middle_name,
        last_name=last_name,
        nickname=nickname,
        generational_suffix=generational_suffix,
        credentials=list(dict.fromkeys(credentials)),
        full_name=full_name,
        person_key=person_key,
        person_root_key=person_root_key,
        person_alt_keys=person_alt_keys,
        phonetic_key=phonetic_key,
        is_valid=True,
        confidence=confidence,
        healing_actions=list(dict.fromkeys(actions)),
    )


def _classify_seniority(norm_title: str, tokens: set[str]) -> str:
    """Classify canonical job title into seniority_level."""
    if (
        _CHIEF_OFFICER_RE.search(norm_title)
        or "GENERAL COUNSEL" in norm_title
    ):
        return "C_SUITE"
    if any(
        w in tokens
        for w in ("OWNER", "FOUNDER", "PARTNER", "CHAIRMAN", "CHAIRPERSON", "CHAIRWOMAN")
    ) or "CO-FOUNDER" in norm_title or (
        "PRESIDENT" in tokens and "VICE" not in tokens
    ):
        return "OWNER_PARTNER"
    if "VICE PRESIDENT" in norm_title:
        return "VP"
    if "DIRECTOR" in tokens or "HEAD OF" in norm_title:
        return "DIRECTOR"
    if "MANAGER" in tokens or "SUPERVISOR" in tokens:
        return "MANAGER"
    if any(w in tokens for w in ("SENIOR", "STAFF", "PRINCIPAL", "ARCHITECT", "FELLOW", "LEAD")):
        return "SENIOR"
    if any(
        w in tokens
        for w in ("JUNIOR", "INTERN", "TRAINEE", "APPRENTICE", "ASSISTANT", "ASSOCIATE", "ENTRY")
    ):
        return "ENTRY"
    return "INDIVIDUAL_CONTRIBUTOR"


def _classify_department(norm_title: str, tokens: set[str]) -> str:
    """Classify canonical job title into functional department."""
    if (
        tokens
        & {
            "TECHNOLOGY",
            "TECHNICAL",
            "SOFTWARE",
            "HARDWARE",
            "ENGINEER",
            "ENGINEERING",
            "DEVELOPER",
            "DATA",
            "INFORMATION",
            "SECURITY",
            "IT",
            "DEVOPS",
            "CLOUD",
            "SYSTEMS",
            "ARCHITECT",
            "QA",
        }
    ):
        return "ENGINEERING"
    if (
        tokens
        & {
            "FINANCIAL",
            "FINANCE",
            "ACCOUNTING",
            "ACCOUNTANT",
            "TREASURY",
            "TREASURER",
            "CONTROLLER",
            "COMPTROLLER",
            "TAX",
            "AUDIT",
            "BILLING",
            "PAYROLL",
        }
    ):
        return "FINANCE"
    if (
        tokens
        & {
            "MARKETING",
            "BRAND",
            "GROWTH",
            "COMMUNICATIONS",
            "CONTENT",
            "ADVERTISING",
            "CREATIVE",
            "PR",
        }
        or "PUBLIC RELATIONS" in norm_title
    ):
        return "MARKETING"
    if (
        tokens
        & {
            "SALES",
            "REVENUE",
            "COMMERCIAL",
            "PARTNERSHIPS",
        }
        or "BUSINESS DEVELOPMENT" in norm_title
        or "ACCOUNT EXECUTIVE" in norm_title
        or "CUSTOMER SUCCESS" in norm_title
    ):
        return "SALES"
    if (
        tokens
        & {
            "OPERATING",
            "OPERATIONS",
            "LOGISTICS",
            "PROCUREMENT",
            "FULFILLMENT",
            "FACILITIES",
            "MANUFACTURING",
            "PLANT",
            "QUALITY",
        }
        or "SUPPLY CHAIN" in norm_title
    ):
        return "OPERATIONS"
    if (
        tokens
        & {
            "LEGAL",
            "COUNSEL",
            "ATTORNEY",
            "COMPLIANCE",
            "REGULATORY",
            "PARALEGAL",
            "PRIVACY",
        }
    ):
        return "LEGAL"
    if (
        tokens
        & {
            "HR",
            "PEOPLE",
            "TALENT",
            "RECRUITING",
            "RECRUITER",
            "BENEFITS",
            "COMPENSATION",
        }
        or "HUMAN RESOURCES" in norm_title
    ):
        return "HR"
    if (
        tokens
        & {
            "EXECUTIVE",
            "PRESIDENT",
            "FOUNDER",
            "OWNER",
            "PARTNER",
            "CHAIRMAN",
            "CHAIRPERSON",
        }
        or "CO-FOUNDER" in norm_title
        or "MANAGING DIRECTOR" in norm_title
        or "GENERAL MANAGER" in norm_title
    ):
        return "EXECUTIVE"
    return "GENERAL"


def standardize_job_title(raw_input: str | None) -> StandardizedJobTitle:
    """Normalize a job title, expanding abbreviations and classifying seniority and department."""
    if raw_input is None:
        return StandardizedJobTitle(raw_input="")

    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw:
        return StandardizedJobTitle(raw_input=str(raw_input))

    actions: list[str] = []
    working = cleaned_raw

    # Unpack JSON array strings (e.g., '["Executive Officer", "Director"]')
    if working.startswith("[") and working.endswith("]"):
        try:
            parsed_arr = json.loads(working)
            items = [str(x).strip() for x in parsed_arr if str(x).strip()]
            if items:
                working = " AND ".join(items)
                actions.append("JSON_ARRAY_UNPACKED")
        except ValueError:
            pass

    working = working.replace("&", " AND ")
    working = _DOTTED_INITIALISM_RE.sub(
        lambda m: f" {_NON_ALPHA_ASCII_RE.sub('', m.group(0)).upper()} ", working
    )
    working = _TITLE_NON_WORD_RE.sub(" ", working)
    raw_tokens = [t.upper().strip("-") for t in working.split() if t.strip("-")]
    if not raw_tokens:
        return StandardizedJobTitle(raw_input=str(raw_input))

    # Multi-token expansions first
    expanded_tokens: list[str] = []
    i = 0
    n = len(raw_tokens)
    while i < n:
        matched_multi = False
        for pat, replacement in _TITLE_MULTI_EXPANSIONS:
            plen = len(pat)
            if i + plen <= n and tuple(raw_tokens[i : i + plen]) == pat:
                expanded_tokens.extend(replacement.split())
                actions.append("TITLE_ABBREVIATION_EXPANDED")
                i += plen
                matched_multi = True
                break
        if matched_multi:
            continue

        tok = raw_tokens[i]
        if tok in _TITLE_TOKEN_EXPANSIONS:
            expanded_tokens.extend(_TITLE_TOKEN_EXPANSIONS[tok].split())
            actions.append("TITLE_ABBREVIATION_EXPANDED")
        else:
            expanded_tokens.append(tok)
        i += 1

    normalized_title = " ".join(expanded_tokens)
    token_set = set(expanded_tokens)
    seniority_level = _classify_seniority(normalized_title, token_set)
    department = _classify_department(normalized_title, token_set)
    is_executive = (
        seniority_level in ("C_SUITE", "OWNER_PARTNER", "VP")
        or bool(token_set & {"EXECUTIVE", "DIRECTOR", "TRUSTEE", "PRINCIPAL"})
    )

    return StandardizedJobTitle(
        raw_input=str(raw_input),
        normalized_title=normalized_title,
        seniority_level=seniority_level,
        department=department,
        is_executive=is_executive,
        is_valid=True,
        confidence=0.96,
        healing_actions=list(dict.fromkeys(actions)),
    )


@dataclass(slots=True)
class PersonComparisonResult:
    """Result of comparing two person name records for entity resolution."""

    is_match: bool
    score: float
    match_type: str
    person_a: StandardizedPerson
    person_b: StandardizedPerson

    def to_dict(self) -> dict[str, Any]:
        """Serialize the person comparison result into a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "person_a": self.person_a.to_dict(),
            "person_b": self.person_b.to_dict(),
        }


def compare_persons(
    person_a: str | StandardizedPerson | None,
    person_b: str | StandardizedPerson | None,
) -> PersonComparisonResult:
    """Compare two person names or StandardizedPerson objects across exact, root-nickname, initial, and phonetic keys."""
    pa = person_a if isinstance(person_a, StandardizedPerson) else standardize_person(person_a)
    pb = person_b if isinstance(person_b, StandardizedPerson) else standardize_person(person_b)

    if (
        not pa.is_valid
        or not pb.is_valid
        or not pa.first_name
        or not pa.last_name
        or not pb.first_name
        or not pb.last_name
    ):
        return PersonComparisonResult(
            is_match=False,
            score=0.0,
            match_type="INVALID_INPUT",
            person_a=pa,
            person_b=pb,
        )

    if (
        pa.generational_suffix
        and pb.generational_suffix
        and pa.generational_suffix != pb.generational_suffix
        and pa.last_name == pb.last_name
        and pa.root_first_name == pb.root_first_name
    ):
        return PersonComparisonResult(
            is_match=False,
            score=0.45,
            match_type="GENERATIONAL_SUFFIX_CONFLICT",
            person_a=pa,
            person_b=pb,
        )

    if pa.person_key == pb.person_key:
        return PersonComparisonResult(
            is_match=True,
            score=1.0,
            match_type="EXACT_PERSON_KEY",
            person_a=pa,
            person_b=pb,
        )

    if pa.person_root_key == pb.person_root_key:
        return PersonComparisonResult(
            is_match=True,
            score=0.96,
            match_type="ROOT_NAME_MATCH",
            person_a=pa,
            person_b=pb,
        )

    if pa.last_name == pb.last_name and (
        set(resolve_given_name_roots(pa.first_name)) & set(resolve_given_name_roots(pb.first_name))
    ):
        return PersonComparisonResult(
            is_match=True,
            score=0.95,
            match_type="MULTI_ROOT_DIMINUTIVE_MATCH",
            person_a=pa,
            person_b=pb,
        )

    surn_vars_a = set(canonicalize_surname_variants(pa.last_name))
    surn_vars_b = set(canonicalize_surname_variants(pb.last_name))
    shared_surname_variant = bool(surn_vars_a & surn_vars_b)

    if (
        shared_surname_variant
        and pa.last_name != pb.last_name
        and (
            pa.root_first_name == pb.root_first_name
            or bool(set(resolve_given_name_roots(pa.first_name)) & set(resolve_given_name_roots(pb.first_name)))
        )
    ):
        return PersonComparisonResult(
            is_match=True,
            score=0.94,
            match_type="PARTICLE_SURNAME_MATCH",
            person_a=pa,
            person_b=pb,
        )

    if shared_surname_variant and (
        (
            _is_two_letter_initialism(pa.first_name)
            and pb.first_name[0] == pa.first_name[0]
            and bool(pb.middle_name and pb.middle_name[0] == pa.first_name[1])
        )
        or (
            _is_two_letter_initialism(pb.first_name)
            and pa.first_name[0] == pb.first_name[0]
            and bool(pa.middle_name and pa.middle_name[0] == pb.first_name[1])
        )
        or (
            len(pa.first_name) == 1
            and bool(pa.middle_name and len(pa.middle_name) == 1)
            and pb.first_name[0] == pa.first_name
            and bool(pb.middle_name and pb.middle_name[0] == pa.middle_name)
        )
        or (
            len(pb.first_name) == 1
            and bool(pb.middle_name and len(pb.middle_name) == 1)
            and pa.first_name[0] == pb.first_name
            and bool(pa.middle_name and pa.middle_name[0] == pb.middle_name)
        )
    ):
        return PersonComparisonResult(
            is_match=True,
            score=0.92,
            match_type="TWO_LETTER_INITIALISM_MATCH",
            person_a=pa,
            person_b=pb,
        )

    # Unhyphenated 2-word surname vs middle+last split (e.g., "Florencia Gomez Stoppello" <-> "Marta Florencia Gomez Stoppello")
    if (
        (pa.middle_name and f"{pa.middle_name} {pa.last_name}" == pb.last_name and pa.root_first_name == pb.root_first_name)
        or (pb.middle_name and f"{pb.middle_name} {pb.last_name}" == pa.last_name and pa.root_first_name == pb.root_first_name)
        or (
            shared_surname_variant
            and pa.middle_name
            and pb.middle_name
            and (
                pb.middle_name == f"{pa.first_name} {pa.middle_name}"
                or pa.middle_name == f"{pb.first_name} {pb.middle_name}"
            )
        )
    ):
        return PersonComparisonResult(
            is_match=True,
            score=0.93,
            match_type="ALT_NAME_KEY_MATCH",
            person_a=pa,
            person_b=pb,
        )

    alt_a = set(pa.person_alt_keys)
    alt_b = set(pb.person_alt_keys)
    three_part_overlap = {k for k in (alt_a & alt_b) if k.count("|") == 2}
    a_matches_b_alt = (
        pa.person_root_key in alt_b
        and (
            not pa.middle_name
            or "'" in pb.last_name
            or "-" in pb.last_name
            or " " in pb.last_name
        )
    )
    b_matches_a_alt = (
        pb.person_root_key in alt_a
        and (
            not pb.middle_name
            or "'" in pa.last_name
            or "-" in pa.last_name
            or " " in pa.last_name
        )
    )
    if three_part_overlap or a_matches_b_alt or b_matches_a_alt:
        return PersonComparisonResult(
            is_match=True,
            score=0.93,
            match_type="ALT_NAME_KEY_MATCH",
            person_a=pa,
            person_b=pb,
        )

    if shared_surname_variant and (
        _is_safe_prefix_shortening(pa.first_name, pb.first_name)
        or (
            pa.middle_name
            and pb.middle_name
            and (
                pa.root_first_name == pb.root_first_name
                or (len(pa.first_name) == 1 and pb.first_name.startswith(pa.first_name))
                or (len(pb.first_name) == 1 and pa.first_name.startswith(pb.first_name))
            )
            and _is_safe_prefix_shortening(pa.middle_name, pb.middle_name)
        )
        or (not pa.middle_name and pb.middle_name and _is_safe_prefix_shortening(pa.first_name, pb.middle_name))
        or (not pb.middle_name and pa.middle_name and _is_safe_prefix_shortening(pb.first_name, pa.middle_name))
    ):
        return PersonComparisonResult(
            is_match=True,
            score=0.90,
            match_type="GIVEN_PREFIX_SHORTENING_MATCH",
            person_a=pa,
            person_b=pb,
        )

    if pa.last_name == pb.last_name and (
        (len(pa.first_name) == 1 and pb.first_name.startswith(pa.first_name))
        or (len(pb.first_name) == 1 and pa.first_name.startswith(pb.first_name))
    ):
        return PersonComparisonResult(
            is_match=True,
            score=0.88,
            match_type="INITIAL_AND_LAST_MATCH",
            person_a=pa,
            person_b=pb,
        )

    if pa.last_name == pb.last_name and _is_safe_given_name_edit1(pa.first_name, pb.first_name):
        return PersonComparisonResult(
            is_match=True,
            score=0.89,
            match_type="GIVEN_NAME_EDIT1_MATCH",
            person_a=pa,
            person_b=pb,
        )

    full_a = f"{pa.root_first_name} {pa.last_name}"
    full_b = f"{pb.root_first_name} {pb.last_name}"
    max_len = max(len(full_a), len(full_b))
    dist = damerau_levenshtein_distance_dispatch(full_a, full_b)
    sim = round(max(0.0, 1.0 - (dist / max_len)), 4)

    if (
        pa.phonetic_key
        and pa.phonetic_key == pb.phonetic_key
        and sim >= 0.82
        and not _is_gender_distinct_given_pair(pa.first_name, pb.first_name)
    ):
        return PersonComparisonResult(
            is_match=True,
            score=sim,
            match_type="PHONETIC_FUZZY_MATCH",
            person_a=pa,
            person_b=pb,
        )

    return PersonComparisonResult(
        is_match=False,
        score=sim,
        match_type="NO_MATCH",
        person_a=pa,
        person_b=pb,
    )


def _compatible_swapped_given(a: str, b: str) -> bool:
    roots_a = set(resolve_given_name_roots(a))
    roots_b = set(resolve_given_name_roots(b))
    if roots_a & roots_b:
        return True
    return len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]


def are_swapped_person_names(
    person_a: str | StandardizedPerson | None,
    person_b: str | StandardizedPerson | None,
) -> bool:
    """Return True if two unpunctuated person names represent swapped First/Last tokens ('Sciandra Julianne' <-> 'Julie Sciandra')."""
    pa = person_a if isinstance(person_a, StandardizedPerson) else standardize_person(person_a)
    pb = person_b if isinstance(person_b, StandardizedPerson) else standardize_person(person_b)
    if not (pa.is_valid and pb.is_valid and pa.first_name and pa.last_name and pb.first_name and pb.last_name):
        return False
    return (pa.first_name == pb.last_name and _compatible_swapped_given(pa.last_name, pb.first_name)) or (
        pb.first_name == pa.last_name and _compatible_swapped_given(pb.last_name, pa.first_name)
    )


def batch_standardize_persons(inputs: Sequence[str | None]) -> list[StandardizedPerson]:
    """Batch-standardize a sequence of person full names."""
    return [standardize_person(item) for item in inputs]


def batch_standardize_job_titles(inputs: Sequence[str | None]) -> list[StandardizedJobTitle]:
    """Batch-standardize a sequence of job titles."""
    return [standardize_job_title(item) for item in inputs]


@dataclass(frozen=True, slots=True)
class PersonCluster:
    """A deduplicated cluster of person records resolved to a single Golden Person Record."""

    cluster_id: str
    golden_person: StandardizedPerson
    members: tuple[StandardizedPerson, ...]
    raw_inputs: tuple[str, ...]
    match_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the person cluster to a JSON-compatible dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "golden_person": self.golden_person.to_dict(),
            "members": [m.to_dict() for m in self.members],
            "raw_inputs": list(self.raw_inputs),
            "match_types": list(self.match_types),
        }


def _person_survivorship_rank(person: StandardizedPerson) -> tuple[int, float, int, int, int]:
    return (
        1 if person.is_valid else 0,
        person.confidence,
        1 if person.middle_name else 0,
        len(person.credentials),
        len(person.full_name or ""),
    )


def deduplicate_persons(
    persons: Sequence[str | StandardizedPerson | None],
    *,
    min_score: float = 0.85,
    fuzzy_threshold: float | None = None,
) -> list[PersonCluster]:
    """Cluster and deduplicate a collection of person names into Golden Person Records."""
    if not persons:
        return []
    threshold = fuzzy_threshold if fuzzy_threshold is not None else min_score

    parsed: list[StandardizedPerson] = [
        p if isinstance(p, StandardizedPerson) else standardize_person(p)
        for p in persons
    ]

    n = len(parsed)
    dsu = DisjointSet(range(n))

    buckets: dict[str, list[int]] = {}
    for idx, p in enumerate(parsed):
        if not p.is_valid:
            continue
        keys: set[str] = {
            f"PK:{p.person_key}",
            f"PRK:{p.person_root_key}",
            f"PH:{p.phonetic_key or ''}",
            f"LNFI:{p.last_name}:{p.first_name[:1]}" if (p.last_name and p.first_name) else "",
        }
        for ak in p.person_alt_keys:
            keys.add(f"PRK:{ak}")
        for sv in canonicalize_surname_variants(p.last_name):
            for r in resolve_given_name_roots(p.first_name):
                keys.add(f"SVAR:{sv}:{r[:1]}")
        keys.discard("")
        keys.discard("PH:")
        for k in keys:
            buckets.setdefault(k, []).append(idx)

    candidate_pairs: set[tuple[int, int]] = set()
    for indices in buckets.values():
        for i_pos in range(len(indices)):
            for j_pos in range(i_pos + 1, len(indices)):
                candidate_pairs.add((indices[i_pos], indices[j_pos]))

    for i, j in sorted(candidate_pairs):
        cmp = compare_persons(parsed[i], parsed[j])
        if cmp.is_match and cmp.score >= threshold:
            dsu.union(i, j, cmp.match_type)

    clusters: list[PersonCluster] = []
    for cluster_num, (root_idx, member_indices) in enumerate(dsu.groups().items(), start=1):
        members = tuple(parsed[i] for i in member_indices)
        golden = max(members, key=_person_survivorship_rank)
        match_types = tuple(sorted(dsu.reasons[root_idx] or {"SINGLETON"}))
        clusters.append(
            PersonCluster(
                cluster_id=f"PERSON-CLUSTER-{cluster_num:04d}",
                golden_person=golden,
                members=members,
                raw_inputs=tuple(m.raw_input for m in members),
                match_types=match_types,
            )
        )
    return clusters



_COUPLE_PREFIX_RE = re.compile(
    r"^(?P<t1>MR|MRS|MS|DR)\.?\s+(?:&|AND)\s+(?P<t2>MR|MRS|MS|DR)\.?\s+(?P<rest>.+)$",
    re.IGNORECASE,
)
_CONJUNCTION_SPLIT_RE = re.compile(r"\s+(?:&|AND)\s+", re.IGNORECASE)


def split_compound_persons(raw_input: str | None) -> list[StandardizedPerson]:
    """Split a joint/couple person string (e.g., 'John & Jane Smith') into individual StandardizedPerson records."""
    if raw_input is None:
        return []
    unesc, _ = unescape_html_entities(str(raw_input))
    cleaned = unesc.strip()
    if not cleaned:
        return []

    if is_organization_name(cleaned):
        return [standardize_person(cleaned)]

    couple_match = _COUPLE_PREFIX_RE.match(cleaned)
    if couple_match:
        t1 = couple_match.group("t1")
        t2 = couple_match.group("t2")
        rest = couple_match.group("rest")
        results = [
            standardize_person(f"{t1} {rest}"),
            standardize_person(f"{t2} {rest}"),
        ]
        for p in results:
            p.healing_actions.append("COMPOUND_PERSON_SPLIT")
        return results

    if "," in cleaned:
        last_part, given_part = cleaned.split(",", 1)
        given_splits = [s.strip() for s in _CONJUNCTION_SPLIT_RE.split(given_part) if s.strip()]
        if len(given_splits) >= 2:
            results = [
                standardize_person(f"{given} {last_part.strip()}")
                for given in given_splits
            ]
            for p in results:
                p.healing_actions.append("COMPOUND_PERSON_SPLIT")
            return results

    parts = [s.strip() for s in _CONJUNCTION_SPLIT_RE.split(cleaned) if s.strip()]
    if len(parts) >= 2:
        tail_person = standardize_person(parts[-1])
        shared_last = tail_person.last_name
        results = []
        for part in parts[:-1]:
            part_tokens = [
                t.strip(".").upper()
                for t in part.split()
                if t.strip(".").upper() not in _SALUTATIONS
            ]
            if len(part_tokens) == 1 and shared_last:
                p = standardize_person(f"{part} {shared_last}")
            else:
                p = standardize_person(part)
            p.healing_actions.append("COMPOUND_PERSON_SPLIT")
            results.append(p)
        tail_person.healing_actions.append("COMPOUND_PERSON_SPLIT")
        results.append(tail_person)
        return results

    return [standardize_person(cleaned)]


