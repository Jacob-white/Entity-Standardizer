"""Cross-system matching, single-file deduplication, steward review queue, and multi-format export."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
import threading
import time
from typing import Any

from entity_standardizer.address.models import extract_street_core_key
from entity_standardizer.address.standardizer import standardize_address
from entity_standardizer.company import (
    StandardizedCompany,
    compact_company_key,
    compare_companies,
    extract_company_acronym,
    resolve_brand_lineage,
    standardize_company,
)
from entity_standardizer.dedup import DisjointSet, compare_addresses, compare_phones
from entity_standardizer.group import (
    StandardizedAdvisorGroup,
    compare_advisor_groups,
    score_member_rosters,
    standardize_advisor_group,
)
from entity_standardizer.identifiers import (
    is_synthetic_or_test_record,
    standardize_crd,
    standardize_external_id,
)
from entity_standardizer.joint import StandardizedContact, standardize_contact
from entity_standardizer.matcher import compute_switchboard_phones
from entity_standardizer.models import StandardizedPhone
from entity_standardizer.person import (
    StandardizedJobTitle,
    StandardizedPerson,
    compare_persons,
    standardize_job_title,
    standardize_person,
)
from entity_standardizer.scoring import (
    _PROFILE_THRESHOLDS,
    EntityScoringProfile,
    SignalEvidence,
    explain_and_score_entities,
    synthesize_scored_match,
)
from entity_standardizer.standardizer import standardize_phone
from entity_standardizer.web import (
    StandardizedEmail,
    StandardizedSocial,
    StandardizedUrl,
    compare_emails,
    compare_urls,
    standardize_email,
    standardize_social,
    standardize_url,
)
from entity_standardizer.workbench.io_formats import (
    FileFormatSpec,
    cell_to_input_text,
    close_row_iter,
    detect_file_format,
    iter_tabular_rows,
    sanitize_row_for_json,
    write_tabular_output,
    write_xlsx_sheets,
)
from entity_standardizer.workbench.mapping import FieldRole, MappingConfig
from entity_standardizer.workbench.standardize_runner import (
    _ADDRESS_ROLES,
    _PERSON_COMPONENT_ROLES,
    _is_placeholder_text,
)

_PERSON_GROUP_ROLES: frozenset[str] = frozenset({FieldRole.PERSON_NAME.value, *_PERSON_COMPONENT_ROLES})

ALL_MATCH_SIGNALS: tuple[str, ...] = (
    "external_id",
    "crd",
    "email",
    "phone",
    "company",
    "person",
    "address",
    "website",
    "roster",
)

_ALL_SIGNALS_SET: frozenset[str] = frozenset(ALL_MATCH_SIGNALS)
_VALID_PROFILES: frozenset[str] = frozenset({p.value for p in EntityScoringProfile} | {"CUSTOM"})
_VALID_SYNTHETIC_POLICIES: frozenset[str] = frozenset({"flag", "exclude", "ignore"})
_MAX_TIER3_BUCKET_SIZE = 500


def _normalize_roster_tokens(raw_val: Any) -> set[str]:
    text = cell_to_input_text(raw_val)
    if not text:
        return set()
    parts = [p.strip() for p in text.replace("|", ";").split(";") if p.strip()]
    tokens: set[str] = set()
    for part in parts:
        if "@" in part:
            em = standardize_email(part)
            if em.is_valid and em.email_key:
                tokens.add(em.email_key.upper())
                continue
        crd = standardize_crd(part)
        if crd.is_valid and crd.canonical_id:
            tokens.add(f"CRD:{crd.canonical_id}")
            continue
        per = standardize_person(part)
        if per.is_valid and per.person_root_key:
            tokens.add(per.person_root_key)
        else:
            tokens.add(part.upper())
    return tokens


@dataclass(slots=True)
class MemberRosterSource:
    """Optional child member table joined by parent_id_col onto Left or Right records."""

    path: str | Path
    parent_id_col: str
    member_cols: list[str]
    delimiter_override: str | None = None
    sheet_name: str | None = None


def _canonical_roster_join_id(raw_id: str) -> str:
    ext = standardize_external_id(raw_id)
    return ext.canonical_id or raw_id.upper()


def load_member_roster_map(source: MemberRosterSource) -> dict[str, set[str]]:
    """Stream a child member table and aggregate normalized member tokens per parent ID."""
    p = Path(source.path)
    spec = detect_file_format(
        p, delimiter_override=source.delimiter_override, sheet_name=source.sheet_name
    )
    columns, row_iter = iter_tabular_rows(p, spec)
    rosters: dict[str, set[str]] = defaultdict(set)
    try:
        if columns:
            col_set = set(columns)
            for req_col in (source.parent_id_col, *source.member_cols):
                if req_col not in col_set:
                    raise ValueError(f"Roster column {req_col!r} not found in {p.name!r}.")
        for row in row_iter:
            raw_pid = cell_to_input_text(row.get(source.parent_id_col))
            if not raw_pid:
                continue
            pid = _canonical_roster_join_id(raw_pid)
            for col in source.member_cols:
                rosters[pid].update(_normalize_roster_tokens(row.get(col)))
    finally:
        close_row_iter(row_iter)
    return dict(rosters)


@dataclass(slots=True)
class MatchingOptions:
    """User-selectable profile, threshold, signal, and guardrail controls for entity matching."""

    profile: str = "CONTACT"
    auto_standardize: bool = True
    match_threshold: float | None = None
    potential_threshold: float | None = None
    enabled_signals: tuple[str, ...] = ALL_MATCH_SIGNALS
    switchboard_min_shared: int = 4
    synthetic_policy: str = "flag"
    default_country: str = "US"

    def __post_init__(self) -> None:
        self.profile = (self.profile or "CONTACT").strip().upper()
        if self.profile not in _VALID_PROFILES:
            raise ValueError(f"Unsupported matching profile {self.profile!r}.")
        self.synthetic_policy = (self.synthetic_policy or "flag").strip().lower()
        if self.synthetic_policy not in _VALID_SYNTHETIC_POLICIES:
            raise ValueError(f"Unsupported synthetic_policy {self.synthetic_policy!r}.")
        if self.match_threshold is not None:
            self.match_threshold = float(self.match_threshold)
            if not math.isfinite(self.match_threshold) or not (0.0 <= self.match_threshold <= 1.0):
                raise ValueError("match_threshold must be between 0.0 and 1.0.")
        if self.potential_threshold is not None:
            self.potential_threshold = float(self.potential_threshold)
            if not math.isfinite(self.potential_threshold) or not (0.0 <= self.potential_threshold <= 1.0):
                raise ValueError("potential_threshold must be between 0.0 and 1.0.")
        m_thr, p_thr = self.effective_thresholds()
        if p_thr > m_thr:
            raise ValueError("potential_threshold cannot exceed match_threshold.")
        if self.switchboard_min_shared < 2:
            raise ValueError("switchboard_min_shared must be >= 2.")
        self.enabled_signals = tuple(s for s in self.enabled_signals if s in _ALL_SIGNALS_SET)
        self.default_country = (self.default_country or "US").strip().upper() or "US"

    def effective_thresholds(self) -> tuple[float, float]:
        """Return (match_threshold, potential_threshold) resolving profile defaults."""
        if self.profile == "CUSTOM":
            base_m, base_p = 0.70, 0.50
        else:
            base_m, base_p = _PROFILE_THRESHOLDS[EntityScoringProfile(self.profile)]
        m_thr = self.match_threshold if self.match_threshold is not None else base_m
        p_thr = self.potential_threshold if self.potential_threshold is not None else min(base_p, m_thr)
        return float(m_thr), float(p_thr)

    def to_dict(self) -> dict[str, Any]:
        """Serialize matching options to a JSON-compatible dictionary."""
        m_thr, p_thr = self.effective_thresholds()
        return {
            "profile": self.profile,
            "auto_standardize": self.auto_standardize,
            "match_threshold": m_thr,
            "potential_threshold": p_thr,
            "enabled_signals": list(self.enabled_signals),
            "switchboard_min_shared": self.switchboard_min_shared,
            "synthetic_policy": self.synthetic_policy,
            "default_country": self.default_country,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> MatchingOptions:
        """Deserialize MatchingOptions from a mapping."""
        if not data:
            return cls()
        sigs = data.get("enabled_signals")
        if sigs is not None and (not isinstance(sigs, Sequence) or isinstance(sigs, (str, bytes))):
            raise ValueError("enabled_signals must be a list of signal names.")
        raw_sw = data.get("switchboard_min_shared", 4)
        if isinstance(raw_sw, bool):
            raise ValueError("switchboard_min_shared must be an integer >= 2.")
        return cls(
            profile=str(data.get("profile", "CONTACT")),
            auto_standardize=bool(data.get("auto_standardize", True)),
            match_threshold=data.get("match_threshold"),
            potential_threshold=data.get("potential_threshold"),
            enabled_signals=tuple(str(s) for s in sigs) if sigs is not None else ALL_MATCH_SIGNALS,
            switchboard_min_shared=int(raw_sw),
            synthetic_policy=str(data.get("synthetic_policy", "flag")),
            default_country=str(data.get("default_country", "US")),
        )


def _assign_atomic_group(
    values: dict[str, str],
    ordered_gids: list[str],
    by_group: dict[str, list[tuple[str, str]]],
    role_set: frozenset[str],
) -> None:
    for gid in ordered_gids:
        pairs = by_group[gid]
        if any(r in role_set for r, _ in pairs):
            for r, raw in pairs:
                if r in role_set and r not in values:
                    values[r] = raw
            return


def _is_valid_duplicate_candidate(role: str, raw: str, default_country: str) -> bool:
    if role in (FieldRole.PHONE.value, FieldRole.FAX.value):
        return standardize_phone(raw, default_country=default_country).is_valid
    if role == FieldRole.EMAIL.value:
        return standardize_email(raw).is_valid
    if role == FieldRole.WEBSITE.value:
        return standardize_url(raw).is_valid
    if role == FieldRole.CRD.value:
        return standardize_crd(raw).is_valid
    if role == FieldRole.EXTERNAL_ID.value:
        return standardize_external_id(raw).is_valid
    return True


def _extract_primary_role_values(
    row: Mapping[str, Any],
    mapping_config: MappingConfig,
    default_country: str = "US",
) -> dict[str, str]:
    by_group: dict[str, list[tuple[str, str]]] = {}
    for m in mapping_config.mappings:
        raw = cell_to_input_text(row.get(m.column))
        if raw and not _is_placeholder_text(raw):
            by_group.setdefault(m.group_id, []).append((m.role, raw))

    ordered_gids = (["primary"] if "primary" in by_group else []) + [
        gid for gid in by_group if gid != "primary"
    ]
    values: dict[str, str] = {}
    _assign_atomic_group(values, ordered_gids, by_group, _ADDRESS_ROLES)
    _assign_atomic_group(values, ordered_gids, by_group, _PERSON_GROUP_ROLES)
    atomic_roles = _ADDRESS_ROLES | _PERSON_GROUP_ROLES
    cands_by_role: dict[str, list[str]] = {}
    for gid in ordered_gids:
        for role, raw in by_group[gid]:
            if role not in atomic_roles:
                cands_by_role.setdefault(role, []).append(raw)
    for role, cands in cands_by_role.items():
        if role == FieldRole.MEMBER_ROSTER.value:
            values[role] = "; ".join(cands)
        elif len(cands) == 1:
            values[role] = cands[0]
        else:
            values[role] = next(
                (c for c in cands if _is_valid_duplicate_candidate(role, c, default_country)),
                cands[0],
            )
    return values


def _assemble_person_raw(vals: Mapping[str, str]) -> str:
    direct = vals.get(FieldRole.PERSON_NAME.value, "")
    if direct:
        return direct
    core = " ".join(
        part
        for part in (
            vals.get(FieldRole.SALUTATION.value, ""),
            vals.get(FieldRole.FIRST_NAME.value, ""),
            vals.get(FieldRole.MIDDLE_NAME.value, ""),
            vals.get(FieldRole.LAST_NAME.value, ""),
        )
        if part
    )
    extra = ", ".join(
        part
        for part in (
            vals.get(FieldRole.GENERATIONAL_SUFFIX.value, ""),
            vals.get(FieldRole.CREDENTIALS.value, ""),
        )
        if part
    )
    if core and extra:
        return f"{core}, {extra}"
    return core or extra


@dataclass(slots=True)
class PreparedEntityRecord:
    """Canonicalized source record ready for cross-system blocking, scoring, and comparison."""

    row_index: int
    record_id: str
    raw_row: dict[str, Any]
    external_id: str | None
    crd: str | None
    contact: StandardizedContact
    advisor_group: StandardizedAdvisorGroup | None
    member_roster: set[str]
    is_synthetic: bool
    country_code: str = ""

    def flat_display(self) -> dict[str, Any]:
        """Return compact standardized attribute dictionary for UI pair inspection."""
        addr = self.contact.address
        return {
            "record_id": self.record_id,
            "external_id": self.external_id or "",
            "crd": self.crd or "",
            "organization": (self.contact.organization.legal_name or "") if self.contact.organization else "",
            "person_name": (self.contact.person.full_name or "") if self.contact.person else "",
            "job_title": (self.contact.job_title.normalized_title or "") if self.contact.job_title else "",
            "advisor_group": (self.advisor_group.normalized_name or "") if self.advisor_group else "",
            "street1": addr.street1 or "",
            "street2": addr.street2 or "",
            "city": addr.city or "",
            "state": addr.state or "",
            "postal_code": addr.postal_code or "",
            "country": self.country_code,
            "phone": self.contact.phone.e164 or "",
            "email": (self.contact.email.email or "") if self.contact.email else "",
            "website": (self.contact.website.domain or "") if self.contact.website else "",
            "roster_count": len(self.member_roster),
            "is_synthetic": self.is_synthetic,
        }


def _build_direct_contact(vals: Mapping[str, str], default_country: str) -> StandardizedContact:
    addr = standardize_address(
        street1=vals.get(FieldRole.STREET1.value) or None,
        street2=vals.get(FieldRole.STREET2.value) or None,
        city=vals.get(FieldRole.CITY.value) or None,
        state=vals.get(FieldRole.STATE.value) or None,
        postal_code=vals.get(FieldRole.POSTAL_CODE.value) or None,
        country=vals.get(FieldRole.COUNTRY.value) or default_country,
        allow_locality=True,
    )
    phone: StandardizedPhone = standardize_phone(
        vals.get(FieldRole.PHONE.value) or None,
        country=vals.get(FieldRole.COUNTRY.value) or None,
        default_country=default_country,
    )
    fax = (
        standardize_phone(vals[FieldRole.FAX.value], default_country=default_country)
        if vals.get(FieldRole.FAX.value)
        else None
    )
    org: StandardizedCompany | None = (
        standardize_company(vals[FieldRole.ORGANIZATION.value])
        if vals.get(FieldRole.ORGANIZATION.value)
        else None
    )
    person_in = _assemble_person_raw(vals)
    per: StandardizedPerson | None = standardize_person(person_in) if person_in else None
    title: StandardizedJobTitle | None = (
        standardize_job_title(vals[FieldRole.JOB_TITLE.value])
        if vals.get(FieldRole.JOB_TITLE.value)
        else None
    )
    email: StandardizedEmail | None = (
        standardize_email(vals[FieldRole.EMAIL.value])
        if vals.get(FieldRole.EMAIL.value)
        else None
    )
    url: StandardizedUrl | None = (
        standardize_url(vals[FieldRole.WEBSITE.value])
        if vals.get(FieldRole.WEBSITE.value)
        else None
    )
    social: StandardizedSocial | None = (
        standardize_social(vals[FieldRole.SOCIAL.value])
        if vals.get(FieldRole.SOCIAL.value)
        else None
    )
    pillar_confs = [
        float(p.confidence)
        for p in (fax, org, per, title, email, url, social)
        if p is not None and p.is_valid
    ]
    if addr.address_status != "parse_failed" and addr.confidence_score:
        pillar_confs.append(float(addr.confidence_score))
    if phone.is_valid:
        pillar_confs.append(float(phone.confidence))
    overall_conf = round(sum(pillar_confs) / len(pillar_confs), 4) if pillar_confs else 0.0
    return StandardizedContact(
        address=addr,
        phone=phone,
        fax=fax,
        organization=org,
        person=per,
        job_title=title,
        email=email,
        website=url,
        social=social,
        overall_confidence=overall_conf,
    )


def prepare_records_for_matching(
    rows: Sequence[Mapping[str, Any]],
    mapping_config: MappingConfig,
    options: MatchingOptions,
    *,
    roster_map: Mapping[str, set[str]] | None = None,
) -> tuple[list[PreparedEntityRecord], int]:
    """Standardize raw rows into PreparedEntityRecords and return (records, excluded_synthetic_count)."""
    records: list[PreparedEntityRecord] = []
    excluded_synthetic = 0

    for idx, row in enumerate(rows):
        vals = _extract_primary_role_values(row, mapping_config, options.default_country)
        raw_rec_id = vals.get(FieldRole.RECORD_ID.value, "")
        record_id = raw_rec_id or f"ROW-{idx + 1}"

        raw_ext = vals.get(FieldRole.EXTERNAL_ID.value, "")
        ext_res = standardize_external_id(raw_ext) if raw_ext else None
        ext_id = ext_res.canonical_id if (ext_res and ext_res.is_valid) else None

        raw_crd = vals.get(FieldRole.CRD.value, "")
        crd_res = standardize_crd(raw_crd) if raw_crd else None
        crd_val = crd_res.canonical_id if (crd_res and crd_res.is_valid) else None

        org_raw = vals.get(FieldRole.ORGANIZATION.value) or None
        person_in = _assemble_person_raw(vals) or None
        email_raw = vals.get(FieldRole.EMAIL.value) or None

        is_syn = (
            is_synthetic_or_test_record(
                name=org_raw or person_in,
                email=email_raw,
                external_id=raw_ext or None,
                crd=raw_crd or None,
            )
            if options.synthetic_policy != "ignore"
            else False
        )
        if is_syn and options.synthetic_policy == "exclude":
            excluded_synthetic += 1
            continue

        if options.auto_standardize:
            contact = standardize_contact(
                street1=vals.get(FieldRole.STREET1.value) or None,
                street2=vals.get(FieldRole.STREET2.value) or None,
                city=vals.get(FieldRole.CITY.value) or None,
                state=vals.get(FieldRole.STATE.value) or None,
                postal_code=vals.get(FieldRole.POSTAL_CODE.value) or None,
                country=vals.get(FieldRole.COUNTRY.value) or None,
                phone=vals.get(FieldRole.PHONE.value) or None,
                fax=vals.get(FieldRole.FAX.value) or None,
                organization=org_raw,
                person_name=person_in,
                job_title=vals.get(FieldRole.JOB_TITLE.value) or None,
                email=email_raw,
                website=vals.get(FieldRole.WEBSITE.value) or None,
                social=vals.get(FieldRole.SOCIAL.value) or None,
                default_country=options.default_country,
                allow_locality=True,
            )
        else:
            contact = _build_direct_contact(vals, options.default_country)

        grp_raw = vals.get(FieldRole.ADVISOR_GROUP.value, "")
        advisor_group = standardize_advisor_group(grp_raw) if grp_raw else None

        roster: set[str] = set()
        if vals.get(FieldRole.MEMBER_ROSTER.value):
            roster.update(_normalize_roster_tokens(vals[FieldRole.MEMBER_ROSTER.value]))
        if roster_map is not None:
            canon_rec_id = _canonical_roster_join_id(raw_rec_id) if raw_rec_id else ""
            for lookup_key in dict.fromkeys((canon_rec_id, raw_rec_id, ext_id or "", record_id)):
                if lookup_key and lookup_key in roster_map:
                    roster.update(roster_map[lookup_key])

        addr_c = contact.address.country or ""
        eff_country = (
            addr_c
            if (
                addr_c
                and addr_c != "ZZZ"
                and (contact.address.address_status != "parse_failed" or bool(vals.get(FieldRole.COUNTRY.value)))
            )
            else ""
        )
        records.append(
            PreparedEntityRecord(
                row_index=idx,
                record_id=record_id,
                raw_row=dict(row),
                external_id=ext_id,
                crd=crd_val,
                contact=contact,
                advisor_group=advisor_group,
                member_roster=roster,
                is_synthetic=is_syn,
                country_code=eff_country,
            )
        )

    return records, excluded_synthetic


def _blocking_keys_for_record(
    rec: PreparedEntityRecord,
    enabled_signals: frozenset[str],
    switchboard_phones: frozenset[str],
) -> dict[int, list[str]]:
    t1: list[str] = []
    t2: list[str] = []
    t3: list[str] = []
    c = rec.contact

    if "external_id" in enabled_signals and rec.external_id:
        t1.append(f"EXT:{rec.external_id}")
    if "crd" in enabled_signals and rec.crd:
        t1.append(f"CRD:{rec.crd}")
    if "email" in enabled_signals and c.email and c.email.is_valid and c.email.email_key:
        if not c.email.is_role_account and not c.email.is_free_provider:
            t1.append(f"EM:{c.email.email_key}")
        else:
            t3.append(f"EM:{c.email.email_key}")

    if "person" in enabled_signals and c.person and c.person.is_valid:
        t2.append(f"PRK:{c.person.person_root_key}")
        for alt in c.person.person_alt_keys:
            t2.append(f"PRK:{alt}")
        if c.person.phonetic_key and (c.address.state or c.address.postal_code):
            loc = (c.address.postal_code or "")[:5] or c.address.state
            t3.append(f"PPH:{c.person.phonetic_key}|{loc}")

    if "company" in enabled_signals and c.organization and c.organization.is_valid:
        t2.append(f"CK:{c.organization.company_key}")
        lineage = resolve_brand_lineage(c.organization)
        if lineage:
            t2.append(f"BL:{lineage}")
        t2.append(f"CCK:{compact_company_key(c.organization)}")
        acr = extract_company_acronym(c.organization)
        if acr and c.address.state:
            t3.append(f"CAS:{acr}|{c.address.state}")
        if c.organization.phonetic_key and c.address.state:
            t3.append(f"CPH:{c.organization.phonetic_key}|{c.address.state}")

    if "address" in enabled_signals and c.address.address_status != "parse_failed":
        t2.append(f"BK:{c.address.building_key}")
        t2.append(f"PBK:{c.address.postal_building_key}")
        if c.address.street1 and c.address.postal_code:
            core = extract_street_core_key(c.address.street1)
            if core:
                t3.append(f"SCP:{core}|{c.address.postal_code[:5]}")

    if (
        "phone" in enabled_signals
        and c.phone.is_valid
        and c.phone.e164
        and not c.phone.is_toll_free
        and c.phone.e164 not in switchboard_phones
    ):
        t2.append(f"PH:{c.phone.e164}")

    if "website" in enabled_signals and c.website and c.website.is_valid and c.website.domain:
        t3.append(f"WEB:{c.website.domain}")

    if "roster" in enabled_signals and rec.member_roster:
        for tok in sorted(rec.member_roster):
            t2.append(f"ROS:{tok}")

    if "company" in enabled_signals and rec.advisor_group and rec.advisor_group.is_valid and rec.advisor_group.member_surname_key:
        t2.append(f"GRP:{rec.advisor_group.member_surname_key}")

    return {1: t1, 2: t2, 3: t3}


def _signal_category(signal_name: str) -> str:
    if signal_name == "EXTERNAL_ID":
        return "external_id"
    if signal_name == "FINRA_CRD":
        return "crd"
    if signal_name.startswith("PERSON_"):
        return "person"
    if signal_name.startswith(("ORG_", "ORGANIZATION_")) or signal_name == "ADVISOR_GROUP":
        return "company"
    if signal_name in ("VALIDATED_ADDRESS", "STREET_CORE_AND_ZIP5", "POSTAL_ZIP5", "CITY_STATE", "STREET_ADDRESS", "ADDRESS"):
        return "address"
    if signal_name in ("DIRECT_PHONE", "SHARED_BRANCH_SWITCHBOARD", "TOLL_FREE_PHONE", "PHONE", "FAX"):
        return "phone"
    if signal_name in ("EMAIL", "CORPORATE_EMAIL_DOMAIN"):
        return "email"
    if signal_name == "WEBSITE_DOMAIN":
        return "website"
    return "roster"


def _score_entity_pair(
    left: PreparedEntityRecord,
    right: PreparedEntityRecord,
    options: MatchingOptions,
    switchboard_phones: frozenset[str],
):
    m_thr, p_thr = options.effective_thresholds()
    scored = explain_and_score_entities(
        left.contact,
        right.contact,
        external_id_a=left.external_id,
        external_id_b=right.external_id,
        crd_a=left.crd,
        crd_b=right.crd,
        member_roster_a=left.member_roster or None,
        member_roster_b=right.member_roster or None,
        switchboard_phones=switchboard_phones,
        match_threshold=m_thr,
        potential_threshold=p_thr,
    )
    ev_list = list(scored.evidence)

    if (
        left.advisor_group
        and right.advisor_group
        and left.advisor_group.is_valid
        and right.advisor_group.is_valid
    ):
        g_cmp = compare_advisor_groups(left.advisor_group, right.advisor_group)
        if g_cmp.is_match:
            ev_list.append(
                SignalEvidence(
                    "ADVISOR_GROUP",
                    round(0.42 * g_cmp.score, 4),
                    f"advisor group matches via {g_cmp.match_type} ('{left.advisor_group.normalized_name}' <-> '{right.advisor_group.normalized_name}')",
                )
            )

    enabled_set = frozenset(options.enabled_signals)
    if enabled_set != _ALL_SIGNALS_SET or len(ev_list) != len(scored.evidence):
        filtered_ev = [e for e in ev_list if _signal_category(e.signal) in enabled_set]
        hard_id = any(
            e.signal in ("EXTERNAL_ID", "FINRA_CRD") and not e.is_conflict for e in filtered_ev
        )
        scored = synthesize_scored_match(
            filtered_ev,
            match_threshold=m_thr,
            potential_threshold=p_thr,
            hard_id_matched=hard_id,
        )
    return scored


def _presence_cmp(val_a: str | None, val_b: str | None) -> str:
    a = (val_a or "").strip()
    b = (val_b or "").strip()
    if not a and not b:
        return "BOTH_EMPTY"
    if a and not b:
        return "LEFT_ONLY"
    if b and not a:
        return "RIGHT_ONLY"
    return "EXACT" if a.upper() == b.upper() else "CONFLICT"


def _compute_field_comparisons(
    left: PreparedEntityRecord,
    right: PreparedEntityRecord,
) -> tuple[dict[str, str], int, int, float, list[str]]:
    la, ra = left.contact, right.contact
    cmps: dict[str, str] = {}

    cmps["cmp_crd"] = _presence_cmp(left.crd, right.crd)

    if la.person and ra.person and la.person.is_valid and ra.person.is_valid:
        pc = compare_persons(la.person, ra.person)
        cmps["cmp_person"] = (
            "EXACT"
            if (la.person.full_name == ra.person.full_name)
            else ("EQUIV" if pc.is_match else "CONFLICT")
        )
    else:
        cmps["cmp_person"] = _presence_cmp(
            la.person.full_name if la.person else "",
            ra.person.full_name if ra.person else "",
        )

    if la.organization and ra.organization and la.organization.is_valid and ra.organization.is_valid:
        oc = compare_companies(la.organization, ra.organization)
        cmps["cmp_org"] = (
            "EXACT"
            if (la.organization.legal_name == ra.organization.legal_name)
            else ("EQUIV" if oc.is_match else "CONFLICT")
        )
    else:
        cmps["cmp_org"] = _presence_cmp(
            la.organization.legal_name if la.organization else "",
            ra.organization.legal_name if ra.organization else "",
        )

    aa, ab = la.address, ra.address
    if aa.street1 and ab.street1:
        ac = compare_addresses(aa, ab)
        cmps["cmp_street"] = "EXACT" if aa.street1 == ab.street1 else ("EQUIV" if ac.is_match else "CONFLICT")
    else:
        cmps["cmp_street"] = _presence_cmp(aa.street1, ab.street1)

    cmps["cmp_city"] = _presence_cmp(aa.city, ab.city)
    cmps["cmp_state"] = _presence_cmp(aa.state, ab.state)
    z5a, z5b = (aa.postal_code or "")[:5], (ab.postal_code or "")[:5]
    if z5a and z5b:
        cmps["cmp_postal"] = "EXACT" if aa.postal_code == ab.postal_code else ("EQUIV" if z5a == z5b else "CONFLICT")
    else:
        cmps["cmp_postal"] = _presence_cmp(aa.postal_code, ab.postal_code)
    cmps["cmp_country"] = _presence_cmp(left.country_code, right.country_code)

    if la.phone.is_valid and ra.phone.is_valid:
        phc = compare_phones(la.phone, ra.phone)
        cmps["cmp_phone"] = "EXACT" if phc.is_exact_match else ("EQUIV" if phc.is_extension_variant else "CONFLICT")
    else:
        cmps["cmp_phone"] = _presence_cmp(la.phone.e164, ra.phone.e164)

    if la.email and ra.email and la.email.is_valid and ra.email.is_valid:
        ec = compare_emails(la.email, ra.email)
        cmps["cmp_email"] = "EXACT" if la.email.email == ra.email.email else ("EQUIV" if ec.is_match else "CONFLICT")
    else:
        cmps["cmp_email"] = _presence_cmp(
            la.email.email if la.email else "",
            ra.email.email if ra.email else "",
        )

    if la.website and ra.website and la.website.is_valid and ra.website.is_valid:
        uc = compare_urls(la.website, ra.website)
        cmps["cmp_website"] = (
            "EXACT"
            if la.website.url == ra.website.url
            else ("EQUIV" if (uc.is_match or la.website.domain == ra.website.domain) else "CONFLICT")
        )
    else:
        cmps["cmp_website"] = _presence_cmp(
            la.website.domain if la.website else "",
            ra.website.domain if ra.website else "",
        )

    if left.member_roster and right.member_roster:
        rc = score_member_rosters(left.member_roster, right.member_roster)
        cmps["cmp_roster"] = "EXACT" if left.member_roster == right.member_roster else ("EQUIV" if rc.is_match else "CONFLICT")
    else:
        cmps["cmp_roster"] = _presence_cmp(
            "1" if left.member_roster else "",
            "1" if right.member_roster else "",
        )

    compared_vals = [v for v in cmps.values() if v in ("EXACT", "EQUIV", "CONFLICT")]
    matched_vals = [v for v in compared_vals if v in ("EXACT", "EQUIV")]
    agreement_pct = round(100.0 * len(matched_vals) / len(compared_vals), 2) if compared_vals else 0.0
    discrepancies = [k.replace("cmp_", "") for k, v in cmps.items() if v == "CONFLICT"]
    return cmps, len(compared_vals), len(matched_vals), agreement_pct, discrepancies


@dataclass(slots=True)
class MatchPairView:
    """Rich cross-system match pair with steward decision state and field-by-field comparison."""

    pair_id: str
    left_idx: int
    right_idx: int
    left_id: str
    right_id: str
    match_tier: str
    engine_disposition: str
    effective_status: str
    steward_decision: str | None
    steward_note: str
    cardinality: str
    is_primary_match: bool
    score: float
    score_100: float
    explanation: str
    matched_signals: list[str]
    conflicting_signals: list[str]
    evidence: list[dict[str, Any]]
    field_comparisons: dict[str, str]
    fields_compared: int
    fields_matched: int
    attribute_agreement_pct: float
    discrepancy_fields: list[str]
    left_display: dict[str, Any]
    right_display: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize match pair view to a JSON-compatible dictionary."""
        return {
            "pair_id": self.pair_id,
            "left_id": self.left_id,
            "right_id": self.right_id,
            "match_tier": self.match_tier,
            "engine_disposition": self.engine_disposition,
            "effective_status": self.effective_status,
            "steward_decision": self.steward_decision,
            "steward_note": self.steward_note,
            "cardinality": self.cardinality,
            "is_primary_match": self.is_primary_match,
            "score": round(self.score, 4),
            "score_100": round(self.score_100, 2),
            "explanation": self.explanation,
            "matched_signals": list(self.matched_signals),
            "conflicting_signals": list(self.conflicting_signals),
            "evidence": list(self.evidence),
            **self.field_comparisons,
            "fields_compared": self.fields_compared,
            "fields_matched": self.fields_matched,
            "attribute_agreement_pct": self.attribute_agreement_pct,
            "discrepancy_fields": list(self.discrepancy_fields),
            "left_display": self.left_display,
            "right_display": self.right_display,
        }


_SEARCH_DISPLAY_KEYS: tuple[str, ...] = (
    "record_id",
    "external_id",
    "crd",
    "organization",
    "person_name",
    "advisor_group",
    "street1",
    "city",
    "state",
    "postal_code",
    "country",
    "phone",
    "email",
    "website",
)


def _display_matches_query(disp: Mapping[str, Any], q: str) -> bool:
    return any(q in str(disp.get(k, "")).lower() for k in _SEARCH_DISPLAY_KEYS)


class MatchSession:
    """Stateful cross-system match session supporting steward overrides and 4 deliverable exports."""

    def __init__(
        self,
        *,
        left_records: list[PreparedEntityRecord],
        right_records: list[PreparedEntityRecord],
        left_columns: list[str],
        right_columns: list[str],
        left_format: FileFormatSpec,
        right_format: FileFormatSpec,
        options: MatchingOptions,
        pairs: list[MatchPairView],
        excluded_synthetic_left: int,
        excluded_synthetic_right: int,
        elapsed_ms: float,
        left_source_path: str | Path | None = None,
        right_source_path: str | Path | None = None,
    ) -> None:
        self.left_records = left_records
        self.right_records = right_records
        self.left_columns = left_columns
        self.right_columns = right_columns
        self.left_format = left_format
        self.right_format = right_format
        self.options = options
        self.pairs = pairs
        self._pairs_by_id = {p.pair_id: p for p in pairs}
        self.excluded_synthetic_left = excluded_synthetic_left
        self.excluded_synthetic_right = excluded_synthetic_right
        self.elapsed_ms = elapsed_ms
        self.left_source_path = Path(left_source_path) if left_source_path is not None else None
        self.right_source_path = Path(right_source_path) if right_source_path is not None else None
        self.scorecard: dict[str, Any] = {}
        self.matched_left_set: set[int] = set()
        self.matched_right_set: set[int] = set()
        self._lock = threading.RLock()
        self.recompute()

    def recompute(self) -> dict[str, Any]:
        """Recompute active/potential/rejected statuses, cardinality, unmatched sets, and scorecard."""
        with self._lock:
            m_thr, _ = self.options.effective_thresholds()
            active_pairs: list[MatchPairView] = []
            potential_pairs: list[MatchPairView] = []
            rejected_pairs: list[MatchPairView] = []

            for p in self.pairs:
                if p.steward_decision == "approved":
                    p.effective_status = "MATCHED"
                    active_pairs.append(p)
                elif p.steward_decision == "rejected":
                    p.effective_status = "REJECTED"
                    p.cardinality = "NONE"
                    p.is_primary_match = False
                    rejected_pairs.append(p)
                elif p.score >= m_thr:
                    p.effective_status = "MATCHED"
                    active_pairs.append(p)
                else:
                    p.effective_status = "POTENTIAL_MATCH"
                    p.cardinality = "CANDIDATE"
                    p.is_primary_match = False
                    potential_pairs.append(p)

            left_deg: dict[int, int] = defaultdict(int)
            right_deg: dict[int, int] = defaultdict(int)
            for p in active_pairs:
                left_deg[p.left_idx] += 1
                right_deg[p.right_idx] += 1

            card_counts = {"1:1": 0, "N:1": 0, "1:N": 0, "M:N": 0}
            tier_counts = {"TIER_1_EXACT_ID": 0, "TIER_2_MULTI_SIGNAL": 0, "TIER_3_FUZZY_CANDIDATE": 0}
            seen_primary_left: set[int] = set()
            for p in sorted(active_pairs, key=lambda x: (0 if x.steward_decision == "approved" else 1)):
                ld = left_deg[p.left_idx]
                rd = right_deg[p.right_idx]
                if ld == 1 and rd == 1:
                    p.cardinality = "1:1"
                elif ld > 1 and rd == 1:
                    p.cardinality = "1:N"
                elif ld == 1 and rd > 1:
                    p.cardinality = "N:1"
                else:
                    p.cardinality = "M:N"
                card_counts[p.cardinality] += 1
                tier_counts[p.match_tier] = tier_counts.get(p.match_tier, 0) + 1
                if p.left_idx not in seen_primary_left:
                    seen_primary_left.add(p.left_idx)
                    p.is_primary_match = True
                else:
                    p.is_primary_match = False

            self.matched_left_set = {p.left_idx for p in active_pairs}
            self.matched_right_set = {p.right_idx for p in active_pairs}
            pot_left = {p.left_idx for p in potential_pairs} - self.matched_left_set
            pot_right = {p.right_idx for p in potential_pairs} - self.matched_right_set

            total_l = len(self.left_records)
            total_r = len(self.right_records)
            agreements = [p.attribute_agreement_pct for p in active_pairs if p.fields_compared > 0]
            avg_agree = round(sum(agreements) / len(agreements), 2) if agreements else 0.0

            pillar_stats: dict[str, float] = {}
            for cmp_key, label in (
                ("cmp_crd", "crd"),
                ("cmp_org", "organization"),
                ("cmp_person", "person"),
                ("cmp_street", "street"),
                ("cmp_phone", "phone"),
                ("cmp_email", "email"),
                ("cmp_website", "website"),
            ):
                vals = [
                    p.field_comparisons[cmp_key]
                    for p in active_pairs
                    if p.field_comparisons[cmp_key] in ("EXACT", "EQUIV", "CONFLICT")
                ]
                if vals:
                    ok = sum(1 for v in vals if v in ("EXACT", "EQUIV"))
                    pillar_stats[label] = round(100.0 * ok / len(vals), 2)

            self.scorecard = {
                "profile": self.options.profile,
                "total_left": total_l,
                "total_right": total_r,
                "matched_left": len(self.matched_left_set),
                "matched_left_pct": round(100.0 * len(self.matched_left_set) / total_l, 2) if total_l else 0.0,
                "matched_right": len(self.matched_right_set),
                "matched_right_pct": round(100.0 * len(self.matched_right_set) / total_r, 2) if total_r else 0.0,
                "potential_left": len(pot_left),
                "potential_right": len(pot_right),
                "unmatched_left": total_l - len(self.matched_left_set),
                "unmatched_right": total_r - len(self.matched_right_set),
                "matched_pairs": len(active_pairs),
                "potential_pairs": len(potential_pairs),
                "rejected_pairs": len(rejected_pairs),
                "tier_counts": tier_counts,
                "cardinality_counts": card_counts,
                "avg_attribute_agreement_pct": avg_agree,
                "pillar_agreement_pct": pillar_stats,
                "synthetic_left": sum(1 for r in self.left_records if r.is_synthetic),
                "synthetic_right": sum(1 for r in self.right_records if r.is_synthetic),
                "excluded_synthetic_left": self.excluded_synthetic_left,
                "excluded_synthetic_right": self.excluded_synthetic_right,
                "elapsed_ms": self.elapsed_ms,
            }
            return self.scorecard

    def apply_decision(self, pair_id: str, decision: str, note: str = "") -> dict[str, Any]:
        """Apply a steward override ('approve', 'reject', or 'reset') to pair_id and recompute scorecard."""
        with self._lock:
            if pair_id not in self._pairs_by_id:
                raise KeyError(f"Unknown pair_id {pair_id!r}.")
            pair = self._pairs_by_id[pair_id]
            act = decision.strip().lower()
            if act == "approve":
                pair.steward_decision = "approved"
            elif act == "reject":
                pair.steward_decision = "rejected"
            elif act == "reset":
                pair.steward_decision = None
            else:
                raise ValueError(f"Invalid decision {decision!r}; expected 'approve', 'reject', or 'reset'.")
            pair.steward_note = note
            scorecard = self.recompute()
            return {"pair": pair.to_dict(), "scorecard": scorecard}

    def query_pairs(
        self,
        *,
        view: str = "all_pairs",
        cardinality: str | None = None,
        search: str = "",
        discrepancy_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Filter and paginate match pairs or unmatched Left/Right records."""
        with self._lock:
            q = search.strip().lower()
            if view in ("unmatched_left", "unmatched_right"):
                recs, matched_set = (
                    (self.left_records, self.matched_left_set)
                    if view == "unmatched_left"
                    else (self.right_records, self.matched_right_set)
                )
                items = [
                    {**disp, "raw_row": sanitize_row_for_json(r.raw_row)}
                    for idx, r in enumerate(recs)
                    if idx not in matched_set
                    for disp in (r.flat_display(),)
                    if not q or _display_matches_query(disp, q)
                ]
            else:
                status_map = {
                    "matched": "MATCHED",
                    "potential": "POTENTIAL_MATCH",
                    "rejected": "REJECTED",
                }
                target_status = status_map.get(view)
                filtered: list[MatchPairView] = []
                for p in self.pairs:
                    if target_status and p.effective_status != target_status:
                        continue
                    if cardinality and p.cardinality != cardinality:
                        continue
                    if discrepancy_only and not p.discrepancy_fields:
                        continue
                    if q:
                        pair_text = f"{p.pair_id} {p.explanation} {p.steward_note}".lower()
                        if (
                            q not in pair_text
                            and not _display_matches_query(p.left_display, q)
                            and not _display_matches_query(p.right_display, q)
                        ):
                            continue
                    filtered.append(p)
                items = [p.to_dict() for p in filtered]

            total = len(items)
            page = items[offset : offset + limit]
            return {"total": total, "offset": offset, "limit": limit, "items": page, "scorecard": self.scorecard}

    def _comparison_columns_and_rows(self) -> tuple[list[str], list[dict[str, Any]]]:
        cols = [
            "pair_id",
            "effective_status",
            "match_tier",
            "engine_disposition",
            "steward_decision",
            "steward_note",
            "score_100",
            "cardinality",
            "is_primary_match",
            "left_id",
            "right_id",
            "left_org",
            "right_org",
            "cmp_org",
            "left_person",
            "right_person",
            "cmp_person",
            "left_crd",
            "right_crd",
            "cmp_crd",
            "left_street1",
            "right_street1",
            "cmp_street",
            "left_city",
            "right_city",
            "cmp_city",
            "left_state",
            "right_state",
            "cmp_state",
            "left_postal",
            "right_postal",
            "cmp_postal",
            "left_country",
            "right_country",
            "cmp_country",
            "left_phone",
            "right_phone",
            "cmp_phone",
            "left_email",
            "right_email",
            "cmp_email",
            "left_website",
            "right_website",
            "cmp_website",
            "cmp_roster",
            "fields_compared",
            "fields_matched",
            "attribute_agreement_pct",
            "discrepancy_fields",
            "matched_signals",
            "conflicting_signals",
            "match_explanation",
        ]
        rows: list[dict[str, Any]] = []
        for p in self.pairs:
            ld, rd, fc = p.left_display, p.right_display, p.field_comparisons
            rows.append(
                {
                    "pair_id": p.pair_id,
                    "effective_status": p.effective_status,
                    "match_tier": p.match_tier,
                    "engine_disposition": p.engine_disposition,
                    "steward_decision": p.steward_decision or "",
                    "steward_note": p.steward_note,
                    "score_100": p.score_100,
                    "cardinality": p.cardinality,
                    "is_primary_match": str(p.is_primary_match),
                    "left_id": p.left_id,
                    "right_id": p.right_id,
                    "left_org": ld.get("organization", ""),
                    "right_org": rd.get("organization", ""),
                    "cmp_org": fc["cmp_org"],
                    "left_person": ld.get("person_name", ""),
                    "right_person": rd.get("person_name", ""),
                    "cmp_person": fc["cmp_person"],
                    "left_crd": ld.get("crd", ""),
                    "right_crd": rd.get("crd", ""),
                    "cmp_crd": fc["cmp_crd"],
                    "left_street1": ld.get("street1", ""),
                    "right_street1": rd.get("street1", ""),
                    "cmp_street": fc["cmp_street"],
                    "left_city": ld.get("city", ""),
                    "right_city": rd.get("city", ""),
                    "cmp_city": fc["cmp_city"],
                    "left_state": ld.get("state", ""),
                    "right_state": rd.get("state", ""),
                    "cmp_state": fc["cmp_state"],
                    "left_postal": ld.get("postal_code", ""),
                    "right_postal": rd.get("postal_code", ""),
                    "cmp_postal": fc["cmp_postal"],
                    "left_country": ld.get("country", ""),
                    "right_country": rd.get("country", ""),
                    "cmp_country": fc["cmp_country"],
                    "left_phone": ld.get("phone", ""),
                    "right_phone": rd.get("phone", ""),
                    "cmp_phone": fc["cmp_phone"],
                    "left_email": ld.get("email", ""),
                    "right_email": rd.get("email", ""),
                    "cmp_email": fc["cmp_email"],
                    "left_website": ld.get("website", ""),
                    "right_website": rd.get("website", ""),
                    "cmp_website": fc["cmp_website"],
                    "cmp_roster": fc["cmp_roster"],
                    "fields_compared": p.fields_compared,
                    "fields_matched": p.fields_matched,
                    "attribute_agreement_pct": p.attribute_agreement_pct,
                    "discrepancy_fields": "|".join(p.discrepancy_fields),
                    "matched_signals": "|".join(p.matched_signals),
                    "conflicting_signals": "|".join(p.conflicting_signals),
                    "match_explanation": p.explanation,
                }
            )
        return cols, rows

    def _scorecard_columns_and_rows(self) -> tuple[list[str], list[dict[str, Any]]]:
        cols = ["metric", "value"]
        rows: list[dict[str, Any]] = []
        for k, v in self.scorecard.items():
            val = "; ".join(f"{sk}={sv}" for sk, sv in v.items()) if isinstance(v, dict) else v
            rows.append({"metric": k, "value": val})
        return cols, rows

    def export_comparison(
        self, output_path: str | Path, format_spec: FileFormatSpec | None = None
    ) -> int:
        """Write full side-by-side comparison report with steward decisions."""
        with self._lock:
            cols, rows = self._comparison_columns_and_rows()
        spec = format_spec or FileFormatSpec(format="csv")
        return write_tabular_output(output_path, cols, rows, spec)

    def export_scorecard(
        self, output_path: str | Path, format_spec: FileFormatSpec | None = None
    ) -> int:
        """Write match summary scorecard."""
        with self._lock:
            cols, rows = self._scorecard_columns_and_rows()
        spec = format_spec or FileFormatSpec(format="csv")
        return write_tabular_output(output_path, cols, rows, spec)

    def export_enriched_left(self, output_path: str | Path) -> int:
        """Write Left source dataset in its exact original format with appended match columns."""
        with self._lock:
            best_by_left: dict[int, MatchPairView] = {}
            ranked = sorted(
                (p for p in self.pairs if p.effective_status in ("MATCHED", "POTENTIAL_MATCH")),
                key=lambda p: (
                    0 if p.steward_decision == "approved" else (1 if p.effective_status == "MATCHED" else 2)
                ),
            )
            for p in ranked:
                if p.left_idx not in best_by_left:
                    best_by_left[p.left_idx] = p

            extra_cols = [
                "match_status",
                "matched_right_id",
                "match_score_100",
                "match_cardinality",
                "match_tier",
                "steward_decision",
                "match_explanation",
            ]
            cols = list(self.left_columns) + [c for c in extra_cols if c not in self.left_columns]
            out_rows: list[dict[str, Any]] = []
            for idx, rec in enumerate(self.left_records):
                row_out = dict(rec.raw_row)
                pair = best_by_left.get(idx)
                if pair is not None:
                    row_out.update(
                        {
                            "match_status": pair.effective_status,
                            "matched_right_id": pair.right_id,
                            "match_score_100": pair.score_100,
                            "match_cardinality": pair.cardinality,
                            "match_tier": pair.match_tier,
                            "steward_decision": pair.steward_decision or "",
                            "match_explanation": pair.explanation,
                        }
                    )
                else:
                    row_out.update(
                        {
                            "match_status": "UNMATCHED",
                            "matched_right_id": "",
                            "match_score_100": "",
                            "match_cardinality": "",
                            "match_tier": "",
                            "steward_decision": "",
                            "match_explanation": "",
                        }
                    )
                out_rows.append(row_out)
        return write_tabular_output(
            output_path,
            cols,
            out_rows,
            self.left_format,
            template_xlsx_path=self.left_source_path if (self.left_source_path and self.left_format.format == "xlsx") else None,
            source_parquet_path=self.left_source_path if (self.left_source_path and self.left_format.format == "parquet") else None,
        )

    def export_unmatched_left(self, output_path: str | Path) -> int:
        """Write unmatched Left records in Left's exact original file format."""
        with self._lock:
            rows = [
                dict(rec.raw_row)
                for idx, rec in enumerate(self.left_records)
                if idx not in self.matched_left_set
            ]
        return write_tabular_output(
            output_path,
            self.left_columns,
            rows,
            self.left_format,
            template_xlsx_path=self.left_source_path if (self.left_source_path and self.left_format.format == "xlsx") else None,
            source_parquet_path=self.left_source_path if (self.left_source_path and self.left_format.format == "parquet") else None,
        )

    def export_unmatched_right(self, output_path: str | Path) -> int:
        """Write unmatched Right records in Right's exact original file format."""
        with self._lock:
            rows = [
                dict(rec.raw_row)
                for idx, rec in enumerate(self.right_records)
                if idx not in self.matched_right_set
            ]
        return write_tabular_output(
            output_path,
            self.right_columns,
            rows,
            self.right_format,
            template_xlsx_path=self.right_source_path if (self.right_source_path and self.right_format.format == "xlsx") else None,
            source_parquet_path=self.right_source_path if (self.right_source_path and self.right_format.format == "parquet") else None,
        )

    def export_xlsx_bundle(self, output_path: str | Path) -> None:
        """Write multi-sheet Excel bundle (Scorecard, Comparison, Unmatched_Left, Unmatched_Right)."""
        with self._lock:
            sc_cols, sc_rows = self._scorecard_columns_and_rows()
            cmp_cols, cmp_rows = self._comparison_columns_and_rows()
            un_l = [dict(r.raw_row) for idx, r in enumerate(self.left_records) if idx not in self.matched_left_set]
            un_r = [dict(r.raw_row) for idx, r in enumerate(self.right_records) if idx not in self.matched_right_set]
        write_xlsx_sheets(
            output_path,
            {
                "Scorecard": (sc_cols, sc_rows),
                "Comparison": (cmp_cols, cmp_rows),
                "Unmatched_Left": (self.left_columns, un_l),
                "Unmatched_Right": (self.right_columns, un_r),
            },
        )


def _read_all_rows(
    path: str | Path,
    *,
    delimiter_override: str | None = None,
    sheet_name: str | None = None,
) -> tuple[FileFormatSpec, list[str], list[dict[str, Any]]]:
    spec = detect_file_format(path, delimiter_override=delimiter_override, sheet_name=sheet_name)
    columns, row_iter = iter_tabular_rows(path, spec)
    try:
        rows = list(row_iter)
    finally:
        close_row_iter(row_iter)
    return spec, columns, rows


def run_cross_system_match(
    left_path: str | Path,
    right_path: str | Path,
    left_mapping: MappingConfig,
    right_mapping: MappingConfig,
    options: MatchingOptions,
    *,
    left_delimiter: str | None = None,
    left_sheet: str | None = None,
    right_delimiter: str | None = None,
    right_sheet: str | None = None,
    left_roster_source: MemberRosterSource | None = None,
    right_roster_source: MemberRosterSource | None = None,
) -> MatchSession:
    """Run cross-system blocking, multi-signal scoring, and reviewable match session build."""
    t0 = time.perf_counter()
    left_spec, left_cols, left_raw = _read_all_rows(
        left_path, delimiter_override=left_delimiter, sheet_name=left_sheet
    )
    right_spec, right_cols, right_raw = _read_all_rows(
        right_path, delimiter_override=right_delimiter, sheet_name=right_sheet
    )

    left_roster = load_member_roster_map(left_roster_source) if left_roster_source else None
    right_roster = load_member_roster_map(right_roster_source) if right_roster_source else None

    left_recs, excl_l = prepare_records_for_matching(
        left_raw, left_mapping.for_columns(left_cols), options, roster_map=left_roster
    )
    right_recs, excl_r = prepare_records_for_matching(
        right_raw, right_mapping.for_columns(right_cols), options, roster_map=right_roster
    )

    phone_rows = [
        {"e164": rec.contact.phone.e164 or ""}
        for rec in (*left_recs, *right_recs)
        if rec.contact.phone.is_valid and rec.contact.phone.e164
    ]
    switchboard_phones = compute_switchboard_phones(
        phone_rows, phone_field="e164", min_shared_count=options.switchboard_min_shared
    )

    enabled_set = frozenset(options.enabled_signals)
    tier_index: dict[tuple[int, str], list[int]] = defaultdict(list)
    for r_idx, r_rec in enumerate(right_recs):
        keys_by_tier = _blocking_keys_for_record(r_rec, enabled_set, switchboard_phones)
        for tier_num, key_list in keys_by_tier.items():
            for key in key_list:
                tier_index[(tier_num, key)].append(r_idx)

    seen_pairs: set[tuple[int, int]] = set()
    scored_pairs: list[tuple[float, int, int, int, Any]] = []
    _, pot_thr = options.effective_thresholds()

    for l_idx, l_rec in enumerate(left_recs):
        l_keys = _blocking_keys_for_record(l_rec, enabled_set, switchboard_phones)
        for tier_num in (1, 2, 3):
            for key in l_keys[tier_num]:
                bucket = tier_index.get((tier_num, key), ())
                if tier_num == 3 and len(bucket) > _MAX_TIER3_BUCKET_SIZE:
                    continue
                for r_idx in bucket:
                    pair = (l_idx, r_idx)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    scored = _score_entity_pair(l_rec, right_recs[r_idx], options, switchboard_phones)
                    if scored.score >= pot_thr:
                        scored_pairs.append((scored.score, tier_num, l_idx, r_idx, scored))

    scored_pairs.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
    pair_views: list[MatchPairView] = []
    for n, (_, _, l_idx, r_idx, scored) in enumerate(scored_pairs, start=1):
        l_rec = left_recs[l_idx]
        r_rec = right_recs[r_idx]
        cmps, f_cmp, f_match, agree_pct, discrepancies = _compute_field_comparisons(l_rec, r_rec)
        if any(s in scored.matched_signals for s in ("EXTERNAL_ID", "FINRA_CRD")):
            m_tier = "TIER_1_EXACT_ID"
        elif scored.is_match:
            m_tier = "TIER_2_MULTI_SIGNAL"
        else:
            m_tier = "TIER_3_FUZZY_CANDIDATE"

        pair_views.append(
            MatchPairView(
                pair_id=f"PAIR-{n:06d}",
                left_idx=l_idx,
                right_idx=r_idx,
                left_id=l_rec.record_id,
                right_id=r_rec.record_id,
                match_tier=m_tier,
                engine_disposition=scored.disposition,
                effective_status="MATCHED" if scored.is_match else "POTENTIAL_MATCH",
                steward_decision=None,
                steward_note="",
                cardinality="1:1",
                is_primary_match=False,
                score=scored.score,
                score_100=scored.score_100,
                explanation=scored.explanation,
                matched_signals=list(scored.matched_signals),
                conflicting_signals=list(scored.conflicting_signals),
                evidence=[ev.to_dict() for ev in scored.evidence],
                field_comparisons=cmps,
                fields_compared=f_cmp,
                fields_matched=f_match,
                attribute_agreement_pct=agree_pct,
                discrepancy_fields=discrepancies,
                left_display=l_rec.flat_display(),
                right_display=r_rec.flat_display(),
            )
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return MatchSession(
        left_records=left_recs,
        right_records=right_recs,
        left_columns=left_cols,
        right_columns=right_cols,
        left_format=left_spec,
        right_format=right_spec,
        options=options,
        pairs=pair_views,
        excluded_synthetic_left=excl_l,
        excluded_synthetic_right=excl_r,
        elapsed_ms=elapsed_ms,
        left_source_path=left_path,
        right_source_path=right_path,
    )


def _completeness_rank(rec: PreparedEntityRecord) -> tuple[int, float, int]:
    d = rec.flat_display()
    populated = sum(
        1
        for k in ("external_id", "crd", "organization", "person_name", "street1", "city", "state", "postal_code", "phone", "email", "website")
        if d.get(k)
    )
    return (populated, rec.contact.overall_confidence, -rec.row_index)


class DedupSession:
    """Single-file deduplication session with steward row exclusion overrides & same-format export."""

    def __init__(
        self,
        *,
        records: list[PreparedEntityRecord],
        columns: list[str],
        format_spec: FileFormatSpec,
        mapping_config: MappingConfig,
        options: MatchingOptions,
        linked_pairs: list[tuple[int, int, str]],
        excluded_synthetic: int,
        elapsed_ms: float,
        source_path: str | Path | None = None,
    ) -> None:
        self.records = records
        self.columns = columns
        self.format_spec = format_spec
        self.mapping_config = mapping_config
        self.options = options
        self.linked_pairs = linked_pairs
        self.excluded_rows: set[int] = set()
        self.excluded_synthetic = excluded_synthetic
        self.elapsed_ms = elapsed_ms
        self.source_path = Path(source_path) if source_path is not None else None
        self.clusters: list[dict[str, Any]] = []
        self.row_cluster_map: dict[int, dict[str, Any]] = {}
        self.summary: dict[str, Any] = {}
        self._lock = threading.RLock()
        self.recompute()

    def recompute(self) -> dict[str, Any]:
        """Rebuild clusters excluding any steward-excluded rows from multi-record merges."""
        with self._lock:
            n = len(self.records)
            dsu = DisjointSet(range(n))
            for i, j, reason in self.linked_pairs:
                if (
                    self.records[i].row_index not in self.excluded_rows
                    and self.records[j].row_index not in self.excluded_rows
                ):
                    dsu.union(i, j, reason)

            raw_groups = list(dsu.groups().items())
            raw_groups.sort(key=lambda item: (-len(item[1]), item[1][0]))

            new_clusters: list[dict[str, Any]] = []
            new_row_map: dict[int, dict[str, Any]] = {}
            for idx, (root_idx, member_indices) in enumerate(raw_groups, start=1):
                cluster_id = f"CLUSTER-{idx:05d}"
                members = [self.records[m] for m in member_indices]
                golden = max(members, key=_completeness_rank)
                reasons = sorted(dsu.reasons[root_idx] or {"SINGLETON"})
                cluster_dict = {
                    "cluster_id": cluster_id,
                    "cluster_size": len(members),
                    "golden_record_id": golden.record_id,
                    "golden_row_index": golden.row_index,
                    "golden_display": golden.flat_display(),
                    "reasons": reasons,
                    "members": [
                        {
                            "row_index": m.row_index,
                            "record_id": m.record_id,
                            "is_golden": m.row_index == golden.row_index,
                            "excluded": m.row_index in self.excluded_rows,
                            "display": m.flat_display(),
                        }
                        for m in members
                    ],
                }
                new_clusters.append(cluster_dict)
                for m in members:
                    new_row_map[m.row_index] = {
                        "cluster_id": cluster_id,
                        "cluster_size": len(members),
                        "is_golden_record": m.row_index == golden.row_index,
                        "golden_record_id": golden.record_id,
                        "golden_rec": golden,
                        "members": members,
                    }

            self.clusters = new_clusters
            self.row_cluster_map = new_row_map
            dup_rows = n - len(new_clusters)
            self.summary = {
                "total_records": n,
                "cluster_count": len(new_clusters),
                "duplicate_rows_collapsed": dup_rows,
                "multi_record_clusters": sum(1 for c in new_clusters if c["cluster_size"] > 1),
                "excluded_synthetic": self.excluded_synthetic,
                "elapsed_ms": self.elapsed_ms,
            }
            return self.summary

    def set_excluded_row(self, row_index: int, excluded: bool) -> dict[str, Any]:
        """Exclude or restore a record row from clustering and recompute golden clusters."""
        with self._lock:
            valid_indices = {r.row_index for r in self.records}
            if row_index not in valid_indices:
                raise KeyError(f"Unknown row_index {row_index}.")
            if excluded:
                self.excluded_rows.add(row_index)
            else:
                self.excluded_rows.discard(row_index)
            summary = self.recompute()
            return {"summary": summary, "clusters": self.clusters}

    def export(
        self,
        output_path: str | Path,
        *,
        mode: str = "tagged_all_rows",
        format_spec: FileFormatSpec | None = None,
    ) -> int:
        """Export deduplicated results in the exact source format ('tagged_all_rows' or 'golden_only')."""
        spec = format_spec or self.format_spec
        with self._lock:
            if mode == "golden_only":
                extra = ["cluster_id", "cluster_size", "merged_record_ids"]
                cols = list(self.columns) + [c for c in extra if c not in self.columns]
                out_rows: list[dict[str, Any]] = []
                for c in self.clusters:
                    meta = self.row_cluster_map[c["golden_row_index"]]
                    golden_rec: PreparedEntityRecord = meta["golden_rec"]
                    members: list[PreparedEntityRecord] = meta["members"]
                    merged_row = dict(golden_rec.raw_row)
                    for m in members:
                        for col in self.columns:
                            if not cell_to_input_text(merged_row.get(col)) and cell_to_input_text(m.raw_row.get(col)):
                                merged_row[col] = m.raw_row[col]
                    merged_row["cluster_id"] = c["cluster_id"]
                    merged_row["cluster_size"] = c["cluster_size"]
                    merged_row["merged_record_ids"] = "|".join(m.record_id for m in members)
                    out_rows.append(merged_row)
            elif mode == "tagged_all_rows":
                extra = ["cluster_id", "cluster_size", "is_golden_record", "golden_record_id"]
                cols = list(self.columns) + [c for c in extra if c not in self.columns]
                out_rows = []
                for rec in self.records:
                    meta = self.row_cluster_map[rec.row_index]
                    row_out = dict(rec.raw_row)
                    row_out["cluster_id"] = meta["cluster_id"]
                    row_out["cluster_size"] = meta["cluster_size"]
                    row_out["is_golden_record"] = str(meta["is_golden_record"])
                    row_out["golden_record_id"] = meta["golden_record_id"]
                    out_rows.append(row_out)
            else:
                raise ValueError(f"Unsupported dedup export mode {mode!r}.")
        return write_tabular_output(
            output_path,
            cols,
            out_rows,
            spec,
            template_xlsx_path=self.source_path if (self.source_path and spec.format == "xlsx") else None,
            source_parquet_path=self.source_path if (self.source_path and spec.format == "parquet") else None,
        )


def run_single_file_dedup(
    source_path: str | Path,
    mapping_config: MappingConfig,
    options: MatchingOptions,
    *,
    delimiter_override: str | None = None,
    sheet_name: str | None = None,
) -> DedupSession:
    """Cluster duplicate records within a single dataset into Golden Record clusters."""
    t0 = time.perf_counter()
    spec, cols, raw_rows = _read_all_rows(
        source_path, delimiter_override=delimiter_override, sheet_name=sheet_name
    )
    eff_mapping = mapping_config.for_columns(cols)
    recs, excl_syn = prepare_records_for_matching(raw_rows, eff_mapping, options)

    phone_rows = [
        {"e164": rec.contact.phone.e164 or ""}
        for rec in recs
        if rec.contact.phone.is_valid and rec.contact.phone.e164
    ]
    switchboard_phones = compute_switchboard_phones(
        phone_rows, phone_field="e164", min_shared_count=options.switchboard_min_shared
    )

    enabled_set = frozenset(options.enabled_signals)
    buckets: dict[tuple[int, str], list[int]] = defaultdict(list)
    for pos, rec in enumerate(recs):
        keys_by_tier = _blocking_keys_for_record(rec, enabled_set, switchboard_phones)
        for tier_num, klist in keys_by_tier.items():
            for k in klist:
                buckets[(tier_num, k)].append(pos)

    seen_pairs: set[tuple[int, int]] = set()
    linked_pairs: list[tuple[int, int, str]] = []
    for (tier_num, _), idxs in buckets.items():
        if len(idxs) < 2 or (tier_num == 3 and len(idxs) > _MAX_TIER3_BUCKET_SIZE):
            continue
        for p1 in range(len(idxs)):
            for p2 in range(p1 + 1, len(idxs)):
                a, b = min(idxs[p1], idxs[p2]), max(idxs[p1], idxs[p2])
                if (a, b) in seen_pairs:
                    continue
                seen_pairs.add((a, b))
                scored = _score_entity_pair(recs[a], recs[b], options, switchboard_phones)
                if scored.is_match:
                    reason = "+".join(scored.matched_signals) or "MULTI_SIGNAL"
                    linked_pairs.append((a, b, reason))

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return DedupSession(
        records=recs,
        columns=cols,
        format_spec=spec,
        mapping_config=eff_mapping,
        options=options,
        linked_pairs=linked_pairs,
        excluded_synthetic=excl_syn,
        elapsed_ms=elapsed_ms,
        source_path=source_path,
    )
