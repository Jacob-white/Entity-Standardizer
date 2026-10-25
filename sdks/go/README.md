# Entity Standardizer Go SDK (`entitystandardizer` `v2.1.0`)

Zero-dependency Go client for the **Entity Standardizer** HTTP service (`entity_standardizer.server:app`).

## Quickstart

```go
package main

import (
	"context"
	"fmt"
	"github.com/Jacob-white/Entity-Standardizer/sdks/go"
)

func main() {
	ctx := context.Background()
	client := entitystandardizer.NewClient("http://127.0.0.1:8000")

	// 1. Joint Multi-Pillar Contact Standardization & Comparison
	contact, _ := client.StandardizeContact(ctx, entitystandardizer.ContactStandardizeRequest{
		Street1:      "350 Fifth Ave Tel: 555-2368",
		City:         "New York",
		PostalCode:   "10118",
		Organization: "The Acme Holdings, Inc. /DE/",
		PersonName:   "Smith, Dr. Bob J.",
		JobTitle:     "SVP & CCO",
		Email:        "Bob.Smith+crm@gmial.com",
	})
	fmt.Println(*contact.Phone.E164)              // "+12125552368"
	fmt.Println(*contact.Organization.CompanyKey) // "ACME HOLDINGS|INC"
	fmt.Println(*contact.Person.PersonRootKey)    // "SMITH|ROBERT"

	contactMatch, _ := client.CompareContacts(ctx, entitystandardizer.ContactCompareRequest{
		ContactA: map[string]any{"organization": "Acme Holdings Inc", "person": "Bob Smith"},
		ContactB: map[string]any{"organization": "The Acme Holdings, Inc. /DE/", "person": "Robert Smith"},
	})
	fmt.Println(contactMatch.IsMatch, contactMatch.MatchedPillars)

	// 2. Standalone Organization, Person, Job Title & Phone Operations
	company, _ := client.StandardizeCompany(ctx, entitystandardizer.CompanyStandardizeRequest{
		Name: "KKR Opportunities III S.à r.l.",
	})
	fmt.Println(*company.LegalName) // "KKR OPPORTUNITIES III SARL"

	companyCmp, _ := client.CompareCompanies(ctx, entitystandardizer.CompanyCompareRequest{
		CompanyA: "Pacific Investment Management Company LLC (PIMCO)",
		CompanyB: "PIMCO LLC",
	})
	fmt.Println(companyCmp.IsMatch, companyCmp.MatchType) // true, "ALIAS_MATCH"

	personCmp, _ := client.ComparePersons(ctx, entitystandardizer.PersonCompareRequest{
		PersonA: "Dr. Bob J. Smith, CFA",
		PersonB: "Robert Smith",
	})
	fmt.Println(personCmp.IsMatch, personCmp.MatchType) // true, "ROOT_NAME_MATCH"

	title, _ := client.StandardizeJobTitle(ctx, entitystandardizer.JobTitleStandardizeRequest{
		Title: "EVP & GC",
	})
	fmt.Println(*title.NormalizedTitle, title.IsExecutive) // "EXECUTIVE VICE PRESIDENT & GENERAL COUNSEL", true

	phone, _ := client.Standardize(ctx, entitystandardizer.PhoneStandardizeRequest{
		Phone: "1-800-FLOWERS ext 104",
	})
	fmt.Println(*phone.E164) // "+18003569377"
}
```

## Available Client Methods (29 Operations)

- `Health(ctx)` — `GET /health`
- `Ready(ctx)` — `GET /ready`
- `StandardizeContact(ctx, req)` — `POST /v1/contact`
- `CompareContacts(ctx, req)` — `POST /v1/contact/compare`
- `ClusterContacts(ctx, req)` — `POST /v1/contact/cluster`
- `BatchStandardizeContacts(ctx, req)` — `POST /v1/contact/batch`
- `StandardizeCompany(ctx, req)` — `POST /v1/company`
- `CompareCompanies(ctx, req)` — `POST /v1/company/compare`
- `DeduplicateCompanies(ctx, req)` — `POST /v1/company/deduplicate`
- `StandardizePerson(ctx, req)` — `POST /v1/person`
- `ComparePersons(ctx, req)` — `POST /v1/person/compare`
- `DeduplicatePersons(ctx, req)` — `POST /v1/person/deduplicate`
- `StandardizeJobTitle(ctx, req)` — `POST /v1/job-title`
- `StandardizeEmail(ctx, req)` — `POST /v1/email`
- `CompareEmails(ctx, req)` — `POST /v1/email/compare`
- `StandardizeUrl(ctx, req)` — `POST /v1/url`
- `CompareUrls(ctx, req)` — `POST /v1/url/compare`
- `StandardizeSocial(ctx, req)` — `POST /v1/social`
- `StandardizeAddress(ctx, req)` — `POST /v1/address`
- `CompareAddresses(ctx, req)` — `POST /v1/address/compare`
- `DeduplicateAddresses(ctx, req)` — `POST /v1/address/deduplicate`
- `AutocompleteAddress(ctx, req)` — `POST /v1/address/autocomplete`
- `Standardize(ctx, req)` — `POST /v1/standardize`
- `Explain(ctx, req)` — `POST /v1/explain`
- `Compare(ctx, req)` — `POST /v1/compare`
- `Deduplicate(ctx, req)` — `POST /v1/deduplicate`
- `Batch(ctx, req)` — `POST /v1/batch`
- `ListCountries(ctx)` — `GET /v1/countries`
- `GetCountry(ctx, identifier)` — `GET /v1/countries/{identifier}`

