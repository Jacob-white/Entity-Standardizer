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


def test_postal_formatting_validation_and_extraction_branches() -> None:
    from entity_standardizer.address.international import postal as pmod

    # Format helpers on canonical and non-canonical lengths
    assert pmod._format_uk("GIR0AA") == "GIR 0AA"
    assert pmod._format_uk("SW1A2AA") == "SW1A 2AA"
    assert pmod._format_uk("ABC") == "ABC"
    assert pmod._format_canada("M5J2J5") == "M5J 2J5"
    assert pmod._format_canada("M5J") == "M5J"
    assert pmod._format_netherlands("1017BV") == "1017 BV"
    assert pmod._format_netherlands("101") == "101"
    assert pmod._format_japan("1000005") == "100-0005"
    assert pmod._format_japan("100") == "100"
    assert pmod._format_poland("00026") == "00-026"
    assert pmod._format_poland("00") == "00"
    assert pmod._format_portugal("1000001") == "1000-001"
    assert pmod._format_portugal("1000") == "1000"
    assert pmod._format_brazil("01310100") == "01310-100"
    assert pmod._format_brazil("013") == "013"
    assert pmod._format_sweden("11135") == "111 35"
    assert pmod._format_sweden("111") == "111"
    assert pmod._format_czech_slovak("11000") == "110 00"
    assert pmod._format_czech_slovak("11") == "11"
    assert pmod._format_greece("10563") == "105 63"
    assert pmod._format_greece("10") == "10"
    assert pmod._format_usa("100051234") == "10005-1234"
    assert pmod._format_usa("10005") == "10005"
    assert pmod._format_saudi("115642341") == "11564-2341"
    assert pmod._format_saudi("11564") == "11564"
    assert pmod._format_korea("123456") == "123-456"
    assert pmod._format_korea("06236") == "06236"
    assert pmod._format_ireland("D02X285") == "D02 X285"
    assert pmod._format_ireland("D02") == "D02"
    assert pmod._format_cayman("CYM KY11104") == "KY1-1104"
    assert pmod._format_cayman("KY 1104") == "KY1-1104"
    assert pmod._format_cayman("1104") == "KY1-1104"
    assert pmod._format_cayman("KY91104") == "KY9-1104"
    assert pmod._format_cayman("XX") == "XX"
    assert pmod._format_vgb("VG1110") == "VG1110"
    assert pmod._format_vgb("1110") == "VG1110"
    assert pmod._format_vgb("XX") == "XX"
    assert pmod._format_malta("VLT1115") == "VLT 1115"
    assert pmod._format_malta("VLT") == "VLT"
    assert pmod._format_bermuda("HM11") == "HM 11"
    assert pmod._format_bermuda("HM") == "HM"

    # Semantic helpers
    assert pmod._validate_uk_semantics("GIR 0AA") is True
    assert pmod._validate_uk_semantics("NOT A CODE") is False
    assert pmod._validate_uk_semantics("QA1 1AA") is False
    assert pmod._validate_uk_semantics("AI1 1AA") is False
    assert pmod._validate_uk_semantics("SW1A 1CA") is False
    assert pmod._validate_dutch_semantics("1017 SA") is False
    assert pmod._validate_dutch_semantics("0123 AB") is False

    # validate_postal_code diagnostic branches
    assert validate_postal_code("10005", "UNKNOWN_COUNTRY", return_details=True).is_valid is False
    assert validate_postal_code("10005", "UNKNOWN_COUNTRY") is False
    assert validate_postal_code("", "ARE", return_details=True).is_non_postal_country is True
    assert validate_postal_code("00000", "ARE") is True
    assert validate_postal_code("", "USA", return_details=True).is_valid is False
    assert validate_postal_code("D-10115", "DEU", return_details=True).formatted_code == "10115"
    assert validate_postal_code("VG 1110", "VGB", return_details=True).formatted_code == "VG1110"
    assert validate_postal_code("KY 1104", "CYM", return_details=True).formatted_code == "KY1-1104"
    assert validate_postal_code("1104", "CYM", return_details=True).formatted_code == "KY1-1104"
    assert validate_postal_code("JE-2 3AB", "JEY", return_details=True).is_valid is True
    assert validate_postal_code("GY-1 1AA", "GGY", return_details=True).is_valid is True
    assert validate_postal_code("IM-1 1AA", "IMN", return_details=True).is_valid is True
    assert validate_postal_code("12A45", "USA", return_details=True).is_valid is False
    assert validate_postal_code("12@45", "USA", return_details=True).is_valid is False
    assert validate_postal_code("SW1@ 2AA", "GBR", return_details=True).is_valid is False
    assert validate_postal_code("12", "USA", return_details=True).is_valid is False
    assert validate_postal_code("123456789012", "USA", return_details=True).is_valid is False
    assert validate_postal_code("123456", "USA", return_details=True).is_valid is False
    assert validate_postal_code("QA1 1AA", "GBR", return_details=True).is_valid is False
    assert validate_postal_code("1017 SA", "NLD", return_details=True).is_valid is False

    # _extract_for_country and _extract_candidate_any branches
    assert extract_postal_code("", "USA") is None
    assert extract_postal_code("Dubai Internet City", "ARE") is None
    assert extract_postal_code("100 Main St", "NONEXISTENT_COUNTRY") is None
    assert extract_postal_code("100 King St W, Toronto M5X 1A9", "CAN") == "M5X 1A9"
    assert extract_postal_code("100 King St W, Toronto", "CAN") is None
    assert extract_postal_code("Keizersgracht 123, 1015 CJ Amsterdam", "NLD") == "1015 CJ"
    assert extract_postal_code("St Stephen's Green, Dublin D02 X285", "IRL") == "D02 X285"
    assert extract_postal_code("Chiyoda-ku, Tokyo 100-0005", "JPN") == "100-0005"
    assert extract_postal_code("Chiyoda-ku, Tokyo 1000005", "JPN") == "100-0005"
    assert extract_postal_code("Av Paulista 1578, CEP 01310-200", "BRA") == "01310-200"
    assert extract_postal_code("ul. Marszałkowska 1, 00-624 Warszawa", "POL") == "00-624"
    assert extract_postal_code("Av da Liberdade 100, 1250-146 Lisboa", "PRT") == "1250-146"
    assert extract_postal_code("Balcarce 50, C1064AAB Buenos Aires", "ARG") == "C1064AAB"
    assert extract_postal_code("1 Raffles Place S048616", "SGP") == "048616"
    assert extract_postal_code("1 Raffles Place 048616", "SGP") == "048616"
    assert extract_postal_code("200 George St NSW 2000", "AUS") == "2000"
    assert extract_postal_code("200 George St Sydney 2000", "AUS") == "2000"
    assert extract_postal_code("Road Town VG1110", "VGB") == "VG1110"
    assert extract_postal_code("Road Town 1110", "VGB") == "VG1110"
    assert extract_postal_code("George Town KY1-1104", "CYM") == "KY1-1104"
    assert extract_postal_code("George Town 1104", "CYM") == "KY1-1104"
    assert extract_postal_code("100 Wall St NY 10005-1234", "USA") == "10005-1234"
    assert extract_postal_code("100 Wall St 10005-1234", "USA") == "10005-1234"
    assert extract_postal_code("100 Wall St 10005", "USA") == "10005"
    assert extract_postal_code("Friedrichstr 10, D-10117 Berlin", "DEU") == "10117"
    assert extract_postal_code("Sveavägen 10, 111 57 Stockholm", "SWE") == "111 57"
    assert extract_postal_code("Nehru Place 110019", "IND") == "110019"
    assert extract_postal_code("Bahnhofstrasse 1, 8001 Zurich", "CHE") == "8001"
    assert extract_postal_code("Triq ir-Repubblika, VLT 1115 Valletta", "MLT") == "VLT 1115"

    # _extract_candidate_any (no country hint, no country detected)
    assert pmod._extract_candidate_any("Some street M5J 2J5") == "M5J 2J5"
    assert pmod._extract_candidate_any("Some street SW1A 2AA") == "SW1A 2AA"
    assert pmod._extract_candidate_any("Some street 1017 BV") == "1017 BV"
    assert pmod._extract_candidate_any("Some street D02 X285") == "D02 X285"
    assert pmod._extract_candidate_any("Some street 100-0005") == "100-0005"
    assert pmod._extract_candidate_any("Some street 01310-200") == "01310-200"
    assert pmod._extract_candidate_any("Some street 00-624") == "00-624"
    assert pmod._extract_candidate_any("Some street 1250-146") == "1250-146"
    assert pmod._extract_candidate_any("Some street C1064AAB") == "C1064AAB"
    assert pmod._extract_candidate_any("Some street 10005-1234") == "10005-1234"
    assert pmod._extract_candidate_any("Some street POSTCODE: AB123") == "AB123"
    assert pmod._extract_candidate_any("Some street D-10115") == "10115"
    assert pmod._extract_candidate_any("Some street XX 12345") == "12345"
    assert pmod._extract_candidate_any("Some street 12345") == "12345"
    assert pmod._extract_candidate_any("Some street 123456") == "123456"
    assert pmod._extract_candidate_any("Some street 1234") == "1234"
    assert pmod._extract_candidate_any("No numbers here at all") is None


def test_upu_eurasia_countries_and_base_grammars() -> None:
    from types import SimpleNamespace
    from entity_standardizer.address.international.base import (
        CountryGrammarRegistry,
        ParsedAddressComponents,
        UniversalInternationalGrammar,
        _postal_run,
        split_commaless_locality,
        split_intl_secondary_unit,
        split_single_line_locality,
    )
    from entity_standardizer.address.international.eurasia import EurasiaGrammar
    import entity_standardizer.address.transliterate as tmod

    # UPU layouts: non-postal, East Asian CJK & Romanized, European number-first & street-first, Anglo-Saxon
    np_obj = SimpleNamespace(
        country_iso3="ARE",
        building_name="BURJ KHALIFA",
        street1="1 SHEIKH MOHAMMED BIN RASHID BLVD",
        street2="LEVEL 120",
        dependent_locality="DOWNTOWN",
        city="DUBAI",
        state="DUBAI",
        postal_code="",
    )
    upu_are = format_upu_address(np_obj, recipient="ACME CORP", include_country_name=True)
    assert "ACME CORP" in upu_are and "BURJ KHALIFA" in upu_are and "UNITED ARAB EMIRATES" in upu_are

    jp_cjk = SimpleNamespace(
        country_iso3="JPN",
        building_name="六本木ヒルズ",
        street1="六本木6-10-1",
        street2="32F",
        dependent_locality="",
        city="港区",
        state="東京都",
        postal_code="106-6132",
    )
    assert "〒106-6132" in format_upu_address(jp_cjk)

    jp_rom = SimpleNamespace(
        country_iso3="JPN",
        building_name="",
        street1="6-10-1 ROPPONGI",
        street2="32F",
        dependent_locality="MINATO-KU",
        city="TOKYO",
        state="TOKYO",
        postal_code="106-6132",
    )
    assert "6-10-1 ROPPONGI" in format_upu_address(jp_rom, include_country_name=False)

    fr_obj = SimpleNamespace(
        country_iso3="FRA",
        building_name="TOUR FIRST",
        street_number="1",
        street_name="PLACE DES SAISONS",
        street1="PLACE DES SAISONS",
        street2="APT 4",
        dependent_locality="LA DEFENSE",
        city="PARIS",
        state="",
        postal_code="92400",
    )
    assert "1 PLACE DES SAISONS" in format_upu_address(fr_obj)

    us_obj = SimpleNamespace(
        country_iso3="USA",
        building_name="EMPIRE STATE BLDG",
        street1="350 5TH AVE",
        street2="STE 4200",
        dependent_locality="MIDTOWN",
        city="NEW YORK",
        state="NY",
        postal_code="10118",
    )
    assert "EMPIRE STATE BLDG" in format_upu_address(us_obj, recipient="JANE DOE")

    # EurasiaGrammar branches
    eg = EurasiaGrammar()
    assert eg._resolve_country_iso(None) == "TUR"
    assert eg._resolve_country_iso("TR") == "TUR"
    assert eg._resolve_country_iso("GEO") == "GEO"
    assert eg._resolve_country_iso("UNKNOWN") == "TUR"
    assert eg.normalize_postal_code("") == ""
    assert eg.normalize_postal_code(" 34710 ") == "34710"
    assert eg.extract_premise_and_thoroughfare("") == (None, None, None)
    assert eg.extract_premise_and_thoroughfare("Bağdat Cad. No: 154")[1] == "154"
    assert eg.extract_premise_and_thoroughfare("15 Rustaveli Ave")[1] == "15"
    assert eg.extract_premise_and_thoroughfare("Atatürk Bulvarı")[2] == "Atatürk Bulvarı"

    p_tr3 = eg.standardize(street1="Bağdat Caddesi No: 154 Daire: 8, Caferağa, Kadıköy/İstanbul 34710, Turkey")
    assert p_tr3.country_iso3 == "TUR" and p_tr3.postal_code == "34710" and p_tr3.unit_type is not None
    p_tr2 = eg.standardize(street1="Atatürk Blv. No: 10, Çankaya/Ankara 06420")
    assert p_tr2.city == "ANKARA" and p_tr2.dependent_locality == "ÇANKAYA"
    p_tr2_nopc = eg.standardize(street1="Rustaveli Ave 12, Tbilisi", country="GEO")
    assert p_tr2_nopc.country_iso3 == "GEO" and p_tr2_nopc.city == "TBILISI"

    # CountryRegistry lookup & detection branches
    assert CountryRegistry.get(None) is None
    assert CountryRegistry.get("   ") is None
    assert CountryRegistry.get("840").alpha3 == "USA"
    assert CountryRegistry.get("00036").alpha3 == "AUS"
    assert CountryRegistry.get("turkiye").alpha3 == "TUR"
    assert CountryRegistry.detect_country("100 Main St", country_hint="DE").alpha3 == "DEU"
    assert CountryRegistry.detect_country("") is None
    assert CountryRegistry.detect_country("Germany").alpha3 == "DEU"
    assert CountryRegistry.detect_country("100 Wall St, NY 10005").alpha3 == "USA"
    assert CountryRegistry.detect_country("10 Downing St, SW1A 2AA").alpha3 == "GBR"
    assert CountryRegistry.detect_country("100 King St, M5J 2J5").alpha3 == "CAN"
    assert CountryRegistry.detect_country("134 Willis St, Wellington, New Zealand").alpha3 == "NZL"
    assert CountryRegistry.detect_country("100 Main St, Paris, TX").alpha3 == "USA"
    assert CountryRegistry.detect_country("100 Main St, Paris Texas").alpha3 == "USA"
    assert CountryRegistry.detect_country("Bahnhofstrasse 10, Switzerland, 8001").alpha3 == "CHE"
    assert CountryRegistry.detect_country("Bahnhofstrasse 10, Zürich").alpha3 == "CHE"
    assert CountryRegistry.has_postal_codes("ARE") is False
    assert CountryRegistry.has_postal_codes("UNKNOWN_XYZ") is True
    assert len(CountryRegistry.all_countries()) >= 200
    assert "USA" in CountryRegistry.all_iso3()

    # base.py helpers & UniversalInternationalGrammar
    assert split_single_line_locality("Bahnhofstrasse 10, 8001, Zürich, Switzerland", "CHE") == (
        "Bahnhofstrasse 10",
        "Zürich",
        "8001",
    )
    assert split_single_line_locality("Bahnhofstrasse 10, Zürich, 8001", "CHE") == (
        "Bahnhofstrasse 10",
        "Zürich",
        "8001",
    )
    assert split_single_line_locality("OnlyOnePart", "CHE") is None
    assert _postal_run("1150 011", "PRT") == "1150 011"
    assert _postal_run("560 001", "IND") == "560 001"
    assert _postal_run("X5000", "ARG") == "X5000"
    assert _postal_run("1000", "PRT", prev="12", nxt="Lisboa") == "1000"

    assert split_commaless_locality("98 Hill Road Mumbai 400050", "IND") is not None
    assert split_commaless_locality("1054 Budapest Zoltán utca 16", "HUN") == (
        "Zoltán utca 16",
        "Budapest",
        "1054",
    )
    assert split_commaless_locality("25 شارع شريف باشا القاهرة 11511", "EGY") is not None
    assert split_commaless_locality("10 Soi Buakhao Pattaya 20150", "THA") is not None

    assert split_intl_secondary_unit("Flat 4A 150 High Street", "")[1].startswith("APT")
    assert split_intl_secondary_unit("8F 100 MAIN BLDG", "")[1].startswith("FL 8")
    assert split_intl_secondary_unit("9TH FLOOR WEST, 100 MAIN ST", "")[1].startswith("FL 9TH WEST")
    assert split_intl_secondary_unit("75 FORT STREET", "")[0] == "75 FORT ST"
    assert split_intl_secondary_unit("AL. JEROZOLIMSKIE 10", "")[0].startswith("AL.")
    assert split_intl_secondary_unit("10 SOUTH CHURCH STREET", "")[0] == "10 SOUTH CHURCH ST"
    assert split_intl_secondary_unit("AV. VALLARTA 1300", "", native_types=True)[0] == "AVE VALLARTA 1300"

    comp = ParsedAddressComponents(
        street_number="10",
        pre_directional="N",
        street_name="MAIN",
        street_type="ST",
        post_directional="W",
        building_name="TOWER 1",
        unit_type="STE",
        unit_number="200",
    )
    assert "TOWER 1" in comp.format_street1()
    assert comp.format_street2() == "STE 200"
    assert ParsedAddressComponents(unit_type="PENTHOUSE").format_street2() == "PENTHOUSE"
    assert ParsedAddressComponents(unit_number="4B").format_street2() == "4B"

    ug = UniversalInternationalGrammar()
    assert ug.normalize_postal_code("") == ""
    assert ug.extract_premise_and_thoroughfare("") == (None, None, None)
    assert ug.extract_premise_and_thoroughfare("Main Street")[2] == "Main Street"
    assert ug.standardize(street1="Koningin Astridln. 10, Antwerpen", country="BEL").city == "ANTWERPEN"
    assert ug.standardize(street1="100 Main St, PO Box 55, George Town, KY1-1104", country="CYM").unit_number is not None
    assert ug.standardize(street1="Suite 200, 75 Fort Street, George Town, KY1-1104", country="CYM").street_name == "75 FORT ST"
    assert ug.standardize(street1="100 Main St, 1000 Bruxelles, Brussels", country="BEL").city == "BRUXELLES"
    assert ug.standardize(street1="100 King St, Toronto, ON M5J 2J5", country="CAN").state == "ON"
    assert ug.standardize(street1="Toronto, ON M5J 2J5", country="CAN").city == "TORONTO"
    assert ug.standardize(street1="London, SW1A 2AA", country="GBR").city == "LONDON"
    assert ug.standardize(street1="1054 Budapest, Zoltán utca 16", country="HUN").city == "BUDAPEST"
    assert ug.standardize(street1="PARIS,", country="FRA").city == "PARIS"
    assert ug.standardize(street1="217/27 Moo 9 Beach Rd., Nongprue, Banglamung", city="Pattaya", country="THA").dependent_locality is not None

    assert CountryGrammarRegistry.has(None) is False
    assert CountryGrammarRegistry.has("GBR") is True
    assert "GBR" in CountryGrammarRegistry.supported_countries()
    assert CountryGrammarRegistry.detect_country(state_raw="Ontario") == "CAN"
    assert CountryGrammarRegistry.detect_country(country_raw="PRI") == "PRI"
    assert CountryGrammarRegistry.detect_country(city_raw="10115 Berlin") == "DEU"
    assert CountryGrammarRegistry.detect_country(city_raw="Berlin 10115") == "DEU"
    assert CountryGrammarRegistry.detect_country(city_raw="Zürich, 8001") == "CHE"
    assert CountryGrammarRegistry.detect_country(postal_raw="M5J 2J5") == "CAN"
    assert CountryGrammarRegistry.detect_country(postal_raw="SW1A 2AA") == "GBR"
    assert CountryGrammarRegistry.detect_country(raw_street="75 Fort St, Grand Cayman") == "CYM"
    assert CountryGrammarRegistry.detect_country(raw_street="10 Downing St, London, UK") == "GBR"
    assert CountryGrammarRegistry.detect_country(raw_street="100 King St, Toronto, Canada") == "CAN"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, Paris, TX, USA") == "USA"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, Paris, France") == "FRA"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, New Zealand") == "NZL"
    assert CountryGrammarRegistry.detect_country(raw_street="Bahnhofstrasse 1, Zürich") == "CHE"

    # transliterate._builtin fallback (when anyascii is absent)
    assert tmod._builtin("Ще Αθήνα Москва 123!", "passthrough") == "Shche Athina Moskva 123!"
    assert tmod._builtin("ЩЕ", "passthrough") == "SHCHE"
    assert tmod._builtin("中文", "passthrough") == "中文"
    with pytest.raises(TransliterationUnavailable):
        tmod._builtin("中文", "strict")


def test_regional_grammars_deep_branches() -> None:
    # Australia
    std_au1 = standardize_address("14 Gray Court Adelaide SA 5000", country="AU")
    assert std_au1.city == "ADELAIDE" and std_au1.state == "SA" and std_au1.postal_code == "5000"
    std_au2 = standardize_address("Tower 1, 100 George Street, Sydney NSW 2000, Australia", country="AU")
    assert std_au2.city == "SYDNEY" and std_au2.state == "NSW"
    std_au3 = standardize_address("L5/100 George Street", city="Sydney", postal_code="2000", country="AU")
    assert std_au3.state == "NSW" and "LEVEL" in std_au3.street2

    # Canada
    std_ca1 = standardize_address("683 Abbott Street Vancouver BC V6B 0J4", country="CA")
    assert std_ca1.city == "VANCOUVER" and std_ca1.state == "BC"
    std_ca2 = standardize_address("RR 2 Site 3 Box 4, Saskatoon, SK, S7K 3J5, Canada", country="CA")
    assert std_ca2.city == "SASKATOON" and std_ca2.state == "SK"
    std_ca3 = standardize_address("PO Box 123 Stn A, 200 Bay St, app. 4, Montreal, QC H3B 2Y5", country="CA")
    assert std_ca3.city == "MONTREAL" and std_ca3.state == "QC"

    # UK
    std_uk1 = standardize_address("Flat 3, 10 Downing Street, Westminster, London, SW1A 2AA, UK", country="GB")
    assert std_uk1.city == "LONDON" and std_uk1.postal_code == "SW1A 2AA"
    std_uk2 = standardize_address("Ground Floor Flat 1, 93, Queen Street, Leeds, LS1 2AJ", country="GB")
    assert std_uk2.city == "LEEDS"
    std_uk3 = standardize_address("14 High Street, Headingley", street2="Abbey House", city="Leeds", postal_code="LS6 2AA", country="GB")
    assert std_uk3.city == "LEEDS"

    # Ireland
    std_ie1 = standardize_address("Block B, Custom House Quay, IFSC, Dublin 1, Co. Dublin, D01 F5P2, Ireland", country="IE")
    assert std_ie1.city == "DUBLIN" and std_ie1.postal_code == "D01 F5P2"

    # CJK (Romanized & native)
    std_jp1 = standardize_address("Roppongi Hills Mori Tower 32F, 6-10-1 Roppongi, Minato-ku, Tokyo 106-6132, JPN", country="JP")
    assert std_jp1.country == "JPN" and std_jp1.postal_code == "106-6132"
    std_jp2 = standardize_address("106-6132 Tokyo Roppongi6-10-1", country="JP")
    assert std_jp2.country == "JPN"
    std_tw = standardize_address("110 台北市信義區信義路五段7號 台北101大樓 35樓", country="TW")
    assert std_tw.country == "TWN"

    # Eastern Europe
    std_pl = standardize_address("ul. Marszałkowska 10 m. 5, 00-624 Warszawa, Poland", country="PL")
    assert std_pl.country == "POL" and std_pl.postal_code == "00-624"
    std_hu = standardize_address("1054 Budapest, Zoltán utca 16, Hungary", country="HU")
    assert std_hu.country == "HUN" and std_hu.city == "BUDAPEST"
    std_ru = standardize_address("Москва, Пречистенская набережная, 9", country="RU")
    assert std_ru.country == "RUS"

    # Latin America
    std_mx = standardize_address("Av. Insurgentes Sur 1602, Col. Crédito Constructor, MZ 4 LT 2, Int. 401, 03940 Ciudad de México, CDMX, Mexico", country="MX")
    assert std_mx.country == "MEX" and std_mx.postal_code == "03940"
    std_br = standardize_address("Avenida Paulista, 1578 - Bela Vista, 01310-200, São Paulo - SP, Brasil", country="BR")
    assert std_br.country == "BRA" and std_br.state == "SP"
    std_co = standardize_address("Carrera 7 # 71-21, Chapinero, Bogotá 110221, Colombia", country="CO")
    assert std_co.country == "COL"

    # Offshore
    std_ky = standardize_address("Ugland House, South Church Street, PO Box 309, KY1-1104, George Town, Grand Cayman, Cayman Islands", country="KY")
    assert std_ky.country == "CYM" and std_ky.postal_code == "KY1-1104"
    std_pa = standardize_address("Torre de las Américas, Calle 50, Apartado 0816-0108, Panama City, Panama", country="PA")
    assert std_pa.country == "PAN"

    # MENA & Africa
    std_ae = standardize_address("Sheikh Zayed Road PO Box 500001, Office 5, Trade Centre 1, Dubai, United Arab Emirates", country="AE")
    assert std_ae.country == "ARE" and std_ae.city == "DUBAI"
    std_za = standardize_address("100 Sandton Drive, Sandton, Johannesburg 2196, Gauteng, South Africa", country="ZA")
    assert std_za.country == "ZAF" and std_za.postal_code == "2196"

    # Hong Kong, India, Southeast Asia, Singapore, Romance, Germanic
    std_hk = standardize_address("Flat A, 12/F, Two International Finance Centre, 8 Finance Street, Central, Hong Kong", country="HK")
    assert std_hk.country == "HKG"
    std_in = standardize_address("Plot 12, SEZ Unit 4, Bandra Kurla Complex, Bandra, Mumbai, Maharashtra 400 051, India", country="IN")
    assert std_in.country == "IND" and std_in.postal_code == "400051"
    std_id = standardize_address("Jalan KH Wahid Hasyim No. 189, Kebon Kacang, Tanah Abang, Central Jakarta 10240, Indonesia", country="ID")
    assert std_id.country == "IDN" and std_id.postal_code == "10240"
    std_my = standardize_address("12 Jalan Ampang, Golden Triangle", city="Kuala Lumpur", postal_code="50450", country="MY")
    assert std_my.country == "MYS" and std_my.state != ""
    std_sg = standardize_address("Marina Bay Sands, 10 Bayfront Avenue, #08-01, Singapore 018956", country="SG")
    assert std_sg.country == "SGP" and std_sg.postal_code == "018956"
    std_fr = standardize_address("142 Boulevard Saint-Germain, Quartier Latin, 75006 Paris, France", country="FR")
    assert std_fr.country == "FRA" and std_fr.postal_code == "75006"
    std_dk = standardize_address("Vesterbrogade 45, 2. tv., 1620 København, Denmark", country="DK")
    assert std_dk.country == "DNK" and std_dk.postal_code == "1620"
    std_de_pf = standardize_address("Postfach 309 Zimmer 100, 10115 Berlin, Germany", country="DE")
    assert std_de_pf.country == "DEU" and "POSTFACH" in std_de_pf.street1
    std_nl_add = standardize_address("Keizersgracht 421-B, 1016 EK Amsterdam, Netherlands", country="NL")
    assert std_nl_add.country == "NLD" and std_nl_add.street2 == "APT B"


def test_cjk_uk_ireland_offshore_eastern_europe_hk_romance_branches() -> None:
    from entity_standardizer.address.international.cjk import CJKGrammar
    from entity_standardizer.address.international.eastern_europe import (
        EasternEuropeGrammar,
        split_cyrillic_locality,
    )
    from entity_standardizer.address.international.hong_kong import HongKongGrammar
    from entity_standardizer.address.international.ireland import (
        IrelandGrammar,
        IrelandParsedAddressComponents,
        format_eircode,
        is_valid_eircode,
    )
    from entity_standardizer.address.international.offshore import OffshoreGrammar
    from entity_standardizer.address.international.romance import (
        RE_ROMANCE_SEC,
        RomanceGrammar,
        expand_italian_street_abbreviation,
        parse_street2_unit,
    )
    from entity_standardizer.address.international.uk import UKGrammar

    # 1. CJKGrammar branches
    cjk = CJKGrammar()
    # 2-part and 1-part comma addresses & 3+ part with leading number
    assert cjk.standardize(street1="6-10-1 Roppongi, Tokyo", country="JPN").city == "TOKYO"
    assert cjk.standardize(street1="100 Nanjing Road, Huangpu, Shanghai, China", country="CHN").city is not None
    # Single-line Romaji with trailing postal code and city prefix
    assert cjk.standardize(street1="Tokyo Roppongi6-10-1 106-6132", country="JPN").postal_code == "106-6132"
    assert cjk.standardize(street1="Roppongi 6-10-1 106-6132", country="JPN").postal_code == "106-6132"
    # Native CJK whitespace-delimited tokens (JP, KR, CN, TW)
    assert cjk.standardize(street1="〒106-6132 東京都 港区 六本木 6-10-1 森タワー 32階", country="JPN").postal_code == "106-6132"
    assert cjk.standardize(street1="서울특별시 강남구 테헤란로 152 강남파이낸스센터 10층", country="KOR").city is not None
    assert cjk.standardize(street1="서울특별시 주흥길 78", country="KOR").city == "서울특별시"
    assert cjk.standardize(street1="105 台北市 復興北路231巷34", country="TWN").postal_code == "105"
    assert cjk.standardize(street1="北京市 海淀区 中关村南大街1号 海淀大厦 501室", country="CHN").unit_number is not None
    # Contiguous CJK hierarchies (JP, CN province, KR, TW) + tail tokens
    assert cjk.standardize(street1="東京都港区六本木6-10-1 六本木ヒルズ 3201室 106-6132", country="JPN").postal_code == "106-6132"
    assert cjk.standardize(street1="广东省深圳市南山区科技南十二路18号", street2="502室", country="CHN").unit_number in ("502", "502室")
    assert cjk.standardize(street1="서울특별시강남구테헤란로 152 06236", street2="10F", country="KOR").postal_code == "06236"
    assert cjk.standardize(street1="台北市信義區信義路五段7號8樓", country="TWN").unit_number is not None
    assert cjk.standardize(street1="6-10-1 Roppongi, Suite 500", city="Tokyo", country="JPN").street_name is not None

    # 2. UKGrammar branches
    uk = UKGrammar()
    assert uk.extract_premise_and_thoroughfare("") == (None, None, None)
    assert uk.extract_premise_and_thoroughfare("Abbey House, 10 High Street") == ("ABBEY HOUSE", "10", "HIGH ST")
    assert uk.extract_premise_and_thoroughfare("10 High Street, Extra") == (None, "10", "HIGH ST EXTRA")
    assert uk.extract_premise_and_thoroughfare("GDN")[2] is None
    assert uk._normalize_street_tokens("") == ""
    assert "RD" in uk._normalize_street_tokens("Stratford-upon-Road North-West")
    assert uk.standardize(street1="Flat 2, SW1A 2AA", country="GBR").postal_code == "SW1A 2AA"
    assert uk.standardize(street1="London, SW1A 2AA", country="GBR").city == "LONDON"
    assert uk.standardize(street1="10, Downing Street, SW1A 2AA", country="GBR").street_number == "10"
    assert uk.standardize(street1="Abbey House, 10 Downing Street, London, SW1A 2AA", country="GBR").building_name == "ABBEY HOUSE"
    assert uk.standardize(street1="10 High St", street2="Flat 4, Abbey House", city="London", country="GBR").building_name == "ABBEY HOUSE"
    assert uk.standardize(street1="10 High St", street2="Flat 4, Westminster", city="London", country="GBR").dependent_locality == "WESTMINSTER"
    assert uk.standardize(street1="10 High St", street2="Westminster", city="London", country="GBR").dependent_locality == "WESTMINSTER"
    assert uk.standardize(street1="Flats 1 & 2, 10 High Street", city="London", country="GBR").unit_number == "1 & 2"
    assert uk.standardize(street1="Flat 3 (A)", city="London", country="GBR").unit_number == "3A"
    assert uk.standardize(street1="3rd Floor West, 10 High Street", city="London", country="GBR").unit_number == "3RD WEST"
    assert uk.standardize(street1="2nd Floor, Flat", city="London", country="GBR").unit_type == "APT"
    assert uk.standardize(street1="PO Box 100, 10 High Street", city="London", country="GBR").unit_type == "PO BOX"
    assert uk.standardize(street1="Suite 5 B", city="London", country="GBR").unit_number == "5B"
    assert uk.standardize(street1="Suite 500", city="London", country="GBR").unit_number == "500"

    # 3. IrelandGrammar branches
    ie = IrelandGrammar()
    assert is_valid_eircode(None) is False
    assert is_valid_eircode("SHORT") is False
    assert is_valid_eircode("1234567") is False
    assert is_valid_eircode("D02 X285") is True
    assert format_eircode("") == ""
    assert format_eircode("D02X285") == "D02 X285"
    assert format_eircode(" Dublin D02 X285 ") == "D02 X285"
    assert format_eircode("INVALID") == "INVALID"

    ie_c1 = IrelandParsedAddressComponents(
        street_number="10",
        pre_directional="N",
        street_name="CUSTOM HOUSE",
        street_type="QUAY",
        post_directional="E",
        building_name="IFSC HOUSE",
        unit_type="UNIT",
        unit_number="4",
    )
    assert "10 N CUSTOM HOUSE QUAY E" == ie_c1.format_street1()
    assert "UNIT 4 IFSC HOUSE" == ie_c1.format_street2()
    ie_c2 = IrelandParsedAddressComponents(street_name="12", unit_type="APT", unit_number="3", building_name="BLOCK A")
    assert ie_c2.format_street1() == "12 APT 3" and ie_c2.format_street2() == "BLOCK A"
    ie_c3 = IrelandParsedAddressComponents(street_number="12", unit_type="APT", unit_number="3")
    assert ie_c3.format_street1() == "12 APT 3" and ie_c3.format_street2() == ""

    assert ie.extract_premise_and_thoroughfare("") == (None, None, None)
    assert ie.extract_premise_and_thoroughfare("Treasury Building, 10 Grand Canal Street Lower")[0] == "TREASURY BUILDING"
    assert ie.extract_premise_and_thoroughfare("12")[2] is None
    assert ie._normalize_street_tokens("") == ""
    assert "QUAY" in ie._normalize_street_tokens("Custom House Quays Lower Upper North")
    assert ie.standardize(street1="9 High Street Galway H91 KW97", country="IRL").city == "GALWAY"
    assert ie.standardize(street1="10 Patrick St", state="County Cork", postal_code="T12 AB12", country="IRL").state == "CO CORK"
    assert ie.standardize(street1="Treasury Bldg, 10 Grand Canal St, Flat 2, Grand Canal Dock, Dublin 2, D02 X285, Ireland", country="IRL").city == "DUBLIN"
    assert ie.standardize(street1="10 Custom House Quay Block A IFSC", city="Dublin 1", country="IRL").dependent_locality == "IFSC"
    assert ie.standardize(street1="10 Grafton St", street2="Suite 5", postal_code="D02 X285", country="IRL").city == "DUBLIN"

    # 4. OffshoreGrammar branches
    off = OffshoreGrammar()
    assert off.normalize_postal_code("") == ""
    assert off.normalize_postal_code("VG1110") == "VG1110"
    assert off.normalize_postal_code("HM12") == "HM 12"
    assert off.normalize_postal_code("0816") == "KY1-0816"
    assert off.normalize_postal_code("PAN-0816") == "PAN-0816"
    assert off.extract_premise_and_thoroughfare("") == (None, None, None)
    assert off.extract_premise_and_thoroughfare("Maples, LLC, 10 Fort Street")[0] == "MAPLES, LLC"
    assert off.extract_premise_and_thoroughfare("Maples, LLC") == (None, None, None)
    assert off.extract_premise_and_thoroughfare("Ugland House 10 South Church Street")[0] == "UGLAND HOUSE"
    assert off._normalize_street_tokens("") == ""
    assert off.standardize(street1="15 Harbour Drive, Road Town, Tortola, VG1110, BVI", country="VGB").city == "ROAD TOWN"
    assert off.standardize(street1="PO Box 309, KY1-1104", country="CYM").unit_type == "PO BOX"
    assert off.standardize(street1="10 Fort St", street2="PO Box 309", city="George Town", country="CYM").unit_type == "PO BOX"
    assert off.standardize(street1="Calle 50", street2="Apartado 0816", city="Panama City", country="PAN").unit_type == "APARTADO"
    assert off.standardize(street1="PO Box 309", street2="Suite 100", city="George Town", country="CYM").street_name == "PO BOX 309"
    assert off.standardize(street1="10 Fort St Apartado 55", city="Panama City", country="PAN").unit_type == "APARTADO"

    # 5. EasternEuropeGrammar branches
    ee = EasternEuropeGrammar()
    assert split_cyrillic_locality("101000 Москва улица Ленина 5") == ("101000", "Москва", "улица Ленина 5")
    assert split_cyrillic_locality("Санкт-Петербург Невский проспект 10")[1] == "Санкт-Петербург"
    assert split_cyrillic_locality("Пречистенская набережная, 9") == ("", "", "Пречистенская набережная, 9")
    assert split_cyrillic_locality("БезТипаУлицы 10") == ("", "", "БезТипаУлицы 10")

    assert ee.normalize_postal_code("") == ""
    assert ee.normalize_postal_code("PL-00-950") == "00-950"
    assert ee.normalize_postal_code("CZ-110 00") == "110 00"
    assert ee.normalize_postal_code("010011") == "010011"
    assert ee.normalize_postal_code("1000") == "1000"
    assert ee.normalize_postal_code("11000") == "11000"
    assert ee.extract_premise_and_thoroughfare("") == (None, None, None)
    assert ee.extract_premise_and_thoroughfare("91, M. Alexandrou Str.")[1] == "91"
    assert ee.extract_premise_and_thoroughfare("12") == (None, None, None)
    for code in ("POL", "HUN", "CZE", "ROU", "GRC", "BGR", "SRB", "UKR", "RUS", "EST", "UNKNOWN"):
        assert len(ee._resolve_country_iso(code)) == 3
    assert ee._resolve_country_iso(None) == "POL"

    assert ee.standardize(street1="ul. Marszałkowska, 12, lok. 4, Warszawa 00-624, Poland", country="POL").postal_code == "00-624"
    assert ee.standardize(street1="00-950 Warszawa", country="POL").postal_code == "00-950"
    assert ee.standardize(street1="101000 Москва улица Тверская 10", street2="кв. 5", country="RUS").city is not None
    assert ee.standardize(street1="ul. Długa 5 00-950", city="00-950 Warszawa", postal_code="00950", country="POL").postal_code == "00-950"
    assert ee.standardize(street1="Václavské náměstí 1", city="Praha", postal_code="11000", country="CZE").postal_code == "110 00"

    # 6. HongKongGrammar branches
    hk = HongKongGrammar()
    assert hk.normalize_postal_code("") == ""
    assert hk.normalize_postal_code("999077") == ""
    assert hk.normalize_postal_code("12345") == ""
    assert hk.extract_premise_and_thoroughfare("") == (None, None, None)
    assert hk.extract_premise_and_thoroughfare("TWO INTERNATIONAL FINANCE CENTRE") == ("TWO INTERNATIONAL FINANCE CENTRE", None, None)
    assert hk.extract_premise_and_thoroughfare("TWO INTERNATIONAL FINANCE CENTRE, FINANCE STREET")[0] == "TWO INTERNATIONAL FINANCE CENTRE"
    assert hk.extract_premise_and_thoroughfare("Cheung Kong Center, Queen's Road Central")[0] == "CHEUNG KONG CENTER"
    assert hk.extract_premise_and_thoroughfare("Cheung Kong Center")[0] == "CHEUNG KONG CENTER"
    assert hk.standardize(street1="Flat A, 12F, 8 Finance Street, Central", country="HKG").unit_number is not None
    assert hk.standardize(street1="Flat A, 12th Floor, 8 Finance Street, Central", country="HKG").unit_number is not None
    assert hk.standardize(street1="12F, Room 301, 8 Finance Street, Central", country="HKG").unit_number is not None
    assert hk.standardize(street1="12th Floor, Room 301, 8 Finance Street, Central", country="HKG").unit_number is not None
    assert hk.standardize(street1="Level 8, 100 Nathan Road, Tsim Sha Tsui", country="HKG").city == "TSIM SHA TSUI"
    assert hk.standardize(street1="8th Floor, 10 Sha Tin Centre Street, Sha Tin", country="HKG").city == "SHA TIN"
    assert hk.standardize(street1="Room 101, 2 Queen's Road Central", city="Tsim Sha Tsui", country="HKG").city == "TSIM SHA TSUI"
    assert hk.standardize(street1="8 Finance Street", street2="Suite 500", city="Kowloon", state="Central", country="HKG").unit_type == "STE"

    # 7. RomanceGrammar branches
    rom = RomanceGrammar()
    assert parse_street2_unit("", RE_ROMANCE_SEC) == (None, None)
    assert parse_street2_unit("3ème étage, 2º B, Bât. A", RE_ROMANCE_SEC)[1] is not None
    assert parse_street2_unit("3ème étage", RE_ROMANCE_SEC) == (None, "ETAGE 3")
    assert parse_street2_unit("Apto 32", RE_ROMANCE_SEC) == ("APTO", "32")
    assert parse_street2_unit("2º B", RE_ROMANCE_SEC) == (None, "2 B")
    assert expand_italian_street_abbreviation("V. Dante 53") == "Via Dante 53"
    assert expand_italian_street_abbreviation("Via Dante 53") == "Via Dante 53"
    assert rom.normalize_postal_code("") == ""
    assert rom.normalize_postal_code("01310200") == "01310-200"
    assert rom.normalize_postal_code("1150 011") == "1150-011"
    assert rom.extract_premise_and_thoroughfare("") == (None, None, None)
    assert rom.extract_premise_and_thoroughfare("Calle 72 No. 10-07")[2] == "CALLE 72 NO. 10-07"
    assert rom.standardize(street1="V. Dante 53, 20121 Milano, MI, Italy", country="ITA").city == "MILANO"
    assert rom.standardize(street1="Rua Augusta 100 - Consolação, 01305-100, São Paulo - SP", country="PRT").state == "SP"
    assert rom.standardize(street1="Calle Mayor 45, 28013 Madrid", street2="Piso 2", country="ESP").city == "MADRID"


def test_international_grammars_exhaustive_coverage() -> None:
    from entity_standardizer.address.international.australia import (
        AustraliaGrammar,
        _au_region_suffix,
        _postcode_in_state,
    )
    from entity_standardizer.address.international.base import (
        CountryGrammarRegistry,
        ParsedAddressComponents,
        UniversalInternationalGrammar,
        split_commaless_locality,
        split_intl_secondary_unit,
        split_single_line_locality,
    )
    from entity_standardizer.address.international.canada import (
        CanadaGrammar,
        _can_region_suffix,
    )
    from entity_standardizer.address.international.cjk import (
        CJKGrammar,
        separate_house_number,
        split_jp_tokens,
        strip_trailing_country,
    )
    from entity_standardizer.address.international.latin_america import LatinAmericaGrammar
    from entity_standardizer.address.international.mena_africa import (
        MenaAfricaGrammar,
        normalize_po_box_str,
    )
    from entity_standardizer.address.international.uk import (
        UKGrammar,
        UKParsedAddressComponents,
        is_uk_building_name,
        is_valid_uk_postcode,
        split_commaless_postal_city,
        split_po_box_unit,
    )

    # 1. AustraliaGrammar exhaustive branches
    au = AustraliaGrammar()
    assert _postcode_in_state("", "NSW") is False
    assert _au_region_suffix(["10", "MAIN", "ST", "MOUNT", "VICTORIA"], "3000") is None
    assert _au_region_suffix(["10", "MAIN", "ST", "SYDNEY", "UNKNOWN"], "2000") is None
    assert au.normalize_postal_code("800") == "0800"
    assert au.normalize_postal_code("Unit 1, NSW 2000") == "2000"
    assert au.normalize_postal_code("ABC") == ""
    assert au.validate_postcode_state("2000", "NSW") is True
    assert au.validate_postcode_state("3000", "NSW") is False
    assert au.extract_premise_and_thoroughfare("") == (None, None, None)
    assert au.extract_premise_and_thoroughfare("5/100 GEORGE ST")[1] == "5"
    assert au.extract_premise_and_thoroughfare("GEORGE ST") == (None, None, "GEORGE ST")
    assert au.parse([], {"street1": "", "street2": "100 George St N", "city": "Sydney", "state": "NSW", "postal_code": "2000"}).street_name == "GEORGE ST N"
    assert au.parse([], {"street1": "12 George St, AUSTRALIA"}).street_number == "12"
    assert au.parse([], {"street1": "12 George St, NSW 2000"}).state == "NSW"
    assert au.parse([], {"street1": "12 George St 2000"}).postal_code == "2000"
    assert au.parse([], {"street1": "STE 5/100 GEORGE ST", "city": "Sydney", "postal_code": "2000"}).unit_type == "STE"
    assert au.parse([], {"street1": "APT 5/100 GEORGE ST", "city": "Sydney", "postal_code": "2000"}).unit_type == "APT"
    assert au.parse([], {"street1": "5/100 GEORGE ST", "city": "Sydney", "postal_code": "2000"}).unit_type == "UNIT"
    assert au.parse([], {"street1": "100 GEORGE ST LEVEL 15", "city": "Sydney", "postal_code": "2000"}).unit_type == "LEVEL"
    assert au.parse([], {"street1": "100 GEORGE ST, SYDNEY, NSW", "postal_code": "2000"}).city == "SYDNEY"

    # 2. CanadaGrammar exhaustive branches
    ca = CanadaGrammar()
    assert _can_region_suffix(["100", "MAIN", "ST", "TORONTO"], "M5J 2J5") is None
    assert ca.normalize_postal_code("") == ""
    assert ca.normalize_postal_code("INVALID") == "INVALID"
    assert ca.extract_premise_and_thoroughfare("Rue Saint-Denis Ouest")[2] == "RUE SAINT-DENIS O"
    assert ca.extract_premise_and_thoroughfare("Rue Saint-Denis North")[2] == "RUE SAINT-DENIS N"
    assert ca._normalize_bilingual_street("") == ""
    assert ca._normalize_bilingual_street("   ") == ""
    assert ca._normalize_bilingual_street("King Street West") == "KING ST W"
    assert ca._normalize_bilingual_street("King Street Ouest") == "KING ST O"
    assert ca.parse([], {"street1": "100 King St, Toronto, NotAProv M5J 2J5"}).city == "NOTAPROV M5J 2J5"
    assert ca.parse([], {"street1": "100 King St, Toronto, Ontario"}).state == "ON"
    assert ca.parse([], {"street1": "100 Spring Garden Rd, Nova Scotia, Halifax B3J 3R4"}).city == "HALIFAX"
    assert ca.parse([], {"street1": "100 King St, Toronto"}).city == "TORONTO"
    assert ca.parse([], {"street1": "100 King St,"}).street_name == "KING ST"
    assert ca.parse([], {"street1": "100 King St ON M5J 2J5", "city": "Toronto"}).state == "ON"
    assert ca.parse([], {"street1": "100 Rue Peel", "street2": "bureau 200", "city": "Montreal"}).unit_type == "STE"
    assert ca.parse([], {"street1": "100 King St PO Box 55", "city": "Toronto"}).unit_type == "PO"

    # 3. international/base.py exhaustive branches
    assert split_single_line_locality("Switzerland, Switzerland", "CHE") is None
    assert split_single_line_locality("8001, Zürich", "CHE") is None
    assert split_single_line_locality("Bahnhofstrasse 10, 8001, Zürich", "CHE") == ("Bahnhofstrasse 10", "Zürich", "8001")
    assert split_commaless_locality("Zurich", "CHE") is None
    assert split_commaless_locality("1054 Budapest", "HUN") is None
    assert split_commaless_locality("1054 Budapest Unknownword", "HUN") is None
    assert split_commaless_locality("12 شارع الملك فهد الرياض 11564", "SAU") is not None
    assert split_commaless_locality("10 Thanon Sukhumvit Bangkok 10110", "THA") is not None
    assert split_commaless_locality("10 ถนนสุขุมวิท Bangkok 10110", "THA") is not None
    assert split_commaless_locality("12 High Road Zurich 8001", "CHE") is not None
    assert split_commaless_locality("Bahnhofstrasse 10 Zürich 8001", "CHE") is not None

    assert split_intl_secondary_unit("Suite 400", "") == ("", "STE 400")
    assert split_intl_secondary_unit("Apt 5, 100 Main St", "")[1] == "APT 5"
    assert "BLDG B" in split_intl_secondary_unit("100 Main St Apt 5", "Bldg B")[1]

    assert ParsedAddressComponents(street_number="10", street_name="MAIN ST", street_type="ST", post_directional="W").format_street1() == "10 MAIN ST W"
    assert ParsedAddressComponents(unit_type="BSMT").format_street2() == "BSMT"
    assert ParsedAddressComponents(unit_number="5B").format_street2() == "5B"
    assert ParsedAddressComponents(building_name="TOWER ONE").format_street1() == "TOWER ONE"

    ug = UniversalInternationalGrammar()
    assert ug.extract_premise_and_thoroughfare("12A Bahnhofstrasse") == (None, "12A", "Bahnhofstrasse")
    assert ug.standardize(street1="100 Main St, Suite 200", city="George Town", country="CYM").unit_type == "STE"
    assert ug.standardize(street1="Bahnhofstrasse 10, 8001 Zürich, ZH", country="ARE").city == "ZH"
    assert ug.standardize(street1="10 Bahnhofstrasse, 8001 Zürich, ZH", country="ARE").postal_code == "8001"
    assert ug.standardize(street1="1054 Budapest, Kossuth Lajos tér 1", country="HUN").postal_code == "1054"

    assert CountryGrammarRegistry.detect_country(country_raw="UNKNOWN_COUNTRY_XYZ") == "USA"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, NY 10005") == "USA"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, Austin, TX") == "USA"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, Austin Texas") == "USA"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, 75001, France") == "FRA"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, U.A.E., Extra") == "ARE"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St New Zealand") == "NZL"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St France") == "FRA"
    assert CountryGrammarRegistry.detect_country(raw_street="Bahnhofstrasse 1, Zürich") == "CHE"

    # 4. MenaAfricaGrammar exhaustive branches
    assert normalize_po_box_str("P.O. Box 12345") == "PO BOX 12345"
    assert normalize_po_box_str("Regular Street") == "Regular Street"
    ma = MenaAfricaGrammar()
    assert ma._resolve_country_iso(None) == "ARE"
    assert ma._resolve_country_iso("السعودية") == "SAU"
    assert ma._resolve_country_iso("MAR") == "MAR"
    assert ma._resolve_country_iso("UNKNOWN") == "ARE"
    assert ma.normalize_postal_code("") == ""
    assert ma.normalize_postal_code("12345-6789") == "12345-6789"
    assert ma.normalize_postal_code("2196") == "2196"
    assert ma.extract_premise_and_thoroughfare("") == (None, None, None)
    assert ma.extract_premise_and_thoroughfare("PO Box 12345")[2] == "PO BOX 12345"
    assert ma.extract_premise_and_thoroughfare("Plot 42 Victoria Island")[1] == "42"
    assert ma.extract_premise_and_thoroughfare("7543 King Fahd Road")[1] == "7543"
    assert ma.extract_premise_and_thoroughfare("Sheikh Zayed Road")[2] == "Sheikh Zayed Road"
    assert ma.parse([], {"street1": "100 Sandton Drive, Sandton, Johannesburg 2196, Gauteng, South Africa", "country": "ZAF"}).state == "GAUTENG"
    assert ma.parse([], {"street1": "100 Maude St, Sandton, Johannesburg, South Africa", "country": "ZAF"}).city == "JOHANNESBURG"
    assert ma.parse([], {"street1": "100 Maude St, Johannesburg 2196", "country": "ZAF"}).postal_code == "2196"
    assert ma.parse([], {"street1": "Sheikh Zayed Road PO Box 5, Office 204, 12345, Dubai", "country": "ARE"}).unit_number is not None
    assert ma.parse([], {"street1": "Dubai, UAE", "country": "ARE"}).city == "DUBAI"
    assert ma.parse([], {"street1": "PO Box 12345, 12345", "country": "ARE"}).street_name == "PO BOX 12345"
    assert ma.parse([], {"street1": "Sheikh Zayed Road", "street2": "PO Box 12345", "city": "Dubai", "country": "ARE"}).unit_number == "PO BOX 12345"
    assert ma.parse([], {"street1": "Sheikh Zayed Road", "street2": "Office 204", "city": "Dubai", "country": "ARE"}).unit_number == "OFFICE 204"
    assert ma.parse([], {"street1": "Sheikh Zayed Road PO Box 12345", "street2": "Office 204", "city": "Dubai", "country": "ARE"}).unit_number == "PO BOX 12345, OFFICE 204"
    assert ma.parse([], {"street1": "", "street2": "PO Box 12345", "city": "Dubai", "country": "ARE"}).street_name == "PO BOX 12345"
    assert ma.parse([], {"street1": "Sheikh Zayed Road Suite 200", "city": "Dubai", "country": "ARE"}).unit_type == "STE"

    # 5. LatinAmericaGrammar exhaustive branches
    la = LatinAmericaGrammar()
    assert la._resolve_country_iso(None) == "MEX"
    assert la._resolve_country_iso("UNKNOWN") == "MEX"
    assert la.normalize_postal_code("") == ""
    assert la.normalize_postal_code("01310200") == "01310-200"
    assert la.normalize_postal_code("C1064AAB") == "C1064AAB"
    assert la.normalize_postal_code("1064") == "1064"
    assert la.extract_premise_and_thoroughfare("") == (None, None, None)
    assert la.extract_premise_and_thoroughfare("Calle 72 No. 10-07")[2] == "CALLE 72 NO. 10-07"
    assert la.extract_premise_and_thoroughfare("Av. Javier Prado 100", country_iso="PER")[2] == "AVE JAVIER PRADO 100"
    assert la.extract_premise_and_thoroughfare("Torre Mayor, Paseo de la Reforma 505")[2] is not None
    assert la.parse([], {"street1": "Av. Paulista, 100 - Bela Vista, Curitiba - Paraná, Brasil", "country": "BRA"}).state == "PR"
    assert la.parse([], {"street1": "Av. Paulista, 100, Bela Vista, São Paulo - SP", "country": "BRA"}).state == "SP"
    assert la.parse([], {"street1": "Huérfanos 48, Santiago, Región Metropolitana 8320000", "country": "CHL"}).postal_code == "8320000"
    assert la.parse([], {"street1": "Av. Insurgentes Sur 1602, Del Valle, 03940 Ciudad de México", "country": "MEX"}).postal_code == "03940"
    assert la.parse([], {"street1": "Av. Paulista 100, Bela Vista, Campinas", "country": "BRA"}).city == "CAMPINAS"
    assert la.parse([], {"street1": "Carrera 7 # 71-21, Chapinero, Bogotá", "country": "COL"}).city == "BOGOTÁ"
    assert la.parse([], {"street1": "Av. Reforma 100, 06600 Monterrey, Nuevo León", "country": "MEX"}).postal_code == "06600"
    assert la.parse([], {"street1": "Av. Reforma 100, Monterrey 06600, Nuevo León", "country": "MEX"}).postal_code == "06600"
    assert la.parse([], {"street1": "Av. Reforma 100, Monterrey, Nuevo León", "country": "MEX"}).city == "MONTERREY"
    assert la.parse([], {"street1": "Balcarce 50, C1064AAB Buenos Aires", "country": "ARG"}).postal_code == "C1064AAB"
    assert la.parse([], {"street1": "Carrera 7 # 71-21, Bogotá 110221", "country": "COL"}).postal_code == "110221"
    assert la.parse([], {"street1": "Bogotá, Colombia", "country": "COL"}).city == "BOGOTÁ"
    assert la.parse([], {"street1": "Col. Juárez, 06600", "country": "MEX"}).postal_code == "06600"
    assert la.parse([], {"street1": "Av. Paulista 1578 - Bela Vista", "street2": "Apto 12", "city": "São Paulo", "country": "BRA"}).dependent_locality == "BELA VISTA"

    # 6. UKGrammar exhaustive branches
    assert is_valid_uk_postcode("") is False
    assert is_valid_uk_postcode("GIR 0AA") is True
    assert is_valid_uk_postcode("Q1A 1AA") is False
    assert is_valid_uk_postcode("AI1 1AA") is False
    assert is_valid_uk_postcode("SW1A 1CA") is False
    assert split_po_box_unit("PO Box 100, Suite 5") == ("PO BOX 100", "Suite 5")
    assert is_uk_building_name("") is False
    assert is_uk_building_name("The Shard") is True
    assert is_uk_building_name("10 High Street") is False
    assert split_commaless_postal_city("10 Downing Street London SW1A 2AA", is_valid_uk_postcode, {"LONDON"}) == (
        "10 Downing Street",
        "London",
        "SW1A 2AA",
    )
    assert split_commaless_postal_city("10 High Street Unknownville SW1A 2AA", is_valid_uk_postcode, set()) == (
        "10 High Street",
        "Unknownville",
        "SW1A 2AA",
    )

    uk_c1 = UKParsedAddressComponents(street_number="10", pre_directional="N", street_name="HIGH", street_type="ST", post_directional="W")
    assert uk_c1.format_street1() == "10 N HIGH ST W"
    uk_c2 = UKParsedAddressComponents(street_name="10", unit_type="UNIT", unit_number="A", building_name="ABBEY HOUSE")
    assert uk_c2.format_street1() == "10 UNIT A" and uk_c2.format_street2() == "ABBEY HOUSE"
    uk_c3 = UKParsedAddressComponents(street_number="10", unit_type="STE", unit_number="302")
    assert uk_c3.format_street1() == "10 STE 302" and uk_c3.format_street2() == ""
    uk_c4 = UKParsedAddressComponents(street_number="10", street_name="HIGH ST", unit_type="FLAT", unit_number="2", building_name="ABBEY HOUSE")
    assert uk_c4.format_street2() == "FLAT 2 ABBEY HOUSE"

    uk = UKGrammar()
    assert uk.normalize_postal_code("") == ""
    assert uk.normalize_postal_code("GIR 0AA") == "GIR 0AA"
    assert uk.normalize_postal_code("GB-JE-2 3RP") == "JE2 3RP"
    assert uk.extract_premise_and_thoroughfare("") == (None, None, None)
    assert uk.extract_premise_and_thoroughfare("123") == ("123", None, None)
    assert uk.extract_premise_and_thoroughfare("Abbey House, 10A High Street") == ("ABBEY HOUSE", "10A", "HIGH ST")
    assert uk.extract_premise_and_thoroughfare("10A High Street") == (None, "10A", "HIGH ST")
    assert uk.standardize(street1="10 Downing Street London SW1A 2AA England", country="GBR").city == "LONDON"
    assert uk.standardize(street1="Unit 5, Abbey House, 10 High Street, Headingley, Leeds, West Yorkshire, LS6 2AA", country="GBR").city == "WEST YORKSHIRE"

    # 7. CJKGrammar exhaustive branches
    assert strip_trailing_country("1-1 Chiyoda, Japan") == ("1-1 Chiyoda", "JPN")
    assert strip_trailing_country("1-1 Chiyoda") == ("1-1 Chiyoda", None)
    assert split_jp_tokens(["福岡市", "中央区", "今泉1-18-25"]) is not None
    assert split_jp_tokens(["東京都八王子市", "元本郷町3-24-1"]) is not None
    assert split_jp_tokens(["福岡", "天神2-13-7"]) is not None
    assert split_jp_tokens(["名古屋市東区白壁", "出来町通4-63-3"]) is not None
    assert separate_house_number("北1条西17丁目16", "JPN") == "北1条西17丁目 16"
    assert separate_house_number("まねき通り1丁目1-6", "JPN") == "まねき通り 1丁目1-6"
    assert separate_house_number("復興北路231巷34", "TWN") == "復興北路231巷 34"
    assert separate_house_number("테헤란로152", "KOR") == "테헤란로 152"
    cjk = CJKGrammar()
    assert cjk._resolve_iso3(None) == "JPN"
    assert cjk._resolve_iso3("MAC") == "MAC"
    assert cjk._resolve_iso3("MNG") == "MNG"
    assert cjk._resolve_iso3("PRK") == "PRK"
    assert cjk._resolve_iso3("UNKNOWN") == "JPN"
    assert cjk.normalize_postal_code("") == ""
    assert cjk.normalize_postal_code("1000005") == "100-0005"
    assert cjk.normalize_postal_code("06236") == "06236"
    assert cjk.normalize_postal_code("123-456") == "123-456"
    assert cjk.normalize_postal_code("123456") == "123456"
    assert cjk.normalize_postal_code("110") == "110"
    assert cjk.normalize_postal_code("ABC") == "ABC"
    assert cjk.extract_premise_and_thoroughfare("") == (None, None, None)
    assert cjk.extract_premise_and_thoroughfare("No. 100, West Nanjing Road")[1] == "100"
    assert cjk.extract_premise_and_thoroughfare("6-10-1 Roppongi")[1] == "6-10-1"
    assert cjk.extract_premise_and_thoroughfare("霞が関1-1-1")[1] == "1-1-1"
    assert cjk.extract_premise_and_thoroughfare("Mori Tower")[2] == "Mori Tower"
    assert cjk.parse([], {"street1": "Mori Tower, 6-10-1 Roppongi, Minato-ku, Tokyo 106-6132, Japan", "country": "JPN"}).building_name == "Mori Tower"
    assert cjk.parse([], {"street1": "No. 7, Sec. 5, Xinyi Rd., Xinyi Dist., Taipei City 110, Taiwan", "country": "TWN"}).postal_code == "110"
    assert cjk.parse([], {"street1": "6-10-1 Roppongi, Japan", "country": "JPN"}).country_iso3 == "JPN"
    assert cjk.parse([], {"street1": "6-10-1 Roppongi, Tokyo", "country": "JPN"}).city == "TOKYO"
    assert cjk.parse([], {"street1": "106-6132 Tokyo Roppongi6-10-1", "country": "JPN"}).postal_code == "106-6132"
    assert cjk.parse([], {"street1": "서울특별시 주흥길 78 South Korea", "country": "KOR"}).city == "서울특별시"
    assert cjk.parse([], {"street1": "東京都港区六本木6-10-1", "street2": "森タワー", "country": "JPN"}).unit_number == "森タワー"
    assert cjk.parse([], {"street1": "6-10-1 Roppongi Suite 300, Tokyo", "country": "JPN"}).unit_number == "300"

    # 8. IndiaGrammar & scripts.py exhaustive branches
    from entity_standardizer.address.international.india import IndiaGrammar
    from entity_standardizer.address.international.scripts import (
        detect_script_country,
        split_script_single_line,
        strip_zero_width,
    )

    ind = IndiaGrammar()
    assert ind.normalize_postal_code("PIN 110001") == "110001"
    assert ind.normalize_postal_code("PIN 110001 EXTRA 99") == "110001"
    assert ind.normalize_postal_code("INVALID") == ""
    assert ind.extract_premise_and_thoroughfare("") == (None, None, None)
    assert ind.extract_premise_and_thoroughfare("MG Road") == (None, None, "MG ROAD")
    assert ind.parse([], {"raw_street_address": "10 MG Road, 110001", "city": "New Delhi", "country": "IND"}).postal_code == "110001"
    assert ind.parse([], {"street1": "10 MG Road", "street2": "Flat 2", "city": "Mumbai", "state": "Maharashtra", "country": "IND"}).unit_number is not None
    assert ind.parse([], {"street1": "10 Connaught Place, New Delhi", "country": "IND"}).city == "NEW DELHI"
    assert ind.parse([], {"street1": "10 Connaught Place New Delhi", "country": "IND"}).city == "NEW DELHI"
    assert ind.parse([], {"street1": "36 Rebello Road, Bandra, Mumbai", "country": "IND"}).dependent_locality == "BANDRA"

    assert strip_zero_width("नमस्ते\u200b") == "नमस्ते"
    assert detect_script_country(None) is None
    assert detect_script_country("漢字 abcdefghijklmnop") is None
    assert detect_script_country("שלום עולם") == "ISR"
    assert detect_script_country("თბილისი") == "GEO"
    assert detect_script_country("Երևան") == "ARM"
    assert detect_script_country("ঢাকা") == "BGD"
    assert detect_script_country("කොළඹ") == "LKA"
    assert detect_script_country("ရန်ကုန်") == "MMR"
    assert detect_script_country("ភ្នំពេញ") == "KHM"
    assert detect_script_country("ວຽງຈັນ") == "LAO"
    assert detect_script_country("አዲስ አበባ") == "ETH"
    assert detect_script_country("กรุงเทพมหานคร") == "THA"
    assert detect_script_country("Београд Ђорђа") == "SRB"
    assert detect_script_country("гр. София, ул. Витоша") == "BGR"
    assert split_script_single_line("", "JPN") is None
    assert split_script_single_line("10 Main St", "USA") is None
    assert split_script_single_line("東京都", "JPN") is None
    assert split_script_single_line("广东省深圳市科技路1号", "CHN") is not None
    assert split_script_single_line("Москва, Московская область, ул. Ленина 5, 101000", "RUS") is not None

    # 9. Additional branches in base.py, eastern_europe.py, romance.py, ireland.py, offshore.py
    from entity_standardizer.address.international.eastern_europe import (
        EasternEuropeGrammar,
        split_cyrillic_locality,
    )
    from entity_standardizer.address.international.ireland import (
        IrelandGrammar,
        IrelandParsedAddressComponents,
    )
    from entity_standardizer.address.international.offshore import OffshoreGrammar
    from entity_standardizer.address.international.romance import (
        RE_ROMANCE_SEC,
        RomanceGrammar,
        parse_street2_unit,
    )

    assert split_single_line_locality("Bahnhofstrasse 10, Zürich, 8001", "CHE") == ("Bahnhofstrasse 10", "Zürich", "8001")
    assert split_commaless_locality("Rua Augusta 100 1150 011 Lisboa", "PRT") is not None
    assert split_commaless_locality("10 MG Road 560 001 Bengaluru", "IND") is not None
    assert split_commaless_locality("Calle San Martin 100 X5000 Cordoba", "ARG") is not None
    assert split_commaless_locality("Calle San Martin 100 5000 Cordoba", "ARG") is not None
    assert split_commaless_locality("83 Tilok Utis 2 Road Hat Yai 90110", "THA") is not None
    assert split_commaless_locality("12 High Road North 8001", "CHE") is None
    assert split_commaless_locality("25 شارع شريف باشا مدينة نصر 11564", "SAU") is None
    assert split_commaless_locality("10 Soi Buakhao 4 Pattaya 20150", "THA") is not None
    assert split_commaless_locality("10 Soi Pattaya 20150", "THA") is None
    assert split_intl_secondary_unit("Flat 4 A", "") == ("", "APT 4A")
    assert split_intl_secondary_unit("8F SHIN-OTEMACHI BLDG", "") == ("SHIN-OTEMACHI BLDG", "FL 8")
    assert split_intl_secondary_unit("9TH FLOOR WEST, 100 MAIN ST", "") == ("100 MAIN ST", "FL 9TH WEST")
    assert split_intl_secondary_unit("100 Main St", "Flat 4") == ("100 MAIN ST", "APT 4")
    assert split_intl_secondary_unit("A Apt 2", "") == ("", "APT 2A")
    assert split_intl_secondary_unit("10 Fort Street", "") == ("10 FORT ST", "")
    assert split_intl_secondary_unit("Al. Jerozolimskie 10", "", native_types=True) == ("AL. JEROZOLIMSKIE 10", "")
    assert split_intl_secondary_unit("10 South Church Street", "") == ("10 SOUTH CHURCH ST", "")

    assert ug.normalize_postal_code("") == ""
    assert ug.parse([], {"street1": "Ln. 10, Koningsln. 5, Kerkstr. 2", "city": "Amsterdam", "country": "NLD"}).street_name is not None
    assert ug.parse([], {"street1": " Ugland House, PO Box 309, George Town, KY1-1104, Cayman Islands", "country": "CYM"}).unit_type == "PO"
    assert ug.parse([], {"street1": "Ugland House, 75 Fort Street, George Town, KY1-1104", "country": "CYM"}).street_name == "75 FORT ST"
    assert ug.parse([], {"street1": "Rue du Rhône 10, Genève, Geneva", "country": "ARE"}).state == "GENEVA"
    assert ug.parse([], {"street1": "Toronto, ON M5J 2J5", "country": "CAN"}).state == "ON"
    assert ug.parse([], {"street1": "Toronto, M5J 2J5", "country": "CAN"}).postal_code == "M5J 2J5"
    assert ug.parse([], {"street1": "100 Main St, George Town", "country": "CYM"}).city == "GEORGE TOWN"
    assert ug.parse([], {"street1": "PARIS,", "country": "FRA"}).city == "PARIS"
    assert ug.parse([], {"street1": "100 Main St,", "country": "CYM"}).street_name == "100 MAIN ST"
    assert ug.parse([], {"street1": "217/27 Moo 9 Beach Rd., Nongprue, Banglamung", "city": "Pattaya", "country": "THA"}).dependent_locality == "NONGPRUE, BANGLAMUNG"

    assert CountryGrammarRegistry.get(None) is CountryGrammarRegistry._fallback_grammar
    assert CountryGrammarRegistry.has(None) is False
    assert CountryGrammarRegistry.has("GBR") is True
    assert "GBR" in CountryGrammarRegistry.supported_countries()
    assert CountryGrammarRegistry.detect_country(state_raw="ON") == "CAN"
    assert CountryGrammarRegistry.detect_country(country_raw="PRI") == "PRI"
    assert CountryGrammarRegistry.detect_country(city_raw="8001 Zurich") == "CHE"
    assert CountryGrammarRegistry.detect_country(city_raw="District, Zurich") == "CHE"
    assert CountryGrammarRegistry.detect_country(city_raw="Zürich 8001") == "CHE"
    assert CountryGrammarRegistry.detect_country(postal_raw="SW1A 2AA") == "GBR"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, Cayman Islands") == "CYM"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, Toronto, Canada") == "CAN"
    assert CountryGrammarRegistry.detect_country(raw_street="100 Main St, Austin, TX, USA") == "USA"

    # EasternEuropeGrammar extra branches
    assert split_cyrillic_locality("Нижний Новгород улица Ленина 5") == ("", "Нижний Новгород", "улица Ленина 5")
    assert split_cyrillic_locality("улица Ленина 5") == ("", "", "улица Ленина 5")
    ee = EasternEuropeGrammar()
    assert ee.parse([], {"street1": "ul. Marszałkowska 10, 00-950, Warszawa", "country": "POL"}).postal_code == "00-950"
    assert ee.parse([], {"street1": "1054 Budapest, Zoltán utca 16.", "country": "HUN"}).postal_code == "1054"
    assert ee.parse([], {"street1": "Москва, Пречистенская набережная, 9", "country": "RUS"}).city == "МОСКВА"
    assert ee.parse([], {"street1": "ул. Витоша 10, София 1000", "country": "BGR"}).postal_code == "1000"
    assert ee.parse([], {"street1": "ul. Marszałkowska 10, Warszawa", "country": "POL"}).city == "WARSZAWA"
    assert ee.parse([], {"street1": "WARSAW,", "country": "POL"}).city == "WARSAW"
    assert ee.parse([], {"street1": "ul. Marszałkowska 10,", "country": "POL"}).street_name == "UL. MARSZAŁKOWSKA 10"
    assert ee.parse([], {"street1": "ul. Marszałkowska 10 lok. 2", "street2": "piętro 3", "city": "Warszawa", "country": "POL"}).unit_number == "LOK. 2 PIĘTRO 3"
    assert ee.parse([], {"street1": "ul. Marszałkowska 10 Suite 5", "city": "Warszawa", "country": "POL"}).unit_type == "STE"
    assert ee.parse([], {"street1": "ul. Marszałkowska 10 Suite 5", "street2": "lok. 2", "city": "Warszawa", "country": "POL"}).unit_number is not None

    # RomanceGrammar extra branches
    rom = RomanceGrammar()
    assert parse_street2_unit("3ème étage, , 2º B", RE_ROMANCE_SEC)[1] == "ETAGE 3 2 B"
    assert rom.parse([], {"street1": "Av. Paulista, 1578 - Bela Vista, Col. Centro, Apto 12, 01310-200, São Paulo - SP, Portugal", "country": "PRT"}).postal_code == "01310-200"
    assert rom.parse([], {"street1": "Av. Paulista, 1578 - Bela Vista, São Paulo", "country": "PRT"}).dependent_locality == "BELA VISTA"
    assert rom.parse([], {"street1": "142 Boulevard Saint-Germain, Quartier Latin, 75006 Paris", "country": "FRA"}).city == "PARIS"
    assert rom.parse([], {"street1": "Calle Mayor 45, Centro, Madrid, MD", "country": "ESP"}).state == "MD"
    assert rom.parse([], {"street1": "Calle Mayor 45, Madrid", "country": "ESP"}).city == "MADRID"
    assert rom.parse([], {"street1": "PARIS,", "country": "FRA"}).city == "PARIS"
    assert rom.parse([], {"street1": "Calle Mayor 45,", "country": "ESP"}).street_name == "CALLE MAYOR 45"
    assert rom.parse([], {"street1": "Col. Centro, 28013", "country": "ESP"}).postal_code == "28013"
    assert rom.parse([], {"street1": "Rua Dona Antonia, 108 Lisboa", "country": "PRT"}).city == "LISBOA"
    assert rom.parse([], {"street1": "Rua Augusta 100 - Baixa", "city": "Lisboa", "country": "PRT"}).dependent_locality == "BAIXA"
    assert rom.parse([], {"street1": "8F PLAZA MAYOR", "city": "Madrid", "country": "ESP"}).unit_type == "FL"
    assert rom.parse([], {"street1": "8F PLAZA MAYOR", "street2": "Piso 3", "city": "Madrid", "country": "ESP"}).unit_number is not None

    # IrelandGrammar extra branches
    c_ir1 = IrelandParsedAddressComponents(street_name="10", unit_type="UNIT", unit_number="2", building_name="BLOCK A")
    assert c_ir1.format_street1() == "10 UNIT 2" and c_ir1.format_street2() == "BLOCK A"
    c_ir2 = IrelandParsedAddressComponents(street_number="10", unit_type="UNIT", unit_number="2")
    assert c_ir2.format_street1() == "10 UNIT 2" and c_ir2.format_street2() == ""
    c_ir3 = IrelandParsedAddressComponents(street_number="10", street_name="BAGGOT ST", unit_type="APT", unit_number="4", building_name="TREASURY BLDG")
    assert c_ir3.format_street2() == "APT 4 TREASURY BLDG"
    ir = IrelandGrammar()
    assert ir._normalize_street_tokens("") == ""
    assert ir.extract_premise_and_thoroughfare("123") == ("123", None, None)
    assert ir.parse([], {"raw_street_address": "10 Baggot Street Lower, Dublin 2, D02 X285", "state": "Territory of Co. Dublin"}).state == "CO DUBLIN"
    assert ir.parse([], {"street1": "Unit 5, Treasury Building, 10 Grand Canal Street Lower, Grand Canal Dock, Cork, Co. Cork, T12 AB12, Ireland"}).city == "CORK"
    assert ir.parse([], {"street1": "Dublin 2, D02 X285, Ireland"}).city == "DUBLIN"
    assert ir.parse([], {"street1": "10 Baggot Street, Suburbia, Extra, Dublin"}).dependent_locality == "SUBURBIA"
    assert ir.parse([], {"street1": "10 Baggot Street Suite 5", "city": "Dublin"}).unit_type == "STE"
    assert ir.parse([], {"street1": "10 Custom House Quay", "state": "CO DUBLIN"}).city == "DUBLIN"
    assert ir.parse([], {"street1": "10 Baggot Street", "postal_code": "D02 X285"}).city == "DUBLIN"
    assert ir.parse([], {"street1": "10 Baggot Street", "city": "Dublin 2", "postal_code": "D04 X285"}).dependent_locality == "DUBLIN 2"

    # OffshoreGrammar extra branches
    off = OffshoreGrammar()
    assert off._normalize_street_tokens("") == ""
    assert off.extract_premise_and_thoroughfare("Acme Corp, LLC") == (None, None, None)
    assert off.extract_premise_and_thoroughfare("Acme Corp, LLC, 10 Fort Street")[0] == "ACME CORP, LLC"
    assert off.extract_premise_and_thoroughfare("Ugland House, South Church Street")[2] == "SOUTH CHURCH ST"
    assert off.extract_premise_and_thoroughfare("Ugland House 10 North Street")[1] == "10"
    assert off.parse([], {"street1": "PO Box 309, Suite 100", "city": "George Town", "country": "CYM"}).unit_type == "STE"
    assert off.parse([], {"street1": "Apartado 0816-01085, Calle 50, Panama, Panama", "country": "PAN"}).unit_type == "APARTADO"
    assert off.parse([], {"street1": "10 Main St, Road Town, Tortola, VG1110, BVI", "country": "VGB"}).state == "TORTOLA"
    assert off.parse([], {"street1": "Suburb, 10 Main St, Hamilton", "country": "BMU"}).city == "HAMILTON"
    assert off.parse([], {"street1": "10 Main St,", "country": "CYM"}).street_name == "10 MAIN ST"
    assert off.parse([], {"street1": "PO Box 309, KY1-1104", "country": "CYM"}).postal_code == "KY1-1104"
    assert off.parse([], {"street1": "10 Main St", "street2": "Apartado 123", "city": "Panama", "country": "PAN"}).unit_type == "APARTADO"
    assert off.parse([], {"street1": "10 Main St PO Box 55", "city": "George Town", "country": "CYM"}).unit_type == "PO BOX"
    assert off.parse([], {"street1": "10 Main St Suite 200", "street2": "PO Box 55", "city": "George Town", "country": "CYM"}).unit_number is not None
    assert off.parse([], {"street1": "Calle 50 Apartado 55", "city": "Panama", "country": "PAN"}).unit_type == "APARTADO"


