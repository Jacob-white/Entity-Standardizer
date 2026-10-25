"""Comprehensive tests for multi-pillar parity across Python, CLI, HTTP, MCP, Batch CSV, and Arrow/Polars."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pyarrow as pa
import polars as pl
import pytest
from fastapi.testclient import TestClient

from entity_standardizer import (
    AddressCluster,
    AddressComparisonResult,
    AutocompleteSuggestion,
    autocomplete_address,
    cluster_contact_records,
    compare_addresses,
    deduplicate_addresses,
    deduplicate_companies,
    deduplicate_persons,
    standardize_address,
    standardize_addresses_arrow,
    standardize_addresses_polars,
    standardize_arrow,
    standardize_companies_arrow,
    standardize_companies_polars,
    standardize_contact,
    standardize_contacts_arrow,
    standardize_contacts_polars,
    standardize_emails_arrow,
    standardize_emails_polars,
    standardize_persons_arrow,
    standardize_persons_polars,
    standardize_polars,
    standardize_urls_arrow,
    standardize_urls_polars,
    stream_standardize_csv,
)
from entity_standardizer.address.models import SpatialResolutionResult, StandardizedAddress
from entity_standardizer.cli import main as cli_main
from entity_standardizer.mcp.server import handle_mcp_request
from entity_standardizer.server import app


def test_address_models_properties_and_to_dict() -> None:
    addr = standardize_address(
        "100 Wall St Ste 400",
        city="New York",
        state="NY",
        postal_code="10005",
        enable_geocoding=True,
        explain=True,
    )
    assert addr.secondary_unit == "STE 400"
    assert addr.phonetic_address_key == addr.phonetic_key
    assert addr.house_number == "100"

    d = addr.to_dict()
    assert "explanation" in d
    assert "field_confidence" in d
    assert "spatial_result" in d
    assert d["latitude"] is not None
    assert d["longitude"] is not None

    # Test house_number when street1 has no leading digits
    po_addr = standardize_address("PO Box 500", city="Austin", state="TX", postal_code="78701")
    assert po_addr.house_number is None

    # Test to_dict with UNRESOLVED spatial_result and dict spatial_result
    unresolved_addr = StandardizedAddress(
        street1="999 UNKNOWN RD",
        street2="",
        city="NOWHERE",
        state="TX",
        postal_code="00000",
        country="USA",
        normalized_address_key=None,
        address_status="parse_failed",
        raw_street_address="999 UNKNOWN RD",
        is_us=True,
    )
    unresolved_addr.spatial_result = SpatialResolutionResult(
        latitude=0.0,
        longitude=0.0,
        precision="UNRESOLVED",
        accuracy_radius_meters=0.0,
        stage=0,
        source="NONE",
        h3_res10="",
    )
    ud = unresolved_addr.to_dict()
    assert ud["latitude"] is None
    assert ud["longitude"] is None
    assert ud["accuracy_radius_meters"] is None

    dict_spatial_addr = StandardizedAddress(
        street1="100 MAIN ST",
        street2="",
        city="AUSTIN",
        state="TX",
        postal_code="78701",
        country="USA",
        normalized_address_key="k1",
        address_status="standardized",
        raw_street_address="100 MAIN ST",
        is_us=True,
    )
    dict_spatial_addr.latitude = 30.2672
    dict_spatial_addr.longitude = -97.7431
    dict_spatial_addr.precision = "POSTAL_CENTROID"
    dict_spatial_addr.accuracy_radius_meters = 15.0
    dict_spatial_addr.spatial_result = {"custom": True}  # type: ignore[assignment]
    dsd = dict_spatial_addr.to_dict()
    assert dsd["spatial_result"] == {"custom": True}
    assert dsd["latitude"] == 30.2672


def test_autocomplete_address_prefix_and_to_dict() -> None:
    suggestions = autocomplete_address(
        prefix="100 WALL",
        city="NEW YORK",
        state="NY",
        postal_code="10005",
        max_results=3,
    )
    assert len(suggestions) >= 1
    assert isinstance(suggestions[0], AutocompleteSuggestion)
    sd = suggestions[0].to_dict()
    assert sd["street1"] == "100 WALL ST"
    assert sd["city"] == "NEW YORK"

    # Prefix without city/postal_code
    suggestions2 = autocomplete_address(prefix="100 WALL", max_results=2)
    assert len(suggestions2) >= 1

    # Empty prefix
    assert autocomplete_address(prefix="") == []


def test_compare_and_deduplicate_addresses_all_branches() -> None:
    # 1. Invalid input
    res_invalid = compare_addresses("", "100 Wall St, New York, NY 10005")
    assert isinstance(res_invalid, AddressComparisonResult)
    assert not res_invalid.is_match
    assert res_invalid.match_type == "INVALID_INPUT"
    assert res_invalid.to_dict()["match_type"] == "INVALID_INPUT"

    # 2. Exact normalized_address_key match (string and dict inputs)
    res_exact = compare_addresses(
        "100 Wall Street, New York, NY 10005",
        {"street1": "100 Wall St", "city": "New York", "state": "NY", "postal_code": "10005"},
    )
    assert res_exact.is_match
    assert res_exact.match_type == "EXACT_ADDRESS_KEY"
    assert res_exact.score == 1.0

    # 3. Same building_key, different secondary_unit
    res_diff_unit = compare_addresses(
        "100 Wall St Ste 400, New York, NY 10005",
        "100 Wall St Ste 800, New York, NY 10005",
    )
    assert not res_diff_unit.is_match
    assert res_diff_unit.match_type == "DIFFERENT_UNIT_SAME_BUILDING"
    assert res_diff_unit.score == 0.75

    # 4. Same building_key, one without secondary_unit
    res_bldg = compare_addresses(
        "100 Wall St Ste 400, New York, NY 10005",
        "100 Wall St, New York, NY 10005",
    )
    assert res_bldg.is_match
    assert res_bldg.match_type == "BUILDING_KEY_MATCH"
    assert res_bldg.score == 0.94

    # 5. Phonetic address key match with same house_number
    addr_p1 = StandardizedAddress(
        street1="100 SMYTHE AVE",
        street2="",
        city="AUSTIN",
        state="TX",
        postal_code="78701",
        country="USA",
        normalized_address_key="nak_1",
        address_status="standardized",
        raw_street_address="100 SMYTHE AVE",
        is_us=True,
        building_key="bk_1",
        phonetic_key="pk_same",
    )
    addr_p2 = StandardizedAddress(
        street1="100 SMITH AVE",
        street2="",
        city="AUSTIN",
        state="TX",
        postal_code="78701",
        country="USA",
        normalized_address_key="nak_2",
        address_status="standardized",
        raw_street_address="100 SMITH AVE",
        is_us=True,
        building_key="bk_2",
        phonetic_key="pk_same",
    )
    res_phonetic = compare_addresses(addr_p1, addr_p2)
    assert res_phonetic.is_match
    assert res_phonetic.match_type == "PHONETIC_ADDRESS_MATCH"
    assert res_phonetic.score == 0.90

    # 6. Fuzzy rooftop match with same house_number
    addr_f1 = StandardizedAddress(
        street1="100 WASHINGTON BLVD",
        street2="",
        city="AUSTIN",
        state="TX",
        postal_code="78701",
        country="USA",
        normalized_address_key="nak_f1",
        address_status="standardized",
        raw_street_address="100 WASHINGTON BLVD",
        is_us=True,
        building_key="bk_f1",
        phonetic_key="pk_f1",
    )
    addr_f2 = StandardizedAddress(
        street1="100 WASHINGTN BLVD",
        street2="",
        city="AUSTIN",
        state="TX",
        postal_code="78701",
        country="USA",
        normalized_address_key="nak_f2",
        address_status="standardized",
        raw_street_address="100 WASHINGTN BLVD",
        is_us=True,
        building_key="bk_f2",
        phonetic_key="pk_f2",
    )
    res_fuzzy = compare_addresses(addr_f1, addr_f2, fuzzy_threshold=0.85)
    assert res_fuzzy.is_match
    assert res_fuzzy.match_type == "FUZZY_ROOFTOP_MATCH"

    # 7. No match
    res_no = compare_addresses(
        "100 Wall St, New York, NY 10005",
        "500 N Michigan Ave, Chicago, IL 60611",
    )
    assert not res_no.is_match
    assert res_no.match_type == "NO_MATCH"

    # 8. deduplicate_addresses
    assert deduplicate_addresses([]) == []
    addr_no_keys = StandardizedAddress(
        street1="UNKNOWN PATH",
        street2="",
        city="",
        state="",
        postal_code="",
        country="USA",
        normalized_address_key=None,
        address_status="parse_failed",
        raw_street_address="UNKNOWN PATH",
        is_us=True,
        building_key=None,
        phonetic_key=None,
    )
    clusters = deduplicate_addresses(
        [
            "100 Wall St, New York, NY 10005",
            "100 Wall Street, New York, NY 10005",
            "200 Park Ave Ste 100, New York, NY 10166",
            "200 Park Ave Ste 200, New York, NY 10166",
            "500 N Michigan Ave, Chicago, IL 60611",
            "",
            addr_no_keys,
        ]
    )
    assert len(clusters) == 6
    assert isinstance(clusters[0], AddressCluster)
    cd = clusters[0].to_dict()
    assert cd["cluster_id"] == 1
    assert len(cd["members"]) == 2


def test_cluster_contact_records_with_raw_address_and_hub() -> None:
    records = [
        {
            "id": "r1",
            "phone": "",
            "street1": "100 Congress Ave",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
        },
        {
            "id": "r2",
            "phone": "",
            "address": "100 Congress Avenue",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
        },
        {
            "id": "r3",
            "phone": "",
            "street1": "1209 N Orange St",
            "city": "Wilmington",
            "state": "DE",
            "postal_code": "19801",
        },
        {
            "id": "r4",
            "phone": "",
            "street1": "1209 North Orange Street",
            "city": "Wilmington",
            "state": "DE",
            "postal_code": "19801",
        },
        {
            "id": "r5",
            "phone": "",
            "street1": "???",
        },
    ]
    clusters = cluster_contact_records(records)
    # r1 and r2 share a non-hub normalized_address_key -> clustered together
    # r3 and r4 are at 1209 N Orange St (Registered Agent hub) -> NOT clustered together
    cluster_map = {c.record_ids: c for c in clusters}
    assert ("r1", "r2") in cluster_map
    assert "SHARED_ADDRESS_KEY" in cluster_map[("r1", "r2")].linkage_reasons
    assert ("r3",) in cluster_map
    assert ("r4",) in cluster_map
    assert ("r5",) in cluster_map


def test_compound_person_splitting_in_standardize_contact() -> None:
    contact = standardize_contact(
        street1="100 Wall St",
        city="New York",
        state="NY",
        postal_code="10005",
        phone="212-555-0199",
        person_name="John & Jane Smith",
    )
    assert contact.person is not None
    assert contact.person.first_name == "JOHN"
    assert contact.person.last_name == "SMITH"
    assert len(contact.additional_persons) == 1
    assert contact.additional_persons[0].first_name == "JANE"
    assert contact.additional_persons[0].last_name == "SMITH"
    assert "COMPOUND_PERSON_SPLIT" in contact.cross_healing_actions
    cd = contact.to_dict()
    assert len(cd["additional_persons"]) == 1
    assert cd["additional_persons"][0]["first_name"] == "JANE"

    # Organization in person_name field still rescued when single item
    org_contact = standardize_contact(person_name="Acme Holdings LLC")
    assert org_contact.person is None
    assert org_contact.organization is not None
    assert "ORGANIZATION_RESCUED_FROM_PERSON_FIELD" in org_contact.cross_healing_actions

    # compare_contacts matches across additional_persons from compound person split
    from entity_standardizer import compare_contacts

    cmp_compound = compare_contacts(
        {"organization": "Acme Corp", "person_name": "John & Jane Smith"},
        {"organization": "Acme Corp", "person_name": "Jane Smith"},
    )
    assert cmp_compound.is_match
    assert "person" in cmp_compound.matched_pillars

    # cluster_contact_records links compound person across (company_key, person_root_key)
    compound_clusters = cluster_contact_records(
        [
            {"id": "c1", "organization": "Acme Corp", "person_name": "John & Jane Smith"},
            {"id": "c2", "organization": "Acme Corp", "person_name": "Jane Smith"},
            {"id": "c3", "organization": "Acme Corp", "person_name": "N/A"},
        ]
    )
    assert len(compound_clusters) == 2
    assert "SHARED_PERSON_AND_COMPANY_KEY" in compound_clusters[0].linkage_reasons


def test_deduplicate_companies_and_persons_fuzzy_threshold() -> None:
    comp_clusters = deduplicate_companies(["Acme Corp", "Acme Corporation"], fuzzy_threshold=0.80)
    assert len(comp_clusters) == 1

    per_clusters = deduplicate_persons(["Robert Smith", "Bob Smith"], fuzzy_threshold=0.80)
    assert len(per_clusters) == 1


def test_stream_standardize_csv_multi_pillar(tmp_path: Path) -> None:
    in_csv = tmp_path / "in.csv"
    out_csv = tmp_path / "out.csv"
    with in_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["phone", "country", "address", "company", "person", "email", "url"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "phone": "(212) 555-0199",
                "country": "US",
                "address": "100 Wall Street, New York, NY 10005",
                "company": "Acme Holdings, Inc.",
                "person": "Dr. Jane Smith",
                "email": "Jane.Smith+tag@gmail.com",
                "url": "http://www.acme.com/about?utm_source=test",
            }
        )

    rows = stream_standardize_csv(
        in_csv,
        out_csv,
        phone_col="phone",
        country_col="country",
        address_col="address",
        company_col="company",
        person_col="person",
        email_col="email",
        url_col="url",
    )
    assert rows == 1
    with out_csv.open("r", encoding="utf-8", newline="") as f:
        result_rows = list(csv.DictReader(f))
    assert len(result_rows) == 1
    r = result_rows[0]
    assert r["phone_e164"] == "+12125550199"
    assert r["address_line_1"] == "100 WALL ST"
    assert r["address_city"] == "NEW YORK"
    assert r["address_state"] == "NY"
    assert r["address_postal_code"] == "10005"
    assert r["address_key"] != ""
    assert r["company_legal_name"] != ""
    assert r["company_key"] != ""
    assert r["person_full_name"] == "JANE SMITH"
    assert r["person_key"] != ""
    assert r["email_canonical"] == "janesmith@gmail.com"
    assert r["email_domain"] == "gmail.com"
    assert r["url_canonical"] == "https://acme.com/about"
    assert r["url_domain"] == "acme.com"

    # Also test when optional column names are passed but absent from CSV input
    out_csv2 = tmp_path / "out2.csv"
    rows2 = stream_standardize_csv(
        in_csv,
        out_csv2,
        phone_col="phone",
        country_col="country",
        address_col="nonexistent_addr",
        company_col="nonexistent_comp",
        person_col="nonexistent_per",
        email_col="nonexistent_email",
        url_col="nonexistent_url",
    )
    assert rows2 == 1


def test_arrow_and_polars_all_six_pillars() -> None:
    # Type errors on invalid input
    with pytest.raises(TypeError):
        standardize_addresses_arrow("not_a_table")
    with pytest.raises(TypeError):
        standardize_addresses_polars("not_a_df")

    # Phone RecordBatch & LazyFrame
    phone_tbl = pa.table({"phone": ["(212) 555-0199"], "country": ["US"]})
    phone_batch = phone_tbl.to_batches()[0]
    res_phone_batch = standardize_arrow(phone_batch, as_struct=True)
    assert isinstance(res_phone_batch, pa.RecordBatch)
    assert "phone_standardized" in res_phone_batch.schema.names

    # Empty RecordBatch (0 rows)
    empty_batch = pa.RecordBatch.from_pydict(
        {"phone": pa.array([], type=pa.string())},
        schema=pa.schema([("phone", pa.string())]),
    )
    res_empty_batch = standardize_arrow(empty_batch)
    assert isinstance(res_empty_batch, pa.RecordBatch)
    assert res_empty_batch.num_rows == 0

    # Overwriting existing column in _finalize_arrow_output
    preexisting_tbl = pa.table({"phone": ["(212) 555-0199"], "phone_e164": ["old"]})
    res_overwrite = standardize_arrow(preexisting_tbl)
    assert res_overwrite.column("phone_e164").to_pylist() == ["+12125550199"]

    phone_lazy = pl.DataFrame({"phone": ["(212) 555-0199"]}).lazy()
    res_phone_lazy = standardize_polars(phone_lazy)
    assert isinstance(res_phone_lazy, pl.LazyFrame)
    assert res_phone_lazy.collect()["phone_e164"].to_list() == ["+12125550199"]

    # 1. Addresses Arrow & Polars
    addr_tbl = pa.table(
        {
            "address": ["100 Wall Street, New York, NY 10005"],
            "country": ["US"],
        }
    )
    with pytest.raises(ValueError, match="not a column"):
        standardize_addresses_arrow(addr_tbl, column="missing")
    res_addr_tbl = standardize_addresses_arrow(addr_tbl, country_column="country")
    assert res_addr_tbl.column("address_line_1").to_pylist() == ["100 WALL ST"]
    assert res_addr_tbl.column("address_city").to_pylist() == ["NEW YORK"]
    assert res_addr_tbl.column("address_state").to_pylist() == ["NY"]
    assert res_addr_tbl.column("address_postal_code").to_pylist() == ["10005"]
    assert res_addr_tbl.column("address_country_iso2").to_pylist() == ["US"]
    assert res_addr_tbl.column("address_is_valid").to_pylist() == [True]

    res_addr_batch = standardize_addresses_arrow(addr_tbl.to_batches()[0], as_struct=True)
    assert isinstance(res_addr_batch, pa.RecordBatch)
    assert "address_standardized" in res_addr_batch.schema.names

    addr_df = pl.DataFrame({"address": ["100 Wall Street, New York, NY 10005"]})
    res_addr_df = standardize_addresses_polars(addr_df)
    assert res_addr_df["address_line_1"].to_list() == ["100 WALL ST"]
    res_addr_lazy = standardize_addresses_polars(addr_df.lazy())
    assert isinstance(res_addr_lazy, pl.LazyFrame)

    # 2. Companies Arrow & Polars
    comp_tbl = pa.table({"company": ["Acme Holdings, Inc."], "country": ["US"]})
    with pytest.raises(ValueError, match="not a column"):
        standardize_companies_arrow(comp_tbl, company_col="missing")
    res_comp_tbl = standardize_companies_arrow(comp_tbl, country_col="country")
    assert res_comp_tbl.column("company_is_valid").to_pylist() == [True]
    res_comp_struct = standardize_companies_arrow(comp_tbl.to_batches()[0], as_struct=True)
    assert isinstance(res_comp_struct, pa.RecordBatch)

    comp_df = pl.DataFrame({"company": ["Acme Holdings, Inc."]})
    res_comp_df = standardize_companies_polars(comp_df)
    assert res_comp_df["company_is_valid"].to_list() == [True]
    assert isinstance(standardize_companies_polars(comp_df.lazy()), pl.LazyFrame)

    # 3. Persons Arrow & Polars
    per_tbl = pa.table({"person": ["Dr. Robert Smith Jr."]})
    with pytest.raises(ValueError, match="not a column"):
        standardize_persons_arrow(per_tbl, person_col="missing")
    res_per_tbl = standardize_persons_arrow(per_tbl)
    assert res_per_tbl.column("person_first_name").to_pylist() == ["ROBERT"]
    assert res_per_tbl.column("person_root_first_name").to_pylist() == ["ROBERT"]
    assert res_per_tbl.column("person_last_name").to_pylist() == ["SMITH"]
    assert isinstance(standardize_persons_arrow(per_tbl.to_batches()[0], as_struct=True), pa.RecordBatch)

    per_df = pl.DataFrame({"person": ["Bob Smith"]})
    res_per_df = standardize_persons_polars(per_df)
    assert res_per_df["person_root_first_name"].to_list() == ["ROBERT"]
    assert isinstance(standardize_persons_polars(per_df.lazy()), pl.LazyFrame)

    # 4. Emails Arrow & Polars
    em_tbl = pa.table({"email": ["Jane.Doe+promo@gmail.com"]})
    with pytest.raises(ValueError, match="not a column"):
        standardize_emails_arrow(em_tbl, email_col="missing")
    res_em_tbl = standardize_emails_arrow(em_tbl)
    assert res_em_tbl.column("email_canonical_email").to_pylist() == ["janedoe@gmail.com"]
    assert res_em_tbl.column("email_domain").to_pylist() == ["gmail.com"]
    assert isinstance(standardize_emails_arrow(em_tbl.to_batches()[0], as_struct=True), pa.RecordBatch)

    em_df = pl.DataFrame({"email": ["info@acme.com"]})
    res_em_df = standardize_emails_polars(em_df)
    assert res_em_df["email_is_role_account"].to_list() == [True]
    assert isinstance(standardize_emails_polars(em_df.lazy()), pl.LazyFrame)

    # 5. URLs Arrow & Polars
    url_tbl = pa.table({"url": ["http://www.acme.com/products?utm_source=ads"]})
    with pytest.raises(ValueError, match="not a column"):
        standardize_urls_arrow(url_tbl, url_col="missing")
    res_url_tbl = standardize_urls_arrow(url_tbl)
    assert res_url_tbl.column("url_url").to_pylist() == ["https://acme.com/products"]
    assert res_url_tbl.column("url_hostname").to_pylist() == ["acme.com"]
    assert res_url_tbl.column("url_domain").to_pylist() == ["acme.com"]
    assert isinstance(standardize_urls_arrow(url_tbl.to_batches()[0], as_struct=True), pa.RecordBatch)

    url_df = pl.DataFrame({"url": ["https://sub.example.co.uk/test"]})
    res_url_df = standardize_urls_polars(url_df)
    assert res_url_df["url_domain"].to_list() == ["example.co.uk"]
    assert isinstance(standardize_urls_polars(url_df.lazy()), pl.LazyFrame)

    # 6. Contacts Arrow & Polars (full columns and partial columns)
    contact_tbl = pa.table(
        {
            "street1": ["100 Wall St"],
            "city": ["New York"],
            "state": ["NY"],
            "postal_code": ["10005"],
            "country": ["US"],
            "phone": ["212-555-0199"],
            "organization": ["Acme Corp"],
            "person_name": ["Jane Smith"],
            "email": ["jane@acme.com"],
            "website": ["https://www.acme.com"],
        }
    )
    res_contact_tbl = standardize_contacts_arrow(contact_tbl)
    assert res_contact_tbl.column("contact_phone_e164").to_pylist() == ["+12125550199"]
    assert res_contact_tbl.column("contact_domain").to_pylist() == ["acme.com"]
    assert isinstance(
        standardize_contacts_arrow(contact_tbl.to_batches()[0], as_struct=True),
        pa.RecordBatch,
    )

    partial_contact_df = pl.DataFrame({"phone": ["212-555-0199"], "email": ["jane@acme.com"]})
    res_contact_df = standardize_contacts_polars(partial_contact_df)
    assert res_contact_df["contact_phone_e164"].to_list() == ["+12125550199"]
    assert res_contact_df["contact_domain"].to_list() == ["acme.com"]
    assert isinstance(standardize_contacts_polars(partial_contact_df.lazy()), pl.LazyFrame)


def test_http_endpoints_parity() -> None:
    client = TestClient(app)

    # /v1/address with enable_geocoding and explain
    r_addr = client.post(
        "/v1/address",
        json={
            "street1": "100 Wall St",
            "city": "New York",
            "state": "NY",
            "postal_code": "10005",
            "enable_geocoding": True,
            "explain": True,
        },
    )
    assert r_addr.status_code == 200
    body_addr = r_addr.json()
    assert "explanation" in body_addr
    assert body_addr["latitude"] is not None

    # /v1/address/compare
    r_acmp = client.post(
        "/v1/address/compare",
        json={
            "address_a": "100 Wall St, New York, NY 10005",
            "address_b": "100 Wall Street, New York, NY 10005",
        },
    )
    assert r_acmp.status_code == 200
    assert r_acmp.json()["is_match"] is True

    # /v1/address/deduplicate
    r_adedup = client.post(
        "/v1/address/deduplicate",
        json={
            "addresses": [
                "100 Wall St, New York, NY 10005",
                "100 Wall Street, New York, NY 10005",
            ]
        },
    )
    assert r_adedup.status_code == 200
    assert r_adedup.json()["cluster_count"] == 1

    # /v1/address/autocomplete
    r_auto = client.post(
        "/v1/address/autocomplete",
        json={"prefix": "100 WALL", "city": "NEW YORK", "state": "NY", "max_results": 3},
    )
    assert r_auto.status_code == 200
    assert r_auto.json()["count"] >= 1

    # /v1/company/deduplicate
    r_cdedup = client.post(
        "/v1/company/deduplicate",
        json={"companies": ["Acme Corp", "Acme Corporation"]},
    )
    assert r_cdedup.status_code == 200
    assert r_cdedup.json()["cluster_count"] == 1

    # /v1/person/deduplicate
    r_pdedup = client.post(
        "/v1/person/deduplicate",
        json={"persons": ["Robert Smith", "Bob Smith"]},
    )
    assert r_pdedup.status_code == 200
    assert r_pdedup.json()["cluster_count"] == 1

    # /v1/email/compare
    r_ecmp = client.post(
        "/v1/email/compare",
        json={"email_a": "jane.doe+1@gmail.com", "email_b": "janedoe@gmail.com"},
    )
    assert r_ecmp.status_code == 200
    assert r_ecmp.json()["is_match"] is True

    # /v1/url/compare
    r_ucmp = client.post(
        "/v1/url/compare",
        json={"url_a": "http://www.acme.com/a?utm_source=x", "url_b": "https://acme.com/a"},
    )
    assert r_ucmp.status_code == 200
    assert r_ucmp.json()["is_match"] is True

    # /v1/contact/cluster
    r_ccluster = client.post(
        "/v1/contact/cluster",
        json={
            "records": [
                {"id": "1", "phone": "212-555-0199", "email": "jane@acme.com"},
                {"id": "2", "phone": "+12125550199", "email": "jane@acme.com"},
            ]
        },
    )
    assert r_ccluster.status_code == 200
    assert r_ccluster.json()["cluster_count"] == 1

    # /v1/contact/batch
    r_cbatch = client.post(
        "/v1/contact/batch",
        json={
            "contacts": [
                {"street1": "100 Wall St", "city": "New York", "state": "NY", "phone": "212-555-0199"},
            ]
        },
    )
    assert r_cbatch.status_code == 200
    assert r_cbatch.json()["count"] == 1


def test_cli_subcommands_parity(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    # address --geocode --explain
    assert (
        cli_main(
            [
                "address",
                "100 Wall St",
                "--city",
                "New York",
                "--state",
                "NY",
                "--postal-code",
                "10005",
                "--geocode",
                "--explain",
            ]
        )
        == 0
    )
    out_addr = json.loads(capsys.readouterr().out)
    assert "explanation" in out_addr
    assert out_addr["latitude"] is not None

    # compare-addresses
    assert (
        cli_main(
            [
                "compare-addresses",
                "100 Wall St, New York, NY 10005",
                "100 Wall Street, New York, NY 10005",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["is_match"] is True

    # dedup-addresses
    assert (
        cli_main(
            [
                "dedup-addresses",
                "100 Wall St, New York, NY 10005",
                "100 Wall Street, New York, NY 10005",
            ]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)) == 1

    # autocomplete
    assert cli_main(["autocomplete", "100 WALL", "--state", "NY", "-n", "2"]) == 0
    assert len(json.loads(capsys.readouterr().out)) >= 1

    # dedup-companies
    assert cli_main(["dedup-companies", "Acme Corp", "Acme Corporation"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1

    # dedup-persons
    assert cli_main(["dedup-persons", "Robert Smith", "Bob Smith"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1

    # compare-emails
    assert cli_main(["compare-emails", "jane.doe@gmail.com", "janedoe@gmail.com"]) == 0
    assert json.loads(capsys.readouterr().out)["is_match"] is True

    # compare-urls
    assert cli_main(["compare-urls", "http://www.acme.com", "https://acme.com"]) == 0
    assert json.loads(capsys.readouterr().out)["is_match"] is True

    # cluster-contacts
    records_json = json.dumps(
        [
            {"id": "1", "phone": "212-555-0199"},
            {"id": "2", "phone": "+12125550199"},
        ]
    )
    assert cli_main(["cluster-contacts", records_json]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1

    # batch with multi-pillar columns
    in_csv = tmp_path / "cli_in.csv"
    out_csv = tmp_path / "cli_out.csv"
    in_csv.write_text(
        "phone,country,addr,comp,per,em,web\n2125550199,US,100 Wall St NY NY 10005,Acme Inc,Jane Doe,jane@acme.com,https://acme.com\n",
        encoding="utf-8",
    )
    assert (
        cli_main(
            [
                "batch",
                str(in_csv),
                str(out_csv),
                "--address-col",
                "addr",
                "--company-col",
                "comp",
                "--person-col",
                "per",
                "--email-col",
                "em",
                "--url-col",
                "web",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["processed_rows"] == 1


def test_mcp_tools_parity() -> None:
    def _call(name: str, arguments: dict[str, object]) -> object:
        resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        return json.loads(resp["result"]["content"][0]["text"])

    addr_res = _call(
        "standardize_address",
        {
            "street1": "100 Wall St",
            "city": "New York",
            "state": "NY",
            "postal_code": "10005",
            "enable_geocoding": True,
            "explain": True,
        },
    )
    assert isinstance(addr_res, dict)
    assert "explanation" in addr_res
    assert addr_res["latitude"] is not None

    ca_res = _call(
        "compare_addresses",
        {
            "address_a": "100 Wall St, New York, NY 10005",
            "address_b": "100 Wall Street, New York, NY 10005",
        },
    )
    assert isinstance(ca_res, dict) and ca_res["is_match"] is True

    da_res = _call(
        "deduplicate_addresses",
        {
            "addresses": [
                "100 Wall St, New York, NY 10005",
                "100 Wall Street, New York, NY 10005",
            ]
        },
    )
    assert isinstance(da_res, list) and len(da_res) == 1

    auto_res = _call(
        "autocomplete_address",
        {"prefix": "100 WALL", "city": "NEW YORK", "state": "NY", "max_results": 2},
    )
    assert isinstance(auto_res, list) and len(auto_res) >= 1

    dc_res = _call(
        "deduplicate_companies",
        {"companies": ["Acme Corp", "Acme Corporation"]},
    )
    assert isinstance(dc_res, list) and len(dc_res) == 1

    dp_res = _call(
        "deduplicate_persons",
        {"persons": ["Robert Smith", "Bob Smith"]},
    )
    assert isinstance(dp_res, list) and len(dp_res) == 1

    ce_res = _call(
        "compare_emails",
        {"email_a": "jane.doe@gmail.com", "email_b": "janedoe@gmail.com"},
    )
    assert isinstance(ce_res, dict) and ce_res["is_match"] is True

    cu_res = _call(
        "compare_urls",
        {"url_a": "http://www.acme.com", "url_b": "https://acme.com"},
    )
    assert isinstance(cu_res, dict) and cu_res["is_match"] is True

    cc_res = _call(
        "cluster_contact_records",
        {
            "records": [
                {"id": "1", "phone": "212-555-0199"},
                {"id": "2", "phone": "+12125550199"},
            ]
        },
    )
    assert isinstance(cc_res, list) and len(cc_res) == 1
