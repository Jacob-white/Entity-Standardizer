"""High-throughput batch and streaming phone standardization utilities."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from entity_standardizer.models import StandardizedPhone
from entity_standardizer.standardizer import standardize_phone


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
) -> int:
    """Stream-process a CSV file, appending standardized phone columns, and return row count."""
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
            out_row = dict(row)
            out_row.update(
                {
                    "phone_e164": res.e164 or "",
                    "phone_national": res.national or "",
                    "phone_international": res.international or "",
                    "phone_rfc3966": res.rfc3966 or "",
                    "phone_country_iso2": res.country_iso2 or "",
                    "phone_region_code": res.region_code or "",
                    "phone_line_type": res.line_type,
                    "phone_extension": res.extension or "",
                    "phone_is_valid": str(res.is_valid),
                    "phone_confidence": f"{res.confidence:.4f}",
                    "phone_routing_tier": res.routing_tier,
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
