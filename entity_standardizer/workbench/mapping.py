"""Grouped field mapping, multi-block auto-detection, and preset storage for Entity Standardizer Workbench."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import json
import os
from pathlib import Path
import re
from typing import Any

from entity_standardizer.person import is_organization_name


class FieldRole(StrEnum):
    """Canonical entity field role assignable to an imported column."""

    RECORD_ID = "record_id"
    EXTERNAL_ID = "external_id"
    CRD = "crd"
    ORGANIZATION = "organization"
    PERSON_NAME = "person_name"
    SALUTATION = "salutation"
    FIRST_NAME = "first_name"
    MIDDLE_NAME = "middle_name"
    LAST_NAME = "last_name"
    GENERATIONAL_SUFFIX = "generational_suffix"
    CREDENTIALS = "credentials"
    JOB_TITLE = "job_title"
    ADVISOR_GROUP = "advisor_group"
    MEMBER_ROSTER = "member_roster"
    STREET1 = "street1"
    STREET2 = "street2"
    CITY = "city"
    STATE = "state"
    POSTAL_CODE = "postal_code"
    COUNTRY = "country"
    PHONE = "phone"
    FAX = "fax"
    EMAIL = "email"
    WEBSITE = "website"
    SOCIAL = "social"


@dataclass(slots=True)
class ColumnMapping:
    """Mapping from a source column name to a canonical FieldRole inside an isolated healing group."""

    column: str
    role: str
    group_id: str = "primary"

    def __post_init__(self) -> None:
        self.role = FieldRole(self.role).value
        self.group_id = (self.group_id or "primary").strip() or "primary"

    def to_dict(self) -> dict[str, Any]:
        """Serialize column mapping to a dictionary."""
        return {
            "column": self.column,
            "role": self.role,
            "group_id": self.group_id,
        }


@dataclass(slots=True)
class MappingConfig:
    """Complete column-to-role mapping and per-group cross-healing switches for a dataset."""

    mappings: list[ColumnMapping] = field(default_factory=list)
    group_cross_healing: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize mapping configuration to a JSON-compatible dictionary."""
        return {
            "mappings": [m.to_dict() for m in self.mappings],
            "group_cross_healing": dict(self.group_cross_healing),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> MappingConfig:
        """Deserialize a MappingConfig from a dictionary."""
        if not data:
            return cls()
        if not isinstance(data, Mapping):
            raise ValueError("mapping_config must be a JSON object.")
        raw_mappings = data.get("mappings") or []
        if not isinstance(raw_mappings, Sequence) or isinstance(raw_mappings, (str, bytes)):
            raise ValueError("mappings must be a list of column mapping objects.")
        mappings: list[ColumnMapping] = []
        for item in raw_mappings:
            if not isinstance(item, Mapping):
                raise ValueError("Each mapping entry must be an object with 'column' and 'role'.")
            mappings.append(
                ColumnMapping(
                    column=str(item["column"]),
                    role=str(item["role"]),
                    group_id=str(item.get("group_id") or "primary"),
                )
            )
        raw_ch = data.get("group_cross_healing") or {}
        if not isinstance(raw_ch, Mapping):
            raise ValueError("group_cross_healing must be a JSON object.")
        group_ch = {str(k): bool(v) for k, v in raw_ch.items()}
        return cls(mappings=mappings, group_cross_healing=group_ch)

    def for_columns(self, columns: Sequence[str]) -> MappingConfig:
        """Return a copy of this MappingConfig restricted to columns present in `columns`."""
        col_set = set(columns)
        return MappingConfig(
            mappings=[m for m in self.mappings if m.column in col_set],
            group_cross_healing=dict(self.group_cross_healing),
        )

    def is_cross_healing_enabled(self, group_id: str, default: bool = True) -> bool:
        """Return whether cross-pillar healing is enabled for group_id."""
        base_group = group_id.split("__", 1)[0]
        return bool(self.group_cross_healing.get(base_group, default))

    def execution_units(self) -> list[tuple[str, str, list[ColumnMapping]]]:
        """Partition mappings into (unit_id, base_group_id, mappings) avoiding role collisions."""
        primary_groups: dict[str, list[ColumnMapping]] = {}
        seen_roles: dict[str, set[str]] = {}
        extra_units: list[tuple[str, str, list[ColumnMapping]]] = []

        for m in self.mappings:
            gid = m.group_id
            roles_in_group = seen_roles.setdefault(gid, set())
            if m.role not in roles_in_group:
                roles_in_group.add(m.role)
                primary_groups.setdefault(gid, []).append(m)
            else:
                extra_units.append((f"{gid}__{m.column}", gid, [m]))

        units: list[tuple[str, str, list[ColumnMapping]]] = [
            (gid, gid, items) for gid, items in primary_groups.items()
        ]
        units.extend(extra_units)
        return units


_CAMEL_BOUNDARY_RE = re.compile(r"([a-z0-9])([A-Z])")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_GROUP_PREFIXES: tuple[tuple[str, str], ...] = (
    ("inst_contact_", "inst_contact"),
    ("assistant_", "assistant"),
    ("asst_", "assistant"),
    ("person_mailing_", "mailing"),
    ("person_other_", "other"),
    ("billing_", "billing"),
    ("shipping_", "shipping"),
    ("mailing_", "mailing"),
    ("other_", "other"),
    ("mmd_", "mmd"),
    ("branch_", "branch"),
    ("office_", "office"),
    ("home_", "home"),
)

_SKIP_COLUMN_WORDS: frozenset[str] = frozenset(
    {
        "date",
        "time",
        "timestamp",
        "created",
        "modified",
        "viewed",
        "referenced",
        "status",
        "tier",
        "rating",
        "rank",
        "ranking",
        "score",
        "count",
        "counter",
        "aum",
        "assets",
        "flows",
        "sales",
        "redemptions",
        "revenue",
        "employees",
        "latitude",
        "longitude",
        "accuracy",
        "geocode",
        "bounced",
        "reason",
        "opt",
        "opted",
        "donot",
        "allowed",
        "note",
        "notes",
        "bio",
        "description",
        "sync",
        "verified",
        "checked",
        "handler",
        "alias",
        "bypass",
        "exclude",
        "include",
        "override",
        "territory",
        "zone",
        "region",
        "segment",
        "channel",
        "coverage",
        "interest",
        "target",
        "priority",
        "complexity",
        "newsletter",
        "blog",
        "news",
        "photo",
        "image",
        "type",
        "parent",
        "owner",
        "supervisor",
        "layout",
        "active",
        "deleted",
        "is",
        "has",
    }
)

_EXACT_ROLE_MAP: dict[str, str] = {
    "id": FieldRole.RECORD_ID.value,
    "record_id": FieldRole.RECORD_ID.value,
    "account_id": FieldRole.RECORD_ID.value,
    "contact_id": FieldRole.RECORD_ID.value,
    "sf_id": FieldRole.RECORD_ID.value,
    "casesafeid_id": FieldRole.RECORD_ID.value,
    "external_id": FieldRole.EXTERNAL_ID.value,
    "external_record_id": FieldRole.EXTERNAL_ID.value,
    "mdm_id": FieldRole.EXTERNAL_ID.value,
    "salesconnect_id": FieldRole.EXTERNAL_ID.value,
    "salesconnect_firm_id": FieldRole.EXTERNAL_ID.value,
    "salesconnect_office_id": FieldRole.EXTERNAL_ID.value,
    "salesconnect_team_id": FieldRole.EXTERNAL_ID.value,
    "sc_firm_id": FieldRole.EXTERNAL_ID.value,
    "crd": FieldRole.CRD.value,
    "crd_number": FieldRole.CRD.value,
    "finra_crd": FieldRole.CRD.value,
    "organization": FieldRole.ORGANIZATION.value,
    "org": FieldRole.ORGANIZATION.value,
    "org_name": FieldRole.ORGANIZATION.value,
    "company": FieldRole.ORGANIZATION.value,
    "company_name": FieldRole.ORGANIZATION.value,
    "firm": FieldRole.ORGANIZATION.value,
    "firm_name": FieldRole.ORGANIZATION.value,
    "account_name": FieldRole.ORGANIZATION.value,
    "legal_name": FieldRole.ORGANIZATION.value,
    "high_level_organization_name": FieldRole.ORGANIZATION.value,
    "person": FieldRole.PERSON_NAME.value,
    "person_name": FieldRole.PERSON_NAME.value,
    "contact_name": FieldRole.PERSON_NAME.value,
    "full_name": FieldRole.PERSON_NAME.value,
    "advisor_name": FieldRole.PERSON_NAME.value,
    "salutation": FieldRole.SALUTATION.value,
    "persontitle": FieldRole.SALUTATION.value,
    "first_name": FieldRole.FIRST_NAME.value,
    "fname": FieldRole.FIRST_NAME.value,
    "middle_name": FieldRole.MIDDLE_NAME.value,
    "mname": FieldRole.MIDDLE_NAME.value,
    "last_name": FieldRole.LAST_NAME.value,
    "lname": FieldRole.LAST_NAME.value,
    "surname": FieldRole.LAST_NAME.value,
    "suffix": FieldRole.GENERATIONAL_SUFFIX.value,
    "generational_suffix": FieldRole.GENERATIONAL_SUFFIX.value,
    "credentials": FieldRole.CREDENTIALS.value,
    "professional_designation": FieldRole.CREDENTIALS.value,
    "title": FieldRole.JOB_TITLE.value,
    "job_title": FieldRole.JOB_TITLE.value,
    "person_title": FieldRole.JOB_TITLE.value,
    "advisor_group": FieldRole.ADVISOR_GROUP.value,
    "advisor_team_name": FieldRole.ADVISOR_GROUP.value,
    "team": FieldRole.ADVISOR_GROUP.value,
    "team_name": FieldRole.ADVISOR_GROUP.value,
    "partnership_name": FieldRole.ADVISOR_GROUP.value,
    "members": FieldRole.MEMBER_ROSTER.value,
    "member_roster": FieldRole.MEMBER_ROSTER.value,
    "member_crds": FieldRole.MEMBER_ROSTER.value,
    "street": FieldRole.STREET1.value,
    "street1": FieldRole.STREET1.value,
    "street_1": FieldRole.STREET1.value,
    "address": FieldRole.STREET1.value,
    "address1": FieldRole.STREET1.value,
    "address_1": FieldRole.STREET1.value,
    "address_line_1": FieldRole.STREET1.value,
    "addr1": FieldRole.STREET1.value,
    "street_address": FieldRole.STREET1.value,
    "line1": FieldRole.STREET1.value,
    "street2": FieldRole.STREET2.value,
    "street_2": FieldRole.STREET2.value,
    "address2": FieldRole.STREET2.value,
    "address_2": FieldRole.STREET2.value,
    "address_line_2": FieldRole.STREET2.value,
    "addr2": FieldRole.STREET2.value,
    "suite": FieldRole.STREET2.value,
    "unit": FieldRole.STREET2.value,
    "line2": FieldRole.STREET2.value,
    "city": FieldRole.CITY.value,
    "town": FieldRole.CITY.value,
    "locality": FieldRole.CITY.value,
    "state": FieldRole.STATE.value,
    "state_code": FieldRole.STATE.value,
    "statecode": FieldRole.STATE.value,
    "province": FieldRole.STATE.value,
    "postal_code": FieldRole.POSTAL_CODE.value,
    "postalcode": FieldRole.POSTAL_CODE.value,
    "zip": FieldRole.POSTAL_CODE.value,
    "zip_code": FieldRole.POSTAL_CODE.value,
    "zipcode": FieldRole.POSTAL_CODE.value,
    "postcode": FieldRole.POSTAL_CODE.value,
    "country": FieldRole.COUNTRY.value,
    "country_code": FieldRole.COUNTRY.value,
    "countrycode": FieldRole.COUNTRY.value,
    "country_iso2": FieldRole.COUNTRY.value,
    "country_iso3": FieldRole.COUNTRY.value,
    "fax": FieldRole.FAX.value,
    "phone": FieldRole.PHONE.value,
    "telephone": FieldRole.PHONE.value,
    "tel": FieldRole.PHONE.value,
    "mobile": FieldRole.PHONE.value,
    "mobile_phone": FieldRole.PHONE.value,
    "direct_phone": FieldRole.PHONE.value,
    "person_phone": FieldRole.PHONE.value,
    "person_mobile_phone": FieldRole.PHONE.value,
    "person_home_phone": FieldRole.PHONE.value,
    "email": FieldRole.EMAIL.value,
    "email_address": FieldRole.EMAIL.value,
    "person_email": FieldRole.EMAIL.value,
    "website": FieldRole.WEBSITE.value,
    "url": FieldRole.WEBSITE.value,
    "web": FieldRole.WEBSITE.value,
    "linkedin": FieldRole.SOCIAL.value,
    "linkedin_link": FieldRole.SOCIAL.value,
    "twitter": FieldRole.SOCIAL.value,
    "social": FieldRole.SOCIAL.value,
}


def _normalize_col_name(col: str) -> str:
    snake = _CAMEL_BOUNDARY_RE.sub(r"\1_\2", col.strip())
    low = re.sub(r"(?:__c|_c)$", "", snake.lower())
    return _NON_ALNUM_RE.sub("_", low).strip("_").replace("linked_in", "linkedin")


def _extract_group_and_stem(norm: str) -> tuple[str, str]:
    for prefix, group_id in _GROUP_PREFIXES:
        if norm.startswith(prefix) and len(norm) > len(prefix):
            return group_id, norm[len(prefix) :]
    return "primary", norm


def _disambiguate_name_role(
    col: str,
    sample_rows: Sequence[Mapping[str, Any]],
    has_split_person: bool,
) -> str | None:
    vals = [str(r.get(col) or "").strip() for r in sample_rows if str(r.get(col) or "").strip()]
    if vals:
        org_hits = sum(1 for v in vals if is_organization_name(v))
        if org_hits * 2 >= len(vals):
            return FieldRole.ORGANIZATION.value
    if has_split_person:
        return None
    return FieldRole.PERSON_NAME.value


_STREET1_STEMS: frozenset[str] = frozenset(
    {
        "street",
        "street1",
        "street_1",
        "address1",
        "address_1",
        "address_line_1",
        "addr1",
        "street_address",
        "line1",
    }
)


def auto_detect_mappings(
    columns: Sequence[str],
    sample_rows: Sequence[Mapping[str, Any]] = (),
) -> MappingConfig:
    """Infer grouped entity FieldRole mappings from column names and sample cell values."""
    normalized_cols = [_normalize_col_name(c) for c in columns]
    parsed_cols = [_extract_group_and_stem(n) for n in normalized_cols]
    split_person_groups: set[str] = {
        gid for gid, st in parsed_cols if st in ("first_name", "fname", "last_name", "lname", "surname")
    }
    street1_groups: set[str] = {gid for gid, st in parsed_cols if st in _STREET1_STEMS}

    mappings: list[ColumnMapping] = []
    for col, norm, (group_id, stem) in zip(columns, normalized_cols, parsed_cols):
        tokens = set(norm.split("_"))

        if stem in ("linkedin", "linkedin_link", "social"):
            role: str | None = FieldRole.SOCIAL.value
        elif tokens & _SKIP_COLUMN_WORDS or stem in ("email_domain", "city_state"):
            role = None
        elif stem == "address" and group_id in street1_groups:
            role = None
        elif stem == "name":
            role = _disambiguate_name_role(col, sample_rows, group_id in split_person_groups)
        else:
            role = _EXACT_ROLE_MAP.get(stem)

        if role is not None:
            mappings.append(ColumnMapping(column=col, role=role, group_id=group_id))

    return MappingConfig(mappings=mappings)


_PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-]{0,79}$")


class PresetStore:
    """File-backed store for saving and reusing field mapping and standardization option presets."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        base = (
            Path(root_dir)
            if root_dir is not None
            else Path(
                os.environ.get("ENTITY_STANDARDIZER_PRESETS_DIR")
                or (Path.home() / ".entity_standardizer" / "presets")
            )
        )
        self.root_dir = base

    def _preset_path(self, name: str) -> Path:
        cleaned = name.strip()
        if not _PRESET_NAME_RE.match(cleaned):
            raise ValueError(
                "Preset name must be 1-80 characters of letters, digits, spaces, '-' or '_'."
            )
        return self.root_dir / f"{cleaned}.json"

    def list_presets(self) -> list[dict[str, Any]]:
        """Return metadata for all saved presets sorted by name."""
        if not self.root_dir.exists():
            return []
        presets: list[dict[str, Any]] = []
        for path in sorted(self.root_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(data, Mapping):
                continue
            presets.append(
                {
                    "name": data.get("name", path.stem),
                    "description": data.get("description", ""),
                    "mapping_count": len((data.get("mapping_config") or {}).get("mappings", [])),
                }
            )
        return presets

    def get_preset(self, name: str) -> dict[str, Any]:
        """Load a saved preset by name or raise FileNotFoundError."""
        path = self._preset_path(name)
        if not path.is_file():
            raise FileNotFoundError(f"Preset '{name}' not found.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Preset '{name}' is corrupted: {exc}") from exc
        if not isinstance(data, Mapping):
            raise ValueError(f"Preset '{name}' must contain a JSON object.")
        return dict(data)

    def save_preset(self, name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Persist a mapping and options preset to disk."""
        path = self._preset_path(name)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "name": name.strip(),
            "description": str(payload.get("description", "")),
            "mapping_config": dict(payload.get("mapping_config") or {}),
            "standardize_options": dict(payload.get("standardize_options") or {}),
            "matching_options": dict(payload.get("matching_options") or {}),
        }
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record

    def delete_preset(self, name: str) -> bool:
        """Delete a saved preset by name, returning True if it existed."""
        path = self._preset_path(name)
        if not path.is_file():
            return False
        path.unlink()
        return True
