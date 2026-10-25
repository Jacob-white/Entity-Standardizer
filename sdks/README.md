# Entity Standardizer — Multi-Platform Client SDKs 🌐

Official client SDKs (`v2.1.0`) and OpenAPI 3.1 contracts for integrating the **Entity Standardizer** HTTP microservice (`entity_standardizer.server:app`) and browser-side React `<PhoneInput />` component across polyglot enterprise stacks:

- **[TypeScript / React (`sdks/typescript`)](typescript/README.md)** — Typed client (`@entity-standardizer/client`), offline `formatAsYouType` formatter, and headless `PhoneInputController` / `usePhoneInput()` React hook.
- **[.NET 8 / C# (`sdks/dotnet`)](dotnet/README.md)** — `EntityStandardizer.Client` (`EntityStandardizer.Client.csproj`) targeting `net8.0` and `netstandard2.0`.
- **[Go (`sdks/go`)](go/README.md)** — Zero-dependency `entitystandardizer` client package (`github.com/Jacob-white/Entity-Standardizer/sdks/go`).

---

## Method Parity Matrix Across All SDKs

Every SDK is continuously contract-tested against the Python dataclasses via [`tests/test_sdk_contract.py`](../tests/test_sdk_contract.py) and supports all **19 HTTP operations** (`GET /health` + 18 `/v1/*` endpoints):

| HTTP Endpoint | TypeScript (`@entity-standardizer/client`) | Go (`entitystandardizer`) | .NET (`EntityStandardizer.Client`) |
| :--- | :--- | :--- | :--- |
| `GET /health` | `health()` | `Health(ctx)` | `HealthAsync(ct)` |
| `POST /v1/contact` | `standardizeContact(req)` | `StandardizeContact(ctx, req)` | `StandardizeContactAsync(req, ct)` |
| `POST /v1/contact/compare` | `compareContacts(req)` | `CompareContacts(ctx, req)` | `CompareContactsAsync(req, ct)` |
| `POST /v1/company` | `standardizeCompany(req)` | `StandardizeCompany(ctx, req)` | `StandardizeCompanyAsync(req, ct)` |
| `POST /v1/company/compare` | `compareCompanies(req)` | `CompareCompanies(ctx, req)` | `CompareCompaniesAsync(req, ct)` |
| `POST /v1/person` | `standardizePerson(req)` | `StandardizePerson(ctx, req)` | `StandardizePersonAsync(req, ct)` |
| `POST /v1/person/compare` | `comparePersons(req)` | `ComparePersons(ctx, req)` | `ComparePersonsAsync(req, ct)` |
| `POST /v1/job-title` | `standardizeJobTitle(req)` | `StandardizeJobTitle(ctx, req)` | `StandardizeJobTitleAsync(req, ct)` |
| `POST /v1/email` | `standardizeEmail(req)` | `StandardizeEmail(ctx, req)` | `StandardizeEmailAsync(req, ct)` |
| `POST /v1/url` | `standardizeUrl(req)` | `StandardizeUrl(ctx, req)` | `StandardizeUrlAsync(req, ct)` |
| `POST /v1/social` | `standardizeSocial(req)` | `StandardizeSocial(ctx, req)` | `StandardizeSocialAsync(req, ct)` |
| `POST /v1/address` | `standardizeAddress(req)` | `StandardizeAddress(ctx, req)` | `StandardizeAddressAsync(req, ct)` |
| `POST /v1/standardize` | `standardize(req)` | `Standardize(ctx, req)` | `StandardizeAsync(req, ct)` |
| `POST /v1/explain` | `explain(req)` | `Explain(ctx, req)` | `ExplainAsync(req, ct)` |
| `POST /v1/compare` | `compare(req)` | `Compare(ctx, req)` | `CompareAsync(req, ct)` |
| `POST /v1/deduplicate` | `deduplicate(req)` | `Deduplicate(ctx, req)` | `DeduplicateAsync(req, ct)` |
| `POST /v1/batch` | `batch(req)` | `Batch(ctx, req)` | `BatchAsync(req, ct)` |
| `GET /v1/countries` | `listCountries()` | `ListCountries(ctx)` | `ListCountriesAsync(ct)` |
| `GET /v1/countries/{identifier}` | `getCountry(id)` | `GetCountry(ctx, id)` | `GetCountryAsync(id, ct)` |
