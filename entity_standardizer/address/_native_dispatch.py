"""
Dynamic Native Acceleration Dispatcher & Fallback Loader.
=========================================================
Dynamic loader that attempts to import the native compiled module (_entity_standardizer_rs),
falling back cleanly, transparently, and deterministically to _pure_python_core.
Provides runtime capability introspection, testing override hooks, and batch dispatch delegation.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from entity_standardizer.address import _pure_python_core
from entity_standardizer.address.models import StandardizedAddress

logger = logging.getLogger(__name__)

# Runtime module state
_NATIVE_MODULE: Optional[Any] = None
_NATIVE_AVAILABLE: bool = False
_FORCE_PURE_PYTHON: bool = False
_FORCE_PURE_ENV = "ENTITY_STANDARDIZER_FORCE_PURE"
_LEGACY_FORCE_PURE_ENV = "ADDRESS_STANDARDIZER_FORCE_PURE"
_LOGGED_FAILURES: set = set()


def _env_forces_pure() -> bool:
    """Operator kill switch: ENTITY_STANDARDIZER_FORCE_PURE=1 (or ADDRESS_STANDARDIZER_FORCE_PURE=1) disables the native extension."""
    val = os.environ.get(_FORCE_PURE_ENV) or os.environ.get(_LEGACY_FORCE_PURE_ENV, "")
    return val.strip().lower() in ("1", "true", "yes", "on")


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
    from pathlib import Path
    from entity_standardizer._native_dispatch import _load_native_module

    release_dir = Path(__file__).resolve().parents[2] / "target" / "release"
    return _load_native_module(release_dir=release_dir)


def _init_native():
    global _NATIVE_MODULE, _NATIVE_AVAILABLE, _FORCE_PURE_PYTHON
    _FORCE_PURE_PYTHON = _env_forces_pure()
    try:
        import _entity_standardizer_rs as _native_ext  # type: ignore[import-not-found]

        _NATIVE_MODULE = _native_ext
        _NATIVE_AVAILABLE = True
        logger.debug("Native compiled acceleration loaded (_entity_standardizer_rs).")
    except (ImportError, ModuleNotFoundError):
        fallback_mod = _load_fallback_native()
        if fallback_mod is not None:
            _NATIVE_MODULE = fallback_mod
            _NATIVE_AVAILABLE = True
            logger.debug("Native compiled acceleration loaded (_entity_standardizer_rs).")
        else:
            _NATIVE_MODULE = None
            _NATIVE_AVAILABLE = False
            logger.info("Native compiled core unavailable; operating via pure Python fallback.")
    except BaseException as exc:  # noqa: BLE001 - a broken extension must not break `import entity_standardizer.address`
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
        "version": "2.1.0",
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


def standardize_batch_dispatch(
    records: List[Any],
    chunk_size: int = 5000,
    **kwargs: Any,
) -> List[StandardizedAddress]:
    """Dispatches batch standardization to _pure_python_core.standardize_batch."""
    return _pure_python_core.standardize_batch(records, chunk_size=chunk_size, **kwargs)

