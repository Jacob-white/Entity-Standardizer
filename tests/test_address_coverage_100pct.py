"""Deterministic unit tests achieving 100% statement coverage across entity_standardizer/address/."""

from __future__ import annotations

import builtins
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from entity_standardizer.address import (
    _native_dispatch,
    _patterns,
    audit as audit_mod,
    batch as batch_mod,
    cache as cache_mod,
    confidence as confidence_mod,
    explain as explain_mod,
    geocoder as geocoder_mod,
    normalization as normalization_mod,
    offline_index as offline_index_mod,
    phonetics as phonetics_mod,
    registry as registry_mod,
    standardizer as standardizer_mod,
    us_street_parser,
)
from entity_standardizer.address.international import (
    australia as australia_mod,
    base as intl_base_mod,
    canada as canada_mod,
    cjk as cjk_mod,
    commaless as commaless_mod,
    countries as countries_mod,
    eastern_europe as ee_mod,
    eurasia as eurasia_mod,
    germanic as germanic_mod,
    hong_kong as hk_mod,
    ireland as ireland_mod,
    latin_america as latam_mod,
    mena_africa as mena_mod,
    offshore as offshore_mod,
    postal as postal_mod,
    romance as romance_mod,
    singapore as sg_mod,
    southeast_asia as sea_mod,
    uk as uk_mod,
)
from entity_standardizer.address.models import StandardizedAddress
from entity_standardizer.address.reference import geonames as geonames_mod, us_zip5 as us_zip5_mod
from entity_standardizer.address.spatial import engine as spatial_engine_mod, ingestion as spatial_ingestion_mod


class _PragmaRaisingConn:
    """Wrapper around sqlite3.Connection that raises on specified SQL prefixes."""

    def __init__(self, real_conn: sqlite3.Connection, fail_prefixes: tuple[str, ...]) -> None:
        self._real = real_conn
        self._fail_prefixes = fail_prefixes

    def __enter__(self) -> _PragmaRaisingConn:
        self._real.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return self._real.__exit__(exc_type, exc_val, exc_tb)

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        stripped = sql.strip().upper()
        if any(stripped.startswith(p) for p in self._fail_prefixes):
            raise sqlite3.Error("simulated pragma/index failure")
        return self._real.execute(sql, *args, **kwargs)


def test_native_dispatch_fatal_and_fallback_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    class _GoodModule:
        @staticmethod
        def compute_soundex(token: str) -> str:
            return "S530"

        @staticmethod
        def get_capabilities() -> dict[str, Any]:
            return {"engine": "Rust_PyO3", "native_functions": ["compute_soundex"]}

    monkeypatch.delenv("ENTITY_STANDARDIZER_FORCE_PURE", raising=False)
    monkeypatch.delenv("ADDRESS_STANDARDIZER_FORCE_PURE", raising=False)
    monkeypatch.setitem(sys.modules, "_entity_standardizer_rs", _GoodModule)  # type: ignore[arg-type]
    _native_dispatch._init_native()
    assert _native_dispatch.is_using_native() is True
    assert _native_dispatch.try_native("compute_soundex", "SMITH") == (True, "S530")
    assert _native_dispatch._native_function_names() == ["compute_soundex"]
    assert _native_dispatch.get_engine_info()["native_functions"] == ["compute_soundex"]
    assert _native_dispatch.get_capabilities()["engine"] == "Rust_PyO3"

    real_import = builtins.__import__

    def _raise_kb(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "_entity_standardizer_rs":
            raise KeyboardInterrupt("simulated interrupt")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise_kb)
    with pytest.raises(KeyboardInterrupt):
        _native_dispatch._init_native()
    monkeypatch.setattr(builtins, "__import__", real_import)

    monkeypatch.setattr(_native_dispatch, "_NATIVE_MODULE", None)
    assert _native_dispatch._native_function_names() == []

    class _FatalModule:
        @staticmethod
        def get_capabilities() -> dict[str, Any]:
            raise KeyboardInterrupt("capability interrupt")

    monkeypatch.setattr(_native_dispatch, "_NATIVE_MODULE", _FatalModule)
    with pytest.raises(KeyboardInterrupt):
        _native_dispatch._native_function_names()

    monkeypatch.delitem(sys.modules, "_entity_standardizer_rs", raising=False)
    _native_dispatch._init_native()


def test_patterns_two_word_alpha_and_plural_intersection() -> None:
    assert _patterns.clean_repetitive_cycles("WALLA WALLA") == "WALLA WALLA"
    assert _patterns.parse_intersection_address("Main St and Fourth Streets") == "MAIN ST & 4TH ST"


def test_audit_ledger_edge_branches() -> None:
    rec = audit_mod.StewardshipAuditRecord(failure_reason_codes=[])
    sql = rec.to_sql_insert()
    assert "ARRAY[]::text[]" in sql

    ledger = audit_mod.StewardshipAuditLedger(":memory:")
    real_conn = ledger._conn
    try:
        ledger._conn = _PragmaRaisingConn(real_conn, ("PRAGMA",))  # type: ignore[assignment]
        ledger._init_db()
    finally:
        ledger._conn = real_conn

    std = standardizer_mod.standardize_address(
        street1="100 Main St", city="New York", state="NY", postal_code="10001"
    )
    conf = confidence_mod.ConfidenceResult(
        composite_score=0.95,
        routing_tier=confidence_mod.RoutingTier.AUTO_PASS,
        s_parse=0.95,
        s_ref_match=1.0,
        s_geo=0.95,
        s_cross_field=1.0,
        failure_reason_codes=[confidence_mod.WARN_TYPO_HEALED],
    )
    logged = ledger.record_standardized_address(std, conf)
    assert logged.action_type == audit_mod.ActionType.AUTO_HEAL
    assert logged.review_status == audit_mod.ReviewStatus.APPROVED


def test_batch_mapping_and_cleanup_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cols = batch_mod.resolve_column_mappings({"addr_col": "address", "zip": "my_zip_col"})
    assert cols[0] == "addr_col"
    assert cols[4] == "my_zip_col"

    # CSV stream with spatial_db to exercise spatial engine cleanup in finally block
    csv_in = tmp_path / "in.csv"
    csv_out = tmp_path / "out.csv"
    spatial_db = tmp_path / "spatial.db"
    csv_in.write_text("street1,city,state,postal_code\n100 Main St,New York,NY,10001\n", encoding="utf-8")
    count = batch_mod.stream_standardize_csv(
        str(csv_in),
        str(csv_out),
        enable_geocoding=True,
        spatial_db=str(spatial_db),
    )
    assert count == 1

    # CSV stream exception after tmp_output is created to exercise tmp_output cleanup
    csv_out_err = tmp_path / "out_err.csv"

    def _boom_replace(src: str, dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(batch_mod.os, "replace", _boom_replace)
    with pytest.raises(OSError, match="replace failed"):
        batch_mod.stream_standardize_csv(str(csv_in), str(csv_out_err))
    assert not Path(f"{csv_out_err}.tmp").exists()

    # JSON array stream exception after tmp_output is written to exercise tmp_output cleanup
    json_in = tmp_path / "in.json"
    json_out_err = tmp_path / "out_err.json"
    json_in.write_text('[{"street1": "100 Main St", "city": "New York", "state": "NY", "postal_code": "10001"}]', encoding="utf-8")
    with pytest.raises(OSError, match="replace failed"):
        batch_mod.stream_standardize_json(str(json_in), str(json_out_err))
    assert not Path(f"{json_out_err}.tmp").exists()


def test_cache_init_db_exception_handlers() -> None:
    cache = cache_mod.SQLiteCache(":memory:")
    real_conn = cache._conn
    try:
        cache._conn = _PragmaRaisingConn(real_conn, ("PRAGMA", "CREATE INDEX"))  # type: ignore[assignment]
        cache._init_db()
    finally:
        cache._conn = real_conn
        cache.close()


def test_confidence_landmark_campus_and_iso_state() -> None:
    engine = confidence_mod.ConfidenceScorer()
    std_campus = standardizer_mod.standardize_address(
        street1="Blue Bell Executive Campus",
        city="Blue Bell",
        state="PA",
        postal_code="19422",
    )
    res_high = engine.score(std_campus, raw_input={"state": "US-PA"})
    assert confidence_mod.WARN_LANDMARK_CAMPUS_PREMISE in res_high.failure_reason_codes
    assert res_high.routing_tier == confidence_mod.RoutingTier.FUZZY_REVIEW

    std_campus_low = StandardizedAddress(
        street1="EXECUTIVE CAMPUS",
        street2="",
        city="99",
        state="",
        postal_code="",
        country="USA",
        normalized_address_key="EXECUTIVE CAMPUS|||||USA",
        address_status="standardized",
        raw_street_address="Executive Campus",
        is_us=True,
    )
    res_low = engine.score(std_campus_low)
    assert res_low.routing_tier == confidence_mod.RoutingTier.MANUAL_STEWARDSHIP


def test_explain_and_geocoder_branches() -> None:
    assert explain_mod.current_recorder() is None

    res = standardizer_mod.standardize_address(
        street1="100 Main St",
        street2="Suite One",
        city="NEW YORK",
        state="ny",
        postal_code="10001",
        explain=True,
    )
    rules = {step["rule"] for step in res.explanation}
    assert "unit_designator_abbreviation" in rules
    assert "number_words_to_digits" in rules
    assert "case_normalized" in rules

    intl_std = standardizer_mod.standardize_address(
        street1="10 Downing Street", city="London", postal_code="SW1A 2AA", country="GBR"
    )
    geo = geocoder_mod.OfflineGeocoder().geocode(intl_std, fallback_to_centroids=True)
    assert isinstance(geo, dict)


def test_international_australia_canada_cjk_commaless() -> None:
    au = australia_mod.AustraliaGrammar()
    p_ste = au.standardize(street1="STE5/100 George St", city="Sydney", state="NSW", postal_code="2000")
    assert p_ste.unit_type == "STE" and p_ste.unit_number == "5"

    p_apt = au.standardize(street1="APT5/100 George St", city="Sydney", state="NSW", postal_code="2000")
    assert p_apt.unit_type == "APT" and p_apt.unit_number == "5"

    p_lvl = au.standardize(street1="100 George St L15", city="Sydney", state="NSW", postal_code="2000")
    assert p_lvl.unit_type == "LEVEL" and p_lvl.unit_number == "15"

    p_st_end = au.standardize(street1="100 George St NSW", city="Sydney")
    assert p_st_end.state == "NSW"

    p_no_post = au.standardize(street1="100 George Street Sydney NSW")
    assert p_no_post.state == "NSW"

    p_digits_only = au.standardize(street1="100 200 2000")
    assert p_digits_only.postal_code == "2000"

    assert commaless_mod.split_commaless_region_postal_city(
        "100 George St", lambda _: False, None, set(), _patterns.RE_TERMINAL_COUNTRY
    ) is None

    can = canada_mod.CanadaGrammar()
    p_can_box = can.standardize(
        street1="100 Queen St, P.O. Box 45", city="Toronto", state="ON", postal_code="M5H 2N2"
    )
    assert p_can_box.unit_type == "PO BOX" and p_can_box.unit_number == "45"

    p_can_dir = can.standardize(street1="100 King Street West Oakville ON L6J 1A1")
    assert p_can_dir.city == "OAKVILLE"

    assert cjk_mod._search_cjk_room("") is None
    m_cn_rm = cjk_mod._search_cjk_room("3层")
    assert m_cn_rm is not None and m_cn_rm.group(1) == "3层"

    cjk = cjk_mod.CJKGrammar()
    p_jp_tokens = cjk.standardize(street1="福岡市 中央区 今泉1-18-25", country="JPN")
    assert p_jp_tokens.city == "福岡市" and p_jp_tokens.dependent_locality == "中央区"

    p_cn_tokens = cjk.standardize(street1="广东省 深圳市 南山区 科技南十二路18号", country="CHN")
    assert p_cn_tokens.dependent_locality == "南山区"

    p_jp_nomuni = cjk.standardize(street1="東京都1-2-3", country="JPN")
    assert p_jp_nomuni.state == "東京都"

    p_cn_nomuni = cjk.standardize(street1="北京市长安街1号", country="CHN")
    assert p_cn_nomuni.state == "北京市"

    p_kr_road = cjk.standardize(street1="세종대로 110", country="KOR")
    assert "세종대로" in (p_kr_road.street_name or "")

    p_tw_tail = cjk.standardize(street1="台北市信義區信義路五段7號 110", country="TWN")
    assert p_tw_tail.postal_code == "110"


def test_international_base_and_countries() -> None:
    assert intl_base_mod.split_commaless_locality("122 شارع 26 يوليو Zamalek 11211", "EGY") == (
        "122 شارع 26 يوليو",
        "Zamalek",
        "11211",
    )
    assert intl_base_mod.split_commaless_locality("10 Soi Buakhao Sattahip 20180", "THA") == (
        "10 Soi Buakhao",
        "Sattahip",
        "20180",
    )
    assert intl_base_mod.split_commaless_locality("10 ถนนสุขุมวิท สัตหีบ 20180", "THA") == (
        "10 ถนนสุขุมวิท",
        "สัตหีบ",
        "20180",
    )

    with pytest.raises(NotImplementedError):
        intl_base_mod.CountryGrammar.parse(None, [], {})  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        intl_base_mod.CountryGrammar.normalize_postal_code(None, "")  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        intl_base_mod.CountryGrammar.extract_premise_and_thoroughfare(None, "")  # type: ignore[arg-type]

    saved_reg = dict(intl_base_mod.CountryGrammarRegistry._registry)
    try:
        intl_base_mod.CountryGrammarRegistry.clear()
        assert intl_base_mod.CountryGrammarRegistry.supported_countries() == set()
    finally:
        intl_base_mod.CountryGrammarRegistry._registry.update(saved_reg)

    assert intl_base_mod.CountryGrammarRegistry.detect_country(city_raw="París") == "FRA"
    assert intl_base_mod.CountryGrammarRegistry.detect_country(raw_street="10 Rue de Rivoli, París") == "FRA"

    info_punct = countries_mod.CountryRegistry.get("CAN-ADA")
    assert info_punct is not None and info_punct.alpha3 == "CAN"
    info_accent = countries_mod.CountryRegistry.get("Frànce")
    assert info_accent is not None and info_accent.alpha3 == "FRA"


def test_international_regional_grammars_and_postal(monkeypatch: pytest.MonkeyPatch) -> None:
    ee = ee_mod.EasternEuropeGrammar()
    p_hu = ee.standardize(street1="Zoltán utca, 1054 Budapest", country="HUN")
    assert p_hu.city == "BUDAPEST"
    assert ee.normalize_postal_code("MD-2001") == "MD-2001"

    eur = eurasia_mod.EurasiaGrammar()
    p_tr = eur.standardize(street1="Bağdat Caddesi No: 154, TURKEY", country="TUR")
    assert "154" in (p_tr.street_name or "")

    assert germanic_mod.expand_dutch_street_abbreviations("") == ""
    assert germanic_mod.is_valid_dutch_postcode("") is False

    hk = hk_mod.HongKongGrammar()
    p_hk1 = hk.standardize(street1="ABC Commercial Building, 8 Queen's Road", city="Central", country="HKG")
    assert p_hk1.format_street2().upper() == "ABC COMMERCIAL BUILDING"
    p_hk2 = hk.standardize(street1="ABC Commercial Building", city="HONG KONG", state="CENTRAL", country="HKG")
    assert p_hk2.city == "CENTRAL"

    ie = ireland_mod.IrelandGrammar()
    assert ie.extract_premise_and_thoroughfare("10 Grafton Street, Part2")[1] == "10"
    assert ie.extract_premise_and_thoroughfare("10 Grafton Street,")[1] == "10"
    p_ie1 = ie.standardize(
        street1="Treasury Building, 10 Lower Grand Canal Street",
        city="Dublin",
        postal_code="D02 X285",
        country="IRL",
    )
    assert p_ie1.building_name == "TREASURY BUILDING"
    assert p_ie1.format_street2() == "TREASURY BUILDING"
    p_ie2 = ie.standardize(street1="10 Grafton Street, Dublin D02 X285", country="IRL")
    assert p_ie2.city == "DUBLIN" and p_ie2.postal_code == "D02 X285"

    latam = latam_mod.LatinAmericaGrammar()
    assert latam.standardize(street1="Av. Larco 100", city="Lima", country="PER").country_iso3 == "PER"
    assert latam.standardize(street1="Av. Paulista 1578, São Paulo - SP", country="BRA").state == "SP"
    assert latam.standardize(street1="Av. Reforma 222, Ciudad de México", country="MEX").city == "CIUDAD DE MÉXICO"
    assert latam.standardize(street1="Av. Reforma 222, 06600, MEXICO", country="MEX").postal_code == "06600"
    p_lat_u1 = latam.standardize(street1="Flat 4 100 Av. Reforma", city="Mexico City", country="MEX")
    assert p_lat_u1.unit_type == "APT" and p_lat_u1.unit_number == "4"
    p_lat_u2 = latam.standardize(
        street1="Flat 4 100 Av. Reforma", street2="Piso 2", city="Mexico City", country="MEX"
    )
    assert "APT 4" in (p_lat_u2.unit_number or "")

    assert mena_mod.normalize_po_box_str("صندوق بريد 1234") == "ص.ب 1234"
    mena = mena_mod.MenaAfricaGrammar()
    p_za1 = mena.standardize(street1="100 Sandton Drive, Johannesburg 2196, Gauteng", country="ZAF")
    assert p_za1.city == "JOHANNESBURG" and p_za1.state == "GAUTENG"
    p_za2 = mena.standardize(street1="100 Sandton Drive, 2196, SOUTH AFRICA", country="ZAF")
    assert p_za2.postal_code == "2196"

    off = offshore_mod.OffshoreGrammar()
    assert off.extract_premise_and_thoroughfare("Ugland House South Church Street")[0] == "UGLAND HOUSE"
    p_off1 = off.standardize(street1="100 Front St Apt 5", street2="Suite 200", city="Hamilton", country="BMU")
    assert "APT 5" in (p_off1.unit_number or "")
    p_off2 = off.standardize(street1="100 Front St P.O. Box 45", city="Hamilton", country="BMU")
    assert p_off2.unit_type == "PO BOX" and p_off2.unit_number == "45"

    rom = romance_mod.RomanceGrammar()
    p_rom1 = rom.standardize(street1="Calle Mayor 10 2º B", city="Madrid", postal_code="28013", country="ESP")
    assert p_rom1.unit_number == "2 B"
    p_rom2 = rom.standardize(
        street1="10 Rue de Rivoli", street2="Aile Nord", city="Paris", postal_code="75001", country="FRA"
    )
    assert p_rom2.unit_number == "AILE NORD"

    sg = sg_mod.SingaporeGrammar()
    assert sg.normalize_postal_code("10 Collyer Quay S(049315)") == "049315"
    assert sg.extract_premise_and_thoroughfare("MARINA BAY FINANCIAL CENTRE, MARINA BOULEVARD") == (
        "MARINA BAY FINANCIAL CENTRE",
        None,
        "MARINA BOULEVARD",
    )

    sea = sea_mod.SoutheastAsiaGrammar()
    assert sea.extract_premise_and_thoroughfare("Jalan Ampang") == (None, None, "Jalan Ampang")

    uk = uk_mod.UKGrammar()
    assert uk_mod.split_commaless_postal_city(
        "10 High Road North Testville SW1A 2AA",
        is_postal=lambda s: s == "SW1A 2AA",
        towns=set(),
        suffix_directionals=frozenset({"NORTH"}),
    ) == (
        "10 High Road North",
        "Testville",
        "SW1A 2AA",
    )
    assert uk.normalize_postal_code("INVALID") == "INVALID"
    assert uk.extract_premise_and_thoroughfare("10 Downing Street,")[1] == "10"
    p_uk1 = uk.standardize(street1="10 Downing Street, SW1A 2AA, UK", country="GBR")
    assert p_uk1.postal_code == "SW1A 2AA"
    p_uk2 = uk.standardize(street1="14 High Street, Victoria House", city="London", postal_code="SW1A 2AA", country="GBR")
    assert p_uk2.street_name == "HIGH ST VICTORIA HOUSE"

    # Postal validation fallbacks and extract_postal_code contextual branches
    assert postal_mod.extract_postal_code("100 Sheikh Zayed Road, Dubai, United Arab Emirates") is None
    assert postal_mod.extract_postal_code("100 Main Street 90210") == "90210"

    monkeypatch.delitem(postal_mod.POSTAL_RULES, "USA")
    res_no_rule = postal_mod.validate_postal_code("12345", "USA", return_details=True)
    assert res_no_rule.is_valid is True

    monkeypatch.setattr(postal_mod, "_validate_canadian_semantics", lambda _: False)
    res_bad_can = postal_mod.validate_postal_code("M5V 2T6", "CAN", return_details=True)
    assert res_bad_can.is_valid is False


def test_normalization_country_detection_branches() -> None:
    assert normalization_mod.normalize_country_code(None, None, None, city_raw="París") == "FRA"
    assert normalization_mod.normalize_country_code(None, None, None, raw_street="100 Main, Street, París") == "FRA"
    assert normalization_mod.normalize_country_code(None, None, None, raw_street="10 Downing St, U.K., 000") == "GBR"
    assert normalization_mod.normalize_country_code(None, None, None, raw_street="100 Queen Street New Zealand") == "NZL"
    assert normalization_mod.normalize_country_code(None, None, None, raw_street="10 Rue de Rivoli, 75001 París") == "FRA"


def test_offline_index_phonetics_reference_registry_spatial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = offline_index_mod.OfflineReferenceIndex(":memory:", seed=True)
    idx._pid = -1
    _ = idx._conn
    assert idx.count() > 0 and idx.count_ranges() > 0

    # Legacy street_ranges schema without parity column
    legacy_conn = sqlite3.connect(":memory:")
    legacy_conn.execute(
        """
        CREATE TABLE street_ranges (
            range_id INTEGER PRIMARY KEY AUTOINCREMENT,
            street_name TEXT NOT NULL,
            postal_code TEXT NOT NULL,
            state TEXT NOT NULL,
            from_number INTEGER NOT NULL,
            to_number INTEGER NOT NULL,
            start_latitude REAL NOT NULL,
            start_longitude REAL NOT NULL,
            end_latitude REAL NOT NULL,
            end_longitude REAL NOT NULL,
            census_tract TEXT,
            fips_code TEXT
        );
        """
    )
    idx._init_schema(legacy_conn)
    cols = {r[1] for r in legacy_conn.execute("PRAGMA table_info(street_ranges)").fetchall()}
    assert "parity" in cols
    legacy_conn.close()

    # Resolve cache eviction
    monkeypatch.setattr(idx, "_RESOLVE_CACHE_MAX", 1)
    a1 = standardizer_mod.standardize_address(street1="100 Main St", city="New York", state="NY", postal_code="10001")
    a2 = standardizer_mod.standardize_address(street1="200 Broadway", city="New York", state="NY", postal_code="10002")
    idx.resolve_coordinates(a1)
    idx.resolve_coordinates(a2)
    assert len(idx._resolve_cache) == 1
    idx.close()

    # Phonetics punctuation-only street (pure Python path)
    assert phonetics_mod._pure_generate_phonetic_address_key("...", "10001", "NY") is None

    # GeoNames _source_files(None)
    monkeypatch.setattr(geonames_mod, "DEFAULT_DOWNLOAD_DIR", tmp_path / "empty_geonames")
    with pytest.raises(FileNotFoundError):
        geonames_mod._source_files(None)

    # USZip5Provider double-checked locking inner branch
    class _FlipLock:
        def __init__(self, target: us_zip5_mod.USZip5Provider) -> None:
            self._target = target

        def __enter__(self) -> None:
            self._target._loaded = True

        def __exit__(self, *args: Any) -> None:
            pass

    prov = us_zip5_mod.USZip5Provider()
    prov._lock = _FlipLock(prov)  # type: ignore[assignment]
    prov._ensure_loaded()
    assert prov._loaded is True

    # Registry memo eviction and international/CMRA branches
    monkeypatch.setattr(registry_mod, "_LOOKUP_MEMO_MAX", 1)
    registry_mod.lookup_corporate_registry("1209 Orange St", city="Wilmington", state="DE", postal_code="19801")
    assert (
        registry_mod.lookup_corporate_registry("Keizersgracht 421", country="", raw_street="Keizersgracht 421 NLD")
        is not None
    )
    assert registry_mod.lookup_corporate_registry("20-22 Wenlock Road N1 7GU", country="") is not None

    cmra_entry = registry_mod.CorporateRegistryEntry(
        provider_name="Test CMRA",
        category=registry_mod.RegistryCategory.MAIL_DROP_CMRA,
        country="USA",
        state="NY",
        city="NEW YORK",
        postal_code="10001",
        street_patterns=["999 CMRA BOX ST"],
        base_risk_score=0.75,
    )
    monkeypatch.setattr(registry_mod, "lookup_corporate_registry", lambda **_kw: cmra_entry)
    ok, reason = registry_mod.can_safely_merge_corporate_entities(
        {"street1": "999 CMRA BOX ST", "city": "NEW YORK", "postal_code": "10001", "country": "USA", "building_key": "B1"},
        {"street1": "999 CMRA BOX ST", "city": "NEW YORK", "postal_code": "10001", "country": "USA", "building_key": "B1"},
    )
    assert ok is False and "Shared virtual office or CMRA" in reason

    score, flags = registry_mod.evaluate_corporate_risk({"street1": "999 CMRA BOX ST", "state": "NY"})
    assert score >= 0.75 and registry_mod.CorporateRiskFlag.RISK_CMRA_MAIL_DROP in flags

    # SpatialEngine pragma error, corrupt metadata_json, and default spatial engine file discovery
    sp_db = tmp_path / "sp.db"
    sp_engine = spatial_engine_mod.SpatialEngine(db_path=str(sp_db), seed=True)
    real_sp_conn = sp_engine._conn
    sp_engine._init_schema(_PragmaRaisingConn(real_sp_conn, ("PRAGMA JOURNAL_MODE",)))  # type: ignore[arg-type]

    with real_sp_conn:
        real_sp_conn.execute("UPDATE spatial_points SET metadata_json = '{bad json'")
    bbox_res = sp_engine.query_bounding_box(-180.0, -90.0, 180.0, 90.0, limit=5)
    assert len(bbox_res) >= 1 and bbox_res[0].metadata == {}
    sp_engine.close()

    monkeypatch.setattr(spatial_engine_mod, "_DEFAULT_SPATIAL_ENGINE", None)
    monkeypatch.delenv("SPATIAL_DB_PATH", raising=False)
    monkeypatch.setattr(
        spatial_engine_mod.os.path,
        "isfile",
        lambda p: str(p) == "data/spatial_index.db",
    )
    monkeypatch.setattr(
        spatial_engine_mod,
        "SpatialEngine",
        lambda db_path=None, seed=True: sp_engine,
    )
    assert spatial_engine_mod.get_default_spatial_engine() is sp_engine
    monkeypatch.setattr(spatial_engine_mod, "_DEFAULT_SPATIAL_ENGINE", None)

    # Antimeridian polygon centroid wrapping negative longitude
    lon, lat = spatial_ingestion_mod.calculate_polygon_centroid(
        [[179.9, 0.0], [-179.8, 0.0], [-179.8, 1.0], [-179.9, 1.0]]
    )
    assert lon < 0.0 and 0.0 <= lat <= 1.0


def test_standardizer_and_us_street_parser_remaining_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    # US standardizer healed city matching norm_s1 (line 740)
    res_healed_city = standardizer_mod.standardize_address(
        street1="San Francisco", city="San Franciso", state="CA", postal_code="94102", enable_fuzzy=True
    )
    assert res_healed_city.street1 == "" and res_healed_city.city == "SAN FRANCISCO"

    # International standardizer norm_s1 == norm_city (line 871)
    res_intl_city = standardizer_mod.standardize_address(
        street1="North Testville", city="N Testville", country="ISL"
    )
    assert res_intl_city.street1 == "" and res_intl_city.city == "N TESTVILLE"

    # International standardizer unit phrase in street1 + PO Box in street2 (line 876)
    res_intl_pob = standardizer_mod.standardize_address(
        street1="Suite 400", street2="PO Box 450", city="Reykjavik", country="ISL"
    )
    assert res_intl_pob.street1 == "PO BOX 450" and res_intl_pob.street2 == "STE 400"

    # us_street_parser lines 410, 492, 890, 936-937, 1097
    res_dangling = us_street_parser._parse_us_street_tokens("100 Main St of New York NY 10001")
    assert res_dangling[0] == "100 MAIN ST" and res_dangling[3].upper() == "NEW YORK"

    res_blank = us_street_parser._parse_us_street_tokens("   ")
    assert res_blank[0] == "" and res_blank[2] is False

    res_same_city = us_street_parser._parse_us_address_components("Boston Suite 100", city_raw="Boston")
    assert res_same_city[0] == "" and res_same_city[1] == "STE 100"

    monkeypatch.setattr(
        us_street_parser.usaddress,
        "parse",
        lambda _s: [("100", "AddressNumber"), ("Calle", "StreetNamePreType"), ("Luna", "PlaceName")],
    )
    res_place_merge = us_street_parser._parse_us_street_tokens("100 Calle Luna", city_raw="San Juan")
    assert res_place_merge[0] == "100 CALLE LUNA"

    monkeypatch.setattr(us_street_parser, "usaddress", None)
    res_fb_zip = us_street_parser._parse_us_street_tokens("Park Way 10001")
    assert res_fb_zip[3] == "Park Way" and res_fb_zip[5] == "10001"
