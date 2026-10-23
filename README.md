# Entity Standardizer 🏛️📞

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/Jacob-white/Entity-Standardizer)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/Jacob-white/Entity-Standardizer)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/Jacob-white/Entity-Standardizer)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Standards](https://img.shields.io/badge/Standards-USPS%20Pub%2028%20%7C%20UPU%20S42%20%7C%20ITU--T%20E.164%20%7C%20E.123%20%7C%20RFC%203966-orange.svg)](https://www.itu.int/rec/T-REC-E.164)

A unified, high-performance multi-national **Entity, Address, and Telephone Standardization, Bidirectional Cross-Healing, and Entity Resolution Engine** (`entity_standardizer`, `address_standardizer`, and `phone_standardizer`) with an optional FastAPI HTTP service, Model Context Protocol (MCP) server, and native Rust PyO3 acceleration. It parses, cleans, cross-heals, validates, and deduplicates physical addresses (**USPS Publication 28 / UPU S42 / ISO 19160-4**) and telephone numbers (**ITU-T E.164 / E.123 / RFC 3966 / NANP**) across all **249 ISO-3166-1 countries and territories** without external API fees or vendor lock-in. Owned and maintained by **HobbyHabbit LLC** under the **MIT License**.

---

## 📚 Documentation & Quickstarts

- **[5-Minute Quickstart Guide](docs/quickstart.md)** — Step-by-step onboarding for joint contact standardization, address & phone parsing, international E.164/E.123/RFC 3966 formatting, NANP attribution, streaming batch, CLI, and HTTP service.
- **[Complete API Reference](docs/api_reference.md)** — Reference for Python models, functions, CLI commands, microservice endpoints, and MCP tools.
- **[Global Telephony Enterprise Blueprint](docs/GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md)** — Master architectural specification and global dial-plan roadmap.
- **[Multi-Platform Client SDKs](sdks/README.md)** — Client library specifications for TypeScript/React, .NET, and Go.
- **[Security Policy & Anti-Fraud Guide](SECURITY.md)** — Threat model, ReDoS prevention, International Revenue Share Fraud (IRSF) guardrails, and vulnerability disclosure procedures.
- **[Architectural Specifications Index](docs/README.md)** — Engineering roadmaps and design notes.

---

## 🌟 Highlights & Enterprise Capabilities

1. **Unified Package Namespace (`entity_standardizer`, `address_standardizer`, `phone_standardizer`)**:
   - Import everything from `entity_standardizer` (`standardize_contact`, `standardize_entity`, `standardize_address`, `standardize_phone`, `cluster_contact_records`) while preserving 100% backward compatibility for `import address_standardizer` and `import phone_standardizer`.
2. **Bidirectional Address ↔ Phone Cross-Healing (`standardize_contact` / `standardize_entity`)**:
   - **Phone Rescue from Address Lines** (`PHONE_RESCUED_FROM_ADDRESS_FIELD`): Extracts misplaced telephone numbers from `street1` or `street2` (`"350 Fifth Ave Tel: (212) 555-2368"`) before address standardization.
   - **Address Country Inference from Phone** (`ADDRESS_COUNTRY_INFERRED_FROM_PHONE`): Uses international E.164 calling codes (`+44`, `+33`, `+81`) to disambiguate international addresses when country is omitted.
   - **US ZIP/State Mismatch Healing from Phone NPA** (`ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA`): Resolves conflicting US state vs. ZIP5 pairs when the phone's NANP area code confirms the true state.
   - **7-Digit Local & Domestic Phone Healing from Standardized Address** (`PHONE_HEALED_FROM_STANDARDIZED_ADDRESS`): Uses the standardized address's inferred state/country to heal 7-digit US local numbers and domestic international numbers.
3. **USPS Publication 28, UPU S42 & Spatial Rooftop Address Standardization**:
   - Deterministic street suffix/directional/secondary unit normalization, typo recovery, DPV/RDI/CMRA delivery intelligence, registered-agent corporate hub detection, H3 spatial indexing, and deterministic `normalized_address_key`, `building_key`, and `phonetic_key` generation.
4. **Universal 249 ISO-3166-1 Country & ITU-T Dial-Plan Registry**:
   - Deterministic dial-plan metadata (`CountryDialPlan`) for every ISO-3166-1 jurisdiction, producing **ITU-T E.164**, **ITU-T E.123 National**, **ITU-T E.123 International**, and **IETF RFC 3966 URI** formats alongside NANP 25-country / 50-state attribution.
5. **Trunk, Legacy Mobile Prefix & ITU-T E.161 Vanity Healer**:
   - Strips redundant `(0)` or leading `0` trunk prefixes, heals Mexican `+52 1` and Argentine `15` $\to$ `+54 9` mobile prefixes, folds Unicode digits, decodes vanity numbers (`1-800-FLOWERS`), and separates extensions.
6. **Fraud, IRSF & Synthetic Range Guardrails**:
   - Detects fictitious ranges (`555-0100`..`0199`, UK Ofcom TV numbers), repeating/sequential bogus digits, premium-rate IRSF risk (`PREMIUM_RATE_IRSF_RISK`), and cross-border address/phone mismatches (`ADDRESS_COUNTRY_MISMATCH`).
7. **Entity Resolution & Multi-Platform Ecosystem**:
   - Clusters noisy contact records (`cluster_contact_records`, `compare_phones`, `deduplicate_phones`), provides `mask_phone()` privacy redaction, lazy-loaded Apache Arrow / Polars / DuckDB vectorized UDFs, and parity-tested TypeScript/React, Go, and .NET SDKs.

---

## 🚀 Quickstart

```python
from entity_standardizer import (
    standardize_address,
    standardize_contact,
    standardize_phone,
    mask_phone,
)

# 1. Joint Contact Standardization & Bidirectional Cross-Healing
contact = standardize_contact(
    street1="350 Fifth Ave Tel: 555-2368",
    city="New York",
    postal_code="10118",
)
assert contact.address.street1 == "350 5TH AVE"
assert contact.address.state == "NY"
assert contact.phone.e164 == "+12125552368"
assert "PHONE_RESCUED_FROM_ADDRESS_FIELD" in contact.cross_healing_actions
assert "PHONE_HEALED_FROM_STANDARDIZED_ADDRESS" in contact.cross_healing_actions

# 2. Standalone Address Standardization (USPS Pub 28 / UPU S42)
addr = standardize_address("1600 Pennsylvania Ave NW", city="Washington", state="DC", postal_code="20500")
assert addr.street1 == "1600 PENNSYLVANIA AVE NW"
assert addr.normalized_address_key is not None

# 3. Vanity Phone + Embedded Extension
rec = standardize_phone("Primary Office: 1-800-FLOWERS ext. 104")
assert rec.e164 == "+18003569377"
assert rec.national == "(800) 356-9377"
assert rec.international == "+1 800-356-9377"
assert rec.rfc3966 == "tel:+1-800-356-9377;ext=104"
assert rec.extension == "104"
assert rec.vanity_alias == "1-800-FLOWERS"
assert rec.line_type == "TOLL_FREE"

# 4. Privacy Masking (partial, redact, hash)
assert mask_phone("+1 (415) 555-2671", strategy="partial") == "+1******2671"
```

---

## 💻 Command Line Interface (CLI), FastAPI Microservice & MCP Tools

```bash
# Joint contact standardization (Address + Phone cross-healing)
entity-standardizer contact --street1 "350 Fifth Ave" --city "New York" --postal-code "10118" --phone "555-2368"

# Standardize a physical address
entity-standardizer address "350 Fifth Ave" --city "New York" --state "NY" --postal-code "10118"

# Parse a single phone number
entity-standardizer parse "+44 (0) 20 7946 0912 ext 42"

# Inspect country dial-plan metadata
entity-standardizer country JP

# Stream-process a CSV file
entity-standardizer batch input.csv output.csv --phone-col phone --country-col country

# Run the FastAPI HTTP service (/v1/standardize, /v1/address, /v1/contact, /v1/compare, /v1/deduplicate, /v1/batch)
uvicorn phone_standardizer.server:app --host 0.0.0.0 --port 8000

# Run the Model Context Protocol (MCP) server (standardize_phone, standardize_address, standardize_contact, ...)
entity-standardizer-mcp
```

---

## 📄 License

Owned and maintained by **HobbyHabbit LLC** under the **[MIT License](LICENSE)**.

