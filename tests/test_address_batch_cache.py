"""Comprehensive unit tests for address batch processing, CSV/JSONL/JSON streaming, multi-tier caching, and pluggable cache backends."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from entity_standardizer.address import (
    LRUCache,
    MultiTierCache,
    SQLiteCache,
    batch_standardize,
    buffered_chunk_generator,
    chunk_generator,
    clear_cache,
    configure_cache,
    get_cache_stats,
    get_default_cache,
    make_cache_key,
    process_chunk,
    standardize_address,
    stream_standardize_csv,
    stream_standardize_json,
    stream_standardize_jsonl,
)
from entity_standardizer.address.batch import resolve_column_mappings
from entity_standardizer.address.cache_backends import (
    RedisCacheBackend,
    backend_from_url,
    deserialize_value,
    serialize_value,
)


def test_address_batch_and_streaming_pipelines(tmp_path: Path) -> None:
    # Column mapping resolution
    s1, s2, city, state, postal, country = resolve_column_mappings(
        {"address1": "street1", "suite": "street2", "zip": "postal_code", "province": "state"}
    )
    assert s1 == "address1" and s2 == "suite" and postal == "zip" and state == "province"

    # Chunk generators
    items = list(range(7))
    assert list(chunk_generator(items, 3)) == [[0, 1, 2], [3, 4, 5], [6]]
    assert list(buffered_chunk_generator(items, 3)) == [[0, 1, 2], [3, 4, 5], [6]]

    # process_chunk & batch_standardize
    rows = [
        {"street1": "100 Wall St Ste 400", "city": "New York", "state": "NY", "postal_code": "10005"},
        {"street1": "1209 N Orange St", "city": "Wilmington", "state": "DE", "postal_code": "19801"},
        {"street1": "=cmd|' /C calc'!A0", "city": "New York", "state": "NY", "postal_code": "10001"},
    ]
    chunk_out = process_chunk(rows)
    assert len(chunk_out) == 3 and chunk_out[0]["std_street1"] == "100 WALL ST"

    batch_out = list(
        batch_standardize(
            rows,
            max_workers=1,
            include_confidence=True,
            enable_geocoding=True,
            include_intl=True,
        )
    )
    assert len(batch_out) == 3
    assert batch_out[0].confidence_score > 0
    assert batch_out[0].spatial_result is not None
    assert batch_out[0].country == "USA"

    # CSV streaming with audit CSV, confidence, and spatial geocoding
    in_csv = tmp_path / "addresses.csv"
    out_csv = tmp_path / "addresses_out.csv"
    audit_csv = tmp_path / "audit_out.csv"
    in_csv.write_text(
        "addr,city,state,zip\n"
        "100 Wall St Ste 400,New York,NY,10005\n"
        "1209 N Orange St,Wilmington,DE,19801\n",
        encoding="utf-8",
    )
    n_csv = stream_standardize_csv(
        str(in_csv),
        str(out_csv),
        chunk_size=1,
        max_workers=1,
        mapping={"addr": "street1", "zip": "postal_code"},
        include_confidence=True,
        audit_csv_path=str(audit_csv),
        enable_geocoding=True,
        include_intl=True,
    )
    assert n_csv == 2
    assert "100 WALL ST" in out_csv.read_text(encoding="utf-8")
    assert audit_csv.exists()

    # Refuse overwriting input path
    with pytest.raises(ValueError):
        stream_standardize_csv(str(in_csv), str(in_csv))

    # JSONL streaming
    in_jsonl = tmp_path / "addresses.jsonl"
    out_jsonl = tmp_path / "addresses_out.jsonl"
    in_jsonl.write_text(
        '\n{"street1": "350 Fifth Ave", "city": "New York", "state": "NY", "postal_code": "10118"}\n'
        '{"street1": "10 Downing Street", "city": "London", "postal_code": "SW1A 2AA", "country": "GB"}\n',
        encoding="utf-8",
    )
    n_jsonl = stream_standardize_jsonl(
        str(in_jsonl),
        str(out_jsonl),
        chunk_size=1,
        max_workers=1,
        include_confidence=True,
        enable_geocoding=True,
        include_intl=True,
    )
    assert n_jsonl == 2
    jsonl_lines = [json.loads(line) for line in out_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert jsonl_lines[0]["std_street1"] == "350 5TH AVE"

    # JSON array streaming
    in_json = tmp_path / "addresses.json"
    out_json = tmp_path / "addresses_out.json"
    in_json.write_text(
        json.dumps([{"street1": "1600 Amphitheatre Pkwy", "city": "Mountain View", "state": "CA", "postal_code": "94043"}]),
        encoding="utf-8",
    )
    n_json = stream_standardize_json(
        str(in_json),
        str(out_json),
        chunk_size=10,
        max_workers=1,
        include_confidence=True,
        enable_geocoding=True,
    )
    assert n_json == 1
    parsed_json = json.loads(out_json.read_text(encoding="utf-8"))
    assert parsed_json[0]["std_street1"] == "1600 AMPHITHEATRE PKWY"


def test_multitier_cache_and_pluggable_backends(tmp_path: Path) -> None:
    # make_cache_key escaping & flags
    k1 = make_cache_key("100 Wall St", "Ste 400", "New York", "NY", "10005", "USA", is_vacant=True, enable_geocoding=True)
    k2 = make_cache_key("100 Wall St|Ste 400", "", "New York", "NY", "10005", "USA")
    assert k1 != k2 and "VACANT" in k1 and "GEOCODE" in k1

    # L1 LRUCache eviction & delete
    l1 = LRUCache(maxsize=2)
    l1.set("a", 1)
    l1.set("b", 2)
    assert l1.get("a") == 1
    l1.set("c", 3)  # evicts "b"
    assert l1.get("b") is None
    assert l1.delete("a") is True
    assert l1.delete("missing") is False
    assert l1.stats()["evictions"] == 1
    l1.clear()
    assert l1.size() == 0

    # L2 SQLiteCache persistence, serialize/deserialize StandardizedAddress with spatial + audit metadata
    std = standardize_address("1209 N Orange St Ste 400", city="Wilmington", state="DE", postal_code="19801", enable_geocoding=True)
    payload = serialize_value(std)
    rebuilt = deserialize_value(payload)
    assert rebuilt.street1 == std.street1
    assert rebuilt.spatial_result is not None

    l2_path = str(tmp_path / "l2_cache.db")
    l2 = SQLiteCache(db_path=l2_path, max_entries=3)
    l2.set("k1", std)
    hit = l2.get("k1")
    assert hit is not None and hit.street1 == std.street1
    assert l2.delete("k1") is True
    assert l2.get("k1") is None
    l2.clear()

    # MultiTierCache L1 -> L2 promotion
    mt = MultiTierCache(l1_maxsize=10, l2_db_path=":memory:")
    mt.set("addr1", std)
    mt._l1.clear()
    promoted = mt.get("addr1")
    assert promoted is not None and promoted.street1 == std.street1
    assert mt._l1.get("addr1") is not None
    assert mt.delete("addr1") is True
    assert mt.stats()["enabled"] is True
    mt.clear()

    # Global configure_cache & backend_from_url
    with pytest.raises(ValueError):
        backend_from_url("ftp://example.com")

    # Mocked RedisCacheBackend resilience (never raises on outage)
    mock_redis = MagicMock()
    mock_redis.get.return_value = payload
    r_backend = RedisCacheBackend(client=mock_redis, ttl_seconds=60)
    r_backend.set("rk1", std)
    r_hit = r_backend.get("rk1")
    assert r_hit is not None and r_hit.street1 == std.street1
    assert r_backend.delete("rk1") is True
    r_backend.clear()
    assert "hits" in r_backend.stats()

    # Simulate Redis failure -> graceful fallback to miss
    mock_redis.get.side_effect = RuntimeError("connection lost")
    assert r_backend.get("rk1") is None
    assert r_backend.stats()["errors"] >= 1

    configure_cache(enabled=True, l1_maxsize=100)
    clear_cache()
    assert get_default_cache().is_enabled() is True
    assert "l1" in get_cache_stats()
