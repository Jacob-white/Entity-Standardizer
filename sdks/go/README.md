# Entity Standardizer Go SDK (`phonestandardizer` `v2.1.0`)

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
	client := phonestandardizer.NewClient("http://127.0.0.1:8000")

	// 1. Joint Multi-Pillar Contact Standardization & Comparison
	contact, _ := client.StandardizeContact(ctx, phonestandardizer.ContactStandardizeRequest{
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

	contactMatch, _ := client.CompareContacts(ctx, phonestandardizer.ContactCompareRequest{
		ContactA: map[string]any{"organization": "Acme Holdings Inc", "person": "Bob Smith"},
		ContactB: map[string]any{"organization": "The Acme Holdings, Inc. /DE/", "person": "Robert Smith"},
	})
	fmt.Println(contactMatch.IsMatch, contactMatch.MatchedPillars)

	// 2. Standalone Organization, Person, Job Title & Phone Operations
	company, _ := client.StandardizeCompany(ctx, phonestandardizer.CompanyStandardizeRequest{
		Name: "KKR Opportunities III S.à r.l.",
	})
	fmt.Println(*company.LegalName) // "KKR OPPORTUNITIES III SARL"

	companyCmp, _ := client.CompareCompanies(ctx, phonestandardizer.CompanyCompareRequest{
		CompanyA: "Pacific Investment Management Company LLC (PIMCO)",
		CompanyB: "PIMCO LLC",
	})
	fmt.Println(companyCmp.IsMatch, companyCmp.MatchType) // true, "ALIAS_MATCH"

	personCmp, _ := client.ComparePersons(ctx, phonestandardizer.PersonCompareRequest{
		PersonA: "Dr. Bob J. Smith, CFA",
		PersonB: "Robert Smith",
	})
	fmt.Println(personCmp.IsMatch, personCmp.MatchType) // true, "ROOT_NAME_MATCH"

	title, _ := client.StandardizeJobTitle(ctx, phonestandardizer.JobTitleStandardizeRequest{
		Title: "EVP & GC",
	})
	fmt.Println(*title.NormalizedTitle, title.IsExecutive) // "EXECUTIVE VICE PRESIDENT & GENERAL COUNSEL", true

	phone, _ := client.Standardize(ctx, phonestandardizer.PhoneStandardizeRequest{
		Phone: "1-800-FLOWERS ext 104",
	})
	fmt.Println(*phone.E164) // "+18003569377"
}
```
