"""Core Global Phone Number Standardization, Formatting, and Line-Type Classification Engine."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from phone_standardizer.cache import get_default_cache, make_cache_key
from phone_standardizer.confidence import evaluate_confidence_and_risk
from phone_standardizer.models import (
    CountryDialPlan,
    HealingAction,
    PhoneLineType,
    PhoneRiskFlag,
    PhoneRoutingTier,
    StandardizedPhone,
)
from phone_standardizer.nanp import (
    NANP_EMERGENCY_CODES,
    NANP_PERSONAL_NPAS,
    NANP_PREMIUM_NPAS,
    NANP_SHORT_CODES,
    NANP_TOLL_FREE_NPAS,
    resolve_nanp_npa,
)
from phone_standardizer.normalization import (
    decode_vanity_phone,
    extract_extension,
    fold_unicode_digits,
    split_primary_phone,
)
from phone_standardizer.registry import (
    CountryDialRegistry,
    normalize_country_iso2,
)
from phone_standardizer.registry_data import EXTENDED_LINE_TYPE_PREFIXES

# Matches an explicit "(0)" redundant trunk indicator inside an international number
_PAREN_ZERO_TRUNK_RE = re.compile(r"\(\s*0\s*\)")
_PLUS_BEFORE_DIGIT_RE = re.compile(r"^(?:[^\d+]*|\s*011\s*)\+")
_CORRUPTED_NANP_HYPHEN_RE = re.compile(r"^\s*\d{3}\s*-\s*\d{3}\s*-")
_US_AND_TERRITORIES: frozenset[str] = frozenset({"US", "PR", "VI", "GU", "MP", "AS", "UM"})


def _extract_address_hint(address_context: Any) -> tuple[str | None, str | None]:
    """Extract (country_iso2, state) hints from a StandardizedAddress or dict (with postal code inference)."""
    if address_context is None:
        return None, None
    from phone_standardizer.dedup import infer_country_from_postal_code

    if isinstance(address_context, dict):
        raw_country = (
            address_context.get("country_iso2")
            or address_context.get("country_code")
            or address_context.get("country")
        )
        raw_state = address_context.get("state") or address_context.get("region")
        raw_postal = (
            address_context.get("postal_code")
            or address_context.get("zip_code")
            or address_context.get("zip")
            or address_context.get("postcode")
        )
        iso2 = normalize_country_iso2(str(raw_country)) if raw_country else None
        if not iso2 and raw_postal:
            iso2 = infer_country_from_postal_code(str(raw_postal))
        return iso2, (str(raw_state).strip().upper() if raw_state else None)

    raw_country = (
        getattr(address_context, "country_iso2", None)
        or getattr(address_context, "country_code", None)
        or getattr(address_context, "country", None)
    )
    raw_state = getattr(address_context, "state", None)
    raw_postal = (
        getattr(address_context, "postal_code", None)
        or getattr(address_context, "zip_code", None)
        or getattr(address_context, "zip", None)
        or getattr(address_context, "postcode", None)
    )
    iso2 = normalize_country_iso2(str(raw_country)) if raw_country else None
    if not iso2 and raw_postal:
        iso2 = infer_country_from_postal_code(str(raw_postal))
    return iso2, (str(raw_state).strip().upper() if raw_state else None)


def _classify_line_type(plan: CountryDialPlan, nsn: str) -> str:
    """Classify a National Significant Number into a PhoneLineType for the given dial plan."""
    ext_map = EXTENDED_LINE_TYPE_PREFIXES.get(plan.iso2)
    if plan.calling_code == "1":
        if len(nsn) == 7:
            return PhoneLineType.UAN
        npa = nsn[:3]
        if npa in NANP_TOLL_FREE_NPAS:
            return PhoneLineType.TOLL_FREE
        if npa in NANP_PREMIUM_NPAS:
            return PhoneLineType.PREMIUM_RATE
        if npa in NANP_PERSONAL_NPAS:
            return PhoneLineType.PERSONAL_NUMBER
        for ltype, prefs in (ext_map or {}).items():
            if nsn.startswith(prefs):
                return ltype
        return PhoneLineType.FIXED_LINE_OR_MOBILE

    if plan.iso2 == "CL" and len(nsn) == 10 and nsn.startswith("600"):
        return PhoneLineType.SHARED_COST
    if plan.iso2 == "IN" and nsn.startswith("74104"):
        return PhoneLineType.FIXED_LINE

    if plan.toll_free_prefixes and nsn.startswith(plan.toll_free_prefixes):
        return PhoneLineType.TOLL_FREE
    if plan.premium_prefixes and nsn.startswith(plan.premium_prefixes):
        return PhoneLineType.PREMIUM_RATE
    if plan.shared_cost_prefixes and nsn.startswith(plan.shared_cost_prefixes):
        return PhoneLineType.SHARED_COST
    if plan.voip_prefixes and nsn.startswith(plan.voip_prefixes):
        return PhoneLineType.VOIP
    for ltype, prefs in (ext_map or {}).items():
        if nsn.startswith(prefs):
            return ltype
    if (plan.mobile_prefixes and nsn.startswith(plan.mobile_prefixes)) or (
        plan.iso2 == "BR" and len(nsn) == 11 and nsn[2] == "9"
    ):
        return PhoneLineType.MOBILE

    # Special regional mobile rules (Mexico)
    if plan.iso2 == "MX" and len(nsn) == 10:
        return PhoneLineType.FIXED_LINE_OR_MOBILE

    return PhoneLineType.FIXED_LINE


def _split_area_and_subscriber(plan: CountryDialPlan, nsn: str) -> tuple[str | None, str | None]:
    """Split a National Significant Number into (area_code, subscriber_number)."""
    if not nsn:
        return None, None
    if plan.calling_code == "1" and len(nsn) == 10:
        return nsn[:3], nsn[3:]
    if plan.calling_code == "44":
        if nsn.startswith("2"):
            return nsn[:2], nsn[2:]
        if nsn.startswith(("11", "121", "131", "141", "151", "161", "191")):
            return nsn[:3], nsn[3:]
        return nsn[:4], nsn[4:]
    if plan.iso2 == "FR" and len(nsn) == 9:
        return nsn[:1], nsn[1:]
    if plan.iso2 in ("AU", "CH") and len(nsn) == 9:
        return nsn[:1] if plan.iso2 == "AU" else nsn[:2], nsn[1:] if plan.iso2 == "AU" else nsn[2:]
    if plan.iso2 == "JP" and len(nsn) in (9, 10):
        if nsn.startswith(("3", "6")):
            return nsn[:1], nsn[1:]
        if nsn.startswith(("70", "80", "90", "50")):
            return nsn[:2], nsn[2:]
        if nsn.startswith("120"):
            return nsn[:3], nsn[3:]
        return nsn[:2], nsn[2:]
    if plan.iso2 == "DE":
        if nsn.startswith(("30", "40", "69", "89")):
            return nsn[:2], nsn[2:]
        if nsn.startswith(("15", "16", "17", "800", "900")):
            return nsn[:3], nsn[3:]
        return nsn[:3], nsn[3:]
    if plan.iso2 == "AR" and len(nsn) == 11 and nsn.startswith("9"):
        if nsn.startswith("911"):
            return "11", nsn[3:]
        return nsn[1:4], nsn[4:]
    if plan.iso2 == "KR" and nsn.startswith("2"):
        return nsn[:1], nsn[1:]
    if plan.iso2 == "CN" and len(nsn) == 11 and nsn.startswith("1") and not nsn.startswith("10"):
        return nsn[:3], nsn[3:]
    if len(nsn) >= 6:
        return nsn[:2], nsn[2:]
    return None, nsn


def _format_numbers(
    plan: CountryDialPlan,
    nsn: str,
    extension: str | None,
) -> tuple[str, str, str, str]:
    """Return (e164, national, international, rfc3966) strings for a valid or possible NSN."""
    cc = plan.calling_code
    e164 = f"+{cc}{nsn}"

    if cc == "1" and len(nsn) == 10:
        npa, nxx, line = nsn[:3], nsn[3:6], nsn[6:]
        national = f"({npa}) {nxx}-{line}"
        international = f"+1 {npa}-{nxx}-{line}"
        rfc_body = f"+1-{npa}-{nxx}-{line}"
    elif cc == "44":
        if nsn.startswith("2") and len(nsn) == 10:
            g1, g2, g3 = nsn[:2], nsn[2:6], nsn[6:]
            national = f"0{g1} {g2} {g3}"
            international = f"+44 {g1} {g2} {g3}"
            rfc_body = f"+44-{g1}-{g2}-{g3}"
        elif nsn.startswith(("11", "121", "131", "141", "151", "161", "191")) and len(nsn) == 10:
            g1, g2, g3 = nsn[:3], nsn[3:6], nsn[6:]
            national = f"0{g1} {g2} {g3}"
            international = f"+44 {g1} {g2} {g3}"
            rfc_body = f"+44-{g1}-{g2}-{g3}"
        else:
            g1, g2 = nsn[:4], nsn[4:]
            national = f"0{g1} {g2}"
            international = f"+44 {g1} {g2}"
            rfc_body = f"+44-{g1}-{g2}"
    elif plan.iso2 == "FR" and len(nsn) == 9:
        groups = [nsn[0], nsn[1:3], nsn[3:5], nsn[5:7], nsn[7:9]]
        national = "0" + " ".join(groups)
        international = "+33 " + " ".join(groups)
        rfc_body = "+33-" + "-".join(groups)
    elif plan.iso2 == "DE":
        area, sub = _split_area_and_subscriber(plan, nsn)
        area_s = area or nsn[:3]
        sub_s = sub or nsn[3:]
        national = f"0{area_s} {sub_s}"
        international = f"+49 {area_s} {sub_s}"
        rfc_body = f"+49-{area_s}-{sub_s}"
    elif plan.iso2 == "JP" and len(nsn) in (9, 10):
        area, sub = _split_area_and_subscriber(plan, nsn)
        area_s = area or nsn[:2]
        sub_s = sub or nsn[2:]
        mid = len(sub_s) - 4
        g2, g3 = sub_s[:mid], sub_s[mid:]
        national = f"0{area_s}-{g2}-{g3}"
        international = f"+81 {area_s}-{g2}-{g3}"
        rfc_body = f"+81-{area_s}-{g2}-{g3}"
    elif plan.iso2 == "AU" and len(nsn) == 9:
        if nsn.startswith("4"):
            g1, g2, g3 = nsn[:3], nsn[3:6], nsn[6:]
            national = f"0{g1} {g2} {g3}"
            international = f"+61 {g1} {g2} {g3}"
            rfc_body = f"+61-{g1}-{g2}-{g3}"
        else:
            g1, g2, g3 = nsn[:1], nsn[1:5], nsn[5:]
            national = f"(0{g1}) {g2} {g3}"
            international = f"+61 {g1} {g2} {g3}"
            rfc_body = f"+61-{g1}-{g2}-{g3}"
    elif plan.iso2 == "AR" and len(nsn) == 11 and nsn.startswith("9"):
        area, sub = _split_area_and_subscriber(plan, nsn)
        assert area is not None and sub is not None
        g2, g3 = sub[:-4], sub[-4:]
        national = f"0{area} 15 {g2} {g3}"
        international = f"+54 9 {area} {g2} {g3}"
        rfc_body = f"+54-9-{area}-{g2}-{g3}"
    else:
        trunk = plan.national_trunk_prefix or ""
        area, sub = _split_area_and_subscriber(plan, nsn)
        if area and sub:
            g1, g2, g3 = area, sub[:-4], sub[-4:]
            parts = [p for p in (g1, g2, g3) if p]
            national = f"{trunk}{parts[0]} " + " ".join(parts[1:])
            international = f"+{cc} " + " ".join(parts)
            rfc_body = f"+{cc}-" + "-".join(parts)
        else:
            national = f"{trunk}{nsn}"
            international = f"+{cc} {nsn}"
            rfc_body = f"+{cc}-{nsn}"

    rfc3966 = f"tel:{rfc_body};ext={extension}" if extension else f"tel:{rfc_body}"
    return e164, national, international, rfc3966


def _is_valid_plan_or_legacy_length(plan: CountryDialPlan, length: int) -> bool:
    """Return True if length is in plan.nsn_lengths or is a healable regional legacy length."""
    if length in plan.nsn_lengths:
        return True
    if plan.iso2 == "CH" and length in (7, 8):
        return True
    if plan.iso2 == "AR" and length in (12, 13):
        return True
    if plan.iso2 == "MX" and length in (11, 12, 13):
        return True
    return bool(plan.iso2 == "BR" and length in (10, 13, 14))


def _is_domestic_prefix_collision(
    plan: CountryDialPlan,
    nsn: str,
    rem: str,
    cc_separated: bool,
) -> bool:
    """Return True if an NSN starting with plan.calling_code is a valid domestic number rather than a bare international prefix."""
    if plan.iso2 == "BR" and len(nsn) in (10, 11) and not rem.startswith(("300", "400", "500", "800", "900")):
        return True
    if cc_separated:
        return False
    if len(nsn) in plan.nsn_lengths and len(rem) < 6:
        return True
    if plan.iso2 == "IT" and len(nsn) in (9, 10) and not rem.startswith(("0", "8")):
        return True
    if plan.iso2 == "IN" and len(nsn) == 10 and not rem.startswith("1800"):
        return True
    return plan.iso2 in ("PL", "ZA", "NL", "PK", "VN") and len(nsn) in (9, 10)


def standardize_phone(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
    address_context: Any = None,
) -> StandardizedPhone:
    """Parse, clean, validate, and format a raw telephone number into a StandardizedPhone record."""
    if raw_phone is None or not str(raw_phone).strip():
        return StandardizedPhone(
            raw_input="" if raw_phone is None else str(raw_phone),
            risk_flags=(PhoneRiskFlag.INVALID_LENGTH,),
        )

    raw_str = str(raw_phone)
    addr_iso2, addr_state = _extract_address_hint(address_context)
    cache_key = make_cache_key(
        raw_str,
        country=country,
        default_country=default_country,
        addr_iso2=addr_iso2,
        addr_state=addr_state,
    )
    cache = get_default_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    healing_actions: list[str] = []
    extra_risk_flags: list[str] = []

    # 1. Fold non-ASCII Unicode digits and punctuation
    working, unicode_folded = fold_unicode_digits(raw_str)
    if unicode_folded:
        healing_actions.append(HealingAction.UNICODE_DIGITS_FOLDED)

    # 2. Split multi-number candidate strings before extension extraction
    working, was_split = split_primary_phone(working)
    if was_split:
        healing_actions.append(HealingAction.MULTI_NUMBER_PRIMARY_SELECTED)

    # 3. Extract trailing extension before vanity decoding
    working, extension = extract_extension(working)
    if extension:
        healing_actions.append(HealingAction.EXTENSION_EXTRACTED)

    # 4. Decode alphanumeric vanity letters (e.g. 1-800-FLOWERS)
    working, vanity_alias = decode_vanity_phone(working)
    if vanity_alias:
        healing_actions.append(HealingAction.VANITY_KEYPAD_DECODED)

    # 4. Determine country hints (explicit country parameter or address_context)
    explicit_iso2 = normalize_country_iso2(country) if country else None
    hint_iso2 = explicit_iso2 or addr_iso2
    if addr_iso2 and not explicit_iso2:
        healing_actions.append(HealingAction.COUNTRY_INFERRED_FROM_CONTEXT)
    fallback_iso2 = hint_iso2 or normalize_country_iso2(default_country) or "US"
    context_plan = CountryDialRegistry.get(fallback_iso2) or CountryDialRegistry.get("US")
    assert context_plan is not None

    # 5. Detect explicit "(0)" redundant trunk marker before stripping punctuation
    has_paren_zero = bool(_PAREN_ZERO_TRUNK_RE.search(working))
    working_no_paren_zero = _PAREN_ZERO_TRUNK_RE.sub("", working) if has_paren_zero else working

    # 6. Check for international prefix (+ or IDD exit prefix)
    trimmed = working.strip()
    has_leading_plus = bool(_PLUS_BEFORE_DIGIT_RE.match(trimmed))
    if has_leading_plus and re.match(r"^\s*011\s*\+", trimmed):
        trimmed = re.sub(r"^\s*011\s*", "", trimmed)
        working_no_paren_zero = re.sub(r"^\s*011\s*", "", working_no_paren_zero)
        healing_actions.append(HealingAction.IDD_EXIT_PREFIX_STRIPPED)
    digits_raw = "".join(ch for ch in trimmed if ch.isdigit())
    digits_no_paren = "".join(ch for ch in working_no_paren_zero if ch.isdigit())

    if not digits_raw:
        res_empty = StandardizedPhone(
            raw_input=raw_str,
            extension=extension,
            vanity_alias=vanity_alias,
            risk_flags=(PhoneRiskFlag.INVALID_LENGTH,),
            healing_actions=tuple(healing_actions),
        )
        cache.set(cache_key, res_empty)
        return res_empty

    # Check short / emergency codes (2-5 digits like 911, 988, 112, 999, 110, 119, 000, 15, 17, 18, 411)
    if (
        not has_leading_plus
        and (len(digits_raw) <= 3 or digits_raw in ("1444", "10111", "116111", "116123"))
        and len(digits_raw) not in context_plan.nsn_lengths
        and (digits_raw in NANP_SHORT_CODES or digits_raw in NANP_EMERGENCY_CODES)
    ):
        line_type = (
            PhoneLineType.SHORT_CODE
            if (digits_raw in NANP_SHORT_CODES and digits_raw not in ("911", "988"))
            else PhoneLineType.EMERGENCY
        )
        res_short = StandardizedPhone(
            raw_input=raw_str,
            e164=digits_raw,
            national=digits_raw,
            international=digits_raw,
            rfc3966=f"tel:{digits_raw}",
            country_calling_code=context_plan.calling_code,
            country_iso2=context_plan.iso2,
            country_iso3=context_plan.iso3,
            country_name=context_plan.name,
            national_significant_number=digits_raw,
            subscriber_number=digits_raw,
            region_code=addr_state,
            line_type=line_type,
            is_valid=True,
            is_possible=True,
            phone_key=digits_raw,
            phone_ext_key=digits_raw,
            confidence=1.0,
            routing_tier=PhoneRoutingTier.AUTO_PASS,
            healing_actions=tuple(healing_actions),
        )
        cache.set(cache_key, res_short)
        return res_short

    is_international = has_leading_plus
    intl_digits_raw = digits_raw
    intl_digits_no_paren = digits_no_paren

    if is_international and intl_digits_raw.startswith("00") and len(intl_digits_raw) >= 9 and intl_digits_raw[2] != "0":
        intl_digits_raw = intl_digits_raw[2:]
        intl_digits_no_paren = intl_digits_no_paren[2:]
        healing_actions.append(HealingAction.IDD_EXIT_PREFIX_STRIPPED)
    elif not is_international:
        # Check for IDD exit prefixes (context_plan.idd_prefix or ITU standard 00) when string is long enough
        idd_candidates = ("00",) if context_plan.idd_prefix == "00" else (context_plan.idd_prefix, "00")
        for idd in idd_candidates:
            if idd and digits_raw.startswith(idd) and len(digits_raw) - len(idd) >= 7:
                is_international = True
                intl_digits_raw = digits_raw[len(idd):]
                intl_digits_no_paren = digits_no_paren[len(idd):]
                healing_actions.append(HealingAction.IDD_EXIT_PREFIX_STRIPPED)
                break
        # Safe "011" IDD exit stripping on non-NANP context_plan when followed by context_plan.calling_code
        if (
            not is_international
            and context_plan.calling_code != "1"
            and digits_raw.startswith("011")
            and len(digits_raw) >= 10
            and (len(digits_raw) - 1) not in context_plan.nsn_lengths
            and digits_raw[3:].startswith(context_plan.calling_code)
        ):
            is_international = True
            intl_digits_raw = digits_raw[3:]
            intl_digits_no_paren = digits_no_paren[3:]
            healing_actions.append(HealingAction.IDD_EXIT_PREFIX_STRIPPED)

    region_code: str | None = None
    recognized_sub_area = True

    if is_international:
        matched_plan, nsn_candidate, resolved_region, recognized_sub_area = (
            CountryDialRegistry.match_calling_code(intl_digits_no_paren, hint_iso2=hint_iso2)
        )
        if matched_plan is None:
            res_unassigned = StandardizedPhone(
                raw_input=raw_str,
                extension=extension,
                vanity_alias=vanity_alias,
                risk_flags=(PhoneRiskFlag.UNASSIGNED_CALLING_CODE,),
                healing_actions=tuple(healing_actions),
            )
            cache.set(cache_key, res_unassigned)
            return res_unassigned
        if has_paren_zero and matched_plan.national_trunk_prefix == "0":
            plan = matched_plan
            nsn = nsn_candidate
            region_code = resolved_region
            healing_actions.append(HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED)
        else:
            matched_plan_raw, nsn_raw, resolved_region_raw, recognized_sub_area_raw = (
                CountryDialRegistry.match_calling_code(intl_digits_raw, hint_iso2=hint_iso2)
            )
            assert matched_plan_raw is not None
            plan = matched_plan_raw
            nsn = nsn_raw
            region_code = resolved_region_raw
            recognized_sub_area = recognized_sub_area_raw
    else:
        plan = context_plan
        if has_paren_zero and plan.national_trunk_prefix == "0":
            nsn = digits_no_paren
            healing_actions.append(HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED)
        else:
            nsn = digits_raw
        if plan.calling_code == "1":
            if len(nsn) == 12 and nsn.startswith("01"):
                nsn = nsn[2:]
                healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
            elif len(nsn) == 11:
                if nsn.startswith("1"):
                    nsn = nsn[1:]
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
                elif nsn.startswith("01") and resolve_nanp_npa(nsn[2:5])[2]:
                    # Heals off-by-one shifted leading zero '01-703-47-8020' -> '7034780200'
                    nsn = nsn[2:] + "0"
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
                elif nsn.startswith("0") and resolve_nanp_npa(nsn[1:4])[2]:
                    nsn = nsn[1:]
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
            if len(nsn) == 10:
                iso2_resolved, region_code, recognized_sub_area = resolve_nanp_npa(
                    nsn[:3], fallback_iso2=plan.iso2
                )
                plan = CountryDialRegistry.get(iso2_resolved) or plan
        else:
            cc = plan.calling_code
            trunk = plan.national_trunk_prefix
            # Heal bare leading country calling code (preventing +6565 / +352352 / +4949 doubling)
            if nsn.startswith(cc):
                rem = nsn[len(cc):]
                cc_separated = has_paren_zero or bool(
                    re.match(rf"^\s*\(?{re.escape(cc)}\)?[\s.\-()]", working)
                )
                if (
                    trunk in ("0", "06")
                    and rem.startswith(trunk)
                    and _is_valid_plan_or_legacy_length(plan, len(rem) - len(trunk))
                    and (
                        cc_separated
                        or len(nsn) not in plan.nsn_lengths
                        or not nsn.startswith(
                            plan.premium_prefixes + plan.toll_free_prefixes + plan.shared_cost_prefixes
                        )
                    )
                ):
                    nsn = rem[len(trunk):]
                    healing_actions.append(HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED)
                elif _is_valid_plan_or_legacy_length(plan, len(rem)):
                    if not _is_domestic_prefix_collision(plan, nsn, rem, cc_separated):
                        nsn = rem

            if plan.iso2 == "BY":
                if nsn.startswith("80") and len(nsn) == 11:
                    nsn = nsn[2:]
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
                elif nsn.startswith("0") and len(nsn) == 10:
                    nsn = nsn[1:]
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
                elif nsn.startswith("8") and (
                    (len(nsn) == 10 and not nsn.startswith(("800", "801", "803", "810", "820")))
                    or len(nsn) == 11
                ):
                    nsn = nsn[1:]
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
            elif plan.iso2 == "HU":
                if nsn.startswith("06") and (len(nsn) - 2) in plan.nsn_lengths:
                    nsn = nsn[2:]
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
                elif nsn.startswith("0") and (len(nsn) - 1) in plan.nsn_lengths:
                    nsn = nsn[1:]
                    healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
            elif plan.iso2 == "BR" and nsn.startswith("0") and len(nsn) in (13, 14):
                nsn = nsn[3:]
                healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
            elif trunk and nsn.startswith(trunk) and _is_valid_plan_or_legacy_length(
                plan, len(nsn) - len(trunk)
            ):
                nsn = nsn[len(trunk):]
                healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)

            # Re-verify UK Crown Dependencies if domestic 01534 / 01481 / 01624 used
            if plan.calling_code == "44":
                matched_plan, _, resolved_region, _ = CountryDialRegistry.match_calling_code(
                    "44" + nsn, hint_iso2=hint_iso2
                )
                assert matched_plan is not None
                plan = matched_plan
                region_code = resolved_region

        # Fallback bare international calling-code resolution when context_plan length does not match
        if not _is_valid_plan_or_legacy_length(plan, len(nsn)) or (
            has_paren_zero and plan.national_trunk_prefix != "0"
        ):
            cand_input = digits_no_paren if has_paren_zero else digits_raw
            cand_plan, cand_nsn, cand_reg, cand_sub = CountryDialRegistry.match_calling_code(
                cand_input, hint_iso2=hint_iso2
            )
            if cand_plan is not None and cand_plan.calling_code != "1":
                stripped_zero = has_paren_zero and cand_plan.national_trunk_prefix == "0"
                if (
                    cand_plan.national_trunk_prefix == "0"
                    and cand_nsn.startswith("0")
                    and _is_valid_plan_or_legacy_length(cand_plan, len(cand_nsn) - 1)
                ):
                    cand_nsn = cand_nsn[1:]
                    stripped_zero = True
                cc_cand = cand_plan.calling_code
                cc_sep = has_paren_zero or bool(
                    re.match(rf"^\s*\(?{re.escape(cc_cand)}\)?[\s.\-()]", working)
                )
                if (
                    _is_valid_plan_or_legacy_length(cand_plan, len(cand_nsn))
                    and len(cand_nsn) >= 7
                    and len(cc_cand) + len(cand_nsn) <= 15
                    and (
                        cc_sep
                        or (len(digits_raw) >= 12 and not _CORRUPTED_NANP_HYPHEN_RE.match(working))
                        or (
                            len(digits_raw) == 11
                            and not digits_raw.startswith("1")
                            and not _CORRUPTED_NANP_HYPHEN_RE.match(working)
                        )
                        or (hint_iso2 is None and not resolve_nanp_npa(digits_raw[:3])[2])
                    )
                ):
                    plan = cand_plan
                    nsn = cand_nsn
                    region_code = cand_reg
                    recognized_sub_area = cand_sub
                    if stripped_zero and HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED not in healing_actions:
                        healing_actions.append(HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED)

    # 7. Heal redundant international trunk prefix (e.g., +44 020 7946 0912 -> +44 20 7946 0912)
    trunk_p = plan.national_trunk_prefix
    if is_international and plan.iso2 == "BR" and nsn.startswith("0") and len(nsn) in (13, 14):
        nsn = nsn[3:]
        healing_actions.append(HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED)
    elif (
        is_international
        and trunk_p in ("0", "06")
        and nsn.startswith(trunk_p)
        and (
            (len(nsn) - len(trunk_p)) in plan.nsn_lengths
            or (plan.iso2 == "AR" and len(nsn) == 13)
        )
    ):
        nsn = nsn[len(trunk_p):]
        healing_actions.append(HealingAction.REDUNDANT_INTL_TRUNK_STRIPPED)
        if plan.calling_code == "44":
            matched_plan, _, resolved_region, _ = CountryDialRegistry.match_calling_code(
                "44" + nsn, hint_iso2=hint_iso2
            )
            assert matched_plan is not None
            plan = matched_plan
            region_code = resolved_region

    # 8. Regional Legacy Mobile Prefix Healing
    # Mexico (+52): heal legacy domestic 044/045/01 prefixes and deprecated international '+52 1' mobile prefix
    if plan.iso2 == "MX":
        if len(nsn) == 13 and nsn.startswith(("044", "045")):
            nsn = nsn[3:]
            healing_actions.append(HealingAction.LEGACY_MEXICO_MOBILE_1_STRIPPED)
        elif len(nsn) == 12 and nsn.startswith("01"):
            nsn = nsn[2:]
            healing_actions.append(HealingAction.NATIONAL_TRUNK_STRIPPED)
        elif len(nsn) == 11 and nsn.startswith("1"):
            nsn = nsn[1:]
            healing_actions.append(HealingAction.LEGACY_MEXICO_MOBILE_1_STRIPPED)

    # Argentina (+54): heal domestic '15' mobile prefix across 2- ('11'), 3-, and 4-digit area codes
    if plan.iso2 == "AR":
        if len(nsn) == 12 and not nsn.startswith("9"):
            if nsn.startswith("11") and nsn[2:4] == "15":
                nsn = "9" + nsn[:2] + nsn[4:]
                healing_actions.append(HealingAction.ARGENTINA_MOBILE_15_HEALED)
            elif nsn[3:5] == "15":
                nsn = "9" + nsn[:3] + nsn[5:]
                healing_actions.append(HealingAction.ARGENTINA_MOBILE_15_HEALED)
            elif nsn[4:6] == "15":
                nsn = "9" + nsn[:4] + nsn[6:]
                healing_actions.append(HealingAction.ARGENTINA_MOBILE_15_HEALED)
        elif len(nsn) == 13 and nsn.startswith("9"):
            if nsn[1:3] == "11" and nsn[3:5] == "15":
                nsn = nsn[:3] + nsn[5:]
                healing_actions.append(HealingAction.ARGENTINA_MOBILE_15_HEALED)
            elif nsn[4:6] == "15":
                nsn = nsn[:4] + nsn[6:]
                healing_actions.append(HealingAction.ARGENTINA_MOBILE_15_HEALED)
            elif nsn[5:7] == "15":  # pragma: no branch
                nsn = nsn[:5] + nsn[7:]
                healing_actions.append(HealingAction.ARGENTINA_MOBILE_15_HEALED)

    # Brazil (+55): heal legacy 10-digit mobile numbers (2-digit DDD + 8-digit mobile starting with 6-9) by inserting '9'
    if plan.iso2 == "BR" and len(nsn) == 10 and nsn[2] in "6789":
        nsn = nsn[:2] + "9" + nsn[2:]
        healing_actions.append(HealingAction.BRAZIL_MOBILE_9_INSERTED)

    # Check cross-field mismatch if explicit/address country hint conflicts with resolved jurisdiction
    # (Skip when country was the originating dial plan for an IDD exit prefix or US <-> US territory)
    if (
        hint_iso2
        and hint_iso2 != plan.iso2
        and not (hint_iso2 in _US_AND_TERRITORIES and plan.iso2 in _US_AND_TERRITORIES)
        and CountryDialRegistry.get(hint_iso2) is not None
        and HealingAction.IDD_EXIT_PREFIX_STRIPPED not in healing_actions
    ):
        extra_risk_flags.append(PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH)

    # 9. Validate length & structural rules
    is_possible = len(nsn) in plan.nsn_lengths and len(plan.calling_code) + len(nsn) <= 15
    is_valid = is_possible

    if not is_possible:
        extra_risk_flags.append(PhoneRiskFlag.INVALID_LENGTH)

    if plan.calling_code == "1" and len(nsn) == 10:
        npa = nsn[:3]
        nxx = nsn[3:6]
        if npa[0] in "01" or npa[1:] == "11" or npa == "555":
            is_valid = False
            extra_risk_flags.append(PhoneRiskFlag.INVALID_AREA_CODE)
        elif npa[1] == "9":
            extra_risk_flags.append(PhoneRiskFlag.INVALID_AREA_CODE)
        if nxx[0] in "01" or (nxx[1:] == "11" and npa not in NANP_TOLL_FREE_NPAS):
            is_valid = False
            extra_risk_flags.append(PhoneRiskFlag.INVALID_EXCHANGE)

    area_code, subscriber_number = _split_area_and_subscriber(plan, nsn)
    line_type = _classify_line_type(plan, nsn) if is_possible else PhoneLineType.UNKNOWN

    if is_possible:
        e164, national, international, rfc3966 = _format_numbers(plan, nsn, extension)
        phone_key = e164
        phone_ext_key = f"{e164}#{extension}" if extension else e164
    else:
        e164 = None
        national = None
        international = None
        rfc3966 = None
        phone_key = None
        phone_ext_key = None

    confidence, routing_tier, risk_flags = evaluate_confidence_and_risk(
        is_valid=is_valid,
        is_possible=is_possible,
        calling_code=plan.calling_code,
        nsn=nsn,
        subscriber=subscriber_number,
        line_type=line_type,
        recognized_sub_area=recognized_sub_area,
        healing_actions=healing_actions,
        extra_risk_flags=extra_risk_flags,
    )

    result = StandardizedPhone(
        raw_input=raw_str,
        e164=e164,
        national=national,
        international=international,
        rfc3966=rfc3966,
        country_calling_code=plan.calling_code,
        country_iso2=plan.iso2,
        country_iso3=plan.iso3,
        country_name=plan.name,
        national_significant_number=nsn,
        area_code=area_code,
        subscriber_number=subscriber_number,
        extension=extension,
        vanity_alias=vanity_alias,
        region_code=region_code or addr_state,
        line_type=line_type,
        is_valid=is_valid,
        is_possible=is_possible,
        phone_key=phone_key,
        phone_ext_key=phone_ext_key,
        confidence=confidence,
        routing_tier=routing_tier,
        risk_flags=risk_flags,
        healing_actions=tuple(healing_actions),
    )
    cache.set(cache_key, result)
    return result


def validate_phone(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
) -> bool:
    """Return True if raw_phone is a valid telephone number for the resolved country."""
    return standardize_phone(raw_phone, country=country, default_country=default_country).is_valid


def format_e164(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
) -> str | None:
    """Return the canonical ITU-T E.164 representation (+14155552671), or None if invalid."""
    res = standardize_phone(raw_phone, country=country, default_country=default_country)
    return res.e164 if res.is_valid else None


def format_national(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
) -> str | None:
    """Return the ITU-T E.123 national representation ((415) 555-2671), or None if invalid."""
    res = standardize_phone(raw_phone, country=country, default_country=default_country)
    return res.national if res.is_valid else None


def format_international(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
) -> str | None:
    """Return the ITU-T E.123 international representation (+1 415-555-2671), or None if invalid."""
    res = standardize_phone(raw_phone, country=country, default_country=default_country)
    return res.international if res.is_valid else None


def format_rfc3966(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
) -> str | None:
    """Return the IETF RFC 3966 URI representation (tel:+1-415-555-2671), or None if invalid."""
    res = standardize_phone(raw_phone, country=country, default_country=default_country)
    return res.rfc3966 if res.is_valid else None


def mask_phone(
    raw_phone: str | None,
    strategy: str = "partial",
    country: str | None = None,
    default_country: str = "US",
) -> str | None:
    """Privacy-preserving phone number masking compatible with Query-Builder CLAC policies.

    Strategies:
    - 'partial': Preserves country calling code and last 4 digits (e.g. '+1******2671')
    - 'partial_phone': Formats as '***-***-XXXX' preserving last 4 digits
    - 'last4': Formats as '****XXXX' preserving last 4 digits
    - 'redact': Full redaction ('[REDACTED PHONE]')
    - 'null': Returns None
    - 'hash' / 'sha256': Deterministic SHA-256 hex digest of the canonical E.164 key
    - 'md5': Deterministic MD5 hex digest of the canonical E.164 key
    """
    strat = strategy.lower().strip()
    if strat == "redact":
        return "[REDACTED PHONE]"
    if strat == "null":
        return None
    if strat not in ("partial", "partial_phone", "last4", "hash", "sha256", "md5"):
        raise ValueError(
            f"Unknown masking strategy: {strategy!r}. Supported strategies: "
            "'partial', 'partial_phone', 'last4', 'redact', 'null', 'hash', 'sha256', 'md5'."
        )
    res = standardize_phone(raw_phone, country=country, default_country=default_country)
    target = res.e164 or (str(raw_phone).strip() if raw_phone else "")
    if not target:
        return "[REDACTED PHONE]"
    if strat in ("hash", "sha256"):
        return hashlib.sha256(target.encode("utf-8")).hexdigest()
    if strat == "md5":
        return hashlib.md5(target.encode("utf-8"), usedforsecurity=False).hexdigest()
    digits = "".join(ch for ch in target if ch.isdigit())
    if strat == "partial_phone":
        return f"***-***-{digits[-4:]}" if len(digits) >= 4 else "***"
    if strat == "last4":
        return f"****{digits[-4:]}" if len(digits) >= 4 else "****"
    # Default ('partial'): preserve calling code and last 4 digits
    if res.e164 and res.country_calling_code and res.national_significant_number:
        nsn = res.national_significant_number
        masked_nsn = ("*" * max(0, len(nsn) - 4)) + nsn[-4:]
        return f"+{res.country_calling_code}{masked_nsn}"
    return ("*" * max(0, len(target) - 4)) + target[-4:]


# Candidate phone number regex for free-text extraction (formatted, contiguous E.164, (0) trunk, 5-group, vanity)
_FREE_TEXT_PHONE_CANDIDATE_RE = re.compile(
    r"(?<![:\d])(?!\d{4}-\d{2}-\d{2}\b)"
    r"(?:"
    r"(?:\+?\d{1,3}[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?|\d{2,4}[\s.\-])[A-Za-z0-9]*[A-Za-z]{3,8}[A-Za-z0-9]*(?:-[A-Za-z0-9]{2,6})?"
    r"|(?:\+\d{1,3}[\s.\-]?(?:\(\s*0\s*\)[\s.\-]?)?)?"
    r"(?:\(\d{1,5}\)[\s.\-]?|\d{1,5}[\s.\-])"
    r"(?:\d{1,5}(?:[\s.\-]\d{2,6}){1,4}|\d{5,9})"
    r"|\+\d{8,15}"
    r")"
    r"(?:\s*(?:;ext=|;isub=|(?:ext\.?|extension|x|#)\s*[:\-#]?\s*)\d{1,10})?"
    r"(?![:\d])",
    re.IGNORECASE,
)


def extract_phones_from_text(
    text: str | None,
    default_country: str = "US",
) -> list[StandardizedPhone]:
    """Extract and standardize all valid telephone numbers embedded in unstructured text."""
    if not text:
        return []
    seen_keys: set[str] = set()
    extracted: list[StandardizedPhone] = []
    for match in _FREE_TEXT_PHONE_CANDIDATE_RE.finditer(text):
        candidate = match.group(0).strip()
        rec = standardize_phone(candidate, default_country=default_country)
        if rec.is_valid and rec.phone_ext_key and rec.phone_ext_key not in seen_keys:
            seen_keys.add(rec.phone_ext_key)
            extracted.append(rec)
    return extracted


