"""Comprehensive unit tests for address fuzzy typo healing and phonetic blocking key generation."""

from __future__ import annotations

from entity_standardizer.address import (
    compute_soundex,
    damerau_levenshtein_distance,
    generate_phonetic_address_key,
    heal_city_token,
    heal_postal_code_transposition,
    heal_street_name,
    heal_street_number_transposition,
    heal_street_suffix,
)
from entity_standardizer.address._pure_python_core import (
    standardize_batch as pure_core_batch,
    standardize_record as pure_core_record,
)
from entity_standardizer.address.fuzzy import _pure_damerau_levenshtein_distance
from entity_standardizer.address.phonetics import (
    _pure_compute_soundex,
    _pure_generate_phonetic_address_key,
)


def test_fuzzy_typo_healing_functions() -> None:
    # Damerau-Levenshtein distance
    assert damerau_levenshtein_distance("BOULEVARD", "BUOLEVARD") == 1
    assert _pure_damerau_levenshtein_distance("AVENUE", "AVNEUE") == 1
    assert _pure_damerau_levenshtein_distance("STREET", "STERET") == 1

    # Street suffix healing
    assert heal_street_suffix("STERET") == "ST"
    assert heal_street_suffix("AVNEUE") == "AVE"
    assert heal_street_suffix("BOULVARD") == "BLVD"
    assert heal_street_suffix("PKWY") == "PKWY"
    # Protected words and digits/hyphens are never corrupted
    assert heal_street_suffix("PARKER") is None
    assert heal_street_suffix("FLORES") is None
    assert heal_street_suffix("123") is None
    assert heal_street_suffix("A-B") is None
    assert heal_street_suffix("NORTH") is None
    assert heal_street_suffix("XY") is None

    # City token healing constrained by state / ZIP3
    assert heal_city_token("CHICGO", state="IL") == "CHICAGO"
    assert heal_city_token("LOS ANGLES", state="CA") == "LOS ANGELES"
    assert heal_city_token("PHILDELPHIA", zip3="191") == "PHILADELPHIA"
    assert heal_city_token("NEW YORK", state="NY") == "NEW YORK"
    assert heal_city_token("BROOKLYN", state="NY") == "BROOKLYN"
    assert heal_city_token("CHICGO") == "CHICAGO"
    assert heal_city_token("") is None

    # Street name healing
    assert heal_street_name("BRADWAY") == "BROADWAY"
    assert heal_street_name("WASHNGTON") == "WASHINGTON"
    assert heal_street_name("MAIN") == "MAIN"
    # Protected words, plurals, ordinals, directionals, digits are untouched
    assert heal_street_name("MARTIN") is None
    assert heal_street_name("PARKS") is None
    assert heal_street_name("NORTH") is None
    assert heal_street_name("123RD") is None
    assert heal_street_name("AB") is None

    # Postal code transposition healing
    assert heal_postal_code_transposition("10018", state="NY") == "10018"
    assert heal_postal_code_transposition("01001", state="NY") == "10001"
    assert heal_postal_code_transposition("90210", state="NY") is None
    assert heal_postal_code_transposition("123", state="NY") is None
    assert heal_postal_code_transposition("", state="NY") is None

    # Street number transposition healing
    assert heal_street_number_transposition("100", valid_ranges=[(100, 200)]) == "100"
    assert heal_street_number_transposition("305", valid_ranges=[(340, 360)]) == "350"
    assert heal_street_number_transposition("305A", valid_ranges=[(340, 360)]) == "350A"
    assert heal_street_number_transposition("999", valid_ranges=[(100, 200)]) is None
    assert heal_street_number_transposition("5", valid_ranges=[(1, 10)]) is None
    assert heal_street_number_transposition("", valid_ranges=None) is None


def test_phonetic_blocking_keys_and_pure_python_core() -> None:
    assert compute_soundex("Washington") == "W252"
    assert _pure_compute_soundex("Pfister") == "P236"
    assert _pure_compute_soundex("12345") == ""
    assert _pure_compute_soundex("Ashcraft") == "A261"

    # Standard street & numbered street hybrid keys
    assert generate_phonetic_address_key("350 5TH AVE", "10118", "NEW YORK") == "350|#5|10118"
    assert generate_phonetic_address_key("450 LEXINGTON AVE", "10017-2201", "NEW YORK") == "450|L252|10017"
    assert _pure_generate_phonetic_address_key("100 WALL ST", "10005", "NEW YORK") == "100|W400|10005"

    # PO Box, Rural Route, Military Unit, Puerto Rico Urbanization, Fractional, Pre/Post-directionals
    assert _pure_generate_phonetic_address_key("PO BOX 1234", "75201", "DALLAS") == "POB 1234|75201"
    assert _pure_generate_phonetic_address_key("RR 2 BOX 152", "62701", "SPRINGFIELD") == "RR 2|B200|62701"
    assert _pure_generate_phonetic_address_key("HC 4", "59601", "HELENA") == "HC 4|H200|59601"
    assert _pure_generate_phonetic_address_key("UNIT 1234 BOX 5678", "09012", "APO") == "1234|B200|09012"
    assert _pure_generate_phonetic_address_key("URB LAS GLADIOLAS 150 CALLE FLAMBOYAN", "00926", "SAN JUAN") == "150|C400|00926"
    assert _pure_generate_phonetic_address_key("100 1/2 N MAIN ST NW", "78701", "AUSTIN") == "100 1/2|M500|78701"
    assert _pure_generate_phonetic_address_key("10 SOUTH ST", "02108", "BOSTON") == "10|S300|02108"
    assert _pure_generate_phonetic_address_key("10 NORTH EAST ST", "02108", "BOSTON") == "10|N630|02108"
    assert _pure_generate_phonetic_address_key("10 DOWNING ST", "SW1A 2AA", "LONDON") == "10|D552|SW1A 2AA"
    assert _pure_generate_phonetic_address_key("10 HAUPTSTRASSE", "", "BERLIN") == "10|H132|BERLIN"
    assert _pure_generate_phonetic_address_key("") is None
    assert _pure_generate_phonetic_address_key("   ") is None

    # Pure python core batch helper
    rec_res = pure_core_record(street1="100 Wall St", city="New York", state="NY", postal_code="10005")
    assert rec_res.street1 == "100 WALL ST"
    batch_res = pure_core_batch(
        [
            {"street1": "100 Wall St", "city": "New York", "state": "NY", "postal_code": "10005"},
            ("200 Park Ave", "Ste 1200", "New York", "NY", "10166", "USA"),
            "350 Fifth Ave, New York, NY 10118",
        ]
    )
    assert len(batch_res) == 3 and batch_res[0].street1 == "100 WALL ST"
    assert pure_core_batch([]) == []
