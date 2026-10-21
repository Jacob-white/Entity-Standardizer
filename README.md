# Phone Standardizer 📞

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/Jacob-white/Phone-Standardizer)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/Jacob-white/Phone-Standardizer)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/Jacob-white/Phone-Standardizer)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Standards](https://img.shields.io/badge/Standards-ITU--T%20E.164%20%7C%20E.123%20%7C%20RFC%203966%20%7C%20NANP-orange.svg)](https://www.itu.int/rec/T-REC-E.164)

A standalone, zero-dependency multi-national telephone number standardization, ITU-T E.164/E.123/RFC 3966 formatting, North American Numbering Plan (`+1` NANP) jurisdiction/state attribution, line-type classification, and telephony entity linkage library (with an optional FastAPI HTTP service, MCP server, and native Rust PyO3 acceleration). It parses, cleans, heals, validates, and deduplicates phone numbers across all **249 ISO-3166-1 countries and territories** without external API fees or vendor lock-in. Owned and maintained by **HobbyHabbit LLC** under the **MIT License**.

---

## 📚 Documentation & Quickstarts

- **[5-Minute Quickstart Guide](docs/quickstart.md)** — Step-by-step onboarding for phone parsing, international E.164/E.123/RFC 3966 formatting, NANP attribution, streaming batch, CLI, and HTTP service.
- **[Complete API Reference](docs/api_reference.md)** — Reference for Python models, functions, CLI commands, microservice endpoints, and MCP tools.
- **[Global Telephony Enterprise Blueprint](docs/GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md)** — Master architectural specification and global dial-plan roadmap.
- **[Multi-Platform Client SDKs](sdks/README.md)** — Client library specifications for TypeScript/React, .NET, and Go.
- **[Security Policy & Anti-Fraud Guide](SECURITY.md)** — Threat model, ReDoS prevention, International Revenue Share Fraud (IRSF) guardrails, and vulnerability disclosure procedures.
- **[Architectural Specifications Index](docs/README.md)** — Engineering roadmaps and design notes.

---

## 🌟 Highlights & Enterprise Capabilities

1. **Universal 249 ISO-3166-1 Country & ITU-T Dial-Plan Registry**: Deterministic dial-plan metadata (`CountryDialPlan`) for every ISO-3166-1 jurisdiction, including calling codes, IDD exit prefixes (`011`, `00`, `0011`, `010`, `810`), national trunk prefixes, NSN length constraints, and line-type prefix allocations.
2. **Multi-Standard Output Formatting**: Every valid phone number simultaneously produces canonical **ITU-T E.164** (`+14155552671`), **ITU-T E.123 National** (`(415) 555-2671` or `020 7946 0912`), **ITU-T E.123 International** (`+1 415-555-2671`), and **IETF RFC 3966 URI** (`tel:+1-415-555-2671;ext=104`).
3. **Complete NANP (`+1`) 25-Country & US/CA State/Province Attribution**: Resolves 3-digit NANP area codes (`NPA`) across all 50 US states, DC, Canadian provinces, and 23 Caribbean/Pacific nations (`PR`, `JM`, `DO`, `BS`, `BB`, `KY`, `BM`, `GU`, `VI`, etc.).
4. **Trunk & Legacy Mobile Prefix Healer**:
   - Strips redundant `(0)` or leading `0` trunk prefixes inside international numbers (`+44 (0) 20 7946 0912` $\to$ `+442079460912`).
   - Heals deprecated Mexican `+52 1` 11-digit mobile numbers into canonical 10-digit `+52` E.164.
   - Heals Argentine domestic `15` mobile prefixes into international `+54 9` format.
   - Folds Full-Width CJK, Arabic-Indic, Eastern Arabic, and Devanagari numerals to ASCII.
5. **ITU-T E.161 Vanity Decoding & Extension Extraction**: Converts alphanumeric vanity numbers (`1-800-FLOWERS` $\to$ `+18003569377`) while preserving `vanity_alias="1-800-FLOWERS"`, and cleanly separates extensions (`ext. 402`, `x402`, `#402`, `;ext=402`).
6. **Fraud, IRSF & Synthetic Range Guardrails**: Detects fictitious ranges (`555-0100`..`0199`, UK Ofcom TV numbers), repeating/sequential bogus digits, and high-risk premium-rate ranges (`PREMIUM_RATE_IRSF_RISK`), assigning composite confidence scores and routing tiers (`AUTO_PASS`, `FUZZY_REVIEW`, `MANUAL_STEWARDSHIP`).
7. **Native Portfolio Interoperability**: Accepts `Address-Standardizer` records (`address_context`) to disambiguate national phone numbers and provides `mask_phone()` privacy redaction compatible with `Query-Builder` CLAC policies.

---

## 🚀 Quickstart

```python
from phone_standardizer import standardize_phone, mask_phone

# 1. Vanity number + embedded extension
rec = standardize_phone("Primary Office: 1-800-FLOWERS ext. 104")
assert rec.e164 == "+18003569377"
assert rec.national == "(800) 356-9377"
assert rec.international == "+1 800-356-9377"
assert rec.rfc3966 == "tel:+1-800-356-9377;ext=104"
assert rec.extension == "104"
assert rec.vanity_alias == "1-800-FLOWERS"
assert rec.line_type == "TOLL_FREE"

# 2. UK number with redundant (0) trunk prefix
uk = standardize_phone("+44 (0) 20 7946 0912")
assert uk.e164 == "+442079460912"
assert uk.national == "020 7946 0912"
assert uk.country_iso2 == "GB"

# 3. Privacy masking (partial, redact, hash)
assert mask_phone("+1 (415) 555-2671", strategy="partial") == "+1******2671"
```

---

## 💻 Command Line Interface (CLI) & Microservice

```bash
# Parse a single phone number
phone-standardizer parse "+44 (0) 20 7946 0912 ext 42"

# Inspect country dial-plan metadata
phone-standardizer country JP

# Stream-process a CSV file
phone-standardizer batch input.csv output.csv --phone-col phone --country-col country

# Run the FastAPI HTTP service
uvicorn phone_standardizer.server:app --host 0.0.0.0 --port 8000
```

---

## 📄 License

Owned and maintained by **HobbyHabbit LLC** under the **[MIT License](LICENSE)**.
