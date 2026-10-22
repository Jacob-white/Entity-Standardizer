# Changelog

All notable changes to **Phone Standardizer** will be documented in this file.

## [1.1.0] - 2026-10-21

### Added
- **Sub-National Geographic, Timezone & Carrier MNO Intelligence** (`phone_standardizer/intelligence.py`):
  - `resolve_timezones`: Maps all 50 US states, DC, Canadian provinces, and global ISO countries to IANA timezones (`America/Los_Angeles`, `Europe/London`, `Asia/Tokyo`, etc.).
  - `resolve_locality`: Metro area & city gazetteer for major NANP and international area codes.
  - `resolve_carrier_hint`: International Mobile Network Operator (MNO) prefix attribution.
  - `evaluate_calling_window`: Conservative multi-timezone TCPA/DNC local quiet-hours evaluator (`08:00–21:00` local time).
- **Multi-Tier Caching Engine** (`phone_standardizer/cache.py`): Thread-safe L1 `LRUCache` + persistent L2 `SQLiteCache` (WAL mode) with `MultiTierCache`, `configure_cache`, `get_cache_stats`, and `clear_cache`.
- **Stewardship Audit Ledger & Explainability** (`phone_standardizer/audit.py`): `explain_phone()` diagnostic report, `/v1/explain` HTTP endpoint, `explain_phone` MCP tool, and SQLite-backed `PhoneStewardshipLedger`.
- **Brazil Legacy 8-to-9 Digit Mobile Healer & Free-Text Bulk Extractor**: `HealingAction.BRAZIL_MOBILE_9_INSERTED` and `extract_phones_from_text()`.
- **Columnar Arrow/Polars/DuckDB UDFs & Multi-Platform SDKs**: `phone_standardizer/arrow.py`, `src/lib.rs` batch E.164 acceleration, and TypeScript/React, Go, and .NET client SDKs.

## [1.0.0] - 2026-10-21

### Added
- **Universal 249 ISO-3166-1 Country & ITU-T E.164 Dial-Plan Registry** (`phone_standardizer/registry.py`, `registry_data.py`).
- **Complete NANP (`+1`) 25-Country & US/Canada State/Province NPA Attribution** (`phone_standardizer/nanp.py`).
- **Multi-Standard Formatting Engine**: ITU-T E.164, ITU-T E.123 National & International, and IETF RFC 3966 (`tel:` URI).
- **Trunk & Legacy Mobile Prefix Healer**: Redundant `(0)` trunk stripping, Mexico `+52 1` mobile prefix healing, Argentina `15` mobile prefix healing, Unicode numeral folding, ITU-T E.161 vanity keypad decoding, and extension extraction.
- **Fraud, IRSF & Synthetic Range Guardrails** (`phone_standardizer/confidence.py`) with composite confidence scoring and routing tiers (`AUTO_PASS`, `FUZZY_REVIEW`, `MANUAL_STEWARDSHIP`).
- **CLI, FastAPI HTTP Microservice, MCP Server, Batch Streaming, and Rust PyO3 Native Extension**.
