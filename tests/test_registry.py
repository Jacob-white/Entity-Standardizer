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

    # Shared calling code (+61 Australia / Christmas Island with hint)
    plan_cx, _, _, _ = CountryDialRegistry.match_calling_code("61891641234", hint_iso2="CX")
    assert plan_cx is not None and plan_cx.iso2 == "CX"

    # Shared calling code with non-matching hint falls back to primary
    plan_au, _, _, _ = CountryDialRegistry.match_calling_code("61891641234", hint_iso2="DE")
    assert plan_au is not None and plan_au.iso2 == "AU"

    # Shared calling code without hint falls back to primary
    plan_au2, _, _, _ = CountryDialRegistry.match_calling_code("61891641234", hint_iso2=None)
    assert plan_au2 is not None and plan_au2.iso2 == "AU"

    # Unassigned calling code (000...)
    plan_none, nsn_none, _, rec_none = CountryDialRegistry.match_calling_code("000123")
    assert plan_none is None and nsn_none == "000123" and rec_none is False


def test_nanp_npa_resolution() -> None:
    assert resolve_nanp_npa("787") == ("PR", "PR", True)
    assert resolve_nanp_npa("416") == ("CA", "ON", True)
    assert resolve_nanp_npa("212") == ("US", "NY", True)
    assert resolve_nanp_npa("800", fallback_iso2="CA") == ("CA", None, True)
    assert resolve_nanp_npa("800", fallback_iso2="DE") == ("US", None, True)
    # Unallocated but structurally valid NPA (e.g. 299)
    assert resolve_nanp_npa("299", fallback_iso2="US") == ("US", None, False)
    assert resolve_nanp_npa("299", fallback_iso2="GB") == ("US", None, False)
    # Structurally invalid NPA (starts with 0 or 1, or N11)
    assert resolve_nanp_npa("012") == ("US", None, False)
    assert resolve_nanp_npa("911") == ("US", None, False)

    # Phase 5: 17 newest US overlay NPAs
    for overlay_npa, expected_state in [
        ("324", "FL"),
        ("327", "AR"),
        ("329", "NY"),
        ("350", "CA"),
        ("353", "WI"),
        ("369", "CA"),
        ("436", "OH"),
        ("526", "CA"),
        ("624", "NY"),
        ("686", "VA"),
        ("728", "FL"),
        ("730", "IL"),
        ("738", "CA"),
        ("821", "SC"),
        ("840", "CA"),
        ("861", "IL"),
        ("924", "MN"),
    ]:
        assert resolve_nanp_npa(overlay_npa) == ("US", expected_state, True)


def test_phase5_dial_plan_registry_precision() -> None:
    # Closed dialing plans (national_trunk_prefix is None)
    for closed_iso in ("PT", "GR", "CZ", "CL", "CO", "UY", "CR", "PA", "LU", "IS", "MT", "CY", "QA", "KW", "BH", "OM"):
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

    # Indonesia supports 9-12 digit NSNs (including 11-12 digit mobiles)
    id_plan = get_dial_plan("ID")
    assert id_plan is not None and 11 in id_plan.nsn_lengths and 12 in id_plan.nsn_lengths

    # Saudi Arabia (9 digits, mobile 5) & Hong Kong (8 digits) & Taiwan (8-9 digits, mobile 9)
    sa = get_dial_plan("SA")
    assert sa is not None and sa.nsn_lengths == (9,) and "5" in sa.mobile_prefixes
    hk = get_dial_plan("HK")
    assert hk is not None and hk.nsn_lengths == (8,) and hk.national_trunk_prefix is None
    tw = get_dial_plan("TW")
    assert tw is not None and tw.nsn_lengths == (8, 9) and "9" in tw.mobile_prefixes

