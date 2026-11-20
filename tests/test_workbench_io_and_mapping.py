"""Tests for multi-format file I/O round-tripping, 300+ column auto-detection, and mapping presets."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import sys

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from entity_standardizer.workbench.io_formats import (
    FileFormatSpec,
    SupportedFormat,
    _cell_to_json_scalar,
    cell_to_input_text,
    close_row_iter,
    detect_file_format,
    inspect_tabular_source,
    iter_tabular_rows,
    write_tabular_output,
    write_xlsx_sheets,
)
from entity_standardizer.workbench.mapping import (
    ColumnMapping,
    FieldRole,
    MappingConfig,
    PresetStore,
    auto_detect_mappings,
)


def test_delimited_json_jsonl_xlsx_and_parquet_round_trips(tmp_path: Path, monkeypatch) -> None:
    rows = [
        {"id": 1, "name": "Acme LLC", "amount": 42.5},
        {"id": 2, "name": "Beta Corp", "amount": 100.0},
    ]
    cols = ["id", "name", "amount"]

    # 1. CSV with UTF-8 BOM + CRLF preservation
    csv_in = tmp_path / "bom_crlf.csv"
    csv_in.write_bytes(b"\xef\xbb\xbfid,name,amount\r\n1,Acme LLC,42.5\r\n2,Beta Corp,100.0\r\n")
    csv_spec = detect_file_format(csv_in)
    assert csv_spec.format == SupportedFormat.CSV.value
    assert csv_spec.has_bom is True
    assert csv_spec.lineterminator == "\r\n"
    assert csv_spec.extension_for_export() == ".csv"
    assert "text/csv" in csv_spec.media_type()

    csv_out = tmp_path / "out_bom.csv"
    c_cols, c_iter = iter_tabular_rows(csv_in, csv_spec)
    assert write_tabular_output(csv_out, c_cols, c_iter, csv_spec) == 2
    raw_bytes = csv_out.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw_bytes

    # 2. TSV and PSV and sniffed custom .txt (pipe and empty fallback)
    tsv_in = tmp_path / "data.tsv"
    tsv_in.write_text("id\tname\n1\tAcme\n", encoding="utf-8")
    assert detect_file_format(tsv_in).delimiter == "\t"

    psv_in = tmp_path / "data.psv"
    psv_in.write_text("id|name\n1|Acme\n", encoding="utf-8")
    assert detect_file_format(psv_in).delimiter == "|"

    txt_in = tmp_path / "pipe.txt"
    txt_in.write_text("id|name|city\n1|Acme|Austin\n", encoding="utf-8")
    txt_spec = detect_file_format(txt_in)
    assert txt_spec.format == SupportedFormat.DELIMITED.value and txt_spec.delimiter == "|"
    assert txt_spec.extension_for_export() == ".txt"

    txt_override = detect_file_format(txt_in, delimiter_override="\\t")
    assert txt_override.delimiter == "\t"

    empty_txt = tmp_path / "empty.txt"
    empty_txt.write_text("", encoding="utf-8")
    assert detect_file_format(empty_txt).delimiter == ","

    # 3. JSON array and wrapped JSON dict
    json_arr = tmp_path / "arr.json"
    json_arr.write_text(json.dumps(rows), encoding="utf-8")
    arr_spec = detect_file_format(json_arr)
    assert arr_spec.format == SupportedFormat.JSON.value and arr_spec.json_wrapper_key is None
    arr_out = tmp_path / "arr_out.json"
    j_cols, j_iter = iter_tabular_rows(json_arr, arr_spec)
    assert write_tabular_output(arr_out, j_cols, j_iter, arr_spec) == 2
    assert isinstance(json.loads(arr_out.read_text(encoding="utf-8")), list)

    json_wrap = tmp_path / "wrap.json"
    json_wrap.write_text(json.dumps({"meta": {"source": "sf"}, "records": rows}), encoding="utf-8")
    wrap_spec = detect_file_format(json_wrap)
    assert wrap_spec.json_wrapper_key == "records"
    assert wrap_spec.json_envelope == {"meta": {"source": "sf"}}
    wrap_out = tmp_path / "wrap_out.json"
    w_cols, w_iter = iter_tabular_rows(json_wrap, wrap_spec)
    write_tabular_output(wrap_out, w_cols, w_iter, wrap_spec)
    rebuilt_wrap = json.loads(wrap_out.read_text(encoding="utf-8"))
    assert rebuilt_wrap["meta"] == {"source": "sf"} and "records" in rebuilt_wrap

    ndjson_in = tmp_path / "events.ndjson"
    ndjson_in.write_text('{"id": 1}\n', encoding="utf-8")
    assert detect_file_format(ndjson_in).extension_for_export() == ".ndjson"

    bad_json = tmp_path / "bad.json"
    bad_json.write_text(json.dumps({"a": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON file must be"):
        detect_file_format(bad_json)

    scalar_json = tmp_path / "scalar.json"
    scalar_json.write_text("42", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON file must be"):
        detect_file_format(scalar_json)

    # 4. JSONL with leading and middle blank lines + whitespace-only JSONL
    jsonl_in = tmp_path / "stream.jsonl"
    jsonl_in.write_text('\n{"id": 1, "name": "Acme"}\n\n{"id": 2, "name": "Beta"}\n', encoding="utf-8")
    jl_spec = detect_file_format(jsonl_in)
    assert jl_spec.format == SupportedFormat.JSONL.value
    jl_out = tmp_path / "stream_out.jsonl"
    jl_cols, jl_iter = iter_tabular_rows(jsonl_in, jl_spec)
    assert write_tabular_output(jl_out, jl_cols, jl_iter, jl_spec) == 2
    assert len(jl_out.read_text(encoding="utf-8").strip().splitlines()) == 2

    empty_jl = tmp_path / "empty.jsonl"
    empty_jl.write_text("\n\n", encoding="utf-8")
    ej_cols, ej_iter = iter_tabular_rows(empty_jl, detect_file_format(empty_jl))
    assert ej_cols == [] and list(ej_iter) == []

    assert _cell_to_json_scalar(None) == ""
    assert _cell_to_json_scalar(datetime.date(2026, 1, 2)) == "2026-01-02"

    # 5. Multi-sheet XLSX preserving untouched sibling sheet + empty XLSX sheet + write_xlsx_sheets
    xlsx_in = tmp_path / "multi.xlsx"
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Contacts"
    ws1.append(["id", "name"])
    ws1.append([1, "Acme"])
    ws2 = wb.create_sheet("Notes")
    ws2.append(["keep_me"])
    ws2.append(["sibling_intact"])
    wb.create_sheet("EmptySheet")
    wb.save(xlsx_in)
    wb.close()

    xlsx_spec = detect_file_format(xlsx_in, sheet_name="Contacts")
    assert xlsx_spec.sheet_name == "Contacts"
    info_xlsx = inspect_tabular_source(xlsx_in, sheet_name="Contacts")
    assert info_xlsx["sheet_names"] == ["Contacts", "Notes", "EmptySheet"]
    assert info_xlsx["total_rows"] == 1

    xlsx_out = tmp_path / "multi_out.xlsx"
    x_cols, x_iter = iter_tabular_rows(xlsx_in, xlsx_spec)
    write_tabular_output(
        xlsx_out,
        x_cols,
        [{"id": 1, "name": "ACME"}],
        xlsx_spec,
        template_xlsx_path=xlsx_in,
    )
    wb_chk = openpyxl.load_workbook(xlsx_out)
    assert wb_chk.sheetnames == ["Contacts", "Notes", "EmptySheet"]
    assert wb_chk["Notes"].cell(2, 1).value == "sibling_intact"
    wb_chk.close()

    # Empty sheet + empty header write_only XLSX branch
    empty_xlsx_info = inspect_tabular_source(xlsx_in, sheet_name="EmptySheet")
    assert empty_xlsx_info["columns"] == [] and empty_xlsx_info["total_rows"] == 0

    wb_blank_template = tmp_path / "blank_tpl.xlsx"
    wb_b = openpyxl.Workbook()
    wb_b.save(wb_blank_template)
    wb_b.close()
    write_tabular_output(
        tmp_path / "blank_tpl_out.xlsx",
        ["a"],
        [{"a": "x"}],
        FileFormatSpec(format="xlsx", sheet_name="Sheet"),
        template_xlsx_path=wb_blank_template,
    )

    write_xlsx_sheets(tmp_path / "bundle.xlsx", {"SheetA": (cols, rows)})
    assert (tmp_path / "bundle.xlsx").is_file()

    # Non-template write_tabular_output for xlsx
    fresh_xlsx = tmp_path / "fresh.xlsx"
    assert (
        write_tabular_output(
            fresh_xlsx,
            ["id", "name"],
            [{"id": 1, "name": "A"}],
            FileFormatSpec(format="xlsx", sheet_name="Out"),
        )
        == 1
    )
    assert fresh_xlsx.is_file()

    # 6. Parquet preserving untouched int64 column & coercing modified column + empty Parquet + large threshold
    pq_in = tmp_path / "data.parquet"
    tbl = pa.table(
        {
            "id": pa.array([101, 102], type=pa.int64()),
            "phone": pa.array(["212-555-0100", "415-555-0199"], type=pa.string()),
            "nan_col": pa.array([float("nan"), 3.5], type=pa.float64()),
            "code_num": pa.array([1, 2], type=pa.int64()),
        }
    )
    pq.write_table(tbl, pq_in)
    pq_info = inspect_tabular_source(pq_in, sample_limit=1)
    assert pq_info["total_rows"] == 2
    assert pq_info["sample_rows"][0]["nan_col"] == ""

    pq_spec = detect_file_format(pq_in)
    pq_out = tmp_path / "data_out.parquet"
    pq_cols, pq_iter = iter_tabular_rows(pq_in, pq_spec)
    modified_pq = []
    for r in pq_iter:
        r["code_num"] = "STR_VAL"  # trigger fallback from int64 -> string
        r["extra"] = "added"
        modified_pq.append(r)
    write_tabular_output(
        pq_out,
        pq_cols + ["extra"],
        modified_pq,
        pq_spec,
        source_parquet_path=pq_in,
    )
    out_tbl = pq.read_table(pq_out)
    assert pa.types.is_int64(out_tbl.schema.field("id").type)
    assert out_tbl.column("extra").to_pylist() == ["added", "added"]

    # Mixed-type without orig_schema + nullable int64 preservation in Parquet
    mixed_pq = tmp_path / "mixed.parquet"
    assert (
        write_tabular_output(
            mixed_pq,
            ["val", "opt_int"],
            [{"val": 42, "opt_int": None}, {"val": "STR_VAL", "opt_int": 7}],
            pq_spec,
        )
        == 2
    )
    mixed_tbl = pq.read_table(mixed_pq)
    assert pa.types.is_string(mixed_tbl.schema.field("val").type)
    assert pa.types.is_int64(mixed_tbl.schema.field("opt_int").type)

    # Empty parquet write with and without source schema
    write_tabular_output(
        tmp_path / "empty_pq.parquet",
        ["id", "new_col"],
        [],
        pq_spec,
        source_parquet_path=pq_in,
    )
    assert pq.read_table(tmp_path / "empty_pq.parquet").num_rows == 0

    # inspect_tabular_source exceeding count_threshold_bytes returns total_rows=None & FileFormatSpec.from_dict
    large_info = inspect_tabular_source(csv_in, sample_limit=1, count_threshold_bytes=1)
    assert large_info["total_rows"] is None
    rebuilt_spec = FileFormatSpec.from_dict(large_info["format_spec"])
    assert rebuilt_spec.has_bom is True

    # 7. Unstarted iterator close on Windows, cp1252 CSV, duplicate/blank headers, atomic in-place write,
    # and corrupt/non-object file validations with zero leaked handles
    unstarted_csv = tmp_path / "unstarted.csv"
    unstarted_csv.write_text("org,org,\nAcme,Beta,Gamma\n", encoding="utf-8")
    us_spec = detect_file_format(unstarted_csv)
    us_cols, us_it = iter_tabular_rows(unstarted_csv, us_spec)
    assert us_cols == ["org", "org_2", "col_3"]
    close_row_iter(us_it)
    close_row_iter(us_it)  # idempotent second close
    unstarted_csv.unlink()  # must not raise PermissionError on Windows!

    cp_csv = tmp_path / "cp1252.csv"
    cp_csv.write_bytes(b"id,org\n1,Caf\xe9 LLC\n")
    cp_spec = detect_file_format(cp_csv)
    assert cp_spec.encoding == "cp1252"
    cp_cols, cp_it = iter_tabular_rows(cp_csv, cp_spec)
    cp_rows = list(cp_it)
    assert cp_rows[0]["org"] == "Café LLC"
    # Atomic in-place write (output_path == input_path)
    assert write_tabular_output(cp_csv, cp_cols, cp_rows, cp_spec) == 1
    assert "Café LLC" in cp_csv.read_text(encoding="cp1252")

    # Corrupt containers raise ValueError cleanly with closed handles
    bad_json_list = tmp_path / "list_ints.json"
    bad_json_list.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="array of JSON objects"):
        detect_file_format(bad_json_list)

    bad_wrap_list = tmp_path / "wrap_ints.json"
    bad_wrap_list.write_text(json.dumps({"records": [1, 2]}), encoding="utf-8")
    with pytest.raises(ValueError, match="array of JSON objects"):
        detect_file_format(bad_wrap_list)

    bad_json_syntax = tmp_path / "syntax.json"
    bad_json_syntax.write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON file"):
        detect_file_format(bad_json_syntax)

    for jl_name, jl_bytes in (("jl_scalar.jsonl", b"123\n"), ("jl_syntax.jsonl", b"{bad\n")):
        jl_bad = tmp_path / jl_name
        jl_bad.write_bytes(jl_bytes)
        with pytest.raises(ValueError):
            iter_tabular_rows(jl_bad, detect_file_format(jl_bad))
        jl_bad.unlink()

    bad_xlsx = tmp_path / "corrupt.xlsx"
    bad_xlsx.write_bytes(b"not-a-zip")
    with pytest.raises(ValueError, match="Invalid Excel"):
        detect_file_format(bad_xlsx)
    bad_xlsx.unlink()

    bad_pq = tmp_path / "corrupt.parquet"
    bad_pq.write_bytes(b"not-parquet")
    with pytest.raises(ValueError, match="Invalid Parquet"):
        detect_file_format(bad_pq)
    bad_pq.unlink()

    bad_delim_csv = tmp_path / "bad_delim.csv"
    bad_delim_csv.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(TypeError):
        iter_tabular_rows(bad_delim_csv, FileFormatSpec(format="csv", delimiter="bad"))
    bad_delim_csv.unlink()

    # Temp file rollback if generator fails mid-write in write_tabular_output / write_xlsx_sheets
    def _failing_rows():
        yield {"a": 1}
        raise ValueError("mid-stream boom")

    with pytest.raises(ValueError, match="mid-stream boom"):
        write_tabular_output(tmp_path / "abort.csv", ["a"], _failing_rows(), FileFormatSpec(format="csv"))
    with pytest.raises(ValueError, match="mid-stream boom"):
        write_xlsx_sheets(tmp_path / "abort.xlsx", {"S": (["a"], _failing_rows())})

    # Pass-3 I/O regressions: delimiter validation, NaN/Inf/bytes/date/ctrl sanitization
    delim_probe = tmp_path / "delim_probe.csv"
    delim_probe.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="single printable character"):
        detect_file_format(delim_probe, delimiter_override="::")
    with pytest.raises(ValueError, match="single printable character"):
        detect_file_format(delim_probe, delimiter_override="\n")

    assert _cell_to_json_scalar(None) == ""
    assert _cell_to_json_scalar(float("inf")) == ""
    assert _cell_to_json_scalar(b"\x80\xff") == "80ff"
    assert _cell_to_json_scalar(datetime.date(2026, 1, 2)) == "2026-01-02"
    assert cell_to_input_text(None) == ""
    assert cell_to_input_text(float("nan")) == ""
    assert cell_to_input_text(2125552368.0) == "2125552368"
    assert cell_to_input_text(3.5) == "3.5"

    # XLSX control chars / NaN / bytes sanitization + JSON/JSONL NaN -> null (strict allow_nan=False)
    ctrl_xlsx = tmp_path / "ctrl_clean.xlsx"
    assert (
        write_tabular_output(
            ctrl_xlsx,
            ["org", "nan_v", "raw_b", "num"],
            [{"org": "Acme\x0bCorp\x00", "nan_v": float("nan"), "raw_b": b"\x0f\x1a", "num": 42}],
            FileFormatSpec(format="xlsx"),
        )
        == 1
    )
    wb_ctrl = openpyxl.load_workbook(ctrl_xlsx)
    assert wb_ctrl.active.cell(2, 1).value == "AcmeCorp"
    assert wb_ctrl.active.cell(2, 2).value is None or wb_ctrl.active.cell(2, 2).value == ""
    assert wb_ctrl.active.cell(2, 3).value == "0f1a"
    assert wb_ctrl.active.cell(2, 4).value == 42
    wb_ctrl.close()

    nan_json = tmp_path / "nan_strict.json"
    assert (
        write_tabular_output(
            nan_json,
            ["a", "b"],
            [{"a": float("nan"), "b": 1.5}],
            FileFormatSpec(format="json"),
        )
        == 1
    )
    assert json.loads(nan_json.read_text(encoding="utf-8")) == [{"a": None, "b": 1.5}]

    nan_jsonl = tmp_path / "nan_strict.jsonl"
    assert (
        write_tabular_output(
            nan_jsonl,
            ["a", "b"],
            [{"a": float("inf"), "b": 2}],
            FileFormatSpec(format="jsonl"),
        )
        == 1
    )
    assert json.loads(nan_jsonl.read_text(encoding="utf-8").strip()) == {"a": None, "b": 2}

    nan_csv = tmp_path / "nan_flat.csv"
    assert (
        write_tabular_output(
            nan_csv,
            ["a", "b", "c"],
            [{"a": None, "b": float("nan"), "c": 3}],
            FileFormatSpec(format="csv"),
        )
        == 1
    )
    assert nan_csv.read_text(encoding="utf-8").splitlines() == ["a,b,c", ",,3"]

    # Pass-4 regressions:
    # 1) Lazy openpyxl ImportError when missing
    import entity_standardizer.workbench.io_formats as _io_mod

    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "openpyxl", None)
        mp.setattr(_io_mod, "_openpyxl_mod", _io_mod._UNSET)
        with pytest.raises(ImportError, match="openpyxl is required"):
            _io_mod._ensure_openpyxl()

    # 2) European semicolon .csv auto-sniffing vs single-column .csv fallback
    eu_csv = tmp_path / "german.csv"
    eu_csv.write_text("id;org;phone\n1;Siemens AG;+49 89 63600\n", encoding="utf-8")
    eu_info = inspect_tabular_source(eu_csv)
    assert eu_info["format_spec"]["delimiter"] == ";"
    assert eu_info["columns"] == ["id", "org", "phone"]

    one_col_csv = tmp_path / "single_col.csv"
    one_col_csv.write_text("id\n1\n", encoding="utf-8")
    assert detect_file_format(one_col_csv).delimiter == ","

    # 3) Sparse >100-line JSONL (with blank lines + late column on line 105) + empty JSONL
    sparse_jl = tmp_path / "sparse_105.jsonl"
    jl_lines = ['{"id": 1, "org": "Acme"}', "", '{"id": 2, "org": "Beta", "phone": "212-555-2368"}']
    jl_lines.extend(f'{{"id": {i}, "org": "Firm {i}"}}' for i in range(3, 105))
    jl_lines.append("")
    jl_lines.append('{"id": 105, "org": "Late Corp", "late_note": "keep_me"}')
    sparse_jl.write_text("\n".join(jl_lines) + "\n", encoding="utf-8")
    sp_spec = detect_file_format(sparse_jl)
    sp_cols, sp_iter = iter_tabular_rows(sparse_jl, sp_spec)
    assert sp_cols == ["id", "org", "phone"]
    sparse_out = tmp_path / "sparse_out.jsonl"
    assert write_tabular_output(sparse_out, sp_cols, sp_iter, sp_spec) == 105
    exported_objs = [json.loads(ln) for ln in sparse_out.read_text(encoding="utf-8").splitlines()]
    assert exported_objs[1]["phone"] == "212-555-2368"
    assert exported_objs[-1]["late_note"] == "keep_me"

    empty_jl = tmp_path / "empty.jsonl"
    empty_jl.write_text("", encoding="utf-8")
    empty_cols, empty_it = iter_tabular_rows(empty_jl, detect_file_format(empty_jl))
    assert empty_cols == [] and list(empty_it) == []

    # 4) XLSX preserves native datetime.date objects and short rows on round-trip
    date_xlsx = tmp_path / "native_date.xlsx"
    wb_dt = openpyxl.Workbook()
    ws_dt = wb_dt.active
    ws_dt.append(["id", "as_of"])
    ws_dt.append([1, datetime.date(2026, 5, 1)])
    ws_dt.append([2])  # short row
    wb_dt.save(date_xlsx)
    wb_dt.close()

    dt_spec = detect_file_format(date_xlsx)
    dt_cols, dt_iter = iter_tabular_rows(date_xlsx, dt_spec)
    dt_rows = list(dt_iter)
    assert isinstance(dt_rows[0]["as_of"], datetime.date)
    assert dt_rows[1]["as_of"] == ""
    date_xlsx_out = tmp_path / "native_date_out.xlsx"
    assert write_tabular_output(date_xlsx_out, dt_cols, dt_rows, dt_spec) == 2
    wb_dt_out = openpyxl.load_workbook(date_xlsx_out)
    assert isinstance(wb_dt_out.active.cell(2, 2).value, (datetime.date, datetime.datetime))
    wb_dt_out.close()

    # Pass-7: XLSX template with merged header & data cells is cleanly unmerged on rewrite
    merged_xlsx = tmp_path / "merged_cells.xlsx"
    wb_mg = openpyxl.Workbook()
    ws_mg = wb_mg.active
    ws_mg.append(["Banner", "", ""])
    ws_mg.merge_cells("A1:C1")
    ws_mg.append(["1", "212-555-2368", "Note"])
    ws_mg.merge_cells("B2:C2")
    wb_mg.save(merged_xlsx)
    wb_mg.close()
    mg_spec = detect_file_format(merged_xlsx)
    mg_cols, mg_it = iter_tabular_rows(merged_xlsx, mg_spec)
    mg_rows = list(mg_it)
    merged_out = tmp_path / "merged_cells_out.xlsx"
    assert write_tabular_output(merged_out, mg_cols, mg_rows, mg_spec, template_xlsx_path=merged_xlsx) == 1
    wb_mg_out = openpyxl.load_workbook(merged_out)
    assert list(wb_mg_out.active.merged_cells.ranges) == []
    assert [wb_mg_out.active.cell(1, c).value for c in (1, 2, 3)] == ["Banner", "col_2", "col_3"]
    wb_mg_out.close()


def test_mapping_auto_detect_300_cols_and_preset_store(tmp_path: Path) -> None:
    sf_cols = [
        "Id",
        "Name",
        "FirstName",
        "MiddleName",
        "LastName",
        "Suffix",
        "Salutation",
        "Title",
        "Phone",
        "MobilePhone",
        "Fax",
        "Email",
        "LinkedIn_Link__c",
        "CRD_Number__c",
        "External_Record_Id__c",
        "Advisor_Team_Name__c",
        "BillingAddress",
        "BillingStreet",
        "BillingCity",
        "BillingStateCode",
        "BillingPostalCode",
        "BillingCountry",
        "BillingCountryCode",
        "ShippingStreet",
        "ShippingCity",
        "ShippingState",
        "ShippingPostalCode",
        "ShippingCountry",
        "MailingStreet",
        "OtherStreet",
        "LastModifiedDate",
        "DoNotCall",
        "Email_Domain__c",
    ] + [f"Custom_Metric_{i}__c" for i in range(280)]

    samples = [
        {
            "Name": "Goldman Sachs & Co LLC",
            "FirstName": "Jane",
            "LastName": "Doe",
            "BillingStreet": "200 West St",
        }
    ]
    cfg = auto_detect_mappings(sf_cols, samples)
    by_col = {m.column: m for m in cfg.mappings}

    assert by_col["Id"].role == FieldRole.RECORD_ID.value
    assert by_col["Name"].role == FieldRole.ORGANIZATION.value
    assert by_col["FirstName"].role == FieldRole.FIRST_NAME.value
    assert by_col["BillingStreet"].group_id == "billing"
    assert by_col["ShippingStreet"].group_id == "shipping"
    assert by_col["MailingStreet"].group_id == "mailing"
    assert by_col["OtherStreet"].group_id == "other"
    assert by_col["LinkedIn_Link__c"].role == FieldRole.SOCIAL.value
    assert by_col["CRD_Number__c"].role == FieldRole.CRD.value
    assert by_col["External_Record_Id__c"].role == FieldRole.EXTERNAL_ID.value
    assert by_col["Advisor_Team_Name__c"].role == FieldRole.ADVISOR_GROUP.value
    assert "BillingAddress" not in by_col
    assert "LastModifiedDate" not in by_col
    assert "DoNotCall" not in by_col
    assert "Email_Domain__c" not in by_col

    # Execution units partition duplicate roles (Phone + MobilePhone, BillingCountry + BillingCountryCode)
    units = cfg.execution_units()
    unit_ids = [u[0] for u in units]
    assert "primary" in unit_ids and "primary__MobilePhone" in unit_ids
    assert "billing" in unit_ids and "billing__BillingCountryCode" in unit_ids
    assert cfg.is_cross_healing_enabled("primary__MobilePhone") is True
    cfg.group_cross_healing["billing"] = False
    assert cfg.is_cross_healing_enabled("billing__BillingCountryCode") is False

    # Ambiguous "Name" without sample rows or without split person cols and non-org sample maps to PERSON_NAME
    assert {m.column: m.role for m in auto_detect_mappings(["Name"]).mappings}["Name"] == FieldRole.PERSON_NAME.value
    cfg_person = auto_detect_mappings(["Name", "Street", "Address"], [{"Name": "Alice Smith"}])
    by_per = {m.column: m for m in cfg_person.mappings}
    assert by_per["Name"].role == FieldRole.PERSON_NAME.value
    assert "Address" not in by_per and by_per["Street"].role == FieldRole.STREET1.value

    # Ambiguous "Name" WITH split person cols and non-org sample is skipped
    cfg_skip_name = auto_detect_mappings(["Name", "FirstName", "LastName"], [{"Name": "Alice Smith"}])
    assert "Name" not in {m.column for m in cfg_skip_name.mappings}

    # Salesforce Person Account columns, per-group split-person isolation, and Address+Address1 skip
    cfg_pa = auto_detect_mappings(
        [
            "Name",
            "Assistant_First_Name",
            "PersonTitle",
            "PersonEmail",
            "PersonHomePhone",
            "PersonMailingStreet",
            "Address",
            "Street1",
        ],
        [{"Name": "Alice Smith"}],
    )
    by_pa = {m.column: m for m in cfg_pa.mappings}
    assert by_pa["Name"].role == FieldRole.PERSON_NAME.value
    assert by_pa["PersonTitle"].role == FieldRole.JOB_TITLE.value
    assert by_pa["PersonEmail"].role == FieldRole.EMAIL.value
    assert by_pa["PersonHomePhone"].role == FieldRole.PHONE.value
    assert by_pa["PersonMailingStreet"].group_id == "mailing"
    assert "Address" not in by_pa and by_pa["Street1"].role == FieldRole.STREET1.value

    # MappingConfig serialization round-trip & empty fallback
    assert MappingConfig.from_dict(None).mappings == []
    rebuilt = MappingConfig.from_dict(cfg.to_dict())
    assert len(rebuilt.mappings) == len(cfg.mappings)

    with pytest.raises(ValueError):
        ColumnMapping(column="x", role="not_a_real_role")

    # PresetStore CRUD and path traversal protection
    store = PresetStore(tmp_path / "presets")
    assert store.list_presets() == []
    saved = store.save_preset(
        "SF Contacts",
        {"description": "CRM preset", "mapping_config": cfg.to_dict()},
    )
    assert saved["name"] == "SF Contacts"
    assert len(store.list_presets()) == 1
    assert store.get_preset("SF Contacts")["description"] == "CRM preset"
    assert store.delete_preset("SF Contacts") is True
    assert store.delete_preset("SF Contacts") is False

    with pytest.raises(FileNotFoundError):
        store.get_preset("Missing Preset")
    with pytest.raises(ValueError):
        store.save_preset("../escape", {})

    # Corrupt & non-object JSON files in PresetStore
    store.save_preset("Valid One", {"mapping_config": cfg.to_dict()})
    (store.root_dir / "Corrupt Syntax.json").write_text("{bad", encoding="utf-8")
    (store.root_dir / "Array Not Object.json").write_text("[1, 2, 3]", encoding="utf-8")
    listed = store.list_presets()
    assert [p["name"] for p in listed] == ["Valid One"]
    with pytest.raises(ValueError, match="corrupted"):
        store.get_preset("Corrupt Syntax")
    with pytest.raises(ValueError, match="JSON object"):
        store.get_preset("Array Not Object")

    # Pass-5: MappingConfig.from_dict rejects malformed shapes
    for bad_cfg in (
        "bad",
        {"mappings": "bad"},
        {"mappings": [123]},
        {"mappings": [], "group_cross_healing": [1, 2]},
    ):
        with pytest.raises(ValueError):
            MappingConfig.from_dict(bad_cfg)  # type: ignore[arg-type]
