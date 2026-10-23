"""Joint Phone + Address entity standardization and bidirectional cross-healing engine."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any

from address_standardizer.models import StandardizedAddress
from address_standardizer.normalization import normalize_country_code
from address_standardizer.standardizer import get_state_from_zip3, standardize_address
from phone_standardizer.models import PhoneRiskFlag, StandardizedPhone
from phone_standardizer.registry import normalize_country_iso2
from phone_standardizer.standardizer import _extract_address_hint, standardize_phone

_EMBEDDED_PHONE_LABEL_RE = re.compile(
    r"(?:[,;|/\-]|\b(?:TEL|TELEPHONE|PHONE|PH|MOBILE|CELL|CALL)\b)[:.\s]*([+()\d][\d\s().\-]{6,22})$",
    re.IGNORECASE,
)
_PURE_PHONE_IN_STREET_RE = re.compile(r"^\s*\+?[\d()\s.\-]{7,22}\s*$")
_ALPHA_RE = re.compile(r"[A-Za-z]")


class CrossHealingAction(StrEnum):
    """Audit trail flag recorded when Phone and Address signals heal each other."""

    PHONE_RESCUED_FROM_ADDRESS_FIELD = "PHONE_RESCUED_FROM_ADDRESS_FIELD"
    ADDRESS_COUNTRY_INFERRED_FROM_PHONE = "ADDRESS_COUNTRY_INFERRED_FROM_PHONE"
    ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA = "ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA"
    PHONE_HEALED_FROM_STANDARDIZED_ADDRESS = "PHONE_HEALED_FROM_STANDARDIZED_ADDRESS"


@dataclass(slots=True)
class StandardizedContact:
    """Unified standardized representation of a physical address and telephone contact."""

    address: StandardizedAddress
    phone: StandardizedPhone
    fax: StandardizedPhone | None = None
    entity_key: str | None = None
    cross_healing_actions: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the joint contact record into a JSON-compatible dictionary."""
        return {
            "address": self.address.as_dict(),
            "phone": self.phone.to_dict(),
            "fax": self.fax.to_dict() if self.fax is not None else None,
            "entity_key": self.entity_key,
            "cross_healing_actions": list(self.cross_healing_actions),
            "overall_confidence": round(self.overall_confidence, 4),
        }


StandardizedEntity = StandardizedContact


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

    if s1 and not _ALPHA_RE.search(s1) and _PURE_PHONE_IN_STREET_RE.match(s1):
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
        if not _ALPHA_RE.search(s2) and _PURE_PHONE_IN_STREET_RE.match(s2):
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
    default_country: str = "US",
    allow_locality: bool = True,
) -> StandardizedContact:
    """Standardize an entity's address and telephone fields with bidirectional cross-healing."""
    cross_actions: list[str] = []
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

    eff_s1 = street1
    eff_s2 = street2

    # 1. Rescue misplaced phone numbers from street1 / street2 when phone is missing/invalid
    if not phone_res.is_valid:
        rescued, new_s1, new_s2 = _try_rescue_phone_from_street(
            eff_s1, eff_s2, country, default_country, raw_ctx
        )
        if rescued is not None:
            phone_res = rescued
            eff_s1 = new_s1
            eff_s2 = new_s2
            cross_actions.append(CrossHealingAction.PHONE_RESCUED_FROM_ADDRESS_FIELD.value)

    # 2. Standardize address (inferring country from phone if country was omitted and phone is explicit)
    has_address_input = any(
        v is not None and str(v).strip()
        for v in (eff_s1, eff_s2, city, state, postal_code)
    )
    default_iso2 = normalize_country_iso2(default_country) or "US"
    eff_country = country
    inferred_country_from_phone = False
    if has_address_input and (country is None or not str(country).strip()):
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
                from address_standardizer.reference._match import name_tokens
                from address_standardizer.reference.us_zip5 import get_default_us_zip5_provider

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
    if inferred_country_from_phone and has_valid_addr:
        cross_actions.append(CrossHealingAction.ADDRESS_COUNTRY_INFERRED_FROM_PHONE.value)

    # 3. Use Phone NPA region to break tie on US Address ERR_ZIP_STATE_MISMATCH
    if (
        addr_res.is_us
        and "ERR_ZIP_STATE_MISMATCH" in addr_res.failure_reason_codes
        and phone_res.is_valid
        and phone_res.country_iso2 == "US"
        and phone_res.region_code
    ):
        phone_st = phone_res.region_code
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

    # 4. Feed standardized address context back into phone standardization
    addr_country = (
        addr_res.country
        if has_valid_addr and addr_res.country and addr_res.country != "ZZZ"
        else country
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
                country=country,
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
                    else country
                ),
                "state": probe_addr.state or state,
                "city": probe_addr.city or city,
                "postal_code": probe_addr.postal_code or postal_code,
            }
            rescued2, new_s1, new_s2 = _try_rescue_phone_from_street(
                eff_s1, eff_s2, country, default_country, probe_ctx
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
                        else country
                    ),
                    "state": addr_res.state or state,
                    "city": addr_res.city or city,
                    "postal_code": addr_res.postal_code or postal_code,
                }

    fax_res: StandardizedPhone | None = None
    if fax is not None and str(fax).strip():
        fax_res = standardize_phone(
            fax,
            country=country,
            default_country=default_country,
            address_context=std_ctx,
        )

    addr_key = addr_res.building_key or addr_res.normalized_address_key or ""
    phone_key = phone_res.e164 or ""
    entity_key = f"{addr_key}||{phone_key}" if (addr_key or phone_key) else None

    addr_conf = float(addr_res.confidence_score or 0.0)
    if addr_conf > 0 and phone_res.is_valid:
        overall_conf = round(0.55 * addr_conf + 0.45 * phone_res.confidence, 4)
    elif addr_conf > 0:
        overall_conf = round(addr_conf, 4)
    else:
        overall_conf = round(phone_res.confidence, 4)

    return StandardizedContact(
        address=addr_res,
        phone=phone_res,
        fax=fax_res,
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
                default_country=default_country,
                allow_locality=allow_locality,
            )
        )
    return results


batch_standardize_entities = batch_standardize_contacts
