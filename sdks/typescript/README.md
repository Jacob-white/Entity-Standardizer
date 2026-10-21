# `@phone-standardizer/client` — TypeScript & React SDK

Typed client library, offline `formatAsYouType` formatter, and headless `PhoneInputController` for the Phone Standardizer microservice.

```ts
import { PhoneStandardizerClient, formatAsYouType, PhoneInputController } from "@phone-standardizer/client";

const client = new PhoneStandardizerClient({ baseUrl: "http://127.0.0.1:8000" });
const res = await client.standardize({ phone: "1-800-FLOWERS ext 104" });
console.log(res.e164); // "+18003569377"
```
