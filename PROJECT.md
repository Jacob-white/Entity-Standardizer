# Project: Entity-Standardizer Unification, Coverage & Optimization

## Architecture
`Entity-Standardizer` provides high-throughput, multi-pillar entity standardization across six core entity types:
1. **Phone**: E.164 parsing, carrier metadata, MCC/MNC lookup, offline formatting, batch streaming.
2. **Address**: US street parsing, 17 international country grammars, UPU envelope formatting, fuzzy healing, confidence scoring, RDI/DPV delivery intelligence, offline spatial/H3 indexing.
3. **Company**: Business entity cleaning, legal suffix normalization, fuzzy deduplication, registered agent hub detection.
4. **Person**: Personal name parsing, honorifics, titles, phonetic/edit-distance matching.
5. **Web (Email & URL)**: RFC 5322 normalization, typo recovery, URL canonicalization, domain classification.
6. **Joint Contact / Entity Resolution**: Multi-pillar contact graph standardization, cross-field reconciliation, and entity resolution scoring.

The runtime architecture is dual-layer:
- **Accelerated Core**: Native Rust PyO3 crate (`_entity_standardizer_rs`), compiled with LTO and codegen-units=1 for compute-intensive hot paths (batch E.164, Unicode folding, Damerau-Levenshtein matrix, Soundex, company tokenization, diacritic folding).
- **Pure-Python Fallback Core**: Complete pure-Python implementations guaranteeing 100% semantic and output parity on platforms without the compiled extension or when `ENTITY_STANDARDIZER_FORCE_PURE=1` is set.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Lazy H3 Import & Cold-Start Hygiene | Lazy load `h3` via `_get_h3()` in `h3_indexer.py` and PEP 562 in `address/__init__.py`; verify `import sys, entity_standardizer; assert 'h3' not in sys.modules` exits 0 | M1 | R1 |
| 2 | Canonical Diacritic Folding | Consolidate duplicate diacritic/ligature folding in `normalization.py`, fixing `đ`/`Đ` parity defect and sharing with `diacritics.py` | M1 | R1 |
| 3 | Unified Cache Operations | `clear_cache()` and `get_cache_stats()` operate coherently across phone and address without breaking backward-compatible dict keys | M1 | R1 |
| 4 | Batch-Streaming Utility Consolidation | Re-export memory-bounded chunkers and CSV formula injection sanitizers across subsystems | M1 | R1 |
| 5 | Address Subsystem Dead Code Cleanup | Remove untracked `address/data/`, dead `# noqa: F401` imports in `us_street_parser.py`, and consolidate duplicate seed tables | M1 | R2 |
| 6 | Address Standardization Test Suite | US street parsing, rural routes, Queens hyphenation, military APO/FPO, intersections, PR urbanizations, secondary units | M2 | R2 |
| 7 | International Address Test Suite | 17 registered country grammars, postal validation/extraction, UPU S42 envelope formatting, transliteration | M2 | R2 |
| 8 | Scoring, Delivery & Audit Test Suite | Confidence calibration (`calibration.py`), DPV footnotes, RDI, explainable trace, corporate registry, stewardship audit | M2 | R2 |
| 9 | Spatial & Reference Test Suite | SQLite R*Tree, H3 indexer, verification cascade, geocoder centroid fallback, offline reference index | M2 | R2 |
| 10 | Address Fuzzy & Phonetics Test Suite | Soundex, phonetic keys, fuzzy suffix and typo recovery with protected word immunity | M2 | R2 |
| 11 | Address Batch & Cache Test Suite | CSV/JSONL batch streaming, memory buffer chunking, SQLite and LRU cache backends | M2 | R2 |
| 12 | Rust PyO3 Diacritic Folding Acceleration | Export `fold_latin_diacritics_rs` from `src/lib.rs` and wire into `entity_standardizer/normalization.py` | M3 | R3 |
| 13 | Rust Company Batch Acceleration | Wire `normalize_batch_company_tokens_dispatch` into `company.py:batch_standardize_companies` | M3 | R3 |
| 14 | Unified Pure-Python Kill Switch | Support `ENTITY_STANDARDIZER_FORCE_PURE=1` in `entity_standardizer/_native_dispatch.py` matching address dispatch | M3 | R3 |
| 15 | 6-Pillar Throughput Benchmark Suite | Expand `benchmarks/benchmark_throughput.py` to benchmark all 6 pillars in both Native Rust and Pure Python modes | M3 | R3 |
| 16 | Comprehensive E2E Testing Suite (Tiers 1-4) | Requirements-driven test suite covering all 6 pillars, validating 100% parity and robustness | M4 / E2E Track | Dual Track |
| 17 | Git Feature Branch, PR & CI Verification | Clean branch off origin/main, Pull Request on Jacob-white/Entity-Standardizer, all 6 GitHub Actions CI checks green | M5 | R4 |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Subsystem Unification & Cold-Start Hygiene | Lazy H3, diacritic folding parity (`đ`/`Đ`), cache unification, batch-streaming sharing, address dead code removal | none | IN_PROGRESS |
| M2 | Address Subsystem Test Coverage Expansion | 6 new deterministic test suites raising address coverage to >= 65% while keeping 100.00% core gate | M1 | PLANNED |
| M3 | Hot-Path Throughput & Rust PyO3 Acceleration | Export `fold_latin_diacritics_rs`, wire company batch tokenization, `ENTITY_STANDARDIZER_FORCE_PURE`, benchmark 6 pillars | M1 | PLANNED |
| M4 | E2E Parity & System Hardening (Dual Track) | Full test suite across both runtimes, cargo test, ruff, benchmarks, 100% parity verification | M2, M3 | PLANNED |
| M5 | Controlled Workspace, PR Delivery & CI Verification | Branch off origin/main, git commit, push, PR creation on Jacob-white/Entity-Standardizer, 6 CI checks green, cleanup | M4 | PLANNED |

---

## Interface Contracts

### Diacritic Normalization
- Module: `entity_standardizer.normalization`
- Function: `fold_latin_diacritics(text: str) -> str`
- Table: `LATIN_LIGATURE_AND_STROKE_MAP: dict[str, str]` (contains `đ: d, Đ: D, ħ: h, Ħ: H, ...`)
- Consumer: `entity_standardizer.address.international.diacritics:LIGATURE_MAP = {k: v.upper() for k, v in LATIN_LIGATURE_AND_STROKE_MAP.items()}`
- Rust Binding: `fold_latin_diacritics_rs(input: &str) -> String` matching Python translation exactly.

### Cache Interface
- Module: `entity_standardizer.cache`
- Function: `clear_cache() -> None`: Clears phone cache and address cache (without eager address cache instantiation).
- Function: `get_cache_stats() -> dict[str, Any]`: Returns dict containing top-level `{"l1": ..., "l2_enabled": ..., "l2_hits": ..., "l2_misses": ..., "phone": {...}, "address": {...}}`.
- Module: `entity_standardizer.address.cache`
- Function: `clear_cache() -> None`, `get_cache_stats() -> dict[str, Any]`.

### Spatial & H3 Lazy Interface
- Module: `entity_standardizer.address`
- Exports: `SpatialEngine`, `SpatialResolutionResult`, `get_default_spatial_engine`, `lat_lng_to_h3`, `resolve_spatial_coordinates` in `__all__`.
- Lazy Resolution: Loaded via PEP 562 `__getattr__` and `__dir__` in `entity_standardizer/address/__init__.py`.
- Module: `entity_standardizer.address.spatial.h3_indexer`
- Function: `_get_h3()` lazily imports `h3` only when spatial functions are executed.

### Native Dispatch & Fallback Interface
- Variable: `ENTITY_STANDARDIZER_FORCE_PURE=1` forces pure-Python execution across all pillars.
- Function: `is_native_available() -> bool`.
- Rust Extension: `_entity_standardizer_rs` exports `fold_latin_diacritics_rs`, `normalize_batch_company_tokens_rs`, `damerau_levenshtein_distance_rs`, `compute_soundex`.

---

## Code Layout

- Implementation Source Files:
  * `entity_standardizer/normalization.py`: Shared diacritic folding table and dispatch.
  * `entity_standardizer/cache.py`: Unified cache stats and clearing.
  * `entity_standardizer/batch.py`: Shared chunking and formula injection prevention.
  * `entity_standardizer/_native_dispatch.py`: Native PyO3 bindings and pure fallback toggle.
  * `entity_standardizer/company.py`: Batch company standardization with native tokenization.
  * `entity_standardizer/address/__init__.py`: PEP 562 lazy spatial exports.
  * `entity_standardizer/address/us_street_parser.py`: Dead import cleanup.
  * `entity_standardizer/address/spatial/h3_indexer.py`: Lazy `h3` import via `_get_h3()`.
  * `entity_standardizer/address/international/diacritics.py`: Import canonical ligature map.
  * `src/lib.rs`: Rust PyO3 function exports (`fold_latin_diacritics_rs`).
- Test Files:
  * `tests/test_address_standardization.py`: US address parsing and edge cases.
  * `tests/test_address_international.py`: International grammars and UPU formatting.
  * `tests/test_address_scoring_delivery.py`: Calibration, confidence, RDI, DPV.
  * `tests/test_address_spatial_reference.py`: Spatial R*Tree, H3 indexing, cascade, geocoding.
  * `tests/test_address_fuzzy_phonetics.py`: Soundex and fuzzy healing.
  * `tests/test_address_batch_cache.py`: Batch streaming and cache backends.
- Benchmarks:
  * `benchmarks/benchmark_throughput.py`: Multi-pillar throughput runner.
