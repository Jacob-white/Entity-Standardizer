# HTTP Microservice Endpoints 🌐

**Entity Standardizer API 2.1.0** (`entity_standardizer.server:app`), OpenAPI 3.1.0.
The machine-readable OpenAPI schema is committed at [`docs/openapi.json`](openapi.json); a running server also serves interactive Swagger UI at `/docs` and ReDoc at `/redoc`.

---

## 1. Unified 6-Pillar Microservice (`entity_standardizer.server:app`)

Start the unified multi-pillar microservice:

```bash
uvicorn entity_standardizer.server:app --host 0.0.0.0 --port 8000
```

### 1.1 Health, Readiness & Country Metadata Endpoints

> **Optional API-Key Authentication**: When `ENTITY_STANDARDIZER_API_KEYS` is set to a comma-separated list of keys, all `/v1/*` routes require `X-API-Key: <key>` or `Authorization: Bearer <key>` (returning `401 Unauthorized` otherwise). `GET /health` and `GET /ready` remain open for orchestrator probes.

#### `GET /health`
Returns service liveness and active package version (`{"status": "ok", "version": "2.1.0"}`).

#### `GET /ready`
Returns service readiness, active package version, and whether the native Rust PyO3 extension is loaded (`{"status": "ready", "version": "2.1.0", "native_available": true}`).

#### `GET /v1/countries`
Returns `{"count": 249, "countries": list[CountryDialPlan]}` containing all **249 ITU-T E.164 country dial plans** sorted by ISO-3166-1 alpha-2 code (`iso2`, `iso3`, `calling_code`, `name`, `region`, `national_trunk_prefix`, `idd_prefix`, `nsn_lengths`, `mobile_prefixes`, `toll_free_prefixes`, `premium_prefixes`, `voip_prefixes`, `shared_cost_prefixes`).

#### `GET /v1/countries/{identifier}`
Looks up a single `CountryDialPlan` by ISO-2 (`"US"`), ISO-3 (`"USA"`), calling code (`"1"` or `"+1"`), or country name. Returns `404` if not found.

---

### 1.2 Joint 6-Pillar Contact Endpoints

#### `POST /v1/contact`
Jointly standardizes and cross-heals a contact record across all 6 entity pillars (**Organization**, **Person & Job Title**, **Email**, **Website & Social**, **Physical Address**, and **Telephone & Fax**).
- **Request body**: `ContactStandardizeRequest`
  - `street1: string | null`, `street2: string | null`, `city: string | null`, `state: string | null`, `postal_code: string | null`, `country: string | null`
  - `phone: string | null`, `fax: string | null`
  - `organization: string | null`
  - `person_name: string | null`
  - `job_title: string | null`
  - `email: string | null`
  - `website: string | null`
  - `social: string | null`
  - `default_country: string` (default `"US"`)
- **Response (`200 OK`)**: `StandardizedContact` (`address`, `phone`, `fax`, `organization`, `person`, `job_title`, `email`, `website`, `social`, `entity_key`, `cross_healing_actions`, `overall_confidence`).

#### `POST /v1/contact/compare`
Compares two multi-pillar contact records (`contact_a` and `contact_b`) across organization, person, phone, email, website, and physical address pillars, enforcing generational suffix conflict protection (`JR` vs `SR`).
- **Request body**: `ContactCompareRequest` (`contact_a: dict`, `contact_b: dict`, `default_country: string = "US"`)
- **Response (`200 OK`)**: `ContactComparisonResult` (`is_match`, `score`, `match_type`, `matched_pillars`, `pillar_scores`, `contact_a`, `contact_b`).

---

### 1.3 Organization / Company Endpoints

#### `POST /v1/company`
Standardizes an organization or company name with ISO 20275 Entity Legal Form (ELF) normalization, SEC `/DE/` suffix stripping, DBA/FKA extraction, Series/SPV/branch extraction, and deterministic key generation.
- **Request body**: `CompanyStandardizeRequest` (`name: string`, `country: string | null = None`)
- **Response (`200 OK`)**: `StandardizedCompany` (`raw_input`, `legal_name`, `base_name`, `brand_stem`, `legal_suffix`, `dba_name`, `fka_name`, `branch_unit`, `inferred_country_iso2`, `company_key`, `brand_key`, `phonetic_key`, `is_valid`, `confidence`, `healing_actions`).

#### `POST /v1/company/compare`
Compares two company/organization names across exact `company_key`, `base_name`, `dba_name`/`fka_name` alias matching, `brand_stem`, and phonetic/token similarity.
- **Request body**: `CompanyCompareRequest` (`company_a: string`, `company_b: string`)
- **Response (`200 OK`)**: `CompanyComparisonResult` (`is_match`, `score`, `match_type`, `company_a`, `company_b`).

---

### 1.4 Person & Job Title Endpoints

#### `POST /v1/person`
Standardizes a person's full name, uninverting `LAST, FIRST`, extracting salutations, generational suffixes, nicknames, and post-nominal credentials, resolving 145+ diminutives to `root_first_name`, and flagging corporate entities in person fields (`is_organization`).
- **Request body**: `PersonStandardizeRequest` (`name: string`)
- **Response (`200 OK`)**: `StandardizedPerson` (`raw_input`, `full_name`, `salutation`, `first_name`, `root_first_name`, `middle_name`, `last_name`, `nickname`, `generational_suffix`, `credentials`, `person_key`, `person_root_key`, `phonetic_key`, `is_organization`, `is_valid`, `confidence`, `healing_actions`).

#### `POST /v1/person/compare`
Compares two person names across exact `person_key`, `person_root_key` (diminutive equivalence), initial + surname matching, and Soundex phonetic similarity, with strict generational conflict rejection (`JR` vs `SR`).
- **Request body**: `PersonCompareRequest` (`person_a: string`, `person_b: string`)
- **Response (`200 OK`)**: `PersonComparisonResult` (`is_match`, `score`, `match_type`, `person_a`, `person_b`).

#### `POST /v1/job-title`
Standardizes a job title, expanding 60+ executive and functional abbreviations (`CCO` -> `CHIEF COMPLIANCE OFFICER`) and classifying `seniority_level`, `department`, and `is_executive`.
- **Request body**: `JobTitleStandardizeRequest` (`title: string`)
- **Response (`200 OK`)**: `StandardizedJobTitle` (`raw_input`, `normalized_title`, `seniority_level`, `department`, `is_executive`, `is_valid`, `confidence`, `healing_actions`).

---

### 1.5 Email, Website URL & Social Profile Endpoints

#### `POST /v1/email`
Standardizes an email address (RFC 5322 display name extraction, `mailto:` stripping, Gmail dot/googlemail folding, `+tag` subaddress extraction, IDNA/punycode decoding, domain typo healing, sentinel rejection, and `CORPORATE` / `FREE_WEBMAIL` / `ROLE_ACCOUNT` / `DISPOSABLE` classification).
- **Request body**: `EmailStandardizeRequest` (`email: string`)
- **Response (`200 OK`)**: `StandardizedEmail` (`raw_input`, `email`, `local_part`, `raw_local_part`, `subaddress`, `domain`, `display_name`, `email_type`, `is_free_provider`, `is_role_account`, `is_disposable`, `inferred_country_iso2`, `email_key`, `is_valid`, `confidence`, `healing_actions`).

#### `POST /v1/url`
Standardizes a website URL (HTTPS upgrade, `www.` stripping, `utm_*`/`gclid`/`fbclid`/`msclkid` tracking parameter removal, multi-part eTLD+1 registrable domain extraction, and `brand_stem` extraction).
- **Request body**: `UrlStandardizeRequest` (`url: string`)
- **Response (`200 OK`)**: `StandardizedUrl` (`raw_input`, `url`, `scheme`, `host`, `domain`, `subdomain`, `public_suffix`, `brand_stem`, `path`, `inferred_country_iso2`, `url_key`, `is_valid`, `confidence`, `healing_actions`).

#### `POST /v1/social`
Standardizes a LinkedIn, X/Twitter, GitHub, Instagram, Facebook, or YouTube URL or `@handle`.
- **Request body**: `SocialStandardizeRequest` (`profile: string`, `platform: string | null = None`)
- **Response (`200 OK`)**: `StandardizedSocial` (`raw_input`, `platform`, `handle`, `profile_type`, `url`, `social_key`, `is_valid`, `confidence`, `healing_actions`).

---

### 1.6 Physical Address Endpoint

#### `POST /v1/address`
Standardizes a US or international physical address to USPS Pub 28 / UPU S42 format with `normalized_address_key`, `building_key`, `phonetic_key`, registered-agent hub detection, and `c/o` Care-Of extraction.
- **Request body**: `AddressStandardizeRequest` (`street1: string = ""`, `street2: string | null = None`, `city: string | null = None`, `state: string | null = None`, `postal_code: string | null = None`, `country: string | null = None`)
- **Response (`200 OK`)**: `StandardizedAddress` dictionary.

---

### 1.7 Telephone Endpoints

#### `POST /v1/standardize`
Standardizes a single telephone number into ITU-T E.164, National, International, and RFC 3966 formats with extension extraction, vanity word translation, and risk scoring.
- **Request body**: `PhoneStandardizeRequest` (`phone: string`, `country: string | null = None`, `default_country: string = "US"`)
- **Response (`200 OK`)**: `StandardizedPhone`.

#### `POST /v1/explain`
Returns a comprehensive diagnostic report for a phone number (`record: StandardizedPhone`, `intelligence: {"locality", "timezones", "carrier_hint", "is_callable_now", "local_hours"}`, `explanation: {"healing_steps_count", "healing_actions", "risk_flags_count", "risk_flags", "confidence", "routing_tier", "requires_human_review"}`).
- **Request body**: `PhoneStandardizeRequest` (`phone: string`, `country: string | null = None`, `default_country: string = "US"`)
- **Response (`200 OK`)**: `PhoneExplainReport` dictionary (`record`, `intelligence`, `explanation`).

#### `POST /v1/compare`
Compares two phone numbers (`phone_a`, `phone_b`) using E.164 equivalence, extension-variant detection, Damerau-Levenshtein transposition analysis, and ITU E.161 keypad-adjacency similarity.
- **Request body**: `PhoneCompareRequest` (`phone_a: string`, `phone_b: string`, `country: string | null = None`, `fuzzy_threshold: float = 0.85`)
- **Response (`200 OK`)**: `PhoneComparisonResult` (`phone_a`, `phone_b`, `is_exact_match`, `is_extension_variant`, `is_fuzzy_match`, `similarity_score`, `match_type`, `edit_distance`, `transposition_detected`, `keypad_adjacent_typo`, `explanation`).

#### `POST /v1/deduplicate`
Clusters and deduplicates a list of raw phone numbers into Golden Phone Records.
- **Request body**: `PhoneDeduplicateRequest` (`phones: list[string]`, `country: string | null = None`, `fuzzy_threshold: float = 0.88`)
- **Response (`200 OK`)**: `{"cluster_count": int, "clusters": list[PhoneCluster]}`.

#### `POST /v1/batch`
Batch-standardizes a list of phone numbers in a single request.
- **Request body**: `PhoneBatchRequest` (`phones: list[string]`, `default_country: string = "US"`)
- **Response (`200 OK`)**: `{"count": int, "results": list[StandardizedPhone]}`.
