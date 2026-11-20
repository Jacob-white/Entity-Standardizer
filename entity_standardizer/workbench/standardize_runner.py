"""Grouped multi-pillar file standardization, dry-run diff preview, and streaming execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from pathlib import Path
import time
from typing import Any

from entity_standardizer.address.models import StandardizedAddress, extract_street_core_key
from entity_standardizer.address.standardizer import standardize_address
from entity_standardizer.batch import _csv_safe_cell
from entity_standardizer.company import (
    StandardizedCompany,
    compact_company_key,
    extract_company_acronym,
    resolve_brand_lineage,
    standardize_company,
)
from entity_standardizer.group import StandardizedAdvisorGroup, standardize_advisor_group
from entity_standardizer.identifiers import (
    StandardizedIdentifier,
    standardize_crd,
    standardize_external_id,
)
from entity_standardizer.joint import StandardizedContact, standardize_contact
from entity_standardizer.models import PhoneRiskFlag, StandardizedPhone
from entity_standardizer.person import (
    StandardizedJobTitle,
    StandardizedPerson,
    split_compound_persons,
    standardize_job_title,
)
from entity_standardizer.registry import get_dial_plan, normalize_country_iso2
from entity_standardizer.standardizer import mask_phone, standardize_phone
from entity_standardizer.web import (
    StandardizedEmail,
    StandardizedSocial,
    StandardizedUrl,
    standardize_email,
    standardize_social,
    standardize_url,
)
from entity_standardizer.workbench.io_formats import (
    cell_to_input_text,
    close_row_iter,
    detect_file_format,
    iter_tabular_rows,
    sanitize_row_for_json,
    write_tabular_output,
)
from entity_standardizer.workbench.mapping import ColumnMapping, FieldRole, MappingConfig
from entity_standardizer.workbench.options import StandardizationOptions

_PLACEHOLDER_STRINGS: frozenset[str] = frozenset(
    {
        "NA",
        "N/A",
        "N / A",
        "NONE",
        "NULL",
        "UNKNOWN",
        "TBD",
        "PENDING",
        "UNAVAILABLE",
        "REDACTED",
        "NOT PROVIDED",
        "NO PHONE",
        "DECLINED",
        "REFUSED",
        "DEFAULT",
        "SAME AS ABOVE",
        "TEST",
        "-",
        "--",
        ".",
        "0",
        "000-000-0000",
        "(000) 000-0000",
    }
)

_KEEP_UPPER_TOKENS: frozenset[str] = frozenset(
    {
        "LLC",
        "LLP",
        "LLLP",
        "LP",
        "INC",
        "CORP",
        "LTD",
        "PLC",
        "PLLC",
        "PC",
        "NA",
        "FSB",
        "SA",
        "SARL",
        "SCSP",
        "SPC",
        "GMBH",
        "KGAA",
        "AG",
        "SE",
        "BV",
        "NV",
        "KK",
        "OU",
        "OY",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "JR",
        "SR",
        "MD",
        "PHD",
        "CFA",
        "CFP",
        "CPA",
        "CAIA",
        "CIMA",
        "PO",
        "NW",
        "NE",
        "SW",
        "SE",
        "N",
        "S",
        "E",
        "W",
        "US",
        "USA",
        "UK",
        "EU",
        "DC",
        "DBA",
        "FKA",
    }
)

_PERSON_COMPONENT_ROLES: tuple[str, ...] = (
    FieldRole.SALUTATION.value,
    FieldRole.FIRST_NAME.value,
    FieldRole.MIDDLE_NAME.value,
    FieldRole.LAST_NAME.value,
    FieldRole.GENERATIONAL_SUFFIX.value,
    FieldRole.CREDENTIALS.value,
)

_ADDRESS_ROLES: frozenset[str] = frozenset(
    {
        FieldRole.STREET1.value,
        FieldRole.STREET2.value,
        FieldRole.CITY.value,
        FieldRole.STATE.value,
        FieldRole.POSTAL_CODE.value,
        FieldRole.COUNTRY.value,
    }
)

_CONTACT_PILLAR_ROLES: frozenset[str] = _ADDRESS_ROLES | frozenset(
    {
        FieldRole.PHONE.value,
        FieldRole.FAX.value,
        FieldRole.ORGANIZATION.value,
        FieldRole.PERSON_NAME.value,
        *_PERSON_COMPONENT_ROLES,
        FieldRole.JOB_TITLE.value,
        FieldRole.EMAIL.value,
        FieldRole.WEBSITE.value,
        FieldRole.SOCIAL.value,
    }
)


def _is_placeholder_text(raw_str: str) -> bool:
    return " ".join(raw_str.strip().upper().split()) in _PLACEHOLDER_STRINGS


def _clean_in(raw_str: str | None) -> str | None:
    if not raw_str or _is_placeholder_text(raw_str):
        return None
    return raw_str


def apply_text_case(value: str, mode: str) -> str:
    """Format standardized uppercase text as UPPERCASE or smart Title Case preserving acronyms/suffixes."""
    if not value or mode == "upper":
        return value.upper() if value else value
    out: list[str] = []
    for tok in value.split():
        if tok.upper() in _KEEP_UPPER_TOKENS:
            out.append(tok.upper())
        else:
            out.append("-".join(part.capitalize() for part in tok.split("-")))
    return " ".join(out)


def format_country_value(
    country_val: str | None,
    raw_val: str,
    country_format: str,
    address_case: str,
) -> str | None:
    """Format a standardized country code into ISO-2, ISO-3, or full country name."""
    if not country_val or country_val == "ZZZ":
        return None
    plan = get_dial_plan(country_val)
    if plan is None:
        return country_val
    if country_format == "auto":
        stripped = raw_val.strip()
        if len(stripped) == 2 and stripped.isalpha():
            fmt = "iso2"
        elif len(stripped) == 3 and stripped.isalpha():
            fmt = "iso3"
        elif stripped:
            fmt = "name"
        else:
            fmt = "iso2"
    else:
        fmt = country_format

    if fmt == "iso2":
        return plan.iso2
    if fmt == "iso3":
        return plan.iso3
    return apply_text_case(plan.name, address_case)


def format_phone_value(res: StandardizedPhone, options: StandardizationOptions) -> str | None:
    """Format a StandardizedPhone according to phone_format and extension_mode options."""
    if not res.is_valid or not res.e164:
        return None
    fmt_res = res
    if options.extension_mode == "strip" and res.extension:
        fmt_res = standardize_phone(
            res.e164,
            country=res.country_iso2,
            default_country=options.default_country,
        )
    if options.phone_format == "e164":
        return fmt_res.e164
    if options.phone_format == "national":
        return fmt_res.national
    if options.phone_format == "international":
        return fmt_res.international
    if options.phone_format == "rfc3966":
        return fmt_res.rfc3966
    if options.phone_format == "masked_partial":
        return mask_phone(fmt_res.e164, strategy="partial")
    return mask_phone(fmt_res.e164, strategy="redact")


def format_email_value(raw_email: str, options: StandardizationOptions) -> tuple[StandardizedEmail, str | None]:
    """Standardize an email while honoring typo-healing, Gmail-dot, and +subaddress options."""
    res = standardize_email(raw_email)
    if not res.is_valid or not res.email:
        return res, None
    local = res.local_part or ""
    domain = res.domain or ""
    if not options.email_heal_typos and "DOMAIN_TYPO_HEALED" in res.healing_actions:
        domain = res.raw_input.strip().rstrip(">").rsplit("@", 1)[1].strip().lower()
    if (
        not options.email_canonicalize_gmail_dots
        and "GMAIL_DOTS_CANONICALIZED" in res.healing_actions
        and res.raw_local_part
    ):
        local = res.raw_local_part.split("+", 1)[0]
    if not options.email_strip_subaddress and res.subaddress:
        local = f"{local}+{res.subaddress}"
    return res, f"{local}@{domain}"


def format_person_full_name(person: StandardizedPerson, options: StandardizationOptions) -> str | None:
    """Format a StandardizedPerson full name respecting nickname root, name order, and casing."""
    if not person.is_valid:
        return None
    first = (
        person.root_first_name
        if (options.use_nickname_root and person.root_first_name)
        else person.first_name
    )
    if options.person_format == "last_comma_first" and person.last_name:
        given = " ".join(part for part in (first, person.middle_name) if part)
        base = f"{person.last_name}, {given}" if given else person.last_name
        if person.generational_suffix:
            base = f"{base}, {person.generational_suffix}"
    else:
        base = " ".join(
            part for part in (first, person.middle_name, person.last_name, person.generational_suffix) if part
        )
    return apply_text_case(base, options.person_case) if base else None


def resolve_output_value(
    raw_str: str,
    std_val: str | None,
    is_valid: bool,
    is_placeholder: bool,
    invalid_policy: str,
) -> tuple[str, str]:
    """Determine final output string and cell status ('modified', 'unchanged', 'cleared', 'invalid')."""
    if not raw_str:
        return (std_val, "modified") if std_val else ("", "unchanged")
    if is_valid and std_val and not is_placeholder:
        status = "unchanged" if std_val == raw_str else "modified"
        return std_val, status
    if invalid_policy == "clear_all_invalid" or (
        invalid_policy == "clear_placeholders_keep_raw" and is_placeholder
    ):
        return "", "cleared"
    return raw_str, "invalid"


def _assemble_person_input(role_raw: dict[str, str]) -> str:
    direct = _clean_in(role_raw.get(FieldRole.PERSON_NAME.value, ""))
    if direct:
        return direct
    core = [
        role_raw.get(FieldRole.SALUTATION.value, ""),
        role_raw.get(FieldRole.FIRST_NAME.value, ""),
        role_raw.get(FieldRole.MIDDLE_NAME.value, ""),
        role_raw.get(FieldRole.LAST_NAME.value, ""),
    ]
    base = " ".join(part for part in core if _clean_in(part))
    tail = [
        role_raw.get(FieldRole.GENERATIONAL_SUFFIX.value, ""),
        role_raw.get(FieldRole.CREDENTIALS.value, ""),
    ]
    extra = ", ".join(part for part in tail if _clean_in(part))
    if base and extra:
        return f"{base}, {extra}"
    return base or extra


@dataclass(slots=True)
class RowStandardizeAudit:
    """Cell-level audit summary produced while standardizing a single input row."""

    cell_changes: dict[str, str] = field(default_factory=dict)
    cross_healing_actions: list[str] = field(default_factory=list)
    cells_changed: int = 0
    cells_cleared: int = 0
    invalid_cells: int = 0


def compute_output_columns(
    base_columns: Sequence[str],
    mapping_config: MappingConfig,
    options: StandardizationOptions,
) -> list[str]:
    """Determine ordered output columns for standardization preview and file export."""
    eff_mapping = mapping_config.for_columns(base_columns)
    out_cols = list(base_columns)
    seen = set(out_cols)

    def _add(col_name: str) -> None:
        if col_name not in seen:
            seen.add(col_name)
            out_cols.append(col_name)

    for m in eff_mapping.mappings:
        if options.column_mode == "append_std":
            _add(f"{m.column}_std")
        elif options.column_mode == "overwrite_keep_raw":
            _add(f"{m.column}_raw")

    if options.couple_split_mode == "append_secondary_col":
        for unit_id, base_group, items in eff_mapping.execution_units():
            roles = {m.role: m.column for m in items}
            if FieldRole.PERSON_NAME.value in roles:
                _add(f"{roles[FieldRole.PERSON_NAME.value]}_secondary")
            elif any(r in roles for r in _PERSON_COMPONENT_ROLES):
                _add(f"{base_group}_secondary_person")

    for unit_id, base_group, items in eff_mapping.execution_units():
        role_set = {m.role for m in items}
        if options.include_audit_cols:
            for sfx in ("valid", "confidence", "key", "healing_actions"):
                _add(f"{unit_id}_{sfx}")
        if options.include_matching_keys:
            if FieldRole.ORGANIZATION.value in role_set:
                for kcol in ("company_brand_lineage", "company_acronym", "company_compact_key"):
                    _add(f"{unit_id}_{kcol}")
            if FieldRole.PERSON_NAME.value in role_set or bool(role_set & set(_PERSON_COMPONENT_ROLES)):
                for kcol in ("person_root_key", "person_alt_keys"):
                    _add(f"{unit_id}_{kcol}")
            if role_set & _ADDRESS_ROLES:
                for kcol in ("address_postal_building_key", "address_street_core_key"):
                    _add(f"{unit_id}_{kcol}")
        if options.enable_geocoding and (role_set & _ADDRESS_ROLES):
            for gcol in ("latitude", "longitude", "precision"):
                _add(f"{unit_id}_{gcol}")

    return out_cols


def _write_mapped_cell(
    row_dict: dict[str, Any],
    col: str,
    raw_str: Any,
    final_val: Any,
    status: str,
    options: StandardizationOptions,
    audit: RowStandardizeAudit,
    *,
    healed: bool = False,
    rescued: bool = False,
) -> None:
    if options.column_mode == "append_std":
        row_dict[f"{col}_std"] = final_val
    elif options.column_mode == "overwrite_keep_raw":
        row_dict[f"{col}_raw"] = raw_str
        row_dict[col] = final_val
    else:
        row_dict[col] = final_val

    tag = status
    if status == "modified":
        audit.cells_changed += 1
        if rescued:
            tag = "rescued"
        elif healed:
            tag = "healed"
    elif status == "cleared":
        audit.cells_cleared += 1
    elif status == "invalid":
        audit.invalid_cells += 1
    audit.cell_changes[col] = tag


def _person_component_value(person: StandardizedPerson, role: str, options: StandardizationOptions) -> str:
    if role == FieldRole.SALUTATION.value:
        return apply_text_case(person.salutation or "", options.person_case)
    if role == FieldRole.FIRST_NAME.value:
        first = (
            person.root_first_name
            if (options.use_nickname_root and person.root_first_name)
            else (person.first_name or "")
        )
        return apply_text_case(first, options.person_case)
    if role == FieldRole.MIDDLE_NAME.value:
        return apply_text_case(person.middle_name or "", options.person_case)
    if role == FieldRole.LAST_NAME.value:
        return apply_text_case(person.last_name or "", options.person_case)
    if role == FieldRole.GENERATIONAL_SUFFIX.value:
        return apply_text_case(person.generational_suffix or "", options.person_case)
    return ", ".join(person.credentials) if person.credentials else ""


def _standardize_standalone_contact_roles(
    role_raw: dict[str, str],
    default_country: str,
    options: StandardizationOptions,
) -> tuple[
    StandardizedAddress | None,
    StandardizedPhone | None,
    StandardizedPhone | None,
    StandardizedCompany | None,
    StandardizedPerson | None,
    tuple[StandardizedPerson, ...],
    StandardizedJobTitle | None,
    StandardizedEmail | None,
    StandardizedUrl | None,
    StandardizedSocial | None,
    list[str],
]:
    addr_obj: StandardizedAddress | None = None
    country_in = _clean_in(role_raw.get(FieldRole.COUNTRY.value))
    if any(_clean_in(role_raw.get(r, "")) for r in _ADDRESS_ROLES):
        addr_obj = standardize_address(
            street1=_clean_in(role_raw.get(FieldRole.STREET1.value)),
            street2=_clean_in(role_raw.get(FieldRole.STREET2.value)),
            city=_clean_in(role_raw.get(FieldRole.CITY.value)),
            state=_clean_in(role_raw.get(FieldRole.STATE.value)),
            postal_code=_clean_in(role_raw.get(FieldRole.POSTAL_CODE.value)),
            country=country_in or default_country,
            allow_locality=True,
            enable_geocoding=options.enable_geocoding,
        )

    phone_in = _clean_in(role_raw.get(FieldRole.PHONE.value, ""))
    phone_obj = (
        standardize_phone(phone_in, country=country_in, default_country=default_country)
        if phone_in
        else None
    )
    fax_in = _clean_in(role_raw.get(FieldRole.FAX.value, ""))
    fax_obj = (
        standardize_phone(fax_in, country=country_in, default_country=default_country)
        if fax_in
        else None
    )
    org_in = _clean_in(role_raw.get(FieldRole.ORGANIZATION.value, ""))
    org_obj = standardize_company(org_in, country=country_in) if org_in else None

    person_raw = _assemble_person_input(role_raw)
    person_obj: StandardizedPerson | None = None
    extra_persons: tuple[StandardizedPerson, ...] = ()
    actions: list[str] = []
    if person_raw:
        split_pers = split_compound_persons(person_raw)
        person_obj = split_pers[0]
        if len(split_pers) > 1:
            extra_persons = tuple(split_pers[1:])
            actions.append("COMPOUND_PERSON_SPLIT")

    title_in = _clean_in(role_raw.get(FieldRole.JOB_TITLE.value, ""))
    title_obj = standardize_job_title(title_in) if title_in else None
    email_in = _clean_in(role_raw.get(FieldRole.EMAIL.value, ""))
    email_obj = standardize_email(email_in) if email_in else None
    url_in = _clean_in(role_raw.get(FieldRole.WEBSITE.value, ""))
    url_obj = standardize_url(url_in) if url_in else None
    social_in = _clean_in(role_raw.get(FieldRole.SOCIAL.value, ""))
    social_obj = standardize_social(social_in) if social_in else None
    return (
        addr_obj,
        phone_obj,
        fax_obj,
        org_obj,
        person_obj,
        extra_persons,
        title_obj,
        email_obj,
        url_obj,
        social_obj,
        actions,
    )


def standardize_row_with_config(
    row: Mapping[str, Any],
    mapping_config: MappingConfig,
    options: StandardizationOptions,
    *,
    is_delimited_export: bool = False,
) -> tuple[list[dict[str, Any]], RowStandardizeAudit]:
    """Standardize a single input row according to grouped mappings and options."""
    base_out: dict[str, Any] = dict(row)
    audit = RowStandardizeAudit()
    group_country_ctx: dict[str, str] = {}
    row_clones_by_unit: list[
        tuple[str, list[ColumnMapping], tuple[StandardizedPerson, ...], list[str], list[str]]
    ] = []

    for unit_id, base_group, items in mapping_config.execution_units():
        role_to_col = {m.role: m.column for m in items}
        role_raw = {m.role: cell_to_input_text(row.get(m.column)) for m in items}
        unit_default_country = group_country_ctx.get(base_group, options.default_country)
        has_contact_roles = any(r in _CONTACT_PILLAR_ROLES for r in role_to_col)
        cross_heal_on = options.enable_cross_healing and mapping_config.is_cross_healing_enabled(unit_id)

        addr_obj: StandardizedAddress | None = None
        phone_obj: StandardizedPhone | None = None
        fax_obj: StandardizedPhone | None = None
        org_obj: StandardizedCompany | None = None
        person_obj: StandardizedPerson | None = None
        extra_persons: tuple[StandardizedPerson, ...] = ()
        title_obj: StandardizedJobTitle | None = None
        email_obj: StandardizedEmail | None = None
        url_obj: StandardizedUrl | None = None
        social_obj: StandardizedSocial | None = None
        actions: list[str] = []

        if has_contact_roles and cross_heal_on:
            person_in = _assemble_person_input(role_raw)
            contact: StandardizedContact = standardize_contact(
                street1=_clean_in(role_raw.get(FieldRole.STREET1.value)),
                street2=_clean_in(role_raw.get(FieldRole.STREET2.value)),
                city=_clean_in(role_raw.get(FieldRole.CITY.value)),
                state=_clean_in(role_raw.get(FieldRole.STATE.value)),
                postal_code=_clean_in(role_raw.get(FieldRole.POSTAL_CODE.value)),
                country=_clean_in(role_raw.get(FieldRole.COUNTRY.value)),
                phone=_clean_in(role_raw.get(FieldRole.PHONE.value)),
                fax=_clean_in(role_raw.get(FieldRole.FAX.value)),
                organization=_clean_in(role_raw.get(FieldRole.ORGANIZATION.value)),
                person_name=person_in or None,
                job_title=_clean_in(role_raw.get(FieldRole.JOB_TITLE.value)),
                email=_clean_in(role_raw.get(FieldRole.EMAIL.value)),
                website=_clean_in(role_raw.get(FieldRole.WEBSITE.value)),
                social=_clean_in(role_raw.get(FieldRole.SOCIAL.value)),
                default_country=unit_default_country,
                allow_locality=True,
            )
            actions = list(contact.cross_healing_actions)
            addr_obj = contact.address
            if options.enable_geocoding and addr_obj.address_status != "parse_failed":
                addr_obj = standardize_address(
                    street1=addr_obj.street1 or None,
                    street2=addr_obj.street2 or None,
                    city=addr_obj.city or None,
                    state=addr_obj.state or None,
                    postal_code=addr_obj.postal_code or None,
                    country=addr_obj.country or unit_default_country,
                    allow_locality=True,
                    enable_geocoding=True,
                )
            phone_obj = contact.phone
            fax_obj = contact.fax
            org_obj = contact.organization
            person_obj = contact.person
            extra_persons = contact.additional_persons
            title_obj = contact.job_title
            email_obj = contact.email
            url_obj = contact.website
            social_obj = contact.social

            if not options.rescue_misplaced_fields:
                if "PHONE_RESCUED_FROM_ADDRESS_FIELD" in actions and not role_raw.get(FieldRole.PHONE.value):
                    phone_obj = StandardizedPhone(raw_input="")
                if "EMAIL_RESCUED_FROM_FIELD" in actions and not role_raw.get(FieldRole.EMAIL.value):
                    email_obj = None
                if "URL_RESCUED_FROM_FIELD" in actions and not role_raw.get(FieldRole.WEBSITE.value):
                    url_obj = None
                if "ORGANIZATION_RESCUED_FROM_PERSON_FIELD" in actions and not role_raw.get(FieldRole.ORGANIZATION.value):
                    org_obj = None

            if not options.infer_blank_fields:
                if "ORGANIZATION_INFERRED_FROM_DOMAIN" in actions and not role_raw.get(FieldRole.ORGANIZATION.value):
                    org_obj = None
                if "PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF" in actions and not person_in:
                    person_obj = None
        elif has_contact_roles:
            (
                addr_obj,
                phone_obj,
                fax_obj,
                org_obj,
                person_obj,
                extra_persons,
                title_obj,
                email_obj,
                url_obj,
                social_obj,
                actions,
            ) = _standardize_standalone_contact_roles(role_raw, unit_default_country, options)

        if base_group not in group_country_ctx:
            raw_cntry_plan = get_dial_plan(_clean_in(role_raw.get(FieldRole.COUNTRY.value)) or "")
            if addr_obj and addr_obj.address_status != "parse_failed" and addr_obj.country and addr_obj.country != "ZZZ":
                group_country_ctx[base_group] = normalize_country_iso2(addr_obj.country) or options.default_country
            elif raw_cntry_plan is not None:
                group_country_ctx[base_group] = raw_cntry_plan.iso2
            elif phone_obj is not None and phone_obj.is_valid and phone_obj.country_iso2:
                group_country_ctx[base_group] = phone_obj.country_iso2

        audit.cross_healing_actions.extend(actions)

        # Write address columns
        addr_valid = addr_obj is not None and addr_obj.address_status != "parse_failed"
        healed_addr = any(
            act in actions
            for act in (
                "ADDRESS_COUNTRY_INFERRED_FROM_PHONE",
                "ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA",
                "COUNTRY_INFERRED_FROM_ENTITY_PILLARS",
            )
        )
        email_rescued_to_col = (
            options.rescue_misplaced_fields
            and "EMAIL_RESCUED_FROM_FIELD" in actions
            and FieldRole.EMAIL.value in role_to_col
        )
        addr_non_email_rescued = options.rescue_misplaced_fields and (
            ("PHONE_RESCUED_FROM_ADDRESS_FIELD" in actions and FieldRole.PHONE.value in role_to_col)
            or ("URL_RESCUED_FROM_FIELD" in actions and FieldRole.WEBSITE.value in role_to_col)
        )
        for role in _ADDRESS_ROLES:
            if role not in role_to_col:
                continue
            col = role_to_col[role]
            raw_v = role_raw[role]
            std_v: str | None = None
            if addr_obj is not None and addr_valid:
                if role == FieldRole.STREET1.value:
                    s1 = addr_obj.street1 or ""
                    if not options.split_secondary_unit and addr_obj.street2:
                        s1 = f"{s1} {addr_obj.street2}".strip()
                    std_v = apply_text_case(s1, options.address_case) if s1 else None
                elif role == FieldRole.STREET2.value:
                    s2 = addr_obj.street2 if options.split_secondary_unit else ""
                    std_v = apply_text_case(s2, options.address_case) if s2 else None
                elif role == FieldRole.CITY.value:
                    std_v = apply_text_case(addr_obj.city, options.address_case) if addr_obj.city else None
                elif role == FieldRole.STATE.value:
                    std_v = addr_obj.state or None
                elif role == FieldRole.POSTAL_CODE.value:
                    std_v = addr_obj.postal_code or None
                else:
                    std_v = format_country_value(
                        addr_obj.country, raw_v, options.country_format, options.address_case
                    )
            elif role == FieldRole.COUNTRY.value:
                c_plan = get_dial_plan(raw_v) if (raw_v and not _is_placeholder_text(raw_v)) else None
                std_v = (
                    format_country_value(c_plan.iso3, raw_v, options.country_format, options.address_case)
                    if c_plan is not None
                    else None
                )
            cell_rescued = False
            if role == FieldRole.STREET2.value and addr_valid and std_v is None and not _is_placeholder_text(raw_v):
                final_v = ""
                status = "modified" if raw_v else "unchanged"
            elif (
                not addr_valid
                and raw_v
                and role in (FieldRole.STREET1.value, FieldRole.STREET2.value)
                and (addr_non_email_rescued or (email_rescued_to_col and "@" in raw_v))
            ):
                final_v, status, cell_rescued = "", "modified", True
            else:
                final_v, status = resolve_output_value(
                    raw_v, std_v, bool(std_v), _is_placeholder_text(raw_v), options.invalid_policy
                )
            _write_mapped_cell(
                base_out, col, raw_v, final_v, status, options, audit, healed=healed_addr, rescued=cell_rescued
            )

        # Write phone & fax
        for p_role, p_res, rescued_flag, healed_flag in (
            (
                FieldRole.PHONE.value,
                phone_obj,
                "PHONE_RESCUED_FROM_ADDRESS_FIELD" in actions,
                "PHONE_HEALED_FROM_STANDARDIZED_ADDRESS" in actions,
            ),
            (FieldRole.FAX.value, fax_obj, False, False),
        ):
            if p_role not in role_to_col:
                continue
            col = role_to_col[p_role]
            raw_v = role_raw[p_role]
            is_valid = p_res is not None and p_res.is_valid
            std_v = format_phone_value(p_res, options) if is_valid else None
            is_ph = _is_placeholder_text(raw_v) or (
                p_res is not None
                and (
                    PhoneRiskFlag.FICTITIOUS_RANGE in p_res.risk_flags
                    or PhoneRiskFlag.REPEATING_DIGITS in p_res.risk_flags
                )
            )
            final_v, status = resolve_output_value(
                raw_v, std_v, is_valid, is_ph, options.invalid_policy
            )
            _write_mapped_cell(
                base_out,
                col,
                raw_v,
                final_v,
                status,
                options,
                audit,
                healed=healed_flag,
                rescued=rescued_flag,
            )

        # Write organization
        if FieldRole.ORGANIZATION.value in role_to_col:
            col = role_to_col[FieldRole.ORGANIZATION.value]
            raw_v = role_raw[FieldRole.ORGANIZATION.value]
            is_valid = org_obj is not None and org_obj.is_valid
            raw_org_txt = (
                (org_obj.brand_stem if options.company_style == "brand_stem" else org_obj.legal_name)
                if is_valid and org_obj is not None
                else None
            )
            std_v = apply_text_case(raw_org_txt, options.company_case) if raw_org_txt else None
            if not is_valid and raw_v and email_rescued_to_col and "@" in raw_v:
                final_v, status, rescued_org = "", "modified", True
            else:
                final_v, status = resolve_output_value(
                    raw_v, std_v, is_valid, _is_placeholder_text(raw_v), options.invalid_policy
                )
                rescued_org = any(
                    a in actions
                    for a in ("ORGANIZATION_RESCUED_FROM_PERSON_FIELD", "ORGANIZATION_INFERRED_FROM_DOMAIN")
                )
            _write_mapped_cell(
                base_out, col, raw_v, final_v, status, options, audit, rescued=rescued_org
            )

        # Write person (full + components)
        rescued_person = "PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF" in actions
        org_rescued_from_person = (
            options.rescue_misplaced_fields
            and "ORGANIZATION_RESCUED_FROM_PERSON_FIELD" in actions
            and FieldRole.ORGANIZATION.value in role_to_col
            and not (person_obj is not None and person_obj.is_valid)
        )
        if FieldRole.PERSON_NAME.value in role_to_col:
            col = role_to_col[FieldRole.PERSON_NAME.value]
            raw_v = role_raw[FieldRole.PERSON_NAME.value]
            is_valid = person_obj is not None and person_obj.is_valid
            std_v = format_person_full_name(person_obj, options) if is_valid and person_obj is not None else None
            if raw_v and not is_valid and (org_rescued_from_person or (email_rescued_to_col and "@" in raw_v)):
                final_v, status, p_rescued = "", "modified", True
            else:
                final_v, status = resolve_output_value(
                    raw_v, std_v, is_valid, _is_placeholder_text(raw_v), options.invalid_policy
                )
                p_rescued = rescued_person
            _write_mapped_cell(
                base_out, col, raw_v, final_v, status, options, audit, rescued=p_rescued
            )

        for comp_role in _PERSON_COMPONENT_ROLES:
            if comp_role not in role_to_col:
                continue
            col = role_to_col[comp_role]
            raw_v = role_raw[comp_role]
            is_valid = person_obj is not None and person_obj.is_valid
            std_v = (
                _person_component_value(person_obj, comp_role, options) or None
                if is_valid and person_obj is not None
                else None
            )
            if raw_v and not is_valid and (org_rescued_from_person or (email_rescued_to_col and "@" in raw_v)):
                final_v, status, c_rescued = "", "modified", True
            elif is_valid and std_v is None and not _is_placeholder_text(raw_v):
                final_v = ""
                status = "modified" if raw_v else "unchanged"
                c_rescued = False
            else:
                final_v, status = resolve_output_value(
                    raw_v, std_v, bool(std_v), _is_placeholder_text(raw_v), options.invalid_policy
                )
                c_rescued = rescued_person
            _write_mapped_cell(
                base_out, col, raw_v, final_v, status, options, audit, rescued=c_rescued
            )

        if options.couple_split_mode == "append_secondary_col":
            sec_vals = [
                formatted
                for extra_p in extra_persons
                if (formatted := format_person_full_name(extra_p, options))
            ]
            if FieldRole.PERSON_NAME.value in role_to_col:
                base_out[f"{role_to_col[FieldRole.PERSON_NAME.value]}_secondary"] = "; ".join(sec_vals)
            elif any(r in role_to_col for r in _PERSON_COMPONENT_ROLES):
                base_out[f"{base_group}_secondary_person"] = "; ".join(sec_vals)

        # Write job title
        if FieldRole.JOB_TITLE.value in role_to_col:
            col = role_to_col[FieldRole.JOB_TITLE.value]
            raw_v = role_raw[FieldRole.JOB_TITLE.value]
            is_valid = title_obj is not None and title_obj.is_valid
            std_v = (
                apply_text_case(title_obj.normalized_title, options.person_case)
                if is_valid and title_obj is not None and title_obj.normalized_title
                else None
            )
            final_v, status = resolve_output_value(
                raw_v, std_v, is_valid, _is_placeholder_text(raw_v), options.invalid_policy
            )
            _write_mapped_cell(base_out, col, raw_v, final_v, status, options, audit)

        # Write email
        if FieldRole.EMAIL.value in role_to_col:
            col = role_to_col[FieldRole.EMAIL.value]
            raw_v = role_raw[FieldRole.EMAIL.value]
            fmt_email_str: str | None = None
            eff_email = email_obj
            if email_obj is not None and email_obj.is_valid:
                eff_email, fmt_email_str = format_email_value(raw_v or email_obj.raw_input, options)
            elif eff_email is None and raw_v:
                eff_email = standardize_email(raw_v)
            is_valid = eff_email is not None and eff_email.is_valid
            is_ph = _is_placeholder_text(raw_v) or (
                eff_email is not None and "SENTINEL_DOMAIN_REJECTED" in eff_email.healing_actions
            )
            final_v, status = resolve_output_value(
                raw_v, fmt_email_str, is_valid, is_ph, options.invalid_policy
            )
            _write_mapped_cell(
                base_out,
                col,
                raw_v,
                final_v,
                status,
                options,
                audit,
                rescued="EMAIL_RESCUED_FROM_FIELD" in actions,
            )

        # Write website URL
        if FieldRole.WEBSITE.value in role_to_col:
            col = role_to_col[FieldRole.WEBSITE.value]
            raw_v = role_raw[FieldRole.WEBSITE.value]
            eff_url = url_obj if url_obj is not None else (standardize_url(raw_v) if raw_v else None)
            is_valid = eff_url is not None and eff_url.is_valid
            std_v = eff_url.url if is_valid and eff_url is not None else None
            is_ph = _is_placeholder_text(raw_v) or (
                eff_url is not None and "SENTINEL_DOMAIN_REJECTED" in eff_url.healing_actions
            )
            final_v, status = resolve_output_value(
                raw_v, std_v, is_valid, is_ph, options.invalid_policy
            )
            _write_mapped_cell(
                base_out,
                col,
                raw_v,
                final_v,
                status,
                options,
                audit,
                rescued="URL_RESCUED_FROM_FIELD" in actions,
            )

        # Write social
        if FieldRole.SOCIAL.value in role_to_col:
            col = role_to_col[FieldRole.SOCIAL.value]
            raw_v = role_raw[FieldRole.SOCIAL.value]
            is_valid = social_obj is not None and social_obj.is_valid
            std_v = social_obj.url if is_valid and social_obj is not None else None
            final_v, status = resolve_output_value(
                raw_v, std_v, is_valid, _is_placeholder_text(raw_v), options.invalid_policy
            )
            _write_mapped_cell(base_out, col, raw_v, final_v, status, options, audit)

        # Write non-contact roles (CRD, External ID, Advisor Group, Record ID / Roster passthrough)
        crd_obj: StandardizedIdentifier | None = None
        if FieldRole.CRD.value in role_to_col:
            col = role_to_col[FieldRole.CRD.value]
            raw_v = role_raw[FieldRole.CRD.value]
            crd_obj = standardize_crd(raw_v) if raw_v else None
            is_valid = crd_obj is not None and crd_obj.is_valid
            std_v = crd_obj.canonical_id if is_valid and crd_obj is not None else None
            is_ph = _is_placeholder_text(raw_v) or (crd_obj is not None and crd_obj.is_placeholder)
            final_v, status = resolve_output_value(
                raw_v, std_v, is_valid, is_ph, options.invalid_policy
            )
            _write_mapped_cell(base_out, col, raw_v, final_v, status, options, audit)

        ext_obj: StandardizedIdentifier | None = None
        if FieldRole.EXTERNAL_ID.value in role_to_col:
            col = role_to_col[FieldRole.EXTERNAL_ID.value]
            raw_v = role_raw[FieldRole.EXTERNAL_ID.value]
            ext_obj = standardize_external_id(raw_v, pad_width=options.id_pad_width) if raw_v else None
            is_valid = ext_obj is not None and ext_obj.is_valid
            std_v = (
                (ext_obj.padded_id if options.id_pad_width else ext_obj.canonical_id)
                if is_valid and ext_obj is not None
                else None
            )
            is_ph = _is_placeholder_text(raw_v) or (ext_obj is not None and ext_obj.is_placeholder)
            final_v, status = resolve_output_value(
                raw_v, std_v, is_valid, is_ph, options.invalid_policy
            )
            _write_mapped_cell(base_out, col, raw_v, final_v, status, options, audit)

        grp_obj: StandardizedAdvisorGroup | None = None
        if FieldRole.ADVISOR_GROUP.value in role_to_col:
            col = role_to_col[FieldRole.ADVISOR_GROUP.value]
            raw_v = role_raw[FieldRole.ADVISOR_GROUP.value]
            grp_obj = standardize_advisor_group(raw_v) if raw_v else None
            is_valid = grp_obj is not None and grp_obj.is_valid
            std_v = (
                apply_text_case(grp_obj.normalized_name, options.company_case)
                if is_valid and grp_obj is not None and grp_obj.normalized_name
                else None
            )
            final_v, status = resolve_output_value(
                raw_v, std_v, is_valid, _is_placeholder_text(raw_v), options.invalid_policy
            )
            _write_mapped_cell(base_out, col, raw_v, final_v, status, options, audit)

        for pass_role in (FieldRole.RECORD_ID.value, FieldRole.MEMBER_ROSTER.value):
            if pass_role in role_to_col:
                col = role_to_col[pass_role]
                orig_v = row.get(col)
                pass_v = "" if (orig_v is None or (isinstance(orig_v, float) and not math.isfinite(orig_v))) else orig_v
                _write_mapped_cell(base_out, col, pass_v, pass_v, "unchanged", options, audit)

        # Optional Audit, Matching Keys, and Geocoding Columns
        before_p_keys: list[str] = []
        after_p_keys: list[str] = []
        if options.include_audit_cols:
            pillar_objs = [
                p
                for p in (org_obj, person_obj, title_obj, email_obj, url_obj, social_obj, crd_obj, ext_obj, grp_obj)
                if p is not None and p.is_valid
            ]
            unit_valid = (
                addr_valid
                or (phone_obj is not None and phone_obj.is_valid)
                or (fax_obj is not None and fax_obj.is_valid)
                or bool(pillar_objs)
            )
            confs = [float(p.confidence) for p in pillar_objs]
            if addr_valid and addr_obj is not None and addr_obj.confidence_score:
                confs.append(float(addr_obj.confidence_score))
            if phone_obj is not None and phone_obj.is_valid:
                confs.append(float(phone_obj.confidence))
            unit_conf = round(sum(confs) / len(confs), 4) if confs else 0.0
            before_p_keys = [
                k
                for k in (
                    addr_obj.normalized_address_key if addr_valid and addr_obj is not None else None,
                    phone_obj.e164 if phone_obj is not None and phone_obj.is_valid else None,
                    org_obj.company_key if org_obj is not None and org_obj.is_valid else None,
                )
                if k
            ]
            after_p_keys = [
                k
                for k in (
                    email_obj.email_key if email_obj is not None and email_obj.is_valid else None,
                    crd_obj.canonical_id if crd_obj is not None and crd_obj.is_valid else None,
                    ext_obj.canonical_id if ext_obj is not None and ext_obj.is_valid else None,
                )
                if k
            ]
            unit_keys = list(
                filter(
                    None,
                    (
                        *before_p_keys,
                        person_obj.person_root_key if person_obj is not None and person_obj.is_valid else None,
                        *after_p_keys,
                    ),
                )
            )
            base_out[f"{unit_id}_valid"] = str(unit_valid)
            base_out[f"{unit_id}_confidence"] = f"{unit_conf:.4f}"
            base_out[f"{unit_id}_key"] = "||".join(unit_keys)
            base_out[f"{unit_id}_healing_actions"] = "|".join(actions)

        if options.couple_split_mode == "split_rows" and extra_persons and person_obj is not None:
            row_clones_by_unit.append((unit_id, items, (person_obj, *extra_persons), before_p_keys, after_p_keys))

        role_set = set(role_to_col.keys())
        if options.include_matching_keys:
            if FieldRole.ORGANIZATION.value in role_set:
                base_out[f"{unit_id}_company_brand_lineage"] = (
                    (resolve_brand_lineage(org_obj) or "") if org_obj is not None and org_obj.is_valid else ""
                )
                base_out[f"{unit_id}_company_acronym"] = (
                    (extract_company_acronym(org_obj) or "") if org_obj is not None and org_obj.is_valid else ""
                )
                base_out[f"{unit_id}_company_compact_key"] = (
                    (compact_company_key(org_obj) or "") if org_obj is not None and org_obj.is_valid else ""
                )
            if FieldRole.PERSON_NAME.value in role_set or bool(role_set & set(_PERSON_COMPONENT_ROLES)):
                base_out[f"{unit_id}_person_root_key"] = (
                    (person_obj.person_root_key or "") if person_obj is not None and person_obj.is_valid else ""
                )
                base_out[f"{unit_id}_person_alt_keys"] = (
                    "|".join(person_obj.person_alt_keys) if person_obj is not None and person_obj.is_valid else ""
                )
            if role_set & _ADDRESS_ROLES:
                base_out[f"{unit_id}_address_postal_building_key"] = (
                    (addr_obj.postal_building_key or "") if addr_valid and addr_obj is not None else ""
                )
                base_out[f"{unit_id}_address_street_core_key"] = (
                    (extract_street_core_key(addr_obj.street1) or "")
                    if addr_valid and addr_obj is not None and addr_obj.street1
                    else ""
                )

        if options.enable_geocoding and (role_set & _ADDRESS_ROLES):
            base_out[f"{unit_id}_latitude"] = (
                addr_obj.latitude if addr_valid and addr_obj is not None and addr_obj.latitude is not None else ""
            )
            base_out[f"{unit_id}_longitude"] = (
                addr_obj.longitude if addr_valid and addr_obj is not None and addr_obj.longitude is not None else ""
            )
            base_out[f"{unit_id}_precision"] = (
                (addr_obj.precision or "") if addr_valid and addr_obj is not None else ""
            )

    out_rows: list[dict[str, Any]] = [base_out]
    if row_clones_by_unit:
        clone_unit_id, unit_items, split_list, before_p_keys, after_p_keys = row_clones_by_unit[0]
        unit_roles = {m.role: m.column for m in unit_items}
        out_rows = []
        for sp_person in split_list:
            clone = dict(base_out)
            if FieldRole.PERSON_NAME.value in unit_roles:
                p_col = unit_roles[FieldRole.PERSON_NAME.value]
                target_col = f"{p_col}_std" if options.column_mode == "append_std" else p_col
                clone[target_col] = format_person_full_name(sp_person, options) or ""
            for comp_role in _PERSON_COMPONENT_ROLES:
                if comp_role in unit_roles:
                    c_col = unit_roles[comp_role]
                    target_col = f"{c_col}_std" if options.column_mode == "append_std" else c_col
                    clone[target_col] = _person_component_value(sp_person, comp_role, options)
            if options.include_matching_keys:
                clone[f"{clone_unit_id}_person_root_key"] = sp_person.person_root_key or ""
                clone[f"{clone_unit_id}_person_alt_keys"] = "|".join(sp_person.person_alt_keys)
            if options.include_audit_cols:
                clone[f"{clone_unit_id}_key"] = "||".join(
                    filter(None, (*before_p_keys, sp_person.person_root_key, *after_p_keys))
                )
            out_rows.append(clone)

    if options.csv_formula_guard and is_delimited_export:
        out_rows = [{k: _csv_safe_cell(v) for k, v in r.items()} for r in out_rows]

    return out_rows, audit


def preview_standardize_source(
    path: str | Path,
    mapping_config: MappingConfig,
    options: StandardizationOptions,
    *,
    limit: int = 50,
    delimiter_override: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Run a dry-run preview of standardization on up to `limit` sample rows with cell diffs."""
    p = Path(path)
    spec = detect_file_format(p, delimiter_override=delimiter_override, sheet_name=sheet_name)
    is_delim = spec.format in ("csv", "tsv", "psv", "delimited")
    columns, row_iter = iter_tabular_rows(p, spec)
    eff_mapping = mapping_config.for_columns(columns)
    out_columns = compute_output_columns(columns, eff_mapping, options)

    preview_rows: list[dict[str, Any]] = []
    cells_changed = 0
    cells_cleared = 0
    invalid_cells = 0
    healing_counts: dict[str, int] = {}

    try:
        for idx, row in enumerate(row_iter):
            if idx >= limit:
                break
            out_rows, audit = standardize_row_with_config(
                row, eff_mapping, options, is_delimited_export=is_delim
            )
            cells_changed += audit.cells_changed
            cells_cleared += audit.cells_cleared
            invalid_cells += audit.invalid_cells
            for act in audit.cross_healing_actions:
                healing_counts[act] = healing_counts.get(act, 0) + 1
            preview_rows.append(
                {
                    "row_index": idx,
                    "before": sanitize_row_for_json(row),
                    "after": sanitize_row_for_json(out_rows[0]),
                    "split_count": len(out_rows),
                    "cell_changes": audit.cell_changes,
                    "cross_healing_actions": list(dict.fromkeys(audit.cross_healing_actions)),
                }
            )
    finally:
        close_row_iter(row_iter)

    return {
        "input_columns": columns,
        "output_columns": out_columns,
        "format_spec": spec.to_dict(),
        "preview_count": len(preview_rows),
        "cells_changed": cells_changed,
        "cells_cleared": cells_cleared,
        "invalid_cells": invalid_cells,
        "cross_healing_counts": healing_counts,
        "rows": preview_rows,
    }


def standardize_tabular_file(
    input_path: str | Path,
    output_path: str | Path,
    mapping_config: MappingConfig,
    options: StandardizationOptions,
    *,
    delimiter_override: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Stream-standardize a multi-format file and write same-format output to output_path."""
    t0 = time.perf_counter()
    in_p = Path(input_path)
    out_p = Path(output_path)
    spec = detect_file_format(in_p, delimiter_override=delimiter_override, sheet_name=sheet_name)
    is_delim = spec.format in ("csv", "tsv", "psv", "delimited")
    columns, row_iter = iter_tabular_rows(in_p, spec)
    eff_mapping = mapping_config.for_columns(columns)
    out_columns = compute_output_columns(columns, eff_mapping, options)

    input_rows = 0
    modified_rows = 0
    cells_changed = 0
    cells_cleared = 0
    invalid_cells = 0
    healing_counts: dict[str, int] = {}
    per_column_changes: dict[str, int] = {}

    def _stream_out():
        nonlocal input_rows, modified_rows, cells_changed, cells_cleared, invalid_cells
        try:
            for row in row_iter:
                input_rows += 1
                out_rows, audit = standardize_row_with_config(
                    row, eff_mapping, options, is_delimited_export=is_delim
                )
                if audit.cells_changed > 0 or audit.cells_cleared > 0:
                    modified_rows += 1
                cells_changed += audit.cells_changed
                cells_cleared += audit.cells_cleared
                invalid_cells += audit.invalid_cells
                for act in audit.cross_healing_actions:
                    healing_counts[act] = healing_counts.get(act, 0) + 1
                for col_name, tag in audit.cell_changes.items():
                    if tag in ("modified", "healed", "rescued", "cleared"):
                        per_column_changes[col_name] = per_column_changes.get(col_name, 0) + 1
                for r in out_rows:
                    yield r
        finally:
            close_row_iter(row_iter)

    output_rows = write_tabular_output(
        out_p,
        out_columns,
        _stream_out(),
        spec,
        template_xlsx_path=in_p if spec.format == "xlsx" else None,
        source_parquet_path=in_p if spec.format == "parquet" else None,
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return {
        "input_rows": input_rows,
        "output_rows": output_rows,
        "modified_rows": modified_rows,
        "cells_changed": cells_changed,
        "cells_cleared": cells_cleared,
        "invalid_cells": invalid_cells,
        "cross_healing_counts": healing_counts,
        "per_column_changes": per_column_changes,
        "input_columns": columns,
        "output_columns": out_columns,
        "format_spec": spec.to_dict(),
        "output_path": str(out_p),
        "elapsed_ms": elapsed_ms,
    }
