"""Synthetic Unit Tests for Cross-System Matcher, Calibration, Registries & International Postal Keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from entity_standardizer import (
    BlockingRule,
    CrossSystemMatcher,
    LabeledEntityPair,
    MatchDisposition,
    SignalEvidence,
    StandardizedAddress,
    compare_persons,
    compute_switchboard_phones,
    evaluate_scoring_calibration,
    explain_and_score_entities,
    get_registry_snapshot,
    load_registry_overrides,
    recommend_threshold_adjustments,
    register_brand_lineage_overrides,
    register_credential_overrides,
    register_multi_root_diminutive_overrides,
    register_nickname_overrides,
    register_surname_particles,
    reset_custom_registries,
    resolve_brand_lineage,
    standardize_address,
    standardize_person,
)
from entity_standardizer.address.models import (
    canonicalize_intl_city,
    canonicalize_intl_postal_code,
    canonicalize_intl_street_for_postal_key,
)


def test_person_luke_lucius_and_prefix_shortening() -> None:
    try:
        res_luke = compare_persons("Luke Bennett", "Lucius Bennett")
        assert res_luke.is_match is True
        assert res_luke.match_type in ("ROOT_NAME_MATCH", "MULTI_ROOT_DIMINUTIVE_MATCH")

        res_lucas = compare_persons("Luke Bennett", "Lucas Bennett")
        assert res_lucas.is_match is True

        # Safe >=4-char prefix shortening on given, middle, and goes-by-middle names
        res_pref_given = compare_persons("Trap Bennett", "Trapnell Bennett")
        assert res_pref_given.is_match is True
        assert res_pref_given.match_type == "GIVEN_PREFIX_SHORTENING_MATCH"

        res_pref_mid = compare_persons("G. Trap Bennett", "George Trapnell Bennett")
        assert res_pref_mid.is_match is True
        assert res_pref_mid.match_type == "GIVEN_PREFIX_SHORTENING_MATCH"

        res_goes_by_mid = compare_persons("Trap Bennett", "George Trapnell Bennett")
        assert res_goes_by_mid.is_match is True
        assert res_goes_by_mid.match_type == "GIVEN_PREFIX_SHORTENING_MATCH"

        res_goes_by_mid_rev = compare_persons("George Trapnell Bennett", "Trap Bennett")
        assert res_goes_by_mid_rev.is_match is True

        # Reject gender-distinct suffix pairs and unrelated names sharing surname
        assert compare_persons("Paul Bennett", "Paula Bennett").is_match is False
        assert compare_persons("Brian Carver", "Lucas Carver").is_match is False
        assert compare_persons("Ann Bennett", "Anna Bennett").is_match is False
    finally:
        reset_custom_registries()


def test_external_json_registries_and_runtime_overrides(tmp_path: Path) -> None:
    try:
        snap = get_registry_snapshot()
        assert snap["nickname_to_root"]["LUKE"] == "LUCIUS"
        assert "OSAIC" in {fam for _, fam in snap["brand_lineage_prefixes"]}
        assert "CFP" in snap["credentials"]
        assert "VON" in snap["surname_particles"]

        # Runtime overrides propagate live into company & person standardization
        register_brand_lineage_overrides([("SILVERPINE WEALTH", "SILVERPINE"), (" ", "EMPTY")])
        register_brand_lineage_overrides({"  ": ""})
        assert resolve_brand_lineage("Silverpine Wealth Advisory LLC") == "SILVERPINE"

        register_nickname_overrides({"BRAM": "ABRAHAM", " ": "NOOP"})
        assert compare_persons("Bram Mercer", "Abraham Mercer").is_match is True

        register_multi_root_diminutive_overrides({"MAXI": ("MAXWELL", "MAXIMILIAN"), " ": []})
        assert compare_persons("Maxi Sterling", "Maximilian Sterling").is_match is True

        register_credential_overrides({"WMBA": "WMBA", "": "NOOP"})
        assert "WMBA" in standardize_person("Taylor Vance, WMBA").credentials

        register_surname_particles(["VANDEN", " "])
        assert "VANDEN" in get_registry_snapshot()["surname_particles"]

        override_file = tmp_path / "custom_reg.json"
        override_file.write_text(
            json.dumps(
                {
                    "brand_lineage_prefixes": {"CRESTLINE": "CRESTLINE"},
                    "nickname_to_root": {"ALFIE": "ALFRED"},
                    "multi_root_diminutives": {"SANDY2": ["SANDRA", "ALEXANDER"]},
                    "credentials": {"CFPA2": "CFPA2"},
                    "surname_particles": ["VANDER2"],
                }
            ),
            encoding="utf-8",
        )
        load_registry_overrides(override_file)
        assert resolve_brand_lineage("Crestline Partners Inc") == "CRESTLINE"
        assert standardize_person("Alfie Stone").root_first_name == "ALFRED"

        load_registry_overrides({"nickname_to_root": {"GUSSIE": "AUGUSTUS"}})
        assert standardize_person("Gussie Stone").root_first_name == "AUGUSTUS"
        load_registry_overrides({"brand_lineage_prefixes": [["NORTHLINE", "NORTHLINE"]]})
        assert resolve_brand_lineage("Northline Capital") == "NORTHLINE"
    finally:
        reset_custom_registries()

    # Reset restores defaults and strips runtime overrides
    assert resolve_brand_lineage("Silverpine Wealth Advisory LLC") is None


def test_international_postal_and_building_keys() -> None:
    # Canada: postal space folding + Toronto borough canonicalization + glued unit stripping
    ca_a = standardize_address("100 King St W Suite 200", city="North York", state="ON", postal_code="M5J 2N8", country="CAN")
    ca_b = standardize_address("100 King St W Ste 400", city="Toronto", state="ON", postal_code="M5J2N8", country="Canada")
    assert ca_a.postal_city == "TORONTO"
    assert ca_a.postal_building_key == ca_b.postal_building_key
    assert ca_a.postal_address_key != ca_b.postal_address_key

    # Canada Montreal bilingual prefix + borough
    ca_mtl = standardize_address("1000 Rue Saint-Jacques", city="Saint-Laurent", state="QC", postal_code="H4R 1E1", country="CA")
    assert ca_mtl.postal_city == "MONTREAL"

    # UK: City of London -> LONDON & space-folded postcode
    uk_a = standardize_address("25 Bishopsgate Floor 4", city="City of London", state="", postal_code="EC2N 4AY", country="GBR")
    uk_b = standardize_address("25 Bishopsgate Floor 8", city="London", state="", postal_code="EC2N4AY", country="UK")
    assert uk_a.postal_city == "LONDON"
    assert uk_a.postal_building_key == uk_b.postal_building_key

    # Switzerland, Germany (fused STRASSE), France (La Defense -> PARIS)
    ch = standardize_address("Bahnhofstrasse 10", city="Zuerich", state="ZH", postal_code="8001", country="CHE")
    assert ch.postal_city == "ZURICH"
    de = standardize_address("Friedrichstrasse 10", city="Frankfurt am Main", state="", postal_code="60311", country="DEU")
    assert de.postal_city == "FRANKFURT"
    assert de.postal_address_key is not None and "FRIEDRICH STR" in de.postal_address_key
    fr = standardize_address("12 Avenue Montaigne", city="La Defense", state="", postal_code="75008", country="FRA")
    assert fr.postal_city == "PARIS"

    # Helper edge cases + unsupported non-US country + empty city + parse_failed
    assert canonicalize_intl_postal_code("m5j 2n8", "CAN") == "M5J2N8"
    assert canonicalize_intl_city("North York", "CA") == "TORONTO"
    assert canonicalize_intl_street_for_postal_key("", "CAN") == ""
    assert canonicalize_intl_street_for_postal_key("10 Friedrichstrasse", "DEU") == "10 FRIEDRICH STR"

    jp = StandardizedAddress(
        street1="1-1 Chiyoda",
        street2="",
        city="Tokyo",
        state="",
        postal_code="100-0001",
        country="JPN",
        normalized_address_key="1-1 CHIYODA||TOKYO||100-0001|JPN",
        address_status="standardized",
        raw_street_address="1-1 Chiyoda",
        is_us=False,
    )
    assert jp.postal_city is None
    assert jp.postal_address_key is None

    can_empty_city = StandardizedAddress(
        street1="",
        street2="",
        city="",
        state="ON",
        postal_code="M5J 2N8",
        country="CAN",
        normalized_address_key="|||ON|M5J 2N8|CAN",
        address_status="standardized",
        raw_street_address="",
        is_us=False,
    )
    assert can_empty_city.postal_city is None
    assert can_empty_city.postal_building_key == "|||ON|M5J2N8|CAN"

    can_prefilled = StandardizedAddress(
        street1="100 King St",
        street2="",
        city="Toronto",
        state="ON",
        postal_code="M5J2N8",
        country="CAN",
        normalized_address_key="100 KING ST||TORONTO|ON|M5J2N8|CAN",
        address_status="standardized",
        raw_street_address="100 King St",
        is_us=False,
        postal_city="TORONTO",
        postal_address_key="CUSTOM_ADDR",
        postal_building_key="CUSTOM_BLDG",
    )
    assert can_prefilled.postal_address_key == "CUSTOM_ADDR"


def test_switchboard_guard_and_conflicting_first_name_scoring() -> None:
    colleagues = [
        {"id": f"c{i}", "office_key": "OFF_1", "phone_e164": "+12125550100"} for i in range(4)
    ] + [
        {"id": "c_blank_ph", "office_key": "OFF_1", "phone_e164": ""},
        {"id": "c_blank_grp", "office_key": "", "phone_e164": "+12125550999"},
        {"id": "c_direct_1", "office_key": "OFF_2", "phone_e164": "+12125550200"},
    ]
    sw_grouped = compute_switchboard_phones(colleagues, group_field="office_key", entity_id_field="id", min_shared_count=4)
    assert "+12125550100" in sw_grouped
    assert "+12125550200" not in sw_grouped

    sw_global = compute_switchboard_phones(colleagues, min_shared_count=4)
    assert "+12125550100" in sw_global

    # Two coworkers sharing address, firm, surname, AND a local branch switchboard phone must NOT false-positive
    coworker_res = explain_and_score_entities(
        {
            "person_name": "Brian Carver",
            "organization": "Oakridge Wealth Partners LLC",
            "street1": "200 Market St",
            "city": "Philadelphia",
            "state": "PA",
            "postal_code": "19103",
            "country": "US",
            "phone": "212-555-0100",
        },
        {
            "person_name": "Lucas Carver",
            "organization": "Oakridge Wealth Partners LLC",
            "street1": "200 Market St",
            "city": "Philadelphia",
            "state": "PA",
            "postal_code": "19103",
            "country": "US",
            "phone": "212-555-0100",
        },
        switchboard_phones=sw_grouped,
    )
    assert coworker_res.is_match is False
    assert coworker_res.is_potential_match is False
    assert coworker_res.disposition == MatchDisposition.NO_MATCH.value
    assert "SHARED_BRANCH_SWITCHBOARD" in coworker_res.matched_signals

    # Initial vs mismatching full first name still exercises the smaller 0.12 conflict path cleanly
    init_conflict = explain_and_score_entities(
        {"person_name": "J Carver", "organization": "Oakridge Wealth Partners LLC"},
        {"person_name": "Robert Carver", "organization": "Oakridge Wealth Partners LLC"},
    )
    assert init_conflict.is_match is False


class _PyListTable:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def to_pylist(self) -> list[dict[str, Any]]:
        return self._rows


class _PolarsLikeTable:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def to_dicts(self) -> list[dict[str, Any]]:
        return self._rows


def test_cross_system_matcher_blocking_cardinality_and_set_rules() -> None:
    left = _PyListTable(
        [
            {
                "id": "L1",
                "crd": "1001",
                "firm_key": "F1",
                "email": "alice.vance@northbridge.example",
                "person_name": "Alice Vance",
                "organization": "Northbridge Partners",
                "street1": "100 Main St",
                "city": "Boston",
                "state": "MA",
                "postal_code": "02110",
                "country": "US",
                "phone": "617-555-0101",
                "phone_e164": "+16175550101",
            },
            {
                "id": "L2",
                "crd": "",
                "firm_key": "F1",
                "email": "bob@northbridge.example",
                "person_name": "Bob Mercer",
                "organization": "Northbridge Partners",
                "street1": "100 Main St",
                "city": "Boston",
                "state": "MA",
                "postal_code": "02110",
                "country": "US",
                "phone": "617-555-0101",
                "phone_e164": "+16175550101",
            },
            {
                "id": "L2B",
                "crd": "",
                "firm_key": "F1",
                "email": "bob@northbridge.example",
                "person_name": "Robert Mercer",
                "organization": "Northbridge Partners",
                "street1": "100 Main St",
                "city": "Boston",
                "state": "MA",
                "postal_code": "02110",
                "country": "US",
                "phone": "617-555-0101",
                "phone_e164": "+16175550101",
            },
            {
                "id": "L3",
                "crd": "",
                "firm_key": "F2",
                "email": "",
                "person_name": "Claire Dalton",
                "organization": "Harbor Wealth",
                "street1": "500 Oak Ave",
                "city": "Chicago",
                "state": "IL",
                "postal_code": "60601",
                "country": "US",
                "phone": "312-555-0199",
                "phone_e164": "+13125550199",
            },
            {
                "id": "L4",
                "crd": "",
                "firm_key": "F2",
                "email": "",
                "person_name": "Dan Foster",
                "organization": "Harbor Wealth",
                "street1": "500 Oak Ave",
                "city": "Chicago",
                "state": "IL",
                "postal_code": "60601",
                "country": "US",
                "phone": "312-555-0199",
                "phone_e164": "+13125550199",
            },
            {"id": "L_UNMATCHED", "crd": "9999", "firm_key": "F9", "person_name": "Zero Hit"},
        ]
    )
    right = _PolarsLikeTable(
        [
            {
                "id": "R1",
                "crd": "1001",
                "firm_key": "F1",
                "email": "alice.vance@northbridge.example",
                "person_name": "Alice Vance",
                "organization": "Northbridge Partners",
                "street1": "100 Main St",
                "city": "Boston",
                "state": "MA",
                "postal_code": "02110",
                "country": "US",
                "phone": "617-555-0101",
                "phone_e164": "+16175550101",
            },
            {
                "id": "R2",
                "crd": "",
                "firm_key": "F1",
                "email": "bob@northbridge.example",
                "person_name": "Robert Mercer",
                "organization": "Northbridge Partners",
                "street1": "100 Main St",
                "city": "Boston",
                "state": "MA",
                "postal_code": "02110",
                "country": "US",
                "phone": "617-555-0101",
                "phone_e164": "+16175550101",
            },
            {
                "id": "R3",
                "crd": "",
                "firm_key": "F2",
                "email": "",
                "person_name": "C. Dalton",
                "organization": "Harbor Wealth",
                "street1": "500 Oak Ave",
                "city": "Chicago",
                "state": "IL",
                "postal_code": "60601",
                "country": "US",
                "phone": "312-555-0199",
                "phone_e164": "+13125550199",
            },
            {
                "id": "R3_ALT",
                "crd": "",
                "firm_key": "F2",
                "email": "",
                "person_name": "Claire Dalton",
                "organization": "Harbor Wealth",
                "street1": "500 Oak Ave",
                "city": "Chicago",
                "state": "IL",
                "postal_code": "60601",
                "country": "US",
                "phone": "312-555-0199",
                "phone_e164": "+13125550199",
            },
        ]
    )

    matcher = CrossSystemMatcher(left, right)
    rules = [
        BlockingRule(
            name="EXACT_CRD",
            key_fn=lambda r: [r["crd"]] if r.get("crd") else (),
            mode="exact_all",
            evidence_fn=lambda a, b: [SignalEvidence("FINRA_CRD", 0.96, f"CRD {a['crd']}")],
        ),
        BlockingRule(
            name="EXACT_EMAIL",
            key_fn=lambda r: r.get("email") or None,
            mode="either_unmatched",
            pair_filter=lambda a, b: a.get("firm_key") == b.get("firm_key"),
        ),
        BlockingRule(
            name="FIRM_CANDIDATES",
            key_fn=lambda r: r.get("firm_key"),
            mode="greedy_scored",
        ),
    ]
    matched, potential, summary = matcher.match(rules)
    assert summary.matched_pairs >= 4
    assert summary.cardinality_counts["N:1"] + summary.cardinality_counts["1:N"] >= 1
    assert summary.to_dict()["matched_pairs"] == len(matched)
    assert matched[0].to_dict()["left_id"] == "L1"
    # R3 was a lower-scored duplicate contender for L3 -> routed into potential after R3_ALT won L3 greedily; Dan vs C. below threshold dropped
    assert any(p.right_id == "R3" for p in potential)

    # Roster set_jaccard mode with primary + high-containment secondary split vs loose sibling -> potential
    # Plus M:N + N:1 + fallback rule scoring & both_unmatched mode coverage
    par_left = [
        {"id": "PL1", "firm": "F1", "members": ["10", "20", "30", "40"], "tag": "X"},
        {"id": "PL2", "firm": "F1", "members": ["10", "20", "30"], "tag": "Y"},
        {"id": "PL_EMPTY", "firm": "F1", "members": [], "tag": "Z"},
    ]
    par_right = [
        {"id": "PR1", "firm": "F1", "members": ["10", "20", "30", "40"], "tag": "X"},
        {"id": "PR2", "firm": "F1", "members": ["10", "20", "50", "60", "70", "80"], "tag": "X"},
    ]
    par_matcher = CrossSystemMatcher(par_left, par_right)
    par_matched, par_pot, par_sum = par_matcher.match(
        [
            BlockingRule(
                name="PARTNERSHIP_ROSTER",
                key_fn=lambda r: r.get("firm"),
                mode="set_jaccard",
                min_jaccard=0.20,
                min_containment=0.75,
                max_primary_links=1,
            ),
            BlockingRule(
                name="TAG_FALLBACK",
                key_fn=lambda r: r.get("tag"),
                mode="both_unmatched",
            ),
        ]
    )
    # PL1-PR1 matches primary (1.0), PL2-PR1 (containment 3/3=1.0 >= 0.75) promotes secondary, while PL1-PR2 (Jaccard 0.25, containment 0.50 < 0.75) goes to potential
    assert any(m.left_id == "PL1" and m.right_id == "PR1" for m in par_matched)
    assert any(m.left_id == "PL2" and m.right_id == "PR1" for m in par_matched)
    assert any(p.left_id == "PL1" and p.right_id == "PR2" for p in par_pot)
    assert par_sum.cardinality_counts["N:1"] + par_sum.cardinality_counts["1:N"] >= 1

    # Exercise 1:N, M:N cardinality, pair_filter rejection, below-threshold drops & set_jaccard low-overlap skip
    mn_matcher = CrossSystemMatcher(
        [
            {"id": "A1", "k": "K1", "k3": "K3", "g": "G1", "person_name": "Alice Doe", "organization": "Northbridge LLC"},
            {"id": "A2", "k": "K1", "k3": "", "g": "G2", "person_name": "Brian Carver", "organization": "Northbridge LLC"},
            {"id": "A3", "k": "K2", "k3": "", "g": "G1", "person_name": "Claire Dalton", "city": "Boston", "state": "MA", "country": "US"},
            {"id": "A_ONE", "k": "ONE_N", "k3": "", "se": "SE", "g": "G1", "members": ["1"]},
            {"id": "A_LOWJ", "k": "LOWJ", "k3": "", "g": "G1", "members": ["1", "2", "3", "4", "5"]},
            {"id": "A_GREEDY", "k": "GREEDY_LOW", "k3": "", "g": "G1", "person_name": "Paul Bennett", "organization": "Oak LLC"},
            {"id": "A_MN1", "k": "MN", "k3": "", "g": "G1"},
            {"id": "A_MN2", "k": "MN", "k3": "", "g": "G1"},
        ],
        [
            {"id": "B1", "k": "K1", "k3": "", "se": "SE", "g": "G1", "person_name": "Alice Doe", "organization": "Northbridge LLC"},
            {"id": "B2", "k": "K1", "k3": "K3", "g": "G1", "person_name": "Lucas Carver", "organization": "Beta Wealth"},
            {"id": "B3", "k": "K2", "k3": "K3", "g": "G1", "person_name": "Robert Stone", "city": "Boston", "state": "MA", "country": "US"},
            {"id": "B_ONE1", "k": "ONE_N", "k3": "", "g": "G1", "members": ["1"]},
            {"id": "B_ONE2", "k": "ONE_N", "k3": "", "g": "G1", "members": ["1"]},
            {"id": "B_LOWJ", "k": "LOWJ", "k3": "", "g": "G1", "members": ["6", "7", "8", "9", "10"]},
            {"id": "B_GREEDY", "k": "GREEDY_LOW", "k3": "", "g": "G1", "person_name": "Paula Bennett", "organization": "Oak LLC"},
            {"id": "B_MN1", "k": "MN", "k3": "", "g": "G1"},
            {"id": "B_MN2", "k": "MN", "k3": "", "g": "G1"},
        ],
    )
    mn_matched, mn_pot, mn_sum = mn_matcher.match(
        [
            BlockingRule(
                name="K1_MULTI",
                key_fn=lambda r: "K1" if r["k"] == "K1" else None,
                mode="exact_all",
                pair_filter=lambda a, b: a.get("g") == b.get("g"),
            ),
            BlockingRule(name="ONE_TO_MANY", key_fn=lambda r: "ONE_N" if r["k"] == "ONE_N" else None, mode="exact_all"),
            BlockingRule(name="MN_MULTI", key_fn=lambda r: "MN" if r["k"] == "MN" else None, mode="exact_all"),
            BlockingRule(name="FILTER_EITHER_SKIP", key_fn=lambda r: r.get("se"), mode="either_unmatched"),
            BlockingRule(name="BOTH_UNMATCHED_SKIP", key_fn=lambda r: r.get("k3") or None, mode="both_unmatched"),
            BlockingRule(name="LOW_SCORE_NO_MATCH", key_fn=lambda r: "K2" if r["k"] == "K2" else None, mode="both_unmatched"),
            BlockingRule(
                name="LOW_JACCARD_SKIP",
                key_fn=lambda r: "LOWJ" if r["k"] == "LOWJ" else None,
                mode="set_jaccard",
                min_jaccard=0.50,
                min_containment=0.75,
            ),
            BlockingRule(name="GREEDY_LOW_DROP", key_fn=lambda r: "GREEDY_LOW" if r["k"] == "GREEDY_LOW" else None, mode="greedy_scored"),
            BlockingRule(
                name="K2_POTENTIAL",
                key_fn=lambda r: "K2" if r["k"] == "K2" else None,
                mode="both_unmatched",
                evidence_fn=lambda a, b: [SignalEvidence("WEAK_HINT", 0.55, "weak hint")],
            ),
        ]
    )
    assert mn_sum.cardinality_counts["M:N"] == 4
    assert mn_sum.cardinality_counts["1:N"] == 4
    assert len(mn_pot) >= 1 and mn_pot[0].disposition == MatchDisposition.POTENTIAL_MATCH.value
    assert any(m.matched_signals == ("MN_MULTI",) for m in mn_matched)


def test_precision_recall_calibration_harness() -> None:
    pairs = [
        LabeledEntityPair(
            left={"person_name": "Luke Bennett", "organization": "Northbridge LLC", "email": "lbennett@nb.example"},
            right={"person_name": "Lucius Bennett", "organization": "Northbridge LLC", "email": "lbennett@nb.example"},
            crd_left="111222",
            crd_right="111222",
            expected_match=True,
            label_reason="CRD + Luke/Lucius",
        ),
        LabeledEntityPair(
            left={"person_name": "Trap Bennett", "organization": "Northbridge LLC", "email": "tbennett@nb.example"},
            right={"person_name": "Trapnell Bennett", "organization": "Northbridge LLC", "email": "tbennett@nb.example"},
            expected_match=True,
            label_reason="4-char prefix + corporate email",
        ),
        LabeledEntityPair(
            left={"person_name": "Sarah Miller", "organization": "Northbridge LLC"},
            right={"person_name": "Claire Miller", "organization": "Northbridge LLC", "street1": "100 Main St"},
            expected_match=True,
            label_reason="Deliberate hard FN test case without shared identifiers",
        ),
        LabeledEntityPair(
            left={
                "person_name": "Brian Carver",
                "organization": "Oakridge Wealth LLC",
                "street1": "200 Market St",
                "city": "Philadelphia",
                "state": "PA",
                "postal_code": "19103",
                "country": "US",
                "phone": "212-555-0100",
            },
            right={
                "person_name": "Lucas Carver",
                "organization": "Oakridge Wealth LLC",
                "street1": "200 Market St",
                "city": "Philadelphia",
                "state": "PA",
                "postal_code": "19103",
                "country": "US",
                "phone": "212-555-0100",
            },
            expected_match=False,
            label_reason="Same surname + office switchboard trap",
        ),
        LabeledEntityPair(
            left={"organization": "Alpha Custody", "phone": "212-555-0188"},
            right={"organization": "Beta Custody", "phone": "212-555-0188"},
            expected_match=False,
            label_reason="Deliberate weak negative",
        ),
    ]

    report = evaluate_scoring_calibration(pairs, switchboard_phones={"+12125550100"})
    assert report.total_pairs == 5
    assert report.true_positives == 2
    assert report.false_negatives == 1
    assert report.true_negatives == 2
    assert report.false_positives == 0
    assert report.precision == 1.0
    assert report.false_positive_rate == 0.0
    assert report.to_dict()["signal_stats"]["FINRA_CRD"]["tp"] == 1

    # Also exercise FP signal_stats, potential_flags, empty denominator, and threshold sweep
    fp_report = evaluate_scoring_calibration(
        [
            LabeledEntityPair(
                left={"person_name": "Alice Doe", "organization": "Firm A LLC", "email": "alice@firma.example"},
                right={"person_name": "Alice Doe", "organization": "Firm A LLC", "email": "alice@firma.example"},
                expected_match=False,
            ),
            LabeledEntityPair(
                left={"organization": "Firm B LLC", "phone": "609-555-0199", "email": "dana@firmb.example"},
                right={"organization": "Firm C LLC", "phone": "609-555-0199", "email": "dana@firmb.example"},
                expected_match=False,
            ),
        ]
    )
    assert fp_report.false_positives == 1
    assert fp_report.potential_flags == 1
    assert fp_report.signal_stats["EMAIL"]["fp"] == 1

    empty_rep = evaluate_scoring_calibration([])
    assert empty_rep.precision == 0.0
    assert empty_rep.false_positive_rate == 0.0
    assert recommend_threshold_adjustments([(0.80, True), (0.60, False)]) == (0.65, 0.45, 1.0)
