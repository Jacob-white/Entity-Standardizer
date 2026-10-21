# Complete API Reference 📖

This document specifies the public Python API, CLI commands, HTTP service endpoints, and Model Context Protocol (MCP) tools for `phone_standardizer`.

---

## 1. Core Data Models (`phone_standardizer.models`)

### `StandardizedPhone`
Immutable dataclass representing a standardized telephone record:
- `raw_input: str` — Original unmodified input string.
- `e164: str | None` — Canonical ITU-T E.164 format (`+14155552671`).
- `national: str | None` — ITU-T E.123 localized national format (`(415) 555-2671` or `020 7946 0912`).
- `international: str | None` — ITU-T E.123 readable international format (`+1 415-555-2671`).
- `rfc3966: str | None` — IETF RFC 3966 URI (`tel:+1-415-555-2671;ext=104`).
- `country_calling_code: str | None` — Numeric ITU country calling code (`"1"`, `"44"`, `"81"`).
- `country_iso2: str | None` — ISO-3166-1 alpha-2 country code (`"US"`, `"GB"`, `"PR"`).
- `country_iso3: str | None` — ISO-3166-1 alpha-3 country code (`"USA"`, `"GBR"`, `"PRI"`).
- `country_name: str | None` — Official country/territory name.
- `national_significant_number: str | None` — Digits following the country calling code (`NSN`).
- `area_code: str | None` — Extracted geographic area code / NPA or national destination code.
- `subscriber_number: str | None` — Local subscriber digits.
- `extension: str | None` — Normalized numeric extension if present.
- `vanity_alias: str | None` — Uppercase alphanumeric vanity string if decoded (`"1-800-FLOWERS"`).
- `region_code: str | None` — State, province, or territory code (e.g., `"CA"`, `"NY"`, `"ON"`).
- `line_type: str` — `PhoneLineType` classification (`"MOBILE"`, `"FIXED_LINE"`, `"TOLL_FREE"`, `"PREMIUM_RATE"`, `"VOIP"`, etc.).
- `is_valid: bool` — Whether the phone number passes strict dial-plan length, prefix, and range validation.
- `is_possible: bool` — Whether the digit length is possible for the target jurisdiction.
- `phone_key: str | None` — Deterministic deduplication key (`E.164` base).
- `phone_ext_key: str | None` — Deterministic deduplication key including extension (`+14155552671#104`).
- `confidence: float` — Composite confidence score (`0.0` to `1.0`).
- `routing_tier: str` — `"AUTO_PASS"`, `"FUZZY_REVIEW"`, or `"MANUAL_STEWARDSHIP"`.
- `risk_flags: tuple[str, ...]` — Diagnostic flags (`"FICTITIOUS_RANGE"`, `"REPEATING_DIGITS"`, `"PREMIUM_RATE_IRSF_RISK"`, etc.).
- `healing_actions: tuple[str, ...]` — Transformations applied (`"VANITY_DECODED"`, `"REDUNDANT_TRUNK_STRIPPED"`, `"LEGACY_MEXICO_MOBILE_1_STRIPPED"`, etc.).

---

## 2. Core Functions (`phone_standardizer`)

- `standardize_phone(raw_phone: str | None, country: str | None = None, default_country: str = "US", address_context: Any = None) -> StandardizedPhone`
- `validate_phone(raw_phone: str | None, country: str | None = None, default_country: str = "US") -> bool`
- `format_e164(raw_phone: str | None, country: str | None = None, default_country: str = "US") -> str | None`
- `mask_phone(raw_phone: str | None, strategy: str = "partial", country: str | None = None) -> str`
- `batch_standardize_phones(records: Iterable[str | dict[str, Any]], default_country: str = "US") -> list[StandardizedPhone]`
- `stream_standardize_csv(input_path: str, output_path: str, phone_col: str = "phone", country_col: str | None = None, default_country: str = "US") -> int`
