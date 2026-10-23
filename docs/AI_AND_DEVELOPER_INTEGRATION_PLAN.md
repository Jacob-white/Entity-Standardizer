# Address-Standardizer AI and Developer Integration Plan
## Architectural Audit, AI Agent Specification, SDK Parity Plan, and Multi-Phase Engineering Roadmap

**Document Version**: 4.0.0  
**Status**: Approved Specification & Architecture Blueprint  
**Date**: 2026-10-17  
**Target Repository**: `/home/jwhite/Address-Standardizer`  
**Current Engine Baseline**: v3.3.0 (`pyproject.toml`, line 3; `Cargo.toml`, line 3)  
**Target Engine Release**: v4.0.0  

---

## Executive Summary

`Address-Standardizer` is an enterprise-grade address parsing, postal validation, and spatial geocoding library. It features a hybrid execution engine: a deterministic high-throughput rule parser and statistical Conditional Random Field (CRF) fallback in Python, accelerated by native Rust PyO3 routines for Soundex and edit-distance computations, with a 100% bit-for-bit identical pure Python fallback. The project enforces an uncompromising quality gate (`pyproject.toml`, lines 86–101) mandating 100% statement and branch test coverage (`fail_under = 100`, `branch = true`), validated across 3,616 tests in 99 test files.

Despite exceptional in-sample accuracy (93.7% all-fields exact match across 2,417 renderings), rigorous held-out generalization evaluations on unseen OpenStreetMap data (`benchmarks/eval/REPORT_HOLDOUT.md`, lines 1–254) demonstrate an **8.3 percentage point drop** to **85.4%** across 10,211 renderings (seed `20261201`). Punctuation degradation presents severe challenges: single-line addresses without commas drop to **51.7%** exact match, and swapped address tokens plummet to **38.5%**. Furthermore, empirical calibration analysis reveals substantial heuristic overconfidence: addresses scored in the highest confidence bin ($[0.9, 1.0)$) carry an average heuristic score of **0.982**, yet achieve an empirical exact-match accuracy of only **85.7%** (Expected Calibration Error $\text{ECE} = 0.127$, Brier Score = $0.135$). While subsequent optimization cycles documented in `REPORT_HOLDOUT_V2.md` (92.2% exact) and `REPORT_HOLDOUT_V3.md` (94.5% exact) have recovered significant accuracy, international outlier countries (such as Hungary at 12.5% and Japan at 21.2% in V1; Peru at 30.9% and Brazil at 87.9% in V3) and commaless single-line inputs remain challenging.

Simultaneously, the modern developer landscape has undergone a tectonic shift: software engineers increasingly deploy autonomous AI agents (powered by Claude, GPT-4o, and Gemini), interact with Model Context Protocol (MCP) servers, build async microservices with FastAPI and Next.js, and process massive analytical datasets with Polars, DuckDB, and Apache Arrow.

This document establishes the authoritative, production-grade blueprint to transform `Address-Standardizer` into the premier developer-first and AI-agent-native address intelligence platform. It is organized into four core architectural pillars:
1. **Holistic Audit & Benchmark Outcome Analysis**: Exhaustive, line-number-grounded technical review across all Python engine modules, native Rust extensions, REST daemon, client SDKs, documentation, and evaluation benchmarks.
2. **AI Agent & LLM Integration Specification**: Complete Model Context Protocol (MCP) server design, five fully articulated JSON schemas, token-efficient payload models, autonomous agent self-correction state machines, operational failure reason code routing, and publication-ready `llms.txt` and Cursor/agent skill definitions.
3. **Developer Experience (DX) & SDK Parity Plan**: Public API surface modernization, zero-config open-data reference validation, side-by-side SDK feature matrix across Python, TypeScript, Go, and .NET, automated jittered retry architectures, and copy-pasteable framework recipes.
4. **Prioritized Multi-Phase Execution Roadmap**: Four sequenced implementation phases (Phases 8.1 through 8.4) ordered by impact-to-effort ratio, specifying target files, deliverables, backwards-compatibility invariants, and exact verification commands preserving `fail_under = 100`.

---

## 1. Holistic Audit & Benchmark Outcome Analysis

### 1.1. Benchmark Evaluations & Held-out Generalization Analysis

The Address Standardizer evaluation framework provides an objective, reproducible measure of parsing accuracy, component precision, and confidence calibration across diverse address topologies.

#### 1.1.1. Held-out Evaluation Analysis (`benchmarks/eval/REPORT_HOLDOUT.md`)
The baseline generalization evaluation (`benchmarks/eval/REPORT_HOLDOUT.md`, lines 1–254) executed against an unseen holdout corpus derived from OpenStreetMap `addr:*` tags reveals critical operational realities:

- **Corpus & Methodology**: 1,195 OSM-derived physical address records expanded into 10,211 input renderings using pseudo-random generation seed `20261201` (`REPORT_HOLDOUT.md`, line 95). Ground truth tags were strictly isolated during parser development.
- **Overall Accuracy**:
  - **All-fields exact match across all renderings**: **85.4%** (8,721 / 10,211 correct; 95% Wilson confidence interval: **84.7% – 86.1%**) (`REPORT_HOLDOUT.md`, line 99).
  - **In-sample vs. Holdout Generalization Gap**: Compared to the tuned in-sample baseline of **93.7%** (2,265 / 2,417 exact), the engine experiences an **-8.3 percentage point delta** (`REPORT_HOLDOUT.md`, lines 25–27).
- **Per-Field Accuracy and Precision** (`REPORT_HOLDOUT.md`, lines 103–110):
  - `house_number`: **96.2%** accuracy, **96.6%** precision ($n=10,211$, 95% CI: 95.9% – 96.6%).
  - `street`: **87.8%** accuracy, **87.8%** precision ($n=10,211$, 95% CI: 87.1% – 88.4%). Street token identification is the primary source of domestic component misclassification.
  - `city`: **89.5%** accuracy, **95.0%** precision ($n=10,211$, 95% CI: 88.8% – 90.0%).
  - `state`: **90.8%** accuracy, **96.2%** precision ($n=706$, 95% CI: 88.4% – 92.7%).
  - `postcode`: **93.3%** accuracy, **100.0%** precision ($n=9,016$, 95% CI: 92.8% – 93.8%). When postcodes are detected, format verification yields zero false-positive contamination.
  - `country`: **100.0%** accuracy, **100.0%** precision ($n=10,211$, 95% CI: 100.0% – 100.0%).
- **Degradation Across Rendering Styles** (`REPORT_HOLDOUT.md`, lines 35–48, 160–173):
  The engine exhibits stark sensitivity to input formatting and delimiter preservation:
  - `structured`: **96.2%** holdout exact match (vs. 100.0% in-sample, $\Delta -3.8$ pts). Structured key-value inputs remain the most resilient ingestion format.
  - `line_no_postal`: **91.7%** holdout exact match (vs. 99.6% in-sample, $\Delta -7.9$ pts).
  - `line_country_text`: **90.6%** holdout exact match (vs. 99.6% in-sample, $\Delta -9.0$ pts).
  - `line` (standard single-line with commas): **90.4%** holdout exact match (vs. 99.6% in-sample, $\Delta -9.3$ pts).
  - `line_lower` / `line_upper` / `line_messy`: **90.4%** holdout exact match (vs. 99.6% in-sample, $\Delta -9.3$ pts). Letter case variations and spurious internal whitespace are cleanly normalized.
  - `line_abbrev`: **82.3%** holdout exact match (vs. 83.7% in-sample, $\Delta -1.4$ pts).
  - `line_nocomma`: **51.7%** holdout exact match (vs. 65.2% in-sample, **$\Delta -13.5$ pts**). Stripping commas prevents deterministic boundary detection between street name and city/state tokens, causing massive fallback cascades.
  - `line_swapped`: **38.5%** holdout exact match (vs. 0.0% in-sample, $+38.5$ pts due to holdout mix). Transposing city/state before street tokens severely degrades standard left-to-right or right-to-left US parsers.
  - `structured_swapped`: **0.0%** holdout exact match (0 / 920). Inverting structured fields completely breaks deterministic field mapping.
- **Geographic Outlier Analysis & International Weak Spots** (`REPORT_HOLDOUT.md`, lines 49–91, 114–156):
  - **Hungary (`HU`)**: **12.5%** exact match. Postcode-first lines (`{pc} {city}, {street} {number}`) parse completely inverted: `{pc} {city}` is placed into `house_number` and `street`, street is placed in `city`, and `postcode` remains empty (`REPORT_HOLDOUT.md`, lines 208–213).
  - **Japan (`JP`)**: **21.2%** exact match (down from 100.0% in-sample, **$\Delta -78.8$ pts**). Outside Tokyo and Osaka, provincial municipal addresses (Fukuoka, Sapporo, Nagoya) fail block number separation, `丁目` extraction, and `市 区` ward/city splits (`REPORT_HOLDOUT.md`, lines 214–219).
  - **Turkey (`TR`)**: **46.7%** exact match due to Unicode dotless `ı`/`I` vs. dotted `i`/`İ` case-folding collisions in street and district tokens (`REPORT_HOLDOUT.md`, lines 226–231).
  - **India (`IN`)**: **57.7%** exact match caused by 6-digit PIN codes concatenated directly to city names without delimiters and dense sub-locality aggregation (`REPORT_HOLDOUT.md`, line 235).
  - **Canada (`CA`)**: **66.8%** exact match (down from 84.7% in-sample, **$\Delta -17.9$ pts**) due to French directional abbreviations (`Ouest`/`Est` $\to$ `O`/`E`) in Montréal street names (`REPORT_HOLDOUT.md`, lines 239–243).
  - **Argentina (`AR`)**: **72.9%** exact match due to alphanumeric CPA postal codes (`X5000`) or 4-digit codes glued to city names (`REPORT_HOLDOUT.md`, lines 222–223).
  - **United States (`US`)**: **78.1%** holdout exact match (vs. 81.8% in-sample) driven by named rural highways (e.g. `COUNTY ROAD 400 N`) and directional prefix collisions (`REPORT_HOLDOUT.md`, lines 244–246).
- **Confidence Calibration Assessment** (`REPORT_HOLDOUT.md`, lines 192–201):
  - Expected Calibration Error: **$\text{ECE} = 0.127$**
  - Brier Score: **$\text{Brier} = 0.135$**
  - Severe Heuristic Overconfidence: In the highest score bin $[0.9, 1.0)$, $n=10,144$ records carried a mean confidence score of **0.982**, but the observed empirical exact match rate was only **85.7%**. Because the raw confidence score is a rule-based weighted sum rather than a posterior probability, agents and downstream systems cannot treat $0.98$ as a $98\%$ probability of correctness.

#### 1.1.2. Evolution in Subsequent Holdout Benchmarks (`V2` and `V3`)
- **`benchmarks/eval/REPORT_HOLDOUT_V2.md`** (lines 1–120, seed `20270115`, $n=1,506$ records, 12,872 renderings):
  - All-fields exact match improved to **92.2%** (11,863 / 12,872, 95% CI: 91.7% – 92.6%).
  - Calibration significantly improved: $\text{ECE} = 0.064$, $\text{Brier} = 0.076$.
  - Remaining country bottlenecks: Argentina (`AR`: 40.8%), Colombia (`CO`: 55.8%), Japan (`JP`: 64.6%), Indonesia (`ID`: 74.6%), Kenya (`KE`: 77.6%), Mexico (`MX`: 79.6%).
- **`benchmarks/eval/REPORT_HOLDOUT_V3.md`** (lines 1–116, seed `20270302`, $n=1,182$ records, 10,106 renderings):
  - All-fields exact match reached **94.5%** (9,547 / 10,106, 95% CI: 94.0% – 94.9%).
  - Field-level accuracy: `house_number` **99.6%**, `street` **97.9%**, `city` **96.9%**, `state` **78.4%** ($n=984$), `postcode` **98.4%** ($n=8,924$), `country` **100.0%**.
  - Calibration hardened: $\text{ECE} = 0.041$, $\text{Brier} = 0.054$.
  - Remaining weak spots in V3: Japan (`JP`: 28.1%), Peru (`PE`: 30.9%), Indonesia (`ID`: 67.9%), Mexico (`MX`: 70.6%), Ecuador (`EC`: 80.5%), Brazil (`BR`: 87.9%).

### 1.2. Ground-Truth Golden Datasets Inventory

The repository maintains two golden datasets:
1. **US Domestic Golden Dataset (`benchmarks/golden_dataset.json`)**:
   - **Record Count**: Exactly 1,000 ground-truth labeled US records.
   - **9 Edge-Case Categories**:
     1. `clean_us_standard` (baseline clean USPS Pub 28 formatting)
     2. `directional_ambiguities` (e.g. `123 N South St`, `450 East West Hwy`)
     3. `dual_address_lines` (simultaneous PO Box and physical street address)
     4. `hyphenated_street_numbers` (e.g. Queens, NY `120-04 14th Ave`)
     5. `international_nonstandard` (unusual US formats, APO/FPO military, Puerto Rico urbanizations)
     6. `missing_commas_delimiters` (single-line unpunctuated text)
     7. `rural_routes` (Highway Contract and Rural Delivery `RR 2 Box 150`)
     8. `secondary_units_pmb` (Private Mailboxes, suites, penthouses, commercial drops)
     9. `typo_scenarios` (transpositions, phonetically misspelled street and city names)
   - **Schema**: `test_id`, `category`, `raw_input` (dict with `street1`, `street2`, `city`, `state`, `postal_code`), `expected_output` (dict containing `street1`, `street2`, `city`, `state`, `postal_code`, `country`, `normalized_address_key`, `building_key`, `phonetic_key`, `address_status`, `is_us`, `is_registered_agent_hub`).
2. **Multinational Golden Dataset (`benchmarks/data/golden_dataset_multinational.json`)**:
   - **Record Count**: Exactly 1,000 ground-truth labeled multinational records.
   - **6 International Categories**:
     1. `uk_commonwealth_postcodes` (200 records): Outward/inward alphanumeric codes, dependent localities, premise names preceding street names.
     2. `eu_inverted_compound` (200 records): Inverted house numbers, compound Germanic street names, alphanumeric unit suffixes (`Musterstraße 12A`, `Calle Mayor 45, 2º B`).
     3. `canada_bilingual_rural` (150 records): Alphanumeric postal codes (`A1A 1A1`), bilingual English/French street types and directions (`Rue`, `Boulevard`, `Ouest`, `Est`).
     4. `latam_compound_urbanization` (150 records): Complex secondary descriptors, manzanas, lotes, interior unit numbers.
     5. `global_formation_hubs` (150 records): Corporate service providers, offshore trust complexes, registered agent networks in Cayman Islands, BVI, Bermuda, Jersey, Guernsey, UK, Switzerland, and Delaware.
     6. `multilingual_diacritics_messy` (150 records): High-order Unicode diacritics, unpunctuated multi-script strings, messy envelope transcriptions.
   - **27 Jurisdictions Represented**: GBR (206), CAN (168), DEU (101), FRA (49), MEX (47), USA (41), NLD (37), ESP (31), POL (28), COL (28), BRA (28), ITA (25), CYM (24), SWE (22), ARG (21), DNK (16), VGB (16), CHL (14), LUX (14), CHE (14), PER (12), PRI (12), JEY (10), GGY (10), IMN (10), BMU (8), PAN (8).

### 1.3. Quality Gates & Configuration (`pyproject.toml`)

Direct inspection of `pyproject.toml` (lines 1–117) demonstrates stringent engineering governance:
- **Core Specification**: Package version `3.3.0`, requiring Python `>=3.11`. Build backend is `setuptools.build_meta`.
- **Runtime Dependencies** (`pyproject.toml`, lines 30–33): Minimal base footprint: `requests>=2.28.0` and `h3>=4.0.0`.
- **Optional Dependency Groups** (`pyproject.toml`, lines 35–75):
  - `server`: `fastapi>=0.100.0`, `uvicorn>=0.23.0`, `pydantic>=2.0.0`, `httpx>=0.24.0`
  - `arrow`: `pyarrow>=14.0.0`, `polars>=0.20.0`, `duckdb>=0.10.0`, `numpy>=1.24`
  - `dev`: `pytest>=7.0.0`, `pytest-cov>=4.0.0`, `ruff>=0.1.0`, `usaddress>=0.5.16`, `hypothesis>=6.100.0`
  - `redis`: `redis>=5.0`
  - `translit`: `anyascii>=0.3`
  - `otel`: `opentelemetry-api>=1.20`
  - `ml`: `usaddress>=0.5.16`
  - `benchmark`: `psutil>=5.9.0`
  - `docs`: `mkdocs>=1.6,<2`, `mkdocs-material>=9.5`, `mkdocstrings[python]>=0.25`
- **Strict Test Coverage Enforcement** (`pyproject.toml`, lines 86–101):
  ```toml
  [tool.coverage.run]
  source = ["address_standardizer"]
  branch = true

  [tool.coverage.report]
  fail_under = 100
  show_missing = true
  skip_covered = false
  ```
  The repository enforces a strict **100% statement AND branch coverage gate** (`fail_under = 100`). Any newly introduced line of code, unexercised error path, or uncovered branch instantly fails continuous integration.
- **Current Test Volume**: Verified via pytest collection: **3,616 tests** across **99 test files** in `tests/`, spanning unit tests, integration suites, property-based fuzzers (`tests/fuzzing/`), spatial cascades (`tests/spatial/`), international grammars (`tests/international/`), and native Rust/Python parity verifiers (`tests/native/`).

### 1.4. Core Python Engine Architecture Audit

A comprehensive, line-grounded audit across all core modules confirms the following internal structures and operational boundaries:

#### 1.4.1. Models & Data Structures (`address_standardizer/models.py`)
- **`SpatialResolutionResult`** (`models.py`, lines 8–38):
  - Dataclass utilizing `slots=True` containing `latitude`, `longitude`, `precision`, `accuracy_radius_meters`, `stage` (1..4, 0 if UNRESOLVED), `source`, `h3_res10`, `parcel_id`, `execution_time_ms`, and `metadata`.
  - **Null Island Invariant** (`models.py`, lines 22–37): When `precision == "UNRESOLVED"`, `as_dict()` explicitly forces `latitude: None`, `longitude: None`, and `accuracy_radius_meters: None`. This prevents naive consumers testing `latitude is not None` from mistaking the coordinate `(0.0, 0.0)` in the Atlantic Ocean off the coast of Ghana ("Null Island") for a valid resolved location.
- **`StandardizedAddress`** (`models.py`, lines 75–571):
  - Primary standardized dataclass. In `__post_init__` (`models.py`, lines 96–106), PO Box addresses, private residences, and failed parses automatically strip `rooftop_address` to prevent misleading parcel mappings.
  - Exposes 30+ properties including `confidence_score` (lines 151–156), `routing_tier` (lines 159–164), `failure_reason_codes` (lines 167–174), `rdi` (lines 192–198), `cmra` (lines 200–214), `vacant` (lines 216–230), `dpv_footnotes` (lines 232–239), `deliverability` (lines 266–282), `secondary_prompt_required` (lines 284–316), `reference_validation` (lines 396–403), `explanation` (lines 405–412), and `alternatives` (lines 423–430).
  - Serializers: `as_dict(include_metadata=False, include_rooftop=False, include_explanation=False)` (`models.py`, lines 473–552), `as_extended_dict()` (lines 554–556), and `format_upu()` (lines 558–570).

#### 1.4.2. Confidence Scoring & Routing Engine (`address_standardizer/confidence.py`)
- **Routing Tiers** (`confidence.py`, lines 28–32):
  - `AUTO_PASS`: Address is verified, fully resolved, and meets all quality thresholds ($S \ge 0.95$ and zero `ERR_*` codes). Suitable for direct automated downstream processing.
  - `FUZZY_REVIEW`: Minor anomalies or ambiguities detected ($0.80 \le S < 0.95$, or non-critical warnings). Suitable for programmatic verification or agent inspection.
  - `MANUAL_STEWARDSHIP`: Severe structural failure ($S < 0.80$ or any critical `ERR_*` code). Mandates human or autonomous agent intervention.
- **Reason Codes Catalog** (`confidence.py`, lines 34–58):
  - **11 Error Codes (`ERR_*`)**: `ERR_ZIP_STATE_MISMATCH`, `ERR_MISSING_HOUSE_NUM`, `ERR_UNRESOLVED_SUFFIX`, `ERR_AMBIGUOUS_DUAL_ADDR`, `ERR_DPV_UNCONFIRMED`, `NO_STREET_NUMBER`, `ERR_PARSE_FAILED`, `ERR_EMPTY_ADDRESS`, `ERR_EMPTY_STREET`, `ERR_CITY_ANOMALY`, `ERR_UNRESOLVED_LOCALITY`.
  - **12 Warning Codes (`WARN_*`)**: `WARN_CRA_HUB_DETECTED`, `WARN_PMB_DISGUISED`, `WARN_RESIDENTIAL_COMM`, `WARN_TYPO_HEALED`, `WARN_STATE_CORRECTED_FROM_ZIP`, `WARN_CMRA_DETECTED`, `WARN_MISSING_SECONDARY_UNIT`, `WARN_VACANT_DELIVERY_POINT`, `WARN_LANDMARK_CAMPUS_PREMISE`, `WARN_LOCALITY_ONLY`, `WARN_POSTAL_IN_CITY`, `WARN_SINGLE_LINE_NO_COMMA`.
- **Composite Scoring Formula** (`confidence.py`, lines 117–123, 448–456):
  $$S = 0.35 \times S_{\text{parse}} + 0.35 \times S_{\text{ref}} + 0.15 \times S_{\text{geo}} + 0.15 \times S_{\text{cross}}$$
  - `WEIGHT_PARSE = 0.35`: Component completeness and token recognizability.
  - `WEIGHT_REF = 0.35`: Reference dataset agreement (ZIP-to-state and USPS DPV match).
  - `WEIGHT_GEO = 0.15`: Spatial resolution cascade stage and accuracy radius.
  - `WEIGHT_CROSS = 0.15`: Internal component consistency and cross-field validation.
  - **Critical Invariant** (`confidence.py`, lines 457–477): Critical errors (`ERR_MISSING_HOUSE_NUM`, `parse_failed`) immediately route to `MANUAL_STEWARDSHIP` regardless of the mathematical score $S$. `AUTO_PASS` strictly requires $S \ge 0.95$ AND zero `ERR_*` codes.
- **Per-Field Confidence** (`confidence.py`, lines 519–687):
  Computes independent confidence values for `street1`, `street2`, `city`, `state`, `postal_code`, and `country`, enabling fine-grained field-level auditing.

#### 1.4.3. Delivery Intelligence & DPV Footnotes (`address_standardizer/delivery.py`)
- **13 Standard USPS DPV Footnotes** (`delivery.py`, lines 30–45):
  - `AA`: Input address matched to ZIP+4 file.
  - `A1`: Input address not matched to ZIP+4 file.
  - `BB`: Number and street matched active delivery point.
  - `CC`: Secondary unit confirmed.
  - `N1`: High-rise / multi-unit address missing secondary information.
  - `M1`: Primary number missing.
  - `M3`: Primary number invalid.
  - `P1`: Box number missing.
  - `PB`: PO Box street address.
  - `RR`: Rural Route address.
  - `F1`: Military / diplomatic address.
  - `G1`: General delivery address.
  - `U1`: Unique ZIP code.
- **RDI & Deliverability** (`delivery.py`, lines 47–52, 77–82):
  - Residential Delivery Indicator (`RDI`): `Residential`, `Commercial`, `Unknown`.
  - Deliverability Classification (`Deliverability`): `DELIVERABLE`, `REQUIRES_SECONDARY`, `UNDELIVERABLE`.
- **Secondary Unit Prompting** (`delivery.py`, lines 316–327):
  When DPV Footnote `N1` is detected on multi-unit buildings, the engine automatically sets `secondary_prompt_required = True`, `prompt_message = "Requires Suite / Apartment Number"`, and populates `suggested_secondary_units = ["STE", "FL", "UNIT", "APT"]`.

#### 1.4.4. Coordination & Public Entry Points (`address_standardizer/standardizer.py`)
- **Public API Signature** (`standardizer.py`, lines 250–269):
  ```python
  def standardize_address(
      street1: Optional[str] = None,
      street2: Optional[str] = None,
      city: Optional[str] = None,
      state: Optional[str] = None,
      postal_code: Optional[str] = None,
      country: Optional[str] = None,
      is_vacant: Optional[bool] = None,
      enable_fuzzy: bool = True,
      enable_geocoding: bool = False,
      use_cache: bool = True,
      allow_locality: bool = False,
      finalize: bool = True,
      correct_state_from_zip: Optional[bool] = None,
      reference_provider: Optional[Any] = None,
      explain: bool = False,
      alternatives: int = 0,
      calibrator: Optional[Any] = None,
      **kwargs: Any,
  ) -> StandardizedAddress:
      ...
  ```
- **Deterministic Key Derivations** (`standardizer.py`, lines 97–149):
  - `generate_building_key`: `{STREET1}||{CITY}|{STATE}|{ZIP5_OR_POSTAL}|{COUNTRY_ALPHA3}`. Uniquely groups all tenants in a multi-tenant physical building.
  - `generate_normalized_address_key`: `{STREET1}|{STREET2}|{CITY}|{STATE}|{ZIP5_OR_POSTAL}|{COUNTRY_ALPHA3}`. Exact unit-level entity resolution key.

#### 1.4.5. Multi-Tier Reference Caching (`address_standardizer/cache.py` & `cache_backends.py`)
- **Three-Tier Architecture**:
  - **L1 In-Memory LRU** (`cache.py`, lines 81–100): Thread-safe in-process cache, capacity 50,000 entries, lookup latency $< 0.001\text{ms}$.
  - **L2 Persistent SQLite WAL** (`cache.py`, lines 102–145): Embedded SQLite store using Write-Ahead Logging (`WAL`), lookup latency $< 0.050\text{ms}$.
  - **Distributed Redis Tier** (`cache_backends.py`, lines 41–55): Enterprise shared cache supporting `redis://`, `rediss://`, and `unix://` connection strings with fail-open circuit breaking (network drops degrade cleanly to cache misses).
- **Cache Key & Multi-Tenant Namespace Isolation** (`cache.py`, lines 33–79):
  Keys follow `street1|street2|city|state|postal_code|country|flags`. Multi-tenant isolation is enforced via Python `ContextVar[str] CACHE_NAMESPACE`, prefixing keys with `@<namespace>`.

#### 1.4.6. Corporate Transparency Registry (`address_standardizer/registry.py` & `registry_data.py`)
- **FinCEN CTA/BOI Compliance Hubs** (`registry_data.py`, lines 8–26):
  Catalogs Commercial Registered Agents, Corporate Formation Agents, Virtual Offices, and Mail-drop CMRAs in Delaware, Wyoming, Nevada, the UK, Switzerland, and offshore secrecy jurisdictions (Cayman Islands, BVI, Bermuda).
- **Three Core Anti-Fraud Invariants** (`registry.py`, lines 7–9):
  1. *Multi-Tenant Skyscraper Suite Isolation*: High-rise commercial addresses require exact secondary unit matching before tagging corporate risk to prevent innocent co-located businesses from false-positive association.
  2. *Private Residence Protection*: Strictly prevents corporate entity co-location merges into flagged residential properties (`is_private_residence = True`).
  3. *Formation Hub Co-Location Isolation*: Blocks false-positive entity mergers of unrelated legal entities registered at the same formation agency address.

#### 1.4.7. Analytical UDFs (`address_standardizer/arrow.py`)
- **Apache Arrow & Polars** (`arrow.py`, lines 37–294):
  `standardize_arrow` and `standardize_polars` provide vectorized chunk processing for `pyarrow.Table`, `polars.DataFrame`, and `polars.LazyFrame` with optional single-column StructArray output.
- **DuckDB In-Database SQL UDFs** (`arrow.py`, lines 300–489):
  Registers 7 SQL functions directly into DuckDB connections:
  - `standardize_address(...) -> STRUCT` (line 373)
  - `standardize_address_full(...) -> STRUCT` (line 396)
  - `standardize_address_text(...) -> STRUCT` (line 415)
  - `standardize_address_key(...) -> VARCHAR` (line 433)
  - `standardize_address_key_text(...) -> VARCHAR` (line 450)
  - `standardize_deliverability(...) -> VARCHAR` (line 467)
  - `standardize_deliverability_text(...) -> VARCHAR` (line 484)

#### 1.4.8. Explainability Engine (`address_standardizer/explain.py`)
- **44 Stable Transformation Rule IDs** (`explain.py`, lines 40–102):
  Captures a precise trace of every modification performed during parsing:
  - *Surface normalization*: `case_normalized`, `punctuation_normalized`, `diacritics_folded`.
  - *Street & unit tokens*: `street_type_abbreviation`, `directional_abbreviation`, `ordinal_normalized`, `unit_designator_abbreviation`, `unit_designator_inserted`, `number_words_to_digits`, `typo_heal_street`, `unit_split`, `secondary_promoted_to_street`, `care_of_removed`, `private_residence_detected`.
  - *City, state & postal*: `typo_heal_city`, `state_abbreviated`, `state_from_zip`, `state_corrected_from_zip`, `postal_normalized`, `postal_extracted_from_text`.
  - *Country & script*: `country_normalized`, `country_inferred_from_script`, `country_inferred_from_postal`, `script_single_line_split`.
  - *Reference data*: `reference_confirmed`, `reference_place_mismatch`, `reference_state_mismatch`.

#### 1.4.9. Spatial & International Subsystems
- **Offline Spatial Geocoding Cascade** (`address_standardizer/spatial/engine.py`, lines 640–895):
  Operates 100% offline using an embedded SQLite R\*Tree spatial index (`minX`, `maxX`, `minY`, `maxY`) answering window queries in $< 1.0\text{ms}$.
  - *Stage 1: Confirmed Rooftop / Parcel Match* ($\sim 3\text{m} - 5\text{m}$ accuracy).
  - *Stage 2: Street Centerline Range Interpolation* ($35\text{m}$ accuracy, with $+10\text{m}$ curb-side parity offset).
  - *Stage 3: Postal Centroid Match* ($8,000\text{m}$ accuracy).
  - *Stage 4: Municipal / Administrative Centroid Match* ($25,000\text{m} - 50,000\text{m}$ accuracy).
  - *Stage 0: Unresolved* (returns `latitude: None`, `longitude: None`).
  - *H3 Hexagonal Indexing* (`spatial/h3_indexer.py`, lines 1–101): Resolution 10 cell computation via official `h3` library.
- **Universal International Registry & Postal Validation** (`address_standardizer/international/`):
  - *All 249 ISO-3166-1 Countries* (`countries.py`, lines 2530–2766): Full coverage of all alpha-2, alpha-3, numeric codes, and localized aliases.
  - *Global Postal Code Validator* (`postal.py`, lines 574–630): Validates official formats across 194 postal-issuing jurisdictions and gracefully validates the 55 non-postal jurisdictions (UAE, Qatar, Bahamas, Panama, etc.) without false rejection.
  - *UPU S42 Formatter* (`upu.py`, lines 1–210): Canonical national envelope layout generation.

### 1.5. Rust PyO3 Native Acceleration Architecture

- **Crate Configuration (`Cargo.toml`)**:
  Crate name `_address_standardizer_rs`, version `3.3.0`, Rust 2021 edition (`rust-version = "1.83"`). Uses `pyo3 = "0.29"` with `extension-module` feature. Release profile enforces `opt-level = 3`, `lto = true`, and `codegen-units = 1` (`Cargo.toml`, lines 25–29).
- **Architectural Boundary & Python Truth Invariant (`src/lib.rs`, lines 1–8)**:
  `src/lib.rs` explicitly documents the core architectural contract:
  > "The module deliberately exposes only functions whose behaviour is fully specified by the Python reference implementation and checked against it by `tests/native/test_native_parity.py`. Everything else (parsing, suffix/directional tables, key assembly) lives in Python, which is the single source of truth: earlier Rust re-implementations of those rules drifted from the Python tables and produced different keys depending on whether the extension happened to be installed."
- **Exported Native Functions (`src/lib.rs`, lines 130–160)**:
  1. `compute_soundex(token: &str) -> String`
  2. `damerau_levenshtein_distance(s1: &str, s2: &str) -> usize`
  3. `get_engine_name() -> &'static str` (`"Rust_PyO3"`)
  4. `is_native() -> bool` (`true`)
  5. `get_capabilities(py: Python) -> PyResult<Bound<PyDict>>`
- **GIL & Concurrency Interaction**:
  PyO3 executes native C-ABI calls synchronously. Because Soundex and Damerau-Levenshtein operate at sub-microsecond latency, the GIL is briefly retained. True batch multi-core concurrency is achieved at the process level via Python `multiprocessing` chunking (`batch.py`) or external service worker pooling (`server.py`), bypassing GIL constraints across CPU cores.
- **Transparent Pure Python Fallback (`address_standardizer/_native_dispatch.py` & `_pure_python_core.py`)**:
  `try_native(...)` catches `BaseException` to prevent PyO3 panics from crashing host processes. If the native wheel is unbuilt or if `ADDRESS_STANDARDIZER_FORCE_PURE=1` is set, the system transparently falls back to `_pure_python_core.py`, guaranteeing 100% bit-for-bit key equivalence and $> 2,000\text{ rec/s}$ throughput.


---

## 2. AI Agent & LLM Integration Specification

As autonomous software agents (e.g. Claude Code, Cursor Composer, Devin, LangChain/LlamaIndex agents) take over data pipelines, forms automation, customer onboarding, and logistics workflows, `Address-Standardizer` must provide first-class, agent-native integration surfaces. 

This section defines the complete Model Context Protocol (MCP) tool specification, token-efficient response models, the autonomous self-correction state machine, and discovery artifacts (`llms.txt` and Cursor/agent skills).

### 2.1. Model Context Protocol (MCP) Tool Definitions & JSON Schemas

The Model Context Protocol (MCP) enables LLMs to query external services through strongly typed tools. To preserve LLM context windows, tool responses must be compact and token-efficient, returning essential standardized components by default while allowing agents to request rich metadata (`include_metadata=true`) or transformation traces (`include_explanation=true`) only when needed.

#### 2.1.1. Tool 1: `standardize_address`
- **Description**: Parses, standardizes, validates, and geocodes a single unstructured or structured postal address across 249 ISO countries. Computes USPS DPV footnotes, deliverability classification, corporate formation hub risk, and confidence routing tier.

```json
{
  "name": "standardize_address",
  "description": "Standardize, validate, and optionally geocode a single postal address across 249 ISO countries. Returns standardized USPS Pub 28 / UPU S42 components, deliverability, confidence routing tier, and building keys.",
  "parameters": {
    "type": "object",
    "properties": {
      "address": {
        "type": "string",
        "description": "Unstructured single-line address string (e.g., '1600 Amphitheatre Pkwy, Mountain View, CA 94043' or '10 Downing St, London SW1A 2AA')."
      },
      "street1": {
        "type": "string",
        "description": "Primary street address line, PO Box, or rural route (when submitting structured fields)."
      },
      "street2": {
        "type": "string",
        "description": "Secondary unit designator, suite, apartment, floor, or building (e.g., 'Suite 400', 'Apt 3B')."
      },
      "city": {
        "type": "string",
        "description": "City, town, municipality, or dependent locality."
      },
      "state": {
        "type": "string",
        "description": "State, province, region, or administrative territory (e.g., 'CA', 'Ontario', 'Bayern')."
      },
      "postal_code": {
        "type": "string",
        "description": "Postal code, ZIP code, or PIN code."
      },
      "country": {
        "type": "string",
        "description": "ISO-3166-1 alpha-2, alpha-3, or country name (defaults to 'USA' if omitted and cannot be inferred)."
      },
      "enable_geocoding": {
        "type": "boolean",
        "default": false,
        "description": "If true, resolves offline spatial coordinates (latitude, longitude, accuracy radius, H3 res-10 index)."
      },
      "include_metadata": {
        "type": "boolean",
        "default": false,
        "description": "If true, includes DPV footnotes, RDI, vacancy, corporate risk flags, and failure reason codes."
      },
      "explain": {
        "type": "boolean",
        "default": false,
        "description": "If true, provides a step-by-step audit trace of exact transformation rules applied during parsing."
      },
      "correct_state_from_zip": {
        "type": "boolean",
        "default": false,
        "description": "If true, automatically corrects a mismatched state when the postal code definitively identifies a single state."
      }
    },
    "required": []
  }
}
```

- **Compact Response Envelope**:
```json
{
  "street1": "1600 AMPHITHEATRE PKWY",
  "street2": "",
  "city": "MOUNTAIN VIEW",
  "state": "CA",
  "postal_code": "94043",
  "country": "USA",
  "normalized_address_key": "1600 AMPHITHEATRE PKWY||MOUNTAIN VIEW|CA|94043|USA",
  "building_key": "1600 AMPHITHEATRE PKWY||MOUNTAIN VIEW|CA|94043|USA",
  "address_status": "standardized",
  "routing_tier": "AUTO_PASS",
  "confidence_score": 0.985,
  "deliverability": "DELIVERABLE"
}
```

#### 2.1.2. Tool 2: `batch_standardize`
- **Description**: Standardizes a batch of up to 500 postal addresses in a single high-throughput vectorized request, returning standardized records, confidence scores, and routing tiers.

```json
{
  "name": "batch_standardize",
  "description": "High-throughput batch standardization of multiple postal addresses (up to 500 records). Ideal for data cleaning pipelines and bulk verification.",
  "parameters": {
    "type": "object",
    "properties": {
      "addresses": {
        "type": "array",
        "description": "Array of unstructured address strings or structured address objects to standardize.",
        "items": {
          "oneOf": [
            {
              "type": "string",
              "description": "Unstructured address string."
            },
            {
              "type": "object",
              "properties": {
                "street1": { "type": "string" },
                "street2": { "type": "string" },
                "city": { "type": "string" },
                "state": { "type": "string" },
                "postal_code": { "type": "string" },
                "country": { "type": "string" }
              },
              "required": ["street1"]
            }
          ]
        },
        "minItems": 1,
        "maxItems": 500
      },
      "enable_geocoding": {
        "type": "boolean",
        "default": false,
        "description": "Whether to resolve spatial coordinates for all batch records."
      },
      "correct_state_from_zip": {
        "type": "boolean",
        "default": false,
        "description": "Whether to auto-correct state from postal code when unambiguous."
      }
    },
    "required": ["addresses"]
  }
}
```

#### 2.1.3. Tool 3: `validate_postal`
- **Description**: Verifies whether a given postal code conforms to the official postal standards of a specific ISO country, returning formatting diagnostics and extracted components.

```json
{
  "name": "validate_postal",
  "description": "Validate a postal code format against official national standards across 249 ISO countries. Identifies non-postal nations and extracts structural components.",
  "parameters": {
    "type": "object",
    "properties": {
      "postal_code": {
        "type": "string",
        "description": "Postal code to validate (e.g., '94043', 'SW1A 1AA', 'K1A 0B1', '10115')."
      },
      "country": {
        "type": "string",
        "description": "ISO-3166-1 alpha-2, alpha-3, or country name (e.g., 'US', 'GB', 'CA', 'DE'). Defaults to 'US'."
      }
    },
    "required": ["postal_code"]
  }
}
```

- **Compact Response Envelope**:
```json
{
  "is_valid": true,
  "postal_code": "SW1A 1AA",
  "country_iso2": "GB",
  "country_iso3": "GBR",
  "country_name": "United Kingdom",
  "has_postal_system": true,
  "format_pattern": "^[A-Z]{1,2}[0-9][A-Z0-9]? [0-9][A-Z]{2}$",
  "diagnostics": "Matched UK alphanumeric outward/inward postcode specification"
}
```

#### 2.1.4. Tool 4: `autocomplete_address`
- **Description**: Provides real-time typeahead suggestions with prefix-trie search, Levenshtein edit-distance tolerance, geographic proximity biasing, and secondary unit prompting.

```json
{
  "name": "autocomplete_address",
  "description": "Real-time address autocomplete and typeahead suggestion engine with fuzzy typo tolerance and geographic proximity biasing.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Partial address string entered by the user (e.g., '1600 Amphitheatre Pk')."
      },
      "limit": {
        "type": "integer",
        "default": 5,
        "minimum": 1,
        "maximum": 20,
        "description": "Maximum number of autocomplete suggestions to return."
      },
      "latitude": {
        "type": "number",
        "description": "User latitude for proximity-biased candidate ranking."
      },
      "longitude": {
        "type": "number",
        "description": "User longitude for proximity-biased candidate ranking."
      },
      "country": {
        "type": "string",
        "default": "USA",
        "description": "Country filter (ISO alpha-2 or alpha-3)."
      }
    },
    "required": ["query"]
  }
}
```

#### 2.1.5. Tool 5: `explain_parse`
- **Description**: Returns an exhaustive audit trace explaining each transformation applied during parsing, highlighting healed typos, re-ordered tokens, extracted secondary units, and candidate alternatives.

```json
{
  "name": "explain_parse",
  "description": "Detailed explanation and audit trace of how an address was parsed and standardized, including 44 stable rule IDs, token rewrites, and alternative interpretations.",
  "parameters": {
    "type": "object",
    "properties": {
      "address": {
        "type": "string",
        "description": "Raw address string to explain."
      },
      "country": {
        "type": "string",
        "description": "Country code hint (optional)."
      },
      "alternatives": {
        "type": "integer",
        "default": 3,
        "minimum": 0,
        "maximum": 5,
        "description": "Number of alternative parsing interpretations to generate."
      }
    },
    "required": ["address"]
  }
}
```

- **Compact Response Envelope**:
```json
{
  "standardized_address": {
    "street1": "100 MAIN ST",
    "street2": "STE 400",
    "city": "SEATTLE",
    "state": "WA",
    "postal_code": "98101",
    "country": "USA"
  },
  "explanation": [
    {
      "field": "street1",
      "before": "100 Main St Ste 400",
      "after": "100 MAIN ST",
      "rule": "unit_split",
      "detail": "a trailing unit was moved from street1 to street2"
    },
    {
      "field": "street2",
      "before": "Ste 400",
      "after": "STE 400",
      "rule": "unit_designator_abbreviation",
      "detail": "unit designator replaced by its abbreviation (SUITE -> STE)"
    }
  ],
  "alternatives": [
    {
      "street1": "100 MAIN ST",
      "street2": "APT 400",
      "score": 0.88,
      "reason": "Alternate unit designator interpretation"
    }
  ]
}
```

---

### 2.2. Agent Self-Correction & Confidence Routing

Autonomous agents must not treat address standardization as a binary success/failure operation. Instead, agents must actively inspect the returned metadata to self-correct malformed inputs, prompt users for missing details, or route cases to human review queues.

#### 2.2.1. Interpretation of Confidence Scores and Routing Tiers
- **`AUTO_PASS` ($S \ge 0.95$ and zero `ERR_*` codes)**:
  - *Agent Action*: Accept the standardized address immediately. Proceed with order fulfillment, shipment booking, database insertion, or CRM synchronization.
- **`FUZZY_REVIEW` ($0.80 \le S < 0.95$ or non-fatal `WARN_*` codes)**:
  - *Agent Action*: The core delivery point is recognizable, but minor ambiguities exist (e.g. healed typos, state inferred from ZIP, or unpunctuated input). The agent should inspect `failure_reason_codes`:
    - If non-critical (e.g. `WARN_TYPO_HEALED` or `WARN_STATE_CORRECTED_FROM_ZIP`), accept with an audit note.
    - If `WARN_MISSING_SECONDARY_UNIT` is present, execute the Secondary Unit Recovery Playbook.
- **`MANUAL_STEWARDSHIP` ($S < 0.80$ or any `ERR_*` code)**:
  - *Agent Action*: Halt automatic processing. Enter the autonomous self-correction loop. If self-correction fails, generate an explicit clarification prompt for the user or dispatch to a human stewardship exception queue.

#### 2.2.2. Operational Reason Code Matrix & Agent Recovery Playbooks

| Reason Code | Category | Root Cause | Autonomous Agent Recovery Action |
| :--- | :---: | :--- | :--- |
| `ERR_MISSING_HOUSE_NUM` / `NO_STREET_NUMBER` | Fatal Error | Address contains street name but no primary house/building number (e.g. `Main St, Boston, MA`). | Check conversation history or context for a house number. If not found, prompt user: *"Please provide the building or house number on [street]."* |
| `ERR_ZIP_STATE_MISMATCH` | Fatal Error | Postal code belongs to a different state than the state provided (e.g. `90210` with `NY`). | Query `explain_parse` or reference database. Ask user: *"Did you mean [City, CA 90210] or [City, NY <ZIP>]?"* If `correct_state_from_zip=True` is authorized, auto-correct state. |
| `ERR_AMBIGUOUS_DUAL_ADDR` | Fatal Error | Input contains both a physical street line and a PO Box (e.g. `100 Main St PO Box 45`). | Clarify delivery intent: USPS mail prefers `PO Box`, while courier freight (FedEx/UPS) requires physical `100 Main St`. Split or prompt user for preferred delivery mode. |
| `ERR_DPV_UNCONFIRMED` | Fatal Error | Street number and name do not exist in USPS delivery point databases. | Verify spelling using `autocomplete_address` with proximity biasing. Prompt user to confirm if the address is a newly constructed property. |
| `ERR_PARSE_FAILED` | Fatal Error | Engine could not segment input tokens into viable address fields. | Reformat input: insert commas between suspected tokens, strip foreign prefixes, or submit structured key-value pairs. |
| `ERR_EMPTY_ADDRESS` / `ERR_EMPTY_STREET` | Fatal Error | Input string is whitespace or lacks street tokens. | Prompt user for valid address input. |
| `WARN_MISSING_SECONDARY_UNIT` | Warning / DPV N1 | Building is a confirmed multi-unit high-rise or commercial complex, but unit/suite is omitted. | Check metadata `suggested_secondary_units`. Prompt user: *"Address requires a suite, apartment, or floor number. Please specify your Suite or Apt."* |
| `WARN_SINGLE_LINE_NO_COMMA` | Warning | Address was submitted as a commaless line, which drops parsing accuracy from 90.4% to 51.7%. | Self-correct: re-tokenize line using postal code and known state anchors, insert commas (`"{street}, {city}, {state} {zip}"`), and re-invoke `standardize_address`. |
| `WARN_TYPO_HEALED` | Warning | Typo was healed via phonetic or Damerau-Levenshtein matching. | Inform user of normalization: *"Corrected [raw_street] to [standardized_street]."* |
| `WARN_STATE_CORRECTED_FROM_ZIP` | Warning | Mismatched state was overridden by authoritative postal code directory. | Accept address; log audit record showing previous state and corrected state. |
| `WARN_CRA_HUB_DETECTED` | Governance | Address matches a FinCEN corporate formation hub or registered agent office. | If onboarding a corporate entity, mandate suite-level verification to prevent false-positive co-location mergers. |
| `WARN_PMB_DISGUISED` | Governance | Private mailbox (PMB) was disguised as a suite (e.g. `# 100` instead of `PMB 100`). | Normalize unit designator to `PMB` in accordance with USPS Pub 28 Section 522. |
| `WARN_VACANT_DELIVERY_POINT` | Warning | Delivery point is flagged as vacant by postal carriers. | Warn user that mail delivery may be suspended at this address. |

#### 2.2.3. Autonomous Agent Self-Correction State Machine

When an address produces a `MANUAL_STEWARDSHIP` or `FUZZY_REVIEW` outcome, the agent executes the following deterministic recovery workflow:

```
                      [Input Address Received]
                                  │
                                  ▼
                     [standardize_address Call]
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │ What is the routing_tier?    │
                   └──────────────┬───────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
    [AUTO_PASS]             [FUZZY_REVIEW]        [MANUAL_STEWARDSHIP]
         │                        │                        │
  (Pass to system)        Check reason_codes         Check error codes
                                  │                        │
                     ┌────────────┴────────────┐     ┌─────┴─────────────────────┐
                     ▼                         ▼     ▼                           ▼
            [Missing Secondary]       [Commaless]   [Fatal Missing Number]   [Mismatched State]
              (DPV Code N1)           (WARN_NO_COMMA)        │                           │
                     │                         │     Check context/history    Is ZIP unambiguous?
             Inspect conversation              │             │                           │
             for Suite / Apt / Unit    Re-tokenize & ┌───────┴───────┐           ┌───────┴───────┐
                     │                 insert commas │ Found         │ Not Found │ Yes           │ No
             ┌───────┴───────┐         & re-parse    ▼               ▼           ▼               ▼
             │ Found         │ Not Found       │  Apply number    Prompt user  Auto-correct    Prompt user
             ▼               ▼                 │  & re-parse      for number   via ZIP         to clarify
        Re-parse with   Prompt user for        │
        suite added     Suite / Apt            │
             │               │                 │
             └───────────────┼─────────────────┘
                             ▼
                 [Re-evaluated Standardize]
                             │
                     Check New Routing Tier
```

##### Heuristic 1: Recovering from Commaless Parsing Degradation
Held-out evaluations confirm that commaless input drops exact match from 90.4% to 51.7% (`REPORT_HOLDOUT.md`, line 43). When `WARN_SINGLE_LINE_NO_COMMA` is triggered:
1. Agent locates the trailing postal code (e.g. 5-digit ZIP or regex `\b[A-Z0-9]{3,8}\b`).
2. Agent scans backward from the postal code to identify the 2-letter state abbreviation or full state name.
3. Agent scans backward from the state to identify the municipal city token.
4. Agent reformats the string into canonical comma-delimited form: `f"{street_tokens}, {city_tokens}, {state_token} {postal_token}"`.
5. Agent re-invokes `standardize_address` with the formatted string.

##### Heuristic 2: Handling High-Rise Secondary Units (DPV Footnote `N1`)
When `DPVFootnote.N1` and `WARN_MISSING_SECONDARY_UNIT` are present:
1. Agent inspects conversation context for secondary descriptors (`Suite`, `Ste`, `Apt`, `Unit`, `Fl`, `#`).
2. If found, agent appends the secondary unit to `street2` and re-runs `standardize_address`.
3. If not found in context, agent generates a user-facing prompt utilizing `suggested_secondary_units`:
   > *"100 Main Street is a multi-unit building. Could you please specify your Suite, Apartment, or Floor number?"*

---

### 2.3. AI Discovery & Context Artifacts

To enable coding assistants (Claude Code, Cursor, GitHub Copilot, Gemini CLI) to implement correct `Address-Standardizer` integrations without hallucinating deprecated or non-existent APIs, the repository must supply standardized LLM discovery documents.

#### 2.3.1. Complete Draft of `llms.txt`

```text
# Address-Standardizer
> High-performance, enterprise-grade address parsing, postal validation, and spatial geocoding in Python and native Rust.

Address-Standardizer standardizes messy, unstructured, and international address strings into canonical USPS Publication 28 and UPU S42 components. It features offline SQLite R*Tree geocoding, 249 ISO country grammars, DPV footnotes, FinCEN corporate secrecy hub detection, and Arrow/Polars/DuckDB analytical UDFs.

## Installation & Setup
- Core Python: `pip install address-standardizer`
- Full Enterprise (FastAPI server + Arrow + Polars + DuckDB): `pip install "address-standardizer[server,arrow]"`
- Docker Daemon: `docker run -p 8000:8000 ghcr.io/jacob-white/address-standardizer:latest`

## Core Python API
- `standardize_address(street1=None, ..., country=None, enable_geocoding=False, explain=False) -> StandardizedAddress`
  Primary standardization entry point. Accepts single-line string or structured keyword arguments.
- `batch_standardize(addresses, enable_geocoding=False) -> List[StandardizedAddress]`
  Vectorized batch standardization for lists of strings or dictionaries.
- `validate_postal_code(postal_code: str, country_code: str = "US") -> bool`
  Validates postal code against national standards across 249 ISO countries.
- `autocomplete_address(query: str, limit: int = 5, latitude=None, longitude=None) -> List[dict]`
  Real-time typeahead suggestions with proximity biasing.

## Data Structures
- `StandardizedAddress`:
  - Fields: `street1`, `street2`, `city`, `state`, `postal_code`, `country`, `normalized_address_key`, `building_key`, `address_status`.
  - Properties: `confidence_score` (0.0-1.0), `routing_tier` ("AUTO_PASS" | "FUZZY_REVIEW" | "MANUAL_STEWARDSHIP"), `deliverability` ("DELIVERABLE" | "REQUIRES_SECONDARY" | "UNDELIVERABLE"), `dpv_footnotes` (e.g. ["AA", "BB", "N1"]), `latitude`, `longitude`, `precision`.
  - Serializers: `.as_dict()`, `.as_extended_dict()`, `.format_upu()`.

## REST API Endpoints
- `POST /v1/standardize`: Single address standardization.
- `POST /v1/batch`: Batch standardization (supports `Accept: application/x-ndjson` streaming).
- `POST /v1/autocomplete`: Typeahead autocomplete suggestions.
- `GET /health`: Health and readiness probe.
- `GET /metrics`: Prometheus and JSON operational metrics.

## Key Invariants
- 100% statement and branch test coverage enforced (`fail_under = 100`).
- Pure Python fallback is guaranteed if compiled native extensions are absent.
- Critical errors (`ERR_MISSING_HOUSE_NUM`, `parse_failed`) strictly route to `MANUAL_STEWARDSHIP`.
```

#### 2.3.2. Complete Draft of `llms-full.txt`

```text
# Address-Standardizer: Full Technical Reference & API Manual

## Architectural Contracts
Address-Standardizer standardizes physical and postal addresses. It uses a three-tier execution pipeline:
1. Fast-Path Regex & Structured Trie: Sub-millisecond parsing for clean addresses.
2. Deterministic Rule Matrix: Reverse-anchor token scanning with 44 stable transformation rules.
3. Statistical CRF Fallback: Conditional Random Field token segmentation via usaddress.

## Confidence Scoring & Routing State Machine
The composite confidence score S is computed as:
  S = 0.35 * S_parse + 0.35 * S_ref + 0.15 * S_geo + 0.15 * S_cross

Routing decisions follow strict thresholds:
- AUTO_PASS: S >= 0.95 and zero ERR_* codes.
- FUZZY_REVIEW: 0.80 <= S < 0.95 and zero fatal ERR_* codes.
- MANUAL_STEWARDSHIP: S < 0.80 or any critical error (ERR_MISSING_HOUSE_NUM, ERR_PARSE_FAILED, ERR_ZIP_STATE_MISMATCH).

## Failure & Warning Reason Codes
- ERR_MISSING_HOUSE_NUM: Street line lacks a house number.
- ERR_ZIP_STATE_MISMATCH: Postal code contradicts state.
- ERR_AMBIGUOUS_DUAL_ADDR: Both street address and PO Box present.
- ERR_DPV_UNCONFIRMED: Delivery point not found in postal database.
- WARN_MISSING_SECONDARY_UNIT: Multi-unit building missing Suite/Apt (DPV N1).
- WARN_SINGLE_LINE_NO_COMMA: Unpunctuated line; accuracy degrades without commas.
- WARN_TYPO_HEALED: Typo corrected within Damerau-Levenshtein distance <= 2.
- WARN_CRA_HUB_DETECTED: Address is a commercial registered agent hub.

## Analytical Stack UDF Integration
- Apache Arrow: `address_standardizer.arrow.standardize_arrow(table)`
- Polars: `address_standardizer.arrow.standardize_polars(df_or_lf)`
- DuckDB: `address_standardizer.arrow.register_duckdb_udfs(con)`
  Registers SQL functions: `standardize_address(...)`, `standardize_address_text(...)`, `standardize_address_key(...)`.
```

#### 2.3.3. Portable Agent Skill Definition (`.agents/skills/address-standardizer/SKILL.md`)

```markdown
---
name: address-standardizer
description: Best practices and tool-calling patterns for parsing, validating, and geocoding postal addresses using the Address-Standardizer engine.
triggers:
  - "standardize address"
  - "parse address"
  - "validate postal code"
  - "address autocomplete"
  - "USPS Pub 28"
  - "DPV footnote"
---

# Address-Standardizer Agent Skill

When integrating or executing address standardization tasks, follow these operational rules:

## 1. Input Formatting Best Practice
- Never pass unpunctuated single-line addresses if commas can be inferred. Commaless lines drop exact-match accuracy from 90.4% to 51.7%.
- Separate street line, city, state, and postal code with commas: `"123 Main St, Springfield, IL 62701"`.
- If structured components are available, pass them as explicit arguments:
  ```python
from address_standardizer import standardize_address

result = standardize_address(
    street1="123 Main St",
    city="Springfield",
    state="IL",
    postal_code="62701",
    country="USA"
)
  ```

## 2. Confidence Tier & Error Handling
- Always inspect `result.routing_tier`:
  - `AUTO_PASS`: Safely persist or dispatch address.
  - `FUZZY_REVIEW`: Inspect `result.failure_reason_codes`. If `WARN_MISSING_SECONDARY_UNIT` is present, prompt the user for their Suite or Apartment number.
  - `MANUAL_STEWARDSHIP`: Do not silently overwrite user input. Inspect `result.failure_reason_codes` and ask for clarification.

## 3. FinCEN & Anti-Fraud Invariants
- Commercial Registered Agent hubs (`result.is_registered_agent_hub == True`) host thousands of unrelated businesses. Never merge corporate entities sharing a registered agent address unless their secondary suite/room numbers match exactly.
- Private residences (`result.is_private_residence == True`) must never have corporate entity co-locations merged.

## 4. Multi-Language SDK Conventions
- When writing TypeScript/Node.js, import `AddressStandardizerClient` from `@address-standardizer/client`.
- When processing massive tabular data in Python, use `standardize_polars(df)` or `standardize_arrow(table)` rather than looping with `standardize_address`.
```


---

## 3. Developer Experience (DX) & SDK Parity Plan

A world-class developer experience requires minimal friction across the entire developer lifecycle: from initial ad-hoc exploration in interactive notebooks to high-concurrency microservice deployment and enterprise data warehouse integration.

### 3.1. Developer Ergonomics & API Surface Modernization

#### 3.1.1. Zero-Config Open-Data Reference Validation
Currently, offline reference validation requires developers to manually download and point to SQLite databases (`reference_provider = SqliteReferenceProvider(path)`).
- **Proposal**: Introduce zero-config embedded reference verification. If no custom database path is specified, the engine lazily accesses an embedded, compressed SQLite reference database containing US ZIP5 centroids, state boundaries, and major municipal gazetteers packaged directly with the distribution or cached in `~/.cache/address_standardizer/`.
- **Developer Experience**:
```python
from address_standardizer import standardize_address

# Zero configuration required; automatically validates ZIP/state agreement
result = standardize_address("100 Main St, Seattle, WA 98101", enable_reference_validation=True)
assert result.reference_validation.is_confirmed is True
```

#### 3.1.2. Single-Call Validation Helper (`validate_address`)
Developers frequently need a boolean check or a quick validation summary without dealing with full dataclass instantiation and key generation.
- **Proposed Signature**:
```python
def validate_address(
    address: Union[str, Dict[str, str]],
    country: str = "US",
    strict: bool = False
) -> AddressValidationResult:
    """Lightweight address validation returning deliverability, validity, and error messages."""
    ...
```
- **Example Usage**:
```python
from address_standardizer import validate_address

validation = validate_address("1600 Amphitheatre Pkwy, Mountain View, CA 94043")
if not validation.is_valid:
    print(f"Address issue: {validation.rejection_reason}")
```

#### 3.1.3. Pydantic v2 & TypedDict Schema Exports
To integrate seamlessly into FastAPI services, LangChain models, and Pydantic validation workflows, `Address-Standardizer` should provide native Pydantic v2 model serializers:
```python
from address_standardizer.schemas import AddressSchema, StandardizedAddressPydantic

# Ingest and validate incoming HTTP payload
@app.post("/verify")
def verify(address: AddressSchema) -> StandardizedAddressPydantic:
    std = standardize_address(**address.model_dump())
    return StandardizedAddressPydantic.from_standardized(std)
```

#### 3.1.4. Native Async Client & High-Concurrency Primitives
For high-concurrency asyncio applications, provide an `AsyncAddressStandardizerClient` utilizing `httpx` with persistent connection pooling, automatic circuit breaking, and keepalive management.

---

### 3.2. Cross-Language SDK Parity Matrix & Architecture Recommendations

The repository currently provides SDKs in three enterprise languages alongside the core Python library and REST service:
- **TypeScript**: `sdks/typescript/`
- **Go**: `sdks/go/`
- **.NET (C#)**: `sdks/dotnet/`

#### 3.2.1. Feature Parity Matrix

| Feature / Capability | Core Python (`standardizer.py`) | REST Server (`server.py`) | TypeScript SDK (`sdks/typescript`) | Go SDK (`sdks/go`) | .NET SDK (`sdks/dotnet`) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Single Address Standardize** | `standardize_address` | `POST /v1/standardize` | `client.standardize()` | `client.Standardize()` | `client.StandardizeAsync()` |
| **Batch Standardize (JSON Array)** | `batch_standardize` | `POST /v1/batch` | `client.standardizeBatch()` | `client.StandardizeBatch()` | `client.StandardizeBatchAsync()` |
| **Batch NDJSON Streaming** | `stream_standardize_csv` | `POST /v1/batch` (`Accept: application/x-ndjson`) | `client.streamBatch()` | `client.StreamBatchRecords()` | `client.StreamBatchRecordsAsync()` |
| **Autocomplete / Typeahead** | `autocomplete_address` | `GET/POST /v1/autocomplete` | `client.autocomplete()` | `client.Autocomplete()` & `AutocompleteGetRequest()` | `client.AutocompleteAsync()` & `AutocompleteGetAsync()` |
| **Health & Readiness Check** | N/A (library) | `GET /health`, `/health/ready`, `/health/live` | `client.health()` | `client.Health()` | `client.GetHealthAsync()` |
| **Telemetry & Metrics** | N/A (library) | `GET /metrics` (JSON & Prometheus) | `client.metrics()` | ❌ Missing | ❌ Missing |
| **Dedicated Postal Code Validation** | `validate_postal_code` | ❌ No dedicated REST endpoint | ❌ Missing | ❌ Missing | ❌ Missing |
| **Explanation Trace Param** | `explain=True` | `include_explanation=true` | ⚠️ Field in options, no typed model | ⚠️ Field in options, no typed model | ⚠️ Field in options, no typed model |
| **Alternatives Param** | `alternatives=N` | `alternatives=N` | ⚠️ Field in options, no typed model | ⚠️ Field in options, no typed model | ⚠️ Field in options, no typed model |
| **Stewardship Review Endpoint** | `get_audit_ledger()` | `POST /v1/review` | ❌ Missing | ❌ Missing | ❌ Missing |
| **Stewardship Audit Query** | `ledger.list_records()` | `GET /v1/audit` | ❌ Missing | ❌ Missing | ❌ Missing |
| **Capabilities Endpoint** | `get_capabilities()` | `GET /v1/capabilities` | ❌ Missing | ❌ Missing | ❌ Missing |
| **Automatic Retry / Jittered Backoff** | N/A | N/A | ❌ Missing (timeout/abort only) | ❌ Missing (transport only) | ❌ Missing (HttpClient timeout only) |
| **Frontend Framework Hooks** | N/A | N/A | ✅ `useAddressAutocomplete` (React) | N/A | N/A |

#### 3.2.2. Concrete Recommendations to Close SDK Gaps

1. **Implement Automated Exponential Backoff with Jitter**:
   - Currently, none of the client SDKs automatically retry transient errors. When operating in distributed cloud environments, rate-limit responses (`429 Too Many Requests`) and service degradation (`503 Service Unavailable`, `502 Bad Gateway`, `504 Gateway Timeout`) require resilient retries.
   - *Target Algorithm*: Decorrelated exponential backoff with full jitter:
     $$t_{\text{sleep}} = \min(t_{\text{max}}, \text{Uniform}(0, t_{\text{base}} \times 2^{\text{attempt}}))$$
   - Configurable parameters: `max_retries` (default: 3), `base_delay_ms` (default: 200ms), `max_delay_ms` (default: 3000ms), `retryable_status_codes: [429, 502, 503, 504]`. Respect `Retry-After` HTTP headers when present.

2. **Add Dedicated Postal Validation REST Endpoint & SDK Methods**:
   - Add `POST /v1/validate-postal` and `GET /v1/validate-postal?code=...&country=...` to `server.py`.
   - Implement `client.validatePostalCode(code, country)` across TypeScript, Go (`client.ValidatePostalCode`), and .NET (`client.ValidatePostalCodeAsync`).

3. **Expose Administrative & Audit Ledger Endpoints**:
   - Provide client methods for `/v1/review` (submitting manual corrections) and `/v1/audit` (querying the stewardship ledger) in Go, TypeScript, and .NET.

4. **Strongly Type Explanation & Alternatives in SDK Models**:
   - Replace untyped `any` or `Dictionary<string, object>` with concrete models:
     - TypeScript: `ExplanationRecord { field: string; before: string; after: string; rule: string; detail: string; }`
     - Go: `type ExplanationRecord struct { Field string, Before string, After string, Rule string, Detail string }`
     - .NET: `public class ExplanationRecord { public string Field { get; set; } ... }`

---

### 3.3. Production-Ready Framework Recipes

#### 3.3.1. Recipe 1: FastAPI Lifespan Dependency Injection Wrapper
Production pattern implementing lazy singleton cache and spatial database warm-up on server startup:

```python
"""Production FastAPI integration recipe for Address Standardizer."""

from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, Field

from address_standardizer import standardize_address, StandardizedAddress
from address_standardizer.cache import get_cache
from address_standardizer.spatial.engine import SpatialEngine


class AddressRequest(BaseModel):
    address: Optional[str] = Field(None, example="1600 Amphitheatre Pkwy, Mountain View, CA 94043")
    street1: Optional[str] = Field(None, example="1600 Amphitheatre Pkwy")
    street2: Optional[str] = Field(None, example=None)
    city: Optional[str] = Field(None, example="Mountain View")
    state: Optional[str] = Field(None, example="CA")
    postal_code: Optional[str] = Field(None, example="94043")
    country: Optional[str] = Field("USA", example="USA")
    enable_geocoding: bool = Field(False, description="Resolve lat/long coordinates")


class StandardizedResponse(BaseModel):
    street1: str
    street2: str
    city: str
    state: str
    postal_code: str
    country: str
    normalized_address_key: Optional[str]
    building_key: Optional[str]
    address_status: str
    routing_tier: str
    confidence_score: float
    deliverability: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AddressService:
    def __init__(self, spatial_engine: Optional[SpatialEngine] = None):
        self.spatial_engine = spatial_engine

    def process(self, req: AddressRequest) -> StandardizedAddress:
        if not req.address and not req.street1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either 'address' single line or 'street1' must be provided."
            )
        return standardize_address(
            street1=req.address or req.street1,
            street2=req.street2,
            city=req.city,
            state=req.state,
            postal_code=req.postal_code,
            country=req.country,
            enable_geocoding=req.enable_geocoding,
            finalize=True,
        )


_service_instance: Optional[AddressService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _service_instance
    # Warm up L1/L2 caches and verify SQLite connections
    cache = get_cache()
    # Initialize optional spatial engine
    spatial_engine = SpatialEngine() if SpatialEngine.is_configured() else None
    _service_instance = AddressService(spatial_engine=spatial_engine)
    yield
    # Graceful shutdown cleanup if needed
    _service_instance = None


app = FastAPI(title="Address Verification Service", lifespan=lifespan)


def get_address_service() -> AddressService:
    if _service_instance is None:
        raise RuntimeError("AddressService not initialized")
    return _service_instance


@app.post("/v1/standardize", response_model=StandardizedResponse)
async def standardize(
    request: AddressRequest,
    service: AddressService = Depends(get_address_service)
):
    result = service.process(request)
    return StandardizedResponse(
        street1=result.street1,
        street2=result.street2,
        city=result.city,
        state=result.state,
        postal_code=result.postal_code,
        country=result.country,
        normalized_address_key=result.normalized_address_key,
        building_key=result.building_key,
        address_status=result.address_status,
        routing_tier=result.routing_tier,
        confidence_score=result.confidence_score,
        deliverability=result.deliverability,
        latitude=result.latitude,
        longitude=result.longitude,
    )
```

#### 3.3.2. Recipe 2: Next.js 14/15 (App Router) TypeScript Route Handler
Client-safe App Router API route using `@address-standardizer/client` with input validation and edge runtime compatibility:

```typescript
// app/api/address/standardize/route.ts
import { NextRequest, NextResponse } from "next/server";
import { AddressStandardizerClient, AddressStandardizerHttpError } from "@address-standardizer/client";

// Initialize client with environment variables
const client = new AddressStandardizerClient({
  baseUrl: process.env.ADDRESS_STANDARDIZER_URL || "http://127.0.0.1:8000",
  timeoutMs: 5000,
});

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (!body.address && !body.street1) {
      return NextResponse.json(
        { error: "Missing required parameter: 'address' or 'street1'" },
        { status: 400 }
      );
    }

    const standardized = await client.standardize({
      address: body.address,
      street1: body.street1,
      street2: body.street2,
      city: body.city,
      state: body.state,
      postal_code: body.postal_code,
      country: body.country || "USA",
      enable_geocoding: Boolean(body.enable_geocoding),
    });

    return NextResponse.json({
      success: true,
      data: {
        street1: standardized.street1,
        street2: standardized.street2,
        city: standardized.city,
        state: standardized.state,
        postalCode: standardized.postal_code,
        country: standardized.country,
        normalizedKey: standardized.normalized_address_key,
        buildingKey: standardized.building_key,
        routingTier: standardized.routing_tier,
        confidenceScore: standardized.confidence_score,
        deliverability: standardized.deliverability,
        latitude: standardized.latitude,
        longitude: standardized.longitude,
      },
    });
  } catch (error: unknown) {
    if (error instanceof AddressStandardizerHttpError) {
      return NextResponse.json(
        { error: "Upstream standardizer error", status: error.status, details: error.body },
        { status: error.status }
      );
    }
    return NextResponse.json(
      { error: "Internal server error", message: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}
```

#### 3.3.3. Recipe 3: Modern Data Pipelines (Pandas, Polars, and DuckDB)

```python
"""High-performance batch address standardization recipes across modern data tools."""

# --- Pattern A: Polars DataFrame & LazyFrame Streaming ---
import polars as pl
from address_standardizer.arrow import standardize_polars

# Load raw customer data
df = pl.DataFrame({
    "customer_id": [101, 102, 103],
    "raw_address": [
        "1600 Amphitheatre Pkwy, Mountain View, CA 94043",
        "100 Main St Ste 400, Seattle, WA 98101",
        "PO Box 1234, Austin, TX 78701"
    ]
})

# Vectorized standardization returning canonical struct columns
standardized_df = standardize_polars(
    df,
    address_col="raw_address",
    as_struct=False  # unpacks street1, city, state, postal_code, normalized_address_key
)
print(standardized_df.select(["customer_id", "street1", "city", "state", "postal_code", "normalized_address_key"]))


# --- Pattern B: In-Database DuckDB SQL UDF ---
import duckdb
from address_standardizer.arrow import register_duckdb_udfs

# Connect to in-memory or persistent DuckDB
con = duckdb.connect()

# Register native C-level Arrow UDFs
register_duckdb_udfs(con)

# Create sample table
con.execute("""
    CREATE TABLE vendor_locations (
        vendor_id INTEGER,
        street VARCHAR,
        city VARCHAR,
        state VARCHAR,
        zip VARCHAR
    );
    INSERT INTO vendor_locations VALUES
        (1, '350 5th Ave', 'New York', 'NY', '10118'),
        (2, '221B Baker Street', 'London', '', 'NW1 6XE');
""")

# Execute SQL query with standardized address normalization
result = con.execute("""
    SELECT 
        vendor_id,
        standardize_address_key(street, city, state, zip) AS deduplication_key,
        standardize_deliverability(street, city, state, zip) AS delivery_status
    FROM vendor_locations
""").fetchdf()
print(result)


# --- Pattern C: Chunked Streaming for Pandas Datasets ---
import pandas as pd
from address_standardizer import batch_standardize

def process_large_csv(input_csv_path: str, output_csv_path: str, chunk_size: int = 1000):
    for i, chunk in enumerate(pd.read_csv(input_csv_path, chunksize=chunk_size)):
        addresses = chunk["raw_address"].tolist()
        std_results = batch_standardize(addresses)
        chunk["clean_street1"] = [r.street1 for r in std_results]
        chunk["clean_city"] = [r.city for r in std_results]
        chunk["clean_state"] = [r.state for r in std_results]
        chunk["clean_zip"] = [r.postal_code for r in std_results]
        chunk["routing_tier"] = [r.routing_tier for r in std_results]
        
        mode = "w" if i == 0 else "a"
        header = i == 0
        chunk.to_csv(output_csv_path, mode=mode, header=header, index=False)
```

#### 3.3.4. Recipe 4: AI Framework Tool Definitions (LangChain, LlamaIndex, Google GenAI)

```python
"""AI Agent Framework Tool Definitions for Address Standardizer."""

# --- 1. LangChain BaseTool ---
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Optional
from address_standardizer import standardize_address

class AddressInputSchema(BaseModel):
    address: str = Field(description="Full unstructured postal address string to standardize.")
    country: Optional[str] = Field("USA", description="ISO country code or name.")

class AddressStandardizerTool(BaseTool):
    name: str = "standardize_postal_address"
    description: str = (
        "Parses, normalizes, and validates physical and postal addresses. "
        "Returns canonical street, city, state, postal code, deliverability status, and confidence routing tier."
    )
    args_schema: Type[BaseModel] = AddressInputSchema

    def _run(self, address: str, country: str = "USA") -> dict:
        std = standardize_address(street1=address, country=country, finalize=True)
        return {
            "street1": std.street1,
            "street2": std.street2,
            "city": std.city,
            "state": std.state,
            "postal_code": std.postal_code,
            "country": std.country,
            "routing_tier": std.routing_tier,
            "confidence_score": std.confidence_score,
            "deliverability": std.deliverability,
            "requires_secondary_unit": std.secondary_prompt_required,
            "suggested_units": list(std.suggested_secondary_units)
        }


# --- 2. LlamaIndex FunctionTool ---
from llama_index.core.tools import FunctionTool

def format_and_verify_address(address: str, country: str = "USA") -> dict:
    """Standardize and verify an address using USPS Pub 28 and UPU S42 rules."""
    std = standardize_address(street1=address, country=country, finalize=True)
    return {
        "canonical_address": f"{std.street1}, {std.city}, {std.state} {std.postal_code}".strip(", "),
        "is_deliverable": std.deliverability == "DELIVERABLE",
        "routing_tier": std.routing_tier,
        "normalized_key": std.normalized_address_key
    }

llama_address_tool = FunctionTool.from_defaults(
    fn=format_and_verify_address,
    name="address_verifier",
    description="Validates and formats customer addresses into clean standardized USPS/UPU components."
)


# --- 3. Google GenAI / Gemini Function Declaration ---
from google.genai import types

gemini_address_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="standardize_address",
            description="Parses, standardizes, and validates postal addresses across 249 ISO countries.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "address": types.Schema(
                        type=types.Type.STRING,
                        description="The unformatted address line."
                    ),
                    "country": types.Schema(
                        type=types.Type.STRING,
                        description="ISO 2 or 3-letter country code (default 'USA')."
                    )
                },
                required=["address"]
            )
        )
    ]
)
```


---

## 4. Prioritized Multi-Phase Execution Roadmap

The implementation roadmap is structured into four self-contained, sequenced engineering phases ordered strictly by **impact-to-effort ratio**. Each phase defines target files, deliverables, backwards-compatibility invariants, and exact verification commands that enforce the project's strict 100% test coverage gate (`fail_under = 100`, `branch = true`).

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 8.1: AI Agent MCP Server & Discovery Artifacts                    │
│ Impact: High | Effort: Low | Ratio: 5.0                                 │
│ Deliverables: Standalone MCP stdio server, llms.txt, agent skills        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 8.2: Developer Ergonomics & Zero-Config Reference Validation      │
│ Impact: High | Effort: Medium | Ratio: 3.5                              │
│ Deliverables: validate_address helper, Pydantic v2 models, embedded DB  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 8.3: Cross-Language SDK Parity & Resilient Retries                │
│ Impact: Medium-High | Effort: Medium | Ratio: 2.8                       │
│ Deliverables: Jittered exponential retries, postal REST API, typed SDKs │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 8.4: Advanced Grammar Tuning & Holdout Calibration                │
│ Impact: High | Effort: High | Ratio: 2.2                                │
│ Deliverables: Commaless token recovery, Hungarian/Japanese parser fixes  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Phase 8.1: AI Agent MCP Server & Discovery Artifacts

#### 4.1.1. Rationale & Impact-to-Effort Ratio
- **Impact**: Unlocks direct tool-calling integration for Claude Desktop, Cursor, Gemini CLI, and agentic workflows. Immediately stops AI assistants from hallucinating obsolete or non-existent APIs.
- **Effort**: Low (exposing existing Python core functions over standard JSON-RPC / MCP protocols without mutating core parsing internals).
- **Impact-to-Effort Ratio**: **5.0 / 5.0** (Highest Priority Quick Win).

#### 4.1.2. Target Files to Create / Modify
- **Create**:
  - `address_standardizer/mcp/__init__.py`
  - `address_standardizer/mcp/server.py` (stdio and SSE MCP server implementation)
  - `address_standardizer/mcp/tools.py` (the 5 tool definitions and token-efficient response mappers)
  - `llms.txt` (repository root)
  - `llms-full.txt` (repository root)
  - `.agents/skills/address-standardizer/SKILL.md` (portable agent skill definition)
  - `.cursorrules` (Cursor IDE integration rules)
  - `tests/test_mcp_server.py` (100% statement and branch coverage test suite)
- **Modify**:
  - `pyproject.toml` (add optional `mcp` dependency group: `mcp>=1.0.0`; add `address-standardizer-mcp` CLI script entry point)
  - `address_standardizer/cli.py` (add `address-standardizer mcp` subcommand)

#### 4.1.3. Deliverables & Capabilities
1. Production Model Context Protocol server exposing `standardize_address`, `batch_standardize`, `validate_postal`, `autocomplete_address`, and `explain_parse`.
2. Token-efficient response serialization to protect agent context windows.
3. Machine-readable `llms.txt` and `llms-full.txt` served at documentation endpoints.
4. Portable agent skill file guiding LLM reasoning on confidence tiers and DPV secondary prompting.

#### 4.1.4. Backwards-Compatibility Invariants
- Existing public signatures for `standardize_address`, `batch_standardize`, and CLI commands remain 100% identical.
- Zero breaking changes to `StandardizedAddress` fields or return types.
- Running without the `mcp` optional dependency gracefully informs the user via `ImportError` with clear installation guidance (`pip install "address-standardizer[mcp]"`).

#### 4.1.5. Verification Commands
```bash
# Verify new MCP unit and integration tests achieve 100% statement and branch coverage
.venv/bin/pytest tests/test_mcp_server.py --cov=address_standardizer.mcp --cov-branch --cov-report=term-missing

# Verify full repository test suite preserves fail_under = 100
.venv/bin/pytest --cov=address_standardizer --cov-branch --cov-report=term-missing

# Verify linting passes cleanly
.venv/bin/ruff check address_standardizer tests
```

---

### Phase 8.2: Developer Ergonomics & Zero-Config Reference Validation

#### 4.2.1. Rationale & Impact-to-Effort Ratio
- **Impact**: Drastically reduces developer onboarding time from minutes to seconds by eliminating manual SQLite file downloads and configuration boilerplate. Bridges Python dataclasses directly into FastAPI and Pydantic ecosystems.
- **Effort**: Medium (packaging a compressed US open-data reference index and authoring Pydantic v2 schemas).
- **Impact-to-Effort Ratio**: **3.5 / 5.0**.

#### 4.2.2. Target Files to Create / Modify
- **Create**:
  - `address_standardizer/schemas.py` (Pydantic v2 models: `AddressInputSchema`, `StandardizedAddressPydantic`, `ValidationResultSchema`)
  - `address_standardizer/data/embedded_reference.py` (compressed embedded ZIP5/state gazetteer loader with automatic decompression into `~/.cache/address_standardizer/`)
  - `tests/test_schemas.py` (test suite for Pydantic exports)
  - `tests/test_embedded_reference.py` (test suite for zero-config reference resolution)
- **Modify**:
  - `address_standardizer/__init__.py` (export `validate_address`, `AddressSchema`, `StandardizedAddressPydantic`)
  - `address_standardizer/standardizer.py` (enable default lazy reference provider when `enable_reference_validation=True`)

#### 4.2.3. Deliverables & Capabilities
1. `validate_address(...)` single-call convenience helper returning clean boolean and reason codes.
2. First-class Pydantic v2 schema integration for FastAPI and LangChain.
3. Zero-config offline ZIP/state reference validation without manual database management.

#### 4.2.4. Backwards-Compatibility Invariants
- `enable_reference_validation` defaults to `False` unless explicitly enabled, ensuring existing execution paths retain exact benchmark latency profiles.
- Standard dataclass returns from `standardize_address` remain unchanged; Pydantic models are optional opt-in exports.

#### 4.2.5. Verification Commands
```bash
# Verify schema and embedded reference test coverage
.venv/bin/pytest tests/test_schemas.py tests/test_embedded_reference.py --cov=address_standardizer --cov-branch

# Verify zero regression on full 3,616+ test suite
.venv/bin/pytest --cov=address_standardizer --cov-branch --cov-fail-under=100
```

---

### Phase 8.3: Cross-Language SDK Parity & Resilient Retries

#### 4.3.1. Rationale & Impact-to-Effort Ratio
- **Impact**: Fortifies enterprise production deployments against transient network blips and rate limiting. Closes documentation and endpoint parity gaps across TypeScript, Go, and .NET.
- **Effort**: Medium (implementing retry policies across three SDK codebases and exposing postal validation endpoints in `server.py`).
- **Impact-to-Effort Ratio**: **2.8 / 5.0**.

#### 4.3.2. Target Files to Create / Modify
- **REST Service**:
  - `address_standardizer/server.py` (add `POST /v1/validate-postal` and `GET /v1/validate-postal`)
  - `tests/test_server.py` (add test coverage for postal endpoint)
- **TypeScript SDK**:
  - `sdks/typescript/src/client.ts` (implement retry logic with decorrelated exponential jitter; add `validatePostalCode`)
  - `sdks/typescript/src/types.ts` (strongly type `ExplanationRecord` and `AlternativeInterpretation`)
  - `sdks/typescript/tests/client.test.ts` (test retry execution and postal validation)
- **Go SDK**:
  - `sdks/go/client.go` (implement retry transport middleware; add `ValidatePostalCode`, `GetMetrics`, `Review`)
  - `sdks/go/models.go` (strongly type `Explanation` and `Alternatives`)
  - `sdks/go/client_test.go` (test retry and validation handlers)
- **.NET SDK**:
  - `sdks/dotnet/AddressStandardizerClient.cs` (integrate Polly or custom jittered retry handler; add `ValidatePostalCodeAsync`)
  - `sdks/dotnet/Models.cs` (strongly type explanation and alternatives)
  - `sdks/dotnet/tests/AddressStandardizer.Client.Tests/` (unit tests for retries)

#### 4.3.3. Deliverables & Capabilities
1. Automatic exponential backoff with full jitter on `429`, `502`, `503`, and `504` HTTP responses across all SDKs.
2. Unified postal validation across Python, REST, TypeScript, Go, and .NET.
3. Strongly typed explanation and alternatives models eliminating untyped dictionaries.

#### 4.3.4. Backwards-Compatibility Invariants
- Retries are transparent to existing SDK callers; timeouts and cancellation tokens continue to be strictly honored.
- Existing REST endpoints and response shapes maintain 100% backward compatibility.

#### 4.3.5. Verification Commands
```bash
# Verify Python REST server tests
.venv/bin/pytest tests/test_server.py --cov=address_standardizer.server --cov-branch --cov-fail-under=100

# Verify TypeScript SDK build and tests
cd sdks/typescript && npm test && cd ../..

# Verify Go SDK tests
cd sdks/go && go test -v -race ./... && cd ../..

# Verify .NET SDK tests
cd sdks/dotnet && dotnet test && cd ../..
```

---

### Phase 8.4: Advanced Grammar Tuning & Holdout Calibration

#### 4.4.1. Rationale & Impact-to-Effort Ratio
- **Impact**: Directly tackles the 8.3 percentage point holdout generalization drop (`REPORT_HOLDOUT.md`), fixing the 51.7% commaless drop, Hungarian inverted parsing (12.5%), and Japanese provincial ward splits (21.2%).
- **Effort**: High (grammar redesign, tokenizer enhancements, and extensive regression evaluation).
- **Impact-to-Effort Ratio**: **2.2 / 5.0**.

#### 4.4.2. Target Files to Create / Modify
- **Modify**:
  - `address_standardizer/us_street_parser.py` (commaless heuristic boundary detection)
  - `address_standardizer/international/hungary.py` (or localized rule in `germanic.py`: inverted postcode-first handling)
  - `address_standardizer/international/japan.py` (provincial municipal `丁目` extraction and ward parsing)
  - `address_standardizer/international/turkey.py` (Unicode dotless `ı` case-folding normalization)
  - `address_standardizer/confidence.py` (Platt scaling / isotonic regression confidence calibration to lower ECE below 0.05)
  - `benchmarks/eval/eval_holdout.py` (benchmark harness runner)
- **Create**:
  - `tests/test_commaless_parser.py` (dedicated regression tests for unpunctuated input)
  - `benchmarks/eval/REPORT_HOLDOUT_V4.md` (re-evaluation outcome report)

#### 4.4.3. Deliverables & Capabilities
1. Commaless single-line parsing accuracy improved from 51.7% to $> 85.0\%$.
2. Hungarian exact match improved from 12.5% to $> 90.0\%$.
3. Japanese holdout exact match improved from 28.1% to $> 80.0\%$.
4. Expected Calibration Error (ECE) reduced from 0.127 to $< 0.040$, aligning confidence scores with true empirical accuracy.

#### 4.4.4. Backwards-Compatibility Invariants
- US standard USPS Pub 28 parsing on punctuated addresses retains 100% exact key generation and zero regression on `benchmarks/golden_dataset.json` (1,000 records).
- All 3,616 existing unit and integration tests continue to pass.

#### 4.4.5. Verification Commands
```bash
# Run full unit and regression test suite with 100% coverage gate
.venv/bin/pytest --cov=address_standardizer --cov-branch --cov-fail-under=100

# Execute US golden benchmark SLA verification
.venv/bin/python benchmarks/run_benchmarks.py --dataset benchmarks/golden_dataset.json

# Execute multinational golden benchmark verification
.venv/bin/python benchmarks/run_benchmarks.py --dataset benchmarks/data/golden_dataset_multinational.json

# Generate updated holdout report V4
.venv/bin/python benchmarks/eval/eval_holdout.py --seed 20270601 --output benchmarks/eval/REPORT_HOLDOUT_V4.md
```

---

## 5. Verification, Quality Assurance & Governance Matrix

To ensure that the implementation of this plan maintains enterprise software standards, all engineering phases must adhere to the following governance matrix:

### 5.1. Continuous Quality Gates

| Gate | Tool / Enforcement | Target / Invariant | Invalidation Condition |
| :--- | :--- | :--- | :--- |
| **Statement Coverage** | `pytest --cov=address_standardizer` | Exactly **100%** (`fail_under = 100`) | Any uncovered statement fails CI |
| **Branch Coverage** | `pytest --cov-branch` | Exactly **100%** (`branch = true`) | Any unexercised `if`/`else` branch fails CI |
| **Code Formatting & Linting** | `ruff check .` & `ruff format --check .` | **0 errors, 0 warnings** | Any lint deviation blocks merge |
| **Version Alignment** | `python scripts/check_versions.py` | Version `3.3.0` across all files | Any mismatch between `pyproject.toml`, `Cargo.toml`, etc. |
| **Native / Python Parity** | `pytest tests/native/test_native_parity.py` | **100% bit-for-bit key match** | Any discrepancy between Rust and pure Python core |
| **US Golden Accuracy** | `benchmarks/golden_dataset.json` | $\ge 99.5\%$ all-fields exact | Any regression below baseline |
| **Multinational Golden Accuracy**| `benchmarks/data/golden_dataset_multinational.json` | $\ge 99.5\%$ all-fields exact | Any regression below baseline |
| **Zero Tracked File Mutation** | `git status --porcelain` | Empty diff on tracked repository files | Any tracked file mutation during planning phase |

### 5.2. Forensic Integrity & Anti-Cheating Protocol
- **No Hardcoded Test Bypasses**: No test results, expected keys, or mock returns may be hardcoded into engine sources.
- **Genuine Execution**: Every standardization, geocoding, and confidence score calculation must execute real parsing automata and mathematical algorithms.
- **Independent Auditor Attestation**: Each completed milestone is reviewed by an independent preview auditor who verifies git tree cleanliness, test coverage, and benchmark grounding before formal sign-off.
