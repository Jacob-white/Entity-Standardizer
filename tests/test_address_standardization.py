"""Comprehensive unit tests for US street parsing, normalization, care-of, secondary units, and explainability."""

from __future__ import annotations

import pytest

from entity_standardizer.address import (
    AutocompleteEngine,
    autocomplete_address,
    clean_rooftop_address,
    generate_building_key,
    generate_normalized_address_key,
    get_state_from_zip3,
    is_registered_agent_hub_address,
    normalize_country,
    normalize_country_code,
    normalize_us_postal_code,
    normalize_us_state,
    num_to_ordinal,
    standardize_address,
    validate_address,
)
from entity_standardizer.address._inputs import (
    coerce_text,
    correct_state_from_zip,
    is_privacy_placeholder,
    normalize_po_box_spelling,
)
from entity_standardizer.address._patterns import (
    clean_redundant_street_tail,
    clean_repetitive_cycles,
    is_city_noise_in_street1,
    is_invalid_thoroughfare,
    parse_intersection_address,
)
from entity_standardizer.address.autocomplete import calculate_haversine_distance_meters
from entity_standardizer.address.care_of import extract_care_of, has_care_of, strip_care_of
from entity_standardizer.address.explain import RULES, standardize_explained
from entity_standardizer.address.normalization import (
    swap_region_city_state,
    swap_us_city_state,
)
from entity_standardizer.address.secondary_units import (
    _numberize_unit_words,
    _pre_normalize_address_string,
    _split_international_secondary_unit,
    _standardize_secondary_unit,
)


def test_us_address_formats_and_special_grammars() -> None:
    # Standard rooftop + suite
    std = standardize_address(
        street1="350 Fifth Avenue Suite 4200",
        city="New York",
        state="New York",
        postal_code="10118-0110",
        country="US",
    )
    assert std.street1 == "350 5TH AVE"
    assert std.street2 == "STE 4200"
    assert std.city == "NEW YORK"
    assert std.state == "NY"
    assert std.postal_code == "10118-0110"
    assert std.country == "USA"
    assert std.is_us is True
    assert std.building_key == "350 5TH AVE||NEW YORK|NY|10118|USA"
    assert std.normalized_address_key == "350 5TH AVE|STE 4200|NEW YORK|NY|10118|USA"

    # Queens hyphenated grid address
    queens = standardize_address("47-11 90th Street, Apt 2B", city="Elmhurst", state="NY", postal_code="11373")
    assert "47-11" in queens.street1
    assert queens.street2 == "APT 2B"

    # Fractional house numbers
    frac = standardize_address("100 1/2 Main Street", city="Austin", state="TX", postal_code="78701")
    assert "100 1/2" in frac.street1
    assert "MAIN ST" in frac.street1

    # Grid coordinates (Salt Lake City / Rural W120N80)
    slc = standardize_address("450 South 200 East", city="Salt Lake City", state="UT", postal_code="84111")
    assert slc.state == "UT"
    assert slc.city == "SALT LAKE CITY"

    # PO Box, Rural Route, Highway Contract
    pob = standardize_address("P.O. Box 1234", city="Dallas", state="TX", postal_code="75201")
    assert pob.street1 == "PO BOX 1234"
    rr = standardize_address("Rural Route 2 Box 152", city="Springfield", state="IL", postal_code="62701")
    assert rr.street1 == "RR 2 BOX 152"
    hc = standardize_address("Highway Contract 4 Box 99", city="Helena", state="MT", postal_code="59601")
    assert "HC" in hc.street1 or "BOX 99" in hc.street1

    # Military APO/FPO/DPO
    mil = standardize_address("PSC 1234 Box 5678", city="APO", state="AE", postal_code="09012")
    assert mil.city == "APO"
    assert mil.state == "AE"

    # Puerto Rico Urbanization
    pr = standardize_address(
        street1="URB LAS GLADIOLAS 150 CALLE A",
        city="SAN JUAN",
        state="PR",
        postal_code="00926",
    )
    assert pr.state == "PR"
    assert "150" in pr.street1

    # Intersections
    inter = standardize_address("Hollywood Blvd and Vine St", city="Los Angeles", state="CA", postal_code="90028")
    assert "&" in inter.street1 or "HOLLYWOOD" in inter.street1

    # Single-line US parsing & locality-only
    single = standardize_address("1600 Amphitheatre Parkway, Mountain View, CA 94043")
    assert single.street1 == "1600 AMPHITHEATRE PKWY"
    assert single.city == "MOUNTAIN VIEW"
    assert single.state == "CA"
    assert single.postal_code == "94043"

    loc_only = standardize_address(city="Boston", state="MA", postal_code="02108", allow_locality=True)
    assert loc_only.address_status == "locality_only"
    assert loc_only.city == "BOSTON"

    # Privacy placeholder
    priv = standardize_address("Private Residence", city="Chicago", state="IL", postal_code="60601")
    assert priv.is_private_residence is True

    # Empty / garbage inputs
    empty = standardize_address("")
    assert empty.address_status == "parse_failed"
    garbage = standardize_address("N/A")
    assert garbage.address_status == "parse_failed"


def test_care_of_secondary_units_and_patterns() -> None:
    assert has_care_of("c/o John Smith, 100 Main St") is True
    assert has_care_of("100 Main St") is False
    cleaned, co = extract_care_of("Attn: Legal Dept, 200 Broadway")
    assert co is not None and "LEGAL" in co.upper()
    assert "200 BROADWAY" in strip_care_of("c/o Jane Doe, 200 Broadway").upper()

    assert _numberize_unit_words(["FL", "TWENTY", "TWO"]) == ["FL", "22"]
    assert _standardize_secondary_unit("Suite 400") == "STE 400"
    assert _standardize_secondary_unit("# 12B") in ("APT 12B", "# 12B", "UNIT 12B")
    pre = _pre_normalize_address_string("123 Main St., Apt. #4B")
    assert "123" in pre
    st_i, sec_i = _split_international_secondary_unit("10 Downing St Flat 2", "")
    assert "10 DOWNING" in st_i.upper()
    assert "2" in sec_i.upper()

    assert clean_redundant_street_tail("100 MAIN ST, NEW YORK, NY 10005", city="NEW YORK", state="NY", postal_code="10005") == "100 MAIN ST"
    assert clean_repetitive_cycles("NEW YORK NEW YORK") == "NEW YORK"
    assert parse_intersection_address("5TH AVE AND 42ND ST") is not None
    assert is_city_noise_in_street1("NEW YORK", "NEW YORK", "NY") is True
    assert is_invalid_thoroughfare("123") is True
    assert clean_rooftop_address("100 MAIN ST STE 200") == "100 MAIN ST"


def test_normalization_helpers_and_inputs() -> None:
    assert num_to_ordinal(1) == "1ST"
    assert num_to_ordinal(2) == "2ND"
    assert num_to_ordinal(3) == "3RD"
    assert num_to_ordinal(11) == "11TH"
    assert num_to_ordinal(22) == "22ND"
    assert get_state_from_zip3("10001") == "NY"
    assert normalize_country_code("United States") == "USA"
    assert normalize_country("GB") == "GBR"
    assert normalize_us_state("California") == "CA"
    assert normalize_us_postal_code("10001-1234") == ("10001-1234", "10001")
    assert normalize_us_postal_code("1234") == ("01234", "01234")
    assert is_registered_agent_hub_address("1209 N Orange St", "", "Wilmington", "DE", "19801") is True

    c_swapped, s_swapped = swap_us_city_state("IL", "CHICAGO")
    assert c_swapped == "CHICAGO" and s_swapped == "IL"
    c_reg, s_reg = swap_region_city_state("ON", "TORONTO", {"ON", "ONTARIO"})
    assert c_reg == "TORONTO" and s_reg == "ON"

    assert coerce_text(12345) == "12345"
    assert coerce_text(None) == ""
    assert is_privacy_placeholder("CONFIDENTIAL ADDRESS") is True
    assert normalize_po_box_spelling("P.O.B. 55") == "PO BOX 55"
    st_fixed, prev_st = correct_state_from_zip("CA", "10001", "USA")
    assert st_fixed == "NY" and prev_st == "CA"


def test_explain_validation_and_autocomplete() -> None:
    # Explainability & alternatives
    explained = standardize_address(
        street1="c/o Acme Corp, Three Hundred Fifty Fifth Avenue Suite 4200",
        city="New York",
        state="California",
        postal_code="10118",
        explain=True,
        alternatives=2,
        correct_state_from_zip=True,
    )
    assert explained.explanation is not None
    assert len(explained.explanation) > 0
    assert explained.field_confidence is not None
    assert all(ev["rule"] in RULES for ev in explained.explanation)
    assert explained.alternatives is not None

    exp2 = standardize_explained(True, 1, None, {"street1": "100 Wall Street, New York, NY 10005"})
    assert exp2.explanation is not None

    # Validate address wrapper
    val = validate_address(street1="100 Wall St", street2="Ste 400", city="New York", state="NY", postal_code="10005")
    assert val.is_valid is True
    assert val.to_dict()["standardized_address"]["street1"] == "100 WALL ST"

    # Keys
    b_key = generate_building_key("100 Wall St", "New York", "NY", "10005")
    n_key = generate_normalized_address_key("100 Wall St", "Ste 400", "New York", "NY", "10005")
    assert b_key == "100 WALL ST||NEW YORK|NY|10005|USA"
    assert n_key == "100 WALL ST|STE 400|NEW YORK|NY|10005|USA"

    # Autocomplete engine
    dist = calculate_haversine_distance_meters(40.7061, -74.0060, 40.7535, -73.9768)
    assert 5000 < dist < 7000
    engine = AutocompleteEngine()
    suggestions = engine.search("100 Wall", state_filter="NY", max_results=5, client_lat=40.7061, client_lon=-74.0060)
    assert len(suggestions) >= 1
    assert suggestions[0].street1 == "100 WALL ST"
    assert suggestions[0].as_dict()["street_line"] == "100 WALL ST"

    unit_suggestions = autocomplete_address("100 WALL ST STE")
    assert len(unit_suggestions) >= 1

    with pytest.raises(AttributeError):
        import entity_standardizer.address as addr_pkg

        _ = addr_pkg.NON_EXISTENT_ATTRIBUTE_XYZ


def test_us_street_parser_and_native_dispatch_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    import entity_standardizer.address._native_dispatch as addr_nd
    import entity_standardizer.address.us_street_parser as usp

    # Direct _rule_based_us_street_parse branches
    assert usp._rule_based_us_street_parse("RR 2 Box 14")[0] == "RR 2 BOX 14"
    assert usp._rule_based_us_street_parse("HC 1 Box 9")[0] == "HC 1 BOX 9"
    assert usp._rule_based_us_street_parse("PSC 2 BOX 100")[0] == "PSC 2 BOX 100"
    assert usp._rule_based_us_street_parse("100 Main St PO Box 50") == ("100 MAIN ST", "PO BOX 50", True)
    assert usp._rule_based_us_street_parse("PO Box 50") == ("PO BOX 50", "", True)
    assert usp._rule_based_us_street_parse("100 Main St PMB 42 #3B") == ("100 MAIN ST", "PMB 42 STE 3B", True)
    assert usp._rule_based_us_street_parse("100 Main St Penthouse") == ("100 MAIN ST", "PH", True)
    assert usp._rule_based_us_street_parse("Ste 100") == ("", "STE 100", True)
    assert usp._rule_based_us_street_parse("100 1/2 Main St")[0] == "100 1/2 MAIN ST"
    assert usp._rule_based_us_street_parse("123-45 82nd Ave")[0] == "123-45 82ND AVE"
    assert usp._rule_based_us_street_parse("100 South St")[0] == "100 SOUTH ST"
    assert usp._rule_based_us_street_parse("100 North East St")[0] == "100 NORTH EAST ST"
    assert usp._rule_based_us_street_parse("100 Twenty First St")[0] == "100 21ST ST"
    assert usp._rule_based_us_street_parse("100 First Ave")[0] == "100 1ST AVE"
    assert usp._rule_based_us_street_parse("100 State Route 9")[0] == "100 STATE RTE 9"
    assert usp._rule_based_us_street_parse("100 5 Ave")[0] == "100 5TH AVE"
    assert usp._rule_based_us_street_parse("100 Main Steret")[0] == "100 MAIN ST"
    assert usp._rule_based_us_street_parse("100 Nroth Main St")[0] == "100 N MAIN ST"
    assert usp._rule_based_us_street_parse("100 Main St", enable_fuzzy=False)[0] == "100 MAIN ST"

    # _unswap_state_city & _move_trailing_house_number
    assert usp._unswap_state_city("100 Main St, IL, Chicago 60614") == "100 Main St, Chicago, IL 60614"
    assert usp._unswap_state_city("100 Main St, Chicago, IL 60614") == "100 Main St, Chicago, IL 60614"
    assert usp._move_trailing_house_number("St. Louis Ave 100") == "100 St. Louis Ave"
    assert usp._move_trailing_house_number("AVENIDA ESMERALDA #5, SECOND FLOOR") == "5 AVENIDA ESMERALDA, SECOND FLOOR"
    assert usp._move_trailing_house_number("County Road 12") == "County Road 12"
    assert usp._move_trailing_house_number("St 100") == "St 100"

    # _parse_us_address_components branches
    assert usp._parse_us_address_components("Urb Las Flores", "Apt 5")[:2] == ("URB LAS FLORES", "APT 5")
    assert usp._parse_us_address_components("Urb Las Flores", "123 Calle Luna")[0].startswith("URB LAS FLORES")
    assert usp._parse_us_address_components("100 Main St", "PO Box 400")[:2] == ("100 MAIN ST", "PO BOX 400")
    assert usp._parse_us_address_components("100 Main St", "200 Oak Ave")[:2] == ("100 MAIN ST", "200 OAK AVE")
    assert usp._parse_us_address_components("PR #2 KM 82 HM. 2", "")[0] == "PR-2 KM 82.2"
    assert usp._parse_us_address_components("", "")[:3] == ("", "", False)

    # _parse_us_street_tokens when usaddress is None (reverse-anchor fallback parser)
    monkeypatch.setattr(usp, "usaddress", None)
    r1 = usp._parse_us_street_tokens("100 Main St, New York, NY 10005")
    assert r1[0] == "100 MAIN ST" and r1[4] == "NY" and r1[5] == "10005"
    r2 = usp._parse_us_street_tokens("PO Box 100 Chicago, IL 60601")
    assert r2[0] == "PO BOX 100" and r2[3].upper() == "CHICAGO"
    r3 = usp._parse_us_street_tokens("100 Main St N Ste 200 Chicago 60601")
    assert r3[0] == "100 MAIN ST N" and r3[1] == "STE 200"
    r4 = usp._parse_us_street_tokens("New York 10005")
    assert r4[0] == "" and r4[3].upper() == "NEW YORK" and r4[5] == "10005"

    # address._native_dispatch branches
    try:
        addr_nd.force_pure_python(True)
        assert addr_nd.is_using_native() is False
        assert addr_nd.get_active_engine().__name__.endswith("_pure_python_core")
        assert addr_nd.get_engine_info()["engine"] == "PurePythonCore"
        assert addr_nd.try_native("levenshtein_distance", "a", "b") == (False, None)

        class BrokenNative:
            def broken_fn(self) -> None:
                raise RuntimeError("boom")

            def get_capabilities(self) -> dict[str, object]:
                raise RuntimeError("caps error")

        addr_nd.force_pure_python(False)
        addr_nd.override_engine_for_testing(BrokenNative())
        assert addr_nd.is_native_available() is True
        assert addr_nd.try_native("missing_fn") == (False, None)
        assert addr_nd.try_native("broken_fn") == (False, None)
        assert addr_nd.get_capabilities()["engine"] == "Rust_PyO3"
    finally:
        addr_nd.override_engine_for_testing(None)
        addr_nd.force_pure_python(False)


def test_explain_and_alternatives_deep_branches() -> None:
    from types import SimpleNamespace
    from entity_standardizer.address.explain import (
        Recorder,
        _city_records,
        _country_records,
        _outcome_records,
        _postal_records,
        _reference_records,
        _state_records,
        _street_records,
        _token_diff,
        build_alternatives,
        build_evidence,
        build_trace,
        standardize_explained,
    )

    rec = Recorder({"street1": "100 Main St", "street2": "", "city": "Boston", "state": "MA", "postal_code": "02110", "country": ""})
    rec.add("street1", "100 MAIN ST", "street_normalized")
    assert rec.current("street1") == "100 MAIN ST"
    rec.country("", "JPN", "", "", "JPN")
    rec.country("", "CAN", "ON", "", None)
    rec.country("", "GBR", "", "SW1A 2AA", None)
    rec.country("", "USA", "", "", None)
    rec.country("", "FRA", "", "", None)

    # _token_diff across replace (equal len & unequal len), insert, delete, and moved_out
    assert len(_token_diff("street1", "One Hundred Main Steret", "100 MAIN ST")) >= 1
    assert len(_token_diff("street1", "100 Nroth Main St", "100 N MAIN ST")) >= 1
    assert len(_token_diff("street1", "100 First Ave", "100 1ST AVE")) >= 1
    assert len(_token_diff("street1", "100 North Main Street", "100 N MAIN ST")) >= 1
    assert len(_token_diff("street1", "100 Twenty First St", "100 21ST ST")) >= 1
    assert len(_token_diff("street1", "100 Peachtre St", "100 PEACHTREE ST")) >= 1
    assert len(_token_diff("street2", "400", "STE 400")) >= 1
    assert len(_token_diff("street1", "100 Main St Extra", "100 MAIN ST")) >= 1
    assert len(_token_diff("street1", "100 Main St Boston", "100 MAIN ST", moved_out={"BOSTON": "locality_moved_from_street"})) >= 1

    # _street_records branches: private residence, street1_moved_to_street2, secondary_promoted_to_street, unit_split, house_number_moved_to_front
    std_priv = standardize_address("Confidential", city="Boston", state="MA", postal_code="02110")
    assert any(r["rule"] == "private_residence_detected" for r in _street_records(Recorder({"street1": "Confidential", "street2": ""}), std_priv))

    std_moved_s2 = SimpleNamespace(street1="", street2="STE 200", city="BOSTON", state="MA", postal_code="02110", is_private_residence=False, building_name=None)
    assert any(r["rule"] == "street1_moved_to_street2" for r in _street_records(Recorder({"street1": "Suite 200", "street2": ""}), std_moved_s2))

    std_prom = SimpleNamespace(street1="PO BOX 450", street2="", city="BOSTON", state="MA", postal_code="02110", is_private_residence=False, building_name=None)
    assert any(r["rule"] == "secondary_promoted_to_street" for r in _street_records(Recorder({"street1": "", "street2": "PO Box 450"}), std_prom))

    std_sec = standardize_address("100 Main Street, Suite 200", city="Boston", state="MA", postal_code="02110")
    s_recs = _street_records(Recorder({"street1": "100 Main Street, Suite 200", "street2": "", "city": "Boston", "state": "MA", "postal_code": "02110"}), std_sec)
    assert any(r["rule"] == "unit_split" for r in s_recs)

    std_hn = standardize_address("St. Louis Ave 100", city="Chicago", state="IL", postal_code="60601")
    hn_recs = _street_records(Recorder({"street1": "St. Louis Ave 100", "street2": "", "city": "Chicago", "state": "IL", "postal_code": "60601"}), std_hn)
    assert any(r["rule"] == "house_number_moved_to_front" for r in hn_recs)

    # _city_records, _state_records, _postal_records, _country_records, _outcome_records, _reference_records
    std_city = standardize_address("100 Main St", city="Bosotn", state="MA", postal_code="02110")
    assert any(r["rule"] == "city_inferred_from_text" for r in _city_records(Recorder({"city": ""}), std_city))
    assert any(r["rule"] == "city_discarded" for r in _city_records(Recorder({"city": "Noise"}), SimpleNamespace(city="", is_us=True)))
    assert any(r["rule"] == "case_normalized" for r in _city_records(Recorder({"city": "boston"}), std_city))
    assert any(r["rule"] == "punctuation_normalized" for r in _city_records(Recorder({"city": "Boston."}), std_city))
    assert any(r["rule"] == "diacritics_folded" for r in _city_records(Recorder({"city": "Bóstón"}), std_city))
    assert any(r["rule"] == "typo_heal_city" for r in _city_records(Recorder({"city": "Bosotn"}), std_city))
    assert any(r["rule"] == "city_canonicalized" for r in _city_records(Recorder({"city": "CompletelyDifferent"}), std_city))

    assert any(r["rule"] == "state_from_zip" for r in _state_records(Recorder({"state": "", "postal_code": "02110"}), std_city))
    assert any(r["rule"] == "state_inferred_from_text" for r in _state_records(Recorder({"state": "", "postal_code": ""}), std_city))
    assert any(r["rule"] == "state_abbreviated" for r in _state_records(Recorder({"state": "Massachusetts", "postal_code": "02110"}), std_city))
    assert any(r["rule"] == "state_normalized" for r in _state_records(Recorder({"state": "UnknownState", "postal_code": "02110"}), std_city))

    assert any(r["rule"] == "postal_extracted_from_text" for r in _postal_records(Recorder({"postal_code": ""}), std_city))
    assert any(r["rule"] == "postal_discarded" for r in _postal_records(Recorder({"postal_code": "999077"}), SimpleNamespace(postal_code="")))
    assert any(r["rule"] == "postal_transposition_healed" for r in _postal_records(Recorder({"postal_code": "20110"}), std_city))
    assert any(r["rule"] == "postal_normalized" for r in _postal_records(Recorder({"postal_code": "2110"}), std_city))

    std_uk = standardize_address("10 Downing St", city="London", postal_code="SW1A 2AA", country="GB")
    assert any(r["rule"] == "country_defaulted_us" for r in _country_records(Recorder({"country": ""}), std_city))
    assert any(r["rule"] == "case_normalized" for r in _country_records(Recorder({"country": "gbr"}), std_uk))
    assert any(r["rule"] == "country_normalized" for r in _country_records(Recorder({"country": "GB"}), std_uk))

    std_hub = standardize_address("1209 Orange St", city="Wilmington", state="DE", postal_code="19801")
    std_hub.is_registered_agent_hub = True
    assert any(r["rule"] == "registered_agent_hub_detected" for r in _outcome_records(std_hub, Recorder({})))
    std_loc = standardize_address(city="Boston", state="MA", postal_code="02110", allow_locality=True)
    assert any(r["rule"] == "locality_only_accepted" for r in _outcome_records(std_loc, Recorder({})))
    std_fail = standardize_address("")
    assert any(r["rule"] == "parse_failed" for r in _outcome_records(std_fail, Recorder({})))
    std_zsm = standardize_address("100 Main St", city="Boston", state="NY", postal_code="02110")
    assert any(r["rule"] == "zip_state_mismatch_kept" for r in _outcome_records(std_zsm, Recorder({})))
    std_bad_pc = SimpleNamespace(
        is_registered_agent_hub=False,
        address_status="standardized",
        is_locality_only=False,
        is_us=False,
        postal_code="INVALID_PC",
        state="",
        country="GBR",
    )
    assert any(r["rule"] == "postal_format_invalid" for r in _outcome_records(std_bad_pc, Recorder({})))

    std_ref_ok = standardize_address("100 Main St", city="Boston", state="MA", postal_code="02110", enable_reference_validation=True)
    assert len(_reference_records(std_ref_ok)) >= 1
    std_ref_bad = standardize_address("100 Main St", city="Miami", state="MA", postal_code="02110", enable_reference_validation=True)
    assert len(_reference_records(std_ref_bad)) >= 1

    # build_trace, build_evidence, and build_alternatives (country, city, and unit alternatives)
    rec_alt = Recorder({"street1": "100 Main St, Suite 200", "street2": "", "city": "Bosotn", "state": "MA", "postal_code": "02110", "country": ""})
    rec_alt.country("", "USA", "", "02110", None)
    std_alt = standardize_address("100 Main St, Suite 200", city="Bosotn", state="MA", postal_code="02110")
    std_alt.dependent_locality = "DOWNTOWN"
    std_alt.building_name = "TOWER ONE"
    trace_alt = build_trace(rec_alt, std_alt)
    ev_alt = build_evidence(rec_alt, std_alt, trace_alt)
    assert ev_alt["zip_state"] == "agree"
    alts = build_alternatives(
        std_alt,
        rec_alt,
        trace_alt,
        {"street1": "100 Main St, Suite 200", "city": "Bosotn", "state": "MA", "postal_code": "02110"},
        limit=5,
    )
    assert len(alts) >= 2

    # _city_alternatives without state
    rec_nostate = Recorder({"city": "Bosotn"})
    std_nostate = SimpleNamespace(is_us=True, city="BOSTON", state="")
    from entity_standardizer.address.explain import _city_alternatives

    assert len(_city_alternatives(std_nostate, rec_nostate)) >= 1

    # standardize_explained with care_of, city_noise, state_corrected_from_zip, script_single_line_split, and calibrator
    fake_cal = SimpleNamespace(calibrate=lambda v: 0.99)
    exp_full = standardize_explained(
        True,
        3,
        fake_cal,
        {
            "street": "c/o Acme Corp, 100 Main St, Suite 200",
            "street2": "Attn: Legal Dept, Fl 3",
            "city": "Bosotn",
            "state": "NY",
            "postal_code": "02110",
            "correct_state_from_zip": True,
        },
    )
    assert exp_full.explanation is not None
    assert exp_full.field_confidence is not None
    assert exp_full.alternatives is not None

    exp_noise = standardize_explained(
        True,
        1,
        None,
        {"street1": "NYC", "city": "New York", "state": "NY", "postal_code": "10005", "allow_locality": True},
    )
    assert exp_noise.explanation is not None

    exp_script = standardize_explained(
        True,
        1,
        None,
        {"street1": "〒106-6132 東京都港区六本木6-10-1"},
    )
    assert exp_script.explanation is not None


def test_fast_path_and_autocomplete_deep_branches() -> None:
    from entity_standardizer.address.autocomplete import AutocompleteEngine
    from entity_standardizer.address.fast_path import (
        _fast_num_to_ordinal,
        _normalize_fast_sec_unit,
        _normalize_fast_street_phrase,
        fast_path_parse,
    )

    assert _fast_num_to_ordinal(11) == "11TH"
    assert _fast_num_to_ordinal(1) == "1ST"
    assert _fast_num_to_ordinal(2) == "2ND"
    assert _fast_num_to_ordinal(3) == "3RD"
    assert _fast_num_to_ordinal(4) == "4TH"

    assert _normalize_fast_sec_unit("") == ""
    assert _normalize_fast_sec_unit("200 OAK AVE APT 3") is None
    assert _normalize_fast_sec_unit("#400") == "STE 400"
    assert _normalize_fast_sec_unit("BASEMENT") == "BSMT"
    assert _normalize_fast_sec_unit("5 OAK") is None
    assert _normalize_fast_sec_unit("3RD FLOOR") == "FL 3"
    assert _normalize_fast_sec_unit("UNKNOWN_TOKEN") is None

    assert _normalize_fast_street_phrase("   ") is None
    assert _normalize_fast_street_phrase("USA") is None
    assert _normalize_fast_street_phrase("PO BOX 100") is None
    assert _normalize_fast_street_phrase("100 Front Royal Pike") is None
    assert _normalize_fast_street_phrase("100 Main St Basement") == ("100 MAIN ST", "BSMT")
    assert _normalize_fast_street_phrase("100 Main St #200") == ("100 MAIN ST", "STE 200")
    assert _normalize_fast_street_phrase("100") is None
    assert _normalize_fast_street_phrase("123-45 82nd Ave") is None
    assert _normalize_fast_street_phrase("100 1/2 Main St") is None
    assert _normalize_fast_street_phrase("ONE Main St") is None
    assert _normalize_fast_street_phrase("100 County Road 12") is None
    assert _normalize_fast_street_phrase("100 N County Road 12") is None
    assert _normalize_fast_street_phrase("100 Texas 71 Frontage Rd") is None
    assert _normalize_fast_street_phrase("100 South St") is None
    assert _normalize_fast_street_phrase("100 North East St") is None
    assert _normalize_fast_street_phrase("100 Nroth Main Steret Nroth") == ("100 N MAIN ST N", "")
    assert _normalize_fast_street_phrase("100 Main UnknownSuffix", enable_fuzzy=True) is None
    assert _normalize_fast_street_phrase("100 Main Steret", enable_fuzzy=False) is None
    assert _normalize_fast_street_phrase("100 Twenty First St") == ("100 21ST ST", "")
    assert _normalize_fast_street_phrase("100 First St") == ("100 1ST ST", "")
    assert _normalize_fast_street_phrase("100 A & B St") == ("100 A & B ST", "")
    assert _normalize_fast_street_phrase("100 5 St") == ("100 5TH ST", "")
    assert _normalize_fast_street_phrase("100 1000 St") == ("100 1000 ST", "")
    assert _normalize_fast_street_phrase("100 42nd St") == ("100 42ND ST", "")
    assert _normalize_fast_street_phrase("100 Main St", enable_fuzzy=False) == ("100 MAIN ST", "")

    # fast_path_parse Path A & Path B
    assert fast_path_parse(street1="100 Main St", city="Toronto", state="ON", postal_code="M5J 2J5", country="CAN") is None
    assert fast_path_parse(street1="100 Main St", city="Boston", state="INVALID_ST", postal_code="02110") is None
    assert fast_path_parse(street1="100 Main St", city="Boston", state="MA", postal_code="ABC") is None
    fp_zip4 = fast_path_parse(street1="100 Main St, Ste 10", street2="Fl 2", city="Bosotn", state="MA", postal_code="20110-1234", enable_fuzzy=True)
    assert fp_zip4 is not None and fp_zip4.postal_code == "02110-1234" and "STE 10" in fp_zip4.street2
    fp_priv_a = fast_path_parse(street1="CONFIDENTIAL", city="Boston", state="MA", postal_code="02110 1234")
    assert fp_priv_a is not None and fp_priv_a.is_private_residence is True
    fp_priv_b = fast_path_parse(street1="PRIVATE RESIDENCE, BOSTON, MA 02110")
    assert fp_priv_b is not None and fp_priv_b.is_private_residence is True
    fp_comma = fast_path_parse(street1="100 Main St, Ste 200, Bosotn, MA 20110-1234", enable_fuzzy=True)
    assert fp_comma is not None and fp_comma.postal_code == "02110-1234" and fp_comma.city == "BOSTON"

    # AutocompleteEngine extra methods and branches
    ac = AutocompleteEngine(seed=False)
    ac.index_addresses([
        {
            "street1": "100 WALL ST",
            "city": "NEW YORK",
            "state": "NY",
            "postal_code": "10005",
            "is_multi_unit": True,
            "known_units": ["STE 100", "STE 200"],
            "latitude": 40.7061,
            "longitude": -74.0060,
        },
        {
            "street1": "200 BROADWAY",
            "street2": "FL 5",
            "city": "NEW YORK",
            "state": "NY",
            "postal_code": "10007",
            "latitude": 999.0,  # out of bounds -> None
            "longitude": -74.0,
        },
    ])
    assert ac.load_reference_stream([{"street1": "300 PARK AVE", "city": "NEW YORK", "state": "NY", "postal_code": "10022"}]) == 1
    n_conn1 = ac.connect_reference_index()
    assert n_conn1 >= 0
    n_conn2 = ac.connect_reference_index()
    assert n_conn2 == 0

    assert ac.search("100 WALL", max_results=0) == []
    assert ac.search("   ") == []
    assert ac.search("...") == []
    # Typo tolerance ("WLL" -> "WALL")
    typo_res = ac.search("100 WLL", typo_tolerance=True)
    assert len(typo_res) >= 1 and typo_res[0].secondary_prompt_required is True
    # Secondary unit fallback when unit isn't indexed
    fallback_res = ac.search("100 WALL ST APT 999", typo_tolerance=True)
    assert len(fallback_res) >= 1
    # Radius filtering with radius_miles (excludes record without coords and outside radius)
    rad_in = ac.search("100 WALL", latitude=40.7061, longitude=-74.0060, radius_miles=2.0)
    assert len(rad_in) >= 1
    rad_out = ac.search("100 WALL", latitude=34.0522, longitude=-118.2437, radius_miles=2.0)
    assert rad_out == []
    assert ac.search("200 BROADWAY", latitude=40.7061, longitude=-74.0060, radius_miles=10.0) == []
    s2_res = ac.search("200 BROADWAY")
    assert len(s2_res) == 1 and "FL 5" in s2_res[0].text


def test_standardizer_and_us_street_parser_deep_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    import entity_standardizer.address.us_street_parser as usp

    # Single-line correct_state_from_zip
    s_zip_fix = standardize_address("100 Main St, Los Angeles, NY 90012", correct_state_from_zip=True, use_cache=False)
    assert s_zip_fix.state == "CA"

    # MAX_FIELD_LENGTH exceeded with non-US country
    s_long = standardize_address("A" * 5000, country="GBR")
    assert s_long.address_status == "parse_failed" and s_long.country == "GBR"

    # Suite words to numbers in street2 + multiline bleed in city and street1 + BRANCH OFFICE suffix
    s_bleed = standardize_address(
        street1="100 Main St\n3rd Floor\nCORPORATE OFFICE",
        street2="Suite Five Hundred",
        city="Boston Main Office\nSuite 200\nMAIN OFFICE\n100 Main St",
        state="MA",
        postal_code="02110",
        use_cache=False,
    )
    assert s_bleed.street1 == "100 MAIN ST" and s_bleed.city == "BOSTON"

    # City noise in street1
    s_noise = standardize_address(street1="NYC", city="New York", state="NY", postal_code="10005", allow_locality=True, use_cache=False)
    assert s_noise.address_status == "locality_only"

    # Region city/state swap for CAN, AUS, BRA, IND, MEX
    assert standardize_address("100 King St", city="ON", state="Toronto", postal_code="M5J 2J5", country="CAN").city == "TORONTO"
    assert standardize_address("100 George St", city="NSW", state="Sydney", postal_code="2000", country="AUS").city == "SYDNEY"
    assert standardize_address("Av Paulista 1000", city="SP", state="Campinas", postal_code="13010-100", country="BRA").city == "CAMPINAS"
    assert standardize_address("100 MG Road", city="MH", state="Mumbai", postal_code="400001", country="IND").city == "MUMBAI"
    assert standardize_address("Av Vallarta 100", city="JAL", state="Guadalajara", postal_code="44100", country="MEX").city == "GUADALAJARA"

    # Intersection address
    s_inter = standardize_address("Hollywood Blvd and Vine St", city="Los Angeles", state="CA", postal_code="90028")
    assert "&" in s_inter.street1 or "AND" in s_inter.street1

    # International PO Box + unit swap & locality-only promotion
    s_intl_po = standardize_address("PO Box 450", street2="Suite 400", city="George Town", country="CYM")
    assert "PO BOX" in s_intl_po.street1 or "PO BOX" in s_intl_po.street2
    s_intl_loc = standardize_address(street1="", street2="ZURICH", country="CHE", allow_locality=True)
    assert s_intl_loc.address_status == "locality_only" and s_intl_loc.city == "ZURICH"
    s_intl_priv = standardize_address("PRIVATE RESIDENCE", city="London", state="US", postal_code="00000", country="GBR")
    assert s_intl_priv.is_private_residence is True and s_intl_priv.state == "" and s_intl_priv.postal_code == ""

    # validate_address with dict, str, None, and strict/non-strict rejection reasons
    v_dict = validate_address({"street1": "100 Wall St", "city": "New York", "state": "NY", "postal_code": "10005"}, country="USA", strict=True)
    assert isinstance(v_dict.as_dict(), dict)
    v_str = validate_address("100 Wall St Ste 400, New York, NY 10005")
    assert v_str.is_deliverable is True
    v_err = validate_address("")
    assert v_err.is_valid is False and v_err.rejection_reason is not None
    v_mismatch = validate_address({"street1": "100 Main St", "city": "Boston", "state": "NY", "postal_code": "02110"})
    assert v_mismatch.is_valid is False

    # _parse_us_street_tokens special branches: RR, HC, Military in single string, multi-word city without comma, zip-only tail
    assert usp._parse_us_street_tokens("RR 2 Box 14, Springfield, IL 62701")[0] == "RR 2 BOX 14"
    assert usp._parse_us_street_tokens("HC 1 Box 9, Austin, TX 78701")[0] == "HC 1 BOX 9"
    assert usp._parse_us_street_tokens("PSC 2 BOX 100, APO, AE 09012")[0] == "PSC 2 BOX 100"
    assert usp._parse_us_street_tokens("100 Main St New York City NY 10005")[3].upper() == "NEW YORK CITY"
    assert usp._parse_us_street_tokens("100 Main St, Boston 02110")[3].upper() == "BOSTON"
    assert usp._parse_us_street_tokens("Boston 02110")[3].upper() == "BOSTON"
    assert usp._parse_us_street_tokens("100 Main St Boston 02110")[3].upper() == "BOSTON"

    # Mock usaddress.parse to exercise specific CRF tag recovery branches in _parse_us_street_tokens
    if usp.usaddress is not None:
        monkeypatch.setattr(
            usp.usaddress,
            "parse",
            lambda s: [
                ("100", "AddressNumber"),
                ("N", "StreetName"),
                ("EAST", "StreetName"),
                ("ST", "StreetNamePostType"),
                ("PH-1A", "PlaceName"),
                ("BSMT", "PlaceName"),
                ("2B", "OccupancyIdentifier"),
                ("FLOOR", "StateName"),
                ("3", "ZipCode"),
            ],
        )
        res_crf1 = usp._parse_us_street_tokens("dummy")
        assert "NORTH EAST" in res_crf1[0] and "FL 3" in res_crf1[1]

        monkeypatch.setattr(
            usp.usaddress,
            "parse",
            lambda s: [
                ("LIGHTON", "PlaceName"),
                ("PLAZA", "PlaceName"),
                ("II", "StreetName"),
                ("LLC", "StateName"),
            ],
        )
        res_crf2 = usp._parse_us_street_tokens("Lighton Plaza II", city_raw="Overland Park")
        assert "LIGHTON PLAZA II" in res_crf2[0]

