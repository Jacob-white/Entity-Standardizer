"""Sub-National Geographic Gazetteer, IANA Timezone Attribution, MNO Carrier Lookup, and TCPA Quiet-Hours Engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# US State & Territory -> IANA Timezones
US_STATE_TIMEZONES: dict[str, tuple[str, ...]] = {
    "AL": ("America/Chicago",),
    "AK": ("America/Anchorage",),
    "AZ": ("America/Phoenix",),
    "AR": ("America/Chicago",),
    "CA": ("America/Los_Angeles",),
    "CO": ("America/Denver",),
    "CT": ("America/New_York",),
    "DE": ("America/New_York",),
    "DC": ("America/New_York",),
    "FL": ("America/New_York", "America/Chicago"),
    "GA": ("America/New_York",),
    "HI": ("Pacific/Honolulu",),
    "ID": ("America/Boise", "America/Los_Angeles"),
    "IL": ("America/Chicago",),
    "IN": ("America/Indiana/Indianapolis", "America/Chicago"),
    "IA": ("America/Chicago",),
    "KS": ("America/Chicago", "America/Denver"),
    "KY": ("America/New_York", "America/Chicago"),
    "LA": ("America/Chicago",),
    "ME": ("America/New_York",),
    "MD": ("America/New_York",),
    "MA": ("America/New_York",),
    "MI": ("America/Detroit", "America/Chicago"),
    "MN": ("America/Chicago",),
    "MS": ("America/Chicago",),
    "MO": ("America/Chicago",),
    "MT": ("America/Denver",),
    "NE": ("America/Chicago", "America/Denver"),
    "NV": ("America/Los_Angeles",),
    "NH": ("America/New_York",),
    "NJ": ("America/New_York",),
    "NM": ("America/Denver",),
    "NY": ("America/New_York",),
    "NC": ("America/New_York",),
    "ND": ("America/Chicago", "America/Denver"),
    "OH": ("America/New_York",),
    "OK": ("America/Chicago",),
    "OR": ("America/Los_Angeles", "America/Boise"),
    "PA": ("America/New_York",),
    "RI": ("America/New_York",),
    "SC": ("America/New_York",),
    "SD": ("America/Chicago", "America/Denver"),
    "TN": ("America/Chicago", "America/New_York"),
    "TX": ("America/Chicago", "America/El_Paso"),
    "UT": ("America/Denver",),
    "VT": ("America/New_York",),
    "VA": ("America/New_York",),
    "WA": ("America/Los_Angeles",),
    "WV": ("America/New_York",),
    "WI": ("America/Chicago",),
    "WY": ("America/Denver",),
    # Canadian Provinces
    "ON": ("America/Toronto",),
    "QC": ("America/Montreal",),
    "BC": ("America/Vancouver",),
    "AB": ("America/Edmonton",),
    "MB": ("America/Winnipeg",),
    "SK": ("America/Regina",),
    "NS": ("America/Halifax",),
    "NB": ("America/Moncton",),
    "NL": ("America/St_Johns",),
    "YT": ("America/Whitehorse",),
}

# Country ISO-2 -> Primary IANA Timezone(s)
COUNTRY_PRIMARY_TIMEZONES: dict[str, tuple[str, ...]] = {
    "US": ("America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"),
    "CA": ("America/Toronto", "America/Edmonton", "America/Vancouver"),
    "PR": ("America/Puerto_Rico",),
    "VI": ("America/St_Thomas",),
    "GU": ("Pacific/Guam",),
    "MP": ("Pacific/Saipan",),
    "AS": ("Pacific/Pago_Pago",),
    "JM": ("America/Jamaica",),
    "DO": ("America/Santo_Domingo",),
    "BS": ("America/Nassau",),
    "BB": ("America/Barbados",),
    "BM": ("Atlantic/Bermuda",),
    "KY": ("America/Cayman",),
    "TT": ("America/Port_of_Spain",),
    "GB": ("Europe/London",),
    "JE": ("Europe/Jersey",),
    "GG": ("Europe/Guernsey",),
    "IM": ("Europe/Isle_of_Man",),
    "IE": ("Europe/Dublin",),
    "FR": ("Europe/Paris",),
    "DE": ("Europe/Berlin",),
    "ES": ("Europe/Madrid",),
    "IT": ("Europe/Rome",),
    "NL": ("Europe/Amsterdam",),
    "BE": ("Europe/Brussels",),
    "CH": ("Europe/Zurich",),
    "AT": ("Europe/Vienna",),
    "SE": ("Europe/Stockholm",),
    "NO": ("Europe/Oslo",),
    "DK": ("Europe/Copenhagen",),
    "FI": ("Europe/Helsinki",),
    "PL": ("Europe/Warsaw",),
    "PT": ("Europe/Lisbon",),
    "GR": ("Europe/Athens",),
    "CZ": ("Europe/Prague",),
    "HU": ("Europe/Budapest",),
    "RO": ("Europe/Bucharest",),
    "UA": ("Europe/Kyiv",),
    "RU": ("Europe/Moscow",),
    "TR": ("Europe/Istanbul",),
    "IL": ("Asia/Jerusalem",),
    "AE": ("Asia/Dubai",),
    "SA": ("Asia/Riyadh",),
    "ZA": ("Africa/Johannesburg",),
    "EG": ("Africa/Cairo",),
    "NG": ("Africa/Lagos",),
    "KE": ("Africa/Nairobi",),
    "IN": ("Asia/Kolkata",),
    "SG": ("Asia/Singapore",),
    "HK": ("Asia/Hong_Kong",),
    "TW": ("Asia/Taipei",),
    "CN": ("Asia/Shanghai",),
    "JP": ("Asia/Tokyo",),
    "KR": ("Asia/Seoul",),
    "AU": ("Australia/Sydney", "Australia/Melbourne", "Australia/Perth"),
    "NZ": ("Pacific/Auckland",),
    "MX": ("America/Mexico_City",),
    "BR": ("America/Sao_Paulo",),
    "AR": ("America/Argentina/Buenos_Aires",),
    "CL": ("America/Santiago",),
    "CO": ("America/Bogota",),
    "PE": ("America/Lima",),
}

# Major NANP & International Area Code -> Metro Locality Gazetteer
AREA_CODE_LOCALITIES: dict[tuple[str, str], str] = {
    # NANP (+1) Major Metro Areas
    ("1", "202"): "Washington, D.C.",
    ("1", "206"): "Seattle",
    ("1", "212"): "New York City",
    ("1", "213"): "Los Angeles",
    ("1", "214"): "Dallas",
    ("1", "215"): "Philadelphia",
    ("1", "302"): "Wilmington",
    ("1", "303"): "Denver",
    ("1", "305"): "Miami",
    ("1", "310"): "Los Angeles",
    ("1", "312"): "Chicago",
    ("1", "313"): "Detroit",
    ("1", "314"): "St. Louis",
    ("1", "404"): "Atlanta",
    ("1", "408"): "San Jose",
    ("1", "412"): "Pittsburgh",
    ("1", "415"): "San Francisco",
    ("1", "416"): "Toronto",
    ("1", "503"): "Portland",
    ("1", "504"): "New Orleans",
    ("1", "512"): "Austin",
    ("1", "514"): "Montreal",
    ("1", "602"): "Phoenix",
    ("1", "604"): "Vancouver",
    ("1", "612"): "Minneapolis",
    ("1", "613"): "Ottawa",
    ("1", "615"): "Nashville",
    ("1", "617"): "Boston",
    ("1", "619"): "San Diego",
    ("1", "650"): "San Mateo / Silicon Valley",
    ("1", "702"): "Las Vegas",
    ("1", "704"): "Charlotte",
    ("1", "713"): "Houston",
    ("1", "718"): "New York City",
    ("1", "787"): "San Juan",
    ("1", "808"): "Honolulu",
    # United Kingdom (+44)
    ("44", "20"): "London",
    ("44", "113"): "Leeds",
    ("44", "114"): "Sheffield",
    ("44", "115"): "Nottingham",
    ("44", "116"): "Leicester",
    ("44", "117"): "Bristol",
    ("44", "118"): "Reading",
    ("44", "121"): "Birmingham",
    ("44", "131"): "Edinburgh",
    ("44", "141"): "Glasgow",
    ("44", "151"): "Liverpool",
    ("44", "161"): "Manchester",
    ("44", "1534"): "Saint Helier",
    ("44", "1481"): "Saint Peter Port",
    ("44", "1624"): "Douglas",
    # Germany (+49)
    ("49", "30"): "Berlin",
    ("49", "40"): "Hamburg",
    ("49", "69"): "Frankfurt am Main",
    ("49", "89"): "Munich",
    ("49", "221"): "Cologne",
    # France (+33)
    ("33", "1"): "Paris / Île-de-France",
    # Japan (+81)
    ("81", "3"): "Tokyo",
    ("81", "6"): "Osaka",
    ("81", "45"): "Yokohama",
    # Australia (+61)
    ("61", "2"): "Sydney / Canberra",
    ("61", "3"): "Melbourne / Hobart",
    ("61", "7"): "Brisbane",
    ("61", "8"): "Perth / Adelaide",
    # Switzerland (+41)
    ("41", "44"): "Zurich",
    ("41", "22"): "Geneva",
}

# International MNO Carrier Prefix Allocation Table
CARRIER_PREFIX_MAP: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
    "DE": (
        (("151", "160", "170", "171", "175"), "Telekom Deutschland"),
        (("152", "162", "172", "173", "174"), "Vodafone Germany"),
        (("157", "159", "163", "176", "177", "178", "179"), "Telefónica O2 Germany"),
    ),
    "CN": (
        (("134", "135", "136", "137", "138", "139", "150", "151", "152", "158", "159", "188"), "China Mobile"),
        (("130", "131", "132", "155", "156", "185", "186"), "China Unicom"),
        (("133", "153", "180", "181", "189"), "China Telecom"),
    ),
    "JP": (
        (("70", "80", "90"), "NTT Docomo / KDDI / SoftBank"),
        (("50",), "IP-Phone VoIP"),
    ),
    "CH": (
        (("79",), "Swisscom"),
        (("76",), "Sunrise"),
        (("78",), "Salt Mobile"),
    ),
}


@dataclass(frozen=True)
class CallingWindowResult:
    """Result of evaluating TCPA/DNC local quiet-hours compliance for a phone number."""

    is_callable_now: bool
    timezones: tuple[str, ...]
    local_hours: tuple[int, ...]
    allowed_start_hour: int
    allowed_end_hour: int


def resolve_timezones(country_iso2: str | None, region_code: str | None) -> tuple[str, ...]:
    """Return the tuple of IANA timezone identifiers for a resolved country and state/province."""
    if region_code and region_code in US_STATE_TIMEZONES:
        return US_STATE_TIMEZONES[region_code]
    if country_iso2 and country_iso2 in COUNTRY_PRIMARY_TIMEZONES:
        return COUNTRY_PRIMARY_TIMEZONES[country_iso2]
    return ("UTC",)


def resolve_locality(calling_code: str | None, area_code: str | None) -> str | None:
    """Resolve a (calling_code, area_code) pair to a major city or metro locality name."""
    if not calling_code or not area_code:
        return None
    return AREA_CODE_LOCALITIES.get((calling_code, area_code))


def resolve_carrier_hint(country_iso2: str | None, nsn: str | None) -> str | None:
    """Resolve an international NSN prefix to its original Mobile Network Operator (MNO)."""
    if not country_iso2 or not nsn or country_iso2 not in CARRIER_PREFIX_MAP:
        return None
    for prefixes, carrier_name in CARRIER_PREFIX_MAP[country_iso2]:
        if nsn.startswith(prefixes):
            return carrier_name
    return None


def evaluate_calling_window(
    timezones: tuple[str, ...],
    utc_dt: datetime | None = None,
    allowed_start_hour: int = 8,
    allowed_end_hour: int = 21,
) -> CallingWindowResult:
    """Evaluate whether a UTC timestamp falls within legal calling hours (default 08:00-21:00 local).

    Under conservative multi-timezone TCPA rules (e.g. Florida or Texas spanning two zones),
    `is_callable_now` is True only if ALL candidate timezones for the number are currently
    within `[allowed_start_hour, allowed_end_hour)`.
    """
    now_utc = utc_dt if utc_dt is not None else datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    tz_list = timezones if timezones else ("UTC",)
    local_hours: list[int] = []
    all_allowed = True

    for tz_name in tz_list:
        local_dt = now_utc.astimezone(ZoneInfo(tz_name))
        hr = local_dt.hour
        local_hours.append(hr)
        if not (allowed_start_hour <= hr < allowed_end_hour):
            all_allowed = False

    return CallingWindowResult(
        is_callable_now=all_allowed,
        timezones=tz_list,
        local_hours=tuple(local_hours),
        allowed_start_hour=allowed_start_hour,
        allowed_end_hour=allowed_end_hour,
    )
