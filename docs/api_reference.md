# Complete API Reference 📖

This document specifies the public Python API, dataclasses, CLI subcommands, FastAPI HTTP microservice endpoints, Model Context Protocol (MCP) tools, and Apache Arrow / Polars / DuckDB integrations for **Entity Standardizer** (`entity_standardizer`, `address_standardizer`, and `phone_standardizer` `v2.1.0`).

---

## 1. Core Data Models

### 1.1 Joint Contact & Multi-Pillar Models (`phone_standardizer.joint`, `phone_standardizer.dedup`)

#### `StandardizedContact` (alias: `StandardizedEntity`)
- `address: StandardizedAddress` — Standardized USPS Pub 28 / UPU S42 address record.
- `phone: StandardizedPhone` — Standardized primary telephone record.
- `fax: StandardizedPhone | None` — Standardized fax telephone record (if provided).
- `organization: StandardizedCompany | None` — Standardized company/organization record.
- `person: StandardizedPerson | None` — Standardized contact person record.
- `job_title: StandardizedJobTitle | None` — Standardized job title record.
- `email: StandardizedEmail | None` — Standardized email address record.
- `website: StandardizedUrl | None` — Standardized website URL record.
- `social: StandardizedSocial | None` — Standardized social profile record.
- `entity_key: str | None` — Composite multi-pillar deterministic entity key.
- `cross_healing_actions: list[str]` — Ordered list of `CrossHealingAction` values applied across pillars.
- `overall_confidence: float` — Composite multi-pillar confidence score (`0.0` to `1.0`).

#### `CrossHealingAction`
- `PHONE_RESCUED_FROM_ADDRESS_FIELD`
- `EMAIL_RESCUED_FROM_FIELD`
- `URL_RESCUED_FROM_FIELD`
- `ORGANIZATION_RESCUED_FROM_PERSON_FIELD`
- `PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF`
- `ORGANIZATION_INFERRED_FROM_DOMAIN`
- `EMAIL_WEBSITE_DOMAIN_MATCH`
- `EMAIL_WEBSITE_DOMAIN_MISMATCH`
- `COUNTRY_INFERRED_FROM_ENTITY_PILLARS`
- `ADDRESS_COUNTRY_INFERRED_FROM_PHONE`
- `ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA`
- `PHONE_HEALED_FROM_STANDARDIZED_ADDRESS`

#### `ContactComparisonResult`
- `is_match: bool` — Whether the two contact records represent the same entity/contact.
- `score: float` — Composite similarity score (`0.0` to `1.0`).
- `match_type: str` — `"MULTI_PILLAR_MATCH"`, `"SINGLE_PILLAR_<PILLAR>_MATCH"`, `"PERSON_GENERATIONAL_CONFLICT"`, `"NO_MATCH"`, or `"INSUFFICIENT_PILLARS"`.
- `matched_pillars: list[str]` — Pillars that matched (`"organization"`, `"person"`, `"phone"`, `"email"`, `"website"`, `"address"`).
- `pillar_scores: dict[str, float]` — Per-pillar comparison scores.
- `contact_a: StandardizedContact`
- `contact_b: StandardizedContact`

#### `ContactCluster`
- `cluster_id: str` — Deterministic cluster identifier (`"ENTITY-0001"`).
- `golden_phone: StandardizedPhone | None` — Highest-survivorship phone record in the cluster.
- `address_keys: tuple[str, ...]` — Distinct normalized address keys in the cluster.
- `records: tuple[dict[str, Any], ...]` — Member contact records.
- `match_reasons: tuple[str, ...]` — Linkage reasons (`"EXACT_PHONE_KEY"`, `"SHARED_ADDRESS_KEY"`, `"SHARED_COMPANY_KEY"`, `"SHARED_PERSON_KEY"`, `"SHARED_EMAIL_KEY"`, `"SHARED_DOMAIN_KEY"`, `"FUZZY_PHONE_MATCH"`, `"SINGLETON"`).

---

### 1.2 Organization / Company Models (`entity_standardizer.company`)

#### `StandardizedCompany` (alias: `StandardizedOrganization`)
- `raw_input: str` — Original unmodified company string.
- `legal_name: str | None` — Canonical uppercase legal name (`"BLACKROCK INC"`, `"KKR OPPORTUNITIES III SARL"`).
- `base_name: str | None` — Core name stripped of legal suffix, leading article, DBA/FKA, and branch unit (`"BLACKROCK"`).
- `brand_stem: str | None` — Core brand stem stripped of trailing corporate noise words (`HOLDINGS`, `GROUP`, `PARTNERS`, `CAPITAL`, `MANAGEMENT`, `ADVISORS`, etc.).
- `legal_suffix: str | None` — Canonical ISO 20275 ELF suffix (`"LLC"`, `"INC"`, `"CORP"`, `"LP"`, `"LLP"`, `"LLLP"`, `"PC"`, `"PLLC"`, `"PA"`, `"NA"`, `"FSB"`, `"PLC"`, `"LTD"`, `"ULC"`, `"GMBH"`, `"AG"`, `"KG"`, `"KGAA"`, `"SE"`, `"SARL"`, `"SAS"`, `"SA"`, `"SCSP"`, `"SPC"`, `"DST"`, `"REIT"`, `"TRUST"`, `"SRL"`, `"SPA"`, `"BV"`, `"NV"`, `"AB"`, `"ASA"`, `"AS"`, `"OY"`, `"APS"`, `"KK"`, `"PTY LTD"`, `"PTE LTD"`, `"PVT LTD"`, `"SDN BHD"`, `"BHD"`, `"SP Z OO"`, `"KFT"`, `"SRO"`, `"DOO"`, `"OU"`, `"SA DE CV"`, `"LTDA"`, `"FOUNDATION"`, `"ASSN"`).
- `dba_name: str | None` — Extracted Doing-Business-As / Trading-As / parenthesized acronym alias (`"PIMCO"`).
- `fka_name: str | None` — Extracted Formerly-Known-As name.
- `branch_unit: str | None` — Extracted division, branch, Series (`"SERIES A"`), Segregated Portfolio (`"SEGREGATED PORTFOLIO 1"`), or institutional role qualifier (`"PROGRAM MANAGER"`).
- `inferred_country_iso2: str | None` — ISO-3166-1 alpha-2 country code inferred from unambiguous legal form or SEC `/DE/` suffix.
- `company_key: str | None` — Deterministic entity key (`"<base_name>|<legal_suffix>"`).
- `brand_key: str | None` — Deterministic brand stem key.
- `phonetic_key: str | None` — American Soundex phonetic key of `brand_stem`.
- `is_valid: bool`
- `confidence: float`
- `healing_actions: list[str]` — `"SEC_STATE_SUFFIX_STRIPPED"`, `"DBA_EXTRACTED"`, `"FKA_EXTRACTED"`, `"BRANCH_UNIT_EXTRACTED"`, `"AMPERSAND_NORMALIZED"`, `"INITIALISM_COLLAPSED"`, `"LEADING_ARTICLE_STRIPPED"`, `"LEGAL_SUFFIX_NORMALIZED"`.

#### `CompanyComparisonResult` & `CompanyCluster`
- `CompanyComparisonResult`: `is_match: bool`, `score: float`, `match_type: str` (`"EXACT_COMPANY_KEY"`, `"BASE_NAME_MATCH"`, `"ALIAS_MATCH"`, `"BRAND_STEM_MATCH"`, `"PHONETIC_FUZZY_MATCH"`, `"NO_MATCH"`, `"INVALID_INPUT"`), `company_a: StandardizedCompany`, `company_b: StandardizedCompany`.
- `CompanyCluster`: `cluster_id: str`, `golden_company: StandardizedCompany`, `members: tuple[StandardizedCompany, ...]`, `raw_inputs: tuple[str, ...]`, `match_types: tuple[str, ...]`.

---

### 1.3 Person & Job Title Models (`entity_standardizer.person`)

#### `StandardizedPerson`
- `raw_input: str`
- `full_name: str | None` — Canonical `"FIRST MIDDLE LAST SUFFIX"` string.
- `salutation: str | None` — Canonical salutation (`"DR"`, `"MR"`, `"MRS"`, `"MS"`, `"PROF"`, `"REV"`, `"HON"`, etc.).
- `first_name: str | None` — Given name (`"BOB"`, `"JOSE"`).
- `root_first_name: str | None` — Formal root given name resolved from diminutives (`"ROBERT"` for `"BOB"`).
- `middle_name: str | None`
- `last_name: str | None` — Surname including compound particles (`"VAN DER BEEK"`).
- `nickname: str | None` — Extracted quoted or parenthesized nickname.
- `generational_suffix: str | None` — `"JR"`, `"SR"`, `"II"`, `"III"`, `"IV"`, `"V"`.
- `credentials: list[str]` — Extracted post-nominal credentials (`"MD"`, `"PHD"`, `"JD"`, `"CPA"`, `"CFA"`, `"CFP"`, `"CHFC"`, `"CLU"`, `"CIMA"`, `"CAIA"`, `"FRM"`, `"EA"`, `"Series 7"`, etc.).
- `person_key: str | None` — `"<last_name>|<first_name>|<middle_initial>|<generational_suffix>"`.
- `person_root_key: str | None` — `"<last_name>|<root_first_name>"`.
- `phonetic_key: str | None` — Soundex phonetic key (`"<last_soundex>|<root_first_soundex>"`).
- `is_organization: bool` — `True` when a corporate/fund/trust name was detected in the person field.
- `is_valid: bool`
- `confidence: float`
- `healing_actions: list[str]` — `"DIACRITICS_FOLDED"`, `"PLACEHOLDER_STRIPPED"`, `"COMPOUND_PERSON_SPLIT"`, `"ORGANIZATION_DETECTED_IN_PERSON_FIELD"`, `"NICKNAME_EXTRACTED"`, `"CREDENTIALS_EXTRACTED"`, `"LAST_FIRST_UNINVERTED"`, `"SALUTATION_EXTRACTED"`, `"GENERATIONAL_SUFFIX_EXTRACTED"`, `"NICKNAME_RESOLVED_TO_ROOT"`.

#### `StandardizedJobTitle`
- `raw_input: str`
- `normalized_title: str | None` — Expanded canonical uppercase job title (`"CHIEF COMPLIANCE OFFICER"`).
- `seniority_level: str | None` — `"C_SUITE"`, `"OWNER_PARTNER"`, `"VP"`, `"DIRECTOR"`, `"MANAGER"`, `"SENIOR"`, `"ENTRY"`, or `"INDIVIDUAL_CONTRIBUTOR"`.
- `department: str | None` — `"ENGINEERING"`, `"FINANCE"`, `"MARKETING"`, `"SALES"`, `"OPERATIONS"`, `"LEGAL"`, `"HR"`, `"EXECUTIVE"`, or `"GENERAL"`.
- `is_executive: bool` — `True` for C-Suite, Owner/Partner, VP, Director, Trustee, Principal, and Executive Officer roles.
- `is_valid: bool`
- `confidence: float`
- `healing_actions: list[str]` — `"JSON_ARRAY_UNPACKED"`, `"TITLE_ABBREVIATION_EXPANDED"`.

#### `PersonComparisonResult` & `PersonCluster`
- `PersonComparisonResult`: `is_match: bool`, `score: float`, `match_type: str` (`"EXACT_PERSON_KEY"`, `"ROOT_NAME_MATCH"`, `"INITIAL_AND_LAST_MATCH"`, `"PHONETIC_FUZZY_MATCH"`, `"GENERATIONAL_SUFFIX_CONFLICT"`, `"NO_MATCH"`, `"INVALID_INPUT"`), `person_a: StandardizedPerson`, `person_b: StandardizedPerson`.
- `PersonCluster`: `cluster_id: str`, `golden_person: StandardizedPerson`, `members: tuple[StandardizedPerson, ...]`, `raw_inputs: tuple[str, ...]`, `match_types: tuple[str, ...]`.

---

### 1.4 Email, Website URL & Social Models (`entity_standardizer.web`)

#### `StandardizedEmail`
- `raw_input: str`
- `email: str | None` — Canonical `local@domain` (subaddress stripped, Gmail dots folded, domain typo healed).
- `local_part: str | None`, `raw_local_part: str | None`, `subaddress: str | None`, `domain: str | None`, `display_name: str | None`
- `email_type: str | None` — `"CORPORATE"`, `"FREE_WEBMAIL"`, `"ROLE_ACCOUNT"`, `"DISPOSABLE"`, or `None` when invalid.
- `is_free_provider: bool`, `is_role_account: bool`, `is_disposable: bool`
- `inferred_country_iso2: str | None`
- `email_key: str | None`
- `is_valid: bool`, `confidence: float`, `healing_actions: list[str]` (`"DISPLAY_NAME_EXTRACTED"`, `"MAILTO_PREFIX_STRIPPED"`, `"IDNA_PUNYCODE_NORMALIZED"`, `"DOMAIN_TYPO_HEALED"`, `"GMAIL_DOMAIN_CANONICALIZED"`, `"SUBADDRESS_EXTRACTED"`, `"GMAIL_DOTS_CANONICALIZED"`).

#### `StandardizedUrl` (alias: `StandardizedWebsite`) & `StandardizedSocial`
- `StandardizedUrl`: `raw_input`, `url`, `scheme`, `host`, `domain` (eTLD+1), `subdomain`, `public_suffix`, `brand_stem`, `path`, `inferred_country_iso2`, `url_key`, `is_valid`, `confidence`, `healing_actions` (`"SCHEME_ADDED"`, `"SCHEME_UPGRADED_HTTPS"`, `"IDNA_PUNYCODE_NORMALIZED"`, `"WWW_STRIPPED"`, `"TRACKING_PARAMS_STRIPPED"`).
- `StandardizedSocial`: `raw_input`, `platform` (`"LINKEDIN"`, `"X"`, `"GITHUB"`, `"INSTAGRAM"`, `"FACEBOOK"`, `"YOUTUBE"`), `handle`, `profile_type`, `url`, `social_key`, `is_valid`, `confidence`, `healing_actions` (`"WWW_STRIPPED"`, `"TWITTER_CANONICALIZED_TO_X"`, `"HANDLE_EXPANDED_TO_URL"`).
- `EmailComparisonResult` & `UrlComparisonResult`: Pairwise comparison results returned by `compare_emails()` and `compare_urls()`.

---

### 1.5 Address & Telephone Models (`address_standardizer.models`, `phone_standardizer.models`)

- `StandardizedAddress`: `street1`, `street2`, `city`, `state`, `postal_code`, `country`, `country_iso3`, `normalized_address_key`, `building_key`, `phonetic_key`, `address_status`, `is_us`, `is_private_residence`, `is_registered_agent_hub`, `deliverability`, `latitude`, `longitude`, `precision`, `confidence_score`, `routing_tier`, `rdi`, `cmra`, `vacant`, `dpv_footnotes`, `care_of`, `failure_reason_codes`, `warning_codes`.
- `StandardizedPhone`: `raw_input`, `e164`, `national`, `international`, `rfc3966`, `country_calling_code`, `country_iso2`, `country_iso3`, `country_name`, `national_significant_number`, `area_code`, `subscriber_number`, `extension`, `vanity_alias`, `region_code`, `line_type`, `is_valid`, `is_possible`, `phone_key`, `phone_ext_key`, `confidence`, `routing_tier`, `risk_flags`, `healing_actions`.

---

## 2. Core Python Functions (`entity_standardizer`)

| Category | Functions |
| :--- | :--- |
| **Joint Contact / Entity** | `standardize_contact` (`standardize_entity`), `batch_standardize_contacts` (`batch_standardize_entities`), `compare_contacts` (`compare_entities`), `cluster_contact_records` |
| **Organization / Company** | `standardize_company` (`standardize_organization`), `batch_standardize_companies` (`batch_standardize_organizations`), `compare_companies` (`compare_organizations`), `deduplicate_companies` (`deduplicate_organizations`) |
| **Person & Job Title** | `standardize_person`, `batch_standardize_persons`, `split_compound_persons`, `is_organization_name`, `compare_persons`, `deduplicate_persons`, `standardize_job_title`, `batch_standardize_job_titles` |
| **Web (Email, URL, Social)** | `standardize_email`, `batch_standardize_emails`, `compare_emails`, `standardize_url` (`standardize_website`), `batch_standardize_urls` (`batch_standardize_websites`), `compare_urls` (`compare_websites`), `standardize_social`, `batch_standardize_socials` |
| **Physical Address** | `standardize_address`, `validate_address`, `batch_standardize`, `autocomplete_address`, `generate_normalized_address_key`, `generate_building_key`, `generate_phonetic_address_key` |
| **Telephone** | `standardize_phone`, `validate_phone`, `format_e164`, `format_national`, `format_international`, `format_rfc3966`, `mask_phone`, `explain_phone`, `compare_phones`, `deduplicate_phones`, `batch_standardize_phones` |
| **Arrow, Polars & DuckDB** | `standardize_arrow`, `standardize_polars`, `standardize_companies_arrow`, `standardize_companies_polars`, `standardize_persons_arrow`, `standardize_persons_polars`, `register_duckdb_udfs` |

---

## 3. FastAPI HTTP Microservice Endpoints (`phone_standardizer.server:app`)

| Method & Path | Request Model | Description |
| :--- | :--- | :--- |
| `GET /health` | — | Health and version status probe |
| `POST /v1/contact` | `ContactStandardizeRequest` | Joint 6-pillar contact standardization and cross-healing |
| `POST /v1/contact/compare` | `ContactCompareRequest` | Multi-pillar contact comparison across org, person, phone, email, URL, and address |
| `POST /v1/company` | `CompanyStandardizeRequest` | ISO 20275 company/organization standardization |
| `POST /v1/company/compare` | `CompanyCompareRequest` | Pairwise company entity resolution comparison |
| `POST /v1/person` | `PersonStandardizeRequest` | Person full-name standardization and root-name resolution |
| `POST /v1/person/compare` | `PersonCompareRequest` | Pairwise person entity resolution comparison |
| `POST /v1/job-title` | `JobTitleStandardizeRequest` | Job title expansion, seniority, department, and executive classification |
| `POST /v1/email` | `EmailStandardizeRequest` | RFC 5321/5322 email standardization and typo/sentinel detection |
| `POST /v1/url` | `UrlStandardizeRequest` | Website URL canonicalization and eTLD+1 domain extraction |
| `POST /v1/social` | `SocialStandardizeRequest` | Social profile handle and URL canonicalization |
| `POST /v1/address` | `AddressStandardizeRequest` | USPS Pub 28 / UPU S42 physical address standardization |
| `POST /v1/standardize` | `PhoneStandardizeRequest` | Single telephone number standardization |
| `POST /v1/explain` | `PhoneStandardizeRequest` | Telephony geographic, timezone, carrier, and TCPA diagnostic report |
| `POST /v1/compare` | `PhoneCompareRequest` | Pairwise telephone fuzzy comparison |
| `POST /v1/deduplicate` | `PhoneDeduplicateRequest` | Telephone list clustering into Golden Phone Records |
| `POST /v1/batch` | `PhoneBatchRequest` | Batch telephone standardization (up to 1,000 numbers per call) |
| `GET /v1/countries` & `/v1/countries/{identifier}` | — | List all 249 country dial plans or lookup a specific country |

---

## 4. Model Context Protocol (MCP) Tools (`entity-standardizer-mcp`)

The stdio JSON-RPC 2.0 MCP server (`phone_standardizer.mcp.server`) exposes **17 tools**:
1. `standardize_contact`
2. `compare_contacts`
3. `standardize_company`
4. `compare_companies`
5. `standardize_person`
6. `compare_persons`
7. `standardize_job_title`
8. `standardize_email`
9. `standardize_url`
10. `standardize_social`
11. `standardize_address`
12. `standardize_phone`
13. `explain_phone`
14. `compare_phones`
15. `deduplicate_phones`
16. `mask_phone`
17. `lookup_country_dial_plan`

---

## 5. DuckDB SQL Scalar UDFs (`register_duckdb_udfs`)

Calling `register_duckdb_udfs(con, default_country="US")` registers **12 SQL scalar functions**:
- `standardize_phone_e164(VARCHAR) -> VARCHAR`
- `standardize_phone_national(VARCHAR) -> VARCHAR`
- `standardize_phone_international(VARCHAR) -> VARCHAR`
- `validate_phone_udf(VARCHAR) -> BOOLEAN`
- `mask_phone_udf(VARCHAR) -> VARCHAR`
- `phone_blocking_keys(VARCHAR) -> VARCHAR[]`
- `standardize_company_name(VARCHAR) -> VARCHAR`
- `company_entity_key(VARCHAR) -> VARCHAR`
- `standardize_person_name(VARCHAR) -> VARCHAR`
- `person_entity_key(VARCHAR) -> VARCHAR`
- `standardize_email_udf(VARCHAR) -> VARCHAR`
- `standardize_url_domain(VARCHAR) -> VARCHAR`
