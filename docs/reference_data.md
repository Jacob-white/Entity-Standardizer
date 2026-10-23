# Reference data: validating against authoritative sources

Standardization makes an address *well formed*. It does not tell you the address *exists*. The reference-data layer
(`address_standardizer.reference`) adds an optional, offline check of the postal code, locality and state against a
reference dataset. It is off unless you pass a provider, and then it only adds information: it never changes the
standardized fields.

## What is validated

With the bundled GeoNames provider, `validate_against_reference(std, provider)` checks:

| Check | Rule | Result when it fails |
|---|---|---|
| Postal code exists | The code (or its coarser spelling, see below) is in the reference data for the country | `postal_unknown`, `ERR_POSTAL_UNKNOWN` |
| State (US and Canada only) | The state equals the state code of at least one place for that postal code | `state_mismatch`, `ERR_POSTAL_STATE_MISMATCH` |
| Locality | The city (or dependent locality) plausibly matches the name or county of a place for that postal code: accent/case-insensitive, token-subset and small-edit-distance tolerant (`St` = `Saint`, `Springfeld` ~ `Springfield`) | `place_mismatch`, `WARN_POSTAL_PLACE_MISMATCH` |
| Distance | When the address has coordinates (for example from `enable_geocoding`), the distance in km to the reference centroid is reported | informational only; no code |

`status` is `confirmed` when every check that could run passed, and `not_checked` when there is nothing to check
(no postal code, unrecognised country, or the provider has no data for that country). Absence of data is never
reported as an error. The result lists the `checks` that actually ran, the `matched_place`, the provider's `source`,
`license` and `as_of`, and `candidate_places` when the city did not match.

A postal code can cover several localities and a mailing city is often not the GeoNames place name (a Brooklyn ZIP is
mailed as "New York"), so a locality mismatch is a *warning*, not an error. Treat it as "worth a look".

## What is NOT validated

* That the street or house number exists, or that mail can be delivered to it.
* USPS Delivery Point Validation (DPV), CMRA/RDI/vacancy truth, ZIP+4, carrier route. The `rdi`, `cmra`, `vacant` and
  `dpv_footnotes` fields in this library are heuristics, not USPS data.
* Coordinates beyond postal-code centroids (GeoNames centroids are approximate).
* Postal codes issued after the data snapshot (`as_of`), and countries or regions GeoNames covers poorly.

## Data sources and licenses

| Source | Use | License |
|---|---|---|
| GeoNames postal codes, `https://download.geonames.org/export/zip/` | The bundled `GeoNamesPostalProvider` | CC BY 4.0. **You must credit GeoNames** wherever you publish results or derived data. The index stores the attribution text; `data info` and `provider.info()["attribution"]` return it. |
| US Census Bureau (ZCTA / TIGER, Gazetteer files) | Possible future provider; US ZIP Code Tabulation Areas are not USPS ZIP codes | Public domain (US government work) |
| USPS AIS / Address Matching System data, DPV, ZIP+4, RDI | Authoritative US delivery-point validation | **Licensed.** Available only through the USPS licensing program and CASS-certified software, or a commercial vendor. It cannot be redistributed, so this project ships none of it and simulates none of it. |

### Plugging in a licensed source

`address_standardizer.reference.AuthoritativeDeliveryProvider` is an interface only: one method,
`verify(std_address) -> DeliveryMatch`, where `DeliveryMatch` carries a DPV-style `match_code` (`Y`, `S`, `D`, `N`
by USPS convention) and DPV `footnotes` (`AA`, `BB`, `N1`, ... see `delivery.DPVFootnote`). Write an adapter around
your licensed engine or vendor API and call it yourself; there is no default implementation and none will be added
without data you are licensed to use.

## Build the index

Network access happens only in `data fetch`; everything else is offline.

```bash
# 1. download the zips (ISO alpha-2 codes, or ALL for allCountries.zip, which is large)
address-standardizer data fetch geonames --countries US,CA,GB --out data/geonames

# 2. build the local SQLite index from the downloaded files
address-standardizer data build geonames --from data/geonames --out data/geonames_postal.db

# 3. inspect it (coverage, row count, as_of, license, attribution)
address-standardizer data info data/geonames_postal.db
```

`data build` also accepts files you obtained yourself (`--from` takes a directory or a single `.zip` / `.txt`) and
`--countries` to index a subset of `allCountries.zip`. `as_of` defaults to the build date; pass `--as-of` to record
the snapshot date.

Some countries are stored at a coarser level in GeoNames than a full postal code: Canada (3-character FSA), Great
Britain and Ireland (outward code / routing key), Netherlands (4 digits), and US ZIP+4 (5-digit ZIP). Lookups retry a
full code at those coarser spellings, so `H2X 1Y4` is checked as `H2X`. For these countries "the postal code exists"
means "the area exists", not "the full code exists".

## Use it

```python
from address_standardizer import standardize_address
from address_standardizer.reference import GeoNamesPostalProvider

with GeoNamesPostalProvider("data/geonames_postal.db") as provider:
    std = standardize_address("100 Wall St", city="Chicago", state="NY", postal_code="10005",
                              reference_provider=provider)
print(std.reference_validation.status)        # place_mismatch
print(std.failure_reason_codes)               # [..., "WARN_POSTAL_PLACE_MISMATCH"]
```

* `reference_provider=None` (the default) changes nothing and costs nothing.
* With a provider, `std.reference_validation` is set and its reason codes are appended to `failure_reason_codes`. The
  confidence score and routing tier are **not** changed by reference validation.
* `validate_against_reference(std, provider)` can be called directly on any `StandardizedAddress`.
* `CompositeProvider([a, b])` queries providers in priority order; the first non-empty answer wins.
* To add a provider, implement `ReferenceProvider` (`name`, `source`, `license`, `as_of`, `covers_country`,
  `lookup_postal`, `lookup_place`).

Reason codes (same `WARN_` / `ERR_` convention as `confidence.py`): `ERR_POSTAL_UNKNOWN`, `ERR_POSTAL_STATE_MISMATCH`,
`WARN_POSTAL_PLACE_MISMATCH`. A `reference_validation` also appears in `as_dict(include_metadata=True)`.

### CLI

```bash
address-standardizer parse "100 Wall St, Chicago, NY 10005" --reference-db data/geonames_postal.db --confidence
```

`--reference-db` applies to a single address (not piped input or `batch`).

### REST

Set `ADDRESS_STANDARDIZER_REFERENCE_DB=/path/to/geonames_postal.db` on the server. Each `/v1/standardize` response (and
each `/v1/batch` item) then carries a `reference_validation` object. Without the variable the response is unchanged.
If the file cannot be opened, the object is still returned with `status: "not_checked"` and the reason in `detail`.

## Accuracy limits, honestly

* GeoNames postal data is community-maintained and is not an official postal authority file. Expect gaps (new
  codes), stale entries and uneven quality outside the US, Canada and Western Europe.
* `postal_unknown` means "not in this dataset", which usually, but not always, means the code does not exist.
* Place-name matching is deliberately tolerant. It will accept some wrong cities (a county name equal to the city,
  a near-identical name) and warn on some right ones (a mailing city that differs from the GeoNames place).
* Postal-centroid distances are only meaningful as a gross sanity check (tens of km), not as address precision.
