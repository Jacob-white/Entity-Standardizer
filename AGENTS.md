# AGENTS.md - Working in Phone-Standardizer

Guidance for AI coding agents and contributors. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md](docs/GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md) for the master specification.

## What this is

A standalone zero-dependency Python library (`phone_standardizer/`) with optional native Rust PyO3 acceleration (`src/lib.rs`) that parses, cleans, heals, validates, and formats telephone numbers across all 249 ISO-3166-1 countries and territories into ITU-T E.164, ITU-T E.123 National/International, and IETF RFC 3966 (`tel:` URI). Exposes a Python API, CLI (`phone-standardizer`), FastAPI HTTP microservice (`phone_standardizer.server:app`), and Model Context Protocol server (`phone-standardizer-mcp`).

## Layout

| Path | Contents |
| :--- | :--- |
| `phone_standardizer/models.py` | `StandardizedPhone`, `CountryDialPlan`, `PhoneLineType`, `PhoneRoutingTier`, `PhoneRiskFlag`, `HealingAction` |
| `phone_standardizer/registry.py`, `registry_data.py` | Universal 249 ISO-3166-1 country & ITU calling code registry |
| `phone_standardizer/nanp.py` | North American Numbering Plan (`+1`) 25-country & US/Canada state/province NPA resolver |
| `phone_standardizer/normalization.py` | Multi-script digit folding, extension extraction, and ITU-T E.161 vanity keypad decoding |
| `phone_standardizer/standardizer.py` | Core `standardize_phone`, `validate_phone`, `format_*`, and `mask_phone` |
| `phone_standardizer/confidence.py` | Fictitious range (`555-01XX`, Ofcom TV), bogus digit, IRSF risk, and confidence scoring |
| `phone_standardizer/batch.py` | Chunked batch & CSV/JSONL streaming pipelines |
| `phone_standardizer/cli.py`, `server.py`, `mcp/` | CLI, FastAPI HTTP microservice, and MCP JSON-RPC stdio server |
| `src/lib.rs`, `phone_standardizer/_native_dispatch.py` | Optional Rust PyO3 native extension and pure-Python fallback dispatcher |
| `tests/` | Full unit & regression test suite enforcing 100% line & branch coverage |

## Commands

```bash
ruff check .
pytest --cov --cov-report=term-missing
```
