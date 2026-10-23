"""
Delivery Intelligence, USPS Diagnostic Footnotes & CMRA/RDI Engine.
===================================================================
Implements USPS Delivery Point Validation (DPV) diagnostic footnotes,
Residential Delivery Indicator (RDI), Commercial Mail Receiving Agency (CMRA)
identification, and vacancy detection.
"""

from enum import Enum
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from address_standardizer.registry import (
    lookup_corporate_registry,
    RegistryCategory,
)
from address_standardizer.tables import ZIP3_TO_STATE, US_STATES
from address_standardizer._patterns import SPANISH_PREFIX_THOROUGHFARES

__all__ = [
    "DPVFootnote",
    "RDI",
    "Deliverability",
    "DeliveryIntelligenceResult",
    "evaluate_delivery_intelligence",
]


class DPVFootnote:
    """Standard USPS DPV Diagnostic Footnote Codes."""
    AA = "AA"  # Input address matched to the ZIP+4 file
    A1 = "A1"  # Input address not matched to the ZIP+4 file
    BB = "BB"  # Entire address (number and street) matched to DPV (active delivery point)
    CC = "CC"  # Secondary number confirmed
    N1 = "N1"  # High-rise address missing secondary information
    M1 = "M1"  # Primary number missing
    M3 = "M3"  # Primary number invalid
    P1 = "P1"  # PO, RR, or HC Box number missing
    PB = "PB"  # PO Box street address
    RR = "RR"  # Rural Route address
    F1 = "F1"  # Military / diplomatic address
    G1 = "G1"  # General delivery address
    U1 = "U1"  # Unique ZIP code


class RDI(str, Enum):
    """Residential Delivery Indicator values."""
    RESIDENTIAL = "Residential"
    COMMERCIAL = "Commercial"
    UNKNOWN = "Unknown"


CMRA_KEYWORDS = frozenset({
    "THE UPS STORE", "UPS STORE", "POSTALANNEX", "POSTAL ANNEX",
    "MAIL BOXES ETC", "MAIL BOXES ETC.", "PAK MAIL", "POSTNET",
    "DAVINCI VIRTUAL", "DAVINCI MEETING", "REGUS", "INTELLIGENT OFFICE", "OFFICE EVOLUTION"
})

# Whole-word matching: "DAVINCI" must not flag "123 Davinci Dr" via a substring of a longer word, and a street
# such as "Vacantville Rd" is not a vacancy marker.
_RE_CMRA_KEYWORD = re.compile(
    r"(?<![A-Z0-9])(?:" + "|".join(re.escape(k) for k in sorted(CMRA_KEYWORDS, key=len, reverse=True)) + r")(?![A-Z0-9])"
)
_RE_PMB_WORD = re.compile(r"(?<![A-Z])PMB(?![A-Z])")
_RE_VACANT_WORD = re.compile(r"(?<![A-Z])VACANT(?![A-Z])")

COMMERCIAL_SEC_UNITS = frozenset({
    "STE", "SUITE", "OFC", "OFFICE", "FL", "FLOOR", "BLDG", "BUILDING", "DEPT", "DEPARTMENT", "RM", "ROOM"
})

RESIDENTIAL_SEC_UNITS = frozenset({
    "APT", "APARTMENT", "UNIT", "LOT", "SPC", "SPACE", "TRLR", "TRAILER"
})


class Deliverability(str, Enum):
    """Consolidated USPS deliverability classifications."""
    DELIVERABLE = "DELIVERABLE"
    REQUIRES_SECONDARY = "REQUIRES_SECONDARY"
    UNDELIVERABLE = "UNDELIVERABLE"


@dataclass
class DeliveryIntelligenceResult:
    """Structured delivery intelligence metadata."""
    rdi: str  # "Residential", "Commercial", "Unknown"
    cmra: bool
    vacant: bool
    dpv_footnotes: List[str] = field(default_factory=list)
    deliverability: str = Deliverability.DELIVERABLE
    secondary_prompt_required: bool = False
    prompt_message: Optional[str] = None
    suggested_secondary_units: List[str] = field(default_factory=list)

    @property
    def is_cmra(self) -> bool:
        return self.cmra

    @property
    def is_vacant(self) -> bool:
        return self.vacant

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rdi": self.rdi,
            "cmra": self.cmra,
            "is_cmra": self.cmra,
            "vacant": self.vacant,
            "is_vacant": self.vacant,
            "dpv_footnotes": list(self.dpv_footnotes),
            "deliverability": self.deliverability,
            "secondary_prompt_required": self.secondary_prompt_required,
            "prompt_message": self.prompt_message,
            "suggested_secondary_units": list(self.suggested_secondary_units),
        }


def evaluate_delivery_intelligence(
    std_address: Any = None,
    raw_input: Optional[Dict[str, Any]] = None,
    is_vacant_override: Optional[bool] = None,
    *,
    street1: Optional[str] = None,
    street2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    address_status: Optional[str] = None,
    **kwargs: Any,
) -> DeliveryIntelligenceResult:
    """
    Evaluates delivery intelligence for a standardized address, computing
    RDI, CMRA status, vacancy flag, USPS DPV diagnostic footnote codes,
    and consolidated deliverability classification.
    """
    if std_address is None or street1 is not None or kwargs:
        from address_standardizer.standardizer import standardize_address
        s1_val = (street1 or getattr(std_address, "street1", "") or kwargs.get("street1", "") or "").strip()
        s2_val = (street2 or getattr(std_address, "street2", "") or kwargs.get("street2", "") or "").strip()
        c_val = (city or getattr(std_address, "city", "") or kwargs.get("city", "") or "").strip()
        st_val = (state or getattr(std_address, "state", "") or kwargs.get("state", "") or "").strip()
        post_val = (postal_code or getattr(std_address, "postal_code", "") or kwargs.get("postal_code", "") or "").strip()
        cntry_val = (country or getattr(std_address, "country", "USA") or kwargs.get("country", "USA"))

        std_address = standardize_address(
            street1=s1_val,
            street2=s2_val,
            city=c_val,
            state=st_val,
            postal_code=post_val,
            country=cntry_val,
            allow_locality=True,
        )

    # 1. International short-circuit
    if not getattr(std_address, "is_us", True):
        status = getattr(std_address, "address_status", "standardized")
        is_deliv = (status == "standardized")
        return DeliveryIntelligenceResult(
            rdi=RDI.UNKNOWN,
            cmra=False,
            vacant=False,
            dpv_footnotes=[],
            deliverability=Deliverability.DELIVERABLE if is_deliv else Deliverability.UNDELIVERABLE,
        )

    raw = raw_input or {}
    raw_combined = f"{raw.get('street1', '')} {raw.get('street2', '')} {getattr(std_address, 'raw_street_address', '')}".upper()
    st1 = (getattr(std_address, "street1", "") or "").strip().upper()
    st2 = (getattr(std_address, "street2", "") or "").strip().upper()
    city = (getattr(std_address, "city", "") or "").strip().upper()
    state = (getattr(std_address, "state", "") or "").strip().upper()
    postal_code = (getattr(std_address, "postal_code", "") or "").strip()
    status = getattr(std_address, "address_status", "standardized")

    # 2. CMRA Evaluation
    is_cmra = False
    if (
        _RE_PMB_WORD.search(st1)
        or _RE_PMB_WORD.search(st2)
        or "PRIVATE MAILBOX" in raw_combined
        or _RE_PMB_WORD.search(raw_combined)
    ):
        is_cmra = True
    elif _RE_CMRA_KEYWORD.search(raw_combined) or _RE_CMRA_KEYWORD.search(st1):
        is_cmra = True
    else:
        reg_entry = lookup_corporate_registry(
            street1=st1,
            street2=st2,
            city=city,
            state=state,
            postal_code=postal_code,
            country="USA",
            raw_street=raw_combined,
        )
        if reg_entry is not None and reg_entry.category in (
            RegistryCategory.MAIL_DROP_CMRA,
            RegistryCategory.VIRTUAL_OFFICE,
        ):
            is_cmra = True

    # 3. Vacancy Evaluation
    is_vacant = bool(is_vacant_override) if is_vacant_override is not None else False
    if _RE_VACANT_WORD.search(raw_combined) or raw.get("vacant") is True or raw.get("is_vacant") is True:
        is_vacant = True

    # 4. RDI (Residential Delivery Indicator) Evaluation
    is_priv = getattr(std_address, "is_private_residence", False)
    is_hub = getattr(std_address, "is_registered_agent_hub", False)
    st2_unit_type = st2.split()[0] if st2 else ""

    if is_hub or is_cmra or st2_unit_type in COMMERCIAL_SEC_UNITS:
        rdi = RDI.COMMERCIAL
    elif is_priv or st2_unit_type in RESIDENTIAL_SEC_UNITS:
        rdi = RDI.RESIDENTIAL
    elif st1.startswith("PO BOX"):
        rdi = RDI.UNKNOWN
    else:
        # Default based on secondary unit or leave Unknown
        rdi = RDI.UNKNOWN

    # 5. USPS DPV Diagnostic Footnotes
    footnotes: List[str] = []

    # AA / A1: Postal code concordance
    norm_st = US_STATES.get(state, state)
    zip_digits = re.sub(r"[^\d]", "", postal_code)
    z3 = zip_digits[:3] if len(zip_digits) >= 3 else ""

    valid_zip_state = bool(
        status != "parse_failed"
        and len(zip_digits) in (5, 9)
        and z3 in ZIP3_TO_STATE
        and (not norm_st or ZIP3_TO_STATE[z3] == norm_st)
    )

    if valid_zip_state:
        footnotes.append(DPVFootnote.AA)
    else:
        footnotes.append(DPVFootnote.A1)

    # Street level deliverability
    if status == "parse_failed" or not st1:
        footnotes.append(DPVFootnote.M1)
    elif st1.startswith("PO BOX"):
        footnotes.append(DPVFootnote.BB)
        footnotes.append(DPVFootnote.PB)
    elif st1.startswith("RR ") or st1.startswith("HC "):
        footnotes.append(DPVFootnote.BB)
        footnotes.append(DPVFootnote.RR)
    elif city in ("APO", "FPO", "DPO") or state in ("AE", "AP", "AA"):
        footnotes.append(DPVFootnote.BB)
        footnotes.append(DPVFootnote.F1)
    else:
        tokens = st1.split()
        first_tok = tokens[0] if tokens else ""
        if (
            first_tok in ("URB", "URB.", "URBANIZACION")
            or first_tok in SPANISH_PREFIX_THOROUGHFARES
        ) and len(tokens) > 1:
            for tok in tokens[1:]:
                tok_clean = re.sub(r"[^\w]", "", tok)
                if any(ch.isdigit() for ch in tok_clean) or tok_clean in {
                    "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN"
                }:
                    first_tok = tok_clean
                    break

        first_digits = re.sub(r"[^\d]", "", first_tok)
        is_all_zero = bool(first_digits and all(c == "0" for c in first_digits))
        has_num = not is_all_zero and (any(ch.isdigit() for ch in first_tok) or first_tok in {
            "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN"
        })

        if is_all_zero:
            footnotes.append(DPVFootnote.M3)
        elif has_num:
            footnotes.append(DPVFootnote.BB)
            # Check secondary unit presence vs necessity
            reg_entry = lookup_corporate_registry(
                street1=st1,
                street2=st2,
                city=city,
                state=state,
                postal_code=postal_code,
                country="USA",
                raw_street=raw_combined,
            )
            from address_standardizer.offline_index import get_default_offline_index
            offline_rec = get_default_offline_index().resolve_coordinates(std_address)
            is_multi_unit_hub = is_hub or (reg_entry is not None) or (offline_rec is not None and getattr(offline_rec, "is_multi_unit", False))

            if st2:
                footnotes.append(DPVFootnote.CC)
            elif is_multi_unit_hub:
                footnotes.append(DPVFootnote.N1)
        else:
            footnotes.append(DPVFootnote.M1)

    # Consolidated deliverability classification
    if status == "parse_failed" or DPVFootnote.M1 in footnotes or DPVFootnote.M3 in footnotes:
        deliverability = Deliverability.UNDELIVERABLE
    elif DPVFootnote.A1 in footnotes and zip_digits:
        # A ZIP was supplied but is malformed or belongs to a different state: it cannot be confirmed
        # (a missing ZIP is left to the street-level result).
        deliverability = Deliverability.UNDELIVERABLE
    elif DPVFootnote.N1 in footnotes:
        deliverability = Deliverability.REQUIRES_SECONDARY
    else:
        # Every street-level outcome adds either M1/M3 (handled above) or BB, so BB is always present here.
        deliverability = Deliverability.DELIVERABLE

    sec_prompt_required = False
    prompt_msg = None
    suggested_sec_units: List[str] = []

    if DPVFootnote.N1 in footnotes:
        sec_prompt_required = True
        prompt_msg = "Requires Suite / Apartment Number"
        if offline_rec and getattr(offline_rec, "known_units", None):
            suggested_sec_units = list(offline_rec.known_units)
        else:
            suggested_sec_units = ["STE", "FL", "UNIT", "APT"]

    return DeliveryIntelligenceResult(
        rdi=rdi,
        cmra=is_cmra,
        vacant=is_vacant,
        dpv_footnotes=footnotes,
        deliverability=deliverability,
        secondary_prompt_required=sec_prompt_required,
        prompt_message=prompt_msg,
        suggested_secondary_units=suggested_sec_units,
    )
