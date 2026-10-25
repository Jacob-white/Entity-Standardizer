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

    # Multiprocessing branch (max_workers=2) on CSV while multi-threaded (no os.fork DeprecationWarning)
    import threading
    import warnings

    stop_evt = threading.Event()
    bg_thread = threading.Thread(target=stop_evt.wait, daemon=True)
    bg_thread.start()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            csv_mp_out = tmp_path / "mp_out.csv"
            n_mp = stream_standardize_csv(str(csv_in), str(csv_mp_out), chunk_size=1, max_workers=2)
            assert n_mp == 2

            # JSONL with geocode=True, max_workers=2, and error branches
            jsonl_in = tmp_path / "geo_in.jsonl"
            jsonl_out = tmp_path / "geo_out.jsonl"
            jsonl_mp_out = tmp_path / "mp_out.jsonl"
            jsonl_in.write_text(
                "\n"
                + json.dumps({"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110", "country": "USA"})
                + "\n"
                + json.dumps({"street1": "10 Downing St", "city": "London", "postal_code": "SW1A 2AA", "country": "GBR"})
                + "\n",
                encoding="utf-8",
            )
            assert stream_standardize_jsonl(str(jsonl_in), str(jsonl_out), max_workers=1, geocode=True, geocoder=mock_geocoder) == 2
            assert stream_standardize_jsonl(str(jsonl_in), str(jsonl_mp_out), chunk_size=1, max_workers=2) == 2

            bad_jsonl = tmp_path / "bad.jsonl"
            bad_jsonl.write_text("{not valid json}\n", encoding="utf-8")
            with pytest.raises(ValueError, match="not valid JSON"):
                stream_standardize_jsonl(str(bad_jsonl), str(tmp_path / "unused1.jsonl"), max_workers=1)

            non_obj_jsonl = tmp_path / "non_obj.jsonl"
            non_obj_jsonl.write_text("[1, 2, 3]\n", encoding="utf-8")
            with pytest.raises(ValueError, match="must be a JSON object"):
                stream_standardize_jsonl(str(non_obj_jsonl), str(tmp_path / "unused2.jsonl"), max_workers=1)

            # JSON with geocode=True, max_workers=2, and error branches
            json_in = tmp_path / "geo_in.json"
            json_out = tmp_path / "geo_out.json"
            json_mp_out = tmp_path / "mp_out.json"
            json_in.write_text(
                json.dumps([
                    {"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02110", "country": "USA"},
                    {"street1": "200 Oak Ave", "city": "Boston", "state": "MA", "postal_code": "02110", "country": "USA"},
                ]),
                encoding="utf-8",
            )
            assert stream_standardize_json(str(json_in), str(json_out), max_workers=1, geocode=True, geocoder=mock_geocoder) == 2
            assert stream_standardize_json(str(json_in), str(json_mp_out), chunk_size=1, max_workers=2) == 2
    finally:
        stop_evt.set()
        bg_thread.join(timeout=1.0)

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


def test_redis_cache_backend_and_serialization(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace
    from entity_standardizer.address.audit import StewardshipAuditRecord, get_audit_ledger
    from entity_standardizer.address.cache_backends import (
        RedisCacheBackend,
        backend_from_url,
        deserialize_value,
        serialize_value,
    )
    from entity_standardizer.address.cascade import CascadeResult
    from entity_standardizer.address.models import LocalityOnlyStatus, SpatialResolutionResult, StandardizedAddress

    with pytest.raises(ValueError, match="needs a redis URL or a client"):
        RedisCacheBackend()

    with pytest.raises(ValueError, match="unsupported cache URL"):
        backend_from_url("http://localhost:6379")

    b_url = backend_from_url("redis://localhost:6379/0", prefix="test:", ttl_seconds=60)
    assert isinstance(b_url, RedisCacheBackend)

    # Test _get_client when redis module is missing vs mocked
    monkeypatch.setitem(sys.modules, "redis", None)
    with pytest.raises(ImportError, match="needs the redis package"):
        b_url._get_client()

    fake_redis_mod = SimpleNamespace(
        Redis=SimpleNamespace(from_url=lambda url, **kw: SimpleNamespace(url=url, kw=kw))
    )
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)
    client_obj = b_url._get_client()
    assert client_obj.url == "redis://localhost:6379/0"

    # Fake Redis client for full get/set/delete/clear/stats and failure/recovery lifecycle
    class FakeRedisClient:
        def __init__(self) -> None:
            self.store: dict[str, bytes] = {}
            self.fail_mode: bool = False

        def get(self, name: str) -> bytes | None:
            if self.fail_mode:
                raise ConnectionError("redis down")
            return self.store.get(name)

        def set(self, name: str, value: str, ex: int | None = None) -> None:
            if self.fail_mode:
                raise ConnectionError("redis down")
            self.store[name] = value.encode("utf-8")

        def delete(self, *names: str) -> int:
            if self.fail_mode:
                raise ConnectionError("redis down")
            removed = 0
            for n in names:
                if n in self.store:
                    del self.store[n]
                    removed += 1
            return removed

        def scan_iter(self, match: str = "*", count: int = 500):
            if self.fail_mode:
                raise ConnectionError("redis down")
            prefix = match[:-1] if match.endswith("*") else match
            return [k for k in list(self.store.keys()) if k.startswith(prefix)]

    now = [100.0]
    fake_client = FakeRedisClient()
    rb = RedisCacheBackend(client=fake_client, prefix="es:", ttl_seconds=120, retry_after=10.0, clock=lambda: now[0])

    # Miss on empty
    assert rb.get("k1") is None
    # Set and hit generic value
    rb.set("k1", {"hello": "world"})
    assert rb.get("k1") == {"hello": "world"}
    # Set and get None (treated as miss)
    rb.set("k_none", None)
    assert rb.get("k_none") is None
    # Non-JSON-serializable value falls back to str(value)
    rb.set("k_obj", object())
    assert isinstance(rb.get("k_obj"), str)

    # Corrupt payload triggers delete and returns None
    fake_client.store["es:corrupt"] = b"{not-json"
    assert rb.get("corrupt") is None
    assert "es:corrupt" not in fake_client.store

    # Delete existing key
    assert rb.delete("k1") is True
    assert rb.delete("k1") is False

    # Clear with > 500 keys to exercise batch deletion loop
    for idx in range(505):
        fake_client.store[f"es:bulk:{idx}"] = b'{"__cache_value__": 1}'
    rb.clear()
    assert len(fake_client.store) == 0

    # Outage degradation and retry_after recovery
    fake_client.fail_mode = True
    assert rb.get("k2") is None
    assert rb.stats()["degraded"] is True
    # While degraded, operations are skipped without touching client
    assert rb.get("k2") is None
    rb.set("k2", "val")
    assert rb.delete("k2") is False
    rb.clear()
    assert rb.stats()["skipped_while_down"] >= 1

    # Advance clock past retry_after and test set/delete/clear failures directly
    now[0] += 15.0
    rb.set("k2", "val")
    now[0] += 15.0
    assert rb.delete("k2") is False
    now[0] += 15.0
    rb.clear()
    now[0] += 15.0
    fake_client.fail_mode = False
    rb.set("k2", "recovered")
    assert rb.get("k2") == "recovered"

    # Full StandardizedAddress serialization & deserialization with audit, cascade, spatial, and locality_only
    std = StandardizedAddress(
        street1="",
        street2="",
        city="BOSTON",
        state="MA",
        postal_code="02110",
        country="USA",
        normalized_address_key="||BOSTON|MA|02110|USA",
        address_status=LocalityOnlyStatus("locality_only"),
        raw_street_address="Boston, MA 02110",
        is_us=True,
    )
    std.country_iso3 = "USA"
    std.deliverability = "DELIVERABLE"
    std.latitude = 42.3601
    std.longitude = -71.0589
    std.audit_record = StewardshipAuditRecord(record_id="REC-1")
    audit_id = std.audit_record.audit_id
    std.cascade_result = CascadeResult(
        latitude=42.3601,
        longitude=-71.0589,
        precision="ROOFTOP",
        accuracy_radius_meters=5.0,
        source="OFFLINE",
        stage=1,
        census_tract="25025010100",
    )
    std.spatial_result = SpatialResolutionResult(
        latitude=42.3601,
        longitude=-71.0589,
        precision="ROOFTOP",
        accuracy_radius_meters=5.0,
        stage=1,
        source="OFFLINE",
        h3_res10="8a2a3066295ffff",
        parcel_id="P123",
        execution_time_ms=0.5,
        metadata={"k": "v"},
    )
    payload = serialize_value(std)
    rebuilt = deserialize_value(payload)
    assert isinstance(rebuilt, StandardizedAddress)
    assert rebuilt.address_status == "locality_only"
    assert rebuilt.audit_record is not None and rebuilt.audit_record.audit_id == audit_id
    assert rebuilt.cascade_result is not None and rebuilt.cascade_result.precision == "ROOFTOP"
    assert rebuilt.spatial_result is not None and rebuilt.spatial_result.parcel_id == "P123"
    assert rebuilt.country_iso3 == "USA"

    # Also test legacy dict shapes in deserialize_value (audit_id lookup, cascade dict, spatial_result dict)
    get_audit_ledger().ensure_recorded(std.audit_record)
    legacy_dict = json.loads(payload)
    del legacy_dict["audit_record_payload"]
    legacy_dict["audit_id"] = audit_id
    legacy_dict["cascade"] = legacy_dict.pop("cascade_result_payload")
    legacy_dict["spatial_result"] = legacy_dict.pop("spatial_result_payload")
    rebuilt_legacy = deserialize_value(json.dumps(legacy_dict))
    assert rebuilt_legacy.audit_record is not None
    assert rebuilt_legacy.cascade_result is not None
    assert rebuilt_legacy.spatial_result is not None
    assert deserialize_value('{"plain": 42}') == {"plain": 42}


def test_census_and_offline_geocoder_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request
    from entity_standardizer.address.geocoder import (
        CensusGeocoder,
        OfflineGeocoder,
        get_fallback_centroid,
        get_fallback_centroid_tier,
        parse_census_geocoder_response,
    )

    # Fallback centroid tiers: 4-digit zip, metro ZIP3, non-metro ZIP3 -> state centroid, state name, unknown
    assert get_fallback_centroid(zip5="2110") is not None
    assert get_fallback_centroid_tier(zip5="10005")[2] == "ZIP3"
    assert get_fallback_centroid_tier(zip5="99501")[2] in ("ZIP3", "STATE")
    assert get_fallback_centroid_tier(zip5="82001")[2] == "STATE"
    assert get_fallback_centroid_tier(state="California")[2] == "STATE"
    assert get_fallback_centroid_tier(state="TX")[2] == "STATE"
    assert get_fallback_centroid(zip5="00", state="ZZ") is None

    # parse_census_geocoder_response
    csv_resp = (
        '"1","100 MAIN ST, BOSTON, MA, 02110","Match","Exact","100 MAIN ST, BOSTON, MA, 02110","-71.0589,42.3601","123456","R"\n'
        '"2","BAD COORDS","Match","Exact","ADDR","not_a_float,xyz","999","L"\n'
        '"3","UNMATCHED","No_Match"\n'
    )
    parsed = parse_census_geocoder_response(csv_resp)
    assert "1" in parsed and parsed["1"] == (42.3601, -71.0589, "123456")
    assert "2" not in parsed and "3" not in parsed

    cg = CensusGeocoder(timeout_seconds=5)
    assert cg.geocode_batch([]) == {}

    class DummyResp:
        def __enter__(self) -> "DummyResp":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return csv_resp.encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: DummyResp())
    batch_out = cg.geocode_batch(
        [
            ("1", '100 "Main" St', "Boston", "MA", "02110"),
            ("3", "999 Unknown Rd", "Boston", "MA", "02110"),
        ],
        fallback_to_centroids=True,
    )
    assert batch_out["1"]["precision"] == "rooftop"
    assert batch_out["3"]["precision"] == "zip_centroid"

    single = cg.geocode_address("100 Main St", "Boston", "MA", "02110")
    assert single is not None and single["precision"] == "rooftop"

    # Exception in urlopen falls back to centroids
    def _raise_url(*args: object, **kwargs: object) -> None:
        raise OSError("network disabled")

    monkeypatch.setattr(urllib.request, "urlopen", _raise_url)
    err_out = cg.geocode_batch([("1", "100 Main St", "Boston", "MA", "02110")], fallback_to_centroids=True)
    assert err_out["1"]["precision"] == "zip_centroid"

    # OfflineGeocoder batch & address methods
    og = OfflineGeocoder()
    og_res = og.geocode_batch([("rec1", "100 Wall St", "New York", "NY", "10005")])
    assert "rec1" in og_res and og_res["rec1"]["latitude"] is not None

