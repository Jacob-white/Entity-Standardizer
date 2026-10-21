# Changelog

All notable changes to **Phone Standardizer** will be documented in this file.

## [1.0.0] - 2026-10-21

### Added
- **Universal 249 ISO-3166-1 Country & ITU-T E.164 Dial-Plan Registry** (`phone_standardizer/registry.py`, `registry_data.py`).
- **Complete NANP (`+1`) 25-Country & US/Canada State/Province NPA Attribution** (`phone_standardizer/nanp.py`).
- **Multi-Standard Formatting Engine**: ITU-T E.164, ITU-T E.123 National & International, and IETF RFC 3966 (`tel:` URI).
- **Trunk & Legacy Mobile Prefix Healer**: Redundant `(0)` trunk stripping, Mexico `+52 1` mobile prefix healing, Argentina `15` mobile prefix healing, Unicode numeral folding, ITU-T E.161 vanity keypad decoding, and extension extraction.
- **Fraud, IRSF & Synthetic Range Guardrails** (`phone_standardizer/confidence.py`) with composite confidence scoring and routing tiers (`AUTO_PASS`, `FUZZY_REVIEW`, `MANUAL_STEWARDSHIP`).
- **CLI, FastAPI HTTP Microservice, MCP Server, Batch Streaming, and Rust PyO3 Native Extension**.
