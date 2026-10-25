"""Tests for Phase 4: Telephony Fuzzy Deduplication, Keypad/Transposition Distance & Contact Entity Resolution."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from entity_standardizer import (
    are_keypad_adjacent,
    cluster_contact_records,
    compare_phones,
    damerau_levenshtein_distance,
    deduplicate_phones,
    generate_phone_blocking_keys,
    infer_country_from_postal_code,
    standardize_phone,
)
from entity_standardizer.cli import main as cli_main
from entity_standardizer.dedup import _detect_single_substitution, _detect_single_transposition
from entity_standardizer.mcp import handle_mcp_request
from entity_standardizer.server import app


def test_postal_code_country_inference() -> None:
    assert infer_country_from_postal_code(None) is None
    assert infer_country_from_postal_code("   ") is None
    assert infer_country_from_postal_code("M5V 2T6") == "CA"
    assert infer_country_from_postal_code("SW1A 1AA") == "GB"
    assert infer_country_from_postal_code("W1F 8") == "GB"
    assert infer_country_from_postal_code("EC1A") == "GB"
    assert infer_country_from_postal_code("JE2 3RP") == "JE"
    assert infer_country_from_postal_code("GY1 1AA") == "GG"
    assert infer_country_from_postal_code("IM1 2PQ") == "IM"
    assert infer_country_from_postal_code("KY1-1102") == "KY"
    assert infer_country_from_postal_code("HM 08") == "BM"
    assert infer_country_from_postal_code("100-0001") == "JP"
    assert infer_country_from_postal_code("01310-100") == "BR"
    assert infer_country_from_postal_code("1012 AB") == "NL"
    assert infer_country_from_postal_code("D02 AF30") == "IE"
    assert infer_country_from_postal_code("00-950") == "PL"
    assert infer_country_from_postal_code("94105-1234") == "US"
    assert infer_country_from_postal_code("UNKNOWN-FORMAT") is None


def test_keypad_adjacency_and_damerau_levenshtein() -> None:
    assert are_keypad_adjacent("5", "2") is True
    assert are_keypad_adjacent("5", "4") is True
    assert are_keypad_adjacent("5", "6") is True
    assert are_keypad_adjacent("5", "8") is True
    assert are_keypad_adjacent("1", "9") is False
    assert are_keypad_adjacent("0", "8") is True
    assert are_keypad_adjacent("X", "1") is False

    assert damerau_levenshtein_distance("4155552671", "4155552671") == 0
    assert damerau_levenshtein_distance("", "123") == 3
    assert damerau_levenshtein_distance("123", "") == 3
    assert damerau_levenshtein_distance("4155552671", "4155552617") == 1  # transposition
    assert damerau_levenshtein_distance("4155552671", "4155552672") == 1  # substitution
    assert damerau_levenshtein_distance("4155552671", "9998887777") >= 7

    assert _detect_single_transposition("123", "12") is False
    assert _detect_single_transposition("123", "123") is False
    assert _detect_single_substitution("123", "12") == (False, False)
    assert _detect_single_substitution("123", "999") == (False, False)


def test_compare_phones_all_match_categories() -> None:
    # 1. Invalid / empty phone
    inv = compare_phones("", "+14155552671")
    assert inv.is_fuzzy_match is False
    assert inv.similarity_score == 0.0
    assert inv.match_type == "DISTINCT"
    assert inv.to_dict()["match_type"] == "DISTINCT"

    # 2. Exact canonical E.164 match (accepting pre-parsed StandardizedPhone too)
    pa = standardize_phone("(415) 555-2671")
    pb = standardize_phone("+1-415-555-2671")
    exact = compare_phones(pa, pb)
    assert exact.is_exact_match is True
    assert exact.is_fuzzy_match is True
    assert exact.similarity_score == 1.0
    assert exact.match_type == "EXACT_MATCH"

    # 3. Same main E.164 with different extension
    ext_var = compare_phones("+1 (415) 555-2671 ext. 101", "+1 (415) 555-2671 ext. 102")
    assert ext_var.is_exact_match is False
    assert ext_var.is_extension_variant is True
    assert ext_var.is_fuzzy_match is True
    assert ext_var.similarity_score == 0.96
    assert ext_var.match_type == "EXTENSION_VARIANT"

    # Also test main line without extension vs with extension
    ext_none = compare_phones("+1 (415) 555-2671", "+1 (415) 555-2671 ext. 102")
    assert ext_none.is_extension_variant is True

    # 4. Identical NSN across different country contexts
    p_us = standardize_phone("4155552671", country="US")
    p_other = standardize_phone("4155552671", country="FR")
    nat_eq = compare_phones(p_us, p_other)
    assert nat_eq.match_type == "NATIONAL_EQUIVALENT"
    assert nat_eq.similarity_score == 0.94
    assert nat_eq.is_fuzzy_match is True

    # 5. Single adjacent transposition (+14155552671 vs +14155552617)
    trans = compare_phones("+1 415-555-2671", "+1 415-555-2617")
    assert trans.match_type == "ADJACENT_TRANSPOSITION"
    assert trans.transposition_detected is True
    assert trans.is_fuzzy_match is True
    assert trans.similarity_score == 0.92

    # 6. Keypad-adjacent single digit substitution (7 -> 8 on last digit: 2678 vs 2670)
    keypad_sub = compare_phones("+1 415-555-2678", "+1 415-555-2670")
    assert keypad_sub.match_type == "KEYPAD_ADJACENT_TYPO"
    assert keypad_sub.keypad_adjacent_typo is True
    assert keypad_sub.similarity_score == 0.91
    assert keypad_sub.is_fuzzy_match is True

    # 7. Non-adjacent single digit substitution (1 -> 9 on last digit)
    single_sub = compare_phones("+1 415-555-2671", "+1 415-555-2679")
    assert single_sub.match_type == "SINGLE_DIGIT_EDIT"
    assert single_sub.keypad_adjacent_typo is False
    assert single_sub.similarity_score == 0.89
    assert single_sub.is_fuzzy_match is True

    # 8. Distinct numbers (multiple edits or different length)
    distinct = compare_phones("+1 415-555-2671", "+1 415-555-9999")
    assert distinct.match_type == "DISTINCT"
    assert distinct.is_fuzzy_match is False
    assert distinct.similarity_score <= 0.84

    diff_len = compare_phones("+1 415-555-2671", "+44 20 7946 0912")
    assert diff_len.match_type == "DISTINCT"
    assert diff_len.is_fuzzy_match is False

    # 9. Phase 6: Corporate switchboard / sequential block ending in 00/000 guard
    corp_sw = compare_phones("800-526-6300", "800-526-6500")
    assert corp_sw.similarity_score == 0.85
    assert corp_sw.is_fuzzy_match is False
    assert compare_phones("800-526-6300", "800-526-6500", fuzzy_threshold=0.85).is_fuzzy_match is True

    # 10. Phase 6: Single-digit insertion/deletion (different length, dist == 1)
    len_edit = compare_phones("+49 30 1234567", "+49 30 12345678")
    assert len_edit.edit_distance == 1
    assert len_edit.match_type == "SINGLE_DIGIT_EDIT"


def test_blocking_keys_and_deduplicate_phones() -> None:
    assert generate_phone_blocking_keys("") == ()
    short_phone = standardize_phone("911")
    short_keys = generate_phone_blocking_keys(short_phone)
    assert "e164:911" in short_keys

    keys = generate_phone_blocking_keys("+1 (415) 555-2671")
    assert "e164:+14155552671" in keys
    assert "nsn:4155552671" in keys
    assert "tail7:5552671" in keys

    assert deduplicate_phones([]) == []

    # Cluster with exact, duplicate identical raw string, extension variant, transposition, and a distinct UK number
    raw_phones = [
        "(415) 555-2671",
        "(415) 555-2671",  # identical raw string hit in local str_cache
        "+1 415-555-2671",  # exact duplicate pre-grouped in O(N)
        "+1-415-555-2671 ext 104",
        "+1 415 555 2617",  # transposition of 71 -> 17
        "+1 415 555 2678",  # single edit (0.89 >= 0.88)
        "+44 (0) 20 7946 0912",
    ]
    clusters = deduplicate_phones(raw_phones)
    assert len(clusters) == 2
    c0 = clusters[0]
    assert len(c0.members) == 6
    assert c0.golden_phone.e164 == "+14155552671"
    assert c0.golden_phone.extension == "104"
    assert "EXACT_MATCH" in c0.match_types
    assert c0.to_dict()["cluster_id"] == "PHONE-CLUSTER-0001"

    # Pre-grouping of empty/invalid phones in deduplicate_phones
    inv_clusters = deduplicate_phones(["", "904-218", "904-218"])
    assert len(inv_clusters) == 2

    # Test union when rj < ri (reverse merge order across buckets)
    # Record 0 and Record 2 share head6, Record 1 and Record 2 share tail7
    reverse_phones = [
        "+1 415-555-1111",  # idx 0
        "+1 212-555-9999",  # idx 1
        "+1 212-555-9998",  # idx 2 (links with idx 1 first -> root 1)
        "+1 415-555-1112",  # idx 3 (links with idx 0 -> root 0)
    ]
    rev_clusters = deduplicate_phones(reverse_phones)
    assert len(rev_clusters) == 2


def test_cluster_contact_records_synergy() -> None:
    assert cluster_contact_records([]) == []

    records = [
        {
            "id": "crm-1",
            "name": "Alice Smith",
            "phone": "(415) 555-2671",
            "postal_code": "94105",
            "address_key": "US|CA|SAN_FRANCISCO|100_MAIN_ST",
        },
        {
            "id": "crm-1b",
            "name": "Alice Smith (Duplicate)",
            "phone": "+1-415-555-2671",  # exact E.164 match pre-grouped in O(N)
            "postal_code": "94105",
            "address_key": "US|CA|SAN_FRANCISCO|100_MAIN_ST",
        },
        {
            "id": "crm-2",
            "name": "A. Smith",
            "phone": "+1 415-555-2617",  # fat-finger transposition
            "postal_code": "94105-1234",
            "address_key": "US|CA|SAN_FRANCISCO|100_MAIN_ST",
        },
        {
            "id": "crm-3",
            "name": "Alice Smith (Reception)",
            "phone": "+1 415-555-9999",  # shares cc_head6 (1:415555) with crm-1, distinct phone, same address_key!
            "postal_code": "94105",
            "address_key": "US|CA|SAN_FRANCISCO|100_MAIN_ST",
        },
        {
            "id": "crm-4",
            "name": "Bob Tanaka",
            "phone": "03-1234-5678",
            "postal_code": "100-0001",  # Infers JP from postal code!
            "address_key": "JP|TOKYO|CHIYODA|1_1",
        },
    ]
    clusters = cluster_contact_records(records)
    assert len(clusters) == 2

    alice_cluster = clusters[0]
    assert alice_cluster.record_ids == ("crm-1", "crm-1b", "crm-2", "crm-3")
    assert alice_cluster.golden_address_key == "US|CA|SAN_FRANCISCO|100_MAIN_ST"
    assert "PHONE_EXACT_MATCH" in alice_cluster.linkage_reasons
    assert "PHONE_ADJACENT_TRANSPOSITION" in alice_cluster.linkage_reasons
    assert "SHARED_ADDRESS_KEY" in alice_cluster.linkage_reasons
    assert alice_cluster.to_dict()["cluster_id"] == "CONTACT-CLUSTER-0001"

    bob_cluster = clusters[1]
    assert bob_cluster.record_ids == ("crm-4",)
    assert bob_cluster.golden_phone.country_iso2 == "JP"
    assert bob_cluster.golden_phone.e164 == "+81312345678"

    # Test reverse root union (ri > rj) in deduplicate_phones and cluster_contact_records
    p0 = standardize_phone("4155552671", country="FR")
    p1 = standardize_phone("+1 415-555-2672")
    p2 = standardize_phone("+1 415-555-2671")
    dedup_ri_gt_rj = deduplicate_phones([p0, p1, p2])
    assert len(dedup_ri_gt_rj) == 1

    rec_ri_gt_rj = [
        {"id": "0", "phone": "4155552671", "country": "FR"},
        {"id": "1", "phone": "+1 415-555-2672", "country": "US"},
        {"id": "2", "phone": "+1 415-555-2671", "country": "US"},
        {"id": "3", "phone": "", "address_key": "US|NY|NYC|1_BROADWAY"},
    ]
    c_ri_gt_rj = cluster_contact_records(rec_ri_gt_rj)
    assert len(c_ri_gt_rj) == 2

    # Phase 5: Explicit international +CC on both inputs must NOT match as NATIONAL_EQUIVALENT
    intl_diff_cc = compare_phones("+1 415-555-2671", "+33 4155552671")
    assert intl_diff_cc.match_type == "DISTINCT"
    assert intl_diff_cc.is_fuzzy_match is False

    # Phase 5: Registered Agent hub and CMRA addresses must NOT link distinct phones via SHARED_ADDRESS_KEY
    class DummyHubAddr:
        is_registered_agent_hub = True
        is_cmra = False

    hub_records = [
        {
            "id": "corp-1",
            "phone": "+1 415-555-1234",
            "address_key": "US|DE|WILMINGTON|1209_ORANGE_ST",
            "is_registered_agent_hub": True,
        },
        {
            "id": "corp-2",
            "phone": "+1 415-555-5678",
            "address_key": "US|DE|WILMINGTON|1209_ORANGE_ST",
            "address_context": {"is_cmra": True},
        },
        {
            "id": "corp-3",
            "phone": "+1 415-555-9012",
            "address_key": "US|DE|WILMINGTON|1209_ORANGE_ST",
            "address_context": DummyHubAddr(),
        },
    ]
    hub_clusters = cluster_contact_records(hub_records)
    assert len(hub_clusters) == 3

    # Multi-pillar linkage via SHARED_EMAIL_KEY and SHARED_PERSON_AND_COMPANY_KEY
    multi_pillar_records = [
        {
            "id": "mp-1",
            "person_name": "Robert J. Smith",
            "organization": "BlackRock, Inc.",
            "email": "Robert.Smith+tag@gmail.com",
            "phone": "+1 212-555-0101",
        },
        {
            "id": "mp-2",
            "person_name": "R. Smith",
            "organization": "BLACKROCK INC /DE/",
            "email": "robertsmith@googlemail.com",
            "phone": "+1 415-555-0202",
        },
        {
            "id": "mp-3",
            "person_name": "Bob Smith",
            "organization": "BlackRock Incorporated",
            "email": "info@blackrock.com",  # role account ignored for email bucket
            "phone": "+44 20 7946 0912",
        },
        {
            "id": "mp-4",
            "person_name": "N/A",
            "organization": "...",
            "email": "bad-email",
            "phone": "+1 312-555-0303",
        },
    ]
    mp_clusters = cluster_contact_records(multi_pillar_records)
    assert len(mp_clusters) == 2
    assert mp_clusters[0].record_ids == ("mp-1", "mp-2", "mp-3")
    assert "SHARED_EMAIL_KEY" in mp_clusters[0].linkage_reasons
    assert "SHARED_PERSON_AND_COMPANY_KEY" in mp_clusters[0].linkage_reasons



def test_server_mcp_and_cli_phase4_endpoints(capsys) -> None:
    client = TestClient(app)

    # FastAPI /v1/compare
    r_cmp = client.post(
        "/v1/compare",
        json={"phone_a": "(415) 555-2671", "phone_b": "+1 415-555-2617"},
    )
    assert r_cmp.status_code == 200
    assert r_cmp.json()["match_type"] == "ADJACENT_TRANSPOSITION"

    # FastAPI /v1/deduplicate
    r_dedup = client.post(
        "/v1/deduplicate",
        json={"phones": ["(415) 555-2671", "+1 415-555-2671 ext 99", "+44 20 7946 0912"]},
    )
    assert r_dedup.status_code == 200
    assert r_dedup.json()["cluster_count"] == 2

    # MCP compare_phones
    mcp_cmp = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {
                "name": "compare_phones",
                "arguments": {"phone_a": "(415) 555-2671", "phone_b": "+1-415-555-2671"},
            },
        }
    )
    assert '"match_type": "EXACT_MATCH"' in mcp_cmp["result"]["content"][0]["text"]

    # MCP deduplicate_phones
    mcp_dedup = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "deduplicate_phones",
                "arguments": {"phones": ["(415) 555-2671", "+1-415-555-2671"]},
            },
        }
    )
    assert "PHONE-CLUSTER-0001" in mcp_dedup["result"]["content"][0]["text"]

    # CLI compare & dedup
    rc_cmp = cli_main(["compare", "(415) 555-2671", "+1 415-555-2617"])
    assert rc_cmp == 0
    out_cmp = json.loads(capsys.readouterr().out)
    assert out_cmp["transposition_detected"] is True

    rc_dedup = cli_main(["dedup", "(415) 555-2671", "+1 415-555-2671"])
    assert rc_dedup == 0
    out_dedup = json.loads(capsys.readouterr().out)
    assert len(out_dedup) == 1
