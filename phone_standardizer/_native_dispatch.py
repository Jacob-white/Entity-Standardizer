"""Dynamic loader and dispatcher for optional Rust PyO3 acceleration (_phone_standardizer_rs)."""

from __future__ import annotations

from typing import Any

from phone_standardizer.normalization import ITU_E161_KEYPAD_MAP

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
