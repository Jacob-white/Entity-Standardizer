"""
Modern Data Stack Plugins: Apache Arrow, Polars, and DuckDB UDFs.
=================================================================
High-performance analytical dataset processing for large address tables:
  - Vectorized Apache Arrow table & batch transformations (zero-copy memory mapping)
  - Polars DataFrame integration with high-throughput columnar operations
  - Embedded DuckDB SQL scalar and struct UDFs for in-database standardization
"""

import warnings
from typing import Any, Dict, List, Optional

from address_standardizer.standardizer import (
    standardize_address,
)

_UNSET: Any = object()
pa: Any = _UNSET
pl: Any = _UNSET
duckdb: Any = _UNSET


# ============================================================================
# Apache Arrow Plugin
# ============================================================================

def standardize_arrow(
    table_or_batch: Any,
    street1_col: str = "street1",
    street2_col: Optional[str] = None,
    city_col: Optional[str] = "city",
    state_col: Optional[str] = "state",
    postal_code_col: Optional[str] = "postal_code",
    country_col: Optional[str] = None,
    enable_geocoding: bool = False,
    enable_fuzzy: bool = True,
    allow_locality: bool = False,
    output_prefix: str = "std_",
    as_struct: bool = False,
) -> Any:
    """
    Standardize addresses in an Apache Arrow Table or RecordBatch.

    Appends standardized USPS / ISO attributes as columnar arrays or a single struct column.
    """
    global pa
    if pa is _UNSET:
        try:
            import pyarrow as _pa

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

    num_rows = table.num_rows
    col_names = table.column_names

    if street1_col not in col_names:
        raise ValueError(f"street1_col {street1_col!r} is not a column of the input (columns: {col_names})")
    missing = [
        name
        for name in (street2_col, city_col, state_col, postal_code_col, country_col)
        if name and name not in col_names
    ]
    if missing:
        warnings.warn(
            f"standardize_arrow: column(s) {missing} not found in the input; those fields are treated as empty",
            stacklevel=2,
        )

    # Extract column lists or defaults
    def _get_col_list(name: Optional[str]) -> List[Optional[str]]:
        if name and name in col_names:
            arr = table.column(name)
            return [str(v) if v is not None else None for v in arr.to_pylist()]
        return [None] * num_rows

    s1_vals = _get_col_list(street1_col)
    s2_vals = _get_col_list(street2_col)
    city_vals = _get_col_list(city_col)
    state_vals = _get_col_list(state_col)
    post_vals = _get_col_list(postal_code_col)
    country_vals = _get_col_list(country_col)

    out_street1: List[str] = []
    out_street2: List[str] = []
    out_city: List[str] = []
    out_state: List[str] = []
    out_postal_code: List[str] = []
    out_country: List[str] = []
    out_key: List[Optional[str]] = []
    out_bldg_key: List[Optional[str]] = []
    out_phonetic_key: List[Optional[str]] = []
    out_status: List[str] = []
    out_deliverability: List[str] = []
    out_lat: List[Optional[float]] = []
    out_lon: List[Optional[float]] = []
    out_precision: List[Optional[str]] = []
    out_accuracy_radius: List[Optional[float]] = []
    out_census_tract: List[Optional[str]] = []
    out_fips_code: List[Optional[str]] = []
    out_confidence: List[Optional[float]] = []
    out_routing_tier: List[Optional[str]] = []
    out_rdi: List[str] = []
    out_cmra: List[bool] = []

    for i in range(num_rows):
        res = standardize_address(
            street1=s1_vals[i],
            street2=s2_vals[i],
            city=city_vals[i],
            state=state_vals[i],
            postal_code=post_vals[i],
            country=country_vals[i],
            enable_geocoding=enable_geocoding,
            enable_fuzzy=enable_fuzzy,
            allow_locality=allow_locality,
        )
        out_street1.append(res.street1 or "")
        out_street2.append(res.street2 or "")
        out_city.append(res.city or "")
        out_state.append(res.state or "")
        out_postal_code.append(res.postal_code or "")
        out_country.append(res.country or "")
        out_key.append(res.normalized_address_key)
        out_bldg_key.append(res.building_key)
        out_phonetic_key.append(res.phonetic_key)
        out_status.append(res.address_status or "")
        out_deliverability.append(res.deliverability or "UNDELIVERABLE")
        out_lat.append(res.latitude)
        out_lon.append(res.longitude)
        out_precision.append(res.precision)
        out_accuracy_radius.append(res.accuracy_radius_meters)
        out_census_tract.append(res.census_tract)
        out_fips_code.append(res.fips_code)
        out_confidence.append(res.confidence_score)
        out_routing_tier.append(res.routing_tier)
        out_rdi.append(res.rdi)
        out_cmra.append(res.cmra)

    if as_struct:
        struct_fields = [
            pa.field("street1", pa.string()),
            pa.field("street2", pa.string()),
            pa.field("city", pa.string()),
            pa.field("state", pa.string()),
            pa.field("postal_code", pa.string()),
            pa.field("country", pa.string()),
            pa.field("normalized_address_key", pa.string()),
            pa.field("building_key", pa.string()),
            pa.field("phonetic_key", pa.string()),
            pa.field("address_status", pa.string()),
            pa.field("deliverability", pa.string()),
            pa.field("latitude", pa.float64()),
            pa.field("longitude", pa.float64()),
            pa.field("precision", pa.string()),
            pa.field("accuracy_radius_meters", pa.float64()),
            pa.field("census_tract", pa.string()),
            pa.field("fips_code", pa.string()),
            pa.field("confidence_score", pa.float64()),
            pa.field("routing_tier", pa.string()),
            pa.field("rdi", pa.string()),
            pa.field("cmra", pa.bool_()),
        ]
        struct_arrays = [
            pa.array(out_street1, pa.string()),
            pa.array(out_street2, pa.string()),
            pa.array(out_city, pa.string()),
            pa.array(out_state, pa.string()),
            pa.array(out_postal_code, pa.string()),
            pa.array(out_country, pa.string()),
            pa.array(out_key, pa.string()),
            pa.array(out_bldg_key, pa.string()),
            pa.array(out_phonetic_key, pa.string()),
            pa.array(out_status, pa.string()),
            pa.array(out_deliverability, pa.string()),
            pa.array(out_lat, pa.float64()),
            pa.array(out_lon, pa.float64()),
            pa.array(out_precision, pa.string()),
            pa.array(out_accuracy_radius, pa.float64()),
            pa.array(out_census_tract, pa.string()),
            pa.array(out_fips_code, pa.string()),
            pa.array(out_confidence, pa.float64()),
            pa.array(out_routing_tier, pa.string()),
            pa.array(out_rdi, pa.string()),
            pa.array(out_cmra, pa.bool_()),
        ]
        struct_col = pa.StructArray.from_arrays(struct_arrays, fields=struct_fields)
        out_table = _put_column(table, "standardized_address", struct_col)
    else:
        columns_to_append = [
            (f"{output_prefix}street1", pa.array(out_street1, pa.string())),
            (f"{output_prefix}street2", pa.array(out_street2, pa.string())),
            (f"{output_prefix}city", pa.array(out_city, pa.string())),
            (f"{output_prefix}state", pa.array(out_state, pa.string())),
            (f"{output_prefix}postal_code", pa.array(out_postal_code, pa.string())),
            (f"{output_prefix}country", pa.array(out_country, pa.string())),
            (f"{output_prefix}normalized_address_key", pa.array(out_key, pa.string())),
            (f"{output_prefix}building_key", pa.array(out_bldg_key, pa.string())),
            (f"{output_prefix}phonetic_key", pa.array(out_phonetic_key, pa.string())),
            (f"{output_prefix}address_status", pa.array(out_status, pa.string())),
            (f"{output_prefix}deliverability", pa.array(out_deliverability, pa.string())),
            (f"{output_prefix}latitude", pa.array(out_lat, pa.float64())),
            (f"{output_prefix}longitude", pa.array(out_lon, pa.float64())),
            (f"{output_prefix}precision", pa.array(out_precision, pa.string())),
            (f"{output_prefix}accuracy_radius_meters", pa.array(out_accuracy_radius, pa.float64())),
            (f"{output_prefix}census_tract", pa.array(out_census_tract, pa.string())),
            (f"{output_prefix}fips_code", pa.array(out_fips_code, pa.string())),
            (f"{output_prefix}confidence_score", pa.array(out_confidence, pa.float64())),
            (f"{output_prefix}routing_tier", pa.array(out_routing_tier, pa.string())),
            (f"{output_prefix}rdi", pa.array(out_rdi, pa.string())),
            (f"{output_prefix}cmra", pa.array(out_cmra, pa.bool_())),
        ]
        out_table = table
        for name, col_arr in columns_to_append:
            out_table = _put_column(out_table, name, col_arr)

    if is_batch:
        # A RecordBatch in, a RecordBatch out - including the zero-row case (which has no batches to return).
        combined = out_table.combine_chunks()
        batches = combined.to_batches()
        if batches:
            return batches[0]
        return pa.RecordBatch.from_arrays(
            [pa.array([], type=field.type) for field in combined.schema], schema=combined.schema
        )
    return out_table


def _put_column(table: Any, name: str, column: Any) -> Any:
    """Append ``column``, replacing an existing column of the same name (so re-applying never duplicates)."""
    idx = table.schema.get_field_index(name)
    if idx >= 0:
        return table.set_column(idx, name, column)
    return table.append_column(name, column)


# ============================================================================
# Polars Plugin
# ============================================================================

def standardize_polars(
    df: Any,
    street1_col: str = "street1",
    street2_col: Optional[str] = None,
    city_col: Optional[str] = "city",
    state_col: Optional[str] = "state",
    postal_code_col: Optional[str] = "postal_code",
    country_col: Optional[str] = None,
    enable_geocoding: bool = False,
    enable_fuzzy: bool = True,
    allow_locality: bool = False,
    output_prefix: str = "std_",
    as_struct: bool = False,
) -> Any:
    """
    Standardize addresses in a Polars DataFrame or LazyFrame.
    """
    global pl
    if pl is _UNSET:
        try:
            import polars as _pl

            pl = _pl
        except ImportError:
            pl = None
    if pl is None:
        raise ImportError("polars is required to use standardize_polars. Install with `pip install polars`.")

    is_lazy = isinstance(df, pl.LazyFrame)
    concrete_df = df.collect() if is_lazy else df

    arrow_tbl = concrete_df.to_arrow()
    res_arrow = standardize_arrow(
        arrow_tbl,
        street1_col=street1_col,
        street2_col=street2_col,
        city_col=city_col,
        state_col=state_col,
        postal_code_col=postal_code_col,
        country_col=country_col,
        enable_geocoding=enable_geocoding,
        enable_fuzzy=enable_fuzzy,
        allow_locality=allow_locality,
        output_prefix=output_prefix,
        as_struct=as_struct,
    )
    res_df = pl.from_arrow(res_arrow)
    return res_df.lazy() if is_lazy else res_df


# ============================================================================
# DuckDB SQL UDF Registration
# ============================================================================

def register_duckdb_udfs(connection: Optional[Any] = None) -> Any:
    """
    Register Address Standardizer scalar and struct UDFs in a DuckDB connection.

    Registered SQL Functions:
      - standardize_address(street1, city, state, postal_code) -> STRUCT
      - standardize_address_full(street1, street2, city, state, postal_code, country) -> STRUCT
      - standardize_address_text(address_text) -> STRUCT
      - standardize_address_key(street1, city, state, postal_code) -> VARCHAR
      - standardize_address_key_text(address_text) -> VARCHAR
      - standardize_deliverability(street1, city, state, postal_code) -> VARCHAR
      - standardize_deliverability_text(address_text) -> VARCHAR
    """
    global duckdb
    if duckdb is _UNSET:
        try:
            import duckdb as _duckdb

            duckdb = _duckdb
        except ImportError:
            duckdb = None
    if duckdb is None:
        raise ImportError("duckdb is required to use register_duckdb_udfs. Install with `pip install duckdb`.")

    con = connection or duckdb.default_connection()

    struct_type_str = (
        "STRUCT("
        "street1 VARCHAR, "
        "street2 VARCHAR, "
        "city VARCHAR, "
        "state VARCHAR, "
        "postal_code VARCHAR, "
        "country VARCHAR, "
        "normalized_address_key VARCHAR, "
        "building_key VARCHAR, "
        "address_status VARCHAR, "
        "deliverability VARCHAR, "
        "latitude DOUBLE, "
        "longitude DOUBLE, "
        "precision VARCHAR, "
        "confidence_score DOUBLE, "
        "rdi VARCHAR, "
        "cmra BOOLEAN"
        ")"
    )

    def _std_dict(res: Any) -> Dict[str, Any]:
        return {
            "street1": res.street1 or "",
            "street2": res.street2 or "",
            "city": res.city or "",
            "state": res.state or "",
            "postal_code": res.postal_code or "",
            "country": res.country or "",
            "normalized_address_key": res.normalized_address_key or "",
            "building_key": res.building_key or "",
            "address_status": res.address_status or "",
            "deliverability": res.deliverability or "UNDELIVERABLE",
            "latitude": float(res.latitude) if res.latitude is not None else None,
            "longitude": float(res.longitude) if res.longitude is not None else None,
            "precision": res.precision or "",
            "confidence_score": float(res.confidence_score) if res.confidence_score is not None else None,
            "rdi": res.rdi or "Unknown",
            "cmra": bool(res.cmra),
        }

    # 1. 4-arg struct function: standardize_address(street1, city, state, postal_code)
    def udf_standardize_4(s1, city, state, postal):
        if all(v is None for v in (s1, city, state, postal)):
            return None
        res = standardize_address(
            street1=str(s1 or "") if s1 is not None else "",
            city=str(city or "") if city is not None else "",
            state=str(state or "") if state is not None else "",
            postal_code=str(postal or "") if postal is not None else "",
            enable_geocoding=True,
        )
        return _std_dict(res)

    con.create_function(
        "standardize_address",
        udf_standardize_4,
        parameters=["VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR"],
        return_type=struct_type_str,
        null_handling="special",
    )

    # 2. 6-arg struct function: standardize_address_full(street1, street2, city, state, postal_code, country)
    def udf_standardize_6(s1, s2, city, state, postal, country):
        if all(v is None for v in (s1, s2, city, state, postal, country)):
            return None
        res = standardize_address(
            street1=str(s1 or "") if s1 is not None else "",
            street2=str(s2 or "") if s2 is not None else "",
            city=str(city or "") if city is not None else "",
            state=str(state or "") if state is not None else "",
            postal_code=str(postal or "") if postal is not None else "",
            country=str(country or "") if country is not None else "",
            enable_geocoding=True,
        )
        return _std_dict(res)

    con.create_function(
        "standardize_address_full",
        udf_standardize_6,
        parameters=["VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR"],
        return_type=struct_type_str,
        null_handling="special",
    )

    # 3. 1-arg struct function: standardize_address_text(address_text)
    def udf_standardize_text(addr_text):
        if addr_text is None:
            return None
        res = standardize_address(
            street1=str(addr_text or "") if addr_text is not None else "",
            enable_geocoding=True,
        )
        return _std_dict(res)

    con.create_function(
        "standardize_address_text",
        udf_standardize_text,
        parameters=["VARCHAR"],
        return_type=struct_type_str,
        null_handling="special",
    )

    # 4. Scalar address key functions
    def udf_key_4(s1, city, state, postal):
        if all(v is None for v in (s1, city, state, postal)):
            return None
        res = standardize_address(
            street1=str(s1 or "") if s1 is not None else "",
            city=str(city or "") if city is not None else "",
            state=str(state or "") if state is not None else "",
            postal_code=str(postal or "") if postal is not None else "",
        )
        return res.normalized_address_key or ""

    con.create_function(
        "standardize_address_key",
        udf_key_4,
        parameters=["VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR"],
        return_type="VARCHAR",
        null_handling="special",
    )

    def udf_key_text(addr_text):
        if addr_text is None:
            return None
        res = standardize_address(street1=str(addr_text or "") if addr_text is not None else "")
        return res.normalized_address_key or ""

    con.create_function(
        "standardize_address_key_text",
        udf_key_text,
        parameters=["VARCHAR"],
        return_type="VARCHAR",
        null_handling="special",
    )

    # 5. Deliverability classification functions
    def udf_deliv_4(s1, city, state, postal):
        if all(v is None for v in (s1, city, state, postal)):
            return None
        res = standardize_address(
            street1=str(s1 or "") if s1 is not None else "",
            city=str(city or "") if city is not None else "",
            state=str(state or "") if state is not None else "",
            postal_code=str(postal or "") if postal is not None else "",
        )
        return res.deliverability or "UNDELIVERABLE"

    con.create_function(
        "standardize_deliverability",
        udf_deliv_4,
        parameters=["VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR"],
        return_type="VARCHAR",
        null_handling="special",
    )

    def udf_deliv_text(addr_text):
        if addr_text is None:
            return None
        res = standardize_address(street1=str(addr_text or "") if addr_text is not None else "")
        return res.deliverability or "UNDELIVERABLE"

    con.create_function(
        "standardize_deliverability_text",
        udf_deliv_text,
        parameters=["VARCHAR"],
        return_type="VARCHAR",
        null_handling="special",
    )

    return con
