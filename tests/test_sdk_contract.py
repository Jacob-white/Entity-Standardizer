"""SDK Contract Verification Tests across TypeScript, Go, and .NET Client Models."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from phone_standardizer.models import CountryDialPlan, StandardizedPhone
from phone_standardizer.server import PhoneBatchRequest, PhoneStandardizeRequest

SDKS_DIR = Path(__file__).resolve().parent.parent / "sdks"


def _ts_interface_fields(interface_name: str) -> set[str]:
    text = (SDKS_DIR / "typescript" / "src" / "types.ts").read_text(encoding="utf-8")
    match = re.search(rf"export interface {interface_name}\s*\{{([^}}]+)\}}", text)
    assert match is not None, f"Missing TypeScript interface {interface_name}"
    return set(re.findall(r"^\s*([a-zA-Z0-9_]+)\??:", match.group(1), re.MULTILINE))


def _go_struct_fields(struct_name: str) -> set[str]:
    text = (SDKS_DIR / "go" / "models.go").read_text(encoding="utf-8")
    match = re.search(rf"type {struct_name} struct\s*\{{([^}}]+)\}}", text)
    assert match is not None, f"Missing Go struct {struct_name}"
    return {tag.split(",")[0] for tag in re.findall(r'`json:"([^"]+)"`', match.group(1))}


def _extract_block(text: str, header_pattern: str) -> str:
    match = re.search(header_pattern, text)
    assert match is not None, f"Missing declaration matching {header_pattern}"
    idx = text.index("{", match.start())
    depth = 0
    start = idx
    while idx < len(text):
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
        idx += 1
    raise AssertionError(f"Unbalanced braces for {header_pattern}")


def _dotnet_class_fields(class_name: str) -> set[str]:
    text = (SDKS_DIR / "dotnet" / "Models.cs").read_text(encoding="utf-8")
    body = _extract_block(text, rf"public sealed class {class_name}\b")
    return set(re.findall(r'\[JsonPropertyName\("([^"]+)"\)\]', body))


def test_sdk_models_match_python_contracts() -> None:
    expected_phone_fields = {f.name for f in dataclasses.fields(StandardizedPhone)}
    expected_plan_fields = {f.name for f in dataclasses.fields(CountryDialPlan)}
    expected_req_fields = set(PhoneStandardizeRequest.model_fields.keys())
    expected_batch_fields = set(PhoneBatchRequest.model_fields.keys())

    # TypeScript
    assert _ts_interface_fields("StandardizedPhone") == expected_phone_fields
    assert _ts_interface_fields("CountryDialPlan") == expected_plan_fields
    assert _ts_interface_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _ts_interface_fields("PhoneBatchRequest") == expected_batch_fields

    # Go
    assert _go_struct_fields("StandardizedPhone") == expected_phone_fields
    assert _go_struct_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _go_struct_fields("PhoneBatchRequest") == expected_batch_fields

    # .NET
    assert _dotnet_class_fields("StandardizedPhone") == expected_phone_fields
    assert _dotnet_class_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _dotnet_class_fields("PhoneBatchRequest") == expected_batch_fields
