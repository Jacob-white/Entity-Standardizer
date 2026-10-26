"""Comprehensive unit tests for confidence scoring, calibration, delivery intelligence, corporate risk registry, and stewardship audit ledger."""

from __future__ import annotations

from pathlib import Path
import pytest

from entity_standardizer.address import (
    ActionType,
    ConfidenceScorer,
    DPVFootnote,
    RDI,
    ReviewStatus,
    RoutingTier,
    StewardshipAuditLedger,
    StewardshipAuditRecord,
    can_safely_merge_corporate_entities,
    compute_confidence_score,
    evaluate_corporate_risk,
    evaluate_delivery_intelligence,
    lookup_corporate_registry,
    standardize_address,
)
from entity_standardizer.address.calibration import (
    Calibrator,
    brier_score,
    calibrate_score,
    expected_calibration_error,
    fit_isotonic,
    reliability_bins,
)
from entity_standardizer.address.confidence import compute_field_confidence
from entity_standardizer.address.delivery import Deliverability


def test_confidence_scoring_and_calibration(tmp_path: Path) -> None:
    scorer = ConfidenceScorer()

    # High-confidence AUTO_PASS address
    good = standardize_address("100 Wall St Ste 400", city="New York", state="NY", postal_code="10005")
    res_good = scorer.score(good, raw_input={"street1": "100 Wall St Ste 400"})
    assert res_good.composite_score >= 0.90
    assert res_good.as_dict()["routing_tier"] in (RoutingTier.AUTO_PASS, RoutingTier.FUZZY_REVIEW)

    # Locality-only FUZZY_REVIEW
    loc = standardize_address(city="Austin", state="TX", postal_code="78701", allow_locality=True)
    res_loc = compute_confidence_score(loc)
    assert res_loc.routing_tier == RoutingTier.FUZZY_REVIEW
    assert "WARN_LOCALITY_ONLY" in res_loc.failure_reason_codes

    # Empty / parse_failed MANUAL_STEWARDSHIP
    bad = standardize_address("")
    res_bad = compute_confidence_score(bad, raw_input={})
    assert res_bad.routing_tier == RoutingTier.MANUAL_STEWARDSHIP
    assert res_bad.composite_score == 0.0

    # Dual address, ZIP-state mismatch, missing house number, landmark premise
    mismatch = standardize_address("350 Fifth Ave", city="New York", state="CA", postal_code="10118")
    res_mm = compute_confidence_score(
        mismatch,
        raw_input={"street1": "PO Box 100, 350 Fifth Ave", "state_corrected_from": "CA"},
        dpv_confirmed="N",
    )
    assert "ERR_ZIP_STATE_MISMATCH" in res_mm.failure_reason_codes
    assert "ERR_AMBIGUOUS_DUAL_ADDR" in res_mm.failure_reason_codes
    assert "ERR_DPV_UNCONFIRMED" in res_mm.failure_reason_codes

    no_num = standardize_address("Main Street", city="Boston", state="MA", postal_code="02108")
    res_nn = compute_confidence_score(no_num, raw_input="Main Street")
    assert "ERR_MISSING_HOUSE_NUM" in res_nn.failure_reason_codes

    campus = standardize_address("One Infinite Loop Plaza", city="Cupertino", state="CA", postal_code="95014")
    fc = compute_field_confidence(campus)
    assert "street1" in fc and "postal_code" in fc

    # Calibration utilities
    pairs = [(0.1, False), (0.2, False), (0.5, True), (0.5, False), (0.8, True), (0.95, True), (0.99, True)]
    bins = reliability_bins(pairs, n_bins=5)
    assert len(bins) >= 2
    assert "accuracy" in bins[0].as_dict()
    ece = expected_calibration_error(pairs, n_bins=5)
    brier = brier_score(pairs)
    assert 0.0 <= ece <= 1.0
    assert 0.0 <= brier <= 1.0

    cal = fit_isotonic(pairs)
    assert 0.0 <= cal.calibrate(0.0) <= 1.0
    assert 0.0 <= cal.calibrate(0.6) <= 1.0
    assert 0.0 <= cal.calibrate(1.0) <= 1.0
    assert calibrate_score(0.75, None) == 0.75
    assert 0.0 <= calibrate_score(0.75, cal) <= 1.0

    cal_path = tmp_path / "calibrator.json"
    cal.save(cal_path)
    loaded_cal = Calibrator.load(cal_path)
    assert loaded_cal.to_dict() == cal.to_dict()

    res_with_cal = compute_confidence_score(good, calibrator=loaded_cal)
    assert res_with_cal.calibrated_score is not None

    with pytest.raises(ValueError):
        reliability_bins([], n_bins=5)
    with pytest.raises(ValueError):
        reliability_bins([(1.5, True)], n_bins=5)
    with pytest.raises(ValueError):
        reliability_bins([(0.5, True)], n_bins=0)


def test_delivery_intelligence_and_corporate_registry() -> None:
    # Commercial suite
    deliv_comm = evaluate_delivery_intelligence(
        street1="350 Fifth Ave",
        street2="Ste 4200",
        city="New York",
        state="NY",
        postal_code="10118",
    )
    assert deliv_comm.rdi == RDI.COMMERCIAL
    assert DPVFootnote.AA in deliv_comm.dpv_footnotes
    assert DPVFootnote.CC in deliv_comm.dpv_footnotes
    assert deliv_comm.deliverability == Deliverability.DELIVERABLE
    assert deliv_comm.as_dict()["rdi"] == "Commercial"

    # Residential apartment
    deliv_res = evaluate_delivery_intelligence(
        street1="400 E 54th St",
        street2="Apt 12B",
        city="New York",
        state="NY",
        postal_code="10022",
    )
    assert deliv_res.rdi == RDI.RESIDENTIAL
    assert deliv_res.is_cmra is False

    # CMRA / PMB & Vacant
    deliv_cmra = evaluate_delivery_intelligence(
        street1="500 N Michigan Ave PMB 104",
        city="Chicago",
        state="IL",
        postal_code="60611",
        raw_input={"street1": "The UPS Store 500 N Michigan Ave PMB 104", "vacant": True},
    )
    assert deliv_cmra.is_cmra is True
    assert deliv_cmra.is_vacant is True

    # High-rise multi-unit building missing secondary unit -> N1 footnote
    deliv_n1 = evaluate_delivery_intelligence(
        street1="100 Wall St",
        city="New York",
        state="NY",
        postal_code="10005",
    )
    assert DPVFootnote.N1 in deliv_n1.dpv_footnotes
    assert deliv_n1.secondary_prompt_required is True
    assert deliv_n1.deliverability == Deliverability.REQUIRES_SECONDARY

    # PO Box, Rural Route, Military, International
    deliv_pob = evaluate_delivery_intelligence(street1="PO Box 500", city="Dallas", state="TX", postal_code="75201")
    assert DPVFootnote.PB in deliv_pob.dpv_footnotes
    deliv_rr = evaluate_delivery_intelligence(street1="RR 2 Box 15", city="Springfield", state="IL", postal_code="62701")
    assert DPVFootnote.RR in deliv_rr.dpv_footnotes
    deliv_intl = evaluate_delivery_intelligence(street1="10 Downing St", city="London", postal_code="SW1A 2AA", country="GB")
    assert deliv_intl.rdi == RDI.UNKNOWN

    # Corporate Registry & BOI Risk
    entry_de = lookup_corporate_registry("1209 N Orange St", "", "Wilmington", "DE", "19801")
    assert entry_de is not None and "Corporation Trust" in entry_de.provider_name

    entry_wy = lookup_corporate_registry("30 N Gould St", "Ste R", "Sheridan", "WY", "82801")
    assert entry_wy is not None

    std_de = standardize_address("1209 N Orange St", city="Wilmington", state="DE", postal_code="19801")
    score, flags = evaluate_corporate_risk(std_de)
    assert score > 0.5
    assert len(flags) >= 1

    # Co-location safety guard: two companies at 1209 N Orange St must not auto-merge on address alone
    allowed_de, reason_de = can_safely_merge_corporate_entities(std_de, std_de)
    assert allowed_de is False and "CO_LOCATION" in reason_de
    std_norm = standardize_address("450 Lexington Ave", city="New York", state="NY", postal_code="10017")
    allowed_norm, _ = can_safely_merge_corporate_entities(std_norm, std_norm)
    assert allowed_norm is True


def test_stewardship_audit_ledger_lifecycle(tmp_path: Path) -> None:
    db_file = str(tmp_path / "audit.db")
    ledger = StewardshipAuditLedger(db_path=db_file)

    std = standardize_address("1209 N Orange St", city="Wilmington", state="DE", postal_code="19801")
    conf = compute_confidence_score(std)
    rec = ledger.record_standardized_address(std, conf, raw_input={"street1": "1209 N Orange St"}, batch_id="B-1")
    assert rec.audit_id is not None
    assert ledger.ensure_recorded(rec).audit_id == rec.audit_id

    # Duplicate record raises ValueError
    with pytest.raises(ValueError):
        ledger.record(rec)

    fetched = ledger.get_record(rec.audit_id)
    assert fetched is not None and fetched.record_id == rec.record_id
    assert len(ledger.list_records(review_status=ReviewStatus.PENDING, limit=10)) >= 1

    # Steward manual override preserves history
    updated = ledger.apply_manual_override(
        rec.audit_id,
        steward_id="steward_alice",
        overrides={"street2": "STE 400"},
        commentary="Confirmed suite on filing",
        review_status=ReviewStatus.MODIFIED,
    )
    assert updated.action_type == ActionType.MANUAL_OVERRIDE
    assert updated.review_status == ReviewStatus.MODIFIED
    hist = ledger.history(rec.audit_id)
    assert len(hist) == 1

    # Reject override
    rejected = ledger.apply_manual_override(
        rec.audit_id,
        steward_id="steward_bob",
        overrides={},
        commentary="Invalid filing",
        review_status=ReviewStatus.REJECTED,
    )
    assert rejected.final_committed_payload == {}

    # Exports
    assert isinstance(ledger.export("dict"), list)
    assert "address_stewardship_audit_ledger" in str(ledger.export("sql"))
    assert rec.audit_id in str(ledger.export("json"))
    assert StewardshipAuditRecord.from_dict(rec.as_dict()).audit_id == rec.audit_id

    ledger.clear()
    assert len(ledger.list_records()) == 0


def test_confidence_and_registry_exhaustive() -> None:
    from types import SimpleNamespace
    from entity_standardizer.address.calibration import fit_isotonic
    from entity_standardizer.address.confidence import compute_confidence_score, compute_field_confidence
    from entity_standardizer.address.registry import (
        can_safely_merge_corporate_entities,
        evaluate_corporate_risk,
        is_registered_agent_hub_address,
        lookup_corporate_registry,
    )

    cal = fit_isotonic([(0.1, False), (0.5, True), (0.9, True)])

    # 1. ConfidenceScorer locality-only, private residence, DPV Y/N, cascade_precision tiers, foreign postal, raw_input str mismatch, city anomalies, disguised PMB
    loc_us_missing = SimpleNamespace(
        street1="",
        street2="",
        city="BOSTON",
        state="",
        postal_code="",
        country="USA",
        is_us=True,
        address_status="locality_only",
        is_locality_only=True,
        is_registered_agent_hub=True,
        is_private_residence=True,
        is_cmra=True,
        is_vacant=True,
    )
    r_loc_us = compute_confidence_score(loc_us_missing, calibrator=cal)
    assert "WARN_LOCALITY_ONLY" in r_loc_us.failure_reason_codes
    assert "WARN_CRA_HUB_DETECTED" in r_loc_us.failure_reason_codes
    assert "calibrated_score" in r_loc_us.as_dict()

    priv_addr = SimpleNamespace(
        street1="PRIVATE RESIDENCE",
        street2="",
        city="BOSTON",
        state="MA",
        postal_code="02110",
        country="USA",
        is_us=True,
        is_private_residence=True,
        is_registered_agent_hub=False,
        address_status="standardized",
        is_locality_only=False,
    )
    assert compute_confidence_score(priv_addr, dpv_confirmed="Y").s_geo == 1.0
    assert compute_confidence_score(priv_addr, dpv_confirmed="N").s_ref_match < 1.0
    assert compute_confidence_score(priv_addr).s_ref_match == 1.0

    for prec in ("CONFIRMED_ROOFTOP", "FALLBACK_TIGER", "FALLBACK_ZIP3", "FALLBACK_STATE", "OTHER_PREC"):
        r_prec = compute_confidence_score(priv_addr, cascade_precision=prec)
        assert r_prec.s_geo > 0.0

    foreign_in_us = SimpleNamespace(
        street1="100 MAIN ST",
        street2="",
        city="ZURICH 8001",
        state="USA-XX",
        postal_code="",
        country="CHE",
        is_us=False,
        is_private_residence=False,
        is_registered_agent_hub=False,
        address_status="standardized",
        is_locality_only=False,
    )
    r_fiu = compute_confidence_score(foreign_in_us)
    assert "WARN_POSTAL_IN_CITY" in r_fiu.failure_reason_codes

    # raw_input as string with mismatched state token + city anomalies + disguised PMB
    anom_addr = SimpleNamespace(
        street1="100 MAIN ST",
        street2="STE 205",
        city="NORTH",
        state="US-NY",
        postal_code="10005",
        country="USA",
        is_us=True,
        is_private_residence=False,
        is_registered_agent_hub=True,
        is_cmra=True,
        is_vacant=True,
        dpv_footnotes=["N1"],
        address_status="standardized",
        is_locality_only=False,
    )
    r_anom = compute_confidence_score(anom_addr, raw_input={"street1": "100 Main St PMB 205", "state": "USA-CA"})
    assert "ERR_ZIP_STATE_MISMATCH" in r_anom.failure_reason_codes
    assert "ERR_CITY_ANOMALY" in r_anom.failure_reason_codes
    assert "WARN_PMB_DISGUISED" in r_anom.failure_reason_codes
    assert "WARN_MISSING_SECONDARY_UNIT" in r_anom.failure_reason_codes

    r_str = compute_confidence_score(anom_addr, raw_input="100 Main St")
    assert r_str.composite_score > 0.0

    # 2. compute_field_confidence exhaustive branches
    assert compute_field_confidence(SimpleNamespace(street1="", city="", state="", postal_code="", country="", is_us=True))["street1"] == 0.0
    assert compute_field_confidence(SimpleNamespace(street1="PRIVATE RESIDENCE", is_private_residence=True, city="BOSTON", state="MA", postal_code="02110", country="USA", is_us=True))["street1"] == 0.30
    fc_ev = compute_field_confidence(
        SimpleNamespace(
            street1="100 MAIN ST",
            street2="STE 200",
            city="BOSTON",
            state="XX",
            postal_code="02110",
            country="ZZ",
            is_us=True,
            failure_reason_codes=[
                "ERR_MISSING_HOUSE_NUM",
                "ERR_UNRESOLVED_SUFFIX",
                "WARN_LANDMARK_CAMPUS_PREMISE",
                "ERR_ZIP_STATE_MISMATCH",
            ],
        ),
        evidence={
            "rules": {
                "street1": ["typo_heal_street", "secondary_promoted_to_street", "token_rewritten"],
                "street2": ["unit_split", "street1_moved_to_street2", "number_words_to_digits"],
                "city": ["city_canonicalized"],
                "state": ["state_from_zip"],
                "postal_code": ["postal_transposition_healed"],
            },
            "reference_status": "state_mismatch",
            "postal_valid": False,
        },
        calibrator=cal,
    )
    assert fc_ev["country"] <= 1.0
    fc_ev2 = compute_field_confidence(
        SimpleNamespace(street1="100 MAIN ST", street2="", city="BOSTON", state="MA", postal_code="02110", country="USA", is_us=True),
        evidence={"reference_status": "place_mismatch"},
    )
    assert fc_ev2["city"] < 0.95
    fc_ev3 = compute_field_confidence(
        SimpleNamespace(street1="100 MAIN ST", street2="", city="BOSTON", state="MA", postal_code="02110", country="USA", is_us=True),
        evidence={"reference_status": "postal_unknown", "rules": {"state": ["state_corrected_from_zip"]}},
    )
    assert fc_ev3["postal_code"] == 0.30

    # 3. registry.py branches
    assert lookup_corporate_registry("", "", "", "", "") is None

    e_de = lookup_corporate_registry("1209 N Orange St", "", "Wilmington", "DE", "19801")
    assert e_de is not None and e_de.as_dict()["state"] == "DE"
    assert lookup_corporate_registry("1209 N Orange St", "", "Wilmington", "DE", "") is not None
    assert lookup_corporate_registry("251 Little Falls Dr", "", "", "", "19808") is not None
    assert lookup_corporate_registry("1209 N Orange St, Wilmington, DE 19801", "", "", "", "") is not None
    # Contradicting city or ZIP skips entry
    assert lookup_corporate_registry("1209 N Orange St", "", "Newark", "DE", "19801") is None
    assert lookup_corporate_registry("1209 N Orange St", "", "Wilmington", "DE", "90210") is None
    # Secondary unit required by tower hub (e.g. 28 Liberty St Ste 4200)
    assert lookup_corporate_registry("28 Liberty St", "Ste 4200", "New York", "NY", "10005") is not None
    assert lookup_corporate_registry("28 Liberty St", "Ste 999", "New York", "NY", "10005") is None
    assert lookup_corporate_registry("28 Liberty St", "", "New York", "NY", "10005") is None
    # International entries & jurisdiction veto
    assert lookup_corporate_registry("Ugland House", "", "George Town", "", "KY1-1104", country="CYM") is not None
    assert lookup_corporate_registry("Ugland House, Cayman Islands", "", "", "", "", country="USA") is not None
    assert lookup_corporate_registry("Clarendon House, 2 Church St", "", "Hamilton", "ON", "L8P 4W7", country="CAN") is None

    assert is_registered_agent_hub_address("", "", "", "", "") is False
    assert is_registered_agent_hub_address("Ugland House", "", "George Town", "", "KY1-1104", country="CYM") is True

    # evaluate_corporate_risk: private residence suppression, hub without secondary unit, disguised PMB
    priv_dict = {"street1": "PRIVATE RESIDENCE", "is_private_residence": True, "is_registered_agent_hub": True}
    p_score, p_flags = evaluate_corporate_risk(priv_dict)
    assert p_score == 0.40 and priv_dict["is_registered_agent_hub"] is False
    priv_obj = SimpleNamespace(street1="PRIVATE RESIDENCE", is_private_residence=True, is_registered_agent_hub=True)
    evaluate_corporate_risk(priv_obj)
    assert priv_obj.is_registered_agent_hub is False

    # Virtual office, offshore secrecy, trust fiduciary, mail drop categories + fallback is_registered_agent_hub=True
    for st1_h, st2_h, city_h, st_h, zip_h, co_h in (
        ("1209 N Orange St", "", "Wilmington", "DE", "19801", "USA"),
        ("Ugland House", "", "George Town", "", "KY1-1104", "CYM"),
        ("Bahnhofstrasse 10", "", "Zug", "", "6300", "CHE"),
    ):
        evaluate_corporate_risk({"street1": st1_h, "street2": st2_h, "city": city_h, "state": st_h, "postal_code": zip_h, "country": co_h})

    fb_score, _ = evaluate_corporate_risk({"street1": "100 UNKNOWN RD", "is_registered_agent_hub": True, "street2": "PMB 104"})
    assert fb_score >= 0.85
    pmb_disguised, pmb_flags = evaluate_corporate_risk(
        {"street1": "100 MAIN ST", "street2": "STE 104"},
        raw_input={"street1": "100 Main St PMB 104"},
    )
    assert pmb_disguised >= 0.65 and len(pmb_flags) >= 2
    pmb_raw_only, _ = evaluate_corporate_risk(
        {"street1": "100 MAIN ST", "street2": ""},
        raw_input={"street1": "100 Main St PMB 104"},
    )
    assert pmb_raw_only >= 0.60

    # can_safely_merge_corporate_entities: empty, private residence, distinct buildings, unflagged hub, CMRA, secondary unit match/mismatch/asymmetry/key_mismatch
    assert can_safely_merge_corporate_entities({"street1": ""}, {"street1": ""})[0] is False
    assert can_safely_merge_corporate_entities(
        {"street1": "PRIVATE RESIDENCE", "building_key": "PRIVATE RESIDENCE||BOSTON|MA|02110|USA"},
        {"street1": "PRIVATE RESIDENCE", "building_key": "PRIVATE RESIDENCE||BOSTON|MA|02110|USA"},
    )[0] is False
    assert can_safely_merge_corporate_entities(
        {"street1": "100 MAIN ST", "building_key": "B1"},
        {"street1": "200 OAK AVE", "building_key": "B2"},
    )[0] is False
    # Unflagged hub caught by defense-in-depth lookup
    assert can_safely_merge_corporate_entities(
        {"street1": "1209 N ORANGE ST", "city": "WILMINGTON", "state": "DE", "postal_code": "19801", "building_key": "1209 N ORANGE ST||WILMINGTON|DE|19801|USA"},
        {"street1": "1209 N ORANGE ST", "city": "WILMINGTON", "state": "DE", "postal_code": "19801", "building_key": "1209 N ORANGE ST||WILMINGTON|DE|19801|USA"},
    )[0] is False
    # CMRA co-location block
    assert can_safely_merge_corporate_entities(
        {"street1": "500 N MICHIGAN AVE", "building_key": "B_CMRA", "is_cmra": True},
        {"street1": "500 N MICHIGAN AVE", "building_key": "B_CMRA", "is_cmra": True},
    )[0] is False
    # Secondary unit matching, key mismatch, unit mismatch, single-tenant key mismatch, and unit asymmetry
    assert can_safely_merge_corporate_entities(
        {"street1": "100 MAIN ST", "street2": "STE 100", "building_key": "B_OK", "normalized_address_key": "K1"},
        {"street1": "100 MAIN ST", "street2": "STE 100", "building_key": "B_OK", "normalized_address_key": "K1"},
    )[0] is True
    assert can_safely_merge_corporate_entities(
        {"street1": "100 MAIN ST", "street2": "STE 100", "building_key": "B_OK", "normalized_address_key": "K1"},
        {"street1": "100 MAIN ST", "street2": "STE 100", "building_key": "B_OK", "normalized_address_key": "K2"},
    )[0] is False
    assert can_safely_merge_corporate_entities(
        {"street1": "100 MAIN ST", "street2": "STE 100", "building_key": "B_OK"},
        {"street1": "100 MAIN ST", "street2": "STE 200", "building_key": "B_OK"},
    )[0] is False
    assert can_safely_merge_corporate_entities(
        {"street1": "100 MAIN ST", "street2": "", "building_key": "B_OK", "normalized_address_key": "K1"},
        {"street1": "100 MAIN ST", "street2": "", "building_key": "B_OK", "normalized_address_key": "K2"},
    )[0] is False
    assert can_safely_merge_corporate_entities(
        {"street1": "100 MAIN ST", "street2": "STE 100", "building_key": "B_OK"},
        {"street1": "100 MAIN ST", "street2": "", "building_key": "B_OK"},
    )[0] is False


