"""Advisor Group, Partnership, Team, and House Account Classification & Standardization."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any

from entity_standardizer._native_dispatch import damerau_levenshtein_distance_dispatch
from entity_standardizer.normalization import fold_latin_diacritics, unescape_html_entities
from entity_standardizer.person import standardize_person


class RepEntityClass(StrEnum):
    """Canonical classification of a broker-dealer representative or trading entity."""

    INDIVIDUAL = "INDIVIDUAL"
    PARTNERSHIP = "PARTNERSHIP"
    TEAM = "TEAM"
    HOUSE_ACCOUNT = "HOUSE_ACCOUNT"


_HOUSE_ACCOUNT_RE = re.compile(
    r"\b(?:HOUSE\s+ACCOUNT|HOUSE\s+REP|HOUSE\s+CODE|UNASSIGNED|ORPHAN|DEFAULT\s+REP|NO\s+REP|BROKERAGE\s+GENERAL|HOME\s+OFFICE\s+ACCOUNT|NON[\-\s]?PRODUCING|INTERNAL\s+ACCOUNT|DIRECT\s+ACCOUNT|FIRM\s+ACCOUNT)\b",
    re.IGNORECASE,
)

_TEAM_KEYWORDS_RE = re.compile(
    r"\b(?:TEAM|WEALTH|ADVISORY|PRIVATE\s+CLIENT|FINANCIAL\s+GROUP|INVESTMENT\s+GROUP|CAPITAL\s+GROUP|FAMILY\s+OFFICE|PRACTICE|STRATEGIES|PLANNING)\b",
    re.IGNORECASE,
)

_PARTNERSHIP_KEYWORDS_RE = re.compile(
    r"\b(?:PARTNERSHIP|PARTNERS|GROUP|ASSOCIATES)\b",
    re.IGNORECASE,
)

_MULTI_DELIM_RE = re.compile(r"[/&;+]|\s+AND\s+", re.IGNORECASE)
_REP_CODE_PREFIX_RE = re.compile(r"^\s*[A-Z0-9]{1,8}\s*[-:]\s+(?=[A-Za-z])")
_SLASH_SEMI_PLUS_RE = re.compile(r"[/;+]")
_CONJ_SPLIT_RE = re.compile(r"\s*(?:&|\bAND\b)\s*", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[^A-Z0-9\s]")
_GROUP_TAIL_NOISE_RE = re.compile(
    r"\b(?:THE|WEALTH\s+MANAGEMENT|WEALTH\s+ADVISORS|WEALTH\s+PARTNERS|PRIVATE\s+WEALTH|PRIVATE\s+CLIENT|ADVISORY\s+GROUP|FINANCIAL\s+GROUP|INVESTMENT\s+GROUP|CAPITAL\s+GROUP|CONSULTING\s+GROUP|FAMILY\s+OFFICE|PARTNERSHIP|PARTNERS|PRACTICE|STRATEGIES|PLANNING|ASSOCIATES|ADVISORS|GROUP|TEAM|LLC|INC|LLP|PC)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class StandardizedAdvisorGroup:
    """Canonical representation of a standardized advisor partnership, team, or rep entity."""

    raw_input: str
    normalized_name: str | None = None
    entity_class: str = RepEntityClass.INDIVIDUAL.value
    member_names: list[str] = field(default_factory=list)
    member_surnames: list[str] = field(default_factory=list)
    entity_key: str | None = None
    member_surname_key: str | None = None
    is_valid: bool = False
    confidence: float = 0.0
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized advisor group into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "normalized_name": self.normalized_name,
            "entity_class": self.entity_class,
            "member_names": list(self.member_names),
            "member_surnames": list(self.member_surnames),
            "entity_key": self.entity_key,
            "member_surname_key": self.member_surname_key,
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "healing_actions": list(self.healing_actions),
        }


@dataclass(slots=True)
class AdvisorGroupComparisonResult:
    """Result of comparing two advisor group / partnership / team records."""

    is_match: bool
    score: float
    match_type: str
    group_a: StandardizedAdvisorGroup
    group_b: StandardizedAdvisorGroup

    def to_dict(self) -> dict[str, Any]:
        """Serialize the advisor group comparison result into a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "group_a": self.group_a.to_dict(),
            "group_b": self.group_b.to_dict(),
        }


def classify_rep_entity(raw_input: str | None) -> str:
    """Classify a raw rep/advisor string into INDIVIDUAL, PARTNERSHIP, TEAM, or HOUSE_ACCOUNT."""
    if not raw_input or not str(raw_input).strip():
        return RepEntityClass.INDIVIDUAL.value
    text, _ = unescape_html_entities(str(raw_input))
    folded = fold_latin_diacritics(" ".join(text.split())).upper()
    folded = _REP_CODE_PREFIX_RE.sub("", folded)
    if _HOUSE_ACCOUNT_RE.search(folded):
        return RepEntityClass.HOUSE_ACCOUNT.value
    if _TEAM_KEYWORDS_RE.search(folded):
        return RepEntityClass.TEAM.value
    if _MULTI_DELIM_RE.search(folded) or _PARTNERSHIP_KEYWORDS_RE.search(folded):
        return RepEntityClass.PARTNERSHIP.value
    return RepEntityClass.INDIVIDUAL.value


def _extract_roster_segments(roster_text: str) -> list[str]:
    """Split an advisor group roster string into candidate member name/surname segments."""
    if _SLASH_SEMI_PLUS_RE.search(roster_text):
        return [s.strip(" ,;-") for s in _SLASH_SEMI_PLUS_RE.split(roster_text) if s.strip(" ,;-")]
    if _CONJ_SPLIT_RE.search(roster_text):
        conj_parts = [s.strip(" ;") for s in _CONJ_SPLIT_RE.split(roster_text) if s.strip(" ;")]
        if "," in roster_text and not all("," in p for p in conj_parts):
            out: list[str] = []
            for p in conj_parts:
                for sub in p.split(","):
                    cleaned_sub = sub.strip(" ,;-")
                    if cleaned_sub:
                        out.append(cleaned_sub)
            return out
        return [p.strip(" ,;-") for p in conj_parts if p.strip(" ,;-")]
    return [roster_text.strip(" ,;-")] if roster_text.strip(" ,;-") else []


def standardize_advisor_group(raw_input: str | None) -> StandardizedAdvisorGroup:
    """Standardize an advisor partnership, team, or rep entity and extract order-independent member surname keys."""
    if raw_input is None:
        return StandardizedAdvisorGroup(raw_input="")
    cleaned_raw = str(raw_input).strip()
    if not cleaned_raw:
        return StandardizedAdvisorGroup(raw_input=str(raw_input))

    actions: list[str] = []
    working = " ".join(cleaned_raw.split())
    unescaped, did_unescape = unescape_html_entities(working)
    if did_unescape:
        working = " ".join(unescaped.split())
        actions.append("HTML_ENTITIES_DECODED")

    folded = fold_latin_diacritics(working)
    if folded != working:
        working = folded
        actions.append("DIACRITICS_FOLDED")

    if _REP_CODE_PREFIX_RE.match(working.upper()):
        working = _REP_CODE_PREFIX_RE.sub("", working.upper()).strip()
        actions.append("REP_CODE_PREFIX_STRIPPED")

    entity_class = classify_rep_entity(working)
    disp_upper = working.upper().replace("&", " AND ")
    norm_tokens = _NON_WORD_RE.sub(" ", disp_upper).split()
    if not norm_tokens:
        return StandardizedAdvisorGroup(raw_input=str(raw_input))

    normalized_name = " ".join(norm_tokens)
    if entity_class == RepEntityClass.HOUSE_ACCOUNT.value:
        return StandardizedAdvisorGroup(
            raw_input=str(raw_input),
            normalized_name=normalized_name,
            entity_class=entity_class,
            entity_key=f"HOUSE|{normalized_name}",
            is_valid=True,
            confidence=0.95,
            healing_actions=list(dict.fromkeys(actions)),
        )

    roster_cleaned = _GROUP_TAIL_NOISE_RE.sub(" ", working)
    segments = _extract_roster_segments(roster_cleaned)
    member_names: list[str] = []
    member_surnames: list[str] = []

    for seg in segments:
        alpha_toks = [t for t in re.findall(r"[A-Za-z'\-]+", seg.upper()) if t.strip("'-")]
        if len(alpha_toks) == 1:
            surname = alpha_toks[0].strip("'-")
            member_names.append(surname)
            member_surnames.append(surname)
        elif len(alpha_toks) >= 2:
            per = standardize_person(seg)
            if per.is_valid and per.last_name:
                member_names.append(per.full_name or per.last_name)
                member_surnames.append(per.last_name)

    unique_surnames = sorted(dict.fromkeys(member_surnames))
    member_surname_key = "|".join(unique_surnames) if unique_surnames else None
    entity_key = f"{entity_class}|{normalized_name}"
    confidence = 0.96 if unique_surnames else 0.88

    return StandardizedAdvisorGroup(
        raw_input=str(raw_input),
        normalized_name=normalized_name,
        entity_class=entity_class,
        member_names=member_names,
        member_surnames=unique_surnames,
        entity_key=entity_key,
        member_surname_key=member_surname_key,
        is_valid=True,
        confidence=confidence,
        healing_actions=list(dict.fromkeys(actions)),
    )


def compare_advisor_groups(
    group_a: str | StandardizedAdvisorGroup | None,
    group_b: str | StandardizedAdvisorGroup | None,
) -> AdvisorGroupComparisonResult:
    """Compare two advisor groups/partnerships/teams across canonical keys and order-independent surname rosters."""
    ga = group_a if isinstance(group_a, StandardizedAdvisorGroup) else standardize_advisor_group(group_a)
    gb = group_b if isinstance(group_b, StandardizedAdvisorGroup) else standardize_advisor_group(group_b)

    if not ga.is_valid or not gb.is_valid or not ga.normalized_name or not gb.normalized_name:
        return AdvisorGroupComparisonResult(False, 0.0, "INVALID_INPUT", ga, gb)

    if (ga.entity_class == RepEntityClass.HOUSE_ACCOUNT.value) != (
        gb.entity_class == RepEntityClass.HOUSE_ACCOUNT.value
    ):
        return AdvisorGroupComparisonResult(False, 0.0, "HOUSE_ACCOUNT_MISMATCH", ga, gb)

    if ga.normalized_name == gb.normalized_name:
        return AdvisorGroupComparisonResult(True, 1.0, "EXACT_GROUP_NAME", ga, gb)

    if (
        ga.member_surname_key
        and ga.member_surname_key == gb.member_surname_key
        and len(ga.member_surnames) >= 2
    ):
        return AdvisorGroupComparisonResult(True, 0.95, "MEMBER_SURNAME_SET_MATCH", ga, gb)

    set_a = set(ga.member_surnames)
    set_b = set(gb.member_surnames)
    shared = set_a & set_b
    if len(shared) >= 2:
        union_len = len(set_a | set_b)
        jaccard = len(shared) / union_len
        if jaccard >= 0.6:
            score = round(0.75 + 0.2 * jaccard, 4)
            return AdvisorGroupComparisonResult(True, score, "PARTIAL_MEMBER_SURNAME_OVERLAP", ga, gb)

    max_len = max(len(ga.normalized_name), len(gb.normalized_name))
    dist = damerau_levenshtein_distance_dispatch(ga.normalized_name, gb.normalized_name)
    sim = round(max(0.0, 1.0 - (dist / max_len)), 4)
    return AdvisorGroupComparisonResult(False, sim, "NO_MATCH", ga, gb)


@dataclass(slots=True)
class RosterComparisonResult:
    """Calibrated comparison and partial-overlap score between two advisor/member rosters."""

    is_match: bool
    is_partial_candidate: bool
    score: float
    match_type: str
    shared_count: int
    size_a: int
    size_b: int
    jaccard: float
    containment: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize the roster comparison result into a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "is_partial_candidate": self.is_partial_candidate,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "shared_count": self.shared_count,
            "size_a": self.size_a,
            "size_b": self.size_b,
            "jaccard": round(self.jaccard, 4),
            "containment": round(self.containment, 4),
        }


def score_member_rosters(
    roster_a: Iterable[str] | None,
    roster_b: Iterable[str] | None,
    *,
    same_firm: bool = False,
) -> RosterComparisonResult:
    """Score two member identifier/CRD/email rosters across exact, Jaccard, and split-evolution subset tiers."""
    set_a = {str(x).strip().upper() for x in (roster_a or ()) if str(x).strip()}
    set_b = {str(x).strip().upper() for x in (roster_b or ()) if str(x).strip()}
    if not set_a or not set_b:
        return RosterComparisonResult(False, False, 0.0, "EMPTY_ROSTER", 0, len(set_a), len(set_b), 0.0, 0.0)

    shared = len(set_a & set_b)
    if shared == 0:
        return RosterComparisonResult(False, False, 0.0, "DISJOINT_ROSTERS", 0, len(set_a), len(set_b), 0.0, 0.0)

    union_n = len(set_a | set_b)
    jacc = shared / union_n
    contain = shared / min(len(set_a), len(set_b))

    if set_a == set_b:
        base = 0.98 if len(set_a) >= 2 else (0.90 if same_firm else 0.78)
        return RosterComparisonResult(True, False, base, "EXACT_ROSTER_MATCH", shared, len(set_a), len(set_b), 1.0, 1.0)

    firm_bonus = 0.06 if same_firm else 0.0
    if shared >= 2 and ((same_firm and jacc >= 0.50) or jacc >= 0.67):
        sc = round(min(0.94, 0.74 + 0.16 * jacc + firm_bonus), 4)
        return RosterComparisonResult(True, False, sc, "STRONG_PARTIAL_ROSTER_MATCH", shared, len(set_a), len(set_b), jacc, contain)

    if same_firm and shared >= 2 and contain >= 0.80 and jacc >= 0.35:
        sc = round(min(0.86, 0.68 + 0.14 * jacc + 0.06 * contain), 4)
        return RosterComparisonResult(True, False, sc, "SAME_FIRM_ROSTER_SUBSET_MATCH", shared, len(set_a), len(set_b), jacc, contain)

    if (shared >= 2 and jacc >= 0.25) or (same_firm and shared >= 1 and jacc >= 0.34):
        sc = round(min(0.69, 0.46 + 0.28 * jacc + firm_bonus), 4)
        return RosterComparisonResult(False, True, sc, "PARTIAL_ROSTER_CANDIDATE", shared, len(set_a), len(set_b), jacc, contain)

    sc_low = round(0.25 * jacc, 4)
    return RosterComparisonResult(False, False, sc_low, "WEAK_ROSTER_OVERLAP", shared, len(set_a), len(set_b), jacc, contain)
