# Entity Standardizer Documentation & Technical Specifications 📚

**Entity Standardizer** (`entity_standardizer`, `address_standardizer`, and `phone_standardizer`) is owned and maintained by **HobbyHabbit LLC** under the **MIT License**. This directory contains the developer guides, API references, operational manuals, and architectural blueprints for the unified multi-pillar platform.

---

## Developer Guides & Reference

- **[5-Minute Quickstart Guide](quickstart.md)** — Step-by-step onboarding for joint contact standardization, company/person/web normalization, USPS Pub 28 / UPU S42 address standardization, ITU-T E.164/E.123/RFC 3966 telephony parsing, entity comparison & deduplication, Arrow/Polars/DuckDB SQL UDFs, CLI, and HTTP service.
- **[Complete API Reference](api_reference.md)** — Reference for all Python models, functions, cross-healing enums, CLI commands, 18 FastAPI endpoints, 17 MCP tools, and Arrow/Polars/DuckDB UDFs.
- **[AI Agent & MCP Integration Guide](ai_agent_guide.md)** & **[`llms.txt`](../llms.txt)** — Model Context Protocol (MCP) configuration, 17-tool catalog, autonomous agent decision tree, and token-efficient LLM context index.
- **[Developer Cookbook & Production Recipes](developer_cookbook.md)** — Production recipes for SEC/Form ADV hygiene, couple splitting, multi-pillar deduplication, Polars/Arrow/DuckDB ETL, and TCPA/IRSF anti-fraud guardrails.
- **[Python API Docstrings](python_api.md)** — MkDocs docstring index for `entity_standardizer`, `address_standardizer`, and `phone_standardizer`.
- **[Multi-Platform Client SDKs](../sdks/README.md)** — Official client libraries for TypeScript/React, .NET, and Go.
- **[Operations & Deployment Guide](operations.md)** — Production deployment, observability, caching, and SLA configuration.
- **[Versioning Policy](VERSIONING.md)** & **[Release Guide](RELEASING.md)** — Semantic versioning guarantees and automated release pipeline.
- **[Security Policy & Anti-Fraud Guide](../SECURITY.md)** — Threat model, ReDoS prevention, IRSF toll-fraud detection, sentinel domain rejection, and vulnerability disclosure procedures.

---

## Architectural Specifications

### [1. Global Telephony Enterprise Blueprint](GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md)
- **Specification**: [`GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md`](GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md)
- **Key Capabilities**:
  - **Universal 249 ISO-3166-1 Country & ITU-T E.164 Registry**: Complete dial-plan coverage across all 249 ISO countries and territories, supporting ITU-T E.164, ITU-T E.123 National/International, and IETF RFC 3966 (`tel:` URI).
  - **NANP (`+1`) 25-Country & US/Canada State/Province Attribution**: Resolves 3-digit area codes (`NPA`) to exact US states, Canadian provinces, and 23 Caribbean/Pacific nations.
  - **Trunk & Legacy Mobile Prefix Healer**: Automatically cleans redundant domestic trunks (`+44 (0) 20...`), legacy Mexican mobile prefixes (`+52 1...`), Argentine mobile `15` prefixes, multi-script Unicode digits, ITU-T E.161 vanity numbers (`1-800-FLOWERS`), and embedded extensions.
  - **Fraud, IRSF & Synthetic Number Guardrails**: Detects fictitious ranges (`555-01XX`, UK Ofcom TV numbers), repeating/sequential bogus digits, and premium-rate IRSF risks with composite confidence routing (`AUTO_PASS`, `FUZZY_REVIEW`, `MANUAL_STEWARDSHIP`).

### [2. Global Spatial & Address Enterprise Blueprint](GLOBAL_SPATIAL_ENTERPRISE_BLUEPRINT.md)
- **Specification**: [`GLOBAL_SPATIAL_ENTERPRISE_BLUEPRINT.md`](GLOBAL_SPATIAL_ENTERPRISE_BLUEPRINT.md)
- **Key Capabilities**:
  - **USPS Publication 28 & UPU S42 Address Standardization**: Deterministic street suffix, directional, and secondary unit normalization across US and international jurisdictions.
  - **Offline Rooftop Geocoding, H3 Indexing & Delivery Intelligence**: DPV/RDI/CMRA flags, registered-agent corporate hub detection, and deterministic `normalized_address_key`, `building_key`, and `phonetic_key` generation.

---

## 📄 License & Ownership

Entity Standardizer is open-source software owned and maintained by **HobbyHabbit LLC** under the **MIT License**. See **[LICENSE](../LICENSE)** for complete details.
