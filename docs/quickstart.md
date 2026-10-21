# 5-Minute Quickstart Guide ⚡

Get up and running with **Phone Standardizer** (`phone_standardizer`) in minutes.

---

## 1. Installation

```bash
# Zero-dependency core library
pip install phone-standardizer

# With FastAPI HTTP server & MCP server extras
pip install "phone-standardizer[server,mcp]"
```

---

## 2. Domestic & International Phone Standardization

```python
from phone_standardizer import standardize_phone

# 1. Messy US number with vanity letters & extension
res = standardize_phone("Call 1-800-FLOWERS ext. 402!")
print(res.e164)           # "+18003569377"
print(res.national)       # "(800) 356-9377"
print(res.international)  # "+1 800-356-9377"
print(res.rfc3966)        # "tel:+1-800-356-9377;ext=402"
print(res.extension)      # "402"
print(res.vanity_alias)   # "1-800-FLOWERS"
print(res.line_type)      # "TOLL_FREE"

# 2. United Kingdom number with redundant (0) trunk prefix
uk = standardize_phone("+44 (0) 20 7946 0912")
print(uk.e164)            # "+442079460912"
print(uk.national)        # "020 7946 0912"
print(uk.international)   # "+44 20 7946 0912"
print(uk.country_iso2)    # "GB"

# 3. NANP Territory & State Attribution from Area Code
pr = standardize_phone("(787) 555-0244")
print(pr.country_iso2)    # "PR" (Puerto Rico)
print(pr.region_code)     # "PR"

ny = standardize_phone("212.555.0299")
print(ny.country_iso2)    # "US"
print(ny.region_code)     # "NY"
```

---

## 3. Interoperability with `Address-Standardizer`

When a phone number lacks an international `+` prefix, pass country or state hints directly from an address record:

```python
from phone_standardizer import standardize_phone

# Disambiguates national number using country ISO hint
de = standardize_phone("030 12345678", country="DE")
print(de.e164)            # "+493012345678"
print(de.international)   # "+49 30 12345678"
```

---

## 4. Command Line Interface (CLI)

```bash
# Parse a single phone number
phone-standardizer parse "+44 (0) 20 7946 0912 ext 15"

# Lookup country dial plan metadata
phone-standardizer country JP

# Batch standardize a CSV file
phone-standardizer batch input.csv output.csv --phone-col phone --country-col country
```
