# Review follow-ups

Open items from the whole-codebase review. The review's other findings are fixed and committed. Tick items off as they land.

## Spatial and autocomplete

- [x] H3 fallback (`spatial/h3_indexer.py`) was not real H3: removed; `h3` is now a required dependency and the wrapper only returns real H3 values; validate coordinates; add known-vector tests when `h3` is present.
- [x] `autocomplete.py`: exclude records without coordinates when a radius is given.
- [x] `autocomplete.py`: dedupe in `connect_reference_index`.
- [x] `autocomplete.py`: clamp the haversine intermediate value to [0, 1].
- [x] `autocomplete.py`: handle negative `max_results`.
- [x] `calculate_polygon_centroid`: antimeridian handling; skip empty polygon rings.

## Tests and benchmarks

- [x] `benchmarks/run_benchmarks.py::benchmark_accuracy` skips expected keys not in its hard-coded dict (`address_status`, `is_us` are never compared): compare every expected key, fail on unknown ones.
- [x] Mark wall-clock assertions as `perf` (`tests/test_m32*`, `tests/test_autocomplete.py`, `tests/spatial/test_integration.py`, ReDoS timings in `tests/test_phase6*`).
- [x] Make hypothesis fuzz tests deterministic (derandomize / fixed seed).
- [x] Add arrow, polars and duckdb to the dev extras, or fail CI when their tests skip.
- [x] SDK contract test (`tests/test_sdk_contract.py`) only checks names: extend to types, nullability and defaults; make its regex parsers fail loudly when they match nothing.
- [x] H3 tests need known vectors.
- [x] `generate_multinational_golden_dataset.py` does not reproduce the committed JSON: fix it, or document why.

## Docs (verified wrong, high severity)

- [x] `docs/api_reference.md`: Python API names and signatures, REST paths (`/v1/*`), batch limit (10,000, 413), CLI syntax (`parse`, not `standardize`; `batch` positional args; `benchmark` flags).
- [x] `docs/quickstart.md`: almost every snippet fails; fix the curl path and the install extras (`[server]`, `[arrow]`).
- [x] `README.md`: wrong outputs; unclosed code fence (~line 504); false claims ("960+ tests", "100% coverage" (actual ~89.6%), "220,000 rec/sec native SIMD", "bit-for-bit"); wrong CLI flags (`--include-intl`, `spatial ingest`, `audit --summary`); wrong install steps.
- [x] SDK READMEs:
  - TypeScript: `RequestOptions`, `isStreamError`, typed errors, `react` peer dependency.
  - Go: `StreamBatchRecords`, `WithTimeout`, `AutocompleteGetRequest`, `*bool` CMRA/Vacant, `testdata` fixtures.
  - .NET: `StreamBatchRecordsAsync`, nullable flags, `AddressStandardizerRecordException` / `AddressStandardizerException`, `AutocompleteGetAsync`.
- [x] Document `correct_state_from_zip` (param, API field, CLI flag, env var). Streaming library functions only honor the env var.
- [x] Document the env vars: `ADDRESS_STANDARDIZER_MAX_BATCH`, `_MAX_BODY_BYTES`, `_CORS_ORIGINS`, `_DISABLE_DOCS`, `_FORCE_PURE`, `_AUDIT_MAX_ROWS`, `_CORRECT_STATE_FROM_ZIP`.
- [x] Document that the Rust module is Soundex-only.
- [x] `docs/RELEASING.md`.

## Status: everything on this list is resolved

All items from the whole-codebase review are fixed, decided, or documented below. Line **and branch** coverage of the package is 100% (`branch = true`, `fail_under = 100`).

### Decisions taken
- **Non-Latin keys:** keys stay ASCII; letters/digits with no ASCII transliteration are encoded as `~<6-digit hex code point>`, so distinct CJK/Hangul/Arabic streets no longer collide.
- **Care-of:** the removed `c/o` / `C/-` / `attn` text is now returned in `care_of` (never part of street1/street2).
- **Hub addresses:** `routing_tier` (parse/deliverability confidence) and `review_status` (stewardship queue) are independent by design; a registered-agent hub can be AUTO_PASS and still PENDING.
- **Free text in `street2`:** `street2` is Address Line 2; any non-empty text there is kept (as a unit when it looks like one), never dropped.
- **`LocalityOnlyStatus`:** equal to both `locality_only` and `city_level`; hash follows the canonical spelling (documented in the class).
- **UK `HILL`/`HILLS`:** deliberately not abbreviated (Royal Mail has none).
- **Bermuda postcodes:** format-checked (`AA NN`, or `HM <letter>X`) but area codes are not whitelisted because published lists disagree.
- **Lone non-numeric street word** (`XYZ`): status `standardized`, routing tier MANUAL_STEWARDSHIP flags it for review.
- **`phonetic_key` `#5`:** intentional numbered-street token.
- **Australian 5-digit "postcode"** after a state is invalid input and is not treated as Australian.

### Still worth knowing
- Direct calls to the private `_rule_based_us_street_parse` with a full "street, city, ST ZIP" string can add an ordinal suffix to the ZIP; the public pipeline splits city/state/ZIP off first, so it never sees that input.
- Danish floor/door text keeps the grammar's lowercase (`2. tv`).
- A `street2` supplied alongside a comma-parsed MENA PO box is ignored (existing behaviour, not part of the reviewed bugs).
- With a street2 present, a street line that itself carries two inline units stays unsplit.
- Romance (ESP/ITA) postal codes are 5 digits only, so a 4-digit trailing token stays in street2.
- Verify the GitHub Actions run after pushing (Linux 3.11 and 3.13 runs were reproduced locally; Windows jobs were not).

## Known behavior notes (for the release notes)

- Street-type abbreviation applies only to the type word.
- ZIP/state mismatch keeps the supplied state by default; `correct_state_from_zip` is opt-in.
- Unresolved geocodes serialize null latitude/longitude.
- Batch size and body size limits return 413.
- `serve` binds to 127.0.0.1 by default.
- The Rust module is trimmed to Soundex only.
- Python 3.11 or newer is required.
- Golden datasets were regenerated from engine output where the old expectations encoded bugs.
- `h3` is a required dependency; there is no approximate fallback. Invalid or out-of-range coordinates raise `ValueError` instead of being clamped.
- A country name that cannot be resolved is reported as `ZZZ`, not `USA`; `N/A`, `none`, `unknown` mean "no country given".
- Postal validation is stricter: Dutch codes cannot start with 0, Eircodes must use the Eircode alphabet, Bermuda codes must be `AA NN` (or `HM <letter>X`).
- `normalize_us_postal_code` no longer pads, truncates or invents a ZIP from malformed input (returns the cleaned text with an empty ZIP5).
- Jersey, Guernsey and the Isle of Man now report `JEY`, `GGY`, `IMN` (previously `GBR`), so their keys end in those codes.
- German house-number ranges (`5-7`) stay in street1; `Str.`/`Pl.` expand to `STRASSE`/`PLATZ`.
- CLI: `--audit-db` / `ADDRESS_STANDARDIZER_AUDIT_DB` persist the audit ledger; `parse` no longer forces a default `--country USA`.
