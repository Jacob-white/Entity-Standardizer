"""
Dynamic Native Acceleration Dispatcher & Fallback Loader.
=========================================================
Dynamic loader that attempts to import the native compiled module (_address_standardizer_rs),
falling back cleanly, transparently, and deterministically to _pure_python_core.
Provides runtime capability introspection, testing override hooks, and batch dispatch delegation.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from address_standardizer import _pure_python_core
from address_standardizer.models import StandardizedAddress

logger = logging.getLogger(__name__)

# Runtime module state
_NATIVE_MODULE: Optional[Any] = None
_NATIVE_AVAILABLE: bool = False
_FORCE_PURE_PYTHON: bool = False
_FORCE_PURE_ENV = "ADDRESS_STANDARDIZER_FORCE_PURE"
_LOGGED_FAILURES: set = set()


def _env_forces_pure() -> bool:
    """Operator kill switch: ADDRESS_STANDARDIZER_FORCE_PURE=1 disables the native extension."""
    return os.environ.get(_FORCE_PURE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _is_fatal(exc: BaseException) -> bool:
    """Exceptions that must never be swallowed by native-failure fallbacks."""
    return isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit))


def _note_native_failure(name: str, exc: BaseException) -> None:
    """Log each distinct native failure once (PyO3 panics surface as BaseException subclasses)."""
    key = (name, type(exc).__name__)
    if key not in _LOGGED_FAILURES:
        _LOGGED_FAILURES.add(key)
        logger.warning("Native call %s failed (%s: %s); falling back to pure Python.", name, type(exc).__name__, exc)


def try_native(name: str, *args: Any, **kwargs: Any) -> Tuple[bool, Any]:
    """Call `name` on the native module if it is active.

    Returns ``(True, result)`` on success and ``(False, None)`` when the native engine is inactive, lacks the
    function, or raised (including PyO3 panics, which derive from BaseException). Callers then use pure Python.
    """
    if not is_using_native() or _NATIVE_MODULE is None:
        return False, None
    func: Optional[Callable[..., Any]] = getattr(_NATIVE_MODULE, name, None)
    if func is None:
        return False, None
    try:
        return True, func(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - PanicException is not an Exception subclass
        if _is_fatal(exc):
            raise
        _note_native_failure(name, exc)
        return False, None


def _load_fallback_native() -> Optional[Any]:
    try:
        import _phone_standardizer_rs as mod  # type: ignore[import-not-found]

        return mod
    except (ImportError, ModuleNotFoundError):
        pass

    import importlib.machinery
    import importlib.util
    from pathlib import Path

    release_dir = Path(__file__).resolve().parent.parent / "target" / "release"
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
                if spec is not None:
                    mod = importlib.util.module_from_spec(spec)
                    loader.exec_module(mod)
                    return mod
            except Exception:
                continue
    return None


def _init_native():
    global _NATIVE_MODULE, _NATIVE_AVAILABLE, _FORCE_PURE_PYTHON
    _FORCE_PURE_PYTHON = _env_forces_pure()
    try:
        import _address_standardizer_rs as _native_ext

        _NATIVE_MODULE = _native_ext
        _NATIVE_AVAILABLE = True
        logger.debug("Native compiled acceleration loaded (_address_standardizer_rs).")
    except (ImportError, ModuleNotFoundError):
        fallback_mod = _load_fallback_native()
        if fallback_mod is not None:
            _NATIVE_MODULE = fallback_mod
            _NATIVE_AVAILABLE = True
            logger.debug("Native compiled acceleration loaded (_phone_standardizer_rs).")
        else:
            _NATIVE_MODULE = None
            _NATIVE_AVAILABLE = False
            logger.info("Native compiled core unavailable; operating via pure Python fallback.")
    except BaseException as exc:  # noqa: BLE001 - a broken extension must not break `import address_standardizer`
        if _is_fatal(exc):
            raise
        _NATIVE_MODULE = None
        _NATIVE_AVAILABLE = False
        logger.warning("Native extension failed to load (%s: %s); using pure Python.", type(exc).__name__, exc)


_init_native()


def is_native_available() -> bool:
    """Returns True if native compiled binary module is available in Python runtime."""
    return _NATIVE_AVAILABLE


def is_using_native() -> bool:
    """Returns True if native compiled core is active for dispatch calls."""
    return _NATIVE_AVAILABLE and not _FORCE_PURE_PYTHON and _NATIVE_MODULE is not None


def get_active_engine() -> Any:
    """Returns active acceleration engine module (native or pure python fallback)."""
    if is_using_native():
        return _NATIVE_MODULE
    return _pure_python_core


def _native_function_names() -> List[str]:
    """Names the loaded native module reports as accelerated (empty if it does not say)."""
    if _NATIVE_MODULE is None or not hasattr(_NATIVE_MODULE, "get_capabilities"):
        return []
    try:
        return list(dict(_NATIVE_MODULE.get_capabilities()).get("native_functions", []))
    except BaseException as exc:  # noqa: BLE001 - PanicException is not an Exception subclass
        if _is_fatal(exc):
            raise
        return []


def get_engine_info() -> Dict[str, Any]:
    """Returns dictionary detailing engine metadata, active status, and SLA capabilities."""
    using_native = is_using_native()
    return {
        "engine": "Rust_PyO3" if using_native else "PurePythonCore",
        "is_native": using_native,
        "native_available": _NATIVE_AVAILABLE,
        "force_pure_python": _FORCE_PURE_PYTHON,
        "version": "3.3.0",
        # The native module only accelerates the functions listed here; parsing and key assembly are Python in both modes.
        "native_functions": _native_function_names() if using_native else [],
        "throughput_sla_target": ">= 2,000 rec/s",
        "simd_acceleration": False,
        "zero_copy_slices": False,
    }


def get_capabilities() -> Dict[str, Any]:
    """Returns engine capabilities dictionary."""
    if is_using_native() and hasattr(_NATIVE_MODULE, "get_capabilities"):
        try:
            return dict(_NATIVE_MODULE.get_capabilities())
        except Exception:
            pass
    return get_engine_info()


def force_pure_python(enabled: bool = True) -> None:
    """Override hook forcing fallback to pure Python engine."""
    global _FORCE_PURE_PYTHON
    _FORCE_PURE_PYTHON = enabled
    logger.debug("Dispatched pure python forced: %s", enabled)


def set_native_module(module: Optional[Any]) -> None:
    """Testing hook to register mock or alternative native module."""
    global _NATIVE_MODULE, _NATIVE_AVAILABLE
    _NATIVE_MODULE = module
    _NATIVE_AVAILABLE = module is not None


def override_engine_for_testing(mock_engine: Optional[Any]) -> None:
    """Convenience testing hook to override or reset the active engine."""
    if mock_engine is not None:
        set_native_module(mock_engine)
    else:
        reset_engine()


def reset_engine() -> None:
    """Reset engine state to system autodetected defaults."""
    _init_native()


def standardize_record_dispatch(
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    **kwargs: Any,
) -> StandardizedAddress:
    """Dispatches single record standardization to the native engine, falling back to pure Python."""
    ok, result = try_native(
        "standardize_record",
        street1=street1, street2=street2, city=city, state=state,
        postal_code=postal_code, country=country, **kwargs,
    )
    if ok:
        return result
    return _pure_python_core.standardize_record(
        street1=street1, street2=street2, city=city, state=state,
        postal_code=postal_code, country=country, **kwargs,
    )


def standardize_batch_dispatch(
    records: List[Any],
    chunk_size: int = 5000,
    **kwargs: Any,
) -> List[StandardizedAddress]:
    """Dispatches batch standardization to the native engine, falling back to pure Python."""
    ok, result = try_native("standardize_batch", records, chunk_size=chunk_size, **kwargs)
    if ok:
        return result
    return _pure_python_core.standardize_batch(records, chunk_size=chunk_size, **kwargs)


def compute_soundex_dispatch(token: str) -> str:
    """Dispatches Soundex computation to the native engine, falling back to pure Python."""
    ok, result = try_native("compute_soundex", token)
    return result if ok else _pure_python_core.compute_soundex(token)


def generate_phonetic_key_dispatch(
    street1: Optional[str],
    postal_or_zip: str = "",
    city: str = "",
) -> Optional[str]:
    """Dispatches phonetic blocking key generation to the native engine, falling back to pure Python."""
    ok, result = try_native("generate_phonetic_address_key", street1, postal_or_zip=postal_or_zip, city=city)
    if ok:
        return result
    return _pure_python_core.generate_phonetic_address_key(street1, postal_or_zip=postal_or_zip, city=city)


def generate_keys_dispatch(
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    allow_locality: bool = False,
    **kwargs: Any,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Dispatches deterministic entity key generation to the native engine, falling back to pure Python."""
    call_kwargs = dict(
        street1=street1, street2=street2, city=city, state=state, postal_code=postal_code,
        country=country, allow_locality=allow_locality, **kwargs,
    )
    ok, result = try_native("generate_keys", **call_kwargs)
    return result if ok else _pure_python_core.generate_keys(**call_kwargs)


def canonicalize_suffix_dispatch(suffix: str) -> Optional[str]:
    """Canonicalizes street suffix using Pub 28 standards via native engine or fallback."""
    ok, result = try_native("canonicalize_suffix", suffix)
    if ok:
        return result
    from address_standardizer.tables import STREET_SUFFIXES
    return STREET_SUFFIXES.get(suffix.strip().upper())


def canonicalize_directional_dispatch(dir_token: str) -> Optional[str]:
    """Canonicalizes directional indicator (e.g. 'NORTH' -> 'N') via native engine or fallback."""
    ok, result = try_native("canonicalize_directional_py", dir_token)
    if ok:
        return result
    from address_standardizer.tables import DIRECTIONALS
    return DIRECTIONALS.get(dir_token.strip().upper())


def fast_tokenize_dispatch(text: str) -> List[str]:
    """Performs fast-path tokenization via native engine or fallback."""
    ok, result = try_native("fast_tokenize", text)
    if ok:
        return result
    import re
    return re.findall(r"[\w#/-]+", text.upper())


def damerau_levenshtein_dispatch(s1: str, s2: str) -> int:
    """Dispatches Damerau-Levenshtein edit distance to native engine, falling back to pure Python."""
    ok, result = try_native("damerau_levenshtein_distance", s1, s2)
    if ok:
        return result
    from address_standardizer.fuzzy import _pure_damerau_levenshtein_distance
    return _pure_damerau_levenshtein_distance(s1, s2)

