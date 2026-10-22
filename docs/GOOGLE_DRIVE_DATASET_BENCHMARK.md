# Google Drive Telephony Dataset Benchmark Report (`AP_20261019`)

**Execution Timestamp:** 2026-10-22T18:52:32Z  
**Engine Mode:** `rust_pyo3` (`native_available=True`)  
**Total Datasets Evaluated:** 4 (`1,104.06 MB`)  
**Total Rows Processed:** `2,005,267`  
**Overall Non-Empty Phone Inputs:** `1,410,115`  
**Baseline Valid Yield (Before Remediation):** `1,260,696 / 1,410,115` (**89.40%**)  
**Post-Remediation Valid Yield (After Remediation):** `1,409,567 / 1,410,115` (**99.96%**, **+148,871 records healed**)  
**Rust/Python Parity Rate:** **100.0000%** (`1,410,115 / 1,410,115` exact matches, **0 divergences**)  

---

## 0. Before vs. After Remediation Summary

| Dataset & Column | Non-Empty Inputs | Baseline Valid (`v1.4.0`) | Post-Remediation Valid | Net Records Healed | Baseline Parity | Post-Remediation Parity |
|---|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` [`Phone`] | 46,511 | 46,443 (**99.85%**) | **46,452 (99.87%)** | **+9** | 100.0000% (0 div) | **100.0000% (0 div)** |
| `AdvizorPro_Person_20261019.csv` [`Phone`] | 559,943 | 410,720 (**73.35%**) | **559,559 (99.93%)** | **+148,839 (+26.58%)** | 99.9982% (10 div) | **100.0000% (0 div)** |
| `AdvizorPro_Person_20261019.csv` [`Firm Phone`] | 803,661 | 803,533 (**99.98%**) | **803,556 (99.99%)** | **+23** | 100.0000% (0 div) | **100.0000% (0 div)** |
| **Total Corpus** | **1,410,115** | **1,260,696 (89.40%)** | **1,409,567 (99.96%)** | **+148,871 (+10.56%)** | **99.9993% (10 div)** | **100.0000% (0 div)** |

### Key Engine Remediations Applied
1. **Unspaced Comma-Delimited Multi-Phone Splitting (`+148,544` records healed)**: Enhanced `split_primary_phone()` and Rust `split_primary_phone_rs()` to isolate the primary telephone number from comma-separated multi-number lists (`"5853254140,5854358032"`, `"2149237666,5122220140ext7733,6309242400"`) when both the primary and secondary segments contain $\ge 7$ digits, while preserving comma-grouped single numbers (`"1,800,555,1212"`) and DTMF pause extensions (`",104"`). Recorded via `HealingAction.MULTI_NUMBER_PRIMARY_SELECTED`.
2. **Rust PyO3 vs. Python Zero-Divergence Pipeline Alignment (`10` divergences $\rightarrow$ `0` divergences)**: Harmonized `split_primary_phone` $\rightarrow$ `extract_extension` execution order, added abutting extension keyword parsing (`ext`, `xt`, `#`) without spaces in Rust (`"7174362144ext25025,7176676902"`), and enforced strict 10/11-digit NANP batch fallthrough guards (`"1800TAXSKI,9097848831"`).
3. **Attached `#` and Pipe `|` Extensions (`45` of `46` records healed)**: Expanded `_EXTENSION_RE` and `strip_extension_rs` to extract inline `#<digits>` (`"5126717526#101"`, `"6032262004#233,6179472393"`) and pipe-delimited extensions (`"800.366.7266 | ext. 3211"`).
4. **11-Digit Bare International Numbers & Legacy Swiss Lengths (`219` records healed)**: Lowered the non-NANP bare international calling-code fallback threshold to support 11-digit international numbers lacking a `+` prefix (e.g., Belgium `"32455113280"`, Switzerland `"41442178372"`, Australia `"61383198111"`), and added legacy 7–8 digit national lengths for Switzerland (`+41`).
5. **NANP Miskeyed Leading `0` / `01` Trunk Prefixes & UK/Crown Outcode Postcodes (`52` records healed)**: Added `01` (12-digit) and `0` (11-digit) domestic trunk stripping when followed by a verified NANP NPA, and expanded `infer_country_from_postal_code()` to recognize partial UK outcodes (`"W1F 8"`, `"EC1A"`) and Crown Dependency postcodes (`JE`, `GG`, `IM`, `KY`, `BM`).
6. **Unhyphenated Vanity Numbers (`7` of `7` records healed)**: Updated `_VANITY_CANDIDATE_RE` and Rust vanity decoding to fold unspaced/unhyphenated vanity numbers (`"1800TAXSKI"` $\rightarrow$ `+1800829754`, `"(844)PLAN4IT"` $\rightarrow$ `+18447526448`).

---

## 1. Dataset Inventory & Schema Discovery

| Dataset File | Format | File Size | Row Count | Phone Columns | Geographic Context Columns |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | CSV | 29.84 MB | 46,621 | `Phone` | country=`Country`, state=`State`, postal_code=`Zip`, city=`City`, address=`Address` |
| `AdvizorPro_Firm_Offices_20261019.csv` | CSV | 18.11 MB | 220,504 | *None* | country=`Country`, state=`State`, postal_code=`Zip`, city=`City` |
| `AdvizorPro_Office_Person_20261019.csv` | CSV | 49.04 MB | 933,161 | *None* | *None* |
| `AdvizorPro_Person_20261019.csv` | CSV | 998.07 MB | 804,981 | `Phone`, `Firm Phone` | country=`Country`, state=`State`, postal_code=`Zip`, city=`City`, address=`Address` |

## 2. Post-Remediation Standardization Metrics

| Dataset | Phone Column | Rows | Non-Empty | Valid Count | Valid Rate | Auto-Pass % | Fuzzy Review % | Manual Stewardship % |
|---|---|---|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 46,621 | 46,511 | 46,452 | **99.87%** | 99.2% | 0.7% | 0.1% |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 804,981 | 559,943 | 559,559 | **99.93%** | 99.7% | 0.2% | 0.1% |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 804,981 | 803,661 | 803,556 | **99.99%** | 99.9% | 0.1% | 0.0% |

## 3. High-Throughput Engine Benchmarking

| Dataset | Phone Column | Single-Record Python | Batch Python | Batch Rust PyO3 | Rust Speedup |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 24,774 rec/s | 110,870 rec/s | **679,106 rec/s** | **6.13x** |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 23,577 rec/s | 104,233 rec/s | **683,116 rec/s** | **6.55x** |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 103,785 rec/s | 114,202 rec/s | **698,194 rec/s** | **6.11x** |

## 4. Rust SIMD vs. Python Batch Parity Verification

| Dataset | Column | Records Evaluated | Exact Parity Matches | Parity Rate | Divergences |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 46,511 | 46,511 | 100.0000% | PASS (100.00%) |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 559,943 | 559,943 | 100.0000% | PASS (100.00%) |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 803,661 | 803,661 | 100.0000% | PASS (100.00%) |

## 5. Remaining Invalid Records Breakdown (`548` of `1,410,115` = `0.039%`)

### 5.1 Corrupted / Ambiguous Dial-Plan Entries (`435` records)
| Failure Code | Total Count | Classification | Concrete Sample Inputs | Root Cause |
|---|---|---|---|---|
| `ACTIONABLE_DIAL_PLAN_OR_METADATA_GAP` | 383 | Corrupted / Unassigned Length or NPA | `011417189030`<br>`+40 20 7072 3100`<br>`1762199943`<br>`3058980672` | Truncated 9-digit US numbers (`1762199943`), unassigned NANP exchange/NPA combinations (`305-898` with invalid subscriber length), or miskeyed country calling codes (`+40` Romania prefix on a London `20 7072 3100` number). |
| `ACTIONABLE_COUNTRY_OR_TRUNK_GAP` | 47 | Ambiguous Domestic Trunk Without Address Context | `0284597439`<br>`01244662810`<br>`01483802010`<br>`01244539595` | 10/11-digit leading-`0` numbers where the row's address context is explicitly `US` or empty, preventing safe UK (`+44`) attribution without risking false positives. |
| `ACTIONABLE_LOCAL_NANP_7_DIGIT` | 4 | 7-Digit Local Number Without Area Code | `735-8882`<br>`7358882` | 7-digit subscriber numbers lacking a 3-digit NPA area code. |
| `ACTIONABLE_EXTENSION_FORMAT_GAP` | 1 | Corrupted Non-Numeric Extension Token | `2129448501#t.310,5164485499` | Malformed `#t.310` punctuation inside a concatenated string. |

### 5.2 Genuinely Unparseable Garbage & Non-Telephony Placeholders (`113` records)

| Garbage Code | Total Count | Taxonomy Description | Sample Values |
|---|---|---|---|
| `GARBAGE_EXCESSIVE_DIGITS` | 57 | Space-concatenated or corrupted >15-digit strings | `212 937 8444 917 363 9568`<br>`786 244-7346 786 458-8491`<br>`0044 0207 76286000`<br>`4254671011237,4255317337` |
| `GARBAGE_INSUFFICIENT_DIGITS` | 24 | Fewer than 7 digits without emergency or short-code classification | `815-281`<br>`701`<br>`507645`<br>`1877` |
| `GARBAGE_SEQUENTIAL_OR_TEST` | 24 | Ascending or descending sequential test pattern | `5551234567`<br>`1234567890`<br>`8601234567`<br>`7601234567` |
| `GARBAGE_ALL_ZEROS_OR_ONES` | 8 | All identical repeated placeholder digits (e.g. 000-000-0000, 999-999-9999) | `0000000000`<br>`00000000` |
