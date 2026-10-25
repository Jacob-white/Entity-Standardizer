"""High-throughput batch and streaming phone standardization utilities."""

from __future__ import annotations

import csv
import json
from collections.abc import Generator, Iterable, Iterator
from pathlib import Path
from typing import Any

from entity_standardizer.models import StandardizedPhone
from entity_standardizer.standardizer import standardize_phone

# Spreadsheet applications evaluate cells that start with these characters as formulas.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe_cell(value: Any) -> Any:
    """Neutralize CSV/formula injection in a text cell by prefixing a single quote."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def buffered_chunk_generator(
    reader: Iterator[dict[str, Any]],
    chunk_size: int = 5000,
) -> Generator[list[dict[str, Any]], None, None]:
    """Yield rows from reader in fixed-size chunks using pre-allocated buffer arrays.

    Ensures O(chunk_size) memory footprint regardless of file size.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    buffer: list[dict[str, Any] | None] = [None] * chunk_size
    count = 0
    for row in reader:
        buffer[count] = row
        count += 1
        if count == chunk_size:
            yield list(buffer)  # type: ignore[arg-type]
            count = 0
    if count > 0:
        yield buffer[:count]  # type: ignore[return-value]


def chunk_generator(
    reader: Iterator[dict[str, Any]],
    chunk_size: int = 5000,
) -> Generator[list[dict[str, Any]], None, None]:
    """Yield rows from reader in fixed-size chunks to bound memory utilization.

    Delegates to buffered_chunk_generator for pre-allocated buffer efficiency.
    """
    yield from buffered_chunk_generator(reader, chunk_size=chunk_size)


def batch_standardize_phones(
    records: Iterable[str | dict[str, Any]],
    default_country: str = "US",
    phone_key: str = "phone",
    country_key: str = "country",
) -> list[StandardizedPhone]:
    """Standardize an iterable of phone strings or dictionaries into StandardizedPhone records."""
    results: list[StandardizedPhone] = []
    for item in records:
        if isinstance(item, dict):
            raw = item.get(phone_key)
            country = item.get(country_key)
            results.append(
                standardize_phone(
                    str(raw) if raw is not None else None,
                    country=str(country) if country is not None else None,
                    default_country=default_country,
                    address_context=item,
                )
            )
        else:
            results.append(standardize_phone(item, default_country=default_country))
    return results


def stream_standardize_csv(
    input_path: str | Path,
    output_path: str | Path,
    phone_col: str = "phone",
    country_col: str | None = "country",
    default_country: str = "US",
    *,
    address_col: str | None = None,
    company_col: str | None = None,
    person_col: str | None = None,
    email_col: str | None = None,
    url_col: str | None = None,
) -> int:
    """Stream-process a CSV file, appending standardized multi-pillar columns, and return row count."""
    from entity_standardizer.address.standardizer import standardize_address
    from entity_standardizer.company import standardize_company
    from entity_standardizer.person import standardize_person
    from entity_standardizer.web import standardize_email, standardize_url

    in_path = Path(input_path)
    out_path = Path(output_path)
    count = 0
    extra_cols = [
        "phone_e164",
        "phone_national",
        "phone_international",
        "phone_rfc3966",
        "phone_country_iso2",
        "phone_region_code",
        "phone_line_type",
        "phone_extension",
        "phone_is_valid",
        "phone_confidence",
        "phone_routing_tier",
    ]
    if address_col:
        extra_cols.extend(
            [
                "address_line_1",
                "address_city",
                "address_state",
                "address_postal_code",
                "address_key",
            ]
        )
    if company_col:
        extra_cols.extend(["company_legal_name", "company_key"])
    if person_col:
        extra_cols.extend(["person_full_name", "person_key"])
    if email_col:
        extra_cols.extend(["email_canonical", "email_domain"])
    if url_col:
        extra_cols.extend(["url_canonical", "url_domain"])

    with in_path.open("r", encoding="utf-8", newline="") as fin, out_path.open(
        "w", encoding="utf-8", newline=""
    ) as fout:
        reader = csv.DictReader(fin)
        base_fields = list(reader.fieldnames or [])
        fieldnames = base_fields + [c for c in extra_cols if c not in base_fields]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            raw_phone = row.get(phone_col, "")
            country_hint = row.get(country_col) if country_col else None
            res = standardize_phone(
                raw_phone,
                country=country_hint,
                default_country=default_country,
            )
            out_row: dict[str, Any] = {k: _csv_safe_cell(v) for k, v in row.items()}
            out_row.update(
                {
                    "phone_e164": res.e164 or "",
                    "phone_national": _csv_safe_cell(res.national or ""),
                    "phone_international": res.international or "",
                    "phone_rfc3966": _csv_safe_cell(res.rfc3966 or ""),
                    "phone_country_iso2": res.country_iso2 or "",
                    "phone_region_code": res.region_code or "",
                    "phone_line_type": res.line_type,
                    "phone_extension": _csv_safe_cell(res.extension or ""),
                    "phone_is_valid": str(res.is_valid),
                    "phone_confidence": f"{res.confidence:.4f}",
                    "phone_routing_tier": res.routing_tier,
                }
            )
            if address_col and address_col in row:
                addr_res = standardize_address(
                    row.get(address_col, ""),
                    country=country_hint or default_country,
                    allow_locality=True,
                )
                out_row.update(
                    {
                        "address_line_1": _csv_safe_cell(addr_res.street1 or ""),
                        "address_city": _csv_safe_cell(addr_res.city or ""),
                        "address_state": _csv_safe_cell(addr_res.state or ""),
                        "address_postal_code": _csv_safe_cell(addr_res.postal_code or ""),
                        "address_key": _csv_safe_cell(addr_res.normalized_address_key or ""),
                    }
                )
            if company_col and company_col in row:
                comp_res = standardize_company(row.get(company_col, ""), country=country_hint)
                out_row.update(
                    {
                        "company_legal_name": _csv_safe_cell(comp_res.legal_name or ""),
                        "company_key": _csv_safe_cell(comp_res.company_key or ""),
                    }
                )
            if person_col and person_col in row:
                per_res = standardize_person(row.get(person_col, ""))
                out_row.update(
                    {
                        "person_full_name": _csv_safe_cell(per_res.full_name or ""),
                        "person_key": _csv_safe_cell(per_res.person_key or ""),
                    }
                )
            if email_col and email_col in row:
                em_res = standardize_email(row.get(email_col, ""))
                out_row.update(
                    {
                        "email_canonical": _csv_safe_cell(em_res.email or ""),
                        "email_domain": _csv_safe_cell(em_res.domain or ""),
                    }
                )
            if url_col and url_col in row:
                url_res = standardize_url(row.get(url_col, ""))
                out_row.update(
                    {
                        "url_canonical": _csv_safe_cell(url_res.url or ""),
                        "url_domain": _csv_safe_cell(url_res.domain or ""),
                    }
                )
            writer.writerow(out_row)
            count += 1
    return count


def stream_standardize_jsonl(
    input_path: str | Path,
    output_path: str | Path,
    phone_key: str = "phone",
    country_key: str = "country",
    default_country: str = "US",
) -> int:
    """Stream-process a JSON Lines (.jsonl) file and return total processed records."""
    in_path = Path(input_path)
    out_path = Path(output_path)
    count = 0
    with in_path.open("r", encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            raw_phone = payload.get(phone_key)
            country = payload.get(country_key)
            res = standardize_phone(
                raw_phone,
                country=country,
                default_country=default_country,
                address_context=payload,
            )
            payload["standardized_phone"] = res.to_dict()
            fout.write(json.dumps(payload) + "\n")
            count += 1
    return count
