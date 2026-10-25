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
