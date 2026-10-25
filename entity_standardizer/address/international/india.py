"""India Address Grammar (IND).

Provides specialized parsing and normalization for Indian addresses:
- 6-digit PIN code validation and normalization (e.g. 110001, 560100)
- SEZ (Special Economic Zone), Plot, Sector, Phase, Block conventions
- Tech Parks, Cyber Cities, Industrial Development Corridors (MIDC, GIDC)
- Major financial and IT hubs (Mumbai, Bengaluru, Gurugram, Noida, Hyderabad, Pune)
"""

from __future__ import annotations

import re
from typing import ClassVar, Dict, List, Optional, Tuple

from entity_standardizer.address.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)


# Indian States and Union Territories
IN_STATES: Dict[str, str] = {
    "ANDAMAN AND NICOBAR ISLANDS": "AN", "AN": "AN",
    "ANDHRA PRADESH": "AP", "AP": "AP",
    "ARUNACHAL PRADESH": "AR", "AR": "AR",
    "ASSAM": "AS", "AS": "AS",
    "BIHAR": "BR", "BR": "BR",
    "CHANDIGARH": "CH", "CH": "CH",
    "CHHATTISGARH": "CG", "CG": "CG",
    "DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "DN", "DN": "DN", "DAMAN AND DIU": "DD",
    "DELHI": "DL", "NEW DELHI": "DL", "NATIONAL CAPITAL TERRITORY OF DELHI": "DL", "DL": "DL",
    "GOA": "GA", "GA": "GA",
    "GUJARAT": "GJ", "GJ": "GJ",
    "HARYANA": "HR", "HR": "HR",
    "HIMACHAL PRADESH": "HP", "HP": "HP",
    "JAMMU AND KASHMIR": "JK", "JK": "JK",
    "JHARKHAND": "JH", "JH": "JH",
    "KARNATAKA": "KA", "KA": "KA",
    "KERALA": "KL", "KL": "KL",
    "LADAKH": "LA", "LA": "LA",
    "LAKSHADWEEP": "LD", "LD": "LD",
    "MADHYA PRADESH": "MP", "MP": "MP",
    "MAHARASHTRA": "MH", "MH": "MH",
    "MANIPUR": "MN", "MN": "MN",
    "MEGHALAYA": "ML", "ML": "ML",
    "MIZORAM": "MZ", "MZ": "MZ",
    "NAGALAND": "NL", "NL": "NL",
    "ODISHA": "OR", "ORISSA": "OR", "OR": "OR",
    "PUDUCHERRY": "PY", "PONDICHERRY": "PY", "PY": "PY",
    "PUNJAB": "PB", "PB": "PB",
    "RAJASTHAN": "RJ", "RJ": "RJ",
    "SIKKIM": "SK", "SK": "SK",
    "TAMIL NADU": "TN", "TN": "TN",
    "TELANGANA": "TG", "TG": "TG", "TS": "TG",
    "TRIPURA": "TR", "TR": "TR",
    "UTTAR PRADESH": "UP", "UP": "UP",
    "UTTARAKHAND": "UK", "UTTARANCHAL": "UK", "UK": "UK",
    "WEST BENGAL": "WB", "WB": "WB",
}

# PIN code: 6 digits starting with 1-9
RE_IN_PINCODE = re.compile(
    r"\b([1-9][0-9]{5})\b",
)

# A PIN written with a space ("560 001") at the end of the address, optionally before the country name.
RE_IN_PIN_SPACED = re.compile(
    r"\b([1-9][0-9]{2})\s([0-9]{3})\b(?=[\s,.]*(?:INDIA|IND|BHARAT)?[\s,.]*$)",
    re.IGNORECASE,
)

# Union territories / states that are also the city ("New Delhi 110001"): the locality stays the city.
IN_CITY_STATES = frozenset({"DELHI", "NEW DELHI", "CHANDIGARH", "PUDUCHERRY", "PONDICHERRY"})

# SEZ, Plot, Sector, Phase, Block patterns
RE_IN_PLOT = re.compile(
    r"\b(?:PLOT\s+NUMBER\b|PLOT\s+NO\b|PLOT)\.?\s*([0-9A-Za-z\/\-]+)\b",
    re.IGNORECASE,
)
RE_IN_SECTOR = re.compile(
    r"\b(?:SECTOR|SEC)\.?\s*([0-9A-Za-z\-]+)\b",
    re.IGNORECASE,
)
RE_IN_PHASE = re.compile(
    r"\b(?:PHASE|PH)\.?\s*([0-9IVX]+)\b",
    re.IGNORECASE,
)
RE_IN_BLOCK = re.compile(
    r"\b(?:BLOCK|BLK)\.?\s*([0-9A-Za-z\-]+)\b",
    re.IGNORECASE,
)
RE_IN_SEZ = re.compile(
    r"\b(?:SEZ|SPECIAL\s+ECONOMIC\s+ZONE)\b(?:\s+(?:UNIT|TOWER|BUILDING)\s*([0-9A-Za-z\-]+))?",
    re.IGNORECASE,
)


class IndiaGrammar(CountryGrammar):
    """India localized address grammar."""

    country_iso3: ClassVar[str] = "IND"
    split_commaless_line: ClassVar[bool] = True
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "IND", "IN", "INDIA", "BHARAT",
        "PAK", "PAKISTAN",
        "BGD", "BANGLADESH",
        "LKA", "SRI LANKA",
        "NPL", "NEPAL",
        "BTN", "BHUTAN",
        "MDV", "MALDIVES",
        "AFG", "AFGHANISTAN",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Indian 6-digit PIN code."""
        if not raw_code:
            return ""
        clean = re.sub(r"[^\d]", "", raw_code.strip())
        if len(clean) == 6 and clean[0] != "0":
            return clean
        m = RE_IN_PINCODE.search(raw_code.strip())
        if m:
            return m.group(1)
        return ""

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise_name, street_number, street_name) from Indian address line."""
        if not street_line:
            return None, None, None

        s_clean = " ".join(street_line.strip().split())

        # Check Plot / Sector / Phase structure
        m_plot = RE_IN_PLOT.search(s_clean)
        if m_plot:
            plot_num = m_plot.group(1).upper()
            rem = s_clean[:m_plot.start()] + " " + s_clean[m_plot.end():]
            rem = " ".join(rem.strip(" ,.-").split()).upper()
            return None, f"PLOT {plot_num}", (rem or None)

        # Check standard street number
        m_st = re.match(r"^(\d+[A-Za-z0-9\-]*)\s+(.+)$", s_clean)
        if m_st:
            return None, m_st.group(1), m_st.group(2).upper()

        return None, None, s_clean.upper()

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        """Parse tokenized lines into structured Indian components."""
        s1 = metadata.get("street1") or ""
        s2 = metadata.get("street2") or ""
        city_raw = metadata.get("city") or ""
        state_raw = metadata.get("state") or ""
        post_raw = metadata.get("postal_code") or ""
        raw_full = metadata.get("raw_street_address") or ""
        country_raw = metadata.get("country", self.country_iso3)
        from entity_standardizer.address.international.countries import CountryRegistry
        info = CountryRegistry.get(country_raw)
        country_iso = info.alpha3 if (info and info.alpha3 in self.supported_countries) else self.country_iso3

        combined = f"{s1} {s2}".strip()
        if raw_full and not combined:
            combined = raw_full

        # Normalize PIN code
        norm_post = self.normalize_postal_code(post_raw)
        if not norm_post:
            m_pin = RE_IN_PINCODE.search(combined)
            if m_pin:
                norm_post = m_pin.group(1)
                combined = combined[:m_pin.start()] + " " + combined[m_pin.end():]
            else:
                m_spaced = RE_IN_PIN_SPACED.search(combined)
                if m_spaced:
                    norm_post = m_spaced.group(1) + m_spaced.group(2)
                    combined = combined[:m_spaced.start()] + " " + combined[m_spaced.end():]

        # Normalize State
        norm_state = ""
        if state_raw:
            s_up = state_raw.strip().upper()
            norm_state = IN_STATES.get(s_up, s_up)
        elif city_raw and city_raw.strip().upper() in IN_CITY_STATES:
            norm_state = IN_STATES[city_raw.strip().upper()]

        # Detect SEZ units
        sec_unit_str = ""
        m_sez = RE_IN_SEZ.search(combined)
        if m_sez:
            u_id = m_sez.group(1)
            sec_unit_str = f"SEZ UNIT {u_id}" if u_id else "SEZ"
            combined = combined[:m_sez.start()] + " " + combined[m_sez.end():]

        if not sec_unit_str and s2:
            # A non-empty street2 always comes back as a non-empty secondary unit.
            st1_rem, sec_unit_str = split_intl_secondary_unit(s1, s2)
            combined = st1_rem

        combined = " ".join(combined.strip(" ,.-").split())

        combined = re.sub(r"(?:,\s*|\s+)\b(?:INDIA|IND|BHARAT)\b$", "", combined, flags=re.IGNORECASE).strip(" ,.-")

        # "..., New Delhi" / "..., Chandigarh": a city-state in the final locality position is the city (and the state).
        city_state_head, _, city_state_tail = combined.rpartition(",")
        if not city_raw and city_state_head and city_state_tail.strip().upper() in IN_CITY_STATES:
            city_raw = city_state_tail.strip()
            if not norm_state:
                norm_state = IN_STATES[city_state_tail.strip().upper()]
            combined = city_state_head.strip(" ,.-")

        # Strip / extract State from combined
        for s_name, s_code in sorted(IN_STATES.items(), key=lambda x: len(x[0]), reverse=True):
            m_s = re.search(rf"\b{re.escape(s_name)}\b", combined, re.IGNORECASE)
            if m_s:
                if not norm_state:
                    norm_state = s_code
                if not city_raw and s_name in IN_CITY_STATES:
                    city_raw = s_name
                combined = combined[:m_s.start()] + " " + combined[m_s.end():]
                combined = " ".join(combined.strip(" ,.-").split())
                break

        dep_locality: Optional[str] = None

        # Extract city if comma-separated
        if not city_raw and "," in combined:
            st_part, city_part = combined.rsplit(",", 1)
            city_raw = city_part.strip().upper()
            combined = st_part.strip()
            # "36 Rebello Road, Bandra, Mumbai": letters-only parts between a numbered street and the city are the
            # sub-locality (dependent locality), not part of the street.
            head, *middle = [p.strip() for p in combined.split(",") if p.strip()]
            if head[0].isdigit() and middle and not any(ch.isdigit() for ch in ",".join(middle)):
                dep_locality = ", ".join(middle).upper()
                combined = head

        # Extract thoroughfare components
        b_name, st_num, st_name = self.extract_premise_and_thoroughfare(combined)

        u_parts = sec_unit_str.split(None, 1) if sec_unit_str else []
        u_type = u_parts[0] if len(u_parts) > 1 else None
        u_num = u_parts[1] if len(u_parts) > 1 else (sec_unit_str or None)

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=st_name,
            street_type=None,
            unit_type=u_type,
            unit_number=u_num,
            building_name=b_name,
            dependent_locality=dep_locality,
            city=city_raw.strip().upper() if city_raw else "",
            state=norm_state,
            postal_code=norm_post or "",
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
            confidence_score=0.95,
        )
