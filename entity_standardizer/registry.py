"""Country Dial-Plan Registry and Calling Code Resolver across 249 ISO-3166-1 Jurisdictions."""

from __future__ import annotations

from entity_standardizer.models import CountryDialPlan
from entity_standardizer.nanp import resolve_nanp_npa
from entity_standardizer.registry_data import COUNTRY_DIAL_PLANS, SUPPLEMENTAL_DIAL_PLANS

# Primary country for shared calling codes when no sub-area prefix matches
PRIMARY_COUNTRY_FOR_CALLING_CODE: dict[str, str] = {
    "1": "US",
    "7": "RU",
    "39": "IT",
    "44": "GB",
    "47": "NO",
    "61": "AU",
    "64": "NZ",
    "212": "MA",
    "262": "RE",
    "290": "SH",
    "358": "FI",
    "500": "FK",
    "590": "GP",
    "599": "CW",
    "672": "NF",
}

# Common aliases to ISO-2
COUNTRY_ALIASES: dict[str, str] = {
    "UK": "GB",
    "GREAT BRITAIN": "GB",
    "ENGLAND": "GB",
    "SCOTLAND": "GB",
    "WALES": "GB",
    "NORTHERN IRELAND": "GB",
    "UNITED KINGDOM": "GB",
    "USA": "US",
    "UNITED STATES OF AMERICA": "US",
    "UNITED STATES": "US",
    "U.S.A.": "US",
    "U.S.": "US",
    "NEW YORK": "US",
    "UAE": "AE",
    "SOUTH KOREA": "KR",
    "KOREA, SOUTH": "KR",
    "REPUBLIC OF KOREA": "KR",
    "NORTH KOREA": "KP",
    "RUSSIA": "RU",
    "RUSSIAN FEDERATION": "RU",
    "VIETNAM": "VN",
    "TAIWAN": "TW",
    "TAIWAN, REPUBLIC OF CHINA": "TW",
    "BRITISH VIRGIN ISLANDS": "VG",
    "VIRGIN ISLANDS, BRITISH": "VG",
    "U.S. VIRGIN ISLANDS": "VI",
    "VIRGIN ISLANDS, U.S.": "VI",
    "BAHAMAS, THE": "BS",
    "THE BAHAMAS": "BS",
    "TURKEY": "TR",
    "TURKIYE": "TR",
    "CZECH REPUBLIC": "CZ",
    "BOLIVIA": "BO",
    "VENEZUELA": "VE",
    "MACAU": "MO",
    "MACAO": "MO",
    "MACAU SAR": "MO",
    "HONG KONG SAR": "HK",
    "GEORGIA/GRUZINSKAYA": "GE",
    "IVORY COAST": "CI",
    "COTE D'IVOIRE": "CI",
    "CURACAO": "CW",
    "REUNION": "RE",
    "BRUNEI": "BN",
    "LAOS": "LA",
    "MOLDOVA": "MD",
    "SYRIA": "SY",
    "TANZANIA": "TZ",
    "PALESTINE": "PS",
    "KOSOVO": "XK",
}


class CountryDialRegistry:
    """Indexed registry of all 249 ISO-3166-1 country dial plans and ITU calling codes."""

    _ALL_INDEXED: tuple[CountryDialPlan, ...] = COUNTRY_DIAL_PLANS + SUPPLEMENTAL_DIAL_PLANS
    _BY_ISO2: dict[str, CountryDialPlan] = {p.iso2: p for p in _ALL_INDEXED}
    _BY_ISO3: dict[str, CountryDialPlan] = {p.iso3: p for p in _ALL_INDEXED}
    _BY_NUMERIC: dict[str, CountryDialPlan] = {p.numeric: p for p in COUNTRY_DIAL_PLANS}
    _BY_NAME: dict[str, CountryDialPlan] = {p.name.upper(): p for p in _ALL_INDEXED}
    _BY_CALLING_CODE: dict[str, list[CountryDialPlan]] = {}

    for _plan in _ALL_INDEXED:
        _BY_CALLING_CODE.setdefault(_plan.calling_code, []).append(_plan)

    # Sorted calling codes longest-first (3 -> 2 -> 1 digits) for greedy prefix matching
    _SORTED_CALLING_CODES: tuple[str, ...] = tuple(
        sorted(_BY_CALLING_CODE.keys(), key=lambda k: (-len(k), k))
    )

    @classmethod
    def get(cls, identifier: str | None) -> CountryDialPlan | None:
        """Lookup a CountryDialPlan by ISO-2, ISO-3, numeric code, or country name."""
        if not identifier:
            return None
        key = " ".join(identifier.strip().upper().split())
        if not key:
            return None
        if key in cls._BY_ISO2:
            return cls._BY_ISO2[key]
        if key in cls._BY_ISO3:
            return cls._BY_ISO3[key]
        if key in COUNTRY_ALIASES:
            return cls._BY_ISO2[COUNTRY_ALIASES[key]]
        if key in cls._BY_NUMERIC:
            return cls._BY_NUMERIC[key]
        if key in cls._BY_NAME:
            return cls._BY_NAME[key]
        return None

    @classmethod
    def all_plans(cls) -> tuple[CountryDialPlan, ...]:
        """Return all 249 ISO-3166-1 CountryDialPlan entries."""
        return COUNTRY_DIAL_PLANS

    @classmethod
    def match_calling_code(
        cls,
        digits_after_plus: str,
        hint_iso2: str | None = None,
    ) -> tuple[CountryDialPlan | None, str, str | None, bool]:
        """Match leading ITU calling code from an international digit string.

        Returns (dial_plan, national_significant_number, region_code, is_recognized_sub_area).
        """
        for cc in cls._SORTED_CALLING_CODES:
            if digits_after_plus.startswith(cc):
                nsn = digits_after_plus[len(cc):]
                plans = cls._BY_CALLING_CODE[cc]
                if cc == "1":
                    if (
                        len(nsn) != 10
                        and hint_iso2
                        and hint_iso2 in cls._BY_ISO2
                        and cls._BY_ISO2[hint_iso2].calling_code == "1"
                    ):
                        return cls._BY_ISO2[hint_iso2], nsn, None, True
                    # NANP: use 3-digit NPA to resolve exact territory & state/province
                    npa = nsn[:3]
                    fallback = hint_iso2 if hint_iso2 and hint_iso2 in cls._BY_ISO2 else "US"
                    iso2, region_code, recognized_npa = resolve_nanp_npa(npa, fallback_iso2=fallback)
                    return cls._BY_ISO2[iso2], nsn, region_code, recognized_npa
                if cc == "44":
                    # UK & Crown Dependencies (Jersey, Guernsey, Isle of Man)
                    clean_nsn = nsn[1:] if nsn.startswith("0") and len(nsn) >= 10 else nsn
                    if clean_nsn.startswith((
                        "1534", "7797", "7700", "7829", "7509", "7937",
                        "800735", "800781", "808901", "901810", "701511",
                    )):
                        return cls._BY_ISO2["JE"], nsn, "JE", True
                    if clean_nsn.startswith(("1481", "7781", "7839", "7911")):
                        return cls._BY_ISO2["GG"], nsn, "GG", True
                    if clean_nsn.startswith((
                        "1624", "7624", "7524", "7924", "74576", "808162", "901624",
                    )):
                        return cls._BY_ISO2["IM"], nsn, "IM", True
                    if hint_iso2 in ("JE", "GG", "IM") and clean_nsn.startswith((
                        "3", "5", "70", "76", "8", "9",
                    )):
                        return cls._BY_ISO2[hint_iso2], nsn, hint_iso2, True
                    return cls._BY_ISO2["GB"], nsn, None, True
                if cc == "7":
                    if nsn.startswith(("6", "7")) or (hint_iso2 == "KZ" and nsn.startswith("8")):
                        return cls._BY_ISO2["KZ"], nsn, None, True
                    return cls._BY_ISO2["RU"], nsn, None, True
                if cc == "39" and nsn.startswith("06698"):
                    return cls._BY_ISO2["VA"], nsn, None, True
                if cc == "47" and nsn.startswith("79"):
                    return cls._BY_ISO2["SJ"], nsn, None, True
                if cc == "61":
                    clean_61 = nsn[1:] if nsn.startswith("0") and len(nsn) >= 10 else nsn
                    if clean_61.startswith("89164"):
                        return cls._BY_ISO2["CX"], nsn, None, True
                    if clean_61.startswith("89162"):
                        return cls._BY_ISO2["CC"], nsn, None, True
                if cc == "358":
                    clean_358 = nsn[1:] if nsn.startswith("0") else nsn
                    if clean_358.startswith("18"):
                        return cls._BY_ISO2["AX"], nsn, None, True
                if cc == "212":
                    clean_212 = nsn[1:] if nsn.startswith("0") else nsn
                    if clean_212.startswith(("5288", "5289")):
                        return cls._BY_ISO2["EH"], nsn, None, True
                if cc == "262":
                    clean_262 = nsn[1:] if nsn.startswith("0") else nsn
                    if clean_262.startswith(("269", "639")):
                        return cls._BY_ISO2["YT"], nsn, None, True
                if cc == "599" and nsn.startswith(("3", "4", "7")):
                    return cls._BY_ISO2["BQ"], nsn, None, True
                if cc == "290" and nsn.startswith("8"):
                    return cls._BY_ISO2["TA"], nsn, None, True
                if len(plans) == 1:
                    return plans[0], nsn, None, True
                if hint_iso2:
                    for p in plans:
                        if p.iso2 == hint_iso2:
                            return p, nsn, None, True
                primary_iso = PRIMARY_COUNTRY_FOR_CALLING_CODE.get(cc, plans[0].iso2)
                return cls._BY_ISO2[primary_iso], nsn, None, True
        return None, digits_after_plus, None, False


def get_dial_plan(identifier: str | None) -> CountryDialPlan | None:
    """Return the CountryDialPlan for a country code or name."""
    return CountryDialRegistry.get(identifier)


def normalize_country_iso2(identifier: str | None) -> str | None:
    """Normalize any country identifier (ISO-2, ISO-3, numeric, name, alias) to ISO-2."""
    plan = CountryDialRegistry.get(identifier)
    return plan.iso2 if plan else None

