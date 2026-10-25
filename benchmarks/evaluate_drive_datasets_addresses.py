#!/usr/bin/env python3
"""Comprehensive Google Drive Dataset Address Benchmark Harness.

Evaluates Entity-Standardizer (/home/jwhite/Entity-Standardizer) across all
address-bearing dataset files in .drive_datasets/ spanning all 6 suites:
  1. AdvizorPro (AP_20261019)
  2. AdvisorAtlas (AdvisorAtlas_20261019)
  3. Discovery Data (Discovery_20261019)
  4. Foursquare Open Source Places Global (Foursquare_OS_Places_Global)
  5. Overture Maps Global Places (Overture_Maps_Global_Places)
  6. Wikidata & SEC/DTCC Global Regulatory Filings (Wikidata_And_Regulatory_Global)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time

__version__ = "2.1.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import polars as pl  # noqa: E402

from entity_standardizer.address import standardize_address  # noqa: E402
from entity_standardizer.address._native_dispatch import get_engine_info  # noqa: E402


@dataclass
class AddressColumnSpec:
    """Column mapping for an address table or address group within a dataset file."""

    label: str
    street1: str | None = None
    street2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


@dataclass
class AddressEvalMetrics:
    """Aggregated Address-Standardizer metrics for a single dataset address group."""

    suite_name: str
    file_name: str
    address_label: str
    total_rows: int = 0
    non_empty_rows: int = 0
    unique_addresses: int = 0
    standardized_count: int = 0
    locality_only_count: int = 0
    parse_failed_count: int = 0
    usable_yield_rate: float = 0.0
    standardized_rate: float = 0.0
    auto_pass_count: int = 0
    fuzzy_review_count: int = 0
    manual_stewardship_count: int = 0
    deliverable_count: int = 0
    requires_secondary_count: int = 0
    undeliverable_count: int = 0
    rooftop_extracted_count: int = 0
    private_residence_count: int = 0
    registered_agent_hub_count: int = 0
    cmra_count: int = 0
    us_records: int = 0
    intl_records: int = 0
    unique_countries: int = 0
    top_countries: dict[str, int] = field(default_factory=dict)
    failure_reasons: dict[str, int] = field(default_factory=dict)
    duration_sec: float = 0.0
    effective_throughput_rec_sec: float = 0.0


def detect_address_specs(df: pl.DataFrame, file_name: str) -> list[AddressColumnSpec]:
    """Detect primary and secondary address column groups in a dataset DataFrame."""
    cols = set(df.columns)
    specs: list[AddressColumnSpec] = []

    if file_name == "AdvizorPro_Firm_20261019.csv":
        specs.append(
            AddressColumnSpec(
                "Primary Address", "Address", None, "City", "State", "Zip", "Country"
            )
        )
    elif file_name == "AdvizorPro_Firm_Offices_20261019.csv":
        specs.append(
            AddressColumnSpec(
                "Office Address", "Address 1", "Address 2", "City", "State", "Zip", "Country"
            )
        )
    elif file_name == "AdvizorPro_Person_20261019.csv":
        specs.append(
            AddressColumnSpec(
                "Person Address", "Address", None, "City", "State", "Zip", "Country"
            )
        )
        specs.append(
            AddressColumnSpec(
                "Firm Address",
                "Firm Address",
                None,
                "Firm City",
                "Firm State",
                "Firm Zip",
                "Firm Country",
            )
        )
    elif "Address Line 1" in cols and "Postal Code 1" in cols:
        specs.append(
            AddressColumnSpec(
                "Address",
                "Address Line 1",
                "Address Line 2",
                "City",
                "State Province",
                "Postal Code 1",
                "Country ID",
            )
        )
    elif "MainOffice_Address1" in cols:
        specs.append(
            AddressColumnSpec(
                "MainOffice Address",
                "MainOffice_Address1",
                "MainOffice_Address2",
                "MainOffice_City",
                "MainOffice_State",
                "MainOffice_ZipCode",
                "MainOffice_Country",
            )
        )
    elif "Branch_Address1" in cols:
        specs.append(
            AddressColumnSpec(
                "Branch Address",
                "Branch_Address1",
                "Branch_Address2",
                "Branch_City",
                "Branch_State",
                "Branch_ZipCode",
                "Branch_Country",
            )
        )
    elif "Office_Address1" in cols:
        specs.append(
            AddressColumnSpec(
                "Office Address",
                "Office_Address1",
                "Office_Address2",
                "Office_City",
                "Office_State",
                "Office_ZipCode",
                "Office_Country",
            )
        )
    elif "BranchAddr1" in cols:
        specs.append(
            AddressColumnSpec(
                "Branch Address",
                "BranchAddr1",
                "BranchAddr2",
                "BranchCity",
                "BranchState",
                "BranchZip",
                None,
            )
        )
        if "HomeAddr1" in cols:
            specs.append(
                AddressColumnSpec(
                    "Home Address",
                    "HomeAddr1",
                    "HomeAddr2",
                    "HomeCity",
                    "HomeState",
                    "HomeZip",
                    None,
                )
            )
    elif "Address1" in cols and "Zip" in cols:
        specs.append(
            AddressColumnSpec(
                "Historical Firm Address",
                "Address1",
                "Address2",
                "City",
                "State",
                "Zip",
                None,
            )
        )
    elif "Address" in cols and "PostalCode" in cols:
        specs.append(
            AddressColumnSpec(
                "Physical Address",
                "Address",
                None,
                "City" if "City" in cols else None,
                "State" if "State" in cols else None,
                "PostalCode",
                "Country" if "Country" in cols else None,
            )
        )
    return specs


def _eval_unique_batch(
    batch: list[tuple[str, str, str, str, str, str]],
) -> list[tuple[str, bool, str, str, bool, bool, bool, bool, bool, str, tuple[str, ...]]]:
    """Worker function to evaluate a chunk of unique (s1, s2, city, state, zip, country) tuples."""
    out = []
    for s1, s2, city, state, postal, country in batch:
        c_in = "" if country in ("null", "NULL", "None", "XX") else country
        std = standardize_address(
            street1=s1 or None,
            street2=s2 or None,
            city=city or None,
            state=state or None,
            postal_code=postal or None,
            country=c_in or None,
            allow_locality=True,
            use_cache=False,
        )
        out.append(
            (
                std.address_status,
                bool(std.is_locality_only),
                str(std.routing_tier.value if hasattr(std.routing_tier, "value") else std.routing_tier),
                str(std.deliverability),
                bool(std.rooftop_address),
                bool(std.is_private_residence),
                bool(std.is_registered_agent_hub),
                bool(std.cmra),
                bool(std.is_us),
                str(std.country_iso3 or std.country or "USA"),
                tuple(std.failure_reason_codes or ()),
            )
        )
    return out


def classify_suite(rel_path: str) -> str:
    if rel_path.startswith("AP_"):
        return "AdvizorPro"
    if rel_path.startswith("AdvisorAtlas"):
        return "AdvisorAtlas"
    if rel_path.startswith("Discovery"):
        return "Discovery"
    if rel_path.startswith("Foursquare"):
        return "Foursquare_OS_Places_Global"
    if rel_path.startswith("Overture"):
        return "Overture_Maps_Global_Places"
    if rel_path.startswith("Wikidata"):
        return "Wikidata_And_Regulatory_Global"
    return "Other"


def _read_csv_with_fallback(
    file_path: Path,
    n_rows: int | None = None,
    columns: list[str] | None = None,
) -> pl.DataFrame:
    try:
        return pl.read_csv(
            file_path,
            separator=",",
            n_rows=n_rows,
            columns=columns,
            infer_schema_length=0,
            ignore_errors=True,
            truncate_ragged_lines=True,
            encoding="utf8-lossy",
        )
    except Exception:
        raw_data = file_path.read_bytes()
        clean_bytes = (
            raw_data.replace(b'\\"', b'""')
            .decode("utf-8", errors="replace")
            .encode("utf-8")
        )
        return pl.read_csv(
            clean_bytes,
            separator=",",
            n_rows=n_rows,
            columns=columns,
            infer_schema_length=0,
            ignore_errors=True,
            truncate_ragged_lines=True,
            encoding="utf8-lossy",
        )


def main() -> None:
    root = REPO_ROOT / ".drive_datasets"
    files = sorted(
        [p for p in root.rglob("*") if p.is_file() and p.suffix in (".csv", ".txt")]
    )
    print("=== Address-Standardizer Empirical Global & Financial Dataset Benchmark ===")
    print("Engine info:", get_engine_info())

    all_metrics: list[AddressEvalMetrics] = []
    global_cache: dict[
        tuple[str, str, str, str, str, str],
        tuple[str, bool, str, str, bool, bool, bool, bool, bool, str, tuple[str, ...]],
    ] = {}

    num_workers = min(16, os.cpu_count() or 4)
    pool = mp.Pool(processes=num_workers)

    try:
        for file_path in files:
            rel_str = str(file_path.relative_to(root))
            suite_name = classify_suite(rel_str)
            try:
                sample_df = _read_csv_with_fallback(file_path, n_rows=10)
            except Exception as e:
                print(f"[!] Skipping {file_path.name}: {e}")
                continue

            specs = detect_address_specs(sample_df, file_path.name)
            if not specs:
                continue

            needed_cols: list[str] = []
            for sp in specs:
                for col_n in (
                    sp.street1,
                    sp.street2,
                    sp.city,
                    sp.state,
                    sp.postal_code,
                    sp.country,
                ):
                    if (
                        col_n
                        and col_n in sample_df.columns
                        and col_n not in needed_cols
                    ):
                        needed_cols.append(col_n)

            try:
                df = _read_csv_with_fallback(file_path, columns=needed_cols)
            except Exception as e:
                print(f"[!] Skipping {file_path.name}: {e}")
                continue

            for spec in specs:
                t0 = time.perf_counter()
                total_rows = len(df)

                def _col_list(col_name: str | None) -> list[str]:
                    if not col_name or col_name not in df.columns:
                        return [""] * total_rows
                    return [
                        str(v).strip() if v is not None else ""
                        for v in df[col_name].to_list()
                    ]

                s1_list = _col_list(spec.street1)
                s2_list = _col_list(spec.street2)
                city_list = _col_list(spec.city)
                state_list = _col_list(spec.state)
                zip_list = _col_list(spec.postal_code)
                country_list = _col_list(spec.country)

                tuple_counts: Counter[tuple[str, str, str, str, str, str]] = Counter()
                non_empty = 0
                for s1, s2, ci, st, zp, co in zip(
                    s1_list, s2_list, city_list, state_list, zip_list, country_list
                ):
                    if not (s1 or s2 or ci or zp):
                        continue
                    non_empty += 1
                    tuple_counts[(s1, s2, ci, st, zp, co)] += 1

                if non_empty == 0:
                    continue

                unseen = [t for t in tuple_counts if t not in global_cache]
                if unseen:
                    chunk_size = max(250, len(unseen) // (num_workers * 4) + 1)
                    chunks = [
                        unseen[i : i + chunk_size]
                        for i in range(0, len(unseen), chunk_size)
                    ]
                    for chunk, res_list in zip(
                        chunks, pool.imap(_eval_unique_batch, chunks)
                    ):
                        for t_key, r_val in zip(chunk, res_list):
                            global_cache[t_key] = r_val

                m = AddressEvalMetrics(
                    suite_name=suite_name,
                    file_name=file_path.name,
                    address_label=spec.label,
                    total_rows=total_rows,
                    non_empty_rows=non_empty,
                    unique_addresses=len(tuple_counts),
                )
                country_counter: Counter[str] = Counter()
                reason_counter: Counter[str] = Counter()

                for t_key, freq in tuple_counts.items():
                    (
                        status,
                        is_loc,
                        rtier,
                        deliv,
                        has_rooftop,
                        is_priv,
                        is_hub,
                        is_cmra,
                        is_us,
                        c_iso3,
                        reasons,
                    ) = global_cache[t_key]

                    if is_loc:
                        m.locality_only_count += freq
                    elif status == "standardized":
                        m.standardized_count += freq
                    else:
                        m.parse_failed_count += freq

                    if "AUTO_PASS" in rtier:
                        m.auto_pass_count += freq
                    elif "FUZZY_REVIEW" in rtier:
                        m.fuzzy_review_count += freq
                    else:
                        m.manual_stewardship_count += freq

                    deliv_u = deliv.upper()
                    if "REQUIRES_SECONDARY" in deliv_u:
                        m.requires_secondary_count += freq
                    elif "UNDELIVERABLE" in deliv_u:
                        m.undeliverable_count += freq
                    else:
                        m.deliverable_count += freq

                    if has_rooftop:
                        m.rooftop_extracted_count += freq
                    if is_priv:
                        m.private_residence_count += freq
                    if is_hub:
                        m.registered_agent_hub_count += freq
                    if is_cmra:
                        m.cmra_count += freq
                    if is_us:
                        m.us_records += freq
                    else:
                        m.intl_records += freq

                    country_counter[c_iso3] += freq
                    for r_code in reasons:
                        reason_counter[r_code] += freq

                dt = time.perf_counter() - t0
                m.duration_sec = round(dt, 3)
                m.effective_throughput_rec_sec = round(non_empty / max(dt, 1e-6), 1)
                m.usable_yield_rate = round(
                    (m.standardized_count + m.locality_only_count) / non_empty, 6
                )
                m.standardized_rate = round(m.standardized_count / non_empty, 6)
                m.unique_countries = len(country_counter)
                m.top_countries = dict(country_counter.most_common(10))
                m.failure_reasons = dict(reason_counter.most_common(10))
                all_metrics.append(m)

                print(
                    f"  [{suite_name}] {file_path.name} ({spec.label}): "
                    f"{non_empty:,} non-empty ({len(tuple_counts):,} unique) | "
                    f"Usable: {m.usable_yield_rate*100:.2f}% (Std: {m.standardized_count:,}, Loc: {m.locality_only_count:,}, Fail: {m.parse_failed_count:,}) | "
                    f"Countries: {m.unique_countries} | {m.effective_throughput_rec_sec:,.0f} rec/s"
                )
    finally:
        pool.close()
        pool.join()

    total_non_empty = sum(m.non_empty_rows for m in all_metrics)
    total_std = sum(m.standardized_count for m in all_metrics)
    total_loc = sum(m.locality_only_count for m in all_metrics)
    total_fail = sum(m.parse_failed_count for m in all_metrics)
    overall_usable = (total_std + total_loc) / max(total_non_empty, 1)

    out_json = REPO_ROOT / "benchmarks" / "drive_datasets_address_results.json"
    out_json.write_text(
        json.dumps(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_address_groups_evaluated": len(all_metrics),
                "total_non_empty_addresses": total_non_empty,
                "total_unique_addresses": len(global_cache),
                "total_standardized": total_std,
                "total_locality_only": total_loc,
                "total_parse_failed": total_fail,
                "overall_usable_yield_rate": round(overall_usable, 6),
                "datasets": [asdict(m) for m in all_metrics],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Google Drive Global & Financial Dataset Address-Standardizer Benchmark Report",
        "",
        f"**Execution Timestamp:** {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}  ",
        "**Engine:** Entity-Standardizer v2.1.0 (`Rust_PyO3` + Multi-National UPU S42 & USPS Pub 28)  ",
        f"**Total Dataset Address Groups Evaluated:** {len(all_metrics)}  ",
        f"**Total Non-Empty Address Records Processed:** {total_non_empty:,}  ",
        f"**Total Unique Address Tuples Evaluated:** {len(global_cache):,}  ",
        f"**Overall Usable Yield (`standardized` + `locality_only`):** **{overall_usable*100:.2f}%** (`{total_std + total_loc:,} / {total_non_empty:,}`)  ",
        f"**Full Street-Level Standardized:** {total_std:,} ({total_std/max(total_non_empty,1)*100:.2f}%)  ",
        f"**Locality-Only Standardized:** {total_loc:,} ({total_loc/max(total_non_empty,1)*100:.2f}%)  ",
        f"**Unparseable / Parse Failed:** {total_fail:,} ({total_fail/max(total_non_empty,1)*100:.2f}%)  ",
        "",
        "---",
        "",
        "## 1. Per-Dataset Address Standardization Yield & Routing Distribution",
        "",
        "| Suite | Dataset File | Address Group | Non-Empty Rows | Unique Tuples | Standardized | Locality Only | Parse Failed | Usable Yield % | Auto-Pass % | Rooftop Extracted | Countries | Throughput |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in all_metrics:
        ap_pct = m.auto_pass_count / max(m.non_empty_rows, 1) * 100
        lines.append(
            f"| `{m.suite_name}` | `{m.file_name}` | `{m.address_label}` | {m.non_empty_rows:,} | {m.unique_addresses:,} | {m.standardized_count:,} | {m.locality_only_count:,} | {m.parse_failed_count:,} | **{m.usable_yield_rate*100:.2f}%** | {ap_pct:.1f}% | {m.rooftop_extracted_count:,} | {m.unique_countries} | {m.effective_throughput_rec_sec:,.0f} r/s |"
        )

    lines.extend(
        [
            "",
            "## 2. Suite-Level Summary",
            "",
            "| Dataset Suite | Non-Empty Addresses | Standardized | Locality Only | Parse Failed | Usable Yield % | US Records | International Records |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    suites_seen = []
    for m in all_metrics:
        if m.suite_name not in suites_seen:
            suites_seen.append(m.suite_name)
    for s_name in suites_seen:
        sm = [m for m in all_metrics if m.suite_name == s_name]
        s_ne = sum(x.non_empty_rows for x in sm)
        s_std = sum(x.standardized_count for x in sm)
        s_loc = sum(x.locality_only_count for x in sm)
        s_fail = sum(x.parse_failed_count for x in sm)
        s_us = sum(x.us_records for x in sm)
        s_intl = sum(x.intl_records for x in sm)
        s_yield = (s_std + s_loc) / max(s_ne, 1) * 100
        lines.append(
            f"| **{s_name}** | {s_ne:,} | {s_std:,} | {s_loc:,} | {s_fail:,} | **{s_yield:.2f}%** | {s_us:,} | {s_intl:,} |"
        )

    md_text = "\n".join(lines) + "\n"
    out_md = REPO_ROOT / "docs" / "GOOGLE_DRIVE_ADDRESS_BENCHMARK.md"
    out_md.write_text(md_text, encoding="utf-8")
    print(f"\n[+] Wrote JSON results to: {out_json}")
    print(f"[+] Wrote Markdown report to: {out_md}")


if __name__ == "__main__":
    main()
