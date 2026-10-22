# Global Telephony Enterprise Blueprint: Universal Multi-National Phone Standardization, NANP Jurisdiction Resolution, Line-Type Classification & Native Compiled Engine

**Document Version:** 1.0.0 (Master Technical Architecture Specification)  
**Status:** Approved Master Technical Architecture Blueprint  
**Date:** 2026-10-21  
**Target System:** `phone_standardizer` Core Engine, NANP Resolver, Fraud/Confidence Engine & Multi-Platform SDKs  
**Workspace Root:** `/home/jwhite/Phone-Standardizer`  
**Classification:** Enterprise Engineering Architecture & Strategic Specification  
**Reference Standards:** ITU-T Recommendation E.164 (International Public Telecommunication Numbering Plan), ITU-T Recommendation E.123 (Notation for National and International Telephone Numbers), ITU-T Recommendation E.161 ( Keypad Alpha-Numeric Mapping), IETF RFC 3966 (The `tel` URI for Telephone Numbers), 3GPP TS 23.003, North American Numbering Plan Administration (NANPA) NPA Registry, ISO 3166-1 (Alpha-2, Alpha-3, Numeric Country Codes), US FCC TCPA / Do-Not-Call (DNC) Compliance Frameworks.

---

## Executive Table of Contents

1. [Section 1: Executive Architecture & Global System Topology](#section-1-executive-architecture--global-system-topology)
   - 1.1 Executive Summary & Evolution Mission
   - 1.2 Why `Phone-Standardizer`: Overcoming Legacy Library Bottlenecks
   - 1.3 Global System Architecture & Module Topology
   - 1.4 End-to-End Pipeline Data Flow
   - 1.5 Codebase Layout & Module Inventory
2. [Section 2: Universal International & Multi-Standard Telephony Engine (R1)](#section-2-universal-international--multi-standard-telephony-engine-r1)
   - 2.1 Standards Compliance: ITU-T E.164, ITU-T E.123, and IETF RFC 3966
   - 2.2 Universal 249 ISO-3166-1 Country & ITU Dial-Plan Registry
   - 2.3 Detailed Regional Telephony Grammars & Trunk Healing Rules
     - 2.3.1 North American Numbering Plan (`+1` NANP — 25 Countries & Territories)
     - 2.3.2 United Kingdom & Crown Dependencies (`+44` — Variable NSN & Trunk `0` Stripping)
     - 2.3.3 Germanic & Open Dialing Plans (`+49` DEU, `+43` AUT — Variable Length Subscriber Numbers)
     - 2.3.4 Latin America Legacy Mobile Prefix Healing (`+52` MEX, `+54` ARG, `+55` BRA)
     - 2.3.5 Multi-Script Numeral Folding (Full-Width CJK, Arabic-Indic, Eastern Arabic, Devanagari)
   - 2.4 Alphanumeric Vanity Decoding (`1-800-FLOWERS` via ITU-T E.161)
   - 2.5 Extension, Sub-Addressing & DTMF Pause Extraction
3. [Section 3: Contextual Country Disambiguation & Portfolio Synergy (R2)](#section-3-contextual-country-disambiguation--portfolio-synergy-r2)
   - 3.1 5-Stage Country & Jurisdiction Inference Cascade
   - 3.2 Complete NANP (`+1`) 3-Digit Area Code (NPA) Jurisdiction & State/Province Crosswalk
   - 3.3 Native Interoperability with `Address-Standardizer`
   - 3.4 Native Interoperability with `Query-Builder`
4. [Section 4: Line-Type Classification, Fraud/IRSF Defense & Confidence Scoring (R3)](#section-4-line-type-classification-fraudirsf-defense--confidence-scoring-r3)
   - 4.1 Line-Type Taxonomy (`MOBILE`, `FIXED_LINE`, `TOLL_FREE`, `VOIP`, `PREMIUM_RATE`, etc.)
   - 4.2 International Revenue Share Fraud (IRSF) & High-Risk Range Guardrails
   - 4.3 Synthetic, Fictitious & Bogus Number Detection (`555-01XX`, Repeating/Sequential Runs)
   - 4.4 Composite Confidence Scoring & Stewardship Routing Tiers
5. [Section 5: Native Rust Acceleration, Vectorized Batch & Multi-Platform SDKs (R4)](#section-5-native-rust-acceleration-vectorized-batch--multi-platform-sdks-r4)
   - 5.1 Native Rust / PyO3 Compiled Core (`_phone_standardizer_rs`)
   - 5.2 Pure Python Zero-Dependency Core (`phone_standardizer`)
   - 5.3 Streaming Batch, Apache Arrow, Polars & DuckDB Vectorized Integration
   - 5.4 FastAPI Microservice, Model Context Protocol (MCP) Server & Polyglot SDKs
6. [Section 6: Automated Test Suite, Golden Datasets & Verification Gates (R5)](#section-6-automated-test-suite-golden-datasets--verification-gates-r5)
   - 6.1 100% Line & Branch Coverage Gate
   - 6.2 Property-Based Generative Fuzzing & Adversarial ReDoS Protection
   - 6.3 Performance & Memory Footprint SLAs
7. [Section 7: Phased Engineering Implementation Roadmap (R6)](#section-7-phased-engineering-implementation-roadmap-r6)

---

## Section 1: Executive Architecture & Global System Topology

### 1.1 Executive Summary & Evolution Mission

**Phone Standardizer** (`phone_standardizer`) is an enterprise-grade, zero-vendor-lockin global telephone number parsing, normalization, validation, line-type classification, jurisdiction attribution, and entity linkage library. Owned and maintained by **HobbyHabbit LLC** under the **MIT License**, it forms the telephony counterpart to **[Address-Standardizer](https://github.com/Jacob-white/Address-Standardizer)** and **[Query-Builder](https://github.com/Jacob-white/Query-Builder)**.

In master data management (MDM), financial regulatory ingestion (SEC Form ADV/BD, FINRA BrokerCheck), healthcare registries, and global CRM pipelines, raw phone numbers arrive corrupted by free-text comments, mixed international dialing prefixes (`011`, `00`, `810`), redundant national trunk codes (`+44 (0) 20...`), legacy mobile prefixes (`+52 1 55...`), vanity letters (`1-800-FLOWERS`), embedded extensions (`ext. 402`), and non-ASCII numerals (`＋８１ ３-１２３４-５６７８`).

**Phone Standardizer** transforms arbitrary, noisy strings into an immutable `StandardizedPhone` golden record containing canonical **ITU-T E.164**, **ITU-T E.123 National**, **ITU-T E.123 International**, **IETF RFC 3966 (`tel:` URI)**, deterministic deduplication hashes, NANP state/territory attribution, line-type classification, fraud/IRSF risk flags, and composite confidence scores.

### 1.2 Why `Phone-Standardizer`: Overcoming Legacy Library Bottlenecks

| Dimension | Legacy `phonenumbers` (Python port of `libphonenumber`) | `Phone-Standardizer` (`phone_standardizer`) |
| :--- | :--- | :--- |
| **Runtime Architecture** | Java-to-Python mechanical port with heavy object allocation and deep regex trees | Zero-dependency Python core + optional Rust PyO3 native extension (`_phone_standardizer_rs`) |
| **Throughput** | ~3,500 – 8,000 numbers/sec in Python | **> 25,000 rec/sec** (Pure Python) / **> 400,000 rec/sec** (Rust PyO3) |
| **Input Noise Resilience** | Fails or misparses free-text notes, double trunk prefixes (`+44 (0)`), or legacy `+52 1` / `+54 9` mobile numbers | Built-in **Trunk & Legacy Prefix Healer** automatically repairs `+CC (0)` and historical LatAm mobile numbers |
| **Contextual Disambiguation** | Requires explicit ISO-2 hint for national numbers; cannot ingest postal or address context | Native interoperability with `Address-Standardizer` (infers country & state from ZIP/postal code or `StandardizedAddress`) |
| **Data Model** | Mutable `PhoneNumber` class requiring 5+ separate helper calls for formats, carrier, geo, and type | Single immutable `StandardizedPhone` dataclass & Pydantic schema with all formats, keys, and diagnostics |
| **Security & Fraud** | No IRSF, bogus pattern (`999-9999`), or TCPA fictitious range (`555-01XX`) diagnostics | Built-in **Fraud & Synthetic Detection** + confidence routing (`AUTO_PASS`, `FUZZY_REVIEW`, `MANUAL_STEWARDSHIP`) |
| **AI & Data Ecosystem** | Library only | Built-in **CLI**, **FastAPI Server**, **MCP Server**, **DuckDB/Polars/Arrow UDFs**, and **React/TS, Go, .NET SDKs** |

### 1.3 Global System Architecture & Module Topology

```
                  RAW TELEPHONY INPUT (String, Dict, CSV, Arrow, API, MCP)
        "Office: +44 (0) 20 7946 0912 ext. 42"  |  "1-800-FLOWERS"  |  "(787) 555-0199"
                                                │
                                                ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│STAGE 1: UNICODE & LEXICAL NORMALIZATION (normalization.py / _phone_standardizer_rs)           │
│ • Unicode NFKC & Multi-Script Numeral Folding (Full-Width, Arabic-Indic, Devanagari -> ASCII) │
│ • Free-Text Wrapper Scrubbing & Extension/Sub-Address Extraction (ext, x, #, ;isub=, DTMF p/w)│
│ • Vanity Keypad Resolution (ITU-T E.161 alpha folding with preservation of vanity_alias)      │
└───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                │
                                                ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│STAGE 2: 5-STAGE COUNTRY & JURISDICTION DISAMBIGUATION (registry.py / nanp.py)                 │
│ 1. Explicit '+' or IDD Exit Prefix Detection (011, 00, 0011, 010, 810 -> Country Calling Code)│
│ 2. Shared Calling Code Resolution (+1 NANP 25-country NPA table; +44 GBR/JEY/GGY/IMN; +7 RUS) │
│ 3. Address Context Hint (Country/State/Postal Code from Address-Standardizer)                 │
│ 4. Explicit Caller Country Hint (ISO-3166-1 alpha-2, alpha-3, numeric, or country name)       │
│ 5. National Trunk & Length Signature Matching                                                 │
└───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                │
                                                ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│STAGE 3: GRAMMAR HEALING, VALIDATION & CLASSIFICATION (standardizer.py)                        │
│ • Redundant National Trunk Removal ("+44 (0) 20..." -> "+44 20...")                           │
│ • Regional Mobile Healer (Mexico +52 1 -> +52; Argentina +54 15 -> +54 9; Brazil 9th digit)   │
│ • NSN Length & Prefix Validation against 249 ISO-3166-1 CountryDialPlan Specifications        │
│ • Line-Type Classification (MOBILE, FIXED_LINE, TOLL_FREE, PREMIUM_RATE, VOIP, SHARED_COST)   │
└───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                │
                                                ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│STAGE 4: FORMATTING, CONFIDENCE SCORING & ENTITY KEY GENERATION (confidence.py / models.py)    │
│ • Formats: E.164 (+18003569377), National ((800) 356-9377), Intl (+1 800-356-9377), RFC 3966  │
│ • Deterministic Keys: phone_key (E.164 base) & phone_ext_key (E.164 + normalized extension)   │
│ • Fraud & Bogus Checks: Fictitious 555-01XX, Repetitive Digits, IRSF High-Risk Premium Ranges │
│ • Confidence Scorer (0.0–1.0) -> AUTO_PASS (>=0.95) | FUZZY_REVIEW | MANUAL_STEWARDSHIP       │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.4 Codebase Layout & Module Inventory

| Module Path | Architectural Responsibility |
| :--- | :--- |
| `phone_standardizer/models.py` | Immutable `StandardizedPhone`, `PhoneLineType`, `PhoneRoutingTier`, `PhoneRiskFlag`, `CountryDialPlan`. |
| `phone_standardizer/registry.py` | Complete 249 ISO-3166-1 country registry, ITU calling codes, trunk/IDD prefixes, NSN lengths, and formatting rules. |
| `phone_standardizer/nanp.py` | North American Numbering Plan (`+1`) 3-digit NPA lookup table mapping 400+ area codes to US states, Canadian provinces, and 23 Caribbean/Pacific nations, plus Toll-Free (`800/833/844/855/866/877/888`) and Premium (`900`) ranges. |
| `phone_standardizer/normalization.py` | Multi-script digit folding, extension/DTMF parser, vanity alphanumeric translator, and trunk prefix stripper. |
| `phone_standardizer/standardizer.py` | Primary `standardize_phone()`, `validate_phone()`, `parse_phone()`, and multi-standard formatters. |
| `phone_standardizer/confidence.py` | Multi-factor `ConfidenceScorer`, bogus/fictitious range detection, IRSF risk flags, and routing tier calculation. |
| `phone_standardizer/batch.py` | Memory-efficient chunked batch and streaming processors for CSV, JSONL, JSON, and iterable records. |
| `phone_standardizer/_native_dispatch.py` | Runtime loader and transparent dispatcher between `_phone_standardizer_rs` (Rust PyO3) and pure Python. |
| `phone_standardizer/cli.py` | Command-line interface (`parse`, `validate`, `batch`, `country`, `serve`). |
| `phone_standardizer/server.py` | FastAPI HTTP microservice with `/v1/standardize`, `/v1/batch`, `/v1/validate`, `/v1/countries`, `/health`. |
| `phone_standardizer/mcp/server.py` | Model Context Protocol (MCP) server exposing telephony tools to AI coding and data agents. |
| `src/lib.rs` | Native Rust PyO3 acceleration core (`_phone_standardizer_rs`). |

---

## Section 2: Universal International & Multi-Standard Telephony Engine (R1)

### 2.1 Standards Compliance: ITU-T E.164, ITU-T E.123, and IETF RFC 3966

1. **ITU-T E.164**:
   - Maximum total length of **15 digits** (Country Calling Code `1–3 digits` + National Significant Number `NSN`).
   - Prefixed with `+` and containing zero spaces, hyphens, or extensions (e.g., `+14155552671`, `+442079460912`).
   - Extensions are strictly excluded from the `e164` field to guarantee schema compatibility with Twilio, AWS SNS, Salesforce, and PostgreSQL E.164 constraints, and stored cleanly in `extension` and `rfc3966`.
2. **ITU-T E.123**:
   - **National Notation**: Includes national trunk prefix (`0` in Europe/Asia/Oceania; parentheses `(NPA) NXX-XXXX` in NANP) and localized digit groupings.
   - **International Notation**: Prefixed with `+CC` followed by space- or hyphen-delimited NSN groups without the domestic trunk prefix.
3. **IETF RFC 3966 (`tel:` URI)**:
   - Standardized URI format: `tel:+1-415-555-2671` or `tel:+1-415-555-2671;ext=402`.

### 2.2 Universal 249 ISO-3166-1 Country & ITU Dial-Plan Registry

The `CountryDialRegistry` maintains deterministic metadata for all **249 ISO-3166-1 alpha-2 jurisdictions**, including:
- `iso2` (`"US"`), `iso3` (`"USA"`), `country_name` (`"United States"`), `calling_code` (`"1"`).
- `idd_prefix` (International Direct Dialing exit code, e.g., `"011"` for NANP, `"00"` for ITU standard/EU, `"0011"` for Australia, `"810"` for Russia).
- `national_trunk_prefix` (e.g., `"1"` for NANP, `"0"` for UK/DE/FR/JP/AU, `None` for open-less plans like Italy/Spain/Denmark).
- `nsn_lengths` (Tuple of valid National Significant Number digit lengths, e.g., `(10,)` for NANP, `(9, 10)` for UK, `(6, 7, 8, 9, 10, 11)` for Germany).
- `mobile_prefixes`, `toll_free_prefixes`, `premium_prefixes`, `voip_prefixes`.
- `national_format_pattern` and `intl_format_pattern`.

### 2.3 Detailed Regional Telephony Grammars & Trunk Healing Rules

#### 2.3.1 North American Numbering Plan (`+1` NANP — 25 Countries & Territories)
- Format: `+1` + `NPA` (3-digit Area Code, `[2-9][0-9]{2}`) + `NXX` (3-digit Central Office Exchange, `[2-9][0-9]{2}`) + `XXXX` (4-digit Subscriber Number).
- **Structural Invariants**:
  - `NPA` cannot start with `0` or `1`.
  - `NXX` cannot start with `0` or `1`, and cannot be `N11` service codes (`211`, `311`, `411`, `511`, `611`, `711`, `811`, `911`) unless classified as `SHORT_CODE` / `EMERGENCY`.
  - Resolves exact ISO-3166-1 country (`US`, `CA`, `PR`, `DO`, `JM`, `BS`, `BB`, `TT`, `VI`, `GU`, `MP`, `AS`, `KY`, `BM`, `TC`, `VG`, `AG`, `DM`, `GD`, `KN`, `LC`, `VC`, `MS`, `AI`, `SX`) directly from the 3-digit `NPA`!

#### 2.3.2 United Kingdom & Crown Dependencies (`+44` — GBR, JEY, GGY, IMN)
- Heals the pervasive British notation `+44 (0) 20 7946 0912` or `0044 07911 123456` by stripping the redundant domestic trunk `0` after `+44`.
- Distinguishes Crown Dependencies by area/mobile prefix:
  - **Jersey (`JE`)**: `+44 1534` (Fixed), `+44 7797` / `+44 7700` / `+44 7829` (Mobile).
  - **Guernsey (`GG`)**: `+44 1481` (Fixed), `+44 7781` / `+44 7839` (Mobile).
  - **Isle of Man (`IM`)**: `+44 1624` (Fixed), `+44 7624` / `+44 7524` (Mobile).
- Line types: `71–75, 77–79` (`MOBILE`), `1, 2` (`FIXED_LINE`), `800, 808` (`TOLL_FREE`), `90, 91, 98` (`PREMIUM_RATE`), `56` (`VOIP`).

#### 2.3.3 Germanic & Open Dialing Plans (`+49` DEU, `+43` AUT)
- Supports variable-length National Significant Numbers (6 to 11 digits in Germany; 4 to 13 digits in Austria).
- Accurately classifies German mobile ranges (`15x`, `16x`, `17x`), toll-free (`800`), and premium (`900`).

#### 2.3.4 Latin America Legacy Mobile Prefix Healing (`+52` MEX, `+54` ARG, `+55` BRA)
- **Mexico (`+52`)**: In 2019, Mexico eliminated the `+52 1` mobile prefix and `044`/`045` domestic prefixes. Millions of legacy CRM records still store `+52 1 55 1234 5678` (11-digit NSN). `Phone-Standardizer` automatically heals `+52 1 + 10 digits` into canonical `+525512345678` and logs the `LEGACY_MOBILE_PREFIX_HEALED` normalization action.
- **Argentina (`+54`)**: Heals domestic mobile `15` prefixes into international `+54 9` mobile format.

#### 2.3.5 Multi-Script Numeral Folding
- Converts non-ASCII digits prior to lexical tokenization:
  - Full-width ASCII (`０`–`９`, `＋`, `－`, `（`, `）` $\to$ `0`–`9`, `+`, `-`, `(`, `)`)
  - Arabic-Indic (`٠`–`٩` $\to$ `0`–`9`)
  - Eastern Arabic-Indic / Persian (`۰`–`۹` $\to$ `0`–`9`)
  - Devanagari (`०`–`९` $\to$ `0`–`9`)

### 2.4 Alphanumeric Vanity Decoding (ITU-T E.161)

When an input contains keypad letters in the subscriber/exchange positions (e.g., `1-800-FLOWERS`, `+1 (888) TAX-HELP`, `0800-REVERSE`):
- Preserves the original uppercase token in `vanity_alias` (e.g., `"1-800-FLOWERS"`).
- Translates letters via the ITU-T E.161 standard keypad map (`ABC->2`, `DEF->3`, `GHI->4`, `JKL->5`, `MNO->6`, `PQRS->7`, `TUV->8`, `WXYZ->9`).
- Distinguishes vanity letters from extension markers (`ext`, `x`) so `"555-2368 ext 12"` does not turn `"ext"` into `"398"`.

### 2.5 Extension, Sub-Addressing & DTMF Pause Extraction

Extracts trailing extensions across international conventions before digit extraction:
- English: `ext`, `ext.`, `extension`, `x`, `#`, `no.`
- Spanish/Portuguese/French: `int`, `int.`, `interno`, `ramal`, `poste`
- German/Nordic: `dw`, `durchwahl`, `app.`
- Russian: `доб.`, `доб`
- Japanese: `内線`
- RFC 3966: `;ext=`, `;isub=`
- DTMF wait/pause sequences: `,`, `;`, `p`, `w`

---

## Section 3: Contextual Country Disambiguation & Portfolio Synergy (R2)

### 3.1 5-Stage Country & Jurisdiction Inference Cascade

When `standardize_phone(raw_phone, country=..., postal_code=..., state=...)` is invoked:
1. **Stage 1 — Explicit International Prefix (`+` or `00` / IDD)**: Parses the ITU calling code (`1` to `3` digits) via longest-prefix match (`+1242` Bahamas before `+1` US/CA; `+44` UK; `+358` Finland).
2. **Stage 2 — Sub-Calling-Code Area Attribution**: For shared calling codes (`+1` NANP, `+44` UK/Crown, `+7` RU/KZ, `+61` AU/CC/CX), inspects the leading area digits (`NPA` or prefix) to assign the exact ISO-3166-1 territory (e.g., `+1 787 555 0199` $\to$ `PR` Puerto Rico; `+1 416 555 0199` $\to$ `CA` Canada, Province `ON`).
3. **Stage 3 — Explicit Country / Address Context Hint**: Uses `country` parameter (`"US"`, `"GBR"`, `"United Kingdom"`) or infers country from `postal_code` / `state` metadata.
4. **Stage 4 — National Trunk & Format Signature**: Recognizes national formats (e.g. `(415) 555-2671` + US/CA context).
5. **Stage 5 — Fallback Default Region**: Defaults to `"US"` (configurable per call or globally).

### 3.2 Native Interoperability with `Address-Standardizer` & `Query-Builder`

- **With `Address-Standardizer`**: Pass a `StandardizedAddress` (or its `country_iso2` and `state`) directly into `standardize_phone(phone, address_context=addr)`. Furthermore, `Phone-Standardizer` detects **Cross-Field Geo Mismatch** (e.g., an address in London, UK paired with a domestic US area code or vice versa) and surfaces it in metadata.
- **With `Query-Builder`**: Provides deterministic E.164 normalization and partial redaction helpers (`mask_phone_e164("+14155552671") -> "+1******2671"`) compatible with `Query-Builder` CLAC policies.

---

## Section 4: Line-Type Classification, Fraud/IRSF Defense & Confidence Scoring (R3)

### 4.1 Line-Type Taxonomy (`PhoneLineType`)
- `MOBILE`: Cellular / wireless numbers.
- `FIXED_LINE`: Geographic landlines.
- `FIXED_LINE_OR_MOBILE`: Ambiguous allocation (common in NANP `+1` where fixed and mobile share geographic area codes).
- `TOLL_FREE`: Freephone (`800`, `888`, `877`, `866`, `855`, `844`, `833`, UK `0800`, DE `0800`).
- `PREMIUM_RATE`: Pay-per-call (`900`, UK `09`, DE `0900`).
- `SHARED_COST`: Split-charge numbers.
- `VOIP`: Non-geographic VoIP ranges.
- `SHORT_CODE` / `EMERGENCY`: `911`, `112`, `999`, `988`, `411`.

### 4.2 Fraud, IRSF & Bogus Number Detection (`PhoneRiskFlag`)
- `FICTITIOUS_RANGE`: North American `NPA-555-0100` through `NPA-555-0199`, UK Ofcom TV numbers (`01632 960xxx`, `020 7946 0xxx`, `07700 900xxx`).
- `REPEATING_DIGITS`: Subscriber numbers consisting of identical digits (e.g., `555-999-9999`, `000-0000`).
- `SEQUENTIAL_DIGITS`: Obvious placeholder runs (`1234567`, `9876543`).
- `PREMIUM_RATE_IRSF_RISK`: High-cost premium rate or known International Revenue Share Fraud (IRSF) ranges that should never be auto-dialed by SMS/voice OTP pipelines.
- `INVALID_AREA_CODE` / `INVALID_EXCHANGE`: Unassigned or structurally impossible area/exchange codes (e.g. NANP `NPA` starting with `0` or `1`, or `555-555-5555`).

### 4.3 Composite Confidence Scoring & Routing Tiers
Computes a deterministic confidence score $C \in [0.0, 1.0]$ and maps to:
- `AUTO_PASS` ($C \ge 0.95$): Fully valid E.164, verified country/area code, zero bogus/fraud flags.
- `FUZZY_REVIEW` ($0.80 \le C < 0.95$): Valid after healing (e.g., legacy prefix stripped, inferred country without `+`, or TV/fictitious test number).
- `MANUAL_STEWARDSHIP` ($C < 0.80$): Invalid digit length, unassigned area code, or repeating placeholder digits.

---

## Section 5: Native Rust Acceleration, Vectorized Batch & Multi-Platform SDKs (R4)

1. **Native Rust PyO3 Core (`_phone_standardizer_rs`)**:
   - Compiled Rust extension providing `normalize_digits_and_vanity_rs`, `extract_e164_candidates_rs`, and fast prefix dispatch.
   - Automatic fallback to `_pure_python_core` when wheel is not compiled, maintaining 100% behavioral parity.
2. **Batch & Streaming Engine (`phone_standardizer/batch.py`)**:
   - `batch_standardize_phones()`, `stream_standardize_csv()`, `stream_standardize_jsonl()`, `stream_standardize_json()`.
3. **HTTP Service & MCP Server**:
   - FastAPI microservice (`phone_standardizer/server.py`) with OpenAPI 3.1 schema.
   - Model Context Protocol (`phone_standardizer/mcp/server.py`) for LLM/agent tool use.
4. **Multi-Platform Client SDKs (`sdks/`)**:
   - TypeScript/React (`sdks/typescript`), Go (`sdks/go`), and .NET (`sdks/dotnet`).

---

## Section 6: Automated Test Suite, Golden Datasets & Verification Gates (R5)

- **100% Line & Branch Coverage Floor**: Enforced in `pyproject.toml` (`fail_under = 100`).
- **Zero Linter Warnings**: Enforced via `ruff check .`.
- **Golden Multi-National Test Matrix**: Covers all 249 ISO-3166-1 countries, all 25 NANP territories, US states & Canadian provinces, vanity numbers, extensions, multi-script numerals, legacy mobile healing, bogus/fictitious detection, CLI, HTTP server, MCP server, and batch streaming.

---

## Section 7: Phased Engineering Implementation Roadmap (R6)

| Milestone | Scope | Key Deliverables | Status |
| :--- | :--- | :--- | :--- |
| **M1** | Core Data Model & 249-Country ITU Registry | `models.py`, `registry.py`, `nanp.py` | **Active (v1.0.0)** |
| **M2** | Normalization, Vanity, Extensions & Trunk Healing | `normalization.py`, `standardizer.py` | **Active (v1.0.0)** |
| **M3** | Fraud/Bogus Detection & Confidence Routing | `confidence.py` | **Active (v1.0.0)** |
| **M4** | Batch Streaming, CLI, FastAPI Server & MCP | `batch.py`, `cli.py`, `server.py`, `mcp/` | **Active (v1.0.0)** |
| **M5** | Native Rust PyO3 Extension, Arrow/DuckDB & SDKs | `src/lib.rs`, `arrow.py`, `_native_dispatch.py`, `sdks/` | **Active (v1.1.0)** |
| **M6** | Sub-National Intelligence, Multi-Tier Cache & Audit Ledger | `intelligence.py`, `cache.py`, `audit.py` | **Active (v1.1.0)** |
| **M7** | Fuzzy Telephony Deduplication & Contact Entity Resolution | `dedup.py`, `/v1/compare`, `/v1/deduplicate` | **Active (v1.2.0)** |
| **M8** | Global Dial-Plan Precision, Subsystem Wiring & Portfolio Hardening | `registry_data.py`, `standardizer.py`, `src/lib.rs`, `sdks/` | **Active (v1.3.0)** |

