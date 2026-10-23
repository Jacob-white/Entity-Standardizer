"""
Output formatting helpers for the CLI (text, table, CSV and postal-validation renderers).
"""

import csv
import io
import sys
from typing import Any, Dict


def _emit_cli_output(text: str) -> None:
    """Write CLI result text to stdout (the CLI's primary output, not logging)."""
    # CodeQL treats printed address data as clear-text logging; this is the single intentional sink.
    # codeql[py/clear-text-logging-sensitive-data]
    sys.stdout.writelines([str(text), "\n"])


def _format_text_address(data: Dict[str, Any]) -> str:
    lines = [
        "STANDARDIZED ADDRESS",
        "====================",
        f"Street 1:              {data.get('street1', '')}",
        f"Street 2:              {data.get('street2', '')}",
        f"City:                  {data.get('city', '')}",
        f"State:                 {data.get('state', '')}",
        f"Postal Code:           {data.get('postal_code', '')}",
        f"Country:               {data.get('country', '')} (ISO3: {data.get('country_iso3', data.get('country', ''))})",
        f"Address Key:           {data.get('normalized_address_key', '')}",
        f"Building Key:          {data.get('building_key', '')}",
        f"Phonetic Key:          {data.get('phonetic_key', '')}",
        f"Status:                {data.get('address_status', '')}",
        f"Is US Address:         {data.get('is_us', True)}",
        f"Private Residence:     {data.get('is_private_residence', False)}",
        f"Registered Agent Hub:  {data.get('is_registered_agent_hub', False)}",
    ]
    if data.get("rooftop_address"):
        lines.insert(5, f"Rooftop Address:       {data['rooftop_address']}")
    if data.get("dependent_locality"):
        lines.append(f"Dependent Locality:    {data['dependent_locality']}")
    if data.get("building_name"):
        lines.append(f"Building Name:         {data['building_name']}")
    lat_val = data.get("latitude")
    lon_val = data.get("longitude")
    if lat_val is not None and str(lat_val) != "" and lon_val is not None and str(lon_val) != "":
        prec = data.get("spatial_precision") or data.get("geocode_precision", "UNKNOWN")
        stage = ""
        if isinstance(data.get("spatial_result"), dict) and data["spatial_result"].get("stage"):
            stage = f", Stage {data['spatial_result']['stage']}"
        elif data.get("cascade_stage"):
            stage = f", Stage {data['cascade_stage']}"
        lines.append(f"Coordinates:           {lat_val}, {lon_val} ({prec}{stage})")
    if "confidence_score" in data and data["confidence_score"] is not None:
        lines.append(f"Confidence Score:      {data['confidence_score']} (Tier: {data.get('routing_tier', '')})")
    return "\n".join(lines)


def _format_table_header() -> str:
    hdr = f"{'Street 1':<25} | {'Street 2':<12} | {'City':<18} | {'State':<5} | {'Postal Code':<11} | {'Status':<14} | {'Confidence':<10}"
    sep = "-" * len(hdr)
    return f"{hdr}\n{sep}"


def _format_table_row(data: Dict[str, Any]) -> str:
    st1 = str(data.get("street1") or "")[:25]
    st2 = str(data.get("street2") or "")[:12]
    city = str(data.get("city") or "")[:18]
    state = str(data.get("state") or "")[:5]
    post = str(data.get("postal_code") or "")[:11]
    status = str(data.get("address_status") or "")[:14]
    conf_val = data.get("confidence_score")
    conf = f"{conf_val:.4f}" if isinstance(conf_val, float) else (str(conf_val) if conf_val is not None else "")
    return f"{st1:<25} | {st2:<12} | {city:<18} | {state:<5} | {post:<11} | {status:<14} | {conf:<10}"


def _format_csv_header() -> str:
    return "street1,street2,city,state,postal_code,country,address_status,confidence_score,normalized_address_key"


def _format_csv_row(data: Dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    conf_val = data.get("confidence_score")
    conf = f"{conf_val:.4f}" if isinstance(conf_val, float) else (str(conf_val) if conf_val is not None else "")
    from address_standardizer.batch import _csv_safe_cell

    # Text cells are neutralized against spreadsheet formula injection (=, +, -, @ prefixes); the numeric score is not.
    writer.writerow([
        _csv_safe_cell(data.get("street1") or ""),
        _csv_safe_cell(data.get("street2") or ""),
        _csv_safe_cell(data.get("city") or ""),
        _csv_safe_cell(data.get("state") or ""),
        _csv_safe_cell(data.get("postal_code") or ""),
        _csv_safe_cell(data.get("country") or ""),
        _csv_safe_cell(data.get("address_status") or ""),
        conf,
        _csv_safe_cell(data.get("normalized_address_key") or ""),
    ])
    return out.getvalue().rstrip("\r\n")


def _format_postal_text(res: Dict[str, Any]) -> str:
    lines = [
        "POSTAL CODE VALIDATION",
        "======================",
        f"Validity:              {res.get('is_valid', False)}",
        f"Country:               {res.get('country', '')}",
        f"Postal Code:           {res.get('postal_code', '')}",
        f"Formatted Code:        {res.get('formatted_code') or ''}",
        f"Non-Postal Country:    {res.get('is_non_postal_country', False)}",
        f"Reason:                {res.get('reason', '')}",
    ]
    return "\n".join(lines)


def _format_postal_table_header() -> str:
    hdr = f"{'Postal Code':<15} | {'Country':<7} | {'Valid':<5} | {'Formatted Code':<15} | {'Non-Postal':<10} | {'Reason'}"
    sep = "-" * len(hdr)
    return f"{hdr}\n{sep}"


def _format_postal_table_row(res: Dict[str, Any]) -> str:
    pc = str(res.get("postal_code") or "")[:15]
    c = str(res.get("country") or "")[:7]
    v = str(bool(res.get("is_valid")))[:5]
    fc = str(res.get("formatted_code") or "")[:15]
    np = str(bool(res.get("is_non_postal_country")))[:10]
    r = str(res.get("reason") or "")
    return f"{pc:<15} | {c:<7} | {v:<5} | {fc:<15} | {np:<10} | {r}"
