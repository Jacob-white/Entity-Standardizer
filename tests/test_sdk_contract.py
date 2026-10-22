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
    from phone_standardizer.audit import explain_phone
    from phone_standardizer.dedup import PhoneCluster, PhoneComparisonResult
    from phone_standardizer.server import PhoneCompareRequest, PhoneDeduplicateRequest

    expected_phone_fields = {f.name for f in dataclasses.fields(StandardizedPhone)}
    expected_plan_fields = {f.name for f in dataclasses.fields(CountryDialPlan)}
    expected_cmp_fields = {f.name for f in dataclasses.fields(PhoneComparisonResult)}
    expected_cluster_fields = {f.name for f in dataclasses.fields(PhoneCluster)}
    expected_req_fields = set(PhoneStandardizeRequest.model_fields.keys())
    expected_batch_fields = set(PhoneBatchRequest.model_fields.keys())
    expected_cmp_req_fields = set(PhoneCompareRequest.model_fields.keys())
    expected_dedup_req_fields = set(PhoneDeduplicateRequest.model_fields.keys())

    sample_explain = explain_phone("+1 (415) 555-2671")
    expected_explain_report_fields = set(sample_explain.keys())
    expected_intelligence_fields = set(sample_explain["intelligence"].keys())
    expected_explanation_fields = set(sample_explain["explanation"].keys())

    # TypeScript
    assert _ts_interface_fields("StandardizedPhone") == expected_phone_fields
    assert _ts_interface_fields("CountryDialPlan") == expected_plan_fields
    assert _ts_interface_fields("PhoneComparisonResult") == expected_cmp_fields
    assert _ts_interface_fields("PhoneCluster") == expected_cluster_fields
    assert _ts_interface_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _ts_interface_fields("PhoneBatchRequest") == expected_batch_fields
    assert _ts_interface_fields("PhoneCompareRequest") == expected_cmp_req_fields
    assert _ts_interface_fields("PhoneDeduplicateRequest") == expected_dedup_req_fields
    assert _ts_interface_fields("PhoneExplainReport") == expected_explain_report_fields
    assert _ts_interface_fields("PhoneIntelligence") == expected_intelligence_fields
    assert _ts_interface_fields("PhoneExplanation") == expected_explanation_fields

    # Go
    assert _go_struct_fields("StandardizedPhone") == expected_phone_fields
    assert _go_struct_fields("CountryDialPlan") == expected_plan_fields
    assert _go_struct_fields("PhoneComparisonResult") == expected_cmp_fields
    assert _go_struct_fields("PhoneCluster") == expected_cluster_fields
    assert _go_struct_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _go_struct_fields("PhoneBatchRequest") == expected_batch_fields
    assert _go_struct_fields("PhoneCompareRequest") == expected_cmp_req_fields
    assert _go_struct_fields("PhoneDeduplicateRequest") == expected_dedup_req_fields
    assert _go_struct_fields("PhoneExplainReport") == expected_explain_report_fields
    assert _go_struct_fields("PhoneIntelligence") == expected_intelligence_fields
    assert _go_struct_fields("PhoneExplanation") == expected_explanation_fields

    # .NET
    assert _dotnet_class_fields("StandardizedPhone") == expected_phone_fields
    assert _dotnet_class_fields("CountryDialPlan") == expected_plan_fields
    assert _dotnet_class_fields("PhoneComparisonResult") == expected_cmp_fields
    assert _dotnet_class_fields("PhoneCluster") == expected_cluster_fields
    assert _dotnet_class_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _dotnet_class_fields("PhoneBatchRequest") == expected_batch_fields
    assert _dotnet_class_fields("PhoneCompareRequest") == expected_cmp_req_fields
    assert _dotnet_class_fields("PhoneDeduplicateRequest") == expected_dedup_req_fields
    assert _dotnet_class_fields("PhoneExplainReport") == expected_explain_report_fields
    assert _dotnet_class_fields("PhoneIntelligence") == expected_intelligence_fields
    assert _dotnet_class_fields("PhoneExplanation") == expected_explanation_fields


