# E2E Test Infra: Entity-Standardizer

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on internal implementation design.
- Multi-runtime testing: Pure-Python fallback mode and Native Rust PyO3 mode must execute all tests and produce 100% identical outputs.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Interaction + Real-World Workload Testing across all 6 entity pillars (`Phone`, `Address`, `Company`, `Person`, `Web`, `Joint Contact`).

## Feature Inventory & Test Matrix
| # | Feature | Source | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Cross-Pillar) |
|---|---------|--------|:-----------------:|:-----------------:|:---------------------:|
| 1 | Cold-Start & Lazy H3 Import | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ |
| 2 | Unified Cache Operations | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ |
| 3 | Canonical Diacritic Folding | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ |
| 4 | Address Standardization & US Edge Cases | ORIGINAL_REQUEST R2 | 10 | 10 | ✓ |
| 5 | International Address & UPU Envelope | ORIGINAL_REQUEST R2 | 10 | 10 | ✓ |
| 6 | Address Scoring, Delivery & Calibration | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ |
| 7 | Spatial & H3 Offline Indexing | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ |
| 8 | Address Fuzzy Recovery & Soundex | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ |
| 9 | Batch Streaming & Formula Injection Defense | ORIGINAL_REQUEST R1, R2 | 5 | 5 | ✓ |
| 10 | Company Standardization & Resolution | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |
| 11 | Person Standardization & Comparison | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |
| 12 | Web (Email & URL) Canonicalization | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |
| 13 | Joint Contact Entity Resolution | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |
| 14 | Rust PyO3 vs Python Parity | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |

## Test Architecture
- Test runner: `.venv/bin/pytest tests/`
- Parity runner: `ENTITY_STANDARDIZER_FORCE_PURE=1 .venv/bin/pytest tests/` and `.venv/bin/pytest tests/`
- Linter & Typechecks: `.venv/bin/ruff check .`
- Cargo Tests: `/root/.cargo/bin/cargo test --locked`
- SDK Tests: `npm --prefix sdks/typescript test`
- Benchmarks: `.venv/bin/python benchmarks/benchmark_throughput.py`

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Target |
|---|----------|--------------------|--------|
| 1 | Multinational Contact Ingestion | Phone + Address (UK/JP/US) + Person + Web | Zero drops, valid E.164 & UPU |
| 2 | Dirty CRM Duplication & Resolution | Company + Person + Damerau-Levenshtein | Clean deduplication, parity |
| 3 | Commercial Courier Dispatch | Delivery RDI + DPV Footnotes + Spatial H3 | Accurate commercial flag & cell |
| 4 | Large CSV Batch Streaming | Batch chunking + CSV formula defense | Safe CSV, memory bounded |
| 5 | High-Concurrency Cold & Warm Cache | Cache multi-tier + Clear cache | No stale entries, stable stats |
