# Google Drive Telephony Dataset Benchmark Report

**Execution Timestamp:** 2026-10-22T17:12:10Z  
**Engine Mode:** rust_pyo3  
**Total Datasets Evaluated:** 4  
**Total Records Processed:** 2,005,267  
**Overall Non-Empty Phone Inputs:** 1,410,115  
**Overall Valid Yield:** 89.40%  
**Rust/Python Parity Rate:** 99.9993%  

---

## 1. Dataset Inventory & Schema Discovery

| Dataset File | Format | File Size | Row Count | Phone Columns | Geographic Context Columns |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | CSV | 29.84 MB | 46,621 | `Phone` | country=`Country`, state=`State`, postal_code=`Zip`, city=`City`, address=`Address` |
| `AdvizorPro_Firm_Offices_20261019.csv` | CSV | 18.11 MB | 220,504 | *None* | country=`Country`, state=`State`, postal_code=`Zip`, city=`City` |
| `AdvizorPro_Office_Person_20261019.csv` | CSV | 49.04 MB | 933,161 | *None* | *None* |
| `AdvizorPro_Person_20261019.csv` | CSV | 998.07 MB | 804,981 | `Phone`, `Firm Phone` | country=`Country`, state=`State`, postal_code=`Zip`, city=`City`, address=`Address` |

## 2. Empirical Baseline Standardization Metrics

| Dataset | Phone Column | Rows | Non-Empty | Valid Count | Valid Rate | Auto-Pass % | Fuzzy Review % | Manual Stewardship % |
|---|---|---|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 46,621 | 46,511 | 46,443 | **99.85%** | 99.2% | 0.6% | 0.2% |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 804,981 | 559,943 | 410,720 | **73.35%** | 73.2% | 0.2% | 26.7% |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 804,981 | 803,661 | 803,533 | **99.98%** | 99.9% | 0.1% | 0.0% |

## 3. High-Throughput Engine Benchmarking

| Dataset | Phone Column | Single-Record Python | Batch Python | Batch Rust PyO3 | Rust Speedup |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 27,466 rec/s | 136,934 rec/s | **789,780 rec/s** | **5.77x** |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 21,780 rec/s | 99,396 rec/s | **705,852 rec/s** | **7.10x** |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 110,101 rec/s | 136,616 rec/s | **811,539 rec/s** | **5.94x** |

## 4. Rust SIMD vs. Python Batch Parity Verification

| Dataset | Column | Records Evaluated | Exact Parity Matches | Parity Rate | Divergences |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 46,511 | 46,511 | 100.0000% | PASS (100.00%) |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 559,943 | 559,933 | 99.9982% | **DIVERGENCE (10)** |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 803,661 | 803,661 | 100.0000% | PASS (100.00%) |

## 5. Actionable Failure Taxonomy & Engine Remediation Gaps

| Failure Code | Total Count | Classification | Concrete Sample Inputs | Engine Remediation Opportunity |
|---|---|---|---|---|
| `ACTIONABLE_DIAL_PLAN_OR_METADATA_GAP` | 602 | Actionable Telephony Gap | `32455113280`<br>`011417189030`<br>`014415426330`<br>`+40 20 7072 3100` | Synchronize national dialing plans with upstream ITU / libphonenumber XML metadata. |
| `ACTIONABLE_COUNTRY_OR_TRUNK_GAP` | 99 | Actionable Telephony Gap | `01-703-47-8020`<br>`0284597439`<br>`02078458534`<br>`02038249955` | Improve country code inference from address context or postal code when leading domestic trunk '0' is encountered. |
| `ACTIONABLE_EXTENSION_FORMAT_GAP` | 46 | Actionable Telephony Gap | `6032262004#233,6179472393`<br>`5126717526,5126717526#101,5127919553`<br>`2819144223,3462952334#102,8324731292`<br>`8003737600#2822,8155907319` | Support extended extension prefixes (`opt.`, `option`, `line`, `direct`, `ext-`, `sub`) and trailing punctuation. |
| `ACTIONABLE_RUST_PYTHON_PARITY_GAP` | 10 | Actionable Telephony Gap | `2149237666,5122220140ext7733,6309242400`<br>`817-410-8200 ext. 9135,8178909135`<br>`8603998202 ext 120,8607293798`<br>`419-873-8500 – EXT. 1052,4793728004` | Harmonize Rust `standardize_batch_e164_rs` and Python `decode_vanity_phone` boundary handling on conversational secondary labels. |
| `ACTIONABLE_VANITY_GAP` | 7 | Actionable Telephony Gap | `1800TAXSKI,9097848831`<br>`2543193848,817-410-8200 ext. 9139,8174108200`<br>`800.366.7266 | ext. 3211,9165020574`<br>`7174362144ext25025,7176676902` | Expand keypad vanity decoding to handle unhyphenated words, numeric-word mixtures, and international vanity numbers. |
| `ACTIONABLE_LOCAL_NANP_7_DIGIT` | 4 | Actionable Telephony Gap | `735-8882`<br>`7358882` | Leverage postal code and state context in `infer_country_from_postal_code` to infer NPA for 7-digit local subscriber numbers. |

## 6. Genuinely Unparseable Garbage & Non-Telephony Placeholders

| Garbage Code | Total Count | Taxonomy Description | Sample Values |
|---|---|---|---|
| `GARBAGE_EXCESSIVE_DIGITS` | 148,601 | Excessive digits (> 15) exceeding ITU-T E.164 maximum capacity | `212 937 8444 917 363 9568`<br>`786 244-7346 786 458-8491`<br>`0044 0207 76286000`<br>`5853254140,5854358032` |
| `GARBAGE_SEQUENTIAL_OR_TEST` | 28 | Ascending or descending sequential test pattern | `5551234567`<br>`1234567890`<br>`8601234567`<br>`7601234567` |
| `GARBAGE_INSUFFICIENT_DIGITS` | 24 | Fewer than 7 digits without emergency or short-code classification | `815-281`<br>`701`<br>`507645`<br>`1877` |
| `GARBAGE_ALL_ZEROS_OR_ONES` | 8 | All identical repeated placeholder digits (e.g. 000-000-0000, 999-999-9999) | `0000000000`<br>`00000000` |
