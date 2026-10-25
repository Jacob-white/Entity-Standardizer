# Entity Standardizer Go SDK (`phonestandardizer`)

Zero-dependency Go client for the **Entity Standardizer** HTTP service (`phone_standardizer.server:app`).

## Quickstart

```go
package main

import (
	"context"
	"fmt"
	"github.com/Jacob-white/Phone-Standardizer/sdks/go"
)

func main() {
	client := phonestandardizer.NewClient("http://127.0.0.1:8000")

	// 1. Joint Multi-Pillar Contact Standardization
	street := "350 Fifth Ave Tel: 555-2368"
	city := "New York"
	zip := "10118"
	org := "The Acme Holdings, Inc. /DE/"
	contact, _ := client.StandardizeContact(context.Background(), phonestandardizer.ContactStandardizeRequest{
		Street1:      &street,
		City:         &city,
		PostalCode:   &zip,
		Organization: &org,
	})
	fmt.Println(*contact.Phone.E164)               // "+12125552368"
	fmt.Println(*contact.Organization.CompanyKey)  // "ACME HOLDINGS|INC"

	// 2. Standalone Phone & Company Standardization
	phone, _ := client.Standardize(context.Background(), phonestandardizer.StandardizeRequest{
		Phone: "1-800-FLOWERS ext 104",
	})
	fmt.Println(*phone.E164) // "+18003569377"
}
```
