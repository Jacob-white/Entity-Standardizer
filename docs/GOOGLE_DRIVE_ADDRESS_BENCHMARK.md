# Google Drive Global & Financial Dataset Address-Standardizer Benchmark Report

**Execution Timestamp:** 2026-10-23T01:56:15Z  
**Engine:** Address-Standardizer v3.3.0 (`Rust_PyO3` + Multi-National UPU S42 & USPS Pub 28)  
**Total Dataset Address Groups Evaluated:** 27  
**Total Non-Empty Address Records Processed:** 5,928,074  
**Total Unique Address Tuples Evaluated:** 2,392,332  
**Overall Usable Yield (`standardized` + `locality_only`):** **100.00%** (`5,927,890 / 5,928,074`)  
**Full Street-Level Standardized:** 5,701,314 (96.17%)  
**Locality-Only Standardized:** 226,576 (3.82%)  
**Unparseable / Parse Failed:** 184 (0.00%)  

---

## 1. Per-Dataset Address Standardization Yield & Routing Distribution

| Suite | Dataset File | Address Group | Non-Empty Rows | Unique Tuples | Standardized | Locality Only | Parse Failed | Usable Yield % | Auto-Pass % | Rooftop Extracted | Countries | Throughput |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `AdvizorPro` | `AdvizorPro_Firm_20261019.csv` | `Primary Address` | 46,619 | 35,356 | 34,592 | 12,027 | 0 | **100.00%** | 71.9% | 34,567 | 93 | 10,240 r/s |
| `AdvizorPro` | `AdvizorPro_Firm_Offices_20261019.csv` | `Office Address` | 220,504 | 179,818 | 173,761 | 46,743 | 0 | **100.00%** | 75.7% | 173,682 | 81 | 9,619 r/s |
| `AdvizorPro` | `AdvizorPro_Person_20261019.csv` | `Person Address` | 804,084 | 192,207 | 749,187 | 54,897 | 0 | **100.00%** | 90.5% | 749,072 | 85 | 34,146 r/s |
| `AdvizorPro` | `AdvizorPro_Person_20261019.csv` | `Firm Address` | 804,106 | 33,829 | 787,380 | 16,726 | 0 | **100.00%** | 96.8% | 787,229 | 91 | 637,811 r/s |
| `AdvisorAtlas` | `FIRMOUTFULL_20261019115038206.txt` | `Address` | 324 | 305 | 324 | 0 | 0 | **100.00%** | 99.1% | 324 | 1 | 1,412 r/s |
| `AdvisorAtlas` | `OFFICEOUTFULL_20261019115038206.txt` | `Address` | 33,822 | 31,444 | 33,819 | 3 | 0 | **100.00%** | 98.4% | 33,705 | 1 | 6,873 r/s |
| `AdvisorAtlas` | `REPOUTFULL_20261019115038206.txt` | `Address` | 220,247 | 21,215 | 220,238 | 9 | 0 | **100.00%** | 98.5% | 220,100 | 1 | 575,659 r/s |
| `Discovery` | `BDFirmDataFeedDelta.csv` | `MainOffice Address` | 31 | 31 | 31 | 0 | 0 | **100.00%** | 96.8% | 31 | 2 | 739 r/s |
| `Discovery` | `BDRepDataFeedDelta.csv` | `Branch Address` | 15,554 | 6,280 | 15,554 | 0 | 0 | **100.00%** | 95.4% | 15,096 | 4 | 17,683 r/s |
| `Discovery` | `BDFirmDataFeedFull.csv` | `MainOffice Address` | 3,237 | 3,018 | 3,236 | 1 | 0 | **100.00%** | 97.6% | 3,231 | 12 | 7,900 r/s |
| `Discovery` | `BDRepDataFeedFull.csv` | `Branch Address` | 652,812 | 106,914 | 652,797 | 15 | 0 | **100.00%** | 94.9% | 627,551 | 28 | 45,684 r/s |
| `Discovery` | `Historical_Firms.csv` | `Historical Firm Address` | 47,009 | 43,264 | 45,885 | 1,124 | 0 | **100.00%** | 91.6% | 44,264 | 66 | 7,226 r/s |
| `Discovery` | `Reps_No_Longer_In_Discovery_Data.csv` | `Branch Address` | 584,560 | 145,742 | 584,482 | 78 | 0 | **100.00%** | 97.2% | 584,441 | 37 | 23,875 r/s |
| `Discovery` | `Reps_No_Longer_In_Discovery_Data.csv` | `Home Address` | 241,432 | 237,508 | 241,347 | 85 | 0 | **100.00%** | 97.1% | 235,623 | 30 | 7,161 r/s |
| `Discovery` | `RIAFirmDataFeedDelta.csv` | `MainOffice Address` | 1,194 | 1,162 | 1,192 | 2 | 0 | **100.00%** | 93.5% | 1,130 | 22 | 5,195 r/s |
| `Discovery` | `RIARepDataFeedDelta.csv` | `Office Address` | 13,136 | 5,369 | 13,115 | 21 | 0 | **100.00%** | 92.3% | 12,322 | 21 | 55,231 r/s |
| `Discovery` | `RIAFirmDataFeedFull.csv` | `MainOffice Address` | 43,714 | 37,882 | 43,675 | 39 | 0 | **100.00%** | 92.7% | 40,790 | 90 | 9,950 r/s |
| `Discovery` | `RIARepDataFeedFull.csv` | `Office Address` | 513,742 | 130,507 | 513,551 | 191 | 0 | **100.00%** | 92.0% | 478,918 | 91 | 151,783 r/s |
| `Foursquare_OS_Places_Global` | `FSQ_Global_Asia_Pacific.csv` | `Physical Address` | 110,737 | 102,266 | 101,541 | 9,167 | 29 | **99.97%** | 88.0% | 101,273 | 51 | 13,997 r/s |
| `Foursquare_OS_Places_Global` | `FSQ_Global_Europe.csv` | `Physical Address` | 247,784 | 230,916 | 239,480 | 8,295 | 9 | **100.00%** | 93.3% | 239,269 | 57 | 18,729 r/s |
| `Foursquare_OS_Places_Global` | `FSQ_Global_Latin_America_Caribbean.csv` | `Physical Address` | 83,574 | 75,276 | 76,953 | 6,614 | 7 | **99.99%** | 88.2% | 76,849 | 48 | 18,968 r/s |
| `Foursquare_OS_Places_Global` | `FSQ_Global_Middle_East_Africa.csv` | `Physical Address` | 93,417 | 83,943 | 82,363 | 10,991 | 63 | **99.93%** | 84.2% | 81,357 | 79 | 18,054 r/s |
| `Foursquare_OS_Places_Global` | `FSQ_Global_North_America.csv` | `Physical Address` | 27,392 | 24,689 | 26,606 | 786 | 0 | **100.00%** | 81.9% | 26,530 | 10 | 10,967 r/s |
| `Overture_Maps_Global_Places` | `Overture_Global_Americas.csv` | `Physical Address` | 377,019 | 307,411 | 362,418 | 14,599 | 2 | **100.00%** | 87.6% | 362,194 | 17 | 15,070 r/s |
| `Overture_Maps_Global_Places` | `Overture_Global_Asia_Oceania.csv` | `Physical Address` | 254,443 | 214,872 | 238,122 | 16,250 | 71 | **99.97%** | 90.2% | 237,724 | 20 | 17,866 r/s |
| `Overture_Maps_Global_Places` | `Overture_Global_Europe_MEA.csv` | `Physical Address` | 404,784 | 333,995 | 389,337 | 15,444 | 3 | **100.00%** | 95.4% | 388,501 | 37 | 20,394 r/s |
| `Wikidata_And_Regulatory_Global` | `SEC_DTCC_Regulatory_Filings.csv` | `Physical Address` | 82,797 | 60,161 | 70,328 | 12,469 | 0 | **100.00%** | 46.2% | 70,167 | 91 | 12,094 r/s |

## 2. Suite-Level Summary

| Dataset Suite | Non-Empty Addresses | Standardized | Locality Only | Parse Failed | Usable Yield % | US Records | International Records |
|---|---:|---:|---:|---:|---:|---:|---:|
| **AdvizorPro** | 1,875,313 | 1,744,920 | 130,393 | 0 | **100.00%** | 1,843,177 | 32,136 |
| **AdvisorAtlas** | 254,393 | 254,381 | 12 | 0 | **100.00%** | 254,393 | 0 |
| **Discovery** | 2,116,421 | 2,114,865 | 1,556 | 0 | **100.00%** | 2,094,265 | 22,156 |
| **Foursquare_OS_Places_Global** | 562,904 | 526,943 | 35,853 | 108 | **99.98%** | 19,785 | 543,119 |
| **Overture_Maps_Global_Places** | 1,036,246 | 989,877 | 46,293 | 76 | **99.99%** | 168,253 | 867,993 |
| **Wikidata_And_Regulatory_Global** | 82,797 | 70,328 | 12,469 | 0 | **100.00%** | 75,228 | 7,569 |
