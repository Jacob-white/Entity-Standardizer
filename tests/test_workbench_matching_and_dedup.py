"""Tests for Cross-System Matching, Child Member Roster Joins, Single-File Dedup, and Exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl
import pytest

from entity_standardizer.workbench.mapping import ColumnMapping, FieldRole, MappingConfig
from entity_standardizer.workbench.match_runner import (
    MatchingOptions,
    MemberRosterSource,
    load_member_roster_map,
    run_cross_system_match,
    run_single_file_dedup,
)


def test_matching_options_and_child_roster_loader(tmp_path: Path) -> None:
    opts_def = MatchingOptions.from_dict(None)
    assert opts_def.profile == "CONTACT"
    assert opts_def.effective_thresholds() == (0.70, 0.50)

    opts_firm = MatchingOptions(profile="FIRM", synthetic_policy="ignore")
    assert opts_firm.effective_thresholds() == (0.72, 0.50)

    opts_cust = MatchingOptions.from_dict(
        {
            "profile": "CUSTOM",
            "match_threshold": 0.65,
            "potential_threshold": 0.45,
            "enabled_signals": ["crd", "company"],
        }
    )
    assert opts_cust.effective_thresholds() == (0.65, 0.45)
    assert opts_cust.to_dict()["profile"] == "CUSTOM"

    with pytest.raises(ValueError):
        MatchingOptions(profile="BAD")
    with pytest.raises(ValueError):
        MatchingOptions(synthetic_policy="BAD")
    with pytest.raises(ValueError, match="match_threshold"):
        MatchingOptions(match_threshold=1.5)
    with pytest.raises(ValueError, match="match_threshold"):
        MatchingOptions(match_threshold=float("nan"))
    with pytest.raises(ValueError, match="potential_threshold"):
        MatchingOptions(potential_threshold=-0.1)
    with pytest.raises(ValueError, match="cannot exceed"):
        MatchingOptions(match_threshold=0.5, potential_threshold=0.8)
    with pytest.raises(ValueError, match="switchboard_min_shared"):
        MatchingOptions(switchboard_min_shared=1)
    assert MatchingOptions(match_threshold=0.45).effective_thresholds() == (0.45, 0.45)

    roster_csv = tmp_path / "members.csv"
    roster_csv.write_text(
        "parent_id,member_crd,member_name,member_email\n"
        "0010,148763,Alice Smith,alice@acme.com\n"
        ",999999,Ignored Row,\n"
        "0010,,,   \n"
        "0010,---,Bob Jones,@@\n",
        encoding="utf-8",
    )
    rmap = load_member_roster_map(
        MemberRosterSource(
            path=roster_csv,
            parent_id_col="parent_id",
            member_cols=["member_crd", "member_name", "member_email"],
        )
    )
    assert "CRD:148763" in rmap["10"]
    assert "ALICE@ACME.COM" in rmap["10"]
    assert "SMITH|ALICE" in rmap["10"]
    assert "---" in rmap["10"] and "@@" in rmap["10"]


def test_cross_system_matching_steward_overrides_and_all_exports(tmp_path: Path, monkeypatch) -> None:
    left_csv = tmp_path / "sf.csv"
    with left_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["sf_id", "ext_id", "crd", "org", "fname", "lname", "cred", "title", "grp", "s1", "s2", "city", "st", "zip", "cntry", "phone", "fax", "email", "web", "social", "members"],
        )
        w.writeheader()
        # 1:1 Tier 1 CRD + org + address + phone + matching advisor_group + credentials
        w.writerow(
            {
                "sf_id": "SF1", "ext_id": "EXT01", "crd": "148763", "org": "Strategic Asset Alliance LLC",
                "fname": "Bob", "lname": "Smith", "cred": "CFA", "title": "Partner", "grp": "The Smith & Jones Group",
                "s1": "11 Bellwether Way", "s2": "", "city": "Bellingham", "st": "WA", "zip": "98225", "cntry": "US",
                "phone": "360-255-2500", "fax": "360-255-2501", "email": "bob@saai.com", "web": "https://saai.com",
                "social": "@saai", "members": "111;222",
            }
        )
        # N:1 + M:N candidates + Tier 2/3 match & potential
        w.writerow(
            {
                "sf_id": "SF2", "ext_id": "", "crd": "", "org": "Verger Capital Management",
                "fname": "Jane", "lname": "Doe", "cred": "", "title": "VP", "grp": "",
                "s1": "751 W 4th St", "s2": "Ste 410", "city": "Winston Salem", "st": "NC", "zip": "27101", "cntry": "US",
                "phone": "336-934-4101", "fax": "", "email": "info@verger.com", "web": "verger.com",
                "social": "", "members": "",
            }
        )
        w.writerow(
            {
                "sf_id": "SF3", "ext_id": "", "crd": "", "org": "Verger Capital Mgmt LP",
                "fname": "Jane", "lname": "Doe", "cred": "", "title": "", "grp": "",
                "s1": "751 W 4th St", "s2": "", "city": "Winston Salem", "st": "NC", "zip": "27101", "cntry": "US",
                "phone": "800-555-0199", "fax": "", "email": "jane.doe@gmail.com", "web": "",
                "social": "", "members": "",
            }
        )
        # Brand lineage + hyphenated surname + PO Box street
        w.writerow(
            {
                "sf_id": "SF4", "ext_id": "", "crd": "", "org": "Merrill Lynch, Pierce, Fenner & Smith",
                "fname": "Mary", "lname": "Smith-Jones", "cred": "", "title": "", "grp": "Turing & Church Advisory",
                "s1": "PO BOX 12", "s2": "", "city": "Austin", "st": "TX", "zip": "78701", "cntry": "US",
                "phone": "512-555-0100", "fax": "", "email": "mary@bofa.com", "web": "",
                "social": "", "members": "999;888",
            }
        )
        # Potential match (person + address, missing org/phone/email)
        w.writerow(
            {
                "sf_id": "SF5", "ext_id": "", "crd": "", "org": "",
                "fname": "Zed", "lname": "Zero", "cred": "", "title": "", "grp": "",
                "s1": "123 Boise Way", "s2": "", "city": "Boise", "st": "ID", "zip": "83701", "cntry": "US",
                "phone": "", "fax": "", "email": "", "web": "",
                "social": "", "members": "",
            }
        )
        # Truly unmatched Left (no org, no phone, no email, no state/zip)
        w.writerow(
            {
                "sf_id": "SF7", "ext_id": "", "crd": "", "org": "",
                "fname": "Orphan", "lname": "Left", "cred": "", "title": "", "grp": "",
                "s1": "", "s2": "", "city": "Reno", "st": "", "zip": "", "cntry": "US",
                "phone": "", "fax": "", "email": "", "web": "",
                "social": "", "members": "",
            }
        )
        # Synthetic test record
        w.writerow(
            {
                "sf_id": "SF6", "ext_id": "", "crd": "99999999", "org": "TEST SANDBOX FIRM",
                "fname": "", "lname": "", "cred": "", "title": "", "grp": "",
                "s1": "", "s2": "", "city": "", "st": "", "zip": "", "cntry": "US",
                "phone": "", "fax": "", "email": "test@acme.com", "web": "",
                "social": "", "members": "",
            }
        )

    right_json = tmp_path / "sc.json"
    right_rows = [
        {
            "sc_id": "SC1", "ext": "000EXT01", "crd": "148763", "org": "STRATEGIC ASSET ALLIANCE",
            "person": "Robert Smith", "grp": "Jones & Smith Group", "s1": "11 Bellwether Way Ste 200",
            "city": "Bellingham", "state": "WA", "zip": "98225-2956", "country": "US",
            "phone": "+13602552500", "fax": "+13602552501", "email": "bob@saai.com", "web": "https://www.saai.com",
            "roster": "111|222",
        },
        {
            "sc_id": "SC2", "ext": "", "crd": "", "org": "VERGER CAPITAL MANAGEMENT LLC",
            "person": "Jane M Doe", "grp": "", "s1": "751 West 4th Street",
            "city": "Winston Salem", "state": "NC", "zip": "27101", "country": "US",
            "phone": "+13369344101", "fax": "", "email": "jdoe@verger.com", "web": "https://verger.com",
            "roster": "",
        },
        {
            "sc_id": "SC3", "ext": "", "crd": "", "org": "VERGER CAPITAL MGMT",
            "person": "J Doe", "grp": "", "s1": "751 W 4th St",
            "city": "Winston Salem", "state": "NC", "zip": "27101", "country": "US",
            "phone": "800-555-0199", "fax": "", "email": "jane.doe@gmail.com", "web": "",
            "roster": "",
        },
        {
            "sc_id": "SC4", "ext": "", "crd": "", "org": "Bank of America Merrill Lynch",
            "person": "Mary Smith-Jones", "grp": "Church & Turing Advisory", "s1": "PO BOX 12",
            "city": "Austin", "state": "TX", "zip": "78701", "cntry": "US",
            "phone": "512-555-0199", "fax": "", "email": "mary.jones@bofa.com", "web": "",
            "roster": "999",
        },
        {
            "sc_id": "SC5", "ext": "", "crd": "", "org": "",
            "person": "Zed Zero", "grp": "", "s1": "123 Boise Way",
            "city": "Boise", "state": "ID", "zip": "83701", "country": "US",
            "phone": "", "fax": "", "email": "", "web": "",
            "roster": "",
        },
        {
            "sc_id": "SC6", "ext": "", "crd": "", "org": "Orphan Right Co",
            "person": "Yolanda Y", "grp": "", "s1": "99 Missing Way",
            "city": "Las Vegas", "state": "NV", "zip": "89101", "country": "US",
            "phone": "702-555-0199", "fax": "", "email": "y@rightonly.com", "web": "",
            "roster": "",
        },
    ]
    right_json.write_text(json.dumps(right_rows), encoding="utf-8")

    l_map = MappingConfig(
        mappings=[
            ColumnMapping("sf_id", FieldRole.RECORD_ID.value),
            ColumnMapping("ext_id", FieldRole.EXTERNAL_ID.value),
            ColumnMapping("crd", FieldRole.CRD.value),
            ColumnMapping("org", FieldRole.ORGANIZATION.value),
            ColumnMapping("fname", FieldRole.FIRST_NAME.value),
            ColumnMapping("lname", FieldRole.LAST_NAME.value),
            ColumnMapping("cred", FieldRole.CREDENTIALS.value),
            ColumnMapping("title", FieldRole.JOB_TITLE.value),
            ColumnMapping("grp", FieldRole.ADVISOR_GROUP.value),
            ColumnMapping("s1", FieldRole.STREET1.value),
            ColumnMapping("s2", FieldRole.STREET2.value),
            ColumnMapping("city", FieldRole.CITY.value),
            ColumnMapping("st", FieldRole.STATE.value),
            ColumnMapping("zip", FieldRole.POSTAL_CODE.value),
            ColumnMapping("cntry", FieldRole.COUNTRY.value),
            ColumnMapping("phone", FieldRole.PHONE.value),
            ColumnMapping("fax", FieldRole.FAX.value),
            ColumnMapping("email", FieldRole.EMAIL.value),
            ColumnMapping("web", FieldRole.WEBSITE.value),
            ColumnMapping("social", FieldRole.SOCIAL.value),
            ColumnMapping("members", FieldRole.MEMBER_ROSTER.value),
        ]
    )
    r_map = MappingConfig(
        mappings=[
            ColumnMapping("sc_id", FieldRole.RECORD_ID.value),
            ColumnMapping("ext", FieldRole.EXTERNAL_ID.value),
            ColumnMapping("crd", FieldRole.CRD.value),
            ColumnMapping("org", FieldRole.ORGANIZATION.value),
            ColumnMapping("person", FieldRole.PERSON_NAME.value),
            ColumnMapping("grp", FieldRole.ADVISOR_GROUP.value),
            ColumnMapping("s1", FieldRole.STREET1.value),
            ColumnMapping("city", FieldRole.CITY.value),
            ColumnMapping("state", FieldRole.STATE.value),
            ColumnMapping("zip", FieldRole.POSTAL_CODE.value),
            ColumnMapping("country", FieldRole.COUNTRY.value),
            ColumnMapping("phone", FieldRole.PHONE.value),
            ColumnMapping("fax", FieldRole.FAX.value),
            ColumnMapping("email", FieldRole.EMAIL.value),
            ColumnMapping("web", FieldRole.WEBSITE.value),
            ColumnMapping("roster", FieldRole.MEMBER_ROSTER.value),
        ]
    )

    # Child roster attached to Left SF1
    l_roster_csv = tmp_path / "l_roster.csv"
    l_roster_csv.write_text("parent_id,rep_name\nSF1,Extra Member\n", encoding="utf-8")
    l_roster = MemberRosterSource(path=l_roster_csv, parent_id_col="parent_id", member_cols=["rep_name"])

    session = run_cross_system_match(
        left_csv,
        right_json,
        l_map,
        r_map,
        MatchingOptions(profile="PARTNERSHIP", synthetic_policy="exclude", potential_threshold=0.45),
        left_roster_source=l_roster,
    )
    sc = session.scorecard
    assert sc["excluded_synthetic_left"] == 1
    assert sc["matched_pairs"] >= 2
    assert sc["total_left"] == 6 and sc["total_right"] == 6

    # Query filters across all views and cardinalities
    all_q = session.query_pairs(view="all_pairs")
    assert all_q["total"] >= 2
    assert session.query_pairs(view="matched")["total"] == sc["matched_pairs"]
    assert session.query_pairs(view="unmatched_left")["total"] == sc["unmatched_left"]
    assert session.query_pairs(view="unmatched_right")["total"] == sc["unmatched_right"]
    assert session.query_pairs(search="Strategic")["total"] >= 1
    assert session.query_pairs(cardinality="1:1")["total"] >= 1
    assert session.query_pairs(discrepancy_only=True)["total"] >= 0

    # Steward decisions: reject active pair, approve potential pair (if present) or re-approve rejected pair, reset
    first_pid = session.pairs[0].pair_id
    res_rej = session.apply_decision(first_pid, "reject", note="False positive check")
    assert res_rej["pair"]["effective_status"] == "REJECTED"
    assert session.query_pairs(view="rejected")["total"] == 1

    res_app = session.apply_decision(first_pid, "approve", note="Verified manually")
    assert res_app["pair"]["effective_status"] == "MATCHED"

    res_rst = session.apply_decision(first_pid, "reset")
    assert res_rst["pair"]["steward_decision"] is None

    # Steward approval promotes a 1:N / potential secondary candidate to primary match & enriched_left winner
    cand_pair = next(p for p in session.pairs if p.pair_id != first_pid)
    session.apply_decision(cand_pair.pair_id, "approve", note="Promote candidate")
    enr_promo = tmp_path / "enriched_promo.csv"
    session.export_enriched_left(enr_promo)
    with enr_promo.open("r", encoding="utf-8", newline="") as epf:
        ep_rows = {r["sf_id"]: r for r in csv.DictReader(epf)}
    assert ep_rows[cand_pair.left_id]["steward_decision"] == "approved"
    session.apply_decision(cand_pair.pair_id, "reset")

    with pytest.raises(KeyError):
        session.apply_decision("NO_SUCH_PAIR", "approve")
    with pytest.raises(ValueError):
        session.apply_decision(first_pid, "unknown_action")

    # Test all 6 export deliverables preserving Left CSV & Right JSON formats
    cmp_out = tmp_path / "comparison.csv"
    enr_out = tmp_path / "enriched_left.csv"
    un_l_out = tmp_path / "unmatched_left.csv"
    un_r_out = tmp_path / "unmatched_right.json"
    sc_out = tmp_path / "scorecard.csv"
    bundle_out = tmp_path / "bundle.xlsx"

    assert session.export_comparison(cmp_out) == len(session.pairs)
    assert session.export_enriched_left(enr_out) == 6
    session.export_unmatched_left(un_l_out)
    session.export_unmatched_right(un_r_out)
    session.export_scorecard(sc_out)
    session.export_xlsx_bundle(bundle_out)

    with enr_out.open("r", encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == 6
    assert isinstance(json.loads(un_r_out.read_text(encoding="utf-8")), list)
    wb = openpyxl.load_workbook(bundle_out)
    assert wb.sheetnames == ["Scorecard", "Comparison", "Unmatched_Left", "Unmatched_Right"]
    wb.close()

    # Also exercise auto_standardize=False, custom signal filter, and Tier 3 > _MAX_TIER3_BUCKET_SIZE guard
    import entity_standardizer.workbench.match_runner as match_runner_mod

    monkeypatch.setattr(match_runner_mod, "_MAX_TIER3_BUCKET_SIZE", 1)
    res_nostd = run_cross_system_match(
        left_csv,
        right_json,
        l_map,
        r_map,
        MatchingOptions(
            profile="CUSTOM",
            auto_standardize=False,
            synthetic_policy="flag",
            enabled_signals=("crd", "company", "email"),
        ),
    )
    assert res_nostd.scorecard["synthetic_left"] == 1


def test_single_file_dedup_and_overrides(tmp_path: Path) -> None:
    src_csv = tmp_path / "dups.csv"
    with src_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "org", "person", "title", "s1", "city", "st", "zip", "phone", "email"])
        w.writeheader()
        w.writerow(
            {
                "id": "1", "org": "BlackRock, Inc.", "person": "Bob Smith", "title": "",
                "s1": "50 Hudson Yards", "city": "New York", "st": "NY", "zip": "10001",
                "phone": "212-555-0101", "email": "bsmith@blackrock.com",
            }
        )
        w.writerow(
            {
                "id": "2", "org": "BLACKROCK INCORPORATED /DE/", "person": "Robert Smith", "title": "Managing Director",
                "s1": "", "city": "New York", "st": "NY", "zip": "10001",
                "phone": "+12125550101", "email": "",
            }
        )
        w.writerow(
            {
                "id": "3", "org": "Vanguard Group", "person": "Alice Roe", "title": "Principal",
                "s1": "100 Vanguard Blvd", "city": "Malvern", "st": "PA", "zip": "19355",
                "phone": "610-555-0202", "email": "alice@vanguard.com",
            }
        )

    mapping = MappingConfig(
        mappings=[
            ColumnMapping("id", FieldRole.RECORD_ID.value),
            ColumnMapping("org", FieldRole.ORGANIZATION.value),
            ColumnMapping("person", FieldRole.PERSON_NAME.value),
            ColumnMapping("title", FieldRole.JOB_TITLE.value),
            ColumnMapping("s1", FieldRole.STREET1.value),
            ColumnMapping("city", FieldRole.CITY.value),
            ColumnMapping("st", FieldRole.STATE.value),
            ColumnMapping("zip", FieldRole.POSTAL_CODE.value),
            ColumnMapping("phone", FieldRole.PHONE.value),
            ColumnMapping("email", FieldRole.EMAIL.value),
        ]
    )

    session = run_single_file_dedup(src_csv, mapping, MatchingOptions(match_threshold=0.70))
    assert session.summary["cluster_count"] == 2
    assert session.summary["duplicate_rows_collapsed"] == 1

    # Export tagged_all_rows and golden_only (golden_only coalesces missing title from duplicate member)
    tagged_out = tmp_path / "tagged.csv"
    golden_out = tmp_path / "golden.csv"
    assert session.export(tagged_out, mode="tagged_all_rows") == 3
    assert session.export(golden_out, mode="golden_only") == 2
    with golden_out.open("r", encoding="utf-8", newline="") as gf:
        g_rows = list(csv.DictReader(gf))
    assert any(r["title"] == "Managing Director" for r in g_rows)

    with pytest.raises(ValueError):
        session.export(tmp_path / "bad.csv", mode="bad_mode")

    # Exclude row 1 from cluster -> splits into 3 singletons, then restore -> 2 clusters
    res_excl = session.set_excluded_row(1, True)
    assert res_excl["summary"]["cluster_count"] == 3
    res_rest = session.set_excluded_row(1, False)
    assert res_rest["summary"]["cluster_count"] == 2

    with pytest.raises(KeyError):
        session.set_excluded_row(999, True)

    # Atomic address/person group isolation (primary Billing UK vs fallback Shipping CA never Frankensteined)
    from entity_standardizer.workbench.match_runner import prepare_records_for_matching

    multi_grp_map = MappingConfig(
        [
            ColumnMapping("id", FieldRole.RECORD_ID.value, "primary"),
            ColumnMapping("b_s1", FieldRole.STREET1.value, "billing"),
            ColumnMapping("b_city", FieldRole.CITY.value, "billing"),
            ColumnMapping("b_cntry", FieldRole.COUNTRY.value, "billing"),
            ColumnMapping("s_st", FieldRole.STATE.value, "shipping"),
            ColumnMapping("org", FieldRole.ORGANIZATION.value, "primary"),
            ColumnMapping("email", FieldRole.EMAIL.value, "primary"),
            ColumnMapping("web", FieldRole.WEBSITE.value, "primary"),
        ]
    )
    prepped, _ = prepare_records_for_matching(
        [
            {
                "id": "1",
                "b_s1": "10 Downing St",
                "b_city": "London",
                "b_cntry": "GB",
                "s_st": "ON",
                "org": "!!!",
                "email": "not-an-email",
                "web": "https://acme.com/about",
            },
            {
                "id": "2",
                "b_s1": "10 Downing St",
                "b_city": "London",
                "b_cntry": "GB",
                "s_st": "ON",
                "org": "TBD",
                "email": "not-an-email",
                "web": "https://acme.com/team",
            },
        ],
        multi_grp_map,
        MatchingOptions(auto_standardize=False),
    )
    d0 = prepped[0].flat_display()
    assert d0["country"] == "GBR" and d0["state"] == ""
    assert d0["email"] == "" and d0["organization"] == ""
    assert prepped[1].flat_display()["organization"] == ""

    # XLSX dedup export preserves untouched sibling sheet
    xlsx_src = tmp_path / "dedup_multi.xlsx"
    wb_d = openpyxl.Workbook()
    ws_data = wb_d.active
    ws_data.title = "Entities"
    ws_data.append(["id", "org", "phone"])
    ws_data.append(["1", "Acme Inc", "212-555-2368"])
    ws_data.append(["2", "Acme Incorporated", "+12125552368"])
    ws_meta = wb_d.create_sheet("Metadata")
    ws_meta.append(["note"])
    ws_meta.append(["keep_sibling"])
    wb_d.save(xlsx_src)
    wb_d.close()

    ds_xlsx = run_single_file_dedup(
        xlsx_src,
        MappingConfig(
            [
                ColumnMapping("id", FieldRole.RECORD_ID.value),
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("phone", FieldRole.PHONE.value),
            ]
        ),
        MatchingOptions(),
        sheet_name="Entities",
    )
    xlsx_out = tmp_path / "dedup_out.xlsx"
    ds_xlsx.export(xlsx_out, mode="golden_only")
    wb_chk = openpyxl.load_workbook(xlsx_out)
    assert wb_chk.sheetnames == ["Entities", "Metadata"]
    assert wb_chk["Metadata"].cell(2, 1).value == "keep_sibling"
    wb_chk.close()

    # Pass-3 regression: float('nan') cells in external_id/person/roster never cause false EXT:NAN matches or block golden survivorship
    prepped_nan, _ = prepare_records_for_matching(
        [
            {"id": "1", "ext": float("nan"), "person": float("nan"), "ros": float("nan")},
            {"id": "2", "ext": float("nan"), "person": float("nan"), "ros": float("nan")},
        ],
        MappingConfig(
            [
                ColumnMapping("id", FieldRole.RECORD_ID.value),
                ColumnMapping("ext", FieldRole.EXTERNAL_ID.value),
                ColumnMapping("person", FieldRole.PERSON_NAME.value),
                ColumnMapping("ros", FieldRole.MEMBER_ROSTER.value),
            ]
        ),
        MatchingOptions(),
    )
    assert prepped_nan[0].external_id is None and prepped_nan[0].contact.person is None
    assert prepped_nan[0].member_roster == set()

    nan_dedup_pq = tmp_path / "nan_coalesce.parquet"
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(
        pa.table(
            {
                "id": ["1", "2"],
                "org": ["Acme LLC", "Acme Incorporated"],
                "street1": ["350 Fifth Ave", "350 5th Ave"],
                "city": ["New York", "New York"],
                "state": ["NY", "NY"],
                "phone": ["+12125552368", "+12125552368"],
                "email": ["info@acme.com", "info@acme.com"],
                "note_f": [float("nan"), 9.5],
            }
        ),
        nan_dedup_pq,
    )
    ds_nan_pq = run_single_file_dedup(
        nan_dedup_pq,
        MappingConfig(
            [
                ColumnMapping("id", FieldRole.RECORD_ID.value),
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("street1", FieldRole.STREET1.value),
                ColumnMapping("city", FieldRole.CITY.value),
                ColumnMapping("state", FieldRole.STATE.value),
                ColumnMapping("phone", FieldRole.PHONE.value),
                ColumnMapping("email", FieldRole.EMAIL.value),
            ]
        ),
        MatchingOptions(),
    )
    ds_nan_out = tmp_path / "nan_coalesced_golden.parquet"
    assert ds_nan_pq.export(ds_nan_out, mode="golden_only") == 1
    assert pq.read_table(ds_nan_out).column("note_f").to_pylist() == [9.5]

    # Pass-5: MatchingOptions malformed inputs & no-address Left vs Canadian Right country comparison + export cols
    with pytest.raises(ValueError, match="enabled_signals"):
        MatchingOptions.from_dict({"enabled_signals": "crd"})
    with pytest.raises(ValueError, match="switchboard_min_shared"):
        MatchingOptions.from_dict({"switchboard_min_shared": True})

    l_noaddr = tmp_path / "l_noaddr.csv"
    r_ca = tmp_path / "r_ca.csv"
    l_noaddr.write_text("id,org,email\nL1,Shopify Inc,ir@shopify.com\n", encoding="utf-8")
    r_ca.write_text(
        "id,org,s1,city,st,zip,cntry,email\n"
        "R1,SHOPIFY INC,151 O'Connor St,Ottawa,ON,K2P 2L8,CA,ir@shopify.com\n",
        encoding="utf-8",
    )
    ms_ca = run_cross_system_match(
        l_noaddr,
        r_ca,
        MappingConfig(
            [
                ColumnMapping("id", FieldRole.RECORD_ID.value),
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("email", FieldRole.EMAIL.value),
            ]
        ),
        MappingConfig(
            [
                ColumnMapping("id", FieldRole.RECORD_ID.value),
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("s1", FieldRole.STREET1.value),
                ColumnMapping("city", FieldRole.CITY.value),
                ColumnMapping("st", FieldRole.STATE.value),
                ColumnMapping("zip", FieldRole.POSTAL_CODE.value),
                ColumnMapping("cntry", FieldRole.COUNTRY.value),
                ColumnMapping("email", FieldRole.EMAIL.value),
            ]
        ),
        MatchingOptions(profile="FIRM"),
    )
    assert len(ms_ca.pairs) == 1
    p_ca = ms_ca.pairs[0]
    assert p_ca.left_display["country"] == ""
    assert p_ca.right_display["country"] == "CAN"
    assert p_ca.field_comparisons["cmp_country"] == "RIGHT_ONLY"
    assert p_ca.discrepancy_fields == []
    cmp_ca_csv = tmp_path / "cmp_ca.csv"
    ms_ca.export_comparison(cmp_ca_csv)
    with cmp_ca_csv.open("r", encoding="utf-8", newline="") as f_ca:
        ca_rows = list(csv.DictReader(f_ca))
    assert ca_rows[0]["left_country"] == "" and ca_rows[0]["right_country"] == "CAN"
    assert ca_rows[0]["cmp_country"] == "RIGHT_ONLY"

    # Pass-6 regressions:
    # 1) Child roster join matches zero-padded RECORD_ID ("0010"), handles blank RECORD_ID,
    #    validates missing roster columns, and returns {} on empty 0-byte roster files
    l_zp = tmp_path / "l_zp.csv"
    r_zp = tmp_path / "r_zp.csv"
    ros_zp = tmp_path / "ros_zp.csv"
    l_zp.write_text("Id,Team_Name\n0010,Alpha Advisors\n,Unkeyed Team\n", encoding="utf-8")
    r_zp.write_text("Id,Team_Name\nR-1,Alpha Wealth\n", encoding="utf-8")
    ros_zp.write_text("Account_Id,Rep_CRD\n0010,148763\n", encoding="utf-8")
    ms_zp = run_cross_system_match(
        l_zp,
        r_zp,
        MappingConfig([ColumnMapping("Id", FieldRole.RECORD_ID.value), ColumnMapping("Team_Name", FieldRole.ADVISOR_GROUP.value)]),
        MappingConfig([ColumnMapping("Id", FieldRole.RECORD_ID.value), ColumnMapping("Team_Name", FieldRole.ADVISOR_GROUP.value)]),
        MatchingOptions(profile="TEAM"),
        left_roster_source=MemberRosterSource(ros_zp, "Account_Id", ["Rep_CRD"]),
    )
    assert [r.flat_display()["roster_count"] for r in ms_zp.left_records] == [1, 0]

    with pytest.raises(ValueError, match="Roster column 'MissingCol' not found"):
        load_member_roster_map(MemberRosterSource(ros_zp, "Account_Id", ["MissingCol"]))
    empty_ros = tmp_path / "empty_ros.csv"
    empty_ros.write_text("", encoding="utf-8")
    assert load_member_roster_map(MemberRosterSource(empty_ros, "Account_Id", ["Rep_CRD"])) == {}

    # 2) Evicted .xlsx & .parquet source files still allow export_enriched_left cleanly
    ev_xlsx = tmp_path / "evict_left.xlsx"
    wb_ev = openpyxl.Workbook()
    wb_ev.active.append(["id", "org"])
    wb_ev.active.append(["1", "Acme LLC"])
    wb_ev.save(ev_xlsx)
    wb_ev.close()
    ms_ev_x = run_cross_system_match(
        ev_xlsx,
        r_zp,
        MappingConfig([ColumnMapping("id", FieldRole.RECORD_ID.value), ColumnMapping("org", FieldRole.ORGANIZATION.value)]),
        MappingConfig([ColumnMapping("Id", FieldRole.RECORD_ID.value), ColumnMapping("Team_Name", FieldRole.ORGANIZATION.value)]),
        MatchingOptions(),
    )
    ev_xlsx.unlink()
    ev_xlsx_out = tmp_path / "evict_enriched.xlsx"
    assert ms_ev_x.export_enriched_left(ev_xlsx_out) == 1
    assert ev_xlsx_out.is_file()

    ev_pq = tmp_path / "evict_left.parquet"
    pq.write_table(pa.table({"id": ["1"], "org": ["Acme LLC"]}), ev_pq)
    ms_ev_p = run_cross_system_match(
        ev_pq,
        r_zp,
        MappingConfig([ColumnMapping("id", FieldRole.RECORD_ID.value), ColumnMapping("org", FieldRole.ORGANIZATION.value)]),
        MappingConfig([ColumnMapping("Id", FieldRole.RECORD_ID.value), ColumnMapping("Team_Name", FieldRole.ORGANIZATION.value)]),
        MatchingOptions(),
    )
    ev_pq.unlink()
    ev_pq_out = tmp_path / "evict_enriched.parquet"
    assert ms_ev_p.export_enriched_left(ev_pq_out) == 1
    assert ev_pq_out.is_file()

    # Pass-7 regressions:
    # 1) MatchSession.query_pairs search covers unmatched_left/unmatched_right, steward_note, and left/right display attrs
    l_q = tmp_path / "l_query.csv"
    r_q = tmp_path / "r_query.csv"
    l_q.write_text(
        "id,org,crd,city,phone\nL1,Acme Corp,1234567,Boston,212-555-2368\nL2,Unmatched Alpha,,Miami,305-555-0100\n",
        encoding="utf-8",
    )
    r_q.write_text(
        "id,org,crd,city,phone\nR1,Acme Corp,1234567,Dallas,212-555-2368\nR2,Unmatched Omega,,Seattle,206-555-0200\n",
        encoding="utf-8",
    )
    q_map = MappingConfig(
        [
            ColumnMapping("id", FieldRole.RECORD_ID.value),
            ColumnMapping("org", FieldRole.ORGANIZATION.value),
            ColumnMapping("crd", FieldRole.CRD.value),
            ColumnMapping("city", FieldRole.CITY.value),
            ColumnMapping("phone", FieldRole.PHONE.value),
        ]
    )
    ms_q = run_cross_system_match(l_q, r_q, q_map, q_map, MatchingOptions(profile="FIRM"))
    ms_q.apply_decision("PAIR-000001", "approve", note="steward-tag-42")
    assert ms_q.query_pairs(view="all_pairs", search="steward-tag-42")["total"] == 1
    assert ms_q.query_pairs(view="all_pairs", search="boston")["total"] == 1
    assert ms_q.query_pairs(view="all_pairs", search="dallas")["total"] == 1
    assert ms_q.query_pairs(view="all_pairs", search="nonexistent-xyz")["total"] == 0
    assert ms_q.query_pairs(view="unmatched_left", search="miami")["total"] == 1
    assert ms_q.query_pairs(view="unmatched_left", search="seattle")["total"] == 0
    assert ms_q.query_pairs(view="unmatched_right", search="seattle")["total"] == 1
    assert ms_q.query_pairs(view="unmatched_right", search="miami")["total"] == 0

    # 2) DedupSession golden_only on merged-cell .xlsx shrinks cleanly with zero phantom empty rows
    mg_ded_xlsx = tmp_path / "dedup_merged.xlsx"
    wb_md = openpyxl.Workbook()
    ws_md = wb_md.active
    ws_md.append(["Id", "Name", "Dept"])
    ws_md.append(["EXT-1", "Bob Smith", "Sales"])
    ws_md.append(["EXT-1", "Bob Smith", "Sales"])
    ws_md.merge_cells("B3:C3")
    wb_md.save(mg_ded_xlsx)
    wb_md.close()
    ds_md = run_single_file_dedup(
        mg_ded_xlsx,
        MappingConfig([ColumnMapping("Id", FieldRole.EXTERNAL_ID.value), ColumnMapping("Name", FieldRole.PERSON_NAME.value)]),
        MatchingOptions(),
    )
    mg_ded_out = tmp_path / "dedup_merged_out.xlsx"
    assert ds_md.export(mg_ded_out, mode="golden_only") == 1
    wb_md_chk = openpyxl.load_workbook(mg_ded_out)
    assert wb_md_chk.active.max_row == 2
    assert list(wb_md_chk.active.merged_cells.ranges) == []
    wb_md_chk.close()
