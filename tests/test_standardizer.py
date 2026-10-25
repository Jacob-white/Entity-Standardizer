"""Comprehensive unit and integration tests for Phone Standardizer (100% coverage suite)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import entity_standardizer.__main__ as main_mod
import entity_standardizer._native_dispatch as native_dispatch
from entity_standardizer import (
    HealingAction,
    PhoneLineType,
    PhoneRiskFlag,
    PhoneRoutingTier,
    batch_standardize_phones,
    decode_vanity_phone,
    extract_phones_from_text,
    fold_vanity_digits_dispatch,
    format_e164,
    format_international,
    format_national,
    format_rfc3966,
    get_engine_info,
    has_repeating_subscriber_digits,
    has_sequential_subscriber_digits,
    is_fictitious_number,
    is_native_available,
    mask_phone,
    standardize_phone,
    stream_standardize_csv,
    stream_standardize_jsonl,
    validate_phone,
)
from entity_standardizer.cli import main as cli_main
from entity_standardizer.mcp import handle_mcp_request
from entity_standardizer.server import app


def test_us_and_nanp_standardization() -> None:
    # Standard US number
    res = standardize_phone("(415) 555-2671")
    assert res.is_valid is True
    assert res.e164 == "+14155552671"
    assert res.national == "(415) 555-2671"
    assert res.international == "+1 415-555-2671"
    assert res.rfc3966 == "tel:+1-415-555-2671"
    assert res.country_iso2 == "US"
    assert res.region_code == "CA"
    assert res.line_type == PhoneLineType.FIXED_LINE_OR_MOBILE
    assert res.routing_tier == PhoneRoutingTier.AUTO_PASS
    assert res.as_dict()["e164"] == "+14155552671"

    # 11-digit US national trunk 1
    res11 = standardize_phone("1-212-555-0299")
    assert res11.e164 == "+12125550299"
    assert res11.region_code == "NY"
    assert HealingAction.NATIONAL_TRUNK_STRIPPED in res11.healing_actions

    # Toll-free vanity + extension
    vanity = standardize_phone("Call 1-800-FLOWERS ext. 402! (Customer Care)")
    assert vanity.e164 == "+18003569377"
    assert vanity.national == "(800) 356-9377"
    assert vanity.rfc3966 == "tel:+1-800-356-9377;ext=402"
    assert vanity.extension == "402"
    assert vanity.vanity_alias == "1-800-FLOWERS"
    assert vanity.line_type == PhoneLineType.TOLL_FREE
    assert vanity.phone_ext_key == "+18003569377#402"

    # Vanity with hyphenated second part (e.g. 1-888-TAX-HELP)
    vanity2, alias2 = decode_vanity_phone("1-888-TAX-HELP")
    assert alias2 == "1-888-TAX-HELP"
    assert "829-4357" in vanity2

    # Premium & Personal NANP
    prem = standardize_phone("+1 900-555-0200")
    assert prem.line_type == PhoneLineType.PREMIUM_RATE
    assert PhoneRiskFlag.PREMIUM_RATE_IRSF_RISK in prem.risk_flags
    assert prem.routing_tier == PhoneRoutingTier.FUZZY_REVIEW

    pers = standardize_phone("+1 500-555-0200")
    assert pers.line_type == PhoneLineType.PERSONAL_NUMBER

    # Unrecognized but structurally valid NANP NPA (299)
    unrec = standardize_phone("299-555-0200")
    assert unrec.is_valid is True
    assert unrec.routing_tier == PhoneRoutingTier.FUZZY_REVIEW


def test_short_and_emergency_codes() -> None:
    em = standardize_phone("911")
    assert em.is_valid is True
    assert em.line_type == PhoneLineType.EMERGENCY
    assert em.e164 == "911"

    sc = standardize_phone("411")
    assert sc.is_valid is True
    assert sc.line_type == PhoneLineType.SHORT_CODE
    assert sc.e164 == "411"


def test_international_dial_plans_and_healing() -> None:
    # UK with redundant (0) trunk
    uk_lon = standardize_phone("+44 (0) 20 7946 0912")
    assert uk_lon.e164 == "+442079460912"
    assert uk_lon.national == "020 7946 0912"
    assert uk_lon.international == "+44 20 7946 0912"
    assert uk_lon.area_code == "20"
    assert PhoneRiskFlag.FICTITIOUS_RANGE in uk_lon.risk_flags

    # UK mobile with +44 07... redundant trunk (without parens)
    uk_mob = standardize_phone("+44 07911 123456")
    assert uk_mob.e164 == "+447911123456"
    assert uk_mob.national == "07911 123456"
    assert uk_mob.line_type == PhoneLineType.MOBILE
    assert HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED in uk_mob.healing_actions

    # UK 3-digit area code (0113 Leeds) and 4-digit area code (01534 Jersey domestic)
    uk_leeds = standardize_phone("0113 496 0200", country="GB")
    assert uk_leeds.e164 == "+441134960200"
    assert uk_leeds.area_code == "113"

    uk_jersey = standardize_phone("01534 555123", country="GB")
    assert uk_jersey.country_iso2 == "JE"
    assert uk_jersey.area_code == "1534"

    # UK Shared Cost & VoIP & Toll Free & Premium
    assert standardize_phone("+44 800 123 4567").line_type == PhoneLineType.TOLL_FREE
    assert standardize_phone("+44 909 879 0123").line_type == PhoneLineType.PREMIUM_RATE
    assert standardize_phone("+44 845 123 4567").line_type == PhoneLineType.SHARED_COST
    assert standardize_phone("+44 560 123 4567").line_type == PhoneLineType.VOIP

    # France (9-digit NSN)
    fr = standardize_phone("01 23 45 67 89", country="FR")
    assert fr.e164 == "+33123456789"
    assert fr.national == "01 23 45 67 89"
    assert fr.international == "+33 1 23 45 67 89"

    # Germany (Berlin 30, Mobile 151, general 3-digit area code)
    de_ber = standardize_phone("030 12345678", country="DE")
    assert de_ber.e164 == "+493012345678"
    assert de_ber.national == "030 12345678"
    assert de_ber.area_code == "30"

    de_mob = standardize_phone("+49 151 23456789")
    assert de_mob.line_type == PhoneLineType.MOBILE
    assert de_mob.area_code == "151"

    de_gen = standardize_phone("+49 221 5551234")
    assert de_gen.area_code == "221"

    # Japan (Full-width Unicode numerals, Tokyo 03, Mobile 090, Toll-free 0120, 2-digit area)
    jp_tok = standardize_phone("＋８１ ３-１２３４-５６７８")
    assert jp_tok.e164 == "+81312345678"
    assert jp_tok.national == "03-1234-5678"
    assert HealingAction.UNICODE_DIGITS_FOLDED in jp_tok.healing_actions

    jp_mob = standardize_phone("090-1234-5678", country="JP")
    assert jp_mob.e164 == "+819012345678"
    assert jp_mob.line_type == PhoneLineType.MOBILE

    jp_tf = standardize_phone("0120-123-456", country="JP")
    assert jp_tf.e164 == "+81120123456"
    assert jp_tf.line_type == PhoneLineType.TOLL_FREE

    jp_other = standardize_phone("045-123-4567", country="JP")
    assert jp_other.e164 == "+81451234567"

    # Australia (Mobile 04 & Fixed 02)
    au_mob = standardize_phone("0412 345 678", country="AU")
    assert au_mob.e164 == "+61412345678"
    assert au_mob.national == "0412 345 678"
    assert au_mob.line_type == PhoneLineType.MOBILE

    au_fix = standardize_phone("02 9876 5432", country="AU")
    assert au_fix.e164 == "+61298765432"
    assert au_fix.national == "(02) 9876 5432"

    # Switzerland
    ch = standardize_phone("044 668 18 00", country="CH")
    assert ch.e164 == "+41446681800"
    assert ch.area_code == "44"

    # Mexico legacy +52 1 mobile healing
    mx = standardize_phone("+52 1 55 8421 9034")
    assert mx.e164 == "+525584219034"
    assert HealingAction.LEGACY_MEXICO_MOBILE_1_STRIPPED in mx.healing_actions
    assert mx.line_type == PhoneLineType.FIXED_LINE_OR_MOBILE
    assert mx.routing_tier == PhoneRoutingTier.AUTO_PASS

    # Argentina domestic 15 mobile healing
    ar = standardize_phone("11 15 8421 9034", country="AR")
    assert ar.e164 == "+5491184219034"
    assert HealingAction.ARGENTINA_MOBILE_15_HEALED in ar.healing_actions
    assert ar.line_type == PhoneLineType.MOBILE

    # Germany international with redundant 0 trunk (+49 030...)
    de_intl_zero = standardize_phone("+49 030 5551234")
    assert de_intl_zero.e164 == "+49305551234"

    # Spain (no national trunk prefix)
    es = standardize_phone("612 34 56 78", country="ES")
    assert es.e164 == "+34612345678"

    # Brazil 11-digit mobile (9th digit)
    br = standardize_phone("+55 11 98765 4321")
    assert br.e164 == "+5511987654321"
    assert br.line_type == PhoneLineType.MOBILE

    # IDD exit prefix stripping (011 from US to DE)
    idd = standardize_phone("011 49 30 5551234", default_country="US")
    assert idd.e164 == "+49305551234"
    assert HealingAction.IDD_EXIT_PREFIX_STRIPPED in idd.healing_actions

    # Short 5-digit NSN formatting (Falkland Islands +500, allow 6-digit in general fallback or test _format_numbers)
    from entity_standardizer.models import CountryDialPlan
    from entity_standardizer.standardizer import _format_numbers, _split_area_and_subscriber
    short_plan = CountryDialPlan(
        iso2="FK", iso3="FLK", numeric="238", name="Falkland Islands", calling_code="500", nsn_lengths=(5,)
    )
    assert _split_area_and_subscriber(short_plan, "") == (None, None)
    assert _split_area_and_subscriber(short_plan, "12345") == (None, "12345")
    e_fk, nat_fk, intl_fk, rfc_fk = _format_numbers(short_plan, "12345", None)
    assert e_fk == "+50012345" and nat_fk == "012345" and intl_fk == "+500 12345" and rfc_fk == "tel:+500-12345"


def test_address_context_and_mismatch() -> None:
    # Dict address context
    res_dict = standardize_phone("030 5551234", address_context={"country_iso2": "DE", "state": "BE"})
    assert res_dict.e164 == "+49305551234"
    assert res_dict.region_code == "BE"
    assert HealingAction.COUNTRY_INFERRED_FROM_CONTEXT in res_dict.healing_actions

    # Object address context (like StandardizedAddress)
    class DummyAddr:
        country = "GBR"
        state = "ENG"

    res_obj = standardize_phone("020 7946 0200", address_context=DummyAddr())
    assert res_obj.e164 == "+442079460200"
    assert res_obj.region_code == "ENG"

    # Cross-field mismatch: +44 UK phone number with country="US" hint
    mismatch = standardize_phone("+44 20 7946 0200", country="US")
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in mismatch.risk_flags
    assert mismatch.routing_tier == PhoneRoutingTier.FUZZY_REVIEW


def test_validation_risk_flags_and_format_helpers() -> None:
    # None / empty / non-digit inputs
    assert standardize_phone(None).is_valid is False
    assert standardize_phone("   ").is_valid is False
    assert standardize_phone("no digits here!").is_valid is False

    # Unassigned calling code (+000...)
    unassigned = standardize_phone("+00012345678")
    assert PhoneRiskFlag.UNASSIGNED_CALLING_CODE in unassigned.risk_flags

    # Invalid length
    short = standardize_phone("12345", country="US")
    assert short.is_valid is False
    assert PhoneRiskFlag.INVALID_LENGTH in short.risk_flags

    # Invalid NANP area code (starts with 1) & invalid exchange (starts with 1 or N11)
    bad_nanp = standardize_phone("123-111-2222", country="US")
    assert bad_nanp.is_valid is False
    assert PhoneRiskFlag.INVALID_AREA_CODE in bad_nanp.risk_flags
    assert PhoneRiskFlag.INVALID_EXCHANGE in bad_nanp.risk_flags
    assert bad_nanp.confidence == 0.25
    assert bad_nanp.routing_tier == PhoneRoutingTier.MANUAL_STEWARDSHIP

    # Fictitious US 555-01XX
    fict = standardize_phone("(415) 555-0142")
    assert PhoneRiskFlag.FICTITIOUS_RANGE in fict.risk_flags
    assert fict.routing_tier == PhoneRoutingTier.FUZZY_REVIEW
    assert is_fictitious_number(None, None) is False
    assert is_fictitious_number("1", "4155550200") is False

    # Repeating & sequential digits -> MANUAL_STEWARDSHIP
    rep = standardize_phone("(415) 999-9999")
    assert PhoneRiskFlag.REPEATING_DIGITS in rep.risk_flags
    assert rep.routing_tier == PhoneRoutingTier.MANUAL_STEWARDSHIP
    assert has_repeating_subscriber_digits("123") is False

    seq = standardize_phone("(415) 234-5678")
    assert PhoneRiskFlag.SEQUENTIAL_DIGITS in seq.risk_flags
    assert seq.routing_tier == PhoneRoutingTier.MANUAL_STEWARDSHIP
    assert has_sequential_subscriber_digits("123") is False

    # Helper functions
    assert validate_phone("+1 415 555 2671") is True
    assert validate_phone("invalid") is False
    assert format_e164("(415) 555-2671") == "+14155552671"
    assert format_e164("invalid") is None
    assert format_national("+14155552671") == "(415) 555-2671"
    assert format_national("invalid") is None
    assert format_international("(415) 555-2671") == "+1 415-555-2671"
    assert format_international("invalid") is None
    assert format_rfc3966("(415) 555-2671 ext 9") == "tel:+1-415-555-2671;ext=9"
    assert format_rfc3966("invalid") is None


def test_mask_phone_strategies() -> None:
    import pytest

    assert mask_phone("+1 (415) 555-2671", strategy="partial") == "+1******2671"
    assert mask_phone("+1 (415) 555-2671", strategy="partial_phone") == "***-***-2671"
    assert mask_phone("123", strategy="partial_phone") == "***"
    assert mask_phone("+1 (415) 555-2671", strategy="last4") == "****2671"
    assert mask_phone("123", strategy="last4") == "****"
    assert mask_phone("+1 (415) 555-2671", strategy="redact") == "[REDACTED PHONE]"
    assert mask_phone("+1 (415) 555-2671", strategy="null") is None
    assert len(mask_phone("+1 (415) 555-2671", strategy="hash")) == 64
    assert len(mask_phone("+1 (415) 555-2671", strategy="sha256")) == 64
    assert len(mask_phone("+1 (415) 555-2671", strategy="md5")) == 32
    assert mask_phone("", strategy="partial") == "[REDACTED PHONE]"
    assert mask_phone("12345", strategy="partial") == "*2345"

    with pytest.raises(ValueError, match="Unknown masking strategy"):
        mask_phone("+1 (415) 555-2671", strategy="invalid_strategy")


def test_phase5_lexical_regional_healing_and_formatting() -> None:
    # 1. Arbitrary leading labels ("Contact: ", "WhatsApp: ")
    lbl1 = standardize_phone("Contact: +44 20 7946 0200")
    assert lbl1.e164 == "+442079460200"
    lbl2 = standardize_phone("WhatsApp: +49 30 12345678")
    assert lbl2.e164 == "+493012345678"

    # 2. Trailing words after complete 10+ digit number are stripped, not folded as vanity digits
    trailing = standardize_phone("+1 415-555-2671 ask for Bob")
    assert trailing.e164 == "+14155552671"
    assert trailing.vanity_alias is None
    trailing2 = standardize_phone("+1 415-555-2671 Mon-Fri")
    assert trailing2.e164 == "+14155552671"
    assert trailing2.vanity_alias is None

    # 3. Expanded extension formats (: / - / # separators, parenthesized, RFC 3966 ;isub=, DTMF , / p / w)
    for ext_input in [
        "+1 415-555-2671 ext: 104",
        "+1 415-555-2671 ext-104",
        "+1 415-555-2671 (ext. 104)",
        "+1 415-555-2671;isub=104",
        "+1 415-555-2671,104",
        "+1 415-555-2671p104",
        "+1 415-555-2671w104",
    ]:
        parsed_ext = standardize_phone(ext_input)
        assert parsed_ext.e164 == "+14155552671"
        assert parsed_ext.extension == "104"

    # 4. Argentina (+54): domestic trunk 0 stripping + 2-, 3-, and 4-digit area code 15 mobile healing
    ar_trunk = standardize_phone("011 15-8421-9034", country="AR")
    assert ar_trunk.e164 == "+5491184219034"
    assert ar_trunk.area_code == "11"
    assert ar_trunk.subscriber_number == "84219034"
    assert ar_trunk.national == "011 15 8421 9034"
    assert ar_trunk.international == "+54 9 11 8421 9034"
    assert ar_trunk.rfc3966 == "tel:+54-9-11-8421-9034"
    assert HealingAction.NATIONAL_TRUNK_STRIPPED in ar_trunk.healing_actions
    assert HealingAction.ARGENTINA_MOBILE_15_HEALED in ar_trunk.healing_actions

    ar_3digit = standardize_phone("0351 15-512-3456", country="AR")
    assert ar_3digit.e164 == "+5493515123456"
    assert ar_3digit.area_code == "351"
    assert ar_3digit.subscriber_number == "5123456"
    assert ar_3digit.national == "0351 15 512 3456"
    assert ar_3digit.international == "+54 9 351 512 3456"

    ar_4digit = standardize_phone("02944 15-456-789", country="AR")
    assert ar_4digit.e164 == "+5492944456789"

    ar_no15_12 = standardize_phone("11 4444 5555 66", country="AR")
    assert ar_no15_12.is_valid is False

    # 5. Mexico (+52): legacy domestic 044, 045, 01 prefix healing and already-clean 10-digit MX
    mx_clean = standardize_phone("+52 55 8421 9034")
    assert mx_clean.e164 == "+525584219034"

    mx_044 = standardize_phone("044 55 8421 9034", country="MX")
    assert mx_044.e164 == "+525584219034"
    assert HealingAction.LEGACY_MEXICO_MOBILE_1_STRIPPED in mx_044.healing_actions

    mx_045 = standardize_phone("045 81 8421 9034", country="MX")
    assert mx_045.e164 == "+528184219034"

    mx_01 = standardize_phone("01 55 8421 9034", country="MX")
    assert mx_01.e164 == "+525584219034"
    assert HealingAction.NATIONAL_TRUNK_STRIPPED in mx_01.healing_actions

    # 6. Closed dial plan (Italy +39) preserves leading (0) / 0 in landline numbers
    it_landline = standardize_phone("+39 (0) 6 1234 5678")
    assert it_landline.e164 == "+390612345678"
    assert HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED not in it_landline.healing_actions

    # Domestic number with (0) in open dial plan (GB)
    gb_dom_paren = standardize_phone("(0) 20 7946 0200", country="GB")
    assert gb_dom_paren.e164 == "+442079460200"
    assert HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED in gb_dom_paren.healing_actions

    # 7. IDD exit prefix does NOT trigger false ADDRESS_COUNTRY_MISMATCH; shared CC conflict DOES
    idd_us_to_gb = standardize_phone("011 44 20 7946 0200", country="US")
    assert idd_us_to_gb.e164 == "+442079460200"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in idd_us_to_gb.risk_flags

    nanp_mismatch = standardize_phone("+1 416-555-0199", country="US")  # 416 is Ontario, CA
    assert nanp_mismatch.country_iso2 == "CA"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in nanp_mismatch.risk_flags

    # 8. NANP NPA=555 is invalid with INVALID_AREA_CODE
    npa_555 = standardize_phone("(555) 234-5678", country="US")
    assert npa_555.is_valid is False
    assert PhoneRiskFlag.INVALID_AREA_CODE in npa_555.risk_flags

    # 9. Address context postal-code country inference (dict and object)
    res_postal_dict = standardize_phone("03-1234-5678", address_context={"postal_code": "100-0001"})
    assert res_postal_dict.country_iso2 == "JP"
    assert res_postal_dict.e164 == "+81312345678"

    class DummyPostalObj:
        postal_code = "SW1A 1AA"

    res_postal_obj = standardize_phone("020 7946 0200", address_context=DummyPostalObj())
    assert res_postal_obj.country_iso2 == "GB"
    assert res_postal_obj.e164 == "+442079460200"

    # 10. UK 3-digit area code, KR Seoul 02, and CN 11-digit mobile E.123 formatting
    uk_leeds = standardize_phone("+44 113 496 0200")
    assert uk_leeds.national == "0113 496 0200"
    assert uk_leeds.international == "+44 113 496 0200"
    assert uk_leeds.rfc3966 == "tel:+44-113-496-0200"

    kr_seoul = standardize_phone("+82 2 1234 5678")
    assert kr_seoul.area_code == "2"
    assert kr_seoul.national == "02 1234 5678"
    assert kr_seoul.international == "+82 2 1234 5678"

    cn_mobile = standardize_phone("+86 138 0013 8000")
    assert cn_mobile.area_code == "138"
    assert cn_mobile.international == "+86 138 0013 8000"
    cn_beijing = standardize_phone("+86 10 1234 5678")
    assert cn_beijing.area_code == "10"
    assert cn_beijing.national == "010 1234 5678"




def test_native_dispatch_and_fallback(monkeypatch) -> None:
    assert isinstance(is_native_available(), bool)
    info = get_engine_info()
    assert info["engine"] in ("pure_python", "rust_pyo3")
    assert fold_vanity_digits_dispatch("FLOWERS") == "3569377"

    # Simulate native Rust module present
    mock_rs = MagicMock()
    mock_rs.fold_vanity_digits_rs.return_value = "3569377"
    monkeypatch.setattr(native_dispatch, "_native_mod", mock_rs)
    assert native_dispatch.is_native_available() is True
    assert native_dispatch.fold_vanity_digits_dispatch("FLOWERS") == "3569377"


def test_batch_csv_and_jsonl_streaming(tmp_path: Path) -> None:
    items = [
        "(415) 555-2671",
        {"phone": "020 7946 0912", "country": "GB"},
    ]
    batch_res = batch_standardize_phones(items)
    assert len(batch_res) == 2
    assert batch_res[0].e164 == "+14155552671"
    assert batch_res[1].e164 == "+442079460912"

    # CSV streaming
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    in_csv.write_text("name,phone,country\nAlice,(415) 555-2671,US\nBob,030 12345678,DE\n", encoding="utf-8")
    count_csv = stream_standardize_csv(in_csv, out_csv)
    assert count_csv == 2
    out_text = out_csv.read_text(encoding="utf-8")
    assert "+14155552671" in out_text
    assert "+493012345678" in out_text

    # JSONL streaming (with blank line handling)
    in_jsonl = tmp_path / "in.jsonl"
    out_jsonl = tmp_path / "out.jsonl"
    in_jsonl.write_text(
        '\n{"phone": "(415) 555-2671", "country": "US"}\n{"phone": "+44 20 7946 0912"}\n',
        encoding="utf-8",
    )
    count_jsonl = stream_standardize_jsonl(in_jsonl, out_jsonl)
    assert count_jsonl == 2
    lines = [json.loads(line) for line in out_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[0]["standardized_phone"]["e164"] == "+14155552671"
    assert lines[1]["standardized_phone"]["e164"] == "+442079460912"


def test_cli_commands(tmp_path: Path, capsys) -> None:
    assert callable(main_mod.main)
    # parse
    rc = cli_main(["parse", "(415) 555-2671", "-c", "US"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["e164"] == "+14155552671"

    # country valid & invalid
    rc_c = cli_main(["country", "JP"])
    assert rc_c == 0
    assert json.loads(capsys.readouterr().out)["calling_code"] == "81"

    rc_err = cli_main(["country", "INVALID_COUNTRY"])
    assert rc_err == 1
    assert "Unknown country" in capsys.readouterr().err

    # batch
    in_csv = tmp_path / "cli_in.csv"
    out_csv = tmp_path / "cli_out.csv"
    in_csv.write_text("phone,country\n(415) 555-2671,US\n", encoding="utf-8")
    rc_b = cli_main(["batch", str(in_csv), str(out_csv)])
    assert rc_b == 0
    assert json.loads(capsys.readouterr().out)["processed_rows"] == 1

    # address & contact
    rc_addr = cli_main(
        ["address", "1600 Amphitheatre Pkwy", "--city", "Mountain View", "--state", "CA", "--postal-code", "94043"]
    )
    assert rc_addr == 0
    assert json.loads(capsys.readouterr().out)["state"] == "CA"

    rc_contact = cli_main(
        [
            "contact",
            "--street1",
            "350 Fifth Ave",
            "--city",
            "New York",
            "--state",
            "NY",
            "--postal-code",
            "10118",
            "--phone",
            "555-2368",
        ]
    )
    assert rc_contact == 0
    assert json.loads(capsys.readouterr().out)["phone"]["e164"] == "+12125552368"



def test_fastapi_server_endpoints() -> None:
    client = TestClient(app)

    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_std = client.post("/v1/standardize", json={"phone": "(415) 555-2671", "country": "US"})
    assert r_std.status_code == 200
    assert r_std.json()["e164"] == "+14155552671"

    r_batch = client.post("/v1/batch", json={"phones": ["(415) 555-2671", "+44 20 7946 0912"]})
    assert r_batch.status_code == 200
    assert r_batch.json()["count"] == 2

    r_country = client.get("/v1/countries/DE")
    assert r_country.status_code == 200
    assert r_country.json()["calling_code"] == "49"

    r_404 = client.get("/v1/countries/NOT_A_COUNTRY")
    assert r_404.status_code == 404

    r_all = client.get("/v1/countries")
    assert r_all.status_code == 200
    assert r_all.json()["count"] == 249

    r_addr = client.post(
        "/v1/address",
        json={"street1": "1600 Amphitheatre Pkwy", "city": "Mountain View", "state": "CA", "postal_code": "94043"},
    )
    assert r_addr.status_code == 200
    assert r_addr.json()["state"] == "CA"

    r_contact = client.post(
        "/v1/contact",
        json={"street1": "350 Fifth Ave", "city": "New York", "state": "NY", "postal_code": "10118", "phone": "555-2368"},
    )
    assert r_contact.status_code == 200
    assert r_contact.json()["phone"]["e164"] == "+12125552368"

    r_company = client.post("/v1/company", json={"name": "The Acme & Co., Inc."})
    assert r_company.status_code == 200
    assert r_company.json()["legal_suffix"] == "INC"

    r_person = client.post("/v1/person", json={"name": "Dr. Robert (Bob) J. Smith, Jr., MD"})
    assert r_person.status_code == 200
    assert r_person.json()["first_name"] == "ROBERT"

    r_email = client.post("/v1/email", json={"email": "Jane.Doe+tag@gmail.com"})
    assert r_email.status_code == 200
    assert r_email.json()["email"] == "janedoe@gmail.com"

    r_url = client.post("/v1/url", json={"url": "www.acme.co.uk/?utm_source=x"})
    assert r_url.status_code == 200
    assert r_url.json()["domain"] == "acme.co.uk"

    r_social = client.post("/v1/social", json={"profile": "@octocat", "platform": "GITHUB"})
    assert r_social.status_code == 200
    assert r_social.json()["url"] == "https://github.com/octocat"


def test_mcp_server_requests() -> None:
    init_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp["result"]["serverInfo"]["name"] == "entity-standardizer-mcp"

    list_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(list_resp["result"]["tools"]) == 17

    call_std = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "standardize_phone", "arguments": {"phone": "(415) 555-2671"}},
        }
    )
    assert "+14155552671" in call_std["result"]["content"][0]["text"]

    call_addr = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": "standardize_address",
                "arguments": {"street1": "1600 Amphitheatre Pkwy", "city": "Mountain View", "state": "CA", "postal_code": "94043"},
            },
        }
    )
    assert '"state": "CA"' in call_addr["result"]["content"][0]["text"]

    call_contact = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {
                "name": "standardize_contact",
                "arguments": {"street1": "350 Fifth Ave", "city": "New York", "state": "NY", "postal_code": "10118", "phone": "555-2368"},
            },
        }
    )
    assert "+12125552368" in call_contact["result"]["content"][0]["text"]

    for tool_id, tool_name, tool_args, expected_substr in [
        (33, "standardize_company", {"name": "Siemens GmbH"}, '"inferred_country_iso2": "DE"'),
        (34, "standardize_person", {"name": "Smith, Jr., Bob"}, '"person_root_key": "SMITH|ROBERT"'),
        (35, "standardize_email", {"email": "user@gmial.com"}, '"email": "user@gmail.com"'),
        (36, "standardize_url", {"url": "acme.com"}, '"url": "https://acme.com"'),
        (37, "standardize_social", {"profile": "https://twitter.com/jack"}, '"platform": "X"'),
    ]:
        resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": tool_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": tool_args},
            }
        )
        assert expected_substr in resp["result"]["content"][0]["text"]

    call_country = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "lookup_country_dial_plan", "arguments": {"identifier": "GB"}},
        }
    )
    assert '"calling_code": "44"' in call_country["result"]["content"][0]["text"]

    call_mask = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "mask_phone", "arguments": {"phone": "+14155552671", "strategy": "partial"}},
        }
    )
    assert "+1******2671" in call_mask["result"]["content"][0]["text"]

    call_unknown_tool = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}},
        }
    )
    assert call_unknown_tool["error"]["code"] == -32601

    call_unknown_method = handle_mcp_request({"jsonrpc": "2.0", "id": 7, "method": "unknown/method"})
    assert call_unknown_method["error"]["code"] == -32601


def test_phase6_global_remediations_and_edge_cases() -> None:
    # 1. Multi-phone primary extraction (';', '/', '&', ', ', '/XXXX') and XT./X. extensions
    assert standardize_phone("212-555-1234 / 212-555-5678").e164 == "+12125551234"
    assert standardize_phone("212-555-1234; 212-555-5678").e164 == "+12125551234"
    assert standardize_phone("443-797-7114 & 281-794-0077").e164 == "+14437977114"
    assert standardize_phone("1-787-425-0035/0036").e164 == "+17874250035"
    assert standardize_phone("212-555-1234, 212-555-5678").e164 == "+12125551234"
    assert standardize_phone("212-555-1234, 104").extension == "104"
    p_semi_ext = standardize_phone("+1 415-555-2671;1234")
    assert p_semi_ext.e164 == "+14155552671"
    assert p_semi_ext.extension == "1234"
    assert p_semi_ext.rfc3966 == "tel:+1-415-555-2671;ext=1234"
    assert HealingAction.EXTENSION_EXTRACTED in p_semi_ext.healing_actions
    assert HealingAction.MULTI_NUMBER_PRIMARY_SELECTED not in p_semi_ext.healing_actions
    p_xt = standardize_phone("415-424-4005 XT. 21")
    assert p_xt.e164 == "+14154244005" and p_xt.extension == "21"
    p_xdot = standardize_phone("212-354-6500 X. 304")
    assert p_xdot.e164 == "+12123546500" and p_xdot.extension == "304"

    # 2. Time range guard and embedded-digit vanity phone decoding
    assert standardize_phone("8:00AM - 6:00PM").is_valid is False
    vanity_emb = standardize_phone("(844) PLAN4IT")
    assert vanity_emb.e164 == "+18447526448"
    assert vanity_emb.vanity_alias == "(844)-PLAN4IT"

    # 3. Extended line-type classification (CA 7-digit UAN, NANP UAN/FIXED_LINE_OR_MOBILE, CL shared cost, IN fixed, GB personal, BR mobile)
    assert standardize_phone("+1 310-1234", country="CA").line_type == PhoneLineType.UAN
    assert standardize_phone("+1 242 225 1234", country="BS").line_type == PhoneLineType.UAN
    assert standardize_phone("+1 242 322 1234", country="BS").line_type == PhoneLineType.FIXED_LINE_OR_MOBILE
    assert standardize_phone("+56 600 123 4567", country="CL").line_type == PhoneLineType.SHARED_COST
    assert standardize_phone("+91 74104 12345", country="IN").line_type == PhoneLineType.FIXED_LINE
    assert standardize_phone("+44 70 1234 5678", country="GB").line_type == PhoneLineType.PERSONAL_NUMBER
    assert standardize_phone("+55 11 91234-5678", country="BR").line_type == PhoneLineType.MOBILE

    # 4. Redundant '011 +', '+00', and safe foreign '011' IDD exit prefix stripping
    p_011_plus = standardize_phone("011 +44 20 7946 0912")
    assert p_011_plus.e164 == "+442079460912"
    assert HealingAction.IDD_EXIT_PREFIX_STRIPPED in p_011_plus.healing_actions

    p_plus_00 = standardize_phone("+0041223188788", country="CH")
    assert p_plus_00.e164 == "+41223188788"
    assert HealingAction.IDD_EXIT_PREFIX_STRIPPED in p_plus_00.healing_actions

    p_011_gb = standardize_phone("011-44-20-7946-0912", country="GB")
    assert p_011_gb.e164 == "+442079460912"
    assert HealingAction.IDD_EXIT_PREFIX_STRIPPED in p_011_gb.healing_actions

    # 5. Bare international calling-code healing & anti-doubling vs domestic prefix collision guards
    assert standardize_phone("6568328282", country="SG").e164 == "+6568328282"
    assert standardize_phone("65123456", country="SG").e164 == "+6565123456"
    assert standardize_phone("352 26 1234", country="LU").e164 == "+352261234"
    assert standardize_phone("49 (0) 69 7560 1000", country="DE").e164 == "+496975601000"
    assert standardize_phone("49 069 7560 1000", country="DE").e164 == "+496975601000"
    assert standardize_phone("39 347 123 4567", country="IT").e164 == "+393471234567"
    assert standardize_phone("3921234567", country="IT").e164 == "+393921234567"
    assert standardize_phone("3931234567", country="IT").e164 == "+393931234567"
    assert standardize_phone("35212345", country="LU").e164 == "+35235212345"
    assert standardize_phone("9001234567", country="TR").e164 == "+909001234567"
    assert standardize_phone("(55) 3220-1234", country="BR").e164 == "+555532201234"
    assert standardize_phone("55991234567", country="BR").e164 == "+5555991234567"
    assert standardize_phone("9123456789", country="IN").e164 == "+919123456789"
    assert standardize_phone("483621234", country="PL").e164 == "+48483621234"
    assert standardize_phone("318123456", country="NL").e164 == "+31318123456"
    assert standardize_phone("9222123456", country="PK").e164 == "+929222123456"
    assert standardize_phone("841234567", country="VN").e164 == "+84841234567"
    assert standardize_phone("272712345", country="ZA").e164 == "+27272712345"

    # 6. Belarus (BY), Hungary (HU), and Brazil (BR) trunk / carrier prefix healing
    assert standardize_phone("80 17 229-40-00", country="BY").e164 == "+375172294000"
    assert standardize_phone("0 17 229-40-00", country="BY").e164 == "+375172294000"
    assert standardize_phone("8 17 229-40-00", country="BY").e164 == "+375172294000"
    assert standardize_phone("17 229-40-00", country="BY").e164 == "+375172294000"
    assert standardize_phone("06 1 234 5678", country="HU").e164 == "+3612345678"
    assert standardize_phone("01 234 5678", country="HU").e164 == "+3612345678"
    assert standardize_phone("1 234 5678", country="HU").e164 == "+3612345678"
    assert standardize_phone("021 11 98765-4321", country="BR").e164 == "+5511987654321"
    assert standardize_phone("+55 021 11 98765-4321", country="BR").e164 == "+5511987654321"

    # 7. Fallback bare international calling-code resolution when context_plan does not match
    assert standardize_phone("44 20 7946 0912", country="US").e164 == "+442079460912"
    assert standardize_phone("49 069 7560 1000", country="US").e164 == "+496975601000"
    assert standardize_phone("44 (0) 20 7946 0912", country="US").e164 == "+442079460912"

    # 8. Argentina 13-digit '+54 9 <area> 15 <subscr>' healing (2, 3, and 4 digit area codes)
    assert standardize_phone("+54 11 2345-6789", country="AR").e164 == "+541123456789"
    assert standardize_phone("+54 9 11 15 2345-6789", country="AR").e164 == "+5491123456789"
    assert standardize_phone("+54 9 351 15 234-5678", country="AR").e164 == "+5493512345678"
    assert standardize_phone("+54 9 2944 15 23-4567", country="AR").e164 == "+5492944234567"

    # 9. US territory ADDRESS_COUNTRY_MISMATCH exemption (both directions) & Toll-Free N11 exchange
    p_pr = standardize_phone("787-555-0244", country="US")
    assert p_pr.country_iso2 == "PR"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in p_pr.risk_flags

    p_us_from_pr = standardize_phone("212-555-1234", country="PR")
    assert p_us_from_pr.country_iso2 == "US"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in p_us_from_pr.risk_flags

    p_tf_n11 = standardize_phone("800-911-4567", country="US")
    assert p_tf_n11.is_valid is True
    assert p_tf_n11.line_type == PhoneLineType.TOLL_FREE

    # 10. ISO-8601 timestamp boundary guard in extract_phones_from_text
    extracted = extract_phones_from_text("2026-04-21T14:30:00-04:00 call (415) 555-2671")
    assert [m.e164 for m in extracted] == ["+14155552671"]


def test_milestone3_drive_dataset_remediations() -> None:
    from entity_standardizer.normalization import extract_extension, split_primary_phone

    # 1. Multi-number comma splitting without space
    p_multi = standardize_phone("5853254140,5854358032")
    assert p_multi.e164 == "+15853254140"
    assert p_multi.is_valid is True
    assert HealingAction.MULTI_NUMBER_PRIMARY_SELECTED in p_multi.healing_actions

    # Multi-number comma splitting with extension and third number
    p_multi_ext = standardize_phone("2149237666,5122220140ext7733,6309242400")
    assert p_multi_ext.e164 == "+12149237666"
    assert HealingAction.MULTI_NUMBER_PRIMARY_SELECTED in p_multi_ext.healing_actions

    # Multi-number with extension on primary
    p_primary_ext = standardize_phone("817-410-8200 ext. 9135,8178909135")
    assert p_primary_ext.e164 == "+18174108200"
    assert p_primary_ext.extension == "9135"
    assert HealingAction.MULTI_NUMBER_PRIMARY_SELECTED in p_primary_ext.healing_actions
    assert HealingAction.EXTENSION_EXTRACTED in p_primary_ext.healing_actions

    # Pipe delimiter before extension
    p_pipe_ext = standardize_phone("800.366.7266 | ext. 3211")
    assert p_pipe_ext.e164 == "+18003667266"
    assert p_pipe_ext.extension == "3211"

    # In-line '#' extension syntax up to 10 digits
    p_hash_ext = standardize_phone("6032262004#233,6179472393")
    assert p_hash_ext.e164 == "+16032262004"
    assert p_hash_ext.extension == "233"

    p_hash_single = standardize_phone("5126717526#101")
    assert p_hash_single.e164 == "+15126717526"
    assert p_hash_single.extension == "101"

    # Vanity candidate without space before letters
    p_vanity = standardize_phone("(844)PLAN4IT")
    assert p_vanity.e164 == "+18447526448"
    assert p_vanity.vanity_alias == "(844)PLAN4IT"

    # Domestic '01' and '0' trunk healing for NANP
    p_01_nanp = standardize_phone("01-703-47-8020")
    assert p_01_nanp.e164 == "+17034780200"
    assert HealingAction.NATIONAL_TRUNK_STRIPPED in p_01_nanp.healing_actions

    p_01_12digit = standardize_phone("01-415-555-2671")
    assert p_01_12digit.e164 == "+14155552671"
    assert HealingAction.NATIONAL_TRUNK_STRIPPED in p_01_12digit.healing_actions

    p_0_11digit = standardize_phone("0-415-555-2671")
    assert p_0_11digit.e164 == "+14155552671"
    assert HealingAction.NATIONAL_TRUNK_STRIPPED in p_0_11digit.healing_actions

    p_0_invalid_npa = standardize_phone("0-999-555-2671")
    assert p_0_invalid_npa.is_valid is False
    assert PhoneRiskFlag.INVALID_LENGTH in p_0_invalid_npa.risk_flags

    # 11-digit non-NANP international dialing code resolution
    p_be = standardize_phone("32455113280")
    assert p_be.e164 == "+32455113280"
    assert p_be.country_iso2 == "BE"

    p_ch = standardize_phone("41442178372")
    assert p_ch.e164 == "+41442178372"
    assert p_ch.country_iso2 == "CH"

    p_au = standardize_phone("61383198111")
    assert p_au.e164 == "+61383198111"
    assert p_au.country_iso2 == "AU"

    # Switzerland legacy lengths (7, 8 digits)
    p_ch_leg7 = standardize_phone("+41 22 123 456")
    assert p_ch_leg7.country_iso2 == "CH"
    p_ch_leg8 = standardize_phone("+41 22 123 4567")
    assert p_ch_leg8.e164 == "+41221234567"
    assert p_ch_leg8.country_iso2 == "CH"

    # Address context with UK outcodes and Crown Dependencies / Overseas Territories
    p_gb_w1f = standardize_phone("020 7845 8534", address_context={"postal_code": "W1F 8"})
    assert p_gb_w1f.e164 == "+442078458534"
    assert p_gb_w1f.country_iso2 == "GB"

    p_gb_ec1a = standardize_phone("020 3824 9955", address_context={"postal_code": "EC1A"})
    assert p_gb_ec1a.e164 == "+442038249955"
    assert p_gb_ec1a.country_iso2 == "GB"

    p_je = standardize_phone("01534 123456", address_context={"postal_code": "JE2 3RP"})
    assert p_je.e164 == "+441534123456"
    assert p_je.country_iso2 == "JE"

    p_gg = standardize_phone("01481 123456", address_context={"postal_code": "GY1 1AA"})
    assert p_gg.e164 == "+441481123456"
    assert p_gg.country_iso2 == "GG"

    p_im = standardize_phone("01624 123456", address_context={"postal_code": "IM1 2PQ"})
    assert p_im.e164 == "+441624123456"
    assert p_im.country_iso2 == "IM"

    p_ky = standardize_phone("345-949-1234", address_context={"postal_code": "KY1-1102"})
    assert p_ky.e164 == "+13459491234"
    assert p_ky.country_iso2 == "KY"

    p_bm = standardize_phone("441-295-1234", address_context={"postal_code": "HM 08"})
    assert p_bm.e164 == "+14412951234"
    assert p_bm.country_iso2 == "BM"

    # split_primary_phone edge cases
    assert split_primary_phone("2125551234") == ("2125551234", False)
    assert split_primary_phone("123;456") == ("123;456", False)
    assert split_primary_phone("2125551234 | 2125555678") == ("2125551234", True)
    assert split_primary_phone("2125551234, 123") == ("2125551234, 123", False)
    assert split_primary_phone("2125551234, 104, 2125555678") == ("2125551234, 104", True)

    # extract_extension edge cases
    assert extract_extension("2125551234")[1] is None
    assert extract_extension("2125551234 |")[0] == "2125551234"
    assert extract_extension("2125551234ext101") == ("2125551234", "101")
    assert extract_extension("2125551234xt999") == ("2125551234", "999")
    assert extract_extension("818,985,2000") == ("818,985,2000", None)
    assert extract_extension("1,800,555,1212,345") == ("1,800,555,1212,345", None)
    assert extract_extension("1,800,555,1212") == ("1,800,555,1212", None)
    assert extract_extension("212-555-1234, 104") == ("212-555-1234", "104")
    assert extract_extension("212-555-1234, ext. 104") == ("212-555-1234", "104")
    assert extract_extension("2125551234#101") == ("2125551234", "101")

    # Milestone 3 engine hardening unit tests
    assert split_primary_phone("5853254140,5854358032;2125551234") == ("5853254140", True)
    assert split_primary_phone("5853254140,5854358032,2125551234") == ("5853254140", True)

    p_grp1 = standardize_phone("1,800,555,1212", country="US")
    assert p_grp1.is_valid is True and p_grp1.e164 == "+18005551212" and p_grp1.extension is None
    p_grp2 = standardize_phone("818,985,2000", country="US")
    assert p_grp2.is_valid is True and p_grp2.e164 == "+18189852000" and p_grp2.extension is None
    p_abut1 = standardize_phone("2125551234ext101", country="US")
    assert p_abut1.is_valid is True and p_abut1.e164 == "+12125551234" and p_abut1.extension == "101"
    p_abut2 = standardize_phone("4155552671ext9999", country="US")
    assert p_abut2.is_valid is True and p_abut2.e164 == "+14155552671" and p_abut2.extension == "9999"
    p_hash_lead = standardize_phone("#2125551234", country="US")
    assert p_hash_lead.is_valid is True and p_hash_lead.e164 == "+12125551234"
    p_multi_semi = standardize_phone("5853254140,5854358032;2125551234", country="US")
    assert p_multi_semi.is_valid is True and p_multi_semi.e164 == "+15853254140"
    p_taxski = standardize_phone("1800TAXSKI,9097848831", country="US")
    assert p_taxski.is_valid is True and p_taxski.e164 == "+19097848831"
    p_tight_ext = standardize_phone("7174362144ext25025,7176676902", country="US")
    assert p_tight_ext.is_valid is True and p_tight_ext.e164 == "+17174362144" and p_tight_ext.extension == "25025"

    # Additional phone cleaning improvements (concatenated NANP extensions, multi-phone fallback, space double NANP, UK trunks & cross-country guard)
    p_concat_ext1 = standardize_phone("5166711099380", country="US")
    assert p_concat_ext1.is_valid is True and p_concat_ext1.e164 == "+15166711099" and p_concat_ext1.extension == "380"
    p_concat_ext2 = standardize_phone("91553288851008", address_context={"country": "US", "state": "TX"})
    assert p_concat_ext2.is_valid is True and p_concat_ext2.e164 == "+19155328885" and p_concat_ext2.extension == "1008"
    p_concat_ext3 = standardize_phone("3145761166226", address_context={"country": "US", "state": "MO"})
    assert p_concat_ext3.is_valid is True and p_concat_ext3.e164 == "+13145761166" and p_concat_ext3.extension == "226"

    p_fallback1 = standardize_phone("1956468217,8307763662,9564682169")
    assert p_fallback1.is_valid is True and p_fallback1.e164 == "+18307763662"
    p_fallback2 = standardize_phone("2129448501#t.310,5164485499")
    assert p_fallback2.is_valid is True and p_fallback2.e164 == "+15164485499"
    p_fallback_vanity_primary = standardize_phone("1-800-FLOWERS,2125551234")
    assert p_fallback_vanity_primary.is_valid is True and p_fallback_vanity_primary.e164 == "+18003569377"
    p_fallback_all_bad = standardize_phone("1956468217,1800426375")
    assert p_fallback_all_bad.is_valid is False

    p_space_dbl1 = standardize_phone("212 937 8444 917 363 9568")
    assert p_space_dbl1.is_valid is True and p_space_dbl1.e164 == "+12129378444"
    p_space_dbl2 = standardize_phone("786 244-7346 786 458-8491")
    assert p_space_dbl2.is_valid is True and p_space_dbl2.e164 == "+17862447346"

    p_uk_11trunk = standardize_phone("01244662810")
    assert p_uk_11trunk.is_valid is True and p_uk_11trunk.e164 == "+441244662810" and p_uk_11trunk.country_iso2 == "GB"
    p_uk_mob_trunk = standardize_phone("07970202432")
    assert p_uk_mob_trunk.is_valid is True and p_uk_mob_trunk.e164 == "+447970202432" and p_uk_mob_trunk.country_iso2 == "GB"

    p_us_in_london1 = standardize_phone("9178229100", address_context={"postal_code": "EC4N"})
    assert p_us_in_london1.is_valid is True and p_us_in_london1.e164 == "+19178229100" and p_us_in_london1.country_iso2 == "US"
    p_us_in_london2 = standardize_phone("2128587000", country="GB")
    assert p_us_in_london2.is_valid is True and p_us_in_london2.e164 == "+12128587000" and p_us_in_london2.country_iso2 == "US"
    p_uk_bare_44 = standardize_phone("4401483688787", country="US")
    assert p_uk_bare_44.is_valid is True and p_uk_bare_44.e164 == "+441483688787" and p_uk_bare_44.country_iso2 == "GB"

    # AdvisorAtlas & Discovery dataset remediation tests
    p_encore = standardize_phone("877-6EN-CORE", country="US")
    assert p_encore.is_valid is True and p_encore.e164 == "+18776362673" and p_encore.vanity_alias == "877-6EN-CORE"
    p_401k1 = standardize_phone("855-508-401k", country="US")
    assert p_401k1.is_valid is True and p_401k1.e164 == "+18555084015" and p_401k1.vanity_alias == "855-508-401K"
    p_401k2 = standardize_phone("860-521-401k", country="US")
    assert p_401k2.is_valid is True and p_401k2.e164 == "+18605214015"

    p_uk_hyph = standardize_phone("442-072-922107", country="US")
    assert p_uk_hyph.is_valid is True and p_uk_hyph.e164 == "+442072922107" and p_uk_hyph.country_iso2 == "GB"
    p_cn_hyph = standardize_phone("861-862-168-8725")
    assert p_cn_hyph.is_valid is True and p_cn_hyph.e164 == "+8618621688725" and p_cn_hyph.country_iso2 == "CN"

    p_hyph_ext1 = standardize_phone("415-984-1915-1", country="US")
    assert p_hyph_ext1.is_valid is True and p_hyph_ext1.e164 == "+14159841915" and p_hyph_ext1.extension == "1"
    p_hyph_ext2 = standardize_phone("415-984-1915-1921")
    assert p_hyph_ext2.is_valid is True and p_hyph_ext2.e164 == "+14159841915" and p_hyph_ext2.extension == "1921"
    p_hyph_ext3 = standardize_phone("315-627-0474225", country="US")
    assert p_hyph_ext3.is_valid is True and p_hyph_ext3.e164 == "+13156270474" and p_hyph_ext3.extension == "225"

    p_hyph_multi1 = standardize_phone("800-965-2576-949-365-177")
    assert p_hyph_multi1.is_valid is True and p_hyph_multi1.e164 == "+18009652576"
    p_hyph_multi2 = standardize_phone("312-558-9400-800-969-3987")
    assert p_hyph_multi2.is_valid is True and p_hyph_multi2.e164 == "+13125589400"
    p_hyph_multi3 = standardize_phone("212-687-5650-6246633423")
    assert p_hyph_multi3.is_valid is True and p_hyph_multi3.e164 == "+12126875650"

    p_dup_exch = standardize_phone("307-771-771-3713")
    assert p_dup_exch.is_valid is True and p_dup_exch.e164 == "+13077713713"

    p_us_in_ch = standardize_phone("212-510-8477", country="CH")
    assert p_us_in_ch.is_valid is True and p_us_in_ch.e164 == "+12125108477" and p_us_in_ch.country_iso2 == "US"
    p_us_in_fr = standardize_phone("212-506-5610", country="FR")
    assert p_us_in_fr.is_valid is True and p_us_in_fr.e164 == "+12125065610" and p_us_in_fr.country_iso2 == "US"
    p_us_in_hk = standardize_phone("949-604-8929", country="HK")
    assert p_us_in_hk.is_valid is True and p_us_in_hk.e164 == "+19496048929" and p_us_in_hk.country_iso2 == "US"
    p_us_in_gi = standardize_phone("305-898-0672", country="GI")
    assert p_us_in_gi.is_valid is True and p_us_in_gi.e164 == "+13058980672" and p_us_in_gi.country_iso2 == "US"

    p_dup_cc_ch1 = standardize_phone("41-41-4151-14687", country="CH")
    assert p_dup_cc_ch1.is_valid is True and p_dup_cc_ch1.e164 == "+41415114687" and p_dup_cc_ch1.country_iso2 == "CH"
    p_dup_cc_ch2 = standardize_phone("0041-41-4151-14631", country="CH")
    assert p_dup_cc_ch2.is_valid is True and p_dup_cc_ch2.e164 == "+41415114631" and p_dup_cc_ch2.country_iso2 == "CH"
    p_dup_cc_au = standardize_phone("61-61292763030", country="AU")
    assert p_dup_cc_au.is_valid is True and p_dup_cc_au.e164 == "+61292763030" and p_dup_cc_au.country_iso2 == "AU"

    p_bare_sg = standardize_phone("65-6411-3000")
    assert p_bare_sg.is_valid is True and p_bare_sg.e164 == "+6564113000" and p_bare_sg.country_iso2 == "SG"
    p_bare_lu = standardize_phone("352-22-74-41")
    assert p_bare_lu.is_valid is True and p_bare_lu.e164 == "+352227441" and p_bare_lu.country_iso2 == "LU"
    p_bare_dk = standardize_phone("45-3154-7235")
    assert p_bare_dk.is_valid is True and p_bare_dk.e164 == "+4531547235" and p_bare_dk.country_iso2 == "DK"
    p_bare_no = standardize_phone("47-905-58-104")
    assert p_bare_no.is_valid is True and p_bare_no.e164 == "+4790558104" and p_bare_no.country_iso2 == "NO"

    # Global dirty dataset remediation tests (FSQ, Overture, Wikidata, SEC/DTCC)
    p_mx_dom10 = standardize_phone("5255123456", country="MX")
    assert p_mx_dom10.is_valid is True and p_mx_dom10.e164 == "+525255123456"
    p_cl_dom9 = standardize_phone("562123456", country="CL")
    assert p_cl_dom9.is_valid is True and p_cl_dom9.e164 == "+56562123456"

    p_gh_plus0 = standardize_phone("+0302123456", country="GH")
    assert p_gh_plus0.is_valid is True and p_gh_plus0.e164 == "+233302123456"

    p_es_plus1 = standardize_phone("+1971800450", country="ES")
    assert p_es_plus1.is_valid is True and p_es_plus1.e164 == "+34971800450"
    p_ru_plus18 = standardize_phone("+183834130584", country="RU")
    assert p_ru_plus18.is_valid is True and p_ru_plus18.e164 == "+73834130584"

    p_ca_plus_dom = standardize_phone("+418-835-5182", country="CA")
    assert p_ca_plus_dom.is_valid is True and p_ca_plus_dom.e164 == "+14188355182" and p_ca_plus_dom.country_iso2 == "CA"
    p_ca_plus_invalid = standardize_phone("+418-035-5182", country="CA")
    assert p_ca_plus_invalid.is_valid is False
    p_cl_plus_dom = standardize_phone("+341234567", country="CL")
    assert p_cl_plus_dom.is_valid is True and p_cl_plus_dom.e164 == "+56341234567" and p_cl_plus_dom.country_iso2 == "CL"

    p_intl_concat_ext = standardize_phone("+12125551234101", country="US")
    assert p_intl_concat_ext.is_valid is True and p_intl_concat_ext.e164 == "+12125551234" and p_intl_concat_ext.extension == "101"
    p_dom11_concat_ext = standardize_phone("12125551234101", country="US")
    assert p_dom11_concat_ext.is_valid is True and p_dom11_concat_ext.e164 == "+12125551234" and p_dom11_concat_ext.extension == "101"

    p_sx_mf = standardize_phone("0590 87 53 26", country="SX")
    assert p_sx_mf.is_valid is True and p_sx_mf.e164 == "+590590875326" and p_sx_mf.country_iso2 == "MF"

    p_lt_trunk8 = standardize_phone("8 5 268 2828", country="LT")
    assert p_lt_trunk8.is_valid is True and p_lt_trunk8.e164 == "+37052682828"

    p_jp_0066 = standardize_phone("0066-9711-0871660", country="JP")
    assert p_jp_0066.is_valid is True and p_jp_0066.e164 == "+816697110871660"

    p_cy_tr_0392 = standardize_phone("0392 227 51 43", country="CY")
    assert p_cy_tr_0392.is_valid is True and p_cy_tr_0392.e164 == "+903922275143" and p_cy_tr_0392.country_iso2 == "TR"
    p_cy_tr_392 = standardize_phone("392 227 51 43", country="CY")
    assert p_cy_tr_392.is_valid is True and p_cy_tr_392.e164 == "+903922275143" and p_cy_tr_392.country_iso2 == "TR"
    p_cy_11_non_tr = standardize_phone("0222 227 51 43", country="CY")
    assert p_cy_11_non_tr.is_valid is False

    p_la_nanp11 = standardize_phone("1-337-232-1111", country="LA")
    assert p_la_nanp11.is_valid is True and p_la_nanp11.e164 == "+13372321111" and p_la_nanp11.country_iso2 == "US"


def test_joint_cross_healing_and_phase7_upgrades() -> None:
    from entity_standardizer import standardize_entity as std_ent
    from entity_standardizer import (
        CrossHealingAction,
        batch_standardize_contacts,
        infer_nanp_npa_from_context,
        resolve_international_region,
        standardize_batch_with_country_dispatch,
        standardize_contact,
    )
    assert std_ent is standardize_contact

    # 1. infer_nanp_npa_from_context & resolve_international_region
    assert infer_nanp_npa_from_context("US", "NY") == "212"
    assert infer_nanp_npa_from_context("US", "New York") == "212"
    assert infer_nanp_npa_from_context("US", "ZZ") is None
    assert infer_nanp_npa_from_context(None, "ZZ") is None
    assert infer_nanp_npa_from_context("PR", None) == "787"
    assert infer_nanp_npa_from_context("GB", None) is None
    assert resolve_international_region("GB", "2079460912") == "London"
    assert resolve_international_region("GB", "7911123456") is None
    assert resolve_international_region("XX", "123456") is None

    # 2. standardize_batch_with_country_dispatch (native and pure-Python fallback)
    pairs = [("(415) 555-2671", "US"), ("020 7946 0912", "GB")]
    assert standardize_batch_with_country_dispatch(pairs) == ["+14155552671", "+442079460912"]
    saved = native_dispatch._native_mod
    try:
        native_dispatch._native_mod = None
        assert standardize_batch_with_country_dispatch(pairs) == ["+14155552671", "+442079460912"]
        assert standardize_batch_with_country_dispatch([("4155552671", "1")]) == ["+14155552671"]
    finally:
        native_dispatch._native_mod = saved

    # 3. Phase 7 standardizer.py upgrades
    # Calling code 1-digit typo healing (+40 -> +44 on JE/GB, and +33 -> +34 on ES)
    p_cc_je = standardize_phone("+40 1534 756100", country="JE")
    assert p_cc_je.is_valid is True and p_cc_je.e164 == "+441534756100" and p_cc_je.country_iso2 == "JE"
    assert HealingAction.CALLING_CODE_HEALED_FROM_CONTEXT in p_cc_je.healing_actions

    p_cc_es = standardize_phone("+33 91123456", country="ES")
    assert p_cc_es.is_valid is False

    p_cc_ro_to_no = standardize_phone("+40 21234567", country="NO")
    assert p_cc_ro_to_no.is_valid is True and p_cc_ro_to_no.e164 == "+4721234567"

    # +1 1 NXX-NXX-XXXX redundant trunk after +1
    p_plus1_1 = standardize_phone("+1 1 800-555-1212", country="US")
    assert p_plus1_1.is_valid is True and p_plus1_1.e164 == "+18005551212"

    # 7-digit local NPA inference from state/territory context and non-inferable fallback
    p_local7_ny = standardize_phone("555-2368", country="US", address_context={"state": "NY"})
    assert p_local7_ny.is_valid is True and p_local7_ny.e164 == "+12125552368"
    assert HealingAction.LOCAL_NPA_INFERRED_FROM_CONTEXT in p_local7_ny.healing_actions

    p_local7_none = standardize_phone("555-2368", country="US")
    assert p_local7_none.is_valid is False

    # 11-digit hyphenated NANP extra-digit healing (trailing and leading extra digit)
    p_extra_tail = standardize_phone("212-555-23689", country="US")
    assert p_extra_tail.is_valid is True and p_extra_tail.e164 == "+12125552368"
    assert HealingAction.TRUNCATED_OR_EXTRA_DIGIT_HEALED in p_extra_tail.healing_actions

    p_extra_head = standardize_phone("9212-555-2368", country="US")
    assert p_extra_head.is_valid is True and p_extra_head.e164 == "+12125552368"
    assert HealingAction.TRUNCATED_OR_EXTRA_DIGIT_HEALED in p_extra_head.healing_actions

    # Cyprus 444XXXX Turkish call-center short code
    p_cy_444 = standardize_phone("444 1 444", country="CY")
    assert p_cy_444.is_valid is True and p_cy_444.e164 == "+904441444" and p_cy_444.country_iso2 == "TR"
    p_cy_7_other = standardize_phone("222 1 444", country="CY")
    assert p_cy_7_other.is_valid is False

    # 4. Joint Contact Standardization & Bidirectional Cross-Healing
    # A. Rescue pure phone from street1
    c_s1_pure = standardize_contact(street1="(212) 555-2368", city="New York", state="NY", postal_code="10001")
    assert c_s1_pure.phone.e164 == "+12125552368"
    assert CrossHealingAction.PHONE_RESCUED_FROM_ADDRESS_FIELD.value in c_s1_pure.cross_healing_actions
    assert c_s1_pure.to_dict()["phone"]["e164"] == "+12125552368"

    # B. Rescue labeled phone from street1
    c_s1_lbl = standardize_contact(
        street1="350 Fifth Ave Tel: (212) 555-2368", city="New York", state="NY", postal_code="10118"
    )
    assert c_s1_lbl.phone.e164 == "+12125552368"
    assert c_s1_lbl.address.street1 == "350 5TH AVE"

    # C. Rescue pure phone and labeled phone from street2
    c_s2_pure = standardize_contact(
        street1="350 Fifth Ave", street2="(212) 555-2368", city="New York", state="NY", postal_code="10118"
    )
    assert c_s2_pure.phone.e164 == "+12125552368"

    c_s2_lbl = standardize_contact(
        street1="350 Fifth Ave", street2="Suite 400 | (212) 555-2368", city="New York", state="NY", postal_code="10118"
    )
    assert c_s2_lbl.phone.e164 == "+12125552368"

    # Street1/street2 with non-phone or invalid phone when phone is missing
    c_no_rescue = standardize_contact(
        street1="350 Fifth Ave Tel: 1234567", street2="Suite 100 Tel: 1234567", city="New York", state="NY"
    )
    assert c_no_rescue.phone.is_valid is False

    c_pure_inv = standardize_contact(street1="1234567", street2="1234567", city="New York")
    assert c_pure_inv.phone.is_valid is False

    # D. Infer address country from international phone when country omitted
    c_intl = standardize_contact(street1="10 Downing Street", city="London", postal_code="SW1A 2AA", phone="+44 20 7946 0912")
    assert c_intl.address.country == "GBR"
    assert CrossHealingAction.ADDRESS_COUNTRY_INFERRED_FROM_PHONE.value in c_intl.cross_healing_actions

    # E. Heal US Address ERR_ZIP_STATE_MISMATCH from Phone NPA
    c_state_heal = standardize_contact(
        street1="350 Fifth Ave", city="New York", state="CA", postal_code="10118", phone="(212) 555-2368", country="US"
    )
    assert c_state_heal.address.state == "NY"
    assert CrossHealingAction.ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA.value in c_state_heal.cross_healing_actions

    # Mismatch where ZIP state does not match phone state
    c_unhealed = standardize_contact(
        street1="350 Fifth Ave", city="New York", state="NY", postal_code="90210", phone="(212) 555-2368", country="US"
    )
    assert c_unhealed.address.postal_code == "90210"

    # F. Standardized Address -> Phone healing (e.g., state inferred from ZIP heals 7-digit local phone, plus fax)
    c_addr_to_phone = standardize_contact(
        street1="350 Fifth Ave", city="New York", postal_code="10118", phone="555-2368", fax="555-2369", country="US"
    )
    assert c_addr_to_phone.phone.e164 == "+12125552368"
    assert c_addr_to_phone.fax is not None and c_addr_to_phone.fax.e164 == "+12125552369"
    assert CrossHealingAction.PHONE_HEALED_FROM_STANDARDIZED_ADDRESS.value in c_addr_to_phone.cross_healing_actions

    # Empty address with valid phone (overall_confidence fallback to phone confidence)
    c_phone_only = standardize_contact(phone="(415) 555-2671")
    assert c_phone_only.overall_confidence == c_phone_only.phone.confidence

    # Completely empty contact
    c_empty = standardize_contact()
    assert c_empty.entity_key is None

    # Batch standardize contacts
    batch_res = batch_standardize_contacts(
        [{"street1": "350 Fifth Ave", "city": "New York", "state": "NY", "postal_code": "10118", "phone": "555-2368"}]
    )
    assert len(batch_res) == 1 and batch_res[0].phone.e164 == "+12125552368"

    # G. Regression tests for v2.0.0 cross-healing & UK 11-digit trunk prefix ordering
    import subprocess
    import sys

    import entity_standardizer as ent_pkg
    import entity_standardizer.__main__ as ent_main
    import entity_standardizer.address as addr_pkg

    assert ent_main.main is not None
    assert ent_pkg.is_native_available() == addr_pkg.is_native_available()
    assert ent_pkg.cluster_contact_records is not None
    assert ent_pkg.ContactCluster is not None
    assert ent_pkg.PhoneCluster is not None
    assert ent_pkg.PhoneComparisonResult is not None
    assert ent_pkg.AddressValidationResult is not None
    assert ent_pkg.generate_phonetic_address_key is not None
    assert ent_pkg.autocomplete_address is not None
    assert ent_pkg.explain_phone is not None
    assert "standardize_arrow" in dir(ent_pkg)
    assert callable(ent_pkg.standardize_arrow)

    # Verify cold import in a fresh process does not load heavy optional integrations
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, entity_standardizer, entity_standardizer.address; "
                "heavy = ('pyarrow', 'polars', 'duckdb', 'fastapi', 'pydantic'); "
                "loaded = [m for m in heavy if m in sys.modules]; "
                "assert not loaded, f'Unexpectedly loaded: {loaded}'; "
                "assert 'standardize_arrow' in dir(entity_standardizer)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


    # Unformatted 11-digit UK numbers must not be hijacked by NANP area codes (e.g. 212, 207)
    p_uk_bham = standardize_phone("01212345678")
    assert p_uk_bham.is_valid is True and p_uk_bham.e164 == "+441212345678" and p_uk_bham.country_iso2 == "GB"
    p_uk_lon = standardize_phone("02079460912")
    assert p_uk_lon.is_valid is True and p_uk_lon.e164 == "+442079460912" and p_uk_lon.country_iso2 == "GB"

    # Empty address must not corrupt UK mobile 0781 into US MA (+1781) or record ADDRESS_COUNTRY_INFERRED_FROM_PHONE
    c_uk_mob_empty = standardize_contact(phone="0781 234 5678", default_country="GB")
    assert c_uk_mob_empty.phone.e164 == "+447812345678" and c_uk_mob_empty.phone.country_iso2 == "GB"
    assert c_uk_mob_empty.cross_healing_actions == []

    c_uk_intl_empty = standardize_contact(phone="+44 20 7946 0912")
    assert c_uk_intl_empty.phone.e164 == "+442079460912"
    assert CrossHealingAction.ADDRESS_COUNTRY_INFERRED_FROM_PHONE.value not in c_uk_intl_empty.cross_healing_actions

    # Domestic US addresses (single-line and structured) must not have country overwritten by foreign phone
    c_us_single_uk_ph = standardize_contact(street1="123 Main St, New York, NY 10001", phone="+44 20 7946 0912")
    assert c_us_single_uk_ph.address.country == "USA" and c_us_single_uk_ph.address.is_us is True
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in c_us_single_uk_ph.phone.risk_flags
    assert CrossHealingAction.ADDRESS_COUNTRY_INFERRED_FROM_PHONE.value not in c_us_single_uk_ph.cross_healing_actions

    c_us_struct_uk_ph = standardize_contact(
        street1="123 Main St", city="New York", state="NY", postal_code="10001", phone="+44 20 7946 0912"
    )
    assert c_us_struct_uk_ph.address.country == "USA" and c_us_struct_uk_ph.address.is_us is True
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in c_us_struct_uk_ph.phone.risk_flags

    # Single-line UK address healing formatted UK phone (020 7946 0912) and embedded phone in street1
    c_uk_single_heal = standardize_contact(street1="10 Downing St, London SW1A 2AA", phone="020 7946 0912")
    assert c_uk_single_heal.address.country == "GBR"
    assert c_uk_single_heal.phone.e164 == "+442079460912" and c_uk_single_heal.phone.country_iso2 == "GB"
    assert CrossHealingAction.PHONE_HEALED_FROM_STANDARDIZED_ADDRESS.value in c_uk_single_heal.cross_healing_actions

    c_uk_rescued_heal = standardize_contact(street1="10 Downing St, London SW1A 2AA Tel: 020 7946 0912")
    assert c_uk_rescued_heal.address.country == "GBR"
    assert c_uk_rescued_heal.phone.e164 == "+442079460912" and c_uk_rescued_heal.phone.country_iso2 == "GB"
    assert CrossHealingAction.PHONE_RESCUED_FROM_ADDRESS_FIELD.value in c_uk_rescued_heal.cross_healing_actions
    assert CrossHealingAction.PHONE_HEALED_FROM_STANDARDIZED_ADDRESS.value in c_uk_rescued_heal.cross_healing_actions

    # Step 4 retry of _try_rescue_phone_from_street when 7-digit local phone needs state inferred from ZIP
    c_rescue_step4 = standardize_contact(street1="350 Fifth Ave Tel: 555-2368", city="New York", postal_code="10118")
    assert c_rescue_step4.phone.e164 == "+12125552368"
    assert c_rescue_step4.address.street1 == "350 5TH AVE"
    assert CrossHealingAction.PHONE_RESCUED_FROM_ADDRESS_FIELD.value in c_rescue_step4.cross_healing_actions
    assert CrossHealingAction.PHONE_HEALED_FROM_STANDARDIZED_ADDRESS.value in c_rescue_step4.cross_healing_actions

    # Single-line international addresses with trailing phones must not pollute state or fail rescue
    c_fr_comma_ph = standardize_contact(street1="10 Rue de Rivoli, 75001 Paris, France, 01 42 68 55 00")
    assert c_fr_comma_ph.phone.e164 == "+33142685500" and c_fr_comma_ph.address.country == "FRA"
    assert c_fr_comma_ph.address.state == "" and c_fr_comma_ph.address.city == "PARIS"

    c_fr_tel_single = standardize_contact(street1="10 Rue de Rivoli, 75001 Paris Tel: 01 42 68 55 00")
    assert c_fr_tel_single.phone.e164 == "+33142685500" and c_fr_tel_single.address.country == "FRA"
    assert c_fr_tel_single.address.city == "PARIS" and c_fr_tel_single.address.postal_code == "75001"

    c_de_tel_single = standardize_contact(street1="Friedrichstrasse 100, 10117 Berlin Tel: 030 1234567")
    assert c_de_tel_single.phone.e164 == "+49301234567" and c_de_tel_single.address.country == "DEU"

    # Non-US default_country on street address without explicit country must not default to USA or corrupt phone
    c_uk_def_mob = standardize_contact(street1="10 High St", phone="0781 234 5678", default_country="GB")
    assert c_uk_def_mob.address.country == "GBR"
    assert c_uk_def_mob.phone.e164 == "+447812345678" and c_uk_def_mob.phone.country_iso2 == "GB"
    assert c_uk_def_mob.cross_healing_actions == []

    c_uk_def_no_ph = standardize_contact(street1="10 High St", default_country="GB")
    assert c_uk_def_no_ph.address.country == "GBR"

    # Single-line US address with trailing <City> <5-digit ZIP> (with or without comma, no state) must not be overwritten by foreign phone
    import entity_standardizer.address.us_street_parser as usp

    saved_usa = usp.usaddress
    try:
        for us_mod in (saved_usa, None):
            usp.usaddress = us_mod
            c_us_zip_uk_ph = standardize_contact(street1="123 Main St, Austin 78701", phone="+44 20 7946 0912")
            assert c_us_zip_uk_ph.address.country == "USA" and c_us_zip_uk_ph.address.state == "TX"
            assert c_us_zip_uk_ph.address.city == "AUSTIN" and c_us_zip_uk_ph.address.postal_code == "78701"
            assert c_us_zip_uk_ph.phone.region_code == "London"
            assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in c_us_zip_uk_ph.phone.risk_flags

            c_us_nocomma = standardize_contact(street1="123 Main St Austin 78701", phone="+44 20 7946 0912")
            assert c_us_nocomma.address.street1 == "123 MAIN ST" and c_us_nocomma.address.city == "AUSTIN"
            assert c_us_nocomma.address.state == "TX" and c_us_nocomma.address.country == "USA"
            assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in c_us_nocomma.phone.risk_flags

            c_us_ny = standardize_contact(street1="123 Main St, New York 10001", phone="+44 20 7946 0912")
            assert c_us_ny.address.street1 == "123 MAIN ST" and c_us_ny.address.city == "NEW YORK"
            assert c_us_ny.address.state == "NY" and c_us_ny.address.country == "USA"

            c_us_stl = standardize_contact(street1="123 Main St St. Louis 63101", phone="+44 20 7946 0912")
            assert c_us_stl.address.street1 == "123 MAIN ST" and c_us_stl.address.city == "ST LOUIS"
            assert c_us_stl.address.state == "MO" and c_us_stl.address.country == "USA"

            c_us_pob = standardize_contact(street1="PO Box 100 Austin 78701", phone="+44 20 7946 0912")
            assert c_us_pob.address.street1 == "PO BOX 100" and c_us_pob.address.city == "AUSTIN"
            assert c_us_pob.address.state == "TX" and c_us_pob.address.country == "USA"
    finally:
        usp.usaddress = saved_usa

    c_stl_struct = standardize_contact(
        street1="123 Main St", city="St. Louis", postal_code="63101", phone="+44 20 7946 0912"
    )
    assert c_stl_struct.address.country == "USA" and c_stl_struct.address.state == "MO"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in c_stl_struct.phone.risk_flags

    c_aus_def_gb = standardize_contact(
        street1="123 Main St", city="Austin", postal_code="78701", default_country="GB"
    )
    assert c_aus_def_gb.address.country == "USA" and c_aus_def_gb.address.state == "TX"

    # European 5-digit postal codes (metro, non-US ZIP, or mismatched US ZIP city) must not trigger false US mismatch
    c_fr_paris = standardize_contact(
        street1="10 Rue de Rivoli", city="Paris", postal_code="75001", phone="+33 1 42 68 55 00"
    )
    assert c_fr_paris.address.country == "FRA"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in c_fr_paris.phone.risk_flags
    assert CrossHealingAction.ADDRESS_COUNTRY_INFERRED_FROM_PHONE.value in c_fr_paris.cross_healing_actions
    assert CrossHealingAction.PHONE_HEALED_FROM_STANDARDIZED_ADDRESS.value not in c_fr_paris.cross_healing_actions

    c_fr_vers = standardize_contact(
        street1="10 Rue de la Paroisse", city="Versailles", postal_code="78000", phone="+33 1 42 68 55 00"
    )
    assert c_fr_vers.address.country == "FRA"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in c_fr_vers.phone.risk_flags

    c_es_toledo = standardize_contact(
        street1="Calle Mayor 1", city="Toledo", postal_code="45001", phone="+34 925 22 33 44"
    )
    assert c_es_toledo.address.country == "ESP"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in c_es_toledo.phone.risk_flags

    c_es_toledo_single = standardize_contact(street1="Calle Mayor 1, Toledo 45001", phone="+34 925 22 33 44")
    assert c_es_toledo_single.address.country == "ESP"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in c_es_toledo_single.phone.risk_flags

    c_fr_lyon_single = standardize_contact(street1="10 Avenue Victor Hugo, Lyon 69002", phone="+33 4 72 10 30 30")
    assert c_fr_lyon_single.address.country == "FRA"
    assert PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in c_fr_lyon_single.phone.risk_flags
    assert c_fr_lyon_single.address.street1 == "10 AV VICTOR HUGO"

    # Batch E.164 dispatch parity for 11-digit UK domestic numbers (both native and pure Python)
    from entity_standardizer import _native_dispatch as nd

    assert nd.standardize_batch_e164_dispatch(["01212345678", "02079460912"], "1") == [
        "+441212345678",
        "+442079460912",
    ]
    saved_mod = nd._native_mod
    try:
        nd._native_mod = None
        assert nd.standardize_batch_e164_dispatch(["01212345678", "02079460912"], "1") == [
            "+441212345678",
            "+442079460912",
        ]
    finally:
        nd._native_mod = saved_mod

    # Semicolon/comma/pipe extension parity (7-digit extensions without space, multi-phone after extension, Rust vs Python)
    for raw_ext_phone, exp_ext in [
        ("212-555-0199; x1234567", "1234567"),
        ("212-555-0199; ext1234567", "1234567"),
        ("212-555-0199; xt1234567", "1234567"),
        ("212-555-0199; x123; 415-555-2671", "123"),
    ]:
        p_ext = standardize_phone(raw_ext_phone)
        assert p_ext.is_valid is True and p_ext.e164 == "+12125550199" and p_ext.extension == exp_ext

    ext_batch_inputs = [
        "212-555-0199;x123",
        "212-555-0199;xt123",
        "212-555-0199;xt. 45",
        "212-555-0199,x123",
        "212-555-0199|x123",
        "+298 123456;ext. 45",
        "212-555-0199; x123; 415-555-2671",
    ]
    expected_ext_batch = [
        "+12125550199",
        "+12125550199",
        "+12125550199",
        "+12125550199",
        "+12125550199",
        "+298123456",
        "+12125550199",
    ]
    assert nd.standardize_batch_e164_dispatch(ext_batch_inputs, "1") == expected_ext_batch
    try:
        nd._native_mod = None
        assert nd.standardize_batch_e164_dispatch(ext_batch_inputs, "1") == expected_ext_batch
    finally:
        nd._native_mod = saved_mod

    # Free-text phone extraction preserves semicolon extensions
    extracted_semi = extract_phones_from_text("Call us at +1-212-555-0199; ext=123 or 212-555-0199; ext. 45")
    assert [(r.e164, r.extension) for r in extracted_semi] == [
        ("+12125550199", "123"),
        ("+12125550199", "45"),
    ]

    # Rescuing misplaced phones with extensions from street1 and street2
    c_rescue_ext1 = standardize_contact(
        street1="123 Main St, Tel: 212-555-0199 ext 123", city="New York", state="NY", postal_code="10001"
    )
    assert c_rescue_ext1.phone.e164 == "+12125550199" and c_rescue_ext1.phone.extension == "123"
    assert c_rescue_ext1.address.street1 == "123 MAIN ST" and c_rescue_ext1.address.street2 == ""

    c_rescue_ext2 = standardize_contact(
        street1="123 Main St", street2="212-555-0199 ext 123", city="New York", state="NY", postal_code="10001"
    )
    assert c_rescue_ext2.phone.e164 == "+12125550199" and c_rescue_ext2.phone.extension == "123"
    assert c_rescue_ext2.address.street1 == "123 MAIN ST" and c_rescue_ext2.address.street2 == ""

    # Inferring missing US state from phone NPA when city matches state (and rejecting mismatched city)
    c_infer_st = standardize_contact(street1="350 Fifth Ave", city="New York", phone="212-555-0199")
    assert c_infer_st.address.state == "NY"
    assert CrossHealingAction.ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA.value in c_infer_st.cross_healing_actions

    c_infer_st_stlouis = standardize_contact(street1="100 Market St", city="St. Louis", phone="314-555-0199")
    assert c_infer_st_stlouis.address.state == "MO"
    assert CrossHealingAction.ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA.value in c_infer_st_stlouis.cross_healing_actions

    c_mismatch_city = standardize_contact(street1="233 S Wacker Dr", city="Chicago", phone="212-555-0199")
    assert c_mismatch_city.address.state == ""

