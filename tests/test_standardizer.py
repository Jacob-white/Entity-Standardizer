"""Comprehensive unit and integration tests for Phone Standardizer (100% coverage suite)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import phone_standardizer.__main__ as main_mod
import phone_standardizer._native_dispatch as native_dispatch
from phone_standardizer import (
    HealingAction,
    PhoneLineType,
    PhoneRiskFlag,
    PhoneRoutingTier,
    batch_standardize_phones,
    decode_vanity_phone,
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
from phone_standardizer.cli import main as cli_main
from phone_standardizer.mcp import handle_mcp_request
from phone_standardizer.server import app


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
    from phone_standardizer.models import CountryDialPlan
    from phone_standardizer.standardizer import _format_numbers, _split_area_and_subscriber
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


def test_mcp_server_requests() -> None:
    init_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp["result"]["serverInfo"]["name"] == "phone-standardizer-mcp"

    list_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(list_resp["result"]["tools"]) == 6

    call_std = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "standardize_phone", "arguments": {"phone": "(415) 555-2671"}},
        }
    )
    assert "+14155552671" in call_std["result"]["content"][0]["text"]

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
