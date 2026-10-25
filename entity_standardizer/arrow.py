"""Modern Data Stack Plugins: Apache Arrow, Polars, and DuckDB Vectorized UDFs.

Provides high-throughput columnar phone standardization for analytical tables:
- Vectorized Apache Arrow Table & RecordBatch transformations (`standardize_arrow`)
- Polars DataFrame & LazyFrame integration (`standardize_polars`)
- Embedded DuckDB SQL scalar UDFs (`register_duckdb_udfs`)
"""

from __future__ import annotations

from typing import Any

from entity_standardizer.standardizer import (
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


def _ensure_pyarrow() -> Any:
    global pa
    if pa is _UNSET:
        try:
            import pyarrow as _pa  # type: ignore[import-not-found]

            pa = _pa
        except ImportError:
            pa = None
    if pa is None:
        raise ImportError("pyarrow is required to use standardize_arrow. Install with `pip install pyarrow`.")
    return pa


def _ensure_polars() -> Any:
    global pl
    if pl is _UNSET:
        try:
            import polars as _pl  # type: ignore[import-not-found]

            pl = _pl
        except ImportError:
            pl = None
    if pl is None:
        raise ImportError("polars is required to use standardize_polars. Install with `pip install polars`.")
    return pl


def _unwrap_arrow_input(table_or_batch: Any) -> tuple[Any, bool]:
    _ensure_pyarrow()
    is_batch = isinstance(table_or_batch, pa.RecordBatch)
    if is_batch:
        return pa.Table.from_batches([table_or_batch]), True
    if isinstance(table_or_batch, pa.Table):
        return table_or_batch, False
    raise TypeError(f"Expected pyarrow.Table or pyarrow.RecordBatch, got {type(table_or_batch)}")


def _finalize_arrow_output(
    table: Any,
    is_batch: bool,
    output_prefix: str,
    arrays_map: list[tuple[str, Any]],
    as_struct: bool,
) -> Any:
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
        return (
            batches[0]
            if batches
            else pa.RecordBatch.from_pydict(
                {field.name: [] for field in result_table.schema},
                schema=result_table.schema,
            )
        )
    return result_table


def _unwrap_polars_input(df_or_lazy: Any) -> tuple[Any, bool]:
    _ensure_polars()
    is_lazy = isinstance(df_or_lazy, pl.LazyFrame)
    if is_lazy:
        return df_or_lazy.collect(), True
    if isinstance(df_or_lazy, pl.DataFrame):
        return df_or_lazy, False
    raise TypeError(f"Expected polars.DataFrame or polars.LazyFrame, got {type(df_or_lazy)}")


def standardize_arrow(
    table_or_batch: Any,
    phone_col: str = "phone",
    country_col: str | None = None,
    default_country: str = "US",
    output_prefix: str = "phone_",
    as_struct: bool = False,
) -> Any:
    """Standardize phone numbers in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)

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

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_polars(
    df_or_lazy: Any,
    phone_col: str = "phone",
    country_col: str | None = None,
    default_country: str = "US",
    output_prefix: str = "phone_",
) -> Any:
    """Standardize phone numbers in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_arrow(
        df.to_arrow(),
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
    from entity_standardizer.dedup import generate_phone_blocking_keys

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

    con.create_function("standardize_phone_e164", _e164_udf, ["VARCHAR"], "VARCHAR", null_handling="special")
    con.create_function("standardize_phone_national", _national_udf, ["VARCHAR"], "VARCHAR", null_handling="special")
    con.create_function(
        "standardize_phone_international", _intl_udf, ["VARCHAR"], "VARCHAR", null_handling="special"
    )
    con.create_function("validate_phone_udf", _valid_udf, ["VARCHAR"], "BOOLEAN", null_handling="special")
    con.create_function("mask_phone_udf", _mask_udf, ["VARCHAR"], "VARCHAR", null_handling="special")
    con.create_function("phone_blocking_keys", _blocking_keys_udf, ["VARCHAR"], "VARCHAR[]", null_handling="special")

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

    con.create_function(
        "standardize_company_name", _company_name_udf, ["VARCHAR"], "VARCHAR", null_handling="special"
    )
    con.create_function("company_entity_key", _company_key_udf, ["VARCHAR"], "VARCHAR", null_handling="special")
    con.create_function(
        "standardize_person_name", _person_name_udf, ["VARCHAR"], "VARCHAR", null_handling="special"
    )
    con.create_function("person_entity_key", _person_key_udf, ["VARCHAR"], "VARCHAR", null_handling="special")
    con.create_function("standardize_email_udf", _email_udf, ["VARCHAR"], "VARCHAR", null_handling="special")
    con.create_function("standardize_url_domain", _url_domain_udf, ["VARCHAR"], "VARCHAR", null_handling="special")

    from entity_standardizer.address.standardizer import standardize_address
    from entity_standardizer.joint import standardize_contact
    from entity_standardizer.web import standardize_social

    def _address_udf(addr: str | None, country: str | None) -> str | None:
        res = standardize_address(addr, country=country or default_country)
        return res.full_rooftop_address or res.street1 or None

    def _social_udf(profile: str | None, platform: str | None) -> str | None:
        return standardize_social(profile, platform=platform).url

    def _contact_key_udf(
        street1: str | None,
        phone: str | None,
        organization: str | None,
        person_name: str | None,
        email: str | None,
    ) -> str | None:
        return standardize_contact(
            street1=street1,
            phone=phone,
            organization=organization,
            person_name=person_name,
            email=email,
            default_country=default_country,
        ).entity_key

    con.create_function(
        "es_standardize_address", _address_udf, ["VARCHAR", "VARCHAR"], "VARCHAR", null_handling="special"
    )
    con.create_function(
        "es_standardize_social", _social_udf, ["VARCHAR", "VARCHAR"], "VARCHAR", null_handling="special"
    )
    con.create_function(
        "es_standardize_contact_key",
        _contact_key_udf,
        ["VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR"],
        "VARCHAR",
        null_handling="special",
    )


def standardize_addresses_arrow(
    table_or_batch: Any,
    column: str = "address",
    country_column: str | None = None,
    default_country: str = "US",
    output_prefix: str = "address_",
    as_struct: bool = False,
) -> Any:
    """Standardize physical/mailing addresses in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)
    from entity_standardizer.address.standardizer import standardize_address
    from entity_standardizer.registry import normalize_country_iso2

    col_names = table.column_names
    if column not in col_names:
        raise ValueError(f"column {column!r} is not a column of the input (columns: {col_names})")

    num_rows = table.num_rows
    addrs = [str(v) if v is not None else None for v in table.column(column).to_pylist()]
    countries = (
        [str(v) if v is not None else None for v in table.column(country_column).to_pylist()]
        if country_column and country_column in col_names
        else [None] * num_rows
    )

    records = [
        standardize_address(addrs[i], country=countries[i] or default_country)
        for i in range(num_rows)
    ]
    arrays_map: list[tuple[str, Any]] = [
        ("line_1", pa.array([r.street1 or None for r in records], type=pa.string())),
        ("city", pa.array([r.city or None for r in records], type=pa.string())),
        ("state", pa.array([r.state or None for r in records], type=pa.string())),
        ("postal_code", pa.array([r.postal_code or None for r in records], type=pa.string())),
        (
            "country_iso2",
            pa.array([normalize_country_iso2(r.country) for r in records], type=pa.string()),
        ),
        ("key", pa.array([r.normalized_address_key for r in records], type=pa.string())),
        ("is_valid", pa.array([r.address_status == "standardized" for r in records], type=pa.bool_())),
    ]

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_addresses_polars(
    df_or_lazy: Any,
    column: str = "address",
    country_column: str | None = None,
    default_country: str = "US",
    output_prefix: str = "address_",
) -> Any:
    """Standardize physical/mailing addresses in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_addresses_arrow(
        df.to_arrow(),
        column=column,
        country_column=country_column,
        default_country=default_country,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]


def standardize_companies_arrow(
    table_or_batch: Any,
    company_col: str = "company",
    country_col: str | None = None,
    output_prefix: str = "company_",
    as_struct: bool = False,
) -> Any:
    """Standardize company/organization names in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)
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

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_companies_polars(
    df_or_lazy: Any,
    company_col: str = "company",
    country_col: str | None = None,
    output_prefix: str = "company_",
) -> Any:
    """Standardize company/organization names in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_companies_arrow(
        df.to_arrow(),
        company_col=company_col,
        country_col=country_col,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]


def standardize_persons_arrow(
    table_or_batch: Any,
    person_col: str = "person",
    output_prefix: str = "person_",
    as_struct: bool = False,
) -> Any:
    """Standardize person full names in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)
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

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_persons_polars(
    df_or_lazy: Any,
    person_col: str = "person",
    output_prefix: str = "person_",
) -> Any:
    """Standardize person full names in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_persons_arrow(
        df.to_arrow(),
        person_col=person_col,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]


def standardize_emails_arrow(
    table_or_batch: Any,
    email_col: str = "email",
    output_prefix: str = "email_",
    as_struct: bool = False,
) -> Any:
    """Standardize email addresses in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)
    from entity_standardizer.web import standardize_email

    col_names = table.column_names
    if email_col not in col_names:
        raise ValueError(f"email_col {email_col!r} is not a column of the input (columns: {col_names})")

    emails = [str(v) if v is not None else None for v in table.column(email_col).to_pylist()]
    records = [standardize_email(e) for e in emails]
    arrays_map: list[tuple[str, Any]] = [
        ("email", pa.array([r.email for r in records], type=pa.string())),
        ("canonical_email", pa.array([r.email for r in records], type=pa.string())),
        ("local_part", pa.array([r.local_part for r in records], type=pa.string())),
        ("domain", pa.array([r.domain for r in records], type=pa.string())),
        ("is_free_provider", pa.array([r.is_free_provider for r in records], type=pa.bool_())),
        ("is_role_account", pa.array([r.is_role_account for r in records], type=pa.bool_())),
        ("is_valid", pa.array([r.is_valid for r in records], type=pa.bool_())),
        ("confidence", pa.array([r.confidence for r in records], type=pa.float64())),
    ]

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_emails_polars(
    df_or_lazy: Any,
    email_col: str = "email",
    output_prefix: str = "email_",
) -> Any:
    """Standardize email addresses in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_emails_arrow(
        df.to_arrow(),
        email_col=email_col,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]


def standardize_urls_arrow(
    table_or_batch: Any,
    url_col: str = "url",
    output_prefix: str = "url_",
    as_struct: bool = False,
) -> Any:
    """Standardize website URLs in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)
    from entity_standardizer.web import standardize_url

    col_names = table.column_names
    if url_col not in col_names:
        raise ValueError(f"url_col {url_col!r} is not a column of the input (columns: {col_names})")

    urls = [str(v) if v is not None else None for v in table.column(url_col).to_pylist()]
    records = [standardize_url(u) for u in urls]
    arrays_map: list[tuple[str, Any]] = [
        ("url", pa.array([r.url for r in records], type=pa.string())),
        ("hostname", pa.array([r.host for r in records], type=pa.string())),
        ("domain", pa.array([r.domain for r in records], type=pa.string())),
        ("path", pa.array([r.path for r in records], type=pa.string())),
        ("is_valid", pa.array([r.is_valid for r in records], type=pa.bool_())),
        ("confidence", pa.array([r.confidence for r in records], type=pa.float64())),
    ]

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_urls_polars(
    df_or_lazy: Any,
    url_col: str = "url",
    output_prefix: str = "url_",
) -> Any:
    """Standardize website URLs in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_urls_arrow(
        df.to_arrow(),
        url_col=url_col,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]


def standardize_socials_arrow(
    table_or_batch: Any,
    social_col: str = "social",
    platform_col: str | None = None,
    default_platform: str | None = None,
    output_prefix: str = "social_",
    as_struct: bool = False,
) -> Any:
    """Standardize social media profiles in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)
    from entity_standardizer.web import standardize_social

    col_names = table.column_names
    if social_col not in col_names:
        raise ValueError(f"social_col {social_col!r} is not a column of the input (columns: {col_names})")

    num_rows = table.num_rows
    socials = [str(v) if v is not None else None for v in table.column(social_col).to_pylist()]
    platforms = (
        [str(v) if v is not None else None for v in table.column(platform_col).to_pylist()]
        if platform_col and platform_col in col_names
        else [default_platform] * num_rows
    )
    records = [standardize_social(socials[i], platform=platforms[i] or default_platform) for i in range(num_rows)]
    arrays_map: list[tuple[str, Any]] = [
        ("platform", pa.array([r.platform for r in records], type=pa.string())),
        ("profile_type", pa.array([r.profile_type for r in records], type=pa.string())),
        ("handle", pa.array([r.handle for r in records], type=pa.string())),
        ("url", pa.array([r.url for r in records], type=pa.string())),
        ("social_key", pa.array([r.social_key for r in records], type=pa.string())),
        ("is_valid", pa.array([r.is_valid for r in records], type=pa.bool_())),
        ("confidence", pa.array([r.confidence for r in records], type=pa.float64())),
    ]

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_socials_polars(
    df_or_lazy: Any,
    social_col: str = "social",
    platform_col: str | None = None,
    default_platform: str | None = None,
    output_prefix: str = "social_",
) -> Any:
    """Standardize social media profiles in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_socials_arrow(
        df.to_arrow(),
        social_col=social_col,
        platform_col=platform_col,
        default_platform=default_platform,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]


def standardize_contacts_arrow(
    table_or_batch: Any,
    street1_col: str = "street1",
    city_col: str = "city",
    state_col: str = "state",
    postal_code_col: str = "postal_code",
    country_col: str = "country",
    phone_col: str = "phone",
    organization_col: str = "organization",
    person_col: str = "person_name",
    email_col: str = "email",
    website_col: str = "website",
    default_country: str = "US",
    output_prefix: str = "contact_",
    as_struct: bool = False,
) -> Any:
    """Jointly standardize multi-pillar contact records in an Apache Arrow Table or RecordBatch."""
    table, is_batch = _unwrap_arrow_input(table_or_batch)
    from entity_standardizer.joint import standardize_contact

    col_names = set(table.column_names)
    num_rows = table.num_rows

    def _col_vals(col_name: str) -> list[str | None]:
        if col_name in col_names:
            return [str(v) if v is not None else None for v in table.column(col_name).to_pylist()]
        return [None] * num_rows

    s1_vals = _col_vals(street1_col)
    city_vals = _col_vals(city_col)
    state_vals = _col_vals(state_col)
    zip_vals = _col_vals(postal_code_col)
    country_vals = _col_vals(country_col)
    phone_vals = _col_vals(phone_col)
    org_vals = _col_vals(organization_col)
    person_vals = _col_vals(person_col)
    email_vals = _col_vals(email_col)
    web_vals = _col_vals(website_col)

    records = [
        standardize_contact(
            street1=s1_vals[i],
            city=city_vals[i],
            state=state_vals[i],
            postal_code=zip_vals[i],
            country=country_vals[i],
            phone=phone_vals[i],
            organization=org_vals[i],
            person_name=person_vals[i],
            email=email_vals[i],
            website=web_vals[i],
            default_country=default_country,
        )
        for i in range(num_rows)
    ]
    arrays_map: list[tuple[str, Any]] = [
        ("entity_key", pa.array([r.entity_key for r in records], type=pa.string())),
        ("phone_e164", pa.array([r.phone.e164 for r in records], type=pa.string())),
        ("address_key", pa.array([r.address.normalized_address_key for r in records], type=pa.string())),
        (
            "company_key",
            pa.array([r.organization.company_key if r.organization else None for r in records], type=pa.string()),
        ),
        (
            "person_key",
            pa.array([r.person.person_key if r.person else None for r in records], type=pa.string()),
        ),
        (
            "email",
            pa.array([r.email.email if r.email else None for r in records], type=pa.string()),
        ),
        (
            "domain",
            pa.array(
                [
                    (r.website.domain if r.website else None) or (r.email.domain if r.email else None)
                    for r in records
                ],
                type=pa.string(),
            ),
        ),
        ("overall_confidence", pa.array([r.overall_confidence for r in records], type=pa.float64())),
    ]

    return _finalize_arrow_output(table, is_batch, output_prefix, arrays_map, as_struct)


def standardize_contacts_polars(
    df_or_lazy: Any,
    street1_col: str = "street1",
    city_col: str = "city",
    state_col: str = "state",
    postal_code_col: str = "postal_code",
    country_col: str = "country",
    phone_col: str = "phone",
    organization_col: str = "organization",
    person_col: str = "person_name",
    email_col: str = "email",
    website_col: str = "website",
    default_country: str = "US",
    output_prefix: str = "contact_",
) -> Any:
    """Jointly standardize multi-pillar contact records in a Polars DataFrame or LazyFrame."""
    df, is_lazy = _unwrap_polars_input(df_or_lazy)
    std_tbl = standardize_contacts_arrow(
        df.to_arrow(),
        street1_col=street1_col,
        city_col=city_col,
        state_col=state_col,
        postal_code_col=postal_code_col,
        country_col=country_col,
        phone_col=phone_col,
        organization_col=organization_col,
        person_col=person_col,
        email_col=email_col,
        website_col=website_col,
        default_country=default_country,
        output_prefix=output_prefix,
    )
    out_df = pl.from_arrow(std_tbl)
    return out_df.lazy() if is_lazy else out_df  # type: ignore[union-attr]
