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
