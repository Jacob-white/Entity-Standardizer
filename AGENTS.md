# AGENTS.md - Working in Entity-Standardizer

Guidance for AI coding agents and contributors. See [CONTRIBUTING.md](CONTRIBUTING.md), [docs/api_reference.md](docs/api_reference.md), and [docs/GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md](docs/GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md) for the master specifications.

## What this is

A unified multi-national **Entity, Organization, Person, Web, Address, and Telephone Standardization, Bidirectional Cross-Healing, and Entity Resolution Engine** (`entity_standardizer/`, `address_standardizer/`, and `phone_standardizer/`) with optional native Rust PyO3 acceleration (`src/lib.rs`). It parses, cleans, cross-heals, validates, compares, and deduplicates companies (**ISO 20275 ELF**), persons & job titles, emails/URLs/social handles (**RFC 5321/5322 / IDNA / eTLD+1**), physical addresses (**USPS Publication 28 / UPU S42 / ISO 19160-4**), and telephone numbers (**ITU-T E.164 / E.123 / RFC 3966 / NANP**) across all 249 ISO-3166-1 countries and territories. Exposes a Python API, CLI (`entity-standardizer` / `phone-standardizer` / `address-standardizer`), FastAPI HTTP microservice (`phone_standardizer.server:app`), Model Context Protocol server (`entity-standardizer-mcp`), Arrow/Polars/DuckDB integrations, and TypeScript, Go, and .NET SDKs.

## Layout

| Path | Contents |
| :--- | :--- |
| `entity_standardizer/__init__.py` | Unified top-level namespace exporting all 6 entity standardization & comparison pillars |
| `entity_standardizer/company.py` | `StandardizedCompany`, `standardize_company`, `compare_companies`, `deduplicate_companies` (ISO 20275 ELF, diacritics, SEC `/DE/`, DBA/FKA/branch/Series extraction) |
| `entity_standardizer/person.py` | `StandardizedPerson`, `StandardizedJobTitle`, `standardize_person`, `split_compound_persons`, `standardize_job_title`, `compare_persons`, `deduplicate_persons`, `is_organization_name` |
| `entity_standardizer/web.py` | `StandardizedEmail`, `StandardizedUrl`, `StandardizedSocial`, `standardize_email`, `standardize_url`, `standardize_social`, `compare_emails`, `compare_urls`, sentinel domain guard |
| `phone_standardizer/joint.py` | `StandardizedContact`, `ContactComparisonResult`, `CrossHealingAction`, `standardize_contact`, `batch_standardize_contacts`, `compare_contacts` |
| `phone_standardizer/models.py`, `standardizer.py` | `StandardizedPhone`, `CountryDialPlan`, `standardize_phone`, `validate_phone`, `format_*`, `mask_phone` |
| `phone_standardizer/registry.py`, `registry_data.py`, `nanp.py` | Universal 249 ISO-3166-1 country & ITU calling code registry and NANP (`+1`) 25-country / 50-state NPA resolver |
| `phone_standardizer/dedup.py` | `compare_phones`, `deduplicate_phones`, `generate_phone_blocking_keys`, and 5-pillar `cluster_contact_records` |
| `phone_standardizer/arrow.py` | Lazy-loaded Apache Arrow (`standardize_arrow`, `standardize_companies_arrow`, `standardize_persons_arrow`), Polars, and DuckDB SQL UDFs (`register_duckdb_udfs`) |
| `phone_standardizer/cli.py`, `server.py`, `mcp/` | CLI, 18-endpoint FastAPI HTTP microservice, and 17-tool MCP JSON-RPC stdio server |
| `address_standardizer/` | USPS Pub 28 / UPU S42 address parser, offline rooftop geocoder, H3 spatial indexer, and delivery intelligence |
| `src/lib.rs`, `phone_standardizer/_native_dispatch.py` | Native Rust PyO3 extension (`_phone_standardizer_rs`) and pure-Python fallback dispatcher |
| `sdks/` | Parity-tested TypeScript/React (`sdks/typescript`), Go (`sdks/go`), and .NET (`sdks/dotnet`) client SDKs |
| `tests/` | Full unit, contract, and regression test suite enforcing 100% line & branch coverage |

## Commands

```bash
ruff check .
pytest --cov --cov-report=term-missing
cargo test
```
