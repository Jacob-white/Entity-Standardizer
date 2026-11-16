"""External Identifier & Regulatory CRD Hygiene (Float Corruption, Zero-Padding & Sentinel Detection)."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any

_SCI_FLOAT_RE = re.compile(r"^[+\-]?\d+(?:\.\d+)?[eE][+\-]?\d+$")
_ZERO_DECIMAL_TAIL_RE = re.compile(r"^(\d+)\.0+$")
_FRACTIONAL_DECIMAL_RE = re.compile(r"^\d+\.\d+$")
_CRD_PREFIX_RE = re.compile(r"^\s*(?:CRD\s*#?\s*:?\s*|#\s*)", re.IGNORECASE)
_ID_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "NA",
        "N/A",
        "NONE",
        "NULL",
        "UNKNOWN",
        "TBD",
        "PENDING",
        "UNASSIGNED",
        "-",
        "--",
        ".",
    }
)
def _is_synthetic_numeric_id(digits: str) -> bool:
    """Return True if a numeric ID is all zeros, 6+ identical digits, or repeated-triple synthetic blocks (999888777)."""
    if not digits:
        return True
    if len(digits) >= 6 and len(set(digits)) == 1:
        return True
    return len(digits) >= 9 and len(digits) % 3 == 0 and all(
        len(set(digits[k : k + 3])) == 1 for k in range(0, len(digits), 3)
    )


def is_synthetic_or_test_record(
    *,
    name: str | None = None,
    email: str | None = None,
    external_id: str | None = None,
    crd: str | None = None,
) -> bool:
    """Return True if standardized inputs exhibit synthetic QA/sandbox patterns (TEST prefix, test@ email, synthetic CRD)."""
    if name:
        n_toks = name.strip().upper().split()
        if n_toks and (n_toks[0] in ("TEST", "DEMO", "SANDBOX") or "WORKATO" in n_toks or "DUMMY" in n_toks):
            return True
    if email:
        em = email.strip().lower()
        if em.startswith(("test@", "test.", "dummy@", "fake@", "qa@", "sandbox@")) or "@test." in em:
            return True
    if crd and standardize_crd(crd).is_placeholder:
        return True
    return bool(external_id and standardize_external_id(external_id).is_placeholder)


@dataclass(slots=True)
class StandardizedIdentifier:
    """Canonical representation of an external CRM, clearing, or FINRA CRD identifier."""

    raw_input: str
    id_type: str = "EXTERNAL_ID"
    canonical_id: str | None = None
    padded_id: str | None = None
    is_valid: bool = False
    is_corrupted_float: bool = False
    is_placeholder: bool = False
    confidence: float = 0.0
    risk_flags: list[str] = field(default_factory=list)
    healing_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the standardized identifier into a JSON-compatible dictionary."""
        return {
            "raw_input": self.raw_input,
            "id_type": self.id_type,
            "canonical_id": self.canonical_id,
            "padded_id": self.padded_id,
            "is_valid": self.is_valid,
            "is_corrupted_float": self.is_corrupted_float,
            "is_placeholder": self.is_placeholder,
            "confidence": round(self.confidence, 4),
            "risk_flags": list(self.risk_flags),
            "healing_actions": list(self.healing_actions),
        }


@dataclass(slots=True)
class IdentifierComparisonResult:
    """Result of comparing two external or regulatory identifiers."""

    is_match: bool
    score: float
    match_type: str
    id_a: StandardizedIdentifier
    id_b: StandardizedIdentifier

    def to_dict(self) -> dict[str, Any]:
        """Serialize the identifier comparison result into a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "id_a": self.id_a.to_dict(),
            "id_b": self.id_b.to_dict(),
        }


def standardize_external_id(
    raw_input: str | int | float | None,
    *,
    id_type: str = "EXTERNAL_ID",
    pad_width: int | None = None,
    allow_alpha: bool = True,
) -> StandardizedIdentifier:
    """Validate and canonicalize an external identifier, catching scientific-notation float corruption and sentinels."""
    if raw_input is None:
        return StandardizedIdentifier(raw_input="", id_type=id_type)

    if isinstance(raw_input, float):
        if math.isnan(raw_input) or math.isinf(raw_input):
            return StandardizedIdentifier(
                raw_input=str(raw_input),
                id_type=id_type,
                is_placeholder=True,
                risk_flags=["NAN_OR_INF_FLOAT"],
            )
        if abs(raw_input) >= 1e15:
            return StandardizedIdentifier(
                raw_input=str(raw_input),
                id_type=id_type,
                is_corrupted_float=True,
                risk_flags=["FLOAT_SCIENTIFIC_CORRUPTION_DETECTED"],
            )

    raw_str = str(raw_input).strip()
    if not raw_str:
        return StandardizedIdentifier(raw_input=str(raw_input), id_type=id_type)

    actions: list[str] = []
    working = raw_str
    if id_type == "CRD" and _CRD_PREFIX_RE.match(working):
        working = _CRD_PREFIX_RE.sub("", working).strip()
        actions.append("ID_PREFIX_STRIPPED")

    upper_work = working.upper()
    if upper_work in _ID_PLACEHOLDERS:
        return StandardizedIdentifier(
            raw_input=str(raw_input),
            id_type=id_type,
            is_placeholder=True,
            risk_flags=["PLACEHOLDER_OR_SENTINEL_ID"],
        )

    if _SCI_FLOAT_RE.match(working):
        return StandardizedIdentifier(
            raw_input=str(raw_input),
            id_type=id_type,
            is_corrupted_float=True,
            risk_flags=["FLOAT_SCIENTIFIC_CORRUPTION_DETECTED"],
        )

    m_zero_dec = _ZERO_DECIMAL_TAIL_RE.match(working)
    if m_zero_dec:
        working = m_zero_dec.group(1)
        actions.append("FLOAT_DECIMAL_ZERO_STRIPPED")
    elif _FRACTIONAL_DECIMAL_RE.match(working):
        return StandardizedIdentifier(
            raw_input=str(raw_input),
            id_type=id_type,
            risk_flags=["INVALID_FRACTIONAL_ID"],
        )

    if working.isdigit():
        stripped = working.lstrip("0")
        if _is_synthetic_numeric_id(stripped):
            return StandardizedIdentifier(
                raw_input=str(raw_input),
                id_type=id_type,
                is_placeholder=True,
                risk_flags=["PLACEHOLDER_OR_SENTINEL_ID"],
            )
        if stripped != working:
            actions.append("LEADING_ZEROS_NORMALIZED")
        canonical = stripped
        padded = canonical.zfill(pad_width) if pad_width is not None else canonical
        return StandardizedIdentifier(
            raw_input=str(raw_input),
            id_type=id_type,
            canonical_id=canonical,
            padded_id=padded,
            is_valid=True,
            confidence=0.99,
            healing_actions=actions,
        )

    if not allow_alpha:
        return StandardizedIdentifier(
            raw_input=str(raw_input),
            id_type=id_type,
            risk_flags=["NON_NUMERIC_CHARACTERS"],
        )

    canonical_alpha = " ".join(working.split())
    padded_alpha = canonical_alpha.zfill(pad_width) if pad_width is not None else canonical_alpha
    return StandardizedIdentifier(
        raw_input=str(raw_input),
        id_type=id_type,
        canonical_id=canonical_alpha,
        padded_id=padded_alpha,
        is_valid=True,
        confidence=0.95,
        healing_actions=actions,
    )


def standardize_crd(raw_input: str | int | float | None) -> StandardizedIdentifier:
    """Validate and canonicalize a FINRA Central Registration Depository (CRD) identifier."""
    res = standardize_external_id(raw_input, id_type="CRD", allow_alpha=False)
    if res.is_valid and res.canonical_id and len(res.canonical_id) > 8:
        return StandardizedIdentifier(
            raw_input=res.raw_input,
            id_type="CRD",
            is_valid=False,
            risk_flags=["CRD_OUT_OF_RANGE"],
            healing_actions=res.healing_actions,
        )
    return res


def compare_external_ids(
    id_a: str | int | float | StandardizedIdentifier | None,
    id_b: str | int | float | StandardizedIdentifier | None,
    *,
    id_type: str = "EXTERNAL_ID",
) -> IdentifierComparisonResult:
    """Compare two external or regulatory identifiers with float-corruption and zero-padding hygiene."""
    norm_fn = standardize_crd if id_type == "CRD" else (lambda x: standardize_external_id(x, id_type=id_type))
    ia = id_a if isinstance(id_a, StandardizedIdentifier) else norm_fn(id_a)
    ib = id_b if isinstance(id_b, StandardizedIdentifier) else norm_fn(id_b)

    if ia.is_corrupted_float or ib.is_corrupted_float:
        return IdentifierComparisonResult(False, 0.0, "CORRUPTED_FLOAT_ID", ia, ib)

    if not ia.is_valid or not ib.is_valid:
        return IdentifierComparisonResult(False, 0.0, "INVALID_INPUT", ia, ib)

    if ia.canonical_id == ib.canonical_id:
        return IdentifierComparisonResult(True, 1.0, "EXACT_CANONICAL_ID", ia, ib)

    return IdentifierComparisonResult(False, 0.0, "DISTINCT_ID", ia, ib)
