# `@phone-standardizer/client` — TypeScript & React SDK

Typed client library, offline `formatAsYouType` formatter, and headless `PhoneInputController` / `usePhoneInput()` React hook for the **Entity Standardizer** microservice.

## Quickstart

```ts
import {
  PhoneStandardizerClient,
  formatAsYouType,
  PhoneInputController,
} from "@phone-standardizer/client";

const client = new PhoneStandardizerClient({ baseUrl: "http://127.0.0.1:8000" });

// 1. Joint Multi-Pillar Contact Standardization
const contact = await client.standardizeContact({
  street1: "350 Fifth Ave Tel: 555-2368",
  city: "New York",
  postal_code: "10118",
  organization: "The Acme Holdings, Inc. /DE/",
  person_name: "Smith, Dr. Bob J.",
  email: "Bob.Smith+crm@gmial.com",
});
console.log(contact.phone.e164);                 // "+12125552368"
console.log(contact.organization?.company_key);  // "ACME HOLDINGS|INC"
console.log(contact.person?.person_root_key);    // "SMITH|ROBERT"

// 2. Standalone Phone, Company, Person, Address, Email & URL Standardization
const phone = await client.standardize({ phone: "1-800-FLOWERS ext 104" });
console.log(phone.e164); // "+18003569377"

const company = await client.standardizeCompany({ name: "KKR Opportunities III S.à r.l." });
console.log(company.legal_name); // "KKR OPPORTUNITIES III SARL"
```
