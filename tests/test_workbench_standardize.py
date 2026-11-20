"""Tests for File Standardizer runner, grouped cross-healing, options, and preview diffs."""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from entity_standardizer.person import StandardizedPerson, standardize_person
from entity_standardizer.standardizer import standardize_phone
from entity_standardizer.workbench.mapping import ColumnMapping, FieldRole, MappingConfig
from entity_standardizer.workbench.options import StandardizationOptions
from entity_standardizer.workbench.standardize_runner import (
    apply_text_case,
    compute_output_columns,
    format_country_value,
    format_email_value,
    format_person_full_name,
    format_phone_value,
    preview_standardize_source,
    standardize_row_with_config,
    standardize_tabular_file,
)


def test_options_validation_and_helpers() -> None:
    opts = StandardizationOptions.from_dict(None)
    assert opts.column_mode == "overwrite"
    assert opts.csv_formula_guard is False

    opts_custom = StandardizationOptions.from_dict(
        {
            "column_mode": "append_std",
            "id_pad_width": 8,
            "default_country": "gb",
        }
    )
    assert opts_custom.id_pad_width == 8 and opts_custom.default_country == "GB"
    assert StandardizationOptions.from_dict({"id_pad_width": None}).id_pad_width is None

    with pytest.raises(ValueError):
        StandardizationOptions(column_mode="bad_mode")
    with pytest.raises(ValueError):
        StandardizationOptions(id_pad_width=0)
    with pytest.raises(ValueError, match="not bool"):
        StandardizationOptions(id_pad_width=True)
    assert StandardizationOptions.from_dict({"id_pad_width": "6"}).id_pad_width == 6

    assert apply_text_case("", "title") == ""
    assert apply_text_case("GOLDMAN SACHS LLC", "title") == "Goldman Sachs LLC"
    assert format_country_value(None, "US", "iso2", "upper") is None
    assert format_country_value("XYZ", "XYZ", "iso2", "upper") == "XYZ"
    assert format_country_value("USA", "United States", "auto", "title") == "United States"
    assert format_country_value("USA", "USA", "auto", "upper") == "USA"
    assert format_country_value("USA", "", "auto", "upper") == "US"
    assert format_country_value("USA", "United States", "iso2", "upper") == "US"
    assert format_country_value("USA", "US", "iso3", "upper") == "USA"
    assert format_phone_value(standardize_phone("bad"), StandardizationOptions()) is None
    assert format_email_value("not-an-email", StandardizationOptions())[1] is None
    assert format_person_full_name(StandardizedPerson(raw_input=""), StandardizationOptions()) is None
    assert (
        format_person_full_name(
            standardize_person("Jane Doe"),
            StandardizationOptions(person_format="last_comma_first", person_case="upper"),
        )
        == "DOE, JANE"
    )

    cols_dup = compute_output_columns(
        ["org", "org_std"],
        MappingConfig([ColumnMapping("org", FieldRole.ORGANIZATION.value)]),
        StandardizationOptions(column_mode="append_std", include_matching_keys=True),
    )
    assert cols_dup.count("org_std") == 1
    assert "primary_company_compact_key" in cols_dup and "primary_address_street_core_key" not in cols_dup

    cols_keep = compute_output_columns(
        ["org"],
        MappingConfig([ColumnMapping("org", FieldRole.ORGANIZATION.value)]),
        StandardizationOptions(column_mode="overwrite_keep_raw", couple_split_mode="append_secondary_col"),
    )
    assert "org_raw" in cols_keep

    cols_sec_p = compute_output_columns(
        ["person"],
        MappingConfig([ColumnMapping("person", FieldRole.PERSON_NAME.value)]),
        StandardizationOptions(couple_split_mode="append_secondary_col"),
    )
    assert "person_secondary" in cols_sec_p

    cols_sec_comp = compute_output_columns(
        ["fn"],
        MappingConfig([ColumnMapping("fn", FieldRole.FIRST_NAME.value)]),
        StandardizationOptions(couple_split_mode="append_secondary_col"),
    )
    assert "primary_secondary_person" in cols_sec_comp


def test_all_output_modes_policies_and_pillars(tmp_path: Path) -> None:
    # Multi-group + split person + phone/fax + web + CRD + external_id + advisor_group + placeholders
    mapping = MappingConfig(
        mappings=[
            ColumnMapping("rec_id", FieldRole.RECORD_ID.value, "primary"),
            ColumnMapping("ext_id", FieldRole.EXTERNAL_ID.value, "primary"),
            ColumnMapping("crd", FieldRole.CRD.value, "primary"),
            ColumnMapping("org", FieldRole.ORGANIZATION.value, "primary"),
            ColumnMapping("sal", FieldRole.SALUTATION.value, "primary"),
            ColumnMapping("fname", FieldRole.FIRST_NAME.value, "primary"),
            ColumnMapping("mname", FieldRole.MIDDLE_NAME.value, "primary"),
            ColumnMapping("lname", FieldRole.LAST_NAME.value, "primary"),
            ColumnMapping("sfx", FieldRole.GENERATIONAL_SUFFIX.value, "primary"),
            ColumnMapping("cred", FieldRole.CREDENTIALS.value, "primary"),
            ColumnMapping("title", FieldRole.JOB_TITLE.value, "primary"),
            ColumnMapping("team", FieldRole.ADVISOR_GROUP.value, "primary"),
            ColumnMapping("roster", FieldRole.MEMBER_ROSTER.value, "primary"),
            ColumnMapping("s1", FieldRole.STREET1.value, "primary"),
            ColumnMapping("s2", FieldRole.STREET2.value, "primary"),
            ColumnMapping("city", FieldRole.CITY.value, "primary"),
            ColumnMapping("st", FieldRole.STATE.value, "primary"),
            ColumnMapping("zip", FieldRole.POSTAL_CODE.value, "primary"),
            ColumnMapping("cntry", FieldRole.COUNTRY.value, "primary"),
            ColumnMapping("phone", FieldRole.PHONE.value, "primary"),
            ColumnMapping("fax", FieldRole.FAX.value, "primary"),
            ColumnMapping("email", FieldRole.EMAIL.value, "primary"),
            ColumnMapping("web", FieldRole.WEBSITE.value, "primary"),
            ColumnMapping("social", FieldRole.SOCIAL.value, "primary"),
            ColumnMapping("ship_s1", FieldRole.STREET1.value, "shipping"),
            ColumnMapping("ship_city", FieldRole.CITY.value, "shipping"),
            ColumnMapping("ship_st", FieldRole.STATE.value, "shipping"),
            ColumnMapping("ship_zip", FieldRole.POSTAL_CODE.value, "shipping"),
            ColumnMapping("ship_cntry", FieldRole.COUNTRY.value, "shipping"),
        ]
    )

    csv_in = tmp_path / "contacts.csv"
    with csv_in.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[m.column for m in mapping.mappings],
        )
        w.writeheader()
        w.writerow(
            {
                "rec_id": "R1",
                "ext_id": "0042",
                "crd": "CRD# 148763",
                "org": "The Acme Holdings, Inc. /DE/",
                "sal": "Dr.",
                "fname": "Bob",
                "mname": "J.",
                "lname": "Smith",
                "sfx": "Jr.",
                "cred": "M.D.",
                "title": "SVP of Eng",
                "team": "Smith & Jones Wealth Group",
                "roster": "111;222",
                "s1": "350 Fifth Ave Ste 400 Tel: 212-555-2368",
                "s2": "",
                "city": "New York",
                "st": "",
                "zip": "10118",
                "cntry": "United States",
                "phone": "",
                "fax": "212-555-9999 ext 12",
                "email": "Bob.Smith+crm@gmial.com",
                "web": "http://www.acme.com/?utm_source=x",
                "social": "@acme",
                "ship_s1": "10 Downing St",
                "ship_city": "London",
                "ship_st": "",
                "ship_zip": "SW1A 2AA",
                "ship_cntry": "GB",
            }
        )
        w.writerow(
            {
                "rec_id": "R2",
                "ext_id": "N/A",
                "crd": "999999999",
                "org": "TBD",
                "sal": "",
                "fname": "",
                "mname": "",
                "lname": "",
                "sfx": "",
                "cred": "",
                "title": "",
                "team": "",
                "roster": "",
                "s1": "",
                "s2": "",
                "city": "",
                "st": "",
                "zip": "",
                "cntry": "",
                "phone": "555-0000",
                "fax": "badphone",
                "email": "bad@example.com",
                "web": "http://none.com",
                "social": "not-a-social",
                "ship_s1": "350 5th Ave",
                "ship_city": "New York",
                "ship_st": "NY",
                "ship_zip": "10118",
                "ship_cntry": "US",
            }
        )

    # 1. Default overwrite mode + audit + matching keys + geocoding + clear_placeholders_keep_raw
    opts = StandardizationOptions(
        include_audit_cols=True,
        include_matching_keys=True,
        enable_geocoding=True,
        id_pad_width=6,
    )
    prev = preview_standardize_source(csv_in, mapping, opts, limit=1)
    assert prev["preview_count"] == 1 and prev["cells_changed"] > 0

    out_over = tmp_path / "contacts_over.csv"
    summary = standardize_tabular_file(csv_in, out_over, mapping, opts)
    assert summary["input_rows"] == 2 and summary["output_rows"] == 2
    with out_over.open("r", encoding="utf-8", newline="") as f:
        out_rows = list(csv.DictReader(f))
    r1, r2 = out_rows
    assert r1["ext_id"] == "000042"
    assert r1["crd"] == "148763"
    assert r1["org"] == "ACME HOLDINGS INC"
    assert r1["fname"] == "BOB" and r1["sfx"] == "JR" and r1["cred"] == "MD"
    assert r1["s1"] == "350 5TH AVE" and r1["s2"] == "STE 400"
    assert r1["st"] == "NY" and r1["cntry"] == "UNITED STATES"
    assert r1["phone"] == "+12125552368"  # NO formula prefix when csv_formula_guard=False
    assert r1["email"] == "bobsmith@gmail.com"
    assert r1["web"] == "https://acme.com"
    assert r1["social"] == "https://x.com/acme"
    assert r1["ship_cntry"] == "GB"  # isolated shipping group stayed GB!
    assert r1["primary_valid"] == "True"
    assert r1["primary_company_compact_key"] != ""
    assert r1["primary_latitude"] != ""
    # Placeholder policy clears N/A, TBD, example.com, none.com, 555-0000, keeps non-placeholder invalid "badphone"/"not-a-social"
    assert r2["ext_id"] == "" and r2["org"] == "" and r2["email"] == "" and r2["web"] == ""
    assert r2["fax"] == "badphone" and r2["social"] == "not-a-social"

    # 2. append_std + clear_all_invalid + csv_formula_guard + title case + nickname root + strip extensions + email opts
    opts2 = StandardizationOptions(
        column_mode="append_std",
        invalid_policy="clear_all_invalid",
        csv_formula_guard=True,
        address_case="title",
        company_case="title",
        company_style="brand_stem",
        person_case="title",
        use_nickname_root=True,
        phone_format="rfc3966",
        extension_mode="strip",
        split_secondary_unit=False,
        email_strip_subaddress=False,
        email_canonicalize_gmail_dots=False,
        email_heal_typos=False,
    )
    out_app = tmp_path / "contacts_app.csv"
    standardize_tabular_file(csv_in, out_app, mapping, opts2)
    with out_app.open("r", encoding="utf-8", newline="") as f:
        app_rows = list(csv.DictReader(f))
    assert app_rows[0]["fname_std"] == "Robert"
    assert app_rows[0]["s1_std"] == "350 5th Ave Ste 400"
    assert app_rows[0]["s2_std"] == ""
    assert app_rows[0]["fax_std"] == "tel:+1-212-555-9999"
    assert app_rows[0]["phone_std"] == "tel:+1-212-555-2368"
    assert app_rows[0]["email_std"] == "bob.smith+crm@gmial.com"
    assert app_rows[1]["fax_std"] == ""  # clear_all_invalid cleared badphone

    # 3. overwrite_keep_raw + keep_all_raw + phone formats (national, international, masked_partial, masked_full) + disable cross-healing
    for ph_fmt, expected_prefix in (
        ("national", "(212)"),
        ("international", "+1 212"),
        ("masked_partial", "+1******2368"),
        ("masked_full", "[REDACTED PHONE]"),
    ):
        opts_ph = StandardizationOptions(
            column_mode="overwrite_keep_raw",
            invalid_policy="keep_all_raw",
            enable_cross_healing=False,
            phone_format=ph_fmt,
            person_format="last_comma_first",
        )
        rows_out, _ = standardize_row_with_config(
            {
                "phone": "212-555-2368",
                "org": "TBD",
                "person": "Bob J. Smith, Jr.",
                "s1": "350 5th Ave",
                "city": "New York",
                "st": "NY",
                "zip": "10118",
                "cntry": "US",
            },
            MappingConfig(
                mappings=[
                    ColumnMapping("phone", FieldRole.PHONE.value),
                    ColumnMapping("org", FieldRole.ORGANIZATION.value),
                    ColumnMapping("person", FieldRole.PERSON_NAME.value),
                    ColumnMapping("s1", FieldRole.STREET1.value),
                    ColumnMapping("city", FieldRole.CITY.value),
                    ColumnMapping("st", FieldRole.STATE.value),
                    ColumnMapping("zip", FieldRole.POSTAL_CODE.value),
                    ColumnMapping("cntry", FieldRole.COUNTRY.value),
                ]
            ),
            opts_ph,
        )
        assert rows_out[0]["phone"].startswith(expected_prefix)
        assert rows_out[0]["phone_raw"] == "212-555-2368"
        assert rows_out[0]["org"] == "TBD"  # keep_all_raw keeps TBD
        assert rows_out[0]["person"] == "SMITH, BOB J, JR"


def test_cross_healing_rescue_infer_and_couple_split_modes(tmp_path: Path) -> None:
    map_full = MappingConfig(
        mappings=[
            ColumnMapping("org", FieldRole.ORGANIZATION.value),
            ColumnMapping("person", FieldRole.PERSON_NAME.value),
            ColumnMapping("s1", FieldRole.STREET1.value),
            ColumnMapping("phone", FieldRole.PHONE.value),
            ColumnMapping("email", FieldRole.EMAIL.value),
            ColumnMapping("web", FieldRole.WEBSITE.value),
        ]
    )

    raw_row = {
        "org": "",
        "person": "",
        "s1": "100 Main St www.stripe.com Tel: 415-555-2671",
        "phone": "",
        "email": "Jane Doe <jane@stripe.com>",
        "web": "",
    }

    # Rescue ON, infer_blank_fields OFF -> rescues phone/web/email (email comes from text or person; here email already present),
    # does NOT fill blank org from domain or blank person from email display name!
    r_no_infer, _ = standardize_row_with_config(
        raw_row,
        map_full,
        StandardizationOptions(rescue_misplaced_fields=True, infer_blank_fields=False),
    )
    assert r_no_infer[0]["phone"] == "+14155552671"
    assert r_no_infer[0]["web"] == "https://stripe.com"
    assert r_no_infer[0]["org"] == ""
    assert r_no_infer[0]["person"] == ""

    # infer_blank_fields ON -> populates blank org & person!
    r_infer, _ = standardize_row_with_config(
        raw_row,
        map_full,
        StandardizationOptions(rescue_misplaced_fields=True, infer_blank_fields=True),
    )
    assert r_infer[0]["org"] == "STRIPE"
    assert r_infer[0]["person"] == "JANE DOE"

    # rescue_misplaced_fields OFF -> does not populate empty phone/web/email/org from other fields
    r_no_rescue, _ = standardize_row_with_config(
        {
            "org": "",
            "person": "Augnition Global Investors LLC",
            "s1": "100 Main St www.stripe.com Tel: 415-555-2671 jane@stripe.com",
            "phone": "",
            "email": "",
            "web": "",
        },
        map_full,
        StandardizationOptions(rescue_misplaced_fields=False, infer_blank_fields=False),
    )
    assert r_no_rescue[0]["phone"] == ""
    assert r_no_rescue[0]["email"] == ""
    assert r_no_rescue[0]["web"] == ""
    assert r_no_rescue[0]["org"] == ""

    # rescue_misplaced_fields=False when no rescue actions occurred; rescue_misplaced_fields=True rescuing blank email;
    # standalone (cross-healing OFF) with blank person; append_secondary_col on org-only mapping
    r_clean_no_rescue, _ = standardize_row_with_config(
        {"org": "Acme LLC", "person": "Jane Doe", "s1": "100 Main St", "phone": "", "email": "", "web": ""},
        map_full,
        StandardizationOptions(rescue_misplaced_fields=False),
    )
    assert r_clean_no_rescue[0]["org"] == "ACME LLC"

    r_rescued_email, _ = standardize_row_with_config(
        {"org": "Acme LLC", "person": "", "s1": "100 Main St jane@acme.com", "phone": "", "email": "", "web": ""},
        map_full,
        StandardizationOptions(rescue_misplaced_fields=True),
    )
    assert r_rescued_email[0]["email"] == "jane@acme.com"

    r_standalone_empty_p, _ = standardize_row_with_config(
        {"org": "Acme LLC", "person": "", "s1": "", "phone": "", "email": "", "web": ""},
        map_full,
        StandardizationOptions(enable_cross_healing=False),
    )
    assert r_standalone_empty_p[0]["org"] == "ACME LLC"

    r_sec_org, _ = standardize_row_with_config(
        {"org": "Acme LLC"},
        MappingConfig([ColumnMapping("org", FieldRole.ORGANIZATION.value)]),
        StandardizationOptions(couple_split_mode="append_secondary_col"),
    )
    assert r_sec_org[0]["org"] == "ACME LLC"

    # Couple split modes: append_secondary_col & split_rows (full person and component columns)
    map_couple = MappingConfig(
        mappings=[
            ColumnMapping("person", FieldRole.PERSON_NAME.value),
            ColumnMapping("email", FieldRole.EMAIL.value),
        ]
    )
    row_sec, _ = standardize_row_with_config(
        {"person": "John & Jane Smith", "email": "smith@acme.com"},
        map_couple,
        StandardizationOptions(couple_split_mode="append_secondary_col"),
    )
    assert row_sec[0]["person"] == "JOHN SMITH" and row_sec[0]["person_secondary"] == "JANE SMITH"

    rows_split, _ = standardize_row_with_config(
        {"person": "John & Jane Smith", "email": "smith@acme.com"},
        map_couple,
        StandardizationOptions(couple_split_mode="split_rows", column_mode="append_std"),
    )
    assert len(rows_split) == 2
    assert [r["person_std"] for r in rows_split] == ["JOHN SMITH", "JANE SMITH"]

    # Split components with append_secondary_col and split_rows + standalone last, first fallback
    map_comp = MappingConfig(
        mappings=[
            ColumnMapping("fn", FieldRole.FIRST_NAME.value),
            ColumnMapping("ln", FieldRole.LAST_NAME.value),
            ColumnMapping("crd", FieldRole.CRD.value),
        ]
    )
    comp_sec, _ = standardize_row_with_config(
        {"fn": "John & Jane", "ln": "Smith", "crd": "12345"},
        map_comp,
        StandardizationOptions(
            couple_split_mode="append_secondary_col",
            enable_cross_healing=False,
            include_audit_cols=True,
            include_matching_keys=True,
        ),
    )
    assert comp_sec[0]["primary_secondary_person"] == "JANE SMITH"

    comp_split, _ = standardize_row_with_config(
        {"fn": "John & Jane", "ln": "Smith", "crd": "12345"},
        map_comp,
        StandardizationOptions(couple_split_mode="split_rows", enable_cross_healing=False),
    )
    assert len(comp_split) == 2
    assert [r["fn"] for r in comp_split] == ["JOHN", "JANE"]

    # Person without last name + credentials-only assembly + invalid geocoding + formula guard on JSON
    rows_misc, _ = standardize_row_with_config(
        {"fn": "", "ln": "", "cred": "CFA", "s1": "bad", "phone": ""},
        MappingConfig(
            mappings=[
                ColumnMapping("fn", FieldRole.FIRST_NAME.value),
                ColumnMapping("ln", FieldRole.LAST_NAME.value),
                ColumnMapping("cred", FieldRole.CREDENTIALS.value),
                ColumnMapping("s1", FieldRole.STREET1.value),
                ColumnMapping("phone", FieldRole.PHONE.value),
            ]
        ),
        StandardizationOptions(person_format="last_comma_first", include_audit_cols=True, enable_geocoding=True),
        is_delimited_export=True,
    )
    assert len(rows_misc) == 1

    # Non-contact only group (no contact pillars) + unchanged second row + JSON file preview/export
    json_in = tmp_path / "ids.json"
    json_in.write_text(
        json.dumps([{"crd": "00123", "ext": "99"}, {"crd": "123", "ext": "00099"}]),
        encoding="utf-8",
    )
    id_map = MappingConfig(
        mappings=[
            ColumnMapping("crd", FieldRole.CRD.value),
            ColumnMapping("ext", FieldRole.EXTERNAL_ID.value),
        ]
    )
    out_json = tmp_path / "ids_out.json"
    res = standardize_tabular_file(
        json_in,
        out_json,
        id_map,
        StandardizationOptions(include_audit_cols=True, id_pad_width=5),
    )
    assert res["output_rows"] == 2 and res["modified_rows"] == 1
    assert json.loads(out_json.read_text(encoding="utf-8"))[0]["ext"] == "00099"

    # Regression checks:
    # - rescue_misplaced_fields clears pure phone in Street1 and org in Person (full & component roles)
    # - split_secondary_unit=False clears folded Street2 instead of flagging it invalid
    # - N/A placeholder in Country/Salutation is isolated from standardizer logic
    # - couple_split_mode="split_rows" updates per-row matching keys & preserves untouched None values
    r_res_clean, a_res_clean = standardize_row_with_config(
        {
            "org": "",
            "person": "Acme Holdings LLC",
            "s1": "212-555-2368",
            "phone": "",
            "raw_null": None,
        },
        MappingConfig(
            [
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("person", FieldRole.PERSON_NAME.value),
                ColumnMapping("s1", FieldRole.STREET1.value),
                ColumnMapping("phone", FieldRole.PHONE.value),
            ]
        ),
        StandardizationOptions(),
    )
    assert r_res_clean[0]["phone"] == "+12125552368" and r_res_clean[0]["s1"] == ""
    assert r_res_clean[0]["org"] == "ACME HOLDINGS LLC" and r_res_clean[0]["person"] == ""
    assert r_res_clean[0]["raw_null"] is None
    assert a_res_clean.cell_changes["s1"] == "rescued"
    assert a_res_clean.cell_changes["person"] == "rescued"

    r_comp_org, a_comp_org = standardize_row_with_config(
        {"org": "", "fn": "Acme Holdings", "ln": "LLC"},
        MappingConfig(
            [
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("fn", FieldRole.FIRST_NAME.value),
                ColumnMapping("ln", FieldRole.LAST_NAME.value),
            ]
        ),
        StandardizationOptions(),
    )
    assert r_comp_org[0]["org"] == "ACME HOLDINGS LLC"
    assert r_comp_org[0]["fn"] == "" and r_comp_org[0]["ln"] == ""
    assert a_comp_org.cell_changes["fn"] == "rescued"

    r_fold, a_fold = standardize_row_with_config(
        {"s1": "350 Fifth Ave", "s2": "Ste 400", "city": "New York", "st": "NY", "zip": "10118", "cntry": "N/A", "sal": "N/A", "fn": "Bob", "ln": "Smith"},
        MappingConfig(
            [
                ColumnMapping("s1", FieldRole.STREET1.value),
                ColumnMapping("s2", FieldRole.STREET2.value),
                ColumnMapping("city", FieldRole.CITY.value),
                ColumnMapping("st", FieldRole.STATE.value),
                ColumnMapping("zip", FieldRole.POSTAL_CODE.value),
                ColumnMapping("cntry", FieldRole.COUNTRY.value),
                ColumnMapping("sal", FieldRole.SALUTATION.value),
                ColumnMapping("fn", FieldRole.FIRST_NAME.value),
                ColumnMapping("ln", FieldRole.LAST_NAME.value),
            ]
        ),
        StandardizationOptions(split_secondary_unit=False),
    )
    assert r_fold[0]["s1"] == "350 5TH AVE STE 400" and r_fold[0]["s2"] == ""
    assert a_fold.cell_changes["s2"] == "modified"
    assert r_fold[0]["cntry"] == "" and r_fold[0]["sal"] == "" and r_fold[0]["fn"] == "BOB"

    r_split_keys, _ = standardize_row_with_config(
        {"person": "John & Jane Smith"},
        MappingConfig([ColumnMapping("person", FieldRole.PERSON_NAME.value)]),
        StandardizationOptions(couple_split_mode="split_rows", include_matching_keys=True),
    )
    assert [r["primary_person_root_key"] for r in r_split_keys] == ["SMITH|JOHN", "SMITH|JANE"]

    # Pass-3 regressions: NaN inputs, integer-float phone, int RECORD_ID passthrough, and strict RFC-8259 preview JSON
    r_nan, _ = standardize_row_with_config(
        {"id": 101, "ext": float("nan"), "person": float("nan"), "phone": 2125552368.0},
        MappingConfig(
            [
                ColumnMapping("id", FieldRole.RECORD_ID.value),
                ColumnMapping("ext", FieldRole.EXTERNAL_ID.value),
                ColumnMapping("person", FieldRole.PERSON_NAME.value),
                ColumnMapping("phone", FieldRole.PHONE.value),
            ]
        ),
        StandardizationOptions(),
    )
    assert r_nan[0]["id"] == 101 and isinstance(r_nan[0]["id"], int)
    assert r_nan[0]["ext"] == "" and r_nan[0]["person"] == ""
    assert r_nan[0]["phone"] == "+12125552368"

    pq_dirty = tmp_path / "preview_dirty.parquet"
    pq.write_table(
        pa.table(
            {
                "id": [1],
                "org": ["Acme Corp"],
                "aum": [float("nan")],
                "inf_v": [float("inf")],
                "as_of": [datetime.date(2026, 2, 1)],
                "raw_b": [b"\x80\x81"],
            }
        ),
        pq_dirty,
    )
    prev_dirty = preview_standardize_source(
        pq_dirty,
        MappingConfig([ColumnMapping("org", FieldRole.ORGANIZATION.value)]),
        StandardizationOptions(),
    )
    strict_txt = json.dumps(prev_dirty, allow_nan=False)
    assert "NaN" not in strict_txt and prev_dirty["rows"][0]["before"]["raw_b"] == "8081"

    # Pass-4 regressions:
    # 1) Standalone Country column formatted cleanly without street1; invalid country cleared under clear_all_invalid
    r_cntry_ok, a_cntry_ok = standardize_row_with_config(
        {"org": "Barclays PLC", "phone": "020 7116 1000", "mobile": "07710 123456", "cntry": "United Kingdom"},
        MappingConfig(
            [
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("phone", FieldRole.PHONE.value),
                ColumnMapping("mobile", FieldRole.PHONE.value),
                ColumnMapping("cntry", FieldRole.COUNTRY.value),
            ]
        ),
        StandardizationOptions(country_format="iso2", invalid_policy="clear_all_invalid"),
    )
    assert r_cntry_ok[0]["cntry"] == "GB"
    assert r_cntry_ok[0]["phone"] == "+442071161000" and r_cntry_ok[0]["mobile"] == "+447710123456"
    assert a_cntry_ok.cell_changes["cntry"] == "modified"

    # 2) Valid phone country propagates across units in a group without Country or Street1, while invalid Country is cleared
    r_cntry_ph, _ = standardize_row_with_config(
        {"phone": "+44 20 7116 1000", "mobile": "07710 123456", "cntry": "AtlantisNotACountry"},
        MappingConfig(
            [
                ColumnMapping("phone", FieldRole.PHONE.value),
                ColumnMapping("mobile", FieldRole.PHONE.value),
                ColumnMapping("cntry", FieldRole.COUNTRY.value),
            ]
        ),
        StandardizationOptions(invalid_policy="clear_all_invalid"),
    )
    assert r_cntry_ph[0]["phone"] == "+442071161000" and r_cntry_ph[0]["mobile"] == "+447710123456"
    assert r_cntry_ph[0]["cntry"] == ""

    # 3) Rescued email honors formatting options + couple split_rows updates per-spouse audit _key
    r_split_audit, _ = standardize_row_with_config(
        {"org": "Acme LLC", "s1": "100 Main St Bob.Smith+tag@gmial.com", "email": "", "person": "John & Jane Smith"},
        MappingConfig(
            [
                ColumnMapping("org", FieldRole.ORGANIZATION.value),
                ColumnMapping("s1", FieldRole.STREET1.value),
                ColumnMapping("email", FieldRole.EMAIL.value),
                ColumnMapping("person", FieldRole.PERSON_NAME.value),
            ]
        ),
        StandardizationOptions(
            couple_split_mode="split_rows",
            include_audit_cols=True,
            email_strip_subaddress=False,
        ),
    )
    assert len(r_split_audit) == 2
    assert r_split_audit[0]["email"] == "bobsmith+tag@gmail.com"
    assert "SMITH|JOHN" in r_split_audit[0]["primary_key"]
    assert "SMITH|JANE" in r_split_audit[1]["primary_key"] and "SMITH|JOHN" not in r_split_audit[1]["primary_key"]

    # Pass-6: Stale preset mapping with absent 'Fax' column does not emit phantom 'Fax_std' or 'Fax' keys
    stale_jl = tmp_path / "stale_preset.jsonl"
    stale_jl.write_text('{"id": 1, "org": "acme llc"}\n', encoding="utf-8")
    stale_cfg = MappingConfig(
        [
            ColumnMapping("id", FieldRole.RECORD_ID.value),
            ColumnMapping("org", FieldRole.ORGANIZATION.value),
            ColumnMapping("Fax", FieldRole.FAX.value),
        ]
    )
    stale_prev = preview_standardize_source(
        stale_jl, stale_cfg, StandardizationOptions(column_mode="append_std")
    )
    assert stale_prev["output_columns"] == ["id", "org", "id_std", "org_std"]
    stale_out = tmp_path / "stale_preset_out.jsonl"
    standardize_tabular_file(stale_jl, stale_out, stale_cfg, StandardizationOptions())
    assert json.loads(stale_out.read_text(encoding="utf-8").strip()) == {"id": 1, "org": "ACME LLC"}

    # Pass-7 regressions:
    # 1) Split person component redistribution clears vacated component cell & does not double-count invalid
    r_shift, a_shift = standardize_row_with_config(
        {"Sal": "N/A", "First": "Bob", "Mid": "", "Last": "Smith", "Sfx": "CFA", "Cred": ""},
        MappingConfig(
            [
                ColumnMapping("Sal", FieldRole.SALUTATION.value),
                ColumnMapping("First", FieldRole.FIRST_NAME.value),
                ColumnMapping("Mid", FieldRole.MIDDLE_NAME.value),
                ColumnMapping("Last", FieldRole.LAST_NAME.value),
                ColumnMapping("Sfx", FieldRole.GENERATIONAL_SUFFIX.value),
                ColumnMapping("Cred", FieldRole.CREDENTIALS.value),
            ]
        ),
        StandardizationOptions(),
    )
    assert r_shift[0] == {"Sal": "", "First": "BOB", "Mid": "", "Last": "SMITH", "Sfx": "", "Cred": "CFA"}
    assert a_shift.invalid_cells == 0 and a_shift.cell_changes["Sfx"] == "modified"

    # 2) Street2="N/A" cleared via placeholder policy while valid Street1 keeps address valid
    r_s2_ph, a_s2_ph = standardize_row_with_config(
        {"s1": "350 Fifth Ave", "s2": "N/A", "city": "New York", "st": "NY", "zip": "10118"},
        MappingConfig(
            [
                ColumnMapping("s1", FieldRole.STREET1.value),
                ColumnMapping("s2", FieldRole.STREET2.value),
                ColumnMapping("city", FieldRole.CITY.value),
                ColumnMapping("st", FieldRole.STATE.value),
                ColumnMapping("zip", FieldRole.POSTAL_CODE.value),
            ]
        ),
        StandardizationOptions(),
    )
    assert r_s2_ph[0]["s2"] == "" and a_s2_ph.cell_changes["s2"] == "cleared"

    # 3) Rescued role/webmail email clears source Person / split First / Org / Street1 without false-clearing unrelated Street1
    resc_cfg = MappingConfig(
        [
            ColumnMapping("org", FieldRole.ORGANIZATION.value),
            ColumnMapping("person", FieldRole.PERSON_NAME.value),
            ColumnMapping("s1", FieldRole.STREET1.value),
            ColumnMapping("email", FieldRole.EMAIL.value),
        ]
    )
    r_p_em, a_p_em = standardize_row_with_config(
        {"org": "", "person": "info@acme.com", "s1": "???", "email": ""},
        resc_cfg,
        StandardizationOptions(infer_blank_fields=False),
    )
    assert r_p_em[0]["email"] == "info@acme.com" and r_p_em[0]["person"] == ""
    assert a_p_em.cell_changes["person"] == "rescued"
    assert r_p_em[0]["s1"] == "???" and a_p_em.cell_changes["s1"] == "invalid"

    r_o_em, a_o_em = standardize_row_with_config(
        {"org": "bob@gmail.com", "person": "", "s1": "???", "email": ""},
        resc_cfg,
        StandardizationOptions(infer_blank_fields=False),
    )
    assert r_o_em[0]["email"] == "bob@gmail.com" and r_o_em[0]["org"] == ""
    assert a_o_em.cell_changes["org"] == "rescued"
    assert r_o_em[0]["s1"] == "???"

    r_s_em, a_s_em = standardize_row_with_config(
        {"org": "", "person": "", "s1": "info@acme.com", "email": ""},
        resc_cfg,
        StandardizationOptions(infer_blank_fields=False),
    )
    assert r_s_em[0]["email"] == "info@acme.com" and r_s_em[0]["s1"] == ""
    assert a_s_em.cell_changes["s1"] == "rescued"

    r_comp_em, a_comp_em = standardize_row_with_config(
        {"fn": "info@acme.com", "ln": "", "email": ""},
        MappingConfig(
            [
                ColumnMapping("fn", FieldRole.FIRST_NAME.value),
                ColumnMapping("ln", FieldRole.LAST_NAME.value),
                ColumnMapping("email", FieldRole.EMAIL.value),
            ]
        ),
        StandardizationOptions(infer_blank_fields=False),
    )
    assert r_comp_em[0]["email"] == "info@acme.com" and r_comp_em[0]["fn"] == ""
    assert a_comp_em.cell_changes["fn"] == "rescued"
