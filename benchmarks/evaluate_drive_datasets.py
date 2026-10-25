"""Comprehensive Google Drive Dataset Benchmark Evaluation Harness.

Satisfies Requirement R2:
- Dynamic discovery of dataset files in `.drive_datasets/` (.csv, .tsv, .parquet, .jsonl).
- Automatic detection of phone columns and geographic context columns.
- Single-record evaluation with `standardize_phone()` including address context.
- High-throughput batch dispatch evaluation with `standardize_batch_e164_dispatch()`.
- Strict Rust PyO3 vs pure Python parity verification.
- Actionable vs. garbage failure mode taxonomy classification.
- Baseline metrics serialization to JSON and publication to Markdown.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return p.parent.parent


REPO_ROOT = _find_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import polars as pl  # noqa: E402

from entity_standardizer import (  # noqa: E402
    PhoneRiskFlag,
    PhoneRoutingTier,
    StandardizedPhone,
    standardize_phone,
)
import entity_standardizer._native_dispatch as nd  # noqa: E402

# -----------------------------------------------------------------------------
# Column Auto-Detection Patterns
# -----------------------------------------------------------------------------

_PHONE_COL_EXCLUDE = re.compile(
    r"^do[\s_-]*not|(?:[\s_-]+|[a-z0-9])(?:type|carrier|flag|valid|status|id|verified|opt_in|opt-in|consent|count|desc|ts|update|donotcall|do_not_call|ext|extension)$",
    re.IGNORECASE,
)

_DATE_PATTERNS = re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}|^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
)

_NON_PHONE_COL = re.compile(
    r"(?:date|time|url|link|email|mail|name|desc|note|comment|title|crd|cik|npn|addr|street|city|state|zip|country|custodian|exam|license|aum|asset|account|client|total|average|avg|change|cagr|sma|revenue|rep|employee|year|age|lat|lon|pct|percent)",
    re.IGNORECASE,
)

_PHONE_PATTERN = re.compile(
    r"^\+?[0-9\s\(\)\-\.\/]{7,25}(?:(?:x|ext|#)\s*\d+)?$",
    re.IGNORECASE,
)

_PHONE_COL_INCLUDE = re.compile(
    r"(?:.*(?:phone|telephon|mobile|cellular|cell_no|cell_num|tel_no|tel_num|fax|contact_no|contact_num|direct_dial)|^(?:tel|cell|fax)$)",
    re.IGNORECASE,
)

_CONTEXT_PATTERNS = {
    "country": re.compile(
        r"(?:^|[\s_])(?:country|country_code|country_iso2|country_iso3|country_name|country[\s_]+id|cntry|c_code|nation)$",
        re.IGNORECASE,
    ),
    "state": re.compile(
        r"(?:^|[\s_]|branch|home|office|mainoffice)(?:state|state_code|state_abbr|state[\s_]+province|province|province_code|region)$",
        re.IGNORECASE,
    ),
    "postal_code": re.compile(
        r"(?:^|[\s_]|branch|home|office|mainoffice)(?:postal_code|postalcode|postal[\s_]+code(?:[\s_]+1)?|zip|zip_code|zipcode|zip5|postcode|pincode)$",
        re.IGNORECASE,
    ),
    "city": re.compile(
        r"(?:^|[\s_]|branch|home|office|mainoffice)(?:city|municipality|town|locality)$",
        re.IGNORECASE,
    ),
    "address": re.compile(
        r"(?:^|[\s_]|branch|home|office|mainoffice)(?:address|address1|address_1|address[\s_]+line[\s_]*1|addr1|street|street_address|line1)$",
        re.IGNORECASE,
    ),
}

_GARBAGE_PLACEHOLDERS = frozenset(
    {
        "N/A",
        "NA",
        "NONE",
        "NULL",
        "UNKNOWN",
        "NO PHONE",
        "DECLINED",
        "REFUSED",
        "NOT PROVIDED",
        "DO NOT CALL",
        "TBD",
        "PENDING",
        "TEST",
        "DEFAULT",
        "SAME AS ABOVE",
        "N / A",
        "0",
        "-",
        "--",
        ".",
    }
)

_TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)\b", re.IGNORECASE)


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------


@dataclass
class FailureTaxonomyReport:
    """Taxonomy metrics for invalid or stewardship-tier records."""

    actionable_gaps: dict[str, dict[str, Any]] = field(default_factory=dict)
    garbage_placeholders: dict[str, dict[str, Any]] = field(default_factory=dict)
    review_risks: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ColumnEvaluationMetrics:
    """Benchmark metrics aggregated for a single phone column."""

    column_name: str
    total_rows: int = 0
    non_empty_rows: int = 0
    valid_count: int = 0
    valid_rate: float = 0.0

    # Routing tier counts
    auto_pass_count: int = 0
    fuzzy_review_count: int = 0
    manual_stewardship_count: int = 0

    # Distributions
    healing_action_counts: dict[str, int] = field(default_factory=dict)
    risk_flag_counts: dict[str, int] = field(default_factory=dict)
    line_type_counts: dict[str, int] = field(default_factory=dict)
    country_distribution: dict[str, int] = field(default_factory=dict)

    # Throughput
    single_record_rec_sec: float = 0.0
    batch_py_rec_sec: float = 0.0
    batch_rs_rec_sec: float = 0.0
    rust_speedup_factor: float = 0.0

    # Parity
    parity_evaluated: int = 0
    parity_matches: int = 0
    parity_rate: float = 1.0
    parity_divergences: list[dict[str, Any]] = field(default_factory=list)

    # Taxonomy
    taxonomy: FailureTaxonomyReport = field(default_factory=FailureTaxonomyReport)


@dataclass
class DatasetEvaluationMetrics:
    """Evaluation summary for a dataset file."""

    file_name: str = ""
    file_path: str = ""
    file_size_bytes: int = 0
    row_count: int = 0
    detected_phone_columns: list[str] = field(default_factory=list)
    detected_context_columns: dict[str, str | None] = field(default_factory=dict)
    column_metrics: dict[str, ColumnEvaluationMetrics] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.file_path:
            self.file_path = str(self.file_path)
            if not self.file_name:
                self.file_name = Path(self.file_path).name
        elif self.file_name and not self.file_path:
            self.file_path = self.file_name


# -----------------------------------------------------------------------------
# Column Auto-Detection & Schema Inspection
# -----------------------------------------------------------------------------


def detect_columns(
    df: pl.DataFrame,
) -> tuple[list[str], dict[str, str | None]]:
    """Auto-detect phone columns and geographic context columns from schema and sample data."""
    phone_cols: list[str] = []
    context_cols: dict[str, str | None] = {
        "country": None,
        "state": None,
        "postal_code": None,
        "city": None,
        "address": None,
    }

    for col in df.columns:
        # Check context columns
        for ctx_key, pattern in _CONTEXT_PATTERNS.items():
            if context_cols[ctx_key] is None and pattern.search(col):
                context_cols[ctx_key] = col

        # Check phone columns
        if _PHONE_COL_EXCLUDE.search(col):
            continue
        if _PHONE_COL_INCLUDE.search(col):
            phone_cols.append(col)
            continue

        # Data-level fallback sampling
        if _NON_PHONE_COL.search(col) or col in context_cols.values():
            continue

        dtype = df.schema.get(col)
        if dtype in (pl.String, pl.Utf8, pl.Object):
            sample_values = (
                df[col]
                .drop_nulls()
                .head(50)
                .to_list()
            )
            if sample_values:
                phone_like_hits = 0
                for val in sample_values:
                    v_str = str(val).strip()
                    if _DATE_PATTERNS.match(v_str):
                        continue
                    if _PHONE_PATTERN.match(v_str):
                        digits = sum(c.isdigit() for c in v_str)
                        if 7 <= digits <= 15:
                            phone_like_hits += 1
                if phone_like_hits / len(sample_values) >= 0.35:
                    phone_cols.append(col)

    return phone_cols, context_cols


# -----------------------------------------------------------------------------
# Failure Taxonomy Classifier
# -----------------------------------------------------------------------------


def classify_record_failure(
    raw: str,
    std: StandardizedPhone,
    py_batch: str | None,
    rs_batch: str | None,
) -> tuple[str, str, str]:
    """Classify an invalid, review-tier, or divergent phone record into taxonomy codes.

    Returns:
        (category, code, description) where category is ACTIONABLE_GAP, GARBAGE_PLACEHOLDER, or REVIEW_RISK.
    """
    # 1. Check Rust/Python parity divergence
    if py_batch != rs_batch:
        return (
            "ACTIONABLE_GAP",
            "ACTIONABLE_RUST_PYTHON_PARITY_GAP",
            "Discrepancy between compiled Rust PyO3 and pure Python batch output",
        )

    # 2. Check if valid with auto-pass
    if std.is_valid and std.routing_tier == PhoneRoutingTier.AUTO_PASS:
        return ("PASS", "AUTO_PASS", "Standardized and verified valid")

    # 3. Check review-tier valid phones
    if std.is_valid:
        if PhoneRiskFlag.FICTITIOUS_RANGE in std.risk_flags:
            return (
                "REVIEW_RISK",
                "REVIEW_FICTITIOUS_RANGE",
                "Valid format but within official fictitious or TV/drama reserved range",
            )
        if PhoneRiskFlag.PREMIUM_RATE_IRSF_RISK in std.risk_flags:
            return (
                "REVIEW_RISK",
                "REVIEW_PREMIUM_IRSF_RISK",
                "Valid premium-rate or toll fraud IRSF high-risk number",
            )
        if PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in std.risk_flags:
            return (
                "REVIEW_RISK",
                "REVIEW_COUNTRY_MISMATCH",
                "Number country calling code contradicts provided address country context",
            )
        return (
            "REVIEW_RISK",
            "REVIEW_FUZZY",
            "Valid phone requiring data stewardship review",
        )

    # 4. Analyze invalid records
    raw_clean = (raw or "").strip().upper()
    digits = "".join(c for c in raw_clean if c.isdigit())

    # Garbage checks
    if raw_clean in _GARBAGE_PLACEHOLDERS or len(raw_clean) == 0:
        return (
            "GARBAGE_PLACEHOLDER",
            "GARBAGE_TEXT_PLACEHOLDER",
            "Non-telephony text placeholder, null representation, or empty string",
        )

    if _TIME_RANGE_RE.search(raw_clean):
        return (
            "GARBAGE_PLACEHOLDER",
            "GARBAGE_TIME_OR_DATE",
            "Operating hours or timestamp range accidentally populated into phone field",
        )

    if digits and len(set(digits)) == 1 and len(digits) >= 4:
        return (
            "GARBAGE_PLACEHOLDER",
            "GARBAGE_ALL_ZEROS_OR_ONES",
            "All identical repeated placeholder digits (e.g. 000-000-0000, 999-999-9999)",
        )

    if any(seq in digits for seq in ("0123456", "1234567", "2345678", "9876543", "8765432")):
        return (
            "GARBAGE_PLACEHOLDER",
            "GARBAGE_SEQUENTIAL_OR_TEST",
            "Ascending or descending sequential test pattern",
        )

    if len(digits) < 7:
        return (
            "GARBAGE_PLACEHOLDER",
            "GARBAGE_INSUFFICIENT_DIGITS",
            "Fewer than 7 digits without emergency or short-code classification",
        )

    # Actionable gap checks
    if re.search(r"[A-Za-z]{3,}", raw_clean) and not std.vanity_alias:
        return (
            "ACTIONABLE_GAP",
            "ACTIONABLE_VANITY_GAP",
            "Contains alphanumeric vanity letters not successfully folded",
        )

    if re.search(r"\s*(?:/|//|;|or|and)\s*", raw_clean) and len(digits) >= 14:
        return (
            "ACTIONABLE_GAP",
            "ACTIONABLE_MULTI_NUMBER_CONCAT",
            "Multiple complete phone numbers concatenated in a single string",
        )

    if re.search(r"(?i)\b(?:ext|x|#|opt|option|line)\b", raw_clean) and not std.extension:
        return (
            "ACTIONABLE_GAP",
            "ACTIONABLE_EXTENSION_FORMAT_GAP",
            "Unrecognized extension syntax or trailing delimiter",
        )

    if len(digits) == 7:
        return (
            "ACTIONABLE_GAP",
            "ACTIONABLE_LOCAL_NANP_7_DIGIT",
            "7-digit local subscriber number lacking NPA area code",
        )

    if digits.startswith("0") and 9 <= len(digits) <= 11 and std.country_iso2 == "US":
        return (
            "ACTIONABLE_GAP",
            "ACTIONABLE_COUNTRY_OR_TRUNK_GAP",
            "Leading zero trunk indicates international number lacking country prefix or context",
        )

    if len(digits) > 15:
        return (
            "GARBAGE_PLACEHOLDER",
            "GARBAGE_EXCESSIVE_DIGITS",
            "Excessive digits (> 15) exceeding ITU-T E.164 maximum capacity",
        )

    return (
        "ACTIONABLE_GAP",
        "ACTIONABLE_DIAL_PLAN_OR_METADATA_GAP",
        "Number structure rejected by current national dial-plan tables or validation regex",
    )


# -----------------------------------------------------------------------------
# Batch Dispatch Parity & Execution Helpers
# -----------------------------------------------------------------------------


def run_batch_python(inputs: list[str], default_calling_code: str = "1") -> list[str | None]:
    """Execute pure Python batch dispatch by temporarily unsetting native module."""
    orig_mod = nd._native_mod
    nd._native_mod = None
    try:
        return nd.standardize_batch_e164_dispatch(inputs, default_calling_code=default_calling_code)
    finally:
        nd._native_mod = orig_mod


def run_batch_rust(inputs: list[str], default_calling_code: str = "1") -> list[str | None]:
    """Execute compiled native Rust PyO3 batch dispatch."""
    if nd._native_mod is not None:
        return list(nd._native_mod.standardize_batch_e164_rs(inputs, default_calling_code))
    return run_batch_python(inputs, default_calling_code=default_calling_code)


# -----------------------------------------------------------------------------
# Evaluation Engine
# -----------------------------------------------------------------------------


def evaluate_column(
    df: pl.DataFrame,
    phone_col: str,
    context_cols: dict[str, str | None],
    batch_size: int = 10000,
    max_sample_failures: int = 10,
) -> ColumnEvaluationMetrics:
    """Evaluate a single phone column end-to-end, collecting accuracy, throughput, parity, and taxonomy."""
    total_rows = len(df)
    metrics = ColumnEvaluationMetrics(column_name=phone_col, total_rows=total_rows)

    healing_counter: Counter[str] = Counter()
    risk_counter: Counter[str] = Counter()
    line_type_counter: Counter[str] = Counter()
    country_counter: Counter[str] = Counter()

    # Taxonomy containers: code -> {"count": int, "description": str, "examples": list[str]}
    actionable_map: dict[str, dict[str, Any]] = {}
    garbage_map: dict[str, dict[str, Any]] = {}
    review_map: dict[str, dict[str, Any]] = {}

    non_empty_indices: list[int] = []
    raw_phones: list[str] = []
    contexts: list[dict[str, Any]] = []

    # Extract non-empty rows
    phone_list = df[phone_col].to_list()
    ctx_lists = {
        k: df[c_name].to_list()
        for k, c_name in context_cols.items()
        if c_name and c_name in df.columns
    }
    for idx, raw_val in enumerate(phone_list):
        if raw_val is not None:
            v_str = str(raw_val).strip()
            if v_str:
                non_empty_indices.append(idx)
                raw_phones.append(v_str)

                # Extract context row
                ctx_dict: dict[str, Any] = {}
                for k, c_vals in ctx_lists.items():
                    v = c_vals[idx]
                    if v is not None:
                        vs = str(v).strip()
                        if vs:
                            ctx_dict[k] = vs
                contexts.append(ctx_dict)

    metrics.non_empty_rows = len(raw_phones)
    if not metrics.non_empty_rows:
        return metrics

    # 1. Measure Throughput & Output of Pure Python Batch
    start_py = time.perf_counter()
    batch_py_results: list[str | None] = []
    for i in range(0, len(raw_phones), batch_size):
        chunk = raw_phones[i : i + batch_size]
        batch_py_results.extend(run_batch_python(chunk))
    time_py = max(1e-9, time.perf_counter() - start_py)
    metrics.batch_py_rec_sec = round(len(raw_phones) / time_py, 2)

    # 2. Measure Throughput & Output of Compiled Rust PyO3 Batch
    start_rs = time.perf_counter()
    batch_rs_results: list[str | None] = []
    for i in range(0, len(raw_phones), batch_size):
        chunk = raw_phones[i : i + batch_size]
        batch_rs_results.extend(run_batch_rust(chunk))
    time_rs = max(1e-9, time.perf_counter() - start_rs)
    metrics.batch_rs_rec_sec = round(len(raw_phones) / time_rs, 2)
    metrics.rust_speedup_factor = round(metrics.batch_rs_rec_sec / max(1.0, metrics.batch_py_rec_sec), 2)

    # 3. Measure Single-Record Standardization with Context & Aggregate Metrics
    start_single = time.perf_counter()
    single_results: list[StandardizedPhone] = []

    for raw, ctx in zip(raw_phones, contexts):
        cntry_hint = ctx.get("country")
        res = standardize_phone(
            raw,
            country=cntry_hint,
            default_country="US",
            address_context=ctx,
        )
        single_results.append(res)

        if res.is_valid:
            metrics.valid_count += 1
        if res.routing_tier == PhoneRoutingTier.AUTO_PASS:
            metrics.auto_pass_count += 1
        elif res.routing_tier == PhoneRoutingTier.FUZZY_REVIEW:
            metrics.fuzzy_review_count += 1
        else:
            metrics.manual_stewardship_count += 1

        for act in res.healing_actions:
            healing_counter[act] += 1
        for flag in res.risk_flags:
            risk_counter[flag] += 1
        if res.line_type:
            line_type_counter[res.line_type] += 1
        if res.country_iso2:
            country_counter[res.country_iso2] += 1

    time_single = max(1e-9, time.perf_counter() - start_single)
    metrics.single_record_rec_sec = round(len(raw_phones) / time_single, 2)
    metrics.valid_rate = round(metrics.valid_count / len(raw_phones), 4)

    # 4. Parity Check & Failure Taxonomy Classification
    parity_matches = 0
    divergences: list[dict[str, Any]] = []

    for idx, (raw, std, py_res, rs_res) in enumerate(
        zip(raw_phones, single_results, batch_py_results, batch_rs_results)
    ):
        # Parity comparison
        if py_res == rs_res:
            parity_matches += 1
        else:
            if len(divergences) < max_sample_failures:
                divergences.append(
                    {
                        "row_index": non_empty_indices[idx],
                        "raw_input": raw,
                        "py_output": py_res,
                        "rs_output": rs_res,
                    }
                )

        # Failure classification
        cat, code, desc = classify_record_failure(raw, std, py_res, rs_res)
        if cat != "PASS":
            target_map = (
                actionable_map
                if cat == "ACTIONABLE_GAP"
                else garbage_map
                if cat == "GARBAGE_PLACEHOLDER"
                else review_map
            )
            if code not in target_map:
                target_map[code] = {
                    "count": 0,
                    "description": desc,
                    "examples": [],
                }
            target_map[code]["count"] += 1
            if len(target_map[code]["examples"]) < max_sample_failures and raw not in target_map[code]["examples"]:
                target_map[code]["examples"].append(raw)

    metrics.parity_evaluated = len(raw_phones)
    metrics.parity_matches = parity_matches
    metrics.parity_rate = round(parity_matches / max(1, len(raw_phones)), 6)
    metrics.parity_divergences = divergences

    metrics.healing_action_counts = dict(healing_counter.most_common())
    metrics.risk_flag_counts = dict(risk_counter.most_common())
    metrics.line_type_counts = dict(line_type_counter.most_common())
    metrics.country_distribution = dict(country_counter.most_common(10))

    metrics.taxonomy.actionable_gaps = actionable_map
    metrics.taxonomy.garbage_placeholders = garbage_map
    metrics.taxonomy.review_risks = review_map

    return metrics


def _resolve_column_context(
    phone_col: str,
    base_context: dict[str, str | None],
    all_columns: list[str],
) -> dict[str, str | None]:
    """Resolve prefix-specific context columns (Firm, MainOffice, Office, Branch, Home, HQMailing) for a phone column."""
    col_context = dict(base_context)
    col_lower = phone_col.lower()
    col_set = set(all_columns)

    if "firm" in col_lower:
        for k, v in base_context.items():
            firm_candidate = f"Firm {v}" if v else None
            if firm_candidate and firm_candidate in col_set:
                col_context[k] = firm_candidate

    prefix_candidates: list[str] = []
    if col_lower.startswith("home_"):
        prefix_candidates = ["Home_"]
    elif col_lower.startswith("home"):
        prefix_candidates = ["Home"]
    elif col_lower.startswith("branch_"):
        prefix_candidates = ["Branch_"]
    elif col_lower.startswith("branch"):
        prefix_candidates = ["Branch"]
    elif col_lower.startswith("office_"):
        prefix_candidates = ["Office_"]
    elif col_lower.startswith("mainoffice_"):
        prefix_candidates = ["MainOffice_"]
    elif col_lower.startswith("hq_"):
        prefix_candidates = ["HQ_", "HQMailing_"]

    suffix_map = {
        "country": ["Country", "CountryID", "Country_ID"],
        "state": ["State", "StateProvince", "Province"],
        "postal_code": ["ZipCode", "Zip", "PostalCode"],
        "city": ["City"],
        "address": ["Address1", "Addr1", "Address"],
    }
    for pfx in prefix_candidates:
        for k, suffixes in suffix_map.items():
            for sfx in suffixes:
                cand = f"{pfx}{sfx}"
                if cand in col_set:
                    col_context[k] = cand
                    break

    return col_context


def _read_csv_with_fallback(
    file_path: Path,
    separator: str = ",",
    n_rows: int | None = None,
    columns: list[str] | None = None,
) -> pl.DataFrame:
    """Read a CSV/TSV/TXT file via Polars with lossless String schema and backslash-escaped quote fallback."""
    try:
        return pl.read_csv(
            file_path,
            separator=separator,
            n_rows=n_rows,
            columns=columns,
            ignore_errors=True,
            truncate_ragged_lines=True,
            encoding="utf8-lossy",
            infer_schema_length=0,
        )
    except Exception:
        if file_path.name.endswith(".gz"):
            import gzip

            with gzip.open(file_path, "rb") as f:
                raw_data = f.read()
        else:
            with file_path.open("rb") as f:
                raw_data = f.read()
        clean_bytes = (
            raw_data.replace(b'\\"', b'""')
            .decode("utf-8", errors="replace")
            .encode("utf-8")
        )
        return pl.read_csv(
            clean_bytes,
            separator=separator,
            n_rows=n_rows,
            columns=columns,
            ignore_errors=True,
            truncate_ragged_lines=True,
            encoding="utf8-lossy",
            infer_schema_length=0,
        )


def evaluate_dataset_file(
    file_path: Path,
    batch_size: int = 10000,
    max_rows: int | None = None,
) -> DatasetEvaluationMetrics:
    """Load and evaluate all phone columns in a dataset file."""
    try:
        file_size = file_path.stat().st_size
    except Exception as exc:
        print(f"  [!] Warning: Could not access {file_path.name}: {exc}. Skipping.")
        return DatasetEvaluationMetrics(
            file_name=file_path.name,
            file_path=str(file_path),
            file_size_bytes=0,
            row_count=0,
        )

    if file_size == 0:
        print(f"  [!] Warning: Skipping 0-byte file: {file_path.name}")
        return DatasetEvaluationMetrics(
            file_name=file_path.name,
            file_path=str(file_path),
            file_size_bytes=0,
            row_count=0,
        )

    suffix = file_path.suffix.lower()

    try:
        # Load dataset via Polars
        if suffix in (".parquet", ".pq"):
            df = pl.read_parquet(file_path, n_rows=max_rows)
            phone_cols, context_cols = detect_columns(df)
            all_cols = list(df.columns)
        elif suffix in (".jsonl", ".ndjson") or file_path.name.endswith(".jsonl.gz"):
            try:
                df = pl.read_ndjson(file_path, n_rows=max_rows, ignore_errors=True)
            except Exception:
                if file_path.name.endswith(".gz"):
                    import gzip

                    with gzip.open(file_path, "rb") as f:
                        raw_data = f.read()
                else:
                    with file_path.open("rb") as f:
                        raw_data = f.read()
                clean_bytes = raw_data.decode("utf-8", errors="replace").encode("utf-8")
                df = pl.read_ndjson(clean_bytes, n_rows=max_rows, ignore_errors=True)
            phone_cols, context_cols = detect_columns(df)
            all_cols = list(df.columns)
        else:
            sep = "\t" if (suffix in (".tsv", ".tab") or file_path.name.endswith(".tsv.gz")) else ","
            sample_df = _read_csv_with_fallback(file_path, separator=sep, n_rows=100)
            all_cols = list(sample_df.columns)
            phone_cols, context_cols = detect_columns(sample_df)
            needed_cols: list[str] = []
            for c in phone_cols:
                if c not in needed_cols:
                    needed_cols.append(c)
                c_ctx = _resolve_column_context(c, context_cols, all_cols)
                for ctx_col in c_ctx.values():
                    if ctx_col and ctx_col in all_cols and ctx_col not in needed_cols:
                        needed_cols.append(ctx_col)
            for ctx_col in context_cols.values():
                if ctx_col and ctx_col in all_cols and ctx_col not in needed_cols:
                    needed_cols.append(ctx_col)
            if not needed_cols and all_cols:
                needed_cols = [all_cols[0]]
            df = _read_csv_with_fallback(
                file_path,
                separator=sep,
                n_rows=max_rows,
                columns=needed_cols or None,
            )

        dataset_metrics = DatasetEvaluationMetrics(
            file_name=file_path.name,
            file_path=str(file_path),
            file_size_bytes=file_size,
            row_count=len(df),
            detected_phone_columns=phone_cols,
            detected_context_columns=context_cols,
        )

        for col in phone_cols:
            col_context = _resolve_column_context(col, context_cols, all_cols)
            col_metrics = evaluate_column(
                df,
                phone_col=col,
                context_cols=col_context,
                batch_size=batch_size,
            )
            dataset_metrics.column_metrics[col] = col_metrics

        return dataset_metrics

    except Exception as exc:
        print(f"  [!] Warning: Failed to evaluate {file_path.name}: {exc}. Skipping.")
        return DatasetEvaluationMetrics(
            file_name=file_path.name,
            file_path=str(file_path),
            file_size_bytes=file_size,
            row_count=0,
        )



# -----------------------------------------------------------------------------
# Dynamic File Discovery
# -----------------------------------------------------------------------------


def discover_dataset_files(datasets_dir: Path) -> list[Path]:
    """Find all supported tabular dataset files in datasets_dir."""
    if not datasets_dir.is_dir():
        return []

    valid_extensions = {".csv", ".tsv", ".tab", ".txt", ".parquet", ".pq", ".jsonl", ".ndjson", ".gz"}
    found: list[Path] = []
    for root, _, files in os.walk(datasets_dir):
        for f in sorted(files):
            p = Path(root) / f
            if p.name.startswith((".", "_")):
                continue
            if any(p.name.lower().endswith(ext) for ext in valid_extensions):
                found.append(p)
    return sorted(found)


# -----------------------------------------------------------------------------
# Markdown Report Generation
# -----------------------------------------------------------------------------


def generate_markdown_report(
    results: dict[str, Any],
    output_path: Path,
) -> None:
    """Generate comprehensive GitHub-flavored Markdown benchmark report."""
    md: list[str] = []
    summary = results.get("summary", {})

    md.append("# Google Drive Telephony Dataset Benchmark Report")
    md.append("")
    md.append(f"**Execution Timestamp:** {results.get('timestamp', 'N/A')}  ")
    md.append(f"**Engine Mode:** {results.get('system_info', {}).get('engine', 'N/A')}  ")
    md.append(f"**Total Datasets Evaluated:** {summary.get('total_datasets', 0)}  ")
    md.append(f"**Total Records Processed:** {summary.get('total_rows_evaluated', 0):,}  ")
    md.append(f"**Overall Non-Empty Phone Inputs:** {summary.get('total_phone_inputs', 0):,}  ")
    md.append(f"**Overall Valid Yield:** {summary.get('overall_valid_rate', 0.0) * 100:.2f}%  ")
    md.append(f"**Rust/Python Parity Rate:** {summary.get('rust_python_parity_rate', 1.0) * 100:.4f}%  ")
    md.append("")
    md.append("---")
    md.append("")

    # 1. Dataset Inventory Table
    md.append("## 1. Dataset Inventory & Schema Discovery")
    md.append("")
    md.append("| Dataset File | Format | File Size | Row Count | Phone Columns | Geographic Context Columns |")
    md.append("|---|---|---|---|---|---|")
    for d_name, d_data in results.get("datasets", {}).items():
        size_mb = d_data.get("file_size_bytes", 0) / (1024 * 1024)
        p_cols = ", ".join(f"`{c}`" for c in d_data.get("detected_phone_columns", [])) or "*None*"
        ctx_list = [f"{k}=`{v}`" for k, v in d_data.get("detected_context_columns", {}).items() if v]
        ctx_str = ", ".join(ctx_list) if ctx_list else "*None*"
        fmt = Path(d_name).suffix.upper().lstrip(".")
        md.append(
            f"| `{d_name}` | {fmt} | {size_mb:.2f} MB | {d_data.get('row_count', 0):,} | {p_cols} | {ctx_str} |"
        )
    md.append("")

    # 2. Empirical Baseline Metrics Table
    md.append("## 2. Empirical Baseline Standardization Metrics")
    md.append("")
    md.append("| Dataset | Phone Column | Rows | Non-Empty | Valid Count | Valid Rate | Auto-Pass % | Fuzzy Review % | Manual Stewardship % |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for d_name, d_data in results.get("datasets", {}).items():
        for col_name, c_data in d_data.get("column_metrics", {}).items():
            non_empty = c_data.get("non_empty_rows", 0)
            valid_pct = c_data.get("valid_rate", 0.0) * 100
            auto_pct = (c_data.get("auto_pass_count", 0) / max(1, non_empty)) * 100
            fuzzy_pct = (c_data.get("fuzzy_review_count", 0) / max(1, non_empty)) * 100
            manual_pct = (c_data.get("manual_stewardship_count", 0) / max(1, non_empty)) * 100
            md.append(
                f"| `{d_name}` | `{col_name}` | {c_data.get('total_rows', 0):,} | {non_empty:,} | "
                f"{c_data.get('valid_count', 0):,} | **{valid_pct:.2f}%** | {auto_pct:.1f}% | {fuzzy_pct:.1f}% | {manual_pct:.1f}% |"
            )
    md.append("")

    # 3. Throughput & Engine Performance Table
    md.append("## 3. High-Throughput Engine Benchmarking")
    md.append("")
    md.append("| Dataset | Phone Column | Single-Record Python | Batch Python | Batch Rust PyO3 | Rust Speedup |")
    md.append("|---|---|---|---|---|---|")
    for d_name, d_data in results.get("datasets", {}).items():
        for col_name, c_data in d_data.get("column_metrics", {}).items():
            single_rps = c_data.get("single_record_rec_sec", 0.0)
            batch_py = c_data.get("batch_py_rec_sec", 0.0)
            batch_rs = c_data.get("batch_rs_rec_sec", 0.0)
            speedup = c_data.get("rust_speedup_factor", 0.0)
            md.append(
                f"| `{d_name}` | `{col_name}` | {single_rps:,.0f} rec/s | {batch_py:,.0f} rec/s | **{batch_rs:,.0f} rec/s** | **{speedup:.2f}x** |"
            )
    md.append("")

    # 4. Parity Verification Table
    md.append("## 4. Rust SIMD vs. Python Batch Parity Verification")
    md.append("")
    md.append("| Dataset | Column | Records Evaluated | Exact Parity Matches | Parity Rate | Divergences |")
    md.append("|---|---|---|---|---|---|")
    for d_name, d_data in results.get("datasets", {}).items():
        for col_name, c_data in d_data.get("column_metrics", {}).items():
            eval_cnt = c_data.get("parity_evaluated", 0)
            matches = c_data.get("parity_matches", 0)
            p_rate = c_data.get("parity_rate", 1.0) * 100
            divs = len(c_data.get("parity_divergences", []))
            status = "PASS (100.00%)" if divs == 0 else f"**DIVERGENCE ({divs})**"
            md.append(
                f"| `{d_name}` | `{col_name}` | {eval_cnt:,} | {matches:,} | {p_rate:.4f}% | {status} |"
            )
    md.append("")

    # 5. Actionable Failure Modes & Remediation Opportunities
    md.append("## 5. Actionable Failure Taxonomy & Engine Remediation Gaps")
    md.append("")
    md.append("| Failure Code | Total Count | Classification | Concrete Sample Inputs | Engine Remediation Opportunity |")
    md.append("|---|---|---|---|---|")

    # Aggregate actionable gaps across datasets
    agg_actionable: dict[str, dict[str, Any]] = {}
    for d_data in results.get("datasets", {}).values():
        for c_data in d_data.get("column_metrics", {}).values():
            tax = c_data.get("taxonomy", {})
            for code, info in tax.get("actionable_gaps", {}).items():
                if code not in agg_actionable:
                    agg_actionable[code] = {
                        "count": 0,
                        "description": info.get("description", ""),
                        "examples": [],
                    }
                agg_actionable[code]["count"] += info.get("count", 0)
                for ex in info.get("examples", []):
                    if len(agg_actionable[code]["examples"]) < 5 and ex not in agg_actionable[code]["examples"]:
                        agg_actionable[code]["examples"].append(ex)

    if not agg_actionable:
        md.append("| *None* | 0 | Actionable Telephony Gap | N/A | Zero actionable gaps identified across corpus |")
    else:
        for code, info in sorted(agg_actionable.items(), key=lambda x: x[1]["count"], reverse=True):
            ex_str = "<br>".join(f"`{e}`" for e in info["examples"][:4]) or "*None*"
            remediation = _suggest_remediation(code)
            md.append(
                f"| `{code}` | {info['count']:,} | Actionable Telephony Gap | {ex_str} | {remediation} |"
            )
    md.append("")

    # 6. Garbage & Non-Telephony Placeholders Table
    md.append("## 6. Genuinely Unparseable Garbage & Non-Telephony Placeholders")
    md.append("")
    md.append("| Garbage Code | Total Count | Taxonomy Description | Sample Values |")
    md.append("|---|---|---|---|")

    agg_garbage: dict[str, dict[str, Any]] = {}
    for d_data in results.get("datasets", {}).values():
        for c_data in d_data.get("column_metrics", {}).values():
            tax = c_data.get("taxonomy", {})
            for code, info in tax.get("garbage_placeholders", {}).items():
                if code not in agg_garbage:
                    agg_garbage[code] = {
                        "count": 0,
                        "description": info.get("description", ""),
                        "examples": [],
                    }
                agg_garbage[code]["count"] += info.get("count", 0)
                for ex in info.get("examples", []):
                    if len(agg_garbage[code]["examples"]) < 5 and ex not in agg_garbage[code]["examples"]:
                        agg_garbage[code]["examples"].append(ex)

    for code, info in sorted(agg_garbage.items(), key=lambda x: x[1]["count"], reverse=True):
        ex_str = "<br>".join(f"`{e}`" for e in info["examples"][:4]) or "*None*"
        md.append(
            f"| `{code}` | {info['count']:,} | {info['description']} | {ex_str} |"
        )
    md.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(md), encoding="utf-8")


def _suggest_remediation(failure_code: str) -> str:
    """Provide specific remediation guidance for an actionable failure code."""
    suggestions = {
        "ACTIONABLE_RUST_PYTHON_PARITY_GAP": "Harmonize Rust `standardize_batch_e164_rs` and Python `decode_vanity_phone` boundary handling on conversational secondary labels.",
        "ACTIONABLE_VANITY_GAP": "Expand keypad vanity decoding to handle unhyphenated words, numeric-word mixtures, and international vanity numbers.",
        "ACTIONABLE_MULTI_NUMBER_CONCAT": "Enhance `split_primary_phone` to detect multi-number slashes and labels, extracting the primary number for standard E.164 formatting.",
        "ACTIONABLE_EXTENSION_FORMAT_GAP": "Support extended extension prefixes (`opt.`, `option`, `line`, `direct`, `ext-`, `sub`) and trailing punctuation.",
        "ACTIONABLE_LOCAL_NANP_7_DIGIT": "Leverage postal code and state context in `infer_country_from_postal_code` to infer NPA for 7-digit local subscriber numbers.",
        "ACTIONABLE_COUNTRY_OR_TRUNK_GAP": "Improve country code inference from address context or postal code when leading domestic trunk '0' is encountered.",
        "ACTIONABLE_DIAL_PLAN_OR_METADATA_GAP": "Synchronize national dialing plans with upstream ITU / libphonenumber XML metadata.",
    }
    return suggestions.get(failure_code, "Inspect failure samples and add targeted regression tests.")


# -----------------------------------------------------------------------------
# Synthetic Dataset Generator (for Verification & Offline Harness Testing)
# -----------------------------------------------------------------------------


def generate_synthetic_benchmark_datasets(target_dir: Path) -> list[Path]:
    """Generate realistic multinational telephony test datasets for offline benchmark execution."""
    target_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # 1. CSV Dataset: US & North American Enterprise Contacts
    csv_path = target_dir / "synthetic_nanp_enterprise_contacts.csv"
    nanp_records = [
        {"contact_id": "C1001", "firm_name": "Acme Corp", "phone": "(415) 555-2671", "country": "US", "state": "CA", "zip": "94105"},
        {"contact_id": "C1002", "firm_name": "Bloom Florist", "phone": "1-800-FLOWERS", "country": "US", "state": "NY", "zip": "10001"},
        {"contact_id": "C1003", "firm_name": "Injury Help", "phone": "800-4-INJURY", "country": "USA", "state": "FL", "zip": "33101"},
        {"contact_id": "C1004", "firm_name": "Direct Tech", "phone": "212.555.0299 ext. 104", "country": "US", "state": "NY", "zip": "10022"},
        {"contact_id": "C1005", "firm_name": "Downtown Branch", "phone": "555-1234", "country": "US", "state": "IL", "zip": "60601"},
        {"contact_id": "C1006", "firm_name": "Hollywood Studios", "phone": "(310) 555-0142", "country": "US", "state": "CA", "zip": "90210"},
        {"contact_id": "C1007", "firm_name": "Bad Data", "phone": "000-000-0000", "country": "US", "state": "TX", "zip": "75001"},
        {"contact_id": "C1008", "firm_name": "Missing", "phone": "N/A", "country": "US", "state": "WA", "zip": "98101"},
        {"contact_id": "C1009", "firm_name": "Call Hours", "phone": "8:00 AM - 5:00 PM", "country": "US", "state": "CO", "zip": "80202"},
        {"contact_id": "C1010", "firm_name": "Multi Line", "phone": "415-555-1212 / 415-555-5678", "country": "US", "state": "CA", "zip": "94102"},
    ] * 200  # 2,000 rows
    pl.DataFrame(nanp_records).write_csv(csv_path)
    created.append(csv_path)

    # 2. Parquet Dataset: Global Multinational Financial Telephony
    pq_path = target_dir / "synthetic_global_multinational.parquet"
    global_records = [
        {"entity_id": "E2001", "legal_name": "London Banking PLC", "telephone": "+44 (0) 20 7946 0912", "country_iso2": "GB", "postal_code": "EC2N 2DB", "city": "London"},
        {"entity_id": "E2002", "legal_name": "Berlin Capital GmbH", "telephone": "030 12345678", "country_iso2": "DE", "postal_code": "10115", "city": "Berlin"},
        {"entity_id": "E2003", "legal_name": "Paris Banque SA", "telephone": "+33 1 42 68 55 55", "country_iso2": "FR", "postal_code": "75008", "city": "Paris"},
        {"entity_id": "E2004", "legal_name": "Tokyo Securities KK", "telephone": "＋８１ ３-１２３４-５６７８", "country_iso2": "JP", "postal_code": "100-0005", "city": "Tokyo"},
        {"entity_id": "E2005", "legal_name": "Sydney Asset Mgt", "telephone": "0412 345 678", "country_iso2": "AU", "postal_code": "2000", "city": "Sydney"},
        {"entity_id": "E2006", "legal_name": "Mexico Inversiones", "telephone": "+52 1 55 8421 9034", "country_iso2": "MX", "postal_code": "06600", "city": "CDMX"},
        {"entity_id": "E2007", "legal_name": "São Paulo Fundo", "telephone": "+55 11 98765 4321", "country_iso2": "BR", "postal_code": "01310-100", "city": "São Paulo"},
        {"entity_id": "E2008", "legal_name": "Unattributed UK", "telephone": "020 7946 0912", "country_iso2": None, "postal_code": None, "city": None},
        {"entity_id": "E2009", "legal_name": "Placeholder Inc", "telephone": "NONE", "country_iso2": "US", "postal_code": "10001", "city": "New York"},
        {"entity_id": "E2010", "legal_name": "Corrupted Multi", "telephone": "Tel: (415) 555-2671 Fax: (415) 555-9999", "country_iso2": "US", "postal_code": "94105", "city": "SF"},
    ] * 200  # 2,000 rows
    pl.DataFrame(global_records).write_parquet(pq_path)
    created.append(pq_path)

    # 3. JSONL Dataset: Streaming Telephony Call Records
    jsonl_path = target_dir / "synthetic_streaming_call_logs.jsonl"
    jsonl_records = [
        {"call_id": "L3001", "caller_num": "+14155552671", "callee_num": "1-800-FLOWERS", "duration_sec": 45},
        {"call_id": "L3002", "caller_num": "011 49 30 5551234", "callee_num": "+44 20 7946 0912", "duration_sec": 120},
        {"call_id": "L3003", "caller_num": "1234567890", "callee_num": "911", "duration_sec": 15},
        {"call_id": "L3004", "caller_num": "unknown", "callee_num": "411", "duration_sec": 60},
    ] * 500  # 2,000 rows
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in jsonl_records:
            f.write(json.dumps(r) + "\n")
    created.append(jsonl_path)

    return created


# -----------------------------------------------------------------------------
# Main Execution CLI
# -----------------------------------------------------------------------------


def main() -> int:
    """Run Google Drive dataset baseline evaluation and report generation."""
    parser = argparse.ArgumentParser(
        description="Empirical Google Drive Dataset Telephony Evaluation Harness (Requirement R2)."
    )
    parser.add_argument(
        "--datasets-dir",
        type=Path,
        default=REPO_ROOT / ".drive_datasets",
        help="Directory containing downloaded dataset files (default: .drive_datasets/).",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT / "benchmarks" / "baseline_drive_datasets_results.json",
        help="Path for aggregated baseline JSON output.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=REPO_ROOT / "docs" / "GOOGLE_DRIVE_DATASET_BENCHMARK.md",
        help="Path for generated Markdown benchmark report.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch chunk size for processing (default: 10,000).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional row limit per dataset for fast sanity runs (default: None, full dataset).",
    )
    parser.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="Generate synthetic benchmark datasets if datasets directory is empty.",
    )

    args = parser.parse_args()

    print("=== Phone-Standardizer Empirical Dataset Benchmark Harness ===")
    print(f"Target datasets directory: {args.datasets_dir}")
    print(f"Engine info: {nd.get_engine_info()}")

    dataset_files = discover_dataset_files(args.datasets_dir)
    if not dataset_files:
        if args.generate_synthetic or not args.datasets_dir.exists() or len(os.listdir(args.datasets_dir)) == 0:
            print(f"[!] Datasets directory '{args.datasets_dir}' is empty.")
            print("[*] Generating synthetic multi-dataset test corpus for benchmark harness verification...")
            dataset_files = generate_synthetic_benchmark_datasets(args.datasets_dir)
        else:
            print(f"[!] No supported dataset files (.csv, .tsv, .parquet, .jsonl) found in '{args.datasets_dir}'.")
            return 1

    print(f"Found {len(dataset_files)} dataset file(s) to evaluate:")
    for f in dataset_files:
        print(f" - {f.name} ({f.stat().st_size / (1024 * 1024):.2f} MB)")

    all_results: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "benchmark_version": "1.0.0",
        "system_info": nd.get_engine_info(),
        "datasets": {},
        "summary": {
            "total_datasets": len(dataset_files),
            "total_rows_evaluated": 0,
            "total_phone_inputs": 0,
            "total_valid": 0,
            "overall_valid_rate": 0.0,
            "total_auto_pass": 0,
            "total_fuzzy_review": 0,
            "total_manual_stewardship": 0,
            "rust_python_parity_rate": 1.0,
        },
    }

    tot_rows = 0
    tot_inputs = 0
    tot_valid = 0
    tot_auto = 0
    tot_fuzzy = 0
    tot_manual = 0
    tot_parity_eval = 0
    tot_parity_matches = 0

    for file_path in dataset_files:
        print(f"\nProcessing {file_path.name}...")
        try:
            eval_metrics = evaluate_dataset_file(
                file_path,
                batch_size=args.batch_size,
                max_rows=args.max_rows,
            )
        except Exception as exc:
            print(f"  [!] Warning: Unexpected error evaluating {file_path.name}: {exc}. Skipping.")
            try:
                f_size = file_path.stat().st_size
            except Exception:
                f_size = 0
            eval_metrics = DatasetEvaluationMetrics(
                file_name=file_path.name,
                file_path=str(file_path),
                file_size_bytes=f_size,
                row_count=0,
            )

        # Convert to dictionary
        d_dict = asdict(eval_metrics)
        all_results["datasets"][file_path.name] = d_dict
        tot_rows += eval_metrics.row_count

        for col_name, c_m in eval_metrics.column_metrics.items():
            tot_inputs += c_m.non_empty_rows
            tot_valid += c_m.valid_count
            tot_auto += c_m.auto_pass_count
            tot_fuzzy += c_m.fuzzy_review_count
            tot_manual += c_m.manual_stewardship_count
            tot_parity_eval += c_m.parity_evaluated
            tot_parity_matches += c_m.parity_matches

            print(
                f"  [{col_name}] {c_m.non_empty_rows:,} non-empty | Valid: {c_m.valid_count:,} ({c_m.valid_rate * 100:.2f}%) | "
                f"Batch Py: {c_m.batch_py_rec_sec:,.0f} r/s | Batch Rust: {c_m.batch_rs_rec_sec:,.0f} r/s ({c_m.rust_speedup_factor:.1f}x) | "
                f"Parity: {c_m.parity_rate * 100:.2f}%"
            )

    all_results["summary"]["total_rows_evaluated"] = tot_rows
    all_results["summary"]["total_phone_inputs"] = tot_inputs
    all_results["summary"]["total_valid"] = tot_valid
    all_results["summary"]["overall_valid_rate"] = round(tot_valid / max(1, tot_inputs), 4)
    all_results["summary"]["total_auto_pass"] = tot_auto
    all_results["summary"]["total_fuzzy_review"] = tot_fuzzy
    all_results["summary"]["total_manual_stewardship"] = tot_manual
    all_results["summary"]["rust_python_parity_rate"] = round(
        tot_parity_matches / max(1, tot_parity_eval), 6
    )

    # Save JSON Baseline
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n[+] Wrote baseline JSON metrics to: {args.output_json}")

    # Save Markdown Benchmark Report
    generate_markdown_report(all_results, args.output_md)
    print(f"[+] Wrote markdown benchmark report to: {args.output_md}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
