"""Tests for Apache Arrow, Polars, DuckDB UDFs, and Native Dispatch Batch Acceleration."""

from __future__ import annotations

from unittest.mock import MagicMock

import duckdb
import polars as pl
import pyarrow as pa
import pytest

import phone_standardizer._native_dispatch as native_dispatch
import phone_standardizer.arrow as arrow_mod
from phone_standardizer import (
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

    # Simulate missing optional dependencies
    monkeypatch.setattr(arrow_mod, "pa", None)
    with pytest.raises(ImportError, match="pyarrow"):
        standardize_arrow(tbl)

    monkeypatch.setattr(arrow_mod, "pl", None)
    with pytest.raises(ImportError, match="polars"):
        standardize_polars(tbl)

    monkeypatch.setattr(arrow_mod, "duckdb", None)
    with pytest.raises(ImportError, match="duckdb"):
        register_duckdb_udfs(None)


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
            mask_phone_udf('(415) 555-2671')
        """
    ).fetchone()
    assert row == (
        "+14155552671",
        "(415) 555-2671",
        "+1 415-555-2671",
        True,
        "+1******2671",
    )


def test_native_dispatch_extended_functions(monkeypatch) -> None:
    # Pure Python fallback path
    folded, changed = fold_unicode_digits_dispatch("＋８１ ３-１２３４-５６７８")
    assert changed is True and folded == "+81 3-1234-5678"
    assert extract_digits_dispatch("+1 (415) 555-2671") == "14155552671"

    batch_py = standardize_batch_e164_dispatch(
        ["(415) 555-2671", "1-212-555-0299", "+44 20 7946 0912", "123", "123456789012345"],
        default_calling_code="1",
    )
    assert batch_py == ["+14155552671", "+12125550299", "+442079460912", None, None]

    batch_de = standardize_batch_e164_dispatch(["3012345678"], default_calling_code="49")
    assert batch_de == ["+493012345678"]

    # Native Rust dispatch path
    mock_rs = MagicMock()
    mock_rs.fold_unicode_digits_rs.return_value = ("+81 3-1234-5678", True)
    mock_rs.extract_digits_rs.return_value = "14155552671"
    mock_rs.standardize_batch_e164_rs.return_value = ["+14155552671"]
    monkeypatch.setattr(native_dispatch, "_native_mod", mock_rs)

    assert fold_unicode_digits_dispatch("＋８１ ３-１２３４-５６７８") == ("+81 3-1234-5678", True)
    assert extract_digits_dispatch("+1 (415) 555-2671") == "14155552671"
    assert standardize_batch_e164_dispatch(["(415) 555-2671"]) == ["+14155552671"]
