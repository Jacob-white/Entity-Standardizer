"""Dynamic loader and dispatcher for optional Rust PyO3 acceleration (_phone_standardizer_rs)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
import re
from typing import Any

from phone_standardizer.normalization import (
    _TIME_RANGE_RE,
    _fold_unicode_digits_py,
    _fold_vanity_digits_py,
    decode_vanity_phone,
    extract_extension,
    split_primary_phone,
)


def _load_native_module(release_dir: Path | None = None) -> Any:
    """Import _phone_standardizer_rs or load it from cargo's target/release directory."""
    if release_dir is None:
        try:
            import _phone_standardizer_rs as mod  # type: ignore[import-not-found]
        except ImportError:
            release_dir = Path(__file__).resolve().parent.parent / "target" / "release"
        else:
            return mod

    for filename in (
        "lib_phone_standardizer_rs.so",
        "lib_phone_standardizer_rs.dylib",
        "_phone_standardizer_rs.pyd",
    ):
        candidate = release_dir / filename
        if candidate.is_file():
            try:
                loader = importlib.machinery.ExtensionFileLoader(
                    "_phone_standardizer_rs", str(candidate)
                )
                spec = importlib.util.spec_from_loader("_phone_standardizer_rs", loader)
                if spec is not None:  # pragma: no branch
                    mod = importlib.util.module_from_spec(spec)
                    loader.exec_module(mod)
                    return mod
            except Exception:
                continue
    return None


_native_mod = _load_native_module()

_PAREN_ZERO_RE = re.compile(r"\(\s*0\s*\)")
_PLUS_BEFORE_DIGIT_RE = re.compile(r"^[^\d+]*\+")


def is_native_available() -> bool:
    """Return True if the compiled Rust extension _phone_standardizer_rs is importable."""
    return _native_mod is not None


def get_engine_info() -> dict[str, Any]:
    """Return diagnostic metadata about the active standardization engine."""
    return {
        "engine": "rust_pyo3" if is_native_available() else "pure_python",
        "native_available": is_native_available(),
    }


def fold_vanity_digits_dispatch(text: str) -> str:
    """Fold uppercase/lowercase ASCII letters to ITU-T E.161 keypad digits using Rust if available."""
    if _native_mod is not None:
        return str(_native_mod.fold_vanity_digits_rs(text))
    return _fold_vanity_digits_py(text)


def fold_unicode_digits_dispatch(text: str) -> tuple[str, bool]:
    """Fold non-ASCII Unicode numerals and full-width punctuation using Rust if available."""
    if _native_mod is not None:
        folded, changed = _native_mod.fold_unicode_digits_rs(text)
        return str(folded), bool(changed)
    return _fold_unicode_digits_py(text)


def extract_digits_dispatch(text: str) -> str:
    """Extract ASCII digits ('0'..'9') using Rust if available."""
    if _native_mod is not None:
        return str(_native_mod.extract_digits_rs(text))
    return "".join(ch for ch in text if ch.isdigit())


def _damerau_levenshtein_distance_py(s1: str, s2: str) -> int:
    """Pure-Python Optimal String Alignment (Damerau-Levenshtein) distance."""
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1

    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
            if (
                i > 1
                and j > 1
                and s1[i - 1] == s2[j - 2]
                and s1[i - 2] == s2[j - 1]
            ):
                dp[i][j] = min(dp[i][j], dp[i - 2][j - 2] + 1)
    return dp[len1][len2]


def damerau_levenshtein_distance_dispatch(s1: str, s2: str) -> int:
    """Compute Damerau-Levenshtein distance using Rust if available."""
    if _native_mod is not None:
        return int(_native_mod.damerau_levenshtein_distance_rs(s1, s2))
    return _damerau_levenshtein_distance_py(s1, s2)


def standardize_batch_e164_dispatch(
    inputs: list[str],
    default_calling_code: str = "1",
) -> list[str | None]:
    """High-throughput batch E.164 normalization using Rust SIMD/batch core if available."""
    if _native_mod is not None:
        return list(_native_mod.standardize_batch_e164_rs(inputs, default_calling_code))
    results: list[str | None] = []
    for raw in inputs:
        folded, _ = _fold_unicode_digits_py(raw)
        primary, _ = split_primary_phone(folded)
        no_ext, _ = extract_extension(primary)
        if _TIME_RANGE_RE.search(no_ext):
            results.append(None)
            continue
        decoded, _ = decode_vanity_phone(no_ext)
        cleaned = _PAREN_ZERO_RE.sub("", decoded).strip()
        has_plus = bool(_PLUS_BEFORE_DIGIT_RE.match(cleaned))
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            results.append(None)
            continue
        if has_plus:
            results.append(f"+{digits}")
            continue
        if default_calling_code == "1":
            if len(digits) == 10:
                results.append(f"+1{digits}")
                continue
            if len(digits) == 11 and digits.startswith("1"):
                results.append(f"+{digits}")
                continue
            results.append(None)
            continue
        elif digits.startswith("0") and len(digits) >= 8:
            digits = digits[1:]
        combined = f"{default_calling_code}{digits}"
        results.append(f"+{combined}" if len(combined) <= 15 else None)
    return results


def standardize_batch_with_country_dispatch(
    pairs: list[tuple[str, str]],
) -> list[str | None]:
    """High-throughput heterogeneous country batch E.164 normalization using Rust if available."""
    if _native_mod is not None:
        inputs = [raw for raw, _ in pairs]
        countries = [cc for _, cc in pairs]
        return list(_native_mod.standardize_batch_with_country_rs(inputs, countries, "1"))
    from phone_standardizer.registry import get_dial_plan

    out: list[str | None] = []
    for raw, country_or_cc in pairs:
        plan = get_dial_plan(country_or_cc)
        cc = plan.calling_code if plan is not None else country_or_cc
        out.append(standardize_batch_e164_dispatch([raw], cc)[0])
    return out


