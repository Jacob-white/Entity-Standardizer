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
                return text[start : idx + 1]
        idx += 1
    raise AssertionError(f"Unbalanced braces for {header_pattern}")


def _dotnet_class_fields(class_name: str) -> set[str]:
    text = (SDKS_DIR / "dotnet" / "Models.cs").read_text(encoding="utf-8")
    body = _extract_block(text, rf"public sealed class {class_name}\b")
    return set(re.findall(r'\[JsonPropertyName\("([^"]+)"\)\]', body))


def test_sdk_models_match_python_contracts() -> None:
    from address_standardizer import standardize_address
    from entity_standardizer.company import StandardizedCompany
    from entity_standardizer.person import StandardizedJobTitle, StandardizedPerson
    from entity_standardizer.web import StandardizedEmail, StandardizedSocial, StandardizedUrl
    from phone_standardizer.audit import explain_phone
    from phone_standardizer.dedup import PhoneCluster, PhoneComparisonResult
    from phone_standardizer.joint import StandardizedContact
    from phone_standardizer.server import (
        AddressStandardizeRequest,
        CompanyStandardizeRequest,
        ContactStandardizeRequest,
        EmailStandardizeRequest,
        PersonStandardizeRequest,
        PhoneCompareRequest,
        PhoneDeduplicateRequest,
        SocialStandardizeRequest,
        UrlStandardizeRequest,
    )

    expected_phone_fields = {f.name for f in dataclasses.fields(StandardizedPhone)}
    expected_plan_fields = {f.name for f in dataclasses.fields(CountryDialPlan)}
    expected_cmp_fields = {f.name for f in dataclasses.fields(PhoneComparisonResult)}
    expected_cluster_fields = {f.name for f in dataclasses.fields(PhoneCluster)}
    expected_company_fields = {f.name for f in dataclasses.fields(StandardizedCompany)}
    expected_person_fields = {f.name for f in dataclasses.fields(StandardizedPerson)}
    expected_title_fields = {f.name for f in dataclasses.fields(StandardizedJobTitle)}
    expected_email_fields = {f.name for f in dataclasses.fields(StandardizedEmail)}
    expected_url_fields = {f.name for f in dataclasses.fields(StandardizedUrl)}
    expected_social_fields = {f.name for f in dataclasses.fields(StandardizedSocial)}
    expected_contact_fields = {f.name for f in dataclasses.fields(StandardizedContact)}
    expected_address_fields = set(
        standardize_address(
            street1="350 Fifth Ave", city="New York", state="NY", postal_code="10118"
        )
        .as_dict()
        .keys()
    )
    expected_req_fields = set(PhoneStandardizeRequest.model_fields.keys())
    expected_batch_fields = set(PhoneBatchRequest.model_fields.keys())
    expected_cmp_req_fields = set(PhoneCompareRequest.model_fields.keys())
    expected_dedup_req_fields = set(PhoneDeduplicateRequest.model_fields.keys())
    expected_addr_req_fields = set(AddressStandardizeRequest.model_fields.keys())
    expected_comp_req_fields = set(CompanyStandardizeRequest.model_fields.keys())
    expected_per_req_fields = set(PersonStandardizeRequest.model_fields.keys())
    expected_email_req_fields = set(EmailStandardizeRequest.model_fields.keys())
    expected_url_req_fields = set(UrlStandardizeRequest.model_fields.keys())
    expected_soc_req_fields = set(SocialStandardizeRequest.model_fields.keys())
    expected_contact_req_fields = set(ContactStandardizeRequest.model_fields.keys())

    sample_explain = explain_phone("+1 (415) 555-2671")
    expected_explain_report_fields = set(sample_explain.keys())
    expected_intelligence_fields = set(sample_explain["intelligence"].keys())
    expected_explanation_fields = set(sample_explain["explanation"].keys())

    # TypeScript
    assert _ts_interface_fields("StandardizedPhone") == expected_phone_fields
    assert _ts_interface_fields("StandardizedAddress") == expected_address_fields
    assert _ts_interface_fields("StandardizedCompany") == expected_company_fields
    assert _ts_interface_fields("StandardizedPerson") == expected_person_fields
    assert _ts_interface_fields("StandardizedJobTitle") == expected_title_fields
    assert _ts_interface_fields("StandardizedEmail") == expected_email_fields
    assert _ts_interface_fields("StandardizedUrl") == expected_url_fields
    assert _ts_interface_fields("StandardizedSocial") == expected_social_fields
    assert _ts_interface_fields("StandardizedContact") == expected_contact_fields
    assert _ts_interface_fields("CountryDialPlan") == expected_plan_fields
    assert _ts_interface_fields("PhoneComparisonResult") == expected_cmp_fields
    assert _ts_interface_fields("PhoneCluster") == expected_cluster_fields
    assert _ts_interface_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _ts_interface_fields("PhoneBatchRequest") == expected_batch_fields
    assert _ts_interface_fields("PhoneCompareRequest") == expected_cmp_req_fields
    assert _ts_interface_fields("PhoneDeduplicateRequest") == expected_dedup_req_fields
    assert _ts_interface_fields("AddressStandardizeRequest") == expected_addr_req_fields
    assert _ts_interface_fields("CompanyStandardizeRequest") == expected_comp_req_fields
    assert _ts_interface_fields("PersonStandardizeRequest") == expected_per_req_fields
    assert _ts_interface_fields("EmailStandardizeRequest") == expected_email_req_fields
    assert _ts_interface_fields("UrlStandardizeRequest") == expected_url_req_fields
    assert _ts_interface_fields("SocialStandardizeRequest") == expected_soc_req_fields
    assert _ts_interface_fields("ContactStandardizeRequest") == expected_contact_req_fields
    assert _ts_interface_fields("PhoneExplainReport") == expected_explain_report_fields
    assert _ts_interface_fields("PhoneIntelligence") == expected_intelligence_fields
    assert _ts_interface_fields("PhoneExplanation") == expected_explanation_fields

    # Go
    assert _go_struct_fields("StandardizedPhone") == expected_phone_fields
    assert _go_struct_fields("StandardizedAddress") == expected_address_fields
    assert _go_struct_fields("StandardizedCompany") == expected_company_fields
    assert _go_struct_fields("StandardizedPerson") == expected_person_fields
    assert _go_struct_fields("StandardizedJobTitle") == expected_title_fields
    assert _go_struct_fields("StandardizedEmail") == expected_email_fields
    assert _go_struct_fields("StandardizedUrl") == expected_url_fields
    assert _go_struct_fields("StandardizedSocial") == expected_social_fields
    assert _go_struct_fields("StandardizedContact") == expected_contact_fields
    assert _go_struct_fields("CountryDialPlan") == expected_plan_fields
    assert _go_struct_fields("PhoneComparisonResult") == expected_cmp_fields
    assert _go_struct_fields("PhoneCluster") == expected_cluster_fields
    assert _go_struct_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _go_struct_fields("PhoneBatchRequest") == expected_batch_fields
    assert _go_struct_fields("PhoneCompareRequest") == expected_cmp_req_fields
    assert _go_struct_fields("PhoneDeduplicateRequest") == expected_dedup_req_fields
    assert _go_struct_fields("AddressStandardizeRequest") == expected_addr_req_fields
    assert _go_struct_fields("CompanyStandardizeRequest") == expected_comp_req_fields
    assert _go_struct_fields("PersonStandardizeRequest") == expected_per_req_fields
    assert _go_struct_fields("EmailStandardizeRequest") == expected_email_req_fields
    assert _go_struct_fields("UrlStandardizeRequest") == expected_url_req_fields
    assert _go_struct_fields("SocialStandardizeRequest") == expected_soc_req_fields
    assert _go_struct_fields("ContactStandardizeRequest") == expected_contact_req_fields
    assert _go_struct_fields("PhoneExplainReport") == expected_explain_report_fields
    assert _go_struct_fields("PhoneIntelligence") == expected_intelligence_fields
    assert _go_struct_fields("PhoneExplanation") == expected_explanation_fields

    # .NET
    assert _dotnet_class_fields("StandardizedPhone") == expected_phone_fields
    assert _dotnet_class_fields("StandardizedAddress") == expected_address_fields
    assert _dotnet_class_fields("StandardizedCompany") == expected_company_fields
    assert _dotnet_class_fields("StandardizedPerson") == expected_person_fields
    assert _dotnet_class_fields("StandardizedJobTitle") == expected_title_fields
    assert _dotnet_class_fields("StandardizedEmail") == expected_email_fields
    assert _dotnet_class_fields("StandardizedUrl") == expected_url_fields
    assert _dotnet_class_fields("StandardizedSocial") == expected_social_fields
    assert _dotnet_class_fields("StandardizedContact") == expected_contact_fields
    assert _dotnet_class_fields("CountryDialPlan") == expected_plan_fields
    assert _dotnet_class_fields("PhoneComparisonResult") == expected_cmp_fields
    assert _dotnet_class_fields("PhoneCluster") == expected_cluster_fields
    assert _dotnet_class_fields("PhoneStandardizeRequest") == expected_req_fields
    assert _dotnet_class_fields("PhoneBatchRequest") == expected_batch_fields
    assert _dotnet_class_fields("PhoneCompareRequest") == expected_cmp_req_fields
    assert _dotnet_class_fields("PhoneDeduplicateRequest") == expected_dedup_req_fields
    assert _dotnet_class_fields("AddressStandardizeRequest") == expected_addr_req_fields
    assert _dotnet_class_fields("CompanyStandardizeRequest") == expected_comp_req_fields
    assert _dotnet_class_fields("PersonStandardizeRequest") == expected_per_req_fields
    assert _dotnet_class_fields("EmailStandardizeRequest") == expected_email_req_fields
    assert _dotnet_class_fields("UrlStandardizeRequest") == expected_url_req_fields
    assert _dotnet_class_fields("SocialStandardizeRequest") == expected_soc_req_fields
    assert _dotnet_class_fields("ContactStandardizeRequest") == expected_contact_req_fields
    assert _dotnet_class_fields("PhoneExplainReport") == expected_explain_report_fields
    assert _dotnet_class_fields("PhoneIntelligence") == expected_intelligence_fields
    assert _dotnet_class_fields("PhoneExplanation") == expected_explanation_fields

    # Client methods and signatures for all endpoints
    ts_client = (SDKS_DIR / "typescript" / "src" / "client.ts").read_text(encoding="utf-8")
    for method, req_type, res_type, endpoint in (
        ("standardizeAddress", "AddressStandardizeRequest", "StandardizedAddress", "/v1/address"),
        ("standardizeCompany", "CompanyStandardizeRequest", "StandardizedCompany", "/v1/company"),
        ("standardizePerson", "PersonStandardizeRequest", "StandardizedPerson", "/v1/person"),
        ("standardizeEmail", "EmailStandardizeRequest", "StandardizedEmail", "/v1/email"),
        ("standardizeUrl", "UrlStandardizeRequest", "StandardizedUrl", "/v1/url"),
        ("standardizeSocial", "SocialStandardizeRequest", "StandardizedSocial", "/v1/social"),
        ("standardizeContact", "ContactStandardizeRequest", "StandardizedContact", "/v1/contact"),
    ):
        assert re.search(
            rf"async\s+{method}\(\s*req:\s*{req_type}[\s\S]*?:\s*Promise<{res_type}>",
            ts_client,
        )
        assert endpoint in ts_client

    ts_index = (SDKS_DIR / "typescript" / "src" / "index.ts").read_text(encoding="utf-8")
    assert "EntityStandardizerClient" in ts_index

    go_client = (SDKS_DIR / "go" / "client.go").read_text(encoding="utf-8")
    go_test = (SDKS_DIR / "go" / "client_test.go").read_text(encoding="utf-8")
    for method, req_type, res_type, endpoint in (
        ("StandardizeAddress", "AddressStandardizeRequest", "StandardizedAddress", "/v1/address"),
        ("StandardizeCompany", "CompanyStandardizeRequest", "StandardizedCompany", "/v1/company"),
        ("StandardizePerson", "PersonStandardizeRequest", "StandardizedPerson", "/v1/person"),
        ("StandardizeEmail", "EmailStandardizeRequest", "StandardizedEmail", "/v1/email"),
        ("StandardizeUrl", "UrlStandardizeRequest", "StandardizedUrl", "/v1/url"),
        ("StandardizeSocial", "SocialStandardizeRequest", "StandardizedSocial", "/v1/social"),
        ("StandardizeContact", "ContactStandardizeRequest", "StandardizedContact", "/v1/contact"),
    ):
        assert re.search(
            rf"func\s+\(c\s+\*Client\)\s+{method}\(ctx\s+context\.Context,\s*req\s+{req_type}\)\s*\(\*{res_type},\s*error\)",
            go_client,
        )
        assert f'"{endpoint}"' in go_client
        assert f'"{endpoint}"' in go_test and f"client.{method}(" in go_test

    dotnet_client = (SDKS_DIR / "dotnet" / "PhoneStandardizerClient.cs").read_text(encoding="utf-8")
    for method, req_type, res_type, endpoint in (
        ("StandardizeAddressAsync", "AddressStandardizeRequest", "StandardizedAddress", "/v1/address"),
        ("StandardizeCompanyAsync", "CompanyStandardizeRequest", "StandardizedCompany", "/v1/company"),
        ("StandardizePersonAsync", "PersonStandardizeRequest", "StandardizedPerson", "/v1/person"),
        ("StandardizeEmailAsync", "EmailStandardizeRequest", "StandardizedEmail", "/v1/email"),
        ("StandardizeUrlAsync", "UrlStandardizeRequest", "StandardizedUrl", "/v1/url"),
        ("StandardizeSocialAsync", "SocialStandardizeRequest", "StandardizedSocial", "/v1/social"),
        ("StandardizeContactAsync", "ContactStandardizeRequest", "StandardizedContact", "/v1/contact"),
    ):
        assert re.search(
            rf"public\s+async\s+Task<{res_type}\?>\s+{method}\(\s*{req_type}\s+request",
            dotnet_client,
        )
        assert f'"{endpoint}"' in dotnet_client
