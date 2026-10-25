"""Comprehensive unit tests for international address grammars, postal validation, UPU formatting, scripts, and transliteration."""

from __future__ import annotations

import pytest

from entity_standardizer.address import (
    CountryRegistry,
    extract_postal_code,
    format_upu_address,
    standardize_address,
    validate_postal_code,
)
from entity_standardizer.address.international import (
    CountryGrammarRegistry,
    fold_to_ascii_key,
    format_eircode,
    is_valid_canadian_postal_code,
    is_valid_dutch_postcode,
    is_valid_eircode,
    is_valid_uk_postcode,
    normalize_to_canonical_unicode,
    register_default_grammars,
    split_intl_secondary_unit,
)
from entity_standardizer.address.international.commaless import (
    split_commaless_region_postal_city,
    town_set,
)
from entity_standardizer.address.international.gazetteer import known_city_suffix_length
from entity_standardizer.address.international.scripts import (
    country_matches_script,
    detect_script_country,
    split_script_single_line,
    strip_zero_width,
)
from entity_standardizer.address.transliterate import (
    TransliterationUnavailable,
    std_to_latin,
    transliterate,
)


@pytest.mark.parametrize(
    ("raw_kwargs", "expected_country", "expected_city_substr"),
    [
        # UK
        ({"street1": "10 Downing Street, Flat 2", "city": "London", "postal_code": "SW1A 2AA", "country": "GB"}, "GBR", "LONDON"),
        # Canada
        ({"street1": "200 Bay Street Suite 3000", "city": "Toronto", "state": "Ontario", "postal_code": "M5J2J5", "country": "CA"}, "CAN", "TORONTO"),
        # Germany (Germanic street + house number)
        ({"street1": "Friedrichstraße 123", "city": "Berlin", "postal_code": "10117", "country": "DE"}, "DEU", "BERLIN"),
        # Netherlands
        ({"street1": "Herengracht 501", "city": "Amsterdam", "postal_code": "1017BV", "country": "NL"}, "NLD", "AMSTERDAM"),
        # France (Romance)
        ({"street1": "29 Boulevard Haussmann", "city": "Paris", "postal_code": "75009", "country": "FR"}, "FRA", "PARIS"),
        # Spain
        ({"street1": "Calle de Alcalá 45, Piso 3", "city": "Madrid", "postal_code": "28014", "country": "ES"}, "ESP", "MADRID"),
        # Italy
        ({"street1": "Via Monte Napoleone 8", "city": "Milano", "state": "MI", "postal_code": "20121", "country": "IT"}, "ITA", "MILANO"),
        # Brazil (Latin America)
        ({"street1": "Avenida Paulista 1578, Conj 402", "city": "São Paulo", "state": "SP", "postal_code": "01310-200", "country": "BR"}, "BRA", "PAULO"),
        # Mexico
        ({"street1": "Av. Paseo de la Reforma 222, Col. Juárez", "city": "Ciudad de México", "state": "CDMX", "postal_code": "06600", "country": "MX"}, "MEX", "MEXICO"),
        # Poland (Eastern Europe)
        ({"street1": "ul. Marszałkowska 142 m. 5", "city": "Warszawa", "postal_code": "00-061", "country": "PL"}, "POL", "WARSZAWA"),
        # Czechia
        ({"street1": "Václavské náměstí 846/1", "city": "Praha", "postal_code": "110 00", "country": "CZ"}, "CZE", "PRAHA"),
        # Russia (Eurasia)
        ({"street1": "ул. Тверская, д. 7", "city": "Москва", "postal_code": "125009", "country": "RU"}, "RUS", ""),
        # Japan (CJK)
        ({"street1": "千代田区丸の内1-9-1", "city": "東京", "postal_code": "100-0005", "country": "JP"}, "JPN", ""),
        # South Korea
        ({"street1": "서울특별시 강남구 테헤란로 152", "postal_code": "06236", "country": "KR"}, "KOR", ""),
        # China
        ({"street1": "北京市朝阳区建国门外大街1号", "postal_code": "100004", "country": "CN"}, "CHN", ""),
        # Hong Kong
        ({"street1": "Flat 12A, 15/F, Tower 2, IFC, 8 Finance Street, Central", "city": "Hong Kong", "country": "HK"}, "HKG", "CENTRAL"),
        # Singapore
        ({"street1": "10 Bayfront Avenue #01-85", "city": "Singapore", "postal_code": "018956", "country": "SG"}, "SGP", "SINGAPORE"),
        # Australia
        ({"street1": "Level 25, 100 Barangaroo Avenue", "city": "Sydney", "state": "NSW", "postal_code": "2000", "country": "AU"}, "AUS", "SYDNEY"),
        # New Zealand
        ({"street1": "Unit 4, 15 Queen Street", "city": "Auckland", "postal_code": "1010", "country": "NZ"}, "NZL", "AUCKLAND"),
        # India
        ({"street1": "Plot 42, Bandra Kurla Complex, Bandra East", "city": "Mumbai", "state": "Maharashtra", "postal_code": "400051", "country": "IN"}, "IND", "MUMBAI"),
        # Ireland
        ({"street1": "70 Sir John Rogerson's Quay", "city": "Dublin 2", "postal_code": "D02R296", "country": "IE"}, "IRL", "DUBLIN"),
        # UAE (MENA)
        ({"street1": "Sheikh Zayed Road, PO Box 12345", "city": "Dubai", "country": "AE"}, "ARE", "DUBAI"),
        # Saudi Arabia
        ({"street1": "6813 Jabal Omar Makkah al Mukarramah 24231", "country": "SA"}, "SAU", "MAKKAH"),
        # South Africa
        ({"street1": "100 Maude Street, Sandton", "city": "Johannesburg", "postal_code": "2196", "country": "ZA"}, "ZAF", "JOHANNESBURG"),
        # Indonesia (Southeast Asia)
        ({"street1": "Jl. Jend. Sudirman Kav. 52-53", "city": "Jakarta Selatan", "postal_code": "12190", "country": "ID"}, "IDN", "JAKARTA"),
        # Cayman Islands (Offshore)
        ({"street1": "Ugland House, South Church Street, PO Box 309", "city": "George Town", "postal_code": "KY1-1104", "country": "KY"}, "CYM", "GEORGE TOWN"),
    ],
)
def test_international_grammars_end_to_end(
    raw_kwargs: dict, expected_country: str, expected_city_substr: str
) -> None:
    std = standardize_address(**raw_kwargs)
    assert std.country == expected_country
    assert std.address_status == "standardized"
    if expected_city_substr:
        assert expected_city_substr in fold_to_ascii_key(std.city)


def test_international_postal_validation_and_upu_formatting() -> None:
    register_default_grammars()
    assert CountryGrammarRegistry.get("GBR") is not None

    assert is_valid_uk_postcode("SW1A 2AA") is True
    assert is_valid_uk_postcode("INVALID") is False
    assert is_valid_canadian_postal_code("M5J 2J5") is True
    assert is_valid_canadian_postal_code("12345") is False
    assert is_valid_dutch_postcode("1017 BV") is True
    assert is_valid_dutch_postcode("0000 AA") is False
    assert is_valid_eircode("D02 R296") is True
    assert format_eircode("D02R296") == "D02 R296"

    assert validate_postal_code("10118-0110", "USA") is True
    assert validate_postal_code("m5j2j5", "CA") is True
    assert validate_postal_code("ABC", "USA") is False

    ext = extract_postal_code("10 Downing Street London SW1A 2AA", "GBR")
    assert ext == "SW1A 2AA"

    std_de = standardize_address("Friedrichstraße 123", city="Berlin", postal_code="10117", country="DE")
    upu = format_upu_address(std_de)
    assert "10117 BERLIN" in upu
    assert "GERMANY" in upu.upper()

    info = CountryRegistry.get("Switzerland")
    assert info is not None and info.alpha3 == "CHE"
    st_part, sec_part = split_intl_secondary_unit("Bahnhofstrasse 10 Apt 4", "")
    assert "BAHNHOFSTRASSE" in st_part.upper() and "4" in sec_part


def test_scripts_gazetteer_commaless_and_transliteration() -> None:
    assert normalize_to_canonical_unicode("  Cafe\u0301  ") == "Café"
    assert strip_zero_width("Hello\u200bWorld") == "HelloWorld"
    assert country_matches_script("JPN", "JPN") is True
    assert detect_script_country("東京都千代田区丸の内1-9-1") == "JPN"
    assert detect_script_country("北京市朝阳区建国门外大街1号") == "CHN"
    assert detect_script_country("서울특별시 강남구 테헤란로 152") == "KOR"
    assert detect_script_country("Москва, ул. Тверская 7") == "RUS"
    assert detect_script_country("Київ, вул. Хрещатик 1") == "UKR"
    assert detect_script_country("Αθήνα, Ερμού 10") == "GRC"
    assert detect_script_country("123 Main Street") is None

    jp_split = split_script_single_line("〒100-0005 東京都千代田区丸の内1-9-1", "JPN")
    assert jp_split is not None and jp_split[3] == "100-0005"
    cn_split = split_script_single_line("北京市朝阳区建国门外大街1号 100004", "CHN")
    assert cn_split is not None and cn_split[3] == "100004"
    kr_split = split_script_single_line("서울특별시 강남구 테헤란로 152 06236", "KOR")
    assert kr_split is not None and kr_split[3] == "06236"
    ru_split = split_script_single_line("г. Москва, ул. Тверская, д. 7, 125009", "RUS")
    assert ru_split is not None and ru_split[3] == "125009"

    # Gazetteer & commaless
    import re

    suffix_len = known_city_suffix_length("SAU", ["6813", "Jabal", "Omar", "Makkah", "al", "Mukarramah"])
    assert suffix_len == 3
    towns = town_set(["Wellington", "Trois-Rivières"])
    assert "TROIS RIVIERES" in towns
    cl = split_commaless_region_postal_city(
        "134 Willis Street Wellington 6011",
        lambda s: len(s) == 4 and s.isdigit(),
        None,
        towns,
        re.compile(r"(?!)"),
    )
    assert cl is not None and cl[1] == "Wellington" and cl[3] == "6011"

    # Transliteration
    assert transliterate("Москва") == "Moskva"
    assert transliterate("Αθήνα") == "Athina"
    assert transliterate("Zurich", script="latin") == "Zurich"
    assert transliterate("") == ""
    with pytest.raises(ValueError):
        transliterate("test", errors="invalid_mode")
    with pytest.raises(ValueError):
        transliterate("test", script="klingon")

    std_ru = standardize_address(street1="ул. Тверская 7", city="Москва", postal_code="125009", country="RU")
    latin_dict = std_to_latin(std_ru)
    assert "MOSKVA" in latin_dict["city"].upper()
    assert TransliterationUnavailable is not None
