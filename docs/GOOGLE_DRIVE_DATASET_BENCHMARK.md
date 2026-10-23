# Google Drive Telephony Dataset Benchmark Report

**Execution Timestamp:** 2026-10-23T01:42:08Z  
**Engine Mode:** rust_pyo3  
**Total Datasets Evaluated:** 29  
**Total Records Processed:** 17,582,685  
**Overall Non-Empty Phone Inputs:** 6,671,617  
**Overall Valid Yield:** 99.96%  
**Rust/Python Parity Rate:** 100.0000%  

---

## 1. Dataset Inventory & Schema Discovery

| Dataset File | Format | File Size | Row Count | Phone Columns | Geographic Context Columns |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | CSV | 29.84 MB | 46,621 | `Phone` | country=`Country`, state=`State`, postal_code=`Zip`, city=`City`, address=`Address` |
| `AdvizorPro_Firm_Offices_20261019.csv` | CSV | 18.11 MB | 220,504 | *None* | country=`Country`, state=`State`, postal_code=`Zip`, city=`City` |
| `AdvizorPro_Office_Person_20261019.csv` | CSV | 49.04 MB | 933,161 | *None* | *None* |
| `AdvizorPro_Person_20261019.csv` | CSV | 998.07 MB | 804,981 | `Phone`, `Firm Phone` | country=`Country`, state=`State`, postal_code=`Zip`, city=`City`, address=`Address` |
| `FIRMOUTFULL_20261019115038206.txt` | TXT | 0.08 MB | 325 | `Phone 1`, `Phone 2`, `Fax 1`, `Fax 2` | country=`Country ID`, state=`State Province`, postal_code=`Postal Code 1`, city=`City`, address=`Address Line 1` |
| `GRPXREFOUTFULL_20261019115038206.txt` | TXT | 10.02 MB | 206,715 | *None* | *None* |
| `OFFICEOUTFULL_20261019115038206.txt` | TXT | 10.66 MB | 33,836 | `Phone 1`, `Phone 2`, `Fax 1`, `Fax 2` | country=`Country ID`, state=`State Province`, postal_code=`Postal Code 1`, city=`City`, address=`Address Line 1` |
| `REPATTROUTFULL_20261019115038206.txt` | TXT | 507.06 MB | 11,103,009 | *None* | *None* |
| `REPOUTFULL_20261019115038206.txt` | TXT | 89.07 MB | 223,870 | `Business Phone`, `Home Phone`, `Mobile Phone`, `Fax 1`, `Fax 2`, `Business Phone 2`, `Assistant Phone` | country=`Country ID`, state=`State Province`, postal_code=`Postal Code 1`, city=`City`, address=`Address Line 1` |
| `BDFirmDataFeedDelta.csv` | CSV | 0.05 MB | 31 | `MainOffice_Phone` | country=`MainOffice_Country`, state=`MainOffice_State`, postal_code=`MainOffice_ZipCode`, city=`MainOffice_City`, address=`MainOffice_Address1` |
| `BDRepDataFeedDelta.csv` | CSV | 30.61 MB | 15,554 | `Branch_Phone`, `Home_Phone`, `HQ_Phone` | country=`Branch_Country`, state=`Branch_State`, postal_code=`Branch_ZipCode`, city=`Branch_City`, address=`Branch_Address1` |
| `BDFirmDataFeedFull.csv` | CSV | 4.93 MB | 3,237 | `MainOffice_Phone` | country=`MainOffice_Country`, state=`MainOffice_State`, postal_code=`MainOffice_ZipCode`, city=`MainOffice_City`, address=`MainOffice_Address1` |
| `BDRepDataFeedFull.csv` | CSV | 1261.70 MB | 652,812 | `Branch_Phone`, `Home_Phone`, `HQ_Phone` | country=`Branch_Country`, state=`Branch_State`, postal_code=`Branch_ZipCode`, city=`Branch_City`, address=`Branch_Address1` |
| `Historical_Firms.csv` | CSV | 4.72 MB | 47,792 | *None* | state=`State`, postal_code=`Zip`, city=`City`, address=`Address1` |
| `Reps_No_Longer_In_Discovery_Data.csv` | CSV | 178.53 MB | 916,503 | `BranchPhone`, `HomePhone` | state=`BranchState`, postal_code=`BranchZip`, city=`BranchCity`, address=`BranchAddr1` |
| `RIAFirmDataFeedDelta.csv` | CSV | 3.43 MB | 1,194 | `MainOffice_Phone`, `MainOffice_Fax` | country=`MainOffice_Country`, state=`MainOffice_State`, postal_code=`MainOffice_ZipCode`, city=`MainOffice_City`, address=`MainOffice_Address1` |
| `RIARepDataFeedDelta.csv` | CSV | 25.56 MB | 13,136 | `Office_Phone`, `Home_Phone`, `HQ_Phone` | country=`Office_Country`, state=`Office_State`, postal_code=`Office_ZipCode`, city=`Office_City`, address=`Office_Address1` |
| `RIAFirmDataFeedFull.csv` | CSV | 108.14 MB | 43,714 | `MainOffice_Phone`, `MainOffice_Fax` | country=`MainOffice_Country`, state=`MainOffice_State`, postal_code=`MainOffice_ZipCode`, city=`MainOffice_City`, address=`MainOffice_Address1` |
| `RIARepDataFeedFull.csv` | CSV | 941.31 MB | 513,742 | `Office_Phone`, `Home_Phone`, `HQ_Phone` | country=`Office_Country`, state=`Office_State`, postal_code=`Office_ZipCode`, city=`Office_City`, address=`Office_Address1` |
| `FSQ_Global_Asia_Pacific.csv` | CSV | 12.57 MB | 118,299 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `FSQ_Global_Europe.csv` | CSV | 26.44 MB | 254,294 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `FSQ_Global_Latin_America_Caribbean.csv` | CSV | 8.91 MB | 88,046 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `FSQ_Global_Middle_East_Africa.csv` | CSV | 10.05 MB | 100,433 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `FSQ_Global_North_America.csv` | CSV | 2.72 MB | 27,850 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `Overture_Global_Americas.csv` | CSV | 43.27 MB | 377,537 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `Overture_Global_Asia_Oceania.csv` | CSV | 31.84 MB | 254,961 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `Overture_Global_Europe_MEA.csv` | CSV | 47.20 MB | 405,752 | `Phone` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `SEC_DTCC_Regulatory_Filings.csv` | CSV | 12.49 MB | 117,233 | `Phone`, `Fax` | country=`Country`, state=`State`, postal_code=`PostalCode`, city=`City`, address=`Address` |
| `Wikidata_Global_Institutions.csv` | CSV | 4.01 MB | 57,543 | `Phone`, `Fax` | country=`Country`, postal_code=`PostalCode` |

## 2. Empirical Baseline Standardization Metrics

| Dataset | Phone Column | Rows | Non-Empty | Valid Count | Valid Rate | Auto-Pass % | Fuzzy Review % | Manual Stewardship % |
|---|---|---|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 46,621 | 46,511 | 46,456 | **99.88%** | 99.2% | 0.7% | 0.1% |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 804,981 | 559,943 | 559,783 | **99.97%** | 99.7% | 0.2% | 0.0% |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 804,981 | 803,661 | 803,574 | **99.99%** | 99.9% | 0.1% | 0.0% |
| `FIRMOUTFULL_20261019115038206.txt` | `Phone 1` | 325 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `FIRMOUTFULL_20261019115038206.txt` | `Phone 2` | 325 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `FIRMOUTFULL_20261019115038206.txt` | `Fax 1` | 325 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `FIRMOUTFULL_20261019115038206.txt` | `Fax 2` | 325 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `OFFICEOUTFULL_20261019115038206.txt` | `Phone 1` | 33,836 | 30,038 | 30,035 | **99.99%** | 100.0% | 0.0% | 0.0% |
| `OFFICEOUTFULL_20261019115038206.txt` | `Phone 2` | 33,836 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `OFFICEOUTFULL_20261019115038206.txt` | `Fax 1` | 33,836 | 23,209 | 23,201 | **99.97%** | 99.9% | 0.0% | 0.0% |
| `OFFICEOUTFULL_20261019115038206.txt` | `Fax 2` | 33,836 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `REPOUTFULL_20261019115038206.txt` | `Business Phone` | 223,870 | 169,552 | 169,536 | **99.99%** | 100.0% | 0.0% | 0.0% |
| `REPOUTFULL_20261019115038206.txt` | `Home Phone` | 223,870 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `REPOUTFULL_20261019115038206.txt` | `Mobile Phone` | 223,870 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `REPOUTFULL_20261019115038206.txt` | `Fax 1` | 223,870 | 14,957 | 14,951 | **99.96%** | 99.9% | 0.0% | 0.0% |
| `REPOUTFULL_20261019115038206.txt` | `Fax 2` | 223,870 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `REPOUTFULL_20261019115038206.txt` | `Business Phone 2` | 223,870 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `REPOUTFULL_20261019115038206.txt` | `Assistant Phone` | 223,870 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `BDFirmDataFeedDelta.csv` | `MainOffice_Phone` | 31 | 24 | 24 | **100.00%** | 100.0% | 0.0% | 0.0% |
| `BDRepDataFeedDelta.csv` | `Branch_Phone` | 15,554 | 15,301 | 15,300 | **99.99%** | 100.0% | 0.0% | 0.0% |
| `BDRepDataFeedDelta.csv` | `Home_Phone` | 15,554 | 2,930 | 2,930 | **100.00%** | 99.9% | 0.1% | 0.0% |
| `BDRepDataFeedDelta.csv` | `HQ_Phone` | 15,554 | 14,309 | 14,309 | **100.00%** | 100.0% | 0.0% | 0.0% |
| `BDFirmDataFeedFull.csv` | `MainOffice_Phone` | 3,237 | 3,026 | 3,026 | **100.00%** | 99.9% | 0.1% | 0.0% |
| `BDRepDataFeedFull.csv` | `Branch_Phone` | 652,812 | 644,931 | 644,902 | **100.00%** | 100.0% | 0.0% | 0.0% |
| `BDRepDataFeedFull.csv` | `Home_Phone` | 652,812 | 148,105 | 148,101 | **100.00%** | 99.9% | 0.1% | 0.0% |
| `BDRepDataFeedFull.csv` | `HQ_Phone` | 652,812 | 634,262 | 634,262 | **100.00%** | 100.0% | 0.0% | 0.0% |
| `Reps_No_Longer_In_Discovery_Data.csv` | `BranchPhone` | 916,503 | 433,637 | 433,607 | **99.99%** | 100.0% | 0.0% | 0.0% |
| `Reps_No_Longer_In_Discovery_Data.csv` | `HomePhone` | 916,503 | 54,726 | 54,726 | **100.00%** | 100.0% | 0.0% | 0.0% |
| `RIAFirmDataFeedDelta.csv` | `MainOffice_Phone` | 1,194 | 1,194 | 1,194 | **100.00%** | 99.7% | 0.3% | 0.0% |
| `RIAFirmDataFeedDelta.csv` | `MainOffice_Fax` | 1,194 | 540 | 540 | **100.00%** | 99.8% | 0.2% | 0.0% |
| `RIARepDataFeedDelta.csv` | `Office_Phone` | 13,136 | 13,135 | 13,132 | **99.98%** | 99.9% | 0.1% | 0.0% |
| `RIARepDataFeedDelta.csv` | `Home_Phone` | 13,136 | 3,173 | 3,173 | **100.00%** | 99.9% | 0.1% | 0.0% |
| `RIARepDataFeedDelta.csv` | `HQ_Phone` | 13,136 | 13,130 | 13,130 | **100.00%** | 99.9% | 0.1% | 0.0% |
| `RIAFirmDataFeedFull.csv` | `MainOffice_Phone` | 43,714 | 43,666 | 43,644 | **99.95%** | 99.2% | 0.7% | 0.1% |
| `RIAFirmDataFeedFull.csv` | `MainOffice_Fax` | 43,714 | 20,026 | 20,024 | **99.99%** | 99.7% | 0.3% | 0.0% |
| `RIARepDataFeedFull.csv` | `Office_Phone` | 513,742 | 513,420 | 513,252 | **99.97%** | 99.7% | 0.2% | 0.0% |
| `RIARepDataFeedFull.csv` | `Home_Phone` | 513,742 | 129,000 | 128,996 | **100.00%** | 99.9% | 0.1% | 0.0% |
| `RIARepDataFeedFull.csv` | `HQ_Phone` | 513,742 | 513,334 | 513,261 | **99.99%** | 99.8% | 0.2% | 0.0% |
| `FSQ_Global_Asia_Pacific.csv` | `Phone` | 118,299 | 118,299 | 117,810 | **99.59%** | 99.2% | 0.3% | 0.5% |
| `FSQ_Global_Europe.csv` | `Phone` | 254,294 | 254,294 | 254,073 | **99.91%** | 99.1% | 0.7% | 0.2% |
| `FSQ_Global_Latin_America_Caribbean.csv` | `Phone` | 88,046 | 88,046 | 87,798 | **99.72%** | 98.3% | 1.3% | 0.4% |
| `FSQ_Global_Middle_East_Africa.csv` | `Phone` | 100,433 | 100,433 | 99,831 | **99.40%** | 97.5% | 1.8% | 0.7% |
| `FSQ_Global_North_America.csv` | `Phone` | 27,850 | 27,850 | 27,824 | **99.91%** | 99.8% | 0.1% | 0.1% |
| `Overture_Global_Americas.csv` | `Phone` | 377,537 | 377,537 | 377,388 | **99.96%** | 98.4% | 1.5% | 0.1% |
| `Overture_Global_Asia_Oceania.csv` | `Phone` | 254,961 | 254,961 | 254,927 | **99.99%** | 98.9% | 1.1% | 0.1% |
| `Overture_Global_Europe_MEA.csv` | `Phone` | 405,752 | 405,752 | 405,640 | **99.97%** | 99.1% | 0.8% | 0.1% |
| `SEC_DTCC_Regulatory_Filings.csv` | `Phone` | 117,233 | 117,233 | 116,975 | **99.78%** | 98.4% | 1.3% | 0.3% |
| `SEC_DTCC_Regulatory_Filings.csv` | `Fax` | 117,233 | 0 | 0 | **0.00%** | 0.0% | 0.0% | 0.0% |
| `Wikidata_Global_Institutions.csv` | `Phone` | 57,543 | 57,476 | 57,330 | **99.75%** | 99.0% | 0.7% | 0.3% |
| `Wikidata_Global_Institutions.csv` | `Fax` | 57,543 | 19,996 | 19,985 | **99.94%** | 99.4% | 0.5% | 0.1% |

## 3. High-Throughput Engine Benchmarking

| Dataset | Phone Column | Single-Record Python | Batch Python | Batch Rust PyO3 | Rust Speedup |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 19,001 rec/s | 59,645 rec/s | **439,286 rec/s** | **7.36x** |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 19,748 rec/s | 70,664 rec/s | **483,527 rec/s** | **6.84x** |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 94,253 rec/s | 94,565 rec/s | **585,599 rec/s** | **6.19x** |
| `FIRMOUTFULL_20261019115038206.txt` | `Phone 1` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `FIRMOUTFULL_20261019115038206.txt` | `Phone 2` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `FIRMOUTFULL_20261019115038206.txt` | `Fax 1` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `FIRMOUTFULL_20261019115038206.txt` | `Fax 2` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `OFFICEOUTFULL_20261019115038206.txt` | `Phone 1` | 24,658 rec/s | 82,999 rec/s | **553,814 rec/s** | **6.67x** |
| `OFFICEOUTFULL_20261019115038206.txt` | `Phone 2` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `OFFICEOUTFULL_20261019115038206.txt` | `Fax 1` | 24,835 rec/s | 88,247 rec/s | **595,200 rec/s** | **6.74x** |
| `OFFICEOUTFULL_20261019115038206.txt` | `Fax 2` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `REPOUTFULL_20261019115038206.txt` | `Business Phone` | 25,963 rec/s | 84,028 rec/s | **556,699 rec/s** | **6.63x** |
| `REPOUTFULL_20261019115038206.txt` | `Home Phone` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `REPOUTFULL_20261019115038206.txt` | `Mobile Phone` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `REPOUTFULL_20261019115038206.txt` | `Fax 1` | 25,000 rec/s | 87,735 rec/s | **600,456 rec/s** | **6.84x** |
| `REPOUTFULL_20261019115038206.txt` | `Fax 2` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `REPOUTFULL_20261019115038206.txt` | `Business Phone 2` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `REPOUTFULL_20261019115038206.txt` | `Assistant Phone` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `BDFirmDataFeedDelta.csv` | `MainOffice_Phone` | 19,840 rec/s | 28,670 rec/s | **261,969 rec/s** | **9.14x** |
| `BDRepDataFeedDelta.csv` | `Branch_Phone` | 42,736 rec/s | 83,945 rec/s | **597,799 rec/s** | **7.12x** |
| `BDRepDataFeedDelta.csv` | `Home_Phone` | 23,325 rec/s | 86,790 rec/s | **597,439 rec/s** | **6.88x** |
| `BDRepDataFeedDelta.csv` | `HQ_Phone` | 151,721 rec/s | 85,585 rec/s | **613,511 rec/s** | **7.17x** |
| `BDFirmDataFeedFull.csv` | `MainOffice_Phone` | 28,964 rec/s | 88,781 rec/s | **622,341 rec/s** | **7.01x** |
| `BDRepDataFeedFull.csv` | `Branch_Phone` | 40,208 rec/s | 86,076 rec/s | **611,340 rec/s** | **7.10x** |
| `BDRepDataFeedFull.csv` | `Home_Phone` | 23,265 rec/s | 85,464 rec/s | **611,873 rec/s** | **7.16x** |
| `BDRepDataFeedFull.csv` | `HQ_Phone` | 283,111 rec/s | 83,718 rec/s | **591,950 rec/s** | **7.07x** |
| `Reps_No_Longer_In_Discovery_Data.csv` | `BranchPhone` | 36,429 rec/s | 83,068 rec/s | **583,159 rec/s** | **7.02x** |
| `Reps_No_Longer_In_Discovery_Data.csv` | `HomePhone` | 21,141 rec/s | 83,663 rec/s | **526,055 rec/s** | **6.29x** |
| `RIAFirmDataFeedDelta.csv` | `MainOffice_Phone` | 23,085 rec/s | 84,044 rec/s | **591,840 rec/s** | **7.04x** |
| `RIAFirmDataFeedDelta.csv` | `MainOffice_Fax` | 23,966 rec/s | 61,386 rec/s | **595,064 rec/s** | **9.69x** |
| `RIARepDataFeedDelta.csv` | `Office_Phone` | 46,877 rec/s | 85,166 rec/s | **615,735 rec/s** | **7.23x** |
| `RIARepDataFeedDelta.csv` | `Home_Phone` | 23,558 rec/s | 78,587 rec/s | **540,159 rec/s** | **6.87x** |
| `RIARepDataFeedDelta.csv` | `HQ_Phone` | 84,899 rec/s | 77,346 rec/s | **645,148 rec/s** | **8.34x** |
| `RIAFirmDataFeedFull.csv` | `MainOffice_Phone` | 23,730 rec/s | 89,427 rec/s | **558,061 rec/s** | **6.24x** |
| `RIAFirmDataFeedFull.csv` | `MainOffice_Fax` | 24,591 rec/s | 89,428 rec/s | **620,826 rec/s** | **6.94x** |
| `RIARepDataFeedFull.csv` | `Office_Phone` | 57,860 rec/s | 87,728 rec/s | **544,782 rec/s** | **6.21x** |
| `RIARepDataFeedFull.csv` | `Home_Phone` | 24,472 rec/s | 79,374 rec/s | **563,040 rec/s** | **7.09x** |
| `RIARepDataFeedFull.csv` | `HQ_Phone` | 128,088 rec/s | 86,861 rec/s | **601,441 rec/s** | **6.92x** |
| `FSQ_Global_Asia_Pacific.csv` | `Phone` | 23,943 rec/s | 81,816 rec/s | **570,976 rec/s** | **6.98x** |
| `FSQ_Global_Europe.csv` | `Phone` | 19,820 rec/s | 69,921 rec/s | **504,396 rec/s** | **7.21x** |
| `FSQ_Global_Latin_America_Caribbean.csv` | `Phone` | 23,856 rec/s | 83,074 rec/s | **627,549 rec/s** | **7.55x** |
| `FSQ_Global_Middle_East_Africa.csv` | `Phone` | 24,337 rec/s | 84,491 rec/s | **563,658 rec/s** | **6.67x** |
| `FSQ_Global_North_America.csv` | `Phone` | 24,518 rec/s | 74,150 rec/s | **605,406 rec/s** | **8.16x** |
| `Overture_Global_Americas.csv` | `Phone` | 15,514 rec/s | 82,829 rec/s | **572,002 rec/s** | **6.91x** |
| `Overture_Global_Asia_Oceania.csv` | `Phone` | 15,133 rec/s | 88,362 rec/s | **609,180 rec/s** | **6.89x** |
| `Overture_Global_Europe_MEA.csv` | `Phone` | 17,530 rec/s | 88,665 rec/s | **581,183 rec/s** | **6.55x** |
| `SEC_DTCC_Regulatory_Filings.csv` | `Phone` | 28,437 rec/s | 87,189 rec/s | **588,252 rec/s** | **6.75x** |
| `SEC_DTCC_Regulatory_Filings.csv` | `Fax` | 0 rec/s | 0 rec/s | **0 rec/s** | **0.00x** |
| `Wikidata_Global_Institutions.csv` | `Phone` | 14,474 rec/s | 71,165 rec/s | **572,177 rec/s** | **8.04x** |
| `Wikidata_Global_Institutions.csv` | `Fax` | 14,698 rec/s | 73,029 rec/s | **580,525 rec/s** | **7.95x** |

## 4. Rust SIMD vs. Python Batch Parity Verification

| Dataset | Column | Records Evaluated | Exact Parity Matches | Parity Rate | Divergences |
|---|---|---|---|---|---|
| `AdvizorPro_Firm_20261019.csv` | `Phone` | 46,511 | 46,511 | 100.0000% | PASS (100.00%) |
| `AdvizorPro_Person_20261019.csv` | `Phone` | 559,943 | 559,943 | 100.0000% | PASS (100.00%) |
| `AdvizorPro_Person_20261019.csv` | `Firm Phone` | 803,661 | 803,661 | 100.0000% | PASS (100.00%) |
| `FIRMOUTFULL_20261019115038206.txt` | `Phone 1` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `FIRMOUTFULL_20261019115038206.txt` | `Phone 2` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `FIRMOUTFULL_20261019115038206.txt` | `Fax 1` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `FIRMOUTFULL_20261019115038206.txt` | `Fax 2` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `OFFICEOUTFULL_20261019115038206.txt` | `Phone 1` | 30,038 | 30,038 | 100.0000% | PASS (100.00%) |
| `OFFICEOUTFULL_20261019115038206.txt` | `Phone 2` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `OFFICEOUTFULL_20261019115038206.txt` | `Fax 1` | 23,209 | 23,209 | 100.0000% | PASS (100.00%) |
| `OFFICEOUTFULL_20261019115038206.txt` | `Fax 2` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `REPOUTFULL_20261019115038206.txt` | `Business Phone` | 169,552 | 169,552 | 100.0000% | PASS (100.00%) |
| `REPOUTFULL_20261019115038206.txt` | `Home Phone` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `REPOUTFULL_20261019115038206.txt` | `Mobile Phone` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `REPOUTFULL_20261019115038206.txt` | `Fax 1` | 14,957 | 14,957 | 100.0000% | PASS (100.00%) |
| `REPOUTFULL_20261019115038206.txt` | `Fax 2` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `REPOUTFULL_20261019115038206.txt` | `Business Phone 2` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `REPOUTFULL_20261019115038206.txt` | `Assistant Phone` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `BDFirmDataFeedDelta.csv` | `MainOffice_Phone` | 24 | 24 | 100.0000% | PASS (100.00%) |
| `BDRepDataFeedDelta.csv` | `Branch_Phone` | 15,301 | 15,301 | 100.0000% | PASS (100.00%) |
| `BDRepDataFeedDelta.csv` | `Home_Phone` | 2,930 | 2,930 | 100.0000% | PASS (100.00%) |
| `BDRepDataFeedDelta.csv` | `HQ_Phone` | 14,309 | 14,309 | 100.0000% | PASS (100.00%) |
| `BDFirmDataFeedFull.csv` | `MainOffice_Phone` | 3,026 | 3,026 | 100.0000% | PASS (100.00%) |
| `BDRepDataFeedFull.csv` | `Branch_Phone` | 644,931 | 644,931 | 100.0000% | PASS (100.00%) |
| `BDRepDataFeedFull.csv` | `Home_Phone` | 148,105 | 148,105 | 100.0000% | PASS (100.00%) |
| `BDRepDataFeedFull.csv` | `HQ_Phone` | 634,262 | 634,262 | 100.0000% | PASS (100.00%) |
| `Reps_No_Longer_In_Discovery_Data.csv` | `BranchPhone` | 433,637 | 433,637 | 100.0000% | PASS (100.00%) |
| `Reps_No_Longer_In_Discovery_Data.csv` | `HomePhone` | 54,726 | 54,726 | 100.0000% | PASS (100.00%) |
| `RIAFirmDataFeedDelta.csv` | `MainOffice_Phone` | 1,194 | 1,194 | 100.0000% | PASS (100.00%) |
| `RIAFirmDataFeedDelta.csv` | `MainOffice_Fax` | 540 | 540 | 100.0000% | PASS (100.00%) |
| `RIARepDataFeedDelta.csv` | `Office_Phone` | 13,135 | 13,135 | 100.0000% | PASS (100.00%) |
| `RIARepDataFeedDelta.csv` | `Home_Phone` | 3,173 | 3,173 | 100.0000% | PASS (100.00%) |
| `RIARepDataFeedDelta.csv` | `HQ_Phone` | 13,130 | 13,130 | 100.0000% | PASS (100.00%) |
| `RIAFirmDataFeedFull.csv` | `MainOffice_Phone` | 43,666 | 43,666 | 100.0000% | PASS (100.00%) |
| `RIAFirmDataFeedFull.csv` | `MainOffice_Fax` | 20,026 | 20,026 | 100.0000% | PASS (100.00%) |
| `RIARepDataFeedFull.csv` | `Office_Phone` | 513,420 | 513,420 | 100.0000% | PASS (100.00%) |
| `RIARepDataFeedFull.csv` | `Home_Phone` | 129,000 | 129,000 | 100.0000% | PASS (100.00%) |
| `RIARepDataFeedFull.csv` | `HQ_Phone` | 513,334 | 513,334 | 100.0000% | PASS (100.00%) |
| `FSQ_Global_Asia_Pacific.csv` | `Phone` | 118,299 | 118,299 | 100.0000% | PASS (100.00%) |
| `FSQ_Global_Europe.csv` | `Phone` | 254,294 | 254,294 | 100.0000% | PASS (100.00%) |
| `FSQ_Global_Latin_America_Caribbean.csv` | `Phone` | 88,046 | 88,046 | 100.0000% | PASS (100.00%) |
| `FSQ_Global_Middle_East_Africa.csv` | `Phone` | 100,433 | 100,433 | 100.0000% | PASS (100.00%) |
| `FSQ_Global_North_America.csv` | `Phone` | 27,850 | 27,850 | 100.0000% | PASS (100.00%) |
| `Overture_Global_Americas.csv` | `Phone` | 377,537 | 377,537 | 100.0000% | PASS (100.00%) |
| `Overture_Global_Asia_Oceania.csv` | `Phone` | 254,961 | 254,961 | 100.0000% | PASS (100.00%) |
| `Overture_Global_Europe_MEA.csv` | `Phone` | 405,752 | 405,752 | 100.0000% | PASS (100.00%) |
| `SEC_DTCC_Regulatory_Filings.csv` | `Phone` | 117,233 | 117,233 | 100.0000% | PASS (100.00%) |
| `SEC_DTCC_Regulatory_Filings.csv` | `Fax` | 0 | 0 | 100.0000% | PASS (100.00%) |
| `Wikidata_Global_Institutions.csv` | `Phone` | 57,476 | 57,476 | 100.0000% | PASS (100.00%) |
| `Wikidata_Global_Institutions.csv` | `Fax` | 19,996 | 19,996 | 100.0000% | PASS (100.00%) |

## 5. Actionable Failure Taxonomy & Engine Remediation Gaps

| Failure Code | Total Count | Classification | Concrete Sample Inputs | Engine Remediation Opportunity |
|---|---|---|---|---|
| `ACTIONABLE_DIAL_PLAN_OR_METADATA_GAP` | 1,619 | Actionable Telephony Gap | `011417189030`<br>`+40 20 7072 3100`<br>`1762199943`<br>`3058980672` | Synchronize national dialing plans with upstream ITU / libphonenumber XML metadata. |
| `ACTIONABLE_LOCAL_NANP_7_DIGIT` | 214 | Actionable Telephony Gap | `735-8882`<br>`7358882`<br>`6644000`<br>`6641370` | Leverage postal code and state context in `infer_country_from_postal_code` to infer NPA for 7-digit local subscriber numbers. |
| `ACTIONABLE_COUNTRY_OR_TRUNK_GAP` | 47 | Actionable Telephony Gap | `0284597439`<br>`01244539595`<br>`0862385503`<br>`0870783000` | Improve country code inference from address context or postal code when leading domestic trunk '0' is encountered. |
| `ACTIONABLE_VANITY_GAP` | 27 | Actionable Telephony Gap | `816-753-729 EXT 8857`<br>`+1-450-346-606-;ext=2950` | Expand keypad vanity decoding to handle unhyphenated words, numeric-word mixtures, and international vanity numbers. |

## 6. Genuinely Unparseable Garbage & Non-Telephony Placeholders

| Garbage Code | Total Count | Taxonomy Description | Sample Values |
|---|---|---|---|
| `GARBAGE_INSUFFICIENT_DIGITS` | 468 | Fewer than 7 digits without emergency or short-code classification | `815-281`<br>`701`<br>`507645`<br>`1877` |
| `GARBAGE_EXCESSIVE_DIGITS` | 302 | Excessive digits (> 15) exceeding ITU-T E.164 maximum capacity | `0044 0207 76286000`<br>`358501282,358968178982`<br>`5555555555,9168061248`<br>`80021468374087471222` |
| `GARBAGE_TEXT_PLACEHOLDER` | 174 | Non-telephony text placeholder, null representation, or empty string | `NULL`<br>`0`<br>`-`<br>`none` |
| `GARBAGE_ALL_ZEROS_OR_ONES` | 69 | All identical repeated placeholder digits (e.g. 000-000-0000, 999-999-9999) | `0000000000`<br>`00000000`<br>`555-555-5555`<br>`000-000-0000` |
| `GARBAGE_SEQUENTIAL_OR_TEST` | 45 | Ascending or descending sequential test pattern | `5551234567`<br>`1234567890`<br>`8601234567`<br>`7601234567` |
| `GARBAGE_TIME_OR_DATE` | 2 | Operating hours or timestamp range accidentally populated into phone field | `8:00AM - 6:00PM` |
