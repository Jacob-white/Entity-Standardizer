# `@phone-standardizer/client` — TypeScript & React SDK (`v2.1.0`)

Typed client library, offline `formatAsYouType` formatter, and headless `PhoneInputController` / `usePhoneInput()` React hook for the **Entity Standardizer** microservice (`phone_standardizer.server:app`).

## Quickstart

```ts
import {
  PhoneStandardizerClient,
  formatAsYouType,
  PhoneInputController,
} from "@phone-standardizer/client";

const client = new PhoneStandardizerClient({ baseUrl: "http://127.0.0.1:8000" });

// 1. Joint Multi-Pillar Contact Standardization & Comparison
const contact = await client.standardizeContact({
  street1: "350 Fifth Ave Tel: 555-2368",
  city: "New York",
  postal_code: "10118",
  organization: "The Acme Holdings, Inc. /DE/",
  person_name: "Smith, Dr. Bob J.",
  job_title: "SVP & CCO",
  email: "Bob.Smith+crm@gmial.com",
});
console.log(contact.phone.e164);                 // "+12125552368"
console.log(contact.organization?.company_key);  // "ACME HOLDINGS|INC"
console.log(contact.person?.person_root_key);    // "SMITH|ROBERT"
console.log(contact.job_title?.normalized_title); // "SENIOR VICE PRESIDENT & CHIEF COMPLIANCE OFFICER"

const contactMatch = await client.compareContacts({
  contact_a: { organization: "Acme Holdings Inc", person: "Bob Smith", email: "bsmith@acme.com" },
  contact_b: { organization: "The Acme Holdings, Inc. /DE/", person: "Robert Smith", email: "bsmith+vip@acme.com" },
});
console.log(contactMatch.is_match, contactMatch.matched_pillars);

// 2. Standalone Organization, Person, Job Title, Email, URL, Social, Address & Phone
const company = await client.standardizeCompany({ name: "KKR Opportunities III S.à r.l." });
console.log(company.legal_name); // "KKR OPPORTUNITIES III SARL"

const companyCmp = await client.compareCompanies({
  company_a: "Pacific Investment Management Company LLC (PIMCO)",
  company_b: "PIMCO LLC",
});
console.log(companyCmp.is_match, companyCmp.match_type); // true, "ALIAS_MATCH"

const personCmp = await client.comparePersons({
  person_a: "Dr. Bob J. Smith, CFA",
  person_b: "Robert Smith",
});
console.log(personCmp.is_match, personCmp.match_type); // true, "ROOT_NAME_MATCH"

const title = await client.standardizeJobTitle({ title: "EVP & GC" });
console.log(title.normalized_title, title.is_executive); // "EXECUTIVE VICE PRESIDENT & GENERAL COUNSEL", true

const phone = await client.standardize({ phone: "1-800-FLOWERS ext 104" });
console.log(phone.e164); // "+18003569377"
```

## Available Client Methods

- `health()` — `GET /health`
- `standardizeContact(req)` — `POST /v1/contact`
- `compareContacts(req)` — `POST /v1/contact/compare`
- `standardizeCompany(req)` — `POST /v1/company`
- `compareCompanies(req)` — `POST /v1/company/compare`
- `standardizePerson(req)` — `POST /v1/person`
- `comparePersons(req)` — `POST /v1/person/compare`
- `standardizeJobTitle(req)` — `POST /v1/job-title`
- `standardizeEmail(req)` — `POST /v1/email`
- `standardizeUrl(req)` — `POST /v1/url`
- `standardizeSocial(req)` — `POST /v1/social`
- `standardizeAddress(req)` — `POST /v1/address`
- `standardize(req)` — `POST /v1/standardize`
- `explain(req)` — `POST /v1/explain`
- `compare(req)` — `POST /v1/compare`
- `deduplicate(req)` — `POST /v1/deduplicate`
- `batch(req)` — `POST /v1/batch`
- `listCountries()` — `GET /v1/countries`
- `getCountry(identifier)` — `GET /v1/countries/{identifier}`
