# 5-Minute Quickstart Guide ⚡

Get up and running with **Entity Standardizer** (`entity_standardizer`) in minutes.

---

## 1. Installation

```bash
# Core library
pip install entity-standardizer

# With FastAPI HTTP server, MCP server, and Arrow/Polars/DuckDB extras
pip install "entity-standardizer[server,mcp,arrow]"
```

---

## 2. Joint Multi-Pillar Contact Standardization & Cross-Healing

`standardize_contact()` (aliased as `standardize_entity()`) jointly standardizes address, phone, organization, person, job title, email, website URL, and social profile pillars—automatically rescuing misplaced fields and inferring missing countries or states across pillars:

```python
from entity_standardizer import standardize_contact

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

print(contact.address.street1)          # "350 5TH AVE"
print(contact.address.state)            # "NY"
print(contact.phone.e164)               # "+12125552368"
print(contact.organization.legal_name)  # "ACME HOLDINGS INC"
print(contact.organization.dba_name)    # "ACME CLOUD"
print(contact.person.full_name)         # "BOB J SMITH JR"
print(contact.person.root_first_name)   # "ROBERT"
print(contact.person.person_root_key)   # "SMITH|ROBERT"
print(contact.job_title.is_executive)   # True
print(contact.email.email)              # "bobsmith@gmail.com"
print(contact.website.domain)           # "acme.com"
print(contact.cross_healing_actions)    # ["PHONE_RESCUED_FROM_ADDRESS_FIELD", ...]
```

---

## 3. Organization / Company Standardization, Comparison & Deduplication

```python
from entity_standardizer import (
    compare_companies,
    deduplicate_companies,
    standardize_company,
)

# 1. International & Offshore Legal Forms (ISO 20275 ELF) + Diacritic Folding
lu = standardize_company("KKR Opportunities III S.à r.l.")
print(lu.legal_name)             # "KKR OPPORTUNITIES III SARL"
print(lu.legal_suffix)           # "SARL"
print(lu.inferred_country_iso2)  # "LU"

series = standardize_company("Acme Real Estate LLC - Series A")
print(series.legal_suffix)       # "LLC"
print(series.branch_unit)        # "SERIES A"

# 2. Pairwise Company Comparison (exact key, base name, DBA alias, brand stem, phonetic)
cmp_res = compare_companies("Pacific Investment Management Company (PIMCO)", "PIMCO LLC")
print(cmp_res.is_match, cmp_res.match_type, cmp_res.score)  # True, "ALIAS_MATCH", 0.94

# 3. Company Clustering into Golden Company Records
clusters = deduplicate_companies([
    "BlackRock, Inc.",
    "BLACKROCK INCORPORATED /DE/",
    "BlackRock LLC",
])
print(clusters[0].golden_company.legal_name)  # "BLACKROCK INC"
```

---

## 4. Person Name, Couple Splitting & Job Title Standardization

```python
from entity_standardizer import (
    compare_persons,
    deduplicate_persons,
    split_compound_persons,
    standardize_job_title,
    standardize_person,
)

# 1. Latin Diacritics Folding & Diminutive-to-Root Resolution
p = standardize_person("José María Núñez")
print(p.full_name)        # "JOSE MARIA NUNEZ"

bob = standardize_person("Smith, Dr. Bob J., M.D.")
print(bob.full_name)      # "BOB J SMITH"
print(bob.root_first_name)# "ROBERT"
print(bob.person_root_key)# "SMITH|ROBERT"
print(bob.credentials)    # ["MD"]

# 2. Split Joint/Couple Person Strings
couple = split_compound_persons("Mr. and Mrs. Robert J. Smith")
print([(c.salutation, c.full_name) for c in couple])
# [("MR", "ROBERT J SMITH"), ("MRS", "ROBERT J SMITH")]

# 3. Compare & Deduplicate Persons (with Generational Suffix Conflict Protection)
print(compare_persons("Bob J. Smith", "Robert M. Smith").is_match)          # True
print(compare_persons("Robert J. Smith Jr.", "Robert J. Smith Sr.").is_match)  # False

# 4. Job Title Normalization & Executive Classification
title = standardize_job_title('["CCO", "Director"]')
print(title.normalized_title)  # "CHIEF COMPLIANCE OFFICER AND DIRECTOR"
print(title.seniority_level)   # "C_SUITE"
print(title.is_executive)      # True
```

---

## 5. Email, Website URL & Social Profile Standardization

```python
from entity_standardizer import (
    compare_emails,
    compare_urls,
    standardize_email,
    standardize_social,
    standardize_url,
)

email = standardize_email("Jane.Doe+newsletter@gmial.com")
print(email.email)       # "janedoe@gmail.com"
print(email.email_type)  # "FREE_WEBMAIL"

url = standardize_url("http://www.blackrock.com/us/individual?utm_source=google&gclid=123")
print(url.url)           # "https://blackrock.com/us/individual"
print(url.domain)        # "blackrock.com"
print(url.brand_stem)    # "BLACKROCK"

social = standardize_social("@openai", platform="X")
print(social.url)        # "https://x.com/openai"

print(compare_emails("jdoe@blackrock.com", "jdoe@blackrock.co.uk").is_match)  # True
print(compare_urls("https://stripe.com/docs", "https://dashboard.stripe.com").is_match)  # True
```

---

## 6. Domestic & International Address and Phone Standardization

```python
from entity_standardizer import mask_phone, standardize_address, standardize_phone

# 1. USPS Pub 28 / UPU S42 Address Standardization
addr = standardize_address("1600 Pennsylvania Ave NW", city="Washington", state="DC", postal_code="20500")
print(addr.street1)                 # "1600 PENNSYLVANIA AVE NW"
print(addr.normalized_address_key)  # Deterministic rooftop key

# 2. Messy US Phone Number with Vanity Letters & Extension
res = standardize_phone("Call 1-800-FLOWERS ext. 402!")
print(res.e164)           # "+18003569377"
print(res.national)       # "(800) 356-9377"
print(res.international)  # "+1 800-356-9377"
print(res.rfc3966)        # "tel:+1-800-356-9377;ext=402"
print(res.line_type)      # "TOLL_FREE"

# 3. United Kingdom Number with Redundant (0) Trunk Prefix
uk = standardize_phone("+44 (0) 20 7946 0912")
print(uk.e164)            # "+442079460912"
print(uk.national)        # "020 7946 0912"
print(uk.country_iso2)    # "GB"

# 4. Privacy Masking
print(mask_phone("+1 (415) 555-2671", strategy="partial"))  # "+1******2671"
```

---

## 7. Multi-Pillar Entity Resolution & Columnar Arrow / Polars / DuckDB

```python
import duckdb
from entity_standardizer import cluster_contact_records, compare_contacts
from entity_standardizer.arrow import register_duckdb_udfs

# 1. Pairwise Multi-Pillar Contact Comparison
cmp_c = compare_contacts(
    {"organization": "BlackRock, Inc.", "person_name": "Bob Smith", "phone": "(212) 555-0199"},
    {"organization": "BLACKROCK INCORPORATED /DE/", "person_name": "Robert Smith", "phone": "+12125550199"},
)
print(cmp_c.is_match, cmp_c.matched_pillars)  # True, ['organization', 'person', 'phone']

# 2. Multi-Record 5-Pillar Contact Clustering
clusters = cluster_contact_records([
    {"organization": "Acme LLC", "email": "info@acme.com", "phone": "(415) 555-2671"},
    {"organization": "The Acme L.L.C.", "website": "https://www.acme.com"},
])
print(len(clusters), clusters[0].match_reasons)

# 3. Embedded DuckDB SQL UDFs
con = duckdb.connect(":memory:")
register_duckdb_udfs(con)
print(con.execute("SELECT standardize_company_name('KKR Opportunities III S.à r.l.')").fetchone()[0])
# "KKR OPPORTUNITIES III SARL"
```

---

## 8. Command Line Interface (CLI), FastAPI Server & MCP Server

```bash
# Joint contact standardization
entity-standardizer contact --street1 "350 Fifth Ave" --city "New York" --postal-code "10118" --phone "555-2368" --organization "The Acme Inc."

# Single-pillar CLI commands & pairwise comparisons
entity-standardizer company "KKR Opportunities III S.à r.l."
entity-standardizer compare-companies "BlackRock, Inc." "BLACKROCK INCORPORATED /DE/"
entity-standardizer person "Smith, Dr. Robert J., Jr."
entity-standardizer compare-persons "Bob Smith" "Robert Smith"
entity-standardizer title '["Executive Officer", "Director"]'
entity-standardizer email "Jane.Doe+tag@gmial.com"
entity-standardizer url "https://www.blackrock.com/?utm_source=x"
entity-standardizer social "@openai" --platform X
entity-standardizer address "350 Fifth Ave" --city "New York" --state "NY" --postal-code "10118"
entity-standardizer parse "+44 (0) 20 7946 0912 ext 15"

# Start FastAPI HTTP Microservice
uvicorn entity_standardizer.server:app --host 0.0.0.0 --port 8000

# Start Model Context Protocol (MCP) Server
entity-standardizer-mcp
```
