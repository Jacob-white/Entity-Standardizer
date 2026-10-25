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


def test_batch_worker_geocoding_and_error_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import entity_standardizer.address.batch as addr_batch

    # Empty chunk & 8-tuple / 9-tuple worker unpacking
    assert addr_batch._worker_process_chunk(([], "street1", "street2", "city", "state", "postal_code", "country", False)) == ([], [])
    rows_8, _ = addr_batch._worker_process_chunk(
        ([{"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110"}], "street1", "street2", "city", "state", "postal_code", "country", True)
    )
    assert rows_8[0]["std_street1"] == "100 MAIN ST"
    rows_9, _ = addr_batch._worker_process_chunk(
        ([{"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110"}], "street1", "street2", "city", "state", "postal_code", "country", True, True)
    )
    assert rows_9[0]["std_country_iso3"] == "USA"

    # Mocked standardize_address path in _worker_process_chunk with duplicate row memoization
    orig_std = addr_batch.standardize_address

    def _mock_std(**kw: object) -> object:
        res = orig_std(**kw)
        mock_aud = MagicMock()
        mock_aud.as_dict.return_value = {"audit_id": "test-aud-1"}
        res.audit_record = mock_aud
        return res

    monkeypatch.setattr(addr_batch, "standardize_address", _mock_std)
    dup_chunk = [
        {"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110"},
        {"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110"},
    ]
    rows_mocked, audits_mocked = addr_batch._worker_process_chunk(
        (dup_chunk, "street1", "street2", "city", "state", "postal_code", "country", True, True, "USA")
    )
    assert len(rows_mocked) == 2 and len(audits_mocked) == 2
    monkeypatch.setattr(addr_batch, "standardize_address", orig_std)

    # Mock CensusGeocoder for geocode=True in CSV, JSONL, and JSON streamers
    mock_geocoder = MagicMock()
    mock_geocoder.geocode_batch.return_value = {
        "0": {"latitude": "42.3601", "longitude": "-71.0589", "precision": "ROOFTOP"}
    }

    csv_in = tmp_path / "geo_in.csv"
    csv_out = tmp_path / "geo_out.csv"
    csv_in.write_text(
        "street1,city,state,postal_code,country\n"
        "100 Main St,Boston,MA,02110,USA\n"
        "200 Oak Ave,Boston,MA,02110,USA\n",
        encoding="utf-8",
    )
    n_csv = stream_standardize_csv(
        str(csv_in),
        str(csv_out),
        max_workers=1,
        geocode=True,
        geocoder=mock_geocoder,
        correct_state_from_zip=True,
    )
    assert n_csv == 2

    # Multiprocessing branch (max_workers=2) on CSV
    csv_mp_out = tmp_path / "mp_out.csv"
    n_mp = stream_standardize_csv(str(csv_in), str(csv_mp_out), chunk_size=1, max_workers=2)
    assert n_mp == 2

    # JSONL with geocode=True and error branches
    jsonl_in = tmp_path / "geo_in.jsonl"
    jsonl_out = tmp_path / "geo_out.jsonl"
    jsonl_in.write_text(
        "\n"
        + json.dumps({"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110", "country": "USA"})
        + "\n"
        + json.dumps({"street1": "10 Downing St", "city": "London", "postal_code": "SW1A 2AA", "country": "GBR"})
        + "\n",
        encoding="utf-8",
    )
    assert stream_standardize_jsonl(str(jsonl_in), str(jsonl_out), max_workers=1, geocode=True, geocoder=mock_geocoder) == 2

    bad_jsonl = tmp_path / "bad.jsonl"
    bad_jsonl.write_text("{not valid json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        stream_standardize_jsonl(str(bad_jsonl), str(tmp_path / "unused1.jsonl"), max_workers=1)

    non_obj_jsonl = tmp_path / "non_obj.jsonl"
    non_obj_jsonl.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        stream_standardize_jsonl(str(non_obj_jsonl), str(tmp_path / "unused2.jsonl"), max_workers=1)

    # JSON with geocode=True and error branches
    json_in = tmp_path / "geo_in.json"
    json_out = tmp_path / "geo_out.json"
    json_in.write_text(
        json.dumps([
            {"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110", "country": "USA"},
            {"street1": "200 Oak Ave", "city": "Boston", "state": "MA", "postal_code": "02110", "country": "USA"},
        ]),
        encoding="utf-8",
    )
    assert stream_standardize_json(str(json_in), str(json_out), max_workers=1, geocode=True, geocoder=mock_geocoder) == 2

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("[123]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        stream_standardize_json(str(bad_json), str(tmp_path / "unused3.json"), max_workers=1)

    # batch_standardize with correct_state_from_zip generator hold, use_cache+batch_size=1, vacant dict, and non-str item
    batch_res = list(
        batch_standardize(
            [
                "100 Wall St, New York, NY 10005",
                {"address": "200 Broadway", "suite": "Ste 10", "city": "New York", "province": "CA", "zip": "10005", "vacant": True},
                12345,
            ],
            correct_state_from_zip=True,
            use_cache=True,
            batch_size=1,
        )
    )
    assert len(batch_res) == 3
    assert batch_res[1].state == "NY"
    assert batch_res[1].vacant is True

