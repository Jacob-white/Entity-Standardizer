# Changelog

All notable changes to **Entity Standardizer** (`entity_standardizer`, `phone_standardizer`, and `address_standardizer`) will be documented in this file.

## [2.0.0] - 2026-10-23

### Added & Fixed
- **Unified `Entity-Standardizer` Architecture (`entity_standardizer`, `phone_standardizer`, `address_standardizer`)**:
  - Merged `Phone-Standardizer` and `Address-Standardizer` into a single unified distribution (`entity-standardizer v2.0.0`) with bidirectional cross-healing (`standardize_contact` / `standardize_entity`), unified PyO3 native extension (`_phone_standardizer_rs` / `_address_standardizer_rs`), and unified CLI, FastAPI (`/v1/address`, `/v1/contact`), and MCP tools.
  - Added fallback loading in `address_standardizer._native_dispatch._init_native()` to import `_phone_standardizer_rs` or load `lib_phone_standardizer_rs.so`/`.dylib`/`.pyd` from `target/release/` so `address_standardizer.is_native_available()` is `True` with the single compiled crate.
  - Added `"h3>=4.0.0"` to `pyproject.toml`, `requirements.txt`, and `requirements-dev.txt`, restored `[tool.setuptools.package-data]` for `address_standardizer`, added `entity_standardizer/__main__.py`, and restored the 5 Rust unit tests for `soundex` and `damerau_levenshtein` in `src/lib.rs`.
- **Bidirectional Cross-Healing & UK 11-Digit Trunk Prefix Hardening (`phone_standardizer/joint.py`, `phone_standardizer/standardizer.py`, `address_standardizer/us_street_parser.py`)**:
  - Guarded `standardize_contact()` against empty or `parse_failed` addresses so UK numbers with `default_country="GB"` (e.g. `0781 234 5678`) are not corrupted by an empty address defaulting to `USA`, and `ADDRESS_COUNTRY_INFERRED_FROM_PHONE` is not recorded on empty addresses.
  - Protected domestic US and conflicting international addresses from having their country overwritten by a foreign phone number in `standardize_contact()` (preserving `country="USA"`, flagging `PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH`, and keeping the foreign phone's own `region_code` rather than overwriting it with the mismatched address state), verified trailing `<City> <5-digit ZIP>` (with or without commas, and including abbreviated names like `St. Louis` via `name_tokens`) against the US ZIP5 reference provider so single-line European 5-digit postal codes (`Calle Mayor 1, Toledo 45001`, `10 Avenue Victor Hugo, Lyon 69002`) do not trigger false US mismatches, and extracted trailing `<City> <5-digit ZIP>` before CRF and in the rule-based US street parser so multi-word cities (`New York 10001`), PO Boxes, and non-comma US addresses parse identically with or without `usaddress`.
  - Enhanced Step 4 of `standardize_contact()` to heal phones when `std_ctx` resolves a concrete country (e.g. single-line `10 Downing St, London SW1A 2AA` with `020 7946 0912`), heal phones rescued in Step 1, and retry `_try_rescue_phone_from_street` with `std_ctx` when a 7-digit local phone requires state inference from `postal_code`; extended Step 3 to infer missing US `state` from the phone's NPA `region_code` when `postal_code` is absent and `city` is verified in that state via `USZip5Provider.lookup_place` (indexing normalized `name_tokens` so abbreviated localities like `St. Louis` resolve in O(1)); and allowed trailing extension suffixes when rescuing misplaced phones from `street1` and `street2`.
  - Ordered UK 11-digit trunk prefix matching (`_UK_DOMESTIC_11DIGIT_TRUNK_PREFIXES`) ahead of generic `0`-prefixed NANP stripping and restricted `01` off-by-one NANP shift healing to non-pure-digit strings so unformatted UK numbers (`01212345678`, `02079460912`) resolve to `GB`.
  - Hardened semicolon/comma/pipe extension extraction and multi-phone splitting parity across Python (`_MULTI_PHONE_SEMI_SLASH_RE`, `_FREE_TEXT_PHONE_CANDIDATE_RE`) and Rust (`strip_extension_single_rs`, `split_primary_phone_rs`) so extensions without spaces (`212-555-0199;x123`, `212-555-0199; x1234567`, `+298 123456;ext. 45`) and multi-phone strings following semicolon extensions (`212-555-0199; x123; 415-555-2671`) preserve both the primary number and its extension.
- **Lazy-Loading Optional Heavy Integrations (`phone_standardizer/arrow.py`, `address_standardizer/__init__.py`, `address_standardizer/arrow.py`)**:
  - Deferred `pyarrow`, `polars`, and `duckdb` imports inside `standardize_arrow()`, `standardize_polars()`, and `register_duckdb_udfs()`, and implemented PEP 562 module-level `__getattr__` in `address_standardizer/__init__.py` for `arrow`, `server`, and `schemas` exports, cutting cold import time of `entity_standardizer` by ~3.4x without eagerly loading `pyarrow`, `polars`, `duckdb`, `fastapi`, or `pydantic`.
- **Multi-Platform SDK Parity for `/v1/address` & `/v1/contact` (`sdks/typescript`, `sdks/go`, `sdks/dotnet`, `tests/test_sdk_contract.py`)**:
  - Added `AddressStandardizeRequest`, `ContactStandardizeRequest`, `StandardizedAddress`, and `StandardizedContact` models and `standardizeAddress` / `standardizeContact` client methods across TypeScript, Go, and .NET SDKs, verified by `tests/test_sdk_contract.py` and `sdks/typescript/tests/client.test.js`.
- **Expanded `entity_standardizer` Exports & v2.0.0 Documentation (`entity_standardizer/__init__.py`, `README.md`)**:
  - Exported `cluster_contact_records`, `ContactCluster`, `PhoneCluster`, `PhoneComparisonResult`, `AddressValidationResult`, `generate_phonetic_address_key`, `autocomplete_address`, and `explain_phone` from `entity_standardizer` and updated `README.md` for `Entity-Standardizer` v2.0.0.

## [1.4.0] - 2026-10-22

### Added & Fixed
- **Dataset-Driven International Healing & Multi-Phone Extraction** (`phone_standardizer/standardizer.py`, `phone_standardizer/normalization.py`):
  - Bare international calling-code healing & anti-doubling: eliminated all 177 doubled calling-code corruptions (`+6565...`, `+352352...`, `+4949...`, `+4343...`, `+6464...`, `+4646...`) while preserving valid 8-digit Singapore `65xx xxxx` landlines and 10-digit Italian `39x xxx xxxx` mobiles.
  - Safe foreign `"011"` IDD exit stripping when `digits_raw` begins with `"011" + context_plan.calling_code` and `"011 +"` redundant prefix stripping.
  - Primary phone extraction (`split_primary_phone`) for `;`, `/`, and `, ` multi-phone strings (`"212-555-1234 / 212-555-5678"`), embedded-digit vanity phone decoding (`"(844) PLAN4IT"`), and clock time-range rejection (`"8:00AM - 6:00PM"`).
  - Argentina (`+54`) 13-digit `+54 9 <area> 15 <subscr>` mobile healing and Brazil (`+55`) `0 + 2-digit carrier code` (`021`, `015`) long-distance prefix stripping.
  - US territory (`PR`, `VI`, `GU`, `AS`, `MP`) `ADDRESS_COUNTRY_MISMATCH` exemption when `country="US"` and NANP Toll-Free `N11` exchange support (`800-211-xxxx`, `800-911-xxxx`).
- **`libphonenumber` `PhoneNumberMetadata.xml` & `ShortNumberMetadata.xml` Full Parity** (`phone_standardizer/registry_data.py`, `phone_standardizer/registry.py`, `phone_standardizer/nanp.py`):
  - Synchronized `nsn_lengths`, `national_trunk_prefix`, and line-type prefixes (`mobile`, `toll_free`, `premium_rate`, `shared_cost`, `voip`, `personal_number`, `pager`, `uan`, `voicemail`) across all 249 ISO-3166-1 dial plans + supplemental territories (`AC`, `TA`, `XK`), achieving **100.00% (`1,132 / 1,132`)** validity, ISO-2, and line-type accuracy against `PhoneNumberMetadata.xml` and **100.00% (`240 / 240`)** emergency code recognition against `ShortNumberMetadata.xml`.
  - Added 5 NANP overlay NPAs (`227` MD, `235` MO, `748` CO, `257` BC, `273` ON) for **439 / 439 (100%)** NANPA area-code parity and sub-area routing for `+39` (`VA`), `+47` (`SJ`), `+61` (`CX`, `CC`), `+358` (`AX`), `+212` (`EH`), `+262` (`YT`), `+599` (`BQ`), and `+290` (`TA`).
- **$O(N)$ Exact-E.164 Deduplication Pre-Grouping & Switchboard Guard** (`phone_standardizer/dedup.py`):
  - Pre-grouped identical `(e164, extension)` records before pairwise bucket indexing in `deduplicate_phones()` and `cluster_contact_records()`, accelerating 22,398-record `dtcc_raw_mfs` deduplication by **58x** (`5,420 ms` -> `92.9 ms`).
  - Guarded corporate switchboard blocks ending in `00`/`000` (`800-526-6300` vs `800-526-6500`) against uncorroborated single-digit fuzzy merges, respected `fuzzy_threshold` on `EXTENSION_VARIANT`, and labeled `dist == 1` length edits as `SINGLE_DIGIT_EDIT`.
- **Rust/Python 100% Batch Parity & Shared Library Auto-Loading** (`src/lib.rs`, `phone_standardizer/_native_dispatch.py`):
  - Synchronized `standardize_batch_e164_rs` with Python's `standardize_batch_e164_dispatch`, achieving **47,270 / 47,270 (100.00%)** parity on `production.firm_master`, and added automatic `target/release/lib_phone_standardizer_rs.so` fallback loading.

## [1.3.0] - 2026-10-22

### Added & Fixed
- **Lexical, Regional Healing & E.123 Formatting Fixes** (`phone_standardizer/normalization.py`, `standardizer.py`, `nanp.py`):
  - Arbitrary leading label stripping (`strip_leading_label`) for CRM/contact labels (`"Contact: +44..."`, `"WhatsApp: +49..."`, `"Call: ..."`).
  - Vanity keypad decoder (`decode_vanity_phone`) guard that strips trailing annotations (`"ask for Bob"`, `"Mon-Fri"`) after complete 10+ digit numbers instead of folding them as keypad digits, and supports longer toll-free vanity words (`1-800-MATTRESS`).
  - Expanded extension parser (`extract_extension`) supporting `:`, `-`, `#` separators, parenthesized extensions (`(ext. 104)`), RFC 3966 `;isub=` subaddresses, and DTMF pause/wait sequences (`,104`, `p104`, `w104`).
  - Argentina (`+54`) domestic trunk `0` stripping and 2-, 3-, and 4-digit area code `15` mobile prefix healing (`+54 9 ...`).
  - Mexico (`+52`) legacy domestic `044`, `045`, and `01` prefix healing alongside international `+52 1` healing.
  - Refined `ADDRESS_COUNTRY_MISMATCH` detection: suppresses false mismatches when `country` was the originating IDD exit dial plan (`011` from `US`) and raises mismatches across shared calling codes (`+1` US vs CA/PR/JM, `+44` GB vs JE/GG/IM, `+7` RU vs KZ).
  - Guarded `(0)` trunk stripping so closed dial plans (`IT`) retain significant leading zeros.
  - Flagged NANP `NPA=555` and reserved `N9X` area codes with `PhoneRiskFlag.INVALID_AREA_CODE` and added 17 new US overlay NPAs (`324`, `327`, `329`, `350`, `353`, `369`, `436`, `526`, `624`, `686`, `728`, `730`, `738`, `821`, `840`, `861`, `924`).
  - Expanded `extract_phones_from_text()` to capture contiguous E.164 (`+14155552671`), 5-group French/German numbers, parenthetical `(0)` trunks, and vanity numbers (`1-800-FLOWERS`).
  - UK (`+44`) 3-digit area code (`0113`, `0121`, `0131`, `0141`, `0151`, `0161`, `0191`) E.123 formatting (`0AAA BBB BBBB`) and 2-digit area-code formatting across `CH`, `BR`, `MX`, `AR`, `IT`, `CN`, and `KR`.
- **Global 249-Country Dial-Plan Registry Precision** (`phone_standardizer/registry_data.py`):
  - Upgraded 193 country dial plans with accurate ITU-T E.164 closed-plan `national_trunk_prefix=None` (`PT`, `GR`, `CZ`, `CL`, `CO`, `UY`, `CR`, `PA`, `LU`, `IS`, `MT`, `CY`, `QA`, `KW`, `BH`, `OM`, `VA`, `SM`, `MC`, `AD`), `8`/`810` trunk/IDD for `KZ`/`BY`, `06` trunk for `HU`, and exact NSN lengths and mobile prefixes across 25+ major economies (`ID`, `SA`, `IL`, `TR`, `BE`, `GR`, `CO`, `PK`, `EG`, `MY`, `PH`, `TH`, `VN`, `NG`, `KE`, `CL`, `PE`, `AR`, `PT`, `CZ`, `HU`, `RO`, `UA`, `FI`, `HK`, `TW`).
- **Subsystem Wiring & Native Rust Dispatch** (`_native_dispatch.py`, `src/lib.rs`, `cache.py`, `audit.py`, `dedup.py`):
  - Wired `fold_unicode_digits_dispatch`, `fold_vanity_digits_dispatch`, and `damerau_levenshtein_distance_dispatch` (`damerau_levenshtein_distance_rs`) into hot paths without circular recursion, and upgraded `standardize_batch_e164_dispatch` / `standardize_batch_e164_rs` to handle extensions, vanity words, and trunk prefixes.
  - Wired `MultiTierCache` and `infer_country_from_postal_code()` into `standardize_phone()`, included `(addr_iso2, addr_state)` in `make_cache_key()`, and added `.close()` / context manager support to `SQLiteCache`, `MultiTierCache`, and `PhoneStewardshipLedger`.
  - Guarded `NATIONAL_EQUIVALENT` in `compare_phones()` when both inputs carry explicit international `+CC` prefixes.
- **Portfolio Synergy (`Address-Standardizer` & `Query-Builder`)**:
  - Guarded `SHARED_ADDRESS_KEY` in `cluster_contact_records()` against `is_registered_agent_hub` and `is_cmra` on `StandardizedAddress` contexts.
  - Expanded `mask_phone()` with all 8 `Query-Builder` CLAC masking strategies (`partial`, `partial_phone`, `last4`, `redact`, `null`, `hash`, `sha256`, `md5`) and registered `phone_blocking_keys()` in `register_duckdb_udfs()`.
- **Multi-Platform SDK Parity (`v1.3.0`)**:
  - Added `usePhoneInput()` React hook + `AbortController`/`requestId` stale-request guard in TypeScript SDK, nullable `*string` fields in Go SDK, and full `explain`, `compare`, `deduplicate`, and `listCountries` parity across TypeScript, Go, and .NET SDKs.

## [1.2.0] - 2026-10-21

### Added
- **Telephony Fuzzy Deduplication, Keypad/Transposition Distance & Contact Entity Resolution** (`phone_standardizer/dedup.py`):
  - `compare_phones` & `PhoneComparisonResult`: Multi-dimensional telephony matcher detecting exact E.164 matches, PBX extension variants (`EXTENSION_VARIANT`), cross-context national equivalents (`NATIONAL_EQUIVALENT`), single adjacent digit swaps (`ADJACENT_TRANSPOSITION`), ITU-T E.161 physical dialpad typos (`KEYPAD_ADJACENT_TYPO`), and Damerau-Levenshtein distance.
  - `generate_phone_blocking_keys`: Multi-pass deterministic blocking keys (`e164`, `nsn`, `tail7`, `cc_sorted`, `cc_head6`, `cc_area_tail4`) for scalable entity resolution and SQL blocking.
  - `deduplicate_phones` & `PhoneCluster`: Disjoint-set contact clustering with deterministic Golden Phone Record survivorship.
  - `cluster_contact_records`, `ContactCluster`, and `infer_country_from_postal_code`: Cross-portfolio entity resolution linking `Phone-Standardizer` (`phone_key` + fuzzy phone matching) with `Address-Standardizer` (`address_key` & postal codes).
- **Service, MCP & CLI Entity Resolution Extensions**:
  - FastAPI endpoints: `POST /v1/compare` and `POST /v1/deduplicate`.
  - MCP tools: `compare_phones` and `deduplicate_phones`.
  - CLI commands: `phone-standardizer compare` and `phone-standardizer dedup`.

## [1.1.0] - 2026-10-21

### Added
- **Sub-National Geographic, Timezone & Carrier MNO Intelligence** (`phone_standardizer/intelligence.py`):
  - `resolve_timezones`: Maps all 50 US states, DC, Canadian provinces, and global ISO countries to IANA timezones (`America/Los_Angeles`, `Europe/London`, `Asia/Tokyo`, etc.).
  - `resolve_locality`: Metro area & city gazetteer for major NANP and international area codes.
  - `resolve_carrier_hint`: International Mobile Network Operator (MNO) prefix attribution.
  - `evaluate_calling_window`: Conservative multi-timezone TCPA/DNC local quiet-hours evaluator (`08:00–21:00` local time).
- **Multi-Tier Caching Engine** (`phone_standardizer/cache.py`): Thread-safe L1 `LRUCache` + persistent L2 `SQLiteCache` (WAL mode) with `MultiTierCache`, `configure_cache`, `get_cache_stats`, and `clear_cache`.
- **Stewardship Audit Ledger & Explainability** (`phone_standardizer/audit.py`): `explain_phone()` diagnostic report, `/v1/explain` HTTP endpoint, `explain_phone` MCP tool, and SQLite-backed `PhoneStewardshipLedger`.
- **Brazil Legacy 8-to-9 Digit Mobile Healer & Free-Text Bulk Extractor**: `HealingAction.BRAZIL_MOBILE_9_INSERTED` and `extract_phones_from_text()`.
- **Columnar Arrow/Polars/DuckDB UDFs & Multi-Platform SDKs**: `phone_standardizer/arrow.py`, `src/lib.rs` batch E.164 acceleration, and TypeScript/React, Go, and .NET client SDKs.

## [1.0.0] - 2026-10-21

### Added
- **Universal 249 ISO-3166-1 Country & ITU-T E.164 Dial-Plan Registry** (`phone_standardizer/registry.py`, `registry_data.py`).
- **Complete NANP (`+1`) 25-Country & US/Canada State/Province NPA Attribution** (`phone_standardizer/nanp.py`).
- **Multi-Standard Formatting Engine**: ITU-T E.164, ITU-T E.123 National & International, and IETF RFC 3966 (`tel:` URI).
- **Trunk & Legacy Mobile Prefix Healer**: Redundant `(0)` trunk stripping, Mexico `+52 1` mobile prefix healing, Argentina `15` mobile prefix healing, Unicode numeral folding, ITU-T E.161 vanity keypad decoding, and extension extraction.
- **Fraud, IRSF & Synthetic Range Guardrails** (`phone_standardizer/confidence.py`) with composite confidence scoring and routing tiers (`AUTO_PASS`, `FUZZY_REVIEW`, `MANUAL_STEWARDSHIP`).
- **CLI, FastAPI HTTP Microservice, MCP Server, Batch Streaming, and Rust PyO3 Native Extension**.
