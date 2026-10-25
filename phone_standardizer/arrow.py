"""Modern Data Stack Plugins: Apache Arrow, Polars, and DuckDB Vectorized UDFs.

Provides high-throughput columnar phone standardization for analytical tables:
- Vectorized Apache Arrow Table & RecordBatch transformations (`standardize_arrow`)
- Polars DataFrame & LazyFrame integration (`standardize_polars`)
- Embedded DuckDB SQL scalar UDFs (`register_duckdb_udfs`)
"""

from __future__ import annotations

from typing import Any

from phone_standardizer.standardizer import (
    format_e164,
    format_international,
    format_national,
    mask_phone,
    standardize_phone,
    validate_phone,
)

_UNSET: Any = object()
pa: Any = _UNSET
pl: Any = _UNSET
duckdb: Any = _UNSET


def standardize_arrow(
    table_or_batch: Any,
    phone_col: str = "phone",
    country_col: str | None = None,
    default_country: str = "US",
    output_prefix: str = "phone_",
    as_struct: bool = False,
) -> Any:
    """Standardize phone numbers in an Apache Arrow Table or RecordBatch."""
    global pa
    if pa is _UNSET:
        try:
            import pyarrow as _pa  # type: ignore[import-not-found]

            pa = _pa
        except ImportError:
            pa = None
    if pa is None:
        raise ImportError("pyarrow is required to use standardize_arrow. Install with `pip install pyarrow`.")

    is_batch = isinstance(table_or_batch, pa.RecordBatch)
    if is_batch:
        table = pa.Table.from_batches([table_or_batch])
    elif isinstance(table_or_batch, pa.Table):
        table = table_or_batch
    else:
        raise TypeError(f"Expected pyarrow.Table or pyarrow.RecordBatch, got {type(table_or_batch)}")

    col_names = table.column_names
    if phone_col not in col_names:
        raise ValueError(f"phone_col {phone_col!r} is not a column of the input (columns: {col_names})")

    num_rows = table.num_rows
    phones = [str(v) if v is not None else None for v in table.column(phone_col).to_pylist()]
    if country_col and country_col in col_names:
        countries = [str(v) if v is not None else None for v in table.column(country_col).to_pylist()]
    else:
        countries = [None] * num_rows

    out_e164: list[str | None] = []
    out_national: list[str | None] = []
    out_intl: list[str | None] = []
    out_rfc3966: list[str | None] = []
    out_country_iso2: list[str | None] = []
    out_region: list[str | None] = []
    out_line_type: list[str] = []
    out_ext: list[str | None] = []
    out_valid: list[bool] = []
    out_confidence: list[float] = []
    out_tier: list[str] = []

    for i in range(num_rows):
        res = standardize_phone(phones[i], country=countries[i], default_country=default_country)
        out_e164.append(res.e164)
        out_national.append(res.national)
        out_intl.append(res.international)
        out_rfc3966.append(res.rfc3966)
        out_country_iso2.append(res.country_iso2)
        out_region.append(res.region_code)
        out_line_type.append(res.line_type)
        out_ext.append(res.extension)
        out_valid.append(res.is_valid)
        out_confidence.append(res.confidence)
        out_tier.append(res.routing_tier)

    arrays_map: list[tuple[str, Any]] = [
        ("e164", pa.array(out_e164, type=pa.string())),
        ("national", pa.array(out_national, type=pa.string())),
        ("international", pa.array(out_intl, type=pa.string())),
        ("rfc3966", pa.array(out_rfc3966, type=pa.string())),
        ("country_iso2", pa.array(out_country_iso2, type=pa.string())),
        ("region_code", pa.array(out_region, type=pa.string())),
        ("line_type", pa.array(out_line_type, type=pa.string())),
        ("extension", pa.array(out_ext, type=pa.string())),
        ("is_valid", pa.array(out_valid, type=pa.bool_())),
        ("confidence", pa.array(out_confidence, type=pa.float64())),
        ("routing_tier", pa.array(out_tier, type=pa.string())),
    ]

    if as_struct:
        struct_arr = pa.StructArray.from_arrays(
            [arr for _, arr in arrays_map],
            names=[name for name, _ in arrays_map],
        )
        result_table = table.append_column(f"{output_prefix}standardized", struct_arr)
    else:
        result_table = table
        for name, arr in arrays_map:
            col_label = f"{output_prefix}{name}"
            if col_label in result_table.column_names:
                idx = result_table.column_names.index(col_label)
                result_table = result_table.set_column(idx, col_label, arr)
            else:
                result_table = result_table.append_column(col_label, arr)

    if is_batch:
        batches = result_table.to_batches()
        return batches[0] if batches else pa.RecordBatch.from_pydict(
            {field.name: [] for field in result_table.schema},
            schema=result_table.schema,
        )
    return result_table


def standardize_polars(
    df_or_lazy: Any,
    phone_col: str = "phone",
    country_col: str | None = None,
    default_country: str = "US",
    output_prefix: str = "phone_",
) -> Any:
    """Standardize phone numbers in a Polars DataFrame or LazyFrame."""
    global pl
    if pl is _UNSET:
        try:
            import polars as _pl  # type: ignore[import-not-found]

            pl = _pl
        except ImportError:
            pl = None
    if pl is None:
        raise ImportError("polars is required to use standardize_polars. Install with `pip install polars`.")

    is_lazy = isinstance(df_or_lazy, pl.LazyFrame)
    if is_lazy:
        df = df_or_lazy.collect()
    elif isinstance(df_or_lazy, pl.DataFrame):
        df = df_or_lazy
    else:
        raise TypeError(f"Expected polars.DataFrame or polars.LazyFrame, got {type(df_or_lazy)}")

    arrow_tbl = df.to_arrow()
    std_tbl = standardize_arrow(
        arrow_tbl,
        phone_col=phone_col,
        country_col=country_col,
        default_country=default_country,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]


def register_duckdb_udfs(con: Any, default_country: str = "US") -> None:
    """Register scalar phone standardization UDFs on a DuckDB connection."""
    global duckdb
    if duckdb is _UNSET:
        try:
            import duckdb as _duckdb  # type: ignore[import-not-found]

            duckdb = _duckdb
        except ImportError:
            duckdb = None
    if duckdb is None:
        raise ImportError("duckdb is required to use register_duckdb_udfs. Install with `pip install duckdb`.")
    from phone_standardizer.dedup import generate_phone_blocking_keys

    def _e164_udf(phone: str | None) -> str | None:
        return format_e164(phone, default_country=default_country)

    def _national_udf(phone: str | None) -> str | None:
        return format_national(phone, default_country=default_country)

    def _intl_udf(phone: str | None) -> str | None:
        return format_international(phone, default_country=default_country)

    def _valid_udf(phone: str | None) -> bool:
        return validate_phone(phone, default_country=default_country)

    def _mask_udf(phone: str | None) -> str | None:
        return mask_phone(phone, strategy="partial", default_country=default_country)

    def _blocking_keys_udf(phone: str | None) -> list[str]:
        if not phone:
            return []
        return list(generate_phone_blocking_keys(phone, country=default_country))

    con.create_function("standardize_phone_e164", _e164_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("standardize_phone_national", _national_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("standardize_phone_international", _intl_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("validate_phone_udf", _valid_udf, ["VARCHAR"], "BOOLEAN")
    con.create_function("mask_phone_udf", _mask_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("phone_blocking_keys", _blocking_keys_udf, ["VARCHAR"], "VARCHAR[]")

    from entity_standardizer.company import standardize_company
    from entity_standardizer.person import standardize_person
    from entity_standardizer.web import standardize_email, standardize_url

    def _company_name_udf(name: str | None) -> str | None:
        return standardize_company(name, country=default_country).legal_name

    def _company_key_udf(name: str | None) -> str | None:
        return standardize_company(name, country=default_country).company_key

    def _person_name_udf(name: str | None) -> str | None:
        return standardize_person(name).full_name

    def _person_key_udf(name: str | None) -> str | None:
        return standardize_person(name).person_root_key

    def _email_udf(email: str | None) -> str | None:
        return standardize_email(email).email

    def _url_domain_udf(url: str | None) -> str | None:
        return standardize_url(url).domain

    con.create_function("standardize_company_name", _company_name_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("company_entity_key", _company_key_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("standardize_person_name", _person_name_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("person_entity_key", _person_key_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("standardize_email_udf", _email_udf, ["VARCHAR"], "VARCHAR")
    con.create_function("standardize_url_domain", _url_domain_udf, ["VARCHAR"], "VARCHAR")


def standardize_companies_arrow(
    table: Any,
    company_col: str = "company",
    country_col: str | None = None,
    output_prefix: str = "company_",
) -> Any:
    """Standardize company/organization names in an Apache Arrow Table."""
    from entity_standardizer.company import standardize_company

    col_names = table.column_names
    if company_col not in col_names:
        raise ValueError(f"company_col {company_col!r} is not a column of the input (columns: {col_names})")

    num_rows = table.num_rows
    names = [str(v) if v is not None else None for v in table.column(company_col).to_pylist()]
    countries = (
        [str(v) if v is not None else None for v in table.column(country_col).to_pylist()]
        if country_col and country_col in col_names
        else [None] * num_rows
    )

    records = [standardize_company(names[i], country=countries[i]) for i in range(num_rows)]
    arrays_map: list[tuple[str, Any]] = [
        ("legal_name", pa.array([r.legal_name for r in records], type=pa.string())),
        ("base_name", pa.array([r.base_name for r in records], type=pa.string())),
        ("brand_stem", pa.array([r.brand_stem for r in records], type=pa.string())),
        ("legal_suffix", pa.array([r.legal_suffix for r in records], type=pa.string())),
        ("inferred_country_iso2", pa.array([r.inferred_country_iso2 for r in records], type=pa.string())),
        ("company_key", pa.array([r.company_key for r in records], type=pa.string())),
        ("is_valid", pa.array([r.is_valid for r in records], type=pa.bool_())),
        ("confidence", pa.array([r.confidence for r in records], type=pa.float64())),
    ]

    result_table = table
    for name, arr in arrays_map:
        result_table = result_table.append_column(f"{output_prefix}{name}", arr)
    return result_table


def standardize_companies_polars(
    df: Any,
    company_col: str = "company",
    country_col: str | None = None,
    output_prefix: str = "company_",
) -> Any:
    """Standardize company/organization names in a Polars DataFrame."""
    std_tbl = standardize_companies_arrow(
        df.to_arrow(),
        company_col=company_col,
        country_col=country_col,
        output_prefix=output_prefix,
    )
    return pl.from_arrow(std_tbl)


def standardize_persons_arrow(
    table: Any,
    person_col: str = "person",
    output_prefix: str = "person_",
) -> Any:
    """Standardize person full names in an Apache Arrow Table."""
    from entity_standardizer.person import standardize_person

    col_names = table.column_names
    if person_col not in col_names:
        raise ValueError(f"person_col {person_col!r} is not a column of the input (columns: {col_names})")

    names = [str(v) if v is not None else None for v in table.column(person_col).to_pylist()]
    records = [standardize_person(n) for n in names]
    arrays_map: list[tuple[str, Any]] = [
        ("full_name", pa.array([r.full_name for r in records], type=pa.string())),
        ("first_name", pa.array([r.first_name for r in records], type=pa.string())),
        ("root_first_name", pa.array([r.root_first_name for r in records], type=pa.string())),
        ("last_name", pa.array([r.last_name for r in records], type=pa.string())),
        ("person_key", pa.array([r.person_key for r in records], type=pa.string())),
        ("person_root_key", pa.array([r.person_root_key for r in records], type=pa.string())),
        ("is_valid", pa.array([r.is_valid for r in records], type=pa.bool_())),
        ("confidence", pa.array([r.confidence for r in records], type=pa.float64())),
    ]

    result_table = table
    for name, arr in arrays_map:
        result_table = result_table.append_column(f"{output_prefix}{name}", arr)
    return result_table


def standardize_persons_polars(
    df: Any,
    person_col: str = "person",
    output_prefix: str = "person_",
) -> Any:
    """Standardize person full names in a Polars DataFrame."""
    std_tbl = standardize_persons_arrow(
        df.to_arrow(),
        person_col=person_col,
        output_prefix=output_prefix,
    )
    return pl.from_arrow(std_tbl)



