"""Latin American Address Grammar (MEX, BRA, COL, ARG, CHL).

Provides specialized parsing and normalization for:
- Mexico (MEX): Colonias, Fraccionamientos, Manzana/Lote, No. Ext/Int.
- Brazil (BRA): Logradouros (Rua, Avenida, etc.), Bairros, CEP formatting (01310-200).
- Colombia (COL): Carrera/Calle/Diagonal/Transversal with # XX-YY intersection syntax.
- Argentina (ARG): Calles, Avenidas, Pasajes, floor/dept (Piso/Depto), CPA 8-char postal codes.
- Chile (CHL): Comunas, Calles, Avenidas, Depto/Oficina, 7-digit postal codes.
"""

from __future__ import annotations

import re
from typing import ClassVar, Dict, List, Optional, Tuple

from address_standardizer._patterns import RE_COMMA_DOT
from address_standardizer.international.base import (
    CountryGrammar,
    ParsedAddressComponents,
    split_intl_secondary_unit,
)
from address_standardizer.international.diacritics import (
    fold_to_ascii_key,
    normalize_to_canonical_unicode,
)
from address_standardizer.international.romance import (
    _SEC_END,
    extract_units_from_part,
    make_strict_sec_regex,
    collapse_number_range,
    merge_num_barrio,
    merge_standalone_number,
    merge_units,
    parse_street2_unit,
    split_number_from_locality,
)
from address_standardizer.tables import COUNTRY_NAME_MAP, GLOBAL_METRO_TO_COUNTRY

# Road type abbreviations for Latin America (Spanish & Portuguese)
LATAM_ROAD_TYPES: Dict[str, str] = {
    # Spanish
    "AVENIDA": "AVENIDA",
    "AV": "AV",
    "AVE": "AV",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "CALLE": "CALLE",
    "C": "CALLE",
    "CLLE": "CALLE",
    "CARRERA": "CRA",
    "CRA": "CRA",
    "CR": "CRA",
    "DIAGONAL": "DIAG",
    "DIAG": "DIAG",
    "TRANSVERSAL": "TRANSV",
    "TRANSV": "TRANSV",
    "CIRCULAR": "CIRC",
    "AUTOPISTA": "AUTOPISTA",
    "AUTOP": "AUTOPISTA",
    "PASEO": "PASEO",
    "CALZADA": "CALZADA",
    "CALZ": "CALZADA",
    "CAMINO": "CAMINO",
    "CARRETERA": "CARRETERA",
    "CTRA": "CARRETERA",
    "PASAJE": "PASAJE",
    "PJE": "PASAJE",
    "CERRADA": "CERRADA",
    "CDA": "CERRADA",
    "PROLONGACION": "PROLONGACIÓN",
    "PROLONGACIÓN": "PROLONGACIÓN",
    "PROL": "PROLONGACIÓN",
    "PLAZA": "PLAZA",
    "PZ": "PLAZA",
    # Portuguese (Brazil)
    "RUA": "RUA",
    "R": "RUA",
    "ALAMEDA": "ALAMEDA",
    "AL": "ALAMEDA",
    "TRAVESSA": "TRAVESSA",
    "TV": "TRAVESSA",
    "RODOVIA": "RODOVIA",
    "ROD": "RODOVIA",
    "PRAÇA": "PRAÇA",
    "PRACA": "PRAÇA",
    "ESTRADA": "ESTRADA",
    "EST": "ESTRADA",
    "LARGO": "LARGO",
    # Peru
    "JIRÓN": "JIRÓN",
    "JIRON": "JIRÓN",
    "JR": "JIRÓN",
}

# Mexican states and federal entities (codes and uppercase names)
MX_STATES: Dict[str, str] = {
    "AGS": "AGS", "AGUASCALIENTES": "AGS",
    "BC": "BC", "BAJA CALIFORNIA": "BC",
    "BCS": "BCS", "BAJA CALIFORNIA SUR": "BCS",
    "CAMP": "CAMP", "CAMPECHE": "CAMP",
    "CHIS": "CHIS", "CHIAPAS": "CHIS",
    "CHIH": "CHIH", "CHIHUAHUA": "CHIH",
    "COAH": "COAH", "COAHUILA": "COAH",
    "COL": "COL", "COLIMA": "COL",
    "CDMX": "CDMX", "CIUDAD DE MEXICO": "CDMX", "CIUDAD DE MÉXICO": "CDMX", "DISTRITO FEDERAL": "CDMX", "DF": "CDMX",
    "DGO": "DGO", "DURANGO": "DGO",
    "GTO": "GTO", "GUANAJUATO": "GTO",
    "GRO": "GRO", "GUERRERO": "GRO",
    "HGO": "HGO", "HIDALGO": "HGO",
    "JAL": "JAL", "JALISCO": "JAL",
    "MEX": "MEX", "ESTADO DE MEXICO": "MEX", "ESTADO DE MÉXICO": "MEX", "EDO DE MEXICO": "MEX",
    "MICH": "MICH", "MICHOACAN": "MICH", "MICHOACÁN": "MICH",
    "MOR": "MOR", "MORELOS": "MOR",
    "NAY": "NAY", "NAYARIT": "NAY",
    "NL": "NL", "NUEVO LEON": "NL", "NUEVO LEÓN": "NL",
    "OAX": "OAX", "OAXACA": "OAX",
    "PUE": "PUE", "PUEBLA": "PUE",
    "QRO": "QRO", "QUERETARO": "QRO", "QUERÉTARO": "QRO",
    "Q ROO": "Q ROO", "QUINTANA ROO": "Q ROO",
    "SLP": "SLP", "SAN LUIS POTOSI": "SLP", "SAN LUIS POTOSÍ": "SLP",
    "SIN": "SIN", "SINALOA": "SIN",
    "SON": "SON", "SONORA": "SON",
    "TAB": "TAB", "TABASCO": "TAB",
    "TAMPS": "TAMPS", "TAMAULIPAS": "TAMPS",
    "TLAX": "TLAX", "TLAXCALA": "TLAX",
    "VER": "VER", "VERACRUZ": "VER",
    "YUC": "YUC", "YUCATAN": "YUC", "YUCATÁN": "YUC",
    "ZAC": "ZAC", "ZACATECAS": "ZAC",
}

# Brazilian states: two-letter UF codes and (upper-case, accent-folded or not) names.
BR_STATES = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
    "ACRE", "ALAGOAS", "AMAPÁ", "AMAPA", "AMAZONAS", "BAHIA", "CEARÁ", "CEARA", "DISTRITO FEDERAL",
    "ESPÍRITO SANTO", "ESPIRITO SANTO", "GOIÁS", "GOIAS", "MARANHÃO", "MARANHAO", "MATO GROSSO",
    "MATO GROSSO DO SUL", "MINAS GERAIS", "PARÁ", "PARA", "PARAÍBA", "PARAIBA", "PARANÁ", "PARANA",
    "PERNAMBUCO", "PIAUÍ", "PIAUI", "RIO DE JANEIRO", "RIO GRANDE DO NORTE", "RIO GRANDE DO SUL",
    "RONDÔNIA", "RONDONIA", "RORAIMA", "SANTA CATARINA", "SÃO PAULO", "SAO PAULO", "SERGIPE", "TOCANTINS",
})

# Brazilian state name (accent-folded, upper case) -> UF code, for "Curitiba - Paraná" style city/state parts.
BR_STATE_UF: Dict[str, str] = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG", "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR",
    "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP",
    "SERGIPE": "SE", "TOCANTINS": "TO",
}
_RE_CITY_DASH_NAME = re.compile(r"^(.*?)\s+-\s+(.+)$")

# Well-known Mexican cities (accent-folded, upper case) -> state name, used only when the address names no state.
# Cities whose state is ambiguous or whose state has several common spellings (the capital, Estado de México) are
# left out on purpose.
MX_CITY_STATE: Dict[str, str] = {
    "GUADALAJARA": "JALISCO", "ZAPOPAN": "JALISCO", "TLAQUEPAQUE": "JALISCO", "TONALA": "JALISCO",
    "PUERTO VALLARTA": "JALISCO",
    "MONTERREY": "NUEVO LEÓN", "SAN PEDRO GARZA GARCIA": "NUEVO LEÓN", "SAN NICOLAS DE LOS GARZA": "NUEVO LEÓN",
    "APODACA": "NUEVO LEÓN",
    "PUEBLA": "PUEBLA", "TIJUANA": "BAJA CALIFORNIA", "MEXICALI": "BAJA CALIFORNIA", "ENSENADA": "BAJA CALIFORNIA",
    "CANCUN": "QUINTANA ROO", "PLAYA DEL CARMEN": "QUINTANA ROO", "MERIDA": "YUCATÁN",
    "LEON": "GUANAJUATO", "GUANAJUATO": "GUANAJUATO", "IRAPUATO": "GUANAJUATO", "CELAYA": "GUANAJUATO",
    "QUERETARO": "QUERÉTARO", "SAN LUIS POTOSI": "SAN LUIS POTOSÍ", "AGUASCALIENTES": "AGUASCALIENTES",
    "CHIHUAHUA": "CHIHUAHUA", "CIUDAD JUAREZ": "CHIHUAHUA", "HERMOSILLO": "SONORA", "CULIACAN": "SINALOA",
    "MAZATLAN": "SINALOA", "MORELIA": "MICHOACÁN", "OAXACA": "OAXACA", "VERACRUZ": "VERACRUZ",
    "XALAPA": "VERACRUZ", "VILLAHERMOSA": "TABASCO", "TUXTLA GUTIERREZ": "CHIAPAS", "SALTILLO": "COAHUILA",
    "TORREON": "COAHUILA", "TAMPICO": "TAMAULIPAS", "REYNOSA": "TAMAULIPAS", "CUERNAVACA": "MORELOS",
    "PACHUCA": "HIDALGO", "ACAPULCO": "GUERRERO", "ZACATECAS": "ZACATECAS", "DURANGO": "DURANGO",
    "CAMPECHE": "CAMPECHE", "COLIMA": "COLIMA", "TLAXCALA": "TLAXCALA",
}

# Argentine provincial capitals and major cities -> province (same rules as MX_CITY_STATE). Buenos Aires itself is left
# out: the autonomous city (CABA) is not part of Buenos Aires Province, and the address rarely says which is meant.
AR_CITY_STATE: Dict[str, str] = {
    "ROSARIO": "SANTA FE", "SANTA FE": "SANTA FE", "RAFAELA": "SANTA FE", "VENADO TUERTO": "SANTA FE",
    "MENDOZA": "MENDOZA", "SAN RAFAEL": "MENDOZA", "CORDOBA": "CÓRDOBA", "RIO CUARTO": "CÓRDOBA",
    "VILLA MARIA": "CÓRDOBA", "VILLA CARLOS PAZ": "CÓRDOBA", "LA PLATA": "BUENOS AIRES",
    "MAR DEL PLATA": "BUENOS AIRES", "BAHIA BLANCA": "BUENOS AIRES", "TANDIL": "BUENOS AIRES",
    "QUILMES": "BUENOS AIRES", "LANUS": "BUENOS AIRES", "LOMAS DE ZAMORA": "BUENOS AIRES",
    "SAN MIGUEL DE TUCUMAN": "TUCUMÁN", "TUCUMAN": "TUCUMÁN", "SALTA": "SALTA", "SAN JUAN": "SAN JUAN",
    "RESISTENCIA": "CHACO", "NEUQUEN": "NEUQUÉN", "SANTIAGO DEL ESTERO": "SANTIAGO DEL ESTERO",
    "CORRIENTES": "CORRIENTES", "POSADAS": "MISIONES", "PARANA": "ENTRE RÍOS", "FORMOSA": "FORMOSA",
    "SAN LUIS": "SAN LUIS", "LA RIOJA": "LA RIOJA", "CATAMARCA": "CATAMARCA",
    "SAN SALVADOR DE JUJUY": "JUJUY", "JUJUY": "JUJUY", "USHUAIA": "TIERRA DEL FUEGO",
    "RIO GALLEGOS": "SANTA CRUZ", "COMODORO RIVADAVIA": "CHUBUT", "TRELEW": "CHUBUT", "RAWSON": "CHUBUT",
    "SAN CARLOS DE BARILOCHE": "RÍO NEGRO", "BARILOCHE": "RÍO NEGRO", "VIEDMA": "RÍO NEGRO",
    "SANTA ROSA": "LA PAMPA",
}

# Chilean regional capitals and major cities -> region (official "Región de ..." names).
CL_CITY_STATE: Dict[str, str] = {
    "TEMUCO": "REGIÓN DE LA ARAUCANÍA", "CONCEPCION": "REGIÓN DEL BIOBÍO", "CHILLAN": "REGIÓN DE ÑUBLE",
    "VALPARAISO": "REGIÓN DE VALPARAÍSO", "VINA DEL MAR": "REGIÓN DE VALPARAÍSO",
    "ANTOFAGASTA": "REGIÓN DE ANTOFAGASTA", "CALAMA": "REGIÓN DE ANTOFAGASTA", "LA SERENA": "REGIÓN DE COQUIMBO",
    "COQUIMBO": "REGIÓN DE COQUIMBO", "RANCAGUA": "REGIÓN DEL LIBERTADOR GENERAL BERNARDO O'HIGGINS",
    "TALCA": "REGIÓN DEL MAULE", "CURICO": "REGIÓN DEL MAULE", "ARICA": "REGIÓN DE ARICA Y PARINACOTA",
    "IQUIQUE": "REGIÓN DE TARAPACÁ", "PUERTO MONTT": "REGIÓN DE LOS LAGOS", "OSORNO": "REGIÓN DE LOS LAGOS",
    "VALDIVIA": "REGIÓN DE LOS RÍOS", "PUNTA ARENAS": "REGIÓN DE MAGALLANES Y DE LA ANTÁRTICA CHILENA",
    "COPIAPO": "REGIÓN DE ATACAMA",
}

# Peruvian regional capitals and Lima districts -> department/region
PE_CITY_STATE: Dict[str, str] = {
    "LIMA": "LIMA", "MIRAFLORES": "LIMA", "SAN ISIDRO": "LIMA", "SANTIAGO DE SURCO": "LIMA",
    "SURCO": "LIMA", "SAN BORJA": "LIMA", "BARRANCO": "LIMA", "LA MOLINA": "LIMA",
    "SAN MIGUEL": "LIMA", "MAGDALENA DEL MAR": "LIMA", "CALLAO": "CALLAO",
    "AREQUIPA": "AREQUIPA", "CUSCO": "CUSCO", "TRUJILLO": "LA LIBERTAD",
    "CHICLAYO": "LAMBAYEQUE", "PIURA": "PIURA", "HUANCAYO": "JUNÍN", "IQUITOS": "LORETO",
}

LATAM_CITY_STATE: Dict[str, Dict[str, str]] = {
    "MEX": MX_CITY_STATE,
    "ARG": AR_CITY_STATE,
    "CHL": CL_CITY_STATE,
}

# Brazilian CEP: 12345-678 or 12345678
RE_BRA_CEP = re.compile(r"^\b(\d{5})-?(\d{3})\b$")

# Argentine CPA (Código Postal Argentino): e.g. C1024CWN or 4-digit 1024
RE_ARG_CPA = re.compile(r"^\b([A-Z]\d{4}[A-Z]{3}|\d{4})\b$", re.IGNORECASE)

# Colonia / Barrio prefix (Mexico / LATAM)
RE_COLONIA = re.compile(
    r"^\b(?:COL|COLONIA|BARRIO|BO|FRACC|FRACCIONAMIENTO|RESIDENCIAL|URB|URBANIZACION)\.?\s+(.+)$",
    re.IGNORECASE,
)

# Manzana / Lote pattern (Mexico)
RE_MANZANA_LOTE = re.compile(
    r"\b(?:MZ|MZA|MANZANA)\.?\s*([A-Za-z0-9\-]+)(?:[\s,]+(?:LT|LOTE)\.?\s*([A-Za-z0-9\-]+))?\b",
    re.IGNORECASE,
)

# Secondary unit indicators (Int, Ext, Piso, Depto, Apto, Bloco, Torre, etc.)
# Keywords are whole words: "INT" never matches inside "Internacional", "ESC" never inside "Escuela".
_LATAM_SEC_TYPES = (
    r"INTERIOR|INT|EXTERIOR|EXT|DEPARTAMENTO|DEPTO|DPTO|PISO|ESC|APARTAMENTO|APTO|APT|SUITE|STE|UNIT|BLOCO|BL"
    r"|SALA|CONJUNTO|CONJ|OFICINA|OF|TORRE|EDIFICIO|EDIF"
)
RE_LATAM_SEC = re.compile(rf"(?<!\w)({_LATAM_SEC_TYPES}){_SEC_END}([A-Za-z0-9\-]+)?", re.IGNORECASE)
RE_LATAM_SEC_STRICT = make_strict_sec_regex(_LATAM_SEC_TYPES)

# Floor/door like 2º B, 2o B, 2ª B, 2° B
# The ordinal marker is º/ª/° (optionally spaced) or a lowercase "o" glued to the number ("2o B"); a letter "o"
# after a space is a word ("12 Oeste", "5 Oriente"). The door/letter is at most 3 characters ("B", "IZQ").
RE_FLOOR_DOOR = re.compile(r"\b(\d+)(?:\s*[ºª°]\s*|o\s+)([A-Za-z0-9\-]{1,3})\b", re.IGNORECASE)


class LatinAmericaGrammar(CountryGrammar):
    """Regional grammar family for Latin America (MEX, BRA, COL, ARG, CHL, PER, ECU)."""

    split_commaless_line: ClassVar[bool] = True

    country_iso3: ClassVar[str] = "MEX"
    supported_countries: ClassVar[Tuple[str, ...]] = (
        "MEX", "MEXICO", "MX",
        "BRA", "BRAZIL", "BRASIL", "BR",
        "COL", "COLOMBIA", "CO",
        "ARG", "ARGENTINA", "AR",
        "CHL", "CHILE", "CL",
        "PER", "PERU", "PERÚ",
        "ECU", "ECUADOR",
        "VEN", "VENEZUELA",
        "URY", "URUGUAY",
        "PRY", "PARAGUAY",
        "BOL", "BOLIVIA",
        "CRI", "COSTA RICA",
        "GTM", "GUATEMALA",
        "DOM", "DOMINICAN REPUBLIC",
        "CUB", "CUBA",
        "HND", "HONDURAS",
        "NIC", "NICARAGUA",
        "SLV", "EL SALVADOR",
        "HTI", "HAITI",
    )

    def normalize_postal_code(self, raw_code: str) -> str:
        """Normalize localized Latin American postal code."""
        if not raw_code:
            return ""
        clean = " ".join(raw_code.strip().upper().split())

        # Brazilian CEP formatting: XXXXX-XXX
        m_bra = RE_BRA_CEP.match(clean)
        if m_bra:
            return f"{m_bra.group(1)}-{m_bra.group(2)}"

        # Argentine CPA: 8 uppercase chars or 4 digits
        m_arg = RE_ARG_CPA.match(clean)
        if m_arg:
            return m_arg.group(1).upper()

        return clean

    def extract_premise_and_thoroughfare(
        self, street_line: str, country_iso: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract (premise, street_number, thoroughfare) from Latin American address line."""
        if not street_line:
            return None, None, None

        line = street_line.strip()

        # Colombian numbered street with intersection syntax:
        # e.g. "Calle 72 No. 10-07" or "Carrera 7 # 71-21"
        if re.search(r"\b(?:NO\.?|#|N°|NUMERO)\s*\d", line, re.IGNORECASE):
            return None, None, line.upper()

        # Latin American / Spanish prefix format:
        # Road type + Name + Number: e.g. "Av. Insurgentes Sur 1602", "Calle Mayor 45", "Av. Providencia 123"
        m_prefix = re.match(r"^([A-Za-zÀ-ÿ\.]+)\s+(.*?)\s+(\d+[A-Za-z0-9\-\/]*)$", line)
        if m_prefix:
            prefix_cand = m_prefix.group(1).strip(".").upper()
            rest_name = m_prefix.group(2).strip(" ,.")
            st_num = m_prefix.group(3).strip().upper()
            if prefix_cand in LATAM_ROAD_TYPES:
                norm_prefix = LATAM_ROAD_TYPES[prefix_cand]
                c_check = country_iso or getattr(self, "_current_country", None)
                if c_check in ("PER", "PE", "PERU") and prefix_cand in ("AV", "AVE", "AVENIDA"):
                    norm_prefix = "AVE"
                st_name = f"{norm_prefix} {rest_name.upper()} {st_num}"
                return None, st_num, st_name

        return None, None, line

    def _resolve_country_iso(self, country_cand: Optional[str]) -> str:
        if not country_cand:
            return "MEX"
        c = country_cand.strip().upper()
        if c in ("MEX", "MEXICO", "MX"):
            return "MEX"
        if c in ("BRA", "BRAZIL", "BRASIL", "BR"):
            return "BRA"
        if c in ("COL", "COLOMBIA", "CO"):
            return "COL"
        if c in ("ARG", "ARGENTINA", "AR"):
            return "ARG"
        if c in ("CHL", "CHILE", "CL"):
            return "CHL"
        from address_standardizer.international.countries import CountryRegistry
        info = CountryRegistry.get(c)
        if info and info.alpha3 in self.supported_countries:
            return info.alpha3
        return "MEX"

    def parse(self, raw_tokens: List[str], metadata: dict) -> ParsedAddressComponents:
        s1_raw = metadata.get("street1", "")
        s2_raw = metadata.get("street2", "")
        city_raw = metadata.get("city", "")
        state_raw = metadata.get("state", "")
        postal_raw = metadata.get("postal_code", "")
        country_raw = metadata.get("country", self.country_iso3)
        country_iso = self._resolve_country_iso(country_raw)

        # Only Argentina has four-digit postal codes; elsewhere a bare four-digit number is a house number.
        pc_digits = r"\d{4,8}" if country_iso == "ARG" else r"\d{5,8}"
        # Argentine CPA is "X5000" (province letter + 4 digits) or the full "X5000ABC"; a short 3-digit code opening
        # the locality part ("500 Córdoba") is a mistyped postcode there. Elsewhere only the full CPA shape is read.
        cpa = r"[A-Z]\d{4}(?:[A-Z]{3})?" if country_iso == "ARG" else r"[A-Z]\d{4}[A-Z]{3}"
        lead_digits = r"\d{3,8}" if country_iso in ("ARG", "MEX", "ECU", "PER") else r"\d{5,8}"
        lead_pc = rf"\d{{5}}(?:-\d{{3}})?|{cpa}|{lead_digits}"
        end_pc = rf"\d{{5}}(?:-\d{{3}})?|{cpa}|{pc_digits}"

        unit_type: Optional[str] = None
        unit_number: Optional[str] = None
        sec_units: List[str] = []
        dep_locality: Optional[str] = None
        street_line = s1_raw

        # Handle comma-delimited single string when city_raw is empty
        if not city_raw and s1_raw and "," in s1_raw:
            parts_comma = [p.strip() for p in s1_raw.split(",") if p.strip()]
            if len(parts_comma) >= 2 and (
                parts_comma[-1].upper() in self.supported_countries
                or parts_comma[-1].upper() in COUNTRY_NAME_MAP
            ):
                country_iso = self._resolve_country_iso(parts_comma[-1])
                parts_comma = parts_comma[:-1]

            rem_parts: List[str] = []
            for part in parts_comma:
                # Check for Colonia / Barrio
                m_col = RE_COLONIA.match(part)
                if m_col:
                    dep_locality = m_col.group(1).strip()
                    continue

                # Check for Manzana / Lote
                m_mzl = RE_MANZANA_LOTE.search(part)
                if m_mzl:
                    sec_units.append(m_mzl.group(0).upper())
                    continue

                # Check for secondary units: "Int. 401", "Piso 4", "Depto B", "Apt 12"
                part, found_units = extract_units_from_part(part, RE_LATAM_SEC, RE_LATAM_SEC_STRICT)
                sec_units.extend(found_units)
                if not part:
                    continue

                # Check if entire part is a postal code
                # (a bare four-digit part after a street part is a house number, not a postal code, outside Argentina)
                if (
                    RE_BRA_CEP.match(part.strip())
                    or (
                        RE_ARG_CPA.match(part.strip())
                        and (country_iso == "ARG" or not part.strip().isdigit() or not rem_parts)
                    )
                    or (re.match(r"^\d{5,8}$", part.strip()) and country_iso != "BRA")
                ):
                    postal_raw = part.strip()
                    continue

                rem_parts.append(part)

            if len(rem_parts) >= 2:
                last_p = rem_parts[-1]
                # Check for "São Paulo - SP"
                m_city_st = re.match(r"^(.*?)\s*-\s*([A-Za-z]{2})$", last_p)
                state_code = m_city_st.group(2).strip() if m_city_st else ""
                if not m_city_st:
                    # "Curitiba - Paraná": a spaced hyphen followed by a full Brazilian state name.
                    m_city_st = _RE_CITY_DASH_NAME.match(last_p)
                    state_code = BR_STATE_UF.get(fold_to_ascii_key(m_city_st.group(2)), "") if m_city_st else ""
                if m_city_st and state_code and not state_raw:
                    city_raw = m_city_st.group(1).strip()
                    state_raw = state_code
                    rem_parts = rem_parts[:-1]

            # "street, number - barrio, city" (Brazil / Mexico style): the number belongs to the street line and the
            # barrio is the dependent locality, so the remaining parts read "street number, city".
            # "Rua X, 123, Bairro, Cidade": the bare number part belongs to the street, not to a locality.
            merge_standalone_number(rem_parts)
            if not city_raw and not dep_locality:
                dep_locality = merge_num_barrio(rem_parts)

            if city_raw:
                if len(rem_parts) >= 2 and not dep_locality:
                    last_rem = rem_parts[-1].strip()
                    if " - " in last_rem:
                        p_dash = last_rem.split(" - ", 1)
                        num_part = p_dash[0].strip()
                        dep_locality = p_dash[1].strip()
                        street_line = f"{', '.join(rem_parts[:-1])} {num_part}".strip()
                    else:
                        dep_locality = last_rem
                        street_line = ", ".join(rem_parts[:-1])
                else:
                    street_line = ", ".join(rem_parts)
            elif len(rem_parts) >= 3:
                # e.g. "Av. Insurgentes Sur 1602", "03940 Ciudad de México", "CDMX"
                # OR "Carrera 7 # 71-21", "Bogotá 110221"
                # OR "Huérfanos 48", "Santiago", "Región Metropolitana 8320000"
                m_pc_last_start = re.match(rf"^({lead_pc})\s+(.*)$", rem_parts[-1], re.IGNORECASE)
                m_pc_last_end = re.match(rf"^(.*?)\s+({end_pc})$", rem_parts[-1], re.IGNORECASE)
                if m_pc_last_start:
                    postal_raw = m_pc_last_start.group(1)
                    city_raw = m_pc_last_start.group(2)
                    street_line = ", ".join(rem_parts[:-1])
                elif m_pc_last_end:
                    loc_name = m_pc_last_end.group(1).strip()
                    postal_raw = m_pc_last_end.group(2).strip()
                    if any(kw in loc_name.upper() for kw in ("REGION", "REGIÓN", "PROVINCIA", "ESTADO", "DPTO")):
                        state_raw = loc_name
                        city_raw = rem_parts[-2].strip()
                        street_line = ", ".join(rem_parts[:-2])
                    else:
                        city_raw = loc_name
                        street_line = ", ".join(rem_parts[:-1])
                else:
                    p_last_clean = rem_parts[-1].strip().upper()
                    if country_iso == "BRA" and p_last_clean not in BR_STATES:
                        # Brazil writes "street, bairro, cidade": the last part is the city, the one before the bairro.
                        city_raw = rem_parts[-1].strip()
                        dep_locality = rem_parts[-2].strip()
                        street_line = ", ".join(rem_parts[:-2])
                    elif p_last_clean in GLOBAL_METRO_TO_COUNTRY or p_last_clean in (
                        "BOGOTÁ", "BOGOTA", "SANTIAGO", "BUENOS AIRES", "LIMA", "CARACAS", "MONTEVIDEO", "QUITO"
                    ):
                        city_raw = rem_parts[-1].strip()
                        dep_locality = rem_parts[-2].strip()
                        street_line = ", ".join(rem_parts[:-2])
                    else:
                        state_raw = rem_parts[-1]
                        m_pc_mid_start = re.match(rf"^({lead_pc})\s+(.*)$", rem_parts[-2], re.IGNORECASE)
                        m_pc_mid_end = re.match(rf"^(.*?)\s+({end_pc})$", rem_parts[-2], re.IGNORECASE)
                        if m_pc_mid_start:
                            postal_raw = m_pc_mid_start.group(1)
                            city_raw = m_pc_mid_start.group(2)
                        elif m_pc_mid_end:
                            city_raw = m_pc_mid_end.group(1)
                            postal_raw = m_pc_mid_end.group(2)
                        else:
                            city_raw = rem_parts[-2]
                        street_line = ", ".join(rem_parts[:-2])
            elif len(rem_parts) == 2:
                # e.g. "Balcarce 50", "C1064AAB Buenos Aires" OR "Carrera 7 # 71-21", "Bogotá 110221"
                m_pc_start = re.match(rf"^({lead_pc})\s+(.*)$", rem_parts[1], re.IGNORECASE)
                m_pc_end = re.match(rf"^(.*?)\s+({end_pc})$", rem_parts[1], re.IGNORECASE)
                if m_pc_start:
                    postal_raw = m_pc_start.group(1)
                    city_raw = m_pc_start.group(2)
                elif m_pc_end:
                    city_raw = m_pc_end.group(1)
                    postal_raw = m_pc_end.group(2)
                else:
                    city_raw = rem_parts[1]
                street_line = rem_parts[0]
            elif len(rem_parts) == 1:
                p0 = rem_parts[0].strip().upper()
                if not city_raw and p0 in GLOBAL_METRO_TO_COUNTRY:
                    city_raw = rem_parts[0]
                    street_line = ""
                else:
                    street_line = rem_parts[0]
            else:
                # Every part was consumed as colonia / unit / postal code: no street line remains.
                street_line = ""

            if city_raw:
                street_line, city_raw = split_number_from_locality(street_line, city_raw)

        # Handle secondary units in s2_raw or embedded in street_line
        s2_type: Optional[str] = None
        s2_number: Optional[str] = None
        if s2_raw:
            s2_type, s2_number = parse_street2_unit(s2_raw, RE_LATAM_SEC)

        street_line = collapse_number_range(street_line)
        # Check for Brazil " - " separator (e.g. "Avenida Paulista, 1578 - Bela Vista")
        if " - " in street_line:
            p_dash = street_line.split(" - ", 1)
            street_line = p_dash[0].strip()
            if not dep_locality:
                dep_locality = p_dash[1].strip()

        # A unit written at the end of the street line ("Avenida Estela 100 Int 4") or a floor/door ("2º B")
        street_line, inline_units = extract_units_from_part(
            street_line, RE_LATAM_SEC_STRICT, RE_LATAM_SEC_STRICT, allow_whole=False
        )
        sec_units.extend(inline_units)
        st1_base, st2_base = split_intl_secondary_unit(street_line, "", native_types=True)
        if st2_base and not (sec_units or s2_type or s2_number):
            st2_parts = st2_base.split(maxsplit=1)
            unit_type = st2_parts[0]
            unit_number = st2_parts[1] if len(st2_parts) > 1 else None
        else:
            if st2_base:
                sec_units.append(st2_base)
            unit_type, unit_number = merge_units(sec_units, s2_type, s2_number)

        # Normalize thoroughfare
        _, st_num, thoroughfare = self.extract_premise_and_thoroughfare(st1_base, country_iso)

        norm_postal = self.normalize_postal_code(postal_raw)
        norm_city = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", city_raw).strip().upper())
        norm_state = normalize_to_canonical_unicode(RE_COMMA_DOT.sub(" ", state_raw).strip().upper())
        norm_dep_loc = normalize_to_canonical_unicode(dep_locality.upper()) if dep_locality else None
        if not norm_state:
            norm_state = LATAM_CITY_STATE.get(country_iso, {}).get(fold_to_ascii_key(norm_city), "")

        return ParsedAddressComponents(
            street_number=st_num,
            street_name=normalize_to_canonical_unicode(thoroughfare) if thoroughfare else None,
            unit_type=unit_type,
            unit_number=unit_number,
            dependent_locality=norm_dep_loc,
            city=norm_city if norm_city else None,
            state=norm_state if norm_state else None,
            postal_code=norm_postal if norm_postal else None,
            country_iso3=country_iso,
            raw_tokens=raw_tokens,
        )
