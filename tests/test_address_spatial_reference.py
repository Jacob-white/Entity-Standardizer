"""Comprehensive unit tests for spatial R*Tree engine, H3 indexing, ETL ingestion, offline rooftop index, cascade, and reference providers."""

from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile
import pytest

from entity_standardizer.address import (
    CensusGeocoder,
    OfflineReferenceIndex,
    SpatialEngine,
    USZip5Provider,
    VerificationCascade,
    get_default_us_zip5_provider,
    get_fallback_centroid,
    lat_lng_to_h3,
    resolve_offline_coordinates,
    resolve_spatial_coordinates,
    resolve_verification_cascade,
    standardize_address,
    validate_against_reference,
    validate_parcel_offline,
)
from entity_standardizer.address.geocoder import (
    OfflineGeocoder,
    geocode_offline,
    get_default_offline_geocoder,
    parse_census_geocoder_response,
)
from entity_standardizer.address.reference import (
    CompositeProvider,
    GeoNamesPostalProvider,
    ReferencePlace,
    build_geonames_index,
    download_geonames,
)
from entity_standardizer.address.reference._match import fold_name, name_tokens, names_match
from entity_standardizer.address.reference.geonames import postal_candidates
from entity_standardizer.address.reference.validation import (
    apply_reference_validation,
    get_env_reference_provider,
)
from entity_standardizer.address.spatial.h3_indexer import (
    h3_distance,
    h3_to_int,
    h3_to_parent,
    int_to_h3,
    is_valid_h3,
    k_ring,
)
from entity_standardizer.address.spatial.ingestion import (
    OpenAddressesIngestor,
    OsmBuildingIngestor,
    TigerLineIngestor,
    build_spatial_database,
    calculate_polygon_centroid,
)


def test_spatial_engine_h3_and_ingestion(tmp_path: Path) -> None:
    # H3 helpers
    h3_cell = lat_lng_to_h3(40.7061, -74.0060, resolution=10)
    assert is_valid_h3(h3_cell) is True
    assert is_valid_h3("invalid_h3") is False
    cell_int = h3_to_int(h3_cell)
    assert int_to_h3(cell_int) == h3_cell
    ring = k_ring(h3_cell, ring_size=1)
    assert h3_cell in ring and len(ring) == 7
    assert h3_distance(h3_cell, h3_cell) == 0
    parent_cell = h3_to_parent(h3_cell, 5)
    assert is_valid_h3(parent_cell) is True

    # SpatialEngine 4-stage cascade
    engine = SpatialEngine(seed=True)
    assert engine.count() >= 5

    # Stage 1: Rooftop match
    s1 = engine.resolve("100 WALL ST|STE 400|NEW YORK|NY|10005|USA")
    assert s1.stage == 1 and s1.precision == "CONFIRMED_ROOFTOP"
    assert s1.as_dict()["parcel_id"] == "NY-MAN-00100"

    # Stage 1 by building key & parcel_id
    s1_bld = engine.resolve({"building_key": "100 WALL ST||NEW YORK|NY|10005|USA"})
    assert s1_bld.stage == 1
    s1_parcel = engine.resolve({"parcel_id": "NY-MAN-00100"})
    assert s1_parcel.stage == 1

    # Stage 2: Street range interpolation
    s2 = engine.resolve({"street1": "1050 MARKET ST", "city": "SAN FRANCISCO", "state": "CA", "postal_code": "94103"})
    assert s2.stage == 2 and s2.precision == "RANGE_INTERPOLATED"

    # Stage 3: Postal centroid
    s3 = engine.resolve({"street1": "999 UNKNOWN RD", "city": "NEW YORK", "state": "NY", "postal_code": "10001"})
    assert s3.stage == 3 and s3.precision == "POSTAL_CENTROID"

    # Stage 4: State/municipal centroid
    s4 = engine.resolve({"street1": "999 UNKNOWN RD", "city": "UNKNOWN CITY", "state": "TX"})
    assert s4.stage == 4 and s4.precision == "MUNICIPAL_CENTROID"

    # Unresolved international
    s0 = engine.resolve({"street1": "10 Downing St", "city": "London", "country": "GBR", "is_us": False})
    assert s0.stage == 0 and s0.precision == "UNRESOLVED"

    # Bounding box, radius, and street segment R*Tree queries
    bbox_pts = engine.query_bounding_box(-74.02, 40.70, -73.95, 40.76)
    assert len(bbox_pts) >= 2
    rad_pts = engine.query_radius(-74.0060, 40.7061, radius_meters=2000.0)
    assert len(rad_pts) >= 1
    segs = engine.query_street_segments(-122.42, 37.77, -122.41, 37.78)
    assert len(segs) >= 1

    # Polygon centroid (including antimeridian & degenerate polygons)
    lon_c, lat_c = calculate_polygon_centroid([[-74.01, 40.70], [-74.00, 40.70], [-74.00, 40.71], [-74.01, 40.71]])
    assert abs(lon_c - (-74.005)) < 0.01 and abs(lat_c - 40.705) < 0.01
    assert calculate_polygon_centroid([]) == (0.0, 0.0)
    assert calculate_polygon_centroid([[179.9, 10.0], [-179.9, 10.0], [-179.9, 10.2], [179.9, 10.2]])[1] == pytest.approx(10.1, abs=0.1)

    # Ingestors & hot_swap
    db_path = str(tmp_path / "spatial_swap.db")
    built = build_spatial_database(
        db_path,
        openaddresses_data=[
            {"NUMBER": "700", "STREET": "BOYLSTON ST", "CITY": "BOSTON", "REGION": "MA", "POSTCODE": "02116", "LATITUDE": 42.3496, "LONGITUDE": -71.0784, "ID": "MA-BOS-700"}
        ],
        tiger_segments=[
            {"street_name": "BEACON ST", "from_number": 100, "to_number": 200, "start_lat": 42.355, "start_lon": -71.070, "end_lat": 42.354, "end_lon": -71.075, "postal_code": "02108", "state": "MA"}
        ],
        osm_features=[
            {"geometry": {"type": "Polygon", "coordinates": [[[-71.06, 42.35], [-71.05, 42.35], [-71.05, 42.36], [-71.06, 42.36]]]}, "properties": {"addr:housenumber": "10", "addr:street": "STATE ST", "addr:city": "BOSTON", "addr:state": "MA", "addr:postcode": "02109"}}
        ],
    )
    built.close()

    oa_csv = io.StringIO("NUMBER,STREET,CITY,REGION,POSTCODE,LATITUDE,LONGITUDE\n800,BOYLSTON ST,BOSTON,MA,02199,42.348,-71.080\n")
    assert OpenAddressesIngestor(engine).ingest_csv(oa_csv) == 1
    tg_csv = io.StringIO("street_name,from_number,to_number,start_lat,start_lon,end_lat,end_lon,postal_code,state\nNEWBURY ST,10,50,42.352,-71.071,42.351,-71.074,02116,MA\n")
    assert TigerLineIngestor(engine).ingest_csv(tg_csv) == 1
    osm_json = io.StringIO(json.dumps({"features": [{"geometry": {"type": "Point", "coordinates": [-71.059, 42.358]}, "properties": {"addr:housenumber": "20", "addr:street": "CONGRESS ST", "addr:city": "BOSTON", "addr:state": "MA", "addr:postcode": "02109"}}]}))
    assert OsmBuildingIngestor(engine).ingest_geojson(osm_json) == 1

    engine.hot_swap(db_path)
    assert engine.has_address_key("700 BOYLSTON ST||BOSTON|MA|02116|USA") is True
    engine.close()

    std_geo = standardize_address("100 Wall St Ste 400", city="New York", state="NY", postal_code="10005", enable_geocoding=True)
    assert std_geo.latitude is not None
    assert resolve_spatial_coordinates(std_geo).stage >= 1


def test_offline_index_geocoder_and_cascade(tmp_path: Path) -> None:
    idx = OfflineReferenceIndex(seed=True)
    assert idx.count() > 0 and idx.count_ranges() > 0

    std_wall = standardize_address("100 Wall St Ste 400", city="New York", state="NY", postal_code="10005")
    rec = idx.resolve_coordinates(std_wall)
    assert rec is not None and rec.precision == "ROOFTOP"
    assert "latitude" in rec.as_dict()

    # Street range interpolation
    interp = idx.interpolate_street_range(1600, "PENNSYLVANIA AVE", postal_code="20500", state="DC")
    assert interp is not None and interp.precision == "RANGE_INTERPOLATED"

    # Parcel validation
    p_val = idx.validate_parcel(std_wall)
    assert p_val.is_valid_parcel is True and p_val.as_dict()["matched_rooftop"] is True
    assert validate_parcel_offline("NONEXISTENT_PARCEL_XYZ").is_valid_parcel is False
    assert resolve_offline_coordinates(std_wall) is not None

    # OfflineGeocoder & CensusGeocoder response parser
    off_geo = get_default_offline_geocoder()
    g_res = off_geo.geocode_address("100 Wall St", city="New York", state="NY", zip_code="10005")
    assert g_res["latitude"] is not None
    g_batch = OfflineGeocoder(idx).geocode_batch([("1", "100 Wall St", "New York", "NY", "10005"), ("2", "999 Unknown St", "Austin", "TX", "78701")])
    assert "1" in g_batch and "2" in g_batch
    assert geocode_offline("100 Wall St, New York, NY 10005")["latitude"] is not None

    csv_resp = '"1","100 Wall St, New York, NY, 10005","Match","Exact","100 WALL ST, NEW YORK, NY, 10005","-74.0060,40.7061","123456","R"\n'
    parsed_census = parse_census_geocoder_response(csv_resp)
    assert parsed_census["1"][0] == pytest.approx(40.7061)
    assert get_fallback_centroid(zip5="10005", state="NY") is not None
    cg = CensusGeocoder(timeout_seconds=1)
    assert cg.geocode_batch([]) == {}

    # VerificationCascade
    cascade = VerificationCascade(offline_index=idx)
    cascade.register_rooftop("10 MAIN ST||BOSTON|MA|02108|USA", 42.358, -71.060)
    c1 = cascade.resolve(normalized_address_key="10 MAIN ST||BOSTON|MA|02108|USA")
    assert c1 is not None and c1.stage == 1 and c1.as_dict()["source"] == "LOCAL_ROOFTOP_REGISTRY"
    c1b = cascade.resolve(street1="100 Wall St", city="New York", state="NY", postal_code="10005")
    assert c1b is not None and c1b.stage == 1
    c3 = resolve_verification_cascade(street1="999 Nowhere Rd", city="New York", state="NY", postal_code="10001")
    assert c3 is not None and c3.stage in (3, 4)

    # Hot-swap offline index
    swap_file = str(tmp_path / "offline_swap.db")
    idx2 = OfflineReferenceIndex(db_path=swap_file, seed=True)
    idx2.close()
    idx.hot_swap(swap_file)
    assert idx.count() > 0
    idx.close()


def test_reference_providers_and_geonames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert fold_name("Saint-Jean-sur-Richelieu") == "SAINT-JEAN-SUR-RICHELIEU"
    assert "SAINT" in name_tokens("St. Louis")
    assert names_match("St. Petersburg", "Saint Petersburg") is True
    assert "M5J" in postal_candidates("CA", "M5J 2J5")
    assert "1017" in postal_candidates("NL", "1017 BV")
    assert "SW1A" in postal_candidates("GB", "SW1A 2AA")

    rp = ReferencePlace(country="US", postal_code="10001", place_name="New York", admin1="New York", admin1_code="NY")
    assert rp.as_dict()["postal_code"] == "10001"
    assert USZip5Provider(data_path=tmp_path / "missing.tsv.gz").lookup_postal("US", "10001") == []

    # USZip5Provider
    us_prov = get_default_us_zip5_provider()
    assert us_prov.covers_country("US") is True
    assert us_prov.covers_country("GB") is False
    places_10001 = us_prov.lookup_postal("US", "10001")
    assert len(places_10001) >= 1 and places_10001[0].admin1_code == "NY"
    zips_nyc = us_prov.lookup_place("US", "New York", admin1_code="NY")
    assert "10001" in zips_nyc

    # Validate against reference
    std_ok = standardize_address("350 Fifth Ave", city="New York", state="NY", postal_code="10118")
    v_ok = validate_against_reference(std_ok, us_prov)
    assert v_ok.is_confirmed is True and v_ok.as_dict()["status"] == "confirmed"

    std_state_err = standardize_address("350 Fifth Ave", city="New York", state="CA", postal_code="10118")
    v_state_err = validate_against_reference(std_state_err, us_prov)
    assert v_state_err.status == "state_mismatch"
    apply_reference_validation(std_state_err, us_prov)
    assert "ERR_POSTAL_STATE_MISMATCH" in std_state_err.failure_reason_codes

    std_place_err = standardize_address("350 Fifth Ave", city="Buffalo", state="NY", postal_code="10118")
    v_place_err = validate_against_reference(std_place_err, us_prov)
    assert v_place_err.status == "place_mismatch"
    apply_reference_validation(std_place_err, us_prov)
    assert "WARN_POSTAL_PLACE_MISMATCH" in std_place_err.failure_reason_codes

    std_unk = standardize_address("350 Fifth Ave", city="New York", state="NY", postal_code="00000")
    v_unk = validate_against_reference(std_unk, us_prov)
    assert v_unk.status == "postal_unknown"

    # Build a GeoNames SQLite index from a synthetic zip archive
    zip_path = tmp_path / "CA.zip"
    tsv_line = "CA\tM5J\tToronto\tOntario\tON\t\t\t\t\t43.6426\t-79.3871\t4\n"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("CA.txt", tsv_line)

    dl_paths = download_geonames(
        ["CA"],
        dest_dir=tmp_path / "dl",
        urlopen=lambda req, timeout=60.0: io.BytesIO(zip_path.read_bytes()),
    )
    assert len(dl_paths) == 1 and dl_paths[0].is_file()

    gn_db = tmp_path / "geonames.sqlite"
    build_geonames_index(gn_db, source=zip_path)
    gn_prov = GeoNamesPostalProvider(gn_db)
    assert gn_prov.covers_country("CA") is True
    ca_places = gn_prov.lookup_postal("CA", "M5J 2J5")
    assert len(ca_places) == 1 and ca_places[0].place_name == "Toronto"
    assert "M5J" in gn_prov.lookup_place("CA", "Toronto", admin1_code="ON")

    comp = CompositeProvider([us_prov, gn_prov])
    assert comp.covers_country("CA") is True and comp.covers_country("US") is True
    assert len(comp.lookup_postal("CA", "M5J 2J5")) == 1

    monkeypatch.setenv("ENTITY_STANDARDIZER_REFERENCE_DB", str(gn_db))
    env_prov = get_env_reference_provider()
    assert env_prov is not None and env_prov.covers_country("CA") is True
    env_prov.close()
    gn_prov.close()


def test_h3_cascade_careof_and_intl_grammar_edges() -> None:
    from unittest.mock import MagicMock
    from entity_standardizer.address.care_of import extract_care_of, has_care_of, strip_care_of, _looks_like_street
    from entity_standardizer.address.international.canada import CanadaGrammar, french_unit, is_valid_canadian_postal_code, province_code
    from entity_standardizer.address.international.singapore import SingaporeGrammar
    from entity_standardizer.address.international.southeast_asia import SoutheastAsiaGrammar

    # 1. H3 validation and error branches
    h3_cell = lat_lng_to_h3(40.7061, -74.0060, resolution=10)
    neighbors = k_ring(h3_cell, ring_size=1)
    other_cell = [c for c in neighbors if c != h3_cell][0]
    assert h3_distance(h3_cell, other_cell) == 1
    assert k_ring(h3_cell, ring_size=0) == [h3_cell]
    assert is_valid_h3(12345) is False  # type: ignore[arg-type]

    for bad_args in (
        (float("nan"), -74.0, 10),
        (95.0, -74.0, 10),
        (40.0, 195.0, 10),
        (40.0, -74.0, True),
        (40.0, -74.0, 20),
    ):
        with pytest.raises(ValueError):
            lat_lng_to_h3(*bad_args)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid H3 index"):
        h3_to_int("not-an-h3")
    with pytest.raises(ValueError, match="Invalid integer representation"):
        int_to_h3(0)
    with pytest.raises(ValueError, match="Invalid H3 index"):
        k_ring("not-an-h3")
    with pytest.raises(ValueError, match="Invalid H3 cell"):
        h3_distance("not-an-h3", h3_cell)
    far_cell = lat_lng_to_h3(-33.8688, 151.2093, resolution=10)
    with pytest.raises(ValueError, match="H3 grid distance undefined"):
        h3_distance(h3_cell, far_cell)
    with pytest.raises(ValueError, match="Invalid H3 index"):
        h3_to_parent("not-an-h3", 5)
    with pytest.raises(ValueError, match="cannot be negative"):
        h3_to_parent(h3_cell, -1)
    with pytest.raises(ValueError, match="cannot be finer"):
        h3_to_parent(h3_cell, 12)

    # 2. VerificationCascade Stage 1 secondary-unit fallback, Stage 2 Census TIGER, Stage 3 4-digit ZIP & ZIP3->State, Stage 4 State
    cascade = VerificationCascade()
    cascade.register_rooftop("100 MAIN ST||BOSTON|MA|02110|USA", 42.358, -71.060)
    c_unit = cascade.resolve(normalized_address_key="100 MAIN ST|STE 200|BOSTON|MA|02110|USA")
    assert c_unit is not None and c_unit.stage == 1

    mock_cg = MagicMock()
    mock_cg.geocode_batch.return_value = {"1": {"latitude": "42.3601", "longitude": "-71.0589", "census_tract": "0101"}}
    c_tiger = cascade.resolve(street1="500 Beacon St", city="Boston", state="MA", postal_code="02115", census_geocoder=mock_cg)
    assert c_tiger is not None and c_tiger.stage == 2 and c_tiger.source == "CENSUS_TIGER"

    mock_cg_err = MagicMock()
    mock_cg_err.geocode_batch.side_effect = RuntimeError("timeout")
    c_z4 = cascade.resolve(street1="500 Beacon St", postal_code="2110", census_geocoder=mock_cg_err)
    assert c_z4 is not None and c_z4.stage in (3, 4)

    c_z3_state = cascade.resolve(postal_code="59901")  # MT ZIP3 not in metro table -> STATE_CENTROID_FROM_ZIP3
    assert c_z3_state is not None and c_z3_state.stage in (3, 4)

    c_state_only = cascade.resolve(state="Wyoming")
    assert c_state_only is not None and c_state_only.stage == 4 and c_state_only.source == "STATE_CENTROID"
    assert cascade.resolve() is None

    # 3. care_of.py branches
    assert extract_care_of("") == ("", "")
    assert _looks_like_street("   ") is False
    assert _looks_like_street("BROADWAY") is True
    assert _looks_like_street("ACME") is False
    assert has_care_of("(C/O Acme Corp) 100 Main St") is True
    assert strip_care_of("[Attn: Legal Dept] 200 Oak Ave") == "200 Oak Ave"
    addr_after_suffix, co_name = extract_care_of("C/O Acme Holdings LLC, 100 Main St")
    assert addr_after_suffix == "100 Main St" and "Acme Holdings" in co_name
    addr_word_num, _ = extract_care_of("C/O Smith & Co LLC One World Trade Center")
    assert "One World Trade Center" in addr_word_num
    addr_after_suf_no_num, _ = extract_care_of("C/O Ocean Park Holdings LLC Main Street")
    assert addr_after_suf_no_num == "Main Street"
    addr_num_tail, _ = extract_care_of("C/O Foo Bar Baz 42 Elm")
    assert addr_num_tail == "42 Elm"
    addr_prefix_only, co_only = extract_care_of("100 Main St, C/O Acme Partners")
    assert addr_prefix_only == "100 Main St" and "Acme Partners" in co_only
    addr_comma_only, _ = extract_care_of("C/O Acme Corp, LLC, Corporate HQ")
    assert addr_comma_only == ""

    # 4. SingaporeGrammar, SoutheastAsiaGrammar, and CanadaGrammar branches
    sg = SingaporeGrammar()
    assert sg.normalize_postal_code("") == ""
    assert sg.normalize_postal_code("49909") == "049909"
    assert sg.normalize_postal_code("Singapore 018981") == "018981"
    assert sg.extract_premise_and_thoroughfare("") == (None, None, None)
    assert sg.extract_premise_and_thoroughfare("MARINA BAY FINANCIAL CENTRE TOWER 1 8 MARINA BOULEVARD") == (
        "MARINA BAY FINANCIAL CENTRE TOWER 1",
        "8",
        "MARINA BOULEVARD",
    )
    assert sg.extract_premise_and_thoroughfare("MARINA BAY FINANCIAL CENTRE") == ("MARINA BAY FINANCIAL CENTRE", None, None)
    assert sg.extract_premise_and_thoroughfare("BLK 101 TOA PAYOH LORONG 1") == (None, "BLK 101", "TOA PAYOH LORONG 1")
    sg_lvl = sg.parse([], {"street1": "10 Collyer Quay Level 24 Singapore 049315"})
    assert sg_lvl.unit_number == "LEVEL 24" and sg_lvl.postal_code == "049315"
    sg_s2 = sg.parse([], {"street1": "1 Raffles Place", "street2": "Suite 10", "postal_code": "048616"})
    assert sg_s2.unit_number is not None

    se = SoutheastAsiaGrammar()
    assert se._resolve_country_iso(None) == "IDN"
    assert se._resolve_country_iso("MY") == "MYS"
    assert se._resolve_country_iso("UNKNOWN") == "IDN"
    assert se.normalize_postal_code("") == ""
    assert se.extract_premise_and_thoroughfare("") == (None, None, None)
    assert se.extract_premise_and_thoroughfare("12 Jalan Ampang")[1] == "12"
    assert se.extract_premise_and_thoroughfare("Jalan Gajah Mada No. 19")[1] == "19"
    se_4part = se.parse([], {"street1": "Jl. Sudirman No. 1, Senayan, Kebayoran Baru, Jakarta 12190, Indonesia"})
    assert se_4part.postal_code == "12190" and se_4part.dependent_locality is not None
    se_2part = se.parse([], {"street1": "7431 Yakal Street, Makati 1203", "country": "PHL"})
    assert se_2part.city == "MAKATI" and se_2part.postal_code == "1203"
    se_my = se.parse([], {"street1": "10 Jalan Ampang, Taman Tun", "city": "Kuala Lumpur", "postal_code": "50450", "country": "MYS"})
    assert se_my.state == "KUL" and se_my.dependent_locality == "TAMAN TUN"

    ca = CanadaGrammar()
    assert is_valid_canadian_postal_code("") is False
    assert is_valid_canadian_postal_code("12345") is False
    assert is_valid_canadian_postal_code("M5J 2J5") is True
    assert province_code("Québec") == "QC"
    assert french_unit("bureau 200") == "STE 200"
    assert ca.extract_premise_and_thoroughfare("RR 2 Site 3 Box 4")[2] == "RR 2 Site 3 Box 4"
    ca_fr = ca.standardize("200 rue Saint-Denis, app. 4, Montréal, Québec H2X 3K8")
    assert ca_fr.state == "QC" and ca_fr.postal_code == "H2X 3K8" and ca_fr.unit_type == "APT"
    ca_po = ca.standardize("PO Box 123, Toronto, ON M5J 2J5", street2="Stn A")
    assert ca_po.street_name == "PO BOX 123 STN A"

