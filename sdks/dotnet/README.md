# Entity Standardizer .NET SDK (`PhoneStandardizer.Client`)

Typed async HTTP client for the **Entity Standardizer** microservice (`phone_standardizer.server:app`) targeting `net8.0` and `netstandard2.0`.

## Quickstart

```csharp
using System;
using System.Net.Http;
using PhoneStandardizer.Client;

using var http = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:8000") };
var client = new PhoneStandardizerClient(http);

// 1. Joint Multi-Pillar Contact Standardization
var contact = await client.StandardizeContactAsync(new ContactStandardizeRequest(
    Street1: "350 Fifth Ave Tel: 555-2368",
    City: "New York",
    PostalCode: "10118",
    Organization: "The Acme Holdings, Inc. /DE/"
));
Console.WriteLine(contact.Phone.E164);                 // "+12125552368"
Console.WriteLine(contact.Organization?.CompanyKey);   // "ACME HOLDINGS|INC"

// 2. Standalone Phone & Company Standardization
var phone = await client.StandardizeAsync(new PhoneStandardizeRequest("1-800-FLOWERS ext 104"));
Console.WriteLine(phone.E164); // "+18003569377"
```
