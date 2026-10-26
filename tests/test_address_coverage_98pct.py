"""Targeted unit tests for address subsystem edge cases and >= 98.5% coverage gate."""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from entity_standardizer.address import (
    SpatialResolutionResult,
    StandardizedAddress,
    standardize_address,
    validate_address,
)
from entity_standardizer.address.models import LocalityOnlyStatus
from entity_standardizer.address._inputs import (
    coerce_text,
    correct_state_from_zip,
    is_privacy_placeholder,
)
from entity_standardizer.address import _native_dispatch as addr_native_dispatch
from entity_standardizer.address._patterns import (
    clean_redundant_street_tail,
    clean_repetitive_cycles,
    clean_rooftop_address,
    is_edit_distance_leq1,
    parse_intersection_address,
)
from entity_standardizer.address._pure_python_core import (
    standardize_batch,
    standardize_record,
)
from entity_standardizer.address.audit import StewardshipAuditLedger
from entity_standardizer.address.autocomplete import (
    AutocompleteEngine,
    AutocompleteSuggestion,
    _finite_or_none,
)
from entity_standardizer.address.batch import (
    resolve_column_mappings,
    stream_standardize_json,
    stream_standardize_jsonl,
)
from entity_standardizer.address.cache import SQLiteCache
from entity_standardizer.address.calibration import (
    Calibrator,
    brier_score,
    expected_calibration_error,
    fit_isotonic,
    reliability_bins,
)
from entity_standardizer.address.confidence import (
    compute_confidence_score,
    compute_field_confidence,
)
from entity_standardizer.address.fast_path import (
    _normalize_fast_sec_unit,
    _normalize_fast_street_phrase,
    fast_path_parse,
)
from entity_standardizer.address.international import CountryGrammarRegistry
from entity_standardizer.address.international.base import (
    ParsedAddressComponents,
    UniversalInternationalGrammar,
    split_single_line_locality,
)
from entity_standardizer.address.international.cjk import (
    separate_house_number,
    split_jp_tokens,
    strip_trailing_country as strip_cjk_trailing_country,
)
from entity_standardizer.address.international.countries import CountryRegistry
from entity_standardizer.address.international.postal import (
    _extract_for_country,
    extract_postal_code,
    validate_postal_code,
)
from entity_standardizer.address.international.uk import UKParsedAddressComponents
from entity_standardizer.address.international.upu import format_upu_address
from entity_standardizer.address.normalization import (
    normalize_country,
    normalize_country_code,
)
from entity_standardizer.address.offline_index import OfflineReferenceIndex
from entity_standardizer.address.reference.base import (
    CompositeProvider,
    DeliveryMatch,
    ReferencePlace,
)
from entity_standardizer.address.reference.us_zip5 import get_default_us_zip5_provider
from entity_standardizer.address.reference.validation import (
    ReferenceValidation,
    apply_reference_validation,
    validate_against_reference,
)
from entity_standardizer.address.registry import (
    evaluate_corporate_risk,
    lookup_corporate_registry,
)
from entity_standardizer.address.spatial.engine import SpatialEngine
from entity_standardizer.address.standardizer import (
    _finalize_standardized_address,
    _is_unit_phrase,
)
from entity_standardizer.address.international import fold_to_ascii_key
from entity_standardizer.address.transliterate import _builtin, transliterate
from entity_standardizer.address.us_street_parser import (
    _parse_us_address_components,
    _parse_us_street_tokens,
    _rule_based_us_street_parse,
    _unswap_state_city,
)


def test_models_and_inputs_edge_cases():
    loc = LocalityOnlyStatus("locality_only")
    assert hash(loc) == hash("locality_only")
    assert (loc == 123) is False
    assert (loc != 123) is True

    addr = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="NEW YORK",
        state="NY",
        postal_code="10001",
        country="USA",
        normalized_address_key="100 MAIN ST||NEW YORK|NY|10001|USA",
        address_status="standardized",
        raw_street_address="100 Main St, New York, NY 10001",
        is_us=True,
    )
    addr._deliverability = None
    addr.dpv_footnotes = ["N1"]
    assert addr.deliverability == "REQUIRES_SECONDARY"
    addr.dpv_footnotes = ["BB"]
    assert addr.deliverability == "DELIVERABLE"
    addr.dpv_footnotes = ["M1"]
    assert addr.deliverability == "UNDELIVERABLE"
    addr.dpv_footnotes = []
    assert addr.deliverability == "DELIVERABLE"
    addr.address_status = "pending"
    assert addr.deliverability == "UNDELIVERABLE"
    addr.address_status = "standardized"

    addr.secondary_prompt_required = True
    addr._prompt_message = None
    addr._suggested_secondary_units = None
    assert addr.prompt_message == "Requires Suite / Apartment Number"
    assert addr.suggested_secondary_units == ["STE", "FL", "UNIT", "APT"]

    sp = SpatialResolutionResult(
        latitude=40.7128,
        longitude=-74.0060,
        precision="CONFIRMED_ROOFTOP",
        accuracy_radius_meters=5.0,
        stage=1,
        source="TEST",
        h3_res10="8a2a1072b59ffff",
        metadata={"census_tract": "36061000100", "fips_code": "36061"},
    )
    addr._latitude = None
    addr._longitude = None
    addr.spatial_result = sp
    assert addr.latitude == 40.7128
    assert addr.longitude == -74.0060

    d_rooftop = addr.as_dict(include_rooftop=True, include_metadata=False)
    assert d_rooftop["rooftop_address"] == "100 MAIN ST"
    assert "full_rooftop_address" in d_rooftop

    addr.reference_validation = ReferenceValidation(status="confirmed")
    addr.alternatives = [{"street1": "100 MAIN ST"}]
    d_ext = addr.as_extended_dict()
    assert d_ext["reference_validation"]["status"] == "confirmed"
    assert d_ext["alternatives"] == [{"street1": "100 MAIN ST"}]

    upu_text = addr.format_upu(recipient="ACME INC", include_country_name=True)
    assert "ACME INC" in upu_text
    assert "100 MAIN ST" in upu_text

    # _inputs.py edge cases
    assert coerce_text(float("nan")) == ""
    assert coerce_text(100.0) == "100"
    assert coerce_text(100.5) == "100.5"
    assert coerce_text(b"100 Main St") == "100 Main St"
    assert coerce_text("100 Main\ud800 St") == "100 Main? St"

    assert is_privacy_placeholder("Confidential, New York") is True
    assert correct_state_from_zip("NY", "10001", "CAN") == ("NY", None)
    assert correct_state_from_zip("NY", "ABC", "USA") == ("NY", None)
    assert correct_state_from_zip("NY", "00000", "USA") == ("NY", None)


def test_native_dispatch_and_pure_python_core(monkeypatch):
    # _pure_python_core edge cases
    assert standardize_batch([]) == []
    res_batch = standardize_batch([123, "100 Main St, Boston, MA 02101"])
    assert len(res_batch) == 2
    assert standardize_record(street1="100 Main St", city="Boston", state="MA", postal_code="02101").street1 == "100 MAIN ST"

    # _native_dispatch edge cases
    with patch.object(addr_native_dispatch, "_NATIVE_AVAILABLE", True), patch.object(
        addr_native_dispatch, "_FORCE_PURE_PYTHON", False
    ), patch.object(
        addr_native_dispatch, "_NATIVE_MODULE", types.SimpleNamespace(bad=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    ):
        assert addr_native_dispatch.try_native("bad") == (False, None)
        assert addr_native_dispatch.try_native("missing_fn") == (False, None)

    def raise_kb():
        raise KeyboardInterrupt()

    with patch.object(addr_native_dispatch, "_NATIVE_AVAILABLE", True), patch.object(
        addr_native_dispatch, "_FORCE_PURE_PYTHON", False
    ), patch.object(
        addr_native_dispatch, "_NATIVE_MODULE", types.SimpleNamespace(kb=raise_kb)
    ):
        with pytest.raises(KeyboardInterrupt):
            addr_native_dispatch.try_native("kb")

    fake_mod = types.ModuleType("_entity_standardizer_rs")
    with patch("entity_standardizer._native_dispatch._load_native_module", return_value=fake_mod):
        assert addr_native_dispatch._load_fallback_native() is fake_mod

    orig_mod = addr_native_dispatch._NATIVE_MODULE
    orig_avail = addr_native_dispatch._NATIVE_AVAILABLE
    orig_force = addr_native_dispatch._FORCE_PURE_PYTHON
    try:
        monkeypatch.setenv("ENTITY_STANDARDIZER_FORCE_PURE", "1")
        addr_native_dispatch._init_native()
        assert addr_native_dispatch.is_using_native() is False
        assert addr_native_dispatch.get_active_engine() is addr_native_dispatch._pure_python_core
        assert addr_native_dispatch.get_engine_info()["is_native"] is False

        monkeypatch.delenv("ENTITY_STANDARDIZER_FORCE_PURE", raising=False)
        monkeypatch.delenv("ADDRESS_STANDARDIZER_FORCE_PURE", raising=False)
        with patch.object(addr_native_dispatch, "_load_fallback_native", return_value=fake_mod), patch(
            "builtins.__import__", side_effect=ImportError("no _entity_standardizer_rs")
        ):
            addr_native_dispatch._init_native()
            assert addr_native_dispatch.is_using_native() is True
            assert addr_native_dispatch.get_active_engine() is fake_mod

        with patch.object(addr_native_dispatch, "_load_fallback_native", return_value=None), patch(
            "builtins.__import__", side_effect=ImportError("no _entity_standardizer_rs")
        ):
            addr_native_dispatch._init_native()
            assert addr_native_dispatch.is_using_native() is False

        with patch("builtins.__import__", side_effect=RuntimeError("unexpected import error")):
            addr_native_dispatch._init_native()
            assert addr_native_dispatch.is_using_native() is False

        class BadCaps:
            def get_capabilities(self):
                raise RuntimeError("caps failed")

        addr_native_dispatch._NATIVE_MODULE = BadCaps()
        addr_native_dispatch._NATIVE_AVAILABLE = True
        addr_native_dispatch._FORCE_PURE_PYTHON = False
        assert addr_native_dispatch._native_function_names() == []
        assert addr_native_dispatch.get_capabilities()["engine"] == "Rust_PyO3"
    finally:
        addr_native_dispatch._NATIVE_MODULE = orig_mod
        addr_native_dispatch._NATIVE_AVAILABLE = orig_avail
        addr_native_dispatch._FORCE_PURE_PYTHON = orig_force


def test_patterns_fast_path_and_us_street_parser():
    assert is_edit_distance_leq1("MAIN", "MAIN") is True
    assert clean_redundant_street_tail("100 Main St SW1A2AA", postal_code="SW1A 2AA") == "100 Main St"
    assert clean_redundant_street_tail("100 Main St 10001", postal_code="10001-1234") == "100 Main St"
    assert clean_redundant_street_tail("100 Main St K1A 0B1", city="Ottawa", state="ON", postal_code="") == "100 Main St"
    assert clean_redundant_street_tail("100 Main St DE Boston", city="Boston") == "100 Main St"

    assert clean_repetitive_cycles("100 MAIN ST, 100 MAIN ST") == "100 MAIN ST"
    assert clean_repetitive_cycles("100 MAIN, STE 200, 100 MAIN, STE 200") == "100 MAIN , STE 200"
    assert clean_repetitive_cycles("MAIN MAIN MAIN") == "MAIN"

    assert parse_intersection_address("100 Main St and 5th Ave") == "100 MAIN ST & 5TH AVE"
    assert parse_intersection_address("Main St at 5th Ave") == "MAIN ST & 5TH AVE"

    assert clean_rooftop_address("100 MAIN ST BLDG NORTH") == "100 MAIN ST BLDG NORTH"
    assert clean_rooftop_address("100 MAIN BUILDING") == "100 MAIN BUILDING"

    # fast_path.py branches
    assert _normalize_fast_street_phrase("USA") is None
    assert _normalize_fast_street_phrase("100 Main St N") == ("100 MAIN ST N", "")
    assert _normalize_fast_street_phrase("100 Main St Nort", enable_fuzzy=True) == ("100 MAIN ST N", "")
    assert _normalize_fast_street_phrase("100 A B C D E F St") is None
    assert _normalize_fast_street_phrase("100 Twenty-First St") == ("100 21ST ST", "")
    assert _normalize_fast_street_phrase("100 1000TH St") == ("100 1000TH ST", "")
    assert _normalize_fast_sec_unit("200 OAK AVE APT 3") is None
    assert _normalize_fast_sec_unit("5 OAK") is None

    # Path A edge cases in fast_path_parse
    assert fast_path_parse(street1="Boston, MA 02101", city="Boston", state="MA", postal_code="02101") is None
    fp_healed = fast_path_parse(street1="100 Main St", city="Boston", state="MA", postal_code="00211", enable_fuzzy=True)
    assert fp_healed is not None and fp_healed.postal_code == "02011"
    assert fast_path_parse(street1="100 Main St", street2="5 OAK", city="Boston", state="MA", postal_code="02101") is None

    # Path B edge cases in fast_path_parse
    assert fast_path_parse(street1="100 Main St, Boston, XX 02101") is None
    assert fast_path_parse(street1="100 A B C D E F St, Boston, MA 02101") is None
    assert fast_path_parse(street1="100 Main St, 5 OAK, Boston, MA 02101") is None
    fp_b_healed = fast_path_parse(street1="100 Main St, Boston, MA 00211", enable_fuzzy=True)
    assert fp_b_healed is not None and fp_b_healed.postal_code == "02011"
    fp_b_healed9 = fast_path_parse(street1="100 Main St, Boston, MA 00211-1234", enable_fuzzy=True)
    assert fp_b_healed9 is not None and fp_b_healed9.postal_code == "02011-1234"

    # us_street_parser.py branches
    assert _rule_based_us_street_parse("100 TWENTY-FIRST ST")[0] == "100 21ST ST"
    assert _rule_based_us_street_parse("100 CUSTOMNAME ST", enable_fuzzy=False)[0] == "100 CUSTOMNAME ST"
    assert _unswap_state_city("100 Main St, IL, Springfield IL 62701") == "100 Main St, IL, Springfield IL 62701"
    assert _parse_us_address_components("", "") == ("", "", False, "", "", "")

    with patch("entity_standardizer.address.us_street_parser.usaddress", None):
        res_no_crf = _parse_us_street_tokens("100 Main St", enable_fuzzy=True)
        assert res_no_crf[0] == "100 MAIN ST"

    with patch("entity_standardizer.address.us_street_parser.usaddress") as mock_usa:
        mock_usa.tag.side_effect = RuntimeError("CRF failure")
        res_err_crf = _parse_us_street_tokens("100 Main St", enable_fuzzy=True)
        assert res_err_crf[0] == "100 MAIN ST"


def test_standardizer_pipeline_and_validation_branches():
    assert _is_unit_phrase("STE 40") is True
    assert _is_unit_phrase("STE 400 EXTRA") is False

    # Multiline bleed in city and street1 when street2 is empty
    r_city_bleed = standardize_address(
        street1="100 Main St", street2="", city="Suite 200\nBoston", state="MA", postal_code="02101", use_cache=False
    )
    assert r_city_bleed.street2 == "STE 200"
    assert r_city_bleed.city == "BOSTON"

    r_s1_bleed = standardize_address(
        street1="100 Main St\nSuite 300", street2="", city="Boston", state="MA", postal_code="02101", use_cache=False
    )
    assert r_s1_bleed.street1 == "100 MAIN ST"
    assert r_s1_bleed.street2 == "STE 300"

    r_s1_all_stripped = standardize_address(
        street1="Suite 200\nMain Office",
        street2="",
        city="Boston",
        state="MA",
        postal_code="02101",
        allow_locality=True,
        use_cache=False,
    )
    assert r_s1_all_stripped.street1 == ""
    assert r_s1_all_stripped.street2 == "STE 200"

    r_s2_garbage = standardize_address(
        street1="100 Main St", street2="N/A", city="Boston", state="MA", postal_code="02101", use_cache=False
    )
    assert r_s2_garbage.street2 == ""

    # US Tier 2 postal transposition healing (5-digit and 9-digit) & privacy placeholder & norm_s1 == norm_city
    r_tier2_zip5 = standardize_address(
        street1="100 1/2 Main St", city="Boston", state="MA", postal_code="00211", enable_fuzzy=True, use_cache=False
    )
    assert r_tier2_zip5.postal_code == "02011"

    r_tier2_zip9 = standardize_address(
        street1="100 1/2 Main St",
        city="Boston",
        state="MA",
        postal_code="00211-1234",
        enable_fuzzy=True,
        use_cache=False,
    )
    assert r_tier2_zip9.postal_code == "02011-1234"

    r_tier2_priv = standardize_address(
        street1="Confidential", city="Boston", state="MA", postal_code="", use_cache=False
    )
    assert r_tier2_priv.is_private_residence is True
    assert r_tier2_priv.street1 == "PRIVATE RESIDENCE"

    r_tier2_same_city = standardize_address(
        street1="Boston", city="Boston", state="MA", postal_code="02101", allow_locality=True, use_cache=False
    )
    assert r_tier2_same_city.street1 == ""
    assert r_tier2_same_city.is_locality_only is True

    # International norm_s1 == norm_city & PO Box promotion
    r_intl_same_city = standardize_address(
        street1="Toronto", city="Toronto", state="ON", postal_code="M5V 2T6", country="CAN", allow_locality=True, use_cache=False
    )
    assert r_intl_same_city.street1 == ""
    assert r_intl_same_city.is_locality_only is True

    r_intl_pobox = standardize_address(
        street1="Suite 40", street2="PO Box 500", city="Cape Town", postal_code="8001", country="ZAF", use_cache=False
    )
    assert "PO BOX 500" in r_intl_pobox.street1
    r_intl_pobox_empty = standardize_address(
        street1="", street2="PO Box 500", city="Cape Town", postal_code="8001", country="ZAF", use_cache=False
    )
    assert "PO BOX 500" in r_intl_pobox_empty.street1

    # _finalize_standardized_address geocoding fallback when spatial returns UNRESOLVED
    std_unresolved = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="BOSTON",
        state="MA",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST||BOSTON|MA|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Boston, MA 02101",
        is_us=True,
    )
    fake_sp = SpatialResolutionResult(
        latitude=0.0,
        longitude=0.0,
        precision="UNRESOLVED",
        accuracy_radius_meters=0.0,
        stage=0,
        source="NONE",
        h3_res10="",
        metadata={},
    )
    fake_geo = {
        "latitude": 42.3601,
        "longitude": -71.0589,
        "precision": "POSTAL_CENTROID",
        "accuracy_radius_meters": 1500.0,
        "census_tract": "25025010100",
        "fips_code": "25025",
    }
    with patch("entity_standardizer.address.spatial.resolve_spatial_coordinates", return_value=fake_sp), patch(
        "entity_standardizer.address.geocoder.geocode_offline", return_value=fake_geo
    ):
        _finalize_standardized_address(std_unresolved, enable_geocoding=True)
        assert std_unresolved.latitude == 42.3601
        assert std_unresolved.census_tract == "25025010100"
        assert std_unresolved.fips_code == "25025"

    # validate_address rejection branches
    fake_std = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="BOSTON",
        state="MA",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST||BOSTON|MA|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Boston, MA 02101",
        is_us=True,
    )
    fake_std.deliverability = "UNDELIVERABLE"
    fake_std.routing_tier = "AUTO_PASS"
    fake_std.failure_reason_codes = []
    fake_std.confidence_score = 0.5
    with patch("entity_standardizer.address.standardizer.standardize_address", return_value=fake_std):
        v1 = validate_address(street1="100 Main St")
        assert v1.is_valid is False
        assert v1.rejection_reason == "Address is undeliverable"

    fake_std.deliverability = "DELIVERABLE"
    fake_std.routing_tier = "MANUAL_STEWARDSHIP"
    with patch("entity_standardizer.address.standardizer.standardize_address", return_value=fake_std):
        v2 = validate_address(street1="100 Main St")
        assert v2.is_valid is False
        assert v2.rejection_reason == "Low confidence score requires manual stewardship"

    fake_std.routing_tier = "FUZZY_REVIEW"
    with patch("entity_standardizer.address.standardizer.standardize_address", return_value=fake_std):
        v3 = validate_address(street1="100 Main St", strict=True)
        assert v3.is_valid is False
        assert v3.rejection_reason == "Address validation failed strict requirements"
        assert v3.to_dict()["is_valid"] is False
        assert v3.is_deliverable is False


def test_batch_streaming_and_column_mappings(tmp_path: Path):
    assert resolve_column_mappings({}) == ("street1", "street2", "city", "state", "postal_code", "country")
    mapped = resolve_column_mappings({"street1": "addr_line_1", "City Name": "city"})
    assert mapped[0] == "addr_line_1"
    assert mapped[2] == "City Name"

    # Build a spatial SQLite DB via SpatialEngine to exercise spatial_db opening/closing in JSONL and JSON batch streaming
    spatial_db = tmp_path / "spatial.sqlite"
    sp_init = SpatialEngine(db_path=str(spatial_db), seed=True)
    sp_init.close()

    jsonl_in = tmp_path / "in.jsonl"
    jsonl_out = tmp_path / "out.jsonl"
    audit_jsonl = tmp_path / "audit_jsonl.csv"
    jsonl_in.write_text(
        json.dumps({"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02101"})
        + "\n"
        + json.dumps({"street1": "X", "city": "", "state": "", "postal_code": ""})
        + "\n",
        encoding="utf-8",
    )
    stats_jsonl = stream_standardize_jsonl(
        str(jsonl_in),
        str(jsonl_out),
        max_workers=1,
        audit_csv_path=str(audit_jsonl),
        spatial_db=str(spatial_db),
        enable_geocoding=True,
        include_confidence=True,
    )
    assert stats_jsonl == 2
    assert audit_jsonl.exists()

    json_in = tmp_path / "in.json"
    json_out = tmp_path / "out.json"
    audit_json = tmp_path / "audit_json.csv"
    json_in.write_text(
        json.dumps(
            [
                {"street1": "100 Main St", "city": "Boston", "state": "MA", "postal_code": "02101"},
                {"street1": "X", "city": "", "state": "", "postal_code": ""},
            ]
        ),
        encoding="utf-8",
    )
    stats_json = stream_standardize_json(
        str(json_in),
        str(json_out),
        max_workers=1,
        audit_csv_path=str(audit_json),
        spatial_db=str(spatial_db),
        enable_geocoding=True,
        include_confidence=True,
    )
    assert stats_json == 2
    assert audit_json.exists()


def test_autocomplete_confidence_and_spatial_engines(tmp_path: Path):
    assert _finite_or_none("not_a_number") is None
    sug = AutocompleteSuggestion(
        text="100 MAIN ST, STE 200, BOSTON, MA 02101",
        street1="100 MAIN ST",
        street2="STE 200",
        city="BOSTON",
        state="MA",
        postal_code="02101",
    )
    assert sug.street_line == "100 MAIN ST"
    assert sug.to_dict()["street_line"] == "100 MAIN ST"

    ref_db = tmp_path / "ref.sqlite"
    ref_idx = OfflineReferenceIndex(db_path=str(ref_db), seed=False)
    ref_idx.insert_record(
        address_key="777 BEACON ST||BOSTON|MA|02115|USA",
        building_key="777 BEACON ST||BOSTON|MA|02115|USA",
        street1="777 BEACON ST",
        city="BOSTON",
        state="MA",
        postal_code="02115",
        latitude=42.3496,
        longitude=-71.1003,
        is_multi_unit=True,
        known_units=["STE 100"],
    )
    # Corrupt known_units JSON on a second row to exercise the JSON fallback in connect_reference_index
    with ref_idx._conn:
        ref_idx._conn.execute(
            "UPDATE rooftop_reference SET known_units = '{bad_json' WHERE address_key = '777 BEACON ST||BOSTON|MA|02115|USA'"
        )

    ac = AutocompleteEngine()
    loaded = ac.connect_reference_index(ref_idx)
    assert loaded == 1
    assert ac.connect_reference_index(ref_idx) == 0  # duplicate skip
    ref_idx.close()

    # Typo search, secondary unit fallback (including typo in base token and empty intersection break), state filter mismatch
    assert ac.search("777 BEACN ST", typo_tolerance=True)
    assert ac.search("777 BEACON ST STE 999", typo_tolerance=True)
    assert ac.search("777 BEACN ST STE 999", typo_tolerance=True)
    assert ac.search("777 UNKNOWNZXY ST STE 999", typo_tolerance=True) == []
    assert ac.search("777 BEACON ST", state_filter="NY") == []
    assert ac.search("999 UNKNOWNZXY BLVD", typo_tolerance=True) == []

    # Confidence edge cases: landmark without house number, invalid country code length, US- state prefix, field confidence
    std_landmark = StandardizedAddress(
        street1="HARVARD UNIVERSITY",
        street2="",
        city="CAMBRIDGE",
        state="MA",
        postal_code="02138",
        country="USA",
        normalized_address_key="HARVARD UNIVERSITY||CAMBRIDGE|MA|02138|USA",
        address_status="standardized",
        raw_street_address="Harvard University, Cambridge, MA 02138",
        is_us=True,
    )
    c_land = compute_confidence_score(std_landmark)
    assert c_land.composite_score > 0.7

    std_bad_iso = StandardizedAddress(
        street1="10 DOWNING ST",
        street2="",
        city="LONDON",
        state="",
        postal_code="SW1A 2AA",
        country="GB",
        normalized_address_key="10 DOWNING ST||LONDON||SW1A 2AA|GB",
        address_status="standardized",
        raw_street_address="10 Downing St, London SW1A 2AA",
        is_us=False,
    )
    c_bad_iso = compute_confidence_score(std_bad_iso)
    assert c_bad_iso.s_ref_match == 0.7

    std_us_pref = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="BOSTON",
        state="US-MA",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST||BOSTON|MA|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Boston, MA 02101",
        is_us=True,
    )
    c_us_pref = compute_confidence_score(std_us_pref)
    assert c_us_pref.s_cross_field >= 0.8

    std_usa_pref = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="BOSTON",
        state="USA-MA",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST||BOSTON|MA|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Boston, MA 02101",
        is_us=True,
    )
    assert compute_confidence_score(std_usa_pref).s_cross_field >= 0.8

    std_no_st = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="BOSTON",
        state="",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST||BOSTON||02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Boston 02101",
        is_us=True,
    )
    c_no_st = compute_confidence_score(std_no_st)
    assert "WARN_SINGLE_LINE_NO_COMMA" in c_no_st.failure_reason_codes

    std_fc = StandardizedAddress(
        street1="100 MAIN ST",
        street2="STE 200",
        city="BOSTON",
        state="MA",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST|STE 200|BOSTON|MA|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Ste 200, Boston, MA 02011",
        is_us=True,
    )
    std_fc.reference_validation = ReferenceValidation(status="confirmed")
    std_fc.failure_reason_codes = ["WARN_POSTAL_TRANSPOSITION_HEALED"]
    fc = compute_field_confidence(
        std_fc,
        evidence={
            "rules": {
                "state": ["state_from_zip"],
                "postal_code": ["postal_transposition_healed"],
            },
            "reference_status": "confirmed",
        },
    )
    assert fc["postal_code"] < 0.99
    assert fc["state"] < 0.99


def test_offline_index_registry_and_spatial_sqlite(tmp_path: Path):
    idx_db = tmp_path / "offline.sqlite"
    idx = OfflineReferenceIndex(db_path=str(idx_db), seed=True)
    idx.insert_records([])
    idx.insert_street_ranges([])
    with pytest.raises(ValueError):
        idx.insert_street_range("MAIN ST", "02101", "MA", 100, 200, 42.36, -71.05, 42.37, -71.06, parity="X")
    with pytest.raises(ValueError):
        idx.insert_street_ranges(
            [
                {
                    "street_name": "MAIN ST",
                    "postal_code": "02101",
                    "state": "MA",
                    "from_number": 100,
                    "to_number": 200,
                    "start_latitude": 42.36,
                    "start_longitude": -71.05,
                    "end_latitude": 42.37,
                    "end_longitude": -71.06,
                    "parity": "X",
                }
            ]
        )
    idx.insert_street_ranges(
        [
            {
                "street_name": "BEACON ST",
                "postal_code": "02115",
                "state": "MA",
                "from_number": 100,
                "to_number": 100,
                "start_latitude": 42.35,
                "start_longitude": -71.08,
                "end_latitude": 42.35,
                "end_longitude": -71.08,
                "parity": "B",
            }
        ]
    )
    idx.insert_street_range(
        street_name="BOYLSTON ST",
        postal_code="02116",
        state="MA",
        from_number=100,
        to_number=200,
        start_latitude=42.35,
        start_longitude=-71.07,
        end_latitude=42.36,
        end_longitude=-71.08,
        parity="E",
    )
    assert idx.count_ranges() >= 2
    assert idx.interpolate_street_range(100, "BEACON ST", postal_code="", state="MA") is not None
    assert idx.interpolate_street_range(100, "BEACON ST", postal_code="02", state="") is None

    # Street number transposition healing in _resolve_coordinates_uncached (step 4)
    std_transposed_hn = StandardizedAddress(
        street1="102 WALL ST",
        street2="",
        city="NEW YORK",
        state="NY",
        postal_code="10005",
        country="USA",
        normalized_address_key="102 WALL ST||NEW YORK|NY|10005|USA",
        building_key="102 WALL ST||NEW YORK|NY|10005|USA",
        address_status="standardized",
        raw_street_address="102 Wall St, New York, NY 10005",
        is_us=True,
    )
    idx.insert_record(
        address_key="120 WALL ST||NEW YORK|NY|10005|USA",
        building_key="120 WALL ST||NEW YORK|NY|10005|USA",
        street1="120 WALL ST",
        city="NEW YORK",
        state="NY",
        postal_code="10005",
        latitude=40.7050,
        longitude=-74.0050,
    )
    with idx._conn:
        idx._conn.execute(
            "UPDATE rooftop_reference SET known_units = '{bad', metadata_json = '{bad' WHERE address_key = '120 WALL ST||NEW YORK|NY|10005|USA'"
        )
    resolved_healed = idx.resolve_coordinates(std_transposed_hn)
    assert resolved_healed is not None and resolved_healed.street1 == "120 WALL ST"

    # Geocode fallback to centroids & unresolved non-US
    geo_centroid = idx.geocode("999 UNKNOWN ST||BOSTON||02101|USA", fallback_to_centroids=True)
    assert geo_centroid["precision"] in ("POSTAL_CENTROID", "LOCALITY")
    geo_unresolved = idx.geocode("999 UNKNOWN ST||LONDON||SW1A 2AA|GBR", fallback_to_centroids=True)
    assert geo_unresolved["precision"] == "UNRESOLVED"

    # Hot-swap error branches
    with pytest.raises(FileNotFoundError):
        idx.hot_swap(str(tmp_path / "does_not_exist.sqlite"))

    # Registry lookup_corporate_registry & evaluate_corporate_risk
    hub_entry = lookup_corporate_registry(
        street1="1209 N ORANGE ST", city="WILMINGTON", state="DE", postal_code="19801", country="USA"
    )
    assert hub_entry is not None
    priv_dict = {"is_private_residence": True, "is_registered_agent_hub": True}
    score_priv, _flags_priv = evaluate_corporate_risk(priv_dict)
    assert score_priv == 0.40 and priv_dict["is_registered_agent_hub"] is False
    idx.close()

    # SpatialEngine Stage 1/2/3/4 and hot_swap / query_street_segments
    sp_db = tmp_path / "spatial_full.sqlite"
    eng = SpatialEngine(db_path=str(sp_db), seed=True)
    assert eng._query_box(-75.0, 40.0, -73.0, 41.0, limit=0) == []
    assert eng.query_street_segments(-123.0, 37.0, -122.0, 38.0)
    with pytest.raises(ValueError):
        eng.insert_point("BAD||KEY", "BAD||KEY", 999.0, 0.0)
    with pytest.raises(ValueError):
        eng.query_radius(0.0, 95.0)
    # Polar circle branch in query_radius
    eng.query_radius(0.0, 89.9, radius_meters=50000.0)
    # Resolve via dict, parcel_id, Stage 2 interpolation, Stage 3 postal centroid, Stage 4 municipal centroid
    r_parcel = eng.resolve({"parcel_id": "NY-MAN-00100", "country": "USA"})
    assert r_parcel.stage == 1
    r_stage2 = eng.resolve({"street1": "1050 MARKET ST", "city": "SAN FRANCISCO", "state": "CA", "postal_code": "94103", "country": "USA"})
    assert r_stage2.stage == 2 and r_stage2.precision == "RANGE_INTERPOLATED"
    r_stage3 = eng.resolve({"street1": "999 UNKNOWN RD", "city": "BOSTON", "state": "MA", "postal_code": "02101", "country": "USA"})
    assert r_stage3.stage == 3 and r_stage3.precision == "POSTAL_CENTROID"
    r_stage4 = eng.resolve({"street1": "999 UNKNOWN RD", "city": "BOSTON", "state": "MA", "postal_code": "", "country": "USA"})
    assert r_stage4.stage == 4 and r_stage4.precision == "MUNICIPAL_CENTROID"
    with pytest.raises(FileNotFoundError):
        eng.hot_swap(str(tmp_path / "missing_spatial.sqlite"))
    bad_sp = tmp_path / "bad_spatial.sqlite"
    bad_sp.write_text("not a sqlite db", encoding="utf-8")
    with pytest.raises(ValueError):
        eng.hot_swap(str(bad_sp))
    eng.close()


def test_reference_providers_and_validation(tmp_path: Path):
    import gzip
    from entity_standardizer.address.reference.us_zip5 import USZip5Provider

    place = ReferencePlace(
        country="US",
        postal_code="02101",
        place_name="BOSTON",
        admin1="MASSACHUSETTS",
        admin1_code="MA",
        latitude=42.3601,
        longitude=-71.0589,
        provider="dummy",
    )
    assert place.as_dict()["place_name"] == "BOSTON"
    dm = DeliveryMatch(match_code="Y", footnotes=["AA", "BB"], provider="dummy")
    assert dm.as_dict()["match_code"] == "Y"

    zip_tsv = tmp_path / "us_zip5.tsv.gz"
    with gzip.open(zip_tsv, "wt", encoding="utf-8") as gz:
        gz.write("02101\tBoston\tMassachusetts\tMA\tSuffolk\t42.3601\t-71.0589\n")
        gz.write("63101\tSt. Louis\tMissouri\tMO\tSt. Louis City\tbad_lat\tbad_lon\n")

    us_prov = USZip5Provider(data_path=zip_tsv)
    assert us_prov.covers_country("CA") is False
    assert us_prov.lookup_postal("CA", "M5V 2T6") == []
    assert us_prov.lookup_postal("US", "02101")
    assert us_prov.lookup_postal("US", "63101")[0].latitude is None
    assert us_prov.lookup_place("CA", "TORONTO", "ON") == []
    assert us_prov.lookup_place("US", "", "MA") == []
    assert us_prov.lookup_place("US", "BOSTON") == ["02101"]
    assert us_prov.lookup_place("US", "BOSTON", "MA") == ["02101"]
    assert us_prov.lookup_place("US", "ST LOUIS", "MO") == ["63101"]
    us_prov.close()

    with pytest.raises(ValueError):
        CompositeProvider([])

    comp = CompositeProvider([us_prov, get_default_us_zip5_provider()])
    assert comp.covers_country("US") is True
    assert comp.lookup_postal("US", "02101")
    assert comp.lookup_postal("US", "99999") == []
    assert comp.lookup_place("US", "BOSTON", "MA")
    assert comp.lookup_place("US", "NOWHERE_CITY_XYZ", "MA") == []

    # Validate non-US, no postal, unknown postal, confirmed, state_mismatch, and place_mismatch
    intl_std = standardize_address(street1="10 Downing St", city="London", postal_code="SW1A 2AA", country="GBR")
    assert validate_against_reference(intl_std, us_prov).status == "not_checked"

    loc_no_zip = StandardizedAddress(
        street1="",
        street2="",
        city="BOSTON",
        state="MA",
        postal_code="",
        country="USA",
        normalized_address_key="||BOSTON|MA||USA",
        address_status="locality_only",
        raw_street_address="Boston, MA",
        is_us=True,
    )
    assert validate_against_reference(loc_no_zip, us_prov).status == "not_checked"

    confirmed_us = standardize_address(
        street1="100 Main St",
        city="Boston",
        state="MA",
        postal_code="02101",
        reference_provider=us_prov,
        use_cache=False,
    )
    assert confirmed_us.reference_validation is not None
    assert confirmed_us.reference_validation.is_confirmed is True

    no_city_us = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="",
        state="MA",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST|||MA|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, MA 02101",
        is_us=True,
    )
    assert validate_against_reference(no_city_us, us_prov).status == "confirmed"

    state_mismatch_us = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="BOSTON",
        state="NY",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST||BOSTON|NY|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Boston, NY 02101",
        is_us=True,
    )
    state_mismatch_us.confidence_score = 0.92
    state_mismatch_us.routing_tier = "AUTO_ACCEPT"
    apply_reference_validation(state_mismatch_us, us_prov)
    assert state_mismatch_us.reference_validation.status == "state_mismatch"

    mismatch_us = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="MIAMI",
        state="MA",
        postal_code="02101",
        country="USA",
        normalized_address_key="100 MAIN ST||MIAMI|MA|02101|USA",
        address_status="standardized",
        raw_street_address="100 Main St, Miami, MA 02101",
        is_us=True,
    )
    mismatch_us.confidence_score = 0.92
    mismatch_us.routing_tier = "AUTO_ACCEPT"
    apply_reference_validation(mismatch_us, us_prov)
    assert mismatch_us.reference_validation.status == "place_mismatch"


def test_international_grammars_and_postal_coverage():
    # postal.py branches
    assert validate_postal_code("12345", "ZZZ") is False
    assert validate_postal_code("12345", "ZZZ", return_details=True).is_valid is False
    assert validate_postal_code("D1A 0A1", "CAN") is False
    assert validate_postal_code("K1A 0D1", "CAN") is False
    assert validate_postal_code("K1A 0A12", "CAN") is False

    for iso in ("GBR", "NLD", "IRL", "JPN", "BRA", "POL", "SGP", "AUS", "VGB", "CYM", "USA", "FRA"):
        assert _extract_for_country("NO POSTAL HERE", CountryRegistry.get(iso)) is None

    ext_no_hint = extract_postal_code("10 Downing St, London SW1A 2AA")
    assert ext_no_hint == "SW1A 2AA"

    # countries.py branches
    assert CountryRegistry.get("") is None
    assert CountryRegistry.has_postal_codes("HKG") is False
    assert CountryRegistry.has_postal_codes("UNKNOWN_COUNTRY") is True
    assert len(CountryRegistry.all_countries()) >= 249
    assert "USA" in CountryRegistry.all_iso3()
    for country_info in (
        CountryRegistry.get("JPN"),
        CountryRegistry.get("DEU"),
        CountryRegistry.get("USA"),
        CountryRegistry.get("HKG"),
    ):
        assert country_info is not None
        assert country_info.house_number_position in ("before_street", "after_street", "cjk_hierarchical")
        assert country_info.postal_position in ("before_city", "after_city", "leading_top", "none")
        assert isinstance(country_info.uses_administrative_state, bool)
        assert country_info.grammar_family

    # base.py branches
    p_base = ParsedAddressComponents(street_number="10", street_name="", building_name="")
    assert p_base.format_street1() == "10"
    p_bldg = ParsedAddressComponents(street_name="TOWER A", building_name="TOWER A")
    assert p_bldg.format_street1() == "TOWER A"
    p_sec = ParsedAddressComponents(unit_type="FL", unit_number="3")
    assert p_sec.format_street2() == "FL 3"
    p_sec_type_only = ParsedAddressComponents(unit_type="BSMT", unit_number="")
    assert p_sec_type_only.format_street2() == "BSMT"
    p_sec_num_only = ParsedAddressComponents(unit_type="", unit_number="#20-61")
    assert p_sec_num_only.format_street2() == "#20-61"

    assert split_single_line_locality("NoCommaHere", "FRA") is None
    assert split_single_line_locality("Rue de Rivoli, Paris", "FRA") is None

    ug = UniversalInternationalGrammar()
    res_fra = ug.standardize(street1="10 Rue de la Paix", city="Paris", state="", postal_code="75002", country="FRA")
    assert "RUE DE LA PAIX" in res_fra.format_street1()
    res_deu_ug = ug.standardize(street1="Friedrichstrasse 10", city="Berlin", state="", postal_code="10117", country="DEU")
    assert "FRIEDRICHSTRASSE 10" in res_deu_ug.format_street1()

    # cjk.py branches
    assert strip_cjk_trailing_country("東京都千代田区1-1-1 Japan") == ("東京都千代田区1-1-1", "JPN")
    assert separate_house_number("北1条西17丁目16", "JPN") == "北1条西17丁目 16"
    assert separate_house_number("復興北路231巷34", "TWN") == "復興北路231巷 34"
    assert separate_house_number("테헤란로152", "KOR") == "테헤란로 152"
    assert split_jp_tokens(["福岡県", "福岡市", "中央区", "今泉1-18-25"]) is not None

    jg = CountryGrammarRegistry.get("JPN")
    jp_res = jg.standardize(
        street1="東京都千代田区霞が関2-1-3 100-8924",
        city="",
        state="",
        postal_code="",
        country="JPN",
    )
    assert jp_res.state in ("TOKYO", "東京都")
    assert jp_res.postal_code == "100-8924"

    cg = CountryGrammarRegistry.get("CHN")
    cn_res = cg.standardize(
        street1="北京市朝阳区建国路88号 500室",
        city="",
        state="",
        postal_code="100022",
        country="CHN",
    )
    assert cn_res.state in ("BEIJING", "北京市")
    assert "500" in cn_res.format_street2()

    kr_res = CountryGrammarRegistry.get("KOR").standardize(
        street1="152 Teheran-ro, Gangnam-gu",
        city="Seoul",
        state="",
        postal_code="06236",
        country="KOR",
    )
    assert kr_res.city == "SEOUL"

    # uk.py branches
    uk_comp1 = UKParsedAddressComponents(street_name="10", unit_type="UNIT", unit_number="A", building_name="THE HUB")
    assert uk_comp1.format_street1() == "10 UNIT A"
    assert uk_comp1.format_street2() == "THE HUB"
    uk_comp2 = UKParsedAddressComponents(street_number="10", street_name="", unit_type="UNIT", unit_number="B")
    assert uk_comp2.format_street1() == "10 UNIT B"

    ukg = CountryGrammarRegistry.get("GBR")
    uk_res = ukg.standardize(
        street1="10 High Street, Reading, RG1 1AA, England",
        city="",
        state="",
        postal_code="",
        country="GBR",
    )
    assert uk_res.postal_code == "RG1 1AA"
    assert uk_res.city == "READING"
    assert uk_res.format_street1() == "10 HIGH ST"

    uk_inferred = ukg.standardize(
        street1="93, Queen Street, Leeds, LS1 2AJ",
        city="",
        state="",
        postal_code="",
        country="GBR",
    )
    assert uk_inferred.city == "LEEDS"
    assert uk_inferred.postal_code == "LS1 2AJ"

    # hong_kong.py, mena_africa.py, germanic.py, eastern_europe.py, offshore.py, southeast_asia.py, australia.py, latin_america.py, singapore.py, canada.py, ireland.py, romance.py, upu.py
    hk_res = CountryGrammarRegistry.get("HKG").standardize(
        street1="15/F, International Finance Centre, 8 Finance Street, Central",
        city="",
        state="NT",
        postal_code="999077",
        country="HKG",
    )
    assert hk_res.postal_code == ""
    assert hk_res.city == "CENTRAL"
    assert hk_res.state == ""

    mena_res = CountryGrammarRegistry.get("ARE").standardize(
        street1="P.O. Box 12345, Sheikh Zayed Road",
        city="Dubai",
        state="DU",
        postal_code="00000",
        country="ARE",
    )
    assert mena_res.state == "DU"
    assert "PO BOX 12345" in mena_res.format_street2()

    za_res = CountryGrammarRegistry.get("ZAF").standardize(
        street1="100 Main Road, Sandton",
        city="Johannesburg",
        state="GP",
        postal_code="2196",
        country="ZAF",
    )
    assert za_res.state == "GP"

    de_res = standardize_address(
        street1="Friedrichstr. 100, Top 5, 10117 Berlin",
        city="",
        state="Berlin",
        postal_code="",
        country="DEU",
        use_cache=False,
    )
    assert de_res.postal_code == "10117"
    assert "100" in de_res.street1

    pl_res = standardize_address(
        street1="ul. Marszalkowska 10/12 m. 5, 00-590 Warszawa",
        city="",
        state="",
        postal_code="",
        country="POL",
        use_cache=False,
    )
    assert pl_res.postal_code == "00-590"
    assert pl_res.street2 == "M. 5"

    ky_res = standardize_address(
        street1="Ugland House, South Church Street, P.O. Box 309, George Town, Grand Cayman KY1-1104",
        city="",
        state="",
        postal_code="",
        country="CYM",
        use_cache=False,
    )
    assert ky_res.postal_code == "KY1-1104"

    sg_res = standardize_address(
        street1="1 Raffles Place #20-61 One Raffles Place",
        city="",
        state="",
        postal_code="Singapore 048616",
        country="SGP",
        use_cache=False,
    )
    assert sg_res.postal_code == "048616"
    assert "#20-61" in sg_res.street2

    sea_res = standardize_address(
        street1="Jalan Ampang 100, 50450 Kuala Lumpur",
        city="",
        state="W.P. Kuala Lumpur",
        postal_code="",
        country="MYS",
        use_cache=False,
    )
    assert sea_res.postal_code == "50450"

    au_res = standardize_address(
        street1="Level 5, 100 George St, Sydney NSW 2000",
        city="",
        state="",
        postal_code="",
        country="AUS",
        use_cache=False,
    )
    assert au_res.state == "NSW"
    assert au_res.postal_code == "2000"

    br_res = standardize_address(
        street1="Av. Paulista, 1000, Conj. 101, Bela Vista, Sao Paulo - SP",
        city="",
        state="",
        postal_code="01310100",
        country="BRA",
        use_cache=False,
    )
    assert br_res.postal_code == "01310-100"
    assert br_res.state == "SP"

    ca_res = standardize_address(
        street1="200-100 Queen St W, Toronto ON M5H 2N2",
        city="",
        state="",
        postal_code="",
        country="CAN",
        use_cache=False,
    )
    assert ca_res.postal_code == "M5H 2N2"
    assert "100 QUEEN ST W" in ca_res.street1

    ie_res = standardize_address(
        street1="10 St Stephen's Green, Dublin 2",
        city="",
        state="Co. Dublin",
        postal_code="D02 XY45",
        country="IRL",
        use_cache=False,
    )
    assert ie_res.postal_code == "D02 XY45"

    rom_res = standardize_address(
        street1="10 Bis Rue de la Paix, Escalier B, 3eme Etage, 75002 Paris",
        city="",
        state="Ile-de-France",
        postal_code="",
        country="FRA",
        use_cache=False,
    )
    assert rom_res.postal_code == "75002"

    # upu.py branches for DEU, JPN, GBR, CAN, SGP, HKG
    for c_iso, st1, city, state, post in [
        ("DEU", "FRIEDRICHSTRASSE 100", "BERLIN", "BE", "10117"),
        ("JPN", "2-1-3 KASUMIGASEKI", "CHIYODA-KU", "TOKYO", "100-8924"),
        ("GBR", "10 DOWNING ST", "LONDON", "", "SW1A 2AA"),
        ("CAN", "100 QUEEN ST W", "TORONTO", "ON", "M5H 2N2"),
        ("SGP", "1 RAFFLES PL", "SINGAPORE", "", "048616"),
        ("HKG", "8 FINANCE ST", "CENTRAL", "HONG KONG ISLAND", ""),
    ]:
        s_addr = StandardizedAddress(
            street1=st1,
            street2="STE 10",
            city=city,
            state=state,
            postal_code=post,
            country=c_iso,
            normalized_address_key=None,
            address_status="standardized",
            raw_street_address=st1,
            is_us=False,
            dependent_locality="SUBLOC",
            building_name="TOWER 1",
        )
        rendered = format_upu_address(s_addr, recipient="RECIPIENT", include_country_name=True)
        assert "RECIPIENT" in rendered

    # Additional targeted international grammar branches (countries, base, cjk, uk, germanic, mena, hk, ee, offshore, sea, au)
    assert CountryRegistry.get("U.S.A.") is not None
    assert CountryRegistry.detect_country("100 Bahnhofstr, 8001 Zurich") is not None
    assert CountryRegistry.detect_country("100 Main Rd, 8001 New Zealand") is not None
    assert CountryRegistry.detect_country("100 Main Rd, 10117 Germany") is not None
    assert CountryRegistry.detect_country("100 Rd, Paris St") is None
    assert CountryGrammarRegistry.detect_country(country_raw="ZZZ") == "ZZZ"
    assert CountryGrammarRegistry.detect_country(state_raw="MA") == "USA"
    assert CountryGrammarRegistry.detect_country(city_raw="Zürich") == "CHE"

    # CJK additional branches
    assert CountryGrammarRegistry.get("JPN").standardize(street1="東京都 港区 六本木 1-2-3", country="JPN").city == "港区"
    assert CountryGrammarRegistry.get("CHN").standardize(
        street1="北京市 朝阳区 建国路 88号 国贸大厦500室", country="CHN"
    ).building_name == "国贸大厦"
    assert CountryGrammarRegistry.get("JPN").standardize(
        street1="東京都新宿区 新宿ゴールデン街 G2通り1丁目1-10 森ビル501号室 160-0021", country="JPN"
    ).postal_code == "160-0021"
    assert CountryGrammarRegistry.get("KOR").standardize(
        street1="주흥길 78", state="서울특별시", city="", country="KOR"
    ).city == "서울특별시"
    assert CountryGrammarRegistry.get("CHN").standardize(
        street1="Flat 4 88 Jianguo Road", city="Beijing", country="CHN"
    ).unit_type == "APT"

    # UK additional branches
    uk_g = CountryGrammarRegistry.get("GBR")
    assert uk_g.standardize(street1="10 North Western Arcade", city="Birmingham", postal_code="B2 5BG", country="GBR")
    assert uk_g.standardize(street1="10 High Street North Nowhereville RG1 1AA", country="GBR")
    assert uk_g.standardize(street1="10 High Street RG1 1AA", country="GBR")
    assert uk_g.standardize(street1="PO Box 309 Suite 100", city="London", postal_code="SW1A 1AA", country="GBR")
    assert uk_g.standardize(street1="10 High Street", street2="Flat 4B", city="London", postal_code="SW1A 1AA", country="GBR")
    assert uk_g.standardize(street1="Flat 4 10 High Street", city="London", postal_code="SW1A 1AA", country="GBR")
    assert uk_g.standardize(street1="2nd Floor", street2="10 High Street", city="London", postal_code="SW1A 1AA", country="GBR")
    assert uk_g.standardize(street1="PO Box 500", city="London", postal_code="SW1A 1AA", country="GBR")
    assert uk_g.standardize(street1="Suite 200, 10 High Street", city="London", postal_code="SW1A 1AA", country="GBR")

    # Germanic, MENA, HK, Eastern Europe, Offshore, Southeast Asia, Australia additional branches
    assert CountryGrammarRegistry.get("DNK").standardize(
        street1="Østergade 45, 2. tv.", street2="Suite 5", city="", country="DNK"
    )
    assert CountryGrammarRegistry.get("DEU").standardize(street1="Friedrichstr. 5-7, Berlin", city="", country="DEU")
    assert CountryGrammarRegistry.get("FIN").standardize(
        street1="Mannerheimintie 12 B 25", city="Helsinki", postal_code="00100", country="FIN"
    )
    assert CountryGrammarRegistry.get("NGA").normalize_postal_code("100001") == "100001"
    assert CountryGrammarRegistry.get("NGA").normalize_postal_code("ABC") == "ABC"
    assert CountryGrammarRegistry.get("EGY").standardize(street1="15 Tahrir St", city="Cairo", country="EGY")
    assert CountryGrammarRegistry.get("NGA").standardize(
        street1="Plot 5, Victoria Island, Lagos 100001", city="", country="NGA"
    )
    assert CountryGrammarRegistry.get("KEN").standardize(
        street1="100 Waiyaki Way, Nairobi 00100, Kenya", city="", country="KEN"
    )
    assert CountryGrammarRegistry.get("HKG").standardize(
        street1="", street2="", raw_street_address="Suite 10, Bank of China Tower", city="Sha Tin", state="Central", country="HKG"
    )
    assert CountryGrammarRegistry.get("HKG").standardize(
        street1="Victoria Peak", city="New Territories", state="Wan Chai", country="HKG"
    )
    assert CountryGrammarRegistry.get("RUS").standardize(
        street1="125009 Москва ул. Тверская 10", city="", state="Moskva", country="RUS"
    )
    assert CountryGrammarRegistry.get("POL").standardize(
        street1="ul. Marszalkowska 10", city="00-590 Warszawa", state="Mazowieckie", country="POL"
    )
    assert CountryGrammarRegistry.get("CYM").standardize(
        street1="100 South Church St, Suite 200", city="George Town", postal_code="KY1-1104", country="CYM"
    )
    assert CountryGrammarRegistry.get("CYM").standardize(
        street1="100 Main St PO Box 309", city="George Town", postal_code="KY1-1104", country="CYM"
    )
    assert CountryGrammarRegistry.get("IDN").standardize(
        street1="Jalan KH Wahid Hasyim No. 189, Tanah Abang, Central Jakarta", street2="Suite 500", city="", postal_code="10250", country="IDN"
    )
    assert CountryGrammarRegistry.get("PHL").standardize(
        street1="7431 Yakal Street, Makati", city="", postal_code="1203", country="PHL"
    )
    assert CountryGrammarRegistry.get("PHL").standardize(
        street1="7431 Yakal Street,", city="", postal_code="1203", country="PHL"
    )
    assert CountryGrammarRegistry.get("AUS").standardize(
        street1="Suite 5/100 George St, Sydney, NSW", city="", postal_code="2000", country="AUS"
    )
    assert CountryGrammarRegistry.get("AUS").standardize(
        street1="Apt 5/100 George St", city="Sydney", state="NSW", postal_code="2000", country="AUS"
    )
    assert CountryGrammarRegistry.get("AUS").standardize(
        street1="100 George St Level 2", city="Sydney", state="NSW", postal_code="2000", country="AUS"
    )

    # Singapore, UPU ParsedAddressComponents, and base split_commaless_locality branches
    sg_g = CountryGrammarRegistry.get("SGP")
    assert sg_g.normalize_postal_code("SG-048616-X") == "048616"
    assert sg_g.normalize_postal_code("123") == ""
    assert sg_g.standardize(
        street1="", street2="", raw_street_address="RAFFLES CITY TOWER, RAFFLES BLVD NORTH", country="SGP"
    )
    from entity_standardizer.address.international.base import split_commaless_locality

    assert split_commaless_locality("122 شارع 26 يوليو Cairo 11211", "EGY") is not None
    assert split_commaless_locality("100 Av Libertador 20 Caracas 1010", "VEN") is not None
    assert split_commaless_locality("1054 Budapest Zoltán utca ABC", "HUN") is None
    assert format_upu_address(
        ParsedAddressComponents(
            street_number="10",
            street_name="FRIEDRICHSTRASSE",
            unit_type="STE",
            unit_number="5",
            city="BERLIN",
            state="",
            postal_code="10117",
            country_iso3="DEU",
        )
    )
    assert format_upu_address(
        ParsedAddressComponents(
            street_number="10",
            street_name="SHEIKH ZAYED RD",
            unit_type="STE",
            unit_number="5",
            city="DUBAI",
            state="",
            postal_code="",
            country_iso3="ARE",
        )
    )
    assert format_upu_address(
        ParsedAddressComponents(
            street_number="10",
            street_name="SHEIKH ZAYED RD",
            unit_type="STE",
            unit_number="5",
            city="",
            state="DUBAI",
            postal_code="",
            country_iso3="ARE",
        )
    )


def test_transliterate_calibration_explain_cache_and_audit(tmp_path: Path):
    # transliterate.py & normalization.py
    assert transliterate("Москва, ул. Тверская 1")
    assert _builtin("Москва ΑΒΓ אבג ابت", "passthrough")
    assert transliterate("", script="latin") == ""
    with pytest.raises(ValueError):
        transliterate("test", errors="bad")
    with pytest.raises(ValueError):
        transliterate("test", script="martian")
    assert fold_to_ascii_key("Straße 10, Zürich") == "STRASSE 10, ZURICH"
    assert normalize_country("United Kingdom") == "GBR"
    assert normalize_country_code("", "", "SW1A 2AA", raw_street="10 Downing St", city_raw="London") == "GBR"

    # calibration.py
    pairs = [(0.2, False), (0.2, True), (0.8, True), (0.95, True)]
    bins = reliability_bins(pairs, n_bins=5)
    assert bins and bins[0].as_dict()["count"] >= 1
    assert expected_calibration_error(pairs) >= 0.0
    assert brier_score(pairs) >= 0.0
    cal = fit_isotonic(pairs)
    assert cal.calibrate(0.0) == cal.ys[0]
    assert cal.calibrate(1.0) == cal.ys[-1]
    assert 0.0 <= cal.calibrate(0.5) <= 1.0
    cal_file = tmp_path / "calibrator.json"
    cal.save(cal_file)
    cal2 = Calibrator.load(cal_file)
    with pytest.raises(ValueError):
        Calibrator.from_dict({"version": 999})
    with pytest.raises(ValueError):
        Calibrator([], [])
    with pytest.raises(ValueError):
        Calibrator([0.5, 0.4], [0.5, 0.6])
    with pytest.raises(ValueError):
        Calibrator([0.4, 0.5], [0.6, 0.5])
    with pytest.raises(ValueError):
        Calibrator([-0.1, 0.5], [0.5, 0.6])

    # explain.py with calibrator & alternatives
    exp_res = standardize_address(
        street1="100 N Main St",
        city="Boston",
        state="MA",
        postal_code="02101",
        explain=True,
        alternatives=3,
        calibrator=cal2,
        use_cache=False,
    )
    assert exp_res.explanation is not None
    assert exp_res.field_confidence is not None
    assert exp_res.alternatives is not None

    # cache.py SQLiteCache
    cache_db = tmp_path / "cache.sqlite"
    sc = SQLiteCache(db_path=str(cache_db), max_entries=5)
    sc.set("k1", exp_res)
    assert sc.get("k1") is not None
    assert sc.size() == 1
    sc.clear()
    assert sc.size() == 0
    sc.close()

    # audit.py StewardshipAuditLedger export / history / clear / close
    ledger = StewardshipAuditLedger()
    std_fail = standardize_address(street1="", city="", state="", postal_code="", use_cache=False)
    conf_fail = compute_confidence_score(std_fail)
    rec = ledger.record_standardized_address(std_fail, conf_fail, raw_input={"street1": ""})
    ledger.ensure_recorded(rec)
    assert ledger.export(format="json")
    assert ledger.export(format="sql")
    assert ledger.export(format="dict")
    assert ledger.history(rec.audit_id) == []
    ledger.clear()
    ledger.close()

