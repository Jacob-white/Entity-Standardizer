# Entity Standardizer .NET SDK (`EntityStandardizer.Client` `v2.1.0`)

Typed async HTTP client for the **Entity Standardizer** microservice (`entity_standardizer.server:app`) targeting `net8.0` and `netstandard2.0`.

## Quickstart

```csharp
using System;
using System.Collections.Generic;
using System.Net.Http;
using EntityStandardizer.Client;

using var http = new HttpClient();
var client = new EntityStandardizerClient("http://127.0.0.1:8000", http);

// 1. Joint Multi-Pillar Contact Standardization & Comparison
var contact = await client.StandardizeContactAsync(new ContactStandardizeRequest
{
    Street1 = "350 Fifth Ave Tel: 555-2368",
    City = "New York",
    PostalCode = "10118",
    Organization = "The Acme Holdings, Inc. /DE/",
    PersonName = "Smith, Dr. Bob J.",
    JobTitle = "SVP & CCO",
    Email = "Bob.Smith+crm@gmial.com",
});
Console.WriteLine(contact.Phone.E164);                 // "+12125552368"
Console.WriteLine(contact.Organization?.CompanyKey);   // "ACME HOLDINGS|INC"
Console.WriteLine(contact.Person?.PersonRootKey);      // "SMITH|ROBERT"

var contactMatch = await client.CompareContactsAsync(new ContactCompareRequest
{
    ContactA = new Dictionary<string, object?> { ["organization"] = "Acme Holdings Inc", ["person"] = "Bob Smith" },
    ContactB = new Dictionary<string, object?> { ["organization"] = "The Acme Holdings, Inc. /DE/", ["person"] = "Robert Smith" },
});
Console.WriteLine($"{contactMatch.IsMatch} ({string.Join(", ", contactMatch.MatchedPillars)})");

// 2. Standalone Organization, Person, Job Title & Phone Operations
var company = await client.StandardizeCompanyAsync(new CompanyStandardizeRequest
{
    Name = "KKR Opportunities III S.à r.l.",
});
Console.WriteLine(company.LegalName); // "KKR OPPORTUNITIES III SARL"

var companyCmp = await client.CompareCompaniesAsync(new CompanyCompareRequest
{
    CompanyA = "Pacific Investment Management Company LLC (PIMCO)",
    CompanyB = "PIMCO LLC",
});
Console.WriteLine($"{companyCmp.IsMatch}: {companyCmp.MatchType}"); // True: ALIAS_MATCH

var personCmp = await client.ComparePersonsAsync(new PersonCompareRequest
{
    PersonA = "Dr. Bob J. Smith, CFA",
    PersonB = "Robert Smith",
});
Console.WriteLine($"{personCmp.IsMatch}: {personCmp.MatchType}"); // True: ROOT_NAME_MATCH

var title = await client.StandardizeJobTitleAsync(new JobTitleStandardizeRequest
{
    Title = "EVP & GC",
});
Console.WriteLine($"{title.NormalizedTitle} (Exec={title.IsExecutive})");

var phone = await client.StandardizeAsync(new PhoneStandardizeRequest
{
    Phone = "1-800-FLOWERS ext 104",
});
Console.WriteLine(phone.E164); // "+18003569377"
```
