"""Tests for Apache Arrow, Polars, DuckDB UDFs, and Native Dispatch Batch Acceleration."""

from __future__ import annotations

from unittest.mock import MagicMock

import duckdb
import polars as pl
import pyarrow as pa
import pytest

import entity_standardizer._native_dispatch as native_dispatch
import entity_standardizer.arrow as arrow_mod
from entity_standardizer import (
    extract_digits_dispatch,
    fold_unicode_digits_dispatch,
    register_duckdb_udfs,
    standardize_arrow,
    standardize_batch_e164_dispatch,
    standardize_polars,
)


def test_standardize_arrow_table_and_batch() -> None:
    tbl = pa.table(
        {
            "id": [1, 2],
            "phone": ["(415) 555-2671", "020 7946 0912"],
            "country": ["US", "GB"],
            "phone_e164": ["old1", "old2"],
        }
    )
    res_tbl = standardize_arrow(tbl, phone_col="phone", country_col="country")
    assert res_tbl.column("phone_e164").to_pylist() == ["+14155552671", "+442079460912"]
    assert res_tbl.column("phone_country_iso2").to_pylist() == ["US", "GB"]
    assert res_tbl.column("phone_is_valid").to_pylist() == [True, True]

    # Without country_col and with as_struct=True
    struct_tbl = standardize_arrow(tbl, phone_col="phone", country_col=None, as_struct=True)
    struct_list = struct_tbl.column("phone_standardized").to_pylist()
    assert struct_list[0]["e164"] == "+14155552671"

    # RecordBatch input (non-empty and empty)
    batch = tbl.to_batches()[0]
    res_batch = standardize_arrow(batch, phone_col="phone", country_col="country")
    assert isinstance(res_batch, pa.RecordBatch)
    assert res_batch.column("phone_e164").to_pylist() == ["+14155552671", "+442079460912"]

    empty_batch = pa.RecordBatch.from_pydict(
        {"phone": pa.array([], type=pa.string())},
    )
    res_empty = standardize_arrow(empty_batch, phone_col="phone")
    assert isinstance(res_empty, pa.RecordBatch)
    assert res_empty.num_rows == 0


def test_standardize_arrow_and_polars_errors(monkeypatch) -> None:
    tbl = pa.table({"other": ["123"]})
    with pytest.raises(ValueError, match="phone_col"):
        standardize_arrow(tbl, phone_col="phone")

    with pytest.raises(TypeError, match="Expected pyarrow"):
        standardize_arrow(["not_a_table"])

    with pytest.raises(TypeError, match="Expected polars"):
        standardize_polars(["not_a_df"])

    # Simulate missing optional dependencies via both None override and lazy _UNSET import failure
    import sys

    for attr, mod_name, fn in (
        ("pa", "pyarrow", standardize_arrow),
        ("pl", "polars", standardize_polars),
        ("duckdb", "duckdb", register_duckdb_udfs),
    ):
        with monkeypatch.context() as mp:
            mp.setattr(arrow_mod, attr, None)
            with pytest.raises(ImportError, match=mod_name):
                fn(tbl if attr != "duckdb" else None)

        with monkeypatch.context() as mp:
            mp.setattr(arrow_mod, attr, arrow_mod._UNSET)
            mp.setitem(sys.modules, mod_name, None)
            with pytest.raises(ImportError, match=mod_name):
                fn(tbl if attr != "duckdb" else None)
            assert getattr(arrow_mod, attr) is None




def test_standardize_polars_df_and_lazy() -> None:
    df = pl.DataFrame(
        {
            "phone": ["(415) 555-2671", "+49 30 12345678"],
            "country": ["US", "DE"],
        }
    )
    out_df = standardize_polars(df, phone_col="phone", country_col="country")
    assert out_df["phone_e164"].to_list() == ["+14155552671", "+493012345678"]

    lazy_out = standardize_polars(df.lazy(), phone_col="phone", country_col="country")
    assert isinstance(lazy_out, pl.LazyFrame)
    assert lazy_out.collect()["phone_e164"].to_list() == ["+14155552671", "+493012345678"]


def test_standardize_companies_and_persons_arrow_and_polars(monkeypatch) -> None:
    from entity_standardizer import (
        standardize_companies_arrow,
        standardize_companies_polars,
        standardize_persons_arrow,
        standardize_persons_polars,
    )

    comp_tbl = pa.table(
        {
            "company": ["BlackRock, Inc. /DE/", "KKR Opportunities III S.à r.l."],
            "country": ["US", "LU"],
        }
    )
    with pytest.raises(ValueError, match="company_col"):
        standardize_companies_arrow(comp_tbl, company_col="missing")

    monkeypatch.setattr(arrow_mod, "pa", arrow_mod._UNSET)
    out_comp_tbl = standardize_companies_arrow(comp_tbl, company_col="company", country_col="country")
    assert out_comp_tbl.column("company_legal_name").to_pylist() == [
        "BLACKROCK INC",
        "KKR OPPORTUNITIES III SARL",
    ]

    comp_df = pl.DataFrame({"company": ["Acme Real Estate LLC - Series A"]})
    monkeypatch.setattr(arrow_mod, "pa", arrow_mod._UNSET)
    monkeypatch.setattr(arrow_mod, "pl", arrow_mod._UNSET)
    out_comp_df = standardize_companies_polars(comp_df, company_col="company")
    assert out_comp_df["company_legal_suffix"].to_list() == ["LLC"]

    per_tbl = pa.table({"person": ["Smith, Dr. Robert J., Jr.", "José María Núñez"]})
    with pytest.raises(ValueError, match="person_col"):
        standardize_persons_arrow(per_tbl, person_col="missing")

    monkeypatch.setattr(arrow_mod, "pa", arrow_mod._UNSET)
    out_per_tbl = standardize_persons_arrow(per_tbl, person_col="person")
    assert out_per_tbl.column("person_full_name").to_pylist() == [
        "ROBERT J SMITH JR",
        "JOSE MARIA NUNEZ",
    ]

    per_df = pl.DataFrame({"person": ["Bob J. Smith"]})
    monkeypatch.setattr(arrow_mod, "pa", arrow_mod._UNSET)
    monkeypatch.setattr(arrow_mod, "pl", arrow_mod._UNSET)
    out_per_df = standardize_persons_polars(per_df, person_col="person")
    assert out_per_df["person_root_first_name"].to_list() == ["ROBERT"]



def test_register_duckdb_udfs() -> None:
    con = duckdb.connect(":memory:")
    register_duckdb_udfs(con, default_country="US")
    row = con.execute(
        """
        SELECT
            standardize_phone_e164('(415) 555-2671'),
            standardize_phone_national('+14155552671'),
            standardize_phone_international('(415) 555-2671'),
            validate_phone_udf('(415) 555-2671'),
            mask_phone_udf('(415) 555-2671'),
            phone_blocking_keys('(415) 555-2671'),
            phone_blocking_keys(''),
            standardize_company_name('KKR Opportunities III S.à r.l.'),
            company_entity_key('BlackRock, Inc. /DE/'),
            standardize_person_name('Smith, Dr. Robert J., Jr.'),
            person_entity_key('Bob J. Smith'),
            standardize_email_udf('Jane.Doe+tag@gmial.com'),
            standardize_url_domain('https://www.blackrock.com/us/individual?utm_source=x')
        """
    ).fetchone()
    assert row[:5] == (
        "+14155552671",
        "(415) 555-2671",
        "+1 415-555-2671",
        True,
        "+1******2671",
    )
    assert "e164:+14155552671" in row[5]
    assert row[6] == []
    assert row[7:] == (
        "KKR OPPORTUNITIES III SARL",
        "BLACKROCK|INC",
        "ROBERT J SMITH JR",
        "SMITH|ROBERT",
        "janedoe@gmail.com",
        "blackrock.com",
    )


def test_native_dispatch_extended_functions(monkeypatch, tmp_path) -> None:
    import importlib.machinery
    from pathlib import Path
    import sys

    from entity_standardizer import (
        damerau_levenshtein_distance_dispatch,
        fold_vanity_digits_dispatch,
    )

    # 1. release_dir has no shared library -> returns None
    assert native_dispatch._load_native_module(tmp_path) is None

    # 2. release_dir has an invalid shared library -> hits except Exception: continue -> returns None
    bad_so = tmp_path / "lib_entity_standardizer_rs.so"
    bad_so.write_bytes(b"corrupt")
    assert native_dispatch._load_native_module(tmp_path) is None

    # 3. release_dir has a loadable shared library -> returns module via ExtensionFileLoader
    with monkeypatch.context() as mp:
        mp.setattr(
            importlib.machinery.ExtensionFileLoader,
            "create_module",
            lambda self, spec: MagicMock(),
        )
        mp.setattr(
            importlib.machinery.ExtensionFileLoader,
            "exec_module",
            lambda self, module: None,
        )
        assert native_dispatch._load_native_module(tmp_path) is not None

    # 4. release_dir=None when _entity_standardizer_rs is installed -> returns imported module
    sentinel_mod = MagicMock()
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "_entity_standardizer_rs", sentinel_mod)
        assert native_dispatch._load_native_module(None) is sentinel_mod

    # 5. release_dir=None when _entity_standardizer_rs is not installed -> falls back to target/release
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "_entity_standardizer_rs", None)
        mp.setattr(Path, "is_file", lambda self: False)
        assert native_dispatch._load_native_module(None) is None

    # Pure Python fallback path (explicitly force _native_mod = None)
    monkeypatch.setattr(native_dispatch, "_native_mod", None)
    assert native_dispatch.is_native_available() is False
    assert native_dispatch.get_engine_info()["engine"] == "pure_python"
    assert fold_vanity_digits_dispatch("FLOWERS") == "3569377"
    folded, changed = fold_unicode_digits_dispatch("＋８１ ３-１２３４-５６７８")
    assert changed is True and folded == "+81 3-1234-5678"
    assert extract_digits_dispatch("+1 (415) 555-2671") == "14155552671"
    assert damerau_levenshtein_distance_dispatch("4155552671", "4155552671") == 0
    assert damerau_levenshtein_distance_dispatch("", "123") == 3
    assert damerau_levenshtein_distance_dispatch("123", "") == 3
    assert damerau_levenshtein_distance_dispatch("4155552671", "4155552617") == 1

    batch_py = standardize_batch_e164_dispatch(
        [
            "(415) 555-2671",
            "1-212-555-0299",
            "+44 (0) 20 7946 0912 ext 104",
            "1-800-FLOWERS",
            "123",
            "123456789012345",
            "8:00AM - 6:00PM",
        ],
        default_calling_code="1",
    )
    assert batch_py == [
        "+14155552671",
        "+12125550299",
        "+442079460912",
        "+18003569377",
        None,
        None,
        None,
    ]

    batch_de = standardize_batch_e164_dispatch(["030 12345678", "3012345678"], default_calling_code="49")
    assert batch_de == ["+493012345678", "+493012345678"]

    # Native Rust dispatch path
    from entity_standardizer._native_dispatch import standardize_batch_with_country_dispatch

    mock_rs = MagicMock()
    mock_rs.fold_vanity_digits_rs.return_value = "3569377"
    mock_rs.fold_unicode_digits_rs.return_value = ("+81 3-1234-5678", True)
    mock_rs.extract_digits_rs.return_value = "14155552671"
    mock_rs.damerau_levenshtein_distance_rs.return_value = 1
    mock_rs.standardize_batch_e164_rs.return_value = ["+14155552671"]
    mock_rs.standardize_batch_with_country_rs.return_value = ["+14155552671"]
    monkeypatch.setattr(native_dispatch, "_native_mod", mock_rs)

    assert native_dispatch.get_engine_info()["engine"] == "rust_pyo3"
    assert fold_vanity_digits_dispatch("FLOWERS") == "3569377"
    assert fold_unicode_digits_dispatch("＋８１ ３-１２３４-５６７８") == ("+81 3-1234-5678", True)
    assert extract_digits_dispatch("+1 (415) 555-2671") == "14155552671"
    assert damerau_levenshtein_distance_dispatch("4155552671", "4155552617") == 1
    assert standardize_batch_e164_dispatch(["(415) 555-2671"]) == ["+14155552671"]
    assert standardize_batch_with_country_dispatch([("(415) 555-2671", "US")]) == ["+14155552671"]

