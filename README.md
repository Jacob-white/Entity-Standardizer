# Entity Standardizer 🏛️📞

[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](https://github.com/Jacob-white/Entity-Standardizer)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/Jacob-white/Entity-Standardizer)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/Jacob-white/Entity-Standardizer)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Standards](https://img.shields.io/badge/Standards-USPS%20Pub%2028%20%7C%20UPU%20S42%20%7C%20ITU--T%20E.164%20%7C%20E.123%20%7C%20RFC%203966%20%7C%20ISO%2020275%20ELF-orange.svg)](https://www.itu.int/rec/T-REC-E.164)

A unified, high-performance multi-national **Entity, Organization, Person, Web, Address, and Telephone Standardization, Bidirectional Cross-Healing, and Multi-Pillar Entity Resolution Engine** (`entity_standardizer`, `address_standardizer`, and `phone_standardizer`) with an optional FastAPI HTTP microservice, Model Context Protocol (MCP) server, Apache Arrow / Polars / DuckDB vectorized integrations, and native Rust PyO3 acceleration. It parses, cleans, cross-heals, validates, compares, and deduplicates organizations (**ISO 20275 ELF**), persons & job titles, emails/URLs/socials (**RFC 5321/5322 / IDNA / eTLD+1**), physical addresses (**USPS Publication 28 / UPU S42 / ISO 19160-4**), and telephone numbers (**ITU-T E.164 / E.123 / RFC 3966 / NANP**) across all **249 ISO-3166-1 countries and territories** without external API fees or vendor lock-in. Owned and maintained by **HobbyHabbit LLC** under the **MIT License**.

---

## 📚 Documentation & Quickstarts

- **[5-Minute Quickstart Guide](docs/quickstart.md)** — Step-by-step onboarding for joint contact cross-healing, company/person/web standardization, address & phone parsing, multi-pillar comparison & deduplication, Arrow/Polars/DuckDB SQL UDFs, CLI, and HTTP service.
- **[Complete API Reference](docs/api_reference.md)** — Full reference for all Python dataclasses, functions, cross-healing enums, CLI commands, 19 HTTP routes (18 `/v1/*` endpoints + `GET /health`), 17 MCP tools, and columnar/SQL UDFs.
- **[AI Agent & MCP Integration Guide](docs/ai_agent_guide.md)** & **[`llms.txt`](llms.txt)** — Model Context Protocol (MCP) setup, 17-tool catalog, autonomous agent decision tree, and token-efficient LLM context index.
- **[Developer Cookbook & Production Recipes](docs/developer_cookbook.md)** — Copy-pasteable recipes for SEC/Form ADV hygiene, couple splitting, multi-pillar deduplication, Polars/Arrow/DuckDB ETL, and TCPA/IRSF anti-fraud guardrails.
- **[Global Telephony Enterprise Blueprint](docs/GLOBAL_TELEPHONY_ARCHITECTURE_PLAN.md)** — Master architectural specification and global dial-plan roadmap.
- **[Global Spatial & Address Enterprise Blueprint](docs/GLOBAL_SPATIAL_ENTERPRISE_BLUEPRINT.md)** — Master architectural specification for USPS Pub 28 / UPU S42 address standardization and offline geocoding.
- **[Multi-Platform Client SDKs](sdks/README.md)** — Client library specifications and examples for TypeScript/React, .NET, and Go.
- **[Security Policy & Anti-Fraud Guide](SECURITY.md)** — Threat model, ReDoS prevention, International Revenue Share Fraud (IRSF) guardrails, sentinel domain rejection, and vulnerability disclosure procedures.
- **[Architectural Specifications Index](docs/README.md)** — Index of all developer guides, engineering blueprints, and operational manuals.

---

## 🌟 Highlights & Enterprise Capabilities

1. **Unified Package Namespace (`entity_standardizer`, `address_standardizer`, `phone_standardizer`)**:
   - Import the entire multi-pillar surface from `entity_standardizer` (`standardize_contact`, `standardize_entity`, `compare_contacts`, `cluster_contact_records`, `standardize_company`, `compare_companies`, `deduplicate_companies`, `standardize_person`, `split_compound_persons`, `compare_persons`, `deduplicate_persons`, `standardize_job_title`, `standardize_email`, `compare_emails`, `standardize_url`, `compare_urls`, `standardize_social`, `standardize_address`, `standardize_phone`, `compare_phones`, `deduplicate_phones`) while preserving 100% backward compatibility for `import address_standardizer` and `import phone_standardizer`.
2. **Multi-Pillar Entity Cross-Healing (`standardize_contact` / `standardize_entity`)**:
   - **Phone, Email, URL & Organization Rescue from Misplaced Fields** (`PHONE_RESCUED_FROM_ADDRESS_FIELD`, `EMAIL_RESCUED_FROM_FIELD`, `URL_RESCUED_FROM_FIELD`, `ORGANIZATION_RESCUED_FROM_PERSON_FIELD`): Extracts misplaced phones, emails, URLs, and corporate entities (`"Augnition Global Investors US GP, LLC"`) from address or person fields before standardization.
   - **Person Rescue & Domain-to-Organization Attribution** (`PERSON_RESCUED_FROM_EMAIL_OR_CARE_OF`, `ORGANIZATION_INFERRED_FROM_DOMAIN`, `EMAIL_WEBSITE_DOMAIN_MATCH` / `MISMATCH`): Infers missing person names from `C/O` lines or email display names/local parts and attributes corporate domains to organization brand stems.
   - **Cross-Pillar Country & State Healing** (`COUNTRY_INFERRED_FROM_ENTITY_PILLARS`, `ADDRESS_COUNTRY_INFERRED_FROM_PHONE`, `ADDRESS_ZIP_STATE_HEALED_FROM_PHONE_NPA`, `PHONE_HEALED_FROM_STANDARDIZED_ADDRESS`): Uses unambiguous ISO 20275 legal suffixes (`GmbH` $\to$ `DE`, `S.à r.l.` / `S.C.Sp.` $\to$ `LU`, `SPC` $\to$ `KY`, `PLC` $\to$ `GB`, `Pty Ltd` $\to$ `AU`), ccTLD domains, E.164 calling codes, and NANP area codes to mutually heal addresses and telephone numbers.
3. **Organization, Person, Job Title, Email, URL & Social Standardization**:
   - **Company/Organization** (`standardize_company`, `compare_companies`, `deduplicate_companies`): ISO 20275 ELF legal suffix canonicalization across 30+ domestic, European, APAC, LATAM, and offshore fund forms (`LLC`, `INC`, `LP`, `LLLP`, `SARL`, `SCSP`, `SPC`, `DST`, `REIT`, `GMBH`, `KGAA`, `AG`, `SE`, `PLC`, `BV`, `NV`, `SP Z OO`, `PTE LTD`, `PVT LTD`, `SDN BHD`, `BHD`, `KFT`, `SRO`, `DOO`, `OU`, `KK`, `SA DE CV`, `LTDA`), Latin diacritic & ligature folding (`S.à r.l.` $\to$ `SARL`, `OÜ` $\to$ `OU`), SEC `/DE/` suffix stripping, trust agreement date guard (`U/A/D`, `F/B/O`), parenthesized acronym alias (`(PIMCO)`) and Series LLC / Segregated Portfolio (`Series A`, `Segregated Portfolio 1`) extraction, and deterministic `company_key` / `brand_key`.
   - **Person & Job Title** (`standardize_person`, `split_compound_persons`, `standardize_job_title`, `compare_persons`, `deduplicate_persons`): Latin diacritics & ligature folding (`José María Núñez` $\to$ `JOSE MARIA NUNEZ`, `Søren`, `Jürgen Weiß`, `Łukasz`), organization-in-person-field guard (`is_organization_name`), placeholder stripping (`N/A`, `[none]`, `---`), joint/couple person splitting (`"Mr. and Mrs. Robert J. Smith"`, `"John & Jane Smith"`), salutation/nickname/compound-surname/suffix/credential parsing, `Last, First` un-inversion, nickname-to-root resolution (`Bob` $\to$ `ROBERT`), JSON role array unpacking (`'["Executive Officer", "Director"]'`), and `seniority_level` / `department` / `is_executive` classification.
   - **Email, Website & Social** (`standardize_email`, `standardize_url`, `standardize_social`, `compare_emails`, `compare_urls`): RFC 5321/5322 normalization, IDNA/Punycode, `+subaddress` and Gmail dot canonicalization, webmail typo healing (`gmial.com` $\to$ `gmail.com`), sentinel/placeholder domain rejection (`example.com`, `none.com`, `test.com`), URL tracking parameter removal (`utm_*`, `fbclid`, `gclid`), eTLD+1 domain extraction, and canonical social handles (`LINKEDIN`, `X`, `GITHUB`, `INSTAGRAM`, `FACEBOOK`, `YOUTUBE`).
4. **USPS Publication 28, UPU S42 & Spatial Rooftop Address Standardization**:
   - Deterministic street suffix/directional/secondary unit normalization, typo recovery, DPV/RDI/CMRA delivery intelligence, registered-agent corporate hub detection, H3 spatial indexing, and deterministic `normalized_address_key`, `building_key`, and `phonetic_key` generation.
5. **Universal 249 ISO-3166-1 Country & ITU-T Dial-Plan Registry**:
   - Deterministic dial-plan metadata (`CountryDialPlan`) for every ISO-3166-1 jurisdiction, producing **ITU-T E.164**, **ITU-T E.123 National**, **ITU-T E.123 International**, and **IETF RFC 3966 URI** formats alongside NANP 25-country / 50-state attribution.
6. **Multi-Pillar Entity Resolution & Modern Data Stack**:
   - Compares and clusters multi-pillar records (`compare_contacts`, `cluster_contact_records`, `deduplicate_companies`, `deduplicate_persons`, `deduplicate_phones`), provides `mask_phone()` privacy redaction, lazy-loaded Apache Arrow / Polars (`standardize_arrow`, `standardize_companies_arrow`, `standardize_persons_arrow`) & DuckDB SQL scalar UDFs (`register_duckdb_udfs`), and parity-tested TypeScript/React, Go, and .NET SDKs.

---

## 🚀 Quickstart

```python
from entity_standardizer import (
    compare_companies,
    compare_contacts,
    compare_persons,
    deduplicate_companies,
    mask_phone,
    split_compound_persons,
    standardize_address,
    standardize_company,
    standardize_contact,
    standardize_job_title,
    standardize_person,
    standardize_phone,
)

# 1. Joint Multi-Pillar Contact Standardization & Cross-Healing
contact = standardize_contact(
    street1="350 Fifth Ave Tel: 555-2368",
    city="New York",
    postal_code="10118",
    organization="The Acme Holdings, Inc. /DE/ (DBA Acme Cloud)",
    person_name="Smith, Jr., Dr. Bob J., MD",
    job_title='["SVP of Eng", "Director"]',
    email="Bob.Smith+crm@gmial.com",
    website="http://www.acme.com/?utm_source=linkedin",
)
assert contact.address.street1 == "350 5TH AVE"
assert contact.phone.e164 == "+12125552368"
assert contact.organization.company_key == "ACME HOLDINGS|INC"
assert contact.person.person_root_key == "SMITH|ROBERT"
assert contact.job_title.is_executive is True
assert contact.email.email == "bobsmith@gmail.com"
assert contact.website.domain == "acme.com"

# 2. International & Offshore Company Standardization, Comparison & Deduplication
sarl = standardize_company("KKR Opportunities III S.à r.l.")
assert sarl.legal_name == "KKR OPPORTUNITIES III SARL"
assert sarl.inferred_country_iso2 == "LU"

cmp_co = compare_companies("Pacific Investment Management Company (PIMCO)", "PIMCO LLC")
assert cmp_co.is_match is True and cmp_co.match_type == "ALIAS_MATCH"

clusters = deduplicate_companies(["BlackRock, Inc.", "BLACKROCK INCORPORATED /DE/", "BlackRock LLC"])
assert len(clusters) == 1 and clusters[0].golden_company.legal_name == "BLACKROCK INC"

# 3. Person Diacritics Folding, Couple Splitting & Comparison
p = standardize_person("José María Núñez")
assert p.full_name == "JOSE MARIA NUNEZ"

couple = split_compound_persons("Mr. and Mrs. Robert J. Smith")
assert [c.full_name for c in couple] == ["ROBERT J SMITH", "ROBERT J SMITH"]

assert compare_persons("Bob J. Smith", "Robert M. Smith").is_match is True

# 4. Multi-Pillar Contact Comparison
cmp_contact = compare_contacts(
    {"organization": "Acme Holdings, Inc.", "person_name": "Bob Smith", "phone": "(212) 555-2368"},
    {"organization": "ACME HOLDINGS INC /DE/", "person_name": "Robert Smith", "phone": "+12125552368"},
)
assert cmp_contact.is_match is True and cmp_contact.match_type == "MULTI_PILLAR_MATCH"

# 5. Standalone Address, Vanity Phone & Privacy Masking
addr = standardize_address("1600 Pennsylvania Ave NW", city="Washington", state="DC", postal_code="20500")
assert addr.street1 == "1600 PENNSYLVANIA AVE NW"

rec = standardize_phone("Primary Office: 1-800-FLOWERS ext. 104")
assert rec.e164 == "+18003569377" and rec.rfc3966 == "tel:+1-800-356-9377;ext=104"
assert mask_phone("+1 (415) 555-2671", strategy="partial") == "+1******2671"
```

---

## 💻 Command Line Interface (CLI), FastAPI Microservice & MCP Tools

```bash
# Joint multi-pillar contact standardization
entity-standardizer contact --street1 "350 Fifth Ave" --city "New York" --postal-code "10118" --phone "555-2368" --organization "The Acme Inc." --person-name "Smith, Bob" --email "bob@acme.com"

# Standardize or compare organization, person, job title, email, URL, or social profile
entity-standardizer company "KKR Opportunities III S.à r.l."
entity-standardizer compare-companies "BlackRock, Inc." "BLACKROCK INCORPORATED /DE/"
entity-standardizer person "Dr. Robert (Bob) J. Smith, Jr., MD"
entity-standardizer compare-persons "Bob J. Smith" "Robert M. Smith"
entity-standardizer title '["Executive Officer", "Director"]'
entity-standardizer email "Jane.Doe+tag@gmial.com"
entity-standardizer url "http://www.acme.co.uk/?utm_source=newsletter"
entity-standardizer social "@openai" --platform X

# Standardize a physical address or phone number
entity-standardizer address "350 Fifth Ave" --city "New York" --state "NY" --postal-code "10118"
entity-standardizer parse "+44 (0) 20 7946 0912 ext 42"
entity-standardizer country JP
entity-standardizer batch input.csv output.csv --phone-col phone --country-col country

# Run the FastAPI HTTP service (19 HTTP routes across phone, address, company, person, job-title, email, url, social, contact)
uvicorn phone_standardizer.server:app --host 0.0.0.0 --port 8000

# Run the Model Context Protocol (MCP) server (17 tools across all entity standardization and comparison pillars)
entity-standardizer-mcp
```

---

## 📄 License

Owned and maintained by **HobbyHabbit LLC** under the **[MIT License](LICENSE)**.
