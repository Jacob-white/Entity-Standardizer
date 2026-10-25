# Developer Cookbook & Production Recipes 🧑‍🍳

Copy-pasteable, production-ready recipes for solving common data engineering, CRM hygiene, regulatory filing (SEC EDGAR / Form ADV), analytical ETL, and anti-fraud problems with **Entity Standardizer** (`entity_standardizer` `v2.1.0`).

---

## Recipe 1: Cleaning Messy SEC / Form ADV & Institutional Fund Records

Financial and regulatory datasets frequently contain trailing SEC state suffixes (`/DE/`), offshore legal forms with Latin diacritics (`S.à r.l.`, `S.C.Sp.`, `SPC`), Series LLC / Segregated Portfolio designations, JSON-encoded officer title arrays, and corporate GP names accidentally placed in individual person fields.

```python
from entity_standardizer import (
    standardize_company,
    standardize_contact,
    standardize_job_title,
)

# 1. Offshore Luxembourg & Cayman Fund Legal Forms + Series / Portfolio Extraction
lu_fund = standardize_company("KKR Opportunities III S.à r.l.")
assert lu_fund.legal_name == "KKR OPPORTUNITIES III SARL"
assert lu_fund.inferred_country_iso2 == "LU"

ky_spc = standardize_company("Apex Master Fund SPC (Segregated Portfolio 1)")
assert ky_spc.legal_suffix == "SPC"
assert ky_spc.branch_unit == "SEGREGATED PORTFOLIO 1"

# 2. Rescue Corporate GP Name from Person Field + Unpack JSON Role Array
rec = standardize_contact(
    person_name="Augnition Global Investors US GP, LLC",
    job_title='["Executive Officer", "Director"]',
    street1="100 Main St",
    city="New York",
    state="NY",
    postal_code="10001",
)
assert rec.person is None
assert rec.organization.legal_name == "AUGNITION GLOBAL INVESTORS US GP LLC"
assert rec.job_title.normalized_title == "EXECUTIVE OFFICER AND DIRECTOR"
assert rec.job_title.is_executive is True
```

---

## Recipe 2: Splitting Joint / Couple Household & Property Deed Records

Tax rolls, wealth management CRMs, and philanthropic donor databases often store two people in a single name field. Use `split_compound_persons()` to expand them into individual `StandardizedPerson` records:

```python
from entity_standardizer import split_compound_persons

for raw in [
    "Mr. and Mrs. Robert J. Smith",
    "John & Jane Smith",
    "Smith, John & Jane",
    "John Smith & Jane Doe",
]:
    people = split_compound_persons(raw)
    print(raw, "->", [(p.salutation, p.full_name, p.person_root_key) for p in people])
```

---

## Recipe 3: Multi-Pillar Entity Resolution & Golden Record Survivorship

Deduplicate noisy company lists, person lists, or full multi-pillar contact records into deterministic Golden Records:

```python
from entity_standardizer import (
    cluster_contact_records,
    compare_addresses,
    compare_contacts,
    deduplicate_addresses,
    deduplicate_companies,
    deduplicate_persons,
)

# 1. Deduplicate Company Variants (SEC suffix, punctuation, legal form variation)
co_clusters = deduplicate_companies([
    "BlackRock, Inc.",
    "BLACKROCK INCORPORATED /DE/",
    "BlackRock LLC",
    "The Vanguard Group, Inc.",
])
for c in co_clusters:
    print(c.cluster_id, c.golden_company.legal_name, c.match_types)

# 2. Deduplicate Person Variants (Salutation, Credentials, Nickname Root, Initials)
per_clusters = deduplicate_persons([
    "Dr. Robert J. Smith, M.D.",
    "Bob J. Smith",
    "R. Smith",
])
assert len(per_clusters) == 1
assert per_clusters[0].golden_person.full_name == "ROBERT J SMITH"

# 3. Compare & Deduplicate Physical Addresses
addr_clusters = deduplicate_addresses([
    "100 Main St, Boston, MA 02110",
    "100 Main Street, Boston, MA 02110",
])
assert len(addr_clusters) == 1 and addr_clusters[0].golden_address.street1 == "100 MAIN ST"

# 4. 6-Pillar Contact Record Clustering
contact_clusters = cluster_contact_records([
    {"organization": "Pacific Investment Management Company (PIMCO)", "phone": "(949) 555-0140"},
    {"organization": "PIMCO LLC", "email": "inst@pimco.com"},
    {"organization": "PIMCO", "website": "https://www.pimco.com"},
])
assert len(contact_clusters) == 1
```

---

## Recipe 4: High-Throughput Columnar ETL with Polars, Apache Arrow & DuckDB (16 Functions + 15 SQL UDFs)

Process analytical tables and data lakehouse partitions without row-by-row boilerplate:

```python
import duckdb
import polars as pl
from entity_standardizer import (
    register_duckdb_udfs,
    standardize_addresses_polars,
    standardize_companies_polars,
    standardize_persons_polars,
    standardize_polars,
    standardize_socials_polars,
)

# 1. Polars DataFrame Enrichment across Address, Phone, Company, Person, and Social Columns
df = pl.DataFrame({
    "address": ["350 Fifth Ave, New York, NY 10118", "1600 Amphitheatre Pkwy, Mountain View, CA 94043"],
    "company": ["BlackRock, Inc. /DE/", "KKR Opportunities III S.à r.l."],
    "person": ["Smith, Dr. Bob J.", "José María Núñez"],
    "phone": ["(212) 555-0199", "+352 26 12 34 56"],
    "social": ["@blackrock", "@kkr"],
    "country": ["US", "LU"],
})
df = standardize_addresses_polars(df, column="address", country_column="country")
df = standardize_companies_polars(df, company_col="company", country_col="country")
df = standardize_persons_polars(df, person_col="person")
df = standardize_polars(df, phone_col="phone", country_col="country")
df = standardize_socials_polars(df, social_col="social", default_platform="X")
print(df.select(["address_line_1", "company_legal_name", "person_full_name", "phone_e164", "social_url"]))

# 2. DuckDB In-Engine SQL Scalar UDFs (15 scalar functions)
con = duckdb.connect(":memory:")
register_duckdb_udfs(con, default_country="US")
rows = con.execute("""
    SELECT
        standardize_company_name('Allegro.pl Sp. z o.o.') AS legal_name,
        company_entity_key('BlackRock, Inc. /DE/')       AS company_key,
        standardize_person_name('José María Núñez')      AS person_name,
        person_entity_key('Bob J. Smith')                AS person_root_key,
        standardize_email_udf('Jane.Doe+vip@gmial.com')  AS clean_email,
        standardize_url_domain('https://www.stripe.com/docs?utm_source=x') AS domain,
        es_standardize_address('350 Fifth Avenue, New York, NY 10118', 'US') AS rooftop_address,
        es_standardize_social('@openai', 'X')            AS social_url,
        es_standardize_contact_key('350 Fifth Ave, New York, NY 10118', '(212) 555-2368', 'Acme Inc.', 'Bob Smith', 'bob@acme.com') AS contact_key
""").fetchall()
print(rows)
```

---

## Recipe 5: TCPA Safe-Calling Window, IRSF Fraud Blocking & PII Masking

```python
from datetime import datetime, timezone
from entity_standardizer import evaluate_calling_window, explain_phone, mask_phone, standardize_phone

# 1. Block Premium-Rate IRSF & Fictitious Numbers Before Sending SMS OTP
phone = standardize_phone("+1 (900) 555-0199")
if "PREMIUM_RATE_IRSF_RISK" in phone.risk_flags or not phone.is_valid:
    print("Blocked high-risk or invalid number:", phone.risk_flags)

# 2. Check TCPA Local Quiet Hours (08:00 - 21:00 Local Time)
window = evaluate_calling_window(
    "+14155552671",
    utc_now=datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc),
)
print("Safe to call now?", window.is_safe_to_call, "Timezones:", window.timezones)

# 3. Mask PII Before Logging or Exporting to Analytics
print(mask_phone("+1 (415) 555-2671", strategy="partial"))  # "+1******2671"
print(mask_phone("+1 (415) 555-2671", strategy="sha256"))   # Deterministic SHA-256 hex digest
```
