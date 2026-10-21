"""Dynamic loader and dispatcher for optional Rust PyO3 acceleration (_phone_standardizer_rs)."""

from __future__ import annotations

from typing import Any

from phone_standardizer.normalization import ITU_E161_KEYPAD_MAP, fold_unicode_digits

try:
    import _phone_standardizer_rs as _native_mod  # type: ignore[import-not-found]
except ImportError:
    _native_mod = None


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
    return "".join(ITU_E161_KEYPAD_MAP.get(ch.upper(), ch) for ch in text)


def fold_unicode_digits_dispatch(text: str) -> tuple[str, bool]:
    """Fold non-ASCII Unicode numerals and full-width punctuation using Rust if available."""
    if _native_mod is not None:
        folded, changed = _native_mod.fold_unicode_digits_rs(text)
        return str(folded), bool(changed)
    return fold_unicode_digits(text)


def extract_digits_dispatch(text: str) -> str:
    """Extract ASCII digits ('0'..'9') using Rust if available."""
    if _native_mod is not None:
        return str(_native_mod.extract_digits_rs(text))
    return "".join(ch for ch in text if ch.isdigit())


def standardize_batch_e164_dispatch(
    inputs: list[str],
    default_calling_code: str = "1",
) -> list[str | None]:
    """High-throughput batch E.164 normalization using Rust SIMD/batch core if available."""
    if _native_mod is not None:
        return list(_native_mod.standardize_batch_e164_rs(inputs, default_calling_code))
    results: list[str | None] = []
    for raw in inputs:
        folded, _ = fold_unicode_digits(raw)
        trimmed = folded.strip()
        has_plus = trimmed.startswith("+")
        digits = "".join(ch for ch in trimmed if ch.isdigit())
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
        combined = f"{default_calling_code}{digits}"
        results.append(f"+{combined}" if len(combined) <= 15 else None)
    return results
