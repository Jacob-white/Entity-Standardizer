"""Singapore Address Grammar (SGP).

Provides specialized parsing and normalization for Singapore addresses:
- 6-digit sector postal codes (e.g. 049909, 018981)
- Block / unit formatting: #08-01, BLK 101
- Commercial tower and building hierarchy (Ocean Financial Centre, Marina Bay Financial Centre, One Raffles Quay)
- Clean city and state conventions (Singapore is a unified city-state)
"""

from __future__ import annotations

import re
from typing import ClassVar, List, Optional, Tuple

from address_standardizer.international.base import (
    may_abbreviate_street_type,
    street_type_index,
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.tables import DIRECTIONALS, STREET_SUFFIXES


# Prominent Singapore Commercial Towers and Buildings
SG_NOTABLE_BUILDINGS = {
    "MARINA BAY FINANCIAL CENTRE TOWER 1", "MARINA BAY FINANCIAL CENTRE TOWER 2",
    "MARINA BAY FINANCIAL CENTRE TOWER 3", "MARINA BAY FINANCIAL CENTRE", "MBFC",
    "OCEAN FINANCIAL CENTRE", "ONE RAFFLES QUAY", "ONE RAFFLES PLACE", "OUB CENTRE",
    "UOB PLAZA 1", "UOB PLAZA 2", "UOB PLAZA", "OCBC CENTRE", "REPUBLIC PLAZA",
    "SUNTEC TOWER ONE", "SUNTEC TOWER TWO", "SUNTEC TOWER THREE", "SUNTEC TOWER FOUR",
    "SUNTEC TOWER FIVE", "SUNTEC TOWER 1", "SUNTEC TOWER 2", "SUNTEC TOWER 3",
    "SUNTEC TOWER 4", "SUNTEC TOWER 5", "SUNTEC CITY", "CAPITAGREEN", "CAPITASPRING",
    "GUOCO TOWER", "ASIA SQUARE TOWER 1", "ASIA SQUARE TOWER 2", "ASIA SQUARE",
    "OUE BAYFRONT", "SGX CENTRE 1", "SGX CENTRE 2", "SGX CENTRE", "MILLENIA TOWER",
    "CENTENNIAL TOWER", "THE PEAK", "INCOME AT RAFFLES", "MAYBANK TOWER",
}

# Singapore Unit pattern: #08-01, #12-345, # 08 - 01
RE_SG_UNIT = re.compile(
    r"(?:^|[\s,])#\s*([0-9]{1,3})\s*-\s*([A-Za-z0-9\-]+)\b",
    re.IGNORECASE,
)

# Block pattern: BLK 101, BLOCK 101, BLK 204A
RE_SG_BLOCK = re.compile(
    r"\b(?:BLK|BLOCK)\.?\s*([0-9]+[A-Za-z]?)\b",
    re.IGNORECASE,
)

# 6-digit postal code pattern
RE_SG_POSTCODE = re.compile(
    r"\b(?:SINGAPORE\s+|S\s*|SG\s*)?([0-9]{6})\b",
    re.IGNORECASE,
)

# Level / Floor pattern: LEVEL 24, LVL 12, FLOOR 5, FL 10
RE_SG_LEVEL = re.compile(
    r"\b(?:LEVEL|LVL|FLOOR|FL)\.?\s*([0-9]+)\b",
    re.IGNORECASE,
)


class SingaporeGrammar(CountryGrammar):
    """Singapore localized address grammar."""

    country_iso3: ClassVar[str] = "SGP"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "SGP",
        "SG",
        "SINGAPORE",
        "REPUBLIC OF SINGAPORE",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Singapore 6-digit postal code."""
        if not raw_code:
            return ""
        clean = re.sub(r"[^\d]", "", raw_code.strip())
        if len(clean) == 5:
            clean = f"0{clean}"
        if len(clean) == 6:
            return clean
        m = RE_SG_POSTCODE.search(raw_code.strip().upper())
        if m:
            return m.group(1)
        return clean if len(clean) == 6 else ""

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise_name, street_number, street_name) from Singapore address line."""
        if not street_line:
            return None, None, None

        s_clean = " ".join(street_line.strip().split())
        s_upper = s_clean.upper()

        # Check prominent buildings
        for bldg in sorted(SG_NOTABLE_BUILDINGS, key=len, reverse=True):
            if s_upper.startswith(bldg):
                rem = s_clean[len(bldg):].strip(" ,.-")
                if rem:
                    m_num = re.match(r"^(\d+[A-Za-z0-9\-]*)\s+(.+)$", rem)
                    if m_num:
                        return bldg, m_num.group(1), m_num.group(2)
                    return bldg, None, rem
                return bldg, None, None

        # Check Block prefix: e.g. "BLK 101 TOA PAYOH LORONG 1"
        m_blk = RE_SG_BLOCK.match(s_clean)
        if m_blk:
            blk_num = m_blk.group(1)
            rem = s_clean[m_blk.end():].strip(" ,.-")
            return None, f"BLK {blk_num}", rem

        # Standard street number and street: e.g. "10 COLLYER QUAY", "1 RAFFLES PLACE"
        m_st = re.match(r"^(\d+[A-Za-z0-9\-]*)\s+(.+)$", s_clean)
        if m_st:
            return None, m_st.group(1), m_st.group(2)

        return None, None, s_clean

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        """Parse tokenized lines into structured Singapore components."""
        s1 = metadata.get("street1") or ""
        s2 = metadata.get("street2") or ""
        post_raw = metadata.get("postal_code") or ""
        raw_full = metadata.get("raw_street_address") or ""

        combined = f"{s1} {s2}".strip()
        if raw_full and not combined:
            combined = raw_full

        # Extract 6-digit postal code if embedded in street string or provided
        norm_post = self.normalize_postal_code(post_raw)
        if not norm_post:
            m_post = RE_SG_POSTCODE.search(combined)
            if m_post:
                norm_post = m_post.group(1)
                combined = combined[:m_post.start()] + " " + combined[m_post.end():]

        # Extract unit number formatted as #08-01
        unit_str = ""
        m_u = RE_SG_UNIT.search(combined)
        if m_u:
            fl_num = int(m_u.group(1))
            u_id = m_u.group(2).upper()
            unit_str = f"#{fl_num:02d}-{u_id}"
            combined = combined[:m_u.start()] + " " + combined[m_u.end():]
        else:
            m_lvl = RE_SG_LEVEL.search(combined)
            if m_lvl:
                unit_str = f"LEVEL {m_lvl.group(1)}"
                combined = combined[:m_lvl.start()] + " " + combined[m_lvl.end():]

        if not unit_str and s2:
            # A non-empty street2 always comes back as a non-empty secondary unit.
            st1_rem, unit_str = split_intl_secondary_unit(s1, s2)
            combined = st1_rem

        combined = " ".join(combined.strip(" ,.-").split())
        # Strip trailing Singapore / SG if present
        combined = re.sub(r"(?:,\s*|\s+)\b(?:SINGAPORE|SG)\b", "", combined, flags=re.IGNORECASE).strip(" ,.-")

        # Extract premise, number, thoroughfare
        b_name, st_num, st_name = self.extract_premise_and_thoroughfare(combined)

        if st_name:
            words = st_name.split()
            norm_words = []
            type_idx = street_type_index(words)
            for idx, w in enumerate(words):
                w_up = w.upper()
                if w_up in STREET_SUFFIXES and may_abbreviate_street_type(w_up, idx, type_idx):
                    norm_words.append(STREET_SUFFIXES[w_up])
                elif w_up in DIRECTIONALS:
                    norm_words.append(DIRECTIONALS[w_up])
                else:
                    norm_words.append(w_up)
            st_name = " ".join(norm_words)

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=st_name,
            street_type=None,
            unit_type=None,
            unit_number=unit_str or None,
            building_name=b_name,
            dependent_locality=None,
            city="SINGAPORE",
            state="",
            postal_code=norm_post or "",
            country_iso3=self.country_iso3,
            raw_tokens=raw_tokens,
            confidence_score=0.95,
        )
