import pytest

import entity_standardizer
from entity_standardizer.address import (
    SpatialEngine,
    SpatialResolutionResult,
    get_default_spatial_engine,
    lat_lng_to_h3,
    resolve_spatial_coordinates,
)
from entity_standardizer.address.international.diacritics import (
    LIGATURE_MAP,
    fold_to_ascii_key,
)
from entity_standardizer.batch import (
    _FORMULA_PREFIXES,
    _csv_safe_cell,
    buffered_chunk_generator,
    chunk_generator,
)
from entity_standardizer.cache import clear_cache, get_cache_stats
from entity_standardizer.normalization import (
    LATIN_LIGATURE_AND_STROKE_MAP,
    fold_latin_diacritics,
)


def test_batch_formula_injection_and_chunking() -> None:
    # Test formula prefix escaping
    for prefix in _FORMULA_PREFIXES:
        injected = f"{prefix}SUM(1+1)"
        safe = _csv_safe_cell(injected)
        assert safe == f"'{prefix}SUM(1+1)"

    # Non-formula strings and non-string types
    assert _csv_safe_cell("Regular Text") == "Regular Text"
    assert _csv_safe_cell(12345) == 12345
    assert _csv_safe_cell(None) is None
    assert _csv_safe_cell(["nested"]) == ["nested"]

    # Invalid chunk_size
    with pytest.raises(ValueError, match="chunk_size must be at least 1"):
        list(buffered_chunk_generator(iter([{"a": 1}]), chunk_size=0))

    with pytest.raises(ValueError, match="chunk_size must be at least 1"):
        list(buffered_chunk_generator(iter([{"a": 1}]), chunk_size=-5))

    # Empty generator
    assert list(buffered_chunk_generator(iter([]), chunk_size=3)) == []
    assert list(chunk_generator(iter([]), chunk_size=3)) == []

    # Exact multiple of chunk_size
    items = [{"id": i} for i in range(6)]
    chunks = list(buffered_chunk_generator(iter(items), chunk_size=3))
    assert len(chunks) == 2
    assert len(chunks[0]) == 3 and chunks[0][0]["id"] == 0
    assert len(chunks[1]) == 3 and chunks[1][2]["id"] == 5

    # Remainder chunk
    items_odd = [{"id": i} for i in range(5)]
    chunks_odd = list(chunk_generator(iter(items_odd), chunk_size=2))
    assert len(chunks_odd) == 3
    assert len(chunks_odd[0]) == 2
    assert len(chunks_odd[1]) == 2
    assert len(chunks_odd[2]) == 1 and chunks_odd[2][0]["id"] == 4


def test_diacritic_parity_and_canonical_maps() -> None:
    # Check canonical table completeness
    assert "đ" in LATIN_LIGATURE_AND_STROKE_MAP
    assert "Đ" in LATIN_LIGATURE_AND_STROKE_MAP
    assert "ħ" in LATIN_LIGATURE_AND_STROKE_MAP
    assert "Ħ" in LATIN_LIGATURE_AND_STROKE_MAP
    assert LATIN_LIGATURE_AND_STROKE_MAP["đ"] == "d"
    assert LATIN_LIGATURE_AND_STROKE_MAP["Đ"] == "D"
    assert LATIN_LIGATURE_AND_STROKE_MAP["ħ"] == "h"
    assert LATIN_LIGATURE_AND_STROKE_MAP["Ħ"] == "H"

    # LIGATURE_MAP derived upper-case
    assert LIGATURE_MAP["đ"] == "D"
    assert LIGATURE_MAP["Đ"] == "D"
    assert LIGATURE_MAP["ħ"] == "H"
    assert LIGATURE_MAP["Ħ"] == "H"

    # Diacritic folding tests
    assert fold_latin_diacritics("đ") == "d"
    assert fold_latin_diacritics("Đ") == "D"
    assert fold_latin_diacritics("ħ") == "h"
    assert fold_latin_diacritics("Ħ") == "H"
    assert fold_latin_diacritics("Đorđe") == "Dorde"
    assert fold_latin_diacritics("Għasri") == "Ghasri"
    assert fold_latin_diacritics("Māra") == "Mara"
    assert fold_latin_diacritics("Kraków") == "Krakow"

    # ASCII key folding parity
    assert fold_to_ascii_key("Đorđe") == "DORDE"
    assert fold_to_ascii_key("Għasri") == "GHASRI"


def test_lazy_spatial_exports_and_dir() -> None:
    import entity_standardizer.address as addr_mod

    # Dir check includes PEP 562 lazy exports
    dir_symbols = dir(addr_mod)
    assert "lat_lng_to_h3" in dir_symbols
    assert "SpatialEngine" in dir_symbols
    assert "SpatialResolutionResult" in dir_symbols
    assert "resolve_spatial_coordinates" in dir_symbols
    assert "get_default_spatial_engine" in dir_symbols

    # Access lazy symbols
    assert entity_standardizer.__version__ == "2.1.0"
    assert lat_lng_to_h3(37.7749, -122.4194) == "8a283082800ffff"
    engine = get_default_spatial_engine()
    assert isinstance(engine, SpatialEngine)
    assert callable(resolve_spatial_coordinates)

    # Resolution result class
    res = SpatialResolutionResult(
        latitude=37.7749,
        longitude=-122.4194,
        precision="CONFIRMED_ROOFTOP",
        accuracy_radius_meters=15.0,
        stage=1,
        source="TEST",
        h3_res10="8a283082800ffff",
    )
    assert res.h3_res10 == "8a283082800ffff"
    assert res.as_dict()["h3_res10"] == "8a283082800ffff"

    # AttributeError on invalid attribute
    with pytest.raises(AttributeError, match="has no attribute 'non_existent_export'"):
        getattr(addr_mod, "non_existent_export")


def test_cache_unification_stats_and_clearing() -> None:
    # Clear cache and verify structure
    clear_cache()
    stats = get_cache_stats()
    assert "l1" in stats
    assert "l2_enabled" in stats
    assert "l2_hits" in stats
    assert "l2_misses" in stats
    assert "phone" in stats
    assert "address" in stats

    # Address cache uninitialized / None branch
    from entity_standardizer.address import cache as _addr_cache

    saved_addr_cache = _addr_cache._DEFAULT_CACHE
    try:
        _addr_cache._DEFAULT_CACHE = None
        stats_no_addr = get_cache_stats()
        assert stats_no_addr["address"]["enabled"] is True
        assert stats_no_addr["address"]["l1"]["size"] == 0
        clear_cache()

        # Initialize address cache and test populated stats
        _addr_cache.get_default_cache()
        stats_with_addr = get_cache_stats()
        assert stats_with_addr["address"]["enabled"] is True
        clear_cache()
    finally:
        _addr_cache._DEFAULT_CACHE = saved_addr_cache
