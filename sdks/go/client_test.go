package entitystandardizer

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func strPtr(s string) *string {
	return &s
}

func TestClientStandardizeAndBatch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/health":
			_ = json.NewEncoder(w).Encode(HealthResponse{Status: "ok", Version: "2.1.0"})
			return
		case "/ready":
			_ = json.NewEncoder(w).Encode(ReadyResponse{Status: "ready", Version: "2.1.0", NativeAvailable: true})
			return
		case "/v1/standardize":
			_ = json.NewEncoder(w).Encode(StandardizedPhone{
				RawInput:    "(415) 555-2671",
				E164:        strPtr("+14155552671"),
				National:    strPtr("(415) 555-2671"),
				CountryISO2: strPtr("US"),
				RegionCode:  strPtr("CA"),
				Extension:   nil,
				IsValid:     true,
				IsPossible:  true,
				Confidence:  1.0,
				RoutingTier: "AUTO_PASS",
			})
			return
		case "/v1/batch":
			_ = json.NewEncoder(w).Encode(BatchResponse{
				Count: 1,
				Results: []StandardizedPhone{
					{E164: strPtr("+14155552671"), IsValid: true},
				},
			})
			return
		case "/v1/explain":
			_ = json.NewEncoder(w).Encode(PhoneExplainReport{
				Record: StandardizedPhone{E164: strPtr("+14155552671"), IsValid: true},
				Intelligence: PhoneIntelligence{
					Locality:      strPtr("San Francisco, CA"),
					Timezones:     []string{"America/Los_Angeles"},
					IsCallableNow: true,
					LocalHours:    []int{10},
				},
				Explanation: PhoneExplanation{
					Confidence:  1.0,
					RoutingTier: "AUTO_PASS",
				},
			})
			return
		case "/v1/compare":
			_ = json.NewEncoder(w).Encode(PhoneComparisonResult{
				IsExactMatch:    true,
				IsFuzzyMatch:    true,
				SimilarityScore: 1.0,
				MatchType:       "EXACT_MATCH",
			})
			return
		case "/v1/deduplicate":
			_ = json.NewEncoder(w).Encode(DeduplicateResponse{
				ClusterCount: 1,
				Clusters: []PhoneCluster{
					{ClusterID: "PHONE-CLUSTER-0001", GoldenPhone: StandardizedPhone{E164: strPtr("+14155552671")}},
				},
			})
			return
		case "/v1/countries/US":
			_ = json.NewEncoder(w).Encode(CountryDialPlan{
				ISO2:        "US",
				CallingCode: "1",
			})
			return
		case "/v1/countries":
			_ = json.NewEncoder(w).Encode(ListCountriesResponse{
				Count:     249,
				Countries: []CountryDialPlan{{ISO2: "US", CallingCode: "1"}},
			})
			return
		case "/v1/address":
			_ = json.NewEncoder(w).Encode(StandardizedAddress{
				Street1:              "350 5TH AVE",
				City:                 "NEW YORK",
				State:                "NY",
				PostalCode:           "10118",
				Country:              "USA",
				NormalizedAddressKey: strPtr("350 5TH AVE|NEW YORK|NY|10118|USA"),
				BuildingKey:          strPtr("350 5TH AVE|NEW YORK|NY|10118|USA"),
				PhoneticKey:          strPtr("350|F130|N620|NY|10118"),
				AddressStatus:        "standardized",
				RawStreetAddress:     "350 Fifth Ave",
				IsUS:                 true,
			})
			return
		case "/v1/address/compare":
			_ = json.NewEncoder(w).Encode(AddressComparisonResult{
				IsMatch:   true,
				Score:     1.0,
				MatchType: "EXACT_ADDRESS_KEY",
			})
			return
		case "/v1/address/deduplicate":
			_ = json.NewEncoder(w).Encode(AddressDeduplicateResponse{
				ClusterCount: 1,
				Clusters:     []AddressCluster{{ClusterID: 1, Confidence: 0.99}},
			})
			return
		case "/v1/address/autocomplete":
			_ = json.NewEncoder(w).Encode(AddressAutocompleteResponse{
				Count:       1,
				Suggestions: []AutocompleteSuggestion{{Street1: "1600 PENNSYLVANIA AVE NW", Score: 0.99}},
			})
			return
		case "/v1/company":
			_ = json.NewEncoder(w).Encode(StandardizedCompany{
				RawInput:    "Acme Holdings, Inc.",
				LegalName:   strPtr("ACME HOLDINGS INC"),
				BaseName:    strPtr("ACME HOLDINGS"),
				BrandStem:   strPtr("ACME"),
				LegalSuffix: strPtr("INC"),
				IsValid:     true,
				Confidence:  0.98,
			})
			return
		case "/v1/company/compare":
			_ = json.NewEncoder(w).Encode(CompanyComparisonResult{
				IsMatch:   true,
				Score:     1.0,
				MatchType: "EXACT_COMPANY_KEY",
				CompanyA:  StandardizedCompany{LegalName: strPtr("ACME HOLDINGS INC"), IsValid: true},
				CompanyB:  StandardizedCompany{LegalName: strPtr("ACME HOLDINGS INC"), IsValid: true},
			})
			return
		case "/v1/company/deduplicate":
			_ = json.NewEncoder(w).Encode(CompanyDeduplicateResponse{
				ClusterCount: 1,
				Clusters:     []CompanyCluster{{ClusterID: "COMPANY-CLUSTER-0001"}},
			})
			return
		case "/v1/person":
			_ = json.NewEncoder(w).Encode(StandardizedPerson{
				RawInput:      "Dr. Bob Smith",
				Salutation:    strPtr("DR"),
				FirstName:     strPtr("BOB"),
				RootFirstName: strPtr("ROBERT"),
				LastName:      strPtr("SMITH"),
				IsValid:       true,
				Confidence:    0.98,
			})
			return
		case "/v1/person/compare":
			_ = json.NewEncoder(w).Encode(PersonComparisonResult{
				IsMatch:   true,
				Score:     0.96,
				MatchType: "ROOT_NAME_MATCH",
				PersonA:   StandardizedPerson{RootFirstName: strPtr("ROBERT"), LastName: strPtr("SMITH"), IsValid: true},
				PersonB:   StandardizedPerson{RootFirstName: strPtr("ROBERT"), LastName: strPtr("SMITH"), IsValid: true},
			})
			return
		case "/v1/person/deduplicate":
			_ = json.NewEncoder(w).Encode(PersonDeduplicateResponse{
				ClusterCount: 1,
				Clusters:     []PersonCluster{{ClusterID: "PERSON-CLUSTER-0001"}},
			})
			return
		case "/v1/job-title":
			_ = json.NewEncoder(w).Encode(StandardizedJobTitle{
				RawInput:        "CCO",
				NormalizedTitle: strPtr("CHIEF COMPLIANCE OFFICER"),
				SeniorityLevel:  strPtr("C_SUITE"),
				Department:      strPtr("LEGAL"),
				IsExecutive:     true,
				IsValid:         true,
				Confidence:      0.96,
			})
			return
		case "/v1/email":
			_ = json.NewEncoder(w).Encode(StandardizedEmail{
				RawInput:  "jane@acme.com",
				Email:     strPtr("jane@acme.com"),
				Domain:    strPtr("acme.com"),
				EmailType: strPtr("CORPORATE"),
				IsValid:   true,
			})
			return
		case "/v1/email/compare":
			_ = json.NewEncoder(w).Encode(EmailComparisonResult{
				IsMatch:   true,
				Score:     1.0,
				MatchType: "EXACT_EMAIL_KEY",
			})
			return
		case "/v1/url":
			_ = json.NewEncoder(w).Encode(StandardizedUrl{
				RawInput:  "https://www.acme.com",
				URL:       strPtr("https://acme.com"),
				Domain:    strPtr("acme.com"),
				BrandStem: strPtr("ACME"),
				IsValid:   true,
			})
			return
		case "/v1/url/compare":
			_ = json.NewEncoder(w).Encode(UrlComparisonResult{
				IsMatch:   true,
				Score:     1.0,
				MatchType: "EXACT_URL_KEY",
			})
			return
		case "/v1/social":
			_ = json.NewEncoder(w).Encode(StandardizedSocial{
				RawInput: "https://twitter.com/openai",
				Platform: strPtr("X"),
				Handle:   strPtr("openai"),
				URL:      strPtr("https://x.com/openai"),
				IsValid:  true,
			})
			return
		case "/v1/contact":
			_ = json.NewEncoder(w).Encode(StandardizedContact{
				Address: StandardizedAddress{
					Street1:       "350 5TH AVE",
					City:          "NEW YORK",
					State:         "NY",
					PostalCode:    "10118",
					Country:       "USA",
					AddressStatus: "standardized",
					IsUS:          true,
				},
				Phone: StandardizedPhone{
					RawInput: "555-2368",
					E164:     strPtr("+12125552368"),
					IsValid:  true,
				},
				EntityKey:           strPtr("350 5TH AVE|NEW YORK|NY|10118|USA||+12125552368"),
				CrossHealingActions: []string{"PHONE_HEALED_FROM_STANDARDIZED_ADDRESS"},
				OverallConfidence:   0.97,
			})
			return
		case "/v1/contact/compare":
			_ = json.NewEncoder(w).Encode(ContactComparisonResult{
				IsMatch:        true,
				Score:          0.98,
				MatchType:      "MULTI_PILLAR_MATCH",
				MatchedPillars: []string{"organization", "phone"},
				PillarScores:   map[string]float64{"organization": 1.0, "phone": 1.0},
			})
			return
		case "/v1/contact/cluster":
			_ = json.NewEncoder(w).Encode(ContactClusterResponse{
				ClusterCount: 1,
				Clusters:     []ContactCluster{{ClusterID: "CONTACT-CLUSTER-0001"}},
			})
			return
		case "/v1/contact/batch":
			_ = json.NewEncoder(w).Encode(ContactBatchResponse{
				Count:   1,
				Results: []StandardizedContact{{OverallConfidence: 0.97}},
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	client := NewClient(srv.URL)
	health, err := client.Health(context.Background())
	if err != nil || health.Status != "ok" || health.Version != "2.1.0" {
		t.Fatalf("unexpected health response: %+v, err=%v", health, err)
	}
	ready, err := client.Ready(context.Background())
	if err != nil || ready.Status != "ready" || !ready.NativeAvailable {
		t.Fatalf("unexpected ready response: %+v, err=%v", ready, err)
	}
	res, err := client.Standardize(context.Background(), PhoneStandardizeRequest{
		Phone: "(415) 555-2671",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if res.E164 == nil || *res.E164 != "+14155552671" || !res.IsValid || res.Extension != nil {
		t.Fatalf("unexpected result: %+v", res)
	}

	batchRes, err := client.Batch(context.Background(), PhoneBatchRequest{
		Phones: []string{"(415) 555-2671"},
	})
	if err != nil {
		t.Fatalf("unexpected batch error: %v", err)
	}
	if batchRes.Count != 1 {
		t.Fatalf("unexpected batch count: %d", batchRes.Count)
	}

	expRes, err := client.Explain(context.Background(), PhoneStandardizeRequest{Phone: "(415) 555-2671"})
	if err != nil || expRes.Intelligence.Locality == nil || *expRes.Intelligence.Locality != "San Francisco, CA" {
		t.Fatalf("unexpected explain result: %+v, err=%v", expRes, err)
	}

	cmpRes, err := client.Compare(context.Background(), PhoneCompareRequest{
		PhoneA: "(415) 555-2671",
		PhoneB: "+14155552671",
	})
	if err != nil || !cmpRes.IsExactMatch {
		t.Fatalf("unexpected compare result: %+v, err=%v", cmpRes, err)
	}

	dedupRes, err := client.Deduplicate(context.Background(), PhoneDeduplicateRequest{
		Phones: []string{"415-555-2671", "+14155552671"},
	})
	if err != nil || dedupRes.ClusterCount != 1 {
		t.Fatalf("unexpected deduplicate result: %+v, err=%v", dedupRes, err)
	}

	countryRes, err := client.GetCountry(context.Background(), "US")
	if err != nil || countryRes.CallingCode != "1" {
		t.Fatalf("unexpected country result: %+v, err=%v", countryRes, err)
	}

	listRes, err := client.ListCountries(context.Background())
	if err != nil || listRes.Count != 249 {
		t.Fatalf("unexpected list countries result: %+v, err=%v", listRes, err)
	}

	addrRes, err := client.StandardizeAddress(context.Background(), AddressStandardizeRequest{
		Street1:    "350 Fifth Ave",
		City:       "New York",
		State:      "NY",
		PostalCode: "10118",
	})
	if err != nil || addrRes.Street1 != "350 5TH AVE" || !addrRes.IsUS {
		t.Fatalf("unexpected address result: %+v, err=%v", addrRes, err)
	}

	addrCmpRes, err := client.CompareAddresses(context.Background(), AddressCompareRequest{
		AddressA: "350 Fifth Ave, New York, NY 10118",
		AddressB: "350 5th Ave, New York, NY 10118",
	})
	if err != nil || !addrCmpRes.IsMatch || addrCmpRes.MatchType != "EXACT_ADDRESS_KEY" {
		t.Fatalf("unexpected compare addresses result: %+v, err=%v", addrCmpRes, err)
	}

	addrDedupRes, err := client.DeduplicateAddresses(context.Background(), AddressDeduplicateRequest{
		Addresses: []any{"350 Fifth Ave, New York, NY 10118"},
	})
	if err != nil || addrDedupRes.ClusterCount != 1 {
		t.Fatalf("unexpected deduplicate addresses result: %+v, err=%v", addrDedupRes, err)
	}

	autoRes, err := client.AutocompleteAddress(context.Background(), AddressAutocompleteRequest{
		Prefix: "1600 Penn",
	})
	if err != nil || autoRes.Count != 1 {
		t.Fatalf("unexpected autocomplete address result: %+v, err=%v", autoRes, err)
	}

	compRes, err := client.StandardizeCompany(context.Background(), CompanyStandardizeRequest{
		Name: "Acme Holdings, Inc.",
	})
	if err != nil || compRes.BrandStem == nil || *compRes.BrandStem != "ACME" {
		t.Fatalf("unexpected company result: %+v, err=%v", compRes, err)
	}

	compCmpRes, err := client.CompareCompanies(context.Background(), CompanyCompareRequest{
		CompanyA: "Acme Holdings, Inc.",
		CompanyB: "ACME HOLDINGS INC /DE/",
	})
	if err != nil || !compCmpRes.IsMatch || compCmpRes.MatchType != "EXACT_COMPANY_KEY" {
		t.Fatalf("unexpected compare companies result: %+v, err=%v", compCmpRes, err)
	}

	compDedupRes, err := client.DeduplicateCompanies(context.Background(), CompanyDeduplicateRequest{
		Companies: []string{"Acme Holdings, Inc."},
	})
	if err != nil || compDedupRes.ClusterCount != 1 {
		t.Fatalf("unexpected deduplicate companies result: %+v, err=%v", compDedupRes, err)
	}

	perRes, err := client.StandardizePerson(context.Background(), PersonStandardizeRequest{
		Name: "Dr. Bob Smith",
	})
	if err != nil || perRes.RootFirstName == nil || *perRes.RootFirstName != "ROBERT" {
		t.Fatalf("unexpected person result: %+v, err=%v", perRes, err)
	}

	perCmpRes, err := client.ComparePersons(context.Background(), PersonCompareRequest{
		PersonA: "Dr. Bob Smith",
		PersonB: "Robert Smith",
	})
	if err != nil || !perCmpRes.IsMatch || perCmpRes.MatchType != "ROOT_NAME_MATCH" {
		t.Fatalf("unexpected compare persons result: %+v, err=%v", perCmpRes, err)
	}

	perDedupRes, err := client.DeduplicatePersons(context.Background(), PersonDeduplicateRequest{
		Persons: []string{"Dr. Bob Smith"},
	})
	if err != nil || perDedupRes.ClusterCount != 1 {
		t.Fatalf("unexpected deduplicate persons result: %+v, err=%v", perDedupRes, err)
	}

	titleRes, err := client.StandardizeJobTitle(context.Background(), JobTitleStandardizeRequest{
		Title: "CCO",
	})
	if err != nil || !titleRes.IsExecutive || titleRes.NormalizedTitle == nil || *titleRes.NormalizedTitle != "CHIEF COMPLIANCE OFFICER" {
		t.Fatalf("unexpected job title result: %+v, err=%v", titleRes, err)
	}

	emailRes, err := client.StandardizeEmail(context.Background(), EmailStandardizeRequest{
		Email: "jane@acme.com",
	})
	if err != nil || emailRes.Email == nil || *emailRes.Email != "jane@acme.com" {
		t.Fatalf("unexpected email result: %+v, err=%v", emailRes, err)
	}

	emailCmpRes, err := client.CompareEmails(context.Background(), EmailCompareRequest{
		EmailA: "jane.doe+work@gmail.com",
		EmailB: "janedoe@gmail.com",
	})
	if err != nil || !emailCmpRes.IsMatch {
		t.Fatalf("unexpected compare emails result: %+v, err=%v", emailCmpRes, err)
	}

	urlRes, err := client.StandardizeUrl(context.Background(), UrlStandardizeRequest{
		URL: "https://www.acme.com",
	})
	if err != nil || urlRes.Domain == nil || *urlRes.Domain != "acme.com" {
		t.Fatalf("unexpected url result: %+v, err=%v", urlRes, err)
	}

	urlCmpRes, err := client.CompareUrls(context.Background(), UrlCompareRequest{
		URLA: "https://www.acme.com",
		URLB: "https://acme.com",
	})
	if err != nil || !urlCmpRes.IsMatch {
		t.Fatalf("unexpected compare urls result: %+v, err=%v", urlCmpRes, err)
	}

	socRes, err := client.StandardizeSocial(context.Background(), SocialStandardizeRequest{
		Profile: "https://twitter.com/openai",
	})
	if err != nil || socRes.Platform == nil || *socRes.Platform != "X" {
		t.Fatalf("unexpected social result: %+v, err=%v", socRes, err)
	}

	contactRes, err := client.StandardizeContact(context.Background(), ContactStandardizeRequest{
		Street1:    "350 Fifth Ave",
		City:       "New York",
		PostalCode: "10118",
		Phone:      "555-2368",
	})
	if err != nil || contactRes.Phone.E164 == nil || *contactRes.Phone.E164 != "+12125552368" || contactRes.Address.State != "NY" {
		t.Fatalf("unexpected contact result: %+v, err=%v", contactRes, err)
	}

	contactCmpRes, err := client.CompareContacts(context.Background(), ContactCompareRequest{
		ContactA: map[string]any{"organization": "Acme Holdings, Inc.", "phone": "+12125552368"},
		ContactB: map[string]any{"organization": "ACME HOLDINGS INC", "phone": "212-555-2368"},
	})
	if err != nil || !contactCmpRes.IsMatch || contactCmpRes.MatchType != "MULTI_PILLAR_MATCH" {
		t.Fatalf("unexpected compare contacts result: %+v, err=%v", contactCmpRes, err)
	}

	contactClusterRes, err := client.ClusterContacts(context.Background(), ContactClusterRequest{
		Records: []map[string]any{{"phone": "+12125552368"}},
	})
	if err != nil || contactClusterRes.ClusterCount != 1 {
		t.Fatalf("unexpected cluster contacts result: %+v, err=%v", contactClusterRes, err)
	}

	contactBatchRes, err := client.BatchStandardizeContacts(context.Background(), ContactBatchRequest{
		Contacts: []map[string]any{{"street1": "350 Fifth Ave", "postal_code": "10118", "phone": "555-2368"}},
	})
	if err != nil || contactBatchRes.Count != 1 {
		t.Fatalf("unexpected batch standardize contacts result: %+v, err=%v", contactBatchRes, err)
	}
}
