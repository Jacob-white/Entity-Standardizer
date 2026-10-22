"""Tests for the 249 ISO-3166-1 Country Dial-Plan Registry and NANP NPA Resolver."""

from __future__ import annotations

from phone_standardizer import (
    CountryDialRegistry,
    get_dial_plan,
    normalize_country_iso2,
    resolve_nanp_npa,
)


def test_all_249_iso_countries_present() -> None:
    plans = CountryDialRegistry.all_plans()
    assert len(plans) == 249
    for plan in plans:
        assert len(plan.iso2) == 2
        assert len(plan.iso3) == 3
        assert len(plan.numeric) == 3
        assert plan.calling_code.isdigit()
        assert plan.to_dict()["iso2"] == plan.iso2


def test_country_lookup_variants() -> None:
    assert get_dial_plan(None) is None
    assert get_dial_plan("   ") is None
    assert get_dial_plan("ZZZ") is None
    assert get_dial_plan("US").iso2 == "US"  # type: ignore[union-attr]
    assert get_dial_plan("GBR").iso2 == "GB"  # type: ignore[union-attr]
    assert get_dial_plan("UK").iso2 == "GB"  # type: ignore[union-attr]
    assert get_dial_plan("840").iso2 == "US"  # type: ignore[union-attr]
    assert get_dial_plan("Japan").iso2 == "JP"  # type: ignore[union-attr]
    assert normalize_country_iso2("United Kingdom") == "GB"
    assert normalize_country_iso2("UNKNOWN") is None


def test_calling_code_matching_variants() -> None:
    # NANP Caribbean
    plan_pr, nsn_pr, reg_pr, rec_pr = CountryDialRegistry.match_calling_code("17875550244")
    assert plan_pr is not None and plan_pr.iso2 == "PR"
    assert nsn_pr == "7875550244"
    assert reg_pr == "PR"
    assert rec_pr is True

    # UK Crown Dependencies: Jersey, Guernsey, Isle of Man
    plan_je, _, reg_je, _ = CountryDialRegistry.match_calling_code("441534555123")
    assert plan_je is not None and plan_je.iso2 == "JE" and reg_je == "JE"

    plan_gg, _, reg_gg, _ = CountryDialRegistry.match_calling_code("441481555123")
    assert plan_gg is not None and plan_gg.iso2 == "GG" and reg_gg == "GG"

    plan_im, _, reg_im, _ = CountryDialRegistry.match_calling_code("441624555123")
    assert plan_im is not None and plan_im.iso2 == "IM" and reg_im == "IM"

    plan_gb, _, reg_gb, _ = CountryDialRegistry.match_calling_code("4402079460912")
    assert plan_gb is not None and plan_gb.iso2 == "GB" and reg_gb is None

    # Russia vs Kazakhstan (+7)
    plan_kz, _, _, _ = CountryDialRegistry.match_calling_code("77015551234")
    assert plan_kz is not None and plan_kz.iso2 == "KZ"

    plan_ru, _, _, _ = CountryDialRegistry.match_calling_code("74955551234")
    assert plan_ru is not None and plan_ru.iso2 == "RU"

    # Shared calling code (+61 Australia / Christmas Island / Cocos Islands)
    plan_cx, _, reg_cx, _ = CountryDialRegistry.match_calling_code("61891641234")
    assert plan_cx is not None and plan_cx.iso2 == "CX" and reg_cx is None

    plan_cc, _, reg_cc, _ = CountryDialRegistry.match_calling_code("61891621234")
    assert plan_cc is not None and plan_cc.iso2 == "CC" and reg_cc is None

    # Shared +61 non-geographic with hint_iso2="CX"
    plan_cx_hint, _, _, _ = CountryDialRegistry.match_calling_code("611800123456", hint_iso2="CX")
    assert plan_cx_hint is not None and plan_cx_hint.iso2 == "CX"

    # Shared calling code with non-matching hint or no hint falls back to primary (AU)
    plan_au, _, _, _ = CountryDialRegistry.match_calling_code("61299991234", hint_iso2="DE")
    assert plan_au is not None and plan_au.iso2 == "AU"

    plan_au2, _, _, _ = CountryDialRegistry.match_calling_code("61299991234", hint_iso2=None)
    assert plan_au2 is not None and plan_au2.iso2 == "AU"

    # Sub-area prefix matching across +39 (VA/IT), +47 (SJ/NO), +358 (AX/FI), +212 (EH/MA), +262 (YT/RE), +599 (BQ/CW), +290 (TA/SH)
    assert CountryDialRegistry.match_calling_code("390669812345")[0].iso2 == "VA"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("39061234567")[0].iso2 == "IT"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("4779123456")[0].iso2 == "SJ"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("4721123456")[0].iso2 == "NO"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("3581812345")[0].iso2 == "AX"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("3589123456")[0].iso2 == "FI"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("212528812345")[0].iso2 == "EH"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("212537123456")[0].iso2 == "MA"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("262269123456")[0].iso2 == "YT"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("262262123456")[0].iso2 == "RE"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("5997171234")[0].iso2 == "BQ"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("59991234567")[0].iso2 == "CW"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("2908123")[0].iso2 == "TA"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("29022123")[0].iso2 == "SH"  # type: ignore[union-attr]

    # Shared non-geographic hint preservation on +1, +44, +7
    assert CountryDialRegistry.match_calling_code("129955", hint_iso2="CA")[0].iso2 == "CA"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("12995550199", hint_iso2="CA")[0].iso2 == "CA"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("12995550199", hint_iso2="DE")[0].iso2 == "US"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("448001234567", hint_iso2="JE")[0].iso2 == "JE"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("78005551234", hint_iso2="KZ")[0].iso2 == "KZ"  # type: ignore[union-attr]

    # Supplemental territories (+247 AC, +383 XK) and expanded aliases
    assert CountryDialRegistry.match_calling_code("24765432")[0].iso2 == "AC"  # type: ignore[union-attr]
    assert CountryDialRegistry.match_calling_code("38338123456")[0].iso2 == "XK"  # type: ignore[union-attr]
    assert normalize_country_iso2("CAYMAN   ISLANDS") == "KY"
    assert normalize_country_iso2("Kosovo") == "XK"

    # Unassigned calling code (000...)
    plan_none, nsn_none, _, rec_none = CountryDialRegistry.match_calling_code("000123")
    assert plan_none is None and nsn_none == "000123" and rec_none is False


def test_nanp_npa_resolution() -> None:
    assert resolve_nanp_npa("787") == ("PR", "PR", True)
    assert resolve_nanp_npa("416") == ("CA", "ON", True)
    assert resolve_nanp_npa("212") == ("US", "NY", True)
    assert resolve_nanp_npa("800", fallback_iso2="CA") == ("CA", None, True)
    assert resolve_nanp_npa("800", fallback_iso2="KY") == ("KY", None, True)
    assert resolve_nanp_npa("800", fallback_iso2="DE") == ("US", None, True)
    # Unallocated but structurally valid NPA (e.g. 299)
    assert resolve_nanp_npa("299", fallback_iso2="US") == ("US", None, False)
    assert resolve_nanp_npa("299", fallback_iso2="GB") == ("US", None, False)
    # Structurally invalid NPA (starts with 0 or 1, or N11)
    assert resolve_nanp_npa("012") == ("US", None, False)
    assert resolve_nanp_npa("911") == ("US", None, False)

    # Phase 5 & Phase 6 US/CA overlay NPAs (achieving 439/439 NANPA parity)
    for overlay_npa, expected_country, expected_state in [
        ("227", "US", "MD"),
        ("235", "US", "MO"),
        ("324", "US", "FL"),
        ("327", "US", "AR"),
        ("329", "US", "NY"),
        ("350", "US", "CA"),
        ("353", "US", "WI"),
        ("369", "US", "CA"),
        ("436", "US", "OH"),
        ("526", "US", "CA"),
        ("624", "US", "NY"),
        ("686", "US", "VA"),
        ("728", "US", "FL"),
        ("730", "US", "IL"),
        ("738", "US", "CA"),
        ("748", "US", "CO"),
        ("821", "US", "SC"),
        ("840", "US", "CA"),
        ("861", "US", "IL"),
        ("924", "US", "MN"),
        ("257", "CA", "BC"),
        ("273", "CA", "ON"),
    ]:
        assert resolve_nanp_npa(overlay_npa) == (expected_country, expected_state, True)


def test_phase5_dial_plan_registry_precision() -> None:
    # Closed dialing plans (national_trunk_prefix is None)
    for closed_iso in (
        "PT", "GR", "CZ", "CL", "CR", "PA", "LU", "IS", "MT", "CY", "QA", "KW", "BH", "OM",
        "UZ", "HN", "SV", "NI", "GT", "BZ", "HT", "GQ", "CF", "CM", "KM", "DJ", "LS", "MU",
        "SC", "CV", "ST", "TG", "ML", "NE", "BF", "BJ", "GW", "PF", "CK", "FO", "GL", "SM",
    ):
        plan = get_dial_plan(closed_iso)
        assert plan is not None
        assert plan.national_trunk_prefix is None, f"Expected None trunk prefix for {closed_iso}"

    # Kazakhstan & Belarus use trunk '8' and IDD '810'
    for cis_iso in ("KZ", "BY"):
        plan = get_dial_plan(cis_iso)
        assert plan is not None
        assert plan.national_trunk_prefix == "8"
        assert plan.idd_prefix == "810"

    # Hungary uses trunk '06'
    hu = get_dial_plan("HU")
    assert hu is not None and hu.national_trunk_prefix == "06"

    # Indonesia supports 7-13 digit NSNs (including 11-12 digit mobiles)
    id_plan = get_dial_plan("ID")
    assert id_plan is not None and 11 in id_plan.nsn_lengths and 12 in id_plan.nsn_lengths

    # Saudi Arabia (9 digits, mobile 5) & Hong Kong (8 digits) & Taiwan (8-9 digits, mobile 9)
    sa = get_dial_plan("SA")
    assert sa is not None and 9 in sa.nsn_lengths and "5" in sa.mobile_prefixes
    hk = get_dial_plan("HK")
    assert hk is not None and 8 in hk.nsn_lengths and hk.national_trunk_prefix is None
    tw = get_dial_plan("TW")
    assert tw is not None and 8 in tw.nsn_lengths and 9 in tw.nsn_lengths and "9" in tw.mobile_prefixes

