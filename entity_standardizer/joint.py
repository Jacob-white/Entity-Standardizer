"""Joint Multi-Pillar Entity Standardization and Bidirectional Cross-Healing Engine."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any

from entity_standardizer.address.models import StandardizedAddress
from entity_standardizer.address.normalization import normalize_country_code
from entity_standardizer.address.standardizer import get_state_from_zip3, standardize_address
from entity_standardizer.company import (
    StandardizedCompany,
    compare_companies,
    standardize_company,
)
from entity_standardizer.models import PhoneRiskFlag, StandardizedPhone
from entity_standardizer.person import (
    StandardizedJobTitle,
    StandardizedPerson,
    compare_persons,
    split_compound_persons,
    standardize_job_title,
    standardize_person,
)
from entity_standardizer.registry import normalize_country_iso2
from entity_standardizer.standardizer import _extract_address_hint, standardize_phone
from entity_standardizer.web import (
    StandardizedEmail,
    StandardizedSocial,
    StandardizedUrl,
    _FREE_WEBMAIL_DOMAINS,
    compare_emails,
    compare_urls,
    extract_registrable_domain,
    standardize_email,
    standardize_social,
    standardize_url,
)

_PHONE_EXT_SUFFIX_PAT = r"(?:[;,|\s]*(?:(?:ext\.?|extension|xt\.?|isub|x\.?|#)\s*[:\-=#]?\s*)\d{1,10})?"
_EMBEDDED_PHONE_LABEL_RE = re.compile(
    rf"(?:[,;|/\-]|\b(?:TEL|TELEPHONE|PHONE|PH|MOBILE|CELL|CALL)\b)[:.\s]*([+()\d][\d\s().\-]{{6,22}}{_PHONE_EXT_SUFFIX_PAT})$",
    re.IGNORECASE,
)
_PURE_PHONE_IN_STREET_RE = re.compile(
    rf"^\s*\+?[\d()\s.\-]{{7,22}}{_PHONE_EXT_SUFFIX_PAT}\s*$",
    re.IGNORECASE,
)

_EMBEDDED_EMAIL_RE = re.compile(
    r"(?:[,;|/\-\s]*(?:\b(?:EMAIL|E-MAIL|MAIL)\b[:.\s]*))?"
    r"(?:<\s*([A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\s*>"
    r"|\(\s*([A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\s*\)"
    r"|(?<![A-Za-z0-9._+\-])([A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}))",
    re.IGNORECASE,
)

_EMBEDDED_URL_RE = re.compile(
    r"(?:[,;|/\-\s]*(?:\b(?:WEB|WEBSITE|URL|SITE)\b[:.\s]*))?"
    r"\b((?:https?://|www\.)[^\s,;|()<>]+)"
    r"|[,;|/\-\s]*\b(?:WEB|WEBSITE|URL|SITE)\b[:.\s]+([A-Za-z0-9][A-Za-z0-9\-]*\.[A-Za-z]{2,}(?:\.[A-Za-z]{2,})?(?:/[^\s,;|()<>]*)?)",
    re.IGNORECASE,
)

_CORPORATE_CARE_OF_WORDS: frozenset[str] = frozenset(
    {
        "HOLDINGS",
        "HOLDING",
        "GROUP",
        "DEPARTMENT",
        "DEPT",
        "DIVISION",
        "DIV",
        "OFFICE",
        "PARTNERS",
        "VENTURES",
        "CAPITAL",
        "SOLUTIONS",
        "SERVICES",
        "ENTERPRISES",
        "INDUSTRIES",
        "MANAGEMENT",
        "BILLING",
        "ACCOUNTS",
        "PAYABLE",
        "RECEIVABLE",
    }
)


class CrossHealingAction(StrEnum):
    """Audit trail flag recorded when entity standardization pillars heal each other."""

    PHONE_RESCUED_FROM_ADDRESS_FIELD = "PHONE_RESCUED_FROM_ADDRESS_FIELD"
    ADDRESS_COUNTRY_INFERRED_FROM_PHONE = "ADDRESS_COUNTRY_INFERRED_FROM_PHONE"
    ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA = "ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA"
    PHONE_HEALED_FROM_STANDARDIZED_ADDRESS = "PHONE_HEALED_FROM_STANDARDIZED_ADDRESS"
    EMAIL_RESCUED_FROM_FIELD = "EMAIL_RESCUED_FROM_FIELD"
    URL_RESCUED_FROM_FIELD = "URL_RESCUED_FROM_FIELD"
    PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF = "PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF"
    ORGANIZATION_INFERRED_FROM_DOMAIN = "ORGANIZATION_INFERRED_FROM_DOMAIN"
    EMAIL_WEBSITE_DOMAIN_MATCH = "EMAIL_WEBSITE_DOMAIN_MATCH"
    EMAIL_WEBSITE_DOMAIN_MISMATCH = "EMAIL_WEBSITE_DOMAIN_MISMATCH"
    COUNTRY_INFERRED_FROM_ENTITY_PILLARS = "COUNTRY_INFERRED_FROM_ENTITY_PILLARS"
    ORGANIZATION_RESCUED_FROM_PERSON_FIELD = "ORGANIZATION_RESCUED_FROM_PERSON_FIELD"
    COMPOUND_PERSON_SPLIT = "COMPOUND_PERSON_SPLIT"


@dataclass(slots=True)
class StandardizedContact:
    """Unified standardized representation of a multi-pillar entity and contact record."""

    address: StandardizedAddress
    phone: StandardizedPhone
    fax: StandardizedPhone | None = None
    organization: StandardizedCompany | None = None
    person: StandardizedPerson | None = None
    additional_persons: tuple[StandardizedPerson, ...] = ()
    job_title: StandardizedJobTitle | None = None
    email: StandardizedEmail | None = None
    website: StandardizedUrl | None = None
    social: StandardizedSocial | None = None
    entity_key: str | None = None
    cross_healing_actions: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0

    @property
    def company(self) -> StandardizedCompany | None:
        """Alias for organization pillar."""
        return self.organization

    def to_dict(self) -> dict[str, Any]:
        """Serialize the joint contact/entity record into a JSON-compatible dictionary."""
        return {
            "address": self.address.as_dict(),
            "phone": self.phone.to_dict(),
            "fax": self.fax.to_dict() if self.fax is not None else None,
            "organization": self.organization.to_dict() if self.organization is not None else None,
            "person": self.person.to_dict() if self.person is not None else None,
            "additional_persons": [p.to_dict() for p in self.additional_persons],
            "job_title": self.job_title.to_dict() if self.job_title is not None else None,
            "email": self.email.to_dict() if self.email is not None else None,
            "website": self.website.to_dict() if self.website is not None else None,
            "social": self.social.to_dict() if self.social is not None else None,
            "entity_key": self.entity_key,
            "cross_healing_actions": list(self.cross_healing_actions),
            "overall_confidence": round(self.overall_confidence, 4),
        }


StandardizedEntity = StandardizedContact


def _try_rescue_email_from_text(
    text: str | None,
    *,
    allow_display_name: bool = False,
) -> tuple[StandardizedEmail | None, str | None]:
    """Attempt to rescue an embedded or angle-bracketed email from a text field."""
    if not text or "@" not in text:
        return None, text
    s = text.strip()
    if allow_display_name:
        full_cand = standardize_email(s)
        if full_cand.is_valid:
            cleaned = full_cand.display_name or ""
            return full_cand, cleaned or None

    match = _EMBEDDED_EMAIL_RE.search(s)
    if match:
        raw_addr = match.group(1) or match.group(2) or match.group(3)
        cand = standardize_email(raw_addr)
        if cand.is_valid:
            before = s[: match.start()].strip(" ,;|/-")
            after = s[match.end() :].strip(" ,;|/-")
            cleaned = f"{before} {after}".strip()
            return cand, cleaned or None
    return None, text


def _try_rescue_url_from_street(
    street1: str | None,
    street2: str | None,
) -> tuple[StandardizedUrl | None, str | None, str | None]:
    """Attempt to rescue a misplaced website URL from street1 or street2."""
    for idx, field_val in enumerate((street1, street2)):
        if not field_val:
            continue
        s = field_val.strip()
        if not s:
            continue
        m = _EMBEDDED_URL_RE.search(s)
        if m:
            raw_url = (m.group(1) or m.group(2) or "").rstrip(".,;)")
            cand = standardize_url(raw_url)
            if cand.is_valid:
                before = s[: m.start()].strip(" ,;|/-")
                after = s[m.end() :].strip(" ,;|/-")
                cleaned = f"{before} {after}".strip() or None
                if idx == 0:
                    return cand, cleaned or "", street2
                return cand, street1, cleaned or ""
    return None, street1, street2


def _try_rescue_phone_from_street(
    street1: str | None,
    street2: str | None,
    country: str | None,
    default_country: str,
    addr_ctx: dict[str, Any],
) -> tuple[StandardizedPhone | None, str | None, str | None]:
    """Check whether street1 or street2 contains a misplaced phone number."""
    s1 = (street1 or "").strip()
    s2 = (street2 or "").strip()

    if s1 and _PURE_PHONE_IN_STREET_RE.match(s1):
        cand = standardize_phone(
            s1, country=country, default_country=default_country, address_context=addr_ctx
        )
        if cand.is_valid:
            return cand, "", s2 or None

    if s1:
        match = _EMBEDDED_PHONE_LABEL_RE.search(s1)
        if match:
            cand = standardize_phone(
                match.group(1),
                country=country,
                default_country=default_country,
                address_context=addr_ctx,
            )
            if cand.is_valid:
                cleaned_s1 = s1[: match.start()].strip(" ,;|/-")
                return cand, cleaned_s1, s2 or None

    if s2:
        if _PURE_PHONE_IN_STREET_RE.match(s2):
            cand = standardize_phone(
                s2, country=country, default_country=default_country, address_context=addr_ctx
            )
            if cand.is_valid:
                return cand, s1 or None, ""
        match2 = _EMBEDDED_PHONE_LABEL_RE.search(s2)
        if match2:
            cand = standardize_phone(
                match2.group(1),
                country=country,
                default_country=default_country,
                address_context=addr_ctx,
            )
            if cand.is_valid:
                cleaned_s2 = s2[: match2.start()].strip(" ,;|/-")
                return cand, s1 or None, cleaned_s2

    return None, street1, street2


def standardize_contact(
    *,
    street1: str | None = None,
    street2: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    phone: str | None = None,
    fax: str | None = None,
    organization: str | None = None,
    company: str | None = None,
    person_name: str | None = None,
    name: str | None = None,
    job_title: str | None = None,
    title: str | None = None,
    email: str | None = None,
    website: str | None = None,
    url: str | None = None,
    social: str | None = None,
    default_country: str = "US",
    allow_locality: bool = True,
) -> StandardizedContact:
    """Standardize an entity's address, phone, organization, person, title, and web pillars with cross-healing."""
    cross_actions: list[str] = []

    eff_s1 = street1
    eff_s2 = street2
    eff_org = organization if organization is not None else company
    eff_person = person_name if person_name is not None else name
    eff_title = job_title if job_title is not None else title
    eff_email = email
    eff_website = website if website is not None else url
    eff_social = social

    # A. Standardize or rescue Email
    email_res: StandardizedEmail | None = None
    if eff_email is not None and str(eff_email).strip():
        cand_email = standardize_email(eff_email)
        if cand_email.is_valid:
            email_res = cand_email

    if email_res is None:
        for field_name, field_val in (
            ("street1", eff_s1),
            ("street2", eff_s2),
            ("organization", eff_org),
            ("person_name", eff_person),
        ):
            rescued_email, cleaned_val = _try_rescue_email_from_text(
                field_val, allow_display_name=(field_name == "person_name")
            )
            if rescued_email is not None:
                email_res = rescued_email
                if field_name == "street1":
                    eff_s1 = cleaned_val or ""
                elif field_name == "street2":
                    eff_s2 = cleaned_val
                elif field_name == "organization":
                    eff_org = cleaned_val
                else:
                    eff_person = cleaned_val
                cross_actions.append(CrossHealingAction.EMAIL_RESCUED_FROM_FIELD.value)
                break

    # B. Standardize or rescue Website URL
    website_res: StandardizedUrl | None = None
    if eff_website is not None and str(eff_website).strip():
        cand_web = standardize_url(eff_website)
        if cand_web.is_valid:
            website_res = cand_web

    if website_res is None:
        rescued_web, new_s1_url, new_s2_url = _try_rescue_url_from_street(eff_s1, eff_s2)
        if rescued_web is not None:
            website_res = rescued_web
            eff_s1 = new_s1_url
            eff_s2 = new_s2_url
            cross_actions.append(CrossHealingAction.URL_RESCUED_FROM_FIELD.value)

    # C. Standardize Organization, Person, Job Title, and Social pillars
    org_res: StandardizedCompany | None = None
    if eff_org is not None and str(eff_org).strip():
        cand_org = standardize_company(eff_org, country=country)
        if cand_org.is_valid:
            org_res = cand_org

    person_res: StandardizedPerson | None = None
    additional_persons: tuple[StandardizedPerson, ...] = ()
    if eff_person is not None and str(eff_person).strip():
        split_pers = split_compound_persons(eff_person)
        if len(split_pers) > 1 and split_pers[0].is_valid:
            person_res = split_pers[0]
            additional_persons = tuple(split_pers[1:])
            cross_actions.append(CrossHealingAction.COMPOUND_PERSON_SPLIT.value)
        else:
            cand_per = split_pers[0]
            if cand_per.is_valid:
                person_res = cand_per
            elif cand_per.is_organization and org_res is None:
                org_res = standardize_company(eff_person, country=country)
                cross_actions.append(
                    CrossHealingAction.ORGANIZATION_RESCUED_FROM_PERSON_FIELD.value
                )

    title_res: StandardizedJobTitle | None = None
    if eff_title is not None and str(eff_title).strip():
        cand_title = standardize_job_title(eff_title)
        if cand_title.is_valid:
            title_res = cand_title

    social_res: StandardizedSocial | None = None
    if eff_social is not None and str(eff_social).strip():
        cand_soc = standardize_social(eff_social)
        if cand_soc.is_valid:
            social_res = cand_soc

    # D. Determine whether entity pillars provide an unambiguous country signal
    pillar_country_iso2: str | None = (
        (org_res.inferred_country_iso2 if org_res and org_res.inferred_country_iso2 else None)
        or (email_res.inferred_country_iso2 if email_res and email_res.inferred_country_iso2 else None)
        or (website_res.inferred_country_iso2 if website_res and website_res.inferred_country_iso2 else None)
    )

    raw_ctx = {
        "country": country,
        "state": state,
        "city": city,
        "postal_code": postal_code,
    }

    phone_res = standardize_phone(
        phone,
        country=country,
        default_country=default_country,
        address_context=raw_ctx,
    )

    inferred_country_from_pillars = False

    # 1. Rescue misplaced phone numbers from street1 / street2 when phone is missing/invalid
    if not phone_res.is_valid:
        rescued, new_s1, new_s2 = _try_rescue_phone_from_street(
            eff_s1, eff_s2, country, default_country, raw_ctx
        )
        if (
            rescued is None
            and (country is None or not str(country).strip())
            and pillar_country_iso2 is not None
        ):
            rescued, new_s1, new_s2 = _try_rescue_phone_from_street(
                eff_s1,
                eff_s2,
                pillar_country_iso2,
                pillar_country_iso2,
                {**raw_ctx, "country": pillar_country_iso2},
            )
            if rescued is not None:
                inferred_country_from_pillars = True
        if rescued is not None:
            phone_res = rescued
            eff_s1 = new_s1
            eff_s2 = new_s2
            cross_actions.append(CrossHealingAction.PHONE_RESCUED_FROM_ADDRESS_FIELD.value)

    # 2. Standardize address (inferring country from phone or entity pillars if country was omitted)
    has_address_input = any(
        v is not None and str(v).strip()
        for v in (eff_s1, eff_s2, city, state, postal_code)
    )
    default_iso2 = normalize_country_iso2(default_country) or "US"
    eff_country = country
    inferred_country_from_phone = False
    phone_raw_str = (phone or (phone_res.raw_input if phone_res.is_valid else "") or "").strip()
    phone_has_explicit_idd = phone_raw_str.startswith("+") or phone_raw_str.startswith("00")

    if country is None or not str(country).strip():
        probed_iso2: str | None = None
        if has_address_input:
            probed_country = normalize_country_code(
                "__PROBE__",
                state or "",
                postal_code or "",
                raw_street=eff_s1 or "",
                city_raw=city or "",
            )
            probed_iso2 = (
                normalize_country_iso2(probed_country)
                if probed_country != "ZZZ"
                else _extract_address_hint(raw_ctx)[0]
            )
            if probed_iso2 is None and eff_s1:
                m_us_zip = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", eff_s1)
                if m_us_zip:
                    from entity_standardizer.address.reference._match import name_tokens
                    from entity_standardizer.address.reference.us_zip5 import get_default_us_zip5_provider

                    places = get_default_us_zip5_provider().lookup_postal("US", m_us_zip.group(1))
                    if places:
                        place_tokens = {name_tokens(p.place_name) for p in places}
                        before_zip = eff_s1[: m_us_zip.start()].rstrip(" ,")
                        tokens = before_zip.split()
                        cand_cities = (
                            [before_zip.rsplit(",", 1)[1].strip()]
                            if "," in before_zip
                            else [" ".join(tokens[-n:]) for n in (4, 3, 2, 1) if len(tokens) >= n + 2]
                        )
                        if any(name_tokens(c) in place_tokens for c in cand_cities):
                            probed_iso2 = "US"

        if (
            pillar_country_iso2 is not None
            and not phone_has_explicit_idd
            and probed_iso2 in (None, pillar_country_iso2)
            and (has_address_input or bool(phone_raw_str))
        ):
            eff_country = pillar_country_iso2
            inferred_country_from_pillars = True
            if phone_raw_str:
                pillar_ctx = {
                    "country": pillar_country_iso2,
                    "state": state,
                    "city": city,
                    "postal_code": postal_code,
                }
                re_pillar_phone = standardize_phone(
                    phone_raw_str,
                    country=pillar_country_iso2,
                    default_country=pillar_country_iso2,
                    address_context=pillar_ctx,
                )
                if re_pillar_phone.is_valid:
                    phone_res = re_pillar_phone
        elif has_address_input:
            if (
                phone_res.is_valid
                and phone_res.country_iso2
                and PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in phone_res.risk_flags
                and probed_iso2 in (None, phone_res.country_iso2)
            ):
                if phone_res.country_iso2 != default_iso2:
                    eff_country = phone_res.country_iso2
                    inferred_country_from_phone = True
                else:
                    eff_country = default_iso2 if default_iso2 != "US" else eff_country
            else:
                eff_country = (
                    default_iso2
                    if (default_iso2 != "US" and probed_iso2 is None)
                    else eff_country
                )

    addr_res = standardize_address(
        street1=eff_s1,
        street2=eff_s2,
        city=city,
        state=state,
        postal_code=postal_code,
        country=eff_country,
        allow_locality=allow_locality,
    )
    has_valid_addr = has_address_input and addr_res.address_status != "parse_failed"
    if inferred_country_from_pillars and (has_valid_addr or phone_res.is_valid):
        cross_actions.append(CrossHealingAction.COUNTRY_INFERRED_FROM_ENTITY_PILLARS.value)
    if inferred_country_from_phone and has_valid_addr:
        cross_actions.append(CrossHealingAction.ADDRESS_COUNTRY_INFERRED_FROM_PHONE.value)

    # 3. Use Phone NPA region to break tie on US Address ERR_ZIP_STATE_MISMATCH or infer missing state
    if (
        has_valid_addr
        and addr_res.is_us
        and phone_res.is_valid
        and phone_res.country_iso2 == "US"
        and phone_res.region_code
    ):
        phone_st = phone_res.region_code
        if "ERR_ZIP_STATE_MISMATCH" in addr_res.failure_reason_codes:
            zip_st = get_state_from_zip3(addr_res.postal_code[:3])
            if zip_st == phone_st:
                addr_res = standardize_address(
                    street1=eff_s1,
                    street2=eff_s2,
                    city=city,
                    state=phone_st,
                    postal_code=postal_code,
                    country="US",
                    allow_locality=allow_locality,
                )
                cross_actions.append(CrossHealingAction.ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA.value)
        elif not addr_res.state and not addr_res.postal_code:
            from entity_standardizer.address.reference.us_zip5 import get_default_us_zip5_provider

            city_to_check = addr_res.city or (city or "").strip()
            if not city_to_check or get_default_us_zip5_provider().lookup_place("US", city_to_check, phone_st):
                addr_res = standardize_address(
                    street1=eff_s1,
                    street2=eff_s2,
                    city=city_to_check or city,
                    state=phone_st,
                    postal_code=postal_code,
                    country="US",
                    allow_locality=allow_locality,
                )
                cross_actions.append(CrossHealingAction.ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA.value)

    # 4. Feed standardized address context back into phone standardization
    addr_country = (
        addr_res.country
        if has_valid_addr and addr_res.country and addr_res.country != "ZZZ"
        else eff_country
    )
    std_ctx = (
        {
            "country": addr_country,
            "state": addr_res.state or state,
            "city": addr_res.city or city,
            "postal_code": addr_res.postal_code or postal_code,
        }
        if has_valid_addr
        else raw_ctx
    )
    if has_valid_addr:
        active_phone = (
            phone
            if (phone and str(phone).strip())
            else (phone_res.raw_input if phone_res.is_valid else None)
        )
        if active_phone:
            re_phone = standardize_phone(
                active_phone,
                country=eff_country,
                default_country=default_country,
                address_context=std_ctx,
            )
            std_country_iso2 = normalize_country_iso2(addr_country) if addr_country else None
            healed_phone = (
                not phone_res.is_valid
                or re_phone.confidence > phone_res.confidence
                or (phone_res.region_code is None and re_phone.region_code is not None)
                or (
                    std_country_iso2 is not None
                    and re_phone.country_iso2 == std_country_iso2
                    and re_phone.country_iso2 != phone_res.country_iso2
                )
            )
            mismatch_detected = (
                PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in re_phone.risk_flags
                and PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH not in phone_res.risk_flags
            )
            if re_phone.is_valid and (healed_phone or mismatch_detected):
                if healed_phone:
                    cross_actions.append(
                        CrossHealingAction.PHONE_HEALED_FROM_STANDARDIZED_ADDRESS.value
                    )
                phone_res = re_phone
        if not phone_res.is_valid:
            m_s1 = _EMBEDDED_PHONE_LABEL_RE.search(eff_s1) if eff_s1 else None
            probe_addr = (
                standardize_address(
                    street1=eff_s1[: m_s1.start()].strip(" ,;|/-"),
                    street2=eff_s2,
                    city=city,
                    state=state,
                    postal_code=postal_code,
                    country=eff_country,
                    allow_locality=allow_locality,
                )
                if m_s1 is not None
                else addr_res
            )
            probe_ctx = {
                "country": (
                    probe_addr.country
                    if probe_addr.country and probe_addr.country != "ZZZ"
                    else eff_country
                ),
                "state": probe_addr.state or state,
                "city": probe_addr.city or city,
                "postal_code": probe_addr.postal_code or postal_code,
            }
            rescued2, new_s1, new_s2 = _try_rescue_phone_from_street(
                eff_s1, eff_s2, eff_country, default_country, probe_ctx
            )
            if rescued2 is not None:
                phone_res = rescued2
                eff_s1 = new_s1
                eff_s2 = new_s2
                cross_actions.append(
                    CrossHealingAction.PHONE_RESCUED_FROM_ADDRESS_FIELD.value
                )
                cross_actions.append(
                    CrossHealingAction.PHONE_HEALED_FROM_STANDARDIZED_ADDRESS.value
                )
                addr_res = standardize_address(
                    street1=eff_s1,
                    street2=eff_s2,
                    city=city,
                    state=state,
                    postal_code=postal_code,
                    country=eff_country,
                    allow_locality=allow_locality,
                )
                std_ctx = {
                    "country": (
                        addr_res.country
                        if addr_res.country and addr_res.country != "ZZZ"
                        else eff_country
                    ),
                    "state": addr_res.state or state,
                    "city": addr_res.city or city,
                    "postal_code": addr_res.postal_code or postal_code,
                }

    # 5. Rescue Person from Address care_of or Email display_name / corporate local-part
    if person_res is None:
        if addr_res.care_of:
            co_comp = standardize_company(addr_res.care_of)
            co_words = set(re.findall(r"[A-Za-z]+", addr_res.care_of.upper()))
            if co_comp.legal_suffix is None and not (co_words & _CORPORATE_CARE_OF_WORDS):
                cand_p = standardize_person(addr_res.care_of)
                if cand_p.is_valid and cand_p.first_name and cand_p.last_name:
                    person_res = cand_p
                    cross_actions.append(
                        CrossHealingAction.PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF.value
                    )
        if person_res is None and email_res is not None and email_res.is_valid:
            if email_res.display_name:
                cand_p = standardize_person(email_res.display_name)
                if cand_p.is_valid:
                    person_res = cand_p
                    cross_actions.append(
                        CrossHealingAction.PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF.value
                    )
            elif not email_res.is_role_account and not email_res.is_disposable and email_res.raw_local_part:
                local_base = email_res.raw_local_part.split("+", 1)[0]
                if "." in local_base or "_" in local_base:
                    parts = [p for p in re.split(r"[._]+", local_base) if p]
                    if (
                        2 <= len(parts) <= 3
                        and all(p.isalpha() for p in parts)
                        and len(parts[0]) >= 2
                        and len(parts[-1]) >= 2
                    ):
                        person_res = standardize_person(" ".join(parts))
                        cross_actions.append(
                            CrossHealingAction.PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF.value
                        )

    # 6. Email <-> Website domain alignment and Organization inference from domain
    if (
        email_res is not None
        and email_res.is_valid
        and not email_res.is_free_provider
        and not email_res.is_disposable
        and email_res.domain
        and website_res is not None
        and website_res.is_valid
        and website_res.domain
    ):
        email_reg_domain, _, _, _ = extract_registrable_domain(email_res.domain)
        if (email_reg_domain or email_res.domain) == website_res.domain:
            cross_actions.append(CrossHealingAction.EMAIL_WEBSITE_DOMAIN_MATCH.value)
        else:
            cross_actions.append(CrossHealingAction.EMAIL_WEBSITE_DOMAIN_MISMATCH.value)

    if org_res is None:
        if (
            website_res is not None
            and website_res.is_valid
            and website_res.brand_stem
            and website_res.domain not in _FREE_WEBMAIL_DOMAINS
        ):
            org_res = standardize_company(
                website_res.brand_stem, country=website_res.inferred_country_iso2
            )
            cross_actions.append(CrossHealingAction.ORGANIZATION_INFERRED_FROM_DOMAIN.value)
        elif (
            email_res is not None
            and email_res.is_valid
            and not email_res.is_free_provider
            and not email_res.is_disposable
            and email_res.domain
        ):
            _, _, _, email_brand = extract_registrable_domain(email_res.domain)
            brand_cand = email_brand or email_res.domain.split(".")[0].upper()
            org_res = standardize_company(
                brand_cand, country=email_res.inferred_country_iso2
            )
            cross_actions.append(
                CrossHealingAction.ORGANIZATION_INFERRED_FROM_DOMAIN.value
            )

    fax_res: StandardizedPhone | None = None
    if fax is not None and str(fax).strip():
        fax_res = standardize_phone(
            fax,
            country=eff_country,
            default_country=default_country,
            address_context=std_ctx,
        )

    addr_key = addr_res.building_key or addr_res.normalized_address_key or ""
    phone_key = phone_res.e164 or ""
    extra_keys = [
        k
        for k in (
            org_res.company_key if org_res else None,
            person_res.person_root_key if person_res else None,
            email_res.email_key if email_res else None,
            website_res.domain if website_res else None,
        )
        if k
    ]
    if extra_keys:
        base_part = f"{addr_key}||{phone_key}" if (addr_key or phone_key) else ""
        entity_key = "||".join([p for p in (base_part, *extra_keys) if p])
    else:
        entity_key = f"{addr_key}||{phone_key}" if (addr_key or phone_key) else None

    addr_conf = float(addr_res.confidence_score or 0.0)
    if addr_conf > 0 and phone_res.is_valid:
        base_conf = round(0.55 * addr_conf + 0.45 * phone_res.confidence, 4)
    elif addr_conf > 0:
        base_conf = round(addr_conf, 4)
    else:
        base_conf = round(phone_res.confidence, 4)

    extra_confs = [
        p.confidence
        for p in (org_res, person_res, title_res, email_res, website_res, social_res)
        if p is not None and p.is_valid
    ]
    if extra_confs:
        avg_extra = sum(extra_confs) / len(extra_confs)
        overall_conf = round(0.5 * base_conf + 0.5 * avg_extra, 4) if base_conf > 0 else round(avg_extra, 4)
    else:
        overall_conf = base_conf

    return StandardizedContact(
        address=addr_res,
        phone=phone_res,
        fax=fax_res,
        organization=org_res,
        person=person_res,
        additional_persons=additional_persons,
        job_title=title_res,
        email=email_res,
        website=website_res,
        social=social_res,
        entity_key=entity_key,
        cross_healing_actions=cross_actions,
        overall_confidence=overall_conf,
    )


standardize_entity = standardize_contact


def batch_standardize_contacts(
    records: Iterable[dict[str, Any]],
    default_country: str = "US",
    allow_locality: bool = True,
) -> list[StandardizedContact]:
    """Batch-standardize an iterable of contact/entity dictionaries with cross-healing."""
    results: list[StandardizedContact] = []
    for row in records:
        results.append(
            standardize_contact(
                street1=row.get("street1") or row.get("address") or row.get("street"),
                street2=row.get("street2") or row.get("suite"),
                city=row.get("city"),
                state=row.get("state") or row.get("region"),
                postal_code=row.get("postal_code") or row.get("zip") or row.get("postcode"),
                country=row.get("country"),
                phone=row.get("phone") or row.get("telephone"),
                fax=row.get("fax"),
                organization=row.get("organization") or row.get("company"),
                person_name=row.get("person_name") or row.get("name"),
                job_title=row.get("job_title") or row.get("title"),
                email=row.get("email"),
                website=row.get("website") or row.get("url"),
                social=row.get("social"),
                default_country=default_country,
                allow_locality=allow_locality,
            )
        )
    return results


batch_standardize_entities = batch_standardize_contacts


@dataclass(slots=True)
class ContactComparisonResult:
    """Result of comparing two multi-pillar contact/entity records."""

    is_match: bool
    score: float
    match_type: str
    matched_pillars: list[str]
    pillar_scores: dict[str, float]
    contact_a: StandardizedContact
    contact_b: StandardizedContact

    def to_dict(self) -> dict[str, Any]:
        """Serialize the multi-pillar contact comparison result to a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "matched_pillars": list(self.matched_pillars),
            "pillar_scores": {k: round(v, 4) for k, v in self.pillar_scores.items()},
            "contact_a": self.contact_a.to_dict(),
            "contact_b": self.contact_b.to_dict(),
        }


def _coerce_contact(
    contact: StandardizedContact | dict[str, Any],
    default_country: str = "US",
) -> StandardizedContact:
    if isinstance(contact, StandardizedContact):
        return contact
    return batch_standardize_contacts([contact], default_country=default_country)[0]


def compare_contacts(
    contact_a: StandardizedContact | dict[str, Any],
    contact_b: StandardizedContact | dict[str, Any],
    *,
    default_country: str = "US",
) -> ContactComparisonResult:
    """Compare two contact/entity records across organization, person, phone, email, website, and address pillars."""
    from entity_standardizer.dedup import compare_phones

    ca = _coerce_contact(contact_a, default_country=default_country)
    cb = _coerce_contact(contact_b, default_country=default_country)

    matched_pillars: list[str] = []
    pillar_scores: dict[str, float] = {}
    person_conflict = False

    if (
        ca.organization is not None
        and cb.organization is not None
        and ca.organization.is_valid
        and cb.organization.is_valid
    ):
        org_cmp = compare_companies(ca.organization, cb.organization)
        pillar_scores["organization"] = org_cmp.score
        if org_cmp.is_match:
            matched_pillars.append("organization")

    if (
        ca.person is not None
        and cb.person is not None
        and ca.person.is_valid
        and cb.person.is_valid
    ):
        per_cmp = compare_persons(ca.person, cb.person)
        pillar_scores["person"] = per_cmp.score
        if per_cmp.is_match:
            matched_pillars.append("person")
        elif per_cmp.match_type == "GENERATIONAL_SUFFIX_CONFLICT":
            person_conflict = True

    if ca.phone.is_valid and cb.phone.is_valid:
        ph_cmp = compare_phones(ca.phone, cb.phone)
        pillar_scores["phone"] = ph_cmp.similarity_score
        if ph_cmp.is_exact_match or ph_cmp.is_extension_variant or ph_cmp.is_fuzzy_match:
            matched_pillars.append("phone")

    if (
        ca.email is not None
        and cb.email is not None
        and ca.email.is_valid
        and cb.email.is_valid
    ):
        em_cmp = compare_emails(ca.email, cb.email)
        pillar_scores["email"] = em_cmp.score
        if em_cmp.is_match:
            matched_pillars.append("email")

    if (
        ca.website is not None
        and cb.website is not None
        and ca.website.is_valid
        and cb.website.is_valid
    ):
        web_cmp = compare_urls(ca.website, cb.website)
        pillar_scores["website"] = web_cmp.score
        if web_cmp.is_match:
            matched_pillars.append("website")

    addr_a_key = ca.address.normalized_address_key or ca.address.building_key
    addr_b_key = cb.address.normalized_address_key or cb.address.building_key
    if (
        ca.address.address_status != "parse_failed"
        and cb.address.address_status != "parse_failed"
        and addr_a_key
        and addr_b_key
    ):
        if (
            ca.address.normalized_address_key
            and ca.address.normalized_address_key == cb.address.normalized_address_key
        ):
            pillar_scores["address"] = 1.0
            matched_pillars.append("address")
        elif ca.address.building_key and ca.address.building_key == cb.address.building_key:
            pillar_scores["address"] = 0.92
            matched_pillars.append("address")
        else:
            pillar_scores["address"] = 0.0

    if not pillar_scores:
        return ContactComparisonResult(
            is_match=False,
            score=0.0,
            match_type="INSUFFICIENT_PILLARS",
            matched_pillars=[],
            pillar_scores={},
            contact_a=ca,
            contact_b=cb,
        )

    if person_conflict:
        return ContactComparisonResult(
            is_match=False,
            score=0.45,
            match_type="PERSON_GENERATIONAL_CONFLICT",
            matched_pillars=matched_pillars,
            pillar_scores=pillar_scores,
            contact_a=ca,
            contact_b=cb,
        )

    if matched_pillars:
        best = max(pillar_scores[p] for p in matched_pillars)
        bonus = min(0.08, 0.03 * (len(matched_pillars) - 1))
        score = round(min(1.0, best + bonus), 4)
        match_type = (
            "MULTI_PILLAR_MATCH"
            if len(matched_pillars) >= 2
            else f"SINGLE_PILLAR_{matched_pillars[0].upper()}_MATCH"
        )
        return ContactComparisonResult(
            is_match=True,
            score=score,
            match_type=match_type,
            matched_pillars=matched_pillars,
            pillar_scores=pillar_scores,
            contact_a=ca,
            contact_b=cb,
        )

    return ContactComparisonResult(
        is_match=False,
        score=round(max(pillar_scores.values()), 4),
        match_type="NO_MATCH",
        matched_pillars=[],
        pillar_scores=pillar_scores,
        contact_a=ca,
        contact_b=cb,
    )


compare_entities = compare_contacts


