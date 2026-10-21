# Phone Standardizer Documentation & Technical Specifications 📚

Phone Standardizer is owned and maintained by **HobbyHabbit LLC** under the **MIT License**. This directory contains the developer guides, API references, and formal architectural blueprints for the platform.

---

## Developer Guides & Reference

- **[5-Minute Quickstart Guide](quickstart.md)** — Step-by-step onboarding for phone parsing, international E.164/E.123/RFC 3966 formatting, NANP jurisdiction resolution, streaming batch, CLI, and HTTP service.
- **[Complete API Reference](api_reference.md)** — Reference for all Python models, functions, classes, CLI commands, microservice endpoints, and MCP tools.
- **[Multi-Platform Client SDKs](../sdks/README.md)** — Official client libraries for TypeScript/React, .NET, and Go.
- **[Security Policy & Anti-Fraud Guide](../SECURITY.md)** — Threat model, ReDoS prevention, IRSF toll-fraud detection, TCPA/fictitious range invariants, and vulnerability disclosure procedures.

---

## Architectural Specifications

### [1. Global Telephony Enterprise Blueprint](GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md) (v1.0.0 — Master Specification)
- **Specification**: [`GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md`](GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md)
- **Status**: Approved Master Technical Architecture Blueprint (`v1.0.0`)
- **Key Capabilities**:
  - **Universal 249 ISO-3166-1 Country & ITU-T E.164 Registry**: Complete dial-plan coverage across all 249 ISO countries and territories, supporting ITU-T E.164, ITU-T E.123 National/International, and IETF RFC 3966 (`tel:` URI).
  - **NANP (`+1`) 25-Country & US/Canada State/Province Attribution**: Resolves 3-digit area codes (`NPA`) to exact US states, Canadian provinces, and 23 Caribbean/Pacific nations.
  - **Trunk & Legacy Mobile Prefix Healer**: Automatically cleans redundant domestic trunks (`+44 (0) 20...`), legacy Mexican mobile prefixes (`+52 1...`), Argentine mobile `15` prefixes, multi-script Unicode digits,ITU E.161 vanity numbers (`1-800-FLOWERS`), and embedded extensions.
  - **Fraud, IRSF & Synthetic Number Guardrails**: Detects fictitious ranges (`555-01XX`, UK Ofcom TV numbers), repeating/sequential bogus digits, and premium-rate IRSF risks with composite confidence routing (`AUTO_PASS`, `FUZZY_REVIEW`, `MANUAL_STEWARDSHIP`).
  - **High-Throughput Python + Rust PyO3 Engine**: Zero-dependency Python core with optional native Rust acceleration, streaming batch processors, FastAPI microservice, and MCP server.

---

## 📄 License & Ownership

Phone Standardizer is open-source software owned and maintained by **HobbyHabbit LLC** under the **MIT License**. See **[LICENSE](../LICENSE)** for complete details.
