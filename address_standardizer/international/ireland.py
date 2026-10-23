"""Ireland Address Grammar (IRL).

Provides specialized parsing and normalization for Ireland (Éire) addresses:
- Eircode validation and canonical formatting (Routing Key + Unique Identifier, e.g. D02 X285)
- 26 Counties normalization (e.g. Co. Dublin, County Cork -> CO DUBLIN, CO CORK)
- Dublin postal districts (Dublin 1 through Dublin 24, Dublin 6W)
- Financial district and commercial hubs (IFSC, Grand Canal Dock, Quays, Business Parks)
- Thoroughfare and directional qualifiers (Quay, Lower, Upper, St, Rd)
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import ClassVar, Dict, List, Optional, Tuple

from address_standardizer._patterns import (
    RE_NON_ALPHANUMERIC,
    is_invalid_thoroughfare,
)
from address_standardizer.international.uk import split_commaless_postal_city
from address_standardizer.international.base import (
    may_abbreviate_street_type,
    street_type_index,
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.tables import DIRECTIONALS, SECONDARY_UNITS, STREET_SUFFIXES


# Valid Eircode routing keys (Dublin districts + Post Towns across 26 counties)
IR_DUBLIN_ROUTING_KEYS = {
    "D01", "D02", "D03", "D04", "D05", "D06", "D6W", "D07", "D08", "D09",
    "D10", "D11", "D12", "D13", "D14", "D15", "D16", "D17", "D18", "D20",
    "D22", "D24",
}

IR_PROVINCIAL_ROUTING_KEYS = {
    "A41", "A42", "A45", "A63", "A67", "A75", "A81", "A82", "A83", "A84", "A85", "A86",
    "A91", "A92", "A94", "A96", "A98", "C15", "E21", "E25", "E32", "E34", "E41", "E45",
    "E53", "E91", "F12", "F23", "F26", "F28", "F31", "F35", "F42", "F45", "F52", "F56",
    "F91", "F92", "F93", "F94", "H12", "H14", "H16", "H18", "H23", "H53", "H54", "H62",
    "H65", "H71", "H91", "K32", "K34", "K36", "K45", "K56", "K67", "K78", "N37", "N39",
    "N41", "N91", "P12", "P14", "P17", "P24", "P25", "P31", "P32", "P36", "P43", "P47",
    "P51", "P56", "P61", "P67", "P72", "P75", "P81", "P85", "R14", "R21", "R32", "R35",
    "R42", "R45", "R51", "R56", "R93", "R95", "T12", "T23", "T34", "T45", "T56", "V14",
    "V15", "V23", "V31", "V42", "V92", "V93", "V94", "V95", "W12", "W23", "W34", "W91",
    "X35", "X42", "X91", "Y14", "Y21", "Y25", "Y34", "Y35",
}

ALL_EIRCODE_ROUTING_KEYS = IR_DUBLIN_ROUTING_KEYS | IR_PROVINCIAL_ROUTING_KEYS

# Eircode exact and search patterns
# Eircode structure: 3-char routing key, space, 4-char unique identifier
# Chars B, G, I, J, L, M, O, Q, S, U, Z are excluded in official Eircodes, but we allow general alnum for OCR
RE_EIRCODE_EXACT = re.compile(
    r"^(?:([AC-FHKNPRTV-Y]\d[0-9AC-FHKNPRTV-Y]|D6W|[A-Za-z]\d[0-9A-Za-z]))\s*([0-9AC-FHKNPRTV-Y]{4}|[0-9A-Za-z]{4})$",
    re.IGNORECASE,
)
RE_EIRCODE_SEARCH = re.compile(
    r"\b([AC-FHKNPRTV-Y]\d[0-9AC-FHKNPRTV-Y]|D6W|[A-Za-z]\d[0-9A-Za-z])\s*([0-9AC-FHKNPRTV-Y]{4}|[0-9A-Za-z]{4})\b",
    re.IGNORECASE,
)

# 26 Counties of Ireland (Republic of Ireland)
IR_COUNTY_NAMES = {
    "CARLOW", "CAVAN", "CLARE", "CORK", "DONEGAL", "DUBLIN", "GALWAY",
    "KERRY", "KILDARE", "KILKENNY", "LAOIS", "LEITRIM", "LIMERICK",
    "LONGFORD", "LOUTH", "MAYO", "MEATH", "MONAGHAN", "OFFALY",
    "ROSCOMMON", "SLIGO", "TIPPERARY", "WATERFORD", "WESTMEATH",
    "WEXFORD", "WICKLOW",
}

IR_COUNTIES: Dict[str, str] = {}
for _name in IR_COUNTY_NAMES:
    _std = f"CO {_name}"
    IR_COUNTIES[_name] = _std
    IR_COUNTIES[f"CO {_name}"] = _std
    IR_COUNTIES[f"CO. {_name}"] = _std
    IR_COUNTIES[f"COUNTY {_name}"] = _std
    IR_COUNTIES[f"CONTAE {_name}"] = _std

# Dublin Postal Districts
DUBLIN_DISTRICTS = {
    f"DUBLIN {i}": f"DUBLIN {i}" for i in range(1, 25)
}
DUBLIN_DISTRICTS["DUBLIN 6W"] = "DUBLIN 6W"
for i in range(1, 25):
    DUBLIN_DISTRICTS[f"D{i:02d}"] = f"DUBLIN {i}"
    DUBLIN_DISTRICTS[f"D{i}"] = f"DUBLIN {i}"
DUBLIN_DISTRICTS["D6W"] = "DUBLIN 6W"

# Dublin / Irish Financial Districts, Commercial Hubs, and Localities
IR_LOCALITIES = {
    "IFSC", "INTERNATIONAL FINANCIAL SERVICES CENTRE", "GRAND CANAL DOCK",
    "SILICON DOCKS", "CUSTOM HOUSE DOCK", "CUSTOM HOUSE QUAY", "NORTH WALL QUAY",
    "SIR JOHN ROGERSON'S QUAY", "SIR JOHN ROGERSONS QUAY", "GEORGE'S DOCK", "GEORGES DOCK",
    "HARBOURMASTER PLACE", "SPENCER DOCK", "EAST POINT BUSINESS PARK",
    "CENTRAL PARK", "SANDYFORD BUSINESS PARK", "SANDYFORD INDUSTRIAL ESTATE",
    "PARK WEST BUSINESS PARK", "BLANCHARDSTOWN CORPORATE PARK",
    "CITYWEST BUSINESS CAMPUS", "BALLSBRIDGE", "RANELAGH", "RATHMINES",
    "DONNYBROOK", "BLACKROCK", "DUN LAOGHAIRE", "DÚN LAOGHAIRE",
    "SWORDS", "TALLAGHT", "CLONDALKIN", "LUCAN", "BLANCHARDSTOWN",
    "MALAHIDE", "HOWTH", "BRAY", "GREYSTONES",
}

# Irish Post Towns
IR_POST_TOWNS = {
    "DUBLIN", "CORK", "GALWAY", "LIMERICK", "WATERFORD", "DROGHEDA",
    "DUNDALK", "SWORDS", "BRAY", "NAVAN", "KILKENNY", "ENNIS",
    "CARLOW", "TRALEE", "NEWBRIDGE", "PORTLAOISE", "BALBRIGGAN",
    "NAAS", "ATHLONE", "MULLINGAR", "CELBRIDGE", "WEXFORD",
    "LETTERKENNY", "SLIGO", "GREYSTONES", "CLONMEL", "MALAHIDE",
    "CARRIGALINE", "LEIXLIP", "TULLAMORE", "KILLARNEY", "ARKLOW",
    "COBH", "CASTLEBAR", "MIDLETON", "MALLOW", "WICKLOW",
    "BALLINA", "ENNISCORTHY", "SHANNON", "ASHBOURNE", "DUNGARVAN",
    "KAVAN", "SKIBBEREEN", "BANTRY", "KINSALE", "YOUGHAL",
    "WESTPORT", "TUAM", "BALLINASLOE", "LOUGHREA", "NENAGH", "THURLES",
}


def is_valid_eircode(code: Optional[str]) -> bool:
    """Validate whether an alphanumeric string is a valid Irish Eircode."""
    if not code:
        return False
    clean = re.sub(r"[\s\-]", "", code.strip()).upper()
    if len(clean) != 7:
        return False
    m = RE_EIRCODE_EXACT.match(clean)
    if not m:
        return False
    routing_key = m.group(1).upper()
    return routing_key in ALL_EIRCODE_ROUTING_KEYS or len(routing_key) == 3


_RE_IE_TRAILING_COUNTRY = re.compile(
    r"\s+(?:REPUBLIC\s+OF\s+IRELAND|IRELAND|EIRE|ÉIRE|IRL|IE)\s*$", re.IGNORECASE
)


def _is_eircode_run(run: str) -> bool:
    """True for a 7-character Eircode written as "H91 KW97" or "H91KW97" (routing key: letter, digit, alphanumeric)."""
    return is_valid_eircode(run) and run.split()[0][1:2].isdigit() and len(run.replace(" ", "")) == 7


def format_eircode(code: str) -> str:
    """Format 7-character Eircode into canonical 'A65 F4E2' representation."""
    if not code:
        return ""
    clean = re.sub(r"[\s\-]", "", code.strip()).upper()
    if len(clean) == 7 and RE_EIRCODE_EXACT.match(clean):
        return f"{clean[:3]} {clean[3:]}"
    m = RE_EIRCODE_SEARCH.search(code.strip())
    if m:
        rk = m.group(1).upper()
        uid = m.group(2).upper()
        return f"{rk} {uid}"
    return code.strip().upper()


@dataclass(slots=True)
class IrelandParsedAddressComponents(ParsedAddressComponents):
    """Structured parsed address components for Ireland."""

    def format_street1(self) -> str:
        """Formats street1 as numbered thoroughfare delivery line."""
        if self.street_number and self.street_name:
            parts = [self.street_number]
            if self.pre_directional:
                parts.append(self.pre_directional)
            parts.append(self.street_name)
            if self.street_type and not (
                self.street_name.endswith(" " + self.street_type)
                or self.street_name.startswith(self.street_type + " ")
                or self.street_name == self.street_type
            ):
                parts.append(self.street_type)
            if self.post_directional:
                parts.append(self.post_directional)
            return " ".join(parts).strip()
        if self.street_name and self.street_name.isdigit() and (self.unit_type or self.unit_number):
            u_str = f"{self.unit_type or 'UNIT'} {self.unit_number or ''}".strip()
            return f"{self.street_name} {u_str}".strip()
        if self.street_number and not self.street_name and (self.unit_type or self.unit_number):
            u_str = f"{self.unit_type or 'UNIT'} {self.unit_number or ''}".strip()
            return f"{self.street_number} {u_str}".strip()
        return ParsedAddressComponents.format_street1(self)

    def format_street2(self) -> str:
        """Formats street2 combining secondary unit and premise name."""
        if (self.street_name and self.street_name.isdigit() and (self.unit_type or self.unit_number)) or (
            self.street_number and not self.street_name and (self.unit_type or self.unit_number)
        ):
            if self.building_name:
                return self.building_name.strip()
            return ""
        sec = ParsedAddressComponents.format_street2(self)
        if self.building_name and self.street_number:
            if sec:
                return f"{sec} {self.building_name}".strip()
            return self.building_name.strip()
        return sec


class IrelandGrammar(CountryGrammar):
    """Ireland localized address grammar."""

    country_iso3: ClassVar[str] = "IRL"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "IRL",
        "IE",
        "IRELAND",
        "REPUBLIC OF IRELAND",
        "ÉIRE",
        "EIRE",
    )

    def standardize(
        self,
        street1: Optional[str] = None,
        street2: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
        raw_street_address: Optional[str] = None,
    ) -> ParsedAddressComponents:
        """Standardize; a comma-less "9 High Street Galway H91 KW97" is split at its trailing Eircode first."""
        if street1 and not (city or state or postal_code) and "," not in street1:
            split = split_commaless_postal_city(
                street1, _is_eircode_run, IR_POST_TOWNS | IR_COUNTY_NAMES, _RE_IE_TRAILING_COUNTRY
            )
            if split is not None:
                street1, city, postal_code = split
        return super().standardize(street1, street2, city, state, postal_code, country, raw_street_address)

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize Irish Eircode to canonical form (e.g. D02 X285)."""
        return format_eircode(raw_code)

    def extract_premise_and_thoroughfare(
        self, street_line: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise_name, street_number, street_name) from Irish thoroughfare line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()
        premise: Optional[str] = None
        st_num: Optional[str] = None
        st_name: Optional[str] = None

        if "," in line:
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) >= 2:
                m_num0 = re.match(r"^(\d+[A-Za-z0-9\-\/]*)\s+(.*)$", parts[0])
                if not m_num0:
                    premise = parts[0].upper()
                    rest = ", ".join(parts[1:])
                else:
                    rest = line
            else:
                rest = line
        else:
            rest = line

        # Split remaining into street number and street name
        m_num = re.match(r"^(\d+[A-Za-z0-9\-\/]*)\s+(.*)$", rest.strip())
        if m_num:
            st_num = m_num.group(1).upper()
            st_name = self._normalize_street_tokens(m_num.group(2))
        else:
            cand = self._normalize_street_tokens(rest)
            if re.match(r"^\d+[A-Za-z]?$", cand) or is_invalid_thoroughfare(cand):
                st_name = None
                premise = cand if not premise else premise
            else:
                st_name = cand

        return premise, st_num, st_name

    def _normalize_street_tokens(self, text: str) -> str:
        """Normalize Irish street name tokens, preserving Quays and directional qualifiers."""
        if not text:
            return ""
        words = text.strip().split()
        norm_words: List[str] = []
        type_idx = street_type_index(words)
        for idx, w in enumerate(words):
            w_clean = RE_NON_ALPHANUMERIC.sub("", w).upper()
            # Retain QUAY, LOWER, UPPER explicitly
            if w_clean in ("QUAY", "QUAYS"):
                norm_words.append("QUAY")
            elif w_clean in ("LOWER", "LR"):
                norm_words.append("LOWER")
            elif w_clean in ("UPPER", "UPR"):
                norm_words.append("UPPER")
            elif w_clean in STREET_SUFFIXES and may_abbreviate_street_type(w_clean, idx, type_idx):
                norm_words.append(STREET_SUFFIXES[w_clean])
            elif w_clean in DIRECTIONALS:
                norm_words.append(DIRECTIONALS[w_clean])
            else:
                norm_words.append(w.upper())
        return " ".join(norm_words)

    def parse(self, raw_tokens: List[str], metadata: dict) -> IrelandParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        raw_full = metadata.get("raw_street_address", "")

        unit_type: Optional[str] = None
        unit_number: Optional[str] = None
        building_name: Optional[str] = None
        dep_locality: Optional[str] = None
        norm_county: Optional[str] = None

        street_line = s1_raw
        if not street_line and raw_full:
            street_line = raw_full

        # Extract Eircode from any field if not present
        if not postal_raw:
            for source in (raw_full, s1_raw, s2_raw, city_raw, state_raw):
                if source:
                    m_eir = RE_EIRCODE_SEARCH.search(source)
                    if m_eir:
                        postal_raw = f"{m_eir.group(1).upper()} {m_eir.group(2).upper()}"
                        break

        # Check and normalize County from state or other fields
        for cand in (state_raw, city_raw, s2_raw):
            if cand:
                c_up = cand.strip().upper()
                if c_up in IR_COUNTIES:
                    norm_county = IR_COUNTIES[c_up]
                    break
                # Check regex like "Co. Dublin" or "County Dublin"
                m_co = re.search(r"\b(?:CO\.?|COUNTY)\s+([A-Z]+)\b", c_up)
                if m_co and m_co.group(1) in IR_COUNTY_NAMES:
                    norm_county = f"CO {m_co.group(1)}"
                    break

        # Comma-separated full address decomposition when city is not structured
        if not city_raw and street_line and "," in street_line:
            parts = [p.strip() for p in street_line.split(",") if p.strip()]
            # Remove country if at end
            if parts and parts[-1].upper() in (
                "IRL", "IE", "IRELAND", "REPUBLIC OF IRELAND", "ÉIRE", "EIRE"
            ):
                parts = parts[:-1]

            # Check if last token has Eircode
            if parts:
                m_end_eir = RE_EIRCODE_SEARCH.search(parts[-1])
                if m_end_eir:
                    # postal_raw is already populated: the Eircode search above covers street1 as well.
                    rem = parts[-1][:m_end_eir.start()].strip()
                    if rem:
                        parts[-1] = rem
                    else:
                        parts = parts[:-1]

            # Check for county in parts
            clean_parts = []
            for p in parts:
                p_up = p.upper()
                if p_up in IR_COUNTIES:
                    if not norm_county:
                        norm_county = IR_COUNTIES[p_up]
                    if p_up in IR_POST_TOWNS and not p_up.startswith(("CO ", "CO.", "COUNTY ")):
                        clean_parts.append(p)  # a bare "Cork"/"Galway" is also the city; do not lose it
                else:
                    clean_parts.append(p)
            parts = clean_parts

            # Check secondary unit in parts (e.g. "Flat 2", "Unit 5", "Block A")
            clean_parts = []
            for p in parts:
                m_sec = re.match(
                    r"^(?:FLAT|APT|APARTMENT|UNIT|SUITE|STE|BLOCK)\s*#?\s*([A-Za-z0-9\-]+)$",
                    p.strip(),
                    re.IGNORECASE,
                )
                if m_sec and not unit_number:
                    p_type = p.strip().split()[0].upper()
                    unit_type = SECONDARY_UNITS.get(p_type, p_type)
                    unit_number = m_sec.group(1).upper()
                else:
                    clean_parts.append(p)
            parts = clean_parts

            # Identify City / Dublin District
            if parts:
                last_token = parts[-1].strip().upper()
                if last_token in DUBLIN_DISTRICTS:
                    city_raw = DUBLIN_DISTRICTS[last_token]
                    parts = parts[:-1]
                elif last_token in IR_POST_TOWNS:
                    city_raw = last_token
                    parts = parts[:-1]

            # Check if second to last is Locality (e.g. IFSC, Grand Canal Dock)
            if parts:
                for loc in sorted(IR_LOCALITIES, key=len, reverse=True):
                    if parts and parts[-1].strip().upper() == loc:
                        dep_locality = loc
                        parts = parts[:-1]
                        break

            if not parts:
                # Everything was country / county / city / Eircode: nothing is left for a thoroughfare.
                street_line = ""
            elif len(parts) == 1:
                street_line = parts[0]
            else:
                # Part 0 could be building name if next part has digits
                if re.search(r"\d", parts[1]) and not re.search(r"\d", parts[0]):
                    building_name = parts[0].upper()
                    street_line = ", ".join(parts[1:])
                else:
                    street_line = parts[0]
                    if not dep_locality and len(parts) > 1:
                        dep_locality = parts[1].upper()

        # Handle secondary unit from s2_raw or inline street_line
        if s2_raw and not unit_number:
            # A non-empty street2 always comes back as a non-empty secondary unit.
            st1_rem, st2_norm = split_intl_secondary_unit(street_line, s2_raw)
            parts_u = st2_norm.split(None, 1)
            unit_type = parts_u[0] if parts_u else None
            unit_number = parts_u[1] if len(parts_u) > 1 else None
            street_line = st1_rem
        elif not unit_number:
            m_block = re.search(r"\b(?:BLOCK|BLK)\s+([A-Za-z0-9]+)\b", street_line, re.IGNORECASE)
            if m_block:
                unit_type = "BLOCK"
                unit_number = m_block.group(1).upper()
                street_line = street_line[:m_block.start()] + street_line[m_block.end():]
                street_line = " ".join(street_line.strip(" ,.-").split())
            else:
                st1_rem, st2_norm = split_intl_secondary_unit(street_line, "")
                if st2_norm:
                    parts_u = st2_norm.split(None, 1)
                    unit_type = parts_u[0] if parts_u else None
                    unit_number = parts_u[1] if len(parts_u) > 1 else None
                    street_line = st1_rem

        # Extract locality from street_line if present (e.g. "IFSC")
        if not dep_locality:
            # Several known localities can occur in one line ("Custom House Quay IFSC": the quay is the street, IFSC
            # the locality). Prefer the one that ends last, then the longest, and never one that is the whole line.
            candidates = []
            upper_line = street_line.upper()
            for loc in IR_LOCALITIES:
                for m_loc in re.finditer(rf"\b{re.escape(loc)}\b", upper_line):
                    candidates.append((m_loc.end(), len(loc), loc))
            for _end, _length, loc in sorted(candidates, reverse=True):
                # Ensure it's not the primary street itself (e.g. "1 IFSC" or "CUSTOM HOUSE QUAY")
                if re.match(rf"^\d+\s+{re.escape(loc)}$", upper_line) or upper_line.strip(" ,.-") == loc:
                    continue
                dep_locality = loc
                street_line = re.sub(rf"(?:,\s*|\s+)\b{re.escape(loc)}\b", "", street_line, flags=re.IGNORECASE).strip(" ,.-")
                break

        premise_cand, st_num, st_name = self.extract_premise_and_thoroughfare(street_line)
        if premise_cand and not building_name:
            building_name = premise_cand

        # Normalize city
        norm_city = city_raw.strip().upper() if city_raw else ""
        dublin_district: Optional[str] = None
        if norm_city in DUBLIN_DISTRICTS:
            # "Dublin 1" is the city Dublin plus a postal district; the district is encoded in the Eircode routing key
            # (D01), so it is folded into the city and only kept (as the dependent locality) when no Eircode carries it.
            dublin_district = DUBLIN_DISTRICTS[norm_city]
            norm_city = "DUBLIN"
            if not norm_county:
                norm_county = "CO DUBLIN"
        elif not norm_city and norm_county == "CO DUBLIN":
            norm_city = "DUBLIN"
        elif not norm_city and postal_raw:
            m_eir_rt = re.match(r"^([A-Za-z0-9]{3})", postal_raw)
            if m_eir_rt and m_eir_rt.group(1).upper() in IR_DUBLIN_ROUTING_KEYS:
                norm_city = "DUBLIN"

        if dublin_district:
            m_rk = re.match(r"^([A-Za-z0-9]{3})", postal_raw or "")
            expected_rk = "D6W" if dublin_district.endswith("6W") else f"D{int(re.sub(r'[^0-9]', '', dublin_district)[:2] or 0):02d}"
            if not (m_rk and m_rk.group(1).upper() == expected_rk) and not dep_locality:
                dep_locality = dublin_district

        # State normalization
        final_state = norm_county or (state_raw.strip().upper() if state_raw else "")
        if final_state in IR_COUNTIES:
            final_state = IR_COUNTIES[final_state]

        # Postal code normalization
        norm_postal = self.normalize_postal_code(postal_raw)

        return IrelandParsedAddressComponents(
            street_number=st_num,
            street_name=st_name,
            street_type=None,
            unit_type=unit_type,
            unit_number=unit_number,
            building_name=building_name,
            dependent_locality=dep_locality,
            city=norm_city,
            state=final_state,
            postal_code=norm_postal,
            country_iso3=self.country_iso3,
            raw_tokens=raw_tokens,
            confidence_score=0.95,
        )
