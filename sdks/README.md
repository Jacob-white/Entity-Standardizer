# Entity Standardizer — Multi-Platform Client SDKs 🌐

Official client SDKs and OpenAPI 3.1 contracts for integrating the **Entity Standardizer** HTTP microservice (`phone_standardizer.server:app`) and browser-side React `<PhoneInput />` component across polyglot enterprise stacks:

- **[TypeScript / React (`sdks/typescript`)](typescript/README.md)** — Typed client (`@phone-standardizer/client`), offline `formatAsYouType` formatter, and headless `PhoneInputController` / `usePhoneInput()` React hook.
- **[.NET 8 / C# (`sdks/dotnet`)](dotnet/README.md)** — `PhoneStandardizer.Client` targeting `net8.0` and `netstandard2.0`.
- **[Go (`sdks/go`)](go/README.md)** — Zero-dependency `phonestandardizer` client package.

---

## Supported Client Operations Across All SDKs

Every SDK is continuously contract-tested against the Python dataclasses via [`tests/test_sdk_contract.py`](../tests/test_sdk_contract.py) and supports:
1. **Joint Multi-Pillar Contact Standardization (`/v1/contact`)** — `standardizeContact` / `StandardizeContact` / `StandardizeContactAsync`
2. **Organization / Company Standardization (`/v1/company`)** — `standardizeCompany` / `StandardizeCompany` / `StandardizeCompanyAsync`
3. **Person Standardization (`/v1/person`)** — `standardizePerson` / `StandardizePerson` / `StandardizePersonAsync`
4. **Email, Website URL & Social Standardization (`/v1/email`, `/v1/url`, `/v1/social`)** — `standardizeEmail`, `standardizeUrl`, `standardizeSocial`
5. **Physical Address Standardization (`/v1/address`)** — `standardizeAddress` / `StandardizeAddress` / `StandardizeAddressAsync`
6. **Telephone Standardization, Explainability, Comparison & Deduplication (`/v1/standardize`, `/v1/explain`, `/v1/compare`, `/v1/deduplicate`, `/v1/batch`, `/v1/countries`)**
